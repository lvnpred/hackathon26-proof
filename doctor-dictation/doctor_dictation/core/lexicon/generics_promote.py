"""Review sheet and gated promotion of new generics (plan I2-d Task 5). Reached through generics_sync.py (same CLI):

    python doctor_dictation/core/lexicon/generics_sync.py review-sheet --out SHEET.csv      (new generics, for a clinician)
    python doctor_dictation/core/lexicon/generics_sync.py promote --review SHEET.csv --source-id generics-ID --reviewer NAME \
        --report REPORT.json [--confirm]

``promote`` adds the clinician-approved new generics to the lexicon as brandless canonicals, only through the importer's gates:
a look-alike twin needs a REVIEWED pair in lasa_pairs.json first; a brand of another drug is never promoted; the licence
recorded is the sync record's, never one chosen here. Without --confirm nothing is written.

Ledger (doctor_dictation/promotion.py, needs PROMOTION_LEDGER_PEPPER): hashes only for refused or rejected rows; the names of
ADDED generics are public (they come from a government list) and are recorded in clear next to their HMAC key.

Write order on --confirm: ledger, then imported.json and drugs.json, then the generics.json links, then the report. A crash
after the ledger write is finished by running the SAME command again ("recovering"); a crash before it leaves nothing.
The module reads the sync module through ``GS`` (bound by generics_sync.py) so both share one set of paths and gates."""
import csv
import hashlib
import io
import json
import re
from datetime import date
from pathlib import Path

GS = None                 # the generics_sync module (bound by generics_sync._promote_module)
SHEET_COLUMNS = ("generic", "lists", "schedule", "near", "twins", "curated_pair", "clinician_ok", "notes")
PROMO_ID = re.compile(r"generics-[a-z0-9-]{3,30}")
LEDGER_NOTE = " hashes only for refused or rejected rows; added generic names are public and recorded."


def _reviewed_pairs() -> set:
    """{frozenset({a, b})} (casefolded) of the pairs a clinician reviewed in lasa_pairs.json; unusable file = none."""
    try:
        pairs = json.loads(Path(GS.PAIRS_JSON).read_text(encoding="utf-8"))["pairs"]
        return {frozenset((str(p["a"]).strip().casefold(), str(p["b"]).strip().casefold())) for p in pairs
                if isinstance(p, dict) and p.get("reviewed") is True and p.get("a") and p.get("b")}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def _shaped(generic) -> bool:
    return bool(generic) and len(generic) <= GS.MAX_GENERIC and all(GS.PART.fullmatch(p) for p in generic.split(" + "))


def _new_generics(data, entries, rules) -> dict:
    """{casefold: {generic, lists, schedule, near, twins, srcs, brand_of}} for every generics.json generic that is not a lexicon
    name. Recomputed from the file and the lexicon each time: a hand-edited sheet cell can never skip the pair check."""
    check, names = GS.LI.Checker(entries, [], [], rules), [e["canonical"] for e in entries]
    brands = {}
    for e in entries:
        for b in e.get("brands", []):
            brands.setdefault(str(b).strip().casefold(), e["canonical"])
    new = [e for e in data["entries"] if isinstance(e, dict) and e.get("generic") and not e.get("lexicon")]
    out = {}
    for e in new:
        g, lists = str(e["generic"]), e.get("lists") if isinstance(e.get("lists"), dict) else {}
        marks = [m.get("schedule", "") for m in lists.values() if isinstance(m, dict)]
        out[g.casefold()] = {"generic": g, "lists": sorted(lists), "near": [n for n in [check.resolve(g)[2]] if n],
                             "schedule": max([*marks, ""], key=lambda x: GS.RANK.get(x, 0)),
                             "twins": GS._twins(g, [*names, *(str(n["generic"]) for n in new)]),
                             "brand_of": brands.get(g.casefold(), ""),
                             "srcs": sorted({m.get("src", "") for m in lists.values() if isinstance(m, dict)})}
    return out


def _safe_cell(value):
    """A cell a spreadsheet would run as a formula gets a leading apostrophe (as promotion._safe_cell)."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _inside_repo(path) -> bool:
    out, root = Path(path).resolve(), Path(GS.REPO_ROOT).resolve()
    return out.is_relative_to(root) and not out.is_relative_to(root / "doctor_dictation" / "data")


def review_rows(data, entries, rules) -> tuple:
    """(rows, skipped): the new generics for the clinician; a name that is not shaped like a generic is skipped, never listed."""
    pairs, rows, skipped = _reviewed_pairs(), [], 0
    for key, n in sorted(_new_generics(data, entries, rules).items()):
        if not _shaped(n["generic"]):
            skipped += 1
            continue
        pair = "n/a" if not n["twins"] else "y" if all(frozenset((key, t.casefold())) in pairs for t in n["twins"]) else "n"
        rows.append({"generic": n["generic"], "lists": "; ".join(n["lists"]), "schedule": n["schedule"], "near": "; ".join(n["near"]),
                     "twins": "; ".join(n["twins"]), "curated_pair": pair, "clinician_ok": "",
                     "notes": f"brand of {n['brand_of']}: not promotable" if n["brand_of"] else ""})
    return rows, skipped


def write_sheet(out, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=SHEET_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: _safe_cell(v) for k, v in r.items()} for r in rows)
    GS._atomic_write(out, buf.getvalue())


def plan_promote(rows, source_id, reviewer, sheet_sha="", today=None):
    """(outcomes [(generic, outcome)], changed entries, source record or {}). Reads only ``generic`` and ``clinician_ok`` (plain y)
    of a row; writes nothing."""
    build, LI = GS.build, GS.LI
    entries, rules, data = build.load_drugs()["entries"], GS.load_rules(), GS.load_generics()
    info, known, pairs = _new_generics(data, entries, rules), LI.alias_map(entries), _reviewed_pairs()
    brand_names = {b.strip().casefold() for e in entries for b in e.get("brands", [])}
    licences = {s.get("id"): str(s.get("licence") or "") for s in data["sources"] if isinstance(s, dict)}
    wanted = [LI.norm_generic(LI.clean(r.get("generic"))) for r in rows if str(r.get("clinician_ok") or "").strip().casefold() == "y"]
    check = LI.Checker(entries, [], [{"brand": g, "generic": g} for g in wanted if g], rules)
    today, seen, outcomes, changed, used = today or date.today().isoformat(), set(), [], [], set()
    for g in wanted:
        key, n = g.casefold(), info.get(g.casefold())
        missing = [t for t in (n or {"twins": []})["twins"] if frozenset((key, t.casefold())) not in pairs]
        failed = check.failures(n["generic"])[0] if n else []
        lic = [licences.get(src, "") for src in (n or {"srcs": []})["srcs"]]
        owner = (n or {}).get("brand_of") or (known.get(key, "") if key in brand_names else "")
        why = ("duplicate-row" if key in seen else f"brand-of-{owner}" if owner else "in-lexicon" if key in known else
               "not-a-new-generic" if not n else f"twin-without-reviewed-pair ({', '.join(missing)})" if missing else
               ", ".join(failed) if failed else
               "no-licence-on-record" if not lic or any(len(x) < build.MIN_LICENCE for x in lic) else "")
        seen.add(key)
        outcomes.append((g, f"refused: {why}" if why else "added"))
        if not why:
            used.update(lic)
            changed.append({"aliases": [n["generic"].lower()], "brands": [], "canonical": n["generic"], "forms": [],
                            "origin": {"date": today, "reviewer": reviewer, "src": source_id}, "strengths": []})
    source = {"id": source_id, "name": f"generics promoted {source_id}", "licence": "; ".join(sorted(used)),
              "reviewer": reviewer} if changed else {}
    return outcomes, changed, source


def write_lexicon(changed, source, sheet_sha=""):
    """Add the entries through build.apply_import (one write), then refresh their generics.json links, then reload."""
    build = GS.build
    try:
        build.check_source(source)
    except ValueError as exc:
        GS._die(f"ERROR: {exc}")
    rules = GS.load_rules()
    build.apply_import(changed, source, {"brands_added": 0, "input_sha256": sheet_sha, "rules": rules["version"]})
    data = GS.load_generics()
    names = {e["canonical"].casefold() for e in changed}
    mine = [e for e in data["entries"] if isinstance(e, dict) and str(e.get("generic", "")).casefold() in names]
    GS.relink(mine, build.load_drugs()["entries"], rules)            # same resolve as the sync: no second sync is needed
    GS._atomic_write(GS.GENERICS_JSON, GS._dump(data))
    GS._reload()


def promote_rows(rows, source_id, reviewer, sheet_sha="", today=None, write=True) -> list:
    """[(generic, outcome)]; ``added`` rows are written in ONE build.apply_import (nothing written when ``write`` is False)."""
    outcomes, changed, source = plan_promote(rows, source_id, reviewer, sheet_sha, today)
    if write and changed:
        write_lexicon(changed, source, sheet_sha)
    return outcomes


def read_sheet(path) -> tuple:
    """(rows, sha256) of a clinician's sheet; a non-UTF-8 or oversized file exits 2 before anything is written."""
    raw = Path(path).read_bytes()
    try:
        rows = []
        for i, rec in enumerate(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))):
            if i >= GS.MAX_ROWS:
                GS._die(f"ERROR: sheet {path} has more than {GS.MAX_ROWS} rows. Nothing was written.")
            rows.append({(k or "").strip().lower(): v for k, v in rec.items()})
    except (UnicodeDecodeError, csv.Error) as exc:
        GS._die(f"ERROR: sheet {path} cannot be read ({exc}). Nothing was written.")
    return rows, hashlib.sha256(raw).hexdigest()


def do_promote(args, parser) -> int:
    build, LI = GS.build, GS.LI
    reviewer = " ".join((args.reviewer or "").split())
    if len(reviewer) < 3 or not PROMO_ID.fullmatch(args.source_id or "") or not args.report:
        parser.error("promote needs --reviewer (the approving clinician, 3+ characters), --source-id generics-<a-z0-9-> and --report. "
                     "Nothing was read or written.")
    if Path(args.report).resolve().is_relative_to(Path(GS.REPO_ROOT).resolve()):
        parser.error("--report must be outside the repository. Nothing was read or written.")
    from doctor_dictation import promotion as P          # the Iteration 1 ledger: HMAC keys under PROMOTION_LEDGER_PEPPER
    ledger = P.load_ledger()                             # first: needs the pepper and refuses a wrong one
    if any(s.get("id") == args.source_id for s in build.load_drugs().get("sources", [])):
        GS._die(f"ERROR: --source-id {args.source_id} was already used: pass a new one. Nothing was read or written.")
    rows, sha = read_sheet(args.review)
    prior, today = [r for r in ledger if r["batch"] == args.source_id], date.today().isoformat()
    if prior:                                            # a crash after the ledger write: finish the lexicon write for those rows
        if {r["reviewer"] for r in prior} != {reviewer}:
            GS._die(f"ERROR: batch {args.source_id} is in the ledger under another reviewer. Nothing was read or written.")
        today, names = prior[0]["date"], {r["canonical"].casefold() for r in prior}
        rows = [r for r in rows if LI.norm_generic(LI.clean(r.get("generic"))).casefold() in names]
        print(f"promote {args.source_id}: the ledger has this batch but the lexicon does not: recovering")
    outcomes, changed, source = plan_promote(rows, args.source_id, reviewer, sha, today)
    for g, o in outcomes:
        print(f"  {g}: {o}")
    added, refused = [g for g, o in outcomes if o == "added"], [g for g, o in outcomes if o != "added"]
    if prior and {g.casefold() for g in added} != {r["canonical"].casefold() for r in prior}:
        GS._die(f"ERROR: this sheet does not match the ledger entries of batch {args.source_id}. Nothing was written.")
    print(f"promote {args.source_id}: approved={len(outcomes)} added={len(added)} refused={len(refused)}" + ("" if outcomes else " (no change)"))
    if not args.confirm:
        print("nothing written: add --confirm after reading the outcomes above")
        return 2
    if added and not prior:                              # the ledger first: a crash later is finished by a re-run
        P.save_ledger(ledger + [{"batch": args.source_id, "canonical": g, "date": today, "decision": "approve", "key": P.ledger_key(g),
                                 "name": g, "outcome": "added", "reviewer": reviewer} for g in added])
    if changed:
        write_lexicon(changed, source, sha)
    if outcomes:
        GS._atomic_write(args.report, GS._dump({"source": args.source_id, "reviewer": reviewer, "date": today, "input_sha256": sha,
                                                "outcomes": [{"generic": g, "outcome": o} for g, o in outcomes]}))
    return 1 if refused else 0


def run(args, parser) -> int:
    """The CLI entry used by generics_sync.main for ``review-sheet`` and ``promote``."""
    if args.cmd == "promote":
        return do_promote(args, parser)
    if _inside_repo(args.out):
        parser.error("--out is inside the repository: write the sheet outside it (or under doctor_dictation/data/)")
    rows, skipped = review_rows(GS.load_generics(), GS.build.load_drugs()["entries"], GS.load_rules())
    write_sheet(args.out, rows)
    print(f"review-sheet: {args.out} ({len(rows)} generics, skipped {skipped} not shaped like a generic)")
    return 0
