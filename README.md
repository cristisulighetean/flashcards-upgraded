# FastAPI Smart Flashcards

An async-first spaced-repetition app with two card sources: AI-generated
flashcards from your own uploaded documents (PDF, TXT, Markdown), and two
bundled vocabulary decks (English, Romanian) covering ~51,000 words between
them. Both study through the same **SM-2** scheduler.

## Features

**Document flashcards**
- Upload PDFs, TXT, or Markdown; text is chunked into overlapping windows and
  sent to an LLM (OpenAI-compatible, configurable model/base URL) which
  returns structured, deduplicated active-recall Q&A pairs.
- New cards land in **Quality Control** for a quick accept/discard pass
  before they enter the study rotation.

**Vocabulary decks**
- Two bundled word lists (`data/`, ~23k English + ~28k Romanian) — each word
  carries its definition *in its own language*, part of speech, and how
  common it is, and becomes two cards: **recognition** (word → meaning) and
  **production** (meaning → word).
- Seeding is two phases: the *entire* list is **cataloged** into Postgres
  immediately (bare rows, no cards — cheap, a few seconds for both decks),
  then batches of 500 are **activated** into real cards on demand. See
  [Vocabulary Decks](#vocabulary-decks) below.
- Every activated word passes through **Quality Control**, one deck at a
  time, before its Study button unlocks — read once, keep or throw out.
- Dismissing a bundled word marks it `dismissed` rather than deleting the
  row, so the next deployment (or the next batch load) doesn't hand it back.

**Study sessions**
- A session pulls up to 50 priority-ranked cards. Words you've never been
  graded on get a **first-look pass** (word + meaning shown together, no
  grading) before the graded quiz starts.
- Grading a card only happens on the first pass through a session; anything
  graded below "Good" comes back in a shuffled **repeat round** afterward —
  repeat rounds drill only, they don't re-submit to SM-2.
- Any card can be discarded mid-session (vocabulary discard removes both its
  recognition and production cards together).

**Spaced Repetition (SM-2)**
- Quality 0–5 grading recalculates ease factor, interval, and next due date.
- An ad-hoc priority score (recency relative to interval, weighted by ease)
  ranks what to study next; dialect-portable across SQLite and Postgres.

**Persistence**
- Postgres 16, async SQLAlchemy 2.0 + `asyncpg`, Alembic migrations.
- The frontend remembers which screen you were on across a page refresh
  (`sessionStorage`), so reloading mid-study doesn't bounce you to the
  dashboard.

## Tech stack

| Layer | Stack |
| --- | --- |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, pytest + aiosqlite |
| Database | Postgres 16 (SQLite in tests, and as the legacy pre-migration store) |
| Frontend | React 19, Vite, plain CSS (no framework) |
| AI | Any OpenAI-compatible endpoint (configured for Groq by default) |
| Containers | Docker Compose locally; images published to GHCR for Kubernetes |

## Project Structure
```text
.
├── alembic/                    # Migrations (0001 initial → 0006 dismiss flag)
├── data/                       # Bundled word lists (English + Romanian CSVs)
├── app/
│   ├── models/                 # Document, Flashcard, Review, VocabEntry
│   ├── routers/                # documents, flashcards, reviews, vocab
│   ├── schemas/                # Pydantic request/response models
│   ├── services/
│   │   ├── openai_service.py   # LLM call + retry
│   │   ├── text_chunker.py     # Document chunking
│   │   ├── file_parser.py      # PDF/TXT/MD extraction
│   │   ├── flashcard_validator.py
│   │   ├── sm2.py              # Spaced-repetition scheduler
│   │   ├── priority.py         # Cross-dialect "what to study next" ranking
│   │   ├── vocab_cards.py      # VocabEntry -> recognition/production cards
│   │   ├── vocab_enricher.py   # AI lookup for hand-added words
│   │   └── vocab_seed.py       # Catalog + batch-activate the bundled lists
│   ├── config.py                # pydantic-settings
│   ├── database.py              # Async engine/session
│   └── main.py                  # FastAPI app + lifespan (tables, seeding)
├── frontend/src/
│   ├── components/
│   │   ├── Dashboard.jsx        # Document library, stats, Study Collection
│   │   ├── UploadSection.jsx    # Document upload + generation
│   │   ├── ReviewSession.jsx    # 50-card sessions: first-look, quiz, repeat
│   │   ├── ReviewNewCards.jsx   # Quality Control for document cards
│   │   ├── CardBrowser.jsx      # Browse a specific card set
│   │   ├── VocabSection.jsx     # Vocabulary page: decks, batches, word list
│   │   └── VocabQualityControl.jsx  # Per-deck Quality Control
│   ├── api.js                   # Fetch wrappers for the whole API surface
│   └── App.jsx                  # View routing + sessionStorage persistence
├── scripts/
│   ├── seed_vocab.py             # One-off text/JSON list importer
│   └── migrate_sqlite_to_postgres.py  # Pre-Postgres data migration
├── tests/                        # pytest + aiosqlite (in-memory, isolated)
├── .github/workflows/            # CI: build + push images to GHCR
├── docker-compose.yml             # db (Postgres) + backend + frontend
├── Dockerfile                     # Backend image
├── frontend/Dockerfile            # Frontend image (Vite build + preview)
└── requirements.txt
```

## Running the Application

### 1. Requirements
- Python 3.11+
- Docker & Docker Compose
- An OpenAI-compatible API key (Groq by default — see `.env.example`)

### 2. Setup
```bash
git clone https://github.com/cristisulighetean/flashcards-upgraded.git
cd flashcards-upgraded/flashcards

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
```bash
cp .env.example .env
# Fill in GROQ_API_KEY (or point GROQ_BASE_URL/GROQ_MODEL elsewhere)
```

### 4. Run the stack
`docker-compose.yml` runs three services: `db` (Postgres 16), `backend`, and
`frontend`. `backend` waits for `db`'s healthcheck before starting.

Bring up Postgres and apply migrations *before* the backend ever starts.
This matters: the backend's own startup also bootstraps a bare schema via
`Base.metadata.create_all` (handy for tests, and so the app never refuses to
boot against an unmigrated database) — if `alembic upgrade head` runs after
the backend has already created the tables, migration 0001 fails with
`relation "documents" already exists`, since `alembic_version` was never
stamped.

```bash
# 1. Postgres only, and wait for it to report healthy.
docker compose up -d db

# 2. Apply migrations against the still-empty database.
docker compose build backend
docker compose run --rm backend python -m alembic upgrade head

# 3. Now bring up the rest — create_all is a no-op, the schema already matches.
docker compose up -d --build
```

If you already ran `docker compose up -d --build` first and hit exactly that
"already exists" error: the schema is fine (create_all already built it
correctly), it's only `alembic_version` that's missing. Fix it in place
without re-running the DDL:
```bash
docker compose run --rm backend python -m alembic stamp head
```

Swagger docs: **[http://localhost:8000/docs](http://localhost:8000/docs)**
App: **[http://localhost:3000/flashcards/](http://localhost:3000/flashcards/)**

### 5. Local development without Docker
Point `DATABASE_URL` at a Postgres you run yourself (or keep the `db`
container running and connect through its published port, `5433` on the host
— see the comment in `docker-compose.yml` on why it isn't `5432`), then:
```bash
alembic upgrade head
uvicorn app.main:app --reload
```

For the frontend: `cd frontend && npm install && npm run dev`.

### Migrating from the old SQLite setup
Earlier versions of this app ran on `flashcards.db` directly (still tracked
in the repo as a pre-migration snapshot). To move that data into a fresh
Postgres instance, do it **before the backend's first boot** — its startup
auto-seeds the vocabulary decks (`SEED_VOCAB_ON_STARTUP=true` by default), and
this script skips any table that already has rows, so a backend that booted
first silently wins the race and your real historical data never copies over:

```bash
docker compose up -d db
docker compose build backend
docker compose run --rm backend python -m alembic upgrade head   # empty DB first

python scripts/migrate_sqlite_to_postgres.py \
    --sqlite-path flashcards.db \
    --postgres-url postgresql+asyncpg://postgres:postgres@localhost:5433/flashcards

docker compose up -d --build   # seeding now finds real data already there — a no-op
```

It copies `documents`, `vocab_entries`, `flashcards`, then `reviews` (in that
FK-safe order), coercing SQLite's stringly-typed booleans and timestamps into
real values. Safe to re-run — it skips any table that already has rows on the
Postgres side, and refuses to run at all if it suspects the backend already
auto-seeded ahead of it.

## Vocabulary Decks

The CSVs in `data/` are the source of truth for the two starter decks and are
sorted most-common-first, so a batch is always "the next most useful words".

Seeding is two phases, both idempotent:

1. **Cataloging** — every word in a list (~23k English, ~28k Romanian)
   becomes a `VocabEntry` row in Postgres with no cards yet. Cheap: a bare row
   costs almost nothing, so this runs to completion on every boot in a couple
   of seconds. This is real Postgres data from the first deploy on, not
   something re-parsed from the CSV each time you ask for more.
2. **Activating** a batch creates the two cards (recognition, production) for
   the next 500 not-yet-activated words — this is what actually puts a word
   in front of you. `SEED_VOCAB_BATCHES` controls how many batches activate
   on boot (1, by default: the commonest 500 words per deck).

A cataloged-but-unactivated word is invisible everywhere in the app — the
Vocabulary page, Quality Control, `/vocab/stats` — all of them only ever
count activated words. `/vocab/decks/batches` is the one place that shows
both numbers side by side (`words_in_catalog` vs `words_loaded`), so you can
see the rest of the list sitting there without it ever looking like part of
your deck. The Vocabulary page's browse list itself only ever fetches 10
words at a time — search narrows it down instead of paging through hundreds.

Every activated word lands in Quality Control first — see below — so a stray
word pulled in from the whole word list gets read once and thrown out before
it can ever show up in a study session.

Deleting a seeded word marks it dismissed instead of removing the row: the
lists decide what a deck should hold, so a deleted row would be handed back on
the next deployment. Its cards go, it disappears from the app, and seeding
skips it forever. Re-adding the exact same word by hand or via bulk import is
still allowed — dismissal blocks re-seeding, not deliberate re-entry. Hand-
added words have no list behind them and are deleted outright.

| Setting | Default | Meaning |
| --- | --- | --- |
| `SEED_VOCAB_ON_STARTUP` | `true` | Seed when the app boots |
| `SEED_VOCAB_BATCHES` | `1` | Batches activated per deck at boot (500 words each) |
| `SEED_VOCAB_LANGS` | `en,ro` | Decks to seed |
| `SEED_VOCAB_STATUS` | `pending` | Activated words go to Quality Control; `accepted` skips it |

### Quality Control gates Study

Each deck on the Vocabulary page has its own Quality Control queue. A word
enters it whenever it is added — seeded on deploy, typed in by hand, or pulled
in as a new batch — and stays there, both of its cards excluded from study,
until you look at it: **Keep it** moves both cards into the study rotation,
**Don't need this** throws the word out for good (see dismissal, above).

The Study button for a deck is disabled while its queue is non-empty, so
working through Quality Control is not optional — it is how you decide, word
by word, which of the several thousand words in a bundled list you actually
want to learn, instead of discovering an unwanted one mid-session.

Load more words later from the Vocabulary screen, over the API, or on the CLI:

```bash
# where each deck stands
python -m app.services.vocab_seed --status

# rewrite words glossed in the wrong language using the bundled list
# (keeps review history; reports words the list does not cover)
python -m app.services.vocab_seed --lang ro --regloss

# one more batch of 500 English words (catalogs the list first if needed)
python -m app.services.vocab_seed --lang en --next

# just phase 1 — catalog the whole list, activate nothing
python -m app.services.vocab_seed --catalog-only

# or over HTTP
curl -X POST localhost:8000/api/v1/vocab/decks/en/batches/next
curl localhost:8000/api/v1/vocab/decks/batches
```

## Study Sessions

A session (`ReviewSession`) pulls up to 50 priority-ranked cards at a time —
enough that repetition inside one sitting actually does something, not so
many that it never ends.

1. **First look** — any card you've never been graded on (`repetitions === 0`)
   is shown once with its answer already visible, no grading, before the quiz
   starts. A vocabulary word's recognition and production cards are deduped
   to one introduction, not two.
2. **Quiz** — the graded pass. This is the only pass that submits to SM-2;
   grading a card here is what sets its real interval and due date.
3. **Repeat rounds** — anything graded below "Good" comes back, shuffled,
   until nothing is shaky. Repeat rounds are drill only and never re-submit
   to SM-2, so revisiting a card three times in one session doesn't collapse
   its schedule the way three real reviews would.

Any card can be discarded mid-session — a vocabulary discard removes both its
recognition and production cards together, so you're never asked the other
direction of a word you just said you don't need.

## API Reference

Full interactive docs at `/docs` (Swagger) once the backend is running. The
router surface:

| Router | Prefix | Covers |
| --- | --- | --- |
| `documents` | `/api/v1/documents` | Upload, list, delete source documents |
| `flashcards` | `/api/v1/flashcards` | List (priority-sorted), review, accept/discard, generate from a document |
| `reviews` | `/api/v1/reviews` | Submit an SM-2 grade |
| `vocab` | `/api/v1/vocab` | Add/import/list/edit/delete words, per-deck stats, batch cataloging & activation |

## Running Tests
Unit and integration tests for the SM-2 algorithm, chunking, validation,
vocabulary seeding (cataloging/activation), and the full API surface, against
an in-memory `aiosqlite` database.

```bash
pytest tests/ -v
```

## CI/CD

`.github/workflows/build-and-push.yml` builds the backend and frontend
images and pushes them to GitHub Container Registry (`ghcr.io`) on every push
to `main`, and on demand via `workflow_dispatch`. Backend tests run first and
gate the build — a red test suite never produces a new image.

Images:
- `ghcr.io/<owner>/flashcards-upgraded-backend:latest` and `:sha-<short-sha>`
- `ghcr.io/<owner>/flashcards-upgraded-frontend:latest` and `:sha-<short-sha>`

These are what a Kubernetes deployment pulls; `docker-compose.yml` still
builds locally from source for development.
