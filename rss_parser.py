"""RSS 抓取与标题解析模块"""

import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from config import RSS_URL
import html as html_mod
import re as _re
import urllib.request as _urllib_req

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
    """从 RSS 标题中提取番剧名（优先中文）。"""
    # 去掉第一个方括号组名前缀，方便后续匹配
    t = re.sub(r"\s+S\d+E\d+\b", "", title)
    t = re.sub(r"^\[.*?\]\s*", "", t)
    # 也去掉 【组名】 前缀
    t = re.sub(r"^(【.*?】\s*)+", "", t)

    # 去掉 ★07月新番★ 之类标记
    t2 = re.sub(r"^[★☆♪♥]+\d+月新番[★☆♪♥]*\s*", "", t)

    # 模式A0: [名1/名2/名3]格式（雪飘工作室等）
    m = re.match(r"^\[([^\]]*)\]\s*", t)
    if m and "/" in m.group(1):
        parts = [p.strip() for p in m.group(1).split("/")]
        # 优先选中文名
        for p in parts:
            if _has_chinese(p):
                name = _clean_name(p)
                if name and len(name) > 1:
                    return name
        # 没有中文名则选第一个
        name = _clean_name(parts[0])
        if name and len(name) > 1:
            return name

    # 模式A: 名1 / 名2 - 集数  →  优先选中文名
    m = re.match(r"(.+?)\s*/\s*(.+?)\s*-\s*\d+", t2)
    if m:
        part1, part2 = m.group(1).strip(), m.group(2).strip()
        # If part1 has CJK chars, prefer it (Mikan format: ??? / ??? / ???)
        if _has_chinese(part1):
            name = _clean_name(part1)
            if name and len(name) > 1:
                return name
        # strip brackets before checking Chinese (avoid codec info like ???? interfering)
        part2_stripped = re.sub(r"\[.*?\]", "", part2)
        if _has_chinese(part2_stripped):
            name = _clean_name(part2)
            if name and len(name) > 1:
                return name
        name = _clean_name(part1)
        if name and len(name) > 1:
            return name

    # 模式B: 名1 / 名2（无集数）
    m = re.match(r"(.+?)\s*/\s*(.+)", t2)
    if m:
        part1, part2 = m.group(1).strip(), m.group(2).strip()
        # If part1 has CJK chars, prefer it (Mikan format: ??? / ??? / ???)
        if _has_chinese(part1):
            name = _clean_name(part1)
            if name and len(name) > 1:
                return name
        # strip brackets before checking Chinese (avoid codec info like ???? interfering)
        part2_stripped = re.sub(r"\[.*?\]", "", part2)
        if _has_chinese(part2_stripped):
            name = _clean_name(part2)
            if name and len(name) > 1:
                return name
        name = _clean_name(part1)
        if name and len(name) > 1:
            return name

    # 模式C: 中文名 - 集数
    m = re.match(r"(.+?)\s*-\s*\d+", t2)
    if m:
        name = _clean_name(m.group(1).strip())
        if name and len(name) > 1:
            return name

    # 模式D: 中文名 [01]
    m = re.match(r"(.+?)\s*\[\d{2}\]", t2)
    if m:
        name = _clean_name(m.group(1).strip())
        if name and len(name) > 1:
            return name

    # 模式E: 中文名 (ABEMA/Baha/CR ...)
    m = re.match(r"(.+?)\s*\((?:ABEMA|Baha|CR|B-Global)\s", t2)
    if m:
        name = _clean_name(m.group(1).strip())
        if name and len(name) > 1:
            return name

    return ""



def _has_chinese(text: str) -> bool:
    """检查文本是否包含中文字符。"""
    return bool(re.search(r'[一-鿿]', text))


def _clean_name(name: str) -> str:
    name = re.sub(r"（放送版）$", "", name)
    name = re.sub(r"^[★☆♪♥]+\d+月新番[★☆♪♥]*", "", name).strip()
    name = re.sub(r"^\[", "", name)
    name = re.sub(r"\]$", "", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def extract_episode(title: str) -> str:
    m = re.search(r"-\s*(\d{1,3})\s*(?:\[|\()", title)
    if m:
        return m.group(1)
    m = re.search(r"\[(\d{1,3})\]", title)
    if m:
        return m.group(1)
    m = re.search(r"S\d+E(\d+)", title, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def _get_text(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else ""
