"""Which literal letterhead lines are blank pad labels, and which profile fields print in both header and footer.

Pure stdlib. Shared by the vision builder (drops labels from a new draft) and the template service (reports them on
every template). English only: labels in other scripts are not recognised here.
"""
from __future__ import annotations

import re

from doctor_dictation.pdf.layout import PROFILE_KEYS
from doctor_dictation.templates import TemplateError

MAX_LABEL_CHARS = 80
# "reg", "regd", "registration" are left out on purpose: the doctor's Reg. No is a profile field.
LABEL_WORDS = frozenset({
    "name", "age", "sex", "gender", "male", "female", "yrs", "years", "address", "mobile", "phone", "contact",
    "op", "ip", "uhid", "mrd", "mr",
    "date", "visit", "next", "review", "follow", "followup", "submit",
    "weight", "wt", "height", "ht", "bp", "pulse", "temp", "temperature", "spo2", "kg"})
FILLER_WORDS = frozenset({"m", "f", "no", "id", "of", "the", "patient", "patients", "on", "after", "up", "and", "or"})

_INNER_DOT = re.compile(r"(?<=[a-z])\.(?=[a-z])")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_PHONE_SPLIT = re.compile(r"[;,/|]")


def is_fill_in_label(text) -> bool:
    """True when a literal line is a blank pad label ("Name: M F Age: Date:", "Visit After", "________")."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_LABEL_CHARS:
        return False
    s = _INNER_DOT.sub("", text.casefold()).replace("'", "").replace("’", "")
    words = _NOT_ALNUM.sub(" ", s).split()
    if not words:
        return True   # only punctuation or underscores: a blank writing line
    if any(w not in LABEL_WORDS and w not in FILLER_WORDS for w in words):
        return False
    if any(c.isdigit() for w in words if w != "spo2" for c in w):
        return False
    return any(w in LABEL_WORDS for w in words)


def _text_blocks(layout):
    """Yield (section, index, block) for every block of header and footer; malformed input yields nothing."""
    for section in ("header", "footer"):
        blocks = layout.get(section) if isinstance(layout, dict) else None
        for index, b in enumerate(blocks if isinstance(blocks, list) else []):
            yield section, index, b


def fill_in_lines(layout) -> list:
    """Literal lines that are fill-in labels: ``[{"section", "index", "text"}]``, header first."""
    return [{"section": s, "index": i, "text": b["text"]} for s, i, b in _text_blocks(layout)
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
            and is_fill_in_label(b["text"])]


def drop_fill_in_lines(layout) -> list:
    """Remove fill-in label blocks from ``layout`` in place; return their texts in reading order."""
    found = fill_in_lines(layout)
    for section in ("header", "footer"):
        for hit in reversed([f for f in found if f["section"] == section]):
            del layout[section][hit["index"]]
    return [f["text"] for f in found]


def left_out_entries(layout) -> list:
    """The fill-in text blocks as restorable entries: ``[{"section", "index", "block"}]`` (original index, a copy)."""
    return [{"section": f["section"], "index": f["index"], "block": dict(layout[f["section"]][f["index"]])}
            for f in fill_in_lines(layout)]


def restore_left_out(layout: dict, include) -> None:
    """Put the ``left_out`` entries at these positions back into header or footer, in place.

    Raises TemplateError(400) unless ``include`` is a list of distinct ints that are positions in ``left_out``.
    Entries go back in ascending original index, each at ``index - k`` (k: entries of its section still left out with a
    smaller index), clamped to the section; ``left_out`` is deleted when it empties; restored texts also leave ``skipped_labels``.
    """
    entries = layout.get("left_out")
    entries = entries if isinstance(entries, list) else []
    if (not isinstance(include, list) or any(type(i) is not int or not 0 <= i < len(entries) for i in include)
            or len(set(include)) != len(include)):
        raise TemplateError(400, "include must list distinct left-out lines")
    chosen = sorted((entries[i] for i in include), key=lambda e: e["index"])
    rest = [e for n, e in enumerate(entries) if n not in include]
    for e in chosen:
        blocks = layout[e["section"]]
        k = sum(1 for r in rest if r["section"] == e["section"] and r["index"] < e["index"])
        blocks.insert(max(0, min(len(blocks), e["index"] - k)), dict(e["block"]))
    skipped = layout.get("skipped_labels")
    if isinstance(skipped, list):       # a line that prints again is no longer "left out" in the old sentence
        for e in chosen:
            if e["block"].get("text") in skipped:
                skipped.remove(e["block"]["text"])
        if not skipped:
            layout.pop("skipped_labels")
    if rest:
        layout["left_out"] = rest
    else:
        layout.pop("left_out", None)


def _digits(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def _collapse(s: str) -> str:
    return " ".join(s.casefold().split())


def _literal_has(field: str, profile: dict, text: str) -> bool:
    """A literal line that carries the profile's phone number(s) or address."""
    value = profile.get(field)
    if not isinstance(value, str):
        return False
    if field == "phone":
        line_digits = _digits(text)
        return any(len(d) >= 6 and d in line_digits for d in (_digits(p) for p in _PHONE_SPLIT.split(value)))
    if field == "address":
        addr, line = _collapse(value), _collapse(text)
        return len(addr) >= 10 and (addr in line or (len(line) >= 10 and line in addr))
    return False


def duplicate_fields(layout) -> list:
    """Profile fields held by both header and footer: ``[{"field", "header": [idx], "footer": [idx]}]``."""
    profile = layout.get("profile") if isinstance(layout, dict) else None
    profile = profile if isinstance(profile, dict) else {}
    where = {f: {"header": [], "footer": []} for f in PROFILE_KEYS}
    for section, index, b in _text_blocks(layout):
        if not isinstance(b, dict) or b.get("type") != "text":
            continue
        f = b.get("field")
        if f in where:
            where[f][section].append(index)
        elif isinstance(b.get("text"), str):
            for field in ("phone", "address"):
                if _literal_has(field, profile, b["text"]):
                    where[field][section].append(index)
    return [{"field": f, "header": w["header"], "footer": w["footer"]}
            for f, w in where.items() if w["header"] and w["footer"]]


KEEP_WHERE = ("header", "footer", "both")


def check_keep(keep) -> list:
    """``keep`` as ``[{"field", "where"}]`` (copies, nothing else carried over), or TemplateError(400)."""
    if not isinstance(keep, list):
        raise TemplateError(400, "keep must be a list")
    out, seen = [], set()
    for k in keep:
        if not isinstance(k, dict) or k.get("field") not in PROFILE_KEYS or k.get("where") not in KEEP_WHERE:
            raise TemplateError(400, "each keep needs a profile field and where (header, footer or both)")
        if k["field"] in seen:
            raise TemplateError(400, "choose one place per field")
        seen.add(k["field"])
        out.append({"field": k["field"], "where": k["where"]})
    return out


_VALUE_LABELS = frozenset({"ph", "phone", "mobile", "mob", "tel", "telephone", "contact", "cell", "no", "call",
                           "address", "add", "addr"})


def _squash(s: str) -> str:
    """Whitespace-normalised text (case kept) for comparing a screen's copy of a line with the stored one."""
    return " ".join(s.split())


def same_text(a: str, b: str) -> bool:
    return _squash(a) == _squash(b)


def _holds_only_value(field: str, profile: dict, text: str) -> bool:
    """True when a literal line is just the profile value (plus a label such as "Ph:"), so removing it loses no other text."""
    value = profile.get(field)
    if not isinstance(value, str):
        return False
    if field == "phone":
        rest = _digits(text)
        for number in sorted({_digits(p) for p in _PHONE_SPLIT.split(value) if len(_digits(p)) >= 6}, key=len, reverse=True):
            rest = rest.replace(number, "")
        if rest:
            return False
        words = _NOT_ALNUM.sub(" ", "".join(" " if c.isdigit() else c for c in text.casefold())).split()
    else:
        line = _collapse(text).replace(_collapse(value), " ")
        words = _NOT_ALNUM.sub(" ", line).split()
        if _collapse(value) not in _collapse(text):
            return True   # the line is a piece of the address (``_literal_has`` matched it that way)
    return all(w in _VALUE_LABELS for w in words)


def apply_line_changes(layout: dict, line_edits: list, keep: list, include=None) -> None:
    """Edit and remove literal lines, and drop one copy of a duplicated field, in ``layout`` in place.

    Every index refers to the layout as stored: all entries are checked first, text edits apply next, then every
    removal (a line's own ``remove`` plus the unwanted copies from ``keep``) is deleted highest index first.
    ``include`` (positions in ``layout["left_out"]``) restores left-out lines last, after the removals.
    Raises TemplateError(400) on a bad entry; ``layout`` may be half-changed then, so callers work on a copy.
    """
    if not isinstance(line_edits, list):
        raise TemplateError(400, "lines must be a list")
    edits, edited, removals = [], set(), {"header": set(), "footer": set()}
    for ln in line_edits:
        if not isinstance(ln, dict):
            raise TemplateError(400, "each line needs section, index and text")
        remove = ln.get("remove")
        if "remove" in ln and remove is not True:
            raise TemplateError(400, "remove must be true")
        if remove is not True and not isinstance(ln.get("text"), str):
            raise TemplateError(400, "each line needs section, index and text")
        section, index = ln.get("section"), ln.get("index")
        if (section not in ("header", "footer") or isinstance(index, bool) or not isinstance(index, int)
                or not 0 <= index < len(layout[section])):
            raise TemplateError(400, "no such line")
        block = layout[section][index]
        if block.get("type") != "text" or "text" not in block:
            raise TemplateError(400, "only literal text lines can be removed" if remove
                                else "only literal text lines can be edited")
        if remove:
            if isinstance(ln.get("text"), str) and not same_text(ln["text"], block["text"]):
                raise TemplateError(400, "the letterhead changed; reopen it")
            removals[section].add(index)
        else:
            edits.append((block, ln["text"].strip()))
            edited.add((section, index))
    wanted = check_keep(keep)
    dups = {d["field"]: d for d in duplicate_fields(layout)}
    for k in wanted:
        d = dups.get(k["field"])
        if d is None or k["where"] == "both":
            continue
        drop = "footer" if k["where"] == "header" else "header"
        keep_side = k["where"]
        profile = layout.get("profile") if isinstance(layout.get("profile"), dict) else {}
        if all(i in removals[keep_side] for i in d[keep_side]):
            continue            # the kept side is being removed too: leave this copy so the field still prints once
        for i in d[drop]:       # a field block always goes; a literal line only when it holds nothing but the value
            b = layout[drop][i]
            if (drop, i) in edited:
                continue        # the doctor changed this line in the same request: keep what they typed
            if b.get("field") or _holds_only_value(k["field"], profile, b.get("text", "")):
                removals[drop].add(i)
    for block, text in edits:
        block["text"] = text
    for section, idx in removals.items():
        for i in sorted(idx, reverse=True):
            del layout[section][i]
    if include is not None and include != []:
        restore_left_out(layout, include)
