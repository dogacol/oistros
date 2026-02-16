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


def _default_memory_path() -> Path:
    p = Path.cwd() / ".oistros" / "memory.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class Memory:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or _default_memory_path()
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
        recent = self.get_recent(n)
        if not recent:
            return ""
        lines = []
        for entry in recent:
            author = entry.get("source_author", "?")
            preview = entry.get("response_preview", "")[:100]
            lines.append(f"- {author}: {preview}")
        return "\n".join(lines)

    def count(self) -> int:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except FileNotFoundError:
            return 0
