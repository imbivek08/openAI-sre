"""Model-provider factory."""

from __future__ import annotations

import logging

from agent.providers.base import ModelProvider
from agent.providers.hosted import HostedProvider
from agent.providers.ollama import OllamaProvider
from api.config import get_settings

logger = logging.getLogger(__name__)


def build_provider() -> ModelProvider | None:
    """Build the configured provider, or None when unconfigured.

    Returns None (rather than a fake provider) when no model is configured —
    the API then returns a clear configuration error for investigation
    requests instead of a fabricated diagnosis.
    """
    settings = get_settings()
    if not settings.llm_configured:
        logger.info("No LLM provider configured; investigations are disabled")
        return None
    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            tool_calling=settings.llm_tool_calling,
        )
    if settings.llm_provider == "hosted":
        return HostedProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            tool_calling=settings.llm_tool_calling,
        )
    logger.warning("Unknown LLM provider %r", settings.llm_provider)
    return None
