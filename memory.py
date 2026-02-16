"""
memory.py — Simple JSONL log of past outputs and themes for Oistros.

Tracks which passages have been used, which themes recur, and what
topics have been covered. Enables the reader to avoid repetition and
allows thematic threads to develop over time.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("oistros.memory")

BASE_DIR = Path(__file__).parent
DEFAULT_MEMORY_PATH = BASE_DIR / "logs" / "memory.jsonl"


class Memory:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or DEFAULT_MEMORY_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def record(
        self,
        passage: dict,
        news_summary: str,
        response: str,
        thinking: str = "",
        model: str = "",
        output_path: str = "",
    ) -> None:
        """Append a record of this cycle to the memory log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source_author": passage.get("author", ""),
            "source_work": passage.get("work", ""),
            "source_ref": f"{passage.get('author', '')}:{passage.get('work', '')}:{passage.get('reference', '')}",
            "urn": passage.get("urn", ""),
            "passage_preview": passage.get("text", "")[:200],
            "news_summary": news_summary[:300],
            "response_preview": response[:300],
            "response_length": len(response),
            "had_thinking": bool(thinking),
            "model": model,
            "output_path": output_path,
        }

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("Recorded memory entry for %s", entry["source_ref"])

    def get_recent(self, n: int = 20) -> list[dict]:
        """Get the most recent N memory entries."""
        entries = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            return []

        return entries[-n:]

    def get_recent_themes(self, n: int = 10) -> str:
        """
        Build a brief summary of recent themes for the thinker's context.
        Returns a string listing recent authors/works and response previews.
        """
        recent = self.get_recent(n)
        if not recent:
            return ""

        lines = []
        for entry in recent:
            author = entry.get("source_author", "?")
            preview = entry.get("response_preview", "")[:100]
            lines.append(f"- {author}: {preview}")

        return "\n".join(lines)

    def get_used_refs(self, n: int = 50) -> set:
        """Get the set of source references used in recent entries."""
        recent = self.get_recent(n)
        return {entry.get("source_ref", "") for entry in recent if entry.get("source_ref")}

    def count(self) -> int:
        """Count total memory entries."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except FileNotFoundError:
            return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    mem = Memory()
    print(f"Memory entries: {mem.count()}")
    recent = mem.get_recent(5)
    if recent:
        print("Recent entries:")
        for entry in recent:
            print(f"  {entry['timestamp']} — {entry['source_ref']}")
    else:
        print("No entries yet.")
