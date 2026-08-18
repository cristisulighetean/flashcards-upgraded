"""Name card directions by skill instead of language pair.

With one language pair, 'ro_en' unambiguously meant term -> translation.
With separate English and Romanian decks the same string would mean
recognition in one deck and production in the other, so directions are
renamed to the skill they exercise.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing vocabulary entries are all Romanian-source, so ro_en was the
    # term -> translation (recognition) card and en_ro the production one.
    op.execute("UPDATE flashcards SET direction = 'recognition' WHERE direction = 'ro_en'")
    op.execute("UPDATE flashcards SET direction = 'production' WHERE direction = 'en_ro'")
    op.create_index("ix_vocab_entries_source_lang", "vocab_entries", ["source_lang"])


def downgrade() -> None:
    op.drop_index("ix_vocab_entries_source_lang", table_name="vocab_entries")
    op.execute("UPDATE flashcards SET direction = 'ro_en' WHERE direction = 'recognition'")
    op.execute("UPDATE flashcards SET direction = 'en_ro' WHERE direction = 'production'")
