"""Trend rules, fact collection, and the wording check.

The card repeats numbers already on the timeline. It does not say what to do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.morning.lexicon import known_names

WINDOW_MS = 5 * 60_000
COOLDOWN_MS = 3 * 60_000
BANNED = re.compile(
    r"\b(give|start|administer|increase|reduce|consider|should|recommend|re-explore|x-ray)\b",
    re.I,
)


@dataclass(frozen=True)
class Reading:
    ts_ms: int
    systolic: int
    diastolic: int
    hr: int


def demo_readings() -> list[Reading]:
    """120 → 86 over 4 minutes. Heart rate rises less than 10 percent."""
    return [
        Reading(0, 120, 70, 70),
        Reading(60_000, 118, 70, 72),
        Reading(180_000, 110, 64, 74),
        Reading(240_000, 86, 50, 76),
    ]


def evaluate(
    readings: list[Reading],
    *,
    last_fired: dict[str, int] | None = None,
    cooldown_ms: int = COOLDOWN_MS,
    window_ms: int = WINDOW_MS,
) -> list[dict]:
    if not readings:
        return []
    last_fired = dict(last_fired or {})
    current = readings[-1]
    fires: list[dict] = []
    window = [row for row in readings[:-1] if current.ts_ms - window_ms <= row.ts_ms <= current.ts_ms]
    if window:
        peak = max(window, key=lambda row: row.systolic)
        if peak.systolic > 0:
            drop = round((peak.systolic - current.systolic) * 100 / peak.systolic)
            span_min = max(1, round((current.ts_ms - peak.ts_ms) / 60_000))
            hr_rise = (current.hr - peak.hr) / peak.hr if peak.hr else 0
            if drop >= 20 and _cooled("bp_drop_pct", current.ts_ms, last_fired, cooldown_ms):
                fires.append(
                    {
                        "rule_id": "bp_drop_pct",
                        "drop_pct": drop,
                        "span_min": span_min,
                        "systolic": current.systolic,
                        "diastolic": current.diastolic,
                        "hr_flat": hr_rise < 0.10,
                        "ts_ms": current.ts_ms,
                    }
                )
                last_fired["bp_drop_pct"] = current.ts_ms
    low = [row for row in readings if row.systolic < 90]
    if len(low) >= 2 and _cooled("bp_low_abs", current.ts_ms, last_fired, cooldown_ms):
        if readings[-1].systolic < 90 and readings[-2].systolic < 90:
            fires.append({"rule_id": "bp_low_abs", "systolic": current.systolic, "ts_ms": current.ts_ms})
            last_fired["bp_low_abs"] = current.ts_ms
    return fires


def _cooled(rule_id: str, now_ms: int, last_fired: dict[str, int], cooldown_ms: int) -> bool:
    previous = last_fired.get(rule_id)
    return previous is None or now_ms - previous >= cooldown_ms


def collect_facts(events: list[dict], now_ms: int) -> list[str]:
    facts: list[str] = []
    for event in events:
        age = now_ms - int(event["ts_ms"])
        if age < 0 or age > 10 * 60_000:
            continue
        payload = event["payload"]
        if event["event_type"] == "druglog.given":
            mins = max(0, age // 60_000)
            amount = payload.get("amount")
            unit = payload.get("unit") or ""
            name = payload.get("generic") or payload.get("name_as_heard")
            facts.append(f"{name} {amount} {unit} {mins} min ago (voice log)".replace("  ", " "))
        elif event["event_type"] == "brownbag.med_found" and payload.get("drug_class"):
            facts.append(
                f"on {payload['generic']} (OPD medicine review, {payload['drug_class']})"
            )
        elif event["event_type"] == "count.item_out":
            pass
    swab_count = sum(
        1
        for event in events
        if event["event_type"] == "count.item_out" and 0 <= now_ms - int(event["ts_ms"]) <= 10 * 60_000
    )
    if swab_count:
        facts.append(f"{swab_count} swabs into the bucket in the last 10 min (Count Guard)")
    return facts


def template_card(fire: dict, facts: list[str]) -> str:
    text = (
        f"BP {fire['systolic']}/{fire['diastolic']}, "
        f"down {fire['drop_pct']}% in {fire['span_min']} min."
    )
    if fire.get("hr_flat"):
        text += " HR not rising."
    if facts:
        text += " " + " ".join(facts)
    return text


def wording_ok(text: str, source: str) -> bool:
    """Reject advice verbs, new numbers, and drug names that are not in the facts."""
    if BANNED.search(text or ""):
        return False
    allowed = set(re.findall(r"\b\d+\b", source))
    for number in re.findall(r"\b\d+\b", text or ""):
        if number not in allowed:
            return False
    for name in known_names():
        if re.search(rf"\b{re.escape(name)}\b", text or "", re.I) and not re.search(
            rf"\b{re.escape(name)}\b", source, re.I
        ):
            return False
    return True


def choose_wording(template: str, llm_text: str | None, *, timed_out: bool = False) -> tuple[str, str]:
    if timed_out or not llm_text or not wording_ok(llm_text, template):
        return template, "template"
    return llm_text.strip(), "llm"
