"""
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import AsyncSessionLocal, Base, engine
from app.routers import documents, flashcards, reviews, vocab
from app.services.vocab_seed import seed_startup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables and seed the word decks (Alembic handles migrations in prod)."""
    async with engine.begin() as conn:
        # Import models so SQLAlchemy knows about them
        import app.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")

    # Idempotent: the full word list is cataloged (cheap, no cards) once,
    # then the configured batch count is activated — a no-op thereafter.
    settings = get_settings()
    if settings.seed_vocab_on_startup:
        await seed_startup(
            AsyncSessionLocal,
            settings.seed_vocab_lang_list,
            settings.seed_vocab_batches,
            settings.seed_vocab_status,
        )

    yield
    await engine.dispose()
    logger.info("Database engine disposed.")


app = FastAPI(
    title="Smart Flashcard API",
    description=(
        "Upload documents (PDF, TXT, Markdown), generate AI-powered flashcards, "
        "and review them with SM-2 spaced repetition."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/flashcards",
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
API_PREFIX = "/api/v1"

app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(flashcards.router, prefix=API_PREFIX)
app.include_router(reviews.router, prefix=API_PREFIX)
app.include_router(vocab.router, prefix=API_PREFIX)


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok"}
