"""规则匹配引擎：验证规则命中、检测未覆盖番剧、检测同集多命中"""

import re
from dataclasses import dataclass
from rss_parser import RSSItem, extract_anime_name, extract_episode, fetch_canonical_title
from utils import split_must_not, normalize_name


@dataclass
class MatchResult:
    """单条规则的匹配结果"""
    rule_name: str
    must_contain: str
    must_not_contain: str
    use_regex: bool
    hit_titles: list[str]
    hit_count: int = 0

    def __post_init__(self):
        self.hit_count = len(self.hit_titles)


@dataclass
class UncoveredItem:
    """RSS 中未被规则覆盖的条目"""
    anime_name: str
    raw_anime_name: str   # name parsed from RSS title (for regex)
    source: str
    titles: list[str]
    episodes: set[str]


@dataclass
class MultiHitItem:
    """同一集命中多个种子的冲突项"""
    rule_name: str
    episode: str
    titles: list[str]


# ── 核心匹配 ────────────────────────────────────────────

def match_titles(titles: list[str], must_contain: str, must_not_contain: str,
                 use_regex: bool = False) -> list[str]:
    """
    对标题列表执行匹配逻辑：
    1. 正向匹配 mustContain
    2. 反向过滤 mustNotContain
    返回通过的标题列表。
    """
    must_not_tokens = split_must_not(must_not_contain)
    matched = []

    for title in titles:
        # 正向匹配
        ok = False
        if use_regex:
            try:
                ok = bool(re.search(must_contain, title))
            except re.error:
                ok = False
        else:
            ok = must_contain in title

        if not ok:
            continue

        # 反向过滤
        blocked = False
        for token in must_not_tokens:
            if token in title:
                blocked = True
                break

        if not blocked:
            matched.append(title)

    return matched


def validate_all_rules(rules: dict, items: list[RSSItem]) -> list[MatchResult]:
    """
    用所有规则对 RSS 条目做匹配验证。
    返回每条规则的命中结果。
    """
    titles = [item.title for item in items]
    results = []

    for rule_name, rule_data in rules.items():
              # 不检查 enabled 状态，因为规则可能尚未启用但已经定义了匹配逻辑
              # if not rule_data.get('enabled', True):
              #     continue
              # if not rule_data.get("enabled", True):
              #     continue

        must = str(rule_data.get("mustContain", ""))
        must_not = str(rule_data.get("mustNotContain", ""))
        use_regex = bool(rule_data.get("useRegex", False))

        hits = match_titles(titles, must, must_not, use_regex)
        results.append(MatchResult(
            rule_name=rule_name,
            must_contain=must,
            must_not_contain=must_not,
            use_regex=use_regex,
            hit_titles=hits,
        ))

    return results


# ── 未覆盖番剧检测 ──────────────────────────────────────

def find_uncovered(items: list[RSSItem], rules: dict) -> list[UncoveredItem]:
    """
    检测 RSS 中未被现有规则覆盖的番剧。
    逻辑：提取每条 RSS 标题的番剧名，检查是否能被任何规则匹配。
    """
    # 收集现有规则覆盖的番剧名（从规则名和 mustContain 中提取）
    covered_names = set()
    for rule_name in rules:
        covered_names.add(normalize_name(rule_name))

    # 按 (番剧名, 来源) 分组
    from utils import extract_source_suffix
    groups: dict[tuple[str, str], UncoveredItem] = {}

    for item in items:
        canonical = fetch_canonical_title(item.link) if item.link else ""
        raw_anime = extract_anime_name(item.title)
        anime = canonical if canonical else raw_anime
        if not anime:
            continue

        source = extract_source_suffix(item.title)
        ep = extract_episode(item.title)
        key = (anime, source)

        if key not in groups:
            groups[key] = UncoveredItem(
                anime_name=anime,
                raw_anime_name=raw_anime if raw_anime else anime,
                source=source,
                titles=[],
                episodes=set(),
            )
        groups[key].titles.append(item.title)
        if ep:
            groups[key].episodes.add(ep)

    # 过滤掉已被覆盖的
    uncovered = []
    for (anime, source), info in groups.items():
        norm = normalize_name(anime)
        rule_name_check = f"{norm} {source}"

        # 检查是否任何现有规则能匹配这些标题
        is_covered = False
        for rule_name, rule_data in rules.items():
              # 不检查 enabled 状态，因为规则可能尚未启用但已经定义了匹配逻辑
              # if not rule_data.get('enabled', True):
              #     continue
              # if not rule_data.get("enabled", True):
              #     continue
            must = str(rule_data.get("mustContain", ""))
            must_not = str(rule_data.get("mustNotContain", ""))
            use_regex = bool(rule_data.get("useRegex", False))
            hits = match_titles(info.titles, must, must_not, use_regex)
            if hits:
                  is_covered = True
                  break  # ???????????

        if not is_covered:
            uncovered.append(info)

    return sorted(uncovered, key=lambda x: x.anime_name)


# ── 同集多命中检测 ──────────────────────────────────────

def detect_multi_hit(match_results: list[MatchResult]) -> list[MultiHitItem]:
    """
    检测同一规则在同一集中命中多个种子的情况。
    返回冲突列表供用户选择。
    """
    conflicts = []
    for result in match_results:
        # 按集数分组
        ep_map: dict[str, list[str]] = {}
        for title in result.hit_titles:
            ep = extract_episode(title)
            if ep:
                ep_map.setdefault(ep, []).append(title)

        for ep, titles in ep_map.items():
            if len(titles) > 1:
                conflicts.append(MultiHitItem(
                    rule_name=result.rule_name,
                    episode=ep,
                    titles=titles,
                ))

    return conflicts


# ── 报告输出 ────────────────────────────────────────────

def print_match_report(results: list[MatchResult]):
    """打印匹配报告。"""
    hit_rules = [r for r in results if r.hit_count > 0]
    miss_rules = [r for r in results if r.hit_count == 0]

    print(f"\n{'='*60}")
    print(f"  匹配报告：共 {len(results)} 条规则")
    print(f"  命中：{len(hit_rules)}  未命中：{len(miss_rules)}")
    print(f"{'='*60}")

    if hit_rules:
        print(f"\n【命中规则】")
        for r in sorted(hit_rules, key=lambda x: -x.hit_count):
            print(f"  {r.rule_name}  →  命中 {r.hit_count} 条")
            for t in r.hit_titles[:2]:
                print(f"    示例: {t}")

    if miss_rules:
        print(f"\n【未命中规则】")
        for r in miss_rules:
            print(f"  {r.rule_name}")


def print_uncovered_report(uncovered: list[UncoveredItem]):
    """打印未覆盖番剧报告。"""
    print(f"\n{'='*60}")
    print(f"  未覆盖番剧：{len(uncovered)} 部")
    print(f"{'='*60}")
    for i, u in enumerate(uncovered, 1):
        print(f"  {i}. {u.anime_name} [{u.source}]  "
              f"({len(u.titles)} 条, 集数: {','.join(sorted(u.episodes)) or '未知'})")
        if u.titles:
            print(f"     示例: {u.titles[0]}")


def print_multi_hit_report(conflicts: list[MultiHitItem]):
    """打印同集多命中报告。"""
    if not conflicts:
        print("\n  无同集多命中冲突。")
        return
    print(f"\n{'='*60}")
    print(f"  同集多命中冲突：{len(conflicts)} 处")
    print(f"{'='*60}")
    for c in conflicts:
        print(f"\n  规则 [{c.rule_name}] 第 {c.episode} 集命中 {len(c.titles)} 条：")
        for t in c.titles:
            print(f"    - {t}")
