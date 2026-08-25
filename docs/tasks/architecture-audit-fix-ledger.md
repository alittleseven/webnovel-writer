# webnovel-writer 架构审计修复台账

> 依据：`research/architecture-audit-2026-08-23`（round1）+ `research/architecture-audit-round2-2026-08-23`（round2）
> 审计基准：v6.2.1（2026-08-23）
> 修复分支：`fix/temp`
> 台账目的：记录全部审计发现的问题（P0/P1/P2），标注已修复/未修复状态与修复进度，逐项落地。
> 当前同步：P0/P1 已按代码与测试证据完成；P2 保持部分完成/未完成状态。当前新增 backlog 与跨方案状态以 `docs/plans/2026-08-25-status-and-pending-work.md` 为准。

## 优先级定义

- **P0**：损害核心承诺的功能性缺陷（伏笔可追踪 / 事实可信 / 审计完整）
- **P1**：结构性弱点（可靠性、token 成本）
- **P2**：规模化与护栏补强

## 状态标记

- `[x]` 已修复（附 commit）
- `[ ]` 未修复
- `[~]` 部分修复

---

## 一、P0 核心承诺级缺陷

### P0-1 伏笔回收路由缺口——state 伏笔永不闭合
- **问题**：`promise_paid_off` 只路由到 memory，state 投影只认 `open_loop_created/closed` → `state.plot_threads.foreshadowing` 永不闭合
- **状态**：`[x]` 已修复
- **Commit**：`146c008 fix(P0-1): 修复伏笔回收路由缺口`
- **改动**：`event_projection_router.py` 增加 state 路由；`state_projection_writer.py` 伏笔聚合分支识别 `promise_paid_off`

### P0-2 BM25 回退失效——embedding 失败 chunk 双双丢失
- **问题**：embedding 失败的 chunk 只写 bm25_index 不写 vectors 表，`bm25_search()` 从 vectors 表取正文时 row=None 直接丢弃 → "无 Key 回退 BM25"失效
- **状态**：`[x]` 已修复
- **Commit**：`94f1d5b` + 补充修复 `338ce56`/`57cfed3`/`84c8f0b`
- **改动**：`rag_adapter.py` `store_chunks` embedding 失败也写正文行（embedding 置 NULL）；空列表边界处理；`vector_projection_writer.py` 降级标记
- **根因修复（P0-2c）**：`config.py` `embed_batch_size` 硬编码 64 → 改默认 20 + `EMBED_BATCH_SIZE` env 覆盖（`0851196`）。百炼单批上限 20，此前 chunk>20 章节整批 400 拒绝——这才是反复 `projection_failed`/大量 NULL embedding 的根因，此前只兜底「失败后走 BM25」未消根因

### P0-3 事件链崩溃窗口 + 修订提案空转
- **状态**：`[x]` 已修复
- **P0-3a 事件链崩溃窗口**：`[x]` 已修复
  - **Commit**：`d23cc58 fix(P0-3a): 闭合事件链崩溃窗口`
  - **改动**：`chapter_commit_service.py` 抽出 `write_events_and_proposals` 供 `apply_projections` 与 `retry_projection` 复用；`projections.py` retry 补跑写 events
- **P0-3b 修订提案空转**：`[x]` 已修复
  - **Commit**：`6bfa978 fix(P0-3b): 修订提案机制做实，为高价值事件补全触发规则`
  - **改动**：`override_ledger_service.py` 为 `world_rule_revealed`/`power_breakthrough`/`character_state_changed` 补全提案规则；字段映射降级（proposed_value 为空不产出空提案）；新增 6 测试

### P0-4 data-agent 提取零校验 + 无纠错回路
- **问题**：accepted 判定只看 blocking/missed_nodes/pending 三路信号，提取事实正确性零校验；错误事实入库后无修正手段
- **状态**：`[x]` 已修复（三步全部落地）
- **Commit**：`c883afc`（第一步轻校验）+ `d323cfd`（P0-4b int 防护）+ `9cf396f`（② memory correct 纠错 + ③ doctor 抽查）
- **改动**：
  - `chapter_commit_service.py` 新增 `_extraction_warnings` 纯函数，三类规则断言写入 `meta.extraction_warnings`，不阻断
  - `chapter_commit_schema.py` `normalize_aliases` + `chapter_commit_service.py` 对非整数章号降级为 `event_chapter_unparseable` warning（不崩溃）
  - `memory/store.py` 新增 `ScratchpadManager.correct()` + memory CLI `correct` 子命令（修正/改状态/删除记忆条目）
  - `doctor.py` 新增 `_extraction_warnings_check`（抽查最新 accepted commit 的提取质量信号）
- **复审发现（2026-08-23，CodeBuddy）**：`int(event_chapter)` 未防护，非整数章号导致 `build_commit` 崩溃。
  - **状态**：`[x]` 已修复（`d323cfd`，P0-4b）

---

## 二、P1 结构性弱点

### P1-1 合同 schema 生成侧零校验
- **问题**：`StorySystemEngine.build()` 返回裸 dict，`persist_story_seed` 直接写盘未经过 `MasterSetting/ChapterBrief` 的 model_validate；`ChapterBrief` 定义了没使用
- **状态**：`[x]` 已修复
- **Commit**：`c84f549 fix(P1-1): 合同 schema 生成侧零校验——persist 写盘前做 model_validate`
- **改动**：`story_contracts.py` persist_story_seed/persist_runtime_contracts 写盘前 model_validate（校验不替换 payload，保留 meta.query）

### P1-2 合同 schema 无版本演进
- **问题**：合同 `schema_version` 硬编码 `"story-system/v1"`，无迁移器（对比 RAG 已有）
- **状态**：`[x]` 已修复
- **Commit**：`dab9dbb feat(P1-2): 合同 schema 版本常量与迁移器框架`
- **改动**：`story_contract_schema.py` 新增 `CONTRACT_SCHEMA_VERSION` 常量；新增 `contract_migrations.py`（迁移注册表 + `migrate_contracts_if_needed` 扫描检测→备份→逐版本迁移→原子写回）；`story_system.py` 写盘前触发迁移；`doctor.py` 新增 `contract.schema_version` 版本一致性检查

### P1-3 记忆四态空转
- **问题**：`contradicted/tentative` 无生产写入路径，矛盾检测空转
- **状态**：`[x]` 已修复
- **Commit**：`44496d2 fix(P1-3): 记忆四态接通生产写入路径，contradicted/tentative 不再空转`
- **改动**：`schema.py` 新增 FACT_CATEGORIES；`upsert_item()` 语义比对（事实类同 key 不同值 → contradicted，状态类维持 outdated）；tentative 候选不降级现有 active 值；`writer.py` confidence < 阈值写入即标 tentative；`conflicts()` 透出 contradicted 矛盾对

### P1-4 token 三漏洞
- **问题**：① `_load_setting` 整份读设定文件；② 4 个死配置 + ranker 只排序不截断；③ JSON 结构冗余 + recent_summaries 默认全文
- **状态**：`[x]` 已修复
- **Commit**：`755ffcf fix(P1-4): 修复 token 三漏洞——设定截断、预算截断、紧凑输出`
- **改动**：`_load_setting` 按 context_setting_max_chars（默认 4000）截断；`ContextRanker.apply_budget` 消费 4 个死参数对文本 section 预算截断；`_render_text` 紧凑 JSON；`_load_summary_text` 默认 800 截断
- **遗留**：完整 L0 摘要层（init/plan 生成设定摘要 + 命中实体展开）留 v7

### P1-5 backup 降级漏备份 + 报告误报
- **问题**：`_local_backup` 非原子且漏 `.story-system/index.db`；git 成功时 user_report 误报
- **状态**：`[x]` 已修复
- **Commit**：`47025a6 fix(P1-5): 本地备份补全 .story-system 合同树与投影数据库，修复 git 成功误报`
- **改动**：`backup_manager.py` 补备份 .story-system + index.db/vectors.db/memory_scratchpad.json，临时目录+os.replace 原子 rename；`user_report.py` 新增 `_git_tag_exists` 识别 git tag 成功形态

### P1-6 run_logger 失败场景不落盘
- **问题**：`write_run_log` mode="w" 覆盖，只记 write-start
- **状态**：`[x]` 已修复
- **Commit**：`5e3a577`
- **改动**：SKILL 新增规范——每个关键步骤追加 `run-log --event <step> --append`；doctor 新增 `_run_log_checks` 诊断（只有 write-start 一条时 warning）

### P1-7 doctor 漏报
- **问题**：不校验卷/章合同 JSON 合法性；SQLite 只查两张表；MASTER_SETTING 缺失标 SKIPPED
- **状态**：`[x]` 已修复
- **Commit**：`5e3a577`
- **改动**：MASTER_SETTING 缺失时已写多章升级 error；新增 `_contract_json_checks`（volumes/chapters/reviews）；_sqlite_checks 扩展 entities/relationships/state_changes 三表

### P1-8 precommit 不校验 review 与正文版本对应
- **问题**：旧审查结果可配新正文通过
- **状态**：`[x]` 已修复
- **Commit**：`5e3a577`
- **改动**：run_ledger 新增 `verify_review_chapter_alignment`；precommit 调用，不一致阻断，无 review 记录跳过

### P1-9 部分 chunk embedding 失败静默
- **问题**：stored>0 即 applied，部分失败无重试标记，doctor 不校验 embedding 完整性
- **状态**：`[x]` 已修复（writer 层 partial 标记 + 状态聚合层透出 + doctor 兜底告警全部落地）
- **Commit**：`3ba03fb`（writer 层 partial 标记 + doctor NULL embedding 扫描）+ `f369a8a`（P1-9b 状态聚合层透出）
- **改动**：
  - `vector_projection_writer.py` stored<total 标 partial
  - `chapter_commit_service.py` `_writer_status` 识别 `partial` 返回独立状态
  - `projection_log.py` `_overall_status` 透出 `partial`（failed/pending 仍优先）
  - `artifact_validator.py` / `postcommit.py` partial 加入 OK 状态集合（不阻断）+ warning 提示
  - `project_phase.py` latest_commit 含 partial 时追加 `latest_commit_projection_partial` warning
  - `doctor.py` 新增 vectors 表 NULL embedding 完整性扫描（`_sqlite_null_embedding_count`）
- **复审发现（2026-08-23，CodeBuddy）**：partial 信号在状态聚合层被吞。
  - **状态**：`[x]` 已修复（`f369a8a`，P1-9b）

---

## 三、P2 规模化与护栏

### P2-1 性能
- **问题**：`_load_latest_commit` 逐章线性回扫；`_project_total_words` 重扫全部章节；`vector_search` 全表 Python 余弦；graph 候选全表扫描
- **状态**：`[~]` 部分修复（_project_total_words 增量 + vector_search norm 预计算已落地；其余 2 项留 v7）
- **Commit**：`b1c2572` + `a1eb037`
- **改动**：`_project_total_words` 增量缓存；`vector_search` 查询向量 norm 循环外预计算一次
- **待办**：`_load_latest_commit` latest.json 指针方案（state current_chapter 起点方案因跳过 commit 风险已回退）、graph 候选 FTS 全文索引（LIKE 无索引收益低），留 v7

### P2-2 大纲硬切与字段名不统一
- **问题**：`load_chapter_outline` 按字符硬切；plot 与 directive 两套字段名
- **状态**：`[~]` 部分修复（截断优化已落地；字段名统一留 v7）
- **Commit**：`dc80506`
- **改动**：`_truncate_outline_by_field_priority` 先保留 CBN/CPNs/CEN/必须覆盖节点/本章禁区，再按剩余预算截断描述文本
- **待办**：字段名统一（mandatory_nodes/prohibitions vs must_cover_nodes/forbidden_zones）涉及 6+ 文件，prewrite.py 已双向兼容，留 v7

### P2-3 实体消歧与追读力护栏
- **问题**：消歧精确匹配无相似度；追读力无 sanity check
- **状态**：`[~]` 部分修复（warn + sanity 断言已落地；LLM 别名预注册留 v7）
- **Commit**：`0dfa842`
- **改动**：`lookup_alias` 一对多时记 warn；`get_entity` compact-id 兜底标 `_compact_id_fallback`；`save_chapter_reading_power` 加 sanity 断言（debt_balance/hook_strength/chapter/override_count）
- **待办**：新实体入库用 LLM 生成 3-5 别名预注册，留 v7

### P2-4 题材参考覆盖不均
- **问题**：genre-tropes 仅 5 题材、genre-profiles 仅 13 profile
- **状态**：`[ ]` 未修复（数据补充，非代码 bug，留 v7）

### P2-5 一致性校验 LLM 自判升级为程序校验
- **问题**：plan 时间线校验靠 LLM 自判
- **状态**：`[x]` 已修复
- **Commit**：`f69d03e feat(P2-5): 时间线校验从 LLM 自判升级为程序校验 timeline-check`
- **改动**：新增 `timeline_check.py`（解析时间线表，校验锚点填写/单调递增/倒计时算术）；`webnovel.py timeline-check` 命令；plan SKILL Step 9 纳入程序校验
- **实测**：fantasy01 第 1 卷抓出第 30 章倒计时回退（D-10 > D-3）

### P2-6 文本侧保护
- **问题**：正文目录无变更记录，状态漂移无检测
- **状态**：`[ ]` 未修复（hook 配置，留 v7）

### P2-7 CSV 检索质量
- **问题**：`_tokenize` 无中文分词；子串兜底误召回
- **状态**：`[x]` 已修复
- **Commit**：`7b740a9`
- **改动**：`_tokenize` 对 CJK token 生成 bigram；`_bm25_score`/`_compute_idf` 子串兜底收紧（长度 >= 2 才兜底）

---

## 四、额外修复（审计外，实测发现）

### EXT-1 CLI 中文参数乱码
- **问题**：Windows PowerShell 传中文参数乱码，`rag search --query "中文"` 返回空
- **状态**：`[x]` 已修复
- **Commit**：`b4dbe99` + `ecd8a3f`
- **改动**：`runtime_compat.py` 新增 `_fix_sys_argv` / `_fix_argv_mojibake`

---

## 修复进度汇总

| 类别 | 总数 | 已修复 | 部分修复 | 未修复 |
|------|------|--------|---------|--------|
| P0 | 4 | 4 | 0 | 0 |
| P1 | 9 | 9（P1-1/2/3/4/5/6/7/8/9） | 0 | 0 |
| P2 | 7 | 2（P2-5/7） | 3（P2-1/2/3 部分修复） | 2（P2-4/6 留 v7） |
| EXT | 1 | 1 | 0 | 0 |
| 复审跟进 | 2 | 2（P0-4b / P1-9b） | 0 | 0 |

## 建议实施节奏

| 阶段 | 内容 |
|------|------|
| 当前（fix/temp） | P0-3b、P0-4 |
| 复审跟进（fix/temp 或新分支） | P0-4b（int 防护）、P1-9b（partial 状态透出）——详见各条目「复审发现」子块 |
| v7 前期 | P1-1/P1-2/P1-4（合同 schema 校验与版本、token） |
| v7 中后期 | P1 其余 + P2 全部 |

每个 P0/P1 项落地后：`python -m pytest`（全量）+ 行为 eval（19 用例）+ 对真实书项目跑 `doctor` + `preflight` 双检查。
