"""Muse Spark 1.3: names a crop (second look) or reads strip labels. It does not decide anything."""

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


STRIP_PROMPT = (
    "Read the printed medicine name and strength on each strip in this photo. "
    'Reply with JSON only: {"strips": [{"name": "...", "strength": "25 mg"}]}. '
    "Copy what is printed. Leave strength empty if it cannot be read. Do not give medical advice."
)


class SparkAdapter:
    """Called when rule R5 fires, or when a patient photographs strips. Only with a key."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def second_look(self, image_data_url: str, tracked_label: str) -> str:
        return normalize_second_look(self._ask(image_data_url, second_look_prompt(tracked_label)))

    def read_strips(self, image_data_url: str) -> str:
        """Raw model text. app.morning.strips.parse_strip_text grounds it."""
        return self._ask(image_data_url, STRIP_PROMPT)

    def _ask(self, image_data_url: str, prompt: str) -> str:
        if not self.settings.spark_configured:
            raise RuntimeError("MODEL_API_KEY is not set")
        body = {
            "model": self.settings.spark_model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
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
        return _output_text(payload)


def _output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    parts = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts)
