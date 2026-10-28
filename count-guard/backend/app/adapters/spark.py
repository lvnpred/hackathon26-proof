"""Muse Spark 1.3 second look. It names a crop. It does not decide the count."""

from __future__ import annotations

import httpx

from app.config import Settings

ALLOWED_NAMES = (
    "lap sponge",
    "gauze swab",
    "surgical forceps",
    "scissors",
    "needle holder",
    "unknown",
)


def second_look_prompt(tracked_label: str) -> str:
    names = ", ".join(ALLOWED_NAMES)
    return (
        "Name the object in this crop with one of these words only: "
        f"{names}. The tracker label is {tracked_label}. "
        "Do not give medical advice. Reply with one name and nothing else."
    )


def normalize_second_look(text: str) -> str:
    lowered = (text or "").strip().lower()
    for name in ALLOWED_NAMES:
        if name in lowered:
            return name
    return "unknown"


class SparkAdapter:
    """Called only when rule R5 fires."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def second_look(self, image_data_url: str, tracked_label: str) -> str:
        if not self.settings.spark_configured:
            raise RuntimeError("MODEL_API_KEY is not set")
        body = {
            "model": self.settings.spark_model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": second_look_prompt(tracked_label)},
                        {"type": "input_image", "image_url": image_data_url},
                    ],
                }
            ],
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{self.settings.meta_base}/responses",
                headers={"Authorization": f"Bearer {self.settings.meta_api_key}"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        text = _output_text(payload)
        return normalize_second_look(text)


def _output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    parts = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)
