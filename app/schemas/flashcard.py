from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FlashcardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: Optional[str] = None
    vocab_entry_id: Optional[str] = None
    question: str
    answer: str
    ease_factor: float
    interval: int
    repetitions: int
    created_at: datetime
    status: str = "accepted"
    card_type: str = "qa"
    direction: Optional[str] = None
    priority_score: float = 0.0
    document_filename: Optional[str] = None


class FlashcardListResponse(BaseModel):
    total: int
    flashcards: list[FlashcardResponse]
    # Global metadata for the dashboard
    total_inventory: Optional[int] = 0
    avg_mastery: Optional[float] = 0.0
    needs_focus_count: Optional[int] = 0


class GenerateFlashcardsRequest(BaseModel):
    document_id: str
    num_cards: Optional[int] = Field(
        default=None,
        ge=1,
        le=30,
        description="Number of flashcards to generate (1–30). Defaults to app setting.",
    )
    language: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Target language for flashcards (e.g. 'Spanish'). Defaults to source language.",
    )
