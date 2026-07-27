import os
"""固定配置：RSS、qBittorrent、路径等常量"""

# ── RSS 源 ──────────────────────────────────────────────
RSS_URL = "https://mikanime.tv/RSS/MyBangumi?token=J2mLlzuklGqvYMRzhzCF%2bw%3d%3d"

# ── qBittorrent WebUI ──────────────────────────────────
QB_BASE_URL = "http://localhost:6079/"
QB_USERNAME = "admin"
QB_PASSWORD = ""

# ── 规则文件目录 ─────────────────────────────────────────
RULE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 下载根路径 ──────────────────────────────────────────
SAVE_PATH_WIN = "E:\\测试2"   # Windows path
SAVE_PATH_UNIX = "E:/测试2"   # qB torrentParams path

# ── 来源集合（需要弹多选框让用户勾选的） ──────────────────
MULTI_SELECT_SOURCES = {"ABEMA", "Baha", "B-Global", "CR"}

# ── 黒ネズミたち 映射：标题中含该组名时，规则名只保留源后缀 ─
KURO_SOURCE_MAP = {
    "ABEMA": "ABEMA",
    "Baha":  "Baha",
    "B-Global": "B-Global",
    "CR":    "CR",
}

# ── ANi 映射：标题含 ANi 时，规则名后缀固定为 Baha ───────
ANI_SUFFIX = "Baha"

# ── 已固定的译名字典 ─────────────────────────────────────
FIXED_TRANSLATIONS = {
    "上伊那牡丹，酒醉身姿似百合花般": "上伊那牡丹，醉姿如百合",
    "上伊那牡丹，醉酒身姿如百合般":  "上伊那牡丹，醉姿如百合",
}

# ── 默认排除词（各规则共用的） ──────────────────────────
DEFAULT_MUST_NOT = "720|ABEMA"

# ── qB API 路径 ─────────────────────────────────────────
QB_API = {
    "login":    "/api/v2/auth/login",
    "rss_items": "/api/v2/rss/items",
    "rss_rules": "/api/v2/rss/rules",
    "rss_set_rule": "/api/v2/rss/setRule",
    "rss_refresh":  "/api/v2/rss/refreshItem",
    "rss_mark_read": "/api/v2/rss/markAsRead",
    "rss_add_feed": "/api/v2/rss/addFeed",
    "torrents_resume": "/api/v2/torrents/resume",
    "torrents_info": "/api/v2/torrents/info",
}
