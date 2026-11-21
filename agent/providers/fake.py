"""Deterministic fake provider for tests and offline development.

Not used in production paths. Lets the full investigation loop be tested
without any model installed.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from agent.providers.base import ModelProvider
from agent.schemas import ProviderResponse, ToolCallRequest


class ScriptedProvider(ModelProvider):
    """Replays a scripted list of responses.

    Each script entry is either:
      - {"tool_name": ..., "arguments": {...}}  -> a tool call
      - {"report": {...}}                        -> final report dict
      - {"content": "..."}                      -> raw content (parsed as report JSON)
    """

    name = "scripted"
    supports_tool_calling = True
    supports_structured_output = True

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.index = 0
        self.calls_made: list[ToolCallRequest] = []

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        if self.index >= len(self.script):
            raise RuntimeError("ScriptedProvider script exhausted")
        step = self.script[self.index]
        self.index += 1
        if "tool_name" in step:
            call = ToolCallRequest(tool_name=step["tool_name"], arguments=step.get("arguments", {}))
            self.calls_made.append(call)
            return ProviderResponse(content=None, tool_calls=[call])
        if "report" in step:
            return ProviderResponse(content=json.dumps(step["report"]))
        return ProviderResponse(content=step.get("content", ""))
