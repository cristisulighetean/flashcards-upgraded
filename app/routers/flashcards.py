"""
Flashcards router — generation, retrieval, adaptive priority study flow.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import get_settings
from app.database import get_db
from app.models.document import Document
from app.models.flashcard import Flashcard
from app.schemas.flashcard import (
    FlashcardListResponse,
    FlashcardResponse,
    GenerateFlashcardsRequest,
)
from app.services.openai_service import generate_flashcards_from_text, LLMRateLimitError
from app.services.priority import NEEDS_FOCUS_THRESHOLD, priority_score_expr

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/flashcards", tags=["Flashcards"])


def _flashcard_to_response(
    flashcard: Flashcard, 
    filename: str | None = None, 
    priority: float = 0.0
) -> FlashcardResponse:
    """Convert a Flashcard ORM object to a FlashcardResponse, attaching document metadata and priority."""
    data = FlashcardResponse.model_validate(flashcard)
    data.document_filename = filename
    data.priority_score = round(priority, 2)
    return data


@router.post(
    "/generate",
    response_model=FlashcardListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate flashcards from an uploaded document",
)
async def generate_flashcards(
    request: GenerateFlashcardsRequest,
    db: AsyncSession = Depends(get_db),
) -> FlashcardListResponse:
    """
    Generate AI flashcards from a previously uploaded document.
    New cards are created with status='pending' for quality control review.
    """
    # Fetch document
    result = await db.execute(select(Document).where(Document.id == request.document_id))
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    num_cards = request.num_cards or settings.default_num_cards

    # Mark as processing
    document.status = "processing"
    await db.flush()

    try:
        card_data = await generate_flashcards_from_text(
            text=document.raw_text,
            num_cards=num_cards,
            language=request.language,
        )
    except LLMRateLimitError as exc:
        document.status = "error"
        logger.warning("Rate limit exhausted for document %s: %s", document.id, exc)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        document.status = "error"
        logger.error("Flashcard generation failed for document %s: %s", document.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Flashcard generation failed: {exc}",
        ) from exc

    if not card_data:
        document.status = "error"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No flashcards could be generated from this document.",
        )

    # Persist flashcards as PENDING (quality control first)
    flashcards: list[Flashcard] = []
    for card in card_data:
        flashcard = Flashcard(
            document_id=document.id,
            question=card.question,
            answer=card.answer,
            status="pending",
        )
        db.add(flashcard)
        flashcards.append(flashcard)

    document.status = "done"
    await db.flush()

    logger.info(
        "Generated %d pending flashcards for document %s", len(flashcards), document.id
    )

    return FlashcardListResponse(
        total=len(flashcards),
        flashcards=[_flashcard_to_response(f, document.filename) for f in flashcards],
    )


@router.get(
    "/",
    response_model=FlashcardListResponse,
    summary="List flashcards, sorted by ad-hoc adaptive priority",
)
async def list_flashcards(
    document_id: Optional[str] = Query(default=None, description="Filter by document ID"),
    card_status: Optional[str] = Query(default=None, description="Filter by status: 'pending' or 'accepted'"),
    card_type: Optional[str] = Query(default=None, description="Filter by type: 'qa' or 'vocab'"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> FlashcardListResponse:
    """
    List flashcards. Accepted cards are sorted by an ad-hoc priority score
    based on mastery (ease) and recency (time since last study).
    Also returns global library statistics for the dashboard.
    """
    # Priority Score Formula (SQL expression, portable across SQLite/Postgres):
    p_score = priority_score_expr()

    # 1. Base Query for the list
    query = (
        select(Flashcard, Document.filename, p_score.label("p_score"))
        .outerjoin(Document, Flashcard.document_id == Document.id)
    )

    # Filter by status
    status_filter = card_status if card_status else "accepted"
    query = query.where(Flashcard.status == status_filter)

    if document_id:
        query = query.where(Flashcard.document_id == document_id)

    if card_type:
        query = query.where(Flashcard.card_type == card_type)

    # Order by priority score (highest first) for accepted cards
    if status_filter == "accepted":
        query = query.order_by(desc("p_score"))
    else:
        query = query.order_by(Flashcard.created_at.asc())

    query = query.limit(limit)

    result = await db.execute(query)
    rows = result.all()

    # 2. Global Library Statistics (only for accepted cards)
    stats_query = select(
        func.count(Flashcard.id).label("total"),
        func.avg(Flashcard.ease_factor).label("avg_ease"),
        # Count needs_focus (priority above the focus threshold)
        func.count(case((p_score > NEEDS_FOCUS_THRESHOLD, Flashcard.id))).label("focus")
    ).where(Flashcard.status == "accepted")

    if card_type:
        stats_query = stats_query.where(Flashcard.card_type == card_type)

    stats_res = await db.execute(stats_query)
    stats = stats_res.one()

    return FlashcardListResponse(
        total=len(rows),
        flashcards=[
            _flashcard_to_response(flashcard, filename, p_score) 
            for flashcard, filename, p_score in rows
        ],
        total_inventory=stats.total or 0,
        avg_mastery=round(stats.avg_ease or 0, 2),
        needs_focus_count=stats.focus or 0
    )


@router.get(
    "/{flashcard_id}",
    response_model=FlashcardResponse,
    summary="Get a single flashcard by ID",
)
async def get_flashcard(
    flashcard_id: str,
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    result = await db.execute(
        select(Flashcard, Document.filename)
        .outerjoin(Document, Flashcard.document_id == Document.id)
        .where(Flashcard.id == flashcard_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found.")
    flashcard, filename = row
    return _flashcard_to_response(flashcard, filename)


@router.patch(
    "/{flashcard_id}/accept",
    response_model=FlashcardResponse,
    summary="Accept a pending flashcard into your library",
)
async def accept_flashcard(
    flashcard_id: str,
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    result = await db.execute(
        select(Flashcard, Document.filename)
        .outerjoin(Document, Flashcard.document_id == Document.id)
        .where(Flashcard.id == flashcard_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found.")
    flashcard, filename = row
    flashcard.status = "accepted"
    flashcard.updated_at = datetime.now(timezone.utc)
    await db.flush()
    logger.info("Accepted flashcard %s into library", flashcard_id)
    return _flashcard_to_response(flashcard, filename)


@router.delete(
    "/{flashcard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard/Delete a flashcard",
)
async def delete_flashcard(
    flashcard_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Flashcard).where(Flashcard.id == flashcard_id))
    flashcard = result.scalar_one_or_none()
    if not flashcard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found.")
    await db.delete(flashcard)
    logger.info("Deleted flashcard %s", flashcard_id)
