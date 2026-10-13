"""Build/refresh the local drug lexicon (offline-first).

Default run is fully offline: normalizes the curated entries already in
drugs.json (no network, deterministic output, sorted order).

Merge the authored seed into drugs.json (offline, deterministic, idempotent):
    python doctor_dictation/core/lexicon/build.py --merge [SEED_FILE]
`SEED_FILE` is a top-level JSON array of entries and defaults to
doctor_dictation/core/lexicon/seed_extra.json. Seed entries win on a case-insensitive
`canonical` collision; the semver minor is bumped only when the entry set
actually changes, so running `--merge` twice is byte-identical.

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
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRUGS_JSON = HERE / "drugs.json"
CACHE_JSON = HERE / "rxnav_cache.json"
DEFAULT_SEED = HERE / "seed_extra.json"


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


def do_merge(seed_path):
    current = load_drugs()
    before = len(current.get("entries", []))
    version_before = current.get("version")
    seed = load_seed(seed_path)
    data, changed = compute_merged(current, seed)
    after = len(data["entries"])

    write_drugs(data)
    note = "version bumped" if changed else "no change (version unchanged)"
    print(
        f"merge {seed_path.name}: entries {before} -> {after}, "
        f"version {version_before} -> {data.get('version')} [{note}]"
    )
    print(f"wrote {DRUGS_JSON} (sorted by canonical, offline)")


def do_check(seed_path):
    """Recompute in memory and compare bytes; never writes. 0 in sync, 1 drift."""
    current = load_drugs()
    seed = load_seed(seed_path)
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
        seed_path = Path(args.merge) if args.merge else DEFAULT_SEED
        sys.exit(do_check(seed_path))

    if args.merge is not None:
        do_merge(Path(args.merge))
        return

    data = load_drugs()
    print(f"lexicon v{data.get('version')} entries={len(data.get('entries', []))}")
    save_drugs(data)  # normalize sort order only
    print("offline normalize done (sorted, no network).")


if __name__ == "__main__":
    main()
