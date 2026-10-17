"""Lexicon load, correct_drugs, suggest_candidates latency: live (508 brands) vs imported (713 brands)."""
import json
import statistics
import time
from pathlib import Path

S = Path(__file__).resolve().parent
import doctor_dictation
assert str(S / "imp") in doctor_dictation.__file__
from doctor_dictation.core import determinism as D
from doctor_dictation.core import candidates as C
from opd_sentences import SENTENCES

TXT = ("patient with fever 3 days and cough, tab dolo 650 mg thrice daily after food, tab azithral 500 mg once daily "
       "for 3 days, syrup ascoril 10 ml twice daily, tab pan 40 before breakfast, review after 5 days")
for path in (S / "drugs.before.json", S / "imp/doctor_dictation/core/lexicon/drugs.json"):
    data = json.loads(path.read_text())
    nb = sum(len(e["brands"]) for e in data["entries"])
    D.LEXICON_PATH, D._lexicon_cache = path, None
    t0 = time.perf_counter()
    D.load_lexicon(); D._maps(); D._alias_map()
    load = (time.perf_counter() - t0) * 1000
    D.correct_drugs("warm up")
    runs = []
    for _ in range(20):
        t0 = time.perf_counter(); D.correct_drugs(TXT); runs.append((time.perf_counter() - t0) * 1000)
    short = []
    for s in SENTENCES[:100]:
        t0 = time.perf_counter(); D.correct_drugs(s); short.append((time.perf_counter() - t0) * 1000)
    sug = []
    for q in ("dolo", "azithral", "wymx", "paracetmol", "the doctor", "zofr", "glycomat", "cefixim"):
        t0 = time.perf_counter(); C.suggest_candidates(q); sug.append((time.perf_counter() - t0) * 1000)
    print(f"{path.name:<18} v{data['version']} brands={nb} bytes={path.stat().st_size} load+maps={load:.1f}ms "
          f"correct_drugs(long OPD)={statistics.median(runs):.1f}ms median, short sentence={statistics.median(short):.1f}ms median "
          f"/ {max(short):.1f} max, suggest_candidates={statistics.median(sug):.1f}ms median / {max(sug):.1f} max")
print("imported.json bytes", (S / "imp/doctor_dictation/core/lexicon/imported.json").stat().st_size)
