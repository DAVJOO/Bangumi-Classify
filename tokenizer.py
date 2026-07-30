"""Release title tokenizer for anime resource names."""

from __future__ import annotations

import re
from dataclasses import dataclass


# -- Input normalization --

_FILE_EXT = re.compile(r"\.(mp4|mkv|avi|mkv\.torrent)$", re.I)
_FULLWIDTH_BRACKETS = str.maketrans("【】", "[]")


def normalize(raw: str) -> str:
    s = raw.strip().replace("\n", " ")
    s = s.translate(_FULLWIDTH_BRACKETS)
    s = _FILE_EXT.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s


# -- Structured result --

@dataclass
class ParsedTitle:
    raw: str
    group: str = ""
    title_zh: str = ""
    title_en: str = ""
    title_raw: str = ""
    season: int | None = None
    episode: int | float | None = None
    source: str = ""
    resolution: str = ""
    subtitle_group: str = ""

    @property
    def primary_title(self) -> str:
        return self.title_zh or self.title_en or self.title_raw


# -- Detection helpers --

_CHINESE_CHAR = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_KANA_CHAR = re.compile(r"[\u3040-\u30ff]")
_LATIN = re.compile(r"[A-Za-z]")

_SOURCE_PAREN = re.compile(
    r"\((ABEMA|Baha|CR|B-Global|IQIYI|Bilibili|Netflix|DisneyPlus)"
    r"(?:\s+[^\)]*)?\)", re.I,
)
_SOURCE_BRACKET = re.compile(
    r"\[(ABEMA|Baha|CR|B-Global|IQIYI|Bilibili|Netflix|DisneyPlus)\]", re.I,
)
_GROUP_SOURCE_MAP = {"ANi": "Baha", "LoliHouse": "LoliHouse"}
_GROUP_PATTERN = re.compile(r"^\[([^\]]+)\]")
_GROUP_NAMES = re.compile(
    r"(LoliHouse|喵萌奶茶屋|雪飘工作室|桜都字幕组|桜都|猎户压制部|"
    r"沸班亚马制作组|绿茶字幕组|弗里吉亚宫内厅|ANi|"
    r"黒ネズミたち|黒ネズミ|雪飘|喵萌|沸班亚马|绿茶)", re.I,
)

_EP_SXXEXX = re.compile(r"S(\d{1,2})E(\d{1,4})", re.I)
_EP_EXPLICIT = re.compile(r"(?:EP?|episode|#)\s*[-_. ]?\s*(\d{1,4})", re.I)
_EP_DASH = re.compile(r"\s-\s(\d{1,4})\s*(?:\[|$|\()")
_EP_BRACKET = re.compile(r"\[(\d{1,4})\]")
_EP_CHINESE = re.compile(r"第\s*(\d{1,4})\s*[话話集]")

_SEASON_SXX = re.compile(r"(?<!\w)S(\d{1,2})(?!\w)", re.I)
_SEASON_CN = re.compile(r"第([零〇一二两三四五六七八九十百\d]+)[季期]")
_SEASON_3 = re.compile(r"\b3(?:期|nd|rd|st|th)\b", re.I)
_SEASON_2ND = re.compile(r"\b(?:第二季|2期|2nd)\b", re.I)

_NOISE = re.compile(
    r"(?:\[BR\]|\[BD\]|\[DVD\]|1080[pPiI]|720[pPiI]|2160[pPiI]|"
    r"4[Kk]|HEVC|AVC|x264|x265|H\.?264|H\.?265|AAC|FLAC|DTS|"
    r"MA5\.1|2\.0|5\.1|7\.1|"
    r"WebRip|Web-DL|WEB-DL|BDRip|BDRemux|HDRip|DVDRip|HDTV|"
    r"NVENC|10bit|10-bit|8bit|8-bit|"
    r"简繁|简中|繁中|简日|繁日|内封|外挂|外置|字幕|"
    r"多语|多字|中日|日繁|简繁日|双语|"
    r"RAW|PROPER|REMUX|CHT|CHS)", re.I,
)
_RESOLUTION = re.compile(r"(4K|2160p?|1080[pPiI]|720[pPiI]|480p?)", re.I)
_TITLE_SEP = re.compile(r"\s*[\/|]\s*")
_TITLE_NOISE = re.compile(r"[★☆♪♥♡●○◆◇■□▲△▼▽※→←↑↓＝＋～〜]")


# -- Main parser --

def parse_title(raw: str) -> ParsedTitle:
    norm = normalize(raw)
    result = ParsedTitle(raw=raw)

    result.episode = _extract_episode(norm)
    result.season = _extract_season(norm)
    result.source = _extract_source(raw)

    g = _GROUP_PATTERN.match(norm)
    if g:
        group_text = g.group(1).strip()
        result.subtitle_group = group_text
        result.group = _resolve_group_name(group_text)
        norm_after_group = norm[g.end():]
    else:
        norm_after_group = norm

    if not result.source and result.group:
        for gname, src in _GROUP_SOURCE_MAP.items():
            if gname.lower() == result.group.lower():
                result.source = src
                break
    if not result.source and result.group:
        if _GROUP_NAMES.search(result.group):
            result.source = result.group

    clean = re.sub(r"\[[^\]]*\]", " ", norm_after_group)
    clean = re.sub(r"\([^\)]*\)", " ", clean)
    clean = _NOISE.sub(" ", clean)

    rm = _RESOLUTION.search(raw)
    if rm:
        result.resolution = rm.group(1)

    clean = _TITLE_NOISE.sub(" ", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    result.title_raw = clean

    parts = _TITLE_SEP.split(clean)
    parts = [p.strip() for p in parts if p.strip()]

    zh_title = ""
    en_title = ""
    for part in parts:
        part = part.strip(" -")
        if not part:
            continue
        part = _strip_episode_from_title(part)
        if not part.strip():
            continue
        if _CHINESE_CHAR.search(part):
            if not zh_title or len(part) > len(zh_title):
                zh_title = part
        elif _KANA_CHAR.search(part) or _LATIN.search(part):
            if not en_title or len(part) > len(en_title):
                en_title = part

    result.title_zh = _clean_title(zh_title) if zh_title else ""
    result.title_en = _clean_title(en_title) if en_title else ""

    if not parts or (not result.title_zh and not result.title_en):
        single = _clean_title(clean)
        single = _strip_episode_from_title(single)
        single = _clean_title(single)
        if _CHINESE_CHAR.search(single):
            result.title_zh = single
        else:
            result.title_en = single

    if not result.title_zh and not result.title_en:
        _extract_title_from_brackets(norm, result)

    return result


# -- Helper functions --

def _extract_title_from_brackets(norm: str, result: ParsedTitle) -> None:
    """Fallback: find title in [bracket] content when primary extraction fails."""
    brackets = re.findall(r"\[([^\]]+)\]", norm)
    if len(brackets) < 2:
        return
    for bracket in brackets[1:]:
        if re.match(r"^\d{1,4}$", bracket.strip()):
            continue
        if _RESOLUTION.match(bracket.strip()):
            continue
        if _NOISE.match(bracket.strip()):
            continue
        sub_parts = _TITLE_SEP.split(bracket)
        for part in sub_parts:
            part = _strip_episode_from_title(part.strip(" -"))
            part = _clean_title(part)
            if not part:
                continue
            if _CHINESE_CHAR.search(part):
                if not result.title_zh or len(part) > len(result.title_zh):
                    result.title_zh = part
            elif _KANA_CHAR.search(part) or _LATIN.search(part):
                if not result.title_en or len(part) > len(result.title_en):
                    result.title_en = part
        if result.title_zh or result.title_en:
            break


def _resolve_group_name(bracket_text: str) -> str:
    for gname in _GROUP_NAMES.finditer(bracket_text):
        return gname.group(1)
    if "&" in bracket_text or "\u00d7" in bracket_text:
        sep = "&" if "&" in bracket_text else "\u00d7"
        first = bracket_text.split(sep)[0].strip()
        if first:
            return first
    return bracket_text.strip()


def _extract_source(title: str) -> str:
    m = _SOURCE_PAREN.search(title)
    if m:
        return _normalize_source(m.group(1).upper())
    first_bracket_end = title.find("]")
    search_from = first_bracket_end + 1 if first_bracket_end > 0 else 0
    remaining = title[search_from:]
    m = _SOURCE_BRACKET.search(remaining)
    if m:
        return _normalize_source(m.group(1).upper())
    if re.search(r"\[ANi\]", title, re.IGNORECASE):
        return "Baha"
    if "\u9ed1\u30cd\u30ba\u30df" in title:
        m = _SOURCE_PAREN.search(title)
        if m:
            return _normalize_source(m.group(1).upper())
    return ""


def _normalize_source(src: str) -> str:
    mapping = {
        "ABEMA": "ABEMA", "BAHA": "Baha", "CR": "CR",
        "B-GLOBAL": "B-Global", "IQIYI": "IQIYI",
        "BILIBILI": "Bilibili", "NETFLIX": "Netflix", "DISNEYPLUS": "DisneyPlus",
    }
    return mapping.get(src.upper(), src)


def _extract_episode(text: str) -> int | None:
    m = _EP_SXXEXX.search(text)
    if m:
        return int(m.group(2))
    m = _EP_EXPLICIT.search(text)
    if m:
        return int(m.group(1))
    m = _EP_DASH.search(text)
    if m:
        return int(m.group(1))
    m = _EP_BRACKET.search(text)
    if m:
        return int(m.group(1))
    m = _EP_CHINESE.search(text)
    if m:
        return int(m.group(1))
    return None


def _strip_episode_from_title(title: str) -> str:
    title = re.sub(r"\s*-\s*\d{1,4}\s*$", "", title)
    title = re.sub(r"\s*(?:EP?|episode|#)\s*[-_. ]?\s*\d{1,4}\s*$", "", title, flags=re.I)
    title = re.sub(r"\s*\[\d{1,4}\]\s*$", "", title)
    return title.strip()


def _extract_season(text: str) -> int | None:
    m = _SEASON_SXX.search(text)
    if m:
        return int(m.group(1))
    if _SEASON_2ND.search(text):
        return 2
    if _SEASON_3.search(text):
        return 3
    m = _SEASON_CN.search(text)
    if m:
        return _chinese_to_int(m.group(1))
    return None


def _chinese_to_int(s: str) -> int | None:
    cn_map = {
        "\u96f6": 0, "\u3007": 0, "\u4e00": 1, "\u4e8c": 2, "\u4e24": 2, "\u4e09": 3,
        "\u56db": 4, "\u4e94": 5, "\u516d": 6, "\u4e03": 7, "\u516b": 8, "\u4e5d": 9,
        "\u5341": 10, "\u767e": 100,
    }
    if s.isdigit():
        return int(s)
    result = 0
    current = 0
    for ch in s:
        if ch in cn_map:
            val = cn_map[ch]
            if val == 10:
                if current == 0:
                    current = 1
                result += current * 10
                current = 0
            elif val == 100:
                result += current * 100 if current else 100
                current = 0
            else:
                current = val
    result += current
    return result if result > 0 else None


def _clean_title(title: str) -> str:
    title = title.strip(" -")
    title = re.sub(r"\s{2,}", " ", title)
    title = re.sub(r"^[\s\u002d_\u00b7.]+", "", title)
    title = re.sub(r"[\s\u002d_\u00b7.]+$", "", title)
    return title
