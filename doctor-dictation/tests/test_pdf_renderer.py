"""ChromiumPoolRenderer with a fake browser (offline); the real-Chromium check skips without Playwright."""
import threading
import time
from pathlib import Path

import pytest

from doctor_dictation.pdf import PdfUnavailable, build_sheet_html, close_renderer
from doctor_dictation.pdf import renderer as R

class FakeBrowser:
    """Browser, context and page in one; records which thread wrote each PDF."""
    def __init__(self): self.fail, self.delay, self.threads, self.up, self.stopped = False, 0, set(), True, 0; self.context_kwargs = []
    def new_context(self, **kw): self.context_kwargs.append(kw); return self
    def new_page(self): return self
    def set_content(self, *a, **kw): pass
    close = set_content
    def is_connected(self): return self.up
    def pdf(self, path, **kw):
        if self.fail: raise OSError("disk full")
        time.sleep(self.delay); self.threads.add(threading.get_ident()); Path(path).write_bytes(b"%PDF-fake")

def make(**kw):
    browser, launches = FakeBrowser(), []
    def launcher():
        launches.append(1)
        return browser, lambda: setattr(browser, "stopped", browser.stopped + 1)
    return R.ChromiumPoolRenderer(launcher, **kw), browser, launches

def run_threads(n, target):
    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    [t.start() for t in threads]; [t.join(60) for t in threads]

def test_lazy_start_one_worker_thread_and_clean_close(tmp_path):
    pool, browser, launches = make()
    assert launches == []
    browser.delay, done = 0.02, []
    run_threads(12, lambda i: done.append(pool.render("<p>x</p>", tmp_path / f"{i}.pdf")))
    assert len(done) == 12 and len(launches) == 1 and len(browser.threads) == 1
    assert threading.get_ident() not in browser.threads
    pool.close()
    assert browser.stopped == 1
    with pytest.raises(PdfUnavailable, match="shut down"):
        pool.render("<p>x</p>", tmp_path / "late.pdf")
    close_renderer()                                            # a no-op when nothing was rendered

def test_full_queue_and_slow_render_raise_pdf_unavailable(tmp_path):
    pool, browser, _ = make(queue_size=1, timeout=0.2)
    browser.delay, errors = 0.6, []
    def go(i):
        try: pool.render("<p>x</p>", tmp_path / f"{i}.pdf")
        except PdfUnavailable as e: errors.append(str(e))
    run_threads(3, go)
    assert any("queue is full" in e for e in errors) and any("took over" in e for e in errors)
    pool.close()

def test_failures_are_pdf_unavailable_and_a_dead_chromium_is_relaunched(tmp_path):
    def broken(): raise PdfUnavailable("PDF renderer unavailable: chromium missing")
    with pytest.raises(PdfUnavailable, match="chromium"):
        R.ChromiumPoolRenderer(broken).render("<p>x</p>", tmp_path / "a.pdf")
    pool, browser, launches = make()
    browser.fail, browser.up = True, False                      # the render fails and chromium is gone
    with pytest.raises(PdfUnavailable, match="chromium"):
        pool.render("<p>x</p>", tmp_path / "a.pdf")
    browser.fail, browser.up = False, True
    assert pool.render("<p>x</p>", tmp_path / "a.pdf").exists() and len(launches) == 2
    pool.close()

def test_real_chromium_identifier_line_only_on_pages_two_and_later(tmp_path):
    PdfReader = pytest.importorskip("pypdf").PdfReader; pytest.importorskip("playwright.sync_api")
    html = build_sheet_html({"patientName": "Anita Rao", "rx": [{"name": f"D{i}"} for i in range(70)]}, {"opNo": "OP-77", "date": "d"})
    pool = R.ChromiumPoolRenderer(timeout=60)
    try: pages = [p.extract_text() for p in PdfReader(str(pool.render(html, tmp_path / "s.pdf"))).pages]
    except PdfUnavailable: pytest.skip("Chromium is not installed")
    finally: pool.close()
    assert len(pages) >= 2 and "Anita Rao | OP/IP No" not in pages[0]
    assert all(f"Anita Rao | OP/IP No: OP-77 | d Page {n} of {len(pages)}" in t for n, t in enumerate(pages[1:], 2))


def test_render_context_has_javascript_disabled(tmp_path):
    pool, browser, _ = make()
    pool.render("<p>x</p>", tmp_path / "a.pdf")
    pool.close()
    assert browser.context_kwargs and all(kw.get("java_script_enabled") is False for kw in browser.context_kwargs)
