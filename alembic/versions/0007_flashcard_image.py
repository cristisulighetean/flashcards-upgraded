"""Let a flashcard carry an optional image.

qa cards generated from diagram-heavy source material (architecture
screenshots, network diagrams) lose real information when reduced to a
prose description. Storing the bytes inline avoids introducing a file/object
store into an app that otherwise only has Postgres — the only place other
than the DB anything gets written is the container filesystem, and that
isn't persisted across deploys anyway.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("flashcards", sa.Column("image_data", sa.LargeBinary(), nullable=True))
    op.add_column("flashcards", sa.Column("image_content_type", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("flashcards", "image_content_type")
    op.drop_column("flashcards", "image_data")
