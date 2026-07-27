import sys
import os
import json
import asyncio
import re
import time
import shutil
import queue
import threading
from typing import Optional
from pathlib import Path

# Add parent dir to path so we can import existing modules
TOOL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOL_DIR))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Bangumi Tool")

# -- Log queue for SSE --
_log_queue: queue.Queue = queue.Queue()

def log(msg: str, level: str = "info"):
    """Put a log entry into the SSE queue."""
    entry = {"time": time.strftime("%H:%M:%S"), "msg": msg, "level": level}
    _log_queue.put(entry)

# -- Lazy imports (deferred to avoid circular) --
_client = None

def get_client():
    global _client
    if _client is None:
        from qbittorrent_api import QBittorrentClient
        _client = QBittorrentClient()
    return _client

def import_config():
    import importlib, importlib.util
    config_path = TOOL_DIR / "config.py"
    spec = importlib.util.spec_from_file_location("config", str(config_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _update_config_path(new_path: str):
    """Update SAVE_PATH_WIN and SAVE_PATH_UNIX in config.py.
    Uses str.replace() instead of re.sub() to avoid backslash escaping issues.
    """
    bs = chr(92)
    qt = chr(34)
    escaped_win = new_path.replace(bs, bs + bs)
    new_path_unix = new_path.replace(bs, "/")
    config_path = TOOL_DIR / "config.py"
    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    win_line = "SAVE_PATH_WIN = " + qt + escaped_win + qt + "   # Windows path" + chr(10)
    unix_line = "SAVE_PATH_UNIX = " + qt + new_path_unix + qt + "   # qB torrentParams path" + chr(10)
    new_lines = []
    for line in lines:
        if line.strip().startswith("SAVE_PATH_WIN"):
            new_lines.append(win_line)
        elif line.strip().startswith("SAVE_PATH_UNIX"):
            new_lines.append(unix_line)
        else:
            new_lines.append(line)
    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

# -- API: Config --
CONFIG_FIELDS = [
    {"key": "RSS_URL", "label": "RSS URL", "type": "text"},
    {"key": "QB_BASE_URL", "label": "qBittorrent WebUI URL", "type": "text"},
    {"key": "QB_USERNAME", "label": "qB Username", "type": "text"},
    {"key": "QB_PASSWORD", "label": "qB Password", "type": "password"},
    {"key": "DEFAULT_MUST_NOT", "label": "默认排除词", "type": "text"},
]

@app.get("/api/config")
def get_config():
    config = import_config()
    values = {}
    for f in CONFIG_FIELDS:
        val = getattr(config, f["key"], "")
        values[f["key"]] = val
    return {"fields": CONFIG_FIELDS, "values": values}

@app.post("/api/config")
def update_config(body: dict):
    updates = body.get("updates", {})
    if not updates:
        raise HTTPException(400, "No updates provided")

    config_path = TOOL_DIR / "config.py"
    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    bs = chr(92)
    qt = chr(34)
    updated = []
    new_lines = []
    for line in lines:
        replaced = False
        for key, val in updates.items():
            if line.strip().startswith(key + " ="):
                # Escape backslashes for Windows paths
                escaped = val.replace(bs, bs + bs)
                new_lines.append(key + " = " + qt + escaped + qt + chr(10))
                replaced = True
                updated.append(key)
                break
        if not replaced:
            new_lines.append(line)

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    log("Config updated: " + ", ".join(updated), "ok")
    return {"ok": True, "updated": updated}

# -- API: Status --
# -- API: Status --
@app.get("/api/status")
def get_status():
    config = import_config()
    from utils import load_rules
    rules = load_rules()
    enabled = sum(1 for r in rules.values() if r.get("enabled", True))
    return {
        "rule_count": len(rules),
        "enabled_count": enabled,
        "qb_url": config.QB_BASE_URL,
        "save_path": config.SAVE_PATH_WIN,
        "rss_url": config.RSS_URL[:60] + "...",
    }

# -- API: Rules --
@app.get("/api/rules")
def get_rules():
    from utils import load_rules
    rules = load_rules()
    result = []
    for name, data in rules.items():
        result.append({
            "name": name,
            "enabled": data.get("enabled", True),
            "mustContain": data.get("mustContain", ""),
            "mustNotContain": data.get("mustNotContain", ""),
            "savePath": data.get("savePath", ""),
            "useRegex": data.get("useRegex", False),
        })
    return {"rules": result, "total": len(result)}

@app.post("/api/rules/toggle/{name}")
def toggle_rule(name: str):
    from utils import load_rules, save_rules
    rules = load_rules()
    if name not in rules:
        raise HTTPException(404, "Rule not found")
    current = rules[name].get("enabled", True)
    rules[name]["enabled"] = not current
    save_rules(rules)
    return {"name": name, "enabled": not current}

@app.delete("/api/rules/{name}")
def delete_rule(name: str):
    from utils import load_rules, save_rules
    rules = load_rules()
    if name not in rules:
        raise HTTPException(404, "Rule not found")
    del rules[name]
    save_rules(rules)
    return {"ok": True}

# -- API: RSS --
@app.post("/api/rss/refresh")
def refresh_rss():
    log("Connecting to qBittorrent...", "info")
    client = get_client()
    if not client.login():
        log("Connection failed", "error")
        return {"ok": False, "msg": "Connection failed"}
    log("Connected", "ok")
    log("Refreshing RSS...", "info")
    count = client.refresh_rss()
    log(f"Refreshed {count} items", "ok")
    return {"ok": True, "refreshed": count}

@app.get("/api/rss/analyze")
def analyze_rss():
    config = import_config()
    from utils import load_rules
    from rss_parser import fetch_rss, extract_anime_name
    from rule_engine import validate_all_rules, find_uncovered

    rules = load_rules()
    log("Refreshing RSS...", "info")
    items = fetch_rss()
    log(f"RSS ??: {len(items)} ?", "info")

    results = validate_all_rules(rules, items)
    uncovered = find_uncovered(items, rules)

    hit = sum(1 for r in results if r.hit_count > 0)
    miss = sum(1 for r in results if r.hit_count == 0)

    hit_rules = []
    for r in sorted(results, key=lambda x: -x.hit_count):
        if r.hit_count > 0:
            hit_rules.append({"name": r.rule_name, "count": r.hit_count, "example": r.hit_titles[0] if r.hit_titles else ""})

    uncovered_list = []
    for u in uncovered:
        uncovered_list.append({
            "anime": u.anime_name,
            "source": u.source,
            "count": len(u.titles),
            "episodes": sorted(u.episodes),
            "example": u.titles[0] if u.titles else "",
        })

    log(f"Result: hit {hit}  miss {miss}  uncovered {len(uncovered)}", "ok" if miss == 0 and len(uncovered) == 0 else "warn")

    return {
        "hit": hit, "miss": miss, "uncovered_count": len(uncovered),
        "hit_rules": hit_rules, "uncovered": uncovered_list,
    }

@app.get("/api/rss/diff")
def rss_diff():
    from utils import load_rules
    from rss_parser import fetch_rss
    from rule_engine import find_uncovered

    rules = load_rules()
    items = fetch_rss()
    uncovered = find_uncovered(items, rules)
    result = []
    for u in uncovered:
        result.append({
            "anime": u.anime_name, "source": u.source,
            "count": len(u.titles), "episodes": sorted(u.episodes),
            "example": u.titles[0] if u.titles else "",
        })
    return {"uncovered": result, "total": len(result)}

@app.get("/api/rss/items")
def rss_items():
    from rss_parser import fetch_rss
    items = fetch_rss()
    return {"items": [{"title": i.title, "link": i.link} for i in items], "total": len(items)}

# -- API: Generate Rules --
@app.post("/api/rules/generate")
def generate_rules():
    from utils import load_rules, save_rules
    from rss_parser import fetch_rss
    from rule_engine import find_uncovered
    from rule_generator import generate_rules_for_uncovered, print_generation_report

    rules = load_rules()
    items = fetch_rss()
    uncovered = find_uncovered(items, rules)

    if not uncovered:
        return {"ok": True, "generated": 0, "msg": "No rules to import"}

    # For API mode: auto-select all sources for all uncovered
    user_selected = {}
    for u in uncovered:
        from utils import normalize_name
        anime = normalize_name(u.anime_name)
        if u.source in {"ABEMA", "Baha", "B-Global", "CR"}:
            user_selected.setdefault(anime, []).append(u.source)

    new_rules = generate_rules_for_uncovered(uncovered, user_selected)

    # Validate
    from rule_engine import match_titles
    validated = []
    for name, data in new_rules.items():
        hits = match_titles([i.title for i in items], data["mustContain"], data["mustNotContain"], data.get("useRegex", False))
        status = "ok" if hits else "miss"
        validated.append({"name": name, "status": status, "hits": len(hits)})

    added = 0
    for name, data in new_rules.items():
        if name not in rules:
            rules[name] = data
            added += 1
    save_rules(rules)

    log(f"Generated {len(new_rules)} rules, {added} new", "ok")
    return {"ok": True, "generated": len(new_rules), "added": added, "validated": validated}

# -- API: Import to qB --
@app.post("/api/rules/import")
def import_rules_to_qb():
    from utils import load_rules
    config = import_config()

    rules = load_rules()
    if not rules:
        return {"ok": False, "msg": "No rules to import"}

    log("Connecting to qBittorrent...", "info")
    client = get_client()
    if not client.login():
        log("Connection failed", "error")
        return {"ok": False, "msg": "Connection failed"}

    # Check RSS feed
    log("Checking RSS feed...", "info")
    client.ensure_rss_feed(config.RSS_URL, "Bangumi")

    # Import rules
    log(f"Importing {len(rules)} rules...", "info")
    result = client.import_rules(rules)
    log(f"Imported: {len(result['success'])} ok, {len(result['failed'])} failed",
        "ok" if not result["failed"] else "warn")

    return {"ok": True, "success": len(result["success"]), "failed": len(result["failed"])}

# -- API: Enable & Download --
@app.post("/api/qb/enable")
def enable_rules():
    from utils import load_rules
    config = import_config()

    rules = load_rules()
    enabled_rules = {n: d for n, d in rules.items() if d.get("enabled", True)}

    log("Connecting to qBittorrent...", "info")
    client = get_client()
    if not client.login():
        return {"ok": False, "msg": "Connection failed"}

    log(f"Enabling {len(enabled_rules)} rules...", "info")
    result = client.enable_rules(list(enabled_rules.keys()))
    log(f"Enabled {len(result.get('enabled', []))} rules", "ok")

    return {"ok": True, "enabled": len(result.get("enabled", [])), "failed": len(result.get("failed", []))}

# -- API: qB Status --
@app.get("/api/qb/status")
def qb_status():
    client = get_client()
    if not client.login():
        return {"connected": False}

    rules = client.get_rules()
    torrents = client.get_all_torrents()
    return {
        "connected": True,
        "rule_count": len(rules) if rules else 0,
        "torrent_count": len(torrents) if torrents else 0,
    }

# -- API: Sync from qB --
@app.post("/api/qb/sync")
def sync_from_qb():
    from utils import RULES_FILE
    client = get_client()
    if not client.login():
        return {"ok": False, "msg": "Connection failed"}

    log("Reading qB rules...", "info")
    result = client.sync_rules_to_local(str(RULES_FILE), mode="overwrite")
    log(f"Synced: {result['total']} rules", "ok")
    return {"ok": True, "total": result["total"], "synced": result["synced"]}

# -- API: Migrate Path --
@app.get("/api/fs/search")
def search_directory(name: str = "", base: str = ""):
    """Search for a directory by name under base path."""
    import string
    if not name:
        return {"results": []}

    results = []
    search_bases = [base] if base else []
    if not search_bases:
        # Search common locations
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                search_bases.append(drive)

    for base_path in search_bases:
        if len(results) >= 10:
            break
        try:
            for root, dirs, files in os.walk(base_path):
                if len(results) >= 10:
                    break
                # Skip hidden and system dirs
                dirs[:] = [d for d in dirs if not d.startswith(('.', '$', 'System', 'Windows'))]
                for d in dirs:
                    if name.lower() in d.lower():
                        full = os.path.join(root, d)
                        results.append({"name": d, "path": full})
                        if len(results) >= 10:
                            break
        except PermissionError:
            continue
    return {"results": results}


@app.get("/api/fs/browse")
def browse_directory(path: str = ""):
    """Browse directories at given path, return folder list."""
    import string
    if not path:
        # Return drive list on Windows
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                drives.append({"name": f"{letter}:", "path": drive, "is_dir": True})
        return {"current": "", "dirs": drives}

    if not os.path.isdir(path):
        return {"current": path, "dirs": [], "error": "Path not found"}

    dirs = []
    try:
        for item in sorted(os.listdir(path)):
            full = os.path.join(path, item)
            if os.path.isdir(full) and not item.startswith('.'):
                dirs.append({"name": item, "path": full, "is_dir": True})
    except PermissionError:
        return {"current": path, "dirs": [], "error": "Permission denied"}

    return {"current": path, "dirs": dirs}


@app.post("/api/qb/change-path")
def change_path_only(body: dict):
    """Change save path for future downloads only (no torrent migration)."""
    new_path = body.get("new_path", "")
    if not new_path:
        raise HTTPException(400, "new_path required")
    config = import_config()
    old_path = config.SAVE_PATH_WIN
    old_path_unix = config.SAVE_PATH_UNIX
    new_path_unix = new_path.replace("\\", "/")
    log(f"Changing path: {old_path} -> {new_path}", "info")
    from utils import load_rules, save_rules
    rules = load_rules()
    updated = 0
    for name, data in rules.items():
        sp = data.get("savePath", "")
        if old_path in sp or old_path_unix in sp:
            new_sp = sp.replace(old_path, new_path).replace(old_path_unix, new_path_unix)
            data["savePath"] = new_sp
            updated += 1
    save_rules(rules)
    log(f"Rules updated: {updated}", "ok")
    _update_config_path(new_path)
    log("Config updated", "ok")
    return {"ok": True, "rules_updated": updated, "torrents_moved": 0}

@app.post("/api/qb/migrate")
def migrate_path(body: dict):
    new_path = body.get("new_path", "")
    if not new_path:
        raise HTTPException(400, "new_path required")

    config = import_config()
    new_path_unix = new_path.replace("\\", "/")

    log("Migration target: " + new_path, "info")

    # Step 1: Detect actual files on disk
    # Read qB rules to find where files actually are
    client = get_client()
    if not client.login():
        return {"ok": False, "msg": "Connection failed"}

    qb_rules = client.get_rules()
    actual_old = None
    if qb_rules and isinstance(qb_rules, dict):
        save_paths = []
        for rname, rdata in qb_rules.items():
            if not isinstance(rdata, dict):
                continue
            sp = rdata.get("savePath", "")
            if sp:
                save_paths.append(sp)
            tp = rdata.get("torrentParams", {})
            if isinstance(tp, dict) and tp.get("save_path", ""):
                save_paths.append(tp["save_path"])
        if save_paths:
            # Find common directory prefix (the actual base on disk)
            normalized = [p.replace("\\", "/").rstrip("/") for p in save_paths]
            split_paths = [p.split("/") for p in normalized]
            common = []
            for segments in zip(*split_paths):
                if len(set(segments)) == 1:
                    common.append(segments[0])
                else:
                    break
            if common:
                detected = "/".join(common).replace("/", "\\")
                if os.path.isdir(detected):
                    actual_old = detected
                    log("Detected actual path on disk: " + detected, "info")

    # Fallback: use config path if detected path not found
    if not actual_old:
        actual_old = config.SAVE_PATH_WIN
        log("Using config path as source: " + actual_old, "info")

    # Step 2: Move files on disk
    files_moved = 0
    files_failed = 0
    if os.path.isdir(actual_old):
        if not os.path.isdir(new_path):
            # Target does not exist -> move the whole folder
            try:
                shutil.move(actual_old, new_path)
                files_moved = 1
                log("Moved entire folder: " + actual_old + " -> " + new_path, "ok")
            except Exception as e:
                files_failed = 1
                log("Failed to move folder: " + str(e), "error")
        else:
            # Target exists -> move subfolders one by one
            for item in os.listdir(actual_old):
                src = os.path.join(actual_old, item)
                dst = os.path.join(new_path, item)
                if not os.path.isdir(src):
                    continue
                if os.path.exists(dst):
                    log("Skip exists: " + item, "warn")
                    continue
                try:
                    shutil.move(src, dst)
                    files_moved += 1
                    log("Moved: " + item, "ok")
                except Exception as e:
                    files_failed += 1
                    log("Failed to move " + item + ": " + str(e), "error")
            log("Files moved: " + str(files_moved) + ", failed: " + str(files_failed),
                "ok" if files_failed == 0 else "warn")
    else:
        log("Source path not found on disk: " + actual_old, "warn")

    # Step 3: Update all qB rules -> new_path
    result = {"updated": 0, "failed": 0}
    if qb_rules and isinstance(qb_rules, dict):
        updated_count = 0
        for rname, rdata in qb_rules.items():
            if not isinstance(rdata, dict):
                continue
            sp = rdata.get("savePath", "")
            if not sp:
                continue
            # Build new savePath: replace old base with new_path
            sp_unix = sp.replace("\\", "/")
            actual_old_unix = actual_old.replace("\\", "/")
            new_sp = None
            if actual_old in sp:
                new_sp = sp.replace(actual_old, new_path)
            elif actual_old_unix in sp_unix:
                new_sp = sp_unix.replace(actual_old_unix, new_path_unix).replace("/", "\\")
            if new_sp is None:
                continue
            rdata["savePath"] = new_sp
            tp = rdata.get("torrentParams", {})
            if isinstance(tp, dict) and tp.get("save_path", ""):
                tsp = tp["save_path"]
                if actual_old_unix in tsp:
                    tp["save_path"] = tsp.replace(actual_old_unix, new_path_unix)
            ok = client.set_rule(rname, rdata)
            if ok:
                updated_count += 1
                log("  Rule OK: " + rname, "ok")
            else:
                log("  Rule FAIL: " + rname, "error")
        result["updated"] = updated_count
    log("Rules updated: " + str(result["updated"]), "ok")

    # Step 4: Update torrent locations
    torrents = client.get_all_torrents()
    actual_old_unix = actual_old.replace("\\", "/")
    matching = [t for t in torrents if actual_old in t.get("save_path", "") or actual_old_unix in t.get("save_path", "")]
    torrent_ok = 0
    if matching:
        torrent_ok = client.set_torrent_location([t["hash"] for t in matching], new_path_unix)
        log("Torrents updated: " + str(torrent_ok) + "/" + str(len(matching)), "ok")

    # Step 5: Update config.py
    _update_config_path(new_path)

    log("Migration complete", "ok")
    return {
        "ok": True,
        "files_moved": files_moved,
        "files_failed": files_failed,
        "rules_updated": result["updated"],
        "torrents_moved": torrent_ok,
    }




# -- API: One-click Auto --
@app.post("/api/auto/run")
def auto_run():
    from utils import load_rules, save_rules
    from rss_parser import fetch_rss
    from rule_engine import find_uncovered, match_titles
    from rule_generator import generate_rules_for_uncovered
    from rule_generator import need_multi_select
    config = import_config()

    steps = []

    # Step 1: Refresh RSS
    log("?? 1/4: ?? RSS", "info")
    client = get_client()
    if not client.login():
        return {"ok": False, "msg": "Connection failed"}
    client.refresh_rss()
    log("RSS refreshed", "ok")

    # Step 2: Diff
    log("Step 2/4: Detecting diff", "info")
    rules = load_rules()
    items = fetch_rss()
    uncovered = find_uncovered(items, rules)
    log(f"???: {len(uncovered)} ?", "ok" if len(uncovered) == 0 else "warn")

    # Step 3: Generate
    log("Step 3/4: Generating rules", "info")
    if uncovered:
        user_selected = {}
        for u in uncovered:
            from utils import normalize_name
            anime = normalize_name(u.anime_name)
            user_selected.setdefault(anime, []).append(u.source)

        new_rules = generate_rules_for_uncovered(uncovered, user_selected)
        for name, data in new_rules.items():
            if name not in rules:
                rules[name] = data
        save_rules(rules)
        log(f"Generated {len(new_rules)} rules", "ok")
    else:
        new_rules = {}
        log("No new rules needed", "ok")

    # Step 4: Import & Enable
    log("Step 4/4: Importing and enabling", "info")
    client.ensure_rss_feed(config.RSS_URL, "Bangumi")
    all_rules = load_rules()
    client.import_rules(all_rules)
    enabled = {n: d for n, d in all_rules.items() if d.get("enabled", True)}
    client.enable_rules(list(enabled.keys()))
    log(f"{len(all_rules)} rules total, {len(enabled)} enabled", "ok")

    return {
        "ok": True,
        "rss_count": len(items),
        "uncovered": len(uncovered),
        "generated": len(new_rules),
        "total_rules": len(all_rules),
        "enabled": len(enabled),
    }

# -- SSE: Real-time Logs --
@app.get("/api/logs/stream")
async def log_stream():
    async def event_generator():
        while True:
            try:
                entry = _log_queue.get_nowait()
                yield {"event": "log", "data": json.dumps(entry, ensure_ascii=False)}
            except queue.Empty:
                await asyncio.sleep(0.3)
    return EventSourceResponse(event_generator())

# -- Serve static files --
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
def index():
    html_path = static_dir / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
