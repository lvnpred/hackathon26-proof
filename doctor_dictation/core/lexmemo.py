"""Race-free, few-slot caches keyed on the identity of a lexicon list (plan PQ-f). Stdlib only.

Each clinic overlay gives a request its own effective list object (``overlay_state.effective_view``), so one process
serves several lists at once from worker threads. A single-slot cache that checks its global and then reads it again
can hand one clinic another clinic's map. ``per_lexicon`` reads its slot once, under a lock, and checks that the hit
was built for this very list object.
"""
import threading
from typing import Callable, TypeVar

T = TypeVar("T")
MAX_SLOTS = 32         # distinct lists kept per cache (= overlay_state.MAX_VIEWS); the least recently used one is dropped

_lock = threading.Lock()


def per_lexicon(slot: dict, lex: list, build: Callable[[], T]) -> T:
    """The value ``build()`` returns for ``lex``, built once per list object and kept in ``slot`` (a plain dict owned by
    the caller: ``id(lex)`` -> ``(lex, value)``). The entry holds ``lex`` itself, so its ``id`` cannot be reused by
    another list while cached. Equal content in a new list object is a miss (identity, not equality). ``build`` runs
    outside the lock (it may call other ``per_lexicon`` caches); when two threads build the same list at once, the first
    stored value wins and both return it. Callers must not mutate the value."""
    key = id(lex)
    with _lock:
        hit = slot.get(key)
        if hit is not None and hit[0] is lex:
            slot[key] = slot.pop(key)          # most recently used goes last
            return hit[1]
    value = build()
    with _lock:
        hit = slot.get(key)
        if hit is not None and hit[0] is lex:
            return hit[1]
        slot.pop(key, None)                    # defensive: re-insert so the new entry is the most recent
        slot[key] = (lex, value)
        while len(slot) > MAX_SLOTS:
            del slot[next(iter(slot))]
    return value
