"""Promotion end to end on temp data only (copy 'live'). Prints what the operator sees."""
import contextlib
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import closing
from pathlib import Path

S = Path(__file__).resolve().parent
ROOT = Path(tempfile.mkdtemp(prefix="e2e_", dir=S))
os.environ.update({"MULTI_CLINIC": "1", "DATA_DIR": str(ROOT / "data"), "SESSION_SECRET": "e2e-session-secret-" + "x" * 24,
                   "OPENAI_API_KEY": "", "DEEPSEEK_API_KEY": ""})
os.environ.pop("DB_PATH", None)
PEPPER = "e2e-pepper-SECRET-9f8e7d6c5b"
os.environ["PROMOTION_LEDGER_PEPPER"] = PEPPER
import doctor_dictation
assert str(S / "live") in doctor_dictation.__file__
from doctor_dictation import admin, clinics, promotion
from doctor_dictation import db as dbmod
from doctor_dictation.core.formulary import key
from doctor_dictation.core.lexicon import build
from doctor_dictation.db import formulary as fdb
from doctor_dictation.scope import clinic_dir

LEX = ROOT / "lex"
LEX.mkdir()
live_drugs = S / "live/doctor_dictation/core/lexicon/drugs.json"
live_before = hashlib.sha256(live_drugs.read_bytes()).hexdigest()
shutil.copy(live_drugs, LEX / "drugs.json")
(LEX / "ledger.json").write_text(json.dumps({"entries": [], "version": "dd-promotion-v2"}, indent=2) + "\n")
build.DRUGS_JSON, build.IMPORTED_JSON, promotion.LEDGER_JSON = LEX / "drugs.json", LEX / "imported.json", LEX / "ledger.json"
CONFLICT = str(S / "live/tests/data/conflict_fixture.csv")


def learn(path, names):
    with closing(dbmod.get_conn(path)) as conn:
        dbmod.migrate(conn)
        eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "Sunita Rao", "40 / F", None))
        docs = [dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(2)]
        for name, generic in names:
            for doc in docs:
                fdb.record_confirmation(conn, key(name), name, generic, doc, None)


COMMON = [("Zorbexin", "paracetamol"), ("Ravi Kulkarni", ""), ("Crocin", "paracetamol"), ("Glycomat", "metformin"),
          ("Quenrix", ""), ("Brivantel", "atorvastatin")]
for slug, extra in (("alpha", [("Velquara", "")]), ("beta", [("Velquara", "")]), ("gamma", [])):
    clinics.provision_clinic(slug, slug.title() + " Clinic")
    learn(clinic_dir(slug) / "app.db", COMMON + extra)


def digests():
    return {p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.glob("data/clinics/*/app.db"))}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = admin.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else f"SystemExit({exc.code!r}) -> 1"
    print(f"\n$ admin {' '.join(a if PEPPER not in a else '<pepper>' for a in argv)}\n  exit={code}")
    for tag, buf in (("out", out), ("err", err)):
        for line in buf.getvalue().splitlines():
            print(f"  {tag}| {line}")
    TRANSCRIPT.append(out.getvalue() + err.getvalue())
    return code


TRANSCRIPT = []
before = digests()
review = ROOT / "data/promotion/2026-11/candidates.csv"
run("promote-candidates", "--out", str(S / "live/docs/candidates.csv"), "--conflict-map", CONFLICT)   # guard
run("promote-candidates", "--out", str(review), "--conflict-map", CONFLICT)
print("  CSV:\n    " + review.read_text().replace("\n", "\n    "))
rows = list(csv.DictReader(review.open()))
for r in rows:
    r["decision"] = {"Zorbexin": "approve", "Quenrix": "approve", "Brivantel": "approve"}.get(r["name"], "reject")
    r["reviewer"] = "Dr. Meera Nair" if r["name"] == "Zorbexin" else ""
rows.append({"name": "Murexol", "generic": "", "clinics_count": "3", "first_seen": "", "last_seen": "", "decision": "reject",
             "reviewer": "", "notes": "a surname"})
reviewed = ROOT / "data/promotion/2026-11/reviewed.csv"
with reviewed.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=promotion.COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
lex_before = (LEX / "drugs.json").read_bytes()
run("promote-apply", "--csv", str(reviewed), "--batch", "2026-11", "--conflict-map", CONFLICT)                  # no reviewer
run("promote-apply", "--csv", str(reviewed), "--batch", "2026-11", "--reviewer", "Dr. Asha Rao", "--conflict-map", CONFLICT)
print("  drugs.json unchanged without --confirm:", (LEX / "drugs.json").read_bytes() == lex_before,
      "| ledger still empty:", json.loads((LEX / "ledger.json").read_text())["entries"] == [])
run("promote-apply", "--csv", str(reviewed), "--batch", "2026-11", "--reviewer", "Dr. Asha Rao", "--conflict-map", CONFLICT, "--confirm")
data = json.loads((LEX / "drugs.json").read_text())
for e in data["entries"]:
    if any(l.get("src", "").startswith("promoted-") for l in e.get("lineage", {}).values()):
        print("  lineage:", e["canonical"], e["brands"][-2:], e["lineage"])
print("  sources:", data.get("sources"), "| version", data["version"])
ledger_text = (LEX / "ledger.json").read_text()
print("  ledger:", ledger_text.replace("\n", " ")[:900])
run("promote-apply", "--csv", str(reviewed), "--batch", "2026-11", "--reviewer", "Dr. Asha Rao", "--conflict-map", CONFLICT, "--confirm")
run("promote-candidates", "--out", str(ROOT / "data/promotion/2026-12/candidates.csv"), "--conflict-map", CONFLICT)
os.environ["PROMOTION_LEDGER_PEPPER"] = "a-different-pepper-123456"
run("promote-candidates", "--out", str(ROOT / "data/promotion/x/c.csv"), "--conflict-map", CONFLICT)
os.environ.pop("PROMOTION_LEDGER_PEPPER")
run("promote-candidates", "--out", str(ROOT / "data/promotion/x/c.csv"), "--conflict-map", CONFLICT)
os.environ["PROMOTION_LEDGER_PEPPER"] = PEPPER
# an unreadable 4th clinic -> INCOMPLETE marker, apply refused
clinics.provision_clinic("delta", "Delta Clinic")
(clinic_dir("delta") / "app.db").write_bytes(b"not a database" * 100)
inc = ROOT / "data/promotion/2026-12/c2.csv"
run("promote-candidates", "--out", str(inc), "--conflict-map", CONFLICT)
print("  marker exists:", Path(str(inc) + ".INCOMPLETE").exists())
run("promote-apply", "--csv", str(inc), "--batch", "2026-12", "--reviewer", "Dr. Asha Rao", "--conflict-map", CONFLICT, "--confirm")
after = digests()
print("\n  clinic DB bytes unchanged (alpha/beta/gamma):", {k: before[k] == after[k] for k in before})
print("  live drugs.json unchanged:", hashlib.sha256(live_drugs.read_bytes()).hexdigest() == live_before)
blob = "\n".join(TRANSCRIPT) + ledger_text + review.read_text() + (LEX / "drugs.json").read_text()
for p in ROOT.rglob("*"):
    if p.is_file() and p.suffix in (".csv", ".json", ".INCOMPLETE", ".tmp"):
        blob += p.read_text(errors="replace")
print("  PHI/pepper scan:", {w: (w in blob) for w in ("Ravi", "Kulkarni", "Sunita", "alpha", "Alpha Clinic", "Murexol", PEPPER)})
print("  ROOT", ROOT)
