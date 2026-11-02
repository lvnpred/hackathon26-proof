"""Play the synthetic morning onto one episode."""

from __future__ import annotations

from app.morning.brownbag import duplicate_generics, read_strip
from app.morning.druglog import parse_drug_phrase
from app.morning.store import MorningStore
from app.morning.vitals import collect_facts, demo_readings, evaluate, template_card

DEMO_STRIPS = (
    ("metoprolol", "25 mg"),
    ("amlodipine", "5 mg"),
)
DEMO_PHRASE = "lignocaine two percent, five ml, local infiltration"


def play(store: MorningStore, episode_id: str, *, decision_tier: bool) -> dict:
    if store.get_episode(episode_id) is None:
        raise KeyError(episode_id)
    strips = [read_strip(name, strength) for name, strength in DEMO_STRIPS]
    for index, strip in enumerate(strips):
        store.append(episode_id, "brownbag.med_found", strip, ts_ms=index * 1000, tier="documentation")
    if decision_tier:
        for generic in duplicate_generics(strips):
            store.append(
                episode_id,
                "brownbag.same_drug_twice",
                {"generic": generic},
                ts_ms=5000,
                tier="decision",
            )
    store.append(
        episode_id,
        "count.pack_opened",
        {"item_type": "swab", "quantity": 20, "source": "scripted"},
        ts_ms=10_000,
    )
    parsed = parse_drug_phrase(DEMO_PHRASE)
    parsed["confirmed"] = True
    store.append(episode_id, "druglog.given", parsed, ts_ms=60_000)
    for offset in range(6):
        store.append(
            episode_id,
            "count.item_out",
            {"track_id": f"swab-{offset + 1}", "source": "scripted"},
            ts_ms=180_000 + offset * 1000,
        )
    readings = demo_readings()
    fired: dict[str, int] = {}
    card = None
    for reading in readings:
        store.append(
            episode_id,
            "vitals.reading",
            {
                "systolic": reading.systolic,
                "diastolic": reading.diastolic,
                "hr": reading.hr,
            },
            ts_ms=reading.ts_ms,
        )
        so_far = [row for row in readings if row.ts_ms <= reading.ts_ms]
        for fire in evaluate(so_far, last_fired=fired):
            fired[fire["rule_id"]] = fire["ts_ms"]
            if not decision_tier or fire["rule_id"] != "bp_drop_pct":
                continue
            facts = collect_facts(store.events(episode_id), reading.ts_ms)
            text = template_card(fire, facts)
            card = store.append(
                episode_id,
                "vitals.card",
                {"text": text, "wording": "template", "facts": facts, "rule_id": fire["rule_id"]},
                ts_ms=reading.ts_ms,
                tier="decision",
            )
            store.append(
                episode_id,
                "vitals.change",
                {"rule_id": fire["rule_id"], "drop_pct": fire["drop_pct"]},
                ts_ms=reading.ts_ms,
                tier="decision",
            )
    store.append(
        episode_id,
        "count.closing",
        {
            "opened": 20,
            "returned": 19,
            "unaccounted": 1,
            "detail": "1 swab unaccounted. The last frame is on the Count Guard screen.",
        },
        ts_ms=300_000,
    )
    return {"episode_id": episode_id, "card_id": None if card is None else card["id"]}
