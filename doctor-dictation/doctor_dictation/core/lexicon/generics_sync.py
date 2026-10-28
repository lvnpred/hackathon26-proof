"""Government generics list: CSV reader, gates and the offline ``sync`` command (plan I2-d). Stdlib only; offline.

    python doctor_dictation/core/lexicon/generics_sync.py sync --csv LIST.csv --source-id ID --source-name NAME \
        --licence TEXT --published YYYY-MM-DD --report REPORT.json [--source-url URL] [--apply-removals]
    python doctor_dictation/core/lexicon/generics_sync.py sync --check --csv LIST.csv --source-id ID ...   (never writes)

One CSV is one publication of ONE list (columns generic, list, [schedule, source_line, notes]). The file is the whole of
that list. It writes core/lexicon/generics.json (read at run time by core/generics.py, never by correct_drugs) and a
report that must stay outside the repository. The licence, source id and date are always supplied by the caller: this
code decides no licence. A generic missing from a newer edition is reported and KEPT unless --apply-removals is given.

    python doctor_dictation/core/lexicon/generics_sync.py review-sheet --out SHEET.csv      (new generics, for a clinician)
    python doctor_dictation/core/lexicon/generics_sync.py promote --review SHEET.csv --source-id generics-ID --reviewer NAME \
        --report REPORT.json [--confirm]

``promote`` adds the clinician-approved new generics to the lexicon as brandless canonicals, only through the importer's gates:
a look-alike twin needs a REVIEWED pair in lasa_pairs.json first; PROMOTION_LEDGER_PEPPER is required (hash-only ledger);
without --confirm nothing is written. The licence recorded is the sync record's, never one chosen here."""
import argparse
import csv
import difflib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[2])]     # run as a script: the sibling modules and the package
import build  # noqa: E402
import lexicon_import as LI  # noqa: E402

GENERICS_JSON = HERE / "generics.json"
PAIRS_JSON = HERE / "lasa_pairs.json"
MAX_ROWS, MAX_GENERIC, TWIN_MIN, RENAME_MIN = 20_000, 80, 0.75, LI.CUTOFF
SCHEDULES = ("", "H", "H1", "X")
RANK = {"H": 1, "H1": 2, "X": 3}
PART = re.compile(r"[A-Za-z][A-Za-z0-9 -]*")
LIST_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 ._-]{0,39}")
EMPTY = {"entries": [], "sources": [], "version": "0.0.0"}


def load_rules(path=LI.RULES_JSON) -> dict:
    """The brand importer's rules plus ``skip_generics`` (a list or {class: [generics]}), casefolded."""
    rules = LI.load_rules(path)
    raw = json.loads(Path(path).read_text(encoding="utf-8")).get("skip_generics", [])
    names = [g for v in raw.values() for g in v] if isinstance(raw, dict) else raw
    return {**rules, "skip_generics": {str(g).casefold() for g in names}}


def read_csv(path, report) -> list:
    """[{line, generic, list, schedule, source_line}] from one publication's CSV (contract: plan I2-d Decision 2)."""
    raw = Path(path).read_bytes()
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"ERROR: CSV {path} is not UTF-8 ({exc.reason} at byte {exc.start}). Nothing was written.") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    col = {(f or "").strip().lower(): f for f in (reader.fieldnames or [])}
    if not {"generic", "list"} <= set(col):
        raise SystemExit(f"ERROR: CSV {path} needs the columns ['generic', 'list']; found {list(col)}")
    get = lambda rec, k: LI.clean(rec.get(col[k]) if k in col else "")          # noqa: E731
    rows = []
    try:
        for line, rec in enumerate(reader, start=2):
            if line > MAX_ROWS + 1:
                raise SystemExit(f"ERROR: CSV {path} has more than {MAX_ROWS} rows")
            sched = re.sub(r"(?i)^schedule\s+", "", get(rec, "schedule")).upper()
            formula = get(rec, "generic")[:1] in ("=", "+", "-", "@")     # cleaning would turn '+SUM(1)' into the word 'Sum'
            rows.append({"line": line, "generic": LI.norm_generic(get(rec, "generic")), "list": get(rec, "list"),
                         "schedule": sched, "source_line": get(rec, "source_line")[:20], **({"formula": True} if formula else {})})
    except csv.Error as exc:                                   # for example a field over 128 KB
        raise SystemExit(f"ERROR: CSV {path} cannot be read: {exc}. Nothing was written.") from None
    names = {r["list"] for r in rows}
    if not rows:
        raise SystemExit(f"ERROR: CSV {path} has no rows. Nothing was written.")
    if len(names) > 1:
        raise SystemExit(f"ERROR: CSV {path} names more than one list; one list per file. Nothing was written.")
    if not LIST_NAME.fullmatch(next(iter(names))):
        raise SystemExit(f"ERROR: CSV {path}: the list name must be 1-40 characters of letters, digits, space . _ - "
                         "(no year). Nothing was written.")
    return rows


def _ratio(a, b) -> float:
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def _twins(generic, pool) -> list:
    """Names of ``pool`` at difflib ratio >= 0.75 (look-alike candidates), closest first."""
    sm, key = difflib.SequenceMatcher(), generic.casefold()
    sm.set_seq2(key)
    found = []
    for other in pool:
        if other.casefold() == key:
            continue
        sm.set_seq1(other.casefold())
        if sm.real_quick_ratio() >= TWIN_MIN and sm.quick_ratio() >= TWIN_MIN and sm.ratio() >= TWIN_MIN:
            found.append((-sm.ratio(), other))
    return [n for _, n in sorted(found, key=lambda t: (t[0], t[1].casefold()))]


def _gate(rows, rules, report):
    """Walk the rows in order. The FIRST accepted row of a generic decides; a later row with the same schedule is a
    ``duplicate``, one with another schedule makes a ``conflict`` (kept with no schedule). Returns
    ({key: {generic, schedule, line, source_line, conflict}}, every generic key present in the file)."""
    accepted, scheds, conflicts, seen = {}, {}, {}, set()
    for r in rows:
        g, key = r["generic"], r["generic"].casefold()
        seen.add(key)
        if r.get("formula"):
            checks = ["formula"]
        elif not g or not all(PART.fullmatch(p) for p in g.split(" + ")) or len(g) > MAX_GENERIC:
            checks = ["shape"]
        elif r["schedule"] not in SCHEDULES:
            checks = ["bad-schedule"]
        elif key in rules.get("skip_generics", ()):
            checks = ["curated-skip"]
        elif key not in accepted:
            accepted[key] = {"generic": g, "schedule": r["schedule"], "line": r["line"], "source_line": r["source_line"],
                             "conflict": False}
            scheds[key] = [r["schedule"]]
            continue
        elif r["schedule"] in scheds[key]:
            report["skipped"].append({"line": r["line"], "generic": g, "checks": ["duplicate"], "first_line": accepted[key]["line"]})
            continue
        else:
            accepted[key]["conflict"] = True
            scheds[key].append(r["schedule"])
            if key not in conflicts:
                conflicts[key] = {"generic": g, "lines": [accepted[key]["line"]], "schedules": [accepted[key]["schedule"]]}
            conflicts[key]["lines"].append(r["line"])
            conflicts[key]["schedules"].append(r["schedule"])
            continue
        report["skipped"].append({"line": r["line"], "generic": g, "checks": checks})
    report["conflicts"] = [conflicts[k] for k in sorted(conflicts)]
    return accepted, seen


def _membership(row, source_id) -> dict:
    return {**({"line": row["source_line"]} if row["source_line"] else {}), "src": source_id,
            **({"schedule": row["schedule"]} if row["schedule"] and not row["conflict"] else {})}


def plan_sync(rows, current, entries, rules, source_id, apply_removals=False):
    """(new generics.json data, report) for one publication; pure: reads nothing, never decides a licence.

    The file is the whole of its list L: added = in the file, not in L; changed = another schedule (applied, the newer
    source wins); removed = in L, not in the file: reported and KEPT with its old lineage unless ``apply_removals``."""
    current = {**EMPTY, **(current or {})}
    L = rows[0]["list"] if rows else ""
    report = {"source": source_id, "list": L, "rows_read": len(rows), "linked": {"exact": 0, "synonym": 0}, "new": 0,
              "new_generics": [], "skipped": [], "conflicts": [], "added": [], "changed": [], "removed": [],
              "possible_renames": [], "dropped": [], "removals_applied": bool(apply_removals)}
    check = LI.Checker(entries, [], [], rules)
    accepted, seen = _gate(rows, rules, report)
    merged = {e["generic"].casefold(): json.loads(json.dumps(e)) for e in current["entries"]}
    for key, row in sorted(accepted.items(), key=lambda kv: kv[1]["generic"].casefold()):
        member, entry = _membership(row, source_id), merged.get(key)
        if entry is None:
            entry = merged[key] = {"generic": row["generic"], "lexicon": "", "lists": {}}
        old = entry["lists"].get(L)
        if old is None:
            report["added"].append(entry["generic"])
            entry["lists"][L] = member
        elif old.get("schedule", "") != member.get("schedule", ""):
            report["changed"].append({"generic": entry["generic"], "list": L, "old": old.get("schedule", ""),
                                      "new": member.get("schedule", "")})
            entry["lists"][L] = member
    for key, entry in sorted(merged.items()):                      # removals: in L, not anywhere in the file
        if L in entry["lists"] and key not in seen:
            report["removed"].append(entry["generic"])
            if apply_removals:
                del entry["lists"][L]
                if not entry["lists"]:
                    report["dropped"].append(entry["generic"])
    for key in [k for k, e in merged.items() if not e["lists"]]:
        del merged[key]
    report["possible_renames"] = _renames(report["removed"], report["added"], rules)
    for key, entry in merged.items():                              # the link to the lexicon is derived: recompute it
        canon, kind, _near = check.resolve(entry["generic"])
        entry["lexicon"] = canon
        if key in accepted:
            if canon:
                report["linked"][kind] += 1
            else:
                report["new"] += 1
    new = [merged[k]["generic"] for k in sorted(accepted) if not merged[k]["lexicon"]]
    names = [e["canonical"] for e in entries]
    for g in sorted(new, key=str.casefold):
        report["new_generics"].append({"generic": g, "near": [n for n in [check.resolve(g)[2]] if n],
                                       "twins": _twins(g, [*names, *new])})
    ordered = sorted(merged.values(), key=lambda e: e["generic"].casefold())
    return {"entries": ordered, "sources": list(current["sources"]), "version": current["version"]}, report


def _renames(removed, added, rules) -> list:
    """removed x added pairs at ratio >= 0.84 or through the synonym table: reported only, never linked."""
    syn = rules["synonyms"]
    pairs = [{"added": a, "removed": r} for r in removed for a in added
             if _ratio(r, a) >= RENAME_MIN or syn.get(r.casefold(), "").casefold() == a.casefold()
             or syn.get(a.casefold(), "").casefold() == r.casefold()]
    return sorted(pairs, key=lambda p: (p["removed"].casefold(), p["added"].casefold()))


# ---- the sync command -------------------------------------------------------------------------------------------

def _die(message, code=2):
    """SystemExit carrying ``code`` (SystemExit(str) alone would exit 1)."""
    err = SystemExit(message)
    err.code = code
    raise err


def _check_folder(path, parser):
    if path and not Path(path).resolve().parent.is_dir():
        parser.error(f"the folder does not exist: {Path(path).resolve().parent}. Create it first. Nothing was read or written.")


def _reload():
    """Tell core.generics to read the new file now (same process only; a running server needs a restart)."""
    try:
        from doctor_dictation.core import generics
        generics.reload()
    except ImportError:
        pass


def relink(entries, lexicon_entries, rules):
    """Set each generics.json entry's derived ``lexicon`` link from the lexicon (the one function sync and promote share)."""
    check = LI.Checker(lexicon_entries, [], [], rules)
    for e in entries:
        e["lexicon"] = check.resolve(e["generic"])[0]

def _atomic_write(path, text):
    """Write LF text through a temp file in the same folder and ``os.replace`` it: a crash never leaves half a file."""
    path = Path(path)
    if not path.parent.is_dir():
        _die(f"ERROR: the folder does not exist: {path.parent}. Create it first; nothing was written.")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _dump(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def load_generics(path=None) -> dict:
    path = Path(path or GENERICS_JSON)
    if not path.exists():
        return json.loads(json.dumps(EMPTY))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"ERROR: {path} is not valid JSON ({exc}). Nothing was written.") from None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list) or not isinstance(data.get("sources"), list):
        raise SystemExit(f"ERROR: {path} is not a generics list (entries and sources are required). Nothing was written.")
    return data


def gate_sync_args(args, parser) -> dict:
    """The licence gate, run BEFORE any read or write: the caller supplies the source, licence and date (no defaults)."""
    sid = (args.source_id or "").strip()
    fields = {"id": sid, "name": (args.source_name or "").strip(), "licence": (args.licence or "").strip(),
              **({"url": args.source_url.strip()} if args.source_url and args.source_url.strip() else {})}
    if sid.startswith(build.RESERVED_IDS) or not (args.report or args.check):
        parser.error("sync needs --report (not for --check) and a --source-id that is not seed, clinic or promoted-*. "
                     "Nothing was read or written.")
    if args.report and Path(args.report).resolve().is_relative_to(REPO_ROOT):
        parser.error("--report must be outside the repository (it lists skipped rows and may hold licensed data). "
                     "Nothing was read or written.")
    _check_folder(args.report, parser)
    try:
        build.check_source(fields)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.published or ""):
            raise ValueError("--published must be the publication date as YYYY-MM-DD. Nothing was read or written.")
        date.fromisoformat(args.published)
    except ValueError as exc:
        parser.error(f"ERROR: {exc}")
    return {**fields, "published": args.published}


def do_sync(args, source) -> int:
    report = {}
    rows = read_csv(args.csv, report)
    current = load_generics()
    prior = next((s for s in current["sources"] if s.get("id") == source["id"]), None)
    if prior and prior.get("input_sha256") != report["input_sha256"]:
        raise SystemExit(f"ERROR: source id {source['id']!r} was already used for another file; pick a new id. Nothing was written.")
    data, plan = plan_sync(rows, current, build.load_drugs()["entries"], load_rules(), source["id"], args.apply_removals)
    plan = {**plan, "input_sha256": report["input_sha256"]}
    same = data["entries"] == current["entries"] and prior is not None
    counts = (f"added={len(plan['added'])} changed={len(plan['changed'])} "
              f"removed={len(plan['removed'])} ({'applied' if args.apply_removals else 'kept'})")
    if args.check:
        if prior is None and data["entries"] == current["entries"]:
            print(f"check FAILED: source {source['id']} is not recorded in generics.json (run the sync to record it)")
            return 1
        print("check OK: generics.json matches this publication" if same else
              f"check FAILED: generics.json differs from {Path(args.csv).name}: {counts}")
        return 0 if same else 1
    if same:
        print("no change: generics.json and the report were not rewritten")
        return 0
    record = {**source, "list": plan["list"], "input_sha256": report["input_sha256"], "rows_read": len(rows),
              "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    data["sources"] = [*(s for s in current["sources"] if s.get("id") != source["id"]), dict(sorted(record.items()))]
    data["version"] = build.bump_minor(current["version"])
    _atomic_write(args.report, _dump(plan))                       # the report first: a failure leaves generics.json alone
    _atomic_write(GENERICS_JSON, _dump(data))
    print(f"sync {Path(args.csv).name}: version {current['version']} -> {data['version']}, entries "
          f"{len(current['entries'])} -> {len(data['entries'])}, rows_read={len(rows)} linked={plan['linked']} "
          f"new={plan['new']} skipped={len(plan['skipped'])} conflicts={len(plan['conflicts'])} {counts}")
    _reload()
    return 0


PROMOTE = None        # the generics_promote module, bound on first use (tests bind a copy)


def _promote_module():
    global PROMOTE
    if PROMOTE is None:
        import generics_promote
        generics_promote.GS, PROMOTE = sys.modules[__name__], generics_promote
    return PROMOTE


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("sync", help="merge one publication of one list into generics.json")
    sp.add_argument("--csv", required=True, help="the publication, one list per file")
    sp.add_argument("--source-id", help="REQUIRED: the edition's id, for example nlem-2022 (recorded on every entry)")
    sp.add_argument("--source-name", help="REQUIRED: the publication's name (recorded)")
    sp.add_argument("--licence", help="REQUIRED: the reuse terms as the owner confirmed them (recorded; never defaulted)")
    sp.add_argument("--published", help="REQUIRED: the publication date, YYYY-MM-DD (recorded)")
    sp.add_argument("--source-url", help="where the publication came from (recorded)")
    sp.add_argument("--report", metavar="PATH", help="REQUIRED unless --check: the change report (JSON), outside the repository")
    sp.add_argument("--check", action="store_true", help="exit 1 when generics.json differs from this publication; writes nothing")
    sp.add_argument("--apply-removals", action="store_true", help="drop generics missing from this edition (after review)")
    rp = sub.add_parser("review-sheet", help="write the new generics (not lexicon names) as a CSV for a clinician to review")
    rp.add_argument("--out", required=True, help="the sheet; outside the repository (or under doctor_dictation/data/)")
    pp = sub.add_parser("promote", help="add the clinician-approved new generics to the lexicon (needs --confirm and PROMOTION_LEDGER_PEPPER; ledger: hashes only for refused or rejected rows, added generic names are public and recorded)")
    pp.add_argument("--review", required=True, help="the sheet with clinician_ok = y on the approved rows")
    pp.add_argument("--source-id", help="REQUIRED: generics-<a-z0-9-> (the batch; recorded as lineage)")
    pp.add_argument("--reviewer", help="REQUIRED: the approving clinician, 3+ characters (recorded)")
    pp.add_argument("--report", help="REQUIRED: the outcome report (JSON), outside the repository")
    pp.add_argument("--confirm", action="store_true", help="without it nothing is written")
    args = ap.parse_args()
    if args.cmd in ("review-sheet", "promote"):
        _check_folder(args.out if args.cmd == "review-sheet" else args.report, rp if args.cmd == "review-sheet" else pp)
        return _promote_module().run(args, rp if args.cmd == "review-sheet" else pp)
    return do_sync(args, gate_sync_args(args, sp))


if __name__ == "__main__":
    sys.exit(main())
