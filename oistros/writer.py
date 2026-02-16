"""
writer.py — Output formatter for Oistros.

Takes the thinker's output and writes it as a dated markdown file
with metadata (source passage, URN, trending topic, timestamp).
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("oistros.writer")


def _get_output_dir() -> Path:
    d = Path.cwd() / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def format_output(
    response: str,
    passage: dict,
    news_summary: str,
    thinking: str = "",
    model: str = "",
    timestamp: Optional[datetime] = None,
) -> str:
    if timestamp is None:
        timestamp = datetime.now()

    author = passage.get("author", "Unknown")
    work = passage.get("work", "")
    reference = passage.get("reference", "")
    urn = passage.get("urn", "")
    text = passage.get("text", "")

    source_line = f"{author}, *{work}*"
    if reference:
        source_line += f" ({reference})"

    date_str = timestamp.strftime("%Y-%m-%d %H:%M")

    passage_preview = text[:300]
    if len(text) > 300:
        passage_preview += "..."

    lines = [
        f"# Oistros — {date_str}",
        "",
        response.strip(),
        "",
        "---",
        "",
        f"**Source:** {source_line}",
    ]

    if urn:
        lines.append(f"**URN:** `{urn}`")

    lines.extend([
        f"**Passage:** \"{passage_preview}\"",
        "",
        f"**Trending:** {news_summary.strip()[:300]}",
    ])

    if model:
        lines.append(f"**Model:** {model}")

    lines.append(f"**Generated:** {timestamp.isoformat()}")

    return "\n".join(lines).rstrip() + "\n"


def write_output(
    response: str,
    passage: dict,
    news_summary: str,
    thinking: str = "",
    model: str = "",
    timestamp: Optional[datetime] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """Write formatted output to a dated markdown file. Returns the path."""
    if timestamp is None:
        timestamp = datetime.now()
    if output_dir is None:
        output_dir = _get_output_dir()

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = timestamp.strftime("%Y-%m-%d_%H%M") + ".md"
    filepath = output_dir / filename

    counter = 1
    while filepath.exists():
        filename = timestamp.strftime("%Y-%m-%d_%H%M") + f"_{counter}.md"
        filepath = output_dir / filename
        counter += 1

    content = format_output(
        response=response,
        passage=passage,
        news_summary=news_summary,
        thinking=thinking,
        model=model,
        timestamp=timestamp,
    )

    filepath.write_text(content, encoding="utf-8")
    logger.info("Wrote output to %s", filepath)

    if thinking:
        think_path = filepath.with_suffix(".thinking.md")
        think_content = f"# Thinking Trace — {timestamp.strftime('%Y-%m-%d %H:%M')}\n\n{thinking}\n"
        think_path.write_text(think_content, encoding="utf-8")
        logger.info("Wrote thinking trace to %s", think_path)

    return filepath
