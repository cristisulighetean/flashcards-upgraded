#!/usr/bin/env python3
"""
Load a word list into a vocabulary deck.

Accepts either JSON or a plain text list, and posts it to the running API.

    # plain text: one "term = translation" per line
    python scripts/seed_vocab.py --lang ro words_ro.txt
    python scripts/seed_vocab.py --lang en words_en.txt

    # JSON: [{"term": "...", "translation": "...", "example": "..."}, ...]
    python scripts/seed_vocab.py --lang en words.json

Separators recognised in text mode: '=', '|', ' - ', tab.
Blank lines and lines starting with '#' are ignored.
Duplicates already in the deck are skipped by the API, so re-running is safe.
"""
import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API = "http://localhost:8000/api/v1/vocab/import"
SEPARATORS = ["\t", " = ", "=", " | ", "|", " - ", " – "]


def parse_text(raw: str) -> list[dict]:
    entries: list[dict] = []
    for lineno, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        for sep in SEPARATORS:
            if sep in line:
                term, _, translation = line.partition(sep)
                term, translation = term.strip(), translation.strip()
                if term and translation:
                    entries.append({"term": term, "translation": translation})
                else:
                    print(f"  line {lineno}: incomplete, skipped -> {line!r}", file=sys.stderr)
                break
        else:
            print(f"  line {lineno}: no separator, skipped -> {line!r}", file=sys.stderr)
    return entries


def load(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        if isinstance(data, dict):  # allow {"entries": [...]}
            data = data.get("entries", [])
        return [e for e in data if e.get("term") and e.get("translation")]
    return parse_text(raw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path, help="Word list (.txt or .json)")
    ap.add_argument("--lang", required=True, choices=["ro", "en"], help="Deck: the language being learned")
    ap.add_argument("--gloss-lang", default=None, choices=["ro", "en"], help="Language of the translations (default: the other one)")
    ap.add_argument("--api", default=DEFAULT_API, help=f"Import endpoint (default {DEFAULT_API})")
    ap.add_argument("--pending", action="store_true", help="Send to Quality Control instead of straight into the library")
    ap.add_argument("--dry-run", action="store_true", help="Parse and report without importing")
    args = ap.parse_args()

    if not args.file.exists():
        print(f"No such file: {args.file}", file=sys.stderr)
        return 1

    entries = load(args.file)
    if not entries:
        print("Nothing to import.", file=sys.stderr)
        return 1

    gloss = args.gloss_lang or ("en" if args.lang == "ro" else "ro")
    print(f"Parsed {len(entries)} entries from {args.file.name} -> deck '{args.lang}' (glossed in '{gloss}')")
    for e in entries[:3]:
        print(f"   {e['term']} = {e['translation']}")
    if len(entries) > 3:
        print(f"   ... and {len(entries) - 3} more")

    if args.dry_run:
        print("Dry run: nothing sent.")
        return 0

    payload = {
        "lang": args.lang,
        "gloss_lang": gloss,
        "entries": entries,
        "accepted": not args.pending,
    }
    req = urllib.request.Request(
        args.api,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = ssl._create_unverified_context() if args.api.startswith("https") else None

    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"Import failed ({exc.code}): {exc.read().decode()[:400]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not reach {args.api}: {exc.reason}", file=sys.stderr)
        print("Is the stack running?  docker compose up -d", file=sys.stderr)
        return 1

    print(f"\nImported {body['imported']} entries -> {body['cards_created']} cards")
    if body["skipped_duplicates"]:
        n = len(body["skipped_duplicates"])
        shown = ", ".join(body["skipped_duplicates"][:8])
        print(f"Skipped {n} already in the deck: {shown}{' ...' if n > 8 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
