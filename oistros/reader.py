"""
reader.py — Perseus/Scaife text fetcher for Oistros.

Uses the new Scaife Viewer JSON API as primary, with GetValidReff-based
discovery to find valid passage references dynamically. Falls back to
the old CTS API and local fragment collections.
"""

import json
import hashlib
import random
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("oistros.reader")

DATA_DIR = Path(__file__).parent / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"


def _get_dirs(data_dir: Optional[Path] = None):
    """Return (cache_dir, reffs_dir), creating them if needed."""
    base = data_dir or Path.cwd()
    cache_dir = base / ".oistros" / "cache"
    reffs_dir = base / ".oistros" / "reffs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    reffs_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir, reffs_dir


def load_catalog() -> dict:
    with open(CATALOG_PATH) as f:
        return json.load(f)


# ── Reference discovery ─────────────────────────────────────────────


def _reffs_cache_path(urn: str, level: int, reffs_dir: Path) -> Path:
    key = hashlib.sha256(f"{urn}:L{level}".encode()).hexdigest()[:16]
    return reffs_dir / f"{key}.json"


def discover_valid_refs(
    urn: str,
    level: int,
    endpoints: dict,
    reffs_dir: Path,
) -> list[str]:
    """
    Get valid passage references for a URN at the given citation level.
    Uses the new Scaife viewer API, falls back to old CTS.
    Results are cached locally.
    """
    cache_path = _reffs_cache_path(urn, level, reffs_dir)
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    refs = _discover_scaife(urn, level, endpoints)
    if not refs:
        refs = _discover_old_cts(urn, level, endpoints)

    if refs:
        cache_path.write_text(json.dumps(refs))
        logger.info("Discovered %d refs for %s (level %d)", len(refs), urn, level)

    return refs


def _discover_scaife(urn: str, level: int, endpoints: dict) -> list[str]:
    """Discover refs via new Scaife viewer API."""
    url_template = endpoints.get(
        "scaife_reffs",
        "https://scaife.perseus.org/library/{urn}/cts-api-xml/reffs/?level={level}",
    )
    url = url_template.format(urn=urn, level=level)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return _parse_reffs_xml(resp.text)
    except requests.RequestException as e:
        logger.debug("Scaife reffs failed for %s: %s", urn, e)
        return []


def _discover_old_cts(urn: str, level: int, endpoints: dict) -> list[str]:
    """Discover refs via old CTS API."""
    url_template = endpoints.get(
        "old_cts_reffs",
        "https://scaife-cts.perseus.org/api/cts?request=GetValidReff&urn={urn}&level={level}",
    )
    url = url_template.format(urn=urn, level=level)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return _parse_reffs_xml(resp.text)
    except requests.RequestException as e:
        logger.debug("Old CTS reffs failed for %s: %s", urn, e)
        return []


def _parse_reffs_xml(xml_text: str) -> list[str]:
    """Parse GetValidReff XML response to extract reference strings."""
    refs = []
    try:
        root = ET.fromstring(xml_text)
        # Look for <reff> elements containing URNs
        for el in root.iter():
            tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if tag in ("reff", "urn", "ref"):
                for child in el:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_tag == "urn" and child.text:
                        # Extract the passage part after the last ':'
                        parts = child.text.strip().split(":")
                        if len(parts) >= 5:
                            refs.append(parts[-1])
            elif el.text and el.text.strip().startswith("urn:cts:"):
                parts = el.text.strip().split(":")
                if len(parts) >= 5:
                    ref = parts[-1]
                    if ref and not ref.startswith("cts"):
                        refs.append(ref)
    except ET.ParseError as e:
        logger.debug("XML parse error in reffs: %s", e)
    return refs


# ── Passage fetching ────────────────────────────────────────────────


def _passage_cache_key(urn: str, ref: str) -> str:
    return hashlib.sha256(f"{urn}:{ref}".encode()).hexdigest()[:16]


def fetch_passage(
    urn: str,
    ref: str,
    endpoints: dict,
    cache_dir: Path,
) -> Optional[str]:
    """Fetch a single passage. Tries Scaife JSON API first, then old CTS."""
    key = _passage_cache_key(urn, ref)
    cache_path = cache_dir / f"{key}.txt"
    if cache_path.exists():
        text = cache_path.read_text(encoding="utf-8")
        if text:
            return text

    text = _fetch_scaife_json(urn, ref, endpoints)
    if not text:
        text = _fetch_old_cts(urn, ref, endpoints)

    if text:
        cache_path.write_text(text, encoding="utf-8")

    return text


def _fetch_scaife_json(urn: str, ref: str, endpoints: dict) -> Optional[str]:
    """Fetch passage via Scaife viewer JSON API."""
    url_template = endpoints.get(
        "scaife_passage",
        "https://scaife.perseus.org/library/passage/{urn}:{ref}/json/",
    )
    url = url_template.format(urn=urn, ref=ref)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # The JSON response has various shapes — try to extract text
        if isinstance(data, dict):
            # Try 'text_html', 'text', or 'passage' keys
            for key in ("text_html", "text", "passage", "content"):
                if key in data and data[key]:
                    return _strip_html(str(data[key]))
            # Try nested 'versions' or 'textParts'
            for key in ("versions", "textParts", "parts"):
                if key in data and isinstance(data[key], list):
                    texts = []
                    for part in data[key]:
                        if isinstance(part, dict):
                            for tkey in ("text_html", "text", "content", "w"):
                                if tkey in part:
                                    texts.append(str(part[tkey]))
                                    break
                        elif isinstance(part, str):
                            texts.append(part)
                    if texts:
                        return _strip_html(" ".join(texts))
        return None
    except requests.RequestException as e:
        logger.debug("Scaife JSON fetch failed for %s:%s — %s", urn, ref, e)
        return None
    except (ValueError, KeyError):
        return None


def _fetch_old_cts(urn: str, ref: str, endpoints: dict) -> Optional[str]:
    """Fetch passage via old CTS XML API."""
    url_template = endpoints.get(
        "old_cts_passage",
        "https://scaife-cts.perseus.org/api/cts?request=GetPassage&urn={urn}:{ref}",
    )
    url = url_template.format(urn=urn, ref=ref)

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return _strip_xml_to_text(resp.text)
    except requests.RequestException as e:
        logger.debug("Old CTS fetch failed for %s:%s — %s", urn, ref, e)
        return None


def _strip_html(text: str) -> str:
    """Strip HTML tags."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def _strip_xml_to_text(xml_str: str) -> str:
    """Extract text content from CTS XML response."""
    try:
        root = ET.fromstring(xml_str)
        texts = []
        for el in root.iter():
            if el.text:
                texts.append(el.text.strip())
            if el.tail:
                texts.append(el.tail.strip())
        result = " ".join(t for t in texts if t)
        return result if len(result) > 10 else None
    except ET.ParseError:
        return xml_str if len(xml_str) > 10 else None


# ── Local fragments ─────────────────────────────────────────────────


def _pick_local_fragment(source: dict) -> Optional[dict]:
    """Pick a random fragment from a locally-stored collection."""
    fragments = source.get("fragments", [])
    if not fragments:
        return None
    frag = random.choice(fragments)
    return {
        "author": source["author"],
        "work": source["work"],
        "reference": f"Fragment {frag['id']}",
        "text": frag["text"],
        "urn": None,
        "api": "local",
    }


# ── Main passage picker ─────────────────────────────────────────────


def pick_passage(memory=None, config: Optional[dict] = None) -> Optional[dict]:
    """
    Select a passage from the catalog.

    For Scaife sources: discovers valid refs, picks one, fetches text.
    For local sources: picks a random fragment.
    Uses memory to avoid recent repeats.

    Returns dict with: author, work, reference, text, urn, api
    """
    catalog = load_catalog()
    sources = catalog["sources"]
    endpoints = catalog["api_endpoints"]

    cache_dir, reffs_dir = _get_dirs()

    # Get recently used refs from memory
    recent_refs = set()
    if memory:
        recent = memory.get_recent(n=30)
        for entry in recent:
            ref = entry.get("source_ref", "")
            if ref:
                recent_refs.add(ref)

    # Shuffle for randomness
    candidates = list(sources)
    random.shuffle(candidates)

    for source in candidates:
        author = source["author"]
        work = source["work"]
        api = source.get("api", "scaife")

        # Local fragment sources
        if api == "local":
            result = _pick_local_fragment(source)
            if result:
                ref_key = f"{author}:{result['reference']}"
                if ref_key not in recent_refs:
                    return result
            continue

        # Scaife sources — use discovery
        urn = source.get("translation_urn") or source.get("urn")
        if not urn:
            continue

        # Determine citation level to discover at
        scheme = source.get("citation_scheme", [])
        level = len(scheme)
        if level == 0:
            level = 1

        # For multi-level texts, discover at a middle level for readable chunks
        # (e.g. book.chapter rather than book.chapter.section)
        discover_level = min(level, 2)

        refs = discover_valid_refs(urn, discover_level, endpoints, reffs_dir)
        if not refs:
            # Try the Greek URN if translation failed
            greek_urn = source.get("urn")
            if greek_urn and greek_urn != urn:
                refs = discover_valid_refs(greek_urn, discover_level, endpoints, reffs_dir)
                if refs:
                    urn = greek_urn

        if not refs:
            logger.debug("No refs discovered for %s (%s)", work, urn)
            continue

        # Pick random refs, avoiding recently used
        random.shuffle(refs)
        for ref in refs[:15]:  # Try up to 15 refs
            ref_key = f"{author}:{work}:{ref}"
            if ref_key in recent_refs:
                continue

            text = fetch_passage(urn, ref, endpoints, cache_dir)
            if text and len(text) > 20:
                return {
                    "author": author,
                    "work": work,
                    "reference": ref,
                    "text": text,
                    "urn": urn,
                    "api": api,
                }

    # Fallback: any local fragment
    logger.warning("No fresh passage found via API, falling back to local fragments")
    local_sources = [s for s in sources if s.get("fragments")]
    if local_sources:
        return _pick_local_fragment(random.choice(local_sources))

    return None
