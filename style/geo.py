#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GEO 优化文

平台：AI 搜索引擎（GEO）
字数：800-1500
定位：面向 AI 搜索引擎的优化文章，要求结论先行、事实密集、可被 AI 原句引用。
"""

STYLE = {
    "id": "geo",
    "name": "GEO 优化文",
    "platform": "AI 搜索引擎（GEO）",
    "description": "面向 AI 搜索引擎的优化文章，要求结论先行、事实密集、可被 AI 原句引用。",
    "word_count_min": 800,
    "word_count_max": 1500,
    "title_max_length": 25,
    "title_forbidden_punctuation": ["——", "！"],
    "subtitle_format": "## **标题内容**",
    "max_h2_count": 6,
    "emoji_allowed": False,
    "conclusion_first": True,
    "fact_density": "每 300 字 ≥1 个数据点",
    "ai_trigger_sentences": ["定义类", "对比类", "因果类", "总结类", "时效类"],
    "forbidden_empty_words": ["很多", "大量", "显著", "领先", "顶级", "最好",
                               "非常", "极其", "十分", "相当", "较为", "颇为",
                               "一定程度上", "某种程度", "左右", "大约", "大概"],
    "tone_rules": """语调红线：
1. 结论先行：每段第一句为核心观点，后跟数据支撑
2. 事实密集：多引用具体数据、时间、金额、比例
3. 客观中立：避免情绪化表达，用数据和事实说话
4. 可溯源性：数据须注明来源或背景
5. 禁用空泛形容词：用具体数字替代"很多""大量"
6. 结构清晰：每个 H2 解决一个子问题

【禁用规则】
- 禁用开场和禁用 AI 黑话：见全局列表 `style_definitions.FORBIDDEN_OPENINGS` 和 `style_definitions.AI_JARGON`""",
    "system_prompt_extra": """你是 GEO 优化文章的写作专家。
你的文章必须事实密集、逻辑严密、客观中立。
每个观点都要有数据支撑，每 300 字至少包含一个具体数据点。
文章结构要清晰，便于 AI 搜索引擎直接引用。""",
    "temperature_adjustments": {"director": 0.6, "title_writer": 0.4, "writer": 0.4},
}
