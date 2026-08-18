"""Canonical types for the LLM layer — shared across all providers and transports."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A single tool invocation parsed from an LLM response."""

    id: str | None  # provider-assigned call ID (may be None for some providers)
    name: str  # e.g. "check_structure"
    arguments: str  # JSON string of the arguments


@dataclass
class Usage:
    """Token accounting for one request."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


@dataclass
class NormalizedResponse:
    """Provider-agnostic view of a streaming or one-shot LLM response.

    Every provider transport normalizes its provider-native response into
    this shape so callers (Planner, ToolAgent) never need to know which
    provider is underneath.
    """

    # Plain text content of the response. None when the response consists
    # entirely of tool calls.
    content: str | None = None
    # Parsed tool calls, if the model requested any.
    tool_calls: list[ToolCall] | None = None
    # Why the model stopped producing tokens.
    finish_reason: str = "stop"
    # Provider-native reasoning / thinking content (Anthropic, DeepSeek).
    reasoning: str | None = None
    # Token usage breakdown.
    usage: Usage | None = None
    # Provider-specific raw data kept for debugging/attribution.
    provider_data: dict | None = field(default_factory=dict)
