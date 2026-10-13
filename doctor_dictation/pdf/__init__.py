from pathlib import Path

from . import renderer as _renderer
from .layout import DEFAULT_LAYOUT, Layout, LayoutError, validate_layout
from .renderer import PdfRenderer, PdfUnavailable, close_renderer, render_prescription
from .sheet import DISCLAIMER, build_sheet_html

def render_pdf(html: str, out_path) -> Path:
    return _renderer.get_renderer().render(html, Path(out_path))
