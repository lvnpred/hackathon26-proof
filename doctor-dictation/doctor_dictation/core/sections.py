"""The prescription's sections: the seven built-ins plus any added plain-text sections. Pure, no I/O but the
settings file. ``parse`` is strict (a bad edit raises ``SectionsError`` naming the entry); the caller decides the fallback."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "lexicon" / "sections.json"
KINDS = {"complaints": "prose", "diagnosis": "prose", "investigations": "investigations", "findings": "prose",
         "rx": "medication", "advice": "list", "review": "review"}
RESERVED = frozenset(KINDS) | {"vitals", "extra", "remove", "replace", "review_date"}
KEY_RE = re.compile(r"[a-z][a-z0-9_]{1,30}")
MAX_ADDED = 10
HEADING_CHARS = 60
CUE_CHARS = 120
VERSION = 1


class SectionsError(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    key: str
    heading: str
    cue: str
    kind: str
    order: int
    on: bool


_HEADINGS = ("Chief Complaints & Brief History", "Diagnosis / Clinical Impression", "Investigations Advised",
             "Findings", "Rx (MEDICATIONS)", "Dietary & General Advice", "Review / Follow-up")
BUILT_INS = tuple(Section(k, h, "", KINDS[k], 10 * (i + 1), True) for i, (k, h) in enumerate(zip(KINDS, _HEADINGS)))


def _entry(e, i: int) -> Section:
    if not isinstance(e, dict):
        raise SectionsError(f"sections[{i}]: entry must be an object")
    key = e.get("key")
    if not isinstance(key, str):
        raise SectionsError(f"sections[{i}]: key must be text")
    name = f"section '{key}'"
    if key in KINDS:
        kind = KINDS[key]
    elif key in RESERVED:
        raise SectionsError(f"{name}: key is reserved")
    elif not KEY_RE.fullmatch(key):
        raise SectionsError(f"{name}: key must be a lowercase slug (letters, digits, underscore; 2-31 chars)")
    else:
        kind = "text"
    if e.get("kind", kind) != kind:
        raise SectionsError(f"{name}: kind must be '{kind}'")
    heading, cue, order, on = e.get("heading"), e.get("cue"), e.get("order"), e.get("on")
    if not isinstance(heading, str) or not heading.strip() or len(heading) > HEADING_CHARS:
        raise SectionsError(f"{name}: heading must be 1-{HEADING_CHARS} characters")
    if not isinstance(cue, str) or len(cue) > CUE_CHARS:
        raise SectionsError(f"{name}: cue must be text of at most {CUE_CHARS} characters")
    if isinstance(order, bool) or not isinstance(order, int):
        raise SectionsError(f"{name}: order must be a whole number")
    if not isinstance(on, bool):
        raise SectionsError(f"{name}: on must be true or false")
    return Section(key, heading, cue, kind, order, on)


def parse(data) -> tuple[Section, ...]:
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != VERSION:
        raise SectionsError(f"version must be {VERSION}")
    entries = data.get("sections")
    if not isinstance(entries, list):
        raise SectionsError("sections must be a list")
    secs: list[Section] = []
    for i, e in enumerate(entries):
        s = _entry(e, i)
        if any(s.key == t.key for t in secs):
            raise SectionsError(f"section '{s.key}': duplicate key")
        secs.append(s)
    if sum(s.kind == "text" for s in secs) > MAX_ADDED:
        raise SectionsError(f"too many added sections (at most {MAX_ADDED})")
    secs += [Section(b.key, b.heading, b.cue, b.kind, b.order, False) for b in BUILT_INS
             if not any(s.key == b.key for s in secs)]       # a built-in left out of the file counts as switched off
    return tuple(sorted(secs, key=lambda s: s.order))        # stable: equal orders keep file order


def load_file(path=None) -> tuple[Section, ...]:
    return parse(json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8")))


LINE_CHARS = 2000
MAX_EXTRA = 20
_EMPTY = {"list": [], "prose": [], "investigations": [], "medication": [], "review": ""}


def coerce_extra(value, limit: int = 12) -> dict:
    """The stored added sections: clean keys only, each ``{"heading", "lines"}``; an entry without lines is dropped."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for key, e in value.items():
        if not (isinstance(key, str) and KEY_RE.fullmatch(key)) or key in RESERVED or not isinstance(e, dict):
            continue
        raw = e.get("lines")
        lines = [str(x).strip()[:LINE_CHARS] for x in raw if x is not None and str(x).strip()] if isinstance(raw, list) else []
        if not lines:
            continue
        heading = " ".join(str(e.get("heading") or "").replace('"', "").split())[:HEADING_CHARS].strip() or key.replace("_", " ").capitalize()
        out[key] = {"heading": heading, "lines": lines[:limit]}
        if len(out) >= MAX_EXTRA:
            break
    return out


def text_headings(secs) -> dict[str, str]:
    return {s.key: s.heading for s in secs if s.kind == "text" and s.on}


def fold(form: dict, headings: dict[str, str]) -> dict:
    """A copy of ``form`` with each added section's flat key (the shape the LLM answers in) filed under ``extra``."""
    out = dict(form)
    extra = out.get("extra") if isinstance(out.get("extra"), dict) else {}
    extra = dict(extra)
    for key, heading in headings.items():
        lines = out.pop(key, None)
        old = extra.get(key) if isinstance(extra.get(key), dict) else {}
        extra[key] = {"heading": old.get("heading") or heading, "lines": lines if lines else old.get("lines")}
    out.pop("extra", None)
    extra = coerce_extra(extra)
    if extra:
        out["extra"] = extra
    return out


def unfold(form: dict) -> tuple[dict, dict[str, str]]:
    """The inverse of ``fold``: a copy without ``extra``, its lines as flat keys, plus each key's stored heading."""
    out = dict(form)
    extra = coerce_extra(out.pop("extra", None))
    for key, e in extra.items():
        out[key] = list(e["lines"])
    return out, {key: e["heading"] for key, e in extra.items()}


def drop_off(structured: dict, secs) -> None:
    """Blank every switched-off built-in in place, so a new draft never fills it."""
    for s in secs:
        if not s.on and s.kind != "text":
            structured[s.key] = _EMPTY[s.kind].copy() if isinstance(_EMPTY[s.kind], list) else _EMPTY[s.kind]


def has_data(structured: dict, key: str, kind: str) -> bool:
    if kind == "text":
        extra = structured.get("extra")
        e = extra.get(key) if isinstance(extra, dict) else None
        return bool(isinstance(e, dict) and e.get("lines"))
    v = structured.get(key)
    if kind == "medication":
        return any(isinstance(r, dict) and str(r.get("name") or "").strip() for r in v or [])
    if kind == "review":
        return bool(str(v or "").strip())
    return bool(v)


def layout(secs, structured: dict) -> list[tuple[str, str, str]]:
    """``(key, heading, kind)`` of what a sheet shows: each section that is on or holds data, in list order, then
    stored added sections the list no longer has. A stored heading wins for an added section."""
    extra = structured.get("extra") if isinstance(structured.get("extra"), dict) else {}
    out = []
    for s in secs:
        if s.on or has_data(structured, s.key, s.kind):
            heading = (extra.get(s.key) or {}).get("heading") if s.kind == "text" else None
            out.append((s.key, heading or s.heading, s.kind))
    known = {s.key for s in secs}
    return out + [(k, e.get("heading") or k, "text") for k, e in extra.items() if k not in known and has_data(structured, k, "text")]


def format_rule(secs) -> str:
    """Prompt rule 15 for the added sections of the list; empty for the default list."""
    heads = text_headings(secs)
    if not heads:
        return ""
    cues = {s.key: s.cue for s in secs}
    items = "; ".join(f'"{k}" ({h}, for example "{cues[k]}")' if cues[k] else f'"{k}" ({h})' for k, h in heads.items())
    return ("\n15. Added sections: also return each of these keys in the JSON object, a list of short sentences "
            "restating ONLY what the doctor dictated for it, [] if nothing was dictated, each item at most 400 "
            f"characters: {items}.")


def correction_rule(headings: dict) -> str:
    """Correction rule 17 for the added list sections the form holds; empty when there are none."""
    if not headings:
        return ""
    items = "; ".join(f'"{k}" ({h})' for k, h in headings.items())
    return f'\n17. Added list sections work like findings in rule 7, and "remove" and "replace" take their keys too: {items}.'


def signature(secs) -> str:
    return ",".join(s.key for s in secs if s.on)
