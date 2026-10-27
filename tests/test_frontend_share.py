"""Share dialog (plan FB-D, C2). frontend/share.js runs under node with a fake DOM, fetch, window.open and confirm; the page
wiring is checked as text."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"

_HARNESS = r"""
globalThis.window = globalThis;
const mkEl = () => { const h = {}; return { hidden: false, disabled: false, value: "", textContent: "", src: "", title: "",
  addEventListener(t, f) { (h[t] = h[t] || []).push(f); }, fire(t) { (h[t] || []).forEach((f) => f({ preventDefault() {} })); } }; };
const ids = ["shareBtn", "shareDlg", "shareQr", "shareLink", "shareUntil", "shareTel", "shareWa", "shareMail", "shareRevoke", "shareMsg", "shareCopy", "shareClose",
  "shareEmail", "shareVia", "shareSms", "shareMore", "shareCopyMsg"];
const els = {}; ids.forEach((i) => { els[i] = mkEl(); });
let shows = 0; els.shareDlg.open = false;
els.shareDlg.showModal = () => { if (els.shareDlg.open) throw new Error("already open"); shows++; els.shareDlg.open = true; els.shareDlg.opened = true; };
els.shareDlg.close = () => { els.shareDlg.open = false; els.shareDlg.opened = false; els.shareDlg.fire("close"); };
globalThis.document = { getElementById: (id) => els[id] || null };
const log = []; const opened = []; const answers = [];
globalThis.fetch = async (url, opts) => { log.push((opts && opts.method || "GET") + " " + url); const a = answers.shift();
  return { ok: a.status === 200, status: a.status, json: async () => a.body }; };
globalThis.open = (...a) => opened.push(a);
globalThis.confirm = () => globalThis.__confirm;
globalThis.__confirm = true;
const store = {}; globalThis.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
const copied = []; const shared = [];
Object.defineProperty(globalThis, "navigator", { configurable: true, writable: true,   // node 21+ has a read-only one
  value: { clipboard: { writeText: async (t) => { copied.push(t); } } } });
globalThis.location = { href: "" };
globalThis.__coarse = false; globalThis.matchMedia = () => ({ matches: globalThis.__coarse });
const LIVE = { url: "https://x/s/rao/T", valid_until: "2 Nov 2026", active: true, revoked: false, can_revoke: true,
  qr: "data:image/svg+xml;base64,AAA", subject: "Your prescription", message: "Ready (valid until 2 Nov 2026): https://x/s/rao/T" };
const tick = () => new Promise((r) => setTimeout(r, 0));
"""


def _run(body):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = _HARNESS + f"const Share = require({json.dumps(str(FRONT / 'share.js'))});" + "(async () => {" + body + "})();"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_phone_numbers_become_wa_me_digits():
    raw = ["98480 12345", "098480-12345", "+91 98480 12345", "919848012345", "+44 7700 900123", "12345", "", "5848012345", None]
    r = _run(f"console.log(JSON.stringify({json.dumps(raw)}.map((x) => Share.normalizePhone(x))));")
    assert r == ["919848012345", "919848012345", "919848012345", "919848012345", "447700900123", None, None, None, None]


def test_whatsapp_and_mail_links_are_built_exactly():
    r = _run("""console.log(JSON.stringify([Share.whatsappUrl("919848012345", "Valid until 2 Nov 2026: https://x/s/rao/T"), Share.mailtoUrl("Your prescription", "a&b"),
      Share.mailUrl("gmail", "p@x.in", "Your prescription", "a&b"), Share.mailUrl("outlook", "", "S", "b"), Share.mailUrl("app", "p@x.in", "S", "b"),
      Share.smsUrl("919848012345", "a b")]));""")
    assert r == ["https://wa.me/919848012345?text=Valid%20until%202%20Nov%202026%3A%20https%3A%2F%2Fx%2Fs%2Frao%2FT",
                 "mailto:?subject=Your%20prescription&body=a%26b",
                 "https://mail.google.com/mail/?view=cm&fs=1&to=p%40x.in&su=Your%20prescription&body=a%26b",
                 "https://outlook.live.com/mail/0/deeplink/compose?to=&subject=S&body=b",
                 "mailto:p%40x.in?subject=S&body=b",
                 "sms:+919848012345?&body=a%20b"]


def test_the_dialog_shows_the_link_and_revokes_through_the_server():
    r = _run("""
      Share.init({ documentId: () => 7 });
      answers.push({ status: 200, body: LIVE });
      els.shareBtn.fire("click"); await tick();
      const res = { first: log.slice(), link: els.shareLink.value, until: els.shareUntil.textContent, qr: els.shareQr.src, opened: els.shareDlg.opened,
        waBefore: els.shareWa.disabled, revokeShown: !els.shareRevoke.hidden };
      els.shareTel.value = "9848012345"; els.shareTel.fire("input");
      res.waAfter = els.shareWa.disabled;
      els.shareWa.fire("click");
      res.wa = opened[0];
      answers.push({ status: 200, body: { revoked: true } });
      answers.push({ status: 200, body: Object.assign({}, LIVE, { active: false, revoked: true }) });
      els.shareRevoke.fire("click"); await tick(); await tick();
      res.log = log.slice(); res.msg = els.shareMsg.textContent; res.qrHidden = els.shareQr.hidden; res.waHidden = els.shareWa.hidden;
      answers.push({ status: 404, body: { error: "no share link for this prescription" } });
      els.shareBtn.fire("click"); await tick();
      res.nolink = els.shareMsg.textContent;
      res.shows = shows;
      console.log(JSON.stringify(res));""")
    assert r["first"] == ["GET /api/v1/documents/7/share"] and r["link"] == "https://x/s/rao/T"
    assert r["until"] == "Valid until 2 Nov 2026" and r["qr"].startswith("data:image/svg+xml") and r["opened"] and r["revokeShown"]
    assert r["waBefore"] is True and r["waAfter"] is False
    assert r["wa"][0].startswith("https://wa.me/919848012345?text=") and r["wa"][1:] == ["_blank", "noopener"]
    assert r["log"][1:] == ["POST /api/v1/documents/7/share/revoke", "GET /api/v1/documents/7/share"]
    assert r["msg"] == "This link was turned off." and r["qrHidden"] is True and r["waHidden"] is True
    assert r["shows"] == 1                       # the revoke re-open did not call showModal on an open dialog
    assert r["nolink"] == "This prescription was saved before sharing was added."


def test_the_page_wires_share_next_to_print():
    html = (FRONT / "index.html").read_text()
    app = (FRONT / "app.js").read_text()
    assert "share.js?v=4" in html and html.index("share.js?v=") < html.index("app.js?v=")
    assert 'id="shareBtn"' in html and 'id="shareDlg"' in html
    assert "Share.init({ documentId: () => state.documentId })" in app
    body = app[app.index("function refreshPrintButton"):]
    assert "Share.sync(printBtn)" in body[:body.index("\n}")]


def test_a_new_prescription_never_inherits_the_previous_phone_number():
    r = _run("""
      let id = 7; Share.init({ documentId: () => id });
      answers.push({ status: 200, body: LIVE });
      els.shareBtn.fire("click"); await tick();
      els.shareTel.value = "9848012345"; els.shareTel.fire("input");
      const typed = els.shareWa.disabled;
      els.shareDlg.close();
      id = 8; answers.push({ status: 200, body: LIVE });
      els.shareBtn.fire("click"); await tick();
      console.log(JSON.stringify({ typed, tel: els.shareTel.value, wa: els.shareWa.disabled }));""")
    assert r == {"typed": False, "tel": "", "wa": True}


def test_failures_show_calm_messages_and_never_throw():
    r = _run("""
      Share.init({ documentId: () => 7 }); const msgs = [];
      globalThis.fetch = async () => { throw new Error("offline"); };
      els.shareBtn.fire("click"); await tick(); msgs.push(els.shareMsg.textContent);
      globalThis.fetch = async (u, o) => { log.push(1); const a = answers.shift(); return { ok: a.status === 200, status: a.status, json: async () => a.body }; };
      els.shareDlg.close();
      answers.push({ status: 404, body: { error: "document_id 7 not found" } }); els.shareBtn.fire("click"); await tick(); msgs.push(els.shareMsg.textContent);
      els.shareDlg.close();
      answers.push({ status: 200, body: Object.assign({}, LIVE, { active: false, revoked: false }) }); els.shareBtn.fire("click"); await tick(); msgs.push(els.shareMsg.textContent);
      els.shareDlg.close();
      answers.push({ status: 200, body: Object.assign({}, LIVE, { qr: "https://evil/x.svg" }) }); els.shareBtn.fire("click"); await tick();
      const qr = { hidden: els.shareQr.hidden, src: els.shareQr.src };
      answers.push({ status: 403, body: { error: "Only the author or an admin can turn this off" } }); els.shareRevoke.fire("click"); await tick();
      msgs.push(els.shareMsg.textContent);
      console.log(JSON.stringify({ msgs, qr }));""")
    assert r["msgs"] == ["The share link could not be loaded. Please try again.", "This prescription could not be found.",
                         "This link expired on 2 Nov 2026. Save the prescription again for a new one.", "Only the author or an admin can turn this off"]
    assert r["qr"] == {"hidden": True, "src": ""}


def test_share_follows_print_while_working():
    app = (FRONT / "app.js").read_text()
    line = next(x for x in app.splitlines() if "if (on) { printBtn.disabled = true" in x)
    assert "Share.sync(printBtn)" in line


def test_an_expired_link_says_save_again_only_when_a_new_link_is_possible():
    r = _run("""
      Share.init({ documentId: () => 7 });
      const dead = Object.assign({}, LIVE, { active: false, revoked: false, valid_until: "2 Nov 2026" });
      answers.push({ status: 200, body: Object.assign({}, dead, { renewable: true }) });
      els.shareBtn.fire("click"); await tick();
      const same = els.shareMsg.textContent;
      answers.push({ status: 200, body: Object.assign({}, dead, { renewable: false }) });
      els.shareBtn.fire("click"); await tick();
      console.log(JSON.stringify({ same, past: els.shareMsg.textContent }));""")
    assert r["same"] == "This link expired on 2 Nov 2026. Save the prescription again for a new one."
    assert r["past"] == "This link can no longer be used. Print a fresh copy for the patient."


def test_emails_are_optional_but_a_bad_one_blocks_the_email_button():
    raw = ["", "  ", "ravi@example.in", " ravi.k+rx@mail.co.uk ", "ravi@", "ravi example.in", "a@b", "a@b.c,d@e.f", None]
    r = _run(f"console.log(JSON.stringify({json.dumps(raw)}.map((x) => Share.normalizeEmail(x))));")
    assert r == ["", "", "ravi@example.in", "ravi.k+rx@mail.co.uk", None, None, None, None, ""]


def test_email_opens_the_chosen_webmail_in_a_new_tab_and_remembers_the_choice():
    r = _run("""
      Share.init({ documentId: () => 7 });
      const first = els.shareVia.value;
      answers.push({ status: 200, body: LIVE });
      els.shareBtn.fire("click"); await tick();
      const res = { first, mailOn: !els.shareMail.disabled };
      els.shareEmail.value = "ravi@"; els.shareEmail.fire("input");
      res.badOff = els.shareMail.disabled; res.badTitle = els.shareMail.title;
      els.shareMail.fire("click"); res.badOpened = opened.length;
      els.shareEmail.value = "ravi@example.in"; els.shareEmail.fire("input");
      els.shareMail.fire("click"); res.gmail = opened[0];
      els.shareVia.value = "outlook"; els.shareVia.fire("change");
      els.shareMail.fire("click"); res.outlook = opened[1][0];
      els.shareVia.value = "app"; els.shareVia.fire("change");
      els.shareMail.fire("click"); res.app = location.href; res.tabs = opened.length; res.kept = store["dd.mailVia"];
      els.shareDlg.close(); res.emailAfter = els.shareEmail.value;
      console.log(JSON.stringify(res));""")
    assert r["first"] == "gmail" and r["mailOn"] is True
    assert r["badOff"] is True and r["badTitle"] == "Check the patient's email address" and r["badOpened"] == 0
    assert r["gmail"][0].startswith("https://mail.google.com/mail/?view=cm&fs=1&to=ravi%40example.in&su=") and r["gmail"][1:] == ["_blank", "noopener"]
    assert r["outlook"].startswith("https://outlook.live.com/mail/0/deeplink/compose?to=ravi%40example.in&")
    assert r["app"].startswith("mailto:ravi%40example.in?subject=") and r["tabs"] == 2 and r["kept"] == "app"
    assert r["emailAfter"] == ""                 # the patient's email never outlives the dialog


def test_a_saved_choice_is_restored_and_a_bad_one_falls_back_to_gmail():
    r = _run("""
      store["dd.mailVia"] = "outlook"; Share.init({ documentId: () => 7 }); const a = els.shareVia.value;
      store["dd.mailVia"] = "yahoo"; Share.init({ documentId: () => 7 }); const b = els.shareVia.value;
      globalThis.localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
      Share.init({ documentId: () => 7 }); const c = els.shareVia.value;
      els.shareVia.value = "app"; els.shareVia.fire("change");
      console.log(JSON.stringify([a, b, c]));""")
    assert r == ["outlook", "gmail", "gmail"]


def test_copy_message_sms_and_the_phone_share_sheet():
    r = _run("""
      Share.init({ documentId: () => 7 });
      answers.push({ status: 200, body: LIVE });
      els.shareBtn.fire("click"); await tick();
      const res = { smsDesk: els.shareSms.hidden, moreDesk: els.shareMore.hidden };
      els.shareCopyMsg.fire("click"); await tick(); res.copied = copied[0]; res.msg = els.shareMsg.textContent;
      globalThis.__coarse = true; navigator.share = async (d) => { shared.push(d); };
      els.shareDlg.close(); answers.push({ status: 200, body: LIVE }); els.shareBtn.fire("click"); await tick();
      res.smsPhone = els.shareSms.hidden; res.morePhone = els.shareMore.hidden; res.smsOff = els.shareSms.disabled;
      els.shareTel.value = "9848012345"; els.shareTel.fire("input");
      els.shareSms.fire("click"); res.sms = location.href;
      els.shareMore.fire("click"); await tick(); res.shared = shared[0];
      navigator.share = async () => { const e = new Error("x"); e.name = "AbortError"; throw e; };
      els.shareMsg.textContent = ""; els.shareMore.fire("click"); await tick(); res.cancel = els.shareMsg.textContent;
      console.log(JSON.stringify(res));""")
    assert r["smsDesk"] is True and r["moreDesk"] is True
    assert r["copied"] == "Ready (valid until 2 Nov 2026): https://x/s/rao/T" and r["msg"] == "Message copied."
    assert r["smsPhone"] is False and r["morePhone"] is False and r["smsOff"] is True
    assert r["sms"] == "sms:+919848012345?&body=Ready%20(valid%20until%202%20Nov%202026)%3A%20https%3A%2F%2Fx%2Fs%2Frao%2FT"
    assert r["shared"] == {"title": "Your prescription", "text": "Ready (valid until 2 Nov 2026): https://x/s/rao/T"}
    assert r["cancel"] == ""                     # closing the share sheet is not an error
