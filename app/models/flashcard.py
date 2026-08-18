import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Nullable: vocabulary cards are not derived from an uploaded document.
    document_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    vocab_entry_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("vocab_entries.id", ondelete="CASCADE"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(nullable=False)
    answer: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="accepted"
    )  # pending | accepted
    card_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="qa", index=True
    )  # qa | vocab
    # 20, not 10: "recognition" is 11 characters. SQLite never enforced the
    # varchar length so this went unnoticed until Postgres did.
    direction: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # vocab only: ro_en | en_ro

    # SM-2 fields
    ease_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # days
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).date(),
    )

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
