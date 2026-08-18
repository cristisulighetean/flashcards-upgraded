from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Lang = Literal["ro", "en"]


class VocabEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    term: str
    translation: str
    source_lang: str
    target_lang: str
    part_of_speech: Optional[str] = None
    frequency: Optional[float] = None
    batch: Optional[int] = None
    example: Optional[str] = None
    example_translation: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    card_count: int = 0


class VocabListResponse(BaseModel):
    total: int
    entries: list[VocabEntryResponse]


class DeckStats(BaseModel):
    lang: str
    entries: int
    cards_pending: int
    cards_accepted: int


class VocabStatsResponse(BaseModel):
    decks: list[DeckStats]


class DeckBatchProgress(BaseModel):
    """How much of a bundled word list is cataloged, activated, and what comes next."""

    lang: str
    label: str
    words_available: int
    # Cataloged: a bare row in Postgres, no cards yet — reaches
    # words_available almost immediately, regardless of how much is activated.
    words_in_catalog: int = 0
    batch_size: int
    batches_total: int
    batches_loaded: int
    words_loaded: int
    words_dismissed: int = 0
    next_batch: Optional[int] = None
    next_batch_preview: list[str] = []


class DeckBatchesResponse(BaseModel):
    decks: list[DeckBatchProgress]


class LoadBatchResponse(BaseModel):
    lang: str
    batch: int
    entries_added: int
    cards_created: int
    progress: DeckBatchProgress


class ImportEntry(BaseModel):
    """One row of a seed list. Only term and translation are required."""

    term: str = Field(min_length=1, max_length=200)
    # 2000, not 500: a same-language definition is longer than a gloss.
    translation: str = Field(min_length=1, max_length=2000)
    part_of_speech: Optional[str] = Field(default=None, max_length=50)
    example: Optional[str] = Field(default=None, max_length=1000)
    example_translation: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("term", "translation")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # min_length=1 only checks the raw string — "  " passes it and would
        # otherwise become an empty, unstudiable card once stripped.
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class ImportRequest(BaseModel):
    """
    Bulk-load a prepared word list into one deck.

    No AI call is made: the translations supplied here are used verbatim, so
    a large list imports instantly and deterministically.
    """

    lang: Lang = Field(description="The language being learned (the deck).")
    gloss_lang: Lang = Field(
        default="en",
        description=(
            "Language the entries are explained in. Equal to `lang` for a "
            "definition deck, the other language for a translation deck."
        ),
    )
    entries: list[ImportEntry] = Field(min_length=1, max_length=2000)
    accepted: bool = Field(
        default=True,
        description="Import straight into the library, skipping quality control.",
    )


class ImportResponse(BaseModel):
    lang: str
    imported: int
    skipped_duplicates: list[str] = []
    cards_created: int


class AddWordsRequest(BaseModel):
    """Quick-add: terms are enriched by the AI unless fields are supplied."""

    terms: list[str] = Field(
        min_length=1,
        max_length=50,
        description="Words or phrases to add (1-50).",
    )
    source_lang: Lang = Field(default="ro", description="The language being learned.")
    target_lang: Lang = Field(default="en", description="Language of the translation.")
    enrich: bool = Field(
        default=True,
        description="Use the AI to fill translation, part of speech and example.",
    )


class VocabEntryUpdate(BaseModel):
    """Manual correction of an entry. Regenerates card text, keeps SM-2 state."""

    term: Optional[str] = Field(default=None, min_length=1, max_length=200)
    translation: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    part_of_speech: Optional[str] = Field(default=None, max_length=50)
    example: Optional[str] = Field(default=None, max_length=1000)
    example_translation: Optional[str] = Field(default=None, max_length=1000)
    notes: Optional[str] = Field(default=None, max_length=500)


class AddWordsResponse(BaseModel):
    added: int
    skipped_duplicates: list[str] = []
    cards_created: int
    entries: list[VocabEntryResponse]
