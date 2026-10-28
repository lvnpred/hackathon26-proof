"""A clinic's overlay (add / edit / hide) laid over the shipped medicine and investigation lists (plan PQ-f). Pure.

``effective_entries`` never changes a shipped entry: those dicts are shared by every clinic. Each entry it changes is a
new dict with new lists; an entry it does not touch is the shipped object itself. Callers must NOT mutate the returned
entries (or their lists): an untouched one is the shipped object every clinic shares.

A name the clinic adds or lists is the clinic's: it is taken out of every other entry's brands, aliases and
``generic_hidden`` (space, hyphen, dash and case alike, as ``determinism._exact_lookup`` matches), so it never becomes
ambiguous (``surface.ambiguous_names``). When two clinic rows list one name, the row with the greater ``entry_key`` keeps
it. A name a ``"safety": true`` entry claims is never taken (the clinic's change is dropped and flagged instead). A
clinic generic spelt like a listed one (case, spacing, hyphens) takes the listed spelling. ``conflicts`` names the rows
the write API refuses (and ``effective_entries`` skips): a generic that is a brand or alias, an add of a listed generic,
an add whose key is not its name's key, a name that is another entry's generic, a hide of an unknown key.
"""
import copy
import functools
import hashlib
import json
import re

from .combo import SEP_CHARS
from .lexicon.build_investigations import key as _ix_key
from .overlay_state import (OverlayState, View, _loaders, _views, activate, active, blocked_of,  # noqa: F401
                            effective_view, register_shipped, shipped, state_from_rows)
from .overlay_validate import (ACTIONS, KINDS, MAX_CATEGORY, MAX_GENERIC, MAX_LIST, MAX_PRINT,  # noqa: F401
                               _allowed, _generic, _name, _names, _text, validate_data)

SHIPPED_CHANGED, SAFETY_OVERRIDE = "shipped-changed", "safety-override"
_SEP_RE = re.compile(rf"[{SEP_CHARS}]+")


def _key(name) -> str:
    from .formulary import key       # lazy: determinism will import this module (plan f, Task 4)
    return key(name)


def entry_key_of(entry: dict) -> str:
    return _key(entry["canonical"])


def entry_sha(entry: dict) -> str:
    text = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- shared pieces ---------------------------------------------------------------------------------------------------

def _claim(name) -> str:
    """The key ``determinism._exact_lookup`` compares: case, spacing, a trailing "." and space/hyphen/dash ignored."""
    return _claim_text(name if isinstance(name, str) else str(name or ""))


@functools.lru_cache(maxsize=16384)
def _claim_text(text: str) -> str:
    return _SEP_RE.sub(" ", text.strip()).rstrip(".").strip().casefold()


def _built(kind: str, data: dict, canonical: str, name: str = "") -> dict:
    if kind == "medicine":
        brands = [name] if name and _key(name) != _key(canonical) else []
        brands += [b for b in data.get("brands", []) if _key(b) not in {_key(x) for x in brands} | {_key(canonical)}]
        entry = {"canonical": canonical, "brands": brands, "aliases": list(data.get("aliases", [])),
                 "forms": [], "strengths": [], "clinic": True}
    else:
        entry = {"canonical": canonical, "aliases": list(data.get("aliases", [])),
                 "category": data.get("category", ""), "print": data.get("print", ""), "clinic": True}
    if "safety" in data:
        entry["safety"] = data["safety"]
    return entry


def _merged(base: dict, data: dict, generic: str) -> dict:
    """``base`` with the edit applied. A rename always keeps the old generic as an alias (even when the edit sends its own
    aliases), so a dictated old name still finds this entry instead of a look-alike (Levofloxacin -> Ofloxacin)."""
    entry = copy.deepcopy(base)
    if generic:
        entry["canonical"] = generic
    for field in ("aliases", "brands", "category", "print", "safety"):
        if field in data:
            entry[field] = copy.deepcopy(data[field])
    old = base.get("canonical")
    if generic and _claim(generic) != _claim(old) and all(_claim(a) != _claim(old) for a in entry.get("aliases", [])):
        entry["aliases"] = [*entry.get("aliases", []), old]
    if "generic_hidden" in entry and "brands" in data:
        keep = {_claim(b) for b in entry.get("brands", [])}
        entry["generic_hidden"] = [b for b in entry["generic_hidden"] if _claim(b) in keep]
    return entry


def _clinic_names(kind: str, action: str, data: dict) -> list:
    """The names this row puts on the clinic's entry (a medicine's generic is not one: other brands of it stay)."""
    names = [data["name"]] if action == "add" and "name" in data else []
    names += data.get("aliases", []) + data.get("brands", [])
    if kind == "medicine" and action == "add" and _key(data["name"]) == _key(data.get("generic", "")):
        names = names[1:]
    return names


def _without(entry: dict, taken: set) -> dict:
    out = copy.deepcopy(entry)
    for field in ("aliases", "brands", "generic_hidden"):
        if isinstance(out.get(field), list):
            out[field] = [a for a in out[field] if _claim(a) not in taken]
    return out


def _names_of(entry: dict) -> set:
    return {_claim(a) for f in ("aliases", "brands", "generic_hidden") for a in entry.get(f, []) if isinstance(a, str)}


def _valid_rows(kind: str, rows) -> list:
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or not isinstance(r.get("entry_key"), str) or not r["entry_key"]:
            continue
        try:
            out.append({**r, "data": validate_data(kind, r.get("action"), r.get("data"))})
        except ValueError:
            continue                     # a row the boundary would refuse never reaches the list
    return sorted(out, key=lambda r: r["entry_key"])


class _Context:
    """The shipped list plus the rows accepted so far (no claims applied): what a row's ``conflicts`` are checked against.

    Rows are accepted greedily in ``entry_key`` order, so of two rows that conflict with each other the first stays."""

    def __init__(self, kind: str, shipped: list):
        self.kind, self.by_key, self.pos, self.derived = kind, {}, {}, {}
        self.spelling: dict = {}        # claim of a generic -> the spelling the list already uses
        self.generics: dict = {}        # claim -> [(source, canonical)]
        self.names: dict = {}           # claim -> [(source, canonical, "brand" | "alias")]
        self.sources: dict = {}         # source -> [(index dict, claim)], to take an edited entry out of the index
        for i, e in enumerate(shipped):
            k = entry_key_of(e) if isinstance(e, dict) and e.get("canonical") else ""
            if not k:
                continue
            if k not in self.by_key:
                self.by_key[k], self.pos[k] = e, i
            self.spelling.setdefault(_claim(e["canonical"]), e["canonical"])
            self._index(("s", k), e)
        self.shipped_generics = set(self.generics)
        self.shipped_tests = {_spaceless(n) for e in shipped if isinstance(e, dict) and e.get("canonical")
                              for n in (e["canonical"], e.get("print"), *(e.get("aliases") or [])) if _spaceless(n)} \
            if kind == "investigation" else set()  # every shipped name of a test, spaceless: "USG/KUB", "R.F.T" are taken

    def _index(self, source, e) -> None:
        refs = self.sources.setdefault(source, [])
        self.generics.setdefault(_claim(e["canonical"]), []).append((source, e["canonical"]))
        refs.append((self.generics, _claim(e["canonical"])))
        for label, field in (("brand", "brands"), ("alias", "aliases")):
            for a in e.get(field, []):
                if isinstance(a, str):
                    self.names.setdefault(_claim(a), []).append((source, e["canonical"], label))
                    refs.append((self.names, _claim(a)))

    def _unindex(self, source) -> None:
        for index, c in self.sources.pop(source, []):
            index[c] = [x for x in index.get(c, []) if x[0] != source]

    def accept(self, row: dict) -> None:
        entry, _base = self.derive(row)
        if row["action"] != "add" and row["entry_key"] in self.by_key:
            self._unindex(("s", row["entry_key"]))
        if entry is not None:
            self._index(("r", row["entry_key"]), entry)
            if self.kind == "medicine":
                self.spelling.setdefault(_claim(entry["canonical"]), entry["canonical"])
        self.derived[row["entry_key"]] = entry

    def generic(self, data: dict) -> str:
        g = data.get("generic", "")
        return self.spelling.get(_claim(g), g) if g else ""

    def derive(self, row: dict):
        """(entry or None, shipped base or None) for one valid row, before claims and flags."""
        key, action, data = row["entry_key"], row["action"], row["data"]
        if action == "add":
            canon = self.generic(data) if self.kind == "medicine" else data["name"]
            return _built(self.kind, data, canon, data["name"]), None
        base = self.by_key.get(key)
        if action == "hide":
            return None, base
        if base is None:
            return (_built(self.kind, data, self.generic(data)) if data.get("generic") else None), None
        return _merged(base, data, self.generic(data) if self.kind == "medicine" else ""), base

    def conflicts(self, row: dict) -> list:
        key, action, data = row["entry_key"], row["action"], row["data"]
        if action == "hide":
            return [] if key in self.by_key else [f"There is no {key!r} on the list to hide"]
        skip = {("r", key)} | ({("s", key)} if action != "add" else set())
        own = self.derive(row)[0] or self.by_key.get(key) or {}
        own_claim = _claim(own.get("canonical"))
        out = []
        if action == "add" and _key(data["name"]) != key:
            out.append(f"The entry key {key!r} does not match the name {data['name']!r}")
        listed = action == "add" and (_claim(data["name"]) in self.shipped_generics
                                      or _spaceless(data["name"]) in self.shipped_tests)
        if listed:
            out.append(f"'{data['name']}' is already on the list — edit it instead")
        g = data.get("generic", "")
        base = self.by_key.get(key) if action != "add" else None
        own_names = [(None, base["canonical"], label) for label, field in (("brand", "brands"), ("alias", "aliases"))
                     for a in (base or {}).get(field, []) if _claim(a) == _claim(g)] if g else []
        for source, canon, label in own_names + (self.names.get(_claim(g), []) if g else []):
            if source not in skip and _claim(canon) != _claim(g):
                out.append(f"'{g}' is a {label} of {canon} — choose the generic")
                break
        mine = _clinic_names(self.kind, action, data)
        if action == "edit":             # names carried over from the shipped entry count too (a renamed generic)
            mine += [a for f in ("aliases", "brands") for a in own.get(f, []) if isinstance(a, str)]
        for n in dict.fromkeys(mine):
            if (listed and n == data.get("name")) or _claim(n) == own_claim:
                continue
            hit = [c for s, c in self.generics.get(_claim(n), []) if s not in skip and _claim(c) != own_claim]
            if hit:
                out.append(f"'{n}' is the generic {hit[0]} on the list — it cannot also be a name of {own.get('canonical')}")
        return out


def conflicts(kind: str, shipped: list, rows: list, row: dict) -> list:
    """Readable reasons the write API refuses ``row`` against the shipped list and the clinic's other ``rows``; [] if none.

    Write and read agree by construction: the read path's ``_settled`` runs on ``rows`` with ``row`` in place of its key.
    ``row`` is refused unless it is accepted there AND every row accepted before still is (the message names the row it
    would set aside). Invalid data gives the ``validate_data`` message. Pure: nothing passed in is changed."""
    if kind not in KINDS:
        raise ValueError(f"Unknown list {kind!r}.")
    if not isinstance(row, dict) or not isinstance(row.get("entry_key"), str) or not row["entry_key"]:
        return ["The entry key is missing."]
    try:
        r = {**row, "data": validate_data(kind, row.get("action"), row.get("data"))}
    except ValueError as e:
        return [str(e)]
    key = r["entry_key"]
    others = [x for x in rows or [] if not (isinstance(x, dict) and x.get("entry_key") == key)]
    _ctx, before, _ = _trace(kind, shipped, rows)     # the rows as they are now, the old version of ``key`` included
    if r["action"] == "hide" and any(x["entry_key"] == key and x["action"] == "add" for x in before):
        return ["This is your own addition \u2014 use Reset to remove it"]
    if r["action"] == "hide" and kind == "medicine":
        users = _generic_users(shipped, before, key)
        if users:
            canon, names = users
            return [f"{canon} is the generic of {names} on your list: edit or reset {names} first"]
    if r["action"] == "add":             # two adds spelt alike (Zerodol-P, Zerodol P, Zerodol-P.) would be one name
        same = _ix_key if kind == "investigation" else _claim   # a test is looked up by its own key (C&S = C and S)
        twin = next((x for x in _valid_rows(kind, others)
                     if x["action"] == "add" and same(x["data"]["name"]) == same(r["data"]["name"])), None)
        if twin is not None:
            return [f"'{r['data']['name']}' is already on your list as {twin['data']['name']}: edit it"]
    hidden = _hidden_test_name(kind, shipped, others, r)     # first: "hidden" says more than "already on the list"
    if hidden:
        return [f"{hidden} is hidden on your list: Reset it first"]
    _ctx, after, refused = _trace(kind, shipped, others + [r])
    if key in refused:
        return refused[key]
    hidden = _hidden_generic(kind, shipped, others, r)
    if hidden:
        return [f"{hidden} is hidden on your list: Reset it first"]
    kept = {x["entry_key"] for x in after}
    return [f"This change would set aside the clinic's entry {x['entry_key']!r}: {refused[x['entry_key']][0]}"
            for x in before if x["entry_key"] not in kept and x["entry_key"] != key]


def _hidden_generic(kind: str, shipped: list, others: list, row: dict) -> str:
    """The generic (or the first of its " + " components) of an add or edit that names a medicine the clinic took off
    its list (blocked by ``others``, the clinic's rows without ``row``'s key), else "". Such a row would put the hidden
    canonical back on the effective list and undo the hide, for the admin, doctor learning and imports alike."""
    g = row["data"].get("generic", "") if kind == "medicine" and row["action"] != "hide" else ""
    if not g:
        return ""
    blocked = effective_and_blocked(kind, shipped, others)[2]
    return next((p for p in [g, *(x.strip() for x in g.split("+"))] if p and _claim(p) in blocked), "")


def _hidden_test_name(kind: str, shipped: list, others: list, row: dict) -> str:
    """The first name of an investigation add or edit (its name, print form or an alias) that the clinic hid (blocked by
    ``others``, the clinic's rows without ``row``'s key), compared as ``hidden_test_hit`` does, else "". Such a name would
    make a hidden test's name find another test."""
    if kind != "investigation" or row["action"] == "hide":
        return ""
    blocked = effective_and_blocked(kind, shipped, others)[2]
    if not blocked:
        return ""
    data = row["data"]
    return hidden_test_hit([data.get("name", ""), data.get("print", ""), *data.get("aliases", [])], blocked)


IX_QUALIFIERS = ("repeat", "follow up", "followup")      # a leading word ``investigations.lookup`` strips
_IX_FRAME = frozenset("test tests level levels profile".split())   # words a hidden name can be wrapped in: "RFT test"


def _test_forms(name: str) -> list:
    """``name`` plus its forms without a leading qualifier ("Repeat KFT") and without frame words ("Rft Profile")."""
    k = _ix_key(name)
    bare = next((k[len(q) + 1:] for q in IX_QUALIFIERS if k.startswith(q + " ")), k)
    out = [name]
    for f in (bare, " ".join(w for w in k.split() if w not in _IX_FRAME), " ".join(w for w in bare.split() if w not in _IX_FRAME)):
        if f and f not in out:
            out.append(f)
    return out


def _spaceless(name) -> str:
    """A test name as ``lookup`` matches a spelled-out one: its investigation key without spaces ("R.F.T" -> "rft")."""
    return _ix_key(name if isinstance(name, str) else "").replace(" ", "")


def hidden_test_hit(names, blocked) -> str:
    """The first of ``names`` that is a hidden test name in ``blocked`` (``_claim`` form), compared as the overlay spells
    names (``_claim``), as the test list looks them up (``_ix_key``: "Vit. D Level" is "Vit D Level") and spaceless, as a
    spelled-out lookup matches ("K.F.T", "R F T" are "kft", "rft"); each also without a leading qualifier and without
    frame words (``_test_forms``: "Repeat KFT", "RFT test"), else "". Over-blocking is the safe direction."""
    if not blocked:
        return ""
    bk = {_ix_key(b) for b in blocked}
    compact = {c.replace(" ", "") for c in bk if c}
    return next((n for n in names if isinstance(n, str) and n
                 and any(_claim(f) in blocked or _ix_key(f) in bk or _spaceless(f) in compact for f in _test_forms(n))), "")


def _generic_users(shipped: list, accepted: list, key: str):
    """(canonical, "A, B") when clinic rows ``accepted`` on the read path (other than ``key``'s) use the shipped entry
    ``key`` as their generic or one of its components, else None. Hiding it would leave it on the list through them (the
    mirror of ``_hidden_generic``); a pending doctor row is not counted (learning skips a hidden generic)."""
    base = next((e for e in shipped if isinstance(e, dict) and e.get("canonical") and entry_key_of(e) == key), None)
    if base is None:
        return None
    c = _claim(base["canonical"])
    names = [x["data"].get("name") or x["entry_key"] for x in accepted
             if x["entry_key"] != key and x["action"] != "hide"
             and c in {_claim(p) for p in [x["data"].get("generic", ""), *str(x["data"].get("generic", "")).split("+")] if p}]
    return (base["canonical"], ", ".join(names)) if names else None


# --- effective_entries -----------------------------------------------------------------------------------------------

def _trace(kind: str, shipped: list, rows: list):
    """(context, accepted rows, {refused key: reasons}): each valid row in ``entry_key`` order is accepted unless it
    conflicts with the shipped list or a row accepted before it. The one procedure both read and write use."""
    ctx, ok, refused = _Context(kind, shipped), [], {}
    for r in _valid_rows(kind, rows):
        why = ctx.conflicts(r)
        if why:
            refused[r["entry_key"]] = why
        else:
            ctx.accept(r)
            ok.append(r)
    return ctx, ok, refused


def _settled(kind: str, shipped: list, rows: list):
    """(context, accepted rows) for the read path (``_trace`` without the reasons)."""
    return _trace(kind, shipped, rows)[:2]


def refused_rows(kind: str, shipped: list, rows: list) -> dict:
    """{entry key: reasons} of the stored rows the read path sets aside (inert: a later shipped list conflicts)."""
    return _trace(kind, shipped, rows)[2]


def claimant_sha(entries, name) -> str:
    """``entry_sha`` of the first of ``entries`` listing ``name`` as a brand, alias or hidden generic; "" when none does."""
    c = _claim(name)
    return next((entry_sha(e) for e in entries if isinstance(e, dict) and c in _names_of(e)), "")


def _apply(ctx: _Context, row: dict):
    """(entry or None, base, flag reason or None) for one row without conflicts."""
    base = ctx.by_key.get(row["entry_key"]) if row["action"] != "add" else None
    if base is not None and base.get("safety") is True:
        return base, base, SAFETY_OVERRIDE
    entry, base = ctx.derive(row)
    if row["action"] == "add":           # an add over a shipped name (a doctor's brand override) records that entry's sha
        sha = str(row.get("base_sha") or "")
        moved = sha and claimant_sha(ctx.by_key.values(), row["data"].get("name", "")) != sha
        return entry, None, SHIPPED_CHANGED if moved else None
    if base is None:                     # the shipped entry this edit was made on is gone
        return entry, None, SHIPPED_CHANGED
    return entry, base, SHIPPED_CHANGED if entry_sha(base) != str(row.get("base_sha") or "") else None


def _layout(kind: str, shipped: list, rows: list) -> tuple:
    """(slots, flag reasons by key, slot index by row key, context, accepted rows, {refused key: reasons}): the one pass
    ``effective_entries`` and ``screen_rows`` share. A slot is the shipped position (replaced by a NEW dict, or None when
    dropped) or an appended entry."""
    ctx, valid, refused = _trace(kind, shipped, rows)
    slots = list(shipped)                # shipped order; a slot is replaced by a NEW dict, or None when dropped
    flags: dict = {}
    where: dict = {}
    clinic = []                          # (row key, slot index, claims, base) per clinic entry, in row order
    for row in valid:
        entry, base, reason = _apply(ctx, row)
        if reason:
            flags[row["entry_key"]] = reason
        if base is not None:
            i = ctx.pos[row["entry_key"]]
            slots[i] = entry
        elif entry is not None:
            slots.append(entry)
            i = len(slots) - 1
        else:
            continue
        where[row["entry_key"]] = i
        if entry is not None and entry is not base:
            clinic.append((row["entry_key"], i, {_claim(n) for n in _clinic_names(kind, row["action"], row["data"])}, base))
    clinic = _yield_to_safety(slots, clinic, flags)
    _take_names(slots, clinic)
    return slots, flags, where, ctx, valid, refused


def effective_entries(kind: str, shipped: list, rows: list) -> tuple:
    """(entries, flags): the shipped list with the clinic's active rows applied. A flag is {"entry_key", "reason"}:
    "shipped-changed" (the shipped entry changed or went since the clinic's edit; the clinic still wins) or
    "safety-override" (a "safety": true shipped entry wins over the clinic's change). Flags sorted, one per key.
    Rows with ``conflicts`` are skipped. Callers must not mutate the returned entries (see the module docstring)."""
    return effective_and_blocked(kind, shipped, rows)[:2]


def _all_names(entries) -> set:
    return {_claim(n) for e in entries if isinstance(e, dict)
            for n in (e.get("canonical"), *(e.get("aliases") or []), *(e.get("brands") or []), *(e.get("generic_hidden") or []))
            if isinstance(n, str) and _claim(n)}


def effective_and_blocked(kind: str, shipped: list, rows: list) -> tuple:
    """(entries, flags, blocked): ``effective_entries`` plus the names (``_claim`` form) the overlay took off the list.

    Blocked = every name of the shipped list (a hidden entry's, a brand or alias an edit dropped) and, for medicines only,
    every name of a clinic row the read path sets aside (inert: blocked so fuzzy matching never routes it to a look-alike
    drug), LESS every name still on the effective list (a name a clinic entry took, or a renamed generic kept as an alias,
    still finds its entry). An investigation row set aside is not blocked (tests match exactly): the list screen flags
    it "shipped-changed" with the reason (``overlay_screen``), so the clinic can Reset it. Name matching never moves a blocked name to another
    drug: it stays as dictated and grades unknown-medicine (``drugnames``)."""
    if kind not in KINDS:
        raise ValueError(f"Unknown list {kind!r}.")
    slots, flags, _where, _ctx, _valid, refused = _layout(kind, shipped, rows)
    entries = [e for e in slots if e is not None]
    inert = {_claim(n) for r in _valid_rows(kind, rows) if r["entry_key"] in refused
             for n in [r["data"].get("name", ""), *_clinic_names(kind, r["action"], r["data"])] if _claim(n)} \
        if kind == "medicine" else set()   # a test matches exactly (never fuzzy): a set-aside row is only flagged
    blocked = frozenset((_all_names(shipped) | inert) - _all_names(entries))
    return entries, [{"entry_key": k, "reason": flags[k]} for k in sorted(flags)], blocked


def screen_rows(kind: str, shipped: list, rows: list, learned: list, pending=()) -> list:
    """The clinic list screen's items (see ``overlay_screen``)."""
    from .overlay_screen import screen_rows as build
    return build(kind, shipped, rows, learned, pending)


def _canon(slot) -> str:
    return _claim(slot.get("canonical")) if isinstance(slot, dict) else ""


def _yield_to_safety(slots, clinic, flags) -> list:
    """A clinic entry listing a name a safety entry claims is dropped (an add) or undone (an edit), flagged."""
    kept = []
    for key, i, claims, base in clinic:
        if any(e is not None and j != i and e.get("safety") is True and _canon(e) != _canon(slots[i])
               and _names_of(e) & claims for j, e in enumerate(slots)):
            slots[i] = base
            flags[key] = SAFETY_OVERRIDE
        else:
            kept.append((key, i, claims, base))
    return kept


def _take_names(slots, clinic) -> None:
    """Each claimed name goes to one clinic entry (the greatest key; rows are in key order) and leaves every other entry
    that has a different generic: shipped and clinic alike."""
    winner = {}
    for _key_, i, claims, _base in clinic:
        for c in claims:
            winner[c] = i
    for j, e in enumerate(slots):
        if e is None:
            continue
        taken = {c for c in _names_of(e) if c in winner and winner[c] != j and _canon(slots[winner[c]]) != _canon(e)}
        if taken:
            slots[j] = _without(e, taken)
