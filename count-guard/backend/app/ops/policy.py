"""The level table (C1). One place says what the AI may do alone, what it proposes, what it never does."""

from __future__ import annotations

from app.journey import seed

LEVELS = {
    "transcribe": "L3", "read_photo": "L3", "count_camera": "L3", "nudge_obs_overdue": "L3",
    "ack_order": "L2", "assign_task": "L2", "route_question": "L2", "file_read": "L2",
    "draft_answer": "L1", "propose_move": "L1", "draft_discharge": "L1",
    "prescribe": "Never", "change_dose": "Never", "advise_patient": "Never",
    "clear_count": "Never", "discharge": "Never",
}
NEVER_WORDS = {
    "prescribe": "prescribe", "change_dose": "change a dose", "advise_patient": "advise a patient",
    "clear_count": "clear a count", "discharge": "discharge a patient",
}
# Kinds the gate carries out itself (gate.EXECUTABLE must match). They cannot be lowered to L1:
# approve could not run them with the person as author.
EXECUTABLE_KINDS = frozenset({"ack_order", "assign_task", "route_question", "file_read", "nudge_obs_overdue"})
SETTABLE = ("L0", "L1", "L2", "L3")

UNDO_MS = 600_000
FILE_AFTER_MS = 300_000
MAX_PROPOSALS = 3
MAX_PASSES = 3

WARD = "Ward 4"
AI_BY = f"AI (on behalf of {WARD})"
OPS_LABEL = f"{WARD} operations (synthetic)"
NURSES = (seed.NURSE, seed.NURSE_THEATRE)
DOCTORS = (seed.DOCTOR,)
