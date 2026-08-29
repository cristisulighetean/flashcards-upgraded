#!/usr/bin/env python3
"""
Concatenate cleaned/enriched source notes into target documents ready for
upload to the flashcards app.

The app's chunker (app/services/text_chunker.py) is character-count-based
and heading-blind — file_parser.py strips markdown heading syntax before
chunking ever sees it — so when merging multiple source notes into one
document, a plain-text separator (not a markdown heading) is inserted
between them. That's the best available signal for "topic boundary here"
once heading markup is gone.

Usage:
    python3 assemble_docs.py mapping.json --out-dir OUTDIR

mapping.json shape:
{
  "Target Document Name.md": [
    {"title": "Source Note Title", "file": "/path/to/cleaned-or-enriched/note1.md"},
    {"title": "Other Note Title",  "file": "/path/to/cleaned-or-enriched/note2.md"}
  ],
  "Another Target.md": [
    {"title": "...", "file": "..."}
  ]
}

Each target document is built by wrapping each source's text in a "# title"
header and joining sources with a plain-text "=====" separator line.
"""
import argparse
import json
import sys
from pathlib import Path

SEPARATOR = "\n\n=====\n\n"


def assemble(sources: list[dict]) -> str:
    chunks = []
    for entry in sources:
        title = entry["title"]
        path = Path(entry["file"])
        text = path.read_text(encoding="utf-8").strip()
        chunks.append(f"# {title}\n\n{text}")
    return SEPARATOR.join(chunks) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mapping", help="Path to mapping.json (see this script's docstring)")
    parser.add_argument("--out-dir", required=True, help="Directory to write assembled documents into")
    args = parser.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for target_name, sources in mapping.items():
        full_text = assemble(sources)
        out_path = out_dir / target_name
        out_path.write_text(full_text, encoding="utf-8")
        print(f"{target_name}: {len(sources)} source note(s), {len(full_text.split())} words, "
              f"{len(full_text)} chars -> {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
