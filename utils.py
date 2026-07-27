"""工具函数：规则管理、命名规范、路径格式化"""

import os
import re
import json
from config import RULE_DIR, FIXED_TRANSLATIONS, SAVE_PATH_WIN, SAVE_PATH_UNIX


# ── 规则文件 ────────────────────────────────────────────

RULES_FILE = os.path.join(RULE_DIR, "rules.json")


def load_rules() -> dict:
    """读取规则文件。"""
    if not os.path.exists(RULES_FILE):
        return {}
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_rules(rules: dict):
    """写入规则文件。"""
    os.makedirs(RULE_DIR, exist_ok=True)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)


def add_rules(new_rules: dict) -> int:
    """将新规则合并到规则文件中（跳过已存在的），返回新增数量。"""
    existing = load_rules()
    count = 0
    for name, data in new_rules.items():
        if name not in existing:
            existing[name] = data
            count += 1
    if count > 0:
        save_rules(existing)
    return count


def remove_rules(rule_names: list[str]):
    """从规则文件中删除指定规则。"""
    existing = load_rules()
    for name in rule_names:
        existing.pop(name, None)
    save_rules(existing)


# ── 命名规范 ────────────────────────────────────────────

def normalize_name(raw_name: str) -> str:
    """按用户偏好规范番剧名。"""
    name = raw_name
    for old, new in FIXED_TRANSLATIONS.items():
        if old in name:
            name = name.replace(old, new)
    name = re.sub(r"[「」『』【】《》〈〉（）\(\)\[\]{}＜＞＜＞]", " ", name)
    name = re.sub(r"[♪★☆♥♡●○◆◇■□▲△▼▽※→←↑↓＝＋]", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def extract_source_suffix(title: str) -> str:
    """从标题中提取来源后缀。"""
    from config import KURO_SOURCE_MAP, ANI_SUFFIX

    if re.search(r"\[ANi\]", title, re.IGNORECASE):
        return ANI_SUFFIX

    if "黒ネズミたち" in title or "黒ネズミ" in title:
        for key, suffix in KURO_SOURCE_MAP.items():
            if key in title:
                return suffix
        return "Unknown"

    group_patterns = [
        (r"\[LoliHouse\]", "LoliHouse"),
        (r"喵萌奶茶屋",   "喵萌奶茶屋"),
        (r"桜都字幕组",   "桜都字幕组"),
        (r"桜都",         "桜都字幕组"),
        (r"雪飘工作室",   "雪飘工作室"),
        (r"猎户压制部",   "猎户压制部"),
        (r"弗里吉亚宫内厅", "弗里吉亚宫内厅"),
        (r"\[Baha",     "Baha"),
        (r"\[CR",       "CR"),
        (r"沸班亚马制作组", "沸班亚马制作组"),
        (r"绿茶字幕组",   "绿茶字幕组"),
        (r"\[B-Global", "B-Global"),
        (r"\[ABEMA",    "ABEMA"),
    ]
    for pattern, suffix in group_patterns:
        if re.search(pattern, title):
            return suffix

    return "Unknown"


def build_rule_name(anime_name: str, source: str) -> str:
    return f"{normalize_name(anime_name)} {source}"


# ── 路径规范 ────────────────────────────────────────────

def build_save_path(rule_name: str) -> tuple[str, str]:
    win = f"{SAVE_PATH_WIN}\\{rule_name}"
    unix = f"{SAVE_PATH_UNIX}/{rule_name}"
    return win, unix


# ── 编码处理 ────────────────────────────────────────────

def load_rules_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_rules_json(data: dict, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 正则辅助 ────────────────────────────────────────────

def split_must_not(text: str) -> list[str]:
    if not text:
        return []
    return [t for t in re.split(r"[\s|]+", text) if t]