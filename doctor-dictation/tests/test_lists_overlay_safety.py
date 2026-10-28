"""The clinic list routes after the plan PQ-f final fix: a hidden drug never comes back as its look-alike through the
app's own routes (C1), two adds spelt alike are refused (I1), and a row a later shipped list conflicts with is flagged
with its reason instead of going quietly inert (I2). Offline; the world of test_users_routes."""
from contextlib import closing

import pytest

from doctor_dictation.core import determinism as D
from doctor_dictation.core import overlay
from doctor_dictation.db import overlay as odb
from test_lists_routes import items, post
from test_users_routes import H, _conn, _signed_in, world  # noqa: F401

COMBO = "Aceclofenac + Paracetamol"


@pytest.fixture(autouse=True)
def _fresh_format_cache():
    D._FORMAT_CACHE.clear()
    yield
    D._FORMAT_CACHE.clear()


def _store(slug, key, action, data, base_sha=""):
    """A row written straight to the clinic's database, as an older release (or an older shipped list) left it."""
    with closing(_conn(slug)) as c:
        odb.upsert(c, "medicine", key, action, data, base_sha, "admin", None)


# ---- C1: end to end --------------------------------------------------------------------------------------------------

def test_format_after_hiding_escitalopram_gives_no_citalopram(world):
    with _signed_in("dr.rao") as (rao,):
        before = rao.post("/api/format", json={"transcript": "tab escitalopram 10 mg once daily"}, headers=H).json()
        assert before["structured"]["rx"][0]["lexicon_match"] == "Escitalopram"
        assert post(rao, "hide", "escitalopram").status_code == 200
        got = rao.post("/api/format", json={"transcript": "tab escitalopram 10 mg once daily"}, headers=H).json()
        assert "Citalopram" not in str(got), got
        (row,) = got["structured"]["rx"]
        assert (row["name"].casefold(), row["status"], row["lexicon_match"]) == ("escitalopram", "unknown-medicine", "")
        typed = {"form": "Tab.", "name": "Escitalopram", "strength": "10 mg", "dose": "1-0-0", "timing": "",
                 "duration": "", "instructions": ""}
        checked = rao.post("/api/v1/rx/check-row", json={"row": typed, "transcript": "tab escitalopram 10 mg"},
                           headers=H).json()["row"]
        assert (checked["status"], checked["lexicon_match"], checked["did_you_mean"]) == ("unknown-medicine", "", "")
    with _signed_in("dr.iyer") as (iyer,):                       # another clinic still has it
        other = iyer.post("/api/format", json={"transcript": "tab escitalopram 10 mg once daily"}, headers=H).json()
        assert other["structured"]["rx"][0]["lexicon_match"] == "Escitalopram"


# ---- I1: two adds spelt alike -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("twin", ["Zerodol P", "Zerodol-P."])
def test_a_second_add_spelt_like_the_first_is_refused(world, twin):
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "add", "zerodol-p", {"name": "Zerodol-P", "generic": COMBO}).status_code == 200
        r = post(rao, "add", twin.casefold(), {"name": twin, "generic": COMBO + " + Chlorzoxazone"})
        assert r.status_code == 409, r.text
        assert r.json()["error"] == f"'{twin}' is already on your list as Zerodol-P: edit it"
        assert set(items(rao)) >= {"zerodol-p"} and twin.casefold() not in items(rao)


def test_an_edit_of_the_clinics_own_add_is_not_its_own_twin(world):
    with _signed_in("dr.rao") as (rao,):
        assert post(rao, "add", "zerodol-p", {"name": "Zerodol-P", "generic": COMBO}).status_code == 200
        r = post(rao, "edit", "zerodol-p", {"name": "Zerodol-P", "generic": COMBO, "aliases": ["Zerodolp"]})
        assert r.status_code == 200, r.text


# ---- I2: a row a later shipped list conflicts with -------------------------------------------------------------------

def test_an_inert_row_is_flagged_with_its_reason_and_keep_mine_says_why(world):
    _store("rao", "crocinol", "add", {"name": "Crocinol", "generic": "Crocin"})     # "Crocin" is now a shipped brand
    with _signed_in("dr.rao") as (rao,):
        it = items(rao)["crocinol"]
        assert (it["badge"], it["flag"]) == ("clinic-added", "shipped-changed")
        assert "'Crocin' is a brand of Paracetamol" in it["flag_reason"]
        assert rao.get("/api/v1/lists/medicine", headers=H).json()["flags"] >= 1
        r = post(rao, "keep-mine", "crocinol")
        assert r.status_code == 409 and "'Crocin' is a brand of Paracetamol" in r.json()["error"]
        typed = {"form": "Tab.", "name": "Crocinol", "strength": "", "dose": "1-0-0", "timing": "", "duration": "",
                 "instructions": ""}
        row = rao.post("/api/v1/rx/check-row", json={"row": typed, "transcript": "tab crocinol"}, headers=H).json()["row"]
        assert (row["status"], row["lexicon_match"], row["did_you_mean"]) == ("unknown-medicine", "", "")
        r = post(rao, "take-new", "crocinol")
        assert r.status_code == 200 and "crocinol" not in items(rao)


def test_an_inert_edit_keeps_its_flag_until_reset(world):
    shipped = next(e for e in D.shipped_lexicon() if e["canonical"] == "Aceclofenac")
    _store("rao", "aceclofenac", "edit", {"brands": ["Zerodol", "Paracetamol"]}, overlay.entry_sha(shipped))
    with _signed_in("dr.rao") as (rao,):
        it = items(rao)["aceclofenac"]
        assert it["flag"] == "shipped-changed" and it["flag_reason"]
        assert post(rao, "keep-mine", "aceclofenac").status_code == 409
        assert post(rao, "reset", "aceclofenac").status_code == 200
        assert items(rao)["aceclofenac"]["flag"] == "" and items(rao)["aceclofenac"]["flag_reason"] == ""
