"""
Turns a vocabulary entry into flashcards.

An entry is content; a flashcard is a scheduling unit.  Each practised
direction becomes its own card so SM-2 can track recognition and production
separately — knowing a word when you read it is a different skill from
recalling it when you need to write it.

Directions are named by *skill*, not by language pair: an entry in the English
deck and one in the Romanian deck both have a "recognition" and a "production"
card, each pointing whichever way that deck requires.

The question/answer text is written onto the flashcard at build time, which is
what lets every existing screen (study, quality control, browser) render a
vocabulary card without knowing anything about vocabulary.
"""
from app.models.flashcard import Flashcard
from app.models.vocab_entry import VocabEntry

DIRECTION_RECOGNITION = "recognition"  # show the term, recall its meaning
DIRECTION_PRODUCTION = "production"    # show the meaning, produce the term

BOTH_DIRECTIONS = (DIRECTION_RECOGNITION, DIRECTION_PRODUCTION)

DIRECTION_LABELS = {
    DIRECTION_RECOGNITION: "Recognition",
    DIRECTION_PRODUCTION: "Production",
}


def _answer_markdown(headline: str, entry: VocabEntry, show_example: bool = True) -> str:
    parts = [f"**{headline}**"]
    if entry.part_of_speech:
        parts[0] += f"  \n*{entry.part_of_speech}*"

    if show_example and entry.example:
        example = f"**Example:** {entry.example}"
        if entry.example_translation:
            example += f"  \n*{entry.example_translation}*"
        parts.append(example)

    if entry.notes:
        parts.append(entry.notes)

    return "\n\n".join(parts)


def build_card_fields(entry: VocabEntry, direction: str) -> tuple[str, str]:
    """Return the (question, answer) text for one direction of an entry."""
    if direction == DIRECTION_RECOGNITION:
        return entry.term, _answer_markdown(entry.translation, entry)
    if direction == DIRECTION_PRODUCTION:
        return entry.translation, _answer_markdown(entry.term, entry)
    raise ValueError(f"unknown direction: {direction}")


def build_flashcards(
    entry: VocabEntry,
    directions: tuple[str, ...] = BOTH_DIRECTIONS,
    status: str = "pending",
) -> list[Flashcard]:
    """Create the flashcard rows for an entry, one per direction."""
    cards: list[Flashcard] = []
    for direction in directions:
        question, answer = build_card_fields(entry, direction)
        cards.append(
            Flashcard(
                vocab_entry_id=entry.id,
                document_id=None,
                question=question,
                answer=answer,
                status=status,
                card_type="vocab",
                direction=direction,
            )
        )
    return cards


def sync_flashcards(entry: VocabEntry, cards: list[Flashcard]) -> None:
    """
    Rewrite card text after an entry is edited.

    Scheduling state (ease, interval, due date) is deliberately preserved —
    fixing a typo in a translation should not reset your review history.
    """
    for card in cards:
        if card.direction:
            card.question, card.answer = build_card_fields(entry, card.direction)
