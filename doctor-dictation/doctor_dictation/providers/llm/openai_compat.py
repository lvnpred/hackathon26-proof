from __future__ import annotations

import json

import httpx

from .base import Completion, LlmError, ToolCall


class OpenAICompatLlm:
    def __init__(self, *, name, base_url, model, api_key, seed):
        self.name, self.model = name, model
        self.base_url = base_url.rstrip("/")
        self._key, self._seed = api_key, seed

    async def _post(self, payload: dict):
        # Full payload + up to 3 param drops; httpx.AsyncClient is looked up at call time.
        async with httpx.AsyncClient(timeout=60.0) as client:
            for _ in range(4):
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._key}",
                             "Content-Type": "application/json"},
                    json=payload)
                if r.status_code == 400:
                    err = r.text[:500].lower()
                    dropped = next((p for p in ("temperature", "top_p", "seed")
                                    if p in payload and p in err), None)
                    if dropped:
                        print(f"LLM {self.model}: dropping unsupported param "
                              f"'{dropped}'", flush=True)
                        payload = {k: v for k, v in payload.items() if k != dropped}
                        continue
                if r.status_code != 200:
                    body = r.text.replace(self._key, "[redacted]") if self._key else r.text
                    return None, f"{self.name} {r.status_code}: {body[:200]}"
                return r, ""
        return None, f"{self.name} 400: params rejected"

    def _payload(self, messages, **extra) -> dict:
        return {"model": self.model, **extra, "temperature": 0.0, "top_p": 1.0,
                "seed": self._seed, "messages": messages}

    async def complete_json(self, messages):
        r, err = await self._post(
            self._payload(messages, response_format={"type": "json_object"}))
        if r is None:
            return None, err
        try:
            return json.loads(r.json()["choices"][0]["message"]["content"]), ""
        except Exception as e:
            return None, f"JSON parse: {e}"

    async def complete(self, messages, tools=None):
        r, err = await self._post(self._payload(messages, **({"tools": tools} if tools else {})))
        if r is None:
            raise LlmError(err[:300])
        try:
            choice = r.json()["choices"][0]
            text = choice["message"].get("content") or ""
            calls = tuple(
                ToolCall(c.get("id", ""), c["function"]["name"],
                         json.loads(c["function"].get("arguments") or "{}"))
                for c in choice["message"].get("tool_calls") or [])
            try:
                value = json.loads(text) if text else None
            except ValueError:
                value = None
            return Completion(text, value if isinstance(value, dict) else None,
                              calls, choice.get("finish_reason") or "")
        except Exception as e:
            raise LlmError(f"{self.name} response parse: {e}"[:300]) from e
