"""Hosted OpenAI-compatible provider (open-weight models via any compatible API).

Works with any endpoint implementing POST /chat/completions, e.g. OpenRouter
(open-weight models), vLLM, llama.cpp server, Together, Groq open-weight
endpoints. The exact model and endpoint are user-configured; no paid provider
is hardcoded.
"""

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


class HostedProvider(ModelProvider):
    name = "hosted"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout: float = 120.0,
        tool_calling: bool = True,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.tool_calling = tool_calling
        self.max_retries = max_retries
        self.supports_tool_calling = tool_calling
        self.supports_structured_output = True

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
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        use_tools = bool(tools and self.tool_calling)
        if use_tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        elif response_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                    )
            except httpx.TimeoutException as exc:
                last_error = TransientProviderError(f"Hosted provider timeout: {exc}")
            except httpx.HTTPError as exc:
                last_error = TransientProviderError(f"Hosted provider connection error: {exc}")
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = TransientProviderError(f"Hosted provider HTTP {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ProviderError(f"Hosted provider HTTP {resp.status_code}: {resp.text[:500]}")
                else:
                    return self._parse_response(resp.json(), response_schema, use_tools)
            logger.warning("Hosted provider attempt %d failed: %s", attempt + 1, last_error)
        raise last_error or ProviderError("Hosted provider failed")

    def _parse_response(
        self, data: dict, response_schema: type[BaseModel] | None, use_tools: bool
    ) -> ProviderResponse:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("Hosted provider returned no choices")
        message = choices[0].get("message", {}) or {}
        content = message.get("content") or ""
        tool_calls: list[ToolCallRequest] | None = None

        if use_tools:
            raw_calls = message.get("tool_calls") or []
            tool_calls = [
                ToolCallRequest(
                    tool_name=fn.get("function", {}).get("name", ""),
                    arguments=_safe_json_loads(fn.get("function", {}).get("arguments", "{}")),
                )
                for fn in raw_calls
                if fn.get("function", {}).get("name")
            ]
            if not tool_calls and content.strip():
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
            raw_finish_reason=(choices[0].get("finish_reason")),
        )


def _safe_json_loads(text: str) -> dict:
    import json

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
