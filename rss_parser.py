"""RSS fetching and title parsing module — uses tokenizer for structured parsing."""

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from config import RSS_URL
import html as html_mod
import re as _re
import urllib.request as _urllib_req
from tokenizer import parse_title, ParsedTitle

CanonicalTitleCache = {}


def fetch_canonical_title(episode_url: str) -> str:
    """Fetch the official anime title from a Mikan episode page."""
    if not episode_url:
        return ""
    if episode_url in CanonicalTitleCache:
        return CanonicalTitleCache[episode_url]
    try:
        req = _urllib_req.Request(episode_url, headers={"User-Agent": "BangumiTool/1.0"})
        with _urllib_req.urlopen(req, timeout=15) as resp:
            page = resp.read().decode("utf-8", errors="ignore")
        m = _re.search(r'class="bangumi-title"[^>]*>.*?<a[^>]*>(.*?)</a>', page, _re.DOTALL)
        if m:
            raw = m.group(1)
            raw = _re.sub(r'<[^>]+>', '', raw)
            raw = html_mod.unescape(raw)
            raw = _re.sub(r'\s+', ' ', raw).strip()
            CanonicalTitleCache[episode_url] = raw
            return raw
    except Exception:
        pass
    CanonicalTitleCache[episode_url] = ""
    return ""


@dataclass
class RSSItem:
    title: str
    pub_date: str = ""
    link: str = ""
    raw: dict = field(default_factory=dict)


def fetch_rss(url: str | None = None) -> list[RSSItem]:
    target = url or RSS_URL
    req = urllib.request.Request(target, headers={"User-Agent": "BangumiTool/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read()
    root = ET.fromstring(content)
    items = []
    for item_el in root.iter("item"):
        title = _get_text(item_el, "title")
        pub_date = _get_text(item_el, "pubDate")
        link = _get_text(item_el, "link")
        items.append(RSSItem(title=title, pub_date=pub_date, link=link))
    return items


def extract_anime_name(title: str) -> str:
    """Extract anime name from RSS title — uses tokenizer for robust parsing."""
    parsed = parse_title(title)
    return parsed.primary_title


def extract_episode(title: str) -> str:
    """Extract episode number from title — uses tokenizer."""
    parsed = parse_title(title)
    if parsed.episode is not None:
        return str(int(parsed.episode))
    return ""


def parse_rss_title(title: str) -> ParsedTitle:
    """Parse an RSS title into structured data using the tokenizer.

    This is the primary entry point for new code.
    """
    return parse_title(title)


def _get_text(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else ""


# -- LLM Fallback Parsing --

def get_llm_config() -> dict:
    """Get LLM configuration."""
    try:
        from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_ENABLED, LLM_MODE
        return {
            "enabled": LLM_ENABLED,
            "api_key": LLM_API_KEY,
            "base_url": LLM_BASE_URL,
            "model": LLM_MODEL,
            "mode": LLM_MODE,
        }
    except ImportError:
        return {"enabled": False}


def extract_anime_name_with_llm(title: str) -> str:
    """Use LLM to parse a single title's anime name (regex fallback)."""
    config = get_llm_config()
    if not config.get("enabled") or not config.get("api_key"):
        return ""
    from llm_parser import parse_single_title
    result = parse_single_title(title, config)
    if result and result.get("anime_name"):
        return result["anime_name"]
    return ""


def extract_metadata_with_llm(titles: list[str]) -> dict[str, dict]:
    """Use LLM to batch-parse multiple titles."""
    config = get_llm_config()
    if not config.get("enabled") or not config.get("api_key"):
        return {}
    from llm_parser import parse_titles_with_llm
    results = parse_titles_with_llm(titles, config)
    mapping = {}
    for i, title in enumerate(titles):
        if i < len(results) and results[i].get("anime_name"):
            mapping[title] = results[i]
    return mapping
