#!/usr/bin/env python3
"""
Strip Obsidian-only markdown syntax that the flashcards app's own parser
(app/services/file_parser.py) does NOT catch.

That parser's image-strip regex only matches standard `![alt](url)` markdown
and its link-strip regex only matches standard `[text](url)` markdown.
Obsidian's `![[Pasted image ...]]` embeds and `[[wiki links]]` use double
brackets with no parens, so they pass straight through as literal junk text
if left in — this script removes/normalizes them before assembly.

Usage:
    python3 clean_notes.py INPUT.md [-o OUTPUT.md]

With no -o, prints the cleaned text to stdout (stats go to stderr, so this
is safe to pipe). This does NOT touch real images that already have
transcriptions in place — if a note has image embeds worth keeping, OCR
them first (see SKILL.md phase 3) so their content survives as prose before
running this script, since this script deletes any embed marker it finds.
"""
import argparse
import re
import sys


def clean(text: str) -> tuple[str, int]:
    before = len(re.findall(r"!\[\[[^\]]*\]\]", text))

    # Obsidian image embeds: delete entirely (no OCR text to preserve here —
    # run the OCR/enrichment pass first if these carry real content).
    text = re.sub(r"!\[\[[^\]]*\]\]\n?", "", text)

    # Obsidian wiki-links: [[Page|alias]] -> alias, [[Page]] -> Page
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)

    # Collapse blank-line runs left behind by removed embeds
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

    return text, before


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Source markdown file")
    parser.add_argument("-o", "--output", help="Write cleaned text here (default: stdout)")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = f.read()

    cleaned, stripped_count = clean(raw)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(cleaned)
        print(f"{args.input}: stripped {stripped_count} image embed(s), "
              f"{len(cleaned.split())} words remain -> {args.output}", file=sys.stderr)
    else:
        print(f"{args.input}: stripped {stripped_count} image embed(s), "
              f"{len(cleaned.split())} words remain", file=sys.stderr)
        print(cleaned)


if __name__ == "__main__":
    main()
