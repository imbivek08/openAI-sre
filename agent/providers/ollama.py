"""Ollama local inference provider (OpenAI-compatible chat API)."""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel

from agent.providers.base import (
    ModelProvider,
    ProviderError,
    TransientProviderError,
    extract_tool_calls,
    parse_structured,
)
from agent.schemas import ProviderResponse, ToolCallRequest

logger = logging.getLogger(__name__)


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        tool_calling: bool = True,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.tool_calling = tool_calling
        self.max_retries = max_retries
        self.supports_tool_calling = tool_calling
        self.supports_structured_output = True  # via JSON fallback / format param

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        use_tools = bool(tools and self.tool_calling)
        if use_tools:
            payload["tools"] = tools
        elif response_schema is not None:
            # Ask for JSON matching the schema; validated deterministically below.
            payload["format"] = "json"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            except httpx.TimeoutException as exc:
                last_error = TransientProviderError(f"Ollama timeout: {exc}")
            except httpx.HTTPError as exc:
                last_error = TransientProviderError(f"Ollama connection error: {exc}")
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = TransientProviderError(f"Ollama HTTP {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ProviderError(f"Ollama HTTP {resp.status_code}: {resp.text[:500]}")
                else:
                    return self._parse_response(resp.json(), response_schema, use_tools)
            logger.warning("Ollama attempt %d failed: %s", attempt + 1, last_error)
        raise last_error or ProviderError("Ollama provider failed")

    def _parse_response(
        self, data: dict, response_schema: type[BaseModel] | None, use_tools: bool
    ) -> ProviderResponse:
        message = data.get("message", {}) or {}
        content = message.get("content") or ""
        tool_calls: list[ToolCallRequest] | None = None

        if use_tools:
            raw_calls = message.get("tool_calls") or []
            tool_calls = [
                ToolCallRequest(
                    tool_name=fn["function"]["name"],
                    arguments=_safe_json_loads(fn["function"].get("arguments", "{}")),
                )
                for fn in raw_calls
                if isinstance(fn, dict) and "function" in fn
            ]
            if not tool_calls and content.strip():
                # Some models emit tool-call syntax in content instead.
                tool_calls = extract_tool_calls(content) or None
        elif response_schema is not None:
            parsed = parse_structured(content, response_schema)
            content = parsed.model_dump_json()

        usage = data.get("usage") or {}
        return ProviderResponse(
            content=content or None,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            },
            raw_finish_reason=data.get("done_reason"),
        )


def _safe_json_loads(text: str) -> dict:
    import json

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
