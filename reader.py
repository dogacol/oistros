"""
reader.py — Perseus/Scaife text fetcher for Oistros.

Picks a passage from the curated catalog, fetches it via the CTS API
or from local fragment collections, and caches results locally.
"""

import json
import hashlib
import random
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import requests
import yaml

logger = logging.getLogger("oistros.reader")

BASE_DIR = Path(__file__).parent
CATALOG_PATH = BASE_DIR / "texts" / "catalog.json"
CACHE_DIR = BASE_DIR / "texts" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_catalog() -> dict:
    with open(CATALOG_PATH) as f:
        return json.load(f)


def _cache_key(urn: str, passage: str) -> str:
    raw = f"{urn}:{passage}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _read_cache(key: str) -> Optional[str]:
    path = CACHE_DIR / f"{key}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _write_cache(key: str, text: str) -> None:
    path = CACHE_DIR / f"{key}.txt"
    path.write_text(text, encoding="utf-8")


def _strip_xml_to_text(xml_str: str) -> str:
    """Extract text content from CTS XML response."""
    try:
        root = ET.fromstring(xml_str)
        # CTS responses wrap text in various elements — walk all and join text
        ns = {
            "cts": "http://chs.harvard.edu/xmlns/cts",
            "tei": "http://www.tei-c.org/ns/1.0",
        }
        # Try to find passage body
        for tag in ["passage", "body", "text", "p", "l", "div"]:
            for prefix in ["cts:", "tei:", ""]:
                elements = root.iter(f"{{{ns.get(prefix.rstrip(':'), '')}}}{tag}" if prefix else tag)
                for el in elements:
                    pass  # just iterating
        # Fallback: grab all text recursively
        texts = []
        for el in root.iter():
            if el.text:
                texts.append(el.text.strip())
            if el.tail:
                texts.append(el.tail.strip())
        return " ".join(t for t in texts if t)
    except ET.ParseError:
        # Not XML, return as-is
        return xml_str


def fetch_cts_passage(urn: str, passage: str, endpoints: dict) -> Optional[str]:
    """Fetch a passage from the CTS API."""
    cache_key = _cache_key(urn, passage)
    cached = _read_cache(cache_key)
    if cached:
        logger.debug("Cache hit for %s:%s", urn, passage)
        return cached

    endpoint = endpoints.get("scaife_cts", endpoints.get("perseus_cts"))
    url = f"{endpoint}?request=GetPassage&urn={urn}:{passage}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        text = _strip_xml_to_text(resp.text)
        if text:
            _write_cache(cache_key, text)
            logger.info("Fetched %s:%s (%d chars)", urn, passage, len(text))
        return text
    except requests.RequestException as e:
        logger.warning("CTS fetch failed for %s:%s — %s", urn, passage, e)
        return None


def fetch_local_fragment(source: dict) -> Optional[dict]:
    """Pick a random fragment from a locally-stored collection."""
    fragments = source.get("fragments", [])
    if not fragments:
        return None
    frag = random.choice(fragments)
    return {
        "author": source["author"],
        "work": source["work"],
        "reference": f"Fragment {frag['number']}",
        "text": frag["text"],
        "urn": source.get("urn"),
        "api": "local",
    }


def pick_passage(memory=None, config=None) -> Optional[dict]:
    """
    Select a passage from the catalog. Uses memory to avoid recent repeats.

    Returns a dict with keys:
        author, work, reference, text, urn, api
    """
    catalog = load_catalog()
    sources = catalog["sources"]
    endpoints = catalog["api_endpoints"]

    # Load config for selection mode
    if config is None:
        config_path = BASE_DIR / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

    selection_mode = config.get("selection_mode", "random")

    # Get recently used URNs/refs from memory to avoid repetition
    recent_refs = set()
    if memory:
        recent = memory.get_recent(n=20)
        for entry in recent:
            ref = entry.get("source_ref", "")
            if ref:
                recent_refs.add(ref)

    # Shuffle sources for randomness
    candidates = list(sources)
    random.shuffle(candidates)

    for source in candidates:
        author = source["author"]
        work = source["work"]
        api = source.get("api", "perseus")

        # Handle local fragment sources (Heraclitus, Parmenides, etc.)
        if api == "local" or (not source.get("urn") and source.get("fragments")):
            result = fetch_local_fragment(source)
            if result:
                ref_key = f"{author}:{result['reference']}"
                if ref_key not in recent_refs:
                    return result
            continue

        # Handle CTS sources
        urn = source.get("translation_urn") or source.get("urn")
        if not urn:
            continue

        passages = source.get("sample_passages", [])
        if not passages:
            continue

        random.shuffle(passages)
        for passage in passages:
            ref_key = f"{author}:{work}:{passage}"
            if ref_key in recent_refs:
                continue

            text = fetch_cts_passage(urn, passage, endpoints)
            if text and len(text) > 20:
                return {
                    "author": author,
                    "work": work,
                    "reference": passage,
                    "text": text,
                    "urn": urn,
                    "api": api,
                }

    # Fallback: just pick any local fragment
    logger.warning("No fresh passage found, falling back to any fragment")
    frag_sources = [s for s in sources if s.get("fragments")]
    if frag_sources:
        return fetch_local_fragment(random.choice(frag_sources))

    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    passage = pick_passage()
    if passage:
        print(f"\n--- {passage['author']}, {passage['work']} ({passage['reference']}) ---")
        print(passage["text"][:500])
    else:
        print("No passage found.")
