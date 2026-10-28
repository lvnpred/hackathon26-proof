"""Brand import for ``build.py --merge FILE.csv`` and ``admin promote-apply`` (plan I1-g simple). Offline, stdlib only.

A brand joins drugs.json only when it passes all five checks (owner rule, 2026-10-17):
  1 its generic is a lexicon canonical or alias, exactly, or a row of the synonym table (import_rules.json);
  2 the brand is listed under one generic only (this file, the full CDCI map, the lexicon);
  3 it has 5+ letters, unless import_rules.json lists it by name;
  4 neither the brand nor any word in it is an ordinary word (core/commonwords.py);
  5 it is not one slip (difflib 0.84) from another drug's name, from any other brand, or from a word of 5+ letters of
    another drug's hyphenated or spaced name (transcripts are read word by word: "Amozid-CV" is heard as "Amozid").
A brand that fails is never added; the report names the row and every failed check. Brands only: no strengths, no forms.
Not a sixth check: a later row of a brand already decided by an earlier row is reported as skipped with the id
``duplicate`` (and ``first_line``), so added + already_present + skipped == rows_read. The FIRST row of a brand decides.
Not a check either: ``skip_brands`` in import_rules.json lists clinician/owner curated exclusions (casefolded exact brand
names, never imported; skipped-row id ``curated-skip``). Known limitation: ``overlay`` (imported.json laid over seed_extra.json) would bring back a brand that a developer later
removes from seed_extra.json; remove it from imported.json as well. All CAPS or all lower case brand names are normalised to Capitalised words (never rejected).
"""
import csv
import difflib
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from doctor_dictation.core.commonwords import WORDS

RULES_JSON = Path(__file__).resolve().parent / "import_rules.json"
CUTOFF, MIN_KEY, MIN_LETTERS, MAX_BRAND, MAX_ROWS = 0.84, 5, 5, 40, 200_000
SHAPE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[ -][A-Za-z0-9]+)*")     # no trailing dot, no leading digit
RX_WORDS = {"rx", "tab", "tablet", "tablets", "cap", "capsule", "capsules", "syp", "syr", "syrup", "inj"}


def clean(text) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).split())


def capitalise_flat(text: str) -> str:
    """ALL CAPS or all lower becomes Capitalised words; a mixed-case spelling is kept."""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), text) if text.isupper() or text.islower() else text


def norm_brand(text) -> str:
    """'TAB. CROCIN' -> 'Crocin': leading Rx/Tab/Cap words go (never the last word), flat case is Capitalised."""
    words = clean(text).split(" ")
    while len(words) > 1 and words[0].lower().rstrip(".:") in RX_WORDS:
        words.pop(0)
    return capitalise_flat(" ".join(words))


def norm_generic(text) -> str:
    """Drop (...) notes; a combination split on + / & , is rejoined as 'A + B'."""
    parts = [capitalise_flat(clean(p)) for p in re.split(r"[+/&,]", re.sub(r"\([^)]*\)", " ", clean(text)))]
    return " + ".join(p for p in parts if p)


def load_rules(path=RULES_JSON) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    skip = raw.get("skip_brands", [])
    skip = [b for names in skip.values() for b in names] if isinstance(skip, dict) else skip     # a list, or {class: [brands]}
    return {"version": raw["version"], "short_ok": {s.casefold() for s in raw["short_brands_allowed"]},
            "synonyms": {k.casefold(): v for k, v in raw["synonyms"].items()},
            "skip": {s.casefold() for s in skip}}


def read_csv(path, report=None, sha_key="input_sha256") -> list:
    """[{line, brand, generic}] from a UTF-8 CSV with brand and generic columns (extra columns ignored)."""
    raw = Path(path).read_bytes()
    if report is not None:
        report[sha_key] = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"ERROR: CSV {path} is not UTF-8 ({exc.reason} at byte {exc.start}). Nothing was written.") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))        # newline="": a quoted newline or \x85 / U+2028 stays in its cell
    col = {(f or "").strip().lower(): f for f in (reader.fieldnames or [])}
    if not {"brand", "generic"} <= set(col):
        raise SystemExit(f"ERROR: CSV {path} needs the columns ['brand', 'generic']; found {list(col)}")
    rows = []
    try:
        for line, rec in enumerate(reader, start=2):          # line = record number, the header is record 1
            if line > MAX_ROWS + 1:
                raise SystemExit(f"ERROR: CSV {path} has more than {MAX_ROWS} rows")
            rows.append({"line": line, "brand": norm_brand(rec.get(col["brand"])), "generic": norm_generic(rec.get(col["generic"]))})
    except csv.Error as exc:                                   # for example a field over 128 KB
        raise SystemExit(f"ERROR: CSV {path} cannot be read: {exc}. Nothing was written.") from None
    return rows


def alias_map(entries) -> dict:
    """determinism._alias_map over ``entries``: canonicals and aliases claim names first, then brands."""
    m: dict = {}
    ordered = sorted(entries, key=lambda e: e.get("canonical", ""))
    for field in ("aliases", "brands"):
        for e in ordered:
            canon = e.get("canonical", "")
            for a in ([canon] if field == "aliases" else []) + list(e.get(field, [])):
                if canon and a.strip() and a.strip().lower() not in m:
                    m[a.strip().lower()] = canon
    return m


class Checker:
    """The five checks over one lexicon, the CDCI map (``conflict_rows``) and the rows of this run (``candidates``)."""

    def __init__(self, entries, conflict_rows, candidates, rules):
        self.rules, self.names = rules, alias_map(entries)
        self.generics = alias_map([{**e, "brands": []} for e in entries])        # canonical and alias only, never a brand
        if any(v.casefold() not in self.generics for v in rules["synonyms"].values()):
            raise SystemExit("ERROR: import_rules.json maps a synonym to a name that is not a lexicon canonical")
        self.listed = defaultdict(set)                                          # brand key -> generics listing it
        for r in [*conflict_rows, *candidates]:
            if r["brand"] and r["generic"]:
                self.listed[r["brand"].casefold()].add((self.resolve(r["generic"])[0] or r["generic"]).casefold())
        self.words, self.word_name = defaultdict(set), {}    # word (5+ letters) of a multi-word name -> its drugs, one name
        for k in [*self.names, *self.listed]:
            if re.search(r"[ -]", k):
                for w in re.findall(r"[a-z]+", k):
                    if len(w) >= MIN_KEY:
                        owners = [self.names[k]] if k in self.names else sorted(self.listed[k])
                        self.words[w] |= {o.casefold() for o in owners}
                        self.word_name.setdefault(w, owners[0])
        self.pool = sorted({k for k in [*self.names, *self.listed, *self.words] if len(k) >= MIN_KEY})

    def resolve(self, generic):
        """(canonical, 'exact' | 'synonym', '') or ('', '', the nearest lexicon generic, for the report only)."""
        key = generic.casefold()
        if key in self.generics:
            return self.generics[key], "exact", ""
        if key in self.rules["synonyms"]:
            return self.rules["synonyms"][key], "synonym", ""
        near = difflib.get_close_matches(key, [k for k in sorted(self.generics) if len(k) >= MIN_KEY], n=1, cutoff=CUTOFF)
        return "", "", self.generics[near[0]] if near else ""

    def failures(self, brand, canonical=""):
        """(failed checks 2-5 plus 'shape', near names behind check 5). ``canonical`` '' = not chosen yet."""
        low, failed = brand.casefold(), []
        if not (SHAPE.fullmatch(brand) and len(brand) <= MAX_BRAND):
            failed.append("shape")
        owner, listed = self.names.get(low), self.listed.get(low, set()) | ({canonical.casefold()} if canonical else set())
        if (owner and owner != canonical) or len(listed) > 1:
            failed.append("2-one-generic")
        if sum(c.isalpha() for c in brand) < MIN_LETTERS and low not in self.rules["short_ok"]:
            failed.append("3-five-letters")
        if low in WORDS or any(w in WORDS for w in re.split(r"[ -]", low)):
            failed.append("4-ordinary-word")
        near = [k for k in difflib.get_close_matches(low, self.pool, n=5, cutoff=CUTOFF)
                if k != low and not (canonical and (self.generics.get(k) == canonical or
                                                    self.words.get(k) == {canonical.casefold()}))]
        return failed + (["5-one-slip"] if near else []), near


def merge_brands(entries, additions) -> list:
    """COMPLETE changed entries: existing lists untouched, new brands last (casefold order), one lineage record each.

    ``additions``: {canonical: [(brand, lineage dict or None)]}."""
    by_canon, changed = {e["canonical"]: e for e in entries}, []
    for canon in sorted(additions):
        base, have = by_canon[canon], {b.casefold() for b in by_canon[canon]["brands"]}
        new = sorted({b.casefold(): (b, lin) for b, lin in additions[canon] if b.casefold() not in have}.values(),
                     key=lambda t: t[0].casefold())
        if new:
            lineage = {**base.get("lineage", {}), **{b: dict(sorted(lin.items())) for b, lin in new if lin}}
            changed.append(dict(sorted({**base, "brands": [*base["brands"], *(b for b, _ in new)],
                                        "lineage": dict(sorted(lineage.items()))}.items())))
    return changed


def overlay(seed, imported):
    """``seed`` entries with the recorded imports laid on top: brands appended in the RECORDED order (several imports
    stay in the order they were merged, not casefold order), lineage merged, nothing removed."""
    by_key = {e["canonical"].casefold(): e for e in seed}
    for imp in imported:
        base = by_key.get(imp["canonical"].casefold())
        if base is None:
            by_key[imp["canonical"].casefold()] = imp
            continue
        have = {b.casefold() for b in base["brands"]}
        new = [b for b in imp["brands"] if b.casefold() not in have]
        if new:
            lineage = {**base.get("lineage", {}), **imp.get("lineage", {})}
            by_key[imp["canonical"].casefold()] = dict(sorted({**base, "brands": [*base["brands"], *new],
                "lineage": dict(sorted((b, lineage[b]) for b in [*base["brands"], *new] if b in lineage))}.items()))
    return list(by_key.values())


def plan_import(rows, entries, conflict_rows, rules, source_id):
    """(changed entries, report) for CSV ``rows``; reads nothing, never changes or removes an existing name."""
    report = {"source": source_id, "rules": rules["version"], "rows_read": len(rows), "brands_added": 0,
              "already_present": 0, "generics": {"exact": 0, "synonym": 0, "not_in_lexicon": 0}, "skipped": []}
    check, seen, firsts, additions = Checker(entries, conflict_rows, rows, rules), {}, {}, defaultdict(list)
    for r in rows:
        canon, kind, near = check.resolve(r["generic"]) if r["generic"] else ("", "", "")
        if r["generic"].casefold() not in seen:
            seen[r["generic"].casefold()] = kind or "not_in_lexicon"
            report["generics"][kind or "not_in_lexicon"] += 1
        if not canon:
            report["skipped"].append({"brand": r["brand"], "checks": ["1-generic"], "generic": r["generic"],
                                      "line": r["line"], **({"looks_like": near} if near else {})})
        elif r["brand"].casefold() not in firsts:
            firsts[r["brand"].casefold()] = (r, canon)
        else:
            report["skipped"].append({"brand": r["brand"], "checks": ["duplicate"], "generic": r["generic"], "line": r["line"],
                                      "first_line": firsts[r["brand"].casefold()][0]["line"]})
    for r, canon in firsts.values():
        if check.names.get(r["brand"].casefold()) == canon:
            report["already_present"] += 1
            continue
        failed, near = check.failures(r["brand"], canon)
        if r["brand"].casefold() in rules.get("skip", ()):
            report["skipped"].append({"brand": r["brand"], "checks": ["curated-skip"], "generic": r["generic"], "line": r["line"]})
        elif failed:
            report["skipped"].append({"brand": r["brand"], "checks": failed, "generic": r["generic"], "line": r["line"],
                                      **({"near": near[:3]} if near else {}),
                                      **({"rewrites_to": check.names.get(near[0]) or check.word_name[near[0]]} if near and (
                                          near[0] in check.names or near[0] in check.word_name) else {})})
        else:
            additions[canon].append((r["brand"], {"src": source_id}))
    changed = merge_brands(entries, additions)
    report["brands_added"] = sum(len(v) for v in additions.values())
    report["skipped"].sort(key=lambda s: s["line"])
    return changed, report
