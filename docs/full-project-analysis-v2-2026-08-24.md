# webnovel-writer 全项目代码分析报告（v6.3.0-dev）

> 审阅日期：2026-08-24
> 分支：`fix/temp`（领先 origin/master 37 个提交）
> 审阅范围：全部源代码逐文件阅读，重点模块逐行验证
> 方法：入口层→数据核心层→门禁层→外围系统，按数据流向追踪

---

## 一、项目概览

webnovel-writer 是一个 Claude Code 插件形态的**长篇网文创作操作系统**。它不是简单的"调 API 写文"工具，而是一套围绕 LLM 的工程化创作基础设施：通过 skills 定义斜杠命令工作流、agents 实现权限最小化的子代理协作、scripts 层提供本地数据引擎、hooks 层实施运行时守卫。

当前版本基于上游 v6.2.1，本地已推进至 v6.3.0 开发态。近期提交集中在 P0-P2 级修复（并发安全、大纲截断、时间线校验、token 预算等），修复质量整体较高。

---

## 二、整体架构与目录结构

### 2.1 双仓库嵌套

```
外层仓库根（marketplace 清单）
└── webnovel-writer/           ← 内层插件本体
    ├── .claude-plugin/plugin.json
    ├── skills/                 ← 8 个技能（斜杠命令）
    ├── agents/                 ← 4 个子代理定义
    ├── hooks/                  ← 运行时守卫钩子
    ├── scripts/
    │   ├── webnovel.py         ← 统一 CLI 入口
    │   ├── data_modules/       ← 核心数据引擎（~200 模块）
    │   └── *.py                ← 顶层工具脚本
    ├── dashboard/              ← FastAPI 本地只读看板
    ├── references/csv/         ← 创作知识库 CSV
    ├── templates/genres/       ← 38 种题材模板
    └── templates/output/       ← 输出文档模板
```

### 2.2 设计哲学：合同真源分层

这是整个项目最核心的架构决策：

- **写前真源** = `.story-system/` 目录（MASTER_SETTING.json / 卷合同 / 章合同 / 审查合同）
- **写后真源** = accepted CHAPTER_COMMIT 事件
- **投影层** = `.webnovel/state.json`、`index.db`、`vectors.db`（只读模型，可重建）
- **知识库** = `references/csv/*.csv`（fallback-only，不覆盖章纲约束）

这一分层确保了即使投影层损坏也能从 commit 事件链完整重建。

---

## 三、各模块功能说明

### 3.1 Skills 层（8 个技能）

| 技能 | 职责 | 复杂度 |
|------|------|--------|
| `webnovel-init` | 初始化书项目（目录结构、state.json、模板选择） | 207 行 |
| `webnovel-plan` | 卷规划与章纲生成 | 218 行 |
| `webnovel-write` | 写章全流程：上下文→起稿→审查→润色→提交→备份 | **303 行**（最复杂） |
| `webnovel-review` | 章节质量审查（六维审查器） | 147 行 |
| `webnovel-query` | 项目状态查询 | 87 行 |
| `webnovel-doctor` | 项目体检与诊断 | 39 行 |
| `webnovel-dashboard` | 启动本地看板 | 78 行 |
| `webnovel-learn` | 作者风格学习与积累 | 44 行 |

其中 `webnovel-write` 是最核心的工作流技能，定义了严格的五步执行链和模式变体（默认/fast/minimal），并强制要求通过 Agent 工具调用指定 subagent。

### 3.2 Agents 层（4 个子代理）

| Agent | 权限 | 职责 |
|-------|------|------|
| **context-agent** | Read/Grep/Bash | 写前研究：加载合同树、组装写作任务书、校验上下文完整性 |
| **reviewer** | Read/Grep/Bash | 六维审查：爽点密度、一致性、节奏、OOC、连贯性、追读力 |
| **data-agent** | Read/Grep/Bash | 从正文提取实体/状态/关系/摘要等 commit artifacts |
| **deconstruction-agent** | Read/Bash | 拆书分析（参考文学习） |

每个 agent 的权限都严格最小化——只有读取和分析权限，没有写入权限。

### 3.3 Scripts/Data Modules 层（核心引擎）

#### 统一 CLI 入口（`webnovel.py` → `data_modules/webnovel.py`）

718 行的路由器，将约 30 个子命令分发到对应模块。设计亮点：
- 自动解析 project_root（支持显式传入、指针文件、全局注册表三级回退）
- 统一注入 `--project-root` 给下游模块，消除重复传参错误
- 兼容直跑脚本与包内调用两种导入方式

#### 状态管理层（`state_manager.py`，1450 行）

管理 `.webnovel/state.json` 的读写操作：
- 实体状态管理（EntityState dataclass：id/name/type/tier/aliases/attributes）
- 进度追踪（章节号、总字数、卷进度）
- 关系记录（Relationship dataclass）
- **FileLock 并发合并**：save 时先重读磁盘最新状态，只合并本实例 pending 增量，再原子写入
- 同步 SQLite：save 后同步到 index.db；失败则恢复 pending 快照重试

#### 索引管理层（`index_manager.py`，1377 行）

管理 `.webnovel/index.db`（SQLite）：
- 章节元数据索引（ChapterMeta：标题/位置/字数/角色/摘要）
- 场景索引（SceneMeta：起始行/结束行/位置/角色）
- 实体出场记录、别名索引（一对多）
- 状态变化日志、关系存储
- 追读力债务管理（chase_debt 表：债务产生/偿还/利息）
- 审查指标存储（review_metrics 表）
- 工具调用统计（tool_call_stats 表）

采用 Mixin 架构拆分为五个子模块（chapter/entity/debt/reading/observability）。

#### RAG 适配层（`rag_adapter.py`，1576 行）

封装向量检索全链路：
- 向量嵌入（调用 Modal API 或 OpenAI 兼容接口）
- 语义搜索（余弦相似度）
- BM25 关键词搜索
- 混合检索（向量 + BM25 → RRF 融合排序）
- 外部 Rerank API 重排
- 图谱增强分支（余弦 + 先验分数混合）
- **多级降级链**：embedding 失败→纯 BM25；rerank 失败→RRF 序直接用；auth 401→degraded_mode 标记

#### 上下文管理（`context_manager.py`，845 行）

为写作阶段组装加权优先级的上下文包：
- 加载章纲、最近剧情、未回收伏笔
- 模板权重体系（不同写作阶段使用不同权重模板）
- 题材画像片段注入
- 写作方法论指导项生成
- 预算控制（按权重截断至 token 上限）

#### 章节提交服务（`chapter_commit_service.py`，284 行）

章节提交流水线的编排中心：
1. CommitArtifactModel 校验（拒绝 wrapper 包裹，强制顶层扁平 schema）
2. 政策层升级判定（blocking_count > 0 → blocker）
3. StateProjectionWriter → 更新 state.json
4. VectorProjectionWriter → chunk 化后写入 vectors.db
5. IndexProjectionWriter → 写入 index.db
6. postcommit gate → backup

partial 投影状态是 warning 级（OK_PROJECTION_STATUSES 包含 done/skipped/partial），不会阻塞提交流程。

#### 记忆系统（`memory/` 子包）

三层记忆架构：
- **ScratchpadManager**（store.py）：短期记忆，JSON 文件持久化，FileLock 保护，自动压缩（超阈值触发 compactor）
- **MemoryWriter**（writer.py）：中期记忆写入，四态生命周期（active/tentative/confirmed/contradicted）
- **MemoryOrchestrator**（orchestrator.py）：长期记忆编排，跨层协调读写

配套有 MemoryContractAdapter 作为薄适配器，包装现有模块满足 MemoryContract Protocol 接口。

#### Story System 引擎（`story_system_engine.py`，601 行）

从 CSV 参考库检索创作知识并生成合同种子：
- 路由决策（根据 query + genre 选定 route 行）
- 查询扩展（合并 chapter_directive 文本 + route 默认查询词）
- 多表采集（场景写法/写作技法/桥段套路/人设与关系等）
- 反模式提取（从各表"毒点"列汇总 anti_patterns）
- 占位符检测（拒绝 `{章纲目标}` 类假查询）

#### 写作门禁（`write_gates/` 子包）

三阶段自然边界校验：
- **prewrite gate**：项目阶段就绪检查 + PrewriteValidator（合同/伏笔/占位符校验）+ runtime fallback 检查
- **precommit gate**：正文版本一致性 + artifact 校验 + 投影前置条件
- **postcommit gate**：投影完成度 + backup 完整性

输出统一的 gate_report 契约（schema_version/stage/errors/warnings/details）。

#### 时间线校验（`timeline_check.py`，253 行）

程序化校验卷级时间线的单调递增与倒计时算术：
- 解析 `大纲/第{N}卷 时间线.md` 的章节时间轴表格
- 校验时间锚点非空、单调递增（可解析天数/年份时做算术比较）
- 校验倒计时 D-N 单调递减且单章跳跃不超过 1

作为独立 CLI 命令暴露（`webnovel.py timeline-check --volume N`），但尚未接入 prewrite gate。

#### 运行台账（`run_ledger.py`，438 行）

记录写章六步骤的状态用于断点续跑：
- 步骤枚举：draft/review/data/commit/projection/backup
- record_write_step() 记录每步的 inputs/outputs/problems/auto_handled/duration_ms
- build_write_resume_plan() 基于 ledger 推断下一个应执行的步骤
- SHA256 正文哈希用于版本对齐校验

#### 诊断与观测

- **doctor.py**（918 行）：项目体检（preflight + 深度检查），输出结构化诊断报告
- **run_ledger.py** + **run_logger.py**：审计链与运行日志
- **observability.py**：性能计时与工具调用安全记录
- **projection_log.py**：投影运行历史追踪
- **event_log_store.py**：CHAPTER_COMMIT 事件审计链

### 3.4 Hooks 层

| Hook | 触发时机 | 职责 |
|------|----------|------|
| `session_start.py` | SessionStart | 打印项目状态简报 |
| `guard_runtime_write.py` | PreToolUse (Write/Edit/MultiEdit/Bash) | 阻止直接写入受保护的运行时文件 |

守卫逻辑：检测命令中是否包含受保护路径 + 写入关键词。白名单放行 `webnovel.py chapter-commit` 和 `projections retry/replay`。

### 3.5 Dashboard 层

FastAPI 本地只读看板：
- 仅 GET 接口，无写入 API
- 所有文件读取经 `path_guard.safe_resolve()` 阻穿越校验
- FileWatcher 监听文件变更推送前端刷新
- 预打包 dist/ 前端，无需 npm build
- CORS 白名单仅允许 localhost

### 3.6 参考知识库

`references/csv/` 下 10 张结构化 CSV 表，配套 `genre_taxonomy.py` 提供 38 种题材的规范化映射，`reference_search.py` 实现 BM25 检索 + bigram 分词 + 题材过滤。

---

## 四、核心代码逻辑详解

### 4.1 数据流总览

```
用户发起写章
    ↓
webnovel-write skill
    ↓
prewrite gate ← story-system contracts ← .story-system/
    ↓
context-agent → load-context → 组装写作任务书
    ↓
主流程起草正文 → 正文/第NNNN章_*.md
    ↓
reviewer agent → review_result.json
    ↓
data-agent → extraction/disambiguation result.json
    ↓
chapter-commit → ChapterCommitService
    ├─ CommitArtifactModel 校验
    ├─ StateProjectionWriter → state.json
    ├─ VectorProjectionWriter → vectors.db  
    ├─ IndexProjectionWriter → index.db
    ├─ postcommit gate
    └─ backup
```

### 4.2 save_state 并发合并机制

```python
def save(self):
    with self._lock:                    # FileLock 获取
        disk = read_json(state_file)     # 重读磁盘最新 state
        merged = self._merge_pending(disk, self._pending)  # 只合并本实例增量
        atomic_write_json(state_file, merged)               # 原子写入
        try:
            self._sync_sqlite(merged)                        # 同步 SQLite
        except:
            self._restore_pending_snapshot()                 # 失败恢复快照
            raise
        self._state = merged                                 # 以磁盘为准
```

这是对多 Agent 并发"读-改-写覆盖"的正确解法。但存在两处旁路破坏该模型。

### 4.3 RAG 混合检索流程

```
query
  ↓ embed(query)
  ├─ 成功 → vector_search（≤500 全表扫 / >500 预筛选局部算）
  └─ 失败 → degraded_mode → 纯 BM25 兜底
  ↓
bm25_search(query)
  ↓
rrf_fuse(vector_results, bm25_results)     # Reciprocal Rank Fusion
  ↓
rerank(fused_results)                       # 外部 API
  ├─ 成功 → 按 relevance_score 重排
  └─ 失败 → 直接用 RRF 序
  ↓
graph_enhancement（可选分支）
  ├─ 余弦相似度 + 图谱先验分数混合
  └─ 无图谱时跳过
```

### 4.4 大纲解析与字段优先级截断

解析链：独立章纲文件 → 卷纲中的章纲段落 → ⚠️ 提示串。

超预算时按字段优先级截断：先保留关键字段行（CBN/CPNs/CEN/必须覆盖节点/本章禁区），再用剩余预算截描述性文本。

关键正则匹配：`^{label}\s*[：:]` 要求标签在行首且紧跟冒号。下游结构解析使用相同裸标签匹配提取 must_cover_nodes 等列表字段。

### 4.5 断点续跑推断

基于 ledger 中已记录的 step 集合，找到 WRITE_STEPS 枚举中第一个未完成的步骤作为 next_step。正确性完全依赖上游 SKILL.md 按正确枚举名记账。

---

## 五、依赖关系

### 5.1 第三方依赖

| 包 | 使用位置 | 用途 |
|---|---|---|
| fastapi + uvicorn | dashboard/app.py, server.py | Web 看板 |
| pydantic | chapter_commit_schema, story_contract_schema, schemas 等 5 处 | 合同/artifact schema 校验 |
| filelock | security_utils, state_manager, state_projection_writer, memory/store | 跨进程文件锁 |
| aiohttp | api_client.py | 异步 HTTP（embedding/rerank） |

注意：根目录 requirements.txt 为空壳；真实依赖分散在两处 requirements.txt，均无版本锁定。

### 5.2 内部依赖要点

- `data_modules/*` 大量使用 try/except 双模式导入（相对导入 → scripts.* 回退）
- `story_system_engine.py` 依赖 scripts 顶层的 `reference_search.py`（跨包引用）
- StateManager 直接访问 `SQLStateManager._index_manager` 私有成员（封装击穿，多处）
- stdlib 之外零硬依赖：RAG 缺失时全链路可降级

### 5.3 数据依赖图

```
.story-system/（合同真源）
    ↑ 读取
write_gates ← skills/webnovel-write
    ↓
ChapterCommitService.apply_projections()
    ├─→ .webnovel/state.json（StateManager 投影）
    ├─→ .webnovel/index.db（IndexManager 投影）
    ├─→ .webnovel/vectors.db（VectorProjectionWriter 投影）
    └─→ summaries/chapter_NNNN.md（SummaryProjectionWriter）

references/csv/*.csv
    ↑ 读取
reference_search ← story_system_engine
```

---

## 六、潜在问题清单

严重度定义：
- **高（H）**= 崩溃 / 数据错误 / 核心功能失效
- **中（M）**= 特定条件下功能受损或性能显著劣化
- **低（L）**= 边界缺陷 / 可维护性问题

### 6.1 高危（H）

**H1 — SQLite 连接未设 WAL/busy_timeout**

8+ 处独立的 `sqlite3.connect()` 调用（index_manager:629、event_log_store:26、rag_adapter:249 等）全部使用默认参数：journal mode = DELETE，busy_timeout = 0。任一进程持写锁时另一进程立即抛 `database is locked`。项目自称"多 Agent 并行"，这是并发第一爆点。

**H2 — total_words 三路写入互相覆盖**

三条链路都写 `progress.total_words`：
1. state_manager.py:285 锁内合并 pending_delta
2. state_manager.py:663-664 update_progress() 直改内存
3. state_projection_writer.py:98-100 从 committed 文件字数重新计算投影值

三者语义不一致且无对账机制。

**H3 — 大纲关键字段裸标签正则漏匹配 markdown 变体**

截断匹配和结构解析均使用 `^{label}\s*[：:]` 模式，无法匹配 `**必须覆盖节点**：`、`### 必须覆盖节点` 等变体。`_clean_plot_line()` 剥列表符号但不剥 `**`。导致 must_cover_nodes 静默为空 → fulfillment 审查空转。

**H4 — SKILL 步骤节点名与 ledger 枚举双轨无映射**

SKILL.md 定义六个步骤名（step-env/step-context/step-draft/...），CLI argparse choices 只有 draft/review/data/commit/projection/backup。交集仅三个，step-env 和 step-context 无法记台账。

**H5 — timeline_check 未接入 prewrite gate**

timeline_check.py 校验逻辑完整且已暴露为 CLI 子命令，但在 write_gates/prewrite.py 中零引用。

**H6 — guard_runtime_write 重定向正则部分失效**

`\b(>|...)` 中 `\b` 在 `>` 前面要求词字符→非词字符边界，标准 shell 重定向形态中 `>` 前是空格（非词字符），不存在 `\b`。Bash 直写 `.story-system/commits/` 的最简形式未被拦截。

**H7 — rag vector_search 直连路径 O(N) 全表扫描**

strategy="vector" 不走预筛选分支，需反序列化全部 float32 blob 逐行 Python 计算余弦。大书（>10000 chunks）单次查询需数秒。

### 6.2 中危（M）

| # | 问题 | 位置 |
|---|---|---|
| M1 | `_save_state()` 绕过锁直接覆写（当前无生产调用点，属潜伏风险） | state_manager.py:714-717 |
| M2 | `update_progress()` 直改内存 total_words，绕过锁内 pending 合并语义 | state_manager.py:663-664 |
| M3 | StateManager 跨层私有访问 `_sql_state_manager._index_manager` 至少 5 处 | state_manager.py |
| M4 | upsert_entity SELECT-then-UPDATE/INSERT 非原子；浅合并丢嵌套 attributes | index_entity_mixin.py |
| M5 | `_validate_reading_power` 裸 `int()` 无防护 | index_reading_mixin.py:66/69 |
| M6 | pay_debt 读余额→计算→写回非原子 | index_debt_mixin.py |
| M7 | sha256 字节级哈希对换行符/BOM 敏感，Windows CRLF 误报率高 | run_ledger.py:76 |
| M8 | 台账防线 fail-open：record_write_step 纯靠 LLM 自觉调用 | run_ledger.py:193-196 |
| M9 | PrewriteValidator 读 state.json 无容错，损坏时异常崩溃而非 fail-closed | prewrite_validator.py:23-25 |
| M10 | rerank 结果解析 int(item.get("index",0))：畸形返回崩溃或缺省锚定第 0 候选 | rag_adapter.py:1106,1315-1316 |
| M11 | store_chunks commit 失败仅记日志不抛出，stored 计数含未提交行 | rag_adapter.py:482-486 |
| M12 | rag `_get_conn` 无 WAL/timeout，每操作新建连接开销大 | rag_adapter.py:246-253 |
| M13 | memory bootstrap 逐条 upsert 全量 load+save，5000 条约万次重写 | memory/bootstrap.py:56-177 |
| M14 | budget 只有条目数预算无 token/字符预算 | memory/budget.py |
| M15 | dashboard 无 Host 头校验、SQLite 非 ro 模式 | dashboard/app.py |
| M16 | 4 处 SKILL 用裸 python（无 -X utf8），Windows GBK 中文路径可能崩 | webnovel-plan/SKILL.md 等 |
| M17 | hook 异常时 fail-open 放行 | hooks/guard_runtime_write.py |
| M18 | failed 前缀判定 `"failed:"` 与 `"failed"` 两套并存 | artifact_validator vs postcommit |
| M19 | Pydantic schema 全部 extra="allow"，LLM 字段拼写错误静默通过 | chapter_commit_schema.py:61 |
| M20 | timeline_check 不支持中文数字天数；跨年误报路径；GBK 文件崩溃 | timeline_check.py:36,159,121 |
| M21 | story_system_engine 别名子串包含匹配过宽；CSV 行序隐式契约无声明 | story_system_engine.py:177,297-302 |
| M22 | _extract_outline_section 只认 ### + 半角冒号 | chapter_outline_loader.py:103-104 |
| M23 | IndexManager _init_db 每次构造全量 DDL，commit 流程构造 2-3 次 | index_manager.py:238-624 |
| M24 | compactor 的 latest_chapter 取自现存条目，压缩后窗口漂移 | memory/compactor.py:48-51 |
| M25 | run-log event 名无白名单 | run_logger.py:53-67 |
| M26 | record_state_change 内存列表无限追加，max_state_changes 未使用 | state_manager.py:960-976 |
| M27 | SQLite 启用时仍向内存 entities_v3 写完整实体副本 | state_manager.py:814-835 |
| M28 | 锁超时抛裸 RuntimeError，CLI 未捕获做结构化输出 | state_manager.py:420-421 |

### 6.3 低危（L）

| # | 问题 |
|---|---|
| L1 | security_utils 双入口并存，备份失败静默 |
| L2 | 测试降级开关 WEBNOVEL_TEST_RELAX_ATOMIC_REPLACE 未限定 pytest 环境 |
| L3 | 中文数字解析不支持百以上及"廿/卅"，百章后标题解析不一致 |
| L4 | timeline 年份正则要求恰好 4 位 |
| L5 | 单字人名被分词丢弃 |
| L6 | anti_patterns 来源字段硬编码映射 |
| L7 | writing/ 下 4 个文件仅 ~310B 疑似占位空壳 |
| L8 | agents/evals 内嵌测试项目随插件分发 |
| L9 | data-agent 置信度 0.5-0.8 区间行为未定义 |
| L10 | review 手动 update-state 与 chapter-commit 并存，重复记录 |
| L11 | graph_hybrid 分数混排，图谱先验增益可能丢失 |
| L12 | budget 余数分配逻辑与注释不完全一致 |
| L13 | 根目录 requirements.txt 空壳且无 lock |
| L14 | README "Skills（斜杠命令）"术语歧义 |

---

## 七、优化建议与修复路线图

### P0 — 立即修复（影响正确性/稳定性）

1. **统一 SQLite 连接工厂**（修 H1/M12/M23）
   新建 `data_modules/db.py` 提供 `connect(path)` 函数：`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON`。替换全部 8+ 处 connect 点。IndexManager 增加 DDL 一次性初始化标记。

2. **修复大纲标签匹配**（修 H3）
   在 `_clean_plot_line` 和截断匹配前统一剥离 Markdown 修饰：`re.sub(r"\*+","",text)` + 剥行首 `#{1,6}`。两处标签匹配抽成单一函数。补变体回归测试。

3. **SKILL 步骤名 ↔ ledger 枚举映射**（修 H4）
   SKILL.md 追加映射说明——step-env/step-context 不记 ledger（或扩枚举）、step-draft→draft、step-review→review、step-data→data、step-commit→依次调用 commit+projection+backup。

4. **接入 timeline_check 到 prewrite gate**（修 H5）
   prewrite gate 增加时间线校验步骤，复用现有 gate_report 契约。

5. **修正守卫正则**（修 H6）
   将 `\b(>|...)` 改为 `(?:^|\s)(?:>|out-file|...)\b` 或直接检测 `>>?` 操作符 + 目标路径组合。补绕过测试用例。

### P1 — 短期（1-2 个迭代）

6. total_words 单一真源（修 H2/M2）：以投影值为准，update_progress 只累积 pending。
7. safe_int 工具函数（修 M5 及全链路裸 int()）。
8. rerank 解析加固（修 M10/M11）：抽 _coerce_rerank_index 三处复用；commit 失败抛异常。
9. sha256 归一化（修 M7）：哈希前统一换行符、剥 BOM。
10. state.json 旁路封堵（修 M1/M26/M27）。
11. 门禁 fail-closed 化（修 M9/M17）。
12. dashboard 加固（修 M15）：Host 头校验 + ro 模式。
13. FAILED_PREFIX 常量化（修 M18）。

### P2 — 中期（架构改善）

14. SQLStateManager 公共 API 补齐（修 M3）
15. upsert_entity/pay_debt BEGIN IMMEDIATE 原子化（修 M4/M6）
16. RAG 大表检索优化：vector 路径预筛选 + 评估 sqlite-vss/faiss（修 H7）
17. memory bootstrap 批量化 + 内容 hash 幂等 id（修 M13）
18. 预算双维度化（修 M14）
19. timeline_check 增强：中文数字 + 二元组单调比较 + 编码容错（修 M20）
20. story_system_engine 匹配收紧（修 M21）
21. run-log event 白名单（修 M25）
22. SKILL 编码统一加 -X utf8（修 M16）

### P3 — 卫生项

清理占位文件（L7）；打包排除 evals 夹具（L8）；明确置信度口径（L9）；移除 review 兼容路径（L10）；requirements.txt 补实（L13）；README 术语澄清（L14）。

---

## 八、总体评价

该项目的**架构分层与设计成熟度显著高于同类插件**。亮点包括：

- 合同真源 / 投影分层的清晰职责边界
- 权限最小化的 agent 协作体系
- fail-closed 门禁报告契约
- RAG 多级降级链
- FileLock + pending 增量合并的并发意识
- 76+ 个测试文件的覆盖投入

主要短板集中在三类系统性问题上：

1. **并发基础设施欠账**——SQLite 连接参数、原子性、双轨写入。"多 Agent 并行"宣称下的最大隐患。

2. **提示词契约与运行时契约的断裂**——SKILL 步骤命名与 ledger 枚举脱节、timeline 断链、ledger 依赖自觉。属于"文档说一套、代码做一套"。

3. **文本解析的正则鲁棒性**——Markdown 变体、编码差异、中文数字。在真实网文语料下持续产生静默失败。

上述问题均为局部可修，不需要伤筋动骨的重构。按 P0→P3 路线推进即可。
