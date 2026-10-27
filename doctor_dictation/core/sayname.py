"""Say it: the medicine name in a short spoken clip. Pure; stdlib only.

"tablet Eltroxin" -> "Eltroxin"; "Eltroxin, E-L-T-R-O-X-I-N" -> "Eltroxin" (spelled letters win outright);
"it is Eltroxin, not L-thyroxine" -> "Eltroxin". A clip never comes back empty because of the clean-up.
"""
import re

from doctor_dictation.core import spelled

_NOT = re.compile(r"(?:^|,\s*|\s+)(?:and\s+)?not\b[^,]*", re.I)
_FILLER = re.compile(
    r"^(?:um|uh|ok|okay|please|it is|it's|this is|the name is|name is|the medicine is|medicine"
    r"|tablet|tab|capsule|cap|syrup|syr|injection|inj|drops|ointment|cream)\b[\s,.:;!?-]*", re.I)
_EDGE = " \t.,;:!?"


def clean_said_name(text) -> str:
    """The name in ``text``: the last spelled word, else the text without a "not ..." clause and leading filler."""
    heard = " ".join((text or "").split())
    _, found = spelled.apply(heard)
    if found:
        return found[-1]["spelled"]
    name = _NOT.sub("", heard).strip(_EDGE)
    while (stripped := _FILLER.sub("", name, count=1)) != name:
        name = stripped
    return name.strip(_EDGE) or heard.strip(_EDGE) or heard
