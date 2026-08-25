# Plugin Runtime Hardening Implementation Plan

> 日期：2026-06-04
> 状态：v6 核心能力已落地；P2 收尾与 v7 迁移保留为待办（2026-08-25 核对）
> 对应 spec：`docs/architecture/plugin-runtime-hardening-spec-2026-06-04.md`
> 范围：把 spec 拆成可实施、可验收、可回退的工程计划，重点说明修改范围与影响面
> 当前实现证据：`project_phase.py`、`project_status.py`、`doctor.py`、`artifact_validator.py`、`write_gates/`、`projection_log.py`、`projections.py`、`validate_plugin_package.py`、`run_behavior_evals.py` 均已存在并有对应测试。未完成项以 `docs/plans/2026-08-25-status-and-pending-work.md` 为准。

---

## 1. 目标

本计划把 `webnovel-writer` 从“主要靠 Skill 文档约束流程”推进到“关键边界由 runtime 可验证”的插件形态。

核心交付：

1. `project_phase` / `project-status`：统一项目阶段推导和短状态摘要，保留现有 `status_reporter.py` 的宏观创作健康报告语义。
2. `/webnovel-doctor`：阶段感知的项目体检，检查目录、文件、数据库、RAG、Python 依赖、Dashboard 配置，并给修复建议。
3. `artifact_validator`：统一校验 agent 产物，避免字段漂移和 schema 错误。
4. `write-gate`：在写前、提交前、提交后三个自然边界做批量校验。
5. `projection_log`：把 commit 事实和 projection 执行日志拆开。
6. `projections retry/replay`：投影失败后可补跑。
7. Skill / Agent 契约补强：按官方 `plugin-dev` 规范收束 frontmatter、description、tools、输出约束。
8. Behavior evals 与 package validator：验证插件行为和发布物一致性。
9. 可选轻量 hook：SessionStart 状态提示与 PreToolUse 危险动作兜底提醒 / 阻断。

---

## 2. 实施原则

### 2.1 先观察，后阻断，再迁移

顺序必须是：

1. 先提供只读诊断能力。
2. 再加入 schema / gate 阻断。
3. 最后处理 projection log 与 replay。

这样可以减少一次性大改对现有写作流程的冲击。

### 2.2 不破坏现有用户项目

所有新增能力默认兼容旧数据：

- 保留现有 `.story-system/commits/*.commit.json` 结构。
- 保留 commit 内 `projection_status` 至少一个版本周期。
- `.webnovel/state.json`、`index.db`、`summaries/`、`memory_scratchpad.json` 继续作为 projection / read-model。
- Dashboard 先兼容旧字段，再逐步读取新 projection log。

### 2.3 遵循官方 `plugin-dev`

所有插件组件改动必须遵循：

```text
C:\Users\lcy\.claude\plugins\marketplaces\claude-plugins-official\plugins\plugin-dev
```

落地要求：

- 插件结构按 `plugin-structure`。
- Skill 按 `skill-development`，保持 `SKILL.md` 精简，详细规则放 `references/`。
- Command 按 `command-development`。
- Agent 按 `agent-development`。
- Hook 按 `hook-development`，插件级 `hooks/hooks.json` 使用 wrapper 格式。
- 每轮插件组件改动后按 `plugin-validator` 思路校验 manifest、skills、agents、hooks、README、LICENSE、路径可移植性。

### 2.4 每阶段独立可回退

每阶段应尽量做到：

- 新增文件多于修改旧文件。
- 旧入口可继续工作。
- 新 CLI 子命令失败不影响旧命令。
- 可通过删除新增入口或关闭 hook 回退。

### 2.5 新入口统一 UTF-8

所有新增 CLI / hook / 子进程入口必须兼容 Windows 中文路径：

- CLI 入口调用 `enable_windows_utf8_stdio()` 或等价逻辑。
- 文件读写显式 `encoding="utf-8"`。
- hook / 子进程使用 `python -X utf8` 或设置 `PYTHONUTF8=1`。
- 不依赖系统默认编码。

---

## 3. 总体依赖顺序

```text
Phase 0 基线审计
  ↓
Phase 1 project_phase + project-status + doctor
  ↓
Phase 2 artifact_validator
  ↓
Phase 3 write-gate
  ↓
Phase 4 projection_log
  ↓
Phase 5 projection retry/replay
  ↓
Phase 6 skill / agent 契约补强
  ↓
Phase 7 behavior evals
  ↓
Phase 8 package validator
  ↓
Phase 9 hooks
```

说明：

- `project_phase` / `project-status` / `doctor` 可以先做，因为它们只读、风险最低，并且后续 gates 和 hooks 都依赖统一 phase。
- `artifact_validator` 应早于 `write-gate`，否则 gate 会重复写 schema 判断。
- `projection_log` 应早于 retry/replay，否则失败记录不稳定。
- hooks 放后面，因为它们会改变 Claude Code 会话体验。

---

## 4. Phase 0：基线审计与测试冻结

### 4.1 目标

在动代码前确认当前功能基线，避免重构时不知道哪里被破坏。

### 4.2 修改范围

优先不改 runtime 代码，只新增或更新文档 / 测试清单：

- `docs/architecture/plugin-runtime-hardening-plan-2026-06-04.md`
- 可选更新 `docs/README.md`

### 4.3 工作项

1. 记录当前 CLI 命令表。
2. 记录现有 Skills、Agents、Dashboard API。
3. 跑一组最小测试：
   - `test_webnovel_unified_cli.py`
   - `test_story_runtime_health.py`
   - `test_chapter_commit_service.py`
   - `test_event_projection_router.py`
   - `test_rag_adapter.py`
   - `test_dashboard_app.py`
4. 确认当前 repo 是否已有未提交改动，避免误覆盖用户修改。

### 4.4 影响

无用户可见行为变化。

### 4.5 验收

- 记录基线测试结果。
- 明确当前失败项是否为既有问题。

---

## 5. Phase 1：`project_phase` / `project-status` / `webnovel-doctor`

### 5.1 目标

新增统一 phase resolver、短状态入口和只读项目体检入口，回答：

- 当前项目处于什么阶段。
- 这个阶段应该有哪些文件。
- 目录、JSON、SQLite、RAG、Python 依赖、Dashboard 配置是否完整。
- 缺失或异常时如何修复。

当前代码已有两个相关入口，必须先明确关系：

- `webnovel.py preflight`：已有快速环境检查，保留并复用。
- `webnovel.py status`：已转发到 `scripts/status_reporter.py`，语义是宏观创作健康报告，保留不占用。

### 5.2 修改范围

新增：

- `webnovel-writer/scripts/data_modules/project_phase.py`
- `webnovel-writer/scripts/data_modules/project_status.py`
- `webnovel-writer/scripts/data_modules/doctor.py`
- `webnovel-writer/scripts/data_modules/tests/test_project_phase.py`
- `webnovel-writer/scripts/data_modules/tests/test_project_status.py`
- `webnovel-writer/skills/webnovel-doctor/SKILL.md`
- `webnovel-writer/scripts/data_modules/tests/test_doctor.py`

修改：

- `webnovel-writer/scripts/data_modules/webnovel.py`
- `docs/guides/commands.md`
- `docs/README.md`

可复用：

- `webnovel.py` 中现有 `_build_preflight_report()`
- `story_runtime_health.py`
- `story_runtime_sources.py`
- `config.py`
- Dashboard 里的 `_inspect_vector_db()` / `_build_env_status()` 思路

### 5.3 具体工作

1. 实现共享 `project_phase.py`：
   - 单一 phase 词表。
   - 不写状态文件。
   - doctor / project-status / write-gate 共用。
2. 实现 `project-status`：
   - `webnovel.py project-status --format json|summary`
   - 保留 `webnovel.py status` 现有转发，不改 `status_reporter.py` 语义。
   - 输出 latest accepted chapter、target chapter、phase、warnings、next action。
3. 实现 `doctor` 数据模型：
   - `DoctorReport`
   - `DoctorCheck`
   - `RepairSuggestion`
   - `ExpectedFiles`
4. 由 `project_phase.py` 实现 phase 推导：
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
5. 实现阶段感知 expected files：
   - init 后只要求骨架、`state.json`、设定集、总纲、`.env.example`。
   - init 阶段不要求 commit、summary、memory、vectors。
   - plan / write / commit 阶段再逐步提高要求。
6. 实现文件检查：
   - 目录存在性。
   - JSON 可读性。
   - 关键字段检查。
7. 实现 SQLite 检查：
   - `index.db` 是否可打开。
   - 关键表是否存在。
   - 行数统计。
   - `vectors.db` 是否可打开、是否有 `vectors` 表。
8. 实现系统配置检查：
   - Python 版本。
   - 核心包 import。
   - RAG env / `.env` 配置。
   - Dashboard dist / requirements / package.json。
9. 在统一 CLI 注册：
   - `webnovel.py project-status --format json|summary`
   - `webnovel.py doctor --format json|text`
   - `webnovel.py doctor --chapter N --format json|text`
   - `webnovel.py doctor --deep --format json|text`
10. 新增 `/webnovel-doctor` Skill：
   - 只读。
   - 不修复。
   - 输出结论、影响、建议命令。

### 5.4 影响

用户影响：

- 新增一个体检命令，不改变旧流程。
- 新增 `project-status` 短状态命令，不改变既有 `status` 健康报告。
- 出问题时用户能看到缺什么、影响什么、怎么修。

代码影响：

- `webnovel.py` 增加 `project-status` 和 `doctor` 子命令。
- 新增 `doctor.py` 只读模块。
- 新增共享 phase resolver。
- 不修改 commit、state、index、summary、memory。

风险：

- phase 推导不准会导致误报。
- 数据库表清单如果过严，会把旧项目误判为坏。
- `project-status` 与现有 `status_reporter.py` 混淆。

控制：

- phase 不确定时只做低风险检查。
- init 阶段缺后续产物只返回 `skip/info`。
- 数据库检查分 `required` 和 `observed`，避免旧表缺失直接阻断。
- 命令名使用 `project-status`，保留 `status` 原语义。
- doctor 快检部分复用 `_build_preflight_report()`，避免 preflight / doctor 两套环境检查漂移。

### 5.5 验收

- 空目录返回 `no_project`，无 traceback。
- `webnovel.py status` 仍运行现有 `status_reporter.py`。
- `webnovel.py project-status --format json` 返回统一 phase。
- `preflight` 仍可运行，并与 doctor 快检结果不冲突。
- init 刚结束返回 `init_scaffolded` 或 `init_ready`。
- init 刚结束缺 commit / summary / vectors 不报 blocker。
- `index.db` 缺关键表时能显示表名、影响、修复建议。
- 缺 RAG key 返回 warning，并说明降级 BM25。
- 默认模式不联网、不写文件、不安装依赖、不启动服务。
- Windows 中文路径下不因默认编码失败。

### 5.6 回退

- 移除 CLI `doctor` / `project-status` 注册。
- 保留 `doctor.py` 不被调用也不影响现有流程。
- 保留 `project_phase.py` 不被调用也不影响现有流程。
- 删除 `/webnovel-doctor` Skill 后插件仍可按原方式运行。

---

## 6. Phase 2：Artifact Validator

### 6.1 目标

统一校验 agent 产物，避免 `review_result`、`fulfillment_result`、`disambiguation_result`、`extraction_result` 字段漂移。

### 6.2 修改范围

新增：

- `webnovel-writer/scripts/data_modules/artifact_validator.py`
- `webnovel-writer/scripts/data_modules/tests/test_artifact_validator.py`

可能修改：

- `chapter_commit_service.py`
- `chapter_commit.py`
- `chapter_commit_schema.py`

### 6.3 具体工作

1. 定义统一错误类型：
   - `schema_error`
   - `missing_artifact`
   - `blocking_review`
   - `missed_outline_node`
   - `pending_disambiguation`
   - `projection_failure`
2. 包装现有 Pydantic schema。权威源统一为 `chapter_commit_schema.py` 中 commit 所需模型：
   - `ReviewResult`
   - `FulfillmentResult`
   - `DisambiguationResult`
   - `ExtractionResult`
3. 明确同名 / 近名模型边界：
   - `review_schema.py` 是 reviewer / review pipeline 局部模型。
   - `entity_linker.py` 中的消歧模型是实体链接局部模型。
   - artifact_validator 只以 commit artifact schema 作为最终提交权威。
4. 提供统一入口：
   - `validate_review_result(path)`
   - `validate_fulfillment_result(path)`
   - `validate_disambiguation_result(path)`
   - `validate_extraction_result(path)`
   - `validate_chapter_commit(path)`
5. 允许兼容已知旧字段，无法兼容时给明确诊断。

### 6.4 影响

用户影响：

- 提交前更早发现 agent 输出错误。
- 报错从 Python traceback 变成结构化说明。

代码影响：

- `chapter_commit_service` 可以逐步改为依赖 validator。
- 后续 `write-gate` 复用 validator，减少重复校验。

风险：

- 过严 schema 可能阻断旧产物。
- 同名模型选错会制造新的 schema 漂移。

控制：

- 首版对旧字段做兼容或 warning。
- 只有明确影响 commit 正确性的错误才 blocker。
- 在代码注释和测试中固定权威源为 `chapter_commit_schema.py`。

### 6.5 验收

- 缺 artifact 返回 `missing_artifact`。
- JSON 外层包错返回 `schema_error`。
- `disambiguation.pending` 非空返回 blocker。
- reviewer blocking issue 返回 blocker。
- `ReviewResult` / `DisambiguationResult` 同名模型不混用。

### 6.6 回退

- `chapter_commit_service` 保留旧校验路径。
- 如果 validator 有误，可先只用于 doctor / gate 报告，不阻断 commit。

---

## 7. Phase 3：Runtime Gates

### 7.1 目标

新增写章关键边界校验：

- `prewrite`
- `precommit`
- `postcommit`

### 7.2 修改范围

新增：

- `webnovel-writer/scripts/data_modules/write_gates/__init__.py`
- `webnovel-writer/scripts/data_modules/write_gates/prewrite.py`
- `webnovel-writer/scripts/data_modules/write_gates/precommit.py`
- `webnovel-writer/scripts/data_modules/write_gates/postcommit.py`
- `webnovel-writer/scripts/data_modules/tests/test_write_gates.py`

修改：

- `webnovel-writer/scripts/data_modules/webnovel.py`
- `webnovel-writer/skills/webnovel-write/SKILL.md`
- `docs/guides/commands.md`

复用：

- `webnovel-writer/scripts/data_modules/prewrite_validator.py`
- `webnovel-writer/scripts/data_modules/tests/test_prewrite_validator.py`

### 7.3 具体工作

1. 注册 CLI：
   - `webnovel.py write-gate --chapter N --stage prewrite --format json`
   - `webnovel.py write-gate --chapter N --stage precommit --format json`
   - `webnovel.py write-gate --chapter N --stage postcommit --format json`
2. `prewrite` 检查必须包装 `PrewriteValidator`：
   - project root。
   - phase 是否允许写。
   - Story System 合同是否齐。
   - 占位符 blocker。
3. `precommit` 检查：
   - 正文文件。
   - review / fulfillment / disambiguation / extraction artifacts。
   - artifact validator。
   - blocking issue。
4. `postcommit` 检查：
   - commit 文件。
   - `projection_status`。
   - summary / index / memory / backup 基本存在性。
5. 更新 `/webnovel-write`：
   - 用 Claude Code Todo 管过程。
   - 只在自然边界调用 gate。

### 7.4 影响

用户影响：

- 写章流程增加 2-3 次确定性检查。
- 提交前错误更清晰。

代码影响：

- `/webnovel-write` 的执行说明会改变。
- `webnovel.py` 增加子命令。
- 现有 `PrewriteValidator` 成为 prewrite gate 的底层实现，避免两套逻辑漂移。

风险：

- gate 太严格会打断写作体验。
- gate 太宽松则无法提升可靠性。
- 如果重写 prewrite 逻辑，会和现有 `PrewriteValidator` 漂移。

控制：

- 首版只阻断明确不可信状态。
- warning 不阻断。
- 所有 gate 输出 repair 建议。
- prewrite 不重写，先适配现有 validator 输出。

### 7.5 验收

- 缺 review artifact 时 `precommit.ok=false`。
- blocking review 时 `precommit.ok=false`。
- disambiguation pending 时 `precommit.ok=false`。
- projection failed 时 `postcommit.ok=false`。
- init 阶段调用 `prewrite` 能给出明确下一步建议。
- 现有 `test_prewrite_validator.py` 继续通过。

### 7.6 回退

- `/webnovel-write` 可临时回到旧流程。
- CLI 子命令保留但不被 Skill 调用。

---

## 8. Phase 4：Projection Log

### 8.1 目标

将 commit 事实和 projection 执行状态拆开，降低 commit 文件同时承载事实与执行日志的混乱。

开工前必须先确认现状痛点：

- 是否出现过 projection failed 后无法定位 writer。
- 是否出现过 commit 内 `projection_status` 与实际 read-model 不一致。
- Dashboard / doctor 是否确实需要跨 writer 的执行历史。

如果没有真实痛点，本阶段可以延后，只保留 doctor 对现有 `projection_status` 的诊断。

### 8.2 修改范围

新增：

- `webnovel-writer/scripts/data_modules/projection_log.py`
- `webnovel-writer/scripts/data_modules/tests/test_projection_log.py`

修改：

- `chapter_commit_service.py`
- `event_projection_router.py`
- `story_runtime_health.py`
- `doctor.py`
- `dashboard/app.py`

### 8.3 具体工作

1. 新增 JSONL projection log：
   - `.webnovel/projection_log.jsonl`
2. 定义 run schema：
   - `run_id`
   - `chapter`
   - `commit_path`
   - `commit_hash`
   - `writer`
   - `status`
   - `started_at`
   - `finished_at`
   - `error`
3. `chapter_commit_service.apply_projections()` 每个 writer 写一条 log。
4. 保留 commit 内 `projection_status` 双写。
5. doctor 优先读取 projection log，缺失时 fallback 到 commit 内字段。
6. Dashboard 先兼容读取，不做大改版。

### 8.4 影响

用户影响：

- 投影失败时能看到具体哪个 writer 失败。
- 不改变章节提交命令。

数据影响：

- 新增 `.webnovel/projection_log.jsonl`。
- commit 文件结构暂时不删字段。

风险：

- 双写不一致。
- Dashboard 读取逻辑复杂一点。
- 新增 projection log 会形成第二份执行状态来源。

控制：

- projection log 写失败不应影响 commit 主流程，但必须 warning。
- doctor 报告双写不一致。
- 保留一个明确决策点：确认收益大于双写复杂度后再施工。

### 8.5 验收

- 每个 writer 有 projection log。
- 单 writer failed 不影响其他 writer 记录。
- doctor 能指出 failed writer。
- commit 内 `projection_status` 仍存在。

### 8.6 回退

- Dashboard 和 doctor fallback 到 commit 内 `projection_status`。
- 删除 projection log 不影响 commit 读取。

---

## 9. Phase 5：Projection Retry / Replay

### 9.1 目标

投影失败后能按 writer 补跑，尤其是 vector / summary / memory。

本阶段风险最高，必须先完成 writer 幂等性审计和测试。

### 9.2 修改范围

新增：

- `webnovel-writer/scripts/data_modules/projection_runner.py`
- `webnovel-writer/scripts/data_modules/tests/test_projection_runner.py`

修改：

- `event_projection_router.py`
- `webnovel.py`
- projection writer 测试

### 9.3 具体工作

1. 新增 CLI：
   - `webnovel.py projections status --chapter N`
   - `webnovel.py projections retry --chapter N --writer vector`
   - `webnovel.py projections retry-failed --chapter N`
   - `webnovel.py projections replay --from 1 --to 20 --writers state,index,summary`
2. 先审计 5 个 writer 幂等性：
   - `state`
   - `index`
   - `summary`
   - `memory`
   - `vector`
3. 补齐 writer 幂等测试，尤其关注：
   - 字数重复累计。
   - 关系 / 事件重复插入。
   - memory 重复沉淀。
   - vector chunk 重复。
4. runner 只读取 accepted commit。
5. retry 不修改 commit 事实内容。
6. retry 结果写 projection log，并兼容更新旧 `projection_status`。

### 9.4 影响

用户影响：

- 外部依赖失败后不用重写整章。
- 可单独补 vector / summary。

数据影响：

- projection read-model 可能被重建。
- 需要保证幂等，避免重复累计字数或重复关系。

风险：

- 幂等不足导致重复数据。
- replay 命令一旦写错，影响范围比单章 commit 大。

控制：

- 先对 state/index/summary/memory/vector writer 分别补幂等测试。
- replay 默认要求明确 chapter 范围。
- 默认不提供全书无边界 replay。

### 9.5 验收

- 删除 summary 后 retry summary 可恢复。
- 重复 replay 同一章节不会重复累计 state / index / memory / vector 数据。
- vector key 缺失时 vector failed，其余 writer done。
- 配置 key 后 retry vector 只补 vector。
- replay 后 state/index/summary 与 commit 链一致。

### 9.6 回退

- 隐藏或下线 projections CLI。
- 继续使用旧 chapter commit 流程。

---

## 10. Phase 6：Skill / Agent 契约补强

### 10.1 目标

按官方 `plugin-dev` 规范增强 Skill / Agent 的触发、工具范围、输出契约。

### 10.2 修改范围

修改：

- `webnovel-writer/skills/*/SKILL.md`
- `webnovel-writer/agents/*.md`
- `webnovel-writer/scripts/data_modules/tests/test_prompt_integrity.py`

可选新增：

- `webnovel-writer/agents/continuity-reviewer.md`
- `webnovel-writer/agents/style-reviewer.md`
- `webnovel-writer/agents/reader-pull-reviewer.md`

### 10.3 具体工作

1. Skill frontmatter：
   - 补强 `description`，写清触发场景和不适用场景。
   - 保持 `SKILL.md` 精简。
   - 大段规则移动到 `references/`。
2. Agent frontmatter：
   - 补 `name`。
   - 补具体 `description`。
   - 明确 `tools`。
   - 需要时补 `model`。
3. Agent 输出契约：
   - reviewer 输出维度固定。
   - data-agent 明确只产出 artifacts，不写 projection。
   - context-agent 明确上下文优先级。
4. 用 plugin-dev 的 validate-agent 规则做人工或脚本校验。

### 10.4 影响

用户影响：

- Claude Code 触发技能和代理更稳定。
- 误触发和漏触发减少。

代码影响：

- 主要是 prompt / markdown 文件。
- 可能影响 Claude Code 的选择行为。

风险：

- description 改动导致触发习惯变化。

控制：

- 改一组测一组。
- 增加 prompt integrity 测试。
- 保留命令名称不变。

### 10.5 验收

- 7 个 Skill 都有明确触发型 description。
- 4 个现有 Agent frontmatter 符合 plugin-dev 要求。
- prompt integrity 测试通过。
- data-agent 文档仍明确不写 state/index/summary/memory。

### 10.6 回退

- 单个 Skill / Agent 可独立回滚 frontmatter。
- 不影响 Python runtime。

---

## 11. Phase 7：Behavior Evals

### 11.1 目标

验证插件在真实行为层面是否按协议执行，而不是只验证 Python 函数。

### 11.2 修改范围

新增：

- `webnovel-writer/evals/`
- `webnovel-writer/scripts/run_behavior_evals.py`
- `webnovel-writer/evals/fixtures/`

修改：

- CI / 本地测试文档。
- `docs/operations/operations.md`

### 11.3 具体工作

1. 建立 eval 分类：
   - skill triggering
   - workflow behavior
   - agent output schema
   - continuity conflict
   - memory commit
2. 首批用例：
   - init 不污染插件目录。
   - write 遇 blocking issue 不进入 commit。
   - data-agent 不写 projection。
   - commit 驱动 projection。
   - dashboard 只读。
3. Runner 输出 JSON 报告。
4. 区分 fast fixture eval 和 slow transcript eval。

### 11.4 影响

用户影响：

- 无直接使用变化。
- 发布前可靠性更高。

代码影响：

- 增加测试资产。
- CI 时间可能增加。

风险：

- transcript eval 成本高、慢。

控制：

- 默认只跑 fast。
- slow 只在发布前或手动运行。

### 11.5 验收

- 每个 Skill 至少一个 eval。
- `/webnovel-write` 覆盖成功链路和 blocking 链路。
- eval report 有 pass/fail/reason/artifacts。

### 11.6 回退

- eval 不参与默认流程时可暂时跳过。
- 不影响 runtime。

---

## 12. Phase 8：Package Validator

### 12.1 目标

防止 manifest、marketplace、README、version、frontmatter 漂移。

### 12.2 修改范围

新增：

- `webnovel-writer/scripts/validate_plugin_package.py`
- `webnovel-writer/scripts/tests/test_validate_plugin_package.py`

修改：

- `docs/operations/plugin-release.md`
- `docs/guides/commands.md`

### 12.3 具体工作

1. 检查 `.claude-plugin/plugin.json`：
   - name kebab-case。
   - version semver。
   - description 非空。
2. 检查 marketplace 文件。
3. 复用或对齐现有 Plugin Version Check：
   - marketplace version。
   - plugin.json version。
   - README 中既有版本位置 / 版本表。
   - 不新增一套与现有 CI 冲突的 README badge 规则。
4. 检查 skills frontmatter。
5. 检查 agents frontmatter。
6. 检查 hooks schema。
7. 检查 LICENSE。
8. 检查 Dashboard dist。
9. 检查无硬编码本机绝对路径。

### 12.4 影响

用户影响：

- 发布包更稳定。

代码影响：

- 新增发布前校验脚本。

风险：

- 校验规则过严影响开发阶段。
- 版本校验与现有 CI 不一致，导致本地通过但 CI 失败，或相反。

控制：

- 区分 `--strict` 和默认模式。
- 默认只阻断明显错误。
- 先读现有 CI / release 文档，再实现版本检查。

### 12.5 验收

- clean clone 校验通过。
- version 任一处漂移时失败。
- 版本漂移规则与现有 CI 一致。
- 删除 Skill frontmatter 时失败。
- hooks 路径不用 `${CLAUDE_PLUGIN_ROOT}` 时 warning 或失败。

### 12.6 回退

- release 流程暂不调用 validator。
- 不影响插件运行。

---

## 13. Phase 9：Hooks

### 13.1 目标

基于 Phase 1 的 `project-status` 提供轻量状态摘要，并对最危险的绕过 runtime 写入做兜底提醒 / 阻断。

### 13.2 修改范围

新增：

- `webnovel-writer/hooks/hooks.json`
- `webnovel-writer/hooks/session_start.py`
- `webnovel-writer/hooks/scripts/guard-runtime-write.py`

修改：

- `webnovel-writer/scripts/data_modules/webnovel.py`
- `webnovel-writer/.claude-plugin/plugin.json`，仅在需要显式声明 hook 路径时修改。
- `docs/operations/operations.md`

### 13.3 具体工作

1. `SessionStart` hook：
   - 只输出短摘要。
   - 不写文件。
   - 不运行完整 doctor。
   - 调用 `webnovel.py project-status --format summary`。
   - 可通过 env 关闭。
2. `PreToolUse` hook：
   - 阻断直接写 `.story-system/commits`。
   - 阻断直接写 `.webnovel/state.json`、`index.db`、`memory_scratchpad.json`。
   - 对 Bash 中绕过 gate 的危险 commit / projection 命令做 best-effort 检测。
   - 不把 Bash 字符串解析当作唯一硬保证。
3. 按 plugin-dev hook-development 校验：
   - `hooks/hooks.json` 使用 wrapper 格式。
   - hook 命令使用 `${CLAUDE_PLUGIN_ROOT}`。
   - hook 脚本校验 stdin JSON。

### 13.4 影响

用户影响：

- 新对话能看到短状态。
- 直接改主链 / projection 文件会被阻断或要求显式走 runtime。

代码影响：

- 新增 hooks 目录。
- Claude Code 会话启动多一次轻量命令。

风险：

- hook 输出太长影响上下文。
- hook 误阻断开发者调试。
- Bash 命令变体太多，hook 无法可靠识别全部绕过方式。

控制：

- 输出限制 8 行 / 1000 字符。
- 提供关闭 env。
- 先只阻断最危险路径。
- 真正可靠性仍由 runtime gate 和 commit 入口保证。

### 13.5 验收

- 无项目根时不报错。
- 有项目根时输出 latest chapter / phase / next action。
- 设置 disable env 后无输出。
- 直接写 commit 文件被阻断。
- 合法 runtime 命令不被阻断。
- `webnovel.py status` 仍保留宏观创作健康报告语义。

### 13.6 回退

- 删除或禁用 `hooks/hooks.json`。
- 保留 `project-status` CLI 不影响旧流程。

---

## 14. 横向影响分析

### 14.1 项目健康入口归属

| 入口 | 当前/目标职责 | 输出 | 是否深检 | 是否写文件 |
|---|---|---|---|---|
| `preflight` | 快速环境检查，保留兼容 | text/json | 否 | 否 |
| `project-status` | 机器可读短状态、phase、下一步 | summary/json | 否 | 否 |
| `doctor` | 文件/数据库/配置体检和修复建议 | text/json | 默认否，`--deep` 可选 | 否 |
| `status` / `status_reporter.py` | 宏观创作健康报告，如角色、伏笔、爽点、关系图谱 | markdown/text | 是，偏创作分析 | 现状可能输出报告文件，语义保持 |
| `build_story_runtime_health()` | 内部主链就绪度 helper | dict | 否 | 否 |

原则：

- 不把所有问题塞进一个命令。
- 不改变现有 `status` 语义。
- doctor 复用 preflight 和 story runtime health，不复制逻辑。

### 14.2 对用户命令的影响

新增命令：

- `/webnovel-doctor`
- `webnovel.py doctor`
- `webnovel.py write-gate`
- `webnovel.py projections`
- `webnovel.py project-status`

现有命令保持：

- `/webnovel-init`
- `/webnovel-plan`
- `/webnovel-write`
- `/webnovel-review`
- `/webnovel-query`
- `/webnovel-dashboard`
- `/webnovel-learn`

现有 `webnovel.py status` 保持转发到 `status_reporter.py`。

### 14.3 对项目数据的影响

新增文件：

- `.webnovel/projection_log.jsonl`
- 可能新增 `.webnovel/tmp/*` 的校验约定。

不改变：

- `.story-system/` 主链真源地位。
- accepted commit 是写后事实入口。
- `.webnovel/*` 是 projection / read-model。

### 14.4 对 Dashboard 的影响

短期：

- Dashboard 保持只读。
- 继续兼容 commit 内 `projection_status`。

中期：

- Dashboard 可展示 projection log。
- System 页可展示 doctor / project-status 摘要。

风险：

- Dashboard 前端 bundle 可能需要 rebuild。

### 14.5 对 RAG 的影响

默认：

- 缺 key 降级 BM25。
- `vectors.db` 缺失只 warning。

深度检查：

- 才测试 API 连通。

### 14.6 对测试的影响

新增测试量较大，需要分层：

- 单元测试：doctor / validator / gates / projection log。
- 集成测试：chapter commit + projection。
- 行为测试：skill / agent 协议。
- 发布测试：package validator。

---

## 15. 建议 PR 切分

### PR 1：Phase Resolver + Project Status + Doctor

包含：

- shared `project_phase`。
- `project-status` CLI。
- doctor runtime。
- doctor CLI。
- `/webnovel-doctor` Skill。
- doctor tests。
- preflight 快检复用关系。

不包含：

- write-gate。
- projection log。
- hooks。

### PR 2：Validator + Gates

包含：

- artifact validator。
- write-gates。
- prewrite gate 包装现有 `PrewriteValidator`。
- `/webnovel-write` 更新。
- gate tests。

### PR 3：Projection Writer 幂等审计

包含：

- state / index / summary / memory / vector writer 幂等测试。
- replay 风险评估。

### PR 4：Projection Log

包含：

- projection log。
- chapter commit 双写。
- doctor / dashboard 兼容读取。

### PR 5：Projection Retry / Replay

包含：

- projection runner。
- projections CLI。
- writer 幂等测试。

### PR 6：Skill / Agent 契约

包含：

- skill frontmatter。
- agent frontmatter。
- prompt integrity tests。

### PR 7：Evals + Package Validator

包含：

- behavior eval runner。
- validate plugin package。
- release docs。

### PR 8：Hooks

包含：

- SessionStart hook。
- PreToolUse guard。
- plugin-dev hook validation。

---

## 16. 总体验收

完成后应满足：

1. 用户能运行 `/webnovel-doctor` 看懂项目文件、数据库、配置是否正常。
2. `project-status` 能给短状态，且不占用现有 `status_reporter.py`。
3. init 刚结束不会因为缺 commit / summary / vectors 被误报。
4. 写章只在三个自然边界增加 gate 检查。
5. agent 产物 schema 错误能被统一报告。
6. projection 失败能定位 writer，并能补跑。
7. commit 事实和 projection 执行日志可区分。
8. Skill / Agent / Hook 结构符合官方 `plugin-dev` 规范。
9. 发布前能校验插件包一致性。

---

## 17. 最小先行版本

如果要尽快落地一版高收益版本，建议只做前三项：

1. `doctor`
2. `project-status` / `project_phase`
3. `artifact_validator`
4. `write-gate`

这三项能先解决最核心的问题：

- 用户知道项目哪里坏。
- runtime 和短状态共用同一套 phase。
- runtime 知道 agent 产物是否可信。
- 写章关键边界不再只靠文档约束。

Projection log、retry/replay、hooks 和 evals 可以在基础稳定后继续推进。
