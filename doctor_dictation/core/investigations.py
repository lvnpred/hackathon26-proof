"""Investigation items (lab tests, imaging) grounded against a catalogue (plan PQ-h). Pure; stdlib only.

An item is ``{"text", "canonical", "status", "source"}``. ``text`` is what is printed; ``canonical`` is the catalogue
name it was matched to (``""`` when none). Matching is exact on a normalised name, never fuzzy.
"""
import difflib
import json
import logging
import re
from contextvars import ContextVar
from pathlib import Path

from doctor_dictation.core import overlay, prose
from doctor_dictation.core.lexicon import build_investigations as _builder
from doctor_dictation.core.lexmemo import per_lexicon

log = logging.getLogger(__name__)

CATALOGUE_PATH = Path(__file__).with_name("lexicon") / "investigations.json"
STATUSES = ("verified", "new", "not-dictated", "")
SOURCES = ("dictated", "doctor")
TEXT_CHARS = 200
QUALIFIERS = overlay.IX_QUALIFIERS     # one list: the hide check strips what lookup strips

_shipped_cache = None            # entries of the shipped file once read; None = not read yet
_NONE: list = []                 # the one empty list a missing file gives, so overlay views keyed on it stay stable
_missing_logged = False
_active: ContextVar = ContextVar("investigations_active", default=None)
_index_slot: dict = {}           # per_lexicon slot: id(entries list) -> (list, key -> entry)
_WS = re.compile(r"\s+")
IX_FRAME = prose.FRAME | frozenset("""of and the for with in on to at or test tests level levels serum report repeat follow up
advised advise done study profile scan""".split())    # words a written-out test name adds without naming a test


def key(text) -> str:
    """The normalised form of a name (same rule as the catalogue builder)."""
    return _builder.key(text if isinstance(text, str) else "")


def shipped() -> list:
    """The shipped catalogue entries, read once; ``[]`` when the file is missing or bad. Callers must not mutate."""
    global _shipped_cache, _missing_logged
    if _shipped_cache is not None:
        return _shipped_cache
    try:
        data = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
        found = data.get("entries", [])
        if not isinstance(found, list):
            raise ValueError("entries is not a list")
        found = [e for e in found if isinstance(e, dict)]
    except (OSError, ValueError, AttributeError) as exc:
        if not _missing_logged:
            _missing_logged = True
            log.warning("investigations catalogue unavailable (%s); grounding is off", exc)
        return _NONE             # not cached, so a file added later is picked up
    _shipped_cache = found
    return found


overlay.register_shipped("investigation", shipped)


def clinic_entries() -> list:
    """The shipped catalogue with this request's clinic overlay applied (``overlay.effective_view``): the shipped list
    itself when the clinic changed nothing. A hidden test is not in it, so ``lookup`` never finds it. Do not mutate."""
    return overlay.effective_view("investigation", shipped())


def activate(entries: list) -> None:
    """Make ``entries`` (the clinic's effective list) this context's catalogue."""
    _active.set(entries)


def entries() -> list:
    """The active clinic's effective entries, else the shipped catalogue."""
    active = _active.get()
    return active if active is not None else shipped()


def _compact(k: str) -> str:
    return k.replace(" ", "")


_SPELLED = re.compile(r"(?:\w )+\w")      # single letters or digits separated by spaces: "r f t"


def _build_index(lex: list) -> tuple:
    """(spaced key -> entry, spaceless key -> entry). A spaceless key two different entries share is dropped."""
    idx: dict = {}
    for entry in lex:
        if not isinstance(entry, dict):
            continue
        for name in [entry.get("canonical"), entry.get("print"), *(entry.get("aliases") or [])]:
            k = key(name)
            if k:
                idx.setdefault(k, entry)
    compact: dict = {}
    dropped: set = set()
    for name_key, entry in idx.items():
        c = _compact(name_key)
        if c in dropped:
            continue
        if c in compact and compact[c] is not entry:
            del compact[c]
            dropped.add(c)
        else:
            compact[c] = entry
    return idx, compact


def _index(lex: list) -> tuple:
    """``_build_index(lex)``, built once per list object."""
    return per_lexicon(_index_slot, lex, lambda: _build_index(lex))


def lookup(text) -> "dict | None":
    """The entry whose canonical name, alias or print form equals ``text`` (after ``key``), retried once with a leading
    qualifier word removed. A spelled-out query ("r f t") also matches the spaceless form of a name ("rft") when that
    form belongs to one entry only. Exact only."""
    return lookup_in(text, entries())


def lookup_in(text, lex: list, memo: bool = True) -> "dict | None":
    """``lookup`` against the list ``lex``. ``memo=False`` builds the index without caching it (a one-off list)."""
    k = key(text)
    if not k:
        return None
    idx, compact = _index(lex) if memo else _build_index(lex)
    for candidate in [k] + [k[len(q) + 1:] for q in QUALIFIERS if k.startswith(q + " ")][:1]:
        hit = idx.get(candidate)
        if hit is None and _SPELLED.fullmatch(candidate):
            hit = compact.get(_compact(candidate))
        if hit is not None:
            return hit
    return None


def coerce_items(values) -> list:
    """Items from a stored or dictated list: strings become dictated items; bad fields fall back to safe defaults;
    blank or non-string/dict entries are dropped. Never mutates ``values``."""
    out: list = []
    for v in values if isinstance(values, list) else []:
        raw = v if isinstance(v, str) else v.get("text") if isinstance(v, dict) else None
        if not isinstance(raw, str):
            continue
        text = _WS.sub(" ", raw).strip()[:TEXT_CHARS].strip()
        if not text:
            continue
        d = v if isinstance(v, dict) else {}
        canonical = d.get("canonical")
        status = d.get("status")
        source = d.get("source")
        out.append({"text": text,
                    "canonical": canonical if isinstance(canonical, str) else "",
                    "status": status if status in STATUSES else "",
                    "source": source if source in SOURCES else "dictated"})
    return out


def flatten(form: dict) -> dict:
    """Shallow copy of ``form`` whose ``investigations`` is the list of item texts."""
    out = dict(form)
    out["investigations"] = [i["text"] for i in coerce_items(form.get("investigations"))]
    return out


def print_text(item) -> str:
    """The printed line for one item: ``text``, plus ``(canonical)`` when the two differ by name."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    text = item.get("text")
    text = text.strip() if isinstance(text, str) else ""
    canonical = item.get("canonical")
    canonical = canonical.strip() if isinstance(canonical, str) else ""
    if text and canonical and key(text) != key(canonical):
        return f"{text} ({canonical})"
    return text


# --- "Was it dictated?" -------------------------------------------------------------------------------------------
# A dictated item is heard when a name of its catalogue entry, or every content word of its text, is in the
# dictation. Both sides first join runs of single letters ("r f t", "R.F.T." -> "rft"). A mention the doctor negated
# ("no need for ECG", "USG KUB not needed", "no ECG") is removed from the dictation first, so a test the AI lists
# anyway stays not-dictated (red).

_CLAUSE = re.compile(r"[,;:!?\n]|(?<=\w\w)\.(?=\s|$)|\bbut\b")   # "R.F.T." and "e. c. g." are not clause ends
_TOKEN = re.compile(r"[a-z0-9]+")
_BARE_NEG = frozenset("no not nil never none".split())            # negates the next word (or catalogue name) only
_LEADS = sorted((tuple(p.split()) for p in ("no need to do", "no need to", "no need for", "no need of", "no need",
                 "dont do", "do not do", "dont need", "do not need", "avoid", "skip", "cancel")), key=len, reverse=True)
_LEAD_ENDS = frozenset("do get advise advised send check order".split())   # a new order ends a lead's reach
_TRAILS = frozenset("needed required necessary indicated advised warranted".split())   # "<test> not needed"
_CONJ = frozenset("and or also".split())


def _join_letters(toks: list) -> list:
    """Runs of two or more single-letter words joined: ["usg", "k", "u", "b"] -> ["usg", "kub"]."""
    out: list = []
    run: list = []
    for w in toks + [""]:
        if len(w) == 1 and w.isalpha():
            run.append(w)
            continue
        out.extend(["".join(run)] if len(run) > 1 else run)
        run = []
        if w:
            out.append(w)
    return out


def _tokens(text) -> list:
    return _join_letters(_TOKEN.findall(str(text or "").casefold().replace("'", "").replace("\u2019", "")))


def _name_len(toks: list, at: int) -> int:
    for n in range(min(5, len(toks) - at), 1, -1):
        if lookup(" ".join(toks[at:at + n])) is not None:
            return n
    return 1


def _unnegated(toks: list) -> list:
    """``toks`` (one clause) without its negated mentions."""
    out: list = []
    i = 0
    while i < len(toks):
        w = toks[i]
        if (w == "not" and i + 1 < len(toks) and toks[i + 1] in _TRAILS) or w == "unnecessary":
            while out and out[-1] not in _CONJ:                      # "rft and usg kub not needed": drop "usg kub"
                out.pop()
            i += 1 if w == "unnecessary" else 2
            continue
        lead = next((len(p) for p in _LEADS if tuple(toks[i:i + len(p)]) == p), 0)
        if lead:
            i += lead
            while i < len(toks) and toks[i] not in _LEAD_ENDS:       # "no need for ecg and rft": both dropped
                i += 1
            continue
        if w in _BARE_NEG:
            i += 1 + (_name_len(toks, i + 1) if i + 1 < len(toks) else 0)
            continue
        out.append(w)
        i += 1
    return out


def _clauses(transcripts) -> list:
    """Per transcript, its clauses as token lists with negated mentions removed."""
    return [[_unnegated(_tokens(c)) for c in _CLAUSE.split(str(t or "").casefold())]
            for t in transcripts if isinstance(t, str)]


def _says(clauses: list, name) -> bool:
    """A run of whole words in one clause spells ``name`` (spaces ignored, so "usgkub" and "usg kub" both match)."""
    target = "".join(_tokens(name))
    if not target:
        return False
    for toks in (c for per in clauses for c in per):
        for i in range(len(toks)):
            joined = ""
            for w in toks[i:]:
                joined += w
                if joined == target:
                    return True
                if not target.startswith(joined):
                    break
    return False


def _heard(text: str, entry, clauses: list) -> bool:
    if isinstance(entry, dict) and any(_says(clauses, n) for n in [entry.get("canonical"), entry.get("print"),
                                                                      *(entry.get("aliases") or [])] if isinstance(n, str)):
        return True
    words = " ".join(_tokens(text))
    if not words or not clauses:
        return False
    pool = prose.heard_pool(*(" ".join(w for c in per for w in c) for per in clauses))
    content = [w for w in re.findall(r"[a-z]+|\d+", words) if w not in IX_FRAME and (len(w) > 1 or w.isdigit())]
    if any(w.isalpha() and len(w) <= 3 and w not in pool[0] for w in content):
        return False                                             # a short code is never a speech spelling ("mri" vs "mr")
    frame = IX_FRAME if content else frozenset()                 # an all-frame text ("Repeat test") must be said as is
    return not prose.missing_in_pool(words, pool, min_word=2, frame=frame) and _in_order(text, clauses)


GAP = 2                                                          # other words allowed between two content words


def _alike(w: str, t: str) -> bool:
    return w == t or (len(w) > 3 and difflib.SequenceMatcher(None, w, t).ratio() >= 0.8)


def _in_order(text: str, clauses: list) -> bool:
    """The content words of ``text`` (not IX_FRAME; single letters count: the "d" of "Vitamin D") appear in order in
    one clause, at most GAP other words apart. Stops words from separate remarks ("kidney pain …, function normal")
    adding up to a test."""
    content = [w for w in _tokens(text) if w not in IX_FRAME]
    if not content:
        return True
    for toks in (c for per in clauses for c in per):
        for start, t in enumerate(toks):
            if not _alike(content[0], t):
                continue
            at = start
            for w in content[1:]:
                at = next((j for j in range(at + 1, min(len(toks), at + 2 + GAP)) if _alike(w, toks[j])), None)
                if at is None:
                    break
            if at is not None:
                return True
    return False


def heard(text: str, entry: "dict | None", *transcripts) -> bool:
    """Whether the dictation said ``text``: a name of ``entry`` as whole words, or every content word of ``text``
    (2+ letters, not IX_FRAME; numbers exactly; close speech spellings allowed). Negated mentions do not count."""
    return _heard(text, entry, _clauses(transcripts))


def check_items(values, *transcripts) -> list:
    """New items (coerced first) with ``status`` and ``canonical`` set: a doctor item is verified or new; a dictated
    item never heard is not-dictated (red), else verified when in the catalogue, else new. Never mutates ``values``."""
    clauses = _clauses(transcripts)
    out: list = []
    for item in coerce_items(values):
        entry = lookup(item["text"])
        found = entry.get("canonical") if isinstance(entry, dict) and isinstance(entry.get("canonical"), str) else ""
        if item["source"] == "doctor":
            status, canonical = ("verified", found) if entry else ("new", item["canonical"])
        elif not _heard(item["text"], entry, clauses):
            status, canonical = "not-dictated", found
        else:
            status, canonical = ("verified", found) if entry else ("new", "")
        out.append({**item, "status": status, "canonical": canonical})
    return out


def reconcile(previous, items, *transcripts) -> list:
    """``items`` after a spoken correction: one whose ``key(text)`` equals a previous item's keeps that item's canonical,
    status and source (first match wins; each previous item is used once). Every other item is checked against the
    correction ``transcripts`` like a new dictated one: its source, status and canonical are reset first, since only the
    doctor's page (the previous items) can carry a doctor source. Never mutates its arguments."""
    left = coerce_items(previous)
    out: list = []
    fresh: list = []
    for item in coerce_items(items):
        k = key(item["text"])
        i = next((n for n, p in enumerate(left) if key(p["text"]) == k), None)
        if i is None:
            out.append(None)
            fresh.append({**item, "source": "dictated", "status": "", "canonical": ""})
        else:
            old = left.pop(i)
            out.append({**item, "canonical": old["canonical"], "status": old["status"], "source": old["source"]})
    checked = iter(check_items(fresh, *transcripts))
    return [o if o is not None else next(checked) for o in out]


def screen(structured) -> list:
    """``[{"index", "text"}]`` for each dictated item still ``not-dictated`` (red), in order. Save is blocked while any
    remain: the doctor keeps the test (source becomes ``doctor``) or removes it."""
    items = coerce_items(structured.get("investigations") if isinstance(structured, dict) else None)
    return [{"index": n, "text": i["text"]} for n, i in enumerate(items)
            if i["status"] == "not-dictated" and i["source"] == "dictated"]


def regrade(items) -> list:
    """New items with the page's ``canonical`` and ``status`` recomputed from the active catalogue, never trusted. A
    dictated item with status ``""`` or ``not-dictated`` keeps its status; its canonical is cleared (``""``) or looked up
    (``not-dictated``). A dictated ``verified``/``new`` item takes both
    from ``lookup``. A doctor item takes its status from ``lookup`` and keeps its own canonical when it has one."""
    out: list = []
    for item in coerce_items(items):
        entry = lookup(item["text"])
        found = entry.get("canonical") if isinstance(entry, dict) and isinstance(entry.get("canonical"), str) else ""
        if item["source"] == "doctor":
            out.append({**item, "status": "verified" if entry else "new", "canonical": item["canonical"] or found})
        elif item["status"] in ("verified", "new"):
            out.append({**item, "status": "verified" if entry else "new", "canonical": found})
        else:                          # unchecked ("") or not-dictated: status kept, the page's canonical never trusted
            out.append({**item, "canonical": found if item["status"] == "not-dictated" else ""})
    return out


# --- "Remember for this clinic" -------------------------------------------------------------------------------------
# A ticked test becomes a clinic overlay row (kind "investigation"). Overlay rows are keyed like every list row
# (``overlay.entry_key_of``: whitespace-collapsed casefold), not by ``key`` above: the write and read paths refuse an
# add whose entry key is not its name's. An investigation add takes ``name`` (its canonical), never ``canonical``.

def _added(name: str, aliases: list) -> dict:
    return {"action": "add", "entry_key": overlay.entry_key_of({"canonical": name}),
            "data": {"name": name, "aliases": aliases, "category": "", "print": ""}, "base_entry": None}


def _with_alias(entry: dict, text: str, shipped: list) -> dict:
    """``entry`` (a test on the clinic's list) with ``text`` as one more alias: an ``edit`` of the shipped entry it is,
    else (a clinic add) the add rewritten under its own key. An edit carries the entry's current aliases, since an edit's
    ``aliases`` replace the entry's."""
    canonical = entry["canonical"]
    k = overlay.entry_key_of(entry)
    aliases = [a for a in entry.get("aliases") or [] if isinstance(a, str)] + [text]
    base = next((e for e in shipped if isinstance(e, dict) and isinstance(e.get("canonical"), str) and e["canonical"]
                 and overlay.entry_key_of(e) == k), None)
    if base is not None:
        return {"action": "edit", "entry_key": k, "data": {"aliases": aliases}, "base_entry": base}
    return {"action": "add", "entry_key": k, "base_entry": None,
            "data": {"name": canonical, "aliases": aliases, "category": str(entry.get("category") or ""),
                     "print": str(entry.get("print") or "")}}


def remember_row(item: dict, entries: list, shipped: list) -> "dict | None":
    """The overlay row "Remember for this clinic" records for one saved item, or None when there is nothing to learn.

    ``{"action": "add" | "edit", "entry_key", "data", "base_entry"}`` (``base_entry``: the shipped entry an edit was made
    on, else None). T = the item's text, C = its canonical (a doctor's typed full name), E_T / E_C = their entries on
    ``entries`` (the clinic's effective list):

    - E_T None, C empty or the same name as T: add T.
    - E_T None, E_C found: T becomes an alias of E_C.
    - E_T None, C set, E_C None: add C with the alias T.
    - E_T found, C empty, the same as T or naming E_T: None (nothing to learn).
    - E_T found, C set, E_C None: add C with the alias T, which the read path takes off E_T. (An investigation edit cannot
      change a canonical, so this is not an edit of E_T.)
    - E_T and E_C found and different: None (a conflict the page shows).

    A name the clinic hid (T, C, or any name of the row, blocked on ``entries`` as ``overlay.hidden_test_hit``
    compares) is never learned. Pure."""
    if not isinstance(item, dict):
        return None
    text = item.get("text").strip() if isinstance(item.get("text"), str) else ""
    canon = item.get("canonical").strip() if isinstance(item.get("canonical"), str) else ""
    if not key(text):
        return None
    if canon and key(canon) == key(text):
        canon = ""
    blocked = overlay.blocked_of(entries)
    row = _row_for(text, canon, entries, shipped)
    names = [text, canon] + ([row["data"].get("name", ""), *row["data"].get("aliases", [])] if row else [])
    return None if row is None or _hidden(names, blocked) else row


def _hidden(names, blocked) -> bool:
    """Whether any of ``names`` is a name the clinic hid, in the overlay's spelling rule, this list's (``key``: "Vit.
    D Level" is "Vit D Level") or spaceless ("K.F.T" is "kft"), so a hidden test never comes back under another
    spelling (``overlay.hidden_test_hit``)."""
    return bool(overlay.hidden_test_hit(names, blocked))


def _row_for(text: str, canon: str, entries: list, shipped: list) -> "dict | None":
    e_t = lookup_in(text, entries)
    e_c = lookup_in(canon, entries) if canon else None
    if e_t is not None:
        if not canon or e_c is not None or key(canon) == key(e_t.get("canonical")):
            return None
        return _added(canon, [text])
    if e_c is not None:
        return _with_alias(e_c, text, shipped) if isinstance(e_c.get("canonical"), str) and e_c["canonical"] else None
    return _added(canon, [text]) if canon else _added(text, [])
