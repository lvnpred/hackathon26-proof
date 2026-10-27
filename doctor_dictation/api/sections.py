"""The one reader of the section list. Today every clinic and doctor gets the shipped list; a later per-clinic or
per-doctor override changes only ``sections_for``."""
import dataclasses
import logging
from functools import lru_cache

from fastapi import APIRouter

from doctor_dictation.core import sections as core
from doctor_dictation.scope import current_scope

router = APIRouter(prefix="/api/v1", tags=["sections"])
log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _shipped() -> tuple[core.Section, ...]:
    try:
        return core.load_file()
    except (core.SectionsError, OSError, ValueError) as exc:     # ValueError covers bad JSON
        log.warning("sections.json unusable; using the built-in sections: %s", exc)
        return core.BUILT_INS


def sections_for(clinic: str | None, doctor_id: int | None = None) -> tuple[core.Section, ...]:
    return _shipped()


def active() -> tuple[core.Section, ...]:
    sc = current_scope()
    return sections_for(sc.clinic_slug if sc else None)


@router.get("/sections")
def list_sections():
    return {"sections": [dataclasses.asdict(s) for s in active()]}
