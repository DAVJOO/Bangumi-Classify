import os
"""Configuration template - copy to config.py and fill in your values."""

# RSS source
RSS_URL = "https://mikanani.kas.pub/RSS/MyBangumi?token=YOUR_TOKEN_HERE"

# qBittorrent WebUI
QB_BASE_URL = "http://localhost:8080/"
QB_USERNAME = "admin"
QB_PASSWORD = ""

# Rule file directory
RULE_DIR = os.path.dirname(os.path.abspath(__file__))

# Download root path
SAVE_PATH_WIN = r"E:\Anime\2026.07.01"   # Windows path
SAVE_PATH_UNIX = "E:/Anime/2026.07.01"     # qB torrentParams path

# Sources requiring multi-select
MULTI_SELECT_SOURCES = {"ABEMA", "Baha", "B-Global", "CR"}

# Kuro Nemuri group mapping
KURO_SOURCE_MAP = {
    "ABEMA": "ABEMA",
    "Baha":  "Baha",
    "B-Global": "B-Global",
    "CR":    "CR",
}

# ANi suffix
ANI_SUFFIX = "Baha"

# Fixed name translations
FIXED_TRANSLATIONS = {}

# Default exclude pattern
DEFAULT_MUST_NOT = "720|ABEMA"

# qB API paths
QB_API = {
    "login":        "/api/v2/auth/login",
    "rss_items":    "/api/v2/rss/items",
    "rss_rules":    "/api/v2/rss/rules",
    "rss_set_rule": "/api/v2/rss/setRule",
    "rss_refresh":  "/api/v2/rss/refreshItem",
    "rss_mark_read": "/api/v2/rss/markAsRead",
    "rss_add_feed": "/api/v2/rss/addFeed",
    "torrents_resume": "/api/v2/torrents/resume",
    "torrents_info": "/api/v2/torrents/info",
}
