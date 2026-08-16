"""LLM provider abstraction for foundry-studio.

Mirrors the spirit of deepseek-harness's provider model, adapted to Python:

- A :class:`BaseLLMProvider` is an adapter that turns a message list into a
  token stream.
- Credentials are referenced by *environment-variable name* (a credential-ref)
  and resolved per request; secrets are never stored in config.
- Failures normalize to stable :class:`LLMError` codes so callers never have to
  parse vendor-specific error text.
- ``errorChain()`` walks ``__cause__`` / ``__context__`` to expose the real
  transport-level root cause (undici's ``TypeError: fetch failed`` masks
  the actual ECONNREFUSED, so callers see "could not resolve host" /
  "connection refused" without instrumenting every layer).
- ``normalizeApiKey()`` rejects whitespace, control characters, and
  non-printable bytes up front so a typo'd env var never reaches the wire.
- :class:`BackoffConfig` adds exponential delay + jitter + a retryable
  code allow-list so the provider's retry loop no longer blindly re-issues
  on every transient error.
- :class:`StreamChunk` / :class:`TokenUsage` / :class:`FinishReason` give
  callers a typed view of the stream, not just text deltas.
"""

from __future__ import annotations

import random
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from enum import Enum


class LLMError(Exception):
    """Normalized LLM failure carrying a stable, vendor-free machine code."""

    AUTH = "AUTH"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    CONTEXT_WINDOW = "CONTEXT_WINDOW"
    INVALID_REQUEST = "INVALID_REQUEST"
    SERVER = "SERVER"
    TIMEOUT = "TIMEOUT"
    TRANSPORT = "TRANSPORT"
    ABORTED = "ABORTED"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
    UNKNOWN = "UNKNOWN"

    _VALID = {
        AUTH,
        RATE_LIMIT,
        QUOTA,
        CONTEXT_WINDOW,
        INVALID_REQUEST,
        SERVER,
        TIMEOUT,
        TRANSPORT,
        ABORTED,
        MISSING_CREDENTIAL,
        UNKNOWN,
    }

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        if code not in self._VALID:
            code = self.UNKNOWN
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.cause = cause

    @classmethod
    def from_http(cls, status: int, body: str | None = None) -> LLMError:
        message = (body or "").strip() or f"provider returned HTTP {status}"
        return cls(cls._http_code(status, body or ""), message, status=status)

    @staticmethod
    def _http_code(status: int, body: str) -> str:
        if status in (401, 403):
            return LLMError.AUTH
        if status == 429:
            return LLMError.RATE_LIMIT
        if status == 400:
            low = body.lower()
            if "maximum context" in low or "context length" in low or "context window" in low:
                return LLMError.CONTEXT_WINDOW
            return LLMError.INVALID_REQUEST
        if status >= 500:
            return LLMError.SERVER
        return f"HTTP_{status}"


def errorChain(exc: BaseException | None) -> list[BaseException]:
    """Walk the ``__cause__`` / ``__context__`` chain and return every link.

    Python's standard traceback tail doesn't always show the wrapped
    exception: undici, for example, raises ``TypeError: fetch failed``
    whose ``__cause__`` is the real :class:`ConnectionError`. Surfacing
    the whole chain lets the planner / log lines tell the user
    "connect ECONNREFUSED" instead of the misleading "fetch failed".

    Also follows an explicit ``cause`` attribute (the convention used by
    :class:`LLMError`) when the Python-level ``__cause__`` link isn't
    set (e.g. when the wrapping happens programmatically, not via
    ``raise X from Y``).
    """
    chain: list[BaseException] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        chain.append(cur)
        nxt = cur.__cause__ or cur.__context__
        if nxt is cur:
            break
        # Fall back to an explicit ``cause`` attribute for exceptions
        # that wrap their trigger without using ``raise ... from ...``.
        if nxt is None:
            attr_cause = getattr(cur, "cause", None)
            if isinstance(attr_cause, BaseException) and id(attr_cause) not in seen:
                nxt = attr_cause
        cur = nxt
    return chain


def rootCauseMessage(exc: BaseException | None) -> str:
    """Return a single human-readable line for the deepest cause in the chain.

    Falls back to ``str(exc)`` when no wrapped cause is present.
    """
    chain = errorChain(exc)
    return f"{type(chain[-1]).__name__}: {chain[-1]}" if chain else ""


# API key sanity check: OpenAI / DeepSeek / most vendors use printable
# ASCII tokens.  Reject whitespace, control chars, and non-ASCII bytes up
# front so a misconfigured env var (newline copy-paste, ``export FOO=$' '``,
# etc.) fails locally instead of getting bounced by the provider as a
# 401 with no useful detail.
_API_KEY_PRINTABLE = re.compile(r"^[\x21-\x7E]+$")


def normalizeApiKey(raw: str | None) -> str:
    """Validate and return a stripped API key, or raise :class:`LLMError`.

    The check is intentionally lenient: it accepts any printable ASCII
    string (matches every major provider's format) and only rejects
    tokens that contain whitespace, control characters, or non-ASCII
    bytes — which are always configuration errors.
    """
    if raw is None:
        raise LLMError(
            LLMError.MISSING_CREDENTIAL, "no API key provided"
        )
    stripped = raw.strip()
    if not stripped:
        raise LLMError(
            LLMError.MISSING_CREDENTIAL, "API key is empty"
        )
    if not _API_KEY_PRINTABLE.match(stripped):
        raise LLMError(
            LLMError.MISSING_CREDENTIAL,
            "API key contains whitespace, control characters, or non-ASCII bytes",
        )
    return stripped


@dataclass(frozen=True)
class TokenUsage:
    """Token accounting for one request.

    Different providers report slightly different shapes; we keep the three
    fields the OpenAI / Anthropic / DeepSeek / vLLM families all agree on.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )

    def __iadd__(self, other: TokenUsage) -> TokenUsage:
        return self.__add__(other)


class FinishReason(str, Enum):  # noqa: UP042 - str+Enum keeps members as plain str
    """Why the model stopped producing tokens.

    Mirrors the union OpenAI / Anthropic / DeepSeek expose (different
    spellings, same semantics).  Unrecognized vendor values are mapped
    to :attr:`UNKNOWN` at the provider boundary.
    """
    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class StreamChunk:
    """One frame in the typed streaming protocol.

    ``type`` discriminates the payload:
    - ``"text"`` carries a single text delta (``text`` set).
    - ``"usage"`` carries token accounting (``usage`` set).
    - ``"finish"`` carries the final stop reason (``finish_reason`` set).
    """
    type: str  # "text" | "usage" | "finish"
    text: str | None = None
    usage: TokenUsage | None = None
    finish_reason: FinishReason | None = None


@dataclass
class BackoffConfig:
    """Retry policy for transient provider failures.

    Replaces the old ``retry: int`` knob.  Providers without an explicit
    :class:`BackoffConfig` get the ``default()`` policy: two retries,
    exponential delay 0.5s → 8s, ±30% jitter, only retrying the codes
    that are safe to retry.
    """
    max_retries: int = 2
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.3  # 0..1; ±30% of the computed delay
    retryable_codes: set[str] = field(
        default_factory=lambda: {
            LLMError.RATE_LIMIT,
            LLMError.SERVER,
            LLMError.TIMEOUT,
            LLMError.TRANSPORT,
        }
    )

    @classmethod
    def default(cls) -> BackoffConfig:
        return cls()

    def is_retryable(self, code: str) -> bool:
        return code in self.retryable_codes

    def delay_for_attempt(self, attempt: int) -> float:
        """Return the delay (seconds) to wait before ``attempt`` (0-indexed).

        ``attempt=0`` is the first retry (after the initial request failed).
        """
        raw = min(self.max_delay, self.base_delay * (2 ** attempt))
        if self.jitter > 0:
            spread = raw * self.jitter
            raw += random.uniform(-spread, spread)
        return max(0.0, raw)


def normalize_messages(messages: Iterable[dict]) -> list[dict]:
    """Coerce arbitrary message dicts into strict {role, content} pairs."""
    out: list[dict] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role is None or content is None:
            continue
        out.append({"role": str(role), "content": str(content)})
    return out


class BaseLLMProvider:
    """Streaming chat-completion adapter. Subclasses implement :meth:`stream`."""

    name: str = "base"
    base_url: str = ""

    async def stream(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        **opts,
    ) -> AsyncIterator[str]:
        """Yield text deltas (token strings) for the conversation.

        Backwards-compatible: this is the string-only iterator the planner
        and older callers use.  New code should prefer
        :meth:`stream_chunks` which exposes the typed
        :class:`StreamChunk` protocol (text + usage + finish reason).
        """
        raise NotImplementedError

    async def stream_chunks(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        **opts,
    ) -> AsyncIterator[StreamChunk]:
        """Yield typed :class:`StreamChunk` frames.

        Default implementation drops the typed protocol on top of
        :meth:`stream` and never yields a usage / finish chunk — providers
        that have richer stream data should override this.  The planner
        uses ``stream()``; the agent capabilities endpoint and any
        future telemetry path will use ``stream_chunks()``.
        """
        async for delta in self.stream(
            messages, model=model, temperature=temperature, **opts
        ):
            yield StreamChunk(type="text", text=delta)
        yield StreamChunk(type="finish", finish_reason=FinishReason.STOP)

    async def complete(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        **opts,
    ) -> str:
        """Convenience: collect the full completion text from :meth:`stream`."""
        parts: list[str] = []
        async for delta in self.stream(
            messages, model=model, temperature=temperature, **opts
        ):
            parts.append(delta)
        return "".join(parts)
