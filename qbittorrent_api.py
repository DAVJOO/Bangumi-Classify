import os
"""qBittorrent WebUI API 交互模块"""

import json
import urllib.request
import urllib.parse
import ipaddress
import socket
from urllib.parse import urlparse
from config import QB_BASE_URL, QB_USERNAME, QB_PASSWORD, QB_API


def _is_local_address(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback
    except ValueError:
        try:
            resolved = socket.gethostbyname(hostname)
            return _is_local_address(f"http://{resolved}/")
        except Exception:
            return False


def _urlopen_bypass_proxy(req, timeout=30):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if _is_local_address(url):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


class QBittorrentClient:
    """qBittorrent WebUI API 客户端"""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or QB_BASE_URL).rstrip("/")
        self.cookie = None

    # ── 认证 ──────────────────────────────────────────────

    def login(self) -> bool:
        """登录并保存会话 cookie。"""
        url = self.base_url + QB_API["login"]
        data = urllib.parse.urlencode({
            "username": QB_USERNAME,
            "password": QB_PASSWORD,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        try:
            resp = _urlopen_bypass_proxy(req, timeout=20)
            # 从 Set-Cookie 中提取 SID
            cookies = resp.headers.get_all("Set-Cookie") or []
            for c in cookies:
                if "SID=" in c:
                    self.cookie = c.split(";")[0]
                    return True
            # 有的版本返回 OK 就算成功
            return resp.read().decode("utf-8").strip() == "Ok."
        except Exception as e:
            print(f"[qB] 登录失败: {e}")
            return False

    def _build_request(self, path: str, data: bytes | None = None,
                       method: str = "GET") -> urllib.request.Request:
        """构建带认证的请求。"""
        url = self.base_url + path
        headers = {
            "User-Agent": "BangumiTool/1.0",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        return urllib.request.Request(url, data=data, headers=headers, method=method)

    def _request_json(self, path: str, data: bytes | None = None,
                      method: str = "GET") -> dict | list | None:
        """发送请求并返回解析后的 JSON（UTF-8 字节解码）。"""
        req = self._build_request(path, data, method)
        try:
            resp = _urlopen_bypass_proxy(req, timeout=30)
            raw_bytes = resp.read()
            # 关键：先保存为字节，再按 UTF-8 解码
            text = raw_bytes.decode("utf-8")
            return json.loads(text)
        except Exception as e:
            print(f"[qB] 请求失败 {path}: {e}")
            return None

    # ── RSS 规则操作 ─────────────────────────────────────

    def get_rules(self) -> dict | None:
        """获取当前所有 RSS 规则（UTF-8 解码）。"""
        return self._request_json(QB_API["rss_rules"])

    def set_rule(self, rule_name: str, rule_def: dict) -> bool:
        """
        设置/更新一条 RSS 规则。
        强制使用 UTF-8 编码提交，避免乱码。
        """
        # ruleDef 需要 JSON 字符串
        rule_def_json = json.dumps(rule_def, ensure_ascii=False)
        data = urllib.parse.urlencode({
            "ruleName": rule_name,
            "ruleDef": rule_def_json,
        }).encode("utf-8")
        req = self._build_request(QB_API["rss_set_rule"], data, "POST")
        try:
            resp = _urlopen_bypass_proxy(req, timeout=30)
            return resp.read().decode("utf-8").strip().lower() in ("ok.", "ok", "")
        except Exception as e:
            print(f"[qB] 设置规则失败 [{rule_name}]: {e}")
            return False

    def delete_rule(self, rule_name: str) -> bool:
        """删除一条 RSS 规则。"""
        data = urllib.parse.urlencode({"ruleName": rule_name}).encode("utf-8")
        req = self._build_request("/api/v2/rss/removeRule", data, "POST")
        try:
            resp = _urlopen_bypass_proxy(req, timeout=30)
            return True
        except Exception as e:
            print(f"[qB] 删除规则失败 [{rule_name}]: {e}")
            return False

    def clear_all_rules(self) -> int:
        """Delete all existing RSS rules from qBittorrent. Returns count deleted."""
        rules = self.get_rules()
        if not rules or not isinstance(rules, dict):
            return 0
        count = 0
        for name in rules:
            if self.delete_rule(name):
                count += 1
        return count

    def import_rules(self, rules: dict) -> dict:
        """
        Delete all old rules then import new ones to qBittorrent.
        Returns {"success": [...], "failed": [...]}
        """
        # Step 1: Clear all existing rules
        deleted = self.clear_all_rules()
        print(f"[qB] Cleared {deleted} old rules")

        # Step 2: Import new rules
        results = {"success": [], "failed": []}
        for rule_name, rule_def in rules.items():
            ok = self.set_rule(rule_name, rule_def)
            if ok:
                results["success"].append(rule_name)
            else:
                results["failed"].append(rule_name)
        return results

    # ── RSS 操作 ─────────────────────────────────────────


    def _get_feed_url(self, rss_tree: dict, target_path: str) -> str:
        """Get the URL for a given RSS feed path."""
        parts = target_path.strip("/").split("/")
        current = rss_tree
        for part in parts:
            if part in current and isinstance(current[part], dict):
                if "url" in current[part]:
                    return current[part]["url"]
                current = current[part].get("children", current[part])
        return ""

    def _remove_rss_item(self, item_path: str) -> bool:
        """Remove an RSS feed or folder by path."""
        data = urllib.parse.urlencode({"path": item_path}).encode("utf-8")
        req = self._build_request("/api/v2/rss/removeItem", data, "POST")
        try:
            _urlopen_bypass_proxy(req, timeout=30)
            return True
        except Exception as e:
            print(f"[qB] Failed to remove RSS item [{item_path}]: {e}")
            return False

    def _add_rss_feed(self, url: str, path: str = "") -> bool:
        """Add an RSS feed to qBittorrent."""
        params = {"url": url}
        if path:
            params["path"] = path
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = self._build_request(QB_API["rss_add_feed"], data, "POST")
        try:
            _urlopen_bypass_proxy(req, timeout=30)
            return True
        except Exception as e:
            print(f"[qB] Failed to add RSS feed: {e}")
            return False

    def refresh_rss(self, item_path: str = "") -> bool:
        """Delete and re-add RSS feeds to force fresh data, then refresh."""
        import time as _time

        rss_items = self.get_rss_items(with_data=False)
        if not rss_items:
            print("[qB] No RSS tree found, adding fresh feed")
            return self._add_rss_feed(RSS_URL, "Bangumi")

        feed_paths = self._collect_feed_paths(rss_items)
        if not feed_paths:
            print("[qB] RSS tree empty, adding fresh feed")
            return self._add_rss_feed(RSS_URL, "Bangumi")

        print(f"[qB] Re-adding {len(feed_paths)} RSS feeds for fresh data...")
        for path in feed_paths:
            # Get the URL before deleting
            feed_url = self._get_feed_url(rss_items, path)
            # Delete old feed
            self._remove_rss_item(path)
            _time.sleep(0.5)
            # Re-add with same URL
            if feed_url:
                self._add_rss_feed(feed_url, path)
            _time.sleep(1)

        # Final refresh
        for path in self._collect_feed_paths(self.get_rss_items(with_data=False) or {}):
            self._refresh_single(path)
        print("[qB] RSS refresh complete")
        return True

    def _refresh_single(self, item_path: str) -> bool:
        """刷新单个 RSS feed。"""
        data = urllib.parse.urlencode({"itemPath": item_path}).encode("utf-8")
        req = self._build_request(QB_API["rss_refresh"], data, "POST")
        try:
            _urlopen_bypass_proxy(req, timeout=30)
            return True
        except Exception as e:
            print(f"[qB] 刷新 RSS 失败 [{item_path}]: {e}")
            return False

    def _collect_feed_paths(self, rss_tree: dict, prefix: str = "") -> list[str]:
        """递归收集 RSS 树中所有叶子 feed 路径。"""
        paths = []
        for key, val in rss_tree.items():
            if isinstance(val, dict) and "url" in val:
                # 叶子节点：有 url 字段的就是 feed
                full_path = f"{prefix}/{key}" if prefix else key
                paths.append(full_path)
            elif isinstance(val, dict) and "children" in val:
                # 文件夹节点
                child_prefix = f"{prefix}/{key}" if prefix else key
                paths.extend(self._collect_feed_paths(val["children"], child_prefix))
            elif isinstance(val, dict):
                # 可能是文件夹但没有 children key
                child_prefix = f"{prefix}/{key}" if prefix else key
                # 尝试当作文件夹继续遍历
                paths.extend(self._collect_feed_paths(val, child_prefix))
        return paths

    def get_rss_items(self, with_data: bool = True) -> dict | None:
        """获取 RSS 条目（含数据）。"""
        path = QB_API["rss_items"]
        if with_data:
            path += "?withData=true"
        return self._request_json(path)

    def add_rss_feed(self, url: str, path: str = "") -> bool:
        """添加 RSS 源到 qBittorrent。path 为文件夹路径（空字符串表示根目录）。"""
        params = {"url": url}
        if path:
            params["path"] = path
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = self._build_request(QB_API["rss_add_feed"], data, "POST")
        try:
            resp = _urlopen_bypass_proxy(req, timeout=30)
            return True
        except Exception as e:
            print(f"[qB] 添加 RSS 失败: {e}")
            return False

    def ensure_rss_feed(self, url: str, feed_name: str = "Bangumi") -> bool:
        """确保 RSS 源已添加。如果不存在则自动添加。"""
        rss_items = self.get_rss_items(with_data=False)
        if rss_items is None:
            print("[qB] 无法检查 RSS 树")
            return False
        
        # 检查是否已存在
        if self._feed_exists(rss_items, url):
            print(f"[qB] RSS 源已存在: {feed_name}")
            return True
        
        # 不存在则添加
        print(f"[qB] 正在添加 RSS 源: {feed_name}")
        return self.add_rss_feed(url, feed_name)

    def _feed_exists(self, rss_tree: dict, target_url: str) -> bool:
        """递归检查 RSS 树中是否已存在目标 URL。"""
        for key, val in rss_tree.items():
            if isinstance(val, dict):
                if val.get("url") == target_url:
                    return True
                if "children" in val:
                    if self._feed_exists(val["children"], target_url):
                        return True
        return False

    # ── Torrent 操作 ─────────────────────────────────────

    def resume_paused_torrents(self) -> int:
        """恢复所有暂停状态的 torrent，返回恢复数量。"""
        torrents = self._request_json(QB_API["torrents_info"] + "?filter=paused")
        if not torrents or not isinstance(torrents, list):
            return 0

        hashes = [t["hash"] for t in torrents if "hash" in t]
        if not hashes:
            return 0

        hash_str = "|".join(hashes)
        data = urllib.parse.urlencode({"hashes": hash_str}).encode("utf-8")
        req = self._build_request(QB_API["torrents_resume"], data, "POST")
        try:
            _urlopen_bypass_proxy(req, timeout=30)
            return len(hashes)
        except Exception as e:
            print(f"[qB] 恢复 torrent 失败: {e}")
            return 0

        # ?? ???? ?????????????????????????????????????????

    def get_all_torrents(self) -> list[dict]:
        """???? torrent ???? save_path??"""
        result = self._request_json(QB_API["torrents_info"])
        return result if isinstance(result, list) else []

    def set_torrent_location(self, hashes: list[str], location: str) -> int:
        """???? torrent ????????????"""
        if not hashes:
            return 0
        hash_str = "|".join(hashes)
        data = urllib.parse.urlencode({
            "hashes": hash_str,
            "location": location,
        }).encode("utf-8")
        req = self._build_request("/api/v2/torrents/setLocation", data, "POST")
        try:
            resp = _urlopen_bypass_proxy(req, timeout=60)
            return len(hashes)
        except Exception as e:
            print(f"[qB] ?? torrent ????: {e}")
            return 0

    def update_rules_save_path(self, old_path: str, new_path: str) -> dict:
        """
        ?????? RSS ????????
        ?? {"updated": int, "failed": int, "details": [...]}
        """
        rules = self.get_rules()
        if not rules or not isinstance(rules, dict):
            return {"updated": 0, "failed": 0, "details": []}

        updated = 0
        failed = 0
        details = []
        old_path_unix = old_path.replace("\\", "/")
        new_path_unix = new_path.replace("\\", "/")

        for name, rule_data in rules.items():
            if not isinstance(rule_data, dict):
                continue
            changed = False
            sp = rule_data.get("savePath", "")
            if old_path in sp or old_path_unix in sp:
                rule_data["savePath"] = sp.replace(old_path, new_path).replace(old_path_unix, new_path_unix)
                changed = True
            tp = rule_data.get("torrentParams", {})
            if isinstance(tp, dict):
                tsp = tp.get("save_path", "")
                if old_path_unix in tsp or old_path in tsp:
                    tp["save_path"] = tsp.replace(old_path_unix, new_path_unix).replace(old_path, new_path)
                    changed = True
            if changed:
                ok = self.set_rule(name, rule_data)
                if ok:
                    updated += 1
                    details.append(f"  OK  {name}")
                else:
                    failed += 1
                    details.append(f"  FAIL  {name}")
            else:
                details.append(f"  SKIP  {name}")

        return {"updated": updated, "failed": failed, "details": details}

# ── 乱码检查 ─────────────────────────────────────────

    def check_garbled_rules(self) -> list[str]:
        """
        检查当前规则中是否存在乱码规则名。
        返回乱码规则名列表。
        
        判定标准：规则名包含连续拉丁乱码串（非正常英文/拼音）。
        """
        rules = self.get_rules()
        if not rules or not isinstance(rules, dict):
            return []

        garbled = []
        for rule_name in rules.keys():
            if _is_garbled(rule_name):
                garbled.append(rule_name)
        return garbled

    # ── 安全导入流程 ─────────────────────────────────────

        # ── 启用规则并开始下载 ─────────────────────────────────

    def enable_rules(self, rule_names: list[str]) -> dict:
        """
        启用指定规则并触发下载：
        1. 逐条启用 (enabled=true, addPaused=false)
        2. 刷新 RSS 让规则重新匹配已有条目
        3. 恢复所有暂停的 torrent
        返回 {"enabled": [...], "failed": [...], "resumed": int}
        """
        result = {"enabled": [], "failed": [], "resumed": 0}
        existing = self.get_rules()
        if not existing or not isinstance(existing, dict):
            print("[qB] 无法读取现有规则。")
            return result

        for name in rule_names:
            if name not in existing:
                print(f"[qB] 规则不存在: {name}")
                result["failed"].append(name)
                continue

            rule_def = existing[name]
            if not isinstance(rule_def, dict):
                print(f"[qB] 规则格式异常: {name}")
                result["failed"].append(name)
                continue

            rule_def["enabled"] = True
            rule_def["addPaused"] = False

            ok = self.set_rule(name, rule_def)
            if ok:
                result["enabled"].append(name)
            else:
                result["failed"].append(name)

        # 启用完成后，刷新 RSS 让规则匹配已有条目
        if result["enabled"]:
            print(f"[qB] 正在刷新 RSS 以触发规则匹配...")
            self.refresh_rss()

            # 恢复所有暂停的 torrent（可能因之前 addPaused=true 而暂停）
            print(f"[qB] 正在恢复暂停的 torrent...")
            result["resumed"] = self.resume_paused_torrents()

        return result

    def safe_import(self, rules: dict) -> dict:
        """
        安全导入流程（对应 SOP §7-9）：
        1. 导入前乱码检查
        2. 逐条导入
        3. 导入后乱码检查
        4. 若有乱码则删除并修复
        返回完整报告。
        """
        report = {
            "pre_check_garbled": [],
            "post_check_garbled": [],
            "imported": [],
            "failed": [],
            "fixed": [],
        }

        # 1. 导入前检查
        report["pre_check_garbled"] = self.check_garbled_rules()

        # 2. 导入
        import_result = self.import_rules(rules)
        report["imported"] = import_result["success"]
        report["failed"] = import_result["failed"]

        # 3. 导入后检查
        report["post_check_garbled"] = self.check_garbled_rules()

        # 4. 检测新增乱码
        new_garbled = [r for r in report["post_check_garbled"]
                       if r not in report["pre_check_garbled"]]
        if new_garbled:
            print(f"[qB] 警告：导入后发现 {len(new_garbled)} 条新乱码规则，正在修复...")
            for name in new_garbled:
                self.delete_rule(name)
                report["fixed"].append(name)

        return report
    def get_qb_rules(self) -> dict:
        """获取 qBittorrent 中所有规则（只读，不写入本地）。"""
        rules = self.get_rules()
        if not rules or not isinstance(rules, dict):
            return {}
        return rules

    def sync_rules_to_local(self, local_rules_path: str, mode: str = "append") -> dict:
        """
        从 qBittorrent 同步规则到本地 rules.json。
        mode: "overwrite" = 覆盖（本地只保留 qB 中的规则）
              "append"    = 追加（保留本地已有，新增 qB 中的）
        返回 {"synced": int, "updated": int, "total": int, "rules": dict}
        """
        import json

        qb_rules = self.get_rules()
        if not qb_rules or not isinstance(qb_rules, dict):
            print("[qB] 无法获取规则。")
            return {"synced": 0, "updated": 0, "total": 0, "rules": {}}

        if mode == "overwrite":
            # 覆盖模式：直接用 qB 规则替换本地
            local_rules = {}
            for name, qb_data in qb_rules.items():
                if isinstance(qb_data, dict):
                    local_rules[name] = qb_data
            synced = len(local_rules)
            updated = 0
        else:
            # 追加模式：保留本地已有，新增 qB 中的
            local_rules = {}
            if os.path.exists(local_rules_path):
                try:
                    with open(local_rules_path, "r", encoding="utf-8") as f:
                        local_rules = json.load(f)
                except Exception:
                    local_rules = {}

            synced = 0
            updated = 0
            for name, qb_data in qb_rules.items():
                if not isinstance(qb_data, dict):
                    continue
                if name in local_rules:
                    local_rules[name]["enabled"] = qb_data.get("enabled", False)
                    local_rules[name]["addPaused"] = qb_data.get("addPaused", True)
                    updated += 1
                else:
                    local_rules[name] = qb_data
                    synced += 1

        with open(local_rules_path, "w", encoding="utf-8") as f:
            json.dump(local_rules, f, ensure_ascii=False, indent=2)

        return {"synced": synced, "updated": updated, "total": len(qb_rules), "rules": local_rules}



def _is_garbled(text: str) -> bool:
    """
    判断规则名是否为乱码。
    典型特征：连续无意义的拉丁字符组合，像 mojibake。
    """
    import re
    # 如果包含正常中文，大概率不是乱码
    if re.search(r"[\u4e00-\u9fff]", text):
        return False
    # 如果纯 ASCII 且超过 20 字符且无空格分词，可能是乱码
    if len(text) > 20 and not re.search(r"[\u4e00-\u9fff]", text):
        # 检查是否有正常单词（至少一个 3+ 字母英文单词）
        words = re.findall(r"[a-zA-Z]{3,}", text)
        if len(words) < 2:
            return True
    return False

