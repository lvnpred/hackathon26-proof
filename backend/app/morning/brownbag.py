"""Ground a photographed strip. The duplicate flag is decision-tier only."""

from __future__ import annotations

from app.morning.lexicon import ground


def read_strip(name: str, strength: str) -> dict:
    found = ground(name)
    return {
        "name_as_read": name.strip(),
        "strength": strength.strip(),
        "generic": found["generic"],
        "drug_class": found["drug_class"],
        "grounded": found["grounded"],
    }


def duplicate_generics(strips: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for strip in strips:
        generic = strip.get("generic")
        if generic:
            counts[generic] = counts.get(generic, 0) + 1
    return sorted(name for name, count in counts.items() if count >= 2)
