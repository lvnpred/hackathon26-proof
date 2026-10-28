"""Draw a proof frame: zone tint, box, and track id."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

ZONE_FILL = {
    "tray": (194, 65, 12, 50),
    "field": (29, 78, 216, 50),
    "bucket": (21, 128, 61, 50),
}
INK = (28, 25, 21, 255)


def render_frame(
    width: int,
    height: int,
    zones: dict[str, list],
    detections: list[dict],
) -> bytes:
    image = Image.new("RGB", (width, height), (244, 240, 230))
    draw = ImageDraw.Draw(image, "RGBA")
    for name, polygon in zones.items():
        points = [(point[0] * width, point[1] * height) for point in polygon]
        draw.polygon(points, fill=ZONE_FILL.get(name, (80, 80, 80, 40)), outline=INK)
        if points:
            draw.text((points[0][0] + 6, points[0][1] + 6), name, fill=INK)
    for detection in detections:
        x, y, w, h = detection["bbox"]
        box = [x * width, y * height, (x + w) * width, (y + h) * height]
        draw.rectangle(box, outline=(28, 25, 21, 255), width=3)
        label = f"{detection['track_id']}"
        draw.text((box[0], max(0, box[1] - 12)), label, fill=INK)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
