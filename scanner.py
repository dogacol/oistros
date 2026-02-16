"""
scanner.py — News/trending topic scanner for Oistros.

Pulls headlines from RSS feeds (no API keys needed).
Returns a short summary of current events for the thinker to work with.
"""

import logging
import random
import re
from typing import Optional
from dataclasses import dataclass, field

import feedparser

logger = logging.getLogger("oistros.scanner")


@dataclass
class NewsItem:
    title: str
    source: str
    summary: str = ""
    link: str = ""


# RSS feeds — no API keys, freely accessible, international spread
DEFAULT_FEEDS = [
    {"name": "Reuters World", "url": "https://feeds.reuters.com/Reuters/worldNews"},
    {"name": "AP Top Headlines", "url": "https://rsshub.app/apnews/topics/apf-topnews"},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "NPR News", "url": "https://feeds.npr.org/1001/rss.xml"},
    {"name": "The Guardian World", "url": "https://www.theguardian.com/world/rss"},
    {"name": "DW News", "url": "https://rss.dw.com/rdf/rss-en-all"},
]

# Fallback feeds if primary ones fail
FALLBACK_FEEDS = [
    {"name": "Reuters", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXigAQ"},
    {"name": "Google News World", "url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx1YlY4U0FtVnVHZ0pWVXigAQ?hl=en-US&gl=US&ceid=US:en"},
]


def _clean_html(text: str) -> str:
    """Strip HTML tags from feed summaries."""
    return re.sub(r"<[^>]+>", "", text).strip()


def fetch_feed(feed_url: str, timeout: int = 15) -> list[NewsItem]:
    """Fetch and parse a single RSS feed."""
    try:
        parsed = feedparser.parse(feed_url)
        if parsed.bozo and not parsed.entries:
            logger.debug("Feed parse warning for %s: %s", feed_url, parsed.bozo_exception)
            return []

        items = []
        for entry in parsed.entries[:10]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            summary = _clean_html(entry.get("summary", entry.get("description", "")))
            # Truncate long summaries
            if len(summary) > 300:
                summary = summary[:297] + "..."
            items.append(NewsItem(
                title=title,
                source=feed_url,
                summary=summary,
                link=entry.get("link", ""),
            ))
        return items
    except Exception as e:
        logger.debug("Failed to fetch feed %s: %s", feed_url, e)
        return []


def scan_news(config: Optional[dict] = None, max_topics: int = 5) -> list[NewsItem]:
    """
    Scan RSS feeds and return a deduplicated list of top news items.

    Args:
        config: Optional config dict; if it has a 'feeds' key, uses those instead of defaults.
        max_topics: Maximum number of topics to return.

    Returns:
        List of NewsItem, deduplicated by title similarity.
    """
    if config and "feeds" in config:
        feeds = config["feeds"]
    else:
        feeds = DEFAULT_FEEDS

    all_items: list[NewsItem] = []

    # Try primary feeds
    for feed_info in feeds:
        url = feed_info["url"] if isinstance(feed_info, dict) else feed_info
        items = fetch_feed(url)
        for item in items:
            item.source = feed_info.get("name", url) if isinstance(feed_info, dict) else url
        all_items.extend(items)

    # If we got very few, try fallbacks
    if len(all_items) < 3:
        logger.info("Few items from primary feeds, trying fallbacks")
        for feed_info in FALLBACK_FEEDS:
            items = fetch_feed(feed_info["url"])
            for item in items:
                item.source = feed_info["name"]
            all_items.extend(items)

    if not all_items:
        logger.warning("No news items fetched from any feed")
        return []

    # Deduplicate by checking for very similar titles
    seen_titles: list[str] = []
    unique_items: list[NewsItem] = []
    for item in all_items:
        title_lower = item.title.lower()
        # Skip if we've seen a very similar title
        is_dup = False
        for seen in seen_titles:
            # Simple overlap check
            words_a = set(title_lower.split())
            words_b = set(seen.split())
            if len(words_a & words_b) / max(len(words_a | words_b), 1) > 0.6:
                is_dup = True
                break
        if not is_dup:
            unique_items.append(item)
            seen_titles.append(title_lower)

    # Shuffle to avoid source bias, then take top N
    random.shuffle(unique_items)
    selected = unique_items[:max_topics]

    logger.info("Scanned %d items, selected %d topics", len(all_items), len(selected))
    return selected


def format_topics(items: list[NewsItem]) -> str:
    """Format news items into a concise string for the thinker prompt."""
    if not items:
        return "No current news available."
    lines = []
    for item in items:
        line = f"- {item.title}"
        if item.summary:
            line += f" ({item.summary[:120]})"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    items = scan_news()
    if items:
        print(f"\n--- {len(items)} trending topics ---")
        print(format_topics(items))
    else:
        print("No news items found.")
