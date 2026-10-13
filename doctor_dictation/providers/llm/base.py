from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Completion:
    text: str
    json: dict | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish: str = ""


class LlmError(Exception):
    """`complete` failed; str(e) is safe to show (<= 300 chars)."""


class LlmProvider(Protocol):
    name: str  # "openai" | "deepseek" | "stub"
    model: str

    async def complete_json(self, messages: list[dict]) -> tuple[dict | None, str]: ...
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> Completion: ...
