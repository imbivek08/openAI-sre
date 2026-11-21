"""Model-provider abstraction shared by all inference backends."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, ValidationError

from agent.schemas import ProviderResponse, ToolCallRequest

logger = logging.getLogger(__name__)

MAX_STRUCTURED_RETRIES = 2


class ProviderError(Exception):
    """Raised when the provider fails in a non-retryable way."""


class TransientProviderError(Exception):
    """Raised for retryable failures (timeouts, 429, 5xx)."""


class ModelProvider(ABC):
    name: str = "abstract"
    supports_tool_calling: bool = False
    supports_structured_output: bool = False

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        """Run one completion request.

        Implementations must return tool_calls when the model requests tools,
        or content (ideally schema-valid JSON when response_schema is set).
        """


def parse_structured(content: str, schema: type[BaseModel]) -> BaseModel:
    """Deterministically parse and validate model output against a schema.

    Accepts raw JSON or a fenced ```json block. Raises ProviderError when the
    content cannot be parsed into a valid instance — never returns partial data.
    """
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop fences and optional language tag
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Model output is not valid JSON: {exc}") from exc
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise ProviderError(f"Model output does not match schema: {exc}") from exc


def extract_tool_calls(content: str) -> list[ToolCallRequest]:
    """Parse tool calls from a model response for providers without native tool calling.

    Expected format (one or more blocks):
        <tool_call>
        {"tool_name": "...", "arguments": {...}}
        </tool_call>
    """
    calls: list[ToolCallRequest] = []
    marker = "<tool_call>"
    end_marker = "</tool_call>"
    idx = 0
    while True:
        start = content.find(marker, idx)
        if start == -1:
            break
        end = content.find(end_marker, start)
        if end == -1:
            break
        payload = content[start + len(marker) : end].strip()
        try:
            data = json.loads(payload)
            calls.append(ToolCallRequest(tool_name=data["tool_name"], arguments=data.get("arguments", {})))
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("Ignoring unparseable tool_call block from model")
        idx = end + len(end_marker)
    return calls
