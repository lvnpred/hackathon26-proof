"""Fold the app owner's exported list changes into the shipped lists in the repo (plan PQ-f, Task 10). Operator-run, offline.

The owner reviews shared-list changes in the app (``api/owner_lists.py``) and exports them as
``{"kind": "medicine" | "investigation", "changes": [{"action": "add" | "edit", "entry_key", "data"}]}``.
``python -m doctor_dictation.admin apply-list-changes <file> [--confirm]`` checks the whole file, plans the change in
memory and prints it. Only with ``--confirm`` does it write: for medicines ``seed_extra.json`` then ``drugs.json`` (one
``sources`` record per file), then ``build.py --check``; for investigations ``investigations.json`` (plan h).

Medicines: ``drugs.json`` is built from ``seed_extra.json`` with ``imported.json`` laid on top (``build.layered_seed``).
So each change goes into the seed as the complete intended entry, and the plan is accepted only when rebuilding from the
new seed gives every intended entry byte for byte (``imported.json`` re-adds brands it recorded; such an edit is
refused). Nothing is written unless every change in the file is valid.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from doctor_dictation.core import overlay
from doctor_dictation.core.lexicon import build
from doctor_dictation.promotion import write_atomic

INVESTIGATIONS_JSON = build.HERE / "investigations.json"     # plan h's catalogue; does not exist before plan h
ACTIONS = ("add", "edit")
CHANGE_KEYS = {"action", "entry_key", "data"}
SOURCE_NAME, SOURCE_LICENCE = "app admin list review", "authored by the app admin; no third-party data"
DONE = "now commit drugs.json and seed_extra.json, then deploy"


# --- reading the export ----------------------------------------------------------------------------------------------

def read_changes(path) -> tuple:
    """(kind, cleaned changes). The whole file is checked first; ValueError names the first bad change by index (1-based)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except ValueError as exc:                       # JSONDecodeError and UnicodeDecodeError
        raise ValueError(f"{path} is not a JSON file: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != {"kind", "changes"}:
        raise ValueError('the file must be an object with exactly "kind" and "changes" (the app\'s export)')
    kind, changes = doc["kind"], doc["changes"]
    if kind not in overlay.KINDS:
        raise ValueError(f"unknown kind {kind!r}: use medicine or investigation")
    if not isinstance(changes, list):
        raise ValueError('"changes" must be a list')
    out, seen = [], set()
    for i, ch in enumerate(changes, 1):
        try:
            out.append(_clean_change(kind, ch, seen))
        except ValueError as exc:
            key = ch.get("entry_key") if isinstance(ch, dict) else None
            raise ValueError(f"change {i}" + (f" ({key})" if isinstance(key, str) else "") + f": {exc}") from exc
    return kind, out


def _clean_change(kind: str, ch, seen: set) -> dict:
    if not isinstance(ch, dict) or set(ch) != CHANGE_KEYS:
        raise ValueError('each change must have exactly "action", "entry_key" and "data"')
    action, key = ch["action"], ch["entry_key"]
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}: an exported change is add or edit")
    if not isinstance(key, str) or not key or len(key) > 60:
        raise ValueError("the entry key must be text of 1 to 60 characters")
    if key in seen:
        raise ValueError(f"the entry key {key!r} appears twice in the file")
    data = overlay.validate_data(kind, action, ch["data"], owner=True)
    if action == "add" and overlay._key(data["name"]) != key:
        raise ValueError(f"the entry key {key!r} does not match the name {data['name']!r}")
    seen.add(key)
    return {"action": action, "entry_key": key, "data": data}


# --- planning (pure: nothing read from or written to disk) -----------------------------------------------------------

def _sorted_keys(entry: dict) -> dict:
    """The entry as it reads back from a file written with sort_keys (seed_extra.json is)."""
    return json.loads(json.dumps(entry, sort_keys=True, ensure_ascii=False))


def _claims(entry: dict) -> set:
    """Every name an entry answers to, compared as ``determinism._exact_lookup`` compares them."""
    names = [entry.get("canonical"), entry.get("print")] + [a for f in ("brands", "aliases", "generic_hidden")
                                        for a in entry.get(f, []) if isinstance(a, str)]
    return {overlay._claim(n) for n in names if n}


def _respelt(entry: dict, base: dict) -> dict:
    """``entry`` with every name the base entry already stores kept in its stored spelling (validate_data re-cases
    names: "acarbose" comes back "Acarbose"). The same field's spelling first, then any of the base's names."""
    anywhere: dict = {}
    for f in ("canonical", "brands", "aliases", "generic_hidden"):
        for n in ([base.get(f)] if f == "canonical" else base.get(f, [])):
            if isinstance(n, str):
                anywhere.setdefault(overlay._claim(n), n)
    for f in ("brands", "aliases", "generic_hidden"):
        if isinstance(entry.get(f), list):
            own = {overlay._claim(n): n for n in base.get(f, []) if isinstance(n, str)}
            entry[f] = [own.get(overlay._claim(n), anywhere.get(overlay._claim(n), n)) if isinstance(n, str) else n
                        for n in entry[f]]
    return entry


def _safety(entry: dict, base: dict) -> dict:
    """``safety: false`` on an entry that never had the key leaves the key out (no change)."""
    if entry.get("safety") is False and "safety" not in base:
        entry.pop("safety")
    return entry


def _folded(base: dict, data: dict) -> dict:
    """A medicine add whose generic is already listed: its name, brands and aliases appended to that entry (the clinic
    overlay likewise gives such an add the listed generic's spelling). Names the entry already has are not repeated."""
    entry = copy.deepcopy(base)
    have = _claims(entry)
    for field, names in (("brands", [data["name"], *data.get("brands", [])]), ("aliases", data.get("aliases", []))):
        for n in names:
            if overlay._claim(n) not in have:
                entry.setdefault(field, []).append(n)
                have.add(overlay._claim(n))
    if "safety" in data:
        entry["safety"] = data["safety"]
    return entry


def _intended(kind: str, changes: list, entries: list) -> list:
    """[(index, change, intended entry, shipped base or None)]: every ``edit`` first, then every ``add`` (file order
    within each). Both were written against the shipped entry: an edit replaces whole lists and an add only appends, so
    applying the adds last keeps every added brand whatever order the export lists them in (it sorts by entry key).
    A later change to the same entry builds on the earlier one; the last tuple per entry holds them all."""
    listed = [e for e in entries if isinstance(e, dict) and e.get("canonical")]
    by_key = {overlay.entry_key_of(e): e for e in listed}
    by_claim = {overlay._claim(e["canonical"]): e for e in listed}
    shipped = dict(by_claim)
    out = []
    for i, ch in sorted(enumerate(changes, 1), key=lambda t: t[1]["action"] != "edit"):
        where = f"change {i} ({ch['entry_key']})"
        data = ch["data"]
        if ch["action"] == "edit":
            base = by_key.get(ch["entry_key"])
            if base is None:
                raise ValueError(f"{where}: there is no {ch['entry_key']!r} on the shipped list to edit")
            entry = overlay._merged(base, data, "")
        else:
            canonical = data["generic"] if kind == "medicine" else data["name"]
            base = by_claim.get(overlay._claim(canonical))      # spacing, hyphens and case alike
            if base is None:
                entry = overlay._built(kind, data, canonical, data["name"])
                entry.pop("clinic", None)
            elif kind == "medicine":
                entry = _folded(base, data)
            else:
                built = overlay._built(kind, data, base["canonical"], data["name"])
                built.pop("clinic", None)
                if _sorted_keys(base) != _sorted_keys(built):
                    raise ValueError(f"{where}: {base['canonical']!r} is already on the list: edit it instead of adding")
                entry = built
        first = shipped.get(overlay._claim(entry["canonical"]))
        entry = _sorted_keys(_safety(_respelt(entry, base) if base is not None else entry, first or {}))
        out.append((i, ch, entry, first))
        by_key[overlay.entry_key_of(entry)] = by_claim[overlay._claim(entry["canonical"])] = entry
    return out


def _check_names(planned: list, entries: list) -> None:
    """A name a change adds to an entry must not already belong to a different entry (it would become ambiguous)."""
    finals = {overlay._claim(e["canonical"]): e for e in entries if isinstance(e, dict) and e.get("canonical")}
    for _i, _ch, entry, _base in planned:
        finals[overlay._claim(entry["canonical"])] = entry
    owners: dict = {}
    for canon, e in finals.items():
        for c in _claims(e):
            owners.setdefault(c, []).append(e["canonical"])
    for i, ch, entry, base in planned:
        own = overlay._claim(entry["canonical"])
        new = _claims(entry) - (_claims(base) if base is not None else set())
        for c in sorted(new):
            other = [n for n in owners.get(c, []) if overlay._claim(n) != own]
            if other:
                raise ValueError(f"change {i} ({ch['entry_key']}): the name {c!r} already belongs to {other[0]!r}; "
                                 "a name may belong to one entry only")


def _layered(seed: list) -> list:
    """``build.layered_seed`` of the default seed, for a seed held in memory: ``imported.json`` laid on top."""
    if build.IMPORTED_JSON.exists():
        return build.lexicon_import.overlay(seed, build.load_seed(build.IMPORTED_JSON))
    return seed


def plan_medicines(changes: list, seed: list, current: dict) -> tuple:
    """(new seed, new drugs data), in memory. ValueError (naming the change) when any change cannot be applied as asked."""
    planned = _intended("medicine", changes, current.get("entries", []))
    _check_names(planned, current.get("entries", []))
    last = {build.canon_key(p[2]): p for p in planned}           # several changes to one entry: the last holds them all
    new_seed = {build.canon_key(e): e for e in seed}
    for _i, _ch, entry, base in last.values():
        if base is not None and _sorted_keys(base) == entry:
            continue                                  # already shipped exactly so: the seed stays as it is
        new_seed[build.canon_key(entry)] = entry
    new_seed = _sorted_keys(build.sort_entries(new_seed.values()))
    data, _changed = build.compute_merged(current, _layered(new_seed))
    got = {build.canon_key(e): e for e in data["entries"]}
    for i, ch, entry, _base in last.values():
        out = got.get(build.canon_key(entry))
        if out is None or json.dumps(out, ensure_ascii=False) != json.dumps(entry, ensure_ascii=False):
            extra = [b for b in (out or {}).get("brands", []) if b not in entry.get("brands", [])]
            if extra:
                raise ValueError(f"change {i} ({ch['entry_key']}): imported.json re-adds brand {extra[0]}; "
                                 "edit imported.json by hand")
            raise ValueError(f"change {i} ({ch['entry_key']}): rebuilding drugs.json would not give the entry as "
                             "asked (imported.json changes it); edit imported.json by hand")
    return new_seed, data


def plan_investigations(changes: list, catalogue: dict) -> dict:
    """The new ``investigations.json`` document (plan h's format): entries sorted by entry key, minor bumped on change."""
    entries = catalogue.get("entries", [])
    planned = _intended("investigation", changes, entries)
    _check_names(planned, entries)
    by_key = {overlay.entry_key_of(e): e for e in entries}
    for _i, _ch, entry, _base in planned:
        by_key[overlay.entry_key_of(entry)] = entry
    new_entries = [by_key[k] for k in sorted(by_key)]
    doc = dict(catalogue)
    doc["entries"] = new_entries
    if _sorted_keys(new_entries) != _sorted_keys(sorted(entries, key=overlay.entry_key_of)):
        doc["version"] = build.bump_minor(catalogue.get("version"))
    return doc


# --- files -----------------------------------------------------------------------------------------------------------

def load_catalogue() -> dict:
    if not INVESTIGATIONS_JSON.exists():
        raise ValueError("investigations.json does not exist yet (plan h)")
    doc = json.loads(INVESTIGATIONS_JSON.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        raise ValueError("investigations.json is not a catalogue (an object with a list of entries)")
    return doc


def _seed_text(seed: list) -> str:
    return json.dumps(seed, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _drugs_in_sync(data: dict, seed: list) -> bool:
    """``build.do_check`` in memory: rebuilding ``data`` from ``seed`` (with imported.json) changes nothing."""
    rebuilt, _ = build.compute_merged(data, _layered(seed))
    return build.serialize(rebuilt) == build.serialize(data)


def _source(sha: str, now: str) -> dict:
    record = {"id": f"admin-list-{sha[:8]}", "name": SOURCE_NAME, "licence": SOURCE_LICENCE,
              "input_sha256": sha, "merged_at": now}
    return dict(sorted(build.check_source(record).items()))


def _describe(kind: str, changes: list, before: dict) -> list:
    """One line per entry: its final result against the shipped entry (e.g. "Adalimumab: + brand Qqqbrand")."""
    last, first = {}, {}
    for p in _intended(kind, changes, before.get("entries", [])):
        first.setdefault(overlay._claim(p[2]["canonical"]), p[1])
        last[overlay._claim(p[2]["canonical"])] = p
    lines = []
    for claim, (_i, _ch, entry, base) in sorted(last.items(), key=lambda kv: min(
            i for i, c in enumerate(changes) if c is first[kv[0]])):
        ch = first[claim]                              # a new entry is named after the change that created it
        if base is None:
            brands = [b for b in entry.get("brands", []) if b != ch["data"].get("name")]
            lines.append(f"  add {ch['data']['name']}" + (f" (generic {entry['canonical']})" if kind == "medicine" else "")
                         + "".join(f"; + brand {b}" for b in brands))
            continue
        parts = []
        for field, label in (("brands", "brand"), ("aliases", "alias")):
            old, new = base.get(field, []), entry.get(field, [])
            changed = [f"+ {label} {x}" for x in new if x not in old] + [f"- {label} {x}" for x in old if x not in new]
            parts += changed or ([f"{field} reordered"] if old != new else [])
        for field in ("category", "print", "safety"):
            if base.get(field) != entry.get(field):
                parts.append(f"{field} {base.get(field)!r} -> {entry.get(field)!r}")
        lines.append(f"  {base['canonical']}: " + ("; ".join(parts) or "no difference"))
    return lines


def _apply_medicines(changes: list, sha: str, confirm: bool, now: str) -> int:
    seed_path, before_seed = build.DEFAULT_SEED, build.load_seed(build.DEFAULT_SEED)
    current = build.load_drugs()
    if build.serialize(build.compute_merged(current, build.layered_seed(seed_path))[0]) != \
            build.DRUGS_JSON.read_text(encoding="utf-8").replace("\r\n", "\n"):
        raise ValueError("drugs.json is already out of sync with seed_extra.json; run build.py --check and fix that first")
    new_seed, data = plan_medicines(changes, before_seed, current)
    if build.serialize(data) == build.serialize(current) and _seed_text(new_seed) == _seed_text(_sorted_keys(before_seed)):
        print("no change: drugs.json and seed_extra.json already hold these changes; nothing was written")
        return 0
    source = _source(sha, now)
    if any(s.get("id") == source["id"] for s in current.get("sources", [])):
        raise ValueError(f"source id {source['id']!r} is already recorded in drugs.json: this file was applied before")
    data["sources"] = [*current.get("sources", []), source]
    if not _drugs_in_sync(data, new_seed):
        raise ValueError("the planned drugs.json would not pass build.py --check; nothing was written")
    print(f"apply-list-changes (medicine): {len(changes)} change(s)")
    print("\n".join(_describe("medicine", changes, current)))
    print(f"drugs.json: entries {len(current['entries'])} -> {len(data['entries'])}, "
          f"version {current.get('version')} -> {data.get('version')}, source {source['id']}")
    if not confirm:
        print("dry run: nothing was written; add --confirm after reading the plan above")
        return 2
    old_seed, old_drugs = seed_path.read_bytes(), build.DRUGS_JSON.read_bytes()
    try:
        for target, text in ((seed_path, _seed_text(new_seed)), (build.DRUGS_JSON, build.serialize(data))):
            try:
                write_atomic(target, text)
            except OSError as exc:              # name the real file, never write_atomic's .tmp sibling
                raise ValueError(f"cannot write {target}: {exc.strerror or exc}") from exc
        ok = build.do_check(build.DEFAULT_SEED) == 0
    except BaseException:
        _restore(seed_path, old_seed, old_drugs)
        raise
    if not ok:
        _restore(seed_path, old_seed, old_drugs)
        print("error: build.py --check failed after writing; seed_extra.json and drugs.json were put back",
              file=sys.stderr)
        return 1
    print(f"wrote {seed_path.name} and {build.DRUGS_JSON.name}")
    print(DONE)
    return 0


def _restore(seed_path: Path, old_seed: bytes, old_drugs: bytes) -> None:
    seed_path.write_bytes(old_seed)
    build.DRUGS_JSON.write_bytes(old_drugs)


def _apply_investigations(changes: list, confirm: bool) -> int:
    catalogue = load_catalogue()
    doc = plan_investigations(changes, catalogue)
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    if text == json.dumps(catalogue, indent=1, ensure_ascii=False) + "\n":
        print("no change: investigations.json already holds these changes; nothing was written")
        return 0
    print(f"apply-list-changes (investigation): {len(changes)} change(s)")
    print("\n".join(_describe("investigation", changes, catalogue)))
    print(f"investigations.json: entries {len(catalogue['entries'])} -> {len(doc['entries'])}, "
          f"version {catalogue.get('version')} -> {doc.get('version')}")
    if not confirm:
        print("dry run: nothing was written; add --confirm after reading the plan above")
        return 2
    try:
        write_atomic(INVESTIGATIONS_JSON, text)
    except OSError as exc:
        raise ValueError(f"cannot write {INVESTIGATIONS_JSON}: {exc.strerror or exc}") from exc
    print(f"wrote {INVESTIGATIONS_JSON.name}")
    print("now commit investigations.json, then deploy")
    return 0


def apply(path, confirm: bool, now: str | None = None) -> int:
    """Exit code: 0 written or no change, 2 dry run, 1 refused (``error: …`` on stderr, nothing written)."""
    try:
        raw = Path(path).read_bytes()
        kind, changes = read_changes(path)
        if not changes:
            print("no change: the file lists no changes; nothing was written")
            return 0
        if kind == "investigation":
            return _apply_investigations(changes, confirm)
        stamp = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _apply_medicines(changes, hashlib.sha256(raw).hexdigest(), confirm, stamp)
    except OSError as exc:
        print(f"error: cannot read {exc.filename or path}: {exc.strerror or exc}", file=sys.stderr)
    except ValueError as exc:
        print(f"error: {exc}; nothing was written", file=sys.stderr)
    return 1


def _cmd(args) -> int:
    return apply(args.file, args.confirm)


def register(sub, commands) -> None:
    """Add apply-list-changes to the admin command line."""
    p = sub.add_parser("apply-list-changes", help="fold the app owner's exported list changes into seed_extra.json and "
                       "drugs.json (or investigations.json); a dry run unless --confirm")
    p.add_argument("file", help="the JSON file the owner exported from the app")
    p.add_argument("--confirm", action="store_true", help="without it nothing is written")
    commands["apply-list-changes"] = _cmd
