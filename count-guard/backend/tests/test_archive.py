"""The older screens and routes are archived, not deleted, and nothing the app runs reaches them (spec §9, A7, U2, U13)."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from tests.test_care_demo import _client

CG = Path(__file__).resolve().parents[2]
ARCHIVE = CG / "archive"
MOVED = (  # spec §9 "Archiving": route files and the scripted plays (U13)
    "backend/app/morning/api.py", "backend/app/morning/routes_extra.py", "backend/app/morning/script.py",
    "backend/app/api/routes.py", "backend/app/api/ws.py", "backend/app/journey/play.py",
    "frontend/src/screens/Morning.jsx", "frontend/src/screens/Ot.jsx", "frontend/src/screens/Journey.jsx",
)
# Not a screen or a route: `core/` stays in place whatever the import graph says (spec §9 "Archiving").
STAYS_UNREACHED = {Path("backend/app/core/clock.py")}


def _archive_set():
    spec = importlib.util.spec_from_file_location("archive_set", CG / "scripts" / "archive_set.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_app_imports_without_archive():
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"} | {"PYTHONPATH": str(CG / "backend")}
    code = (
        "import sys, app.main\n"
        f"bad = [m for m, mod in sys.modules.items() if '{ARCHIVE}' in str(getattr(mod, '__file__', '') or '')]\n"
        f"assert not any('{ARCHIVE}' in p for p in sys.path), sys.path\n"
        "assert not bad, bad\n"
    )
    done = subprocess.run([sys.executable, "-c", code], cwd=CG / "backend", env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_old_files_moved_not_deleted():
    for rel in MOVED:
        assert not (CG / rel).exists(), f"{rel} is still in place"
        assert (ARCHIVE / rel).is_file(), f"{rel} is missing from archive/"


def test_nothing_left_unreachable():
    """The archive set comes from the import graph (spec §9): after the move, nothing under app/ or src/ is orphaned."""
    assert set(_archive_set().unreachable(CG)) <= STAYS_UNREACHED


def test_archive_set_finds_an_orphan(tmp_path):
    (tmp_path / "backend/app/journey").mkdir(parents=True)
    (tmp_path / "frontend/src/screens").mkdir(parents=True)
    (tmp_path / "backend/app/__init__.py").write_text("")
    (tmp_path / "backend/app/journey/__init__.py").write_text("")
    (tmp_path / "backend/app/main.py").write_text("from app.journey import used\n")
    (tmp_path / "backend/app/journey/used.py").write_text("from .helper import x\n")
    (tmp_path / "backend/app/journey/helper.py").write_text("x = 1\n")
    (tmp_path / "backend/app/journey/old.py").write_text("x = 2\n")
    (tmp_path / "frontend/src/main.jsx").write_text('import App from "./App";\n')
    (tmp_path / "frontend/src/App.jsx").write_text('import { A } from "./screens/Kept.jsx";\n')
    (tmp_path / "frontend/src/screens/Kept.jsx").write_text("export const A = 1;\n")
    (tmp_path / "frontend/src/screens/Old.jsx").write_text("export const B = 1;\n")
    module = _archive_set()
    assert module.unreachable(tmp_path) == [Path("backend/app/journey/old.py"), Path("frontend/src/screens/Old.jsx")]
    kept = module.unreachable(tmp_path, keep=[Path("frontend/src/screens/Old.jsx")])
    assert kept == [Path("backend/app/journey/old.py")]


def test_no_care_file_imports_screens():
    src = CG / "frontend" / "src"
    assert not (src / "screens").exists() or not any((src / "screens").iterdir())
    for path in [*src.rglob("*.js"), *src.rglob("*.jsx")]:
        text = path.read_text(encoding="utf8")
        assert not re.search(r"""from\s+['"][./]*(screens|archive)/""", text), path


def test_kept_screens_not_in_menu():
    """U11: a screen kept past the freeze stays routed but leaves the menu. Nothing is kept, so the menu is the care app's."""
    menu = (CG / "frontend" / "src" / "care" / "menu.js").read_text(encoding="utf8")
    kept = re.findall(r'"(/[a-z-]+)"', menu.split("export const KEPT")[1].split(";")[0])
    listed = re.findall(r'"(/[a-z:/-]*)"', menu.split("export const MENU")[1].split("];")[0])
    assert not set(kept) & set(listed)
    app = (CG / "frontend" / "src" / "App.jsx").read_text(encoding="utf8")
    for old in ("/steps", "/older", "/count", "/morning", "/opd", "/ot", "/ward", "/case/", "/journey", "/doctor",
                "/nurse", "/patient", "/audit"):
        if old not in kept:
            assert f'path="{old}"' not in app and f'path="{old.rstrip("/")}/' not in app, old


def test_old_routes_are_gone(tmp_path):
    """R17: the scripted plays wrote person-labelled packs and closings. Both routes are gone (U13)."""
    client = _client(tmp_path)
    eid = client.post("/journey/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    assert client.post(f"/morning/episodes/{eid}/play").status_code == 404
    assert client.post(f"/journey/episodes/{eid}/play").status_code == 404
    assert client.app.state.morning.events(eid) == []
    paths = set(client.app.openapi()["paths"])
    assert not [p for p in paths if p.endswith("/play") or p.startswith(("/morning", "/cases"))], paths


def test_health_stays_after_the_camera_routes_left(tmp_path):
    """GET /health (README) lived in the archived api/routes.py; it moved to site.py unchanged in shape."""
    body = _client(tmp_path).get("/health").json()
    assert body["ok"] is True and body["banner"] == "Research demo. Not for clinical use."
    assert set(body["adapters"]) == {"sam-3.1", "muse-voice-transcribe", "muse-spark-open", "muse-spark-1.3"}
    assert body["adapters"]["muse-voice-transcribe"]["note"].startswith("Turn-level")
    assert body["adapters"]["sam-3.1"]["configured"] is False


def test_episode_create_route(tmp_path):
    client = _client(tmp_path)
    made = client.post("/journey/episodes", json={"label": "Synthetic demo, B"})
    assert made.status_code == 200 and made.json()["label"] == "Synthetic demo, B"
    assert client.get(f"/journey/episodes/{made.json()['id']}").status_code == 200
    assert client.post("/journey/episodes", json={"label": ""}).status_code == 422
    assert client.post("/journey/episodes", json={"label": "x", "by": "y"}).status_code == 422
