"""Pooled headless-Chromium PDF renderer: one browser owned by one worker thread, a bounded queue."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Callable, Protocol

from .sheet import build_sheet_html

class PdfUnavailable(RuntimeError):
    """No PDF could be produced; callers fall back to browser print-to-PDF."""

class PdfRenderer(Protocol):
    def render(self, html: str, out_path: Path) -> Path: ...     # raises PdfUnavailable

def _no(why) -> PdfUnavailable:
    return PdfUnavailable(f"PDF renderer unavailable: {why}. Install it with 'pip install playwright' then "
                          "'playwright install chromium'; otherwise use browser print-to-PDF.")

def launch_chromium():
    """Start Playwright and Chromium; return ``(browser, stop)``. Playwright is imported lazily."""
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
    except Exception as e:  # not installed, or a broken install
        raise _no(f"Playwright (chromium) is not usable ({str(e)[:100]})") from e
    try:
        browser = pw.chromium.launch()
    except Exception as e:
        pw.stop()
        raise _no(f"chromium would not start ({str(e)[:100]})") from e
    return browser, lambda: (browser.close(), pw.stop())

class ChromiumPoolRenderer:
    """The one-thread executor is the worker: lazy, launches Chromium on its first job, the only Playwright thread."""

    def __init__(self, launcher: Callable = launch_chromium, *, queue_size: int = 16, timeout: float = 30.0):
        self._launcher, self._timeout, self._slots = launcher, timeout, threading.BoundedSemaphore(queue_size)
        self._lock, self._pool, self._browser, self._stop, self._closed = threading.Lock(), None, None, None, False

    def render(self, html: str, out_path) -> Path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._closed:
                raise _no("the renderer was shut down")
            self._pool = self._pool or ThreadPoolExecutor(1, thread_name_prefix="pdf-worker")
            if not self._slots.acquire(blocking=False):
                raise _no("the PDF queue is full")
            job = self._pool.submit(self._job, html, out)
        job.add_done_callback(lambda _: self._slots.release())
        try:
            return job.result(timeout=self._timeout)
        except FutureTimeout:
            job.cancel()
            raise _no(f"chromium took over {self._timeout:g}s") from None

    def _job(self, html: str, out: Path) -> Path:        # runs on the worker thread only
        self._browser, self._stop = (self._browser, self._stop) if self._browser else self._launcher()
        try:
            context = self._browser.new_context(java_script_enabled=False)    # the sheet needs no scripts
            try:
                page, part = context.new_page(), out.with_name(out.name + ".part")
                page.set_content(html, wait_until="load", timeout=int(self._timeout * 1000))
                page.pdf(path=str(part), prefer_css_page_size=True, print_background=True)
                os.replace(part, out)
                return out
            finally:
                context.close()
        except Exception as e:
            if not self._browser.is_connected():         # chromium died: relaunch on the next job
                self._close_browser()
            raise _no(f"could not render with chromium ({e})") from e

    def _close_browser(self) -> None:
        stop, self._browser, self._stop = self._stop, None, None
        stop and stop()

    def close(self) -> None:
        with self._lock:
            self._closed, pool = True, self._pool
        if pool is not None:
            pool.submit(self._close_browser).result(timeout=10)
            pool.shutdown(wait=True)

_default, _default_lock = None, threading.Lock()

def get_renderer() -> PdfRenderer:
    global _default
    with _default_lock:
        _default = _default or ChromiumPoolRenderer()
        return _default

def close_renderer() -> None:
    """App shutdown: stop the worker and its browser; a no-op when no PDF was ever rendered."""
    global _default
    with _default_lock:
        renderer, _default = _default, None
    if renderer is not None and hasattr(renderer, "close"):
        renderer.close()

def render_prescription(structured: dict, meta: dict, out_path, layout=None) -> Path:
    """Build the sheet and render it; raises ``PdfUnavailable`` (or OSError) so the caller can fail soft."""
    return get_renderer().render(build_sheet_html(structured, meta, layout), Path(out_path))
