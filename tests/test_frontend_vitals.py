"""Plan PQ-d task 7, page: frontend/vitals.js under node with a tiny fake DOM."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """const els = {}; ["vBp", "vPulse", "vWeight", "vSpo2", "vTemp", "vHint"].forEach((id) => { els[id] = { id, textContent: "", hidden: true }; });
globalThis.document = { getElementById: (id) => els[id] || null }; globalThis.window = globalThis;"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = FAKE + "require(process.argv[1]);" + body
    out = subprocess.run([node, "-e", js, str(FRONT / "vitals.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_render_and_read_round_trip():
    r = _run("""Vitals.render({ bp: "140/90", pulse: 88, weight: "  72   kg " }); const a = Vitals.read();
      Vitals.render(undefined); const b = Vitals.read();
      console.log(JSON.stringify({ a, b, text: els.vPulse.textContent }));""")
    assert r["a"] == {"bp": "140/90", "pulse": "", "weight": "72 kg", "spo2": "", "temp": ""}   # a number is not text: ""
    assert r["b"] == dict.fromkeys(("bp", "pulse", "weight", "spo2", "temp"), "") and r["text"] == ""   # Review Focus 1


def test_hints_are_gentle_and_only_for_odd_values():
    r = _run("""const h = (o) => Vitals.hints(Object.assign({ bp: "", pulse: "", weight: "", spo2: "", temp: "" }, o));
      Vitals.render({ pulse: "900" }); const shown = [els.vHint.textContent, els.vHint.hidden];
      Vitals.render({ pulse: "88/min", bp: "140/90", weight: "72 kg", spo2: "98%", temp: "101 F" }); const calm = [els.vHint.textContent, els.vHint.hidden];
      console.log(JSON.stringify({ shown, calm, ok: h({ temp: "37.2 C" }), bp: h({ bp: "400/90" }), spo2: h({ spo2: "120" }),
        chars: h({ weight: "7<2" }), long: h({ weight: "1".repeat(21) }), word: h({ pulse: "regular" }) }));""")
    assert r["shown"] == ["Pulse 900 looks unusual — check it", False] and r["calm"] == ["", True]
    assert r["ok"] == [] and r["word"] == []
    assert r["bp"] == ["BP 400/90 looks unusual — check it"] and r["spo2"] == ["SpO2 120 looks unusual — check it"]
    assert r["chars"] == ["Weight: this value will not be saved (use letters, numbers and . , / % \u00b0 : + -, at most 20 characters)"]
    assert r["long"] == r["chars"]


def test_page_wires_vitals():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    fmt = app[app.index("async function formatTranscript"):app.index("async function applyCorrection")]
    cor = app[app.index("async function applyCorrection"):app.index("function retryLast")]
    assert "warningNote(j)" in fmt and "warningNote(j)" in cor             # /api/format warnings shown like a correction's
    assert "base.vitals = Vitals.read();" in app and "Vitals.render(s.vitals);" in app and "Vitals.render({});" in app
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index("vitals.js?v=2") < html.index("app.js?v=51") and 'id="pVitals"' in html and "styles.css?v=14" in html
    assert 'class="sub vitals-row"' in html
    for i in ("vBp", "vPulse", "vWeight", "vSpo2", "vTemp"):          # each input is labelled; order is BP, pulse, weight, SpO2, temp
        assert f'aria-labelledby="{i}L"' in html
    assert [html.index(f'id="{i}"') for i in ("vBp", "vPulse", "vWeight", "vSpo2", "vTemp")] == sorted(html.index(f'id="{i}"') for i in ("vBp", "vPulse", "vWeight", "vSpo2", "vTemp"))
