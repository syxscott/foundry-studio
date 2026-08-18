"""LLM provider layer for foundry-studio.

Public surface: :class:`BaseLLMProvider`, :class:`LLMError`, :class:`LLMRegistry`
and :func:`build_registry`, plus the typed stream protocol
(:class:`StreamChunk`, :class:`TokenUsage`, :class:`FinishReason`), the
retry policy (:class:`BackoffConfig`), and the cause-chain helpers
(:func:`errorChain`, :func:`rootCauseMessage`, :func:`normalizeApiKey`),
the canonical types (:class:`ToolCall`, :class:`Usage`,
:class:`NormalizedResponse`), the transport layer (:class:`ProviderTransport`,
:func:`get_transport`), and the tool registry (:class:`ToolRegistry`).
"""

from __future__ import annotations

from foundry_studio.llm.base import (
    BackoffConfig,
    BaseLLMProvider,
    FinishReason,
    LLMError,
    StreamChunk,
    TokenUsage,
    errorChain,
    normalize_messages,
    normalizeApiKey,
    rootCauseMessage,
)
from foundry_studio.llm.registry import LLMRegistry, build_registry
from foundry_studio.llm.transports import ProviderTransport, get_transport
from foundry_studio.llm.types import NormalizedResponse, ToolCall, Usage

__all__ = [
    "BackoffConfig",
    "BaseLLMProvider",
    "FinishReason",
    "LLMError",
    "LLMRegistry",
    "NormalizedResponse",
    "ProviderTransport",
    "StreamChunk",
    "TokenUsage",
    "ToolCall",
    "Usage",
    "build_registry",
    "errorChain",
    "get_transport",
    "normalizeApiKey",
    "normalize_messages",
    "rootCauseMessage",
]

