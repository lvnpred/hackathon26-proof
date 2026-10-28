"""A3 brands 'tablet <brand> 500 mg': classify every rewrite by the drug of the replacement word, before vs after."""
import json
import re
from pathlib import Path

S = Path(__file__).resolve().parent
import doctor_dictation
assert str(S / "imp") in doctor_dictation.__file__
from doctor_dictation.core import determinism as D
from doctor_dictation.core.lexicon import lexicon_import as LEX

BEFORE, AFTER = S / "drugs.before.json", S / "imp/doctor_dictation/core/lexicon/drugs.json"
a3 = {}
for r in LEX.read_csv(S / "cdci/a3_nlem_brands.csv"):
    if r["brand"]:
        a3.setdefault(r["brand"].casefold(), (r["brand"], r["generic"]))
own_checker = LEX.Checker(json.loads(BEFORE.read_text())["entries"], [], [], LEX.load_rules())
res = {}
for tag, path in (("before", BEFORE), ("after", AFTER)):
    D.LEXICON_PATH, D._lexicon_cache = path, None
    amap = D._alias_map()
    out = {}
    for k, (b, g) in a3.items():
        t = f"tablet {b} 500 mg"
        n = D.normalize_transcript(t)
        if n.casefold() == t.casefold():
            continue
        old, new = re.findall(r"[A-Za-z]+", t.casefold()), re.findall(r"[A-Za-z]+", n.casefold())
        repl = [w for w in new if w not in old]
        drugs = sorted({amap.get(w) or D._canonical_lookup(w) for w in repl} - {"", None}) or \
            sorted({D._canonical_lookup(n[len("tablet "):-len(" 500 mg")])} - {""})
        own = own_checker.resolve(g)[0] if g else ""
        kind = "same drug" if drugs and all(d == own for d in drugs) else \
            "different drug" if drugs and own else "own generic unknown to lexicon" if drugs else "no drug"
        out[k] = (n[len("tablet "):-len(" 500 mg")] if n.endswith(" 500 mg") else n, kind, drugs, own)
    res[tag] = out
summary = {}
for tag in res:
    c = {}
    for v in res[tag].values():
        c[v[1]] = c.get(v[1], 0) + 1
    summary[tag] = c
print("A3 distinct", len(a3), json.dumps(summary))
newdiff = {k: v for k, v in res["after"].items() if v[1] in ("different drug", "own generic unknown to lexicon")
           and res["before"].get(k, (None,))[0] != v[0]}
gone = {k: v for k, v in res["before"].items() if v[1] in ("different drug", "own generic unknown to lexicon")
        and res["after"].get(k, (None,))[0] != v[0]}
print("NEW wrong-drug rewrites after import:", len(newdiff))
for k, v in sorted(newdiff.items()):
    print(f"   {a3[k][0]} ({a3[k][1]}) -> {v[0]}  [{v[1]}: {', '.join(v[2])}; before: {res['before'].get(k, ('unchanged',))[0]}]")
print("wrong-drug rewrites that disappear after import:", len(gone))
for k, v in sorted(gone.items())[:20]:
    print(f"   {a3[k][0]} ({a3[k][1]}) before -> {v[0]} ; after -> {res['after'].get(k, ('unchanged',))[0]}")
