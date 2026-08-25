# Webnovel Writer 当前状态与待完成清单

> 核对日期：2026-08-25
> 适用范围：`C:\lgq\ai-workspace\projects\claude-plugins\webnovel-writer`
> 状态依据：当前代码、测试输出、Git 提交记录；方案文档只作为设计意图和历史记录。

## 状态规则

| 标记 | 含义 |
|---|---|
| `[x]` | 已实现，并有代码与测试/可复现命令证据 |
| `[~]` | 部分实现，剩余范围已明确 |
| `[ ]` | 尚未实现，或没有足够证据证明已实现 |
| `[blocked]` | 因明确外部条件暂时无法推进 |
| `[superseded]` | 被后续架构或计划取代，不再按原方案实施 |

## 已完成事项

### v6 Runtime 基线

- `[x]` 统一 CLI 入口、项目阶段推导和短状态：`scripts/webnovel.py`、`project_phase.py`、`project_status.py`。
- `[x]` 阶段感知体检：`doctor.py`，覆盖项目文件、合同、SQLite、RAG、Python 依赖和 Dashboard 产物。
- `[x]` 三道写作闸门：`write_gates/prewrite.py`、`precommit.py`、`postcommit.py`。
- `[x]` Agent 产物校验：`artifact_validator.py` 及对应测试。
- `[x]` Story System 合同、章节提交和事件审计主链：`.story-system/` 相关 runtime 已存在。
- `[x]` projection retry/replay、projection log、memory correction、contract migration 等 v6 运维能力已存在。
- `[x]` P0/P1 审计项按 [审计修复台账](../tasks/architecture-audit-fix-ledger.md) 已标记完成；P2 剩余项不应再误标为已完成。

### 作者体验与验证

- `[x]` 作者术语、错误目录、审查作者视图、统一用户报告和运行账本 runtime 已存在：`author_glossary.py`、`error_catalog.py`、`review_author_view.py`、`user_report.py`、`run_ledger.py`、`run_logger.py`。
- `[x]` 插件包校验通过：`python -X utf8 webnovel-writer/scripts/validate_plugin_package.py --format json`。
- `[x]` 快速行为评估通过：`run_behavior_evals.py`，当前结果为 18/18。
- `[x]` `run_ledger.py` 与 Prompt integrity 相关测试通过。
- `[x]` Dashboard FastAPI 后端、React/Vite 源码和预构建 `dist/` 已存在。

### 设定增强实验

- `[x]` `fantasy01` 已建立 Markdown 设定卡实验目录，包含能力、物品、资源和战力锚点卡。
- `[x]` 插件 `context-agent`、`reviewer`、`webnovel-plan` 已加入设定卡按需读取规则。
- `[~]` 设定卡实验尚未完成第 23-25 章效果验证，不能据此宣称通用设定 Schema 已完成。

## 当前待完成事项

### P0：先恢复可验证基线

- `[x]` 修复 Windows 长路径导致的投影写入失败与备份瞬时占用误报（2026-08-26）。
  - 根因一：`LongPathsEnabled=0` 时 >260 字符路径 `mkstemp`/`os.replace` 报 ENOENT/WinError 5；`security_utils.atomic_write_json` 系列已加 `_win_long_abs()` 扩展前缀保护（阈值 200 字符，预留文件名增长），新增回归测试 `test_atomic_write_json_beyond_max_path`。
  - 根因二：本地备份目录 rename 遇杀毒/索引器瞬时占用；复用 issue #125 退避重试（`_replace_with_retry`）。
  - 证据：commit `1e1b4ac`、`ecc24de`；全量 `python -m pytest -q --no-cov` 通过。
  - 附带发现（环境项，非代码缺陷）：仓库曾被整树复制，陈旧 `__pycache__` 内嵌旧 checkout 源码路径并通过 mtime/size 校验，导致 traceback 指向 `tencent_opc` 且测试加载旧模块；已清理全部 `__pycache__` 与 `.coverage`。若再次出现异仓帧，优先清缓存排查。
- `[~]` 版本状态统一（2026-08-26 登记差异）：
  - 已核实：`.claude-plugin/marketplace.json`、`webnovel-writer/.claude-plugin/plugin.json`、README badge 均为 `6.2.1`；项目 `AGENTS.md` 记录本地改造版本为 `v6.3.0（未发布）`，即 manifest 尚未随开发分支 bump——属"未发布前保持 6.2.1"的预期状态，非数据漂移。
  - 待作者决策后执行：发布 v6.3.0 时按发版流程同步三处版本号与 release notes；在此之前不改任何版本字段。
  - 决策入口：`[ ]` 确定并统一发布版本号（依赖作者拍板）。

### P1：完成 v6 必要收尾，不再扩张 v6

- `[x]` 隐私出网守卫（2026-08-26）：无 `EMBED_API_KEY` 时向量投影在进入网络路径前直接跳过（原因 `no_api_key`），零 HTTP 请求；检索退回 BM25。
  - 证据：`vector_projection_writer.apply()` 前置守卫；测试 `test_no_api_key_skips_without_network`（触达 `_store_chunks` 即失败）；文档新增「数据出网说明」（`docs/guides/rag-and-config.md`）与 README 提示。
- `[x]` CI 加固（2026-08-26）：`plugin-version.yml` 顶层 `permissions: contents: read`；release 的 `workflow_dispatch.version` 增加 semver 前置校验；`softprops/action-gh-release` pin 到已验证 commit `3bb1273…`（v2.6.2）；`git ls-remote` 区分"查询失败"与"标签不存在"，查询异常时显式报错而非静默建 tag。
  - 证据：两个 workflow YAML 通过 `yaml.safe_load` 解析；线上行为需待下次 push/release 触发验证。
- `[ ]` 对 v6 作者体验计划的未完成项逐项核账：完整 Skill 接入、未知错误降级、自动处理说明和续跑边界；已实现项在原计划中改为 `[x]` 或在条目旁注明代码证据。

### P2：v7 Story Repo 迁移

- `[ ]` 实现 v6 → v7 只读迁移器：生成 `book.yaml`、`定稿/`、`大纲/`、`文风/` 和初始迁移提交，原 v6 数据保持可回退。
- `[ ]` 实现 `.cache/index.db` 的全量重建，并验证删除缓存后查询仍可用。
- `[ ]` 以 `fantasy01` 第 23 章做第一条垂直切片：决策卡 → 上下文包 → 草稿 → 机检 → 作者验收 → settle → Git commit。
- `[ ]` 明确 v6/v7 双格式期间的唯一写入路径，禁止同一章节双写。

### P2：支撑能力

- `[ ]` 长路径防护收口：`security_utils` 已覆盖原子写入/读取/备份恢复，但 `run_ledger.file_signature`、dashboard 文件读取、`chapter_paths.find_chapter_file` 等触点仍走原生路径，>260 字符场景会失败；统一封装后再移除散点转换。
- `[ ]` 题材 taxonomy：把现有 `resolve_genre()`、模板归一化和 alias 逻辑收敛到单一 taxonomy index，并补全入口测试。
- `[ ]` 设定增强通用化：先根据 `fantasy01` 实验结果抽象 Markdown 卡片契约，再决定是否引入 Pydantic 子模型；暂不直接引入三套 JSON Schema。
- `[ ]` `fantasy01` 验证：生成第 23 章合同后，用第 23-25 章确认设定卡确实改善能力代价、战力边界和资源设定一致性。
- `[ ]` 上下文减负收尾：清理已迁移的死 reference、复核 loading map，并用行为契约替代纯文案断言。
- `[ ]` 多宿主适配：仅在 v7 垂直切片稳定后，先选择一个宿主建立 adapter、support.md、生成器和 smoke test；不同时铺开多个宿主。

### 明确不再按原计划推进

- `[superseded]` `docs/superpowers/plans/2026-06-10-audit-fix-plan.md` 中已在文件顶部声明作废的 Task 8-24、26-27、29-34：目标属于 v7 将删除或重构的 v6 模块，不再按原步骤修缮。
- `[superseded]` 把 Graphiti/Neo4j、Letta、MIRIX 作为当前事实主库：仅保留研究参考，不引入第二事实源。
- `[superseded]` 直接重写全部 v6 代码：改用 v6 稳定收尾 + v7 绞杀式迁移。

## 执行顺序

1. 修复并确认全量测试基线，统一版本状态。
2. 完成隐私出网和 CI 这两个 v6 必要收尾项。
3. 做 `fantasy01` 第 23-25 章设定卡实验验证。
4. 实现 v7 迁移器和第一条垂直切片。
5. 再推进 taxonomy、上下文减负、设定增强通用化和单宿主 adapter。

## 每项完成时必须留下的证据

- 代码路径或文档路径。
- 相关测试命令及结果。
- 若改变架构，注明影响的 v6/v7 不变量。
- 对应清单条目状态和完成日期。
- 一个独立 Git commit；未验证不得标 `[x]`。
