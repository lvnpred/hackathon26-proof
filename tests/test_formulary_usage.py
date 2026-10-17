"""Usage ranking of the clinic formulary (plan I1-r1): hint order and the Spell it near-tie rule. Offline."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from doctor_dictation.core import formulary as F
from doctor_dictation.core import rowcheck
from doctor_dictation.core.candidates import suggest_candidates
from doctor_dictation.core.hints import build_hints

TODAY = date(2026, 10, 17)


@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())


def row(name, count, last_seen):
    """One db.formulary.list_active row."""
    return {"id": 0, "name": name, "generic": None, "confirm_count": count, "first_seen_at": last_seen,
            "last_seen_at": last_seen, "added_by": None}


def names(layer):
    return [n for n, _ in layer.items]


def test_usage_blends_the_count_with_recency_as_in_the_worked_example():
    rows = [row("Quillavex", 2, "2026-10-17T08:00:00Z"),          # list_active order: most recently seen first
            row("Zorbexin", 200, "2026-10-16T09:00:00Z"),
            row("Morvexa", 40, "2026-07-19T10:00:00Z")]
    assert [F.usage_score(r["confirm_count"], r["last_seen_at"], TODAY) for r in rows] == [1.584963, 7.476301, 0.669694]
    layer = F.ranked_layer(rows, TODAY)
    assert names(layer) == ["Zorbexin", "Quillavex", "Morvexa"]
    assert layer.usage_of(" ZORBEXIN ") == 7.476301 and layer.usage_of("Paracetamol") == 0.0
    assert F.HALF_LIFE_DAYS == 30


def test_ties_are_deterministic_and_odd_rows_neither_crash_nor_lead():
    same = [row("Zeta", 3, "2026-10-12T08:00:00Z"), row("Alfa", 3, "2026-10-12T08:00:00Z"),
            row("Beta", 3, "2026-10-12T09:00:00Z")]                  # one day, one count: equal scores
    assert names(F.ranked_layer(same, TODAY)) == ["Beta", "Alfa", "Zeta"]          # newer first, then the name key
    assert names(F.ranked_layer(list(reversed(same)), TODAY)) == ["Beta", "Alfa", "Zeta"]   # input order is irrelevant
    odd = [row("Future", 2, "2027-01-01T00:00:00Z"), row("Garbled", 9, "not a date"),
           row("Huge", 2**63 - 1, "2026-10-17T00:00:00Z"), row("Ancient", 10**6, "1990-01-01T00:00:00Z"),
           row("Nulls", None, None)]
    layer = F.ranked_layer(odd, TODAY)
    assert names(layer)[:2] == ["Huge", "Future"] and set(names(layer)[2:]) == {"Garbled", "Ancient", "Nulls"}
    assert (layer.usage_of("Huge"), layer.usage_of("Future")) == (63.0, 1.584963)     # no overflow; future = today
    assert layer.usage_of("Garbled") == layer.usage_of("Ancient") == layer.usage_of("Nulls") == 0.0


def test_hints_follow_usage_inside_the_same_caps_and_the_cache_version_follows_the_names_only():
    rows = [row(f"Drug{chr(97 + i)}x", i + 2, "2026-10-17T00:00:00Z") for i in range(11)]   # Drugax least used
    layer = F.ranked_layer(rows, TODAY)
    assert layer.hint_names() == [f"Drug{chr(97 + i)}x" for i in range(10, 0, -1)]      # the least used is left out
    assert layer.version == F.ClinicLayer(tuple((r["name"], "") for r in rows)).version    # usage is not in the key
    long = F.ranked_layer([row("W" * 50 + str(i), 10 - i, "2026-10-17T00:00:00Z") for i in range(4)], TODAY)
    assert long.hint_names() == ["W" * 50 + "0", "W" * 50 + "1"] and len(", ".join(long.hint_names())) <= F.HINT_CHARS
    cold = build_hints([], limit=70)
    F.activate(layer)
    assert build_hints([], limit=70)[:10] == layer.hint_names()
    F.activate(F.ranked_layer([], TODAY))
    assert F.active_layer() == F.ClinicLayer() and F.active_layer().version == "0" and build_hints([], limit=70) == cold

def test_the_loaded_layer_ranks_by_usage_and_a_removed_name_restarts_from_a_fresh_count(tmp_path, monkeypatch):
    from doctor_dictation import db as dbmod
    from doctor_dictation.api.formulary import load_layer
    from doctor_dictation.db import formulary as fdb
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))           # never the real dev database
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    docs = iter([dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(10)])
    today = date(2031, 3, 5)      # a fixed date, far from the real one: the pinned score cannot flake at midnight, and a load_layer
    monkeypatch.setattr("doctor_dictation.api.formulary._today", lambda: today)    # that ignored _today would see these rows as years old

    def confirm(name, times, days_ago):
        for _ in range(times):
            fdb.record_confirmation(conn, F.key(name), name, "", next(docs), None)
        conn.execute("UPDATE clinic_formulary SET last_seen_at = ? WHERE name_key = ?",
                     ((today - timedelta(days=days_ago)).isoformat() + "T08:00:00Z", F.key(name)))
        conn.commit()
    confirm("Zorbexin", 6, 3)
    confirm("Quillavex", 2, 0)
    assert [r["name"] for r in fdb.list_active(conn)] == ["Quillavex", "Zorbexin"]   # the Team list: most recent first
    assert names(load_layer()) == ["Zorbexin", "Quillavex"]                         # the hints: most used first
    assert load_layer().usage_of("Zorbexin") == F.usage_score(6, str(today - timedelta(days=3)), today) < F.usage_score(6, str(today), today)
    (zor,) = [r for r in fdb.list_active(conn) if r["name"] == "Zorbexin"]
    assert fdb.remove(conn, zor["id"]) == "Zorbexin"
    gone = load_layer()
    assert names(gone) == ["Quillavex"] and gone.usage_of("Zorbexin") == 0.0       # a removed name never ranks
    confirm("Zorbexin", 2, 0)                                                         # learned again from 2 new documents
    back = load_layer()
    assert back.usage_of("Zorbexin") == back.usage_of("Quillavex") == 1.584963       # the count restarted at 2, not 8
    assert names(back) == ["Quillavex", "Zorbexin"]                                  # equal usage, same time: name key
    conn.close()

def test_usage_reorders_only_the_clinic_names_inside_the_band():
    use = {"Cl-hi": 50.0, "Cl-mid": 5.0, "Cl-lo": 0.5, "Cl-far": 99.0}
    scored = [("Cl-lo", 1.0, True), ("Lexa", 0.99, False), ("Cl-mid", 0.98, True), ("Cl-hi", 0.971, True),
              ("Cl-far", 0.969, True), ("Lexb", 0.90, False)]
    assert F.BAND == 0.03
    assert F.tie_break(scored, lambda n: use.get(n, 0.0)) == ["Cl-hi", "Lexa", "Cl-mid", "Cl-lo", "Cl-far", "Lexb"]
    assert F.tie_break(scored, lambda n: 0.0) == [n for n, _s, _c in scored]          # no usage: today's order exactly
    assert F.tie_break([], lambda n: 1.0) == []


def test_spell_it_offers_the_clinic_names_and_usage_only_breaks_near_ties():
    unknown = {"name": "Dolvex", "lexicon_match": ""}
    assert suggest_candidates("Dolvex") == [] and rowcheck.suggestions(unknown) == []        # cold clinic: as today
    rows = [row("Dolvexa", 2, "2026-10-17T00:00:00Z"), row("Dolvexi", 30, "2026-10-15T00:00:00Z"),
            row("Dolmexa", 500, "2026-10-17T00:00:00Z")]
    F.activate(F.ClinicLayer(tuple((r["name"], "") for r in rows)))                          # no usage: score, then name
    assert rowcheck.suggestions(unknown) == ["Dolvexa", "Dolvexi", "Dolmexa"]
    F.activate(F.ranked_layer(rows, TODAY))
    assert rowcheck.suggestions(unknown) == ["Dolvexi", "Dolvexa", "Dolmexa"]    # 1.0 twins: more used first; 0.785 stays 3rd
    assert rowcheck.suggestions({"name": "Dolvexa", "lexicon_match": ""})[0] == "Dolvexa"    # a clinic row's own name leads
    F.activate(F.ranked_layer([row("Zorbexin", 200, "2026-10-17T00:00:00Z"),
                               row("Zorbexim", 2, "2026-10-17T00:00:00Z")], TODAY))
    assert rowcheck.suggestions({"name": "Zorbexem", "lexicon_match": ""}) == ["Zorbexim", "Zorbexin"]   # 1.0 vs 0.79
    today = rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})
    F.activate(F.ranked_layer([row("Prednisome", 900, "2026-10-17T00:00:00Z")], TODAY))
    assert rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"}) == today   # a lexicon row: unchanged
    assert rowcheck.suggestions({"name": "Crocin", "lexicon_match": "Paracetamol"})[0] == "Paracetamol"  # did you mean


def test_check_row_returns_the_ranked_list_and_keeps_the_dictated_name(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation import db as dbmod
    from doctor_dictation.api.app import create_app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))
    seen = datetime.now(timezone.utc).date().isoformat() + "T08:00:00Z"
    with TestClient(create_app()) as client:                          # start-up migrates the temp database
        conn = dbmod.get_conn()
        for name, count in (("Dolvexa", 2), ("Dolvexi", 30), ("Dolmexa", 500)):
            conn.execute("INSERT INTO clinic_formulary(name_key, name, confirm_count, first_seen_at, last_seen_at)"
                         " VALUES (?, ?, ?, ?, ?)", (F.key(name), name, count, seen, seen))
        conn.commit()
        conn.close()
        r = client.post("/api/v1/rx/check-row", json={"row": {"name": "Dolvex"}, "transcript": "tablet dolvex daily"})
    got = r.json()
    assert r.status_code == 200 and got["suggestions"] == ["Dolvexi", "Dolvexa", "Dolmexa"]
    assert (got["row"]["name"], got["row"]["status"]) == ("Dolvex", "unknown-medicine")   # offered, never applied


def test_the_page_shows_the_suggestions_in_the_order_the_server_sends():
    js = (Path(__file__).resolve().parents[1] / "frontend" / "rxview.js").read_text(encoding="utf-8")
    line = next(t for t in js.splitlines() if "res.suggestions" in t)
    assert ".slice(0, 6)" in line and ".sort(" not in line and ".reverse(" not in line
    assert 'list.forEach((s) => { const b = btn("sug", "sug", s)' in js and '"Did you mean"' in js


def test_suggestions_never_leak_another_clinics_names():
    import contextvars
    row_ = {"name": "Dolvex", "lexicon_match": ""}

    def ask(layer):                                   # each clinic's request runs in its own context, as in the app
        def run():
            F.activate(layer)
            return rowcheck.suggestions(row_)
        return contextvars.copy_context().run(run)
    a = ask(F.ranked_layer([row("Dolvexa", 5, "2026-10-17T00:00:00Z")], TODAY))
    b = ask(F.ranked_layer([row("Dolvexi", 5, "2026-10-17T00:00:00Z")], TODAY))
    none = ask(F.ClinicLayer())
    assert (a, b, none) == (["Dolvexa"], ["Dolvexi"], [])
    assert rowcheck.suggestions(row_) == []           # the surrounding context still has no layer


def test_the_band_edge_is_inclusive_and_a_weak_sound_alike_is_never_offered():
    use = {"Cl-edge": 9.0, "Cl-top": 1.0}
    edge = [("Cl-top", 1.0, True), ("Cl-edge", 0.97, True)]                     # exactly BAND below the top: inside
    assert F.tie_break(edge, lambda n: use.get(n, 0.0)) == ["Cl-edge", "Cl-top"]
    out = [("Cl-top", 1.0, True), ("Cl-edge", 0.969, True)]                     # a hair further: outside, no swap
    assert F.tie_break(out, lambda n: use.get(n, 0.0)) == ["Cl-top", "Cl-edge"]
    F.activate(F.ranked_layer([row("Dolxyzq", 900, "2026-10-17T00:00:00Z")], TODAY))   # far from "Dolvex": under 0.78
    assert 0.0 < F.similarity("Dolvex", "Dolxyzq") < 0.78
    assert rowcheck.suggestions({"name": "Dolvex", "lexicon_match": ""}) == []
