"""SYNTHETIC dosing reference for tests: invented, clinically meaningless numbers. Never copy into dosing.json."""
import json

def _e(name, strengths, forms, usual, cap, reviewed=True):
    return {"canonical": name, "strengths": strengths, "forms": forms, "source": "SYNTHETIC TEST DATA",
            "reviewed": reviewed, "adult": {"usual": usual, "freq": "once daily", "max_daily_mg": cap}}

FIXTURE = {"version": "test-1", "built_at": "2026-01-01", "entries": [
    _e("Paracetamol", ["500 mg", "650 mg", "1 g"], ["Tab.", "Syr."], "650 mg", 1500),
    _e("Prednisolone", ["5 mg", "10 mg", "20 mg"], ["Tab.", "Syr."], "10 mg", 30),
    _e("Digoxin", ["0.25 mg"], ["Tab."], "0.25 mg", 0.75),
    _e("Amlodipine", ["2.5 mg", "5 mg", "10 mg"], ["Tab."], "5 mg", 10, reviewed=False)]}

def use_fixture(monkeypatch, tmp_path, data=FIXTURE):
    """Point the dosing loader at a temp copy of ``data`` (it re-reads when the path changes)."""
    from doctor_dictation.core import dosing
    (tmp_path / "dosing.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")
