import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VocabEntry(Base):
    """
    A vocabulary record: one word/phrase and its translation.

    An entry is the *content*; the flashcards it generates are the
    *scheduling units*.  One entry produces one card per practised
    direction, each reviewed independently by SM-2.
    """

    __tablename__ = "vocab_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    term: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    translation: Mapped[str] = mapped_column(String(500), nullable=False)

    source_lang: Mapped[str] = mapped_column(String(5), nullable=False, default="ro")
    target_lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    part_of_speech: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example_translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
