"""Layout vocabulary (spec 7A.2). Pure stdlib: the only way an LLM-written layout reaches the renderer."""
import re
from dataclasses import dataclass

PROFILE_KEYS = ("doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone")
ALIGNS, MAX_TEXT, MAX_BLOCKS, MAX_DOCTORS = ("left", "center", "right"), 200, 12, 12   # chars per literal line; blocks per header/footer; doctors printed
MAX_PROFILE = 600                     # chars per profile value: room for several doctors joined with "; "
_ENUMS = {"role": (("title", "subtitle", "normal", "small"), "normal"), "align": (ALIGNS, "left"),
          "thickness": (("thin", "medium"), "thin")}
_FIELDS = {"text": ("role", "align"), "logo": ("align",), "rule": ("thickness",),
           "doctors": ("role", "align")}   # enum keys each block type takes; "doctors" is filled at print time
_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
POWERED_BY = "Powered By Lightday"      # the app's print credit (owner, 2026-10-20)
_POWERED = re.compile(r"\s*powered\s+by\b", re.IGNORECASE)


def credit_text(text: str) -> str:
    """A pad's own "Powered by ..." line becomes the app's credit; any other text is returned unchanged."""
    return POWERED_BY if _POWERED.match(text or "") else text


def has_credit(blocks) -> bool:
    """True when a literal text block among ``blocks`` is a "Powered by ..." line."""
    return any(b.get("type") == "text" and "text" in b and _POWERED.match(str(b["text"])) for b in blocks)


class LayoutError(ValueError):
    """Outside the vocabulary; ``str(e)`` is safe to show."""


@dataclass(frozen=True)
class Layout:
    header: tuple
    footer: tuple                     # normalised block dicts in print order
    body_top: float
    body_bottom: float                # fractions of the page height: the blank printable area
    profile: dict                     # all six PROFILE_KEYS, "" when unknown


def _check(ok, where, why):
    if not ok:
        raise LayoutError(f"{where}: {why}")


def _num(v, where):
    _check(type(v) in (int, float) and 0 <= v <= 1, where, "must be a number from 0 to 1")
    return float(v)


def _block(raw, where, in_header):
    kind = raw.get("type") if isinstance(raw, dict) else None
    _check(kind in _FIELDS, where, f"unknown block type {str(kind)[:30]!r}")
    out = {"type": kind}
    for key in _FIELDS[kind]:
        out[key] = raw.get(key, _ENUMS[key][1])
        _check(out[key] in _ENUMS[key][0], where, f"{key} must be one of {', '.join(_ENUMS[key][0])}")
    if raw.get("color", "") != "" and kind != "logo":
        _check(isinstance(raw["color"], str) and _HEX.fullmatch(raw["color"]), where, "color must be hex such as #1a3c6e")
        out["color"] = raw["color"]
    if kind == "text":
        _check(("field" in raw) != ("text" in raw), where, "needs exactly one of field or text")
        key = "field" if "field" in raw else "text"
        _check(raw[key] in PROFILE_KEYS if key == "field" else isinstance(raw[key], str) and raw[key].strip()
               and len(raw[key]) <= MAX_TEXT, where, f"field must be a profile field, or text 1 to {MAX_TEXT} characters")
        out[key] = raw[key]
    if kind == "logo":
        crop = raw.get("crop")
        _check(in_header and isinstance(crop, list) and len(crop) == 4, where, "logo needs a 4-number crop, header only")
        x0, y0, x1, y1 = out["crop"] = [_num(v, f"{where}.crop") for v in crop]
        _check(x0 < x1 and y0 < y1, where, "crop needs x0 < x1 and y0 < y1")
    return out


def _blocks(raw, name):
    _check(isinstance(raw, list) and len(raw) <= MAX_BLOCKS, name, f"must be a list of at most {MAX_BLOCKS} blocks")
    return tuple(_block(b, f"{name}[{i}]", name == "header") for i, b in enumerate(raw))


def validate_layout(raw) -> Layout:
    """Return a normalised ``Layout`` or raise ``LayoutError``."""
    _check(isinstance(raw, dict) and isinstance(raw.get("body"), dict) and isinstance(raw.get("profile", {}), dict),
           "layout", "must be an object with a body object (and an object profile)")
    top, bottom, profile = _num(raw["body"].get("top"), "body.top"), _num(raw["body"].get("bottom"), "body.bottom"), raw.get("profile", {})
    _check(0 <= top <= 0.5 <= bottom <= 1, "body", "needs 0 <= top <= 0.5 and 0.5 <= bottom <= 1")
    _check(top < bottom, "body", "needs top < bottom")
    _check(all(isinstance(v, str) and len(v) <= MAX_PROFILE for v in profile.values()), "profile", "values must be short text")
    return Layout(_blocks(raw.get("header", []), "header"), _blocks(raw.get("footer", []), "footer"),
                  top, bottom, {k: profile.get(k, "") for k in PROFILE_KEYS})


DEFAULT_LAYOUT = validate_layout({
    "header": [{"type": "text", "field": "doctor_name", "role": "title", "align": "center"},
               {"type": "text", "field": "clinic_name", "align": "center"}, {"type": "rule"}],
    "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}], "body": {"top": 0.18, "bottom": 0.92}})
