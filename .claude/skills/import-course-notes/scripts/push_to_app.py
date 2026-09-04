#!/usr/bin/env python3
"""
Upload one assembled document to the flashcards app and bulk-create its
authored flashcards, idempotently.

A card may optionally carry an `image_path` (absolute path to a local
PNG/JPG/GIF/WEBP file — e.g. the original screenshot behind a diagram card
authored during the OCR pass) alongside `question`/`answer`. This script
reads it, base64-encodes it, and sends it as `image_base64`/
`image_content_type` in the bulk request — see `POST /flashcards/bulk` and
`app/models/flashcard.py` (`image_data`/`image_content_type` columns, qa
cards only, capped at 3MB per image server-side).

This exists because of two real bugs hit doing this by hand:

1. `jq` rejects raw control characters that Python's `json.loads(strict=False)`
   tolerates, so hand-rolled `jq --slurpfile ... | curl -d "$payload"` pipelines
   can silently mis-parse the SERVER'S RESPONSE (not the request) and report a
   failure for a call that actually succeeded. This script never pipes
   anything through `jq` — it POSTs the JSON payload straight from a temp
   file (`curl -d @file`) and parses responses with Python's own `json`
   module, sidestepping the whole class of bug.
2. `POST /flashcards/bulk` only dedupes *within* one call. Retrying a call
   you think failed (see #1) silently doubles the cards. This script always
   checks the document's current pending questions first and only pushes
   the delta — safe to re-run.

Usage:
    python3 push_to_app.py \\
        --base-url http://flashcards.tailbebff1.ts.net/flashcards \\
        --doc-file "/path/to/assembled/CKAD - Pod Design.md" \\
        --cards-json "/path/to/cards/pod-design.json" \\
        [--dry-run]

--base-url is the app's root_path prefix (e.g. ".../flashcards" for the
production Tailscale deployment, or "http://localhost:8000" for a local
docker-compose backend with no prefix) — this script appends /api/v1 itself.
"""
import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_QUESTION_LEN = 500
MAX_ANSWER_LEN = 4000
MAX_IMAGE_BYTES = 3 * 1024 * 1024  # matches the backend's cap
IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def curl_json(args: list[str], timeout: int) -> tuple[int, dict | list | None, str]:
    """Run curl, return (http_code, parsed_json_or_None, raw_text)."""
    result = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), "-w", "\n%{http_code}"] + args,
        capture_output=True, text=True,
    )
    raw = result.stdout
    body, _, code = raw.rpartition("\n")
    try:
        parsed = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return int(code) if code.strip().isdigit() else 0, parsed, body


def probe_bulk_endpoint(base: str) -> bool:
    code, _, _ = curl_json(
        ["-X", "POST", f"{base}/flashcards/bulk", "-H", "Content-Type: application/json", "-d", "{}"],
        timeout=15,
    )
    if code == 404:
        return False
    return True  # 422 (validation ran, route exists) or anything else non-404


def find_or_upload_document(base: str, doc_file: Path, dry_run: bool) -> str:
    filename = doc_file.name
    code, docs, raw = curl_json(["-X", "GET", f"{base}/documents/"], timeout=15)
    if code != 200 or docs is None:
        print(f"!!! could not list documents (http {code}): {raw[:300]}", file=sys.stderr)
        sys.exit(1)

    for d in docs:
        if d.get("filename") == filename:
            print(f"  reusing existing document {d['id']}", file=sys.stderr)
            return d["id"]

    if dry_run:
        print(f"  [dry-run] would upload {filename}", file=sys.stderr)
        return "DRY-RUN-DOC-ID"

    # Quoted @"path" and filename="...": curl's -F splits an unquoted @path
    # on literal commas (it doubles as multi-file syntax), which silently
    # breaks any source filename containing one — e.g. "Containers (ECS,
    # Fargate, ECR, EKS).md" — with a bare "(26) Failed to open/read local
    # data from file" and no indication that filename content was the cause.
    code, resp, raw = curl_json(
        ["-X", "POST", f"{base}/documents/upload",
         "-F", f'file=@"{doc_file}";type=text/markdown;filename="{filename}"'],
        timeout=30,
    )
    if code != 201 or not resp or "id" not in resp:
        print(f"!!! upload failed (http {code}): {raw[:300]}", file=sys.stderr)
        sys.exit(1)
    print(f"  uploaded new document {resp['id']}", file=sys.stderr)
    return resp["id"]


def load_and_validate_cards(cards_json: Path) -> list[dict]:
    raw = json.loads(cards_json.read_text(encoding="utf-8"), strict=False)
    if not isinstance(raw, list):
        print(f"!!! {cards_json} must be a plain JSON array of {{question, answer}} objects", file=sys.stderr)
        sys.exit(1)

    valid = []
    for i, item in enumerate(raw):
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        if not q or not a:
            print(f"  skipping card {i}: missing question or answer", file=sys.stderr)
            continue
        if len(q) > MAX_QUESTION_LEN:
            print(f"  skipping card {i}: question exceeds {MAX_QUESTION_LEN} chars ({len(q)})", file=sys.stderr)
            continue
        if len(a) > MAX_ANSWER_LEN:
            print(f"  skipping card {i}: answer exceeds {MAX_ANSWER_LEN} chars ({len(a)})", file=sys.stderr)
            continue

        card = {"question": q, "answer": a}
        image_path = item.get("image_path")
        if image_path:
            img_file = Path(image_path)
            content_type = IMAGE_CONTENT_TYPES.get(img_file.suffix.lower())
            if not img_file.is_file():
                print(f"  skipping image for card {i}: {image_path} not found (card kept, no image)", file=sys.stderr)
            elif not content_type:
                print(f"  skipping image for card {i}: unsupported extension {img_file.suffix!r} (card kept, no image)", file=sys.stderr)
            elif img_file.stat().st_size > MAX_IMAGE_BYTES:
                print(f"  skipping image for card {i}: {image_path} exceeds {MAX_IMAGE_BYTES} bytes (card kept, no image)", file=sys.stderr)
            else:
                card["image_base64"] = base64.b64encode(img_file.read_bytes()).decode("ascii")
                card["image_content_type"] = content_type

        valid.append(card)
    return valid


def existing_pending_questions(base: str, doc_id: str) -> set[str]:
    code, resp, raw = curl_json(
        ["-X", "GET", f"{base}/flashcards/?document_id={doc_id}&card_status=pending&limit=1000"],
        timeout=15,
    )
    if code != 200 or resp is None:
        print(f"!!! could not list existing flashcards (http {code}): {raw[:300]}", file=sys.stderr)
        sys.exit(1)
    return {c["question"].strip().lower() for c in resp["flashcards"]}


def push_delta(base: str, doc_id: str, delta: list[dict], dry_run: bool) -> int:
    if dry_run:
        print(f"  [dry-run] would create {len(delta)} card(s)", file=sys.stderr)
        return len(delta)

    payload = {"document_id": doc_id, "cards": delta}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        payload_path = f.name

    try:
        code, resp, raw = curl_json(
            ["-X", "POST", f"{base}/flashcards/bulk",
             "-H", "Content-Type: application/json", "-d", f"@{payload_path}"],
            timeout=90,
        )
    finally:
        Path(payload_path).unlink(missing_ok=True)

    if code != 201 or not resp:
        print(f"!!! bulk-create failed (http {code}): {raw[:500]}", file=sys.stderr)
        print("    Re-check the actual pending count before retrying — the create may have", file=sys.stderr)
        print("    partially succeeded server-side even if this response looks like an error.", file=sys.stderr)
        sys.exit(1)
    return resp["total"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True, help="App root, e.g. http://host/flashcards")
    parser.add_argument("--doc-file", required=True, type=Path, help="Assembled markdown document to upload")
    parser.add_argument("--cards-json", required=True, type=Path, help="Authored {question, answer} pairs (plain JSON array)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without writing anything")
    args = parser.parse_args()

    base = args.base_url.rstrip("/") + "/api/v1"

    if not probe_bulk_endpoint(base):
        print("!!! POST /flashcards/bulk returned 404 — this deployment doesn't have the", file=sys.stderr)
        print("    bulk-import endpoint (added in commit 9de5765). Either redeploy the", file=sys.stderr)
        print("    flashcards backend, or fall back to POST /flashcards/generate with a", file=sys.stderr)
        print("    small num_cards (<=8-10) per call — see SKILL.md's Known Pitfalls.", file=sys.stderr)
        sys.exit(1)

    print(f"=== {args.doc_file.name} ===", file=sys.stderr)
    doc_id = find_or_upload_document(base, args.doc_file, args.dry_run)

    cards = load_and_validate_cards(args.cards_json)
    if not cards:
        print("!!! no valid cards to push", file=sys.stderr)
        sys.exit(1)

    existing = set() if args.dry_run and doc_id == "DRY-RUN-DOC-ID" else existing_pending_questions(base, doc_id)
    delta = []
    seen = set()
    for c in cards:
        key = c["question"].strip().lower()
        if key in existing or key in seen:
            continue
        seen.add(key)
        delta.append(c)

    if not delta:
        print(f"  already up to date: {len(cards)} card(s) present, nothing to push", file=sys.stderr)
        return

    print(f"  {len(cards)} authored, {len(existing)} already present, pushing {len(delta)} new", file=sys.stderr)
    created = push_delta(base, doc_id, delta, args.dry_run)
    print(f"  created {created} card(s), status=pending (review in Quality Control before study)", file=sys.stderr)


if __name__ == "__main__":
    main()
