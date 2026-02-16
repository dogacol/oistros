"""
cli.py — Command-line interface for Oistros.

Usage:
    oistros              Run the daemon (cycle every N minutes)
    oistros run          Run a single cycle
    oistros test         Test passage fetching + news scanning (no LLM)
    oistros read         Fetch and display a random passage
    oistros scan         Scan and display current news headlines
    oistros log          Show recent memory entries
    oistros --help       Show help
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
import schedule

from oistros import __version__
from oistros.reader import pick_passage
from oistros.scanner import scan_news, format_topics
from oistros.thinker import think
from oistros.writer import write_output
from oistros.memory import Memory

logger = logging.getLogger("oistros")

DEFAULT_CONFIG_PATH = Path.cwd() / "config.yaml"


def load_config(path: Optional[Path] = None) -> dict:
    p = path or DEFAULT_CONFIG_PATH
    if p.exists():
        with open(p) as f:
            return yaml.safe_load(f) or {}
    return {}


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"oistros_{datetime.now().strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


# ── Core cycle ───────────────────────────────────────────────────────


def run_cycle(config: dict, memory: Memory) -> bool:
    """Execute one full Oistros cycle. Returns True on success."""
    cycle_start = datetime.now()
    logger.info("=== Oistros cycle starting at %s ===", cycle_start.isoformat())

    # 1. Pick a passage
    logger.info("Picking a passage...")
    passage = pick_passage(memory=memory, config=config)
    if not passage:
        logger.error("Failed to pick a passage. Skipping cycle.")
        return False
    logger.info(
        "  %s, %s (%s)",
        passage["author"], passage["work"], passage.get("reference", "?"),
    )

    # 2. Scan news
    logger.info("Scanning news...")
    news_items = scan_news(config=config.get("scanner", {}))
    news_summary = format_topics(news_items)

    # 3. Think
    logger.info("Thinking...")
    memory_context = memory.get_recent_themes(n=config.get("memory_context_size", 5))
    result = think(
        passage=passage,
        news_summary=news_summary,
        memory_context=memory_context,
        config=config.get("thinker", {}),
    )
    if not result or not result.get("response"):
        logger.error("Thinker returned no response. Skipping cycle.")
        return False

    response = result["response"]
    thinking_trace = result.get("thinking", "")
    model = result.get("model", "")

    # 4. Write output
    logger.info("Writing output...")
    output_path = write_output(
        response=response,
        passage=passage,
        news_summary=news_summary,
        thinking=thinking_trace,
        model=model,
        timestamp=cycle_start,
    )

    # 5. Record to memory
    memory.record(
        passage=passage,
        news_summary=news_summary,
        response=response,
        thinking=thinking_trace,
        model=model,
        output_path=str(output_path),
    )

    elapsed = (datetime.now() - cycle_start).total_seconds()
    logger.info("=== Cycle complete in %.1f seconds === [%s]", elapsed, output_path)
    return True


# ── Commands ─────────────────────────────────────────────────────────


def cmd_daemon(config: dict) -> None:
    """Run Oistros as a daemon with scheduled cycles."""
    memory = Memory()
    interval = config.get("interval_minutes", 30)

    print(f"Oistros v{__version__} — daemon mode")
    print(f"  Model: {config.get('thinker', {}).get('model', 'qwen3:0.6b')}")
    print(f"  Interval: {interval} minutes")
    print(f"  Output: {Path.cwd() / 'output'}")
    print()

    # Run once immediately
    run_cycle(config, memory)

    schedule.every(interval).minutes.do(run_cycle, config=config, memory=memory)

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nOistros stopped.")


def cmd_run(config: dict) -> None:
    """Run a single cycle."""
    memory = Memory()
    success = run_cycle(config, memory)
    sys.exit(0 if success else 1)


def cmd_test(config: dict) -> None:
    """Test passage fetching and news scanning (no LLM call)."""
    memory = Memory()

    print(f"Oistros v{__version__} — test mode\n")

    print("Fetching a passage...")
    passage = pick_passage(memory=memory, config=config)
    if passage:
        print(f"  {passage['author']}, {passage['work']} ({passage.get('reference', '?')})")
        text_preview = passage["text"][:300]
        if len(passage["text"]) > 300:
            text_preview += "..."
        print(f"  \"{text_preview}\"")
        if passage.get("urn"):
            print(f"  URN: {passage['urn']}")
    else:
        print("  No passage found.")

    print()
    print("Scanning news...")
    news_items = scan_news(config=config.get("scanner", {}))
    news_summary = format_topics(news_items)
    print(f"  {len(news_items)} topics:")
    for item in news_items:
        print(f"    - {item.title}")

    print()
    print("Test complete. Use 'oistros run' to run a full cycle with LLM.")


def cmd_read(config: dict) -> None:
    """Fetch and display a random passage."""
    memory = Memory()
    passage = pick_passage(memory=memory, config=config)
    if passage:
        print(f"{passage['author']}, {passage['work']} ({passage.get('reference', '?')})")
        print()
        print(passage["text"])
        if passage.get("urn"):
            print(f"\nURN: {passage['urn']}")
    else:
        print("No passage found.")


def cmd_scan(config: dict) -> None:
    """Scan and display current news."""
    news_items = scan_news(config=config.get("scanner", {}))
    if news_items:
        print(format_topics(news_items))
    else:
        print("No news items found.")


def cmd_log(config: dict) -> None:
    """Show recent memory entries."""
    memory = Memory()
    recent = memory.get_recent(20)
    total = memory.count()

    if not recent:
        print("No entries yet. Run 'oistros run' to generate your first output.")
        return

    print(f"Recent outputs ({len(recent)} of {total} total):\n")
    for entry in recent:
        ts = entry.get("timestamp", "?")[:16]
        author = entry.get("source_author", "?")
        work = entry.get("source_work", "?")
        preview = entry.get("response_preview", "")[:80]
        print(f"  {ts}  {author}, {work}")
        print(f"    {preview}...")
        print()


# ── Main ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="oistros",
        description="Oistros (Οἶστρος) — the philosophical gadfly",
    )
    parser.add_argument(
        "--version", action="version", version=f"oistros {__version__}",
    )
    parser.add_argument(
        "--config", "-c", type=str, default=None,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run a single cycle")
    subparsers.add_parser("test", help="Test passage + news fetching (no LLM)")
    subparsers.add_parser("read", help="Fetch and display a random passage")
    subparsers.add_parser("scan", help="Scan and display current news")
    subparsers.add_parser("log", help="Show recent memory entries")

    args = parser.parse_args()

    setup_logging(args.verbose)

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)

    commands = {
        "run": cmd_run,
        "test": cmd_test,
        "read": cmd_read,
        "scan": cmd_scan,
        "log": cmd_log,
        None: cmd_daemon,  # default: run daemon
    }

    handler = commands.get(args.command, cmd_daemon)
    handler(config)
