"""The clinic overlay feeds name matching (plan PQ-f, Task 5): load_lexicon is the clinic's effective list, every route
that grounds medicines activates it, and no cache answers across clinics or across a list edit. Offline, temp DBs."""
import contextvars
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from authorship_fixtures import H, as_user, clinic_conn
from doctor_dictation import accounts, clinics
from doctor_dictation import db as dbmod
from doctor_dictation.api import formulary as route_mod
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D
from doctor_dictation.core import formulary as F
from doctor_dictation.core import overlay, overlay_state, rowcheck
from doctor_dictation.db import overlay as odb

GENERIC = "Aceclofenac + Paracetamol"
ADD = {"kind": "medicine", "entry_key": "zerodol-p", "action": "add",
       "data": {"name": "Zerodol-P", "generic": GENERIC}, "base_sha": ""}
HIDE = {"kind": "medicine", "entry_key": "acarbose", "action": "hide", "data": {}, "base_sha": ""}
TRANSCRIPT = "tab zerodol-p twice daily for 5 days"
ROW = {"form": "Tab.", "name": "Zerodol-P", "strength": "", "dose": "1-0-1", "timing": "", "duration": "5 days",
       "instructions": "", "status": "unknown-medicine"}


@pytest.fixture(autouse=True)
def _own_overlay():
    """A test that activates an overlay must not leave it on the test thread's context for the next test."""
    before = overlay_state._active.get()
    yield
    overlay_state._active.set(before)


def _ground(name="Zerodol-P", transcript=TRANSCRIPT):
    (row,), _ = D.ground_rx([{"name": name, "strength": ""}], transcript)
    return row


# ---- load_lexicon and lexicon_identity -------------------------------------------------------------------------------

def test_without_overlay_load_lexicon_is_the_shipped_list():
    assert D.load_lexicon() is D.shipped_lexicon()
    assert overlay.shipped("medicine") is D.shipped_lexicon()           # registered at import


def test_a_clinic_added_brand_grounds_verified_with_the_clinic_generic():
    assert _ground()["status"] != "verified"
    overlay.activate(overlay.state_from_rows([ADD]))
    row = _ground()
    assert (row["status"], row["lexicon_match"], row["generic"]) == ("verified", GENERIC, GENERIC)
    assert D.load_lexicon() is D.load_lexicon() is not D.shipped_lexicon()   # one object per overlay version


def test_a_hidden_entry_reads_unknown():
    assert _ground("Acarbose", "tab acarbose 25 mg once daily")["status"] != "unknown-medicine"
    overlay.activate(overlay.state_from_rows([HIDE]))
    assert _ground("Acarbose", "tab acarbose 25 mg once daily")["status"] == "unknown-medicine"


def test_lexicon_identity_changes_with_the_overlay_version():
    empty = D.lexicon_identity()
    assert empty == f"{D.lexicon_version()}+0"
    overlay.activate(overlay.state_from_rows([ADD]))
    added = D.lexicon_identity()
    overlay.activate(overlay.state_from_rows([ADD, HIDE]))
    assert len({empty, added, D.lexicon_identity()}) == 3
    assert D.lexicon_version() == empty.split("+")[0]                  # health and engine strings: the shipped version


def test_the_lookalike_verdict_is_not_cached_from_another_clinics_list(monkeypatch):
    """formulary._twin is an lru_cache: keyed on the shipped version alone, clinic A's answer would serve clinic B."""
    seen = []
    monkeypatch.setattr(F, "suggest_candidates", lambda name, k, **_kw: seen.append(D.lexicon_identity()) or [])
    F._twin.cache_clear()
    F._lexicon_twin("Zorbexin")
    overlay.activate(overlay.state_from_rows([ADD]))
    F._lexicon_twin("Zorbexin")
    assert len(seen) == 2 and seen[0] != seen[1]


def test_health_reads_the_shipped_list_without_an_overlay_warning(monkeypatch):
    monkeypatch.setattr(overlay_state, "_warned", False)
    ctx = contextvars.Context()
    ctx.run(F.mark_request_scoped)
    assert ctx.run(D.lexicon_size) == len(D.shipped_lexicon())
    assert overlay_state._warned is False


# ---- threads ---------------------------------------------------------------------------------------------------------

def _context(state) -> contextvars.Context:
    ctx = contextvars.Context()
    ctx.run(overlay.activate, state)
    return ctx


def _observe():
    row = _ground()
    return (row["status"], row["generic"], D.correct_drugs("tab zerodolp"),
            tuple(sorted(rowcheck.did_you_mean("Zerodolp", D.RX_UNKNOWN_MEDICINE).items())))


def test_interleaved_threads_never_cross():
    contexts = {"add": _context(overlay.state_from_rows([ADD])), "empty": _context(overlay.OverlayState())}
    expected = {k: ctx.copy().run(_observe) for k, ctx in contexts.items()}
    assert expected["add"][:2] == ("verified", GENERIC) and expected["empty"][0] != "verified"
    assert expected["add"] != expected["empty"]
    jobs = ["add" if n % 2 else "empty" for n in range(200)]
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(lambda k: (k, contexts[k].copy().run(_observe)), jobs))
    crossed = [(k, g) for k, g in got if g != expected[k]]
    assert not crossed, crossed[:3]


# ---- correct_drugs after a clinic rename -----------------------------------------------------------------------------

def test_a_renamed_multi_word_generic_is_not_doubled_when_its_old_name_is_dictated():
    """The old canonical is only an alias now, and "Magnesium Citrate" (a shorter alias) matches inside the new name."""
    old = "Potassium Magnesium Citrate"
    (entry,) = [e for e in D.shipped_lexicon() if e["canonical"] == old]
    rename = {"kind": "medicine", "entry_key": F.key(old), "action": "edit",
              "data": {"generic": f"{old} Renamed"}, "base_sha": overlay.entry_sha(entry)}
    assert D.correct_drugs(f"syr {old.lower()} 15 ml") == f"syr {old} 15 ml"
    overlay.activate(overlay.state_from_rows([rename]))
    for said in (old.lower(), old, f"{old} Renamed", "magnesium citrate"):
        assert D.correct_drugs(f"syr {said} 15 ml") == f"syr {old} Renamed 15 ml", said


def test_every_multi_word_alias_on_the_shipped_list_writes_its_name_once():
    """Each spaced alias, dictated alone, gives its text exactly once (no shorter alias re-matches inside it)."""
    amap, _amb = D._maps()
    doubled = []
    for alias in sorted(a for a in amap if " " in a):
        out = D.correct_drugs(f"tab {alias} daily")
        if out.lower().count(amap[alias].lower()) > 1:
            doubled.append((alias, out))
    assert not doubled, doubled[:5]


# ---- routes ----------------------------------------------------------------------------------------------------------

def _offline(monkeypatch):
    def fake(structured, meta, out_path, layout=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"%PDF-fake")
        return Path(out_path)
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", fake)
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [ROW]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    D._FORMAT_CACHE.clear()


@pytest.fixture()
def team(multi, monkeypatch):
    _offline(monkeypatch)
    ids = {}
    for slug in ("rao", "iyer"):
        clinics.provision_clinic(slug, f"{slug.title()} Clinic")
        ids[slug], _ = accounts.create_user(slug, f"adm.{slug}", role="admin", password="a-long-password-1")
        with clinic_conn(slug) as c:
            c.execute("UPDATE users SET must_change_password = 0")
            c.commit()
    app = create_app()
    with TestClient(app):
        yield {"ids": ids, **{s: as_user(TestClient(app), ids[s], s) for s in ids}}


def _add_in(slug, data=ADD["data"]):
    with clinic_conn(slug) as c:
        odb.upsert(c, "medicine", "zerodol-p", "add", data, "", "admin", None)


def _format(client):
    return client.post("/api/format", json={"transcript": TRANSCRIPT}, headers=H).json()


def _check(client):
    return client.post("/api/v1/rx/check-row", json={"row": dict(ROW), "transcript": TRANSCRIPT}, headers=H).json()["row"]


def test_format_cache_misses_after_a_list_edit(team):
    rao, iyer = team["rao"], team["iyer"]
    assert _format(rao)["cached"] is False and _format(rao)["cached"] is True
    _add_in("rao")
    got = _format(rao)
    assert got["cached"] is False and got["structured"]["rx"][0]["status"] == "verified"
    assert _format(rao)["cached"] is True
    other = _format(iyer)                                     # same transcript, other clinic: never the same answer
    assert other["cached"] is False and other["structured"]["rx"][0]["status"] != "verified"
    _add_in("rao", {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol + Serratiopeptidase"})
    assert _format(rao)["cached"] is False                    # an edit of the same row is a new version too


def test_check_row_route_sees_the_overlay(team):
    _add_in("rao")
    for _ in range(2):                                        # alternate, so a leaked ContextVar would show
        mine, theirs = _check(team["rao"]), _check(team["iyer"])
        assert (mine["status"], mine["generic"]) == ("verified", GENERIC)
        assert theirs["status"] != "verified"


def test_save_regrounds_with_the_overlay(team):
    _add_in("rao")
    body = {"structured": {"patientName": "Anita", "ageSex": "40 / F", "opNo": "",
                           "rx": [{**ROW, "status": "verified", "lexicon_match": GENERIC}]}, "confirmed_rows": []}
    r = team["rao"].post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    stored = team["rao"].get(f"/api/v1/documents/{r.json()['document_id']}").json()["structured"]["rx"][0]
    assert (stored["status"], stored["generic"]) == ("verified", GENERIC)


def _document(conn, n):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, f"Patient {n}", "50 / F", f"OP-{n}"),
                                 op_no=f"OP-{n}", status="finalized")
    return dbmod.save_document(conn, eid, f"sha-{n}", {"patientName": f"Patient {n}", "rx": []},
                               finalized_at=dbmod._utcnow())


def test_a_pending_row_does_not_reach_the_lexicon(team):
    with clinic_conn("rao") as c:
        odb.record_confirmation(c, "medicine", "zerodol-p", "add", ADD["data"], "", _document(c, 1), None)
    assert _check(team["rao"])["status"] != "verified"
    with clinic_conn("rao") as c:
        assert odb.record_confirmation(c, "medicine", "zerodol-p", "add", ADD["data"], "", _document(c, 2), None) == 2
    assert _check(team["rao"])["status"] == "verified"


SPIES = [("/api/format", "doctor_dictation.api.format.validate_structured", {"transcript": TRANSCRIPT}),
         ("/api/v1/correct", "doctor_dictation.api.format.validate_structured",
          {"transcript": "", "current_form": {"patientName": "A", "rx": [dict(ROW)]}}),
         ("/api/v1/documents", "doctor_dictation.api.persistence.validate_structured",
          {"structured": {"patientName": "A", "ageSex": "", "opNo": "", "rx": [dict(ROW)]}, "confirmed_rows": [0]}),
         ("/api/v1/rx/check-row", "doctor_dictation.api.rx.ground_one", {"row": dict(ROW), "transcript": TRANSCRIPT})]


@pytest.mark.parametrize("path,target,body", SPIES, ids=[s[0] for s in SPIES])
def test_every_route_that_grounds_medicines_runs_under_the_clinic_overlay(team, monkeypatch, path, target, body):
    _add_in("rao")
    with clinic_conn("rao") as c:
        want = overlay.state_from_rows(odb.list_rows(c, "medicine")).version
    seen = []
    mod, name = target.rsplit(".", 1)
    real = getattr(__import__(mod, fromlist=[name]), name)
    monkeypatch.setattr(target, lambda *a, **k: seen.append(overlay.active().version) or real(*a, **k))
    assert team["rao"].post(path, json=body, headers=H).status_code == 200
    assert seen and set(seen) == {want}, (path, seen)


def test_transcribe_builds_its_hints_under_the_clinic_overlay(team, monkeypatch):
    from doctor_dictation.api import stt as stt_mod
    from doctor_dictation.providers.stt.base import Transcript
    _add_in("rao")
    seen = []

    class Recorder:
        name = "recorder"
        available = staticmethod(lambda: True)

        async def transcribe(self, audio, filename, hints=()):
            return Transcript(text="hello", engine="recorder")
    monkeypatch.setattr(stt_mod, "make_stt", lambda settings: Recorder())
    monkeypatch.setattr(stt_mod, "build_hints", lambda *a: seen.append(overlay.active().version) or [])
    override_settings(monkeypatch, stt_use_hints=True, stt_hint_limit=8)
    r = team["rao"].post("/api/transcribe", files={"audio": ("n.webm", b"RAW", "audio/webm")}, headers=H)
    assert r.status_code == 200 and seen and seen[0] != "0"


def test_a_database_failure_while_loading_the_overlay_means_the_shipped_list(team, monkeypatch, caplog):
    _add_in("rao")

    def boom(conn, kind, **k):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(odb, "list_rows", boom)
    with caplog.at_level("WARNING", logger=route_mod.__name__):
        assert _check(team["rao"])["status"] != "verified"
    assert any("overlay" in r.getMessage() for r in caplog.records)
