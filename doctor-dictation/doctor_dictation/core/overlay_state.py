"""The clinic overlay a request runs under, and the one effective list per (kind, overlay, shipped list) (plan PQ-f).

Split out of ``overlay`` to keep that file small; ``overlay`` re-exports every name here. The state is a ContextVar, like
``formulary.activate`` and scope.py: it follows ``asyncio.to_thread`` and a copied context, but a bare ``Thread`` starts
with the empty state (the CLI, the bench and tests see no overlay). Nothing here does I/O.
"""
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable

MAX_VIEWS = 32


@dataclass(frozen=True)
class OverlayState:
    rows: tuple = ()
    version: str = "0"

    def rows_for(self, kind: str) -> list:
        return [r for r in self.rows if r.get("kind") == kind]


def state_from_rows(rows: list) -> OverlayState:
    """``version`` is the sha256 (64 hex) over the sorted (kind, entry_key, action, data, base_sha) tuples, "0" when there
    are no rows: two clinics with the same rows share one version, hence one effective list. The rows are copied, so a
    later change to the caller's dicts cannot split the version from the rows."""
    rows = tuple(dict(r) for r in (rows or ()))
    if not rows:
        return OverlayState()
    parts = sorted(json.dumps([r.get("kind"), r.get("entry_key"), r.get("action"),
                               json.dumps(r.get("data"), sort_keys=True, ensure_ascii=False), r.get("base_sha") or ""],
                              ensure_ascii=False) for r in rows)
    return OverlayState(rows, hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest())


log = logging.getLogger(__name__)
_EMPTY = OverlayState()
_active: ContextVar = ContextVar("dd_clinic_overlay", default=None)
_warned = False


def active() -> OverlayState:
    """This request's overlay. Never set (CLI, bench, a bare thread) means empty; inside a request that is a wiring bug
    (the route lacks the overlay activation), so say so once per process instead of failing open silently. The request
    marker is ``formulary.mark_request_scoped``'s."""
    global _warned
    state = _active.get()
    if state is not None:
        return state
    from .formulary import _in_request
    if _in_request.get() and not _warned:
        _warned = True
        log.warning("clinic overlay: a request read the default EMPTY overlay; a route that reads the medicine or "
                    "investigation list is missing the overlay activation (clinic changes will not show)")
    return _EMPTY


def activate(state: OverlayState) -> None:
    """Set this request's overlay (a ContextVar: it follows ``asyncio.to_thread``; a bare ``Thread`` starts empty)."""
    _active.set(state)


_loaders: dict = {}
_views: "OrderedDict[tuple, tuple]" = OrderedDict()      # (kind, id(shipped), version) -> (shipped, effective list)
_lock = threading.Lock()


def register_shipped(kind: str, loader: Callable[[], list]) -> None:
    _loaders[kind] = loader


def shipped(kind: str) -> list:
    """The shipped list of ``kind``; [] for a kind with no loader."""
    loader = _loaders.get(kind)
    return loader() if loader else []


class View(list):
    """A clinic's effective list (a plain list of entries) plus ``blocked``: the names (``overlay._claim`` form) the
    clinic's overlay took off the list, which name matching must never move to another drug. Built once per memo slot."""
    blocked: frozenset = frozenset()


def blocked_of(lex) -> frozenset:
    """The blocked names of a list ``effective_view`` returned; empty for the shipped list itself (no overlay)."""
    return getattr(lex, "blocked", None) or frozenset()


def effective_view(kind: str, shipped: list) -> list:
    """``shipped`` itself when this request's overlay has no rows of ``kind``; else the clinic's effective list (a
    ``View`` carrying its blocked names), one object per (kind, overlay version, shipped list) so identity-keyed caches
    downstream keep hitting. Callers must not mutate it. Plan h's investigations loader calls this."""
    state = active()
    if not state.rows_for(kind):
        return shipped
    key = (kind, id(shipped), state.version)
    with _lock:
        hit = _views.get(key)
        if hit is not None and hit[0] is shipped:
            _views.move_to_end(key)
            return hit[1]
    from .overlay import effective_and_blocked
    entries, _flags, blocked = effective_and_blocked(kind, shipped, state.rows_for(kind))
    view = View(entries)
    view.blocked = blocked
    with _lock:
        hit = _views.get(key)
        if hit is not None and hit[0] is shipped:
            return hit[1]
        _views[key] = (shipped, view)     # the shipped list is held, so its id is never reused while cached
        while len(_views) > MAX_VIEWS:
            _views.popitem(last=False)
    return view
