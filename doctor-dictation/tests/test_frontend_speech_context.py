"""Plan SH-H3: a spoken correction sends the sheet's diagnosis and patient as `context`; a first dictation sends none."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _fn(src, head):
    part = src[src.index(head):]
    return part[:part.index("\n}\n") + 3]


def test_a_correction_sends_the_sheets_diagnosis_and_patient_and_a_first_dictation_sends_nothing():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    script = """
      globalThis.FormData = class { constructor() { this.f = {}; } append(k, v) { this.f[k] = v; } };
      const sent = []; globalThis.fetch = async (url, o) => { sent.push(o.body.f); return { ok: true, status: 200, json: async () => ({ transcript: "x" }) }; };
      const safeJson = async (r) => r.json(), setWorking = () => {}, setStep = () => {}, TRANSCRIBE_TIMEOUT_MS = 1000;
      const recCap = { capped: () => false, stopText: "" };
      const sheet = { pName: "  Asha Verma ", pAge: "40 / F", pOp: "OP 7" }; let dx = [" Acute pharyngitis ", "", "Fever"];
      const $ = (id) => ({ id }), text = (el) => sheet[el.id] || "", readList = (id) => (id === "pDx" ? dx : []);
      const state = { pendingMode: "correct", structured: { rx: [] } };
      """ + _fn(app, "function patientContext") + _fn(app, "function speechContext") + _fn(app, "async function transcribe(") + """
      (async () => {
        await transcribe("blob");
        state.pendingMode = "dictate"; await transcribe("blob");
        state.pendingMode = "correct"; state.structured = null; await transcribe("blob");
        dx = Array.from({ length: 12 }, (_, i) => String(i) + "x".repeat(250)); const many = JSON.parse(speechContext()).diagnosis;
        dx = Array.from({ length: 10 }, () => "अ".repeat(200)); const wide = speechContext();
        console.log(JSON.stringify({ keys: sent.map((f) => Object.keys(f)), first: JSON.parse(sent[0].context),
          many: [many.length, many[0].length, many[9].slice(0, 2)], bytes: new TextEncoder().encode(wide).length, lines: JSON.parse(wide).diagnosis.length }));
      })();"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["keys"] == [["audio", "context"], ["audio"], ["audio"]]          # a correction only, and only with a draft
    assert r["first"] == {"diagnosis": ["Acute pharyngitis", "Fever"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": "OP 7"}}
    assert r["many"] == [10, 200, "9x"]                                       # at most 10 lines of 200 characters
    assert r["bytes"] <= 4096 and r["lines"] == 6                             # whole lines dropped from the end to fit


def test_say_it_sends_the_context_and_the_name_mode_and_takes_the_name():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    script = """
      globalThis.FormData = class { constructor() { this.f = {}; } append(k, v) { this.f[k] = v; } };
      const sent = [], answers = [{ transcript: "Eltroxin, E-L-T-R-O-X-I-N", name: "Eltroxin" }, { transcript: "Dolo 650" }];
      globalThis.fetch = async (url, o) => { sent.push([url, o.body.f]); return { ok: true, status: 200, json: async () => answers.shift() }; };
      const safeJson = async (r) => r.json();
      const speechContext = () => '{"diagnosis":[],"patient":{"name":"Asha Verma","age_sex":"","op_no":""}}';
      """ + _fn(app, "async function transcribeName") + """
      (async () => {
        const out = [await transcribeName("blob"), await transcribeName("blob")];
        console.log(JSON.stringify({ keys: sent.map(([, f]) => Object.keys(f).sort()), modes: sent.map(([, f]) => f.mode), urls: sent.map(([u]) => u),
          ctx: sent[0][1].context, out }));
      })();"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["keys"] == [["audio", "context", "mode"]] * 2 and r["modes"] == ["name", "name"] and r["urls"] == ["/api/transcribe"] * 2
    assert json.loads(r["ctx"])["patient"]["name"] == "Asha Verma" and r["out"] == ["Eltroxin", "Dolo 650"]


def test_dictation_corrections_and_say_it_send_context_and_say_it_sends_the_name_mode():
    app, html = (FRONT / "app.js").read_text(encoding="utf-8"), (FRONT / "index.html").read_text(encoding="utf-8")
    assert int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 52
    assert app.count('fd.append("context", speechContext())') == 2 and 'fd.append("mode", "name")' in _fn(app, "async function transcribeName")
