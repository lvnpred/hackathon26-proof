"""Cited procedure and set-up templates, loaded once and validated at import. Pure: no I/O after load."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import SETUP_CONCEPTS, TRAY_CONCEPTS

DATA = Path(__file__).parent / "sample_data"
Name = Field(min_length=1, max_length=80)
Qty = Field(ge=1, le=20)


class _Base(BaseModel):
    # Own strict base: importing journey.api.Strict would make an import cycle (api -> states -> procedures).
    model_config = ConfigDict(extra="forbid", strict=True)


class Source(_Base):
    id: int = Field(ge=1)
    url: str = Field(pattern=r"^https://\S+$", max_length=400)
    title: str = Field(min_length=1, max_length=160)
    took: str = Field(min_length=1, max_length=500)


class Instrument(_Base):
    name: str = Name
    qty: int = Qty
    concept: str | None
    source: int


class Swab(_Base):
    name: str = Name
    packs: int = Qty
    pack_size: int = Field(ge=1, le=50)
    source: int


class SetupItem(_Base):
    name: str = Name
    qty: int = Qty
    concept: str
    source: int


def _cited(rows, sources) -> None:
    ids = {s.id for s in sources}
    if len(ids) != len(sources):
        raise ValueError("Source ids must be unique.")
    for row in rows:
        if row.source not in ids:
            raise ValueError(f"{row.name}: source {row.source} is not listed.")


class Template(_Base):
    key: str = Field(min_length=1, max_length=40)
    title: str = Name
    expected_minutes: int = Field(ge=1, le=600)
    instruments: list[Instrument] = Field(max_length=40)
    swabs: list[Swab] = Field(max_length=10)
    count_points: list[str] = Field(max_length=10)
    sources: list[Source] = Field(min_length=1, max_length=10)
    note: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "Template":
        _cited([*self.instruments, *self.swabs], self.sources)
        for item in self.instruments:
            if item.concept is not None and item.concept not in TRAY_CONCEPTS:
                raise ValueError(f"{item.name}: unknown concept.")
        return self


class SetupTemplate(_Base):
    key: str = Field(min_length=1, max_length=40)
    title: str = Name
    keywords: list[str] = Field(min_length=1, max_length=10)
    items: list[SetupItem] = Field(max_length=40)
    sources: list[Source] = Field(min_length=1, max_length=10)
    note: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "SetupTemplate":
        _cited(self.items, self.sources)
        for item in self.items:
            if item.concept not in SETUP_CONCEPTS:
                raise ValueError(f"{item.name}: unknown concept.")
        return self


def _load(model, filename: str) -> dict:
    return model.model_validate(json.loads((DATA / filename).read_text())).model_dump()


PROCEDURE_TEMPLATES: dict[str, dict] = {"hernia-repair": _load(Template, "hernia-repair.json")}
SETUP_TEMPLATES: dict[str, dict] = {"saline": _load(SetupTemplate, "saline-setup.json")}


def tray_plan(key: str) -> dict:
    """The plan the doctor confirms. Raises KeyError for an unknown key."""
    template = PROCEDURE_TEMPLATES[key]
    swabs = [dict(s) for s in template["swabs"]]
    return {
        "template": key,
        "title": template["title"],
        "instruments": [{k: i[k] for k in ("name", "qty", "concept")} for i in template["instruments"]],
        "swabs": swabs,
        "swab_total": sum(s["packs"] * s["pack_size"] for s in swabs),
        "expected_minutes": template["expected_minutes"],
        "sources": [{k: s[k] for k in ("id", "title", "url")} for s in template["sources"]],
    }


def setup_for(task: dict) -> str | None:
    """The first set-up whose keyword appears in the task title."""
    title = str(task.get("title", "")).lower()
    for key, template in SETUP_TEMPLATES.items():
        if any(word in title for word in template["keywords"]):
            return key
    return None
