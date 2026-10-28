"""Validation of a clinic overlay row's ``data`` (plan PQ-f), split out of ``overlay`` (which re-exports it). Pure."""
import re

KINDS = ("medicine", "investigation")
ACTIONS = ("add", "edit", "hide")
MAX_GENERIC, MAX_CATEGORY, MAX_PRINT = 120, 40, 30
MAX_LIST = {"aliases": 20, "brands": 40}
_TEXT_OK = re.compile(r"[A-Za-z][A-Za-z0-9 .,'+/()%-]*")
_DOSE_END = re.compile(r"\d+(?:\.\d+)?\s*(?:mg|mcg|ug|g|gm|kg|ml|l|iu|units?|%)$", re.I)


def _key(name) -> str:
    from .formulary import key       # lazy: determinism imports overlay, which imports this module
    return key(name)


def _allowed(kind: str, action: str, owner: bool) -> set:
    keys = {"aliases"} | ({"brands"} if kind == "medicine" else {"category", "print"})
    if action == "add":
        keys |= {"name"} | ({"generic"} if kind == "medicine" else set())
    elif kind == "medicine" and not owner:
        keys.add("generic")              # a clinic may change a shipped generic; an owner edit never changes canonical
    return keys | ({"safety"} if owner else set())


def _text(field: str, value, low: int, high: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"The {field} must be text.")
    text = " ".join(value.split())
    if not text and low == 0:
        return ""
    if not (low <= len(text) <= high) or not _TEXT_OK.fullmatch(text):
        raise ValueError(f"The {field} must be {max(low, 1)} to {high} characters: letters, digits, spaces and . , ' + / ( ) % -")
    return text


def _generic(value) -> str:
    text = _text("generic name", value, 3, MAX_GENERIC)
    if sum(c.isalpha() for c in text) < 3:
        raise ValueError("The generic name needs at least 3 letters.")
    if _DOSE_END.search(text):
        raise ValueError("Write the generic without its strength (for example 'Paracetamol', not 'Paracetamol 500 mg').")
    return text


_IX_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .'+/&-]*")
MAX_IX_NAME, MAX_IX_WORDS = 60, 8


def _ix_name(value) -> str:
    """A test name to store (its own case kept: RFT, HbA1c, CA 125, Urine C&S), or "": whitespace collapsed, 2 to 60
    characters, at most 8 words, letters, digits, spaces and . ' + / & - (starting with a letter or digit), 1+ letter."""
    name = " ".join(value.split()) if isinstance(value, str) else ""
    if not (2 <= len(name) <= MAX_IX_NAME) or len(name.split()) > MAX_IX_WORDS or not _IX_NAME.fullmatch(name):
        return ""
    return name if any(c.isalpha() for c in name) else ""


def _name(field: str, value, kind: str) -> str:
    """``formulary.clean_name`` for a medicine; ``_ix_name`` for an investigation (its own, wider rule)."""
    if kind == "investigation":
        name = _ix_name(value)
        if not name:
            raise ValueError(f"The {field} {value!r} is not a test name we can store (2 to 60 characters: letters, digits,"
                             " spaces and . ' + / & -).")
        return name
    from .formulary import clean_name
    name = clean_name(value) if isinstance(value, str) else ""
    if not name:
        raise ValueError(f"The {field} {value!r} is not a medicine or test name we can store (3 to 60 letters and digits).")
    return name


def _names(field: str, value, kind: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"The {field} must be a list of names.")
    if len(value) > MAX_LIST[field]:
        raise ValueError(f"At most {MAX_LIST[field]} {field} are allowed.")
    out, seen = [], set()
    for item in value:
        name = _name(field[:-1] if field != "aliases" else "alias", item, kind)
        if _key(name) not in seen:
            seen.add(_key(name))
            out.append(name)
    return out


def validate_data(kind: str, action: str, data, owner: bool = False) -> dict:
    """A cleaned copy of an overlay row's ``data``, or ValueError with a message a person can read.

    Values are text, lists of text, or (owner only) the bool ``safety``: a JSON number is refused, so "1" and "1.0" can
    never be two different rows. Text is whitespace-collapsed and names go through ``formulary.clean_name``, so a
    re-validated row is unchanged (the function is idempotent)."""
    if kind not in KINDS:
        raise ValueError(f"Unknown list {kind!r}.")
    if action not in ACTIONS:
        raise ValueError(f"Unknown change {action!r}: use add, edit or hide.")
    if action == "hide":
        if data not in (None, {}):
            raise ValueError("Hiding an entry takes no other details.")
        return {}
    if not isinstance(data, dict):
        raise ValueError("The details must be an object.")
    extra = sorted(str(k) for k in data if k not in _allowed(kind, action, owner))
    if extra:
        raise ValueError(f"These details cannot be set here: {', '.join(extra)}.")
    if not data:
        raise ValueError("Nothing to change.")
    out: dict = {}
    if action == "add":
        out["name"] = _name("name", data.get("name"), kind)
        if kind == "medicine" and "generic" not in data:
            raise ValueError("A new medicine needs its generic name.")
    if "generic" in data:
        out["generic"] = _generic(data["generic"])
    for field in ("aliases", "brands"):
        if field in data:
            out[field] = _names(field, data[field], kind)
    if "category" in data:
        out["category"] = _text("category", data["category"], 0, MAX_CATEGORY)
    if "print" in data:
        out["print"] = _text("printed name", data["print"], 0, MAX_PRINT)
    if "safety" in data:
        if type(data["safety"]) is not bool:
            raise ValueError("Safety must be true or false.")
        out["safety"] = data["safety"]
    return out
