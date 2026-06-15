#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — 知识库 + 图片库 最小 API 服务

启动：python server.py --db /path/to/wrw_agent.db --img /path/to/images --port 8600
然后浏览器打开 http://localhost:8600

依赖：仅 Python 标准库
"""

import argparse
import json
import os
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# 将 scripts 目录加入 sys.path，以便导入工具模块
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import knowledge_tools as kt
import image_tools as it


# ═══════════════════════════════════════════════════════════════════
# HTTP 处理器
# ═══════════════════════════════════════════════════════════════════

class APIHandler(SimpleHTTPRequestHandler):
    """处理 API 请求 + 静态文件。"""

    # 类级别配置
    db_path = ""
    img_dir = ""
    img_base_url = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # API 路由
        if path == "/api/knowledge/bases":
            return self._json(kt.list_knowledge_bases(
                user_id=_int(qs.get("user_id", [None])[0]),
            ))
        if path == "/api/knowledge/bases/detail":
            return self._json(kt.get_knowledge_base(kb_id=int(qs["kb_id"][0])))
        if path == "/api/knowledge/entries/list":
            # 返回原始条目列表（非解析后）
            kb_id = _int(qs.get("kb_id", [None])[0])
            return self._json(_list_raw_entries(kb_id))
        if path == "/api/knowledge/entry/detail":
            entry_id = _int(qs.get("id", [None])[0])
            return self._json(_get_raw_entry(entry_id))
        if path == "/api/knowledge/search":
            return self._json(kt.search_knowledge(
                query=qs["query"][0],
                kb_ids=_int_list(qs.get("kb_ids", [])),
                max_results=_int(qs.get("max_results", ["20"])[0]),
            ))
        if path == "/api/knowledge/relevant":
            return self._json(kt.get_relevant_knowledge(
                topic=qs["topic"][0],
                kb_ids=_int_list(qs.get("kb_ids", [])),
                max_entries=_int(qs.get("max_entries", ["5"])[0]),
            ))
        if path == "/api/knowledge/check":
            body = qs.get("content", [""])[0]
            return self._json(kt.check_content_against_knowledge(
                content=body,
                kb_ids=_int_list(qs.get("kb_ids", [])),
                strict_mode="strict" in qs,
            ))
        if path == "/api/images/groups":
            return self._json(it.list_image_groups(
                user_id=_int(qs.get("user_id", [None])[0]),
            ))
        if path == "/api/images/list":
            return self._json(it.list_images(
                group_id=_int(qs.get("group_id", [None])[0]),
            ))

        # 静态文件：优先返回 scripts/index.html
        if path == "/" or path == "/index.html":
            return self._serve_static("index.html", "text/html; charset=utf-8")
        # 其他静态文件
        file_path = SCRIPT_DIR / path.lstrip("/")
        if file_path.is_file():
            return self._serve_file(str(file_path))
        # 兜底
        self.send_error(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 读取 body（支持 UTF-8 和 GBK 编码）
        content_length = int(self.headers.get("Content-Length", 0) or 0)
        body_raw = self.rfile.read(content_length) if content_length else b""
        body = ""
        if body_raw:
            for enc in ("utf-8", "gbk", "gb2312", "gb18030"):
                try:
                    body = body_raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if not body:
                body = body_raw.decode("utf-8", errors="replace")

        # -- 知识库条目 CRUD（action 参数放在 query）--
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/knowledge/bases/create":
            data = _json_body(body)
            err = _check_kb_name_exists(data["name"], None)
            if err: self._json({"ok": False, "error": err}); return
            self._json({"ok": True, "id": _create_kb(data)})
        elif path == "/api/knowledge/bases/update":
            data = _json_body(body)
            err = _check_kb_name_exists(data.get("name", ""), data.get("kb_id"))
            if err: self._json({"ok": False, "error": err}); return
            _update_kb(data)
            self._json({"ok": True})
        elif path == "/api/knowledge/bases/delete":
            data = _json_body(body)
            _delete_kb(data["kb_id"])
            self._json({"ok": True})
        elif path == "/api/knowledge/bases/toggle":
            data = _json_body(body)
            _toggle_kb(data["kb_id"], data.get("is_active", True))
            self._json({"ok": True})
        elif path == "/api/knowledge/entries/create":
            data = _json_body(body)
            self._json({"ok": True, "id": _create_entry(data)})
        elif path == "/api/knowledge/entries/update":
            data = _json_body(body)
            _update_entry(data)
            self._json({"ok": True})
        elif path == "/api/knowledge/entries/delete":
            data = _json_body(body)
            _delete_entry(data["entry_id"])
            self._json({"ok": True})

        # -- 图片库 --
        elif path == "/api/images/groups/create":
            data = _json_body(body)
            err = _check_image_group_name_exists(data.get("name", ""), None)
            if err: self._json({"ok": False, "error": err}); return
            self._json(it.create_image_group(
                name=data["name"],
                description=data.get("description", ""),
                user_id=data.get("user_id"),
            ))
        elif path == "/api/images/groups/update":
            data = _json_body(body)
            err = _check_image_group_name_exists(data.get("name", ""), data.get("group_id"))
            if err: self._json({"ok": False, "error": err}); return
            self._json(it.update_image_group(
                group_id=data["group_id"],
                name=data.get("name", ""),
                description=data.get("description", ""),
            ))
        elif path == "/api/images/groups/delete":
            data = _json_body(body)
            self._json(it.delete_image_group(group_id=data["group_id"]))
        elif path == "/api/images/upload":
            self._handle_image_upload(body_raw)
        elif path == "/api/images/delete":
            data = _json_body(body)
            self._json(it.delete_image(item_id=data["item_id"]))
        elif path == "/api/images/bulk-delete":
            data = _json_body(body)
            self._json(it.bulk_delete_images(item_ids=data["item_ids"]))
        else:
            self.send_error(404)
            self.end_headers()

    # ═══════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════

    def _json(self, data):
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _serve_static(self, filename, content_type):
        file_path = SCRIPT_DIR / filename
        if not file_path.is_file():
            self.send_error(404)
            self.end_headers()
            return
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_file(self, path):
        with open(path, "rb") as f:
            content = f.read()
        ct = _guess_content_type(path)
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_image_upload(self, body_raw):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(400, "Expected multipart/form-data")
            self.end_headers()
            return

        # 简单 multipart 解析
        boundary = content_type.split("boundary=")[1].strip()
        if boundary.startswith('"'):
            boundary = boundary[1:-1]
        boundary_bytes = boundary.encode()

        parts = body_raw.split(b"--" + boundary_bytes)
        files_data = []
        group_id = 1
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header = part[:header_end].decode("utf-8", errors="replace")
            file_data = part[header_end + 4:]
            if file_data.endswith(b"\r\n"):
                file_data = file_data[:-2]

            # 提取表单字段（无 filename）
            if 'filename="' not in header:
                if 'name="group_id"' in header:
                    group_id = int(file_data.decode("utf-8", errors="replace").strip())
                continue

            # 提取文件名
            fname = "upload"
            for line in header.split("\r\n"):
                if "filename=" in line:
                    fname = line.split('filename="')[1].split('"')[0]
                    break
            if fname and fname != "upload":
                files_data.append((fname, file_data))

        if not files_data:
            self._json({"ok": True, "results": [], "total": 0})
            return

        # 直接写入目标目录（跳过 temp 文件）
        img_dir = Path(APIHandler.img_dir) if APIHandler.img_dir else Path("images")
        img_dir.mkdir(parents=True, exist_ok=True)
        thumb_dir = img_dir / "thumbs"
        thumb_dir.mkdir(exist_ok=True)

        ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif"}
        THUMB_MAX = 400
        results = []

        try:
            from PIL import Image
            HAS_PIL = True
        except ImportError:
            HAS_PIL = False

        import hashlib, time, sqlite3
        conn = sqlite3.connect(APIHandler.db_path)

        try:
            for fname, data in files_data:
                ext = Path(fname).suffix.lower()
                if ext not in ALLOWED:
                    results.append({"filename": fname, "error": f"不支持格式: {ext}"})
                    continue

                h = hashlib.md5(f"{time.time()}_{fname}".encode()).hexdigest()[:12]
                stored_name = f"{h}{ext}"
                stored_path = img_dir / stored_name
                stored_path.write_bytes(data)

                fsize = len(data)
                width, height = 0, 0
                thumb_url = ""

                if HAS_PIL:
                    try:
                        img = Image.open(stored_path)
                        width, height = img.size
                        # 生成缩略图到 thumbs/ 子目录（原图不动）
                        thumb_path = thumb_dir / stored_name
                        thumb_img = img.copy()
                        thumb_img.thumbnail((THUMB_MAX, THUMB_MAX))
                        thumb_img.save(thumb_path, optimize=True, quality=80)
                        base = APIHandler.img_base_url
                        thumb_url = f"{base.rstrip('/')}/thumbs/{stored_name}" if base else str(thumb_path)
                    except Exception:
                        pass

                base = APIHandler.img_base_url
                url = f"{base.rstrip('/')}/{stored_name}" if base else str(stored_path)

                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO image_items (group_id, user_id, filename, url, thumb_url, stored_path, file_size, width, height)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (group_id, None, fname, url, thumb_url, str(stored_path), fsize, width, height),
                )
                results.append({"ok": True, "id": cur.lastrowid, "filename": fname, "url": url})

            conn.commit()
        finally:
            conn.close()

        self._json({"ok": True, "results": results, "total": len(results)})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[API] {args[0]}")


# ═══════════════════════════════════════════════════════════════════
# KB CRUD 辅助（直接操作 sqlite3）
# ═══════════════════════════════════════════════════════════════════

def _create_kb(data):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO knowledge_bases (name, user_id, is_active) VALUES (?, ?, 1)",
                (data["name"], data.get("user_id")))
    kb_id = cur.lastrowid
    conn.commit()
    conn.close()
    return kb_id

def _update_kb(data):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute("UPDATE knowledge_bases SET name = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (data["name"], data["kb_id"]))
    conn.commit()
    conn.close()

def _delete_kb(kb_id):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM knowledge_entry_items WHERE kb_id = ?", (kb_id,))
    cur.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
    conn.commit()
    conn.close()

def _toggle_kb(kb_id, is_active):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute("UPDATE knowledge_bases SET is_active = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (1 if is_active else 0, kb_id))
    conn.commit()
    conn.close()

def _create_entry(data):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO knowledge_entry_items (kb_id, title, entry_type, content, tags, source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["kb_id"], data.get("title", ""), data.get("entry_type", "brand"),
         data.get("content", ""), json.dumps(data.get("tags", [])), data.get("source", "")),
    )
    eid = cur.lastrowid
    conn.commit()
    conn.close()
    return eid

def _update_entry(data):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute(
        """UPDATE knowledge_entry_items SET title=?, entry_type=?, content=?, tags=?, source=?,
           updated_at = datetime('now','localtime') WHERE id=?""",
        (data.get("title", ""), data.get("entry_type", "brand"),
         data.get("content", ""), json.dumps(data.get("tags", [])),
         data.get("source", ""), data["entry_id"]),
    )
    conn.commit()
    conn.close()

def _delete_entry(entry_id):
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM knowledge_entry_items WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


def _check_kb_name_exists(name: str, exclude_id: int = None) -> str | None:
    """检查知识库名称是否重复，返回错误信息或 None。"""
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    try:
        cur = conn.cursor()
        if exclude_id:
            cur.execute("SELECT id FROM knowledge_bases WHERE name = ? AND id != ?", (name, exclude_id))
        else:
            cur.execute("SELECT id FROM knowledge_bases WHERE name = ?", (name,))
        if cur.fetchone():
            return f"知识库名称「{name}」已存在"
        return None
    finally:
        conn.close()


def _check_image_group_name_exists(name: str, exclude_id: int = None) -> str | None:
    """检查图片分组名称是否重复，返回错误信息或 None。"""
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    try:
        cur = conn.cursor()
        if exclude_id:
            cur.execute("SELECT id FROM image_groups WHERE name = ? AND id != ?", (name, exclude_id))
        else:
            cur.execute("SELECT id FROM image_groups WHERE name = ?", (name,))
        if cur.fetchone():
            return f"图片分组名称「{name}」已存在"
        return None
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════════

def _int(v):
    try: return int(v)
    except (TypeError, ValueError): return None

def _int_list(v):
    if not v: return []
    if isinstance(v, list) and len(v) == 1 and "," in v[0]:
        v = v[0].split(",")
    result = []
    for x in (v if isinstance(v, list) else [v]):
        try:
            result.append(int(x))
        except (TypeError, ValueError):
            pass
    return result

def _json_body(body: str) -> dict:
    if not body:
        return {}
    return json.loads(body)


def _list_raw_entries(kb_id: int) -> dict:
    """列出知识库的原始条目（非解析后）。"""
    import sqlite3
    if not kb_id:
        return {"ok": False, "error": "kb_id required"}
    conn = sqlite3.connect(APIHandler.db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, title, entry_type, content, tags, source, created_at, updated_at FROM knowledge_entry_items WHERE kb_id = ? ORDER BY id ASC", (kb_id,))
        entries = []
        for row in cur.fetchall():
            entries.append({
                "id": row[0], "title": row[1], "entry_type": row[2],
                "content": row[3], "tags": row[4], "source": row[5],
                "created_at": row[6], "updated_at": row[7],
            })
        return {"ok": True, "entries": entries, "total": len(entries)}
    finally:
        conn.close()


def _get_raw_entry(entry_id: int) -> dict:
    """获取单条原始条目。"""
    import sqlite3
    if not entry_id:
        return {"ok": False, "error": "entry_id required"}
    conn = sqlite3.connect(APIHandler.db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, kb_id, title, entry_type, content, tags, source, created_at, updated_at FROM knowledge_entry_items WHERE id = ?", (entry_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "条目不存在"}
        return {"ok": True, "entry": {
            "id": row[0], "kb_id": row[1], "title": row[2],
            "entry_type": row[3], "content": row[4], "tags": row[5],
            "source": row[6], "created_at": row[7], "updated_at": row[8],
        }}
    finally:
        conn.close()


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".txt": "text/plain",
}

def _guess_content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")


INIT_SQL = [
    "CREATE TABLE IF NOT EXISTS knowledge_bases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT DEFAULT '', is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULT (datetime('now','localtime')))",
    "CREATE TABLE IF NOT EXISTS knowledge_entry_items (id INTEGER PRIMARY KEY AUTOINCREMENT, kb_id INTEGER NOT NULL, title TEXT DEFAULT '', entry_type TEXT DEFAULT 'brand', content TEXT DEFAULT '', tags TEXT DEFAULT '[]', source TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')), updated_at TEXT DEFAULT (datetime('now','localtime')))",
    "CREATE TABLE IF NOT EXISTS image_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT DEFAULT '', description TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now','localtime')))",
    "CREATE TABLE IF NOT EXISTS image_items (id INTEGER PRIMARY KEY AUTOINCREMENT, group_id INTEGER NOT NULL, user_id INTEGER, filename TEXT DEFAULT '', url TEXT DEFAULT '', thumb_url TEXT DEFAULT '', stored_path TEXT DEFAULT '', file_size INTEGER DEFAULT 0, width INTEGER DEFAULT 0, height INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now','localtime')))",
    "CREATE INDEX IF NOT EXISTS idx_kb_user ON knowledge_bases(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_kei_kb ON knowledge_entry_items(kb_id)",
    "CREATE INDEX IF NOT EXISTS idx_ig_user ON image_groups(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_ii_group ON image_items(group_id)",
    "CREATE INDEX IF NOT EXISTS idx_ii_user ON image_items(user_id)",
]


def _ensure_db():
    import sqlite3
    conn = sqlite3.connect(APIHandler.db_path)
    try:
        for sql in INIT_SQL:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _kill_port(port: int):
    """杀掉占用指定端口的进程（Windows）。"""
    import subprocess, re
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{port} "',
            shell=True, text=True, stderr=subprocess.DEVNULL,
        )
        pids = set()
        for line in out.strip().split('\n'):
            m = re.search(r'LISTENING\s+(\d+)', line)
            if m:
                pids.add(m.group(1))
        for pid in pids:
            try:
                subprocess.run(f'taskkill /f /pid {pid}', shell=True, capture_output=True, text=True)
                print(f"  已释放端口 {port}（PID {pid}）")
            except Exception:
                pass
    except subprocess.CalledProcessError:
        pass  # 没有占用该端口的进程


# ═══════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="知识库 + 图片库 管理服务")
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--img", default="", help="图片存储目录")
    parser.add_argument("--port", type=int, default=8600, help="端口（默认8600）")
    parser.add_argument("--base-url", default="", help="图片 URL 前缀")
    args = parser.parse_args()

    APIHandler.db_path = args.db
    APIHandler.img_dir = args.img
    APIHandler.img_base_url = args.base_url

    kt.set_database_path(args.db)
    it.set_database_path(args.db)
    if args.img:
        it.set_image_dir(args.img)

    # 自动建表
    _ensure_db()

    # 杀掉占用端口的旧进程
    _kill_port(args.port)

    print(f"""
╔══════════════════════════════════════════════════╗
║  知识库 + 图片库 管理服务                          ║
║  数据库: {args.db}
║  图片: {args.img or '(未配置)'}
║  地址: http://localhost:{args.port}
╚══════════════════════════════════════════════════╝
""")
    server = HTTPServer(("0.0.0.0", args.port), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
