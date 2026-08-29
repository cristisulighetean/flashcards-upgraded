---
name: import-course-notes
description: >
  Turn a folder of notes/course documents (Obsidian vault notes, plain
  markdown, screenshot-heavy study notes, etc.) into flashcards in this
  app's Quality Control queue, then push them to a running instance
  (local or the deployed production one). Handles OCR-transcribing
  embedded screenshots, cleaning Obsidian-only syntax the app's own
  parser doesn't catch, grouping notes into sensible documents, authoring
  the actual question/answer cards, and pushing them idempotently.
  Trigger: "import these notes into flashcards", "turn my [X] course notes
  into flashcards", "add [course] to the flashcards app", "push notes to
  flashcards".
---

# Import Course Notes → Flashcards

Turns a folder of study notes into real flashcards in this app, end to end.
Built from a real run (CKAD course notes, 2026-08-29) that hit and fixed
several concrete bugs — read **Known Pitfalls** before pushing anything.

## When to use this

The user points at a folder of notes (any format — Obsidian vault export,
plain markdown, PDFs) and wants it turned into study material in this app.
Judgment-heavy steps stay manual (you, the agent, doing the reading/writing);
mechanical steps use the scripts in `scripts/` next to this file.

## Phase 1 — Discovery

Inventory the source folder. For each note, judge:
- **Topic** and rough **content density** (dense prose/command-rich vs.
  sparse/image-dependent vs. pure meta-checklist with no facts).
- Whether it leans on embedded images for real content. Obsidian vaults use
  `![[Pasted image <timestamp>.png]]` syntax — these files usually do NOT
  live next to the note. Find the vault's attachment folder by searching for
  one of the referenced filenames across the vault root, e.g.:
  ```bash
  find "/path/to/vault" -iname "Pasted image *.png" | head -1
  ```
  Don't assume a folder name — this session's vault used `Attachments/` but
  that's vault-specific configuration, not a convention.
- Natural topic groupings (do the notes already map to a course's own module
  structure? A cert's exam domains? Neither?).

Also flag: meta/checklist notes (TODO lists, lab-exercise checklists with no
prose answers, personal review scratch notes) — these are usually not good
flashcard source material and should be called out as candidates to skip.

## Phase 2 — Scope with the user

Use AskUserQuestion before doing any heavy work. At minimum, resolve:
1. **Staging** — everything in one batch, or split into batches (a large
   source corpus with many images to OCR can mean 100+ image reads; say so
   explicitly and let the user decide whether to stage it).
2. **Image-heavy/thin notes** — OCR them, skip them, or include as-is with
   thin coverage?
3. **Duplicate/overlapping content** (common when a folder mixes several
   courses covering the same ground) — skip duplicates, or accept overlap?
4. **Document grouping granularity** — one target document per source note
   (simplest, most granular Library sections) vs. concatenating related
   notes into fewer topic documents (matches a cert's exam domains better,
   but see the character-count-chunking caveat in Known Pitfalls).
5. **Target instance** — local Docker Compose or a deployed instance? Get
   the actual base URL and confirm reachability before starting:
   ```bash
   curl -sS --max-time 8 <base-url>/health
   ```
   Don't assume `https://` works just because the host resolves — a Tailscale
   MagicDNS host in this session only answered on plain `http://`.

## Phase 3 — OCR pass (only if scoped in)

For each image-heavy note, in parallel (one general-purpose subagent per
note — this needs Write access to save its output, so use `general-purpose`,
not `Explore`):
- Resolve every `![[...]]` reference against the attachment folder found in
  Phase 1.
- Read each image (the Read tool handles images directly — multimodal).
- Replace the embed marker in place with a plain-text transcription:
  verbatim command/output or YAML in a fenced code block; a clear prose
  description for diagrams/whiteboard sketches, in terms of the note's own
  subject matter.
- Never modify the source file — write an "enriched" copy to a scratch
  directory (e.g. this session's
  `<scratchpad>/<project>-import/enriched/<slug>.md` pattern).
- Report back image count transcribed and flag any illegible ones plainly
  rather than guessing at their content.

## Phase 4 — Clean + assemble

```bash
# Per source note that doesn't need OCR (or after OCR, on the enriched copy):
python3 scripts/clean_notes.py "source note.md" -o "<scratch>/cleaned/note.md"

# Once every source note has a cleaned/enriched copy, build a mapping.json
# (see assemble_docs.py's docstring for the exact shape) grouping them into
# target documents per the Phase 2 decision, then:
python3 scripts/assemble_docs.py mapping.json --out-dir "<scratch>/assembled"
```

`clean_notes.py` strips Obsidian embed/wiki-link syntax the app's own
`app/services/file_parser.py` doesn't catch (its regexes only match standard
`![alt](url)`/`[text](url)` markdown, not double-bracket Obsidian syntax).
`assemble_docs.py` concatenates with a plain-text `=====` separator between
merged source notes — see Known Pitfalls for why headings alone don't work
as a separator here.

## Phase 5 — Author flashcards

One general-purpose subagent per target document, in parallel. Point it at
the assembled document and this exact quality bar (copied verbatim from
`app/services/openai_service.py`'s `SYSTEM_PROMPT` so hand-authored cards
match what the app's own AI-generation path produces):

> Each flashcard must have a clear, specific QUESTION and a detailed,
> well-structured ANSWER. Questions should test deep understanding — prefer
> "Why", "How", "What happens when", "What is the difference between" over
> trivial "What is" questions.
>
> Use Markdown formatting inside answers: **bold** for key terms, bullet or
> numbered lists for multiple points, fenced code blocks with language tags
> for any commands/config (reproduced exactly from the source), short
> paragraph breaks between ideas. 2-3 short paragraphs or explanation +
> example. Include "why it works" reasoning, not just "what it is". Include
> a concrete example labeled **Example:** wherever the source supports one.
>
> Do not include flashcards that are too vague, trivial, or duplicative. Do
> not invent facts not present in (or reasonably inferable from) the source.

Hard limits (the bulk endpoint enforces these — `app/schemas/flashcard.py`):
question ≤ 500 chars, answer ≤ 4000 chars.

Each agent writes a plain JSON array (`[{"question": "...", "answer": "..."}]`)
to a scratch path and validates it (`python3 -m json.tool` or `json.load`)
before reporting back — don't trust an unvalidated file.

Card count: aim for real coverage of every distinct fact/concept in the
source, not a fixed number — a thin 200-word note might warrant 8 cards, a
dense 1500-word note might warrant 25.

## Phase 6 — Push to the app

```bash
python3 scripts/push_to_app.py \
  --base-url "http://flashcards.tailbebff1.ts.net/flashcards" \
  --doc-file "<scratch>/assembled/Target Document.md" \
  --cards-json "<scratch>/cards/target-document.json"
```

Run once per target document. This script is idempotent — safe to re-run if
you're unsure whether a previous call succeeded (see Known Pitfalls). Use
`--dry-run` first if you want to see what it would do without writing
anything. It never calls the accept endpoint — cards land as `pending` for
the user's own Quality Control pass, by design (same gate every other card
in this app goes through).

For a local Docker Compose target, `--base-url` is typically
`http://localhost:8000` (no `/flashcards` prefix — that prefix only exists
in the deployed-with-Traefik setup, driven by `root_path="/flashcards"` in
`app/main.py`, which is baked in at image-build time either way).

## Phase 7 — Verify

```bash
BASE="<base-url>/api/v1"
curl -sS "$BASE/documents/" | python3 -c "import json,sys; [print(d['filename'], d['id']) for d in json.load(sys.stdin)]"
curl -sS "$BASE/flashcards/?document_id=<id>&card_status=pending&limit=1000" | python3 -c "import json,sys; print(json.load(sys.stdin)['total'])"
```

Confirm each document's pending count matches what was authored. Spot-read
2-3 cards' `question`/`answer` fields to sanity-check formatting and content
before telling the user it's done. Tell the user which documents/cards were
created and that they're sitting in Quality Control, awaiting review.

## Known Pitfalls

- **`POST /flashcards/generate` (the AI-generation path) caps completions at
  4096 tokens** (`app/services/openai_service.py`). Requesting many verbose
  cards in one call (e.g. `num_cards=30`) reliably overflows this and Groq
  returns `json_validate_failed` — sometimes with a helpful
  `"max completion tokens reached before generating a valid document"`
  message, sometimes not. This is why this skill authors cards directly
  instead of relying on that endpoint. If `/flashcards/bulk` isn't available
  and you must fall back to `/generate`, keep `num_cards` small (≤ 8-10) and
  issue multiple calls per document.
- **`/flashcards/bulk` only dedupes within one call.** Calling it twice for
  the same document doubles the cards. `push_to_app.py` guards against this
  by checking existing pending questions first and only pushing the delta —
  don't bypass that check with a hand-rolled curl call.
- **`jq` is stricter about control characters than Python's JSON parser.**
  A hand-rolled `jq --slurpfile ... | curl -d "$payload"` pipeline can fail
  to parse the *server's response* even when the request itself was fine and
  the server-side create succeeded — which looks exactly like a failure but
  isn't, and retrying it creates duplicates. `push_to_app.py` never touches
  `jq`; it posts from a temp file and parses responses with Python directly.
  If you're improvising outside the script for any reason, do the same.
- **The bulk endpoint may not exist on an older deployed image** — it was
  added in commit `9de5765` (2026-08-29). `push_to_app.py` probes for it
  (`POST /flashcards/bulk` with an empty body: `422` means the route exists
  and validation ran, `404` means it doesn't) and exits with guidance rather
  than proceeding blind.
- **The chunker is character-count-based and heading-blind.** `app/services/
  text_chunker.py` splits on paragraph/character boundaries (2000 chars,
  200 overlap by default); `file_parser.py` strips markdown heading syntax
  *before* chunking ever runs. If you concatenate multiple distinct topics
  into one document, a chunk can straddle two unrelated topics — mitigated
  by `assemble_docs.py`'s plain-text separator, not eliminated. This mostly
  matters for the AI-generation path, less for hand-authored cards where you
  control topic boundaries directly by which agent authors which document.
- **Don't assume the scheme.** A Tailscale MagicDNS hostname can resolve
  fine over DNS while still only answering on `http://`, not `https://`.
  Check with a real `curl` before building anything around a base URL.
