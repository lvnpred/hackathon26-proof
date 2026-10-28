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
_PDF_MAGIC = b"%PDF-"
_PDFIUM_ERR_PASSWORD = 4  # FPDF_ERR_PASSWORD


def _render_pdf_page_one(raw: bytes, *, max_pixels: int, max_edge: int) -> Image.Image:
    """Page 1 of a PDF as an RGB image whose long edge is ``max_edge``. Only the first page is ever loaded."""
    import pypdfium2 as pdfium
    from pypdfium2 import PdfiumError
    pdf = page = None
    try:
        try:
            pdf = pdfium.PdfDocument(raw)
            if len(pdf) < 1:
                raise TemplateError(400, "could not read this PDF")
            page = pdf[0]
            width_pt, height_pt = page.get_size()
        except PdfiumError as exc:
            if getattr(exc, "err_code", None) == _PDFIUM_ERR_PASSWORD:
                raise TemplateError(400, "this PDF is password protected") from None
            raise TemplateError(400, "could not read this PDF") from None
        if not (width_pt > 0 and height_pt > 0):
            raise TemplateError(400, "could not read this PDF")
        scale = max_edge / max(width_pt, height_pt)          # chosen from the page size, so a huge page stays small
        px_w, px_h = max(1, round(width_pt * scale)), max(1, round(height_pt * scale))
        if px_w * px_h > max_pixels:                         # checked before any bitmap is allocated
            raise TemplateError(413, "image has too many pixels")
        try:
            return page.render(scale=scale).to_pil().convert("RGB")   # white background, no alpha
        except PdfiumError:
            raise TemplateError(400, "could not read this PDF") from None
    finally:
        if page is not None:
            page.close()
        if pdf is not None:
            pdf.close()


def clean_image(raw: bytes, *, max_bytes: int, max_pixels: int, max_edge: int = 1600) -> bytes:
    if len(raw) > max_bytes:
        raise TemplateError(413, "image file is too large")
    if raw.startswith(_PDF_MAGIC):                           # by content, never by file name or content type
        im = _render_pdf_page_one(raw, max_pixels=max_pixels, max_edge=max_edge)
        width, height = im.size
    else:
        try:
            im = Image.open(io.BytesIO(raw), formats=ACCEPTED)  # type from content, never from the name
            width, height = im.size                          # header only, nothing decoded yet
        except Image.DecompressionBombError:
            raise TemplateError(413, "image has too many pixels") from None
        except (UnidentifiedImageError, OSError, ValueError):
            raise TemplateError(400, "not a JPEG, PNG, HEIC or PDF file") from None
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
