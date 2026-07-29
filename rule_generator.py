"""规则生成器：为未覆盖番剧自动生成候选规则"""

from collections import OrderedDict
import re
from config import (
    RSS_URL, DEFAULT_MUST_NOT, MULTI_SELECT_SOURCES,
    SAVE_PATH_WIN, SAVE_PATH_UNIX,
)
from rule_engine import UncoveredItem
from utils import normalize_name, build_save_path


def generate_rule(uncovered: UncoveredItem) -> tuple[str, dict]:
    """为一个未覆盖番剧生成一条规则。返回 (rule_name, rule_data)。"""
    anime = normalize_name(uncovered.anime_name)
    source = uncovered.source
    rule_name = f"{anime} {source}"

    # Use raw_anime_name (from RSS title) for regex matching, not canonical name
    escaped_anime = _flexible_escape(uncovered.raw_anime_name)
    escaped_source = _flexible_escape(source)
    # Use lookaheads: both anime name and source must appear in the title.
    # This works regardless of whether source is before or after the anime name.
    must_contain = f"(?=.*{escaped_anime})(?=.*{escaped_source})"

    must_not = DEFAULT_MUST_NOT
    if source == "ABEMA":
        tokens = [t for t in must_not.split("|") if t.strip() != "ABEMA"]
        must_not = "|".join(tokens) if tokens else "720"

    win_path, unix_path = build_save_path(rule_name)

    rule_data = OrderedDict([
        ("addPaused", True),
        ("affectedFeeds", [RSS_URL]),
        ("assignedCategory", ""),
        ("enabled", True),
        ("episodeFilter", ""),
        ("ignoreDays", 0),
        ("lastMatch", None),
        ("mustContain", must_contain),
        ("mustNotContain", must_not),
        ("previouslyMatchedEpisodes", []),
        ("priority", 0),
        ("savePath", win_path),
        ("smartFilter", False),
        ("torrentContentLayout", None),
        ("torrentParams", OrderedDict([
            ("category", ""),
            ("download_limit", -1),
            ("download_path", ""),
            ("inactive_seeding_time_limit", -2),
            ("operating_mode", "AutoManaged"),
            ("ratio_limit", -2),
            ("save_path", unix_path),
            ("seeding_time_limit", -2),
            ("share_limit_action", "Default"),
            ("skip_checking", False),
            ("ssl_certificate", ""),
            ("ssl_dh_params", ""),
            ("ssl_private_key", ""),
            ("tags", []),
            ("upload_limit", -1),
            ("use_auto_tmm", False),
        ])),
        ("useRegex", True),
    ])

    return rule_name, rule_data


def generate_rules_for_uncovered(uncovered_list: list[UncoveredItem],
                                  user_selected_sources: dict[str, list[str]] | None = None
                                  ) -> OrderedDict:
    """为所有未覆盖番剧生成规则。"""
    rules = OrderedDict()

    for item in uncovered_list:
        anime = normalize_name(item.anime_name)
        source = item.source

        if source in MULTI_SELECT_SOURCES:
            if not user_selected_sources or anime not in user_selected_sources:
                continue
            if source not in user_selected_sources[anime]:
                continue

        rule_name, rule_data = generate_rule(item)
        rules[rule_name] = rule_data

    return rules


def need_multi_select(uncovered_list: list[UncoveredItem]) -> dict[str, list[str]]:
    """检查哪些番剧需要弹多选框。"""
    result: dict[str, list[str]] = {}
    for item in uncovered_list:
        if item.source in MULTI_SELECT_SOURCES:
            anime = normalize_name(item.anime_name)
            result.setdefault(anime, []).append(item.source)
    return {k: sorted(v) for k, v in result.items() if v}


def export_incremental_rules(new_rules: OrderedDict) -> dict:
    """导出增量规则字典。"""
    return dict(new_rules)


def print_generation_report(rules: OrderedDict):
    """打印规则生成报告。"""
    print(f"\n{'='*60}")
    print(f"  生成规则报告：共 {len(rules)} 条")
    print(f"{'='*60}")
    for name, data in rules.items():
        must = data.get("mustContain", "")
        must_not = data.get("mustNotContain", "")
        print(f"  {name}")
        print(f"    mustContain:     {must}")
        print(f"    mustNotContain:  {must_not}")
        print(f"    savePath:        {data.get('savePath', '')}")
        print(f"    enabled:         {data.get('enabled', False)}")
        print()


def _flexible_escape(text: str) -> str:
    """转义正则特殊字符，但对空白做灵活化处理。"""
    escaped = re.escape(text)
    escaped = re.sub(r"(?:\\ )+", r"\\s*?", escaped)
    return escaped