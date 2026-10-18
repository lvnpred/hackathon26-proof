# Letterhead upload accepts PDF (page 1 only)

Branch `letterhead-pdf`, nothing staged or committed.

## What changed
- `doctor_dictation/templates/images.py`: new `_render_pdf_page_one` and a `%PDF-` content check at the top of `clean_image`. Size limit (`max_bytes`) runs first, unchanged. Page 1 is rendered with `pypdfium2` at scale `max_edge / long edge in points`; pixel count is computed from the page size and checked against `max_pixels` BEFORE `page.render`. Page and document are closed in `finally`. The bitmap then goes through the existing flatten, thumbnail, metadata-clear, JPEG path.
- Errors (`TemplateError`): password PDF 400 "this PDF is password protected" (pdfium err_code 4); corrupt, zero pages or bad page size 400 "could not read this PDF"; too large 413. Generic message is now "not a JPEG, PNG, HEIC or PDF file".
- `doctor_dictation/requirements.txt`: `pypdfium2>=5,<6` (installed 5.14.0).
- `frontend/index.html`: `#lhFile` accept gains `application/pdf,.pdf`; label is "Picture or PDF of the blank pad (JPEG, PNG, iPhone HEIC or PDF, up to 8 MB; PDF: first page only)"; `letterhead.js?v=10` -> `v=11`.
- `frontend/letterhead.js`: the 400 message now mentions PDF and password protection (the UI maps by status code and does not show the server text). Needed the v=11 bump.
- Tests pinning the version updated: `tests/test_frontend_letterhead.py`, `tests/test_frontend_doctorgrid.py`.
- No route change: `api/templates.py` and `service.upload` already pass raw bytes to `clean_image`.

## Dockerfile
`Dockerfile:16-17` installs from `doctor_dictation/requirements.txt`, so the pin is picked up. No apt change: the pypdfium2 wheel bundles PDFium.

## Licence
pypdfium2: BSD-3-Clause or Apache-2.0 (its own code); bundled PDFium is BSD-3-Clause/Apache-2.0, with its dependency licences listed in the wheel.

## Tests
New `tests/test_letterhead_pdf.py` (13 tests): valid 1-page PDF -> JPEG; 2-page PDF uses page 1 (landscape red vs portrait blue); encrypted PDF; garbage after `%PDF-`; zero-page PDF; over-limit PDF 413; PNG named .pdf works as PNG; 20000x20000 pt page capped to 1600; pixel cap enforced before render (render patched to fail); extreme aspect ratio; generic message mentions PDF; route end to end (stub LLM, vision input captured); route 400 password and 413. Written first and seen failing.
Full suite: 2066 passed, 1 skipped (baseline 2053 + 13).

## Mutants (all killed, each reverted, file diffed against the original)
| Mutant | Result |
|---|---|
| render last page | killed (2 failed) |
| skip encrypted handling | killed (2) |
| skip `max_bytes` check | killed (3) |
| never detect PDF by content | killed (10) |
| no scale (1 px per pt) | killed (3) |
| skip pixel guard before render | SURVIVED the first test set (the later generic pixel check still caught it after rendering); added a test that patches `PdfPage.render` to fail; now killed |

## Real render check
Letterhead-like image (1240x1754 at 150 dpi) saved as PDF, then `clean_image`: 49,446-byte PDF -> JPEG 1132x1600, 21,410 bytes.

## Caveats
- Only page 1 is read; multi-page PDFs are silently truncated (label says so).
- PDF vector content is rasterised at ~1600 px long edge, same as photos.
- Upscaling: small pages are scaled up to 1600 px for legibility.
- The UI shows one generic 400 message for all unreadable files; the specific password message appears only in the API response.
- pypdfium2 import is lazy inside the PDF branch, so an environment without it still serves images.
