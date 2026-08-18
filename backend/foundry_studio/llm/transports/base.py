"""ProviderTransport ABC — the seam between provider-specific HTTP and canonical types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from foundry_studio.llm.base import StreamChunk
    from foundry_studio.llm.types import Usage


class ProviderTransport(ABC):
    """Abstract transport that converts between provider-native formats and the
    canonical :class:`~foundry_studio.llm.base.StreamChunk` / :class:`NormalizedResponse`
    types.

    Each transport targets one API surface (OpenAI chat/completions, Anthropic
    messages, …).  The :class:`~foundry_studio.llm.registry.LLMRegistry` holds
    one transport instance per configured provider; callers always go through
    a transport, never directly through httpx /aiohttp.
    """

    @property
    @abstractmethod
    def api_mode(self) -> str:
        """Identifier of this transport's API surface, e.g. ``"chat_completions"``
        or ``"anthropic_messages"``.  Used for transport selection and for
        logging / telemetry.
        """

    # ------------------------------------------------------------------ #
    # Message / tool conversion                                          #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def convert_messages(self, messages: list[dict]) -> any:
        """Convert a list of ``{role, content}`` dicts to the provider-native
        message format.

        The input always follows the OpenAI shape (``role`` + ``content``);
        the output is whatever the provider's API expects.
        """

    @abstractmethod
    def convert_tools(self, tools: list[dict]) -> any:
        """Convert a list of OpenAI tool schemas to the provider-native format.

        Returns the provider-specific tools payload (list, dict, or None if
        the provider doesn't support tools).
        """

    # ------------------------------------------------------------------ #
    # Streaming                                                          #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        **opts,
    ) -> AsyncIterator["StreamChunk"]:
        """Stream chunks from the provider.

        Yields :class:`~foundry_studio.llm.base.StreamChunk` objects
        with ``type`` in ``{"text", "usage", "finish"}`` plus
        ``tool_call`` chunks for providers that surface tool calls in-stream.

        Subclasses MUST:
        - Handle retries internally (up to their configured policy).
        - Raise :class:`~foundry_studio.llm.base.LLMError` on non-retryable failures.
        - Yield a final ``finish`` chunk even on abnormal stream termination.
        """

    # ------------------------------------------------------------------ #
    # One-shot                                                            #
    # ------------------------------------------------------------------ #

    @abstractmethod
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
        """Convenience: collect the full text from :meth:`stream`.

        Default implementation accumulates ``text`` chunks and returns the
        joined string.  Providers that have a non-streaming API route may
        override this with a more efficient implementation.
        """
