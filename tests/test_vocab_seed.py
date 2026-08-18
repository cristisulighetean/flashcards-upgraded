"""
Bundled word lists — parsing, cataloging the full list, and activating batches.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func
from sqlalchemy.future import select

from app.models.flashcard import Flashcard
from app.models.vocab_entry import VocabEntry
from app.services.vocab_cards import build_flashcards
from app.services.vocab_seed import (
    WORD_LISTS,
    WORDS_PER_BATCH,
    activate_batch,
    activate_next_batch,
    activate_through,
    batch_rows,
    deck_progress,
    load_word_list,
    loaded_batches,
    regloss_from_list,
    seed_catalog,
    total_batches,
    word_list,
)


class TestWordLists:

    @pytest.mark.parametrize("lang", ["en", "ro"])
    def test_list_is_present_and_parses(self, lang):
        rows = load_word_list(WORD_LISTS[lang], limit=50)
        assert len(rows) == 50
        assert all(r["term"] and r["translation"] for r in rows)

    @pytest.mark.parametrize("lang", ["en", "ro"])
    def test_rows_are_ordered_most_common_first(self, lang):
        rows = load_word_list(WORD_LISTS[lang], limit=200)
        frequencies = [r["frequency"] for r in rows]
        assert frequencies == sorted(frequencies, reverse=True)

    def test_english_abbreviations_are_spelled_out(self):
        rows = load_word_list(WORD_LISTS["en"], limit=500)
        parts = {r["part_of_speech"] for r in rows}
        assert "adjective" in parts
        assert "adj" not in parts

    @pytest.mark.parametrize("lang", ["en", "ro"])
    def test_batch_numbers_follow_position(self, lang):
        rows = load_word_list(WORD_LISTS[lang], limit=WORDS_PER_BATCH + 10)
        assert rows[0]["batch"] == 1
        assert rows[WORDS_PER_BATCH - 1]["batch"] == 1
        assert rows[WORDS_PER_BATCH]["batch"] == 2

    def test_batches_slice_the_list_without_gaps(self):
        first, second = batch_rows("en", 1), batch_rows("en", 2)
        assert len(first) == len(second) == WORDS_PER_BATCH
        assert word_list("en")[WORDS_PER_BATCH] == second[0]
        assert not set(r["term"] for r in first) & set(r["term"] for r in second)

    def test_batch_beyond_the_list_is_empty(self):
        assert batch_rows("en", total_batches("en") + 1) == []
        assert batch_rows("en", 0) == []


@pytest_asyncio.fixture
async def empty_decks(db_session):
    """The seeding tests count rows, so they need the decks to themselves."""
    await _wipe(db_session)
    yield db_session
    await _wipe(db_session)


async def _wipe(db):
    await db.execute(Flashcard.__table__.delete())
    await db.execute(VocabEntry.__table__.delete())
    await db.commit()


async def _seed_and_activate(db, lang, batch=1, status="pending"):
    """Catalog the whole list, then activate one batch — the common test setup."""
    await seed_catalog(db, lang)
    return await activate_batch(db, lang, batch, status)


@pytest.mark.asyncio
class TestCataloging:
    """Phase 1: every word becomes a row, with no cards yet."""

    async def _entries(self, db, lang):
        return await db.scalar(
            select(func.count(VocabEntry.id)).where(VocabEntry.source_lang == lang)
        )

    async def _cards(self, db, lang):
        return await db.scalar(
            select(func.count(Flashcard.id))
            .join(VocabEntry, Flashcard.vocab_entry_id == VocabEntry.id)
            .where(VocabEntry.source_lang == lang)
        )

    async def test_catalogs_the_whole_list_with_no_cards(self, empty_decks):
        added = await seed_catalog(empty_decks, "ro")
        assert added == len(word_list("ro"))
        assert await self._entries(empty_decks, "ro") == len(word_list("ro"))
        assert await self._cards(empty_decks, "ro") == 0

    async def test_cataloging_twice_inserts_nothing_the_second_time(self, empty_decks):
        first = await seed_catalog(empty_decks, "en")
        second = await seed_catalog(empty_decks, "en")
        assert first == len(word_list("en"))
        assert second == 0
        assert await self._entries(empty_decks, "en") == len(word_list("en"))

    async def test_does_not_duplicate_a_hand_added_word(self, empty_decks):
        # "priceput" is an early word in the Romanian list.
        empty_decks.add(
            VocabEntry(term="priceput", translation="my own gloss", source_lang="ro", target_lang="ro")
        )
        await empty_decks.commit()

        await seed_catalog(empty_decks, "ro")

        rows = (
            await empty_decks.execute(
                select(VocabEntry).where(
                    VocabEntry.source_lang == "ro", func.lower(VocabEntry.term) == "priceput"
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].translation == "my own gloss"  # untouched, not overwritten


@pytest.mark.asyncio
class TestActivating:
    """Phase 2: turning catalogued rows into cards, one batch at a time."""

    async def _cards(self, db, lang):
        return await db.scalar(
            select(func.count(Flashcard.id))
            .join(VocabEntry, Flashcard.vocab_entry_id == VocabEntry.id)
            .where(VocabEntry.source_lang == lang)
        )

    async def test_activating_a_batch_creates_two_cards_each(self, empty_decks):
        activated = await _seed_and_activate(empty_decks, "en", 1)
        assert activated == WORDS_PER_BATCH
        assert await self._cards(empty_decks, "en") == WORDS_PER_BATCH * 2

    async def test_activating_twice_creates_nothing_the_second_time(self, empty_decks):
        await seed_catalog(empty_decks, "ro")
        first = await activate_batch(empty_decks, "ro", 1)
        second = await activate_batch(empty_decks, "ro", 1)
        assert first == WORDS_PER_BATCH
        assert second == 0
        assert await self._cards(empty_decks, "ro") == WORDS_PER_BATCH * 2

    async def test_activating_one_batch_does_not_touch_the_rest_of_the_catalog(self, empty_decks):
        await seed_catalog(empty_decks, "en")
        await activate_batch(empty_decks, "en", 1)

        total_catalog = await empty_decks.scalar(
            select(func.count(VocabEntry.id)).where(VocabEntry.source_lang == "en")
        )
        assert total_catalog == len(word_list("en"))  # the whole list is still there
        assert await self._cards(empty_decks, "en") == WORDS_PER_BATCH * 2  # only batch 1 has cards

    async def test_next_batch_continues_where_the_last_one_stopped(self, empty_decks):
        await seed_catalog(empty_decks, "en")
        await activate_through(empty_decks, "en", 2)
        assert await loaded_batches(empty_decks, "en") == 2

        batch, activated = await activate_next_batch(empty_decks, "en")
        assert batch == 3
        assert activated == WORDS_PER_BATCH

        progress = await deck_progress(empty_decks, "en")
        assert progress["batches_loaded"] == 3
        assert progress["next_batch"] == 4
        assert len(progress["next_batch_preview"]) == 5

    async def test_activated_entries_are_definition_decks(self, empty_decks):
        await _seed_and_activate(empty_decks, "ro", 1)
        entry = (
            await empty_decks.execute(
                select(VocabEntry).where(VocabEntry.source_lang == "ro").limit(1)
            )
        ).scalar_one()
        # A word explained in its own language: both sides of the card are Romanian.
        assert entry.source_lang == entry.target_lang == "ro"
        assert entry.frequency is not None
        assert entry.batch == 1

    async def test_activating_skips_dismissed_words(self, empty_decks):
        await seed_catalog(empty_decks, "en")
        entry = (
            await empty_decks.execute(
                select(VocabEntry).where(VocabEntry.source_lang == "en", VocabEntry.batch == 1).limit(1)
            )
        ).scalar_one()
        entry.dismissed = True
        await empty_decks.commit()

        activated = await activate_batch(empty_decks, "en", 1)
        assert activated == WORDS_PER_BATCH - 1  # the dismissed word is left alone

        cards = await self._cards(empty_decks, "en")
        assert cards == (WORDS_PER_BATCH - 1) * 2


@pytest.mark.asyncio
class TestDeckProgress:

    async def test_catalog_size_is_independent_of_activation(self, empty_decks):
        await seed_catalog(empty_decks, "ro")
        progress = await deck_progress(empty_decks, "ro")
        assert progress["words_in_catalog"] == len(word_list("ro"))
        assert progress["words_loaded"] == 0  # cataloged, but nothing activated yet
        assert progress["batches_loaded"] == 0

        await activate_batch(empty_decks, "ro", 1)
        progress = await deck_progress(empty_decks, "ro")
        assert progress["words_in_catalog"] == len(word_list("ro"))  # unchanged
        assert progress["words_loaded"] == WORDS_PER_BATCH


@pytest.mark.asyncio
class TestBatchApi:

    async def test_progress_lists_both_decks(self, client: AsyncClient):
        res = await client.get("/api/v1/vocab/decks/batches")
        assert res.status_code == 200

        decks = {d["lang"]: d for d in res.json()["decks"]}
        assert set(decks) == {"en", "ro"}
        assert decks["en"]["batch_size"] == WORDS_PER_BATCH
        assert decks["en"]["words_available"] > 20000
        assert decks["ro"]["batches_total"] == total_batches("ro")

    async def test_loading_a_batch_moves_progress_forward(self, client: AsyncClient):
        before = await client.get("/api/v1/vocab/decks/batches")
        loaded_before = {d["lang"]: d["batches_loaded"] for d in before.json()["decks"]}

        res = await client.post("/api/v1/vocab/decks/en/batches/next")
        assert res.status_code == 201

        body = res.json()
        assert body["batch"] == loaded_before["en"] + 1
        assert body["cards_created"] == body["entries_added"] * 2
        assert body["progress"]["batches_loaded"] == body["batch"]
        # Cataloging happens alongside activation, so the rest of the list is
        # already sitting in Postgres too, not just the activated batch.
        assert body["progress"]["words_in_catalog"] > body["progress"]["words_loaded"]

    async def test_unknown_deck_is_a_404(self, client: AsyncClient):
        res = await client.post("/api/v1/vocab/decks/fr/batches/next")
        assert res.status_code == 404

    async def test_catalogued_but_unactivated_words_do_not_appear_in_the_list(
        self, empty_decks, client: AsyncClient
    ):
        """
        The whole point of cataloging ahead of activation: the Vocabulary page
        must never show the other tens of thousands of words just because they
        happen to already be rows in Postgres.
        """
        res = await client.post("/api/v1/vocab/decks/en/batches/next")
        assert res.json()["entries_added"] == WORDS_PER_BATCH
        catalog_size = res.json()["progress"]["words_in_catalog"]
        assert catalog_size > WORDS_PER_BATCH * 5  # the whole list, not just a batch

        listed = await client.get("/api/v1/vocab/?lang=en&limit=1000")
        assert listed.json()["total"] == WORDS_PER_BATCH

        stats = await client.get("/api/v1/vocab/stats")
        en_stats = next(d for d in stats.json()["decks"] if d["lang"] == "en")
        assert en_stats["entries"] == WORDS_PER_BATCH


@pytest.mark.asyncio
async def test_import_accepts_a_same_language_definition_deck(client: AsyncClient):
    """A definition deck glosses a word in its own language — lang == gloss_lang."""
    res = await client.post(
        "/api/v1/vocab/import",
        json={
            "lang": "en",
            "gloss_lang": "en",
            "entries": [
                {"term": "perspicacious", "translation": "having keen insight"}
            ],
        },
    )
    assert res.status_code == 201
    assert res.json()["imported"] == 1


@pytest.mark.asyncio
class TestRegloss:

    async def test_foreign_glosses_are_rewritten_from_the_word_list(self, empty_decks):
        # A word added before the decks were seeded: Romanian term, English gloss.
        entry = VocabEntry(
            term="a tăgădui",
            translation="to deny, to disavow",
            source_lang="ro",
            target_lang="en",
        )
        empty_decks.add(entry)
        await empty_decks.flush()
        for card in build_flashcards(entry, status="accepted"):
            card.repetitions = 4  # a word with review history behind it
            card.ease_factor = 2.1
            empty_decks.add(card)
        await empty_decks.commit()

        updated, unmatched = await regloss_from_list(empty_decks, "ro")
        assert updated == 1
        assert unmatched == []

        await empty_decks.refresh(entry)
        # Matched on the bare headword, since the list has no infinitive marker.
        assert entry.target_lang == "ro"
        assert entry.translation == "a refuza să accepte sau să creadă"
        assert entry.part_of_speech == "verb"
        assert entry.frequency is not None

        cards = (
            await empty_decks.execute(
                select(Flashcard).where(Flashcard.vocab_entry_id == entry.id)
            )
        ).scalars().all()
        # Card text follows the entry; the schedule it earned does not reset.
        assert any(entry.translation in c.answer for c in cards)
        assert all(c.repetitions == 4 and c.ease_factor == 2.1 for c in cards)

    async def test_words_missing_from_the_list_are_reported_not_mangled(self, empty_decks):
        entry = VocabEntry(
            term="dor",
            translation="longing, yearning",
            source_lang="ro",
            target_lang="en",
        )
        empty_decks.add(entry)
        await empty_decks.commit()

        updated, unmatched = await regloss_from_list(empty_decks, "ro")
        assert updated == 0
        assert unmatched == ["dor"]

        await empty_decks.refresh(entry)
        assert entry.translation == "longing, yearning"


def test_definition_prompt_asks_for_a_same_language_definition():
    from app.services.vocab_enricher import _system_prompt

    prompt = _system_prompt("ro", "ro")
    assert "Romanian lexicographer" in prompt
    assert "written IN\n  Romanian" in prompt

    bilingual = _system_prompt("ro", "en")
    assert "Romanian-English lexicographer" in bilingual


@pytest.mark.asyncio
class TestDismissingWords:
    """A word you throw out must not come back on the next deployment."""

    async def test_dismissed_word_is_not_reactivated(self, empty_decks, client: AsyncClient):
        await _seed_and_activate(empty_decks, "en", 1)

        entry = (
            await empty_decks.execute(
                select(VocabEntry).where(VocabEntry.source_lang == "en").limit(1)
            )
        ).scalar_one()
        term = entry.term

        res = await client.delete(f"/api/v1/vocab/{entry.id}")
        assert res.status_code == 204

        # The row survives, flagged, so activation still recognises the term.
        await empty_decks.refresh(entry)
        assert entry.dismissed is True
        cards = await empty_decks.scalar(
            select(func.count(Flashcard.id)).where(Flashcard.vocab_entry_id == entry.id)
        )
        assert cards == 0

        # Re-activating the same batch, as a redeploy would, leaves it out.
        assert await activate_batch(empty_decks, "en", 1) == 0
        rows = (
            await empty_decks.execute(
                select(func.count(VocabEntry.id)).where(VocabEntry.term == term)
            )
        ).scalar_one()
        assert rows == 1

    async def test_dismissed_words_are_hidden_and_not_counted(
        self, empty_decks, client: AsyncClient
    ):
        await _seed_and_activate(empty_decks, "ro", 1)
        entry = (
            await empty_decks.execute(
                select(VocabEntry).where(VocabEntry.source_lang == "ro").limit(1)
            )
        ).scalar_one()

        await client.delete(f"/api/v1/vocab/{entry.id}")

        listed = (await client.get("/api/v1/vocab/?lang=ro&limit=1000")).json()
        assert all(e["term"] != entry.term for e in listed["entries"])

        progress = await deck_progress(empty_decks, "ro")
        assert progress["words_dismissed"] == 1
        assert progress["words_loaded"] == WORDS_PER_BATCH - 1

    async def test_hand_added_words_are_deleted_outright(
        self, empty_decks, client: AsyncClient
    ):
        entry = VocabEntry(
            term="ghiozdan", translation="rucsac de școală",
            source_lang="ro", target_lang="ro",
        )
        empty_decks.add(entry)
        for card in build_flashcards(entry, status="accepted"):
            empty_decks.add(card)
        await empty_decks.commit()

        # No batch, so nothing would ever seed it back — no reason to keep a row.
        await client.delete(f"/api/v1/vocab/{entry.id}")
        remaining = await empty_decks.scalar(
            select(func.count(VocabEntry.id)).where(VocabEntry.id == entry.id)
        )
        assert remaining == 0


@pytest.mark.asyncio
async def test_a_stray_high_batch_word_is_not_read_as_batch_progress(empty_decks):
    """
    Re-glossing stamps a hand-added word with its rank in the list, which can
    be batch 39 in a deck that has only activated batch 1. It already has
    cards from being hand-added, so it should still count as one of your
    words — it just must not look like batch 39 has been activated.
    """
    await _seed_and_activate(empty_decks, "ro", 1)

    stray = VocabEntry(
        term="a desluși", translation="A face clar și de înțeles",
        source_lang="ro", target_lang="ro", frequency=4.0, batch=39,
    )
    empty_decks.add(stray)
    await empty_decks.flush()
    for card in build_flashcards(stray, status="accepted"):
        empty_decks.add(card)
    await empty_decks.commit()

    assert await loaded_batches(empty_decks, "ro") == 1

    progress = await deck_progress(empty_decks, "ro")
    assert progress["batches_loaded"] == 1
    assert progress["words_loaded"] == WORDS_PER_BATCH + 1  # the batch, plus the stray
    assert progress["next_batch"] == 2
