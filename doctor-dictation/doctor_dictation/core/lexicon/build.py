"""Build/refresh the local drug lexicon (offline-first).

Default run is fully offline: normalizes the curated entries already in
drugs.json (no network, deterministic output, sorted order).

Merge the authored seed into drugs.json (offline, deterministic, idempotent):
    python doctor_dictation/core/lexicon/build.py --merge [SEED_FILE]
`SEED_FILE` is a top-level JSON array of entries and defaults to
doctor_dictation/core/lexicon/seed_extra.json. Seed entries win on a case-insensitive
`canonical` collision; the semver minor is bumped only when the entry set
actually changes, so running `--merge` twice is byte-identical.

Import brands from a CSV (offline; five checks, brands only; plan I1-g simple). Needs --source-id, --source-name,
--licence, --conflict-map and --report (outside the repository). Writes drugs.json (a `sources` record and per-brand
`lineage`) and imported.json (the changed entries, laid over seed_extra.json by later runs):
    python doctor_dictation/core/lexicon/build.py --merge BRANDS.csv --source-id ID --source-name NAME --licence TEXT \
        --conflict-map MAP.csv --report REPORT.json

Verify the on-disk drugs.json is in sync (offline, never writes):
    python doctor_dictation/core/lexicon/build.py --check [--merge SEED_FILE]
Exits 0 when in sync, 1 when the bytes differ.

Optional enrichment from NIH RxNav (needs internet):
    python doctor_dictation/core/lexicon/build.py --enrich --terms Tamsulosin Azithromycin
Results are cached in doctor_dictation/core/lexicon/rxnav_cache.json so runtime never
depends on the network. Runtime path (doctor_dictation/core/determinism.py) only reads
drugs.json — never calls an API.
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[2])]     # run as a script: the sibling module and the package
import lexicon_import  # noqa: E402

DRUGS_JSON = HERE / "drugs.json"
CACHE_JSON = HERE / "rxnav_cache.json"
DEFAULT_SEED = HERE / "seed_extra.json"
IMPORTED_JSON = HERE / "imported.json"   # every entry an import changed, complete; laid over the seed
MIN_SOURCE_NAME, MIN_LICENCE = 3, 10
SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9.-]{2,40}")
RESERVED_IDS = ("seed", "clinic", "promoted-")       # lineage ids the CSV import may not use


def load_drugs():
    return json.loads(DRUGS_JSON.read_text(encoding="utf-8"))


def serialize(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_drugs(data):
    """Write drugs.json with explicit LF newlines.

    The repo stores LF blobs (``core.autocrlf=true`` can check them out as
    CRLF); writing LF keeps the canonical content byte-identical on every
    platform and avoids ``write_text``'s Windows ``\\n`` -> ``\\r\\n`` translation.
    """
    DRUGS_JSON.write_text(serialize(data), encoding="utf-8", newline="\n")


def save_drugs(data):
    """Normalize sort order only (offline default run; never bumps version).

    Uses the same case-insensitive canonical order as ``--merge``/``--check``
    so a bare run can never reorder — and thus desync — a merged drugs.json.
    """
    data["entries"] = sort_entries(data.get("entries", []))
    write_drugs(data)


def canon_key(entry):
    """Case-insensitive identity key for an entry."""
    return str(entry.get("canonical", "")).casefold()


def sort_entries(entries):
    """Deterministic order: alphabetical by canonical, case-insensitive."""
    return sorted(entries, key=canon_key)


def bump_minor(version):
    """Increment the semver minor component (1.0.0 -> 1.1.0)."""
    parts = str(version or "0.0.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        int(parts[0])
        int(parts[1])
    except ValueError:
        return version  # not a numeric semver: leave untouched
    parts[1] = str(int(parts[1]) + 1)
    return ".".join(parts[:3])


def load_seed(seed_path):
    """Load a seed file and fail loudly on a duplicate canonical inside it."""
    if not seed_path.exists():
        raise SystemExit(f"ERROR: seed file not found: {seed_path}")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(seed, list):
        raise SystemExit(f"ERROR: seed file must be a top-level JSON array: {seed_path}")
    seen = set()
    for entry in seed:
        key = canon_key(entry)
        if key in seen:
            raise SystemExit(
                f"ERROR: duplicate canonical in seed {seed_path}: "
                f"{entry.get('canonical')!r}"
            )
        seen.add(key)
    return seed


def compute_merged(current_data, seed_entries):
    """Merge ``seed_entries`` into ``current_data``.

    Union by case-insensitive ``canonical``; the seed wins on collision.
    Returns ``(data, changed)`` where ``changed`` is True when the entry set
    actually differs (added/removed/changed) and the minor was bumped.
    """
    current_entries = current_data.get("entries", [])
    by_key = {canon_key(e): e for e in current_entries}
    for e in seed_entries:
        by_key[canon_key(e)] = e  # seed wins
    merged = sort_entries(list(by_key.values()))

    changed = sort_entries(current_entries) != merged
    version = current_data.get("version")
    if changed:
        version = bump_minor(version)

    data = dict(current_data)  # preserve top-level key order
    data["entries"] = merged
    data["version"] = version
    return data, changed


def check_source(source):
    """The licence gate for any import: a source id, a name and a licence text, or SystemExit (nothing written)."""
    if len(source.get("name", "")) < MIN_SOURCE_NAME or len(source.get("licence", "")) < MIN_LICENCE \
            or not SOURCE_ID.fullmatch(source.get("id", "")):
        raise ValueError("an import needs --source-id (a-z0-9.-), --source-name (3+ chars) and --licence "
                         "(10+ chars). Nothing was read or written. See plan I1-g simple, Task 5: confirm the licence first.")
    return source


def require_source(args, parser, writes=True):
    """The CLI gate: a CSV merge names its data, licence and CDCI map (and, when it writes, a --report).

    A JSON seed (the repo's seed_extra.json or any other seed array) is not gated: no source or flags needed."""
    if Path(args.merge).suffix.lower() != ".csv":
        return None
    sid = (args.source_id or "").strip()
    fields = {"id": sid, "name": (args.source_name or "").strip(), "licence": (args.licence or "").strip(),
              **{k: v.strip() for k, v in (("url", args.source_url), ("attribution", args.attribution)) if v and v.strip()}}
    if sid.startswith(RESERVED_IDS) or not args.conflict_map or (writes and not args.report):
        parser.error("a CSV merge needs --conflict-map (the full CDCI brand map) and --report (--check needs no report), "
                     "and a --source-id that is not seed, clinic or promoted-*. Nothing was read or written.")
    if args.report and Path(args.report).resolve().is_relative_to(REPO_ROOT):
        parser.error("--report must be outside the repository (it lists skipped brands and may hold licensed data). "
                     "Nothing was read or written.")
    try:
        return check_source(fields)
    except ValueError as exc:
        parser.error(f"ERROR: {exc}")


def layered_seed(seed_path):
    """The seed's entries; for the default seed, with the recorded imports laid on top (additions only)."""
    entries = load_seed(seed_path)
    if seed_path.resolve() == DEFAULT_SEED.resolve() and IMPORTED_JSON.exists():
        entries = lexicon_import.overlay(entries, load_seed(IMPORTED_JSON))
    return entries


def plan_merge(seed_path, source, conflict_path=None):
    """(seed entries, report). A .csv goes through the five checks; anything else is a JSON seed array."""
    if seed_path.suffix.lower() != ".csv":
        return layered_seed(seed_path), None
    check_source(source or {})                       # do_merge called from Python without a source: ValueError, nothing read
    for path in (seed_path, Path(conflict_path)):
        if not path.is_file():
            raise SystemExit(f"ERROR: CSV file not found: {path}")
    report = {}
    rows = lexicon_import.read_csv(seed_path, report)
    conflict = lexicon_import.read_csv(Path(conflict_path), report, "conflict_map_sha256")
    changed, plan = lexicon_import.plan_import(rows, load_drugs()["entries"], conflict, lexicon_import.load_rules(), source["id"])
    return changed, {**plan, **report}


def apply_import(changed, source, report, now=None):
    """Merge COMPLETE changed entries, record them in imported.json and one ``sources`` record; True when written."""
    current = load_drugs()
    data, did_change = compute_merged(current, changed)
    if not did_change:
        return False
    if any(s.get("id") == source["id"] for s in current.get("sources", [])):
        raise SystemExit(f"ERROR: source id {source['id']!r} was already used for an import; pick a new id.")
    recorded = {e["canonical"]: e for e in load_seed(IMPORTED_JSON)} if IMPORTED_JSON.exists() else {}
    recorded.update((e["canonical"], e) for e in changed)
    IMPORTED_JSON.write_text(json.dumps(sort_entries(recorded.values()), indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8", newline="\n")
    record = {**source, "brands_added": report["brands_added"], "input_sha256": report["input_sha256"],
              "merged_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "rules": report["rules"],
              **({"conflict_map_sha256": report["conflict_map_sha256"]} if "conflict_map_sha256" in report else {})}
    data["sources"] = [*current.get("sources", []), dict(sorted(record.items()))]
    write_drugs(data)
    return True


def do_merge(seed_path, source=None, conflict_path=None, report_path=None, now=None):
    before = load_drugs()
    seed, report = plan_merge(seed_path, source, conflict_path)
    if report is None:
        data, changed = compute_merged(before, seed)
        write_drugs(data)
    else:
        changed = apply_import(seed, source, report, now)
        if changed:                                  # a no-change re-run keeps the first run's report
            Path(report_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        else:
            print("no change: drugs.json, imported.json and the report were not rewritten")
    after = load_drugs()
    note = "version bumped" if changed else "no change (version unchanged)"
    print(f"merge {seed_path.name}: entries {len(before['entries'])} -> {len(after['entries'])}, "
          f"version {before.get('version')} -> {after.get('version')} [{note}]")
    if report is not None:
        first = {}
        for s in report["skipped"]:
            first[s["checks"][0]] = first.get(s["checks"][0], 0) + 1
        print(f"import: rows_read={report['rows_read']} brands_added={report['brands_added']} "
              f"already_present={report['already_present']} generics={report['generics']} skipped={dict(sorted(first.items()))}")
    if report is None or changed:
        print(f"wrote {DRUGS_JSON} (sorted by canonical, offline)")


def do_check(seed_path, source=None, conflict_path=None):
    """Recompute in memory and compare bytes; never writes. 0 in sync, 1 drift."""
    current = load_drugs()
    seed, _report = plan_merge(seed_path, source, conflict_path)
    data, _ = compute_merged(current, seed)
    expected = serialize(data).encode("utf-8")
    # Compare canonical (LF) bytes: a CRLF working-tree checkout (core.autocrlf)
    # is semantically identical, so normalize before the byte-for-byte compare.
    actual = DRUGS_JSON.read_bytes().replace(b"\r\n", b"\n")

    if expected == actual:
        print(
            f"check OK: {DRUGS_JSON.name} in sync "
            f"(v{data.get('version')}, {len(data['entries'])} entries)."
        )
        return 0

    cur_c = [canon_key(e) for e in current.get("entries", [])]
    exp_c = [canon_key(e) for e in data["entries"]]
    missing = sorted(set(exp_c) - set(cur_c))[:5]
    extra = sorted(set(cur_c) - set(exp_c))[:5]
    print(f"check FAILED: {DRUGS_JSON.name} is out of sync with {seed_path.name}.", file=sys.stderr)
    print(f"  on-disk : version={current.get('version')} entries={len(cur_c)}", file=sys.stderr)
    print(f"  expected: version={data.get('version')} entries={len(exp_c)}", file=sys.stderr)
    if missing:
        print(f"  missing canonicals: {missing}", file=sys.stderr)
    if extra:
        print(f"  unexpected canonicals: {extra}", file=sys.stderr)
    if not missing and not extra:
        print("  entry set matches but version/serialization differs.", file=sys.stderr)
    return 1


def rxnav_approximate(term: str, cache: dict) -> list:
    if term in cache:
        return cache[term]
    url = ("https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term="
           + urllib.parse.quote(term) + "&maxEntries=5")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"RxNav failed for {term!r}: {e}", file=sys.stderr)
        return []
    cands = (((payload.get("approximateGroup") or {}).get("candidate")) or [])
    names = [c.get("name", "") for c in cands if c.get("name")]
    cache[term] = names
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", action="store_true", help="query RxNav for alias suggestions (needs net)")
    ap.add_argument("--terms", nargs="*", default=[], help="terms to enrich")
    ap.add_argument(
        "--merge", nargs="?", const=str(DEFAULT_SEED), default=None, metavar="SEED_FILE",
        help="merge seed entries into drugs.json (offline, deterministic; "
             "default seed_extra.json)",
    )
    ap.add_argument(
        "--check", action="store_true",
        help="verify drugs.json matches the seed byte-for-byte (offline, never writes)",
    )
    ap.add_argument("--source-id", help="REQUIRED to merge a CSV: lineage id written on every brand (e.g. cdci-2026-08-31)")
    ap.add_argument("--source-name", help="REQUIRED to merge a CSV: the dataset's name (recorded)")
    ap.add_argument("--licence", help="REQUIRED to merge a CSV: the licence text or URL (recorded)")
    ap.add_argument("--source-url", help="where the dataset came from (recorded)")
    ap.add_argument("--attribution", help="attribution text the licence requires (recorded)")
    ap.add_argument("--conflict-map", metavar="CSV", help="REQUIRED with a CSV: the full CDCI brand,generic map (checks 2, 5)")
    ap.add_argument("--report", metavar="PATH", help="REQUIRED to merge a CSV (not for --check): the skipped-row report (JSON), written only when the merge changed entries; keep it outside the repository")
    args = ap.parse_args()

    if args.enrich:
        data = load_drugs()
        print(f"lexicon v{data.get('version')} entries={len(data.get('entries', []))}")
        cache = {}
        if CACHE_JSON.exists():
            cache = json.loads(CACHE_JSON.read_text(encoding="utf-8"))
        for t in args.terms:
            names = rxnav_approximate(t, cache)
            print(f"{t}: {names}")
        CACHE_JSON.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"cache saved: {CACHE_JSON} ({len(cache)} terms)")
        return

    if args.check:
        args.merge = args.merge or str(DEFAULT_SEED)
        sys.exit(do_check(Path(args.merge), require_source(args, ap, writes=False), args.conflict_map))

    if args.merge is not None:
        do_merge(Path(args.merge), require_source(args, ap), args.conflict_map, args.report)
        return

    data = load_drugs()
    print(f"lexicon v{data.get('version')} entries={len(data.get('entries', []))}")
    save_drugs(data)  # normalize sort order only
    print("offline normalize done (sorted, no network).")


if __name__ == "__main__":
    main()
