"""The `evidence` an event carries for one model result (care-app clarity §4.2), read by the Expand view.

    {"kind": ..., "captured": {what went in: photo_id / audio_id / transcript / the text sent},
     "returned": {"model": display name or "rules", "mode": live|prepared|failed|none, "ms": int or None,
                  "raw": reply or None},
     "used": {what the app took from it; "fallback": "rules" | "template" when the reply was not used},
     "calls": [the calls, as the record keeps them]}

`returned` describes the last call of the result (the one whose reply the app used or rejected). No call means no
model was asked: mode "none", model "rules" (the page says "No model used — drafted by rules"). A model asked whose
reply was not usable is mode "failed", and `used.fallback` says what stood in. Keys, tokens and headers never enter: secret-named keys are dropped and bearer or
`sk-` tokens in text are redacted.
"""

from __future__ import annotations

import re

from app.journey.live import mode_of

RAW_MAX = 4000
MODEL_NAMES = {"sam": "SAM 3.1", "spark": "Spark 1.3", "spark-open": "Spark Open", "voice": "Muse Voice"}
_SECRET_KEY = re.compile(r"^(api[_-]?key|.*_key|token|.*_token|secret|.*_secret|authorization|headers?|password|cookie)$", re.I)
_SECRET_TEXT = re.compile(r"(?i)\bbearer\s+\S+|\bsk-[A-Za-z0-9_-]{6,}")
REDACTED = "[redacted]"
NO_MODEL = "rules"


def clean(value):
    """The value with secret-named keys dropped and tokens in text redacted, all the way down."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if not _SECRET_KEY.match(str(k))}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, str):
        return _SECRET_TEXT.sub(REDACTED, value)
    return value


def returned_of(calls: list[dict], reply: str | None) -> dict:
    """The model, mode, time and raw reply (cut to RAW_MAX characters) of the last call."""
    if not calls:
        return {"model": NO_MODEL, "mode": "none", "ms": None, "raw": None}
    call = calls[-1]
    mode = mode_of(call.get("source") or "") or "failed"  # asked, with no live or prepared word: its reply not used
    raw = clean(reply)[:RAW_MAX] if isinstance(reply, str) and reply else None
    return {"model": MODEL_NAMES.get(call.get("model")), "mode": mode, "ms": call.get("ms"), "raw": raw}


def evidence_of(kind: str, *, inputs: dict, reply: str | None, used: dict, calls: list[dict]) -> dict:
    return {"kind": kind, "captured": clean(inputs), "returned": returned_of(calls, reply), "used": clean(used),
            "calls": clean(list(calls))}


def fallback(source: str) -> str | None:
    """"rules" when a draft came from the rules, not a model reply; None when the reply was used."""
    return "rules" if source.startswith("rules") else None


def heard_inputs(heard: dict) -> dict:
    """What a spoken or typed line captured: the kept recording (or None) and the words."""
    return {"audio_id": heard.get("audio_id"), "transcript": heard["text"], "typed": heard["source"] == "typed"}
