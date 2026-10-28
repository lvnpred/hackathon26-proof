"""Browser evidence for the multi-clinic demo (spec 13.1 "Browser" and the 13.2 demo script).

Signs Dr. Rao and Dr. Iyer in to two separate browser contexts (separate cookie jars, like two windows), later
Dr. Mehta in a third, walks the six demo steps against a RUNNING server, and saves screenshots, PDFs and an
evidence.txt log under .superpowers/demo-evidence/<timestamp>/ (git-ignored). Automatic checks print PASS/FAIL;
a person still reads every screenshot (the list is in the M6 plan, Task 9).

    .venv/bin/python scripts/demo_browser.py --print-env      # the stub STT/LLM settings the server must use
    .venv/bin/python scripts/demo_browser.py --base http://127.0.0.1:8765 --data-dir <the server's DATA_DIR>
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from doctor_dictation import scope  # noqa: E402
from doctor_dictation.admin_demo import DOCTORS  # noqa: E402

PwTimeout = TimeoutError    # replaced by Playwright's TimeoutError in main(); Playwright is only needed for a real run
LOOPBACK = {"127.0.0.1", "localhost", "::1"}

EVIDENCE = ROOT / ".superpowers" / "demo-evidence"
STEPS = ("1-two-windows", "2-rao-dictates-and-saves", "3-mehta-views-reprints-edit-refused", "4-letterheads",
         "5-pasted-link-404", "6-audit-and-data-folder")
PASSWORD = {d["username"]: d["password"] for d in DOCTORS}
JSON_HEADERS = {"Content-Type": "application/json", "X-DD-Client": "1"}
NEW_PATIENT = "Kiran Joshi"
STUB_FORM = {"patientName": NEW_PATIENT, "ageSex": "40 / M", "opNo": "", "diagnosis": ["Viral fever"],
             "complaints": ["Fever since 2 days"], "investigations": [],
             "rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-0-1",
                     "timing": "After food", "duration": "3 days", "instructions": ""}],
             "advice": ["Plenty of fluids"], "review": "Review after 3 days"}
SERVER_ENV = {"ALLOW_STUB_PROVIDERS": "1", "STT_CHAIN": "stub", "LLM_PROVIDER": "stub",
              "STUB_TRANSCRIPT": "patient Kiran Joshi 40 year old male, fever since two days, tablet paracetamol "
                                 "650 mg twice daily after food for 3 days",
              "STUB_LLM_JSON": json.dumps(STUB_FORM)}


class DemoFail(Exception):
    """A step could not run at all (sign-in refused, an API call failed): reported as a FAIL line, exit 1."""


def check_data_dir(path: Path) -> str | None:
    """Why this folder must not be used for the demo, or None. Step 6 only reads it, but a demo run against real
    data would still sign in with the published passwords, so the folder must be a seeded demo folder."""
    path = Path(path).resolve()
    default = scope.DEFAULT_DATA_DIR.resolve()
    if path == default or default in path.parents or path in default.parents:
        return f"{path} is the app's default data folder; use the temp DATA_DIR the demo server was seeded into"
    if not path.is_dir():
        return f"{path} is not a folder"
    single = [n for n in ("app.db", "pdfs", "templates") if (path / n).exists()]
    if single:
        return f"{path} holds single-clinic data ({', '.join(single)}); the demo needs a freshly seeded multi-clinic folder"
    return None


def check_base(url: str, allow_remote: bool = False) -> str | None:
    """Why this server address is refused, or None. The script tries the published demo passwords against it."""
    host = urlparse(url).hostname
    if host in LOOPBACK or allow_remote:
        return None
    return f"{url} is not a loopback address (127.0.0.1, localhost, ::1); pass --allow-remote only for a demo server"


def pdf_text(path: Path) -> str | None:
    """Text of a saved PDF through pdftotext, or None when the tool is missing."""
    tool = shutil.which("pdftotext")
    if tool is None:
        return None
    out = subprocess.run([tool, "-layout", str(path), "-"], capture_output=True, text=True, check=False)
    return out.stdout


class Evidence:
    """The log, the PASS/FAIL checks and the saved files of one run."""

    def __init__(self, out: Path):
        self.out, self.lines, self.failed, self.fallback = out, [], [], False
        out.mkdir(parents=True, exist_ok=True)

    def log(self, text: str) -> None:
        print(text, flush=True)
        self.lines.append(text)

    def check(self, ok: bool, what: str) -> None:
        self.log(("PASS  " if ok else "FAIL  ") + what)
        if not ok:
            self.failed.append(what)

    def shot(self, page, name: str) -> None:
        page.screenshot(path=str(self.out / f"{name}.png"), full_page=True)
        self.log(f"saved {name}.png")

    def save(self, name: str, body: bytes) -> None:
        (self.out / name).write_bytes(body)
        self.log(f"saved {name}")

    def check_pdf(self, name: str, wants: list[str], forbids: list[str]) -> None:
        text = pdf_text(self.out / name)
        if text is None:
            self.log(f"NOTE  pdftotext not on PATH: the text of {name} was not checked")
            return
        self.check(all(w in text for w in wants) and not any(f in text for f in forbids),
                   f"{name} contains {wants} and none of {forbids}")

    def close(self) -> None:
        (self.out / "evidence.txt").write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def wait_today(page) -> None:
    page.wait_for_selector("#todayList .today-item, #todayList .today-empty")


def today_names(page) -> list[str]:
    return page.locator("#todayList .today-item .today-name").all_inner_texts()


def visible(page, selector: str, timeout: int = 10_000) -> bool:
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        return True
    except PwTimeout:
        return False


def sign_in(browser, base: str, username: str):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, permissions=["microphone"])
    page = ctx.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    try:
        page.goto(f"{base}/login")
        page.fill("#username", username)
        page.fill("#password", PASSWORD[username])
        page.click("#loginForm button[type=submit]")
        page.wait_for_url(f"{base}/", timeout=15_000)
        page.wait_for_function("document.getElementById('topClinic').textContent.trim() !== 'Clinic'", timeout=15_000)
        wait_today(page)
    except PwTimeout as exc:
        raise DemoFail(f"{username} could not sign in at {base} (was the server seeded with seed-demo?): "
                       f"{str(exc).splitlines()[0]}") from exc
    return ctx, page


def api(ctx, base: str, method: str, path: str, body=None):
    r = ctx.request.fetch(base + path, method=method, headers=JSON_HEADERS,
                          data=None if body is None else json.dumps(body))
    return r.status, r.body()


def api_json(ctx, base: str, path: str):
    status, body = api(ctx, base, "GET", path)
    if status != 200:
        raise DemoFail(f"GET {path} answered {status}")
    return json.loads(body)


def switch_to_whole_clinic(page) -> bool:
    """A4 (M3): the Today toggle is #todayScope; its "Whole clinic" button has data-scope="clinic"."""
    try:
        page.click('#todayScope [data-scope="clinic"]', timeout=5_000)
        page.wait_for_timeout(800)
        return True
    except PwTimeout:
        return False


def dictate_and_save(ctx, page, base: str, ev: Evidence) -> None:
    """Fake microphone -> stub STT -> stub LLM -> Save. Falls back to the save API if no sheet appears."""
    try:
        page.click("#recBtn")
        page.wait_for_timeout(2_500)
        page.click("#recBtn")
        page.wait_for_selector("#saveBtn:not([hidden])", timeout=60_000)
        page.click("#saveBtn")
        if visible(page, "#blockPanel", timeout=3_000):       # the verify gate asks to confirm medicines
            page.click("#confirmAllBtn")
        page.wait_for_function("!document.getElementById('printBtn').disabled", timeout=60_000)
        ev.log("dictated through the fake microphone and saved with the Save button")
    except PwTimeout:
        form = {**STUB_FORM, "rx": [{**row, "status": "verified"} for row in STUB_FORM["rx"]]}
        status, _ = api(ctx, base, "POST", "/api/v1/documents", {"structured": form, "confirmed_rows": [0]})
        ev.fallback = True
        ev.log(f"FALLBACK: no sheet from the fake microphone; saved through the API instead (status {status})")


def run(browser, base: str, data_dir: Path, ev: Evidence) -> None:
    rao_ctx, rao = sign_in(browser, base, "dr.rao")
    iyer_ctx, iyer = sign_in(browser, base, "dr.iyer")

    ev.log(f"== {STEPS[0]}")
    ev.shot(rao, "1-rao-today")
    ev.shot(iyer, "1-iyer-today")
    rao_list, iyer_list = today_names(rao), today_names(iyer)
    ev.log(f"Rao Clinic Today: {rao_list}")
    ev.log(f"Iyer Clinic Today: {iyer_list}")
    ev.check(bool(rao_list) and bool(iyer_list) and not set(rao_list) & set(iyer_list), "the two Today lists differ")

    ev.log(f"== {STEPS[1]}")
    dictate_and_save(rao_ctx, rao, base, ev)
    new_id = max(row["document_id"] for row in api_json(rao_ctx, base, "/api/v1/encounters/today"))
    for page in (rao, iyer):
        page.reload()
        wait_today(page)
    ev.shot(rao, "2-rao-after-save")
    ev.shot(iyer, "2-iyer-unchanged")
    ev.check(NEW_PATIENT in today_names(rao) and NEW_PATIENT not in today_names(iyer),
             f"{NEW_PATIENT} (document {new_id}) shows in Rao Clinic only")
    firsts = {}
    for who, ctx in (("rao", rao_ctx), ("iyer", iyer_ctx)):
        page = ctx.new_page()
        page.goto(f"{base}/api/v1/documents/1")
        ev.shot(page, f"2-{who}-document-1")
        page.close()
        firsts[who] = api_json(ctx, base, "/api/v1/documents/1")["structured"]["patientName"]
    ev.check(firsts["rao"] != firsts["iyer"], f"document 1 is different in each clinic: {firsts}")

    ev.log(f"== {STEPS[2]}")
    mehta_ctx, mehta = sign_in(browser, base, "dr.mehta")
    switched = switch_to_whole_clinic(mehta)
    ev.shot(mehta, "3-mehta-whole-clinic")
    ev.check(switched and NEW_PATIENT in today_names(mehta), "Mehta's Whole clinic list shows Rao's new prescription")
    try:
        mehta.locator("#todayList .today-item", has_text=NEW_PATIENT).first.click(timeout=5_000)
    except PwTimeout:
        ev.log("could not click Rao's prescription in Mehta's Today list")
    banner = visible(mehta, "#viewOnlyBanner") and "view only" in mehta.inner_text("#viewOnlyBanner")
    ev.shot(mehta, "3-mehta-view-only")
    ev.check(banner, "a 'view only' banner shows on Rao's prescription")
    ev.check(mehta.is_disabled("#recBtn") and (mehta.is_hidden("#saveBtn") or mehta.is_disabled("#saveBtn")),
             "mic and Save are disabled for Mehta")
    status, body = api(mehta_ctx, base, "GET", f"/api/v1/documents/{new_id}/pdf")
    ev.save("3-mehta-reprint-of-rao.pdf", body)
    ev.check(status == 200 and body.startswith(b"%PDF"), f"Mehta can reprint Rao's prescription (status {status})")
    ev.check_pdf("3-mehta-reprint-of-rao.pdf", ["Dr. A. Rao"], [])
    doc = api_json(mehta_ctx, base, f"/api/v1/documents/{new_id}")
    rows = list(range(len(doc["structured"].get("rx") or [])))
    status, body = api(mehta_ctx, base, "POST", "/api/v1/documents",
                       {"structured": doc["structured"], "confirmed_rows": rows, "document_id": new_id})
    ev.log(f"Mehta re-saving Rao's prescription: {status} {body.decode('utf-8', 'replace')}")
    ev.check(status == 403, "Mehta's re-save of Rao's prescription is refused (403)")

    ev.log(f"== {STEPS[3]}")
    for who, ctx, page in (("rao", rao_ctx, rao), ("iyer", iyer_ctx, iyer)):
        status, body = api(ctx, base, "GET", "/api/v1/documents/1/pdf")
        ev.save(f"4-{who}-clinic-letterhead.pdf", body)
        ev.check(status == 200 and body.startswith(b"%PDF"), f"{who}: document 1 prints as a PDF")
        other = "Iyer Clinic" if who == "rao" else "Rao Clinic"
        mehta = ["Dr. S. Mehta"]                          # Rao's shared pad lists both doctors; Iyer's never does
        ev.check_pdf(f"4-{who}-clinic-letterhead.pdf", [f"{who.capitalize()} Clinic"] + (mehta if who == "rao" else []),
                     [other] + ([] if who == "rao" else mehta))
        page.click("#profileOpenBtn")
        page.wait_for_selector("#profilePanel[open]")
        page.wait_for_timeout(800)                       # the letterhead status loads after the dialog opens
        ev.shot(page, f"4-{who}-profile-letterhead")
        page.keyboard.press("Escape")

    ev.log(f"== {STEPS[4]}")
    link = f"{base}/api/v1/documents/{new_id}/pdf"
    resp = iyer.goto(link)
    got = resp.status if resp else None
    ev.shot(iyer, "5-iyer-opens-rao-pdf-link")
    ev.check(got == 404, f"Iyer opening {link} gets 404 (got {got})")

    ev.log(f"== {STEPS[5]}")
    ev.log(f"data folder {data_dir}:")
    for f in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        ev.log(f"  {f.relative_to(data_dir)}  ({f.stat().st_size} bytes)")
    dbs = sorted((data_dir / "clinics").glob("*/app.db"))
    ev.check([d.parent.name for d in dbs] == ["iyer", "rao"] and (data_dir / "directory.db").is_file(),
             "directory.db plus one app.db per clinic (iyer, rao)")
    actors = {}
    for db in dbs:
        with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as con:
            found = con.execute("SELECT COALESCE(actor, '-'), action, COUNT(*) FROM audit_log"
                                " GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        actors[db.parent.name] = {r[0] for r in found}
        ev.log(f"audit log of {db.parent.name}:")
        for actor, action, n in found:
            ev.log(f"  {actor:<10} {action:<18} {n}")
    ev.check("dr.iyer" not in actors.get("rao", set()) and not {"dr.rao", "dr.mehta"} & actors.get("iyer", set()),
             "each clinic's audit log names only its own doctors")
    for ctx in (rao_ctx, iyer_ctx, mehta_ctx):
        ctx.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Browser evidence for the multi-clinic demo (spec 13.2).")
    parser.add_argument("--print-env", action="store_true", help="print the stub settings the server needs, then exit")
    parser.add_argument("--base", default="http://127.0.0.1:8765", help="where the server runs")
    parser.add_argument("--data-dir", type=Path, help="the server's DATA_DIR (for step 6)")
    parser.add_argument("--allow-remote", action="store_true",
                        help="allow a --base that is not loopback (the published demo passwords will be tried there)")
    parser.add_argument("--headed", action="store_true", help="show the browser windows")
    args = parser.parse_args(argv)
    if args.print_env:
        for key, value in SERVER_ENV.items():
            print(f"export {key}={shlex.quote(value)}")
        return 0
    if args.data_dir is None:
        parser.error("--data-dir is required (the DATA_DIR the server was started with)")
    for problem in (check_data_dir(args.data_dir), check_base(args.base, args.allow_remote)):
        if problem:
            parser.error(problem)
    if args.allow_remote and check_base(args.base):
        print(f"WARNING: {args.base} is not loopback; the published demo passwords will be tried against it.",
              file=sys.stderr)
    try:
        from playwright.sync_api import TimeoutError as pw_timeout, sync_playwright
    except ImportError:
        parser.error("Playwright is needed for a real run: pip install playwright && playwright install chromium")
    globals()["PwTimeout"] = pw_timeout
    ev = Evidence(EVIDENCE / datetime.now().strftime("%Y%m%d-%H%M%S"))
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed,
                                         args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
            try:
                run(browser, args.base.rstrip("/"), args.data_dir.resolve(), ev)
            except DemoFail as exc:
                ev.check(False, str(exc))
            finally:
                browser.close()
    finally:
        ev.close()
    print(f"\nevidence saved in {ev.out}")
    if ev.fallback:
        print("WARNING: step 2 used the API fallback; mic/STT/Save through the UI were NOT exercised")
    if ev.failed:
        print(f"{len(ev.failed)} automatic check(s) failed:\n  " + "\n  ".join(ev.failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
