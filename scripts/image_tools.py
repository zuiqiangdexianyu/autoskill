#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
image_tools.py — 独立图片库工具（sqlite3 直连 + 文件系统）

完全独立，无需 FastAPI / SQLAlchemy，任何人都能直接使用。

依赖：仅 Python 标准库 + sqlite3 + Pillow（可选，用于缩略图）

用法：
    import image_tools as it

    # 设置数据库路径和图片存储目录
    it.set_database_path("/path/to/wrw_agent.db")
    it.set_image_dir("/path/to/images")

    # 列出图片分组
    result = it.list_image_groups(user_id=1)
    for g in result["groups"]:
        print(g["name"], g["image_count"])

    # 列出分组内图片
    result = it.list_images(group_id=1)
    for img in result["images"]:
        print(img["filename"], img["url"])

    # 上传图片
    result = it.upload_images(
        file_paths=["/tmp/photo.jpg", "/tmp/chart.png"],
        group_id=1,
        user_id=1,
        base_url="https://example.com/images/",
    )

    # 插入图片到文章
    result = it.insert_images_into_article(body, group_ids=[1])
    print(result["body"])

数据库建表 SQL（SQLite）：
    CREATE TABLE image_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT DEFAULT '',
        description TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE image_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        user_id INTEGER,
        filename TEXT DEFAULT '',
        url TEXT DEFAULT '',
        thumb_url TEXT DEFAULT '',
        stored_path TEXT DEFAULT '',
        file_size INTEGER DEFAULT 0,
        width INTEGER DEFAULT 0,
        height INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX idx_ig_user ON image_groups(user_id);
    CREATE INDEX idx_ii_group ON image_items(group_id);
    CREATE INDEX idx_ii_user ON image_items(user_id);
"""

import json
import os
import random
import re
import shutil
import sqlite3
from typing import Any, Dict, List, Optional

_DATABASE_PATH: Optional[str] = None
_IMAGE_DIR: Optional[str] = None

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif"}
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB


def set_database_path(path: str) -> None:
    global _DATABASE_PATH
    _DATABASE_PATH = path


def get_db_path() -> str:
    if _DATABASE_PATH and os.path.exists(_DATABASE_PATH):
        return _DATABASE_PATH
    raise RuntimeError("数据库路径未设置。请先调用 set_database_path()")


def set_image_dir(path: str) -> None:
    global _IMAGE_DIR
    _IMAGE_DIR = path
    os.makedirs(path, exist_ok=True)


def get_image_dir() -> str:
    if _IMAGE_DIR:
        os.makedirs(_IMAGE_DIR, exist_ok=True)
        return _IMAGE_DIR
    raise RuntimeError("图片目录未设置。请先调用 set_image_dir()")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


# ═══════════════════════════════════════════════════════════════════
# 分组管理
# ═══════════════════════════════════════════════════════════════════

def list_image_groups(user_id: Optional[int] = None) -> Dict[str, Any]:
    """列出所有图片分组及其图片数量。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        if user_id is not None:
            cur.execute("SELECT * FROM image_groups WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        else:
            cur.execute("SELECT * FROM image_groups ORDER BY created_at DESC")
        groups = []
        for row in cur.fetchall():
            g = dict(row)
            cur.execute("SELECT COUNT(*) FROM image_items WHERE group_id = ?", (g["id"],))
            g["image_count"] = cur.fetchone()[0]
            groups.append(g)
        return {"ok": True, "groups": groups, "total": len(groups)}
    finally:
        conn.close()


def create_image_group(name: str, description: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO image_groups (name, description, user_id) VALUES (?, ?, ?)",
            (name, description, user_id),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


def update_image_group(group_id: int, name: str = "", description: str = "") -> Dict[str, Any]:
    conn = _connect()
    try:
        updates, params = [], []
        if name:
            updates.append("name = ?"); params.append(name)
        if description:
            updates.append("description = ?"); params.append(description)
        if not updates:
            return {"ok": False, "error": "No fields to update"}
        params.append(group_id)
        conn.execute(f"UPDATE image_groups SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def delete_image_group(group_id: int) -> Dict[str, Any]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT stored_path FROM image_items WHERE group_id = ?", (group_id,))
        for row in cur.fetchall():
            path = row[0]
            if path and os.path.isfile(path):
                os.remove(path)
                _delete_thumb(path)
        cur.execute("DELETE FROM image_items WHERE group_id = ?", (group_id,))
        cur.execute("DELETE FROM image_groups WHERE id = ?", (group_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════
# 图片管理
# ═══════════════════════════════════════════════════════════════════

def list_images(group_id: Optional[int] = None) -> Dict[str, Any]:
    """列出图片。可指定 group_id，不指定则列全部。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        if group_id is not None:
            cur.execute("SELECT * FROM image_items WHERE group_id = ? ORDER BY created_at DESC", (group_id,))
        else:
            cur.execute("SELECT * FROM image_items ORDER BY created_at DESC")
        images = [dict(row) for row in cur.fetchall()]
        return {"ok": True, "images": images, "total": len(images)}
    finally:
        conn.close()


def upload_images(
    file_paths: List[str],
    group_id: int,
    user_id: Optional[int] = None,
    base_url: str = "",
) -> Dict[str, Any]:
    """上传图片到指定分组。自动压缩至5MB，生成400px缩略图。"""
    img_dir = get_image_dir()
    conn = _connect()
    results = []
    try:
        for fp in file_paths:
            if not os.path.isfile(fp):
                results.append({"filename": os.path.basename(fp), "error": "File not found"})
                continue
            ext = os.path.splitext(fp)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                results.append({"filename": os.path.basename(fp), "error": f"Unsupported extension: {ext}"})
                continue

            fsize = os.path.getsize(fp)
            if fsize > 100 * 1024 * 1024:  # 100MB hard limit
                results.append({"filename": os.path.basename(fp), "error": "File too large (>100MB)"})
                continue

            # 生成唯一文件名
            import hashlib, time
            h = hashlib.md5(f"{time.time()}_{fp}".encode()).hexdigest()[:12]
            stored_name = f"{h}{ext}"
            stored_path = os.path.join(img_dir, stored_name)

            # 复制并压缩（如有 Pillow）
            shutil.copy2(fp, stored_path)
            width, height = 0, 0
            try:
                from PIL import Image
                img = Image.open(stored_path)
                width, height = img.size
                if fsize > MAX_UPLOAD_SIZE:
                    img.save(stored_path, optimize=True, quality=85)
                # 生成缩略图
                thumb_name = f"{h}_thumb{ext}"
                thumb_path = os.path.join(img_dir, thumb_name)
                img.thumbnail((400, 400))
                img.save(thumb_path, optimize=True, quality=80)
                thumb_url = f"{base_url}{thumb_name}" if base_url else thumb_path
            except ImportError:
                thumb_url = ""
            except Exception:
                thumb_url = ""

            url = f"{base_url}{stored_name}" if base_url else stored_path

            cur = conn.cursor()
            cur.execute(
                """INSERT INTO image_items (group_id, user_id, filename, url, thumb_url, stored_path, file_size, width, height)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (group_id, user_id, os.path.basename(fp), url, thumb_url, stored_path, fsize, width, height),
            )
            results.append({"ok": True, "id": cur.lastrowid, "filename": os.path.basename(fp), "url": url})
        conn.commit()
        return {"ok": True, "results": results, "total": len(results)}
    finally:
        conn.close()


def _delete_thumb(stored_path: str):
    """删除缩略图（支持两种存放位置）。"""
    if not stored_path:
        return
    # 位置1：同目录 thumb_ 前缀
    d, fn = os.path.dirname(stored_path), os.path.basename(stored_path)
    candidates = [
        os.path.join(d, "thumbs", fn),          # thumbs/ 子目录
        os.path.join(d, f"thumb_{fn}"),          # 同目录 thumb_ 前缀
        os.path.join(d, f"{os.path.splitext(fn)[0]}_thumb{os.path.splitext(fn)[1]}"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            try:
                os.remove(c)
            except OSError:
                pass


def delete_image(item_id: int) -> Dict[str, Any]:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT stored_path FROM image_items WHERE id = ?", (item_id,))
        row = cur.fetchone()
        if row and row[0] and os.path.isfile(row[0]):
            os.remove(row[0])
            _delete_thumb(row[0])
        cur.execute("DELETE FROM image_items WHERE id = ?", (item_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def bulk_delete_images(item_ids: List[int]) -> Dict[str, Any]:
    for iid in item_ids:
        delete_image(iid)
    return {"ok": True, "deleted": len(item_ids)}


# ═══════════════════════════════════════════════════════════════════
# 图片插入
# ═══════════════════════════════════════════════════════════════════

def _find_paragraph_breaks(body: str) -> list:
    breaks = [(m.start(), m.end()) for m in re.finditer(r'\n\n+', body)]
    if len(breaks) >= 2:
        return breaks
    breaks = [(m.start(), m.end()) for m in re.finditer(r'</p>', body)]
    if len(breaks) >= 2:
        return breaks
    breaks = [(m.start(), m.end()) for m in re.finditer(r'\n', body)]
    return breaks if len(breaks) >= 2 else []


def _image2_position(body: str, breaks: list) -> int:
    if len(breaks) < 3:
        return breaks[-1][0]
    pre_last = body[breaks[-3][1]:breaks[-2][0]].strip()
    if re.match(r'^#{1,3}\s+\*?\*?', pre_last):
        return breaks[-3][0]
    return breaks[-1][0]


def _get_random_images(group_ids: List[int], count: int) -> List[str]:
    conn = _connect()
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" * len(group_ids))
        cur.execute(f"SELECT url FROM image_items WHERE group_id IN ({placeholders})", group_ids)
        urls = [r[0] for r in cur.fetchall()]
        if not urls:
            return []
        return random.sample(urls, min(count, len(urls)))
    finally:
        conn.close()


def insert_images_into_article(
    body: str,
    group_ids: List[int],
    existing_images: Optional[List[str]] = None,
) -> dict:
    """在 Markdown 正文中自动插入图片。

    规则：
    - 正文 <800 字 → 1 张，放在第一段之后
    - 正文 ≥800 字 → 2 张，第一段之后 + 末段之前（避开 H2）
    """
    if not group_ids:
        return {"body": body, "images": existing_images or []}

    text_len = len(body.replace(" ", "").replace("\n", ""))
    img_count = 1 if text_len < 800 else 2
    image_urls = _get_random_images(group_ids, img_count)
    if not image_urls:
        return {"body": body, "images": existing_images or []}

    img_md = lambda u: f"\n\n![图片]({u})\n"
    breaks = _find_paragraph_breaks(body)

    if len(breaks) < 2:
        mid = len(body) // 3
        if img_count == 1:
            new_body = body[:mid] + img_md(image_urls[0]) + body[mid:]
        else:
            mid2 = len(body) * 2 // 3
            new_body = (body[:mid] + img_md(image_urls[0])
                        + body[mid:mid2] + img_md(image_urls[1]) + body[mid2:])
        return {"body": new_body, "images": image_urls}

    pos_after_first = breaks[0][1]
    pos_before_last = _image2_position(body, breaks)

    if img_count == 1:
        new_body = body[:pos_after_first] + img_md(image_urls[0]) + body[pos_after_first:]
    else:
        new_body = (body[:pos_after_first]
                    + img_md(image_urls[0])
                    + body[pos_after_first:pos_before_last]
                    + img_md(image_urls[1])
                    + body[pos_before_last:])

    return {"body": new_body, "images": image_urls}


# ═══════════════════════════════════════════════════════════════════
# 快捷入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        set_database_path(sys.argv[1])
    if len(sys.argv) > 2:
        set_image_dir(sys.argv[2])
    print("图片库工具模块加载成功。")
    print("  set_database_path('/path/to/wrw_agent.db')")
    print("  set_image_dir('/path/to/images')")
    print("  list_image_groups()")
    print("  upload_images(file_paths=[...], group_id=1, base_url='https://...')")
    print("  insert_images_into_article(body='...', group_ids=[1])")
