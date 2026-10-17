"""Autoformat safety measurement: live lexicon (drugs.before.json) vs imported copy. Run with PYTHONPATH=<imp copy>."""
import csv
import json
import random
import sys
import time
from pathlib import Path

S = Path(__file__).resolve().parent
sys.path.insert(0, str(S))
import doctor_dictation
from doctor_dictation.core import determinism as D
from doctor_dictation.core.lexicon import lexicon_import as LEX
from opd_sentences import SENTENCES

assert str(S / "imp") in doctor_dictation.__file__, doctor_dictation.__file__
BEFORE, AFTER = S / "drugs.before.json", S / "imp/doctor_dictation/core/lexicon/drugs.json"


def use(path):
    D.LEXICON_PATH = path
    D._lexicon_cache = None
    D._FORMAT_CACHE.clear()
    D.load_lexicon()
    D._maps()


def entries(path):
    return json.loads(path.read_text(encoding="utf-8"))["entries"]


a3 = LEX.read_csv(S / "cdci/a3_nlem_brands.csv")
a3_gen = {}
for r in a3:
    if r["brand"]:
        a3_gen.setdefault(r["brand"].casefold(), (r["brand"], r["generic"]))
after_entries = entries(AFTER)
added = [(b, e["canonical"]) for e in after_entries for b, lin in e.get("lineage", {}).items()
         if lin.get("src") == "cdci-2026-08-31"]
checker = LEX.Checker(after_entries, [], [], LEX.load_rules())
assert len(added) == 205, len(added)
assert len(SENTENCES) >= 300, len(SENTENCES)

res = {}
for tag, path in (("before", BEFORE), ("after", AFTER)):
    use(path)
    t0 = time.perf_counter()
    res[tag] = {
        "a3": {k: D.normalize_transcript(f"tablet {b} 500 mg") for k, (b, _g) in a3_gen.items()},
        "a1": {b: D.normalize_transcript(f"tab {b.lower()} 500 mg") for b, _c in added},
        "opd": [D.normalize_transcript(s) for s in SENTENCES],
    }
    res[tag]["secs_total"] = time.perf_counter() - t0
    print(tag, "done", round(res[tag]["secs_total"]), "s", flush=True)


def mid(out, pre, post=" 500 mg"):
    return out[len(pre):-len(post)] if out.lower().startswith(pre) and out.endswith(post) else out


def drug_of(name, lookup_tag):
    use(BEFORE if lookup_tag == "before" else AFTER)
    return D._canonical_lookup(name) or ""


wrong = {}
for tag in ("before", "after"):
    w = {}
    for k, (b, g) in a3_gen.items():
        m = mid(res[tag]["a3"][k], "tablet ")
        if m.casefold() != b.casefold():
            w[k] = m
    wrong[tag] = w
new = {k: v for k, v in wrong["after"].items() if wrong["before"].get(k) != v}
fixed = {k: v for k, v in wrong["before"].items() if k not in wrong["after"]}
# classify new rewrites: target drug (imported lexicon) vs the brand's A3 generic
use(AFTER)
rows = []
for k, m in sorted(new.items()):
    b, g = a3_gen[k]
    target = D._canonical_lookup(m) or ""
    own = checker.resolve(g)[0] if g else ""
    rows.append({"brand": b, "a3_generic": g, "own_canonical": own, "before": mid(res["before"]["a3"][k], "tablet "),
                 "after": m, "after_drug": target, "different_drug": bool(target) and target != own})
a1_bad = []
for b, c in added:
    m = mid(res["after"]["a1"][b], "tab ")
    if m.casefold() != b.casefold():
        a1_bad.append({"brand": b, "canonical": c, "after": m, "after_drug": D._canonical_lookup(m) or ""})
opd_changed = [{"in": s, "before": x, "after": y} for s, x, y in zip(SENTENCES, res["before"]["opd"], res["after"]["opd"])
               if x != y or y.casefold() != D.normalize_numbers(" ".join(s.split())).casefold()]

# latency: correct_drugs per call, warm, both lexicons
lat = {}
sample = random.Random(1).sample(SENTENCES, 50) + [f"tab {b} 500 mg" for b in list(a3_gen)[:50]]
for tag, path in (("before", BEFORE), ("after", AFTER)):
    use(path)
    for s in sample[:5]:
        D.correct_drugs(s)
    t0 = time.perf_counter()
    for s in sample:
        D.correct_drugs(s)
    lat[tag] = (time.perf_counter() - t0) / len(sample) * 1000
    from doctor_dictation.core.candidates import suggest_candidates
    t0 = time.perf_counter()
    for s in sample[:40]:
        suggest_candidates(s.split()[1] if len(s.split()) > 1 else s)
    lat[tag + "_suggest"] = (time.perf_counter() - t0) / 40 * 1000

out = {"a3_distinct": len(a3_gen), "wrong_before": len(wrong["before"]), "wrong_after": len(wrong["after"]),
       "new_rewrites": rows, "new_count": len(rows), "new_different_drug": sum(r["different_drug"] for r in rows),
       "fixed_count": len(fixed), "fixed": {a3_gen[k][0]: v for k, v in sorted(fixed.items())},
       "a1_added": len(added), "a1_bad": a1_bad, "opd_n": len(SENTENCES), "opd_changed": opd_changed,
       "latency_ms": lat, "batch_secs": {t: res[t]["secs_total"] for t in res}}
(S / "measure_out.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print({k: v for k, v in out.items() if k not in ("new_rewrites", "fixed", "a1_bad", "opd_changed")})
print("a1_bad", a1_bad)
print("opd_changed", len(opd_changed))
for o in opd_changed[:40]:
    print("  ", o)
print("new rewrites (different drug first):")
for r in sorted(rows, key=lambda r: not r["different_drug"])[:80]:
    print("  ", r)
with (S / "new_rewrites.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["brand"])
    w.writeheader()
    w.writerows(rows)
