"""Validate by content, normalise, strip metadata. Output is always a clean JPEG."""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from doctor_dictation.templates import TemplateError

try:  # a missing HEIC codec only means HEIC uploads are rejected as unreadable
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

ACCEPTED = ["JPEG", "PNG", "HEIF"]


def clean_image(raw: bytes, *, max_bytes: int, max_pixels: int, max_edge: int = 1600) -> bytes:
    if len(raw) > max_bytes:
        raise TemplateError(413, "image file is too large")
    try:
        im = Image.open(io.BytesIO(raw), formats=ACCEPTED)  # type from content, never from the name
        width, height = im.size                              # header only, nothing decoded yet
    except Image.DecompressionBombError:
        raise TemplateError(413, "image has too many pixels") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise TemplateError(400, "not a JPEG, PNG or HEIC image") from None
    if width * height > max_pixels:
        raise TemplateError(413, "image has too many pixels")
    try:
        im = ImageOps.exif_transpose(im)                     # decodes and applies the rotation
        if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
            rgba = im.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.getchannel("A"))
            im = flat
        else:
            im = im.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise TemplateError(400, "image could not be decoded") from None
    im.thumbnail((max_edge, max_edge), Image.LANCZOS)
    im.info.clear()                                          # Pillow's JPEG writer re-emits info["comment"], icc_profile, exif, xmp, dpi...
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85, optimize=True)          # no exif=/icc_profile=/comment=: nothing is carried over
    return out.getvalue()


def to_data_uri(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def crop_fraction(jpeg: bytes, crop, max_edge: int = 400) -> bytes:
    """Crop ``[x0, y0, x1, y1]`` (fractions) out of a clean JPEG: clamp to 0..1, order the corners."""
    im = Image.open(io.BytesIO(jpeg))
    w, h = im.size
    x0, y0, x1, y1 = (max(0.0, min(1.0, float(v))) for v in crop)
    box = (int(min(x0, x1) * w), int(min(y0, y1) * h), int(max(x0, x1) * w), int(max(y0, y1) * h))
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        raise TemplateError(502, "the logo region the model chose is empty")
    part = im.crop(box)
    part.thumbnail((max_edge, max_edge), Image.LANCZOS)
    part.info.clear()                                        # crop copies im.info, and the writer would re-emit the comment
    out = io.BytesIO()
    part.save(out, "JPEG", quality=85)
    return out.getvalue()
