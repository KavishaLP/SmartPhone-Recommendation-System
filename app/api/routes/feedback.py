"""Step 13–14 endpoints: recommendation satisfaction + evaluation summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.schemas import EvaluationReport, FeedbackOut, FeedbackRequest
from app.services.feedback import evaluation_summary, list_feedback, submit_feedback

router = APIRouter(prefix="/feedback", tags=["evaluation"])


@router.post("", response_model=FeedbackOut, summary="Submit recommendation satisfaction (1–5)")
def post_feedback(request: FeedbackRequest, db: Session = Depends(get_db)) -> FeedbackOut:
    """Step 13 — store per-phone (and overall) satisfaction for the Top-N ranking."""
    try:
        row = submit_feedback(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FeedbackOut.model_validate(row)


@router.get("", response_model=list[FeedbackOut], summary="List recent satisfaction ratings")
def get_feedback(
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
) -> list[FeedbackOut]:
    return [FeedbackOut.model_validate(row) for row in list_feedback(db, limit=limit)]


@router.get(
    "/evaluation",
    response_model=EvaluationReport,
    summary="ABSA validity + recommendation satisfaction (Step 14)",
)
def get_evaluation(db: Session = Depends(get_db)) -> EvaluationReport:
    return evaluation_summary(db, get_settings())
