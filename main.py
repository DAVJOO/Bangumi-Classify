"""Bangumi 自动分类工具 - 交互式主程序"""

import sys
import os
import glob

# PyInstaller ???? exe ???????? config.py
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

# ????? config.py ?????????
import importlib
import importlib.util
_external_config = os.path.join(APP_DIR, "config.py")
if os.path.isfile(_external_config):
    _spec = importlib.util.spec_from_file_location("config", _external_config)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["config"] = _mod
    _spec.loader.exec_module(_mod)

from collections import OrderedDict
from rss_parser import fetch_rss, extract_anime_name
from rule_engine import (
    validate_all_rules, find_uncovered, detect_multi_hit,
    print_match_report, print_uncovered_report, print_multi_hit_report,
)
from rule_generator import (
    generate_rules_for_uncovered, need_multi_select, export_incremental_rules,
    print_generation_report,
)
from utils import (
    load_rules, save_rules, add_rules, remove_rules, RULES_FILE,
    normalize_name, extract_source_suffix,
)
from qbittorrent_api import QBittorrentClient
from config import MULTI_SELECT_SOURCES, RULE_DIR, QB_BASE_URL, RSS_URL

VERSION = "2.0.0"


# ── 颜色输出 ────────────────────────────────────────────

def _c(text, code):
    try:
        return f"\033[{code}m{text}\033[0m"
    except Exception:
        return text

def green(t):  return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t):    return _c(t, "31")
def cyan(t):   return _c(t, "36")
def bold(t):   return _c(t, "1")


# ── UI 辅助 ─────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def pause():
    input("\n按 Enter 继续...")

def print_header(title):
    w = 56
    print()
    print(cyan("=" * w))
    print(cyan(f"  {title}"))
    print(cyan("=" * w))

def print_menu_item(num, label, desc=""):
    line = f"  [{num}] {label}"
    if desc:
        line += f"  - {desc}"
    print(line)

def prompt_int(prompt, min_val, max_val):
    while True:
        try:
            val = int(input(prompt))
            if min_val <= val <= max_val:
                return val
            print(f"  请输入 {min_val}-{max_val} 之间的数字")
        except ValueError:
            print("  请输入数字")
        except (EOFError, KeyboardInterrupt):
            return -1

def prompt_yes_no(prompt, default="y"):
    suffix = "[Y/n]" if default == "y" else "[y/N]"
    try:
        ans = input(f"{prompt} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default == "y"
    if not ans:
        return default == "y"
    return ans in ("y", "yes", "是")


# ── [1] 查看状态 ────────────────────────────────────────

def do_status():
    """查看当前所有规则的状态。"""
    print_header("当前状态")
    rules = load_rules()
    if not rules:
        print("  当前无规则。")
        return

    enabled = sum(1 for r in rules.values() if r.get("enabled", True))
    print(f"  规则总数: {len(rules)}")
    print(f"  已启用:   {enabled}")
    print(f"  未启用:   {len(rules) - enabled}")

    print(f"\n  规则列表:")
    for name, data in rules.items():
        en = "ON " if data.get("enabled", True) else "OFF"
        must = data.get("mustContain", "")[:50]
        print(f"    [{en}] {name}")
        print(f"         mustContain: {must}...")


# ── [2] 刷新 RSS ────────────────────────────────────────

def do_refresh_rss():
    """刷新 qBittorrent RSS。"""
    import time
    print_header("刷新 RSS")
    print("  正在连接 qBittorrent...")
    client = QBittorrentClient()
    if not client.login():
        print(f"  {red('连接失败！')}")
        return

    print("  正在刷新 RSS...")
    if client.refresh_rss():
        print(f"  {green('RSS 已刷新！')}")
    else:
        print(f"  {yellow('刷新可能未成功，请手动检查。')}")

    print("\n  等待 RSS 数据加载...")
    for i in range(5):
        time.sleep(1)
        items = client.get_rss_items(with_data=True)
        if items:
            loading = sum(1 for v in items.values() if isinstance(v, dict) and v.get("isLoading", False))
            if loading == 0:
                count = len(items)
                print(f"  {green(f'RSS 加载完成！频道数: {count}')}")
                for name, data in items.items():
                    if isinstance(data, dict) and "articleIds" in data:
                        print(f"    - {name}: {len(data['articleIds'])} 条")
                return
            else:
                print(f"  {i+1}/5 等待中... ({loading} 个频道正在加载)")
        else:
            print(f"  {i+1}/5 等待中...")
    print(f"  {yellow('超时：RSS 数据可能未完全加载。')}")


# ── [3] 分析规则 ────────────────────────────────────────

def do_analyze():
    """分析现有规则 vs RSS 匹配情况。"""
    rules = load_rules()
    if not rules:
        print("\n  错误：当前无规则。")
        return

    print_header("规则分析")
    print(f"  规则数: {len(rules)}")

    print("  正在抓取 RSS...")
    items = fetch_rss()
    print(f"  RSS 条目: {len(items)} 条")

    results = validate_all_rules(rules, items)
    print_match_report(results)

    conflicts = detect_multi_hit(results)
    print_multi_hit_report(conflicts)

    uncovered = find_uncovered(items, rules)
    print_uncovered_report(uncovered)


# ── [4] 查看差异 ────────────────────────────────────────

def do_diff():
    """查看 RSS 中新增的、尚未有规则覆盖的番剧。"""
    rules = load_rules()
    print_header("新增番剧（未覆盖）")
    print(f"  当前规则数: {len(rules)}")
    print("  正在抓取 RSS...")
    items = fetch_rss()
    print(f"  RSS 条目: {len(items)} 条")

    uncovered = find_uncovered(items, rules)
    print_uncovered_report(uncovered)
    return uncovered


# ── [5] 生成规则 ────────────────────────────────────────

def do_generate():
    """交互式生成增量规则。"""
    rules = load_rules()

    print_header("生成增量规则")
    print("  正在抓取 RSS...")
    items = fetch_rss()
    print(f"  RSS 条目: {len(items)} 条")

    uncovered = find_uncovered(items, rules)
    if not uncovered:
        print(f"\n  {green('没有发现未覆盖的番剧，无需生成新规则。')}")
        return

    print_uncovered_report(uncovered)

    multi = need_multi_select(uncovered)
    user_selected: dict[str, list[str]] = {}

    if multi:
        print(f"\n  {yellow('以下番剧涉及 ABEMA/Baha/B-Global/CR 来源，请选择要下载的：')}")
        print()

        for i, (anime, sources) in enumerate(multi.items(), 1):
            print(f"  番剧 {i}: {bold(anime)}")
            print(f"    可选来源: {', '.join(sources)}")

            chosen = []
            for j, src in enumerate(sources, 1):
                default = "n" if src == "ABEMA" else "y"
                if prompt_yes_no(f"    下载 {src} 版本？", default=default):
                    chosen.append(src)

            if chosen:
                user_selected[anime] = chosen
            print()

        if user_selected:
            print(f"  你的选择:")
            for anime, srcs in user_selected.items():
                print(f"    {anime}: {', '.join(srcs)}")
        else:
            print(f"  {yellow('你没有选择任何来源，将仅生成非 MULTI_SELECT 来源的规则。')}")

    new_rules = generate_rules_for_uncovered(uncovered, user_selected)
    if not new_rules:
        print(f"\n  {yellow('没有需要生成的规则。')}")
        return

    print_generation_report(new_rules)

    # 命中验证
    print("  正在验证新规则命中...")
    results = validate_all_rules(dict(new_rules), items)
    all_hit = True
    for r in results:
        if r.hit_count > 0:
            print(f"    {green('OK')}  {r.rule_name}  命中 {r.hit_count} 条")
        else:
            print(f"    {red('MISS')}  {r.rule_name}  未命中")
            all_hit = False

    if not all_hit:
        print(f"\n  {yellow('部分规则未命中，是否仍然保存？')}")
        if not prompt_yes_no("  继续", default="n"):
            print("  已取消。")
            return

    # 合并到规则文件
    count = add_rules(dict(new_rules))
    print(f"\n  {green(f'已保存 {count} 条新规则到 rules.json')}")
    print(f"  当前规则总数: {len(load_rules())}")


# ── [6] 导入规则到 qBittorrent ─────────────────────────

def do_import():
    """将规则导入到 qBittorrent。"""
    rules = load_rules()
    if not rules:
        print("\n  错误：当前无规则。")
        return

    print_header("导入规则到 qBittorrent")
    print(f"  待导入: {len(rules)} 条规则")
    print(f"  目标: {QB_BASE_URL}")
    print()

    for i, name in enumerate(rules.keys(), 1):
        print(f"    {i:2d}. {name}")

    print(f"\n  {yellow('注意：导入前会自动检查乱码，导入后会再次检查。')}")
    if not prompt_yes_no("  确认导入？", default="n"):
        print("  已取消。")
        return

    print("\n  正在连接 qBittorrent...")
    client = QBittorrentClient()
    if not client.login():
        print(f"  {red('连接失败！请检查 qBittorrent 是否运行中。')}")
        return
    print(f"  {green('连接成功！')}")

    # 确保 RSS 源已添加
    print("  正在检查 RSS 源...")
    if not client.ensure_rss_feed(RSS_URL, "Bangumi"):
        print(f"  {red('RSS 源添加失败！')}")
        return

    print("  正在导入...")
    report = client.safe_import(rules)

    print_header("导入报告")
    print(f"  本次导入: {len(report['imported'])} 条")
    print(f"  导入失败: {len(report['failed'])} 条")
    print(f"  导入前乱码: {len(report['pre_check_garbled'])} 条")
    print(f"  导入后乱码修复: {len(report['fixed'])} 条")

    if report["imported"]:
        print(f"\n  {green('成功:')}")
        for name in report["imported"]:
            print(f"    - {name}")

    if report["failed"]:
        print(f"\n  {red('失败:')}")
        for name in report["failed"]:
            print(f"    - {name}")


# ── [7] 启用下载 ────────────────────────────────────────

def do_enable_and_download():
    """启用规则并开始下载。"""
    print_header("启用并下载")

    print("  正在连接 qBittorrent...")
    client = QBittorrentClient()
    if not client.login():
        print(f"  {red('连接失败！请检查 qBittorrent 是否运行中。')}")
        return
    print(f"  {green('连接成功！')}")

    rules = client.get_rules()
    if not rules or not isinstance(rules, dict):
        print("  qB 中没有规则。请先使用 [6] 导入规则。")
        return

    disabled = []
    for name, data in rules.items():
        if isinstance(data, dict) and not data.get("enabled", True):
            disabled.append(name)

    if not disabled:
        print(f"  {green('所有规则都已启用，无需操作。')}")
        return

    print(f"  当前有 {len(disabled)} 条禁用规则：")
    for i, name in enumerate(disabled, 1):
        print(f"    {i:2d}. {name}")

    print(f"\n  {yellow('即将启用以上全部规则并设置为立即下载（非暂停）。')}")
    if not prompt_yes_no("  确认启用？", default="y"):
        print("  已取消。")
        return

    print("\n  正在启用规则并触发下载...")
    result = client.enable_rules(disabled)

    print_header("启用报告")
    print(f"  成功启用: {len(result['enabled'])} 条")
    print(f"  启用失败: {len(result['failed'])} 条")
    print(f"  恢复下载: {result.get('resumed', 0)} 个 torrent")

    if result["enabled"]:
        print(f"\n  {green('已启用:')}")
        for name in result["enabled"]:
            print(f"    - {name}")

        # 同步本地规则文件
        _sync_rules_enabled(result["enabled"])

    if result["failed"]:
        print(f"\n  {red('失败:')}")
        for name in result["failed"]:
            print(f"    - {name}")

    resumed_count = result.get("resumed", 0)
    if resumed_count > 0:
        print(f"\n  已恢复 {resumed_count} 个暂停的 torrent，下载应已开始。")


def _sync_rules_enabled(enabled_names: list[str]):
    """将启用状态同步到本地规则文件。"""
    rules = load_rules()
    modified = False
    for name in enabled_names:
        if name in rules:
            rules[name]["enabled"] = True
            rules[name]["addPaused"] = False
            modified = True
    if modified:
        save_rules(rules)
        print(f"  {green('本地规则文件已同步')}")


# ── [8] qB 状态 ────────────────────────────────────────

def do_import_status():
    """查看 qBittorrent 中的规则状态。"""
    print_header("qBittorrent 规则状态")
    print("  正在连接...")
    client = QBittorrentClient()
    if not client.login():
        print(f"  {red('连接失败！')}")
        return

    rules = client.get_rules()
    if not rules or not isinstance(rules, dict):
        print("  未获取到规则。")
        return

    print(f"  规则总数: {len(rules)}")

    garbled = client.check_garbled_rules()
    if garbled:
        print(f"\n  {red(f'发现 {len(garbled)} 条乱码规则:')}")
        for g in garbled:
            print(f"    - {repr(g)}")
        if prompt_yes_no("  是否删除这些乱码规则？", default="n"):
            for g in garbled:
                client.delete_rule(g)
            print(f"  {green('已删除。')}")
    else:
        print(f"  {green('无乱码规则。')}")

    print(f"\n  规则列表:")
    for name in sorted(rules.keys()):
        data = rules[name]
        if isinstance(data, dict):
            en = "ON " if data.get("enabled", True) else "OFF"
        else:
            en = " ? "
        print(f"    [{en}] {name}")


# ── [9] 一键自动化 ──────────────────────────────────────

def do_auto():
    """一键自动化：识别差异 → 生成规则 → 导入 → 启用下载。"""
    import time

    print_header("一键自动化流程")

    # 步骤 1: 刷新 RSS
    print("  步骤 1/4: 刷新 RSS")
    print("  " + "─" * 28)

    print("\n  正在连接 qBittorrent...")
    client = QBittorrentClient()
    if not client.login():
        print(f"  {red('连接失败！请检查 qBittorrent 是否运行中。')}")
        return
    print(f"  {green('连接成功！')}")

    print("\n  正在刷新 RSS...")
    client.refresh_rss()
    time.sleep(2)

    print("\n  正在读取 RSS 条目...")
    items = fetch_rss()
    print(f"  RSS 条目: {len(items)} 条")

    if not items:
        print(f"\n  {yellow('RSS 为空，无法继续。')}")
        return

    # 步骤 2: 识别差异
    print(f"\n  步骤 2/4: 识别差异")
    print("  " + "─" * 28)

    all_rules = load_rules()
    print(f"  当前规则数: {len(all_rules)}")
    uncovered = find_uncovered(items, all_rules)
    print_uncovered_report(uncovered)

    if not uncovered:
        print(f"\n  {green('所有番剧都已覆盖，无需生成新规则。')}")
        print(f"\n  步骤 3/4: 跳过（无新规则）")
        print(f"\n  步骤 4/4: 启用下载")
        print("  " + "─" * 28)
        _auto_enable(client)
        return

    # 步骤 3: 生成规则
    print(f"\n  步骤 3/4: 生成规则")
    print("  " + "─" * 28)

    multi = need_multi_select(uncovered)
    user_selected: dict[str, list[str]] = {}

    if multi:
        print(f"\n  {yellow('以下番剧涉及 ABEMA/Baha/B-Global/CR 来源，请选择要下载的：')}")
        print()

        for i, (anime, sources) in enumerate(multi.items(), 1):
            print(f"  番剧 {i}: {bold(anime)}")
            print(f"    可选来源: {', '.join(sources)}")

            chosen = []
            for j, src in enumerate(sources, 1):
                default = "n" if src == "ABEMA" else "y"
                if prompt_yes_no(f"    下载 {src} 版本？", default=default):
                    chosen.append(src)

            if chosen:
                user_selected[anime] = chosen
            print()

        if user_selected:
            print(f"  你的选择:")
            for anime, srcs in user_selected.items():
                print(f"    {anime}: {', '.join(srcs)}")
        else:
            print(f"  {yellow('你没有选择任何来源，将仅生成非 MULTI_SELECT 来源的规则。')}")

    new_rules = generate_rules_for_uncovered(uncovered, user_selected)
    if not new_rules:
        print(f"\n  {yellow('没有需要生成的规则。')}")
        return

    print_generation_report(new_rules)

    # 命中验证
    print("  正在验证新规则命中...")
    results = validate_all_rules(dict(new_rules), items)
    all_hit = True
    for r in results:
        if r.hit_count > 0:
            print(f"    {green('OK')}  {r.rule_name}  命中 {r.hit_count} 条")
        else:
            print(f"    {red('MISS')}  {r.rule_name}  未命中")
            all_hit = False

    if not all_hit:
        print(f"\n  {yellow('部分规则未命中，是否仍然继续？')}")
        if not prompt_yes_no("  继续", default="n"):
            print("  已取消。")
            return

    # 保存规则
    count = add_rules(dict(new_rules))
    print(f"\n  {green(f'已保存 {count} 条新规则到 rules.json')}")

    # 步骤 4: 导入并启用
    print(f"\n  步骤 4/4: 导入规则并启用下载")
    print("  " + "─" * 28)

    print("\n  正在检查 RSS 源...")
    if not client.ensure_rss_feed(RSS_URL, "Bangumi"):
        print(f"  {red('RSS 源添加失败！')}")
        return

    print("  正在导入规则...")
    report = client.safe_import(load_rules())
    print(f"  导入完成: 成功 {len(report['imported'])} 条，失败 {len(report['failed'])} 条")

    if not report["imported"]:
        print(f"\n  {red('没有规则导入成功，无法启用。')}")
        return

    _auto_enable(client, report["imported"])


def _auto_enable(client, rule_names: list[str] = None):
    """自动启用规则并开始下载。"""
    import time

    if not rule_names:
        rules = client.get_rules()
        if not rules or not isinstance(rules, dict):
            print("  qB 中没有规则。")
            return
        rule_names = [name for name, data in rules.items()
                      if isinstance(data, dict) and not data.get("enabled", True)]

    if not rule_names:
        print(f"\n  {green('所有规则都已启用。')}")
        print("  正在刷新 RSS...")
        client.refresh_rss()
        time.sleep(1)
        resumed = client.resume_paused_torrents()
        if resumed > 0:
            print(f"\n  已恢复 {resumed} 个暂停的 torrent，下载应已开始。")
        return

    print(f"\n  正在启用 {len(rule_names)} 条规则...")
    result = client.enable_rules(rule_names)

    print(f"\n  成功启用: {len(result['enabled'])} 条")
    print(f"  启用失败: {len(result['failed'])} 条")

    if result["enabled"]:
        print(f"\n  {green('已启用的规则:')}")
        for name in result["enabled"]:
            print(f"    - {name}")
        _sync_rules_enabled(result["enabled"])

    resumed_count = result.get("resumed", 0)
    if resumed_count > 0:
        print(f"\n  已恢复 {resumed_count} 个暂停的 torrent，下载应已开始。")
    else:
        print(f"\n  {green('自动化流程完成！')}")


def do_change_path():
    """?????????"""
    import config
    print_header("??????")

    print(f"  ?? Windows ??: {config.SAVE_PATH_WIN}")
    print(f"  ?? Unix ??:    {config.SAVE_PATH_UNIX}")
    print()

    new_path = input("  ?????????Windows ???? F:\??\2026.07?: ").strip()
    if not new_path:
        print("  ????")
        return

    # ???? Unix ???????????
    new_path_unix = new_path.replace("\\", "/")

    print()
    print(f"  ? Windows ??: {new_path}")
    print(f"  ? Unix ??:    {new_path_unix}")
    confirm = input("  ?????[Y/n] ").strip().lower()
    if confirm == "n":
        print("  ????")
        return

    # ?? config.py ??
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg_content = f.read()

    # ?? SAVE_PATH_WIN
    cfg_content = re.sub(
        r'SAVE_PATH_WIN\s*=\s*r?"[^"]*"',
        f'SAVE_PATH_WIN = r"{new_path}"',
        cfg_content
    )
    # ?? SAVE_PATH_UNIX
    cfg_content = re.sub(
        r'SAVE_PATH_UNIX\s*=\s*"[^"]*"',
        f'SAVE_PATH_UNIX = "{new_path_unix}"',
        cfg_content
    )

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(cfg_content)

    # ?????????
    config.SAVE_PATH_WIN = new_path
    config.SAVE_PATH_UNIX = new_path_unix

    print()
    print(f"  {green('?????')}")
    print(f"  Windows: {new_path}")
    print(f"  Unix:    {new_path_unix}")
    print()
    print("  ????????????????????????????")
    print("  ????????????????m????????")


def do_migrate_path():
    """??????????? qB ???"""
    import config
    print_header("???? & ?? qB")

    print(f"  ?? Windows ??: {config.SAVE_PATH_WIN}")
    print(f"  ?? Unix ??:    {config.SAVE_PATH_UNIX}")
    print()

    new_path = input("  ?????????? F:\??\2026.07?: ").strip()
    if not new_path:
        print("  ????")
        return

    new_path_unix = new_path.replace("\\", "/")
    old_path = config.SAVE_PATH_WIN
    old_path_unix = config.SAVE_PATH_UNIX

    print()
    print(f"  ???: {old_path}")
    print(f"  ???: {new_path}")
    print()

    # ?? ?? 1: ?????? ??
    migrate_files = False
    if os.path.isdir(old_path):
        print(f"  ????????: {old_path}")
        migrate_files = input("  ?????????[Y/n] ").strip().lower() != "n"
    else:
        print(f"  ??????????????")

    if migrate_files:
        print(f"  ??????...")
        os.makedirs(new_path, exist_ok=True)
        moved = 0
        skipped = 0
        for item in os.listdir(old_path):
            src = os.path.join(old_path, item)
            dst = os.path.join(new_path, item)
            if os.path.exists(dst):
                skipped += 1
                continue
            try:
                import shutil
                shutil.move(src, dst)
                moved += 1
            except Exception as e:
                print(f"    ???? {item}: {e}")
        print(f"  ??????: ?? {moved} ?, ?? {skipped} ??????")
    print()

    # ?? ?? 2: ?? qB RSS ???? ??
    print("  ???? qBittorrent...")
    client = QBittorrentClient()
    if not client.login():
        print("  ?????????? config?")
    else:
        print("  ?????")
        print()

        # ??????
        print("  [1/2] ?? RSS ????...")
        result = client.update_rules_save_path(old_path, new_path)
        for line in result["details"]:
            print(line)
        print(f"  ????: ?? {result['updated']}, ?? {result['failed']}")
        print()

        # ???? torrent ??
        print("  [2/2] ???? torrent ????...")
        torrents = client.get_all_torrents()
        matching = []
        for t in torrents:
            sp = t.get("save_path", "")
            if old_path in sp or old_path_unix in sp:
                matching.append(t)

        if matching:
            print(f"  ?? {len(matching)} ???? torrent?????...")
            hashes = [t["hash"] for t in matching]
            ok = client.set_torrent_location(hashes, new_path_unix)
            print(f"  torrent ????: {ok}/{len(hashes)} ??")
        else:
            print("  ???????? torrent?")

    # ?? ?? 3: ???? config ??
    print()
    print("  [3/3] ???? config.py...")
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = f.read()

    cfg = re.sub(
        r'SAVE_PATH_WIN\s*=\s*r?"[^"]*"',
        f'SAVE_PATH_WIN = r"{new_path}"',
        cfg
    )
    cfg = re.sub(
        r'SAVE_PATH_UNIX\s*=\s*"[^"]*"',
        f'SAVE_PATH_UNIX = "{new_path_unix}"',
        cfg
    )

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(cfg)

    config.SAVE_PATH_WIN = new_path
    config.SAVE_PATH_UNIX = new_path_unix

    print(f"  {green('?????')}")
    print(f"  ????: {'???' if migrate_files else '???'}")
    print(f"  qB ??: ???")
    print(f"  ?? config: ???")


def do_sync():
    """从 qBittorrent 同步规则到本地。"""
    print_header("从 qB 同步规则")

    # 步骤1: 连接并查看 qB 规则
    print("  正在连接 qBittorrent...")
    client = QBittorrentClient()
    if not client.login():
        print(f"  {red('连接失败！请检查 qBittorrent 是否运行中。')}")
        return
    print(f"  {green('连接成功！')}")

    print("\n  正在读取 qB 中的规则...")
    qb_rules = client.get_qb_rules()
    if not qb_rules:
        print(f"  {yellow('qB 中没有规则。')}")
        return

    print(f"\n  qB 中共 {len(qb_rules)} 条规则：")
    for i, (name, data) in enumerate(sorted(qb_rules.items()), 1):
        enabled = data.get("enabled", False) if isinstance(data, dict) else False
        print(f"    {i:2d}. [{'ON' if enabled else 'OFF'}] {name}")

    # 步骤2: 确认是否同步
    print()
    if not prompt_yes_no("  是否同步这些规则到本地？", default="y"):
        print("  已取消。")
        return

    # 步骤3: 选择覆盖还是追加
    local_rules = load_rules()
    if local_rules:
        print(f"\n  本地已有 {len(local_rules)} 条规则。")
        print(f"  [1] 追加  - 保留本地规则，新增 qB 中的规则")
        print(f"  [2] 覆盖  - 用 qB 规则完全替换本地规则")
        mode_choice = prompt_int("  请选择 [1/2]: ", 1, 2)
        mode = "overwrite" if mode_choice == 2 else "append"
    else:
        print(f"\n  本地无规则，直接导入。")
        mode = "append"

    # 步骤4: 执行同步
    print("\n  正在同步...")
    result = client.sync_rules_to_local(RULES_FILE, mode=mode)

    # 报告
    print_header("同步结果")
    if mode == "overwrite":
        print(f"  模式: 覆盖")
        print(f"  本地规则已替换为 qB 中的 {result['total']} 条规则")
    else:
        print(f"  模式: 追加")
        print(f"  新增: {result['synced']} 条")
        print(f"  已更新状态: {result['updated']} 条")

    print(f"  本地规则数: {len(result['rules'])}")
    print(f"\n  {green('同步完成！')}")

    print(f"\n  规则列表:")
    for name in sorted(result["rules"].keys()):
        enabled = result["rules"][name].get("enabled", False)
        print(f"    [{'ON' if enabled else 'OFF'}] {name}")



def print_main_menu():
    clear()
    print(cyan("╔══════════════════════════════════════════════════════════╗"))
    print(cyan("║") + bold("        Bangumi 自动分类工具") + f"  v{VERSION}" + " " * 16 + cyan("║"))
    print(cyan("╚══════════════════════════════════════════════════════════╝"))
    print()
    rules = load_rules()
    if rules:
        enabled = sum(1 for r in rules.values() if r.get("enabled", True))
        print(f"  当前规则: {len(rules)} 条 (已启用 {enabled})")
    else:
        print(f"  {yellow('当前无规则')}")
    print()
    print_menu_item(1, "查看状态", "显示当前所有规则")
    print_menu_item(2, "刷新 RSS", "连接 qBittorrent 刷新 RSS")
    print_menu_item(3, "分析规则", "匹配现有规则 vs RSS，输出命中/未命中/未覆盖")
    print_menu_item(4, "查看差异", "查看 RSS 中新增的、尚未有规则覆盖的番剧")
    print_menu_item(5, "生成规则", "交互式生成新规则（核心功能）")
    print_menu_item(6, "导入规则", "将规则导入 qBittorrent")
    print_menu_item(7, "启用下载", "启用规则并开始自动下载")
    print_menu_item(8, "qB 状态", "查看 qBittorrent 规则、乱码检查")
    print_menu_item(9, "一键自动化", "识别差异→生成→导入→下载")
    print_menu_item(10, "启动 WebUI", "在浏览器中打开 Web 控制台")
    print()
    print_menu_item(0, "从 qB 同步", "从 qBittorrent 同步规则到本地")
    print()
    print(f"  " + bold("p") + " 修改保存路径    修改番剧下载保存路径")
    print(f"  " + bold("m") + " \u8fc1\u79fb\u8def\u5f84      \u8fc1\u79fb\u5df2\u4e0b\u8f7d\u6587\u4ef6\u5e76\u66f4\u65b0 qB \u8def\u5f84")
    print(f"  输入 q 退出")
    print()


# ── 主循环 ──────────────────────────────────────────────

def do_start_webui():
    print("\n  \u6b63\u5728\u542f\u52a8 WebUI...\n")
    print(f"  \u6d4f\u89c8\u5668\u8bbf\u95ee: {cyan('http://localhost:8080')}")
    print(f"  \u6309 Ctrl+C \u505c\u6b62\u670d\u52a1\n")
    try:
        import uvicorn
        from webapp.app import app
        uvicorn.run(app, host="0.0.0.0", port=8080)
    except KeyboardInterrupt:
        print("\n  WebUI \u5df2\u505c\u6b62")
    except Exception as e:
        print(f"  \u542f\u52a8\u5931\u8d25: {e}")


def main():
    while True:
        print_main_menu()
        raw = input("请选择功能 [0-9, p, m, q=退出]: ").strip().lower()
        if raw in ("q", "quit", "exit"):
            print("\n  再见！")
            break
        if raw == "p":
            do_change_path()
            pause()
            continue
        if raw == "m":
            do_migrate_path()
            pause()
            continue
        try:
            choice = int(raw)
        except ValueError:
            continue
        if choice < 0 or choice > 9:
            continue
        elif choice == 0:
            do_sync()
            pause()
        elif choice == 1:
            do_status()
            pause()
        elif choice == 2:
            do_refresh_rss()
            pause()
        elif choice == 3:
            do_analyze()
            pause()
        elif choice == 4:
            do_diff()
            pause()
        elif choice == 5:
            do_generate()
            pause()
        elif choice == 6:
            do_import()
            pause()
        elif choice == 7:
            do_enable_and_download()
            pause()
        elif choice == 8:
            do_import_status()
            pause()
        elif choice == 9:
            do_auto()
            pause()
        elif choice == 10:
            do_start_webui()


if __name__ == "__main__":
    # exe: default WebUI; add --cli for terminal menu
    if getattr(sys, "frozen", False):
        if "--cli" in sys.argv:
            main()
        else:
            do_start_webui()
    else:
        if "--webui" in sys.argv:
            do_start_webui()
        else:
            main()
