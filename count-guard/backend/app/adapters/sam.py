"""SAM 3.1 on the Meta Model API.

Docs checked 27 Oct 2026 (https://dev.meta.ai/docs/sam/segmenting):
one noun phrase per request, image or uploaded video, Responses API,
streamed special-token text. There is no live frame socket. Object ids
are stable inside one response and are not kept across a new call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from app.config import Settings

_RECORD = re.compile(
    r"(?P<id>\d+)"
    r"<\|box;x1=(?P<x1>\d+);y1=(?P<y1>\d+);x2=(?P<x2>\d+);y2=(?P<y2>\d+);"
    r"w=(?P<w>\d+);h=(?P<h>\d+)(?:;c=(?P<conf>[0-9.]+))?\|>"
    r"<\|mask;x=0;y=0(?:;c=(?P<mconf>[0-9.]+))?;data=(?P<mh>\d+),(?P<mw>\d+),"
    r"(?P<enc>[~!])(?P<payload>.*?)\|>",
    re.S,
)


def parse_sam_text(text: str) -> list[dict]:
    """Parse streamed SAM lines into normalized boxes. Mask tokens are kept."""
    records = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        marker = re.match(r"<(\d+)f>", line)
        if not marker:
            continue
        frame_index = int(marker.group(1))
        for match in _RECORD.finditer(line[marker.end() :]):
            frame_w = int(match.group("w")) or 1
            frame_h = int(match.group("h")) or 1
            x1 = int(match.group("x1"))
            y1 = int(match.group("y1"))
            x2 = int(match.group("x2"))
            y2 = int(match.group("y2"))
            confidence = match.group("conf") or match.group("mconf")
            records.append(
                {
                    "frame_index": frame_index,
                    "object_id": match.group("id"),
                    "bbox": [
                        x1 / frame_w,
                        y1 / frame_h,
                        max(1, x2 - x1) / frame_w,
                        max(1, y2 - y1) / frame_h,
                    ],
                    "score": float(confidence) if confidence else None,
                    "frame_w": frame_w,
                    "frame_h": frame_h,
                    "mask_token": match.group(0),
                }
            )
    return records


def concept_request(concept: str, *, file_id: str | None = None, image_data_url: str | None = None, model: str = "sam-3.1") -> dict:
    """One concept per call. A comma-separated prompt returns nothing."""
    if file_id and image_data_url:
        raise ValueError("Send a video file or an image, not both")
    content: list[dict] = [{"type": "input_text", "text": concept}]
    if file_id:
        content.append({"type": "input_video", "file_id": file_id})
    elif image_data_url:
        content.append({"type": "input_image", "image_url": image_data_url})
    else:
        raise ValueError("SAM 3.1 needs a video file id or an image")
    return {
        "model": model,
        "stream": True,
        "input": [{"type": "message", "role": "user", "content": content}],
        "metadata": {"include_confidence": "true"},
    }


def read_sse_text(lines: list[str]) -> str:
    parts: list[str] = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            parts.append(data)
            continue
        if payload.get("type") == "response.output_text.delta":
            parts.append(payload.get("delta") or "")
        elif payload.get("type") == "response.completed":
            output = payload.get("response", {}).get("output") or []
            for item in output:
                for content in item.get("content") or []:
                    if content.get("type") == "output_text" and content.get("text"):
                        parts.append(content["text"])
    return "".join(parts)


def upload_video(settings: Settings, path: Path) -> str:
    """Upload one MP4 to the Files API. SAM 3.1 and the Muse Spark baseline both read it by id."""
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{settings.meta_base}/files",
            headers={"Authorization": f"Bearer {settings.meta_api_key}"},
            files={"file": (path.name, path.read_bytes(), "video/mp4")},
            data={"purpose": "user_data"},
        )
        response.raise_for_status()
        return response.json()["id"]


class SamAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    def segment_video(self, path: Path, concepts: list[str]) -> list[dict]:
        if not self.settings.sam_configured:
            raise RuntimeError("MODEL_API_KEY is not set")
        file_id = self._upload(path)
        records: list[dict] = []
        for concept in concepts:
            body = concept_request(concept, file_id=file_id, model=self.settings.sam_model)
            text = self._stream(body)
            for record in parse_sam_text(text):
                record["label"] = concept
                records.append(record)
        return records

    def segment_images(self, data_urls: list[str], concepts: list[str]) -> list[dict]:
        """Records for still photos: `frame_index` is the photo's position, so a concept's count is per photo."""
        if not self.settings.sam_configured:
            raise RuntimeError("MODEL_API_KEY is not set")
        records: list[dict] = []
        for concept in concepts:
            for index, url in enumerate(data_urls):
                text = self._stream(concept_request(concept, image_data_url=url, model=self.settings.sam_model))
                if text.strip() and not re.match(r"\s*<\d+f>", text):
                    text = "<0f>" + text.strip().replace("\n", "\n<0f>")  # an image reply may carry no frame marker
                for record in parse_sam_text(text):
                    records.append({**record, "label": concept, "frame_index": index})
        return records

    def _upload(self, path: Path) -> str:
        return upload_video(self.settings, path)

    def _stream(self, body: dict) -> str:
        lines: list[str] = []
        with httpx.Client(timeout=300) as client:
            with client.stream(
                "POST",
                f"{self.settings.meta_base}/responses",
                headers={"Authorization": f"Bearer {self.settings.meta_api_key}"},
                json=body,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    lines.append(line)
        return read_sse_text(lines)
