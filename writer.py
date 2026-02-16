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

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def format_output(
    response: str,
    passage: dict,
    news_summary: str,
    thinking: str = "",
    model: str = "",
    timestamp: Optional[datetime] = None,
) -> str:
    """
    Format the thinker's output as a markdown document with metadata.

    Returns the full markdown string.
    """
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

    # Include a truncated version of the passage
    passage_preview = text[:300]
    if len(text) > 300:
        passage_preview += "..."
    lines.extend([
        f"**Passage:** \"{passage_preview}\"",
        "",
        f"**Trending:** {news_summary.strip()[:300]}",
        "",
        f"**Model:** {model}" if model else "",
        f"**Generated:** {timestamp.isoformat()}",
    ])

    # Filter empty lines at end
    return "\n".join(line for line in lines if line is not None).rstrip() + "\n"


def write_output(
    response: str,
    passage: dict,
    news_summary: str,
    thinking: str = "",
    model: str = "",
    timestamp: Optional[datetime] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Write the formatted output to a dated markdown file.

    Returns the path to the written file.
    """
    if timestamp is None:
        timestamp = datetime.now()
    if output_dir is None:
        output_dir = OUTPUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    filename = timestamp.strftime("%Y-%m-%d_%H%M") + ".md"
    filepath = output_dir / filename

    # Avoid overwriting: append a counter if needed
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

    # Also write thinking trace if present (separate file, for review)
    if thinking:
        think_path = filepath.with_suffix(".thinking.md")
        think_content = f"# Thinking Trace — {timestamp.strftime('%Y-%m-%d %H:%M')}\n\n{thinking}\n"
        think_path.write_text(think_content, encoding="utf-8")
        logger.info("Wrote thinking trace to %s", think_path)

    return filepath


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Test output
    test_passage = {
        "author": "Heraclitus",
        "work": "Fragments",
        "reference": "Fragment B53",
        "text": "War is the father of all and king of all.",
        "urn": "urn:cts:greekLit:tlg0004.tlg001",
    }
    test_response = "The defence minister speaks of *readiness* as though it were a posture one could adopt at will..."
    test_news = "NATO summit tensions over defense spending"

    path = write_output(
        response=test_response,
        passage=test_passage,
        news_summary=test_news,
        model="qwen3:0.6b",
    )
    print(f"Test output written to: {path}")
    print(path.read_text())
