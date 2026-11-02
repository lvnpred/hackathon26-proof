"""Save & admit to ward, the page side (frontend/admit.js under node with fake env objects; the wiring as text)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_HARNESS = r"""
const statuses = []; const asked = []; const urls = []; const waits = [];
const mkEnv = (extra) => Object.assign({
  reason: () => "Hernia repair", askReason: () => asked.push(1), setStatus: (m) => statuses.push(m),
  wait: async (ms) => waits.push(ms), save: async () => ({ document_id: 7 }),
}, extra);
const answers = (list) => async (u) => { urls.push(u); const a = list.shift() || { status: 200, body: {} };
  return { status: a.status, ok: a.status < 300, json: async () => a.body }; };
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"const Admit = require({json.dumps(str(FRONT / 'admit.js'))});" + _HARNESS + "(async () => {" + body + "})();"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_fixed_copy():
    r = _run("console.log(JSON.stringify(Admit.MSG));")
    assert r["sending"] == "Saved. Sending to Count Guard…" and r["done"] == "Saved and in Count Guard."
    assert r["notYet"] == "Saved. Not yet in Count Guard — use Sync there."


def test_admit_sends_the_reason_then_reports_in_count_guard():
    r = _run(r"""
    let seen = null;
    const env = mkEnv({ save: async () => { seen = globalThis.ddAdmit; return { document_id: 7 }; },
                        fetch: answers([{ status: 200, body: { status: "admit", pushed_at: null, last_error: null } },
                                        { status: 200, body: { status: "admit", pushed_at: "2026-11-03T10:14:05Z" } }]) });
    const msg = await Admit.admitAndSave(env);
    console.log(JSON.stringify({ msg, seen, after: globalThis.ddAdmit === undefined, statuses, urls, waits }));""")
    assert r["seen"] == {"admit": True, "admit_reason": "Hernia repair"} and r["after"] is True
    assert r["statuses"] == ["Saved. Sending to Count Guard…", "Saved and in Count Guard."] and r["msg"] == r["statuses"][-1]
    assert r["urls"] == ["/api/v1/documents/7/admission"] * 2 and r["waits"] == [1000, 1000]


def test_last_error_or_timeout_says_use_sync():
    r = _run(r"""
    const a = await Admit.admitAndSave(mkEnv({ fetch: answers([{ status: 200, body: { status: "admit", last_error: "x" } }]) }));
    const n = urls.length;
    const b = await Admit.admitAndSave(mkEnv({ fetch: answers([]) }));
    console.log(JSON.stringify({ a, b, n, tries: urls.length - n }));""")
    assert r["a"] == r["b"] == "Saved. Not yet in Count Guard — use Sync there."
    assert r["n"] == 1 and r["tries"] == 5


def test_no_reason_asks_and_never_saves_and_a_failed_save_clears_the_flag():
    r = _run(r"""
    let saves = 0;
    const none = await Admit.admitAndSave(mkEnv({ reason: () => "  ", save: async () => { saves++; return {}; } }));
    let threw = false;
    try { await Admit.admitAndSave(mkEnv({ save: async () => { throw new Error("x"); } })); } catch (e) { threw = true; }
    const blocked = await Admit.admitAndSave(mkEnv({ save: async () => undefined, fetch: answers([]) }));
    console.log(JSON.stringify({ none, saves, asked: asked.length, threw, flag: "ddAdmit" in globalThis, blocked, statuses }));""")
    assert r["none"] is None and r["saves"] == 0 and r["asked"] == 1
    assert r["threw"] is True and r["flag"] is False and r["blocked"] is None
    assert r["statuses"] == ["Type the reason for admission, then press “Save & admit to ward” again."]


def test_page_wiring():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert ">Save &amp; send home</button>" in html and ">Save &amp; admit to ward</button>" in html
    assert 'id="admitReason"' in html and 'id="admitRow"' in html
    assert html.index("app.js?v=62") < html.index("admit.js?v=1")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "if (window.ddAdmit) Object.assign(payload, window.ddAdmit)" in app and "    return j;\n  } catch (e) {" in app
    assert '"Save & send home"' in (FRONT / "rxstate.js").read_text(encoding="utf-8")
