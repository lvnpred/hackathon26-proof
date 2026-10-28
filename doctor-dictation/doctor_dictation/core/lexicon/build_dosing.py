"""Rebuild lexicon/dosing.json from a LOCAL CSV (offline, no scheduler): build_dosing.py in.csv --version 2026-10.

Header: canonical,strengths,forms,usual,freq,max_daily_mg,source,reviewed (';' separates list cells). An invalid
row lists every problem, exits 1 and leaves the existing file alone. Same CSV and flags give the same bytes.
"""
import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from doctor_dictation.core.dosing import parse_strength_mg

HERE = Path(__file__).resolve().parent
DRUGS_JSON, DOSING_JSON = HERE / "drugs.json", HERE / "dosing.json"
COLUMNS = ["canonical", "strengths", "forms", "usual", "freq", "max_daily_mg", "source", "reviewed"]
MAX_DAILY_MG_CEILING = 100000                # plausibility ceiling, not a clinical limit
_CAP_RE = re.compile(r"[0-9]+(\.[0-9]+)?")   # ASCII digits only: no signs, exponents, underscores, nan/inf
FORMS = ("Tab.", "Cap.", "Syr.", "Inj.")   # a test pins this to determinism.ALLOWED_FORMS

def _entry(row: dict, canon: dict) -> tuple:
    """(entry, []) or (None, problems)."""
    if None in row or any(v is None for v in row.values()):
        return None, ["wrong number of columns"]
    if any("\x00" in v for v in row.values()):
        return None, ["NUL byte in a cell"]
    g = lambda k: (row.get(k) or "").strip()                                   # noqa: E731
    cells = lambda k: [c.strip() for c in g(k).split(";") if c.strip()]       # noqa: E731
    name, strengths, forms = canon.get(g("canonical").casefold()), cells("strengths"), cells("forms")
    cap = float(g("max_daily_mg")) if _CAP_RE.fullmatch(g("max_daily_mg")) else 0.0
    bad = [msg for ok, msg in [
        (name, f"canonical {g('canonical')!r} is not in drugs.json"),
        (strengths and all(parse_strength_mg(s) is not None for s in strengths), "strengths must be like '5 mg', '1 g', '250 mcg'"),
        (forms and all(f in FORMS for f in forms), f"forms must be a ';' list of {', '.join(FORMS)}"),
        (g("usual") in strengths, f"usual {g('usual')!r} is not one of the strengths"),
        (0 < cap <= MAX_DAILY_MG_CEILING, f"max_daily_mg {g('max_daily_mg')!r} is not a positive number (at most {MAX_DAILY_MG_CEILING})"),
        (len(set(strengths)) == len(strengths), "duplicate strength in the strengths cell"),
        (len(set(forms)) == len(forms), "duplicate form in the forms cell"),
        (g("source"), "source is blank"),
        (g("reviewed").lower() in ("yes", "no"), "reviewed must be yes or no"),
    ] if not ok]
    if bad:
        return None, bad
    adult = {"usual": g("usual"), "freq": g("freq"), "max_daily_mg": int(cap) if cap == int(cap) else cap}
    return {"canonical": name, "strengths": strengths, "forms": forms, "adult": adult,
            "source": g("source"), "reviewed": g("reviewed").lower() == "yes"}, []

def build_entries(csv_path: Path) -> list:
    """Validated entries sorted by canonical; ValueError lists every problem."""
    canon = {e["canonical"].casefold(): e["canonical"] for e in json.loads(DRUGS_JSON.read_text("utf-8"))["entries"]}
    problems, entries = [], {}
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"CSV header must be exactly: {','.join(COLUMNS)}")
        for n, row in enumerate(reader, start=2):
            entry, errs = _entry(row, canon)
            if entry and entry["canonical"] in entries:
                errs = [f"duplicate canonical {entry['canonical']!r}"]
            problems += [f"row {n}: {e}" for e in errs]
            if not errs:
                entries[entry["canonical"]] = entry
    if not problems and not entries:
        raise ValueError("CSV has no data rows (refusing to wipe the reference)")
    if problems:
        raise ValueError("\n".join(problems))
    return sorted(entries.values(), key=lambda e: e["canonical"].casefold())

def _entry_count(path: Path) -> int:
    """Entries in the existing output file; 0 when it is missing or unreadable."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
        return len(entries) if isinstance(entries, list) else 0
    except Exception:    # noqa: BLE001  missing, broken or oddly shaped: nothing to protect
        return 0

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--version", required=True, help="footer label, for example 2026-10")
    ap.add_argument("--built-at", default=date.today().isoformat(), help="pass it for a byte-identical rerun")
    ap.add_argument("--out", type=Path, default=DOSING_JSON)
    ap.add_argument("--allow-shrink", action="store_true", help="accept a result under 80%% of the existing entry count")
    args = ap.parse_args(argv)
    if not args.version.strip():
        print("ERROR: --version must not be blank", file=sys.stderr)
        return 1
    try:
        entries = build_entries(args.csv)
    except (ValueError, OSError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    old = _entry_count(args.out)
    print(f"old: {old} entries, new: {len(entries)} entries")
    if old >= 5 and len(entries) < 0.8 * old and not args.allow_shrink:
        print(f"ERROR: new reference has {len(entries)} entries, the existing one has {old} (under 80%); "
              "file left untouched. Pass --allow-shrink if that is intended.", file=sys.stderr)
        return 1
    doc = {"version": args.version, "built_at": args.built_at, "entries": entries}
    tmp = args.out.with_name(args.out.name + ".tmp")        # write beside the target, then replace: never half a file
    try:
        tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, args.out)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.out}: {len(entries)} entries")
    return 0

if __name__ == "__main__":
    sys.exit(main())
