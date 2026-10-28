"""The labelled context groups under the Spell it list (plan SH-B2). Pure: the caller reads the database.

Context only adds a labelled group below the sound-alikes and breaks near-ties among clinic names (S1); it never
changes a row."""
from collections.abc import Callable
from dataclasses import dataclass

GROUP_CAP = 3                       # names per group


@dataclass(frozen=True)
class CtxName:
    term_id: int
    key: str                        # spoken.key(spoken)
    name: str                       # spoken_terms.spoken: "Urimax"
    generic: str
    weight: float                   # usage_score(uses, last_used_at, today)


def prefer_keys(names, linked_by_key: dict[str, set[int]], patient_keys: set[str]) -> frozenset[str]:
    """Keys that break near-ties among clinic names: every linked name's key and this patient's earlier keys."""
    linked = set().union(*linked_by_key.values()) if linked_by_key else set()
    return frozenset({n.key for n in names if n.term_id in linked} | set(patient_keys))


def _top(names) -> list[CtxName]:
    return sorted(names, key=lambda n: (-n.weight, n.name.casefold(), n.name))[:GROUP_CAP]


def _item(n: CtxName) -> dict:
    return {"name": n.name, "generic": n.generic}


def groups(names, linked_by_key: dict[str, set[int]], lines: dict[str, str], patient_keys: set[str],
           skip_key: str, blocked: Callable[[str], bool]) -> list[dict]:
    """[{"kind": "diagnosis"|"patient", "for": line, "items": [{"name", "generic"}]}], empty groups left out.

    ``for`` is the sheet's own line when exactly one diagnosis key contributed a name, else "". A name shown in the
    diagnosis group is not repeated in the patient group; the row's own name (``skip_key``) and a blocked name never show."""
    ok = [n for n in names if n.key != skip_key and not blocked(n.name)]
    contrib = {k: [n for n in ok if n.term_id in ids] for k, ids in linked_by_key.items()}
    shown = _top({n.term_id: n for ns in contrib.values() for n in ns}.values())
    out = []
    if shown:
        ids = {n.term_id for n in shown}
        used = [k for k, ns in contrib.items() if any(n.term_id in ids for n in ns)]
        out.append({"kind": "diagnosis", "for": lines.get(used[0], "") if len(used) == 1 else "",
                    "items": [_item(n) for n in shown]})
    seen = {n.term_id for n in shown}
    mine = _top(n for n in ok if n.key in patient_keys and n.term_id not in seen)
    if mine:
        out.append({"kind": "patient", "for": "", "items": [_item(n) for n in mine]})
    return out
