"""PDF letterhead upload: page 1 is rendered to an image, then the normal image path runs."""
import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from doctor_dictation.config import override_settings
from doctor_dictation.templates import TemplateError
from doctor_dictation.templates.images import clean_image
from template_fixtures import tclient  # noqa: F401

CAPS = dict(max_bytes=8 << 20, max_pixels=40_000_000)
URL = "/api/v1/templates"
RED, BLUE = (220, 20, 20), (20, 20, 220)


def _pdf_from_images(*images):
    b = io.BytesIO()
    images[0].save(b, "PDF", save_all=True, append_images=list(images[1:]), resolution=72)
    return b.getvalue()


def _red_page(size=(300, 200)):
    return Image.new("RGB", size, RED)


def _blank_pdf(w_pt, h_pt):
    w = PdfWriter()
    w.add_blank_page(width=w_pt, height=h_pt)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def _jpeg(raw):
    out = Image.open(io.BytesIO(raw))
    assert out.format == "JPEG"
    return out


def test_valid_one_page_pdf_becomes_clean_jpeg():
    raw = _pdf_from_images(_red_page())
    assert raw.startswith(b"%PDF-")
    out = _jpeg(clean_image(raw, **CAPS))
    assert max(out.size) == 1600 and out.size[0] > out.size[1]   # landscape, long edge scaled to max_edge
    assert not out.info.get("exif") and not out.info.get("icc_profile")
    r, g, b = out.convert("RGB").getpixel((out.size[0] // 2, out.size[1] // 2))
    assert r > 180 and g < 70 and b < 70


def test_two_page_pdf_uses_page_one_only():
    raw = _pdf_from_images(_red_page((300, 200)), Image.new("RGB", (200, 300), BLUE))
    assert len(PdfReader(io.BytesIO(raw)).pages) == 2
    out = _jpeg(clean_image(raw, **CAPS))
    assert out.size[0] > out.size[1]                            # page 1 is landscape, page 2 is portrait
    r, _, b = out.convert("RGB").getpixel((out.size[0] // 2, out.size[1] // 2))
    assert r > 180 and b < 70


def test_encrypted_pdf_is_rejected_with_password_message():
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(_pdf_from_images(_red_page()))))
    w.encrypt("secret")
    b = io.BytesIO()
    w.write(b)
    with pytest.raises(TemplateError) as e:
        clean_image(b.getvalue(), **CAPS)
    assert e.value.status == 400 and "password protected" in str(e.value)


def test_garbage_after_pdf_magic_is_rejected():
    with pytest.raises(TemplateError) as e:
        clean_image(b"%PDF-1.7\nthis is not really a pdf at all\x00\x01\x02", **CAPS)
    assert e.value.status == 400 and "could not read this PDF" in str(e.value)


def test_pdf_with_no_pages_is_rejected():
    w = PdfWriter()
    b = io.BytesIO()
    w.write(b)
    with pytest.raises(TemplateError) as e:
        clean_image(b.getvalue(), **CAPS)
    assert e.value.status == 400 and "could not read this PDF" in str(e.value)


def test_over_byte_cap_pdf_is_413():
    raw = _pdf_from_images(_red_page())
    with pytest.raises(TemplateError) as e:
        clean_image(raw, max_bytes=len(raw) - 1, max_pixels=40_000_000)
    assert e.value.status == 413


def test_png_named_pdf_still_works_as_png():
    b = io.BytesIO()
    Image.new("RGB", (120, 80), RED).save(b, "PNG")
    out = _jpeg(clean_image(b.getvalue(), **CAPS))
    assert out.size == (120, 80)          # not re-rendered, not upscaled


def test_huge_page_size_is_capped_not_rendered_at_full_size():
    raw = _blank_pdf(20000, 20000)        # at 1 px per pt this would be 400M pixels
    out = _jpeg(clean_image(raw, **CAPS))
    assert max(out.size) <= 1600


def test_pixel_cap_is_enforced_before_rendering(monkeypatch):
    import pypdfium2

    def boom(self, *a, **k):
        raise AssertionError("page.render must not run once the pixel cap is known to be exceeded")
    monkeypatch.setattr(pypdfium2.PdfPage, "render", boom)
    raw = _pdf_from_images(_red_page())   # renders to 1600 x 1067, about 1.7M pixels
    with pytest.raises(TemplateError) as e:
        clean_image(raw, max_bytes=8 << 20, max_pixels=100_000)
    assert e.value.status == 413


def test_extreme_aspect_ratio_page_does_not_crash():
    out = _jpeg(clean_image(_blank_pdf(20000, 5), **CAPS))
    assert out.size[1] >= 1


def test_generic_error_mentions_pdf():
    with pytest.raises(TemplateError) as e:
        clean_image(b"plain words", **CAPS)
    assert e.value.status == 400 and "PDF" in str(e.value)


def test_route_accepts_pdf_end_to_end(tclient, monkeypatch):
    seen = {}

    async def fake_build(jpeg, settings):
        seen["jpeg"] = jpeg
        return await real_build(jpeg, settings)

    from doctor_dictation.templates import service
    real_build = service.build_draft
    monkeypatch.setattr(service, "build_draft", fake_build)
    raw = _pdf_from_images(_red_page((300, 200)), Image.new("RGB", (200, 300), BLUE))
    r = tclient.post(URL, files={"image": ("pad.pdf", raw, "application/pdf")})
    assert r.status_code == 201 and r.json()["status"] == "draft"
    sent = _jpeg(seen["jpeg"])                     # the vision step received page 1 as a JPEG
    assert sent.size[0] > sent.size[1]


def test_route_password_pdf_is_400_and_pdf_too_large_is_413(tclient, monkeypatch):
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(_pdf_from_images(_red_page()))))
    w.encrypt("pw")
    b = io.BytesIO()
    w.write(b)
    r = tclient.post(URL, files={"image": ("pad.pdf", b.getvalue(), "application/pdf")})
    assert r.status_code == 400 and "password protected" in r.json()["error"]
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, template_max_image_bytes=100)
    r = tclient.post(URL, files={"image": ("pad.pdf", _pdf_from_images(_red_page()), "application/pdf")})
    assert r.status_code == 413
