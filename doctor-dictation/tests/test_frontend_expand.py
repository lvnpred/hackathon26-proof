"""Expand on the draft (care-app clarity §4.7): the recording, the transcript, the engine, and the draft as first produced
against the doctor's edits (frontend/expand.js under node; the wiring in app.js and index.html as text)."""
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
    script = f"const X = require({json.dumps(str(FRONT / 'expand.js'))});" + body
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


FIRST = {"patientName": "R. Kumar", "diagnosis": ["Inguinal hernia"],
         "rx": [{"name": "Paracetamol", "dose": "500 mg", "frequency": "TDS"}], "advice": ""}


def test_the_four_parts_name_what_went_in_what_came_back_how_it_was_used_and_the_edits():
    current = {**FIRST, "patientName": "R. Kumar", "advice": "Rest for a week",
               "rx": [{"name": "Paracetamol", "dose": "650 mg", "frequency": "TDS"}]}
    r = _run(f"""
    const p = X.parts({{ audioUrl: "blob:x", transcript: "paracetamol five hundred tds", engine: "groq · llama",
                         stt: "muse", cached: false, first: {json.dumps(FIRST)}, current: {json.dumps(current)} }});
    console.log(JSON.stringify(p));""")
    assert [part["title"] for part in r["list"]] == ["Captured", "Model returned", "How the app used it", "What a person did"]
    assert r["captured"]["audio"] == "blob:x" and r["captured"]["transcript"] == "paracetamol five hundred tds"
    assert r["returned"]["lines"] == ["Transcribed by muse", "Drafted by groq · llama"]
    assert "Patient name: R. Kumar" in r["used"]["lines"]
    assert "Rx: Paracetamol 500 mg TDS" in r["used"]["lines"]
    assert r["people"]["changes"] == [
        {"field": "Rx", "before": "Paracetamol 500 mg TDS", "after": "Paracetamol 650 mg TDS"},
        {"field": "Advice", "before": "—", "after": "Rest for a week"},
    ]
    assert r["people"]["text"] == "Changed by the doctor (2 fields)"


def test_no_edits_and_no_draft_say_so():
    r = _run(f"""console.log(JSON.stringify([
      X.parts({{ transcript: "t", engine: "stub", first: {json.dumps(FIRST)}, current: {json.dumps(FIRST)} }}).people,
      X.parts({{ transcript: "", engine: "", first: null, current: null }})]));""")
    assert r[0] == {"text": "Not changed by the doctor yet", "changes": []}
    assert r[1]["captured"]["audio"] is None and r[1]["used"]["lines"] == []
    assert r[1]["returned"]["lines"] == ["No draft yet"]


def test_a_cached_draft_says_so():
    r = _run(f"""console.log(JSON.stringify(X.parts({{ transcript: "t", engine: "deepseek", cached: true,
      first: {json.dumps(FIRST)}, current: {json.dumps(FIRST)} }}).returned.lines));""")
    assert r == ["Drafted by deepseek (cached: the same words were drafted before)"]


def test_the_page_wiring():
    src = (FRONT / "expand.js").read_text()
    assert '"data-expand": "open"' in src and '"data-expand": "closed"' in src
    assert "innerHTML" not in src  # the transcript and fields are text, never markup
    assert 'el("audio"' in src and "controls" in src  # the recording plays
    app = (FRONT / "app.js").read_text()
    assert "DDExpand.keepAudio(blob)" in app and "DDExpand.drafted(transcript, j)" in app
    html = (FRONT / "index.html").read_text()
    assert html.index('src="app.js') < html.index('src="expand.js')


def test_a_correction_resets_the_base_and_each_recording_keeps_its_own_transcript_and_engine():
    r = _run("""
    X.keepAudio(new Blob(["first"]));
    X.heard({ transcript: "paracetamol five hundred", engine: "muse" });
    X.drafted("paracetamol five hundred", { engine: "groq", structured: { rx: "Paracetamol 500 mg" } });
    const one = X.snapshot();
    X.keepAudio(new Blob(["second"]));
    const pending = X.snapshot();
    X.heard({ transcript: "make it six fifty", engine: "faster-whisper" });
    X.drafted("make it six fifty", { engine: "groq", structured: { rx: "Paracetamol 650 mg" } });
    const two = X.snapshot();
    console.log(JSON.stringify({ one, pending, two }));""")
    one, pending, two = r["one"], r["pending"], r["two"]
    assert one["transcript"] == "paracetamol five hundred" and one["stt"] == "muse" and one["audioUrl"].startswith("blob:")
    assert pending["audioUrl"] == one["audioUrl"] and pending["transcript"] == one["transcript"]  # paired only once heard
    assert two["transcript"] == "make it six fifty" and two["stt"] == "faster-whisper" and two["audioUrl"] != one["audioUrl"]
    assert two["first"] == {"rx": "Paracetamol 650 mg"}  # the corrected draft is the new base for the doctor's edits


def test_a_correction_and_the_transcribe_reply_are_wired():
    app = (FRONT / "app.js").read_text()
    assert "DDExpand.heard(j)" in app
    assert "DDExpand.drafted(transcript, { ...j, structured: state.structured })" in app
    assert "/api/health" not in (FRONT / "expand.js").read_text()
