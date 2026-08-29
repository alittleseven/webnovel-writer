# 更新日志

这里记录每个正式版本对作者和维护者的影响。发布说明优先面向中文网文作者：先说写作体验有什么变化，再补维护者关心的技术细节。

## Unreleased（v7-tmp 开发分支）

### 给作者看的变化

- **写前上下文包预算实装（C1，S1）**：`load_context` 的 `budget_tokens` 从死参数变为真执行——按 section 配额 + 键优先级收缩（`source_trace` 等元数据不再进入上下文；上一章提交全文只保留 meta 与摘要一句，fantasy01 实测该块占基础包 39%），超总预算按价值递减丢弃低优先级节。默认总预算经 [S1 配额分析](../reports/2026-08-30-S1-预算配额分析.md)（fantasy01 实测）定为 **20,000 字符**：ch35 基础包 59,977 → **19,241 字符（−68%）**，`budget_used_tokens` 返回真值。硬约束类（合同/运行状态）永不整体丢弃，任务书五段数据来源完整保留。
- **新增章级 token 计量（D1）**：写章起点自动建立计量标记，收尾输出「本章总消耗」一行结论（总计 + 去缓存新增 tokens，**含全部子代理轮次**），结果落盘 `.webnovel/tmp/chapter_meter_result.json` 供报告引用；写章过程中由 UserPromptSubmit 钩子每轮注入「本章累计」。非 ZCode 宿主（无用量库）自动降级跳过，不阻塞写作。
- 口径说明：数据源为 ZCode 本地用量库 `~/.zcode/cli/db/db.sqlite` 的 `turn_usage` 表（只读）；子代理会话与主会话无父子关联，聚合按时间窗一并计入，因此**写章期间请勿并行跑其他重会话**，否则可能串入其他会话的消耗。

### 给维护者

- 新增 `data_modules/chapter_meter.py`：`start_meter`（推断当前主会话 = 最近完成的非子代理轮，锚点为其完成时刻）/ `aggregate_usage`（时间窗 + `session_id = 主会话 OR LIKE 'sess_subagent%'`）/ `stop_meter`（关账 + 结果文件）。
- CLI 新增 `meter start|stop|report` 子命令（`--db` 可注入测试库）。
- 新增 `hooks/chapter_meter_hook.py`（UserPromptSubmit：标记 open 时注入本章累计）并接入 `hooks.json`。
- `webnovel-write` SKILL：write-start 同一时点 `meter start`，user-report 后 `meter stop` 并把一行总消耗并入最终回复。

## v6.4.0 - 写章上下文瘦身与实测修复

### 给作者看的变化

- **修复「中文参数被改写成乱码」**：fantasy01 第 35 章实测发现，v6.3.0 引入的 argv 乱码自动修复存在误报——「钱平」等正常中文的 GBK 编码恰好是合法 UTF-8，会被误判为乱码改写（`钱平`→`Ǯƽ`），导致 `get-by-alias` 等中文参数查询失败。由于真乱码与正常中文在字符串层面无法可靠区分，argv 自动修复改为**默认关闭**，受 PowerShell 传参乱码影响的环境设 `WEBNOVEL_FIX_ARGV_MOJIBAKE=1` 显式开启；stdio UTF-8 包装不受影响。
- **CLI 对损坏 JSON 的报错更友好**：`review-pipeline` / `chapter-commit` 遇到无法解析（如含未转义引号）或缺失的 artifact 时，不再抛 Python traceback，改为输出定位明确的一行错误与修复提示，退出码 2。

### 给维护者

- `runtime_compat._fix_sys_argv`：增加 `WEBNOVEL_FIX_ARGV_MOJIBAKE` 环境变量门控（1/true/yes/on 开启）；`_fix_argv_mojibake` 函数行为不变，新增误报类回归测试（`钱平` 不应被自动修复场景由门控覆盖）。
- `review_pipeline.main`：`build_review_artifacts` 的 `JSONDecodeError`/`OSError` 转为 stderr 友好报错 + `SystemExit(2)`。
- `chapter_commit._read_json`：同上，artifact 无法解析或缺失时友好报错 + `SystemExit(2)`。

## v6.3.0 - 修复伏笔回收、BM25 回退与事件审计链三个核心缺陷（未发布）

> 依据架构审计（2026-08-23，round1/round2）的 P0 缺陷清单落地。尚未发版，待全量验证与 Human Owner 确认。

### 给作者看的变化

- 修复「伏笔账永不闭合」：用 `promise_paid_off`（读者承诺兑现）表回收伏笔时，`state.plot_threads.foreshadowing` 现在会正确标记为已回收，与 `open_loop_closed` 等效。
- 修复「embedding 失败导致检索缺口」：向量生成失败的场景，现在仍能通过关键词（BM25）检索到正文，不再出现"语义检索 + 关键词检索双双丢失"的静默缺口。
- 修复「中断后审计链断链」：写章提交后若因崩溃中断，用 `projections retry` 补跑时会补齐事件审计文件与修订提案，不再永久丢失审计记录。

### 是否需要改旧项目

- 已存在的项目，此前因上述缺陷导致伏笔未闭合 / 检索缺块，可分别用 `doctor` 检查、`projections replay` 重放补偿，无需手动迁移。

### 给维护者

- `event_projection_router.py`：`promise_paid_off` 增加 `state` 路由；`state_projection_writer.py` 的伏笔聚合分支识别 `promise_paid_off` 并走闭合路径。
- `rag_adapter.py`：`store_chunks` 在 embedding 失败时也向 `vectors` 表写正文行（embedding 置 NULL），使 `bm25_search` 能取到正文；`vector_search` 本就跳过空向量行。
- `chapter_commit_service.py`：抽出 `write_events_and_proposals` 供 `apply_projections` 与 `retry_projection` 复用；`append_projection_run` 失败改为记日志而非静默吞掉。
- `projections.py`：`retry_projection` 补跑时调用 `write_events_and_proposals`，闭合事件链崩溃窗口。
- 同步修正固化旧行为的测试 `test_retry_projection_does_not_rewrite_commit_side_effects`（改为断言 retry 后 events 文件存在）。

### 补充修复（2026-08-23 实测写章后发现）

- `rag_adapter.py` `store_chunks`：`embed_batch` 返回**空列表**（整批 embedding 失败，如批次超限 >20）时，原逻辑提前 `return 0` 跳过 fallback 分支，导致失败 chunk 的正文既不入 `vectors` 表也不入 `bm25_index`，BM25 也召回不到。现把空列表视作「所有 chunk 均失败」，统一走 embedding 置 NULL 的 fallback 分支。
- `vector_projection_writer.py` `apply`：embedding 全部失败但 fallback 已写入 vectors 表（BM25 可用）时，返回 `embedding_degraded_bm25_fallback`（映射为 `skipped` 状态）而非 `error:store_failed`，避免投影被误判为 blocking 失败、阻断下一章写作。
- 新增测试：`test_embedding_batch_empty_still_searchable_via_bm25`（空列表边界）、`test_store_zero_for_required_chunks_is_error`（无 vectors 数据时仍报 store_failed）。

### CLI 中文参数乱码修复（2026-08-23 实测发现）

- `runtime_compat.py` `enable_windows_utf8_stdio`：新增 `_fix_sys_argv`，在 Windows 下就地修复 `sys.argv` 中因 PowerShell 传参导致的乱码（UTF-8 字节被 GBK 误解码）。之前只处理了 stdout/stderr 输出编码，未处理 argv 输入编码，导致 `rag search --query "中文"` 这类命令在 PowerShell 下查询到乱码、返回空结果。
- 新增 `_fix_argv_mojibake` 函数：仅当「GBK 编码 → UTF-8 解码」能无损往返且结果不同于原串时才修复，纯 ASCII、正常中文、路径、参数名不受影响。
- 新增测试：`webnovel-writer/scripts/tests/test_runtime_compat.py`（11 个用例，覆盖乱码还原、ASCII/中文/路径/混合场景不变性）。

### embedding 批次超限根因修复（2026-08-23 补跑投影时发现）

- `config.py` `embed_batch_size`：默认值从 `64` 改为 `20`，并支持 `EMBED_BATCH_SIZE` 环境变量覆盖（`field(default_factory=...)` 写法，与同文件 `embed_base_url` 等一致）。百炼（dashscope）embedding 接口单批上限 20，此前硬编码 64 导致 chunk 数 >20 的章节被当成单个 batch 整批 400 拒绝——这是此前反复出现 `projection_failed` / 大量 NULL embedding 的**根因**；P0-2 修复只兜底了「失败后走 BM25」，未消除「为何失败」。
- 实测：`fantasy01` 补跑 `projections replay 1-17` 后，17 章 `vector` 投影从 12 章 `skipped` 全部转为 `done`；`doctor` 的 `embedding_null` 告警从 23 条清零。

### 复审跟进修复（2026-08-23 复审发现）

- **P0-4b int 章号防护**：`chapter_commit_schema.py` `normalize_aliases` 与 `chapter_commit_service.py` 对 data-agent 产出的非整数章号（`"五"`/`"3.5"`/`"xian"`）降级为 `event_chapter_unparseable` warning，不再因 `int()` 崩溃阻断提交。
- **P1-9b partial 状态透出**：`_writer_status`/`_overall_status` 识别 `partial`（部分 chunk embedding 失败但 BM25 可用）并透出独立状态，`artifact_validator`/`postcommit` 不阻断但给 warning，`project_phase` 追加 `latest_commit_projection_partial` warning，让语义检索缺口在 `project-status` 可见、可进 retry 候选。
- **P0-4 纠错回路补齐**：新增 `memory correct` 命令（按 id 或 category+subject 定位，修正内容/改状态/删除）；`doctor` 新增 `commit.extraction_warnings` 抽查，透出最新 accepted commit 的提取质量信号。
- **P1-2 合同 schema 版本演进**：`story_contract_schema.py` 新增 `CONTRACT_SCHEMA_VERSION` 常量；新增 `contract_migrations.py` 迁移框架（检测→备份→逐版本迁移→原子写回，版本更高时安全跳过）；`story_system.py` 写盘前触发迁移；`doctor` 新增 `contract.schema_version` 版本一致性检查。

### P1-3 / P1-4 修复（2026-08-23 第二批）

- **P1-3 记忆四态接通生产写入路径**：事实类记忆（story_fact/world_rule）同 key 出现不同值时，旧值标 `contradicted` 而非 `outdated`（矛盾留痕，`conflicts()` 可透出）；data-agent 提取记录带 `confidence` 且低于阈值（默认 0.6）时写入即标 `tentative`，且 tentative 候选不降级现有 active 值（并存待确认，可用 `memory correct --status active` 升级）。
- **P1-4 token 三漏洞**：设定文件注入按 `context_setting_max_chars`（默认 4000）截断，随书膨胀不再撑爆写章上下文；`ContextRanker` 新增 `apply_budget` 预算截断（消费此前零引用的 4 个压缩配置）；上下文输出改紧凑 JSON（省 15-30% 结构冗余）；`recent_summaries` 默认路径统一 800 字截断。

### P1-6 / P1-7 / P1-8 修复（2026-08-23 第三批）

- **P1-6 run-log 关键步骤追加**：webnovel-write SKILL 新增规范——`write-start` 后每个关键步骤（env/context/draft/review/data/commit）必须追加 `run-log --event <step> --append`，使崩溃后 `run_last.log` 有最后卡点；doctor 新增 `run_log.step_coverage` 诊断（只有 write-start 一条时 warning 提示）。
- **P1-7 doctor 漏报扩展**：MASTER_SETTING 缺失时若已写多章（`current_chapter > 0`）升级为 error（不再是 SKIPPED）；新增 `_contract_json_checks` 校验 volumes/chapters/reviews 下合同 JSON 合法性；`_sqlite_checks` 扩展 index_db 的 entities/relationships/state_changes 三表完整性检查。
- **P1-8 precommit 正文版本校验**：`run_ledger` 新增 `verify_review_chapter_alignment` 公共函数（复用已有 sha256 签名机制，比对 review 步骤记录的正文 sha 与当前正文）；`precommit` gate 调用该函数，不一致时阻断提交（防止旧审查结果配新正文通过），无 review 记录时跳过（兼容 `--minimal`）。

### P2 优化（2026-08-23 第四批）

- **P2-7 CSV 检索 bigram 分词**：`reference_search._tokenize` 对 CJK token（长度 >= 3）生成 2-gram（如"战斗描写"→["战斗","斗描","描写"]），查询"战斗"直接命中无需子串兜底；子串兜底收紧（长度 >= 2 才生效），消除"金"命中"金币/黄金/金属"等误召回。
- **P2-2 大纲截断按字段边界优先**：`load_chapter_outline` 截断时先保留 CBN/CPNs/CEN/必须覆盖节点/本章禁区等关键字段行，再用剩余预算按字符数截断描述文本，避免硬切关键字段中间。字段名统一（mandatory_nodes/prohibitions vs must_cover_nodes/forbidden_zones）留 v7。
- **P2-3 实体消歧 warn + 追读力 sanity**：`lookup_alias` 一对多时记 warning；`get_entity` compact-id 兜底命中标 `_compact_id_fallback` 供 pending 复核；`save_chapter_reading_power` 加 sanity 断言（debt_balance ±100000、hook_strength 标准值、chapter 正数、override_count 非负）。LLM 别名预注册留 v7。
- **P2-1 \_project_total_words 增量优化**：读 state.json 缓存的 total_words + 已缓存章号集合，只算未缓存章节增量，避免每次 commit 全量重扫。`_load_latest_commit` latest.json 指针方案、vector_search numpy、graph SQL 下推留 v7。

### P2-5 / P2-1 追加优化（2026-08-24 第五批）

- **P2-5 时间线程序化校验**：新增 `webnovel.py timeline-check` 命令，解析 `大纲/第N卷-时间线.md` 章节时间轴，程序化校验时间锚点填写/单调递增/倒计时算术（D-N 单调递减、单章跳跃不超过 1），替代 plan 阶段 LLM 自判。实测 fantasy01 第 1 卷抓出第 30 章倒计时回退（D-10 > D-3）。
- **P2-1 vector_search 查询 norm 预计算**：`vector_search` 循环外预计算查询向量 norm，循环内内联余弦相似度复用查询 norm，消除 O(N) 次重复计算，数值结果与 `_cosine_similarity` 完全等价。

### 验证

- 新增测试：伏笔 `promise_paid_off` 闭合、BM25 召回 embedding 失败 chunk、retry 补写 events、embedding 整批失败空列表边界。
- 相关测试文件（投影 writer / 路由 / projections CLI / RAG / commit service / 事件日志 / 覆写账本）全绿。
- 实测：`fantasy01` 第 17 章写章后 `projections retry` 将 vector 状态从 `failed:store_failed` 修复为 `skipped`，`project-status` 从 `projection_failed` 回到健康态（`plan_in_progress`）。

## v6.2.1 - 修复 Windows 下写章提交偶发的「拒绝访问」

发版范围：`v6.2.0..v6.2.1`。

### 给作者看的变化

- 修复 Windows 上写章提交时偶发的 `WinError 5（拒绝访问）`：`.webnovel/` 下的故事资料文件被 VSCode、杀毒软件或同步盘短暂占用时，系统会自动等待并重试，不再直接失败（#125）。
- 建议 VSCode 用户把 `**/.webnovel/**` 加入 `files.watcherExclude`，项目尽量不放同步盘目录，可进一步降低占用冲突。

### 是否需要改旧项目

不需要。已有书项目继续使用，无需任何迁移。

### 给维护者

- `atomic_write_json` 的 `os.replace` 遇 `PermissionError` 改为指数退避重试（约 2.6 秒窗口），穷尽后如实抛错；全部 JSON 投影共用该写入函数，一并受益。
- 新增 4 个针对性测试，含 Windows 真实句柄占用复现。

### 验证

- 全量 pytest 通过（774 passed）。
- 版本同步、发布说明与插件包校验通过。

## v6.2.0 - 写章结果更清楚，失败后更好恢复

发版范围：`v6.1.0..v6.2.0`。

### 给作者看的变化

- 写章、审查、规划和初始化结束后，最终报告更像写作助手的汇报：会说明已完成、部分完成、需要你处理或未完成。
- `/webnovel-write` 中断后，重复执行同一章会优先检查可信断点，尽量从失败位置继续，减少重写和误覆盖。
- 写章过程减少技术细节打扰；只有创作方向、事实取舍、文件覆盖风险或阻断问题需要裁决时才询问。
- 写作流程的上下文读取更克制，初始化、规划、写章、审查、查询等命令更聚焦，减少无关资料塞满上下文。
- 章节提交前后的中间结果校验更稳，能更早发现缺失的审查、事实提取或故事资料同步结果。
- 文档补充了最终报告读法、恢复边界、日志用途和常见运维入口。

### 是否需要改旧项目

不需要。已有书项目可以继续使用，不需要迁移 `.story-system/` 或 `.webnovel/` 数据。

### 给维护者

- 新增作者术语表、异常目录、审查作者视图、最终报告 helper、写章 run ledger、脱敏 run log。
- 新增 `user-report`、`run-ledger`、`run-log` 统一 CLI 子命令。
- 收紧 commit artifacts、projection writers、write-gate 和 postcommit 的结构化校验。
- 轻量化多个 Skill / Agent 的提示词，补充 reference loading map 和 region-read 规则。
- 增加 prompt integrity、unit tests、behavior eval，覆盖 artifact ownership、最小写章模式、projection retry、blocking review、断点续跑和日志脱敏。
- `Plugin Release` 工作流改为推送到 `master` 后自动发版，并保留手动兜底入口。

### 验证

- 相关 pytest 通过。
- behavior eval 通过。
- `compileall` 通过。
- `git diff --check` 通过。
- 版本同步和插件包校验通过。

## v6.1.0 - 项目体检更稳，出问题更容易定位

- 增加 doctor、project-status、write-gate、projection 重放、hooks、行为评估和插件包校验。
- 强化 Story System 运行时健康检查和 Marketplace 发布校验。

## v6.0.0 - Story System 主链上线，长篇事实更不容易写乱

- 上线合同种子、运行时合同、章节提交、事件审计和投影链路。
- 补齐主链相关集成测试。
