"""Elapsed-seconds ticker on the status line (care-app clarity Task 9): Transcribing/Structuring with the engine
from /api/health. Pure parts under node (frontend/stepinfo.js); the two app.js hooks and the script tag as text."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"const X = require({json.dumps(str(FRONT / 'stepinfo.js'))});" + body
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_label_names_the_job_the_engine_and_the_seconds():
    r = _run("""console.log(JSON.stringify([
      X.label("transcribe", "Muse Voice", 0),
      X.label("transcribe", "Muse Voice", 3),
      X.label("structure", "Spark", 12)]));""")
    assert r == ["Transcribing with Muse Voice… 0 s", "Transcribing with Muse Voice… 3 s",
                 "Structuring with Spark… 12 s"]


def test_engines_come_from_the_health_body():
    r = _run("""console.log(JSON.stringify([
      X.engineFor({stt_engine: "muse"}, "transcribe"),
      X.engineFor({stt_engine: "groq"}, "transcribe"),
      X.engineFor({stt_engine: "faster-whisper", whisper_model: "base"}, "transcribe"),
      X.engineFor({}, "transcribe"),
      X.engineFor({llm_configured: true, llm_provider: "meta", llm_model: "muse-spark-1.3"}, "structure"),
      X.engineFor({llm_configured: true, llm_provider: "groq"}, "structure"),
      X.engineFor({deepseek_configured: true}, "structure"),
      X.engineFor({}, "structure")]));""")
    assert r == ["Muse Voice", "Groq", "Whisper", "Speech", "Spark", "Groq", "DeepSeek", "Rules"]


def test_during_ticks_until_the_call_settles_then_stops():
    r = _run("""(async () => {
      const el = {textContent: ""};
      let cb = null, now = 1000;
      const setInterval = (f) => { cb = f; return 1; };
      let cleared = 0;
      const p = X.during("transcribe", () => new Promise((res) => setTimeout(() => res("done"), 5)),
        {el, getHealth: async () => ({stt_engine: "muse"}), setInterval, clearInterval: () => { cleared += 1; },
         now: () => now});
      await new Promise((res) => setTimeout(res, 5));
      const first = el.textContent;
      now += 3000; cb();
      const third = el.textContent;
      const out = await p;
      cb();
      console.log(JSON.stringify({first, third, out, cleared, last: el.textContent}));
    })();""")
    assert r["first"] == "Transcribing with Muse Voice… 0 s"
    assert r["third"] == "Transcribing with Muse Voice… 3 s"
    assert r["out"] == "done" and r["cleared"] == 1
    assert r["last"] == "Transcribing with Muse Voice… 3 s"  # stopped ticking: the last write stands


def test_during_stops_on_failure_too():
    r = _run("""(async () => {
      const el = {textContent: ""};
      let cleared = 0;
      try {
        await X.during("structure", () => Promise.reject(new Error("down")),
          {el, getHealth: async () => ({}), setInterval: () => 1, clearInterval: () => { cleared += 1; }});
      } catch (e) { console.log(JSON.stringify({cleared, error: e.message})); }
    })();""")
    assert r == {"cleared": 1, "error": "down"}


def test_app_hooks_the_ticker_at_exactly_two_call_sites():
    app = (FRONT / "app.js").read_text()
    assert app.count('.during("transcribe"') == 1
    assert app.count('.during("structure"') == 1
    assert "DDExpand.heard" in app and "DDExpand.drafted" in app  # Task 4 Expand intact
    html = (FRONT / "index.html").read_text()
    assert '<script src="stepinfo.js?v=1"></script>' in html
