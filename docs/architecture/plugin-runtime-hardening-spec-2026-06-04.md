# Plugin Runtime Hardening Spec

> 日期：2026-06-04
> 状态：v6 Runtime 基线已基本落地；本文保留为设计依据，剩余事项转入当前待办清单（2026-08-25 核对）
> 范围：基于优秀 Claude Code 插件调研，对 `webnovel-writer` 的插件形态、运行时可靠性、workflow 编排、doctor 自检、hook 状态感知、eval 与发布治理做系统收束
> 调研样本：`anthropics/claude-plugins-official`、`anthropics/skills`、`obra/superpowers`、`SonarSource/sonarqube-agent-plugins`、`appwrite/claude-plugin`、`aws-samples/sample-claude-code-plugins-for-startups`、社区多插件 marketplace

---

## 1. 背景

`webnovel-writer` 当前已经不是普通单一 Skill，而是一个完整的长篇写作运行时插件：

- 8 个 Skill 命令负责 init / plan / write / review / query / learn / dashboard / doctor。
- 4 个 Agent 负责写前上下文、审查、事实提取、参考拆解。
- Python CLI 与 `data_modules` 承担 Story System、commit、projection、RAG、memory、Dashboard 数据层。
- `.story-system/` 是合同与提交主链，`.webnovel/*` 是 projection / read-model。

优秀 Claude Code 插件的共同经验是：

1. `SKILL.md` 做路由和流程，不承载全部知识。
2. 确定性动作下沉到脚本 / runtime / MCP，而不是靠 prompt 约束。
3. `commands / skills / agents / hooks / MCP` 边界清楚。
4. hooks 只做轻量状态提示、自检或接线，不做重业务。
5. 复杂 workflow 有可验证的输入、输出、停止条件和验收标准。
6. 有 `doctor / integrate / setup` 类环境自检入口。
7. 有真实行为 eval，证明 agent 会按协议执行。
8. manifest、marketplace、README、版本、LICENSE 有校验，避免漂移。

本 spec 的目标是把这些经验转化为 `webnovel-writer` 的下一阶段架构改造路线。

---

## 2. 一句话目标

把 `webnovel-writer` 从“强 Skill 包 + Python 工具链”升级为：

> 可自检、可验证、可恢复、可重放、可发版治理的长篇写作运行时插件。

---

## 3. 设计原则

### 3.1 Runtime First

写章、提交、投影、校验等关键链路必须由 runtime 保证，不再主要依赖 Skill 文档中的自然语言步骤。

### 3.2 Skill as Router

`SKILL.md` 保留：

- 何时触发
- 决策树
- 高层流程
- 必读/按需引用路由
- 失败处理边界

`SKILL.md` 不应承担：

- 长命令拼接细节
- schema 校验逻辑
- projection 修复逻辑
- 大段题材知识
- 可程序化验证规则

### 3.3 Commit Is Fact

`CHAPTER_COMMIT` 是写后事实，不应和 projection 执行日志混在一起。事实记录与投影执行状态要逐步解耦。

### 3.4 Hooks Are Advisory Guards

hooks 可以承担“自动触发的轻量守卫”，但不能成为隐藏业务流程。

允许：

- SessionStart 项目状态摘要
- 依赖 / 配置提醒
- doctor 入口提示
- dashboard / RAG / Story System 健康提示
- skill-scoped 固定预检，且通过时静默
- PreToolUse 对危险写入 / commit 命令做硬阻断

禁止：

- 自动写 state / commit / memory
- 自动安装外部依赖
- 自动修改正文或设定
- 注入大段创作方法论
- 作为章节主状态机写入 step state
- 每个步骤都用 hook 自动打点
- 在用户不可见的情况下推进写作流程

### 3.5 Behavior Must Be Tested

现有 Python 单元测试继续保留，但不足以证明插件行为。必须增加 skill / agent 工作流级 eval。

### 3.6 UTF-8 First

本项目大量读取中文路径和中文文件名，新入口必须显式 UTF-8：

- Python CLI 入口调用 `enable_windows_utf8_stdio()` 或等价逻辑。
- 所有文本读取 / 写入显式 `encoding="utf-8"`。
- hook / 子进程命令优先使用 `python -X utf8`，或显式设置 `PYTHONUTF8=1`。
- doctor / project-status / write-gate / hook 脚本不得依赖系统默认编码。

### 3.7 Follow Official `plugin-dev`

后续对本插件的任何新增或修改，必须先遵循官方 `plugin-dev` 插件的指导：

```text
C:\Users\lcy\.claude\plugins\marketplaces\claude-plugins-official\plugins\plugin-dev
```

落地约束：

- 插件结构遵循 `plugin-structure`：`.claude-plugin/plugin.json` 必须在插件根的 `.claude-plugin/` 下；`commands/`、`agents/`、`skills/`、`hooks/` 位于插件根层级。
- 所有插件内路径使用 `${CLAUDE_PLUGIN_ROOT}`，不在 manifest / hook / command 中写死本机绝对路径。
- 新增 Skill 遵循 `skill-development`：`SKILL.md` 必须有 `name`、具体触发型 `description`、可选 `version`；正文保持精简，详细规则放入 `references/`，确定性脚本放入 `scripts/`。
- 新增 Command 遵循 `command-development`：使用 markdown + YAML frontmatter，包含清晰 `description`、必要时声明 `argument-hint` 与 `allowed-tools`。
- 新增 Agent 遵循 `agent-development`：frontmatter 补齐 `name`、`description`、`model` / `tools` 等字段；复杂触发场景用示例描述；修改后用 validate-agent 规则检查。
- 新增 Hook 遵循 `hook-development`：插件级 `hooks/hooks.json` 使用 wrapper 格式，即外层包含 `description` 与 `hooks`；命令 hook 使用 `${CLAUDE_PLUGIN_ROOT}`；轻量确定性检查用 command hook，上下文判断才用 prompt hook。
- 修改插件组件后，必须按 `plugin-validator` 思路做结构校验：manifest、commands、agents、skills、hooks、MCP、README、LICENSE、敏感信息与路径可移植性。

这条优先级高于本 spec 中任何自定义落点建议；如果冲突，以官方 `plugin-dev` 约束为准。

---

## 4. 非目标

本轮不做：

- 不重写 Story System 主链语义。
- 不引入大规模新 MCP 服务。
- 不把 37 个题材模板拆成 37 个独立 Skill。
- 不照搬 Superpowers 的高频 git commit 机制。
- 不让 hook 承担写作业务。
- 不在本轮重构 Dashboard 前端信息架构。
- 不改变已有用户项目的数据格式，除非提供兼容读取。

---

## 5. 目标架构

### 5.1 组件边界

```text
commands/ 或 Slash Skill 入口
        ↓
Skill router（流程、引用路由、失败边界）
        ↓
Claude Code Todo（过程约束，由宿主管理）
        ↓
Runtime Gates（写前 / 提交前 / 提交后批量校验）
        ↓
Agents（context / draft / review / data extract）
        ↓
Artifact Validator
        ↓
CHAPTER_COMMIT（事实主链）
        ↓
Projection Engine（state/index/summary/memory/vector）
        ↓
Dashboard / Query / Doctor（只读消费）
```

### 5.2 写章过程管理

不新增独立 resume / step mark / workflow state。Claude Code 本身已经有 Todo 和会话恢复能力，写章过程的步骤约束交给宿主 Todo 管理。

推荐 Todo 形态：

```text
[ ] 写前预检与合同刷新
[ ] context-agent 生成写作任务书
[ ] 起草正文
[ ] reviewer 审查
[ ] blocking issue 裁决 / 定点修复
[ ] 润色与排版
[ ] data-agent 提取事实 artifacts
[ ] chapter-commit 提交事实
[ ] 验证 projection 与备份
```

runtime 不维护每一步状态，只提供三个自然边界的批量 gate：

- `prewrite`：写前检查项目根、占位符、Story Runtime、章节合同。
- `precommit`：提交前检查正文、review、fulfillment、disambiguation、extraction artifacts。
- `postcommit`：提交后检查 commit、projection、summary、memory、backup。

这样一章最多增加 2-3 次确定性脚本调用，不做每一步打点。

### 5.3 状态感知模型

项目状态分两层：

| 层级 | 负责者 | 持久性 | 用途 |
|---|---|---|---|
| 会话内进度 | Claude Code Task / Todo | 会话级 | 约束本轮写作步骤、显示当前正在做什么 |
| 项目真实状态 | Story System / commit / projection / artifacts | 项目级 | 新对话、resume、doctor 判断下一步 |

不新增独立 workflow state。项目真实状态由 runtime 现场推导：

- `.story-system/commits/*.commit.json` 判断最新 accepted/rejected 章节。
- `.story-system/MASTER_SETTING.json` 和章节合同判断下一章目标。
- `.webnovel/tmp/*` artifacts 判断是否已经 review / fulfillment / extraction。
- `.webnovel/projection_log.jsonl` 或兼容字段判断 projection 是否失败。
- draft 文件和 chapter artifact 判断是否存在未提交正文。

新增机器可读的项目状态入口，避免占用现有 `webnovel.py status`。当前 `status` 已转发到 `status_reporter.py`，语义是宏观创作健康报告；本 spec 需要的是短状态摘要，因此使用新命令：

```bash
webnovel.py project-status --format json
webnovel.py project-status --format summary
```

示例状态：

```json
{
  "schema_version": "webnovel-project-status/v1",
  "project": "灵石庄",
  "latest_accepted_chapter": 12,
  "target_chapter": 13,
  "phase": "chapter_contract_ready",
  "blocking": [],
  "warnings": ["rag_vector_missing"],
  "next_action": "run /webnovel-write chapter 13"
}
```

`phase` 是一个可推导状态，不是 hook 写入的状态机。phase 词表必须只有一个权威来源，建议新增 `project_phase.py`，由 doctor、project-status、write-gate 共同消费。推荐最小集合：

- `no_project`
- `unknown`
- `init_scaffolded`
- `init_ready`
- `plan_in_progress`
- `chapter_contract_ready`
- `draft_in_progress`
- `ready_to_commit`
- `chapter_committed`
- `projection_failed`

### 5.4 Hook 与状态的边界

hook 只读状态、注入短上下文或阻断危险动作：

- `SessionStart`：调用 `project-status --format summary`，在新对话、resume、clear、compact 后告诉 Claude 当前项目写到哪里。
- `PreToolUse`：在 `webnovel-write` skill 激活期间，阻断绕过 gate 的 commit / projection 写入。
- `PostToolUse`：可用于把 gate 失败原因补充给 Claude，但不能防止已经发生的副作用。

状态转换只能来自显式 runtime 命令：

- `write-gate --stage prewrite/precommit/postcommit`
- `chapter-commit`
- `projections retry/replay`
- 用户显式裁决 blocking issue

这保证流程推进发生在显式 skill / runtime 命令中，而不是 hook 暗中推进。

---

## 6. Phase 1：`webnovel-doctor` 项目体检入口

### 6.1 目标

新增只读体检命令，作为现有 `preflight` 的上位诊断入口。`preflight` 已经负责 CLI 环境、project_root 与 `story_runtime` 摘要；`doctor` 必须复用或吸收这些检查，不另造一套并行环境检查。

重点解决三类问题：

1. **文件层面**：目录是否规范、关键文件是否缺失、JSON / SQLite / Markdown 等内容是否符合预期。
2. **系统配置层面**：RAG API / key、Python 依赖、Dashboard 构建产物等运行条件是否完整。
3. **错误解释与修复建议**：缺失或异常时说明影响范围，并给出可执行修复命令或人工处理建议。

`doctor` 不负责判断一章具体该怎么写，也不替代 `write-gate`。它回答的是：

> 这个书项目和当前插件运行环境是否完整、可读、可运行；如果不完整，哪里坏了，怎么修。

### 6.2 入口

CLI：

```bash
python -X utf8 webnovel-writer/scripts/webnovel.py --project-root "<PROJECT_ROOT>" doctor --format json
```

Skill：

```text
/webnovel-doctor
```

与现有入口关系：

- `preflight`：保留为快速环境检查和兼容入口。
- `doctor`：覆盖 `preflight` 的快检能力，并追加阶段感知文件清单、SQLite、RAG、Python 依赖、Dashboard、修复建议。
- `project-status`：只输出短状态和下一步，不做深度体检。
- `status`：保留现有 `status_reporter.py` 的宏观创作健康报告语义。

可选后续 hook：

```text
SessionStart -> 打印 project-status 摘要；异常时提示运行 /webnovel-doctor
```

### 6.3 模式

默认模式必须只做本地只读检查：

```bash
webnovel.py doctor --format json
webnovel.py doctor --format text
```

可选深度模式才允许做慢检查或外部连通性检查：

```bash
webnovel.py doctor --deep --format json
```

可选章节模式用于检查指定章节相关 artifacts：

```bash
webnovel.py doctor --chapter 13 --format json
```

默认 `doctor` 禁止：

- 写任何文件。
- 自动修复。
- 自动安装 Python / Node 依赖。
- 自动启动 Dashboard。
- 默认联网测试 RAG API。

### 6.4 阶段感知的期望文件清单

`doctor` 必须先判断项目当前阶段，再决定“这个阶段应该有哪些文件”。不能用最终态清单检查所有项目。

#### 6.4.1 阶段推导

阶段由共享 `project_phase.py` 现场推导，不写任何状态文件。doctor、project-status、write-gate 必须消费同一个 resolver，避免出现多套 phase 词表：

| phase | 判定依据 | 含义 |
|---|---|---|
| `no_project` | project root 无效，或没有 `.webnovel/state.json` | 尚未初始化或未绑定书项目 |
| `unknown` | 文件状态不足以稳定判断 | 只做低风险检查 |
| `init_scaffolded` | 有 `.webnovel/state.json`、基础目录、设定集/总纲，但没有 `.story-system/MASTER_SETTING.json` | `webnovel.py init` 刚结束，Story System 尚未生成 |
| `init_ready` | 有 `.webnovel/state.json`、基础设定集、`大纲/总纲.md`、`.story-system/MASTER_SETTING.json` | init 完成，可进入 plan |
| `plan_in_progress` | 有 MASTER_SETTING，但卷/章合同不完整 | 正在规划，尚不能直接写章 |
| `chapter_contract_ready` | 指定章节有 volume / chapter / review 合同 | 可进入写前上下文和起草 |
| `draft_in_progress` | 指定章节有正文草稿或 `.webnovel/tmp` artifacts | 写章中或审查中 |
| `ready_to_commit` | review / fulfillment / disambiguation / extraction artifacts 都存在 | 可进入 precommit gate |
| `chapter_committed` | 指定章节有 commit | 章节已提交，检查 projection |
| `projection_failed` | latest commit 有 `projection_status.failed:*` | read-model 不可信，需要修复 |

如果无法确定阶段，返回 `phase=unknown`，并只做低风险文件可读性检查。

#### 6.4.2 阶段期望清单

`doctor` 输出必须包含当前阶段的期望清单：

```json
{
  "phase": "init_ready",
  "expected_profile": "after_init",
  "expected_files": {
    "required": [
      ".webnovel/state.json",
      ".webnovel/summaries/",
      "设定集/世界观.md",
      "设定集/力量体系.md",
      "设定集/主角卡.md",
      "设定集/反派设计.md",
      "大纲/总纲.md",
      ".env.example",
      ".story-system/MASTER_SETTING.json"
    ],
    "conditional": [
      "设定集/主角组.md",
      "设定集/女主卡.md"
    ],
    "not_expected_yet": [
      ".story-system/volumes/volume_001.json",
      ".story-system/chapters/chapter_001.json",
      ".story-system/reviews/chapter_001.review.json",
      ".story-system/commits/chapter_001.commit.json",
      ".webnovel/summaries/chapter_001.md",
      ".webnovel/memory_scratchpad.json"
    ]
  }
}
```

`conditional` 文件必须根据 `state.json` 判断。例如：

- `protagonist_structure` 是多主角 / 主角组时，才要求 `设定集/主角组.md`。
- `heroine_config` 不是无女主时，才要求 `设定集/女主卡.md`。
- 无金手指项目不要求单独 `金手指设计.md`。

#### 6.4.3 init 刚结束的判定

`webnovel.py init` 刚结束时，合理期望是项目骨架完整，但不要求写作后产物。

必须存在：

```text
.webnovel/
.webnovel/backups/
.webnovel/archive/
.webnovel/summaries/
.webnovel/state.json
设定集/
设定集/世界观.md
设定集/力量体系.md
设定集/主角卡.md
设定集/反派设计.md
大纲/
大纲/总纲.md
正文/
审查报告/
.env.example
```

如果 `/webnovel-init` 已完成 Story System 初始化，还必须存在：

```text
.story-system/
.story-system/MASTER_SETTING.json
.story-system/anti_patterns.json
```

init 阶段不应该要求：

```text
.story-system/volumes/volume_001.json
.story-system/chapters/chapter_001.json
.story-system/reviews/chapter_001.review.json
.story-system/commits/chapter_001.commit.json
.webnovel/summaries/chapter_001.md
.webnovel/memory_scratchpad.json
.webnovel/vectors.db
```

缺这些只能返回 `skip` 或 `info`，不能作为 warning / blocker。

#### 6.4.4 plan / write / commit 阶段清单

规划完成后，才开始要求：

```text
.story-system/volumes/volume_001.json
.story-system/chapters/chapter_001.json
.story-system/reviews/chapter_001.review.json
```

写章中，才开始检查：

```text
.webnovel/tmp/review_results.json
.webnovel/tmp/fulfillment_result.json
.webnovel/tmp/disambiguation_result.json
.webnovel/tmp/extraction_result.json
```

commit 后，才开始要求：

```text
.story-system/commits/chapter_001.commit.json
.webnovel/summaries/chapter_001.md
.webnovel/index.db
```

RAG 向量库永远是增强项：

```text
.webnovel/vectors.db
```

缺失或为空默认只返回 warning，并说明会降级 BM25；在用户显式要求语义检索或 `--deep --require-rag` 时才可升级为 blocker。

#### 6.4.5 误报控制

`doctor` 的严重级别必须基于“当前阶段 + 用户目标”判断：

| 情况 | 阶段 | 结果 |
|---|---|---|
| 缺 commit | `init_ready` | `skip` / `info` |
| 缺 commit | `ready_to_commit` | `blocker` |
| 缺 summary | `init_ready` | `skip` / `info` |
| 缺 summary | `chapter_committed` 且 projection summary=done | `blocker` |
| 缺 vectors.db | 任意默认模式 | `warning` |
| 缺 MASTER_SETTING | `init_scaffolded` | `warning`，提示运行 story-system persist |
| 缺 MASTER_SETTING | `plan_in_progress` 或之后 | `blocker` |

### 6.5 文件 / 数据结构检查

`doctor` 必须把“肉眼难看见”的项目文件和数据库结构变成可读报告。

#### 6.5.1 目录结构

检查：

- project root 是否有效，且不是插件目录本身。
- `.webnovel/` 是否存在。
- `.story-system/` 是否存在。
- `正文/`、`大纲/`、`设定集/` 等书项目目录是否存在。
- 用户项目文件是否误写入插件目录。

判定：

- project root 无效：`blocker`。
- 缺 `.webnovel/` 或 `.story-system/`：`blocker` 或 `warning`，取决于是否是刚 init 的项目。
- 缺正文/大纲/设定集目录：`warning`，并提示初始化或补建。

#### 6.5.2 Story System 主链文件

检查：

- `.story-system/MASTER_SETTING.json` 是否存在、JSON 可读、`meta.contract_type` 是否正确。
- `volumes/volume_*.json` 是否存在、JSON 可读。
- `chapters/chapter_*.json` 是否存在、JSON 可读。
- `reviews/chapter_*.review.json` 是否存在、JSON 可读。
- `commits/chapter_*.commit.json` 是否存在、JSON 可读。
- latest commit 的 `meta.status` 是否是 `accepted` / `rejected`。
- latest commit 的 `provenance.write_fact_role` 是否为 `chapter_commit`。

判定：

- 主链 JSON 读不出来：`blocker`。
- 已进入写作流程但缺 MASTER_SETTING：`blocker`。
- latest commit schema 明显不合法：`blocker`。
- 新项目尚无 commit：`info` 或 `warning`，不能误报为错误。

#### 6.5.3 Projection / Read-model 文件

检查：

- `.webnovel/state.json` 是否存在、JSON 可读、基础字段可解析。
- `.webnovel/summaries/` 是否存在，最新 accepted 章节是否有 summary。
- `.webnovel/memory_scratchpad.json` 是否存在、JSON 可读、基础结构可解析。
- latest commit 的 `projection_status` 是否有 `pending` / `failed:*`。

判定：

- `state.json` 不可读：`blocker`。
- projection writer failed：`blocker`，因为后续查询和 dashboard 可能不可信。
- summary / memory 缺失：通常 `warning`，除非对应 projection 标记为 done 但实物不存在。

#### 6.5.4 SQLite 数据库

检查 `.webnovel/index.db`：

- 文件是否存在。
- SQLite 是否可打开。
- 关键表是否存在。
- 关键表行数是否异常。
- 基础查询是否能执行。

建议首批关键表：

```text
entities
relationships
story_events
review_metrics
writing_checklist_scores
override_ledger
```

检查 `.webnovel/vectors.db`：

- 文件是否存在。
- SQLite 是否可打开。
- `vectors` 表是否存在。
- vector 行数。
- `bm25_index` / `doc_stats` 是否存在。

数据库报告必须显式展示表和行数，例如：

```json
{
  "id": "db.index.tables",
  "status": "ok",
  "severity": "info",
  "path": ".webnovel/index.db",
  "tables": {
    "entities": 128,
    "relationships": 42,
    "story_events": 36,
    "review_metrics": 12
  }
}
```

判定：

- `index.db` 不存在或打不开：`blocker`。
- `story_events` 缺失：`warning` 或 `blocker`，取决于当前是否已经有 accepted commit。
- `vectors.db` 缺失：`warning`，RAG 可降级 BM25。
- `vectors` 行数为 0：`warning`。

#### 6.5.5 Reference / CSV 文件

检查：

- `references/csv/*.csv` 是否存在。
- 必要 CSV 表头是否符合预期。
- 题材别名、题材与调性推理、反模式等核心表是否可读。
- 明显占位符是否残留。

判定：

- 核心 CSV 不可读或表头缺失：`warning`。
- 会导致 story-system 无法生成 MASTER_SETTING 的缺失：`blocker`。

### 6.6 系统 / 配置检查

#### 6.6.1 Python 依赖

检查：

- 当前 Python 版本。
- `scripts/requirements.txt` 是否存在。
- 核心包是否可 import。

首批核心包：

```text
pydantic
numpy
requests
fastapi
uvicorn
watchdog
```

判定：

- 运行 CLI 必需包缺失：`blocker`。
- Dashboard 专用包缺失：`warning`，除非用户正在运行 dashboard skill。

#### 6.6.2 RAG 配置

默认模式检查：

- `.env` / 环境变量是否能读到 embedding 配置。
- embed base_url / model 是否配置。
- embed api_key 是否存在。
- rerank base_url / model / api_key 是否存在。
- `vectors.db` 是否存在且有数据。
- 当前推断 RAG 模式：`full` / `embed_only` / `bm25_only`。

`--deep` 模式才检查：

- embed API 是否真实可调用。
- rerank API 是否真实可调用。
- API 返回维度是否与已有 vectors 兼容。

判定：

- 缺 RAG key：`warning`，必须明确说明会降级到 BM25。
- API 连通失败：`warning` 或 `blocker`，取决于用户是否要求必须语义检索。
- base_url / model 明显空缺：`warning`。

#### 6.6.3 Dashboard / Node

检查：

- `dashboard/frontend/dist/index.html` 是否存在。
- dashboard 后端模块是否能 import。
- `dashboard/requirements.txt` 是否存在。
- `dashboard/frontend/package.json` 是否存在。

默认不检查：

- 不自动 `npm install`。
- 不自动启动服务。
- 不默认检查 localhost 端口。

判定：

- dist 缺失：`warning`，提示重新 build。
- FastAPI 依赖缺失：`warning`。

### 6.7 输出格式

每条检查必须包含：

- `id`：稳定错误码，方便测试和 UI 展示。
- `status`：`ok` / `fail` / `warn` / `skip`。
- `severity`：`blocker` / `warning` / `info`。
- `path`：相关文件路径，没有则为空。
- `expected`：预期状态。
- `actual`：实际状态。
- `impact`：对用户有什么影响。
- `repair`：修复命令或人工修复建议。

```json
{
  "ok": false,
  "project_root": "...",
  "mode": "default",
  "phase": "chapter_committed",
  "expected_profile": "after_commit",
  "blocking_count": 1,
  "warning_count": 2,
  "expected_files": {
    "required": [".webnovel/state.json", ".story-system/commits/chapter_001.commit.json"],
    "not_expected_yet": []
  },
  "checks": [
    {
      "id": "db.index.missing_table",
      "status": "fail",
      "severity": "blocker",
      "path": ".webnovel/index.db",
      "expected": "table story_events exists",
      "actual": "table missing",
      "impact": "无法确认 accepted commit 的事件链是否完成投影",
      "repair": {
        "command": "webnovel.py projections replay --from 1 --to latest --writers index",
        "manual": "如果 replay 尚未实现，先重新执行最近章节的 chapter-commit 或从备份恢复 index.db"
      }
    }
  ],
  "recommended_actions": [
    {
      "command": "webnovel.py rag stats",
      "reason": "vectors.db missing; semantic retrieval will fall back to BM25",
      "severity": "warning"
    }
  ]
}
```

### 6.8 错误码命名

错误码按域划分：

```text
project.root.invalid
project.phase.unknown
project.expected_file.missing
project.structure.missing_dir
story.master.missing
story.commit.invalid_json
story.commit.invalid_status
projection.status.failed
projection.file.missing
db.index.unreadable
db.index.missing_table
db.vector.empty
rag.embed.key_missing
rag.embed.api_unreachable
python.import_missing
dashboard.dist_missing
reference.csv.invalid_header
artifact.schema_error
```

### 6.9 文件落点

- `webnovel-writer/scripts/data_modules/doctor.py`
- `webnovel-writer/scripts/data_modules/project_phase.py`
- `webnovel-writer/scripts/data_modules/project_status.py`
- `webnovel-writer/scripts/data_modules/webnovel.py`
- `webnovel-writer/skills/webnovel-doctor/SKILL.md`
- `webnovel-writer/scripts/data_modules/tests/test_doctor.py`
- `webnovel-writer/scripts/data_modules/tests/test_project_phase.py`
- `webnovel-writer/scripts/data_modules/tests/test_project_status.py`
- `docs/guides/commands.md`

### 6.10 验收

- 空项目返回 `ok=false`，但不写任何文件。
- init 刚结束时能识别 `phase=init_scaffolded` 或 `phase=init_ready`，并返回该阶段的 `expected_files`。
- init 刚结束时缺 commit / summary / memory / vectors.db 不得返回 blocker。
- init 刚结束时缺 `state.json`、`设定集/世界观.md`、`大纲/总纲.md` 必须返回 blocker 或 warning，并给出补救命令。
- `MASTER_SETTING.json` 在 `init_scaffolded` 阶段缺失是 warning，在 plan/write 阶段缺失是 blocker。
- 正常项目返回 `ok=true`，并显示 `index.db` / `vectors.db` 的关键表和行数。
- 缺 `state.json` 返回 `project.structure` 或 `projection.file` 类 blocker。
- `index.db` 缺关键表时返回稳定错误码、影响说明和修复建议。
- `vectors.db` 缺失或为空时返回 warning，并明确说明 RAG 会降级到 BM25。
- 缺 RAG key 时返回 warning，不阻断普通写作。
- Python 必需包缺失时返回 blocker，并提示安装 `scripts/requirements.txt`。
- Dashboard dist 缺失时返回 warning，并提示 build 命令。
- latest commit projection failed 时返回 actionable command。
- 默认模式不联网、不安装依赖、不启动服务、不写文件。
- `--deep` 模式可进行 RAG API ping，但必须明确标记为 deep check。
- `preflight` 仍可运行；其结果与 doctor 的快检部分不冲突。
- 所有中文路径和中文文件读取在 Windows 下使用 UTF-8，不因默认 GBK 失败。

---

## 7. Phase 2：章节 Runtime Gates

### 7.1 目标

不重造一套 workflow/resume 系统。把 `/webnovel-write` 中最容易出错的关键边界下沉为批量校验 gate，过程顺序由 Claude Code Todo 约束。

实施顺序上，Runtime Gates 必须依赖 Artifact Validator 的统一错误语义；本节描述 gate 设计，不代表先于 validator 开工。

### 7.2 新增模块

建议新增 gate 外壳，但 `prewrite` 必须包装或迁移现有 `PrewriteValidator`，不得重写一套占位符和合同判断逻辑：

```text
webnovel-writer/scripts/data_modules/write_gates/
  __init__.py
  prewrite.py
  precommit.py
  postcommit.py
```

已有复用点：

- `webnovel-writer/scripts/data_modules/prewrite_validator.py`
- `webnovel-writer/scripts/data_modules/tests/test_prewrite_validator.py`

### 7.3 Gate 设计

不写 `.workflow.json`，不维护 step state。每次 gate 根据现有项目文件和 artifacts 现场计算结果。

统一输出：

```json
{
  "schema_version": "write-gate/v1",
  "chapter": 12,
  "stage": "precommit",
  "ok": false,
  "blocking": [
    {
      "type": "pending_disambiguation",
      "detail": "disambiguation_result.pending is not empty"
    }
  ],
  "warnings": [],
  "artifacts": {
    "review_result": ".webnovel/tmp/review_results.json",
    "fulfillment_result": ".webnovel/tmp/fulfillment_result.json",
    "disambiguation_result": ".webnovel/tmp/disambiguation_result.json",
    "extraction_result": ".webnovel/tmp/extraction_result.json"
  }
}
```

### 7.4 Gate 职责

runtime gate 负责：

- 校验必要文件存在。
- 校验 JSON schema。
- prewrite 阶段复用 `PrewriteValidator`。
- 判定 blocking issue。
- 判定是否允许进入下一自然阶段。
- 输出明确的失败原因和建议命令。

runtime gate 不负责：

- 代替 LLM 起草正文。
- 代替 Agent 做审查。
- 自动决定用户裁决。
- 记录每一步进度。
- 替代 Claude Code Todo / 会话恢复能力。

### 7.5 CLI 子命令

```bash
webnovel.py write-gate --chapter N --stage prewrite --format json
webnovel.py write-gate --chapter N --stage precommit --format json
webnovel.py write-gate --chapter N --stage postcommit --format json
```

### 7.6 Skill 改动

`webnovel-write/SKILL.md` 改为：

1. 使用 Claude Code Todo 建立本章流程清单。
2. 调 `write-gate --stage prewrite`，通过后才写。
3. 调 context-agent。
4. 起草正文。
5. 调 reviewer。
6. blocking issue 由 Todo 记录并裁决 / 定点修复。
7. 润色后调 data-agent。
8. 调 `write-gate --stage precommit`，通过后才提交。
9. 调 chapter-commit。
10. 调 `write-gate --stage postcommit`，通过后才宣布完成。

### 7.7 验收

- 缺 `review_results.json` 时不允许进入 commit。
- reviewer 有 blocking issue 时 `precommit.ok=false`。
- disambiguation pending 非空时 `precommit.ok=false`。
- projection failed 时 `postcommit.ok=false`。
- gate 调用次数控制在每章 2-3 次，不做逐步 mark。

---

## 8. Phase 3：Artifact Validator

### 8.1 目标

统一校验所有 agent 产物，避免字段名漂移、包错外层、缺 required 字段。

### 8.2 校验对象

- `review_results.json`
- `fulfillment_result.json`
- `disambiguation_result.json`
- `extraction_result.json`
- `chapter_XXX.commit.json`
- `projection_status`

权威 schema 来源：

- `review_results.json`、`fulfillment_result.json`、`disambiguation_result.json`、`extraction_result.json` 默认以 `chapter_commit_schema.py` 中 commit 所需的 Pydantic model 为准。
- `review_schema.py` 和 `entity_linker.py` 中同名 / 近名模型只作为上游工具局部模型，不作为 commit artifact 的最终权威。
- 如需兼容上游局部模型输出，必须在 `artifact_validator.py` 显式做 normalize，并在输出中标注兼容来源。

### 8.3 输出错误分类

```text
schema_error
missing_artifact
blocking_review
missed_outline_node
pending_disambiguation
commit_rejected
projection_failure
unsafe_project_root
placeholder_blocker
```

### 8.4 文件落点

- `webnovel-writer/scripts/data_modules/artifact_validator.py`
- `webnovel-writer/scripts/data_modules/tests/test_artifact_validator.py`
- `webnovel-writer/scripts/data_modules/write_gates/precommit.py`

### 8.5 验收

- `extraction_result.json` 外层包成 `{"extraction": ...}` 时返回 schema_error。
- `state_deltas` 使用旧字段名时能兼容或给出明确诊断。
- `disambiguation_result.pending` 非空时阻断 commit。
- `fulfillment_result.missed_nodes` 非空时阻断 accepted commit。
- `ReviewResult` / `DisambiguationResult` 等同名模型不再各自漂移，validator 明确以 commit artifact schema 为准。

---

## 9. Phase 4：Commit 不可变与 Projection Log 外置

### 9.1 当前问题

当前 `ChapterCommitService` 会：

1. build commit。
2. persist commit。
3. apply projections。
4. 将 `projection_status` 写回 commit。

这让 commit 同时承担“事实记录”和“投影执行日志”两个职责。

### 9.2 目标

将事实与投影执行状态拆开：

```text
.story-system/commits/chapter_012.commit.json     # 不可变事实
.webnovel/projection_log.jsonl                    # 投影执行日志
index.db.projection_runs                           # 可查询投影状态
```

### 9.3 迁移策略

Phase 4 不强制立刻删除 commit 内 `projection_status`，采用双写过渡：

1. 保留 commit 内 projection_status 兼容 Dashboard。
2. 新增 projection log。
3. Dashboard / doctor 优先读取 projection log。
4. 后续版本再将 commit 内 projection_status 标记 deprecated。

### 9.4 Projection Run Schema

```json
{
  "run_id": "ch012-20260604T102233",
  "chapter": 12,
  "commit_path": ".story-system/commits/chapter_012.commit.json",
  "commit_hash": "sha256:...",
  "writer": "memory",
  "status": "done",
  "started_at": "...",
  "finished_at": "...",
  "error": "",
  "retry_of": ""
}
```

### 9.5 文件落点

- `webnovel-writer/scripts/data_modules/projection_log.py`
- `webnovel-writer/scripts/data_modules/chapter_commit_service.py`
- `webnovel-writer/scripts/data_modules/tests/test_projection_log.py`
- `webnovel-writer/dashboard/app.py`
- `webnovel-writer/scripts/data_modules/story_runtime_health.py`

### 9.6 验收

- 每个 writer 执行后都有 projection log。
- 单 writer failed 不影响其他 writer 记录。
- doctor 能指出 failed writer 和建议重跑命令。
- commit 文件 hash 在 projection log 中可追溯。

---

## 10. Phase 5：Projection Replay / Retry

### 10.1 目标

投影失败时可以只补跑失败 writer，尤其是 vector / RAG 等外部依赖。

### 10.2 CLI

```bash
webnovel.py projections status --chapter N
webnovel.py projections retry --chapter N --writer vector
webnovel.py projections retry-failed --chapter N
webnovel.py projections replay --from 1 --to 20 --writers state,index,summary
```

### 10.3 约束

- replay 只能读取 accepted commit。
- rejected commit 只允许 state writer 更新状态。
- writer 必须幂等。
- retry 不得修改 commit 事实内容。

### 10.4 文件落点

- `webnovel-writer/scripts/data_modules/projection_runner.py`
- `webnovel-writer/scripts/data_modules/event_projection_router.py`
- projection writer 幂等性测试

### 10.5 验收

- 删除 `summaries/chapter_012.md` 后 retry summary 可恢复。
- vector API key 缺失时 vector failed，其余 writer done。
- 配置 key 后 retry vector 只补 vector。
- replay 1-5 后 state/index/summary 与 commit 链一致。

---

## 11. Phase 6：Skill / Agent 契约补强

### 11.1 Skill Frontmatter

8 个现有 Skill 的 `description` 要从单句说明升级为召回规则：

- 何时使用。
- 典型触发词。
- 不适用场景。
- 是否有副作用。

示例：

```yaml
description: Use when the user wants to draft, continue, rewrite, or commit a numbered webnovel chapter. Runs the full context -> draft -> review -> polish -> fact extraction -> chapter commit workflow. Do not use for pure status queries, project initialization, or dashboard-only requests.
```

### 11.2 Agent Frontmatter

所有 agent 补齐：

- `name`
- `description`
- `tools`
- `model` 可选
- `output_schema`
- `failure_statuses`

### 11.3 Agent 分工调整

现有：

- `context-agent`
- `reviewer`
- `data-agent`
- `deconstruction-agent`

建议新增或拆分：

- `continuity-reviewer`：设定 / 时间线 / 人物状态 / 伏笔合规。
- `style-reviewer`：文风 / AI 味 / 句式重复 / 排版。
- `reader-pull-reviewer`：爽点 / 钩子 / 微兑现 / 追读力。

短期可以先不新增文件，而是在 `reviewer` 输出 schema 中拆维度；中期再拆 agent。

### 11.4 验收

- prompt integrity 测试确认所有 Skill 有足够长的 description。
- agent 输出 schema 可被 artifact validator 校验。
- data-agent 文档中仍明确“不直接写 state/index/summaries/memory”。

---

## 12. Phase 7：Behavior Evals

### 12.1 目标

学习 Superpowers 的 headless 行为测试思路，补上“插件是否按协议执行”的验证层。

### 12.2 Eval 类型

新增：

```text
evals/
  skill-triggering/
  workflow-behavior/
  agent-output-schema/
  continuity-conflict/
  memory-commit/
```

### 12.3 首批用例

| Eval | 目标 |
|---|---|
| init_project_safety | 不在插件目录生成项目，不污染 canon |
| plan_outputs_executable_chapter_tasks | 章纲包含目标情绪、人物变化、伏笔、禁写事项 |
| write_blocks_on_review_blocking_issue | blocking issue 不进入 commit |
| data_agent_never_writes_projection | data-agent 只产出 artifacts |
| commit_drives_projection | accepted commit 后 projection writer 被触发 |
| query_falls_back_explicitly | 主链缺失时 query 明确说明 fallback |
| dashboard_readonly | Dashboard API 不提供写接口 |

### 12.4 Runner

先做轻量 runner：

```bash
python webnovel-writer/scripts/run_behavior_evals.py --case write_blocks_on_review_blocking_issue
```

如果本地没有 Claude Code CLI，则 eval 可跳过 transcript 测试，只跑 artifact fixture 测试。

### 12.5 验收

- 每个 Skill 至少有 1 个 eval。
- `webnovel-write` 至少覆盖成功链路和 blocking 链路。
- eval 输出 JSON 报告，包含 pass/fail/reason/artifacts。

---

## 13. Phase 8：Manifest / Marketplace / 发布治理

### 13.1 目标

防止插件元数据、README、marketplace、version 之间漂移。

### 13.2 校验脚本

新增：

```bash
python webnovel-writer/scripts/validate_plugin_package.py
```

检查：

- 根 `.claude-plugin/marketplace.json` 存在。
- 插件 `.claude-plugin/plugin.json` 存在。
- marketplace version 与 plugin.json version 一致。
- README / 现有 CI 使用的版本位置与 plugin.json 一致；不得新增一套与既有 Plugin Version Check 冲突的 README 版本规则。
- 每个 `skills/*/SKILL.md` 有 frontmatter。
- 每个 `agents/*.md` 有 frontmatter。
- LICENSE 存在。
- Dashboard dist 存在。
- `scripts/requirements.txt` 与根 `requirements.txt` 可解析。
- docs 命令表与实际 Skill 名称一致。

### 13.3 可选 manifest 增强

如 Claude Code manifest 支持，可补：

- `commands`
- `agents`
- `hooks`
- `mcpServers`
- user config schema
- screenshots / assets

如果当前宿主不需要显式声明，则保持默认目录发现，避免过度配置。

### 13.4 验收

- clean clone 后 validate 通过。
- 修改 version 任一处导致 validate 失败。
- 删除一个 Skill frontmatter 导致 validate 失败。
- 版本校验复用或对齐现有 CI 规则，不与 README 版本表 / badge 检查互相打架。

---

## 14. Phase 9：轻量 SessionStart Hook（可选）

### 14.1 目标

新增可选 hook，在会话启动、resume、clear、compact 时提示项目状态。该 hook 是状态观察器，不是状态机。

### 14.2 输出

```text
Webnovel Writer initialized.
  project: 灵石庄
  story runtime: mainline ready, latest chapter 12 accepted
  projections: 4 done, 1 failed(vector)
  rag: BM25 fallback; EMBED_API_KEY missing
  next: run /webnovel-doctor for details
```

### 14.3 约束

- 只读。
- 不安装依赖。
- 不写任何文件。
- 输出不超过 8 行。
- 正常状态下只输出摘要，不输出完整 JSON。
- 失败时给出一个下一步命令，不展开长诊断。
- 可通过环境变量关闭：

```text
WEBNOVEL_DISABLE_SESSION_HOOK=1
```

### 14.4 文件落点

- `webnovel-writer/hooks/hooks.json`
- `webnovel-writer/hooks/session_start.py`
- `webnovel-writer/.claude-plugin/plugin.json` 或默认 hook 发现路径
- `docs/operations/operations.md`

### 14.5 验收

- 无项目根时不报错，只提示未绑定项目。
- 有项目根时调用 `project-status --format summary` 或 doctor summary。
- 设置 disable env 后无输出。
- resume 后能刷新 latest chapter / projection 状态。
- 输出不会超过 1000 字符。

### 14.6 Skill-scoped 预检 Hook（可选）

对 `/webnovel-write` 这类高风险 skill，可以在 skill frontmatter 中挂轻量 hook：

- `PreToolUse(Bash)`：对直接运行 `chapter_commit.py`、`webnovel.py chapter-commit` 或 projection 写入命令做 best-effort 提醒 / 兜底阻断。Bash 字符串解析不能作为唯一可靠保证，真正的强保证必须在 runtime gate 和 commit 入口中实现。
- `PreToolUse(Write|Edit)`：如果目标路径是 `.story-system/` commit、`.webnovel/state.json`、`index.db`、`memory_scratchpad.json` 等 projection 产物，则要求走 runtime 命令。
- hook 通过时必须静默；只在阻断时返回简短原因。

不建议把所有固定预检都放进 hook。推荐分层：

| 预检类型 | 放在哪里 |
|---|---|
| 新会话状态摘要 | plugin-level `SessionStart` hook |
| 是否能开始写本章 | `write-gate --stage prewrite` |
| 是否能提交本章 | `write-gate --stage precommit` |
| 是否能宣布完成 | `write-gate --stage postcommit` |
| 禁止绕过 runtime 写主链 | skill-scoped `PreToolUse` hook |
| 复杂修复建议 | `/webnovel-doctor` skill |

## 15. 推荐实施顺序

1. `project_phase` + `project-status` + `webnovel-doctor`：先建立统一阶段推导、短状态和只读自检基本盘。
2. `Artifact Validator`：统一错误语义。
3. `Runtime Gates`：用写前 / 提交前 / 提交后批量校验约束关键边界，其中 prewrite 复用 `PrewriteValidator`。
4. `Projection Log`：事实与投影日志解耦。
5. `Projection Retry / Replay`：补恢复能力。
6. `Skill / Agent 契约补强`：降低 prompt 漂移。
7. `Behavior Evals`：证明插件协议有效。
8. `Plugin Package Validator`：发布治理。
9. 可选 `SessionStart Hook`：只读状态提示。
10. 可选 `Skill-scoped PreToolUse Hook`：阻断绕过 runtime 的危险写入。

---

## 16. 验收总表

| 能力 | 验收标准 |
|---|---|
| Doctor | 能只读报告目录/文件/数据库完整性、RAG/Python/Dashboard 配置，并给出修复建议 |
| Project Status | 能从主链和 artifacts 推导当前章节阶段，不占用既有 `status_reporter.py` 语义，不写 workflow state |
| Runtime Gates | `/webnovel-write` 在写前、提交前、提交后三个自然边界有批量校验 |
| Validator | agent 产物 schema 漂移能被统一诊断 |
| Commit | commit 事实与 projection log 可分离追溯 |
| Replay | vector/summary 等投影失败后可单独 retry |
| Skills | 8 个 Skill description 足够路由，长知识按需加载 |
| Agents | agent 有工具范围、输出 schema、失败状态 |
| Evals | 每个 Skill 至少 1 个行为 eval |
| Package | manifest / marketplace / README / version 可校验 |
| Hook | 如果启用，SessionStart 只读短输出，PreToolUse 只做危险动作阻断 |

---

## 17. 风险

### 17.1 过度工程化

风险：为了学习优秀插件，把当前系统拆得太碎。
控制：先做 doctor / validator / runtime gates 三个高收益模块，不急着拆 37 个题材 Skill。

### 17.2 Hook 副作用

风险：hook 自动执行导致用户不信任插件。
控制：SessionStart hook 只读，PreToolUse hook 只阻断危险动作；所有修复和推进必须由 skill / runtime 显式触发。

### 17.3 Hook 状态机漂移

风险：如果 hook 自己写状态，可能与 commit / projection / Todo 产生三套真相。
控制：状态由共享 `project_phase` / `project-status` 现场推导；hook 不写状态；流程推进只由显式 skill / runtime 命令触发。

### 17.4 Commit 迁移破坏 Dashboard

风险：projection_status 外置后 Dashboard 读不到状态。
控制：先双写，Dashboard 优先读新 projection log，旧字段保留一个版本周期。

### 17.5 Eval 成本高

风险：headless Claude 行为 eval 慢且贵。
控制：分 fast fixture eval 和 slow transcript eval；CI 默认只跑 fast。

### 17.6 Skill 触发变化

风险：description 改长后触发行为变化。
控制：增加 skill-triggering eval，先验证再发布。

---

## 18. 不变量

无论如何重构，必须保持：

1. `.story-system/` 是主链真源。
2. accepted `CHAPTER_COMMIT` 是写后事实入口。
3. `.webnovel/state.json`、`index.db`、`summaries/`、`memory_scratchpad.json` 是 projection / read-model。
4. `data-agent` 不直接写 projection。
5. Dashboard 默认只读。
6. RAG key 缺失必须可降级到 BM25。
7. 用户项目文件不能写到插件目录。
8. hook 不是项目状态真源。
9. `webnovel.py status` 继续保留宏观创作健康报告语义，短状态使用 `project-status`。

---

## 19. 第一批可开工任务

1. 新增 `project_phase.py`，统一 doctor / project-status / gates 的 phase 推导。
2. 新增 `project_status.py`，注册 `project-status` 子命令，保留现有 `status` 转发到 `status_reporter.py`。
3. 新增 `doctor.py`，复用现有 `preflight` / `build_story_runtime_health()`。
4. 在统一 CLI 注册 `doctor` 子命令。
5. 新增 `/webnovel-doctor` Skill。
6. 新增 `artifact_validator.py`，先包装 `chapter_commit_schema.py` 中的 commit artifact Pydantic schema。
7. 给 `webnovel-write` 的四类 agent artifact 增加 validator 测试 fixture。
8. 新增 `write_gates/prewrite.py`、`write_gates/precommit.py`、`write_gates/postcommit.py`，其中 prewrite 包装 `PrewriteValidator`。
9. 修改 `webnovel-write/SKILL.md`，开始引用 `write-gate --stage prewrite/precommit/postcommit`，过程管理仍使用 Claude Code Todo。
10. 先审计 5 个 projection writer 的幂等性，再新增 `projection_log.py`。
11. 给 8 个 Skill 补 description。
12. 新增 `validate_plugin_package.py`，先对齐现有版本 CI，再校验 frontmatter / LICENSE / dist。
13. 新增可选 SessionStart hook，只注入 project-status summary。
14. 新增可选 skill-scoped PreToolUse hook，作为 best-effort 兜底提醒 / 阻断。

---

## 20. 最终判断

`webnovel-writer` 当前最大短板不是知识库不足，也不是题材模板不够，而是：

> 关键流程仍有一部分靠 Skill 文档和 Agent 遵守协议来保证。

本 spec 的核心就是把这些协议逐步变成 runtime 可验证机制：

- doctor 负责知道项目文件、数据库和系统配置是否完整可用；
- project-status 负责用统一 phase resolver 知道项目现在写到哪里；
- runtime gates 负责知道关键边界是否可继续；
- validator 负责知道产物是否可信；
- projection log 负责知道 read-model 是否同步；
- eval 负责证明 agent 真的按协议执行；
- package validator 负责发布物没有漂移。

做到这些，`webnovel-writer` 才会真正具备优秀 Claude Code 插件的工程稳定性。
