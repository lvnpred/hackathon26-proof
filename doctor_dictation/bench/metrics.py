"""Scoring for the STT benchmark. Pure: stdlib only.

Normalisation, both sides: lowercase; apostrophes dropped; other punctuation and
symbols become spaces ("1-0-1" -> "1 0 1"); whitespace collapsed. Number words are
left as-is ("five hundred" != "500").
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence


def normalise(text: str) -> str:
    lowered = text.lower().replace("'", "").replace("’", "")
    return " ".join("".join(" " if unicodedata.category(c)[0] in "PS" else c for c in lowered).split())


def _edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    """Word-level Levenshtein: insert, delete, substitute each cost 1."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Edit distance / reference words (may exceed 1.0). Empty reference: 0.0 if the
    hypothesis is empty too, else 1.0 (defined, not a division by zero)."""
    ref, hyp = normalise(reference).split(), normalise(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def drug_recall(reference: str, hypothesis: str, drug_names: Iterable[str]) -> tuple[int, int]:
    """(found, expected) over distinct names: expected = in the reference, found =
    also in the hypothesis. Whole-word, case-insensitive; a multi-word name needs
    the same words in order ("dolo" != "dolor"; "calcium carbonate" != "calcium and carbonate")."""
    ref, hyp = f" {normalise(reference)} ", f" {normalise(hypothesis)} "
    expected = [n for n in {normalise(n) for n in drug_names} - {""} if f" {n} " in ref]
    return sum(f" {n} " in hyp for n in expected), len(expected)
