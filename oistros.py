#!/usr/bin/env python3
"""
oistros.py — Main loop and scheduler for Oistros, the philosophical gadfly.

Runs a cycle every N minutes:
  1. Reader picks an ancient passage
  2. Scanner checks current news
  3. Thinker generates philosophical commentary
  4. Writer saves the output
  5. Memory records the cycle

Can run as a daemon (schedule library) or be invoked once by cron.
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
import schedule

from reader import pick_passage
from scanner import scan_news, format_topics
from thinker import think
from writer import write_output
from memory import Memory

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"

logger = logging.getLogger("oistros")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


def run_cycle(config: dict, memory: Memory) -> bool:
    """
    Execute one full Oistros cycle. Returns True on success.
    """
    cycle_start = datetime.now()
    logger.info("=== Oistros cycle starting at %s ===", cycle_start.isoformat())

    # 1. Pick a passage
    logger.info("Step 1: Picking a passage...")
    passage = pick_passage(memory=memory, config=config)
    if not passage:
        logger.error("Failed to pick a passage. Skipping cycle.")
        return False
    logger.info(
        "Selected: %s, %s (%s)",
        passage["author"], passage["work"], passage.get("reference", "?"),
    )

    # 2. Scan news
    logger.info("Step 2: Scanning news...")
    news_items = scan_news(config=config.get("scanner", {}))
    news_summary = format_topics(news_items)
    logger.info("News topics:\n%s", news_summary)

    # 3. Think
    logger.info("Step 3: Thinking...")
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

    logger.info("Response length: %d chars", len(response))
    if thinking_trace:
        logger.info("Thinking trace: %d chars", len(thinking_trace))

    # 4. Write output
    logger.info("Step 4: Writing output...")
    output_path = write_output(
        response=response,
        passage=passage,
        news_summary=news_summary,
        thinking=thinking_trace,
        model=model,
        timestamp=cycle_start,
    )
    logger.info("Output written to %s", output_path)

    # 5. Record to memory
    logger.info("Step 5: Recording to memory...")
    memory.record(
        passage=passage,
        news_summary=news_summary,
        response=response,
        thinking=thinking_trace,
        model=model,
        output_path=str(output_path),
    )

    elapsed = (datetime.now() - cycle_start).total_seconds()
    logger.info("=== Cycle complete in %.1f seconds ===", elapsed)
    total = memory.count()
    logger.info("Total outputs: %d", total)

    return True


def run_daemon(config: dict) -> None:
    """Run Oistros as a daemon with scheduled cycles."""
    memory = Memory()
    interval = config.get("interval_minutes", 30)

    logger.info("Oistros daemon starting. Interval: %d minutes.", interval)
    logger.info("Model: %s", config.get("thinker", {}).get("model", "qwen3:0.6b"))
    logger.info("Press Ctrl+C to stop.")

    # Run once immediately
    run_cycle(config, memory)

    # Schedule subsequent runs
    schedule.every(interval).minutes.do(run_cycle, config=config, memory=memory)

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Oistros daemon stopped.")


def run_once(config: dict) -> None:
    """Run a single Oistros cycle (for cron usage)."""
    memory = Memory()
    success = run_cycle(config, memory)
    sys.exit(0 if success else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Oistros — the philosophical gadfly",
        epilog="Runs a cycle that reads ancient texts, scans current news, "
               "and generates philosophical commentary via a local LLM.",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="daemon",
        choices=["daemon", "once", "test"],
        help="Run mode: 'daemon' (scheduled loop), 'once' (single cycle), "
             "'test' (dry run with sample data). Default: daemon",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=str(CONFIG_PATH),
        help=f"Path to config file. Default: {CONFIG_PATH}",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"oistros_{datetime.now().strftime('%Y-%m-%d')}.log"

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        logger.info("Loaded config from %s", config_path)
    else:
        config = {}
        logger.info("No config file found, using defaults")

    if args.mode == "daemon":
        run_daemon(config)
    elif args.mode == "once":
        run_once(config)
    elif args.mode == "test":
        # Test mode: just pick a passage and scan news, no LLM call
        logger.info("=== TEST MODE ===")
        memory = Memory()

        passage = pick_passage(memory=memory, config=config)
        if passage:
            logger.info("Passage: %s, %s (%s)", passage["author"], passage["work"], passage.get("reference", ""))
            logger.info("Text: %s", passage["text"][:200])
        else:
            logger.error("No passage found.")

        news_items = scan_news(config=config.get("scanner", {}))
        news_summary = format_topics(news_items)
        logger.info("News:\n%s", news_summary)

        logger.info("=== Test complete. Use 'once' or 'daemon' mode to run with LLM. ===")


if __name__ == "__main__":
    main()
