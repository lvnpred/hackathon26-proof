"""English words (macOS web2, lower-case, 5+ letters, not in the denylist) newly rewritten after the import."""
import difflib
import json
from pathlib import Path

S = Path(__file__).resolve().parent
import doctor_dictation
assert str(S / "imp") in doctor_dictation.__file__
from doctor_dictation.core import determinism as D
from doctor_dictation.core.commonwords import WORDS

after = json.loads((S / "imp/doctor_dictation/core/lexicon/drugs.json").read_text())["entries"]
new_keys = sorted({b.lower() for e in after for b, l in e.get("lineage", {}).items() if len(b) >= 5 and " " not in b})
words = sorted({w.strip() for w in open("/usr/share/dict/web2") if w.strip().islower() and len(w.strip()) >= 5} - WORDS)
cand = [w for w in words if difflib.get_close_matches(w, new_keys, n=1, cutoff=0.84)]
print("web2 words", len(words), "near a new key", len(cand))


def run(path):
    D.LEXICON_PATH, D._lexicon_cache = path, None
    return {w: D.normalize_transcript(f"patient {w} today") for w in cand}


b, a = run(S / "drugs.before.json"), run(S / "imp/doctor_dictation/core/lexicon/drugs.json")
changed = {w: (b[w], a[w]) for w in cand if a[w] != b[w]}
print("newly rewritten", len(changed))
for w, (x, y) in sorted(changed.items()):
    print(f"  {w:<14} -> {y}")
(S / "dictscan_out.json").write_text(json.dumps(changed, indent=1))
