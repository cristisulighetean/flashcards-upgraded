import base64
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    # Full bytes never ride along in a list response — fetch via
    # GET /flashcards/{id}/image when this is true.
    has_image: bool = False


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


# Keeps a single card's row (and the bulk request body carrying up to 100 of
# them) from ballooning — plenty for a diagram screenshot, not a photo dump.
MAX_IMAGE_BYTES = 3 * 1024 * 1024


class BulkFlashcardItem(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    # Longer than the AI-generation cap (1000): hand-authored answers are
    # written up front to the same depth as the LLM system prompt asks for
    # (multi-paragraph, code blocks, worked examples), so they run longer.
    answer: str = Field(..., min_length=1, max_length=4000)
    # Optional diagram/screenshot for this card. Both fields must be present
    # together or both absent.
    image_base64: Optional[str] = Field(default=None, description="Raw base64, no data: URI prefix")
    image_content_type: Optional[str] = Field(default=None, max_length=50, examples=["image/png"])

    @field_validator("image_base64")
    @classmethod
    def _validate_image(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            decoded = base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError("image_base64 is not valid base64") from exc
        if len(decoded) > MAX_IMAGE_BYTES:
            raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} bytes")
        return v

    @model_validator(mode="after")
    def _image_fields_paired(self) -> "BulkFlashcardItem":
        if bool(self.image_base64) != bool(self.image_content_type):
            raise ValueError("image_base64 and image_content_type must be given together")
        return self


class BulkCreateFlashcardsRequest(BaseModel):
    document_id: str
    cards: list[BulkFlashcardItem] = Field(..., min_length=1, max_length=100)
