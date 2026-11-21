"""Typed tool registry with explicit allowlists.

The registry is the single source of truth for which tools exist, what inputs
they accept, how long they may run, and how much they may return. The
investigation engine may only execute tools that are both registered AND
present in the incident source's allowlist (agent.policies).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

ToolFunction = Callable[[dict], Awaitable[str]]


class ToolValidationError(Exception):
    pass


class ToolExecutionError(Exception):
    pass


class ToolTimeoutError(ToolExecutionError):
    pass


class ToolOutputTooLargeError(ToolExecutionError):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    execute: ToolFunction
    timeout_seconds: float = 20.0
    max_output_bytes: int = 262_144
    access_policy: str = "investigation"  # investigation | admin
    audit: bool = True
    metadata: dict = field(default_factory=dict)

    def input_schema_dict(self) -> dict:
        return self.input_model.model_json_schema()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool {spec.name} already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def for_allowlist(self, allowlist: list[str]) -> list[ToolSpec]:
        specs = []
        for name in allowlist:
            spec = self._tools.get(name)
            if spec is None:
                logger.warning("Allowlist references unregistered tool %s", name)
                continue
            specs.append(spec)
        return specs

    def tool_dicts(self, allowlist: list[str]) -> list[dict]:
        """OpenAI-style tool definitions for providers with native tool calling."""
        out = []
        for spec in self.for_allowlist(allowlist):
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.input_schema_dict(),
                    },
                }
            )
        return out

    async def execute(self, name: str, arguments: dict) -> str:
        """Validate and execute a tool call. Returns a string result.

        Raises ToolValidationError / ToolExecutionError — never fabricates output.
        """
        spec = self._tools.get(name)
        if spec is None:
            raise ToolValidationError(f"Unknown tool: {name}")
        try:
            parsed = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(f"Invalid arguments for {name}: {exc}") from exc

        payload = parsed.model_dump()
        logger.info("Executing tool %s", name)
        try:
            result = await asyncio.wait_for(spec.execute(payload), timeout=spec.timeout_seconds)
        except TimeoutError as exc:
            raise ToolTimeoutError(f"Tool {name} timed out after {spec.timeout_seconds}s") from exc
        except ToolExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - structured, non-misleading error
            raise ToolExecutionError(f"Tool {name} failed: {type(exc).__name__}: {exc}") from exc

        encoded = result.encode("utf-8", errors="replace")
        if len(encoded) > spec.max_output_bytes:
            raise ToolOutputTooLargeError(
                f"Tool {name} output exceeded {spec.max_output_bytes} bytes"
            )
        return result


# --- Decorator-based registration helper ------------------------------------

_REGISTRY = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _REGISTRY


def tool(
    name: str,
    description: str,
    input_model: type[BaseModel],
    timeout_seconds: float = 20.0,
    max_output_bytes: int = 262_144,
    access_policy: str = "investigation",
) -> Callable[[ToolFunction], ToolFunction]:
    def decorator(fn: ToolFunction) -> ToolFunction:
        _REGISTRY.register(
            ToolSpec(
                name=name,
                description=description,
                input_model=input_model,
                execute=fn,
                timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                access_policy=access_policy,
            )
        )
        return fn

    return decorator
