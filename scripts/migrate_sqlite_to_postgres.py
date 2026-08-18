#!/usr/bin/env python3
"""
One-time data copy: the SQLite file this app used to run on -> Postgres.

Schema comes from Alembic (`alembic upgrade head` against the empty Postgres
database first); this script only moves rows, in FK-safe order: documents and
vocab_entries before flashcards, flashcards before reviews.

SQLite has no real boolean or timestamp type — it stores `dismissed` as 0/1
and every DateTime/Date as ISO text — so those are parsed into real Python
values on the way through instead of handed to asyncpg as strings.

SQLite also never enforced this app's `reviews.flashcard_id` foreign key (no
`PRAGMA foreign_keys=ON`), so some review rows point at flashcards deleted
along the way without their reviews cascading with them. Postgres enforces
the constraint correctly and would reject them, so orphaned reviews are
dropped here — they're history for a card that no longer exists, not
recoverable data.

Usage:
    python scripts/migrate_sqlite_to_postgres.py \\
        --sqlite-path flashcards.db \\
        --postgres-url postgresql+asyncpg://postgres:postgres@localhost:5433/flashcards

Safe to re-run: skips a table if it already has rows in Postgres, so it will
not double-insert.

Run this before the backend's first boot. Its startup auto-seeds the
vocabulary decks by default (SEED_VOCAB_ON_STARTUP=true), and since this
script skips any table that already has rows, a backend that booted first
wins the race silently — vocab_entries/flashcards look "already migrated"
when they are really just fresh catalog data, and your real history for
those tables never copies over. A pre-flight check below refuses to run in
exactly that situation rather than silently doing the wrong thing.
"""
import argparse
import asyncio
import sqlite3
import sys
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models import Document, Flashcard, Review, VocabEntry

# (model, sqlite table, columns that need type coercion)
TABLES = [
    (Document, "documents", {}),
    (VocabEntry, "vocab_entries", {"dismissed": "bool"}),
    (Flashcard, "flashcards", {"due_date": "date"}),
    (Review, "reviews", {}),
]

TIMESTAMP_COLUMNS = {"created_at", "updated_at", "reviewed_at"}


def _coerce(row: dict, coercions: dict) -> dict:
    out = dict(row)
    for col in TIMESTAMP_COLUMNS & out.keys():
        if isinstance(out[col], str):
            out[col] = datetime.fromisoformat(out[col])
    for col, kind in coercions.items():
        val = out.get(col)
        if val is None:
            continue
        if kind == "bool":
            out[col] = bool(val)
        elif kind == "date" and isinstance(val, str):
            out[col] = date.fromisoformat(val)
    return out


class AlreadySeededError(RuntimeError):
    """Raised when the backend looks like it auto-seeded ahead of this script."""


async def _check_not_already_seeded(db, src: sqlite3.Connection, sqlite_path: str) -> None:
    """
    Refuse to run if this looks like the auto-seed-raced-the-migration case.

    Signature: SQLite has real documents to migrate, Postgres has none yet
    (so no table has been touched by a real migration run), but VocabEntry
    already has rows anyway — the only thing that could have put them there
    with no documents migrated first is the backend's own startup seeding.
    """
    sqlite_documents = src.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    if not sqlite_documents:
        return  # nothing at stake for this signature either way

    pg_documents = await db.scalar(select(func.count()).select_from(Document))
    pg_vocab = await db.scalar(select(func.count()).select_from(VocabEntry))
    if pg_documents == 0 and pg_vocab > 0:
        raise AlreadySeededError(
            f"Postgres has {pg_vocab} vocab_entries but 0 documents, while "
            f"{sqlite_path} has {sqlite_documents} documents waiting to "
            "migrate. This looks like the backend already auto-seeded the "
            "vocab decks before this script ran, which means it will skip "
            "vocab_entries/flashcards and your real history is not copied.\n"
            "Fix: drop the Postgres volume and start over in the order in "
            "the README (`db` up + `alembic upgrade head` + this script, "
            "*then* `docker compose up -d --build`), or set "
            "SEED_VOCAB_ON_STARTUP=false, recreate the schema, and re-run."
        )


async def migrate(sqlite_path: str, postgres_url: str) -> None:
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    engine = create_async_engine(postgres_url)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    async with session_factory() as db:
        await _check_not_already_seeded(db, src, sqlite_path)

        for model, table, coercions in TABLES:
            existing = await db.scalar(select(func.count()).select_from(model))
            if existing:
                print(f"{table}: {existing} rows already in Postgres, skipping")
                continue

            query = f"SELECT * FROM {table}"
            if table == "reviews":
                query += (
                    " WHERE flashcard_id IN (SELECT id FROM flashcards)"
                )
            all_rows = list(src.execute(f"SELECT * FROM {table}"))
            rows = [_coerce(dict(r), coercions) for r in src.execute(query)]

            skipped = len(all_rows) - len(rows)
            if skipped:
                print(f"{table}: skipping {skipped} row(s) with no matching flashcard (orphaned)")
            if not rows:
                print(f"{table}: nothing to copy")
                continue

            db.add_all(model(**row) for row in rows)
            await db.commit()
            print(f"{table}: copied {len(rows)} rows")

    src.close()
    await engine.dispose()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sqlite-path", default="flashcards.db")
    ap.add_argument("--postgres-url", required=True)
    args = ap.parse_args()

    try:
        asyncio.run(migrate(args.sqlite_path, args.postgres_url))
    except AlreadySeededError as exc:
        print(f"Refusing to run: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
