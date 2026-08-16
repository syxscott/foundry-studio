"""LLM provider layer for foundry-studio.

Public surface: :class:`BaseLLMProvider`, :class:`LLMError`, :class:`LLMRegistry`
and :func:`build_registry`, plus the typed stream protocol
(:class:`StreamChunk`, :class:`TokenUsage`, :class:`FinishReason`), the
retry policy (:class:`BackoffConfig`), and the cause-chain helpers
(:func:`errorChain`, :func:`rootCauseMessage`, :func:`normalizeApiKey`).
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

__all__ = [
    "BackoffConfig",
    "BaseLLMProvider",
    "FinishReason",
    "LLMError",
    "LLMRegistry",
    "StreamChunk",
    "TokenUsage",
    "build_registry",
    "errorChain",
    "normalizeApiKey",
    "normalize_messages",
    "rootCauseMessage",
]
