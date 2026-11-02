"""Live switches (spec §6.7). Each AI step asks here whether to call its model.

A switch is live only when the model key is set. VOICE_LIVE, PROOF_LIVE and SPARK_LIVE come from the
environment (Settings: None follows the key). TRAY_LIVE, SETUP_LIVE, SWABS_LIVE and MEDICINES_LIVE are the
D3 cut switches: set one False to make that step use the prepared result even with a key.
A live call that fails gives `unavailable(...)`, never a prepared result picked by the uploaded file name.
"""

from __future__ import annotations

from typing import Literal

from app.config import Settings

Name = Literal["voice", "proof", "spark", "tray", "setup", "swabs", "medicines"]
NAMES: tuple[str, ...] = ("voice", "proof", "spark", "tray", "setup", "swabs", "medicines")
UNAVAILABLE = "unavailable"
NOT_CHECKED = "Not checked — model unavailable"

TRAY_LIVE = True  # D3 cut switch: False makes the tray check use the prepared result only
SETUP_LIVE = True  # the same cut switch for the set-up check
SWABS_LIVE = True  # and for the swab camera count
MEDICINES_LIVE = True  # D3 second cut: False makes the medicine photo always use the prepared result

# Spec §6.7: a SAM call that fails with its switch on stands on the prepared result of its check kind, one fixed
# fixture per kind. The uploaded file name never chooses it (§4).
PREPARED_BY_CHECK = {"tray": "tray-hernia.json", "setup": "saline-setup.json", "swabs": "swabs-closing.json"}

_CUT = {"tray": "TRAY_LIVE", "setup": "SETUP_LIVE", "swabs": "SWABS_LIVE", "medicines": "MEDICINES_LIVE"}


def _keyed(settings: Settings, name: str) -> bool:
    if name == "voice":
        return settings.voice_configured
    if name in ("tray", "setup", "swabs"):
        return settings.sam_configured
    return settings.spark_configured


def is_live(settings: Settings, name: Name) -> bool:
    """True when this step calls its model: the key is set and the switch is not turned off."""
    if name not in NAMES:
        raise ValueError(f"unknown switch {name!r}")
    if not _keyed(settings, name):
        return False
    if name in _CUT:
        return bool(globals()[_CUT[name]])
    flag = getattr(settings, f"{name}_live")
    return True if flag is None else bool(flag)


def report(settings: Settings) -> dict[str, bool]:
    """Every switch and whether it is live now, for GET /journey/models."""
    return {name: is_live(settings, name) for name in NAMES}


def unavailable(reason: str) -> dict:
    """A live call that did not answer. The step shows the reason; nothing prepared stands in for it."""
    return {"source": UNAVAILABLE, "why": reason}
