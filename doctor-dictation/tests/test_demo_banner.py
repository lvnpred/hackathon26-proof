"""The two-app demo banner (DD → Count Guard flow, spec §12): "Research demo · Synthetic data · Not for clinical use"
shows only when DEMO_BANNER=1 (read at call time), so a real clinic never sees it."""
from pathlib import Path

from fastapi.testclient import TestClient

FRONT = Path(__file__).resolve().parents[1] / "frontend"
TEXT = "Research demo · Synthetic data · Not for clinical use"


def _health():
    import doctor_dictation.main as M
    return TestClient(M.app).get("/api/health").json()


def test_banner_off_by_default(monkeypatch):
    monkeypatch.delenv("DEMO_BANNER", raising=False)
    assert _health()["demo_banner"] is False


def test_banner_on_with_env_read_at_call_time(monkeypatch):
    monkeypatch.setenv("DEMO_BANNER", "1")
    assert _health()["demo_banner"] is True
    monkeypatch.setenv("DEMO_BANNER", "0")
    assert _health()["demo_banner"] is False


def test_page_has_the_hidden_banner_and_its_script():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert f'<p id="demoBanner" class="demo-banner no-print" role="note" hidden>{TEXT}</p>' in html
    assert '<script src="demobanner.js?v=1"></script>' in html
    js = (FRONT / "demobanner.js").read_text(encoding="utf-8")
    assert "/api/health" in js and "demo_banner" in js
