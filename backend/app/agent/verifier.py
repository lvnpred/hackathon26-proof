"""Check a sentence against the ledger before it reaches the screen."""

from __future__ import annotations

import re

ADVICE = re.compile(
    r"\b("
    r"recommend(?:ed|s)?|should|must|x-?rays?|re-?explore|reexplore|"
    r"inside the patient|probably|advise[sd]?|suggest(?:ed|s|ion)?|"
    r"treatment|dosage|medications?|vital signs|order an|order a"
    r")\b",
    re.I,
)


def check_sentence(
    text: str,
    *,
    evidence_ids: list[str],
    known_ids: set[str],
    figures: dict,
    claims: dict,
    track_id: str | None = None,
) -> list[str]:
    """Return a list of problems. An empty list means the sentence can be shown."""
    errors: list[str] = []
    if ADVICE.search(text or ""):
        errors.append("advice wording")
    for evidence_id in evidence_ids:
        if evidence_id not in known_ids:
            errors.append(f"unknown evidence {evidence_id}")
        if evidence_id and evidence_id not in text:
            errors.append(f"evidence not cited {evidence_id}")
    for key, value in claims.items():
        if key not in figures:
            errors.append(f"claim {key} is not on the ledger")
        elif figures.get(key) != value:
            errors.append(f"claim {key} {value} does not match ledger {figures.get(key)}")
    allowed = {str(value) for value in figures.values() if isinstance(value, int)}
    redacted = text or ""
    for evidence_id in evidence_ids:
        redacted = redacted.replace(evidence_id, " ")
    if track_id:
        redacted = redacted.replace(track_id, " ")
    for number in re.findall(r"\b\d+\b", redacted):
        if number not in allowed:
            errors.append(f"number {number} is not in the ledger figures")
    return errors


def template_sentence(row: dict) -> dict:
    """Fixed sentence. Used when the model is absent or fails the check."""
    figures = row.get("figures") or {}
    evidence = [item for item in (row.get("evidence") or []) if item]
    evidence_text = ", ".join(evidence) if evidence else "ledger"
    rule_id = row["rule_id"]
    if rule_id == "R1":
        text = (
            f"{row['item_type']}: opened {figures.get('opened')}. "
            f"In the bucket {figures.get('bucket')}. On the tray {figures.get('tray')}. "
            f"Evidence {evidence_text}."
        )
    elif rule_id == "R2":
        text = (
            f"Spoken count: {figures.get('spoken', row.get('expected'))}. "
            f"Camera count: {figures.get('camera', row.get('observed'))}. "
            f"Evidence {evidence_text}."
        )
    elif rule_id == "R3":
        text = (
            f"Unaccounted: {figures.get('unaccounted', 1)} {row['item_type']}. "
            f"Last seen {figures.get('seen_min', 0)} min {figures.get('seen_sec', 0)} sec, "
            f"{row.get('last_zone') or 'field'}. "
            f"Evidence {evidence_text}."
        )
    elif rule_id == "R4":
        text = (
            f"Unannounced add: {figures.get('observed', 0)} {row['item_type']} on the tray. "
            f"Spoken add matched: {figures.get('expected', 0)}. "
            f"Evidence {evidence_text}."
        )
    else:
        text = (
            f"Needs a human look at {row.get('track_id') or 'one detection'}. "
            f"This is not a count alert. Evidence {evidence_text}."
        )
    claims = {}
    if row.get("expected") is not None:
        claims["expected"] = row["expected"]
    if row.get("observed") is not None:
        claims["observed"] = row["observed"]
    return {
        "discrepancy_id": row["id"],
        "text": text,
        "evidence_ids": evidence,
        "claims": claims,
        "source": "template",
    }
