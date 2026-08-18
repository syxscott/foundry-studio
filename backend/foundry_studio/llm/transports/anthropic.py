"""Anthropic Messages API transport.

Supports the Anthropic ``/v1/messages`` endpoint and any API gateway that
speaks the same protocol (Kimi, DouBao Seed, 火山方舟, …).
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

_API_MODE = "anthropic_messages"

_ANTHROPIC_STREAMING_EVENTS = frozenset([
    "content_block_start",
    "content_block_delta",
    "content_block_stop",
    "message_delta",
    "message_stop",
    "ping",
])


def register() -> None:
    from foundry_studio.llm.transports import register_transport

    register_transport(_API_MODE, AnthropicTransport)


class AnthropicTransport(ProviderTransport):
    """Streaming Messages API client for Anthropic-compatible endpoints."""

    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
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
        self.api_key_env = api_key_env
        self.model = model
        self.models = models or []
        self.default_max_tokens = default_max_tokens
        self.timeout = float(timeout)
        self.retry = max(0, int(retry))
        self.backoff = backoff or BackoffConfig(max_retries=self.retry)

    @property
    def api_mode(self) -> str:
        return _API_MODE

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
                f"no API key for provider '{self.name}'; set env var {self.api_key_env}",
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

    def convert_messages(self, messages: list[dict]) -> list[dict]:
        """OpenAI-style {role, content} → Anthropic ``{role, content}``."""
        out: list[dict] = []
        for m in messages:
            role = str(m.get("role") or "user")
            content = m.get("content") or ""
            # Map 'system' to Anthropic's system param is handled separately
            if role == "system":
                continue  # systems go in _payload as top-level field
            out.append({"role": role, "content": str(content)})
        return out

    def convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI tool schemas to Anthropic tool format.

        Anthropic expects: {name, description, input_schema: {...}}
        OpenAI uses:        {type, name, description, parameters: {...}}
        """
        anthropic_tools: list[dict] = []
        for tool in tools:
            # OpenAI tool schema shape
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    def _payload(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        model: str | None,
        temperature: float,
        max_tokens: int,
        system: str | None = None,
    ) -> dict:
        payload: dict = {
            "model": model or self.model,
            "messages": self.convert_messages(messages),
            "stream": True,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        if temperature > 0:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = self.convert_tools(tools)
        return payload

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        **opts,
    ) -> AsyncIterator[StreamChunk]:
        import httpx

        # Extract system message
        system_msgs = [m for m in messages if m.get("role") == "system"]
        system_content = "\n".join(m.get("content", "") or "" for m in system_msgs) or None
        non_system = [m for m in messages if m.get("role") != "system"]

        payload = self._payload(
            non_system,
            tools,
            model,
            temperature,
            max_tokens or self.default_max_tokens,
            system=system_content,
        )
        headers = self._headers(api_key)
        usage = Usage()
        finish = FinishReason.STOP
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
                                chunk_data = _json.loads(data_str)
                            except _json.JSONDecodeError:
                                continue

                            if current_event not in _ANTHROPIC_STREAMING_EVENTS:
                                continue

                            if current_event == "content_block_start":
                                block = chunk_data.get("block", {})
                                if block.get("type") == "cache_creation":
                                    cache_tokens = block.get("cache_created_input_tokens", 0)
                                    usage += Usage(cached_tokens=int(cache_tokens or 0))

                            elif current_event == "content_block_delta":
                                delta = chunk_data.get("delta", {})
                                delta_type = delta.get("type")

                                if delta_type == "text_delta":
                                    text = delta.get("text", "")
                                    if text:
                                        yield StreamChunk(type="text", text=text)

                                elif delta_type == "input_json_delta":
                                    # Partial JSON for tool use arguments
                                    partial = delta.get("partial_json", "")
                                    yield StreamChunk(
                                        type="tool_call",
                                        tool_call_id=None,
                                        tool_call_name="__partial__",
                                        tool_call_arguments=partial,
                                        is_partial=True,
                                    )

                            elif current_event == "message_delta":
                                delta_usage = chunk_data.get("usage", {})
                                if delta_usage:
                                    usage += Usage(
                                        input_tokens=delta_usage.get("input_tokens", 0) or 0,
                                        output_tokens=delta_usage.get("output_tokens", 0) or 0,
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
                                yield StreamChunk(type="finish", finish_reason=finish)
                                emitted_finish = True
                                return

                if not emitted_finish:
                    if usage.input_tokens or usage.output_tokens:
                        yield StreamChunk(type="usage", usage=usage)
                    yield StreamChunk(type="finish", finish_reason=FinishReason.STOP)
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
