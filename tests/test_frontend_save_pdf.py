"""Save PDF (owner feedback E6). frontend/savepdf.js runs under node with fake env/fetch objects; the page wiring is
checked as text."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

# A fake browser: an anchor that records clicks and a URL that records create/revoke.
_HARNESS = r"""
globalThis.window = globalThis;
const clicks = []; const revoked = []; const timers = []; const attached = [];
const mkEnv = (extra) => Object.assign({
  setTimeout: (f, ms) => timers.push([f, ms]),
  document: { body: { append: (a) => attached.push(a) }, createElement: () => { const a = { click() { clicks.push(a); }, remove() { a.removed = attached.includes(a); } }; return a; } },
  URL: { createObjectURL: () => "blob:x", revokeObjectURL: (u) => revoked.push(u) },
}, extra);
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"const SavePdf = require({json.dumps(str(FRONT / 'savepdf.js'))});" + _HARNESS + "(async () => {" + body + "})();"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_file_name_rule():
    r = _run(r"""
    const f = SavePdf.fileName;
    console.log(JSON.stringify({
      full: f({ name: "Kodanda Pani", day: "2026-10-25", op: "OP-20261025-002" }),
      unsafe: f({ name: 'a/b:c*"d', day: "2026-10-25", op: "" }),
      noName: f({ name: "", day: "2026-10-25", op: "" }),
      none: f({ name: "", day: "", op: "" }),
      long: f({ name: "x".repeat(200), day: "2026-10-25", op: "" }),
      emoji: f({ name: "Ravi \u{1F600} Kumar", day: "", op: "" }),
      pipes: f({ name: "a\\b<c>d|e?f", day: "", op: "" }),
    }));""")
    assert r["full"] == "Kodanda Pani 2026-10-25 OP-20261025-002.pdf"
    assert r["unsafe"] == "abcd 2026-10-25.pdf"
    assert r["noName"] == "2026-10-25.pdf"
    assert r["none"] == "prescription.pdf"
    assert r["long"].endswith(".pdf") and len(r["long"]) <= 120 + 4
    assert r["emoji"] == "Ravi Kumar.pdf"
    assert r["pipes"] == "abcdef.pdf"


def test_picker_path_writes_the_blob_and_returns_picked():
    r = _run(r"""
    const log = []; let opts = null;
    const env = mkEnv({ showSaveFilePicker: async (o) => { opts = o; return { createWritable: async () => ({ write: async (b) => log.push(["write", b]), close: async () => log.push(["close"]) }) }; } });
    const how = await SavePdf.save("BLOB", "A 2026-10-25.pdf", env);
    console.log(JSON.stringify({ how, opts, log, clicks: clicks.length }));""")
    assert r["how"] == "picked"
    assert r["opts"]["suggestedName"] == "A 2026-10-25.pdf"
    assert r["opts"]["types"] == [{"description": "PDF", "accept": {"application/pdf": [".pdf"]}}]
    assert r["log"] == [["write", "BLOB"], ["close"]] and r["clicks"] == 0


def test_cancel_is_silent():
    r = _run(r"""
    const env = mkEnv({ showSaveFilePicker: async () => { throw { name: "AbortError" }; } });
    console.log(JSON.stringify({ how: await SavePdf.save("B", "n.pdf", env), clicks: clicks.length }));""")
    assert r == {"how": "cancelled", "clicks": 0}


def test_other_picker_errors_reject():
    r = _run(r"""
    const env = mkEnv({ showSaveFilePicker: async () => { throw new Error("disk full"); } });
    let msg = ""; try { await SavePdf.save("B", "n.pdf", env); } catch (e) { msg = e.message; }
    console.log(JSON.stringify({ msg }));""")
    assert r == {"msg": "disk full"}


def test_fallbacks_download_when_no_picker_or_activation_expired():
    r = _run(r"""
    const out = [];
    for (const extra of [{}, { showSaveFilePicker: async () => { throw { name: "SecurityError" }; } }]) {
      clicks.length = 0; revoked.length = 0; timers.length = 0; attached.length = 0;
      const how = await SavePdf.save("B", "n.pdf", mkEnv(extra));
      const early = revoked.slice(), a = clicks[0];
      timers.forEach(([f]) => f());
      out.push({ how, download: a.download, clicks: clicks.length, attached: attached.length, removed: a.removed, early, delay: timers[0][1], revoked: revoked.slice() });
    }
    console.log(JSON.stringify(out));""")
    for o in r:
        assert o == {"how": "downloaded", "download": "n.pdf", "clicks": 1, "attached": 1, "removed": True,
                     "early": [], "delay": 30000, "revoked": ["blob:x"]}


def test_fetch_pdf_rejects_a_non_pdf_answer():
    r = _run(r"""
    const mk = (status, ct) => { const calls = []; const f = async (u, o) => { calls.push([u, o]); return { ok: status === 200, status, headers: { get: () => ct }, blob: async () => "PDFBLOB" }; }; return { f, calls }; };
    const res = {};
    for (const [k, s, ct] of [["err", 500, "application/pdf"], ["html", 200, "text/html"]]) {
      try { await SavePdf.fetchPdf(7, mk(s, ct).f); res[k] = "resolved"; } catch (e) { res[k] = "rejected"; }
    }
    const ok = mk(200, "application/pdf");
    res.blob = await SavePdf.fetchPdf(7, ok.f); res.call = ok.calls[0];
    console.log(JSON.stringify(res));""")
    assert r["err"] == "rejected" and r["html"] == "rejected" and r["blob"] == "PDFBLOB"
    assert r["call"] == ["/api/v1/documents/7/pdf", {"cache": "no-store"}]


def test_page_wires_the_button_like_print():
    html = (FRONT / "index.html").read_text()
    app = (FRONT / "app.js").read_text()
    assert html.index('id="printBtn"') < html.index('id="savePdfBtn"') < html.index('id="printBtn"') + 700
    assert html.index("savepdf.js?v=2") < html.index("app.js?v=51")
    assert "savePdfBtn.disabled = printBtn.disabled" in app
    assert app.count("savePdfBtn.hidden = printBtn.hidden") == 2
    assert "SavePdf.fetchPdf" in app and "SavePdf.save" in app
