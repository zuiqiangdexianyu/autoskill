#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
knowledge_tools.py — 独立知识库工具（sqlite3 直连）

完全独立，无需 FastAPI / SQLAlchemy，任何人都能直接使用。

依赖：仅 Python 标准库 + sqlite3

用法：
    import knowledge_tools as kt

    # 设置数据库路径
    kt.set_database_path("/path/to/wrw_agent.db")

    # 列出知识库
    result = kt.list_knowledge_bases()
    print(result["knowledge_bases"])

    # 搜索知识库
    result = kt.search_knowledge(query="研发投入", kb_ids=[1], max_results=3)
    for r in result["results"]:
        print(r["entry"]["key"], r["entry"]["value"])

    # 按主题获取相关条目
    result = kt.get_relevant_knowledge(topic="航空运力", kb_ids=[1], max_entries=3)
    for e in result["relevant_entries"]:
        print(e["key"], e["value"])

    # 检查内容是否违反红线
    result = kt.check_content_against_knowledge("文章中提到了京东")
    print(result["has_conflicts"], result["conflicts"])

    # 获取知识库详情
    result = kt.get_knowledge_base(kb_id=1)
    for e in result["entries"]:
        print(e["key"], e["value"])

数据库建表 SQL（SQLite）：
    CREATE TABLE knowledge_bases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE knowledge_entry_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kb_id INTEGER NOT NULL,
        title TEXT DEFAULT '',
        entry_type TEXT DEFAULT 'brand',   -- brand / competitor / redline
        content TEXT DEFAULT '',
        tags TEXT DEFAULT '[]',             -- JSON array
        source TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        updated_at TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX idx_kb_user ON knowledge_bases(user_id);
    CREATE INDEX idx_kei_kb ON knowledge_entry_items(kb_id);
"""

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# 全局数据库路径
_DATABASE_PATH: Optional[str] = None


def set_database_path(path: str) -> None:
    """设置 SQLite 数据库路径。"""
    global _DATABASE_PATH
    _DATABASE_PATH = path


def get_db_path() -> str:
    """获取数据库路径，若未设置则报错。"""
    if _DATABASE_PATH and os.path.exists(_DATABASE_PATH):
        return _DATABASE_PATH
    raise RuntimeError(
        "数据库路径未设置。请先调用 set_database_path('/path/to/wrw_agent.db')"
    )


# ═══════════════════════════════════════════════════════════════════
# KnowledgeEntry
# ═══════════════════════════════════════════════════════════════════

@dataclass
class KnowledgeEntry:
    """知识库中的单条解析后条目。"""
    key: str
    value: str
    entry_type: str = "information"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "type": self.entry_type,
            "metadata": self.metadata,
            "kb_name": self.metadata.get("kb_name", ""),
            "kb_id": self.metadata.get("kb_id"),
        }

    def matches_query(self, query: str) -> bool:
        q = query.lower()
        return (
            q in self.key.lower()
            or q in self.value.lower()
            or any(q in str(t).lower() for t in self.metadata.get("tags", []))
        )

    def conflicts_with(self, content: str) -> List[Dict[str, Any]]:
        conflicts = []
        cl = content.lower()
        for kw in self.metadata.get("keywords", []):
            if str(kw).lower() in cl and self.entry_type == "prohibition":
                conflicts.append({
                    "type": "prohibition", "keyword": kw,
                    "entry_key": self.key,
                    "message": self.metadata.get("message", ""),
                    "severity": self.metadata.get("severity", "high"),
                })
        contradiction_kws = self.metadata.get("contradiction_keywords", [])
        if contradiction_kws:
            required = self.metadata.get("required_keyword", "").lower()
            for part in contradiction_kws:
                if str(part).lower() in cl and required not in cl:
                    conflicts.append({
                        "type": "contradiction", "keyword": part,
                        "entry_key": self.key,
                        "message": self.metadata.get("contradiction_message", ""),
                        "severity": "high",
                    })
        return conflicts


# ═══════════════════════════════════════════════════════════════════
# KnowledgeParser
# ═══════════════════════════════════════════════════════════════════

class KnowledgeParser:
    """解析知识库内容为 KnowledgeEntry 列表。"""

    @staticmethod
    def parse_qa(content: str) -> List[KnowledgeEntry]:
        entries = []
        for m in re.finditer(
            r"Q\d+[:：]\s*(.+?)\nA\d+[:：]\s*(.+?)(?=\nQ\d+[:：]|$)",
            content, re.DOTALL | re.IGNORECASE,
        ):
            entries.append(KnowledgeEntry(
                key=m.group(1).strip(), value=m.group(2).strip(),
                entry_type="qa", metadata={"format": "qa"},
            ))
        return entries

    @staticmethod
    def parse_keyvalue(content: str) -> List[KnowledgeEntry]:
        entries = []
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(.+?)[:：]\s*(.+)$", line)
            if m:
                entries.append(KnowledgeEntry(
                    key=m.group(1).strip(), value=m.group(2).strip(),
                    entry_type="information", metadata={"format": "keyvalue"},
                ))
        return entries

    @staticmethod
    def parse_rules(content: str) -> List[KnowledgeEntry]:
        entries = []
        for m in re.finditer(
            r"^(必读|必须|禁止|不得|应当|建议|推荐)(.+?)[:：]\s*(.+?)$",
            content, re.MULTILINE,
        ):
            prefix, rule, desc = m.group(1), m.group(2), m.group(3)
            etype = "prohibition" if prefix in ("禁止", "不得") else \
                    "recommendation" if prefix in ("建议", "推荐") else "requirement"
            kws = [x for t in re.findall(r'[""''](.+?)[""'']|「(.+?)」|（(.+?)）', desc) for x in t if x]
            entries.append(KnowledgeEntry(
                key=f"{prefix}{rule}".strip(), value=desc.strip(),
                entry_type=etype,
                metadata={
                    "prefix": prefix, "keywords": kws,
                    "severity": "high" if etype == "prohibition" else "medium",
                },
            ))
        return entries

    @staticmethod
    def parse_points(content: str) -> List[KnowledgeEntry]:
        entries = []
        current_section = ""
        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.match(r"^\d+[.、]\s*(.+)", line) or re.match(r"^[a-zA-Z][.、]\s*(.+)", line):
                entries.append(KnowledgeEntry(
                    key=current_section, value=re.sub(r"^\d+[.、]\s*", "", line),
                    entry_type="point", metadata={"section": current_section},
                ))
            elif line.startswith("【") and line.endswith("】"):
                current_section = line[1:-1]
            elif line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
        return entries

    @staticmethod
    def parse_document(content: str) -> List[KnowledgeEntry]:
        entries = []
        for section in re.split(r"\n(?=第[一二三四五六七八九十\d]+[章节条])", content):
            section = section.strip()
            if not section:
                continue
            m = re.match(r"第[一二三四五六七八九十\d]+[章节条]\s*(.+)", section)
            key = m.group(1) if m else section.split("\n")[0][:50]
            body = section[m.end():].strip() if m else section
            entries.append(KnowledgeEntry(
                key=key, value=body, entry_type="document",
                metadata={"original_format": "document"},
            ))
        return entries

    @staticmethod
    def parse_markdown(content: str) -> List[KnowledgeEntry]:
        entries = []
        lines = content.split("\n")
        current_key, current_value, current_type = "", "", "section"
        in_table, table_lines = False, []

        def create_entry(k, v, t):
            if k and v.strip():
                v = v.strip()
                if t == "subsection" and len(v) > 500:
                    t = "document"
                entries.append(KnowledgeEntry(key=k, value=v, entry_type=t))

        for line in lines:
            s = line.strip()
            if not s:
                if in_table:
                    table_lines.append("")
                continue
            if s.startswith("# "):
                create_entry(current_key, current_value, current_type)
                current_key, current_type, current_value = s[2:].strip(), "section", ""
                in_table = False
            elif s.startswith("## "):
                create_entry(current_key, current_value, current_type)
                current_key, current_type, current_value = s[3:].strip(), "subsection", ""
                in_table = False
            elif s.startswith("### "):
                create_entry(current_key, current_value, current_type)
                current_key, current_type, current_value = s[4:].strip(), "subsection", ""
                in_table = False
            elif s.startswith("#### "):
                create_entry(current_key, current_value, current_type)
                current_key, current_type, current_value = s[5:].strip(), "information", ""
                in_table = False
            elif s.startswith("| ") and s.endswith(" |"):
                if not in_table:
                    in_table, table_lines = True, []
                table_lines.append(s)
            elif in_table and not (s.startswith("| ") and s.endswith(" |")):
                if len(table_lines) > 2 and current_key:
                    current_value += "\n" + "\n".join(table_lines) + "\n"
                in_table, table_lines = False, []
                if current_key:
                    current_value += s + "\n"
            elif s.startswith("- ") or s.startswith("* "):
                if current_key:
                    current_value += s + "\n"
            elif s.startswith("> "):
                if current_key:
                    entries.append(KnowledgeEntry(
                        key=current_key, value=s[2:].strip(),
                        entry_type="important", metadata={"format": "blockquote"},
                    ))
            else:
                if current_key:
                    current_value += s + "\n"

        create_entry(current_key, current_value, current_type)
        if not entries:
            entries = KnowledgeParser.parse_keyvalue(content)
        return entries

    @staticmethod
    def parse(content: str, content_type: str = "markdown") -> List[KnowledgeEntry]:
        parsers = {
            "markdown": KnowledgeParser.parse_markdown,
            "qa": KnowledgeParser.parse_qa,
            "rules": KnowledgeParser.parse_rules,
            "points": KnowledgeParser.parse_points,
            "document": KnowledgeParser.parse_document,
            "keyvalue": KnowledgeParser.parse_keyvalue,
        }
        parser = parsers.get(content_type.lower(), KnowledgeParser.parse_markdown)
        result = parser(content)
        if not result and content_type.lower() != "keyvalue":
            result = KnowledgeParser.parse_keyvalue(content)
        return result


# ═══════════════════════════════════════════════════════════════════
# KnowledgeChecker
# ═══════════════════════════════════════════════════════════════════

class KnowledgeChecker:
    """检查内容是否违反知识库红线。"""

    @staticmethod
    def check_conflicts(
        content: str,
        entries: List[KnowledgeEntry],
        strict_mode: bool = False,
    ) -> Dict[str, Any]:
        all_conflicts, warnings = [], []
        for entry in entries:
            if entry.entry_type in ("prohibition", "contradiction"):
                all_conflicts.extend(entry.conflicts_with(content))
            elif entry.entry_type == "requirement" and strict_mode:
                for kw in entry.metadata.get("required_keywords", []):
                    if str(kw).lower() not in content.lower():
                        warnings.append({
                            "type": "missing_requirement", "entry_key": entry.key,
                            "message": f"缺少必要内容：{entry.value}",
                            "suggestion": f"建议包含：{', '.join(entry.metadata.get('required_keywords', []))}",
                        })
        high = [c for c in all_conflicts if c.get("severity") == "high"]
        medium = [c for c in all_conflicts if c.get("severity") == "medium"]
        return {
            "has_conflicts": len(all_conflicts) > 0,
            "has_high_severity": len(high) > 0,
            "total_conflicts": len(all_conflicts),
            "high_severity_count": len(high),
            "medium_severity_count": len(medium),
            "conflicts": all_conflicts,
            "warnings": warnings,
            "is_safe": len(high) == 0,
            "recommendation": "REJECT" if high else "REVIEW" if warnings else "APPROVE",
        }

    @staticmethod
    def find_relevant_entries(
        entries: List[KnowledgeEntry],
        topic: str,
        max_entries: int = 5,
    ) -> List[KnowledgeEntry]:
        # 类型权重
        type_weights = {
            "prohibition": 10, "redline": 10,
            "important": 5, "requirement": 3,
            "recommendation": 2, "fact": 1.5,
            "qa": 1, "section": 1, "subsection": 1,
            "information": 1, "document": 0.8, "point": 0.8,
            "general": 0.5,
        }

        # topic → n-gram 词集
        topic_words = set()
        for seq in re.findall(r'[一-龥]{2,}', topic.lower()):
            for i in range(len(seq)):
                for j in range(2, 7):
                    if i + j <= len(seq):
                        topic_words.add(seq[i:i + j])

        scored = []
        for entry in entries:
            k = entry.key.lower()
            v = entry.value.lower()
            tags = [str(t).lower() for t in entry.metadata.get("tags", [])]
            match = 0
            for w in topic_words:
                if w in k: match += 2
                if w in v: match += 1
                if any(w in t for t in tags): match += 1
            score = float(match)
            score += type_weights.get(entry.entry_type, 0.5)
            if re.search(r"\d", v):
                score += 1.5
            if len(v) > 2000:
                score *= 0.7
            elif len(v) > 1000:
                score *= 0.85
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:max_entries]]


# ═══════════════════════════════════════════════════════════════════
# 工具函数（sqlite3 直连）
# ═══════════════════════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    db = get_db_path()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def list_knowledge_bases(
    user_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """列出所有知识库。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        sql = "SELECT * FROM knowledge_bases WHERE 1=1"
        params = []
        if user_id is not None:
            sql += " AND user_id = ?"; params.append(user_id)
        if is_active is not None:
            sql += " AND is_active = ?"; params.append(1 if is_active else 0)
        sql += " ORDER BY updated_at DESC"
        cur.execute(sql, params)
        kbs = []
        for row in cur.fetchall():
            row_d = dict(row)
            cur.execute("SELECT COUNT(*) FROM knowledge_entry_items WHERE kb_id = ?", (row_d["id"],))
            row_d["entry_count"] = cur.fetchone()[0]
            kbs.append(row_d)
        return {"ok": True, "knowledge_bases": kbs, "total": len(kbs)}
    finally:
        conn.close()


def get_knowledge_base(kb_id: int) -> Dict[str, Any]:
    """获取指定知识库详情及全部解析后条目。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,))
        kb = cur.fetchone()
        if not kb:
            return {"ok": False, "error": f"Knowledge base {kb_id} not found"}
        kb_d = dict(kb)
        cur.execute("SELECT * FROM knowledge_entry_items WHERE kb_id = ?", (kb_id,))
        entries = cur.fetchall()
        all_parsed = []
        for item in entries:
            item_d = dict(item)
            parsed = KnowledgeParser.parse(item_d.get("content", ""), "markdown")
            tags_raw = item_d.get("tags", "[]")
            if isinstance(tags_raw, str):
                try:
                    tags = json.loads(tags_raw)
                except (json.JSONDecodeError, TypeError):
                    tags = []
            else:
                tags = tags_raw if isinstance(tags_raw, list) else []
            for pe in parsed:
                pe.metadata["kb_name"] = kb_d.get("name", "")
                pe.metadata["kb_id"] = kb_d["id"]
                pe.metadata["entry_title"] = item_d.get("title", "")
                pe.metadata["entry_type"] = item_d.get("entry_type", "brand")
                pe.metadata["tags"] = tags
            all_parsed.extend(parsed)
        return {
            "ok": True,
            "knowledge_base": {"id": kb_d["id"], "name": kb_d["name"],
                               "entry_count": len(entries), "is_active": kb_d.get("is_active", True)},
            "entries": [e.to_dict() for e in all_parsed],
        }
    finally:
        conn.close()


def search_knowledge(
    query: str,
    kb_ids: Optional[List[int]] = None,
    max_results: int = 20,
) -> Dict[str, Any]:
    """按关键词搜索知识库。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        if kb_ids:
            placeholders = ",".join("?" * len(kb_ids))
            cur.execute(f"SELECT * FROM knowledge_bases WHERE id IN ({placeholders})", kb_ids)
        else:
            cur.execute("SELECT * FROM knowledge_bases WHERE is_active = 1")
        kb_list = [dict(r) for r in cur.fetchall()]
        if not kb_list:
            return {"ok": True, "results": [], "message": "No knowledge bases found"}

        all_entries = []
        for kb in kb_list:
            cur.execute("SELECT * FROM knowledge_entry_items WHERE kb_id = ?", (kb["id"],))
            for item in cur.fetchall():
                item_d = dict(item)
                parsed = KnowledgeParser.parse(item_d.get("content", ""), "markdown")
                tags_raw = item_d.get("tags", "[]")
                if isinstance(tags_raw, str):
                    try:
                        tags = json.loads(tags_raw)
                    except (json.JSONDecodeError, TypeError):
                        tags = []
                else:
                    tags = tags_raw if isinstance(tags_raw, list) else []
                for pe in parsed:
                    pe.metadata["kb_name"] = kb.get("name", "")
                    pe.metadata["kb_id"] = kb["id"]
                    pe.metadata["entry_title"] = item_d.get("title", "")
                    pe.metadata["entry_type"] = item_d.get("entry_type", "brand")
                    pe.metadata["tags"] = tags
                all_entries.extend([(pe, kb) for pe in parsed])

        results = []
        for entry, kb in all_entries:
            if entry.matches_query(query):
                results.append({"entry": entry.to_dict(), "knowledge_base": kb})
                if len(results) >= max_results:
                    break

        return {"ok": True, "query": query, "results": results, "total_found": len(results)}
    finally:
        conn.close()


def get_relevant_knowledge(
    topic: str,
    kb_ids: Optional[List[int]] = None,
    max_entries: int = 5,
) -> Dict[str, Any]:
    """按主题获取相关知识库条目。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        if kb_ids:
            placeholders = ",".join("?" * len(kb_ids))
            cur.execute(f"SELECT * FROM knowledge_bases WHERE id IN ({placeholders})", kb_ids)
        else:
            cur.execute("SELECT * FROM knowledge_bases WHERE is_active = 1")
        kb_list = [dict(r) for r in cur.fetchall()]
        if not kb_list:
            return {"ok": True, "relevant_entries": [], "message": "No knowledge bases found"}

        all_entries = []
        for kb in kb_list:
            cur.execute("SELECT * FROM knowledge_entry_items WHERE kb_id = ?", (kb["id"],))
            for item in cur.fetchall():
                item_d = dict(item)
                parsed = KnowledgeParser.parse(item_d.get("content", ""), "markdown")
                tags_raw = item_d.get("tags", "[]")
                if isinstance(tags_raw, str):
                    try:
                        tags = json.loads(tags_raw)
                    except (json.JSONDecodeError, TypeError):
                        tags = []
                else:
                    tags = tags_raw if isinstance(tags_raw, list) else []
                for pe in parsed:
                    pe.metadata["kb_name"] = kb.get("name", "")
                    pe.metadata["kb_id"] = kb["id"]
                    pe.metadata["entry_title"] = item_d.get("title", "")
                    pe.metadata["entry_type"] = item_d.get("entry_type", "brand")
                    pe.metadata["tags"] = tags
                    # 红线条目特殊标记
                    if item_d.get("entry_type") == "redline":
                        pe.entry_type = "redline"
                        pe.key = f"[红线] {pe.key}"
                all_entries.extend(parsed)

        relevant = KnowledgeChecker.find_relevant_entries(all_entries, topic, max_entries)
        return {
            "ok": True,
            "topic": topic,
            "relevant_entries": [e.to_dict() for e in relevant],
            "total_found": len(relevant),
        }
    finally:
        conn.close()


def check_content_against_knowledge(
    content: str,
    kb_ids: Optional[List[int]] = None,
    strict_mode: bool = False,
) -> Dict[str, Any]:
    """检查内容是否违反知识库红线/规则。"""
    conn = _connect()
    try:
        cur = conn.cursor()
        if kb_ids:
            placeholders = ",".join("?" * len(kb_ids))
            cur.execute(f"SELECT * FROM knowledge_bases WHERE id IN ({placeholders})", kb_ids)
        else:
            cur.execute("SELECT * FROM knowledge_bases WHERE is_active = 1")
        kb_list = [dict(r) for r in cur.fetchall()]
        if not kb_list:
            return {"ok": True, "has_conflicts": False, "message": "No knowledge bases found",
                    "recommendation": "APPROVE"}

        all_entries = []
        for kb in kb_list:
            cur.execute("SELECT * FROM knowledge_entry_items WHERE kb_id = ?", (kb["id"],))
            for item in cur.fetchall():
                item_d = dict(item)
                parsed = KnowledgeParser.parse(item_d.get("content", ""), "markdown")
                tags_raw = item_d.get("tags", "[]")
                if isinstance(tags_raw, str):
                    try:
                        tags = json.loads(tags_raw)
                    except (json.JSONDecodeError, TypeError):
                        tags = []
                else:
                    tags = tags_raw if isinstance(tags_raw, list) else []
                for pe in parsed:
                    pe.metadata["tags"] = tags
                all_entries.extend(parsed)

        result = KnowledgeChecker.check_conflicts(content, all_entries, strict_mode)
        result["ok"] = True
        result["knowledge_bases_checked"] = len(kb_list)
        result["total_entries_checked"] = len(all_entries)
        return result
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════
# 快捷入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        set_database_path(sys.argv[1])
    print("知识库工具模块加载成功。")
    print("  set_database_path('/path/to/wrw_agent.db')")
    print("  list_knowledge_bases()")
    print("  search_knowledge(query='研发投入', max_results=3)")
    print("  get_relevant_knowledge(topic='航空运力', max_entries=3)")
    print("  check_content_against_knowledge(content='...')")
    print("  get_knowledge_base(kb_id=1)")
