"""Provider registry + settings-driven construction.

A registry maps a provider name to a :class:`BaseLLMProvider` instance. The
single configured provider is built from :class:`foundry_studio.config.Settings`,
so configuration changes (base URL, credential-ref env var, default model) take
effect on the next request without a code change.
"""

from __future__ import annotations

import os

from foundry_studio.config import Settings
from foundry_studio.llm.base import BaseLLMProvider
from foundry_studio.llm.providers.openai_compat import OpenAICompatibleProvider


class LLMRegistry:
    """In-memory mapping of provider name -> provider instance."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseLLMProvider] = {}

    def register(self, name: str, provider: BaseLLMProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> BaseLLMProvider | None:
        return self._providers.get(name)

    def default_provider(self) -> BaseLLMProvider | None:
        if not self._providers:
            return None
        return next(iter(self._providers.values()))

    def __bool__(self) -> bool:
        return bool(self._providers)

    def summaries(self) -> list[dict]:
        """Per-provider status for the API (no secrets, only a key-present flag)."""
        out: list[dict] = []
        for name, p in self._providers.items():
            api_key_env = getattr(p, "api_key_env", "") or ""
            key_present = bool(api_key_env) and bool(
                os.environ.get(api_key_env, "").strip()
            )
            out.append(
                {
                    "name": name,
                    "base_url": p.base_url,
                    "model": getattr(p, "model", None),
                    "api_key_env": api_key_env,
                    "key_present": key_present,
                    "configured": bool(p.base_url),
                }
            )
        return out

    @classmethod
    def from_settings(cls, settings: Settings) -> LLMRegistry:
        reg = cls()
        provider = (settings.agent_llm_provider or "").strip()
        if not provider:
            return reg
        base_url = (settings.agent_llm_base_url or "").strip() or (
            OpenAICompatibleProvider.DEFAULT_BASE_URL
        )
        api_key_env = (settings.agent_llm_api_key_env or "").strip()
        reg.register(
            provider,
            OpenAICompatibleProvider(
                name=provider,
                base_url=base_url,
                api_key_env=api_key_env,
                model=(settings.agent_llm_model or None),
                models=list(settings.agent_llm_models or []),
                retry=int(settings.agent_llm_retry or 0),
                timeout=float(
                    getattr(settings, "agent_llm_timeout", 60.0) or 60.0
                ),
            ),
        )
        return reg


def build_registry(settings: Settings) -> LLMRegistry:
    """Convenience wrapper used by the planner and the API layer."""
    return LLMRegistry.from_settings(settings)
