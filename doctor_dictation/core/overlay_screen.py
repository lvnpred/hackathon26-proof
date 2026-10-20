"""The rows of the clinic list screen: shipped entries, the clinic's changes, learned names, doctors' pending suggestions
(plan PQ-f, Task 6). Pure. ``overlay.screen_rows`` is the entry point; this module only keeps ``overlay`` small."""
from . import overlay as O

BADGE = {"add": "clinic-added", "edit": "clinic-edited", "hide": "hidden"}


def _fallback(ctx, kind: str, row: dict) -> dict:
    """An entry for a row with no effective entry (refused, or a pending suggestion): what its data would make, else a stub."""
    try:
        data = O.validate_data(kind, row.get("action"), row.get("data"))
        entry = ctx.derive({"entry_key": row["entry_key"], "action": row["action"], "data": data})[0]
    except (ValueError, KeyError, TypeError):
        entry = None
    return entry or {"canonical": row["entry_key"]}


def _item(key, badge, entry, shipped, flag="", fid=None, reason="") -> dict:
    return {"entry_key": key, "badge": badge, "flag": flag, "flag_reason": reason, "entry": entry, "shipped": shipped,
            "base_sha_now": O.entry_sha(shipped) if shipped else "", "formulary_id": fid, "pending": None}


def screen_rows(kind: str, shipped: list, rows: list, learned: list, pending=()) -> list:
    """One item per entry key, flagged ones first, then by key: ``{entry_key, badge, flag, flag_reason, entry, shipped,
    base_sha_now, formulary_id, pending}``. ``rows`` are the ACTIVE overlay rows (a stored row the read path refuses is
    still listed, so it can be reset: it is flagged "shipped-changed" with the reason in ``flag_reason``), ``learned``
    the active clinic_formulary names, ``pending`` the doctors' rows below the threshold (one attaches to the item with
    its key, else it makes a ``learned`` item of its own)."""
    from .formulary import THRESHOLD
    if kind not in O.KINDS:
        raise ValueError(f"Unknown list {kind!r}.")
    slots, flags, where, ctx, _, refused = O._layout(kind, shipped, rows)
    stored = {r["entry_key"]: r for r in rows if isinstance(r, dict) and isinstance(r.get("entry_key"), str) and r["entry_key"]}
    items: dict = {}
    for key, i in ctx.pos.items():
        if key not in stored:
            items[key] = _item(key, "shipped", slots[i] or ctx.by_key[key], ctx.by_key[key])
    for key, r in stored.items():
        base = ctx.by_key.get(key) if r.get("action") != "add" else None
        i = where.get(key)
        entry = slots[i] if i is not None and slots[i] is not None else (base or _fallback(ctx, kind, r))
        if key in refused:               # set aside by the read path (a later shipped list conflicts): inert, so flag it
            items[key] = _item(key, BADGE.get(r.get("action"), "clinic-edited"), entry, base, O.SHIPPED_CHANGED,
                               reason="; ".join(refused[key]))
        else:
            items[key] = _item(key, BADGE.get(r.get("action"), "clinic-edited"), entry, base, flags.get(key, ""))
    for p in pending:
        mark = {"count": p.get("confirm_count", 0), "threshold": THRESHOLD, "action": p.get("action"), "data": p.get("data")}
        if p["entry_key"] not in items:
            items[p["entry_key"]] = _item(p["entry_key"], "learned", _fallback(ctx, kind, p), None)
        items[p["entry_key"]]["pending"] = mark
    listed = {O._claim(n) for e in slots if e is not None
              for n in [e.get("canonical"), *e.get("brands", []), *e.get("aliases", [])]}
    for name in learned:
        key = O._key(name["name"])
        if O._claim(name["name"]) not in listed and key not in items:
            entry = {"canonical": name.get("generic") or "", "brands": [name["name"]]}
            items[key] = _item(key, "learned", entry, None, fid=name.get("id"))
    return sorted(items.values(), key=lambda i: (not i["flag"], i["entry_key"]))
