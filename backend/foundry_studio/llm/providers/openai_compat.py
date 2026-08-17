"""OpenAI-compatible chat-completions provider.

One adapter covers every OpenAI-compatible endpoint — OpenAI, DeepSeek,
vLLM, OpenRouter, and Ollama's ``/v1`` surface — because they all speak the
same ``POST /chat/completions`` SSE protocol. The only differences are the
``base_url`` and the credential-ref env var, so a single class with per-instance
configuration is enough (exactly the "one adapter, many providers" shape from
deepseek-harness).

The API key is *never* stored in config: only the environment-variable name is,
and it is resolved on each request. For keyless endpoints (local Ollama) leave
``api_key_env`` empty.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Iterable

from foundry_studio.llm.base import (
    BackoffConfig,
    BaseLLMProvider,
    FinishReason,
    LLMError,
    StreamChunk,
    TokenUsage,
    normalize_messages,
    normalizeApiKey,
    rootCauseMessage,
)

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
    "tool_calls": FinishReason.TOOL_CALLS,
    "function_call": FinishReason.TOOL_CALLS,
}


class OpenAICompatibleProvider(BaseLLMProvider):
    """Streaming chat-completions client for any OpenAI-compatible server."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str | None = None,
        api_key_env: str = "",
        model: str | None = None,
        models: list[str] | None = None,
        timeout: float = 60.0,
        retry: int = 2,
        backoff: BackoffConfig | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key  # direct key (from request), overrides env
        self.api_key_env = api_key_env  # env-var name (from settings)
        self.model = model
        self.models = models or []
        self.timeout = float(timeout)
        self.retry = max(0, int(retry))
        self.backoff = backoff or BackoffConfig(max_retries=self.retry)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _resolve_key(self, api_key: str | None = None) -> str | None:
        # Priority: direct api_key (from request) > env var
        if api_key:
            return normalizeApiKey(api_key)
        if not self.api_key_env:
            return None
        raw = os.environ.get(self.api_key_env, "")
        if not raw or not raw.strip():
            raise LLMError(
                LLMError.MISSING_CREDENTIAL,
                f"no API key for provider '{self.name}'; set environment variable "
                f"{self.api_key_env}",
            )
        return normalizeApiKey(raw)

    def _headers(self, api_key: str | None = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        key = self._resolve_key(api_key)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def _payload(
        self, messages: list[dict], model: str | None, temperature: float
    ) -> dict:
        return {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

    # ------------------------------------------------------------------ #
    # Stream: text-only (backwards compatible)
    # ------------------------------------------------------------------ #
    async def stream(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
        **opts,
    ) -> AsyncIterator[str]:
        async for chunk in self.stream_chunks(
            messages, model=model, temperature=temperature, api_key=api_key, **opts
        ):
            if chunk.type == "text" and chunk.text:
                yield chunk.text

    # ------------------------------------------------------------------ #
    # Stream: typed (text + usage + finish)
    # ------------------------------------------------------------------ #
    async def stream_chunks(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
        **opts,
    ) -> AsyncIterator[StreamChunk]:
        import httpx

        payload = self._payload(normalize_messages(messages), model, temperature)
        headers = self._headers(api_key=api_key)
        usage = TokenUsage()
        finish = FinishReason.UNKNOWN
        emitted_finish = False
        attempts = self.backoff.max_retries + 1
        last_err: BaseException | None = None
        last_err_code: str = LLMError.UNKNOWN

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream(
                        "POST", self.endpoint, json=payload, headers=headers
                    ) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            err = LLMError.from_http(
                                resp.status_code, _safe_text(body)
                            )
                            # Only retry the codes the policy allows; an
                            # INVALID_REQUEST or AUTH never gets better
                            # with a second try.
                            if self.backoff.is_retryable(err.code) and attempt + 1 < attempts:
                                last_err = err
                                last_err_code = err.code
                                await asyncio.sleep(
                                    self.backoff.delay_for_attempt(attempt)
                                )
                                continue
                            raise err
                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data = line[len("data:") :].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            # Some providers (vLLM, OpenRouter) emit a
                            # top-level usage block on the final frame.
                            chunk_usage = chunk.get("usage")
                            if chunk_usage:
                                usage += TokenUsage(
                                    input_tokens=int(
                                        chunk_usage.get("prompt_tokens", 0) or 0
                                    ),
                                    output_tokens=int(
                                        chunk_usage.get("completion_tokens", 0) or 0
                                    ),
                                    cached_tokens=int(
                                        chunk_usage.get(
                                            "cached_tokens", 0
                                        )
                                        or 0
                                    ),
                                )
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            finish_raw = choice.get("finish_reason")
                            if finish_raw is not None:
                                finish = _FINISH_REASON_MAP.get(
                                    finish_raw, FinishReason.UNKNOWN
                                )
                            else:
                                finish = FinishReason.UNKNOWN
                            delta = (
                                (choice.get("delta") or {}).get("content")
                            )
                            if delta:
                                yield StreamChunk(type="text", text=delta)
                # Provider sent [DONE] or closed the stream without one.
                if usage.input_tokens or usage.output_tokens:
                    yield StreamChunk(type="usage", usage=usage)
                yield StreamChunk(
                    type="finish", finish_reason=finish or FinishReason.STOP
                )
                emitted_finish = True
                return
            except LLMError as exc:
                # Retryable + attempts left → back off and retry.
                if (
                    self.backoff.is_retryable(exc.code)
                    and attempt + 1 < attempts
                ):
                    last_err = exc
                    last_err_code = exc.code
                    await asyncio.sleep(
                        self.backoff.delay_for_attempt(attempt)
                    )
                    continue
                # Walk the cause chain to expose the real root error in the
                # user-facing message; LLMError.cause is set when we wrap a
                # transport exception, so the chain often has 2-3 entries.
                chain_hint = ""
                if exc.cause is not None:
                    chain_hint = f" (root: {rootCauseMessage(exc.cause)})"
                raise LLMError(
                    exc.code,
                    f"{self.name} request failed: {exc.message}{chain_hint}",
                    status=exc.status,
                    cause=exc.cause,
                ) from exc
            except Exception as exc:  # noqa: BLE001 - normalize transport errors
                last_err = exc
                last_err_code = LLMError.TRANSPORT
                if attempt + 1 < attempts:
                    await asyncio.sleep(
                        self.backoff.delay_for_attempt(attempt)
                    )
                    continue
                # Final attempt: surface the deepest cause in the chain so
                # "fetch failed" becomes "ConnectionError: ECONNREFUSED".
                raise LLMError(
                    LLMError.TRANSPORT,
                    f"{self.name} request failed: {rootCauseMessage(exc)}",
                    cause=exc,
                ) from exc
            finally:
                # If the inner block returns without ever emitting a finish
                # chunk (e.g. a provider that doesn't send a final frame),
                # `emitted_finish` ensures we only emit once.  The function
                # returns explicitly above, so this is a no-op in practice.
                _ = emitted_finish
        # Loop exhausted: emit the most recent error with its root cause.
        if last_err is None:
            raise LLMError(
                LLMError.UNKNOWN,
                f"{self.name} request failed without an error",
            )
        raise LLMError(
            last_err_code,
            f"{self.name} request failed after {attempts} attempts: "
            f"{rootCauseMessage(last_err)}",
            cause=last_err,
        )


def _safe_text(body: bytes) -> str:
    try:
        return body.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
