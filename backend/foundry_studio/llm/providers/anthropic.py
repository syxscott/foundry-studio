"""Anthropic Messages API provider.

Supports the Anthropic /v1/messages endpoint and any API gateway that speaks
the same protocol (e.g. Kimi's Anthropic-compatible endpoint, DouBao Seed
/api/compatible, PackyCode, 火山方舟, …).  The key differences from
OpenAI-compatible providers are:

- Endpoint: ``{base_url}/v1/messages`` (not /chat/completions)
- Auth header: ``x-api-key`` (not Authorization: Bearer)
- Required: ``max_tokens`` in every request
- Streaming: SSE with ``event:`` prefixes (not bare ``data:`` lines)
- Streaming events: content_block_delta / message_delta / message_stop
  (not OpenAI's choices[0].delta)

The API key is never stored in config — only the environment-variable name
(credential-ref) is, resolved on each request.
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
    normalizeApiKey,
    rootCauseMessage,
)

# Anthropic SSE event types
_ANTHROPIC_STREAMING_EVENTS = frozenset([
    "content_block_start",
    "content_block_delta",
    "content_block_stop",
    "message_delta",
    "message_stop",
    "ping",
])


class AnthropicProvider(BaseLLMProvider):
    """Streaming Messages API client for Anthropic-compatible endpoints."""

    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str | None = None,
        api_key_env: str = "",
        model: str | None = None,
        models: list[str] | None = None,
        default_max_tokens: int = 4096,
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
        self.default_max_tokens = default_max_tokens
        self.timeout = float(timeout)
        self.retry = max(0, int(retry))
        self.backoff = backoff or BackoffConfig(max_retries=self.retry)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/v1/messages"

    def _resolve_key(self, api_key: str | None = None) -> str | None:
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
        key = self._resolve_key(api_key)
        headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "accept": "text/event-stream",
        }
        if key:
            headers["x-api-key"] = key
        return headers

    def _payload(
        self,
        messages: list[dict],
        model: str | None,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        payload: dict = {
            "model": model or self.model or "claude-sonnet-4-20250514",
            "messages": list(messages),
            "stream": True,
            "max_tokens": max_tokens,
        }
        # Anthropic only respects temperature for non-reasoning models;
        # skip it for zero to keep the payload clean.
        if temperature > 0:
            payload["temperature"] = temperature
        return payload

    # ------------------------------------------------------------------ #
    # String-stream (backwards-compatible)
    # ------------------------------------------------------------------ #
    async def stream(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
        max_tokens: int | None = None,
        **opts,
    ) -> AsyncIterator[str]:
        async for chunk in self.stream_chunks(
            messages,
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_tokens=max_tokens,
            **opts,
        ):
            if chunk.type == "text" and chunk.text:
                yield chunk.text

    # ------------------------------------------------------------------ #
    # Typed stream chunks
    # ------------------------------------------------------------------ #
    async def stream_chunks(
        self,
        messages: Iterable[dict],
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
        max_tokens: int | None = None,
        **opts,
    ) -> AsyncIterator[StreamChunk]:
        import httpx

        # Coerce messages to plain list (consume the iterable once)
        msgs = _normalize_messages(messages)
        payload = self._payload(
            msgs,
            model,
            temperature,
            max_tokens or self.default_max_tokens,
        )
        headers = self._headers(api_key=api_key)
        attempts = self.backoff.max_retries + 1
        last_err: BaseException | None = None
        last_err_code: str = LLMError.UNKNOWN

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream(
                        "POST",
                        self.endpoint,
                        json=payload,
                        headers=headers,
                    ) as resp:
                        if resp.status_code != 200:
                            body = await resp.aread()
                            err = LLMError.from_http(
                                resp.status_code, _safe_text(body)
                            )
                            if (
                                self.backoff.is_retryable(err.code)
                                and attempt + 1 < attempts
                            ):
                                last_err = err
                                last_err_code = err.code
                                await asyncio.sleep(
                                    self.backoff.delay_for_attempt(attempt)
                                )
                                continue
                            raise err

                        usage = TokenUsage()
                        finish = FinishReason.STOP
                        emitted_finish = False
                        current_event = ""

                        async for raw_line in resp.aiter_lines():
                            line = raw_line.strip()
                            if not line:
                                continue
                            if line.startswith("event: "):
                                current_event = line[7:].strip()
                                continue
                            if not line.startswith("data: "):
                                continue

                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break

                            chunk_data: dict
                            try:
                                chunk_data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            # Skip non-streaming event types
                            if current_event not in _ANTHROPIC_STREAMING_EVENTS:
                                continue

                            if current_event == "content_block_delta":
                                delta = chunk_data.get("delta", {})
                                if delta.get("type") == "text":
                                    text = delta.get("text", "")
                                    if text:
                                        yield StreamChunk(type="text", text=text)

                            elif current_event == "message_delta":
                                delta_usage = chunk_data.get("usage", {})
                                if delta_usage:
                                    usage += TokenUsage(
                                        input_tokens=delta_usage.get(
                                            "input_tokens", 0
                                        )
                                        or 0,
                                        output_tokens=delta_usage.get(
                                            "output_tokens", 0
                                        )
                                        or 0,
                                    )
                                stop_reason = chunk_data.get("stop_reason", "")
                                if stop_reason == "end_turn":
                                    finish = FinishReason.STOP
                                elif stop_reason == "max_tokens":
                                    finish = FinishReason.LENGTH
                                elif stop_reason == "stop_sequence":
                                    finish = FinishReason.STOP
                                else:
                                    finish = FinishReason.UNKNOWN

                            elif current_event == "message_stop":
                                if usage.input_tokens or usage.output_tokens:
                                    yield StreamChunk(type="usage", usage=usage)
                                yield StreamChunk(
                                    type="finish", finish_reason=finish
                                )
                                emitted_finish = True
                                return

                # Provider closed without explicit message_stop
                if not emitted_finish:
                    if usage.input_tokens or usage.output_tokens:
                        yield StreamChunk(type="usage", usage=usage)
                    yield StreamChunk(type="finish", finish_reason=FinishReason.STOP)
                return

            except LLMError as exc:
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
                chain_hint = ""
                if exc.cause is not None:
                    chain_hint = f" (root: {rootCauseMessage(exc.cause)})"
                raise LLMError(
                    exc.code,
                    f"{self.name} request failed: {exc.message}{chain_hint}",
                    status=exc.status,
                    cause=exc.cause,
                ) from exc

            except Exception as exc:  # noqa: BLE001
                last_err = exc
                last_err_code = LLMError.TRANSPORT
                if attempt + 1 < attempts:
                    await asyncio.sleep(
                        self.backoff.delay_for_attempt(attempt)
                    )
                    continue
                raise LLMError(
                    LLMError.TRANSPORT,
                    f"{self.name} request failed: {rootCauseMessage(exc)}",
                    cause=exc,
                ) from exc

        # Exhausted retries
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


def _normalize_messages(messages: Iterable[dict]) -> list[dict]:
    """Normalise arbitrary message dicts to Anthropic {role, content} shape."""
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


def _safe_text(body: bytes) -> str:
    try:
        return body.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""
