"""The follow-up date for a review line typed on the page (plan I2-b)."""
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.api import visit
from doctor_dictation.core.followup import date_label, review_date

router = APIRouter()
MAX_CHARS = 1000   # a boundary cap; the parser itself reads 200


class ReviewDateRequest(BaseModel):
    review: Any = ""


@router.post("/api/v1/review-date")
def review_date_route(req: ReviewDateRequest):
    """The follow-up date for a review line typed on the page (plan I2-b). Stateless: no database, no clinic data."""
    if not isinstance(req.review, str) or len(req.review) > MAX_CHARS:
        return JSONResponse(status_code=400, content={"error": f"review must be text of at most {MAX_CHARS} characters"})
    iso = review_date(req.review, visit.today())
    return {"review_date": iso, "label": date_label(iso)}
