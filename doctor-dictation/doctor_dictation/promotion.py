"""Promote names many clinics learned into the core lexicon (plan I1-g simple, Task 4). Operator-run, offline.

``promote-candidates`` reads every clinic's ACTIVE learned names READ-ONLY (table clinic_formulary only: never patients,
documents or users) and writes a review CSV of names learned in N+ clinics, with counts only. ``promote-apply`` merges the
rows a clinician approved through the same five checks as the CSV import and appends every decision to the committed
ledger. Neither command writes to a clinic database; the review CSV is clinic-derived data and never goes into git.
The ledger keys are HMAC-SHA256 hashes under a secret pepper (env PROMOTION_LEDGER_PEPPER, 32+ characters, kept outside
git, never written anywhere); losing the pepper only means rejected names can be proposed again. The ledger's 8-hex
pepper_check lets anyone test guesses offline, so a weak pepper is guessable: use a random one (see .env.example).
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.core import formulary as F
from doctor_dictation.core.lexicon import build
from doctor_dictation.directory import list_clinics, open_directory
from doctor_dictation.scope import clinic_dir, multi_clinic_enabled

LEX = build.lexicon_import
LEDGER_JSON = build.HERE / "promotion_ledger.json"
REPO = Path(__file__).resolve().parents[1]
COLUMNS = ("name", "generic", "clinics_count", "first_seen", "last_seen", "decision", "reviewer", "notes")
INCOMPLETE = ".INCOMPLETE"
BATCH = re.compile(r"[a-z0-9][a-z0-9-]{2,30}")
LICENCE = "internal: names confirmed on saved prescriptions in several clinics, approved by a clinician"
_ACTIVE = "SELECT name, generic, first_seen_at, last_seen_at FROM clinic_formulary WHERE removed_at IS NULL AND confirm_count >= ?"


LEDGER_VERSION = "dd-promotion-v2"
PEPPER_ENV = "PROMOTION_LEDGER_PEPPER"
PEPPER_MIN = 32


def die(message, code=2):
    """Print to stderr and exit with ``code`` (SystemExit keeps the text for callers and tests)."""
    print(message, file=sys.stderr)
    error = SystemExit(message)
    error.code = code
    raise error


def pepper() -> bytes:
    """The secret that keys the ledger hashes: from the environment only, no default, never stored."""
    value = os.environ.get(PEPPER_ENV, "")
    if len(value) < PEPPER_MIN:
        die(f"ERROR: {PEPPER_ENV} is required ({PEPPER_MIN}+ characters, keep it outside git). Nothing was read or written.")
    return value.encode("utf-8")


def pepper_check() -> str:
    """A short non-secret value that lets the ledger detect a wrong or changed pepper."""
    return hmac.new(pepper(), b"dd-promotion-check", hashlib.sha256).hexdigest()[:8]


def ledger_key(name) -> str:
    """The ledger stores a keyed hash, never a rejected name (it could be a patient's name that slipped past the learning rules)."""
    return hmac.new(pepper(), F.key(name).encode("utf-8"), hashlib.sha256).hexdigest()


def load_ledger() -> list:
    """The ledger entries; refuses (exit 2) when the pepper does not match the ledger. Checks the pepper first."""
    check = pepper_check()
    doc = json.loads(LEDGER_JSON.read_text(encoding="utf-8")) if LEDGER_JSON.exists() else {}
    entries = doc.get("entries", []) if isinstance(doc, dict) else None
    if entries is None or doc.get("version", LEDGER_VERSION) != LEDGER_VERSION:
        die(f"ERROR: {LEDGER_JSON.name} is not a {LEDGER_VERSION} ledger. Nothing was read or written.")
    if (entries or "pepper_check" in doc) and doc.get("pepper_check") != check:
        die(f"ERROR: {PEPPER_ENV} does not match the ledger (wrong or changed pepper): rejected names would be proposed "
            "again. Nothing was read or written.")
    return entries


def write_atomic(path, text) -> None:
    """Write via a temp file in the same directory, then os.replace: a failure leaves the old file intact."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save_ledger(entries) -> None:
    doc = {"entries": sorted(entries, key=lambda r: (r["key"], r["batch"])), "pepper_check": pepper_check(),
           "version": LEDGER_VERSION}
    write_atomic(LEDGER_JSON, json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def clinic_dbs() -> list:
    """[(label, path)]: every registered clinic's app.db in multi-clinic mode (as migrate-all), else the one database."""
    if not multi_clinic_enabled():
        return [("single", Path(os.getenv(dbmod.DB_PATH_ENV) or dbmod.DEFAULT_DB_PATH))]
    with closing(open_directory()) as d:
        return [(r["slug"], clinic_dir(r["slug"]) / "app.db") for r in list_clinics(d)]


def read_active(path) -> list:
    """One clinic's active names, opened read-only: a missing file raises and is never created."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        return conn.execute(_ACTIVE, (F.THRESHOLD,)).fetchall()


def candidates(min_clinics, conflict_rows):
    """(review rows, Counter of exclusions, {clinic label: error}). Counts only: no clinic, user or document leaves."""
    seen, failed, bad = defaultdict(lambda: {"names": Counter(), "generics": Counter(), "dates": []}), {}, 0
    reviewed = {r["key"] for r in load_ledger()}                  # first: needs the pepper, before any clinic DB opens
    for label, path in clinic_dbs():
        try:
            rows = read_active(path)
        except sqlite3.Error as exc:
            failed[label] = f"{type(exc).__name__}: {exc}"
            continue
        for name, generic, first, last in rows:                  # name_key is unique per clinic: one row per clinic
            name = F.clean_name(name)                            # a tampered row must not reach the CSV
            if not name:
                bad += 1
                continue
            s = seen[F.key(name)]
            s["names"][name] += 1
            s["dates"] += [str(first)[:10], str(last)[:10]]
            if F.clean_name(generic):
                s["generics"][F.clean_name(generic)] += 1
    entries = build.load_drugs()["entries"]
    check, names = LEX.Checker(entries, conflict_rows, [], LEX.load_rules()), LEX.alias_map(entries)
    out, why = [], Counter({"invalid-name": bad} if bad else {})
    for k, s in seen.items():
        name, count = min(s["names"].items(), key=lambda kv: (-kv[1], kv[0]))[0], sum(s["names"].values())
        typed = min(s["generics"], key=lambda g: (-s["generics"][g], g), default="")
        generic = check.resolve(LEX.norm_generic(typed))[0] if typed else ""
        reason = ("fewer-clinics" if count < min_clinics else "in-lexicon" if k in names else
                  "reviewed" if ledger_key(name) in reviewed else "person-like" if F.person_like(name) else "")
        failed_checks = [] if reason else check.failures(name, generic)[0]
        if reason or failed_checks:
            why[reason or failed_checks[0]] += 1
            continue
        out.append({"name": name, "generic": generic or typed, "clinics_count": count, "first_seen": min(s["dates"]),
                    "last_seen": max(s["dates"]), "decision": "", "reviewer": "", "notes": ""})
    return sorted(out, key=lambda r: (-r["clinics_count"], F.key(r["name"]))), why, failed


def write_review(path, rows) -> None:
    out = Path(path).resolve()
    if out.is_relative_to(REPO) and not out.is_relative_to(REPO / "doctor_dictation" / "data"):
        die(f"ERROR: {out} is inside the repository; the review CSV is clinic data: write it under DATA_DIR")
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: _safe_cell(v) for k, v in row.items()} for row in rows)
    write_atomic(out, buf.getvalue())


def _safe_cell(value):
    """A cell a spreadsheet would run as a formula gets a leading apostrophe."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def apply(csv_path, batch, reviewer, conflict_rows, confirm, today):
    """Merge the approved rows that pass all five checks; ledger every decision. Returns (exit code, outcome Counter)."""
    ledger = load_ledger()                           # first: needs the pepper and refuses a wrong one
    if Path(str(csv_path) + INCOMPLETE).exists():
        die(f"ERROR: {csv_path}{INCOMPLETE} exists: the candidate run could not read every clinic. Nothing was read or "
            "written; re-run promote-candidates, or remove the marker only if you accept an incomplete review.")
    reviewer = " ".join(str(reviewer or "").split())
    if len(reviewer) < 3:
        die("ERROR: promote-apply needs --reviewer (the approving clinician, 3+ characters). Nothing was read or written.")
    if not BATCH.fullmatch(batch or ""):
        die("ERROR: --batch must be 3-31 characters of a-z, 0-9 and -, starting with a letter or digit. "
            "Nothing was read or written.")
    if any(r["batch"] == batch for r in ledger):
        die(f"ERROR: --batch {batch} is already in the ledger: pass a new --batch. Nothing was read or written.")
    report = {}
    rows = list(csv.DictReader(io.StringIO(Path(csv_path).read_bytes().decode("utf-8-sig"), newline="")))
    report["input_sha256"] = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    approved = [{"brand": F.clean_name(r.get("name")), "generic": LEX.norm_generic(r.get("generic"))}
                for r in rows if (r.get("decision") or "").strip().casefold() == "approve"]
    entries = build.load_drugs()["entries"]
    known = LEX.alias_map(entries)
    check, done = LEX.Checker(entries, conflict_rows, approved, LEX.load_rules()), {r["key"] for r in ledger}
    additions, decisions, outcomes = defaultdict(list), [], Counter()
    for r in rows:
        name, decision = F.clean_name(r.get("name")), (r.get("decision") or "").strip().casefold()
        who = " ".join((r.get("reviewer") or "").split()) or reviewer
        if decision == "approve" and not name:                   # a hand-edited name that is no medicine name at all
            outcomes["rejected: invalid-name"] += 1
            continue
        if decision not in ("approve", "reject") or not name or ledger_key(name) in done:
            outcomes["undecided or already reviewed"] += 1
            continue
        canon, outcome = (check.resolve(LEX.norm_generic(r.get("generic")))[0], "") if decision == "approve" else ("", "rejected")
        if decision == "approve" and (F.key(name) in known or F.person_like(name)):   # hand-edited rows: same exclusions as candidates
            canon, outcome = "", "rejected: " + ("in-lexicon" if F.key(name) in known else "person-like")
        elif decision == "approve" and not canon:          # owner 2026-10-17: no trusted generic, no core list
            outcome = "clinic-only: 1-generic"
        elif decision == "approve":
            failed = [] if check.names.get(name.casefold()) == canon else check.failures(name, canon)[0]
            outcome = "clinic-only: " + ", ".join(failed) if failed else "added"
            if not failed:
                additions[canon].append((name, {"date": today, "reviewer": who, "src": f"promoted-{batch}"}))
        done.add(ledger_key(name))
        outcomes[outcome if outcome.startswith("rejected:") else outcome.split(":")[0]] += 1
        decisions.append({"batch": batch, "date": today, "decision": decision, "key": ledger_key(name), "outcome": outcome,
                          "reviewer": who, **({"canonical": canon, "name": name} if outcome == "added" else {})})
    if not confirm:
        return 2, outcomes
    changed = LEX.merge_brands(entries, additions)
    try:
        source = build.check_source({"id": f"promoted-{batch}", "name": f"clinic promotion {batch}", "licence": LICENCE,
                                     "reviewer": reviewer})
    except ValueError as exc:                       # the gate raises ValueError (task 3); nothing has been written yet
        raise SystemExit(f"ERROR: {exc}") from exc
    if changed:
        build.apply_import(changed, source, {**report, "brands_added": sum(len(v) for v in additions.values()),
                                             "rules": check.rules["version"]})
    save_ledger(ledger + decisions)
    return 0, outcomes


def _candidates_cmd(args) -> int:
    if args.min_clinics < 1:
        die("ERROR: --min-clinics must be 1 or more")
    rows, why, failed = candidates(args.min_clinics, LEX.read_csv(args.conflict_map))
    write_review(args.out, rows)
    marker = Path(str(args.out) + INCOMPLETE)
    if failed:
        marker.write_text(f"{len(failed)} clinic(s) unreadable; do not apply\n", encoding="utf-8")
        print(f"INCOMPLETE: do not apply ({len(failed)} clinic(s) unreadable)", file=sys.stderr)
    else:
        marker.unlink(missing_ok=True)
    print(f"promote-candidates: {len(rows)} names written to {args.out}; not proposed: {dict(sorted(why.items()))}")
    for label, error in failed.items():
        print(f"{label}: FAILED {error}")
    return 1 if failed else 0


def _apply_cmd(args) -> int:
    code, outcomes = apply(args.csv, args.batch, args.reviewer, LEX.read_csv(args.conflict_map), args.confirm,
                           date.today().isoformat())
    print(f"promote-apply {args.batch}: {dict(sorted(outcomes.items()))}" + ("" if code == 0 else
          "\nnothing written: add --confirm after reading the outcome above"))
    return code


def register(sub, commands) -> None:
    """Add promote-candidates and promote-apply to the admin command line."""
    c = sub.add_parser("promote-candidates", help="write a review CSV of drug names learned in N+ clinics (read-only; needs PROMOTION_LEDGER_PEPPER (32+ random characters), "
                        "kept outside git: losing it only means rejected names can be proposed again)")
    c.add_argument("--out", required=True, help="the review CSV: clinic data, keep it under DATA_DIR, never in git")
    c.add_argument("--conflict-map", required=True, help="the full CDCI brand,generic CSV (checks 2 and 5)")
    c.add_argument("--min-clinics", type=int, default=3, help="distinct clinics that must have learned a name (default 3)")
    a = sub.add_parser("promote-apply", help="merge the clinician-approved rows into drugs.json (needs --confirm and PROMOTION_LEDGER_PEPPER (32+ random characters), "
                        "kept outside git: losing it only means rejected names can be proposed again)")
    a.add_argument("--csv", required=True)
    a.add_argument("--batch", required=True, help="new batch id, e.g. 2026-11; lineage becomes promoted-<batch>")
    a.add_argument("--reviewer", help="REQUIRED: the clinician who approved the batch")
    a.add_argument("--conflict-map", required=True)
    a.add_argument("--confirm", action="store_true", help="without it nothing is written")
    commands.update({"promote-candidates": _candidates_cmd, "promote-apply": _apply_cmd})
