"""Round 2 (R4, 2026-10-27): frontend/themepick.js under node on a tiny fake DOM. The colour theme is per device
(localStorage `dd.theme`), applied as <html data-theme> before first paint; a bad or unreadable value is the Regular
(midnight) theme and never throws. The Profile panel's Appearance radios follow and set it."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """const attrs = {}; const handlers = {};
const radios = ["midnight", "ink", "graphite"].map((v) => ({ value: v, checked: false,
  addEventListener: (ev, f) => { handlers[v] = f; } }));
globalThis.window = globalThis;
globalThis.document = { readyState: "complete", addEventListener: () => {},
  documentElement: { setAttribute: (k, v) => { attrs[k] = String(v); }, getAttribute: (k) => attrs[k] },
  querySelectorAll: (sel) => sel === 'input[name="ddTheme"]' ? radios : [] };
%s
require(%r);
const checked = () => radios.filter((r) => r.checked).map((r) => r.value);"""
MEM = """const mem = {}; globalThis.localStorage = { getItem: (k) => k in mem ? mem[k] : null, setItem: (k, v) => { mem[k] = String(v); } };"""


def _run(storage, body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    src = FAKE % (storage, str(FRONT / "themepick.js")) + "\n" + body
    r = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_no_stored_theme_applies_midnight_and_set_stores_and_applies():
    out = _run(MEM, """const a = [attrs["data-theme"], ThemePick.current(), checked()];
ThemePick.set("graphite"); const b = [attrs["data-theme"], mem["dd.theme"], ThemePick.current(), checked()];
ThemePick.apply("ink"); const c = attrs["data-theme"];
console.log(JSON.stringify([a, b, c]));""")
    assert out[0] == ["midnight", "midnight", ["midnight"]]
    assert out[1] == ["graphite", "graphite", "graphite", ["graphite"]]
    assert out[2] == "ink"


def test_a_stored_theme_is_applied_on_load_and_a_bad_one_is_midnight():
    good = _run(MEM.replace("const mem = {};", 'const mem = {"dd.theme": "ink"};'),
                'console.log(JSON.stringify([attrs["data-theme"], checked()]));')
    assert good == ["ink", ["ink"]]
    bad = _run(MEM.replace("const mem = {};", 'const mem = {"dd.theme": "<b>red</b>"};'),
               'ThemePick.apply("nope"); console.log(JSON.stringify([attrs["data-theme"], ThemePick.current()]));')
    assert bad == ["midnight", "midnight"]


def test_storage_that_throws_falls_back_to_midnight_without_throwing():
    throwing = """Object.defineProperty(globalThis, "localStorage", { get() { throw new Error("blocked"); }, configurable: true });"""
    out = _run(throwing, 'ThemePick.set("ink"); console.log(JSON.stringify([ThemePick.current(), attrs["data-theme"]]));')
    assert out == ["midnight", "ink"]                  # applied for this page, nothing stored, nothing thrown
    broken = """globalThis.localStorage = { getItem() { throw new Error("x"); }, setItem() { throw new Error("y"); } };"""
    out = _run(broken, 'ThemePick.set("graphite"); console.log(JSON.stringify([ThemePick.current(), attrs["data-theme"]]));')
    assert out == ["midnight", "graphite"]


def test_choosing_a_radio_applies_and_stores_at_once():
    out = _run(MEM, """radios[2].checked = true; handlers.graphite();
console.log(JSON.stringify([attrs["data-theme"], mem["dd.theme"]]));""")
    assert out == ["graphite", "graphite"]


def test_index_loads_the_script_in_head_and_the_profile_has_an_appearance_group():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    head = html[:html.index("</head>")]
    assert '<script src="themepick.js?v=1"></script>' in head
    assert "<script>" not in html                       # no inline script
    group = html[html.index('id="profAppearance"'):]
    group = group[:group.index("</fieldset>")]
    assert "<legend>Appearance</legend>" in group
    vals = re.findall(r'<input type="radio" name="ddTheme" value="(\w+)"', group)
    assert vals == ["midnight", "ink", "graphite"]
    for word in ("Regular", "Ink", "Graphite"):
        assert word in group
    assert group.count('class="theme-swatch"') == 3
    assert html.index('id="profAppearance"') < html.index('id="profileStatus"')
