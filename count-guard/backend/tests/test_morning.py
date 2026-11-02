"""Morning modules from the hackathon pack. No clinic-app code."""

from __future__ import annotations

import threading

from app.morning.druglog import parse_drug_phrase
from app.morning.vitals import choose_wording, demo_readings, evaluate, wording_ok


PHRASES = [
    ("lignocaine two percent, five ml, local infiltration", "lignocaine", 5, "ml", "2%", "local infiltration", True),
    ("fentanyl 50 micrograms iv", "fentanyl", 50, "mcg", None, "iv", True),
    ("ceftriaxone one gram intravenous", "ceftriaxone", 1, "g", None, "iv", True),
    ("ondansetron 4 mg iv", "ondansetron", 4, "mg", None, "iv", True),
    ("xyzolone 10 mg oral", None, 10, "mg", None, "oral", False),
]


def test_five_drug_phrases():
    for text, generic, amount, unit, strength, route, grounded in PHRASES:
        parsed = parse_drug_phrase(text)
        assert parsed["generic"] == generic
        assert parsed["amount"] == amount
        assert parsed["unit"] == unit
        assert parsed["strength"] == strength
        assert parsed["route"] == route
        assert parsed["grounded"] is grounded
        assert parsed["confirmed"] is False


def test_bp_drop_fires_once_per_cooldown():
    readings = demo_readings()
    first = evaluate(readings)
    drop = [row for row in first if row["rule_id"] == "bp_drop_pct"]
    assert len(drop) == 1
    assert drop[0]["drop_pct"] == 28
    assert drop[0]["span_min"] == 4
    assert drop[0]["hr_flat"] is True
    second = evaluate(readings, last_fired={"bp_drop_pct": readings[-1].ts_ms})
    assert [row for row in second if row["rule_id"] == "bp_drop_pct"] == []


def test_wording_check_keeps_the_template():
    template = "BP 86/50, down 28% in 4 min. lignocaine 5 ml 3 min ago (voice log)."
    assert wording_ok("BP 86/50, down 28% in 4 min. lignocaine 5 ml.", template)
    bad_number = "BP 86/50, down 40% in 4 min."
    advice = "Consider giving a fluid bolus."
    assert wording_ok(bad_number, template) is False
    assert wording_ok(advice, template) is False
    text, source = choose_wording(template, advice)
    assert source == "template"
    assert text == template


def test_store_reads_are_safe_across_threads(tmp_path):
    # The ward screen reads every episode at once; one shared connection must not garble a read.
    from app.morning.store import MorningStore

    store = MorningStore(tmp_path / "t.db")
    ids = [store.create_episode("x")["id"] for _ in range(3)]
    for episode_id in ids:
        for k in range(30):
            store.append(episode_id, "t", {"k": k}, ts_ms=k)
    errors = []

    def read(episode_id):
        for _ in range(500):
            try:
                assert len(store.events(episode_id)) == 30
                assert store.get_episode(episode_id)
                assert len(store.list_episodes()) == 3
            except BaseException as exc:  # noqa: BLE001 - any failure is the finding
                errors.append(repr(exc))

    threads = [threading.Thread(target=read, args=(episode_id,)) for episode_id in ids for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
