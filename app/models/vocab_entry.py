import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VocabEntry(Base):
    """
    A vocabulary record: one word/phrase and its translation.

    An entry is the *content*; the flashcards it generates are the
    *scheduling units*.  One entry produces one card per practised
    direction, each reviewed independently by SM-2.

    `translation` holds whatever explains the term: a gloss in the other
    language for a bilingual pair, or a same-language definition for the
    seeded English and Romanian decks.
    """

    __tablename__ = "vocab_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    term: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Text, not String(n): dictionary definitions run long (700+ chars).
    translation: Mapped[str] = mapped_column(Text, nullable=False)

    source_lang: Mapped[str] = mapped_column(String(5), nullable=False, default="ro")
    target_lang: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    part_of_speech: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # How common the word is in its language. Scales differ per word list
    # (Zipf for English, corpus counts for Romanian) — higher is commoner
    # within one deck, and it is only ever compared inside a deck.
    frequency: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    # Which slice of the bundled word list this came from (1 = commonest 500).
    # NULL for words added by hand, which belong to no batch.
    batch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # A word thrown out of the deck. The row stays so seeding recognises the
    # term and does not hand the word back on the next deployment; its cards
    # are gone and it is hidden everywhere in the app.
    # false(), not text("0"): SQLite accepts a bare 0 as a boolean default, but
    # Postgres's boolean column rejects an integer literal default outright.
    dismissed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
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
