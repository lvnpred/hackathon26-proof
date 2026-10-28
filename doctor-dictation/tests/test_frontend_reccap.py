"""Dictation stops at 5 minutes (UI-A Task 3). frontend/reccap.js runs under node with a fake clock that drives the same
500 ms tick app.js runs while recording; the app.js wiring is checked as text."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

# A fake recording: a timer element, a status line, a recorder whose stop() is counted, and a 500 ms tick up to `until` s.
_HARNESS = r"""
globalThis.window = globalThis;
const cls = new Set(); const timer = { classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c) } };
const said = []; let stops = 0;
const cap = RecCap.create({ max: 300, warn: 270, timer, status: (m) => said.push(m), stop: () => { stops++; } });
const at = {};
function runTo(until) { for (let ms = 0; ms <= until * 1000; ms += 500) { const s = Math.floor(ms / 1000); cap.tick(s); at[s] = { warn: cls.has("rec-warn"), stops, said: said.length }; } }
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"require({json.dumps(str(FRONT / 'reccap.js'))});" + _HARNESS + body
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_no_warning_before_270_seconds():
    r = _run("runTo(269); console.log(JSON.stringify({ at: at[269], said, stops, capped: cap.capped() }));")
    assert r == {"at": {"warn": False, "stops": 0, "said": 0}, "said": [], "stops": 0, "capped": False}


def test_the_warning_comes_once_at_270_seconds():
    r = _run("runTo(290); console.log(JSON.stringify({ at: at[270], said, stops }));")
    assert r["at"]["warn"] is True and r["stops"] == 0
    assert r["said"] == ["30 seconds left — finish the dictation."]


def test_the_recorder_stops_exactly_once_at_300_seconds():
    r = _run("runTo(299); const before = stops; runTo(310); console.log(JSON.stringify({ before, at: at[300], stops, said, capped: cap.capped() }));")
    assert r["before"] == 0 and r["at"]["stops"] == 1 and r["stops"] == 1 and r["capped"] is True
    assert r["said"][-1] == "Stopped at 5 minutes — transcribing."
    assert r["said"].count("30 seconds left — finish the dictation.") == 1 and r["said"].count("Stopped at 5 minutes — transcribing.") == 1


def test_a_late_tick_that_skips_270_still_warns_and_stops():
    r = _run("cap.tick(305); cap.tick(306); console.log(JSON.stringify({ warn: timer.classList.contains('rec-warn'), stops, said }));")
    assert r == {"warn": True, "stops": 1, "said": ["30 seconds left — finish the dictation.", "Stopped at 5 minutes — transcribing."]}


def test_reset_clears_the_warning_for_the_next_recording():
    r = _run("runTo(300); cap.reset(); const after = [timer.classList.contains('rec-warn'), cap.capped()]; cap.tick(10);"
             " console.log(JSON.stringify({ after, stops }));")
    assert r == {"after": [False, False], "stops": 1}


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _function(js, name):
    start = js.index(f"function {name}(")
    return js[start:js.index("\n}\n", start)]


def test_app_js_caps_every_dictation_and_keeps_the_stop_message_while_transcribing():
    js = _read("app.js")
    assert "const MAX_RECORD_S = 300;" in js and "const WARN_RECORD_S = 270;" in js
    assert re.search(r"RecCap\.create\(\{ max: MAX_RECORD_S, warn: WARN_RECORD_S, timer: timerEl, status: setStatus, stop: \(\) =>", js)
    begin = _function(js, "beginRecording")
    assert "recCap.reset()" in begin and "recCap.tick(s)" in begin                        # first dictations and corrections alike
    assert 'timerEl.classList.remove("rec-warn")' in _function(js, "endRecordingUI")       # capped() stays readable for transcribe()
    assert "recCap.capped()" in js[js.index("async function transcribe("):js.index("async function transcribe(") + 400]
    html, css = _read("index.html"), _read("styles.css")
    assert html.index("reccap.js?v=") < html.index("app.js?v=")
    rule = re.search(r"\.timer\.rec-warn \{([^}]*)\}", css).group(1)
    assert "var(--warn)" in rule and "#" not in rule                                       # a token, no raw colour


def test_spell_it_voice_input_is_not_capped_by_this():
    assert "RecCap" not in _read("spellmodal.js")
