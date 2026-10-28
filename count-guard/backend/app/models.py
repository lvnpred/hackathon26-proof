"""Pydantic models. Bad data is rejected at the edge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import SAM_CONCEPTS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseIn(StrictModel):
    label: str = Field(min_length=1, max_length=120)
    item_types: list[str] = Field(min_length=1)

    @field_validator("item_types")
    @classmethod
    def known_item_types(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in SAM_CONCEPTS]
        if unknown:
            raise ValueError(f"unknown item types {unknown}; expected some of {list(SAM_CONCEPTS)}")
        return value


class ZoneIn(StrictModel):
    name: Literal["tray", "field", "bucket"]
    polygon: list[list[float]] = Field(min_length=3)

    @field_validator("polygon")
    @classmethod
    def xy_points(cls, value: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in value):
            raise ValueError("each point must be [x, y]")
        if any(not 0 <= coord <= 1 for point in value for coord in point):
            raise ValueError("points are normalized 0 to 1")
        return value


class ZonesIn(StrictModel):
    zones: list[ZoneIn] = Field(min_length=3)

    @field_validator("zones")
    @classmethod
    def one_of_each(cls, value: list[ZoneIn]) -> list[ZoneIn]:
        names = [zone.name for zone in value]
        if len(set(names)) != len(names):
            raise ValueError("zone names must not repeat")
        return value


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
