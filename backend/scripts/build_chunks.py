"""Build chunks.json from knowledge .md files for local fallback search.

Usage:
    python -m scripts.build_chunks

Reads all .md files from backend/data/knowledge/, splits by ## headers,
and writes backend/data/knowledge/chunks.json.
"""

import json
import re
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"
OUTPUT_FILE = KNOWLEDGE_DIR / "chunks.json"


def split_into_chunks(filepath: Path) -> list[dict]:
    """Split a markdown file into chunks by ## headers."""
    text = filepath.read_text(encoding="utf-8")
    filename = filepath.stem

    category_map = {
        "career-decisions": "career",
        "startup-business": "startup",
        "relationship-psychology": "relationship",
        "health-lifestyle": "health",
        "education-decisions": "education",
        "decision-science": "general",
    }
    category = category_map.get(filename, "general")

    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        title_match = re.match(r"^##\s+(.+)", section)
        title = title_match.group(1).strip() if title_match else filename

        keywords = set()
        for word in re.findall(r"[a-z]{3,}", section.lower()):
            keywords.add(word)

        chunks.append({
            "source": filename,
            "category": category,
            "title": title,
            "content": section,
            "keywords": sorted(keywords),
        })

    return chunks


def main():
    all_chunks = []
    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))

    if not md_files:
        print(f"No .md files found in {KNOWLEDGE_DIR}")
        return

    for filepath in md_files:
        chunks = split_into_chunks(filepath)
        all_chunks.extend(chunks)
        print(f"  {filepath.name}: {len(chunks)} chunks")

    OUTPUT_FILE.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")
    print(f"\nWrote {len(all_chunks)} chunks to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
