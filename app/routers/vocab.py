"""
Vocabulary router — add words, list them, edit and delete.

Adding a word creates a VocabEntry plus one flashcard per practised direction.
The cards start as 'pending' so they land in the existing Quality Control
screen for approval before entering the study rotation.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.flashcard import Flashcard
from app.models.vocab_entry import VocabEntry
from app.schemas.vocab import (
    AddWordsRequest,
    AddWordsResponse,
    DeckBatchesResponse,
    DeckBatchProgress,
    DeckStats,
    LoadBatchResponse,
    ImportRequest,
    ImportResponse,
    VocabEntryResponse,
    VocabEntryUpdate,
    VocabListResponse,
    VocabStatsResponse,
)
from app.services.openai_service import LLMRateLimitError
from app.services.vocab_cards import build_flashcards, sync_flashcards
from app.services.vocab_enricher import VocabValidationError, enrich_terms
from app.services.vocab_seed import WORD_LISTS, activate_next_batch, deck_progress, seed_catalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vocab", tags=["Vocabulary"])


def _to_response(entry: VocabEntry, card_count: int = 0) -> VocabEntryResponse:
    data = VocabEntryResponse.model_validate(entry)
    data.card_count = card_count
    return data


@router.post(
    "/",
    response_model=AddWordsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add words to your vocabulary",
)
async def add_words(
    request: AddWordsRequest,
    db: AsyncSession = Depends(get_db),
) -> AddWordsResponse:
    """
    Add one or more words. With `enrich` on (the default) the AI supplies the
    translation, part of speech and an example sentence for each.
    """
    terms = [t.strip() for t in request.terms if t.strip()]
    if not terms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No usable terms supplied.",
        )

    # Skip words already in this language pair, case-insensitively. Dismissed
    # words are excluded here on purpose: a word you threw out should be
    # addable again if you change your mind, not blocked forever.
    existing_rows = await db.execute(
        select(func.lower(VocabEntry.term)).where(
            VocabEntry.source_lang == request.source_lang,
            VocabEntry.target_lang == request.target_lang,
            VocabEntry.dismissed.is_(False),
        )
    )
    existing = set(existing_rows.scalars().all())

    if request.enrich:
        try:
            enriched = await enrich_terms(
                terms, request.source_lang, request.target_lang
            )
        except LLMRateLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
            ) from exc
        except VocabValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI lookup failed: {exc}",
            ) from exc
        except Exception as exc:
            logger.error("Vocabulary enrichment failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI lookup failed: {exc}",
            ) from exc
    else:
        # Manual mode: "word - translation", or a bare word with no translation.
        enriched = []
        for term in terms:
            head, sep, tail = term.partition("-")
            enriched.append(
                {
                    "term": head.strip() if sep else term,
                    "translation": tail.strip() if sep and tail.strip() else "?",
                    "part_of_speech": None,
                    "example": None,
                    "example_translation": None,
                    "notes": None,
                }
            )

    created: list[VocabEntry] = []
    skipped: list[str] = []
    cards_created = 0

    for item in enriched:
        key = item["term"].lower()
        if key in existing:
            skipped.append(item["term"])
            continue
        existing.add(key)

        entry = VocabEntry(
            term=item["term"],
            translation=item["translation"],
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            part_of_speech=item.get("part_of_speech"),
            example=item.get("example"),
            example_translation=item.get("example_translation"),
            notes=item.get("notes"),
        )
        db.add(entry)
        await db.flush()  # assign entry.id before building its cards

        cards = build_flashcards(entry)
        for card in cards:
            db.add(card)
        cards_created += len(cards)
        created.append(entry)

    await db.flush()
    logger.info(
        "Added %d vocabulary entries (%d cards), skipped %d duplicates",
        len(created),
        cards_created,
        len(skipped),
    )

    return AddWordsResponse(
        added=len(created),
        skipped_duplicates=skipped,
        cards_created=cards_created,
        entries=[_to_response(e, card_count=2) for e in created],
    )


@router.get("/", response_model=VocabListResponse, summary="List vocabulary entries")
async def list_entries(
    lang: str | None = Query(default=None, description="Deck: the language being learned"),
    search: str | None = Query(default=None, description="Filter by term or translation"),
    pending: bool = Query(
        default=False, description="Only words with at least one card awaiting Quality Control"
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> VocabListResponse:
    counts = (
        select(Flashcard.vocab_entry_id, func.count(Flashcard.id).label("n"))
        .where(Flashcard.vocab_entry_id.is_not(None))
        .group_by(Flashcard.vocab_entry_id)
        .subquery()
    )

    # Hand-added words (no frequency) come first, newest first; the seeded
    # word lists follow in order of how common the word is. Quality Control
    # instead works oldest-added first, so words come up in the order they
    # were loaded, batch by batch.
    query = select(VocabEntry, func.coalesce(counts.c.n, 0)).outerjoin(
        counts, VocabEntry.id == counts.c.vocab_entry_id
    )
    query = query.where(VocabEntry.dismissed.is_(False))
    # Cataloged-but-not-yet-activated words (the rest of a bundled list,
    # sitting in Postgres with no cards) are not "your vocabulary" yet — only
    # words that have actually been turned into cards show up here.
    query = query.where(func.coalesce(counts.c.n, 0) > 0)
    if lang:
        query = query.where(VocabEntry.source_lang == lang)

    if pending:
        pending_entry_ids = select(Flashcard.vocab_entry_id).where(
            Flashcard.vocab_entry_id.is_not(None), Flashcard.status == "pending"
        )
        query = query.where(VocabEntry.id.in_(pending_entry_ids))
        query = query.order_by(VocabEntry.created_at.asc())
    else:
        query = query.order_by(
            VocabEntry.frequency.is_(None).desc(),
            VocabEntry.frequency.desc(),
            VocabEntry.created_at.desc(),
        )

    query = query.limit(limit)

    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(
            func.lower(VocabEntry.term).like(pattern)
            | func.lower(VocabEntry.translation).like(pattern)
        )

    rows = (await db.execute(query)).all()
    return VocabListResponse(
        total=len(rows),
        entries=[_to_response(entry, n) for entry, n in rows],
    )


@router.patch(
    "/{entry_id}",
    response_model=VocabEntryResponse,
    summary="Correct an entry (keeps review history)",
)
async def update_entry(
    entry_id: str,
    request: VocabEntryUpdate,
    db: AsyncSession = Depends(get_db),
) -> VocabEntryResponse:
    entry = (
        await db.execute(select(VocabEntry).where(VocabEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vocabulary entry not found."
        )

    updates = request.model_dump(exclude_unset=True)

    new_term = updates.get("term")
    if new_term and new_term.lower() != entry.term.lower():
        clash = await db.scalar(
            select(VocabEntry.id).where(
                VocabEntry.id != entry_id,
                VocabEntry.source_lang == entry.source_lang,
                VocabEntry.dismissed.is_(False),
                func.lower(VocabEntry.term) == new_term.lower(),
            )
        )
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"'{new_term}' is already in this deck.",
            )

    for field, value in updates.items():
        setattr(entry, field, value)

    cards = (
        await db.execute(
            select(Flashcard).where(Flashcard.vocab_entry_id == entry_id)
        )
    ).scalars().all()
    sync_flashcards(entry, list(cards))

    await db.flush()
    return _to_response(entry, card_count=len(cards))


@router.patch(
    "/{entry_id}/accept",
    response_model=VocabEntryResponse,
    summary="Approve a word out of Quality Control",
)
async def accept_entry(entry_id: str, db: AsyncSession = Depends(get_db)) -> VocabEntryResponse:
    """
    Move every card of a word into the study rotation.

    Quality Control works word by word, not card by card: a word's recognition
    and production cards say the same thing in two directions, and approving
    one while the other waits is a distinction without a difference.
    """
    entry = (
        await db.execute(select(VocabEntry).where(VocabEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vocabulary entry not found."
        )

    cards = (
        await db.execute(
            select(Flashcard).where(Flashcard.vocab_entry_id == entry_id)
        )
    ).scalars().all()
    for card in cards:
        card.status = "accepted"

    await db.flush()
    logger.info("Accepted word %r (%d cards)", entry.term, len(cards))
    return _to_response(entry, card_count=len(cards))


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Throw a word out of its deck",
)
async def delete_entry(entry_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """
    Remove a word you do not want to learn, along with its cards.

    A word that came from a bundled list is marked dismissed rather than
    deleted: the lists are the source of truth for what a deck should contain,
    so a deleted row would simply be seeded again on the next deployment. The
    kept row is hidden everywhere and carries no cards.
    """
    entry = (
        await db.execute(select(VocabEntry).where(VocabEntry.id == entry_id))
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vocabulary entry not found."
        )

    # Explicit: SQLite does not enforce ON DELETE CASCADE unless pragma is on.
    await db.execute(delete(Flashcard).where(Flashcard.vocab_entry_id == entry_id))

    if entry.batch is not None:
        entry.dismissed = True
        logger.info("Dismissed seeded word %r (%s) and deleted its cards", entry.term, entry_id)
    else:
        await db.delete(entry)
        logger.info("Deleted vocabulary entry %s and its cards", entry_id)


@router.get(
    "/stats",
    response_model=VocabStatsResponse,
    summary="Entry and card counts per language deck",
)
async def deck_stats(db: AsyncSession = Depends(get_db)) -> VocabStatsResponse:
    # "entries" here means activated words (they have cards) — a cataloged
    # but not-yet-activated word is background data, not part of the deck a
    # learner sees.
    entry_rows = await db.execute(
        select(VocabEntry.source_lang, func.count(func.distinct(VocabEntry.id)))
        .select_from(VocabEntry)
        .join(Flashcard, Flashcard.vocab_entry_id == VocabEntry.id)
        .where(VocabEntry.dismissed.is_(False))
        .group_by(VocabEntry.source_lang)
    )
    entry_counts = dict(entry_rows.all())

    card_rows = await db.execute(
        select(
            VocabEntry.source_lang,
            Flashcard.status,
            func.count(Flashcard.id),
        )
        .join(VocabEntry, Flashcard.vocab_entry_id == VocabEntry.id)
        .group_by(VocabEntry.source_lang, Flashcard.status)
    )
    card_counts: dict[tuple[str, str], int] = {
        (lang, status_): n for lang, status_, n in card_rows.all()
    }

    langs = sorted(set(entry_counts) | {lang for lang, _ in card_counts})
    return VocabStatsResponse(
        decks=[
            DeckStats(
                lang=lang,
                entries=entry_counts.get(lang, 0),
                cards_pending=card_counts.get((lang, "pending"), 0),
                cards_accepted=card_counts.get((lang, "accepted"), 0),
            )
            for lang in langs
        ]
    )


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk-import a prepared word list (no AI call)",
)
async def import_words(
    request: ImportRequest,
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """
    Load a ready-made list into one deck.  Translations are taken as given, so
    this is instant and deterministic — the intended way to seed a deck.

    `gloss_lang` may equal `lang`: the bundled decks explain each word with a
    definition in its own language rather than a translation.
    """
    # Dismissed words are excluded so a thrown-out word can be re-imported
    # instead of being silently blocked forever.
    existing_rows = await db.execute(
        select(func.lower(VocabEntry.term)).where(
            VocabEntry.source_lang == request.lang,
            VocabEntry.dismissed.is_(False),
        )
    )
    existing = set(existing_rows.scalars().all())

    card_status = "accepted" if request.accepted else "pending"
    imported = 0
    cards_created = 0
    skipped: list[str] = []

    for item in request.entries:
        term = item.term.strip()
        key = term.lower()
        if key in existing:
            skipped.append(term)
            continue
        existing.add(key)

        entry = VocabEntry(
            term=term,
            translation=item.translation.strip(),
            source_lang=request.lang,
            target_lang=request.gloss_lang,
            part_of_speech=item.part_of_speech,
            example=item.example,
            example_translation=item.example_translation,
            notes=item.notes,
        )
        db.add(entry)
        await db.flush()

        for card in build_flashcards(entry, status=card_status):
            db.add(card)
        cards_created += 2
        imported += 1

    await db.flush()
    logger.info(
        "Imported %d %s entries (%d cards, status=%s), skipped %d duplicates",
        imported,
        request.lang,
        cards_created,
        card_status,
        len(skipped),
    )

    return ImportResponse(
        lang=request.lang,
        imported=imported,
        skipped_duplicates=skipped,
        cards_created=cards_created,
    )


# ---------------------------------------------------------------------------
# Bundled word lists — loaded a batch at a time
# ---------------------------------------------------------------------------

@router.get(
    "/decks/batches",
    response_model=DeckBatchesResponse,
    summary="How much of each bundled word list is loaded",
)
async def list_deck_batches(db: AsyncSession = Depends(get_db)) -> DeckBatchesResponse:
    """
    Progress through the shipped word lists, per deck.

    Every word is already cataloged in Postgres (`words_in_catalog`), but that
    is background data — deployment only *activates* the first few batches
    into actual cards, so the study queue only ever holds words you have
    signed up to learn.
    """
    return DeckBatchesResponse(
        decks=[
            DeckBatchProgress(**await deck_progress(db, lang))
            for lang in WORD_LISTS
        ]
    )


@router.post(
    "/decks/{lang}/batches/next",
    response_model=LoadBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Load the next batch of words into a deck",
)
async def load_next_batch(
    lang: str,
    card_status: str = Query(
        default="pending",
        pattern="^(accepted|pending)$",
        description="Route the new cards to Quality Control, or study them straight away",
    ),
    db: AsyncSession = Depends(get_db),
) -> LoadBatchResponse:
    """
    Activate the next 500 words of the bundled list, commonest first.

    The words themselves are already sitting in Postgres from cataloging —
    this only creates their cards, so it is a database write, not a CSV
    re-parse.
    """
    if lang not in WORD_LISTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No bundled word list for deck '{lang}'.",
        )

    # Defensive: guarantees the batch exists as catalog rows even if the app
    # booted with seeding off. A no-op once the catalog is already complete.
    await seed_catalog(db, lang)

    batch, added = await activate_next_batch(db, lang, card_status)
    if added == 0:
        progress = await deck_progress(db, lang)
        if progress["next_batch"] is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"The '{lang}' word list is fully loaded ({progress['words_loaded']} words).",
            )

    logger.info("Activated batch %d of the '%s' deck: %d words", batch, lang, added)
    return LoadBatchResponse(
        lang=lang,
        batch=batch,
        entries_added=added,
        cards_created=added * 2,
        progress=DeckBatchProgress(**await deck_progress(db, lang)),
    )
