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

# ─────────────────────────── 全局规则（跨风格）───────────────────────────
# 这两个列表是"硬底线"，配合 skill/humanizer/SKILL.md 的 20 类中文 AI 腔一起用。
# humanizer 负责"改"，这两个列表负责"查"。

# 禁用开场：正文第一句绝不能这样起。一上来就空话铺垫是中文 AI 稿最明显的特征。
FORBIDDEN_OPENINGS = [
    "在当今…时代", "在当今…背景下", "在…日益激烈的今天",
    "随着…快速发展…", "随着…的不断…", "近年来，随着…",
    "众所周知", "不可否认", "毋庸置疑",
    "XXX是一家…", "关于XXX，很多人会问…", "说到XXX，大家第一反应是…",
    "很多人以为…", "大家都说A，但其实B",
    "想象一下", "试想一下", "设想这样一个场景",
    "在这个…的时代", "提到…，你会想到什么",
]

# 禁用 AI 黑话：这些词真人写稿几乎不用，见到就要换成具体说法（数字/动作/机制）。
AI_JARGON = [
    # —— AI 高频黑话词 ——
    "护城河", "赋能", "闭环", "抓手", "底层逻辑", "颗粒度",
    "生态", "维度", "链路", "心智", "势能", "范式", "对齐", "拉通",
    "沉淀", "价值洼地", "心智占领", "组合拳", "新基建",
    # —— 意义拔高 / 强行升华 ——
    "标志着", "折射出", "彰显了", "见证了", "书写了新篇章",
    "注入新动能", "具有重要意义", "是…的一个缩影", "扮演重要角色",
    "亮眼答卷", "交出…答卷", "迈向新征程", "新台阶",
    # —— 机械连接 / 套话 ——
    "值得一提的是", "值得关注的是", "不容忽视的是", "值得注意的是",
    "需要指出的是", "本质上", "从某种意义上说", "在某种程度上",
    "综上所述", "总而言之", "由此可见", "讲到底", "说穿了",
    # —— 伪深度词 ——
    "深入挖掘", "深度剖析", "多维度", "全方位", "一站式", "全链路",
    # —— 空泛形容词（该用数字的地方）——
    "强大的", "卓越的", "极致的", "领先的", "优质的", "高效的",
    "大幅提升", "显著改善", "极大优化", "明显增长", "有效降低",
    # —— 虚拟场景 / 自解释 / 自问自答 ——
    "想象一下", "试想一下", "不妨想一想", "设想",
    "翻译成大白话就是", "说得直白一点", "简单来说", "说白了",
    "答案很简单", "原因无非是", "说白了就是", "问题来了",
    # —— 机械引导 / 服务腔 ——
    "如果你翻翻", "你会发现", "让我们", "接下来我将为大家",
    "废话不多说", "希望这篇文章能帮到你",
    # —— 否定平行结构 ——
    "不只是X而已", "不只是X，更是", "这不仅是…更是", "与其说是…不如说是",
    # —— 空洞收尾 ——
    "这个数字说明了一切", "答案已经很明显了", "未来可期",
    "值得期待", "拭目以待", "充满想象", "充满无限可能",
    # —— AI 文学化比喻 ——
    "藏着一场无声的战争", "无声的博弈", "于无声处",
    # —— 虚假引用 / 模糊归因 ——
    "行业专家认为", "业内人士指出", "有专家表示", "据了解",
    "相关数据显示", "研究表明",
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
