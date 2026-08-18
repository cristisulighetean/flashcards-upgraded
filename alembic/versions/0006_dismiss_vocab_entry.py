"""Let a word be thrown out of a deck for good.

Deleting a seeded word outright does not stick: the next deployment sees it
missing from the deck and seeds it again, because the word lists in data/ are
the source of truth for what a deck should hold.

Marking it dismissed keeps the row — so seeding still recognises the term —
while its flashcards are deleted and the word is hidden from the app.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sa.false(), not text("0"): SQLite accepts a bare 0 as a boolean default,
    # but Postgres's boolean column rejects an integer literal outright.
    op.add_column(
        "vocab_entries",
        sa.Column(
            "dismissed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("vocab_entries", "dismissed")
