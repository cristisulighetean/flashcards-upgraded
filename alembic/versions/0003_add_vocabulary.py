"""Add vocabulary entries and link them to flashcards.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vocab_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("term", sa.String(200), nullable=False, index=True),
        sa.Column("translation", sa.String(500), nullable=False),
        sa.Column("source_lang", sa.String(5), nullable=False, server_default="ro"),
        sa.Column("target_lang", sa.String(5), nullable=False, server_default="en"),
        sa.Column("part_of_speech", sa.String(50), nullable=True),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("example_translation", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # batch_alter_table: SQLite cannot ALTER a column's nullability in place,
    # so Alembic recreates the table and copies the rows across.
    with op.batch_alter_table("flashcards") as batch:
        batch.add_column(sa.Column("vocab_entry_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("card_type", sa.String(10), nullable=False, server_default="qa")
        )
        batch.add_column(sa.Column("direction", sa.String(10), nullable=True))
        batch.alter_column("document_id", existing_type=sa.String(36), nullable=True)
        batch.create_foreign_key(
            "fk_flashcards_vocab_entry",
            "vocab_entries",
            ["vocab_entry_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_index("ix_flashcards_card_type", "flashcards", ["card_type"])
    op.create_index("ix_flashcards_vocab_entry_id", "flashcards", ["vocab_entry_id"])


def downgrade() -> None:
    op.drop_index("ix_flashcards_vocab_entry_id", table_name="flashcards")
    op.drop_index("ix_flashcards_card_type", table_name="flashcards")

    with op.batch_alter_table("flashcards") as batch:
        batch.drop_constraint("fk_flashcards_vocab_entry", type_="foreignkey")
        batch.drop_column("direction")
        batch.drop_column("card_type")
        batch.drop_column("vocab_entry_id")

    op.drop_table("vocab_entries")
