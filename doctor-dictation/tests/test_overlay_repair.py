"""The AI repair path never brings back a look-alike of a drug the clinic removed (plan PQ-f final fix, C1 repair path).

With Escitalopram hidden, the repair prompt used to offer "Sound-alike names in the medicine list: Citalopram", and a
"Citalopram" row then grounded VERIFIED because "citalopram" is heard inside the dictated "escitalopram". Now no
candidate is offered for a removed name (or a near spelling of one), and a name is never heard inside a removed name.
Offline: the LLM is a stub over httpx; the single-clinic database is a temp file (conftest)."""
import json
import re
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism as D
from doctor_dictation.core import overlay, overlay_state, rowcheck
from doctor_dictation.core.candidates import scored_candidates, scored_spellings, suggest_candidates
from doctor_dictation.core.repair import build_repair_message, UNKNOWN_MEDICINE_TEXT
from doctor_dictation.db import overlay as odb

TRANSCRIPT = "tab escitalopram 10 mg once daily"
OFFERED = re.compile(r"Sound-alike names in the medicine list: ([^\n]+)")


@pytest.fixture(autouse=True)
def _own_overlay():
    before = overlay_state._active.get()
    D._FORMAT_CACHE.clear()
    yield
    overlay_state._active.set(before)
    D._FORMAT_CACHE.clear()


def _entry(canon):
    return next(e for e in D.shipped_lexicon() if e["canonical"] == canon)


def _hide(canon):
    e = _entry(canon)
    return overlay.state_from_rows([{"kind": "medicine", "entry_key": overlay.entry_key_of(e), "action": "hide",
                                     "data": {}, "base_sha": overlay.entry_sha(e)}])


def _rx(name):
    return {"form": "Tab.", "name": name, "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "",
            "instructions": ""}


# ---- layer 1: no candidate is offered for a removed name --------------------------------------------------------------

def test_without_an_overlay_escitalopram_has_its_sound_alikes():
    assert "Citalopram" in suggest_candidates("Escitalopam", k=3)


@pytest.mark.parametrize("name", ["Escitalopram", "escitalopram", "Escitalopam", "Escitaloprem"])
def test_a_removed_name_or_its_near_spelling_gets_no_candidates(name):
    overlay.activate(_hide("Escitalopram"))
    assert suggest_candidates(name) == [] and scored_candidates(name) == [] and scored_spellings(name, 40) == []
    issue = f"rx[0] '{name}': {UNKNOWN_MEDICINE_TEXT} (447 entries)"
    assert "Sound-alike" not in build_repair_message([issue], TRANSCRIPT)
    row = {"name": name, "lexicon_match": ""}
    assert rowcheck.suggestions(row) == [] and rowcheck.options(row)[1] == 0


def test_a_listed_name_near_a_removed_one_keeps_its_candidates():
    overlay.activate(_hide("Escitalopram"))
    assert suggest_candidates("Citalopram")[0] == "Citalopram"
    assert suggest_candidates("Citalopam")[0] == "Citalopram"


# ---- layer 2: a drug is never heard inside a removed name -------------------------------------------------------------

def test_citalopram_is_not_heard_inside_a_dictated_escitalopram_once_escitalopram_is_hidden():
    overlay.activate(_hide("Escitalopram"))
    norm = D.normalize_transcript(TRANSCRIPT)
    (row,), _ = D.ground_rx([_rx("Citalopram")], norm, TRANSCRIPT)
    assert row["status"] != "verified" and row["status"] == "unverified-name", row
    grounded = rowcheck.ground_one(_rx("Citalopram"), TRANSCRIPT, norm)
    assert grounded["status"] == "unverified-name"


@pytest.mark.parametrize("transcript", ["tab citalopram 10 mg once daily",
                                        "tab escitalopram 10 mg and tab citalopram 10 mg once daily"])
def test_a_really_dictated_citalopram_still_verifies(transcript):
    for state in (overlay.OverlayState(), _hide("Escitalopram")):
        overlay.activate(state)
        if state.version == "0" and "escitalopram" in transcript:
            continue
        norm = D.normalize_transcript(transcript)
        assert D._ground_row("Citalopram", "10 mg", norm.lower())[:2] == ("verified", "Citalopram"), state.version
        (row,), _ = D.ground_rx([_rx("Citalopram")], norm, transcript)
        # the curated Citalopram/Escitalopram pair still asks the doctor while both are listed: one tap, never unknown
        assert row["lexicon_match"] == "Citalopram" and row["status"] in ("verified", "lookalike-check"), row


def test_without_an_overlay_nothing_changes_for_citalopram_in_escitalopram():
    (row,), _ = D.ground_rx([_rx("Citalopram")], TRANSCRIPT, TRANSCRIPT)
    assert row["lexicon_match"] == "Citalopram"     # today's behaviour without a removed name: heard (look-alike rules apply)


def test_a_clinics_own_learned_name_is_still_heard_as_itself():
    overlay.activate(_hide("Escitalopram"))
    assert D._name_in_transcript("Escitalopram", "tab escitalopram 10 mg")
    assert not D._name_in_transcript("Citalopram", "tab escitalopram 10 mg")
    assert not D._name_in_transcript("Citalopram", "tab escitalopram. 10 mg")


@pytest.mark.parametrize("hidden, listed", [("Magnesium", "Magnesium Hydroxide"), ("Ferrous Ascorbate", "Ferrous Fumarate"),
                                             ("Calcium Carbonate", "Calcium Carbonate + Cholecalciferol"),
                                             ("Doxylamine", "Doxylamine + Pyridoxine")])
def test_a_listed_longer_name_that_shares_words_with_a_removed_one_still_verifies(hidden, listed):
    overlay.activate(_hide(hidden))
    transcript = f"tab {listed.lower()} once daily"
    norm = D.normalize_transcript(transcript)
    assert D._name_in_transcript(listed, norm.lower())
    assert D._ground_row(listed, "", norm.lower())[:2] == ("verified", listed)


# ---- through the repair loop ------------------------------------------------------------------------------------------

def _stub_llm(monkeypatch, second, first="Escitalopram"):
    """The first draft names ``first``; the repair answer is ``second(repair message)``. Records every message list."""
    calls = {"messages": []}

    class Resp:
        status_code = 200

        def __init__(self, draft):
            self.text = json.dumps(draft)
            self._draft = draft

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(self._draft)}}]}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, **kw):
            msgs = kw["json"]["messages"]
            calls["messages"].append(msgs)
            if len(calls["messages"]) == 1:
                return Resp({"rx": [_rx(first)]})
            return Resp({"rx": [_rx(second(msgs[-1]["content"]))]})

    monkeypatch.setattr("httpx.AsyncClient", Client)
    override_settings(monkeypatch, openai_api_key="dummy-key", llm_provider="openai")
    return calls


def _hide_in_db(canon):
    e = _entry(canon)
    dbmod.init_db()
    with closing(dbmod.get_conn()) as c:
        odb.upsert(c, "medicine", overlay.entry_key_of(e), "hide", {}, overlay.entry_sha(e), "admin", None)


def _format():
    r = TestClient(M.app).post("/api/format", json={"transcript": TRANSCRIPT})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_repair_loop_offers_no_look_alike_and_a_picked_one_never_verifies(monkeypatch):
    _hide_in_db("Escitalopram")

    def pick_offered(repair):                          # an AI that takes the first offered candidate, if any
        m = OFFERED.search(repair)
        return m.group(1).split(", ")[0] if m else "Escitalopram"
    calls = _stub_llm(monkeypatch, pick_offered)
    got = _format()
    assert len(calls["messages"]) >= 2
    assert all("Sound-alike" not in msgs[-1]["content"] for msgs in calls["messages"][1:])
    (row,) = got["structured"]["rx"]
    assert (row["name"], row["status"], row["lexicon_match"]) == ("Escitalopram", "unknown-medicine", "")


def test_an_ai_that_names_the_look_alike_on_its_own_is_not_verified(monkeypatch):
    _hide_in_db("Escitalopram")
    _stub_llm(monkeypatch, lambda _repair: "Citalopram", first="Citalopram")
    (row,) = _format()["structured"]["rx"]
    assert (row["name"], row["status"]) == ("Citalopram", "unverified-name"), row     # not heard: the doctor confirms


def test_with_nothing_hidden_the_loop_still_offers_and_verifies(monkeypatch):
    def pick_offered(repair):
        m = OFFERED.search(repair)
        return m.group(1).split(", ")[0] if m else "Escitalopram"
    calls = _stub_llm(monkeypatch, pick_offered)
    (row,) = _format()["structured"]["rx"]
    assert len(calls["messages"]) == 1                 # Escitalopram is on the list: no repair round at all
    assert row["lexicon_match"] == "Escitalopram"
