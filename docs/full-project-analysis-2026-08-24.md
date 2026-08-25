# webnovel-writer 全项目代码分析报告

> 审阅日期：2026-08-24
> 审阅范围：`projects/claude-plugins/webnovel-writer` 全部代码（207 个 Python 文件 / 约 5.66 万行，183 个 Markdown 文档）
> 审阅方式：4 组并行深度审阅（数据核心层 / 记忆与 RAG / 门禁与校验 / dashboard·hooks·模板体系）+ 入口层人工复核
> 关联文档：[code-review-2026-08-24.md](./code-review-2026-08-24.md)（上一轮针对近期修复的专项审阅）

---

## 目录

1. [项目概览](#1-项目概览)
2. [整体架构与目录结构](#2-整体架构与目录结构)
3. [各模块功能说明](#3-各模块功能说明)
4. [核心代码逻辑](#4-核心代码逻辑)
5. [依赖关系](#5-依赖关系)
6. [潜在问题清单](#6-潜在问题清单)
7. [优化建议与修复路线图](#7-优化建议与修复路线图)

---

## 1. 项目概览

### 1.1 定位

webnovel-writer 是一个 **Claude Code 插件形态的长篇网文创作系统**，版本 6.2.1（GPL-3.0）。它不是传统的"调用 API 写文"工具，而是一套围绕 Claude Code 的 **skills + agents + 数据链路 + RAG** 的工程化创作基础设施：

- **skills/**（7 个）：以 SKILL.md 形式提供斜杠命令级工作流（init / plan / query / write / review / deconstruct / dashboard）
- **agents/**（4 个）：context-agent、reviewer、data-agent、deconstruction-agent 四个权限最小化的子代理
- **scripts/**：约 200 个 Python 模块构成的本地数据引擎（状态管理、索引库、记忆系统、RAG、写作门禁、运行台账）
- **dashboard/**：FastAPI 本地只读看板
- **hooks/**：PreToolUse 写保护守卫 + 会话生命周期钩子

### 1.2 设计哲学

从代码实现可以提炼出四条贯穿性设计原则：

| 原则 | 体现 |
|---|---|
| **合同真源分层** | `.story-system/` 是创作合同真源（MASTER_SETTING / 卷简报 / 审查合同），`.webnovel/` 是投影层（state.json / index.db / 向量库），dashboard 只读投影 |
| **SQLite-first** | v5.1 起实体/别名/状态变化/关系落 index.db，state.json 只保留轻量字段；事件日志 JSON 与 SQLite 双写镜像 |
| **fail-closed 门禁** | 写前/提交后三道 gate 收集全部 issue 后一次性返回，blocking 升级策略明确；流程级短路靠退出码 + SKILL.md 纪律条款 |
| **降级可用** | RAG embedding 失败降级 BM25、rerank 失败回退 RRF 排序、外部依赖全部可缺省 |

---

## 2. 整体架构与目录结构

```
webnovel-writer/
├── .claude-plugin/plugin.json        # 插件清单（v6.2.1）
├── README.md
├── sitecustomize.py                  # Windows UTF-8 环境兜底
├── pytest.ini / requirements.txt     # 测试配置（根级 requirements 为空壳）
├── docs/
│   ├── architecture/overview.md      # 架构总览文档
│   └── code-review-2026-08-24.md     # 上轮修复专项审阅
└── webnovel-writer/                  # 插件主体
    ├── scripts/
    │   ├── webnovel.py               # CLI 统一入口壳（转发 data_modules/webnovel.py）
    │   ├── security_utils.py         # 原子写/FileLock（顶层副本）
    │   ├── review_pipeline.py        # Step3 审查结果处理
    │   ├── run_logger.py             # run-log 日志器
    │   ├── reference_search.py       # CSV 参考表检索
    │   └── data_modules/             # ★ 核心包（约 150+ 模块）
    │       ├── webnovel.py           # CLI 实现（argparse 子命令注册表）
    │       ├── config.py             # DataModulesConfig 全局配置
    │       ├── state_manager.py      # state.json 门面（1511 行）
    │       ├── index_manager.py      # index.db DDL+CRUD（组合 5 个 mixin）
    │       ├── sql_state_manager.py  # SQL 状态管理封装
    │       ├── chapter_commit_service.py / chapter_commit_schema.py
    │       ├── projections.py / state_projection_writer.py /
    │       │   vector_projection_writer.py / index_projection_writer.py
    │       ├── event_log_store.py    # 事件日志（JSON+SQLite 双写）
    │       ├── story_contracts.py / story_contract_schema.py
    │       ├── story_system_engine.py # 题材路由→合同种子
    │       ├── chapter_outline_loader.py # 大纲解析/截断
    │       ├── write_gates/{prewrite,precommit,postcommit}.py
    │       ├── prewrite_validator.py / artifact_validator.py
    │       ├── timeline_check.py     # 时间线程序化校验
    │       ├── run_ledger.py         # 运行台账（断点续跑计划）
    │       ├── doctor.py             # 体检聚合（38KB）
    │       ├── rag_adapter.py        # ★ 自建向量库+BM25+RRF+Rerank（1600+ 行）
    │       ├── context_ranker.py / context_manager.py
    │       ├── runtime_sources.py    # 运行时素材源
    │       ├── memory/               # 记忆系统（orchestrator/store/schema/
    │       │                         #   compactor/budget/bootstrap/exporter…）
    │       └── tests/                # 76 个测试文件
    ├── dashboard/
    │   ├── app.py                    # FastAPI 应用
    │   ├── server.py                 # uvicorn 启动器
    │   ├── path_guard.py             # 路径安全守卫
    │   └── static/                   # 前端资源
    ├── hooks/
    │   ├── hooks.json                # PreToolUse/SessionStart 等注册
    │   └── guard_runtime_write.py    # 运行时写守卫
    ├── skills/                       # 8 个 SKILL.md 工作流
    ├── agents/                       # 4 个 subagent 定义 + evals 夹具
    ├── references/                   # 共享参考层（genre-profiles、CSV 9 张表、
    │                                 #   taxonomy、shared/、index/ 导航图）
    └── templates/                    # 输出模板 + genres/ 39 个题材模板
```

### 2.1 数据流总览

```
init:  story-system-engine → .story-system 合同种子（schema 校验后落盘）
       ↓
plan:  大纲加载(chapter_outline_loader) → 时间线校验(timeline_check)
       ↓
write: write-gate prewrite → context-agent(六层素材源+RAG) → draft
       → reviewer agent → review-pipeline(解析/metrics/报告)
       → write-gate precommit → chapter-commit-service
       → 三路投影(state/vector/index writer) → postcommit gate → backup
       ↓
全程:  run-ledger 台账记录 → write-resume 断点续跑计划
       hooks 守卫拦截对 .story-system/commits 的绕过写入
```

---

## 3. 各模块功能说明

### 3.1 CLI 入口层（scripts/webnovel.py + data_modules/webnovel.py）

入口壳仅 918B，实际实现位于 `data_modules/webnovel.py`。argparse 注册了 29 个转发目标脚本与大量子命令（memory-contract / index / knowledge / state / write-gate / run-ledger / doctor 等）。`cmd_write_gate` 以退出码 0/1 表达门禁结果，是流程短路的唯一强制点。

### 3.2 数据核心存储层

| 模块 | 功能 |
|---|---|
| `security_utils.py` | 原子写（tmp+replace）、FileLock、备份机制；存在 `create_secure_file` 直写路径与 `atomic_write_json` 双入口 |
| `state_manager.py`（1511 行） | state.json 读写门面。核心是 `save_state()`：FileLock 内重读磁盘最新 state → 只合并本实例 pending 增量 → 原子写 → 同步 SQLite（失败恢复 pending 快照重试）。章节状态机单调递进不可回退 |
| `index_manager.py` + 4 个 mixin | index.db 全部 DDL 与 CRUD。IndexManager 组合 chapter/entity/debt/reading/observability 五个 mixin；表演进靠 `CREATE TABLE IF NOT EXISTS` + 手工 ALTER 补列，无 schema_version 表 |
| `chapter_commit_service.py` | 提交编排：正文落盘 → artifact 校验 → 三路投影 → 台账记录 |
| `projections.py` + 3 个 writer | state 投影（按 committed 章节字数重算 total_words）、向量投影（chunk 化入 RAG 库）、index 投影（每次新建 IndexManager） |
| `event_log_store.py` | 事件日志 JSON 权威 + SQLite 镜像（INSERT OR IGNORE 幂等），统一连接上下文管理器 |
| `story_contracts.py` | `.story-system` 合同持久化：pydantic 校验后才落盘（P1-1 修复）、STORY-SYSTEM 标记块替换写 markdown |

### 3.3 记忆系统（memory/）

- **orchestrator.py**：记忆读写编排入口
- **store.py**：Scratchpad 存储（FileLock 保护）
- **compactor.py**：窗口压缩，timeline 的 latest_chapter 取自现存条目
- **budget.py**：按 task_type 分配 working/episodic/semantic 三层数量预算（余数补齐保证总和恒等）
- **bootstrap.py**：首次启用时从 IndexManager 回填角色状态/关系/伏笔到 open_loop
- **exporter.py**：面向 context 的导出

### 3.4 RAG 子系统（rag_adapter.py，1600+ 行）

自建方案，**不依赖第三方向量数据库**：

- 存储：SQLite vectors 表（float32 blob）+ BM25 倒排索引
- 检索：向量召回 + BM25 → RRF 融合 → 外部 Rerank API（Modal/OpenAI 兼容）→ 图谱增强混合
- 降级链：embed 失败的 chunk 以 `embedding=NULL` 仍入库（保 BM25）；查询 embed 失败置 degraded_mode 并输出 DEGRADED_MODE warning；rerank 失败回退 RRF 排序
- 规模自适应：≤500 chunk 全表扫描，超过则预筛选后局部算相似度
- schema 迁移：缺列时备份→重建表→复制共有列→失败自动恢复

### 3.5 写作门禁与校验层

| 模块 | 功能 |
|---|---|
| `write_gates/prewrite.py` | 写前检查：合同存在性、fulfillment_seed、前置章状态 |
| `write_gates/precommit.py` | 相位/正文/sha/artifact 四组检查一次跑完 |
| `write_gates/postcommit.py` | commit 文件整体校验（嵌套 artifact + projection_status）；partial 是 warning 级 |
| `artifact_validator.py` | 四份 commit artifact 的 JSON/schema/policy 三级校验；blocking_count>0 / missed_nodes / pending 升级 blocker |
| `chapter_commit_schema.py` | pydantic 模型（extra="allow" 宽容 LLM 输出；blocking_count 是唯一 strict 字段） |
| `timeline_check.py` | 解析时间线表格做三类校验：锚点非空、单调递增、倒计时 D-N 单调递减且单章跳跃 ≤1 |
| `prewrite_validator.py` | prewrite 的底层校验器 |
| `run_ledger.py` | 台账记录 + `build_write_resume_plan()` 断点续跑计划 + `verify_review_chapter_alignment`（sha256 对齐校验） |

issue 结构为五元组（severity/category/location/evidence/fix_hint），报告契约成熟。

### 3.6 dashboard/

FastAPI + uvicorn 本地服务。`path_guard.py` 做项目根约束防目录穿越；app.py 提供 SSE 流式、静态资源挂载；对 `.webnovel` 数据只读消费。

### 3.7 hooks/

`hooks.json` 注册 PreToolUse 守卫与会话钩子。`guard_runtime_write.py` 用正则拦截 Bash 直写受保护路径（`.story-system/commits/` 等），失败时 fail-open 放行。

### 3.8 skills / agents / references / templates

- **skills**：7 个工作流，write 主流程定义 step-env → step-context → step-draft → step-review → step-data → step-commit 六类节点；`--minimal` 模式支持内联覆盖写 no-review artifact
- **agents**：4 个 subagent 权限最小化（reviewer 不持 Write、data-agent 仅限三份 tmp artifact、deconstruction-agent 禁写），SubagentRun 信号段与 SKILL.md 汇总字段闭环
- **references**：共享层（genre-profiles、review-schema、CSV 9 张表约 550KB、导航图）+ 各 skill 私有层；已核对三个主 skill 引用表，**未发现悬空路径**
- **templates**：39 个题材模板 + 输出模板

---

## 4. 核心代码逻辑

### 4.1 save_state 并发合并（state_manager.py:229-421）

```
FileLock 获取
  → 重读磁盘最新 state（拿其他实例的更新）
  → 只合并本实例 pending 增量（_pending_progress_words_delta 等）
  → 原子写入
  → 同步 SQLite；失败则恢复 pending 快照重试
  → 以 disk_state 为准覆盖 self._state
```

这是对多 Agent 并发"读-改-写覆盖"的正确解法。但存在两处旁路破坏该模型（见问题清单 M1/M2）。

### 4.2 章节提交流水线（chapter_commit_service.py）

```
正文写入 → CommitArtifactModel 校验（拒绝 wrapper 包裹，强制顶层扁平）
  → policy 层升级判定（blocking_count>0 / missed_nodes / pending → blocker）
  → StateProjectionWriter（FileLock + 按 committed 章节字数投影 total_words）
  → VectorProjectionWriter（chunk 化 → rag store_chunks）
  → IndexProjectionWriter（每次新建 IndexManager.apply）
  → postcommit gate → backup
```

partial 投影状态是 warning 级（OK_PROJECTION_STATUSES = {done, skipped, partial}），P1-9b 决策贯彻到位。

### 4.3 RAG 混合检索（rag_adapter.py）

```
query → embed（失败→degraded_mode，纯 BM25 兜底）
  → 向量召回（≤500 全表扫 / >500 预筛选局部算）
  → BM25 召回 → RRF 融合
  → 外部 Rerank API（失败→直接用 RRF 序）
  → 图谱增强分支（余弦+先验分数）
```

### 4.4 断点续跑（run_ledger.py:247-348）

`build_write_resume_plan()` 基于 ledger 中已记录的 step（draft/review/data/commit/projection/backup 六枚举）推断下一个应执行的步骤，是 write-resume 的核心。其正确性完全依赖上游按正确枚举记账——这正是当前最大的契约断裂点（见 H4）。

### 4.5 大纲截断与结构解析（chapter_outline_loader.py）

`load_chapter_outline` 优先拆分章纲文件 → 卷纲段落 → ⚠️ 提示串；超预算走 `_truncate_outline_by_field_priority`（关键字段行全保留）。下游 `parse_chapter_plot_structure` 从清洗后的行提取 must_cover_nodes。两处均用行首裸标签正则匹配，构成一条贯穿性的静默失败链（见 H3）。

---

## 5. 依赖关系

### 5.1 第三方依赖（实际使用）

| 包 | 使用位置 | 用途 |
|---|---|---|
| fastapi + uvicorn | dashboard/app.py、server.py | Web 看板 |
| pydantic | chapter_commit_schema、story_contract_schema、schemas、amend_proposal_schema、story_event_schema、artifact_validator | 合同/artifact schema 校验 |
| filelock | security_utils、state_manager、state_projection_writer、memory/store | 跨进程文件锁 |

**注意**：根目录 `requirements.txt` 为空壳，真实依赖分散在 `webnovel-writer/scripts/requirements.txt` 与 `webnovel-writer/dashboard/requirements.txt`，且未见版本锁定（无 lock 文件）。

### 5.2 内部依赖要点

- `data_modules/*` 大量使用"try 相对导入 except ImportError 回退 scripts.*"的双模式导入，兼容脚本直跑与包内调用两种场景
- `story_system_engine.py` 依赖 scripts 顶层的 `reference_search.py`（非包内），形成跨层引用
- `story_contracts.py` 反向依赖 `chapter_outline_loader.volume_num_for_chapter_from_state`
- StateManager 直接访问 `SQLStateManager._index_manager` 私有成员（封装击穿，多处）
- stdlib 之外零硬依赖：RAG 的 embedding/rerank 是 HTTP API，缺失时全链路可降级

### 5.3 数据依赖

```
.story-system/（合同真源） ← write_gates ← skills/webnovel-write
.webnovel/state.json       ← state_manager ← 所有投影 writer
.webnovel/index.db         ← index_manager / event_log_store / rag vectors
大纲/*.md                  ← chapter_outline_loader / timeline_check
references/csv/*.csv       ← reference_search ← story_system_engine
```

---

## 6. 潜在问题清单

严重度定义：**高** = 崩溃/数据错误/核心功能失效；**中** = 特定条件下功能受损或性能显著劣化；**低** = 边界缺陷/可维护性问题。

### 6.1 高危（H）

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| H1 | **SQLite 连接未设 WAL/busy_timeout**。index_manager.py:629、event_log_store.py:26、vector_projection_writer.py:88 三处独立 `sqlite3.connect`，默认 journal=DELETE + busy_timeout=0。任一进程持写锁时另一进程立即抛 `database is locked`。项目自称"多 Agent 并行"，这是并发第一爆点 | index_manager.py:629 等 | 多 Agent 同时跑时随机崩溃 |
| H2 | **total_words 双轨制互相覆盖**。StateProjectionWriter 按 committed 章节文件字数投影，StateManager.update_progress 按 data-agent 上报增量累加，两条链路都写 `progress.total_words`，互相覆盖且增量缓存误差永不自愈 | state_manager.py:285 vs 663-664 | 字数统计不可信 |
| H3 | **大纲关键字段裸标签正则漏匹配 markdown 变体**。`^{label}\s*[：:]` 无法匹配 `**必须覆盖节点**：`、`### 必须覆盖节点`、列表加粗等真实写法；`_clean_plot_line` 剥列表符但不剥 `**`。截断与结构解析两处同时失效 → must_cover_nodes 静默为空 → fulfillment 审查形同虚设 | chapter_outline_loader.py:182-185, 338 | 大纲覆盖检查空转 |
| H4 | **SKILL 步骤节点名与 record-write-step 枚举双轨无映射**。SKILL.md 定义 step-env/step-context/step-draft/step-review/step-data/step-commit，CLI 枚举只有 draft/review/data/commit/projection/backup（run_ledger.py:35，未知值 raise ValueError）。按文档字面执行必触发报错；step-context 失败无法留痕，write-resume 无法从 context 断点续跑 | skills/webnovel-write/SKILL.md:299-304,317 vs run_ledger.py:35 | 台账记录必错、断点续跑缺口 |
| H5 | **timeline_check 未接入 prewrite gate**。模块自身校验逻辑完整，但 write_gates 内零引用——文档承诺的 plan 阶段兜底在写作期完全失效 | timeline_check.py vs write_gates/ | 时间线错误无人拦截 |
| H6 | **guard_runtime_write 重定向正则永不匹配**。`\b>\b` 中 `\b` 在 `>` 两侧永远无法成立（`>` 是非词字符），Bash 直写 `.story-system/commits/` 的最常见形态未被拦截 | guard_runtime_write.py:108 | 写保护被绕过 |
| H7 | **rag vector_search 直连路径 O(N) 全表扫描**。`strategy="vector"` 不走预筛选分支，大书（>1 万 chunk）单次查询需反序列化全部 float32 blob 逐行 Python 算余弦 | rag_adapter.py:596-669 | 大项目检索秒级卡顿 |

### 6.2 中危（M）

| # | 问题 | 位置 |
|---|---|---|
| M1 | `_save_state()` 绕过锁与 pending 合并整份覆写（backup=False），public-ish 方法一旦被调用即撕开并发窗口 | state_manager.py:714-717 |
| M2 | `update_progress()` 直改内存 total_words，与锁内 pending 合并语义分叉，save 后内存先行增量可能被静默回退 | state_manager.py:657-664 |
| M3 | 跨层私有访问泛滥：`self._sql_state_manager._index_manager.record_appearance(...)` 等，封装击穿 | state_manager.py:505/556/573/744 |
| M4 | `upsert_entity` SELECT-then-UPDATE/INSERT 非原子（无 BEGIN IMMEDIATE）；UPDATE 分支不更新 first_appearance；浅合并致嵌套状态丢失 | index_entity_mixin.py:58-163 |
| M5 | `_validate_reading_power` 裸 `int()` 确认仍在：L66/L69 缺 try/except（同函数 L57 对 debt_balance 却有防护），怪值输入使 sanity check 自身崩溃 | index_reading_mixin.py:52-71 |
| M6 | `pay_debt` 读余额→计算→写回三步非原子，并发还款丢更新 | index_debt_mixin.py:338-433 |
| M7 | verify_review_chapter_alignment 的 sha256 字节级哈希对换行符/BOM 敏感，win32 环境误报率高，阻断正常提交 | run_ledger.py:76 |
| M8 | P1-8 防线系统性 fail-open：record_write_step 纯靠 LLM 自觉调用（review-pipeline 不自动落账）；review 非 completed 也放行 | run_ledger.py:193-196 |
| M9 | PrewriteValidator 读 state.json 无容错，state.json 损坏时 gate 以异常崩溃而非 fail-closed 报告 | prewrite_validator.py:23-25 |
| M10 | rerank 结果解析 `int(item.get("index", 0))`：畸形返回崩溃；缺省 0 静默锚定第 0 个候选污染排序；两处负数防御不一致 | rag_adapter.py:1106, 1315-1316 |
| M11 | store_chunks commit 失败仅记 error 不抛出，返回 stored 计数仍含未提交行 | rag_adapter.py:482-486 |
| M12 | rag `_get_conn` 无 WAL/timeout，Windows 并发读写 vectors.db 易 locked；每操作新建连接开销大 | rag_adapter.py:246-253 |
| M13 | memory bootstrap 逐条 upsert（全量 load+save），5000 条时约万次全文件重写；open_loop id 幂等不足；排序键 int() 遇字符串主键崩溃 | memory/bootstrap.py:56-177 |
| M14 | budget 只有条目数预算无 token/字符预算，working 层单条可达 800 字符，最坏远超预期 token 量 | memory/budget.py |
| M15 | dashboard 无 Host 校验（DNS rebinding 可达本地 API）、SQLite 连接非 ro | dashboard/app.py |
| M16 | 4 处 skill 用裸 `python`（无 `-X utf8`）解析 PROJECT_ROOT，Windows GBK 控制台中文路径可能 UnicodeDecodeError | webnovel-plan/SKILL.md:34 等 4 处 |
| M17 | hook 失败 fail-open 放行，守卫语义可被异常绕过 | hooks/guard_runtime_write.py |
| M18 | failed 前缀判定不统一：`"failed:"` 与 `"failed"` 两套前缀并存，行为碰巧一致但语义漂移已埋下 | artifact_validator.py:299 vs postcommit.py:91 |
| M19 | schema 全部 extra="allow"，LLM 字段拼写错误静默通过，只能靠 policy 层单个必填兜底 | chapter_commit_schema.py:61 |
| M20 | timeline_check 不支持中文数字天数（"第三天"静默跳过检查）；跨年边界存在误报路径；GBK 文件 read_text 直接崩 | timeline_check.py:36, 159, 121 |
| M21 | story_system_engine 别名子串包含匹配命中面过宽；CSV 行序即优先级的隐式契约无声明；reasoning 缺失静默降级 | story_system_engine.py:177, 297-302 |
| M22 | `_extract_outline_section` 只认 `###` + 半角冒号，其他排版整段提取失败返回 ⚠️ 提示串，易被下游当正文消费 | chapter_outline_loader.py:103-104 |
| M23 | `_init_db` 每次构造 IndexManager 全量跑几十条 DDL，commit 流程构造 2-3 次，DDL 风暴放大锁竞争 | index_manager.py:238-624 |
| M24 | compactor 的 timeline latest_chapter 取自现存条目而非真实最新章，窗口随压缩漂移 | memory/compactor.py:48-51 |
| M25 | run-log event 名无白名单校验，任意字符串可写入，日志命名漂移无约束 | run_logger.py:53-67 |
| M26 | `record_state_change` 向内存列表无限追加（v5.1 已声明该字段迁走），`config.max_state_changes` 截断配置完全未被使用 | state_manager.py:960-976 |
| M27 | SQLite 启用时仍向内存 entities_v3 写完整实体，与"state.json 不再维护 entities_v3"的声明矛盾，数据活不过下次 save 却占内存 | state_manager.py:814-835 |
| M28 | 锁超时抛裸 RuntimeError，CLI 层未捕获做结构化错误输出，调用方拿到 traceback | state_manager.py:420-421 |

### 6.3 低危与可维护性（L）

| # | 问题 | 位置 |
|---|---|---|
| L1 | security_utils 双入口：`create_secure_file` 直写路径与 `atomic_write_json` 并存，备份失败仅静默、restore 前不校验 JSON、单代 .bak 易被覆盖 | scripts/security_utils.py |
| L2 | 测试降级开关 `WEBNOVEL_TEST_RELAX_ATOMIC_REPLACE` 未限定 pytest 环境，生产误设即降级 | security_utils.py |
| L3 | 中文数字解析不支持"一百二十"以上及"廿/卅"，百章后大纲标题解析行为不一致 | chapter_outline_loader.py:119-128 |
| L4 | timeline `_YEAR_RE` 要求恰好 4 位数字，"历三千二百年"类写法全部漏检 | timeline_check.py:38 |
| L5 | 单字人名（len<2）被分词丢弃，不参与章节关键词打分 | story_system_engine.py:441 |
| L6 | anti_patterns 来源字段硬编码映射到"毒点"列，新增表需手工同步常量 | story_system_engine.py:104-109 |
| L7 | write 私有 writing/ 下 4 个文件仅约 310B，疑似占位空壳仍被引用表列出，浪费上下文窗口 | webnovel-write/references/writing/* |
| L8 | agents/evals 内嵌完整测试项目随插件分发，`.webnovel/state.json` 可能被 where 兜底逻辑误命中 | agents/evals/files/test-project/ |
| L9 | data-agent 置信度口径模糊：>0.8 自动采用与 pending 非空 needs_user_action 之间，0.5-0.8 区间是否进 pending 未定义 | data-agent.md:30 vs 118 |
| L10 | webnovel-review Step7 手动 update-state 写兼容投影，与 chapter-commit 自动推进并存，重跑 review 产生重复审查记录 | webnovel-review/SKILL.md:106-112 |
| L11 | graph_hybrid 分数混排：base_results 被 rerank relevance_score 覆盖，图谱先验增益可能被冲掉 | rag_adapter.py:1074-1110 |
| L12 | budget 余数分配逻辑与注释"语义层优先"不完全一致，属轻微偏差 | memory/budget.py:37-50 |
| L13 | 根目录 requirements.txt 为空壳，依赖分散两处且无版本锁定 | 仓库根 |
| L14 | README 称"Skills（斜杠命令）"，与新版权限体系 commands/skills 分离术语有歧义 | README.md |

---

## 7. 优化建议与修复路线图

### 7.1 P0 — 立即修复（影响正确性/稳定性）

1. **统一 SQLite 连接工厂**（修 H1/M12/M23）
   新建 `data_modules/db.py` 提供 `connect(db_path)`：`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON`，三处 connect 点全部替换；IndexManager 增加 DDL 初始化一次性标记或 schema_version 表。

2. **修复大纲标签匹配**（修 H3）
   在 `_clean_plot_line` 与截断匹配前统一剥离 markdown 修饰：`re.sub(r"\*+", "", text)` + 剥行首 `#{1,6}`；两处标签匹配抽成单一函数；补 `**必须覆盖节点**：` 变体回归测试。

3. **SKILL 节点名 ↔ ledger 枚举映射**（修 H4）
   推荐方案 (a)：在 SKILL.md 节点表后追加映射说明——step-env/step-context 不记 ledger（或扩枚举）、step-draft→draft、step-review→review、step-data→data、step-commit→commit+backup 两次调用。改动面最小；方案 (b) 扩展 WRITE_STEPS 枚举需同步 argparse choices + 全部测试。

4. **接入 timeline_check 到 prewrite gate**（修 H5）
   prewrite 增加时间线校验步骤，产出 warning/blocking issue，复用现有报告契约。

5. **修正守卫正则**（修 H6）
   `\b>\b` → `(?:^|\s)>(?:\s|$)` 或直接检测 `>>?` 操作符 + 目标路径组合；补 Bash 重定向绕过用例测试。

### 7.2 P1 — 短期（1-2 个迭代）

6. **total_words 单一真源**（修 H2/M2）：确定以 StateProjectionWriter 投影值为准，update_progress 只累积 pending 不直改内存；增加与 committed 字数的定期对账。
7. **safe_int 工具函数**（修 M5 及全链路裸 int()）：抽 `safe_int(value, default, strict=False)` 替换 runtime_sources/context_ranker/writer/index_reading_mixin 等处的裸转换。
8. **rerank 解析加固**（修 M10/M11）：抽 `_coerce_rerank_index(item, n)`（try int + 边界 + 负数防御）三处复用；store_chunks commit 失败改抛异常或扣减 stored 计数。
9. **sha256 归一化**（修 M7）：哈希前统一 `\r\n→\n`、剥 BOM；ledger 版本不匹配输出 warning 而非静默重置。
10. **state.json 旁路封堵**（修 M1/M26/M27）：删除或改造 `_save_state` 为锁内别名；record_state_change 不再写内存副本；SQLite 启用时跳过 entities_v3 内存写入。
11. **门禁 fail-closed 化**（修 M9/M17）：PrewriteValidator 读 state 包 try/except 转 error issue；hook 异常时默认 block 并输出原因（提供显式 opt-out 开关）。
12. **FAILED_PREFIX 常量化**（修 M18）：定义常量三处共用。
13. **dashboard 加固**（修 M15）：uvicorn 绑定 127.0.0.1 + Host 头校验中间件；只读连接以 `mode=ro` 打开 SQLite。

### 7.3 P2 — 中期（架构改善）

14. **SQLStateManager 公共 API 补齐**（修 M3）：为 StateManager 需要的操作提供公开方法，消除 `._index_manager` 私有访问。
15. **upsert_entity/pay_debt 原子化**（修 M4/M6）：BEGIN IMMEDIATE 包裹读-算-写；UPDATE 分支合并 first_appearance；深合并嵌套 dict。
16. **RAG 大表检索优化**（修 H7）：vector 直连路径统一走 chunk_id 预筛选；评估 sqlite-vss/faiss；degraded_mode 提前短路 vector 分支。
17. **memory bootstrap 批量化**（修 M13）：ScratchpadManager 批量 upsert；open_loop id 改内容 hash 保证幂等；排序键改 (chapter, 行序)；坏文件 try/except 跳过。
18. **预算双维度化**（修 M14）：条目数 + 字符/token 双预算，与 ranker 的 `_budget_text_list` 思路统一。
19. **timeline_check 增强**（修 M20）：天数解析复用中文数字解析器；(year, day) 二元组整体单调比较消除跨年误报；read_text 容错编码。
20. **story_system_engine 匹配收紧**（修 M21）：别名改全词/分词匹配并显式声明优先级列；reasoning 缺失注入 source_trace warning。
21. **run-log event 白名单**（修 M25）：建立 RUN_LOG_EVENTS 常量并在 run_logger 校验。
22. **skill 编码统一**（修 M16）：四处裸 `python` 统一加 `-X utf8`。

### 7.4 P3 — 卫生项

- 清理 writing/ 占位空壳文件（L7）；打包排除 evals 夹具（L8）；明确 0.5-0.8 置信度口径（L9）；移除 review 手动 update-state 兼容路径（L10）；根 requirements.txt 写明真实依赖或删除（L13）；README 术语澄清（L14）。

### 7.5 总体评价

该项目的**架构分层与设计成熟度显著高于同类插件**：合同真源/投影分层、权限最小化的 agent 体系、fail-closed 门禁报告契约、RAG 多级降级链都是亮点，76 个测试文件的覆盖意识也值得肯定。

主要短板集中在三类系统性问题上：

1. **并发基础设施欠账**——SQLite 连接参数、原子性、双轨写入，是"多 Agent 并行"宣称下的最大隐患；
2. **提示词契约与运行时契约的断裂**——SKILL 步骤命名双轨、timeline 断链、ledger 依赖自觉，属于"文档说一套、代码做一套"；
3. **文本解析的正则鲁棒性**——markdown 变体、编码、中文数字，在真实网文语料下会持续产生静默失败。

上述问题均为局部可修，按 P0→P3 路线推进即可，不需要伤筋动骨的重构。
