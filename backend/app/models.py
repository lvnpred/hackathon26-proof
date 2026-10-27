"""Pydantic models. Bad data is rejected at the edge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseIn(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    item_types: list[str] = Field(min_length=1)


class ZoneIn(StrictModel):
    name: Literal["tray", "field", "bucket"]
    polygon: list[list[float]] = Field(min_length=3)


class ZonesIn(StrictModel):
    zones: list[ZoneIn] = Field(min_length=3)


class ResolveIn(StrictModel):
    reason: str = Field(min_length=3, max_length=500)
    by: str = Field(min_length=1, max_length=80)


class Event(StrictModel):
    id: str
    case_id: str
    media_ts_ms: int = Field(ge=0)
    wall_clock: str
    source: str
    confidence: float | None = None
    evidence: list[str] = Field(default_factory=list)
    event_type: str
    payload: dict
