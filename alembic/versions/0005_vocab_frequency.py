"""Record word frequency and batch, and let definitions run long.

The bundled word lists are ordered most-common-first, and that ordering is
what decides which words seed a deck. Keeping the number on the row means the
deck can be re-sorted or extended later without re-reading the CSVs.

`batch` records which 500-word slice of the list a word came from, so the rest
of the list can be loaded later, a batch at a time, as the loaded words are
learned. NULL means the word was added by hand.

`translation` also carries same-language dictionary definitions now, which
exceed the old 500-character limit, so it becomes Text.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vocab_entries", sa.Column("frequency", sa.Float(), nullable=True))
    op.add_column("vocab_entries", sa.Column("batch", sa.Integer(), nullable=True))
    op.create_index("ix_vocab_entries_frequency", "vocab_entries", ["frequency"])
    op.create_index("ix_vocab_entries_batch", "vocab_entries", ["batch"])
    # batch_alter_table: SQLite cannot ALTER a column type in place.
    with op.batch_alter_table("vocab_entries") as batch:
        batch.alter_column(
            "translation",
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("vocab_entries") as batch:
        batch.alter_column(
            "translation",
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=False,
        )
    op.drop_index("ix_vocab_entries_batch", table_name="vocab_entries")
    op.drop_index("ix_vocab_entries_frequency", table_name="vocab_entries")
    op.drop_column("vocab_entries", "batch")
    op.drop_column("vocab_entries", "frequency")
