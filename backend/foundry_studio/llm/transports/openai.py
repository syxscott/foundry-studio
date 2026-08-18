"""OpenAI-compatible /chat/completions transport.

Handles OpenAI, DeepSeek, vLLM, OpenRouter, Ollama — any server that
implements the ``POST /chat/completions`` SSE protocol.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from foundry_studio.llm import LLMError
from foundry_studio.llm.base import BackoffConfig, FinishReason, StreamChunk, normalizeApiKey, rootCauseMessage
from foundry_studio.llm.types import Usage
from foundry_studio.llm.transports.base import ProviderTransport

if TYPE_CHECKING:
    pass

_API_MODE = "chat_completions"

_FINISH_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.CONTENT_FILTER,
    "tool_calls": FinishReason.TOOL_CALLS,
}


def register() -> None:
    from foundry_studio.llm.transports import register_transport

    register_transport(_API_MODE, OpenAITransport)


class OpenAITransport(ProviderTransport):
    """Streaming chat/completions client for any OpenAI-compatible server."""

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key_env: str = "",
        model: str | None = None,
        models: list[str] | None = None,
        timeout: float = 60.0,
        retry: int = 2,
        backoff: BackoffConfig | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.model = model
        self.models = models or []
        self.timeout = float(timeout)
        self.retry = max(0, int(retry))
        self.backoff = backoff or BackoffConfig(max_retries=self.retry)

    @property
    def api_mode(self) -> str:
        return _API_MODE

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _resolve_key(self, api_key: str | None) -> str | None:
        if api_key:
            return normalizeApiKey(api_key)
        if not self.api_key_env:
            return None
        raw = os.environ.get(self.api_key_env, "")
        if not raw or not raw.strip():
            raise LLMError(
                LLMError.MISSING_CREDENTIAL,
                f"no API key for provider '{self.name}'; set env var {self.api_key_env}",
            )
        return normalizeApiKey(raw)

    def _headers(self, api_key: str | None) -> dict:
        headers: dict = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        key = self._resolve_key(api_key)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    def convert_messages(self, messages: list[dict]) -> list[dict]:
        """Pass-through: OpenAI already uses {role, content} shape."""
        return list(messages)

    def convert_tools(self, tools: list[dict]) -> list[dict] | None:
        """Pass-through: OpenAI tool schemas are already in the right format."""
        if not tools:
            return None
        return list(tools)

    def _build_payload(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        model: str | None,
        temperature: float,
    ) -> dict:
        payload: dict = {
            "model": model or self.model or "gpt-4o",
            "messages": self.convert_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = self.convert_tools(tools)
            payload["tool_choice"] = "auto"
        return payload

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        **opts,
    ) -> AsyncIterator[StreamChunk]:
        import httpx

        payload = self._build_payload(messages, tools, model, temperature)
        headers = self._headers(api_key)
        usage = Usage()
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
                            err = LLMError.from_http(resp.status_code, _safe_text(body))
                            if self.backoff.is_retryable(err.code) and attempt + 1 < attempts:
                                last_err = err
                                last_err_code = err.code
                                await asyncio.sleep(self.backoff.delay_for_attempt(attempt))
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
                                chunk = _json.loads(data)
                            except _json.JSONDecodeError:
                                continue

                            chunk_usage = chunk.get("usage")
                            if chunk_usage:
                                usage += Usage(
                                    input_tokens=int(chunk_usage.get("prompt_tokens", 0) or 0),
                                    output_tokens=int(chunk_usage.get("completion_tokens", 0) or 0),
                                    cached_tokens=int(chunk_usage.get("cached_tokens", 0) or 0),
                                )

                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            finish_raw = choice.get("finish_reason")
                            if finish_raw is not None:
                                finish = _FINISH_MAP.get(finish_raw, FinishReason.UNKNOWN)
                            delta = choice.get("delta") or {}

                            # Tool call deltas arrive inside the delta object
                            tool_call = delta.get("tool_calls") or []
                            for tc in tool_call:
                                tc_id = tc.get("id")
                                tc_name = tc.get("function", {}).get("name", "")
                                tc_args = tc.get("function", {}).get("arguments", "")
                                if tc_id or tc_name:
                                    yield StreamChunk(
                                        type="tool_call",
                                        tool_call_id=tc_id or None,
                                        tool_call_name=tc_name,
                                        tool_call_arguments=tc_args,
                                    )

                            content = delta.get("content")
                            if content:
                                yield StreamChunk(type="text", text=content)

                if usage.input_tokens or usage.output_tokens:
                    yield StreamChunk(type="usage", usage=usage)
                yield StreamChunk(type="finish", finish_reason=finish or FinishReason.STOP)
                emitted_finish = True
                return

            except LLMError as exc:
                if self.backoff.is_retryable(exc.code) and attempt + 1 < attempts:
                    last_err = exc
                    last_err_code = exc.code
                    await asyncio.sleep(self.backoff.delay_for_attempt(attempt))
                    continue
                chain_hint = f" (root: {rootCauseMessage(exc.cause)})" if exc.cause else ""
                raise LLMError(
                    exc.code,
                    f"{self.name} request failed: {exc.message}{chain_hint}",
                    status=exc.status,
                    cause=exc.cause,
                ) from exc
            except Exception as exc:
                last_err = exc
                last_err_code = LLMError.TRANSPORT
                if attempt + 1 < attempts:
                    await asyncio.sleep(self.backoff.delay_for_attempt(attempt))
                    continue
                raise LLMError(
                    LLMError.TRANSPORT,
                    f"{self.name} request failed: {rootCauseMessage(exc)}",
                    cause=exc,
                ) from exc

        if last_err is None:
            raise LLMError(LLMError.UNKNOWN, f"{self.name} request failed without an error")
        raise LLMError(
            last_err_code,
            f"{self.name} request failed after {attempts} attempts: {rootCauseMessage(last_err)}",
            cause=last_err,
        )

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        **opts,
    ) -> str:
        parts: list[str] = []
        async for chunk in self.stream(
            messages, tools, api_key=api_key, model=model, temperature=temperature, **opts
        ):
            if chunk.type == "text" and chunk.text:
                parts.append(chunk.text)
        return "".join(parts)


def _safe_text(body: bytes) -> str:
    try:
        return body.decode("utf-8", "replace")
    except Exception:
        return ""


# Auto-register on import
register()
