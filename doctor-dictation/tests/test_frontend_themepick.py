"""Round 2 (R4, 2026-10-27; Lightday the same day): frontend/themepick.js under node on a tiny fake DOM. The colour theme is
per device (localStorage `dd.theme`), applied as <html data-theme> before first paint; the themes are Lightday's Day and Dusk.
A bad, unreadable or retired value (midnight, ink, graphite) is Day and never throws. The Profile panel's Appearance radios
follow and set it."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """const attrs = {}; const handlers = {};
const radios = ["day", "dusk"].map((v) => ({ value: v, checked: false,
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


def test_no_stored_theme_applies_day_and_set_stores_and_applies():
    out = _run(MEM, """const a = [attrs["data-theme"], ThemePick.current(), checked()];
ThemePick.set("dusk"); const b = [attrs["data-theme"], mem["dd.theme"], ThemePick.current(), checked()];
ThemePick.apply("day"); const c = attrs["data-theme"];
console.log(JSON.stringify([a, b, c]));""")
    assert out[0] == ["day", "day", ["day"]]
    assert out[1] == ["dusk", "dusk", "dusk", ["dusk"]]
    assert out[2] == "day"


def test_a_stored_theme_is_applied_on_load_and_a_bad_one_is_day():
    good = _run(MEM.replace("const mem = {};", 'const mem = {"dd.theme": "dusk"};'),
                'console.log(JSON.stringify([attrs["data-theme"], checked()]));')
    assert good == ["dusk", ["dusk"]]
    bad = _run(MEM.replace("const mem = {};", 'const mem = {"dd.theme": "<b>red</b>"};'),
               'ThemePick.apply("nope"); console.log(JSON.stringify([attrs["data-theme"], ThemePick.current()]));')
    assert bad == ["day", "day"]


@pytest.mark.parametrize("old", ["midnight", "ink", "graphite"])
def test_a_retired_midnight_theme_is_day(old):
    out = _run(MEM.replace("const mem = {};", 'const mem = {"dd.theme": "%s"};' % old),
               'console.log(JSON.stringify([attrs["data-theme"], ThemePick.current(), checked()]));')
    assert out == ["day", "day", ["day"]]


def test_storage_that_throws_falls_back_to_day_without_throwing():
    throwing = """Object.defineProperty(globalThis, "localStorage", { get() { throw new Error("blocked"); }, configurable: true });"""
    out = _run(throwing, 'ThemePick.set("dusk"); console.log(JSON.stringify([ThemePick.current(), attrs["data-theme"]]));')
    assert out == ["day", "dusk"]                  # applied for this page, nothing stored, nothing thrown
    broken = """globalThis.localStorage = { getItem() { throw new Error("x"); }, setItem() { throw new Error("y"); } };"""
    out = _run(broken, 'ThemePick.set("dusk"); console.log(JSON.stringify([ThemePick.current(), attrs["data-theme"]]));')
    assert out == ["day", "dusk"]


def test_choosing_a_radio_applies_and_stores_at_once():
    out = _run(MEM, """radios[1].checked = true; handlers.dusk();
console.log(JSON.stringify([attrs["data-theme"], mem["dd.theme"]]));""")
    assert out == ["dusk", "dusk"]


def test_index_loads_the_script_in_head_and_the_profile_has_an_appearance_group():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    head = html[:html.index("</head>")]
    assert '<script src="themepick.js?v=2"></script>' in head
    assert "<script>" not in html                       # no inline script
    group = html[html.index('id="profAppearance"'):]
    group = group[:group.index("</fieldset>")]
    assert "<legend>Appearance</legend>" in group
    vals = re.findall(r'<input type="radio" name="ddTheme" value="(\w+)"', group)
    assert vals == ["day", "dusk"]
    for word in ("Day", "Dusk"):
        assert word in group
    for word in ("Regular", "Ink", "Graphite"):
        assert word not in group
    assert group.count('class="theme-swatch"') == 2
    assert html.index('id="profAppearance"') < html.index('id="profileStatus"')
