"""Untrusted CSV handling in lexicon_import.read_csv (copy 'live'); memory for 1e6 rows; splitlines vs csv on real files."""
import csv
import io
import resource
import sys
import time
import traceback
from pathlib import Path

S = Path(__file__).resolve().parent
import doctor_dictation
assert str(S / "live") in doctor_dictation.__file__
from doctor_dictation.core.lexicon import lexicon_import as LEX

D = S / "sec"
D.mkdir(exist_ok=True)
H = "brand,generic\n"
cases = {
    "bom_crlf": ("﻿" + H + "Zentramol,Paracetamol\r\nCrocin,Paracetamol\r\n").encode("utf-8"),
    "nul": (H + "Zent\x00ramol,Paracetamol\n").encode(),
    "non_utf8": (H + "Zentr\xe9mol,Paracetamol\n").encode("latin-1"),
    "huge_field": (H + "A" * 200_000 + ",Paracetamol\n").encode(),
    "formfeed_in_cell": (H + '"Zen\x0ctramol",Paracetamol\nCrocin,Paracetamol\n').encode(),
    "quoted_newline": (H + '"Zen\ntramol",Paracetamol\nCrocin,Paracetamol\n').encode(),
    "x85_in_cell": (H + "Zen\u0085Glycomat,Metformin\n").encode(),
    "formula": (H + "=HYPERLINK(\"x\"),Paracetamol\n").encode(),
    "no_header": b"",
}
for name, data in cases.items():
    p = D / f"{name}.csv"
    p.write_bytes(data)
    try:
        rows = LEX.read_csv(p)
        print(f"{name:<18} OK rows={[(r['line'], r['brand'][:30], r['generic']) for r in rows]}")
    except SystemExit as e:
        print(f"{name:<18} SystemExit: {str(e)[:100]}")
    except Exception as e:
        print(f"{name:<18} {type(e).__name__}: {str(e)[:100]}  (traceback to the operator)")
# 1e6 rows: memory and time
big = D / "big.csv"
with big.open("w") as f:
    f.write(H)
    for i in range(1_000_000):
        f.write(f"Brand{i:07d},Paracetamol\n")
t0, m0 = time.time(), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
try:
    LEX.read_csv(big)
except SystemExit as e:
    print("1e6 rows:", str(e)[:80])
print(f"1e6 rows: {time.time() - t0:.1f}s, peak RSS +{(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - m0) / 1e6:.0f} MB "
      f"(file {big.stat().st_size / 1e6:.0f} MB)")
big.unlink()
# splitlines vs a real csv reader on the real files
for f in ("a1_top_brands.csv", "a3_nlem_brands.csv"):
    raw = (S / "cdci" / f).read_bytes().decode("utf-8-sig")
    a = list(csv.DictReader(raw.splitlines()))
    b = list(csv.DictReader(io.StringIO(raw, newline="")))
    odd = sum(raw.count(ch) for ch in "\x0b\x0c\x1c\x1d\x1e\x85  \r")
    print(f, "splitlines rows", len(a), "csv rows", len(b), "same", a == b, "odd line-break chars", odd)
