"""8 mutants on the scratch copy 'mut'; each is applied, the lexicon/promotion tests run, the file restored."""
import os
import subprocess
import sys
from pathlib import Path

S = Path(__file__).resolve().parent
M = S / "mut"
DD = M / "doctor_dictation"
MUTANTS = [
    ("denylist pass-2 hook removed", DD / "core/determinism.py",
     "if _ambiguous_for(low) or low in COMMON_WORDS:", "if _ambiguous_for(low):"),
    ("check 2 within-map conflict loosened (>1 -> >2)", DD / "core/lexicon/lexicon_import.py",
     "or len(listed) > 1:", "or len(listed) > 2:"),
    ("gate after read (plan_merge reads CSVs before check_source)", DD / "core/lexicon/build.py",
     "    check_source(source or {})                       # do_merge called from Python without a source: ValueError, nothing read\n"
     "    for path in (seed_path, Path(conflict_path)):\n        if not path.is_file():\n            raise SystemExit(f\"ERROR: CSV file not found: {path}\")\n"
     "    report = {}\n    rows = lexicon_import.read_csv(seed_path, report)\n",
     "    report = {}\n    rows = lexicon_import.read_csv(seed_path, report)\n    check_source(source or {})\n"),
    ("lineage dropped for imported brands", DD / "core/lexicon/lexicon_import.py",
     'additions[canon].append((r["brand"], {"src": source_id}))', 'additions[canon].append((r["brand"], None))'),
    ("ledger key plain sha256 (no pepper)", DD / "promotion.py",
     'return hmac.new(pepper(), F.key(name).encode("utf-8"), hashlib.sha256).hexdigest()',
     'return hashlib.sha256(F.key(name).encode("utf-8")).hexdigest()'),
    ("apply writes without --confirm", DD / "promotion.py", "    if not confirm:\n        return 2, outcomes\n", ""),
    ("candidates opens clinic DBs read-write", DD / "promotion.py", '"?mode=ro"', '"?mode=rw"'),
    ("skip_brands ignored", DD / "core/lexicon/lexicon_import.py", 'rules.get("skip", ())', '()'),
]
TESTS = ["tests/test_commonwords.py", "tests/test_lexicon_import.py", "tests/test_promotion.py", "tests/test_candidates.py",
         "tests/test_determinism.py", "tests/test_brand_as_dictated.py"]
env = {**os.environ, "PYTHONPATH": str(M), "DB_PATH": str(S / "x_mut.db")}
for name, path, old, new in MUTANTS:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, text.count(old))
    path.write_text(text.replace(old, new), encoding="utf-8")
    try:
        r = subprocess.run([str(M / ".venv/bin/python"), "-m", "pytest", *TESTS, "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=M, env=env, capture_output=True, text=True)
        tail = [l for l in r.stdout.splitlines() if l.startswith("FAILED") or " passed" in l or " failed" in l]
        print(f"{'KILLED ' if r.returncode else 'SURVIVED'} | {name} | {' / '.join(tail[-2:])}", flush=True)
    finally:
        path.write_text(text, encoding="utf-8")
