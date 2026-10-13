from __future__ import annotations

import asyncio
import json
import os

from .base import Completion


class StubLlm:
    name = model = "stub"

    def __init__(self, text: str = "{}", delay: float = 0.0):
        self._text, self._delay = text, delay

    @classmethod
    def from_env(cls) -> "StubLlm":
        ms = os.getenv("STUB_DELAY_MS", "0")
        return cls(os.getenv("STUB_LLM_JSON", "{}"), int(ms) / 1000 if ms.isdigit() else 0.0)

    async def complete_json(self, messages):
        await asyncio.sleep(self._delay)
        try:
            value = json.loads(self._text)
        except ValueError as e:
            return None, f"stub STUB_LLM_JSON invalid: {e}"
        return (value, "") if isinstance(value, dict) else (None, "stub: not an object")

    async def complete(self, messages, tools=None):
        value, err = await self.complete_json(messages)
        return Completion(self._text if value is not None else err, value, (), "stop")
