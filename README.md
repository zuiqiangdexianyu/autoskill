# autoskill — 自动化稿件创作

中文稿件创作系统。用户给一个主题，自动产出带标题和正文、可直接发布的完整稿件。
唯一目标是**写出好稿子**——真人会写、读者读得下去、AI 愿意引用，而不是跑完流程交差。

## 支持的风格

- **自媒体（深度观点）** — 公众号 / 知乎 / 头条，800–1200 字，懂行但不端着。
- **GEO 优化文** — 面向 AI 搜索引擎，800–1500 字，结论先行、事实密集、可被原句引用。

## 创作工作流（6 步）

立意 → 选材 → 搭架 → 起草 → 精修 → 导出。功夫集中在搭架、起草、精修三步。
详见 [`SKILL.md`](./SKILL.md)，其中第一节「什么是好稿子」是质量标尺。

## 目录结构

```
SKILL.md                  技能定义（craft-first 工作流 + 质量标尺）
style/                    风格定义，每种风格一个文件，含完整中文范例
  ├── zimeiti.py          自媒体（深度观点）
  └── geo.py              GEO 优化文
skill/humanizer/          去 AI 腔润色技能（中文版，20 类中文 AI 腔）
scripts/                  工具集
  ├── knowledge_tools.py  知识库 CRUD + RAG 检索
  ├── image_tools.py      图片库管理 + 自动配图
  ├── banned_words.py     违禁词检测（6 类）
  ├── style_definitions.py风格加载器 + 全局禁用词库
  ├── server.py           HTTP API + Web 管理界面
  ├── index.html          管理界面前端
  └── word_export.py      导出 Word / 打包 zip
```

## 管理界面

```bash
python scripts/server.py --db wrw_agent.db --img images/ --port 8600
# 浏览器打开 http://localhost:8600 管理知识库 / 图片库
```

## 新增风格

在 `style/` 下新建一个 `.py` 文件，导出一个 `STYLE` 字典即可，无需改代码。
建议照 `zimeiti.py` / `geo.py` 的结构补齐范例字段（标题/开头/段落/结构/结尾对照），
范例是提升稿件质量最有效的杠杆。
