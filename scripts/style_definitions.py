#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
style_definitions.py — 稿件风格定义加载器

从 style/ 目录下加载各风格的独立文件。
每个文件导出一个 STYLE 字典。
"""

import importlib
import os
import sys
from typing import Any, Dict, List, Optional

STYLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "style")
STYLE_DIR = os.path.normpath(STYLE_DIR)

# 全局规则（跨风格）
FORBIDDEN_OPENINGS = [
    "在当今…时代", "XXX是一家…", "关于XXX，很多人会问…",
    "随着…快速发展…", "很多人以为…", "说到XXX，大家第一反应是…",
    "大家都说A，但其实B",
]

AI_JARGON = [
    "护城河", "赋能", "闭环", "抓手", "底层逻辑", "颗粒度",
    "亮眼答卷", "未来可期", "说白了", "说穿了", "讲到底", "本质上",
    "值得一提的是", "不可否认的是", "毋庸置疑",
    "在这个…的背景下", "在…的大潮中", "正如…所说",
    "值得关注的是", "不容忽视的是", "从某种意义上说",
    "深入挖掘", "深度剖析", "多维度",
    # 虚拟场景引导
    "想象一下", "试想一下", "不妨想一想",
    # 自解释句式
    "翻译成大白话就是", "说得直白一点", "简单来说",
    # 自问自答
    "答案很简单", "原因无非是", "说白了就是",
    # 机械引导
    "如果你翻翻", "你会发现",
    # 否定平行结构
    "不只是X而已", "不只是X，更是",
    # AI 式开场
    "当你在…的时候", "在很多人的印象中",
    # 空洞收尾
    "这个数字说明了一切", "答案已经很明显了",
    "值得期待", "迈向新征程",
    # AI 文学化比喻
    "藏着一场无声的战争", "无声的博弈",
    # 虚假引用
    "行业专家认为", "业内人士指出",
]


def _load_all_styles() -> List[Dict[str, Any]]:
    """从 style/ 目录加载所有风格文件。"""
    if STYLE_DIR not in sys.path:
        sys.path.insert(0, STYLE_DIR)

    styles = []
    if not os.path.isdir(STYLE_DIR):
        return styles

    for fname in sorted(os.listdir(STYLE_DIR)):
        if fname.endswith(".py") and not fname.startswith("_"):
            mod_name = fname[:-3]
            try:
                mod = importlib.import_module(mod_name)
                style = getattr(mod, "STYLE", None)
                if style and isinstance(style, dict):
                    styles.append(style)
            except Exception as e:
                print(f"[style_definitions] 加载 {fname} 失败: {e}")

    return styles


ALL_STYLES: List[Dict[str, Any]] = _load_all_styles()
STYLE_MAP: Dict[str, Dict[str, Any]] = {s["id"]: s for s in ALL_STYLES}


def get_style(style_id: str) -> Dict[str, Any]:
    style = STYLE_MAP.get(style_id)
    if not style:
        raise ValueError(f"未知风格: {style_id}，可选: {', '.join(STYLE_MAP.keys())}")
    return style


def list_styles() -> List[Dict[str, Any]]:
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "platform": s["platform"],
            "description": s["description"],
            "word_count": f"{s['word_count_min']}-{s['word_count_max']} 字",
        }
        for s in ALL_STYLES
    ]


def get_temperature(style_id: str, role: str) -> float:
    style = get_style(style_id)
    adjustments = style.get("temperature_adjustments", {})
    default_temps = {
        "director": 0.7, "material_specialist": 0.15, "prompt_designer": 0.65,
        "title_writer": 0.8, "writer": 0.7, "reviewer": 0.2, "optimizer": 0.3,
    }
    temp = default_temps.get(role, 0.7)
    if role in adjustments:
        temp = adjustments[role]
    return temp


if __name__ == "__main__":
    print("文章风格定义加载成功。\n")
    print(f"风格目录: {STYLE_DIR}\n")
    for s in ALL_STYLES:
        print(f"  [{s['id']}] {s['name']} — {s['description']}")
        print(f"        字数: {s['word_count_min']}-{s['word_count_max']} | 标题上限: {s['title_max_length']} 字")
        print(f"        平台: {s['platform']}")
        print()
