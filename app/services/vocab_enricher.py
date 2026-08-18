"""
Fills in the details of a vocabulary word using the LLM.

You type a word; this supplies the translation, part of speech and an example
sentence.  Reuses the retry/rate-limit handling from the flashcard generator.
"""
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from app.config import get_settings
from app.services.openai_service import LLMRateLimitError, _call_llm_with_retry

logger = logging.getLogger(__name__)
settings = get_settings()

LANG_NAMES = {"ro": "Romanian", "en": "English"}

MAX_TERM_LEN = 200
MAX_BATCH = 50


class VocabValidationError(ValueError):
    pass


def _system_prompt(source_lang: str, target_lang: str) -> str:
    src = LANG_NAMES.get(source_lang, source_lang)
    tgt = LANG_NAMES.get(target_lang, target_lang)
    return f"""You are a {src}-{tgt} lexicographer building vocabulary flashcards.

For each {src} term you are given, produce:
- "term": the term, corrected to its standard dictionary form (fix spelling and
  diacritics; for verbs use the infinitive). Keep the learner's word — do not
  swap it for a synonym.
- "translation": the {tgt} translation. Give the 1-3 most common senses,
  comma-separated, most common first. No explanations.
- "part_of_speech": one of noun, verb, adjective, adverb, preposition,
  conjunction, pronoun, interjection, phrase.
- "example": ONE natural short sentence in {src} using the term.
- "example_translation": that sentence translated into {tgt}.
- "notes": OPTIONAL. Only when genuinely useful — irregular forms, false
  friends, register (formal/slang). Otherwise omit or use null. Keep under 100
  characters. Do not pad.

Rules:
- If a term is misspelled, correct it and translate the corrected form.
- If a term is already in {tgt} rather than {src}, still translate between the
  two languages, setting "term" to the {src} form.
- Return one object per input term, in the same order.
- Respond ONLY with valid JSON in exactly this shape, no markdown wrapper:

{{"entries": [{{"term": "...", "translation": "...", "part_of_speech": "...",
  "example": "...", "example_translation": "...", "notes": null}}]}}"""


def validate_entries_json(raw: dict, expected: int) -> list[dict]:
    """Validate the LLM's JSON payload and return clean entry dicts."""
    if not isinstance(raw, dict):
        raise VocabValidationError("Expected a JSON object at the top level.")

    entries = raw.get("entries")
    if entries is None:
        raise VocabValidationError("Missing required key 'entries' in response.")
    if not isinstance(entries, list):
        raise VocabValidationError("'entries' must be a JSON array.")
    if not entries:
        raise VocabValidationError("'entries' array is empty.")

    def _clean(value, limit: int) -> Optional[str]:
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value[:limit] if value else None

    validated: list[dict] = []
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            raise VocabValidationError(f"entries[{idx}] must be an object.")

        term = _clean(item.get("term"), MAX_TERM_LEN)
        translation = _clean(item.get("translation"), 500)
        if not term:
            raise VocabValidationError(f"entries[{idx}].term must be a non-empty string.")
        if not translation:
            raise VocabValidationError(
                f"entries[{idx}].translation must be a non-empty string."
            )

        validated.append(
            {
                "term": term,
                "translation": translation,
                "part_of_speech": _clean(item.get("part_of_speech"), 50),
                "example": _clean(item.get("example"), 1000),
                "example_translation": _clean(item.get("example_translation"), 1000),
                "notes": _clean(item.get("notes"), 500),
            }
        )

    if len(validated) != expected:
        logger.warning(
            "LLM returned %d entries for %d terms; using what came back.",
            len(validated),
            expected,
        )
    return validated


async def enrich_terms(
    terms: list[str],
    source_lang: str = "ro",
    target_lang: str = "en",
) -> list[dict]:
    """
    Look up *terms* and return a dict of vocabulary fields for each.

    Raises LLMRateLimitError or VocabValidationError on failure.
    """
    terms = [t.strip() for t in terms if t and t.strip()]
    if not terms:
        return []
    if len(terms) > MAX_BATCH:
        raise VocabValidationError(f"Too many terms at once (max {MAX_BATCH}).")

    client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)

    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(terms))
    response = await _call_llm_with_retry(
        client=client,
        messages=[
            {"role": "system", "content": _system_prompt(source_lang, target_lang)},
            {"role": "user", "content": f"Terms:\n{numbered}"},
        ],
    )

    raw_content = response.choices[0].message.content or "{}"
    try:
        raw_json = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise VocabValidationError(f"AI returned invalid JSON: {exc}") from exc

    return validate_entries_json(raw_json, expected=len(terms))
