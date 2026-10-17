"""Clinician review sheet for the 205 brands the real A1 import would add (from the imported scratch copy)."""
import csv
import json
import random
from pathlib import Path

S = Path(__file__).resolve().parent
import doctor_dictation
assert str(S / "imp") in doctor_dictation.__file__
from doctor_dictation.core.lexicon import lexicon_import as LEX

after = json.loads((S / "imp/doctor_dictation/core/lexicon/drugs.json").read_text())["entries"]
before = json.loads((S / "drugs.before.json").read_text())["entries"]
a1 = list(csv.DictReader((S / "cdci/a1_top_brands.csv").open(encoding="utf-8-sig")))
a1rows = LEX.read_csv(S / "cdci/a1_top_brands.csv")
a3 = LEX.read_csv(S / "cdci/a3_nlem_brands.csv")
checker = LEX.Checker(before, [], [], LEX.load_rules())
first = {}
for r, raw in zip(a1rows, a1):
    if r["brand"].casefold() not in first:
        first[r["brand"].casefold()] = (r, raw)
added = sorted(((b, e["canonical"]) for e in after for b, lin in e.get("lineage", {}).items()
                if lin.get("src") == "cdci-2026-08-31"), key=lambda t: (t[1].casefold(), t[0].casefold()))
assert len(added) == 205
web2 = {w.strip().casefold() for w in open("/usr/share/dict/web2")}
proper = {w.strip().casefold() for w in open("/usr/share/dict/propernames")}
generic_words = set()
for e in before:
    for n in [e["canonical"], *e.get("aliases", [])]:
        generic_words.update(w for w in n.casefold().replace("-", " ").split() if len(w) >= 4)
a3_generics = {r["generic"].casefold() for r in a3 if r["generic"]}
SALTS = {"hcl", "hydrochloride", "sulphate", "sulfate", "sodium", "potassium", "acetate", "citrate", "phosphate",
         "maleate", "bromide", "iv", "im", "sr", "cr", "er", "xl", "odt", "d3", "k1"}
HOSPITAL = {"Rituximab", "Enoxaparin", "Meropenem", "Vancomycin", "Oxytocin", "Iron Sucrose", "Cefotaxime", "Ceftazidime",
            "Morphine", "Zoledronic Acid", "Methylergometrine", "Gentamicin", "Insulin Glargine", "Mifepristone",
            "Buprenorphine", "Cyclosporine", "Tacrolimus", "Mycophenolate Mofetil", "Methotrexate", "Amiodarone",
            "Fluphenazine", "Phytomenadione", "Potassium Chloride", "Sodium Bicarbonate", "Magnesium", "Haloperidol",
            "Digoxin", "Labetalol"}
COMBO = {"Suboxone": "buprenorphine + naloxone in practice", "Duodopa": "intestinal gel (hospital)",
         "Gris ODT": "name suggests griseofulvin; CDCI says terbinafine", "Advent": "English word 'advent'",
         "Salazar": "a surname", "Iwata": "a surname"}
SCAN = json.loads((S / "dictscan_out.json").read_text())   # word -> (before, after) from dictscan.py


def lev1(a, b):
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


others = {}   # key -> canonical, lexicon (before) + other added brands + A3 brands with their resolved generic
for k, v in LEX.alias_map(before).items():
    others[k] = v
for r in a3:
    if r["brand"]:
        others.setdefault(r["brand"].casefold(), checker.resolve(r["generic"])[0] or r["generic"])
for b, c in added:
    others.setdefault(b.casefold(), c)

out = []
for b, canon in added:
    r, raw = first[b.casefold()]
    low, flags = b.casefold(), []
    words = low.replace("-", " ").split()
    if any(w in generic_words for w in words) or low in a3_generics:
        flags.append("generic-or-salt name")
    if any(w in SALTS for w in words) and "generic-or-salt name" not in flags:
        flags.append("salt/route suffix")
    form = raw["form"].lower()
    inj_only = ("inject" in form or "infus" in form) and not any(x in form for x in ("oral", "tablet", "capsule"))
    if inj_only:
        flags.append("injectable only (source form: " + raw["form"] + ")")
    elif canon in HOSPITAL:
        flags.append("mostly hospital/specialist drug")
    if 4 <= len(low) <= 8 and low in web2:
        flags.append("English word")
    if low in proper:
        flags.append("proper name")
    near = sorted(k for k, c in others.items() if c and c.casefold() != canon.casefold() and lev1(low, k))
    if 4 <= len(low.replace(" ", "")) <= 8 and near:
        flags.append("one slip from " + "/".join(near[:3]))
    if b in COMBO:
        flags.append(COMBO[b])
    eats = sorted(w for w, (_x, y) in SCAN.items() if y.split()[1] == b)
    if eats:
        flags.append("REWRITES English words: " + "/".join(eats[:6]))
    out.append({"brand": b, "generic": canon, "source_generic": raw["generic"], "source_line": r["line"],
                "source_form": raw["form"], "doubtful": "; ".join(flags), "clinician_ok (y/n)": "", "notes": ""})
cols = list(out[0])
with (S / "clinician_review_sheet.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(out)
sample = sorted(random.Random(20261017).sample(out, 60), key=lambda r: (r["generic"].casefold(), r["brand"].casefold()))
with (S / "clinician_sample_60.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    w.writerows(sample)
flagged = [o for o in out if o["doubtful"]]
print("rows", len(out), "flagged", len(flagged), "sample flagged", sum(1 for o in sample if o["doubtful"]))
from collections import Counter
print(Counter(f.split(" (")[0].split(" from ")[0] for o in out for f in o["doubtful"].split("; ") if f))
for o in flagged:
    if "hospital" not in o["doubtful"] or len(o["doubtful"].split(";")) > 1:
        print(f"  {o['brand']:<20} {o['generic']:<24} {o['doubtful']}")
