# 功能流程与数据流全景（v6.3 + v7.0）

> 定位：一份**当前实现**的全景图——功能怎么串、数据落在哪、谁是真源谁是派生。面向维护者/审阅者，作为 [overview](overview.md)（v6 理念层）与 [story-repo-spec](story-repo-spec-2026-06-10.md)（v7 法律文本）之间的「实况层」。
> 基线：`@7e3bfe2`（2026-09-02）+ P1/P2/P3 修复批（S25/S26，同日）。图中标注「⚠审阅」处为 [增量审阅报告](../reports/2026-09-02-增量代码审阅报告.md) 的遗留缺陷位置（S26 后仅剩 H2 写入语义与个别需改前端 dist 的项，理由见报告 §4），属当前实现实况。

## 1. 总体架构分层

```mermaid
graph TB
    subgraph HOST["宿主：Claude Code / ZCode"]
        SK["Skills ×8<br/>init / plan / write / review / query / learn / doctor / dashboard"]
        AG["Agents ×4<br/>context-agent（读）· data-agent（写）· reviewer（审）· deconstruction-agent（拆书）"]
        HK["Hooks ×4<br/>session-start · chapter-meter · guard-runtime-write · chapter-body-trace"]
    end

    subgraph CMDS["命令面 scripts/"]
        CLI["webnovel.py 统一 CLI<br/>36 顶层子命令 / 含子动作约 48 个"]
        V7CLI["v7 独立脚本（v6 命令面之外）<br/>migrate_v6_to_v7 · v7_cache · v7_write"]
    end

    subgraph SVC["服务层 scripts/data_modules/"]
        CTX["上下文组装<br/>ContextManager · Ranker · Budget · settings_digest"]
        SSE["StorySystemEngine + 合同树<br/>CSV 题材路由 → MASTER/volume/chapter/review 合同"]
        GATES["写闸 write_gates ×3<br/>prewrite · precommit · postcommit<br/>+ dual_format_guard（v6/v7 唯一写入路径）"]
        COMMIT["ChapterCommitService<br/>四 artifact → accepted commit（事实源）"]
        EVT["EventLogStore + 投影路由"]
        PROJW["投影写入器 ×5<br/>state · index · summary · memory · vector"]
        IDX["IndexManager<br/>index.db 19 表（查询面）"]
        MEM["memory/ 长期记忆子包<br/>store · compactor · orchestrator · budget"]
        DIAG["诊断面<br/>doctor · project_status · status_reporter"]
        DASH["dashboard<br/>FastAPI 只读 API + React dist + SSE watcher"]
        BK["backup_manager / archive_manager"]
    end

    subgraph V6["v6 书仓（一本书目录）"]
        SSYS[".story-system/<br/>合同 · commits · events（写前/写后真源）"]
        WEBN[".webnovel/<br/>state.json · index.db · summaries · 记忆 · vectors（投影/read-model）"]
        DOC6["正文/ · 大纲/ · 设定集/"]
    end

    subgraph V7["v7 书仓（一本书 = 一个 git 仓库）"]
        CANON["定稿/ 正文·设定·记忆 + 大纲/ + 文风/"]
        WORK["工作区/ 决策卡·上下文包·草稿（gitignored）"]
        CACHE7[".cache/index.db（唯一持久派生物）"]
        BOOK["book.yaml（唯一纯 YAML）"]
    end

    SK --> CLI
    SK --> AG
    AG --> CLI
    HK --> CLI
    CLI --> CTX
    CLI --> SSE
    CLI --> GATES
    CLI --> COMMIT
    CLI --> DIAG
    CLI --> BK
    CLI --> DASH
    V7CLI --> CANON
    V7CLI --> CACHE7
    V7CLI --> BOOK
    SSE --> SSYS
    COMMIT --> SSYS
    COMMIT --> EVT
    EVT --> PROJW
    PROJW --> WEBN
    PROJW --> IDX
    CTX --> WEBN
    CTX --> SSYS
    CTX --> DOC6
    DASH --> WEBN
    DASH --> SSYS
    MEM --> WEBN
```

要点：

- **v6 链路**：Skills/Agents 全部经统一 CLI 进服务层；`.story-system/` 是真源（合同→commit→事件），`.webnovel/` 全部是投影/read-model（[overview](overview.md) 的真源划分）。
- **v7 链路**：三脚本独立于 v6 命令面，直接以 Markdown + git 为中心，唯一派生物是 `.cache/index.db`。
- **双链收口**：`dual_format_guard` 是两链路间互斥机制——迁移器自动落 `git config dualformat.v6root` 映射（settle 兜底读取）、prewrite/precommit 双挂载、v6 侧经可选 `--link-back` 写 .env 激活（S26 接线）。

## 2. 功能域与命令面速查

| 功能域 | 入口 | 读写 |
|---|---|---|
| 环境定位 | `where` / `use` / `preflight [--all]` / `project-status` | 指针+只读体检 |
| 初始化 | `webnovel.py init`（40+ 采集项）+ `story-system`（种子合同） | 建目录/合同 |
| 规划 | `timeline-check` / `master-outline-sync` / `update-state` / `story-system --emit-runtime-contracts` | 大纲+state |
| 上下文 | `context` / `extract-context` / `memory-contract load-context·query-*` / `setting-read` | 只读 |
| 检索 | `knowledge query-entity-state·query-relationships` / `index ·` 30+ 子命令 / `rag` | 只读 index.db |
| 写章 | `write-gate --stage {prewrite,precommit,postcommit}` | 门禁快照 |
| 提交 | `chapter-commit`（四 artifact）/ `projections retry·replay` | commits+投影 |
| 审查 | `review-pipeline` / `story-events` | metrics 入库 |
| 记账 | `run-log` / `run-ledger` / `meter` / `user-report` | 台账 |
| 运维 | `backup` / `archive` / `migrate` / `status` / `doctor [--deep]` / `project-memory add-pattern` | 备份/归档/体检 |
| v7 | `migrate_v6_to_v7` / `v7_cache rebuild·verify·snapshot` / `v7_write decision·pack·check`（settle 仅 Python API） | v7 书仓 |

## 3. 核心功能流程图

### 3.1 `/webnovel-write` 写一章（v6 主链）

```mermaid
flowchart TD
    P0["预检：preflight --all<br/>+ run-log write-start + meter start"] -->|"[占位符>0 阻断]"| X1["修大纲占位后重来"]
    P0 --> C1["刷合同：story-system<br/>--persist --emit-runtime-contracts"]
    C1 --> G1{"write-gate prewrite<br/>phase · 双格式守卫 · 合同齐备 · 时间线"}
    G1 -->|blocking| X2["补合同 / 作者裁决"]
    G1 -->|pass| S1["Step1 任务书：context-agent<br/>主：memory-contract load-context（20k 预算）<br/>降级：extract-context --format json"]
    S1 --> S2["Step2 起草：主流程写正文<br/>CBN→CPNs→CEN，无脚本"]
    S2 --> S3["Step3 审查：reviewer agent 六维<br/>→ .webnovel/tmp/review_results.json"]
    S3 --> RP["review-pipeline --save-metrics<br/>metrics 写入 index.db"]
    RP --> BL{"blocking > 0 ?"}
    BL -->|是| FIX["定点修复 / AskUserQuestion 裁决"] --> S2
    BL -->|否| S4["Step4 润色：读 polish/typesetting/style 参考"]
    S4 --> S5["Step5.1 提取：data-agent<br/>→ review/fulfillment/disambiguation/extraction 四结果"]
    S5 --> G2{"write-gate precommit<br/>正文非空 · 审查 sha 对齐 · artifact schema"}
    G2 -->|fail| S5
    G2 -->|pass| GIT["只读 git diff --check 体检"]
    GIT --> CC{"chapter-commit 判定<br/>blocking/missed/pending → rejected"}
    CC -->|rejected| S5R["修 problems 重跑 5.1-5.2"] --> CC
    CC -->|accepted| G3{"write-gate postcommit<br/>五投影状态核验"}
    G3 -->|"投影失败"| RT["projections retry --chapter（不回退正文）"] --> G3
    G3 -->|ok| S6["Step6 收尾：backup（git tag chNNNN）<br/>run-ledger 批量冲账 · user-report · meter stop"]
```

充分性闸门（SKILL 约定）：正文非空 / 审查落库 / blocking 处理 / anti-AI 通过 / commit=accepted 且五投影 done·skipped / chapter_status=committed / 三道 gate 全过——任一不满足不得声称完成。

### 3.2 v7 写一章（story-repo 新架构）

```mermaid
flowchart TD
    MIG["migrate_v6_to_v7（一次性，只读源仓）<br/>正文补 front matter · 设定/时间线合并<br/>名册 ← index.db · book.yaml 预填配额 · git init"] --> RC["v7_cache rebuild<br/>定稿+大纲+名册 → .cache/index.db"]
    RC --> DEC["① decision：写 工作区/决策卡-NNNN.md<br/>目标字数/节拍/禁区/合同断言/关键实体"]
    DEC -->|作者拍板| PACK["② pack：组装 工作区/上下文包-NNNN.md<br/>近3章摘要+实体解析+上章尾部（20k 预算，按书配额）"]
    PACK --> DR["③ 草稿：LLM/作者写 工作区/草稿-NNNN.md"]
    DR --> CHK{"④ check 机检（硬闸，exit 2 拒绝）<br/>字数≥0.75×目标 · 无占位符 · 标题一致<br/>承诺非空或豁免 · 名册 advisory"}
    CHK -->|不过| DR
    CHK -->|pass| ACC["⑤ 作者验收卡：接受/改完接受/打回<br/>（含章摘要扫一眼 + 新专名确认）"]
    ACC -->|接受| SET["settle（原子）：正文 NNNN-标题.md<br/>+ 章摘要 + 名册新实体 → 单次 git commit"]
    SET --> RB["settle 成功后自动 rebuild .cache<br/>（best-effort；缓存缺失/损坏首查亦自愈）"]
```

v7 与 v6 的本质差异：**没有中间投影层**——正文/摘要/名册直接是定稿文件，git commit 即事务边界，`.cache` 可随时删（S25 后 settle 自动刷新、损坏自愈）。

### 3.3 初始化与规划

```mermaid
flowchart LR
    IN["/webnovel-init 分阶段采集<br/>（可选拆书：deconstruction-agent）"] --> INITC["webnovel.py init<br/>建 .webnovel/ 设定集/ 大纲/总纲"]
    INITC --> SSC["story-system --persist<br/>CSV 题材路由 → MASTER_SETTING + 合同种子"]
    SSC --> PLAN["/webnovel-plan：卷纲/时间线/章纲"]
    PLAN --> TL["timeline-check（单调性/倒计时）"]
    PLAN --> MOS["master-outline-sync（卷锚点写回总纲）"]
    PLAN --> US["update-state --volume-planned 等"]
```

### 3.4 审查 / 诊断 / 面板

```mermaid
flowchart LR
    REV["/webnovel-review：reviewer agent<br/>+ review-pipeline + update-state --add-review"] --> IDB2["index.db review_metrics"]
    DOC["/webnovel-doctor：doctor --deep<br/>目录/JSON/合同树/DB/投影/依赖/dist 十二类检查"] --> REP["blocker/warning/建议"]
    DASH2["/webnovel-dashboard：server.py<br/>127.0.0.1:8765 只读 API + SSE"] --> SPA["React dist 六页<br/>Overview/Characters/Foreshadowing/Pacing/Files/System"]
```

## 4. 数据流

### 4.1 v6 章节提交数据流（写路径核心）

```mermaid
flowchart LR
    A["四 artifact JSON<br/>review · fulfillment · disambiguation · extraction<br/>（data-agent 产出）"] --> B["ChapterCommitService.build_commit<br/>pydantic 校验 → accepted / rejected"]
    B -->|"accepted"| C["persist_commit<br/>.story-system/commits/chapter_NNN.commit.json<br/>+ latest.json 指针（max）"]
    C --> D["write_events_and_proposals<br/>events/chapter_NNN.events.json（事件真源，event_id=确定性 sha1）<br/>index.db story_events 镜像（幂等）+ amend 提案入 override 账本"]
    B --> E["apply_projections<br/>路由按 status/extraction 圈定 writer 集合"]
    E --> W1["state 投影 → state.json<br/>chapter_status · current_chapter · total_words（⚠H2 三路竞写仍在，doctor 对账已可见化）<br/>entity_state · 伏笔 · strand_tracker"]
    E --> W2["index 投影 → index.db<br/>chapters · scenes · appearances<br/>state_changes · entity_deltas"]
    E --> W3["summary 投影 → .webnovel/summaries/chNNNN.md"]
    E --> W4["memory 投影 → memory_scratchpad.json<br/>（upsert 语义 + 内嵌 compactor >500 项）"]
    E --> W5["vector 投影（可选）→ vectors.db<br/>无 embed key 则 skip"]
    E --> PL["projection_log.jsonl 追加审计<br/>+ commit.json 回写 projection_status<br/>失败可 projections retry / replay"]
    B -->|"rejected"| RJ["投影记 not_required<br/>（rejected 仅写入空/已 rejected 章——单调状态机，S26）"]
```

旁路写链（不走 commit）：`webnovel.py state process-chapter` → `StateManager.process_chapter_result` → FileLock + 锁内重读合并写 state.json → 增量同步 index.db（失败保留 pending 待重试）。

### 4.2 读路径：上下文组装

```mermaid
flowchart LR
    subgraph SRC["数据源"]
        ST["state.json<br/>进度/主角/伏笔/strand"]
        SUMS["summaries/chNNNN.md<br/>近 3 章"]
        IDBX["index.db<br/>实体/关系/出场/追读力"]
        CONTRACTS[".story-system<br/>MASTER/volume/chapter/review 合同"]
        SCRP["memory_scratchpad<br/>三层记忆（working/episodic/semantic）"]
        SETD["设定集/<br/>settings_digest L0≈240字（sha256 自愈）"]
    end
    CM["context 命令<br/>ContextManager 16 节 + Ranker 打分截断"]
    MC["memory-contract load-context<br/>合同+记忆包+大纲+摘要<br/>20k 总预算（SECTION_QUOTAS/DROP_ORDER）"]
    EQC["extract-context（精简包，始终 JSON）"]
    ST --> CM
    SUMS --> CM
    IDBX --> CM
    SETD --> CM
    CONTRACTS --> MC
    SCRP --> MC
    SUMS --> MC
    ST --> MC
    ST --> EQC
    CM --> CA["context-agent 任务书 → 起草"]
    MC --> CA
    EQC --> CA
```

### 4.3 v7 读路径

`v7_write pack` ← `book.yaml`（预算）+ `.cache` 的 `get_summary`（近 3 章）/ `find_entity`（决策卡关键实体，正名+别名模糊）+ 名册目录扫描（候选新实体）+ 上章正文尾部 + 全书字数统计。查询面三 API 均短连接直读 `.cache/index.db`（4 表：chapters/entities/summaries/meta）。

### 4.4 数据落点全景（真源 / 投影 / 派生标注）

**v6 书仓**

| 落点 | 格式 | 角色 | 写者 | 读者 |
|---|---|---|---|---|
| `正文/第N章-*.md` | Markdown | 内容真源 | 主流程/作者 | commit 链、backup、dashboard |
| `大纲/`（总纲/卷/时间线） | Markdown | 意图真源 | init/plan/master-outline-sync/作者 | context、story-system、timeline-check |
| `设定集/*.md` | Markdown | 设定真源 | init/作者 | settings_digest → context |
| `.story-system/MASTER_SETTING.json`、`volumes/`、`chapters/`、`reviews/` | JSON | **写前真源（合同）** | story-system 引擎 | prewrite 闸、context、dashboard |
| `.story-system/commits/chapter_NNN.commit.json` + `latest.json` | JSON | **写后真源（事实）** | ChapterCommitService | postcommit 闸、projections、dashboard、memory 契约 |
| `.story-system/events/chapter_NNN.events.json` | JSON | **事件真源（审计）** | commit 链 | story-events、dashboard |
| `.webnovel/state.json`(+.lock) | JSON | 投影 | state 投影 / StateManager / update_state | context、dashboard、doctor（FileLock+原子写） |
| `.webnovel/index.db`（19 表） | SQLite | 投影/查询面 | index 投影、EventLogStore、review-pipeline、archive | knowledge、dashboard、status_reporter、context |
| `.webnovel/summaries/chNNNN.md` | Markdown | 派生 | summary 投影 | context、memory orchestrator、bootstrap |
| `.webnovel/memory_scratchpad.json`(+.lock) | JSON | 派生（长期记忆） | memory 投影 / process_chapter | orchestrator、status_reporter（内嵌 compactor） |
| `vectors.db` / `rag.db` | SQLite | 派生（可选） | vector 投影 / RAGAdapter | rag_adapter（无 key 自动降级 BM25） |
| `.webnovel/projection_log.jsonl` | JSONL | 审计 | append_projection_run | postcommit 闸、doctor、dashboard |
| `.webnovel/run_ledger.json` | JSON | 台账 | run-ledger 命令 | 断点续跑（锁内原子写，S26） |
| `.webnovel/logs/run_last.log`、`observability/*.jsonl`、`logs/chapter_body_trace.log` | 日志 | 观测 | run-log / data-agent / hook | 排障 |
| `.webnovel/tmp/`（gate 快照、review_results.json、meter 标记） | JSON | 瞬态 | 闸/审查/计量 | 各自消费方 |
| `.webnovel/backups/`、git tag `chNNNN` | git/快照 | 备份 | backup_manager | 回滚/diff |
| `.webnovel/archive/*.json` | JSON | 冷存 | archive_manager | 按名恢复 |

**v7 书仓**

| 落点 | 格式 | 角色 | 写者 | 读者 |
|---|---|---|---|---|
| `book.yaml` | YAML | 配置（唯一纯 YAML） | 迁移器/作者 | pack 预算、cache meta |
| `定稿/正文/NNNN-标题.md`（中文键 front matter） | Markdown | **真源** | 仅 settle | cache rebuild、pack 尾部、字数统计 |
| `定稿/记忆/章摘要/NNNN.md` | Markdown | 真源 | settle（作者可改） | cache、下章 pack |
| `定稿/设定/名册.md` + `名册/<正名>.md` | Markdown | 真源（双落点） | 迁移器写单表；settle 写目录 | cache 兼读（目录优先，含首现章列） |
| `定稿/设定/`（角色/时间线/世界观） | Markdown | 真源 | 迁移器/作者 | （v7.0 尚无程序化读） |
| `大纲/`、`文风/` | Markdown | 作者意图 | 作者（v7.0） | 未来 pack 扩展 |
| `工作区/`（决策卡/上下文包/草稿） | Markdown | 瞬态（gitignored） | v7_write、LLM | 作者界面、机检 |
| `.cache/index.db`（4 表） | SQLite | **唯一派生缓存** | rebuild_cache（settle 后自动/首查触发） | 查询面三 API（可随时删；缺失/损坏首查自愈） |

### 4.5 hooks 数据流

| Hook | 触发 | 数据流 |
|---|---|---|
| session-start | SessionStart | 子进程跑 `project-status --format summary` → 裁剪注入上下文（可 env 关闭） |
| chapter-meter | UserPromptSubmit | 读 `.webnovel/tmp/chapter_meter.json`（status=open）→ 聚合 ZCode 用量库 → 注入「本章累计」 |
| guard-runtime-write | PreToolUse(Write/Edit/Bash) | deny 对 `commits/`、`index.db`、`vectors.db`、`memory_scratchpad.json`、`projection_log.jsonl` 的直写（拦截名单含 cp/mv/tee/sed -i/dd/git checkout，S26） |
| chapter-body-trace | PostToolUse(Write) | `正文/` 落笔 → 追加 JSONL 审计 |

### 4.6 v6 → v7 迁移数据流（一次性）

```mermaid
flowchart LR
    subgraph V6S["v6 源仓（只读）"]
        ZW["正文/"]
        SJ["设定集/ + state.json"]
        IDX6["index.db（实体/别名）"]
        SUM6[".webnovel/summaries/"]
        DL6["大纲/"]
    end
    subgraph V7T["v7 新仓"]
        Z7["定稿/正文/NNNN-标题.md<br/>（补中文键 front matter）"]
        S7["定稿/设定/ + 时间线合并"]
        M7["定稿/记忆/章摘要/"]
        R7["名册.md（← index.db，含首现章）"]
        B7["book.yaml（≥3 章预填 prev_chapter_tail 配额）"]
        G7["git 初始提交"]
    end
    ZW --> Z7
    SJ --> S7
    IDX6 --> R7
    SUM6 --> M7
    DL6 -->|"总纲/卷纲平移"| V7D["大纲/"]
    IDX6 -.->|"git config dualformat.v6root 自动落映射<br/>--link-back 可选写 v6 .env（S26）"| GUARD["dual_format_guard"]
```

映射表完整版见 spec §12。旧 `state.json`/事件链/投影在 v7 侧**不迁移**（spec 不做清单），事实只保留定稿文件承载的部分。

## 5. 守卫与不变量的实现落点

| 不变量（spec/设计） | 实现落点 | 现状 |
|---|---|---|
| 机检先于模型评审 | v7 `check` 硬闸 exit 2；v6 prewrite/precommit | ✅ 两章实测有效 |
| 结转原子性（要么完成要么原样） | v7 settle 回滚；v6 commit+projection retry | ✅（S26：unlink 逐文件保护 + reset 范围化） |
| 派生物可丢弃、首查重建 | `v7_cache._conn` / `projections replay` | ✅（S25 后：settle 自动刷新 + 缺失/损坏首查重建） |
| 唯一写入路径（v6/v7 互斥） | `dual_format_guard` + prewrite/precommit/settle 挂载 | ✅（S26 接线） |
| 定稿只增不改 | settle 仅新建文件 + git（章号前缀判重） | ✅ |
| 容错读取（未知字段保留） | 各 schema 解析器（名册目录单文件损坏跳过） | ✅ |
| 状态写入受锁保护 | FileLock + 原子写（state/scratchpad/run_ledger） | ✅ |
| 运行时数据防直写 | guard_runtime_write hook | best-effort（拦截名单已补齐） |
