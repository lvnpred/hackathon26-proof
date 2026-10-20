"""Build ``investigations.json`` from the reviewed investigations CSV.

Usage: python -m doctor_dictation.core.lexicon.build_investigations <csv> [--version X.Y.Z]

CSV columns: canonical, aliases (semicolon-separated), category, print, and an
optional safety column. Lines starting with ``#`` are comments. A comment
containing ``NOT REVIEWED`` makes the build refuse unless ``allow_draft``.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from pathlib import Path

CATEGORIES = ("Blood", "Urine", "Stool", "Microbiology", "Hormones",
              "Tumour markers", "Imaging", "Cardiac", "Urology", "Other")
OUT_PATH = Path(__file__).with_name("investigations.json")
_NON_ALNUM = re.compile(r"[\W_]+")
_TRUTHY = {"1", "true", "yes", "y"}


def key(text: str) -> str:
    """Normalise a name: casefold, '&' as ' and ', non-alphanumerics as space."""
    folded = (text or "").casefold().replace("&", " and ")
    return _NON_ALNUM.sub(" ", folded).strip()


def rows_from_csv(text: str, allow_draft: bool = False) -> list[dict]:
    comments = [ln for ln in text.splitlines() if ln.startswith("#")]
    if not allow_draft and any("NOT REVIEWED" in ln.upper() for ln in comments):
        raise ValueError("investigations CSV is marked NOT REVIEWED")
    body = "\n".join(ln for ln in text.splitlines() if not ln.startswith("#"))
    entries: list[dict] = []
    owner: dict[str, str] = {}
    for n, row in enumerate(csv.DictReader(io.StringIO(body)), start=1):
        canonical = (row.get("canonical") or "").strip()
        if not canonical:
            raise ValueError(f"row {n}: blank canonical")
        category = (row.get("category") or "").strip()
        if category not in CATEGORIES:
            raise ValueError(f"row {n} ({canonical}): unknown category {category!r}")
        aliases = [a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()]
        printed = (row.get("print") or "").strip()
        seen: set[str] = set()
        for name in [canonical, *aliases, printed]:
            k = key(name)
            if not k or k in seen:
                continue
            seen.add(k)
            if k in owner:
                raise ValueError(
                    f"name {k!r} claimed by both {owner[k]!r} and {canonical!r}")
            owner[k] = canonical
        entry = {"canonical": canonical, "aliases": aliases,
                 "category": category, "print": printed}
        if (row.get("safety") or "").strip().casefold() in _TRUTHY:
            entry["safety"] = True
        entries.append(entry)
    return entries


def build(csv_path: Path, out_path: Path, version: str,
          allow_draft: bool = False) -> dict:
    entries = rows_from_csv(Path(csv_path).read_text(encoding="utf-8"), allow_draft)
    doc = {"version": version, "entries": entries}
    Path(out_path).write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", type=Path)
    ap.add_argument("--version", default="1.0.0")
    args = ap.parse_args(argv)
    doc = build(args.csv, OUT_PATH, args.version)
    print(f"wrote {len(doc['entries'])} entries to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
