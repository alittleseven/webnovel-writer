# 更新日志

这里记录每个正式版本对作者和维护者的影响。发布说明优先面向中文网文作者：先说写作体验有什么变化，再补维护者关心的技术细节。

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
