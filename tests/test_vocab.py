"""
Vocabulary feature — card building, validation, and the API flow.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.vocab_entry import VocabEntry
from app.services.vocab_cards import (
    BOTH_DIRECTIONS,
    DIRECTION_PRODUCTION,
    DIRECTION_RECOGNITION,
    build_card_fields,
    build_flashcards,
    sync_flashcards,
)
from app.services.vocab_enricher import VocabValidationError, validate_entries_json


def _entry(**kw) -> VocabEntry:
    defaults = dict(
        id="entry-1",
        term="cumpătat",
        translation="temperate, moderate",
        source_lang="ro",
        target_lang="en",
        part_of_speech="adjective",
        example="Este un om cumpătat.",
        example_translation="He is a temperate man.",
        notes=None,
    )
    defaults.update(kw)
    return VocabEntry(**defaults)


class TestCardBuilding:

    def test_recognition_asks_source_word(self):
        q, a = build_card_fields(_entry(), DIRECTION_RECOGNITION)
        assert q == "cumpătat"
        assert "temperate, moderate" in a

    def test_production_asks_translation(self):
        q, a = build_card_fields(_entry(), DIRECTION_PRODUCTION)
        assert q == "temperate, moderate"
        assert "cumpătat" in a

    def test_both_directions_produce_two_cards(self):
        cards = build_flashcards(_entry())
        assert len(cards) == 2
        assert {c.direction for c in cards} == set(BOTH_DIRECTIONS)

    def test_cards_are_vocab_typed_and_pending(self):
        for card in build_flashcards(_entry()):
            assert card.card_type == "vocab"
            assert card.status == "pending"
            assert card.document_id is None
            assert card.vocab_entry_id == "entry-1"

    def test_answer_includes_example_and_part_of_speech(self):
        _, a = build_card_fields(_entry(), DIRECTION_RECOGNITION)
        assert "adjective" in a
        assert "Este un om cumpătat." in a
        assert "He is a temperate man." in a

    def test_answer_omits_missing_optional_fields(self):
        _, a = build_card_fields(_entry(example=None, part_of_speech=None), DIRECTION_RECOGNITION)
        assert "Example" not in a
        assert a.strip() == "**temperate, moderate**"

    def test_unknown_direction_raises(self):
        with pytest.raises(ValueError, match="unknown direction"):
            build_card_fields(_entry(), "fr_de")

    def test_sync_rewrites_text_but_keeps_schedule(self):
        entry = _entry()
        cards = build_flashcards(entry)
        for c in cards:  # simulate prior review history
            c.ease_factor, c.interval, c.repetitions = 2.9, 12, 4

        entry.translation = "moderate"
        sync_flashcards(entry, cards)

        recog = next(c for c in cards if c.direction == DIRECTION_RECOGNITION)
        prod = next(c for c in cards if c.direction == DIRECTION_PRODUCTION)
        assert "moderate" in recog.answer
        assert prod.question == "moderate"
        # Scheduling state must survive an edit.
        assert all((c.ease_factor, c.interval, c.repetitions) == (2.9, 12, 4) for c in cards)


class TestEnricherValidation:

    def test_valid_payload(self):
        raw = {"entries": [{"term": "zăpadă", "translation": "snow",
                            "part_of_speech": "noun", "example": "E multă zăpadă.",
                            "example_translation": "There is a lot of snow.", "notes": None}]}
        out = validate_entries_json(raw, expected=1)
        assert out[0]["term"] == "zăpadă"
        assert out[0]["notes"] is None

    def test_missing_entries_key_raises(self):
        with pytest.raises(VocabValidationError, match="Missing required key"):
            validate_entries_json({"words": []}, expected=1)

    def test_empty_array_raises(self):
        with pytest.raises(VocabValidationError, match="empty"):
            validate_entries_json({"entries": []}, expected=1)

    def test_blank_translation_raises(self):
        with pytest.raises(VocabValidationError, match="translation"):
            validate_entries_json({"entries": [{"term": "a", "translation": "  "}]}, expected=1)

    def test_count_mismatch_is_tolerated(self):
        raw = {"entries": [{"term": "a", "translation": "b"}]}
        assert len(validate_entries_json(raw, expected=3)) == 1

    def test_non_string_fields_become_none(self):
        raw = {"entries": [{"term": "a", "translation": "b", "part_of_speech": 42}]}
        assert validate_entries_json(raw, expected=1)[0]["part_of_speech"] is None


def _mock_llm(entries: list[dict]) -> MagicMock:
    import json
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = json.dumps({"entries": entries})
    return resp


SAMPLE = [{"term": "zăpadă", "translation": "snow", "part_of_speech": "noun",
           "example": "E multă zăpadă.", "example_translation": "There is a lot of snow.",
           "notes": None}]


class TestVocabAPI:

    @patch("app.services.vocab_enricher.AsyncOpenAI")
    async def test_add_word_creates_entry_and_two_cards(self, mock_cls, client: AsyncClient):
        mock_cls.return_value.chat = MagicMock()
        mock_cls.return_value.chat.completions = MagicMock()
        mock_cls.return_value.chat.completions.create = AsyncMock(return_value=_mock_llm(SAMPLE))

        r = await client.post("/api/v1/vocab/", json={"terms": ["zapada"]})
        assert r.status_code == 201
        body = r.json()
        assert body["added"] == 1
        assert body["cards_created"] == 2
        assert body["entries"][0]["translation"] == "snow"

    @patch("app.services.vocab_enricher.AsyncOpenAI")
    async def test_duplicate_word_is_skipped(self, mock_cls, client: AsyncClient):
        mock_cls.return_value.chat = MagicMock()
        mock_cls.return_value.chat.completions = MagicMock()
        mock_cls.return_value.chat.completions.create = AsyncMock(return_value=_mock_llm(SAMPLE))

        await client.post("/api/v1/vocab/", json={"terms": ["zapada"]})
        again = await client.post("/api/v1/vocab/", json={"terms": ["zapada"]})
        assert again.json()["added"] == 0
        assert again.json()["skipped_duplicates"] == ["zăpadă"]

    async def test_add_without_enrich_parses_dash_syntax(self, client: AsyncClient):
        r = await client.post(
            "/api/v1/vocab/",
            json={"terms": ["carte - book"], "enrich": False},
        )
        assert r.status_code == 201
        assert r.json()["entries"][0]["term"] == "carte"
        assert r.json()["entries"][0]["translation"] == "book"

    async def test_empty_terms_rejected(self, client: AsyncClient):
        r = await client.post("/api/v1/vocab/", json={"terms": []})
        assert r.status_code == 422

    async def test_vocab_cards_are_filterable(self, client: AsyncClient):
        await client.post("/api/v1/vocab/", json={"terms": ["masa - table"], "enrich": False})
        r = await client.get("/api/v1/flashcards/?card_status=pending&card_type=vocab")
        assert r.status_code == 200
        cards = r.json()["flashcards"]
        assert cards, "expected vocabulary cards"
        assert all(c["card_type"] == "vocab" for c in cards)
        assert all(c["document_id"] is None for c in cards)

    async def test_legacy_cards_excluded_from_vocab_filter(self, client: AsyncClient):
        r = await client.get("/api/v1/flashcards/?card_type=qa&card_status=pending")
        assert all(c["card_type"] == "qa" for c in r.json()["flashcards"])

    async def test_update_entry_rewrites_cards(self, client: AsyncClient):
        created = await client.post(
            "/api/v1/vocab/", json={"terms": ["fereastra - windo"], "enrich": False}
        )
        entry_id = created.json()["entries"][0]["id"]

        patched = await client.patch(
            f"/api/v1/vocab/{entry_id}", json={"translation": "window"}
        )
        assert patched.status_code == 200
        assert patched.json()["translation"] == "window"

        cards = (await client.get("/api/v1/flashcards/?card_status=pending&card_type=vocab")).json()
        texts = [c["question"] + c["answer"] for c in cards["flashcards"]]
        assert any("window" in t for t in texts)

    async def test_delete_entry_removes_its_cards(self, client: AsyncClient):
        created = await client.post(
            "/api/v1/vocab/", json={"terms": ["scaun - chair"], "enrich": False}
        )
        entry_id = created.json()["entries"][0]["id"]

        assert (await client.delete(f"/api/v1/vocab/{entry_id}")).status_code == 204

        remaining = (await client.get("/api/v1/vocab/")).json()
        assert all(e["id"] != entry_id for e in remaining["entries"])

        cards = (await client.get("/api/v1/flashcards/?card_status=pending&card_type=vocab")).json()
        assert all("chair" not in c["answer"] for c in cards["flashcards"])

    async def test_update_missing_entry_returns_404(self, client: AsyncClient):
        r = await client.patch("/api/v1/vocab/nope", json={"translation": "x"})
        assert r.status_code == 404

    async def test_delete_missing_entry_returns_404(self, client: AsyncClient):
        assert (await client.delete("/api/v1/vocab/nope")).status_code == 404

    async def test_search_filters_entries(self, client: AsyncClient):
        await client.post("/api/v1/vocab/", json={"terms": ["pisica - cat"], "enrich": False})
        r = await client.get("/api/v1/vocab/?search=cat")
        assert any("cat" in e["translation"] for e in r.json()["entries"])


class TestLanguageDecks:
    """Two decks: the 'lang' is the language being learned, not a direction."""

    async def _import(self, client: AsyncClient, lang: str, entries: list[dict], **kw):
        payload = {"lang": lang, "gloss_lang": "ro" if lang == "en" else "en",
                   "entries": entries}
        payload.update(kw)
        return await client.post("/api/v1/vocab/import", json=payload)

    async def test_import_seeds_a_deck_without_ai(self, client: AsyncClient):
        r = await self._import(client, "en", [
            {"term": "ubiquitous", "translation": "omniprezent", "part_of_speech": "adjective"},
            {"term": "resilient", "translation": "rezilient"},
        ])
        assert r.status_code == 201
        body = r.json()
        assert body["imported"] == 2
        assert body["cards_created"] == 4
        assert body["lang"] == "en"

    async def test_imported_words_are_accepted_by_default(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "thrive", "translation": "a prospera"}])
        r = await client.get("/api/v1/flashcards/?card_type=vocab&lang=en")
        assert any(c["question"] == "thrive" for c in r.json()["flashcards"])

    async def test_import_can_route_to_quality_control(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "prudent", "translation": "prudent"}],
                           accepted=False)
        r = await client.get("/api/v1/flashcards/?card_status=pending&card_type=vocab&lang=en")
        assert any(c["question"] == "prudent" for c in r.json()["flashcards"])

    async def test_same_word_allowed_in_both_decks(self, client: AsyncClient):
        # 'a' words that legitimately exist in each language must not collide.
        en = await self._import(client, "en", [{"term": "actual", "translation": "real"}])
        ro = await self._import(client, "ro", [{"term": "actual", "translation": "current"}])
        assert en.json()["imported"] == 1
        assert ro.json()["imported"] == 1

    async def test_duplicates_skipped_within_a_deck(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "diligent", "translation": "harnic"}])
        again = await self._import(client, "en", [{"term": "Diligent", "translation": "harnic"}])
        assert again.json()["imported"] == 0
        assert again.json()["skipped_duplicates"] == ["Diligent"]

    async def test_import_rejects_identical_languages(self, client: AsyncClient):
        r = await client.post("/api/v1/vocab/import", json={
            "lang": "en", "gloss_lang": "en",
            "entries": [{"term": "x", "translation": "y"}]})
        assert r.status_code == 422

    async def test_lang_filter_separates_the_decks(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "meadow", "translation": "pajiște"}])
        await self._import(client, "ro", [{"term": "pajiște", "translation": "meadow"}])

        en_cards = (await client.get("/api/v1/flashcards/?card_type=vocab&lang=en")).json()
        ro_cards = (await client.get("/api/v1/flashcards/?card_type=vocab&lang=ro")).json()

        assert any(c["question"] == "meadow" for c in en_cards["flashcards"])
        assert all(c["question"] != "pajiște" or c["direction"] == "production"
                   for c in en_cards["flashcards"])
        assert any(c["question"] == "pajiște" for c in ro_cards["flashcards"])

    async def test_listing_entries_filters_by_deck(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "steadfast", "translation": "statornic"}])
        en = (await client.get("/api/v1/vocab/?lang=en")).json()
        ro = (await client.get("/api/v1/vocab/?lang=ro")).json()
        assert any(e["term"] == "steadfast" for e in en["entries"])
        assert all(e["term"] != "steadfast" for e in ro["entries"])

    async def test_stats_report_each_deck(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "candour", "translation": "sinceritate"}])
        await self._import(client, "ro", [{"term": "sinceritate", "translation": "candour"}])

        stats = (await client.get("/api/v1/vocab/stats")).json()
        by_lang = {d["lang"]: d for d in stats["decks"]}
        assert by_lang["en"]["entries"] >= 1
        assert by_lang["ro"]["entries"] >= 1
        assert by_lang["en"]["cards_accepted"] >= 2

    async def test_directions_are_skill_named_not_language_named(self, client: AsyncClient):
        await self._import(client, "en", [{"term": "elusive", "translation": "evaziv"}])
        cards = (await client.get("/api/v1/flashcards/?card_type=vocab&lang=en")).json()
        dirs = {c["direction"] for c in cards["flashcards"]}
        assert dirs <= {"recognition", "production"}
        # The English deck asks the English word on its recognition card.
        recog = [c for c in cards["flashcards"]
                 if c["direction"] == "recognition" and c["question"] == "elusive"]
        assert recog, "recognition card should show the learned term"
