import io
import struct
import zlib

import pytest
from PIL import Image

from doctor_dictation.templates import TemplateError
from doctor_dictation.templates.images import clean_image, crop_fraction, to_data_uri

CAPS = dict(max_bytes=8 << 20, max_pixels=40_000_000)


def _png_header(w, h):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")


def _save(im, fmt, **kw):
    b = io.BytesIO()
    im.save(b, fmt, **kw)
    return b.getvalue()


def test_jpeg_exif_rotated_and_metadata_stripped():
    ex = Image.Exif()
    ex[0x0112] = 6
    ex[0x010F] = "PhoneCo"
    gps = ex.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (17.0, 23.0, 0.0), "E", (78.0, 29.0, 0.0)
    raw = _save(Image.new("RGB", (400, 200), (200, 30, 30)), "JPEG", exif=ex)
    assert dict(Image.open(io.BytesIO(raw)).getexif())  # tags present before
    out = Image.open(io.BytesIO(clean_image(raw, **CAPS)))
    assert out.format == "JPEG" and out.size == (200, 400)
    assert dict(out.getexif()) == {} and 0x8825 not in out.getexif()


def test_png_alpha_flattened_to_white():
    raw = _save(Image.new("RGBA", (50, 50), (0, 0, 0, 0)), "PNG")
    out = Image.open(io.BytesIO(clean_image(raw, **CAPS)))
    assert out.mode == "RGB" and out.getpixel((10, 10)) == (255, 255, 255)


def test_heic_accepted_by_content():
    raw = _save(Image.new("RGB", (300, 300), (10, 200, 10)), "HEIF")
    assert raw[4:12] == b"ftypheic"
    out = Image.open(io.BytesIO(clean_image(raw, **CAPS)))
    assert out.format == "JPEG" and out.size == (300, 300)


def test_large_image_downscaled_and_smaller():
    raw = _save(Image.effect_noise((3000, 2000), 40).convert("RGB"), "PNG")
    out = clean_image(raw, max_bytes=50 << 20, max_pixels=40_000_000)
    assert max(Image.open(io.BytesIO(out)).size) == 1600 and len(out) < len(raw) / 4


def test_text_renamed_jpg_is_400():
    with pytest.raises(TemplateError) as e:
        clean_image(b"this is just text, named photo.jpg", **CAPS)
    assert e.value.status == 400


def test_gif_pdf_and_truncated_jpeg_are_400():
    gif = _save(Image.new("RGB", (10, 10)), "GIF")
    jpg = _save(Image.new("RGB", (400, 400), (9, 9, 9)), "JPEG")
    for data in (gif, b"%PDF-1.4 hello", jpg[: len(jpg) // 2]):
        with pytest.raises(TemplateError) as e:
            clean_image(data, **CAPS)
        assert e.value.status == 400


def test_pixel_bomb_header_is_413():
    bomb = _png_header(50000, 50000)
    assert len(bomb) < 100
    with pytest.raises(TemplateError) as e:
        clean_image(bomb, **CAPS)
    assert e.value.status == 413


def test_over_pixel_cap_below_pillow_limit_is_413():
    raw = _save(Image.new("L", (8000, 6000)), "PNG")  # 48M pixels, tiny file
    with pytest.raises(TemplateError) as e:
        clean_image(raw, **CAPS)
    assert e.value.status == 413


def test_over_byte_cap_is_413_before_decoding():
    with pytest.raises(TemplateError) as e:
        clean_image(b"x" * 101, max_bytes=100, max_pixels=1)
    assert e.value.status == 413


def test_crop_fraction_clamps_orders_and_rejects_empty():
    jpg = _save(Image.new("RGB", (1000, 500), (1, 2, 3)), "JPEG")
    assert Image.open(io.BytesIO(crop_fraction(jpg, [0.1, 0.0, 0.3, 0.2]))).size == (200, 100)
    assert Image.open(io.BytesIO(crop_fraction(jpg, [-1, -1, 3, 3]))).size == (400, 200)
    assert Image.open(io.BytesIO(crop_fraction(jpg, [0.3, 0.2, 0.1, 0.0]))).size == (200, 100)
    with pytest.raises(TemplateError) as e:
        crop_fraction(jpg, [0.5, 0.5, 0.5, 0.5])
    assert e.value.status == 502


def test_to_data_uri():
    assert to_data_uri(b"abc") == "data:image/jpeg;base64,YWJj"


def test_png_with_gps_like_text_chunk_is_stripped():
    im = Image.new("RGB", (20, 20))
    from PIL.PngImagePlugin import PngInfo
    meta = PngInfo()
    meta.add_text("Location", "17.38,78.48")
    raw = _save(im, "PNG", pnginfo=meta)
    assert b"17.38" in raw and b"17.38" not in clean_image(raw, **CAPS)


def test_jpeg_comment_marker_is_stripped_from_clean_and_crop():
    raw = _save(Image.new("RGB", (200, 200), (10, 120, 10)), "JPEG", comment=b"GPS 17.38N 78.48E")
    assert b"GPS 17.38N" in raw
    cleaned = clean_image(raw, **CAPS)
    assert b"GPS 17.38N" not in cleaned
    assert b"GPS 17.38N" not in crop_fraction(cleaned, [0, 0, 1, 1])
    assert b"GPS 17.38N" not in crop_fraction(raw, [0, 0, 1, 1])   # even a crop of a dirty JPEG
