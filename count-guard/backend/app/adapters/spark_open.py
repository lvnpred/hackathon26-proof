"""Muse Spark Open on Baseten. The reconciler's tool loop.

Public Baseten id on 15 Oct 2026 was meta-models/muse-spark-open.
The hackathon spec names meta-models/muse-spark-open-1026. The env var
SPARK_OPEN_MODEL selects one. Tool calling is documented. It is not
treated as confirmed until a key is present and a call succeeds.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from app.config import Settings

Complete = Callable[[list[dict], list[dict]], dict]


class SparkOpenAdapter:
    def __init__(self, settings: Settings, complete: Complete | None = None):
        self.settings = settings
        self._complete = complete or self._http_complete

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        return self._complete(messages, tools)

    def _http_complete(self, messages: list[dict], tools: list[dict]) -> dict:
        if not self.settings.spark_open_configured:
            raise RuntimeError("BASETEN_API_KEY is not set")
        body: dict = {
            "model": self.settings.spark_open_model,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
        with httpx.Client(timeout=90) as client:
            response = client.post(
                f"{self.settings.spark_open_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.baseten_api_key}"},
                json=body,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]
