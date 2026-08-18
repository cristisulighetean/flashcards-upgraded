from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./flashcards.db"

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama3-8b-8192"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Text chunking
    max_chunk_size: int = 2000
    max_chunk_overlap: int = 200

    # Flashcard generation
    default_num_cards: int = 10
    max_num_cards: int = 30

    # File upload
    max_file_size_mb: int = 10

    # Vocabulary seeding (data/*.csv, most common words first)
    seed_vocab_on_startup: bool = True
    # One batch (500 words) to start: everything lands in Quality Control, so
    # a bigger number here just means more to read and reject before you can
    # study anything. Load more deliberately, batch by batch, once caught up.
    seed_vocab_batches: int = 1
    seed_vocab_langs: str = "en,ro"
    # pending: every seeded word passes through Quality Control first, so you
    # read it once and throw out what you do not want before it enters study.
    seed_vocab_status: str = "pending"  # pending (quality control) | accepted

    @property
    def seed_vocab_lang_list(self) -> list[str]:
        return [lang.strip() for lang in self.seed_vocab_langs.split(",") if lang.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
