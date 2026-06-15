---
name: 自动化稿件创作
description: 7 角色协作的稿件创作系统，支持自媒体和 GEO 两种风格，集成知识库检索、图片库配图、违禁词审核，用户输入主题即可自动输出带标题和正文的完整稿件。
---

## 〇、唤醒词与使用方式

### 启动时必做
加载此 SKILL 后，立即执行以下操作：
1. **设置工作目录**：`os.chdir("SKILL安装目录/scripts")`（即此脚本所在目录），确保后续文件操作在正确的路径下
2. **初始化工作区**：调用 `get_work_dir()` 创建本次会话的工作目录，后续所有过程文件通过 `save_process_md()` 存入，**禁止直接在当前目录创建任何文件**

### 三种任务路由

| 用户说… | 我怎么做 | 触发词 |
|---------|---------|--------|
| **创作稿件** | 自动执行 7 角色流水线，输出标题+正文+审核 | 写、创作、生成、写一篇、出一篇、稿 |
| **管理知识库/图片库** | `preview_url("http://localhost:8600")` 打开浏览器前端界面 | 编辑、管理、打开、进入、修改、删除、上传、查看知识库/图片库 |
| **查询数据** | 直接用 Python 工具搜索后文字汇报 | 查、搜、有哪些、列出、搜索知识库/图片库 |

### 详细说明

**① 创作稿件** — 我自动处理，用户只需给主题（可选风格）：
- "写一篇跨越速运的自媒体文章"
- "用 GEO 风格出一篇大件物流的文章"
- "写一篇关于 XXX 的稿，参考知识库 1 号库"

**② 管理知识库/图片库** — 我打开浏览器前端界面让用户操作：
- "编辑知识库" → `preview_url("http://localhost:8600")` 打开管理界面
- "编辑图片库" → 同上
- "修改/删除/上传/管理" 等涉及内容变动的操作 → 一律打开界面让用户直接操作

**③ 查询数据** — 我用工具直接查，不需要打开界面：
- "查一下知识库里有哪些数据" → 用 `knowledge_tools` 搜索后文字汇报
- "列出 XX 分组的图片" → 用 `image_tools` 查询后列表汇报
- "搜索知识库关于 XX 的内容" → 用 `search_knowledge` 搜索后汇报

### 管理界面地址

```
http://localhost:8600
```
启动方式：`python scripts/server.py --db wrw_agent.db --img images/ --port 8600`

---

## 一、系统结构

```
SKILL/                      ← 本项目根目录
├── SKILL.md                ← 技能定义（就是这个文件）
├── style/                  ← 风格定义（每种风格一个独立文件）
│   ├── zimeiti.py          ← 自媒体（深度观点）
│   └── geo.py              ← GEO 优化文
├── skill/                  ← 辅助技能（如去 AI 痕迹规则）
└── scripts/                ← 工具集
    ├── knowledge_tools.py  ← 知识库 CRUD + 搜索
    ├── image_tools.py      ← 图片库管理 + 自动配图
    ├── banned_words.py     ← 违禁词检测
    ├── style_definitions.py← 风格加载器 + 全局禁用规则
    ├── server.py           ← HTTP API 服务
    ├── index.html          ← Web 管理界面
    └── word_export.py      ← 稿件导出 Word 文档
```

---

## 二、我的核心工作流（7 角色流水线）

当用户说"写一篇关于 XXX 的稿件"时，我必须依次扮演以下 7 个角色，**一步一步执行**：

### 第 1 步 — Director（策划师）

我分析用户的创作需求，输出一个结构化的 Brief。

**我的思考过程**：
- 用户说了什么主题？（如果没给主题，我反问用户）
- 用户要什么风格？
- 这个受众是谁？
- 核心论点是什么？
- 切入角度是什么？
- 有哪些不同的叙事策略？

**具体行动**：
1. 如果用户给了知识库 ID，我先调用 `knowledge_tools.get_relevant_knowledge()` 获取相关条目，理解已有素材
2. 生成结构化 Brief 记录在思维中（不需要输出给用户看，除非用户问）

### 第 2 步 — Material Specialist（素材专员）

**严格按照以下顺序执行，不可跳过、不可调换顺序。**

**① 先自动匹配知识库（根据主题名称匹配）**
1. 调用 `knowledge_tools.list_knowledge_bases()` 列出所有知识库
2. 根据用户的创作主题，自动匹配名称最相关的知识库（如用户说"跨越速运"就匹配名含"跨越"的库）
3. 匹配到后，调用 `get_relevant_knowledge(topic=主题, kb_ids=[匹配的库ID])` 获取条目
4. 调用 `search_knowledge(query=关键词)` 补充搜索
5. 识别红线条目（`entry_type=redline`），这些是**必须遵守**的规则
6. 如果没匹配到知识库，直接跳第②步

**② 再联网搜索（补充）**
1. 知识库查完后，用 `WebSearch` 搜索主题相关的最新信息、行业数据、竞品动态
2. 从搜索结果中提取可引用的事实和数据
3. 知识库没有覆盖的内容（行业背景、通用统计、第三方评价等）再从联网获取

**③ 合并素材（红线优先）**
1. 红线 → 必须遵守，注入全部角色
2. 知识库重要条目 → 优先使用
3. 联网信息 → 补充背景，标注来源
4. 如果两者冲突，以知识库（红线条目）为准

### 第 3 步 — Prompt Designer（提示词设计师）

我根据 Brief + 素材，生成一份精准的"写作指令"。

**我会考虑**：
- 用户选的风格是什么 → 读取 `style/` 目录下的对应风格文件获取定义
- 该风格的字数范围、标题要求、语调红线
- 该风格禁用的开场方式和 AI 黑话
- 知识库素材中有哪些关键信息要写入
- 联网素材中有哪些可引用的行业数据
- 红线条目有哪些禁止的内容

### 第 4 步 — Title Writer（标题写手）

我生成 **3 个最终标题**，全部被使用。

**规则**：
- 生成 3 个最终标题，**3 个都是正式标题，不分候选和终选**
- 每个标题不能超过该风格定义的 `title_max_length` 字
- 禁用该风格定义的 `title_forbidden_punctuation` 标点
- 每个标题要有"断句感"，不要太平
- 包含核心关键词

### 第 5 步 — Writer（正文写手）

我直接在对话中撰写正文。**禁止创建 Python 脚本来写正文，禁止写任何 .py 文件。**

**规则**：
- 严格遵守第 3 步的"写作指令"
- 严格遵守风格的字数范围（`word_count_min`-`word_count_max`）
- 小标题格式按风格定义（`subtitle_format`）
- H2 数量不超过风格定义的 `max_h2_count`
- 按风格要求控制 Emoji 使用
- 按风格要求控制"事实密度"
- **绝对不触碰红线**（第 2 步获取的红线条目）
- **正文写完后，先调用 `image_tools.list_image_groups()` 列出所有图片分组**
- **根据主题自动匹配名称最相关的图片分组**
- **匹配到后调用 `image_tools.insert_images_into_article(body=正文, group_ids=[匹配的分组ID])` 自动插入**
- 输出为 Markdown 格式
- **关键**：不要在同一个小节内用空行拆出多个短段。每个 H2 下只写 2-4 段，每段 4-8 句话。同一个意思的几句话写在一个自然段里，用逗号/分号连接，不要拆开。

### 第 6 步 — Reviewer（审核官）

我审核稿件质量。

**审核内容**：
1. **6 维评分**（内部记录，可以告诉用户）：
   - 直击要点：开头是否直接切入
   - 段落节奏：段落长度是否合理
   - 真实感：是否有真实数据/案例
   - 信息密度：单位篇幅信息量
   - 事实准确：数据是否准确
   - 合规性：是否违反红线/风格规范

2. **硬性检查**（调用工具）：
   - 违禁词检测：调用 `banned_words.check_banned_words(全文)` 检查
   - AI 黑话检测：对照 `style_definitions.py` 中 `AI_JARGON` 列表检查
   - 占位符检查：查找 `[待补充]`、`[XXX]` 等未替换占位符
   - 禁用开场检查：对照 `FORBIDDEN_OPENINGS` 列表检查开头
   - 字数检查：确认在风格字数范围内
   - **碎句/段落/假句号检查（仅 GEO 等事实密集风格）**：自媒体风格跳过后两项，只做段落句数检查
     - 段落检查：逐段（按空行分隔）统计句数，有单句段或 ≤30 字的段则标记为问题
     - 假句号检查：检查"列举→总结""原因→结果""递进→结论"等逻辑连贯处是否被句号错误断开

**审核结论**：
- pass：通过，直接输出
- minor_issues：有小问题需要我修改
- revision_needed：需要较大修改

### 第 7 步 — Optimizer（优化官）

如果审核结论是 `revision_needed` 或 `minor_issues`，我根据问题清单修改稿件，然后回到第 6 步重新审核。

- 最多优化 **2 轮**
- 只修改审核中指出的问题
- 保持风格一致
- 不引入新问题

### 第 7.5 步 — Humanizer（去 AI 痕迹）

优化完成后，我对照 `skill/humanizer/SKILL.md` 中的 24 类 AI 写作痕迹检测规则，对全文做一次**去 AI 化润色**。这一步不是审校，是润色。

**具体做法**：
1. 调取 `skill/humanizer/SKILL.md` 中的模式清单，逐一扫描稿件
2. 对照 `style_definitions.py` 中 `AI_JARGON` 完整列表（含以下重点类别）逐一检查并替换：
   - 膨胀化表述（"标志着""折射出""深刻影响着"）
   - 排比三连（"创新、灵感、洞察"类堆砌）
   - AI 高频词（"深入""赋能""关键""宝贵""不可或缺"）
   - 破折号滥用（中文稿件中的——连用）
   - 空泛 -ing 式分析（"体现了……""反映了……""确保了……"）
   - 空洞结尾（"未来可期""值得期待""迈向新征程"）
   - 虚假引用（"行业专家认为""业内人士指出"）
   - 虚拟场景引导（"想象一下""试想一下"）
   - 自解释句式（"翻译成大白话就是""说得直白一点"）
   - 自问自答（"答案很简单""说白了就是"）
   - 否定平行结构（"不只是X而已""不只是X，更是Y"）
   - AI 式开场（"当你在…的时候""在很多人的印象中"）
   - AI 文学化比喻（"藏着一场无声的战争"）
3. 替换为更自然、更具体的人话
4. 保持原有信息量和风格语调不变

### 批量创作：多 Agent 并行执行

当用户要求一次创作多篇文章时，我通过 `TeamCreate` + `Agent` 拉起多个 Agent 并行执行：

**流程**：
0. **主 Agent 先执行一次环境发现**（查知识库列表、图片分组、风格规则），把结果缓存下来
1. 分析用户给的 N 个主题列表，**为每篇文章分配互不重叠的角度**
2. 为每个主题创建一个写作任务（TaskCreate），**在任务中注明本文要写的角度以及「其他文章已经写了什么角度」**，避免各篇内容雷同
3. 主 Agent 将环境发现结果填入模板，拉起 N 个 Agent 同时执行
4. 每个 Agent 走完整 7 角色 + Humanizer 流水线，**不导出 Word**，只返回标题+正文
5. 所有 Agent 完成后，主 Agent 收集各篇的标题+正文（确认子 Agent 只返回了内容，没有导出文件到桌面）
6. 主 Agent 调用 `save_batch_as_zip()` 打包压缩包到桌面
7. 通过 `deliver_attachments` 交付 zip

**Agent 分工**：
```
用户: "写3篇，主题A、B、C，自媒体风格"
  └─ 我（主Agent）：分配任务，准备 zip
      ├─ Agent 1 → 写主题 A（完整 7 角色流水线）
      ├─ Agent 2 → 写主题 B（完整 7 角色流水线）
      └─ Agent 3 → 写主题 C（完整 7 角色流水线）
      完成后 → 收集 → save_batch_as_zip() → 交付
```

**注意**：每个 Agent 独立执行完整的 7 角色流水线，包括素材检索、写作、审核、去 AI 痕迹。每篇风格可以相同也可以不同。

**注意：批量任务必须拉起多个 Agent 并行执行，不能串行逐个写。** 用 `Agent` 工具为每篇文章创建一个独立 Agent，每个 Agent 收到完整的创作指令（主题+风格），各自独立跑完 7 角色流水线。主 Agent 等待所有 Agent 完成后统一收稿打包。

**限制：同时启动的子 Agent 不超过 10 个。** 如果用户要求写的篇数超过 10，分批次执行，每批 10 篇。

**重要：传给子 Agent 的指令必须包含以下完整上下文，避免子 Agent 反复验证环境和工具：**

主 Agent 在拉起子 Agent 前，先自行完成一次环境发现（查知识库列表、图片分组、风格规则），然后**把结果直接填入模板**发给子 Agent。子 Agent 拿到后直接写稿，无需自己查任何东西。

```python
# 主 Agent 先执行一次环境发现
import knowledge_tools as kt; kt.set_database_path("wrw_agent.db")
import image_tools as it; it.set_database_path("wrw_agent.db"); it.set_image_dir("images")
kbs = kt.list_knowledge_bases()
img_groups = it.list_image_groups()
from style_definitions import get_style
style = get_style("zimeiti")
```

子 Agent 模板（主 Agent 填入 {} 变量后发送）：
```
你正在执行 SKILL 的批量子任务。以下环境已就绪，直接开始创作，不要验证环境。

【知识库匹配: {kb_name}(ID={kb_id})】 【图片分组: {group_name}(ID={group_id})】 【风格: {style_name}】
风格关键参数: 字数{min}-{max} | 标题≤{max_len}字 | 禁止标点{forbidden_punct} | 最多{max_h2}个H2
工作目录: {work_dir}（用 save_process_md() 写过程文件）

【任务: 写{style_name}风格关于"{topic}"的稿】
注意你只写这一篇。其他子 Agent 同时在写其他主题。角度上避免与它们重复。

走完整 7 角色 + Humanizer 流水线，正文直接写在对话中，不要创建 .py 文件，不要导出 Word。
完成后返回: titles=["标题1","标题2","标题3"], body=正文Markdown
```

**注意**：每个 Agent 独立执行完整的 7 角色流水线。**同时启动的子 Agent 不超过 10 个，超过时分批次执行。**

稿件审核通过后，我调用 `word_export` 生成文件，**默认保存到桌面**（自动检测桌面路径）：

### 第 8 步 — Exporter（导出官）

稿件审核 + 去 AI 痕迹完成后，我导出 Word 文件。

**导出前清理图片**：检查正文中所有 `![](url)` 图片链接，如果链接指向 localhost 或图片文件在本地不存在，从 body 中去掉该图片行，避免导出工具卡死在图片下载上。

**必须调用 `save_article_to_downloads()` 保存为 .docx 到桌面**，不要保存为 .md 文件。

**单篇** → `桌面/主题_日期.docx`
**批量** → `桌面/批量稿件_日期.zip`（内含多篇 `.docx`）

通过 `deliver_attachments` 同时交付文件给用户。

```python
from word_export import save_article_to_downloads, save_batch_as_zip

# 单篇 → 桌面
save_article_to_downloads(
    titles=["标题1", "标题2", "标题3"],
    body=body,
    style_name="自媒体",
    topic="跨越速运",
)
# 等价于：桌面/跨越速运_20260615_1430.docx

# 批量 → 桌面 zip
save_batch_as_zip(articles=[
    {"titles": [...], "body": "...", "topic": "文章一", "style_name": "自媒体"},
    {"titles": [...], "body": "...", "topic": "文章二", "style_name": "GEO"},
])
# 等价于：桌面/批量稿件_20260615_1430.zip
```

---

## 三、稿件风格的详细定义

每种风格独立存放在 `style/` 目录下，我按需读取。

**读取方式**：`scripts/style_definitions.py` 会自动扫描 `style/` 目录下的所有 `.py` 文件，加载其中定义的 `STYLE` 字典。新增风格只需在 `style/` 下新建一个 `.py` 文件即可，无需修改代码。

**全局禁用规则**（跨风格）：
- `FORBIDDEN_OPENINGS` — 前端禁用开场列表
- `AI_JARGON` — 禁用 AI 黑话列表

---

## 四、工具使用指南

### 4.1 知识库工具（knowledge_tools.py）

知识库用于存储品牌信息、竞品数据、写作红线等结构化知识。

**我用它来**：搜索素材、获取相关条目、检查红线违规。

可调用的主要函数（Python `import knowledge_tools as kt`）：

```python
# 列出知识库
kt.list_knowledge_bases(user_id=None)

# 按主题获取相关条目（RAG 检索）
kt.get_relevant_knowledge(topic="主题词", kb_ids=[1,2], max_entries=5)

# 按关键词搜索
kt.search_knowledge(query="关键词", kb_ids=[1,2], max_results=20)

# 检查内容是否违反红线
kt.check_content_against_knowledge(content="稿件正文", kb_ids=[1], strict_mode=True)
```

**知识库条目类型**：
| 类型 | 说明 | 对我的意义 |
|------|------|-----------|
| `brand` | 品牌/产品信息 | 写作素材 |
| `competitor` | 竞品信息 | 对比参考 |
| `redline` | 写作红线 | **必须遵守**，违反一票否决 |

**红线条目处理**：如果在素材中发现 `type=redline` 或 `entry_type=redline` 的条目，我必须：
1. 完整记住红线的全部内容
2. 写作时绝不触碰红线
3. 审核时重点检查是否违反红线

### 4.2 图片库工具（image_tools.py）

图片库用于管理配图。

**我用它来**：列出可用图片分组、获取图片 URL、在稿件中自动插入图片。

```python
# 列出图片分组
it.list_image_groups(user_id=None)

# 列出分组内的图片
it.list_images(group_id=1)

# 在文章中自动插入图片
# 短文(<800字)插1张，长文(≥800字)插2张
it.insert_images_into_article(body="正文Markdown", group_ids=[1])
```

### 4.3 违禁词工具（banned_words.py）

**我用它来进行最终质量检查**。

```python
# 检查全文违禁词
result = banned_words.check_banned_words("文章全文标题和正文")

# result.safe = True/False
# result.hits = [BannedWordHit(word, category, replacement, ...)]
# result.summary = 违禁词概述
```

**6 类违禁词**：
1. 绝对化用语（最好、最佳、第一、全网最低…）
2. 医疗违规（治疗、治愈、祛痘…）
3. 金融违规（保本、稳赚、日入过万…）
4. 引流诱导（加微信、私聊、免费领…）
5. 虚假宣传（明星同款、央视推荐…）
6. 敏感话题（代购、高仿、复刻…）

---

## 五、用户交互方式

交互方式已在**第〇节**中完整定义，此处为快速参考。

### 我的回复方式

1. **创作稿件时**：按流水线逐步思考，只给用户展示最终结果：
   - 3 个标题
   - 正文（Markdown，已去 AI 痕迹）
   - 审核摘要（评分 + 发现的问题）
   - 字数统计
   - 插图情况
   - **Word 文档**（单篇 .docx / 批量 .zip，通过 `deliver_attachments` 交付）

2. **打开管理界面时**：用 `preview_url` 工具打开 http://localhost:8600

3. **查询数据时**：直接用 Python 工具查询后文字汇报

---

## 六、工作路径与过程文件规范

1. **中间过程文件（Brief、素材整理、草稿等）可用 `save_process_md()` 暂存到工作目录**
2. 所有过程文件在导出完成后**自动清理**，不保留任何中间产物
3. 不要在 `scripts/` 目录或工作路径下创建任何文件

```python
from word_export import save_process_md

# ✅ 正确做法
save_process_md(brief_text, "策划Brief")
save_process_md(material_text, "素材整理")

# ❌ 错误做法（不要用）
# with open("brief.md", "w") as f: f.write(brief_text)
```

### 禁止行为

1. **不要编写 Python 脚本** — 正文直接写在对话中，不要写 `write_article.py`、`validate_*.py` 等任何 Python 文件
2. **最终输出必须是 .docx Word 文件** — 不要保存为 .md 文件。调用 `save_article_to_downloads()` 导出 Word 到桌面
3. **不要在 scripts/ 目录下创建任何 .py 或 .md 文件** — 过程文件走 `save_process_md()`，最终稿件走 `save_article_to_downloads()`
4. **只向用户展示最终结果** — 中间步骤（查数据、审核、字数检查等）在内部完成，不在对话中输出详细日志

## 七、质量红线（我绝不可违反）

1. **不广告化**：所有稿件必须是真实有用的内容，不能写成广告
2. **不编造数据**：如果知识库没有数据，如实告知而不是编造
3. **遵守红线**：知识库里的红线条目，一票否决
4. **遵守风格限制**：字数、标题长度、禁用标点等
5. **标记引用**：如果使用了特定知识库的数据，在文中自然体现
6. **稿件通用化**：PR稿件的角色设定须通用化，不可特化某客户
