"""Step 13–14: recommendation satisfaction feedback and evaluation summary."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.entities import AspectSentiment, RecommendationFeedback
from app.models.schemas import (
    EvaluationReport,
    FeedbackOut,
    FeedbackRequest,
    ValidationReport,
)
from app.nlp.aggregate import validation_report


def _overall_satisfaction(request: FeedbackRequest) -> int:
    if request.phone_ratings:
        mean = sum(r.satisfaction for r in request.phone_ratings) / len(request.phone_ratings)
        return max(1, min(5, int(round(mean))))
    if request.satisfaction is not None:
        return int(request.satisfaction)
    raise ValueError("Provide phone_ratings (preferred) or overall satisfaction 1–5.")


def submit_feedback(db: Session, request: FeedbackRequest) -> RecommendationFeedback:
    if not request.phone_ratings and request.satisfaction is None:
        raise ValueError("Rate each recommended phone (1–5), or provide overall satisfaction.")

    ratings_payload = [r.model_dump() for r in request.phone_ratings] or None
    top_ids = list(request.top_phone_ids) or [
        r.smartphone_id for r in request.phone_ratings
    ]
    top_names = list(request.top_phone_names) or [r.name for r in request.phone_ratings]

    row = RecommendationFeedback(
        satisfaction=_overall_satisfaction(request),
        comment=(request.comment or "").strip() or None,
        weights_used=request.weights_used or None,
        top_phone_ids=top_ids or None,
        top_phone_names=top_names or None,
        phone_ratings=ratings_payload,
        candidates_considered=request.candidates_considered,
        session_id=(request.session_id or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_feedback(db: Session, *, limit: int = 50) -> list[RecommendationFeedback]:
    return list(
        db.scalars(
            select(RecommendationFeedback)
            .order_by(RecommendationFeedback.created_at.desc())
            .limit(limit)
        ).all()
    )


def _iter_phone_scores(rows: list[RecommendationFeedback]) -> list[tuple[int, int | None]]:
    """Yield (satisfaction, rank) from per-phone ratings, else session-level score."""
    out: list[tuple[int, int | None]] = []
    for row in rows:
        ratings = row.phone_ratings or []
        if isinstance(ratings, list) and ratings:
            for item in ratings:
                if not isinstance(item, dict):
                    continue
                sat = item.get("satisfaction")
                if sat is None:
                    continue
                rank = item.get("rank")
                out.append((int(sat), int(rank) if rank is not None else None))
        else:
            out.append((int(row.satisfaction), None))
    return out


def _verdict(mean: float | None) -> str | None:
    if mean is None:
        return None
    if mean >= 4.0:
        return "Good - users are generally satisfied with the ranked phones."
    if mean >= 3.0:
        return "Mixed - recommendations are acceptable but need improvement."
    return "Weak - users are often unsatisfied with the recommended phones."


def evaluation_summary(db: Session, settings: Settings | None = None) -> EvaluationReport:
    settings = settings or get_settings()
    absa_raw = validation_report(db, settings)
    absa = ValidationReport(
        reviews_compared=int(absa_raw["reviews_compared"]),
        agreement_rate=float(absa_raw["agreement_rate"]),
        mean_absolute_error=float(absa_raw["mean_absolute_error"]),
        by_rating=absa_raw["by_rating"],
        note=str(absa_raw["note"]),
    )

    method_rows = db.execute(
        select(AspectSentiment.method, func.count(AspectSentiment.id)).group_by(
            AspectSentiment.method
        )
    ).all()
    method_breakdown = {str(method): int(count) for method, count in method_rows}

    all_rows = list(db.scalars(select(RecommendationFeedback)).all())
    feedback_rows = list_feedback(db, limit=20)
    scores = _iter_phone_scores(all_rows)

    distribution = {str(i): 0 for i in range(1, 6)}
    by_rank: dict[int, list[int]] = defaultdict(list)
    for sat, rank in scores:
        distribution[str(sat)] = distribution.get(str(sat), 0) + 1
        if rank is not None:
            by_rank[rank].append(sat)

    mean = (sum(s for s, _ in scores) / len(scores)) if scores else None
    mean_by_rank = {
        str(rank): round(sum(vals) / len(vals), 3)
        for rank, vals in sorted(by_rank.items())
        if vals
    }
    top1_vals = by_rank.get(1) or []
    top1_mean = round(sum(top1_vals) / len(top1_vals), 3) if top1_vals else None
    high_rate = (
        round(sum(1 for s, _ in scores if s >= 4) / len(scores), 4) if scores else None
    )

    return EvaluationReport(
        absa_engine=settings.resolved_absa_engine(),
        absa_method_breakdown=method_breakdown,
        absa_validation=absa,
        feedback_count=len(all_rows),
        phone_rating_count=len(scores),
        mean_satisfaction=round(float(mean), 3) if mean is not None else None,
        satisfaction_distribution=distribution,
        mean_satisfaction_by_rank=mean_by_rank,
        top1_mean_satisfaction=top1_mean,
        high_satisfaction_rate=high_rate,
        evaluation_verdict=_verdict(mean),
        recent_feedback=[FeedbackOut.model_validate(row) for row in feedback_rows],
    )
