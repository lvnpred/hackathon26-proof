"""Repair-loop helpers moved out of determinism.py (re-exported there; no behaviour change).
The three constants live here because determinism imports this module (importing back is a cycle)."""
import re

from .candidates import suggest_candidates

RX_VERIFIED = "verified"

# Wording of the unknown-medicine issue. build_repair_message recognises those
# issues by this text, so ground_rx and the message builder share one constant.
UNKNOWN_MEDICINE_TEXT = "not in medicine list"

# Max LLM calls per /api/format request (extract + up to 2 repairs).
FORMAT_LLM_CAP = 3

MAX_CANDIDATE_ROWS = 5  # unknown rows that get a candidate lookup per repair message
_UNKNOWN_ISSUE_RE = re.compile(r"^rx\[\d+\] '(.*)': " + re.escape(UNKNOWN_MEDICINE_TEXT))


def build_repair_message(issues, transcript: str) -> str:
    """Deterministic targeted repair prompt naming each offending row.

    For an unknown-medicine issue the row's name is read back out of the issue
    text and up to 3 sound-alike lexicon names are listed under it. The model
    may pick exactly one or keep its spelling; nothing here edits a row.
    """
    lines = [
        "Your previous JSON has grounding problems against the dictated",
        "transcript and the medicine list. Fix EXACTLY these rows:",
    ]
    offered = False
    looked_up = 0
    for iss in issues:
        lines.append(f"- {iss}")
        m = _UNKNOWN_ISSUE_RE.match(iss)
        cands = []
        if m and looked_up < MAX_CANDIDATE_ROWS:
            looked_up += 1
            cands = suggest_candidates(m.group(1))
        if cands:
            offered = True
            lines.append("  Sound-alike names in the medicine list: " + ", ".join(cands))
    lines.append(
        "For each row: either quote the exact transcript words supporting the"
        " medicine (and use a strength stated in the transcript), or remove"
        " the row. Never invent medicines, strengths, or durations."
    )
    if offered:
        lines.append(
            "Where sound-alike names are listed, pick EXACTLY ONE of them only if"
            " it is what the doctor said (judge by the transcript words);"
            " otherwise keep your spelling unchanged. Never pick a name that is"
            " not listed. A name kept as dictated stays flagged for the doctor."
        )
    lines.append("Return ONLY the FULL corrected JSON matching the schema.")
    return "\n".join(lines)


def loop_should_continue(prev_open: int, new_open: int, llm_calls_used: int,
                         cap: int = FORMAT_LLM_CAP) -> bool:
    """Loop guard: continue only with open issues, budget left, strict progress."""
    return new_open > 0 and llm_calls_used < cap and new_open < prev_open


def open_issues(validated: dict):
    """Issue strings for validated rows whose status is not verified."""
    out = []
    rx = (validated or {}).get("rx") or []
    for i, row in enumerate(rx):
        if isinstance(row, dict) and row.get("status", RX_VERIFIED) != RX_VERIFIED:
            out.append(f"rx[{i}] '{row.get('name', '?')}': {row.get('status')}")
    return out
