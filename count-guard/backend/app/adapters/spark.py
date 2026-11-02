"""Muse Spark 1.3: names a crop (second look), reads strip labels, rewords a handover, or says whether a proof
photo shows what it should (a person can override that verdict). It decides nothing else."""

from __future__ import annotations

import base64
import json
import re

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

MONITOR_PROMPT = (
    "Read the numbers on this blood pressure monitor screen. "
    'Reply with JSON only: {"sbp": 0, "dbp": 0, "hr": 0}. '
    "Use null for a number that cannot be read. Copy what is shown. Do not give medical advice."
)


VERDICTS = ("accepted", "not_accepted")
_FENCE = re.compile(r"^```[a-z]*\s*|\s*```$", re.I)


def check_photo_prompt(expect: str) -> str:
    return (
        "A nurse took this photo as proof of a care step. "
        f"The photo should show: {expect}. "
        "Accept it only if that is clearly in the photo. "
        'Reply with JSON only: {"verdict": "accepted" or "not_accepted", "why": "one short sentence on what the photo shows"}. '
        "Do not give medical advice."
    )


def parse_check_photo(text: str) -> dict:
    """The verdict and a one-line reason from the model's reply, or ValueError when it is not that."""
    payload = json.loads(_FENCE.sub("", (text or "").strip()))  # json.JSONDecodeError is a ValueError
    if not isinstance(payload, dict) or payload.get("verdict") not in VERDICTS:
        raise ValueError("the photo check reply has no verdict")
    why = " ".join(str(payload.get("why") or "").split())[:200]
    if not why:
        raise ValueError("the photo check reply has no reason")
    return {"verdict": payload["verdict"], "why": why}


class SparkAdapter:
    """Called when rule R5 fires, a patient photographs strips, or a nurse drafts a handover. Only with a key."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def second_look(self, image_data_url: str, tracked_label: str) -> str:
        return normalize_second_look(self._ask(second_look_prompt(tracked_label), image_data_url))

    def read_strips(self, image_data_url: str) -> str:
        """Raw model text. app.morning.strips.parse_strip_text grounds it."""
        return self._ask(STRIP_PROMPT, image_data_url)

    def read_monitor(self, image_data_url: str) -> str:
        """Raw model text for a monitor photo."""
        return self._ask(MONITOR_PROMPT, image_data_url)

    def check_photo(self, raw: bytes, content_type: str, expect: str) -> dict:
        """{verdict: accepted|not_accepted, why} for a proof photo against what it should show. ValueError when the reply does not parse."""
        kind = content_type if (content_type or "").startswith("image/") else "image/jpeg"
        data_url = f"data:{kind};base64,{base64.b64encode(raw).decode()}"
        return parse_check_photo(self._ask(check_photo_prompt(expect), data_url))

    def write(self, prompt: str) -> str:
        """Text in, text out. The caller checks the wording before it is shown."""
        return self._ask(prompt)

    def watch(self, prompt: str, video_file_id: str) -> str:
        """Muse Spark alone on an uploaded MP4. Used only by the eval baseline in app.baseline."""
        return self._ask(prompt, video_file_id=video_file_id, timeout=300)

    def _ask(
        self,
        prompt: str,
        image_data_url: str | None = None,
        *,
        video_file_id: str | None = None,
        timeout: float = 60,
    ) -> str:
        if not self.settings.spark_configured:
            raise RuntimeError("MODEL_API_KEY is not set")
        content: list[dict] = [{"type": "input_text", "text": prompt}]
        if image_data_url:
            content.append({"type": "input_image", "image_url": image_data_url})
        if video_file_id:
            content.append({"type": "input_video", "file_id": video_file_id})
        body = {
            "model": self.settings.spark_model,
            "input": [{"type": "message", "role": "user", "content": content}],
        }
        with httpx.Client(timeout=timeout) as client:
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
