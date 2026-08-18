"""
Deck seeding — two phases: catalog the whole word list, then activate batches.

The CSVs under `data/` are the canon for the two starter decks: one row per
word, its definition *in the same language*, its part of speech, and how
common it is.  Both files are sorted most-common-first, so a fixed-size slice
off the front is also "the next most useful words" — which is what makes
batching meaningful rather than arbitrary.

Phase 1, **cataloging**, inserts every word from a list as a `VocabEntry` with
no cards yet — the whole ~50k-word catalog lives in Postgres from the start,
cheap because a bare row with no cards costs almost nothing. Phase 2,
**activating** a batch, creates the two cards (recognition, production) for
the next 500 not-yet-activated words in that catalog, which is what actually
puts them in front of you: Quality Control, then study.

A word only counts as "loaded" once it is activated. Cataloging on its own is
invisible everywhere in the app — the Vocabulary page, Quality Control, and
`/vocab/stats` all only ever show activated words — so having the full
catalog resident in the database does not mean you are staring down 23,000
words; it means the *next* batch is just a database write away instead of a
fresh CSV parse.

Both phases are idempotent: a term already catalogued is skipped by phase 1,
and a word that already has cards (or was dismissed) is skipped by phase 2.

Run it by hand against a live database with:

    python -m app.services.vocab_seed --batches 4          # both decks
    python -m app.services.vocab_seed --lang en --next     # one more batch
    python -m app.services.vocab_seed --status
    python -m app.services.vocab_seed --lang ro --regloss  # fix foreign glosses
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.flashcard import Flashcard
from app.models.vocab_entry import VocabEntry
from app.services.vocab_cards import build_flashcards, sync_flashcards

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Words per batch. Deliberately a constant and not a setting: batch numbers are
# stored on the rows, so changing the size after seeding would renumber history.
WORDS_PER_BATCH = 500

# Catalog rows inserted per round trip. A plain bulk INSERT, not the ORM, so
# this can be large without the per-row overhead batch activation has to pay.
CATALOG_CHUNK = 2000

# Activated (card-creating) rows committed at a time. Small enough that a
# failure part-way through a batch leaves a usable deck rather than nothing.
COMMIT_EVERY = 250

# The word lists abbreviate; the card spells it out.
POS_LABELS = {
    "adj": "adjective",
    "adv": "adverb",
    "n": "noun",
    "v": "verb",
}


# Dictionary headwords are bare, but people write verbs with their infinitive
# marker. Stripping it is what lets "a tăgădui" find "tăgădui" in the list.
INFINITIVE_MARKERS = {"ro": "a ", "en": "to "}


@dataclass(frozen=True)
class WordList:
    """One bundled CSV and the column names it uses."""

    lang: str
    label: str
    filename: str
    term_col: str
    definition_col: str
    pos_col: str
    frequency_col: str
    example_col: str | None = None

    @property
    def path(self) -> Path:
        return DATA_DIR / self.filename


WORD_LISTS: dict[str, WordList] = {
    "en": WordList(
        lang="en",
        label="English",
        filename="english_advanced_words_full.csv",
        term_col="word",
        definition_col="definition",
        pos_col="pos",
        frequency_col="commonness_zipf",
        example_col="example",
    ),
    "ro": WordList(
        lang="ro",
        label="Romanian",
        filename="romana_cuvinte_complet.csv",
        term_col="cuvant",
        definition_col="definitie",
        pos_col="parte_de_vorbire",
        frequency_col="frecventa",
    ),
}

# Parsed lists are cached: the files never change at runtime, and re-reading
# 28k rows on every batch request would be wasted work.
_CACHE: dict[str, list[dict]] = {}


def load_word_list(spec: WordList, limit: int | None = None) -> list[dict]:
    """
    Read a bundled CSV into entry-shaped dicts, most common first.

    Rows without a term or a definition are dropped: a card with a blank side
    is unstudiable, and the lists are long enough that skipping beats
    repairing.
    """
    if not spec.path.exists():
        raise FileNotFoundError(f"Word list missing: {spec.path}")

    rows: list[dict] = []
    seen: set[str] = set()

    with spec.path.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            term = (raw.get(spec.term_col) or "").strip()
            definition = (raw.get(spec.definition_col) or "").strip()
            if not term or not definition:
                continue

            key = term.lower()
            if key in seen:  # the lists are clean today; stay safe if edited
                continue
            seen.add(key)

            pos = (raw.get(spec.pos_col) or "").strip().lower()
            example = (raw.get(spec.example_col) or "").strip() if spec.example_col else ""

            try:
                frequency = float(raw.get(spec.frequency_col) or 0.0)
            except ValueError:
                frequency = 0.0

            rows.append(
                {
                    "term": term,
                    "translation": definition,
                    "part_of_speech": POS_LABELS.get(pos, pos) or None,
                    "example": example or None,
                    "frequency": frequency,
                    "batch": len(rows) // WORDS_PER_BATCH + 1,
                }
            )
            if limit is not None and len(rows) >= limit:
                break

    return rows


def word_list(lang: str) -> list[dict]:
    """The full parsed list for a deck, cached."""
    if lang not in _CACHE:
        _CACHE[lang] = load_word_list(WORD_LISTS[lang])
    return _CACHE[lang]


def total_batches(lang: str) -> int:
    rows = word_list(lang)
    return (len(rows) + WORDS_PER_BATCH - 1) // WORDS_PER_BATCH


def batch_rows(lang: str, batch: int) -> list[dict]:
    """The words of one batch (1-based). Empty past the end of the list."""
    if batch < 1:
        return []
    rows = word_list(lang)
    start = (batch - 1) * WORDS_PER_BATCH
    return rows[start : start + WORDS_PER_BATCH]


def lookup(lang: str, term: str) -> dict | None:
    """Find a word in the bundled list, with or without its infinitive marker."""
    index = _index(lang)
    key = term.strip().lower()
    marker = INFINITIVE_MARKERS.get(lang, "")
    bare = key[len(marker):] if marker and key.startswith(marker) else key
    return index.get(key) or index.get(bare)


_INDEXES: dict[str, dict[str, dict]] = {}


def _index(lang: str) -> dict[str, dict]:
    if lang not in _INDEXES:
        _INDEXES[lang] = {row["term"].lower(): row for row in word_list(lang)}
    return _INDEXES[lang]


async def regloss_from_list(db: AsyncSession, lang: str) -> tuple[int, list[str]]:
    """
    Rewrite entries that are glossed in the wrong language using the bundled list.

    A deck seeded from `data/` explains each word in its own language, but
    words added before that — or by the AI, which translates — carry a gloss in
    the other language and look out of place next to the rest of the deck.

    Card text is regenerated, review history is not touched, so a word you have
    been studying for weeks keeps its schedule and simply reads correctly.

    Returns (entries updated, terms with no entry in the word list).
    """
    entries = (
        await db.execute(
            select(VocabEntry).where(
                VocabEntry.source_lang == lang,
                VocabEntry.target_lang != lang,
            )
        )
    ).scalars().all()

    updated = 0
    unmatched: list[str] = []

    for entry in entries:
        row = lookup(lang, entry.term)
        if row is None:
            unmatched.append(entry.term)
            continue

        entry.translation = row["translation"]
        entry.target_lang = lang
        entry.part_of_speech = row["part_of_speech"] or entry.part_of_speech
        entry.frequency = row["frequency"]
        entry.batch = row["batch"]

        cards = (
            await db.execute(
                select(Flashcard).where(Flashcard.vocab_entry_id == entry.id)
            )
        ).scalars().all()
        sync_flashcards(entry, list(cards))
        updated += 1

    await db.commit()
    return updated, unmatched


# ---------------------------------------------------------------------------
# Phase 1 — cataloging: get every word into Postgres, no cards yet
# ---------------------------------------------------------------------------

async def seed_catalog(db: AsyncSession, lang: str) -> int:
    """
    Insert every word of a deck's list as a cardless `VocabEntry`.

    A plain bulk INSERT rather than the ORM: at ~25k rows per deck, a
    flush-per-row loop would mean tens of thousands of round trips. This is a
    handful of round trips instead, one per `CATALOG_CHUNK`.

    Terms already present (case-insensitive) are skipped, whether they arrived
    as an earlier catalog run, a hand-added word, or an activated batch — so
    this is safe to call on every boot once the catalog already exists.
    """
    rows = word_list(lang)

    existing_rows = await db.execute(
        select(func.lower(VocabEntry.term)).where(VocabEntry.source_lang == lang)
    )
    existing = set(existing_rows.scalars().all())

    now = datetime.now(timezone.utc)
    to_insert = [
        {
            "id": str(uuid.uuid4()),
            "term": row["term"],
            "translation": row["translation"],
            "source_lang": lang,
            "target_lang": lang,
            "part_of_speech": row["part_of_speech"],
            "frequency": row["frequency"],
            "batch": row["batch"],
            "example": row["example"],
            "example_translation": None,
            "notes": None,
            "dismissed": False,
            "created_at": now,
            "updated_at": now,
        }
        for row in rows
        if row["term"].lower() not in existing
    ]

    table = VocabEntry.__table__
    for start in range(0, len(to_insert), CATALOG_CHUNK):
        chunk = to_insert[start : start + CATALOG_CHUNK]
        await db.execute(insert(table), chunk)
        await db.commit()

    return len(to_insert)


# ---------------------------------------------------------------------------
# Phase 2 — activation: turn a catalogued batch into cards
# ---------------------------------------------------------------------------

async def loaded_batches(db: AsyncSession, lang: str) -> int:
    """
    How many batches from the front of the list are fully **activated**.

    A batch is settled, one word at a time, once every one of its words has
    either been turned into cards or dismissed — the two ways a catalogued
    word stops being just a bare row. Counted as contiguous complete batches
    from batch 1, not by the highest batch number present: a stray batch
    number (a hand-added word re-glossed from deep in the list, or the rest of
    the catalog sitting un-activated) must not read as progress.
    """
    rows = await db.execute(
        select(VocabEntry.batch, func.count(func.distinct(VocabEntry.id)))
        .outerjoin(Flashcard, Flashcard.vocab_entry_id == VocabEntry.id)
        .where(
            VocabEntry.source_lang == lang,
            VocabEntry.batch.is_not(None),
            or_(VocabEntry.dismissed.is_(True), Flashcard.id.is_not(None)),
        )
        .group_by(VocabEntry.batch)
    )
    counts = {int(batch): n for batch, n in rows.all()}

    complete = 0
    while True:
        expected = len(batch_rows(lang, complete + 1))
        if expected == 0 or counts.get(complete + 1, 0) < expected:
            return complete
        complete += 1


async def activate_batch(
    db: AsyncSession,
    lang: str,
    batch: int,
    status: str = "pending",
) -> int:
    """
    Create cards for every catalogued, not-yet-activated word in one batch.

    Words already carrying cards, or dismissed, are left alone — this is what
    makes activating the same batch twice a no-op.
    """
    already_active = select(Flashcard.vocab_entry_id).where(
        Flashcard.vocab_entry_id.is_not(None)
    )
    entries = (
        await db.execute(
            select(VocabEntry).where(
                VocabEntry.source_lang == lang,
                VocabEntry.batch == batch,
                VocabEntry.dismissed.is_(False),
                VocabEntry.id.not_in(already_active),
            )
        )
    ).scalars().all()

    activated = 0
    for entry in entries:
        for card in build_flashcards(entry, status=status):
            db.add(card)
        activated += 1
        if activated % COMMIT_EVERY == 0:
            await db.commit()

    await db.commit()
    return activated


async def activate_through(
    db: AsyncSession,
    lang: str,
    batches: int,
    status: str = "pending",
) -> int:
    """Make sure batches 1..`batches` are activated. Returns words activated."""
    activated = 0
    for batch in range(1, min(batches, total_batches(lang)) + 1):
        activated += await activate_batch(db, lang, batch, status)
    return activated


async def activate_next_batch(
    db: AsyncSession,
    lang: str,
    status: str = "pending",
) -> tuple[int, int]:
    """Activate the batch after the highest activated one. Returns (batch, activated)."""
    batch = await loaded_batches(db, lang) + 1
    if batch > total_batches(lang):
        return batch, 0
    return batch, await activate_batch(db, lang, batch, status)


async def deck_progress(db: AsyncSession, lang: str) -> dict:
    """What is catalogued, what is activated, and what the next batch would bring."""
    spec = WORD_LISTS[lang]
    rows = word_list(lang)
    loaded = await loaded_batches(db, lang)

    in_catalog = await db.scalar(
        select(func.count(VocabEntry.id)).where(VocabEntry.source_lang == lang)
    ) or 0
    dismissed = await db.scalar(
        select(func.count(VocabEntry.id)).where(
            VocabEntry.source_lang == lang,
            VocabEntry.dismissed.is_(True),
        )
    ) or 0
    # Activated and kept: has a card, not dismissed. Being catalogued alone
    # does not count — that is background data, not something you hold yet.
    held = await db.scalar(
        select(func.count(func.distinct(VocabEntry.id)))
        .select_from(VocabEntry)
        .join(Flashcard, Flashcard.vocab_entry_id == VocabEntry.id)
        .where(VocabEntry.source_lang == lang, VocabEntry.dismissed.is_(False))
    ) or 0

    next_batch = loaded + 1
    preview = [r["term"] for r in batch_rows(lang, next_batch)[:5]]

    return {
        "lang": lang,
        "label": spec.label,
        "words_available": len(rows),
        "words_in_catalog": in_catalog,
        "batch_size": WORDS_PER_BATCH,
        "batches_total": total_batches(lang),
        "batches_loaded": loaded,
        "words_loaded": held,
        "words_dismissed": dismissed,
        "next_batch": next_batch if next_batch <= total_batches(lang) else None,
        "next_batch_preview": preview,
    }


async def seed_startup(
    session_factory: async_sessionmaker[AsyncSession],
    langs: list[str],
    batches: int,
    status: str = "pending",
) -> dict[str, tuple[int, int]]:
    """
    Catalog every configured deck in full, then activate its first `batches`.

    Called from the app lifespan. Failures are logged and swallowed per deck:
    a missing or malformed word list should not stop the API from serving the
    cards it already has. Returns {lang: (catalogued, activated)}.
    """
    results: dict[str, tuple[int, int]] = {}

    for lang in langs:
        if lang not in WORD_LISTS:
            logger.warning("No bundled word list for deck '%s', skipping.", lang)
            continue
        try:
            async with session_factory() as db:
                catalogued = await seed_catalog(db, lang)
            async with session_factory() as db:
                activated = await activate_through(db, lang, batches, status)
        except Exception as exc:  # noqa: BLE001 — seeding must never block boot
            logger.error("Seeding the '%s' deck failed: %s", lang, exc)
            continue

        results[lang] = (catalogued, activated)
        if catalogued:
            logger.info(
                "Catalogued %d '%s' words from %s (no cards yet)",
                catalogued, lang, WORD_LISTS[lang].filename,
            )
        if activated:
            logger.info(
                "Activated %d '%s' words (%d cards, status=%s), batches 1-%d",
                activated, lang, activated * 2, status, batches,
            )
        if not catalogued and not activated:
            logger.info("Deck '%s': catalog complete, batches 1-%d already active.", lang, batches)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.database import AsyncSessionLocal, Base, engine

    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    print(f"Database: {settings.database_url}")

    langs = [args.lang] if args.lang else list(WORD_LISTS)

    if args.dry_run:
        for lang in langs:
            rows = word_list(lang)
            head = ", ".join(r["term"] for r in rows[:5])
            print(f"{lang}: {len(rows)} words, {total_batches(lang)} batches -> {head} ...")
        return 0

    async with engine.begin() as conn:
        import app.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        if args.regloss:
            for lang in langs:
                updated, unmatched = await regloss_from_list(db, lang)
                print(f"{lang}: re-glossed {updated} entries from the word list")
                if unmatched:
                    print(f"   not in the list, left as they were: {', '.join(unmatched)}")
        elif args.status_only:
            for lang in langs:
                p = await deck_progress(db, lang)
                print(
                    f"{lang}: catalog {p['words_in_catalog']}/{p['words_available']} · "
                    f"activated {p['batches_loaded']}/{p['batches_total']} batches "
                    f"({p['words_loaded']} words) "
                    f"next: {', '.join(p['next_batch_preview']) or '-'}"
                )
        elif args.catalog_only:
            for lang in langs:
                n = await seed_catalog(db, lang)
                print(f"{lang}: catalogued {n} new words (no cards)")
        elif args.next:
            for lang in langs:
                await seed_catalog(db, lang)
                batch, n = await activate_next_batch(db, lang, args.card_status)
                print(f"{lang}: batch {batch} -> {n} words activated ({n * 2} cards)")
        else:
            for lang in langs:
                await seed_catalog(db, lang)
                n = await activate_through(db, lang, args.batches, args.card_status)
                print(f"{lang}: batches 1-{args.batches} -> {n} words activated ({n * 2} cards)")

    await engine.dispose()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--lang", choices=sorted(WORD_LISTS), help="One deck (default: all)")
    ap.add_argument("--batches", type=int, default=4,
                    help=f"Activate batches 1..N ({WORDS_PER_BATCH} words each)")
    ap.add_argument("--next", action="store_true", help="Activate only the next batch")
    ap.add_argument("--catalog-only", action="store_true",
                    help="Only phase 1: insert the full word list, no cards")
    ap.add_argument("--regloss", action="store_true",
                    help="Rewrite entries glossed in the other language using the bundled list")
    ap.add_argument("--status", dest="status_only", action="store_true",
                    help="Report what is catalogued/activated, write nothing")
    ap.add_argument("--card-status", default="pending", choices=["accepted", "pending"],
                    help="Activated cards go into Quality Control, or straight into study")
    ap.add_argument("--dry-run", action="store_true", help="Parse and report without touching the database")
    return asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
