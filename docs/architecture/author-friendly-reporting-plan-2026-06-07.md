# 作者友好报告与异常可见性改造 Plan

> 日期：2026-06-07
> 状态：核心 runtime 已落地；跨 Skill 全量收尾仍待完成（2026-08-25 核对）
> 范围：承接 spec 的「作者外壳 / 作者界面层」七组件，统一 `init / plan / write / review` 的最终汇报、subagent 返回协议、错误目录、审查作者视图、下一步建议、异常分类、耗时呈现与作者友好术语；先取消 token 统计
> 核心原则：问题不静默、自动处理要说明、技术细节默认隐藏、最终报告面向作者而不是工程日志；工程内核不动
> 实施方式：先用 Skill / Agent 契约固定行为，再用 runtime helper 收敛格式，避免只靠提示词导致输出漂移
> 状态说明：`author_glossary.py`、`error_catalog.py`、`review_author_view.py`、`user_report.py`、`run_ledger.py`、`run_logger.py` 与相关测试已存在；本文原有未勾选项保留为历史施工细目，当前剩余项以 `docs/plans/2026-08-25-status-and-pending-work.md` 为准。

---

## 0. 与产品 Spec 的对齐关系

本计划是 `docs/superpowers/specs/2026-06-07-author-friendly-experience-design.md` 的工程落地计划，不再另起一套产品口径。

分工如下：

| 文档 | 负责什么 | 不负责什么 |
|---|---|---|
| 产品 spec | 定义「工程内核 + 作者外壳」分层、七个组件、错误恢复红线、分期价值 | 不展开具体文件、测试与施工顺序 |
| 本 plan | 把七组件落到 Skill / Agent / runtime helper / 测试 / 文档 | 不重新定义产品目标，不放宽 spec 红线 |

对齐后的共同边界：

- Story System、`write-gate`、`chapter-commit`、projection、RAG 等工程内核不改语义、不降校验强度。
- 作者默认看到里程碑、结论、影响和下一步；工程命令、JSON、schema、traceback 默认写入日志或技术详情。
- 自动处理只限幂等、可重试、不碰作者内容的过程性问题；最终报告必须说明处理过什么，不能静默。
- 不新增 UI、按钮、进度条、命令别名或自动修复大循环。

七组件在本计划中的落点：

| spec 组件 | 本 plan 落点 |
|---|---|
| 术语对照表 | §5 单一事实源；Phase 1 先落结构化词表 |
| 进度播报规范 | §8 过程易用性；Phase 5A |
| 错误→行动映射表 | §15 异常分类 + Phase 4 runtime helper；新增 `error_catalog.py` 与 `author_error_catalog.json` |
| 审查作者视图 | §16 helper / `review_pipeline.py` 渲染；Phase 4 优先接 `review` |
| 导航尾巴 | §4 三段式报告第三段；§20 推荐施工顺序中作为早期交付 |
| 命令任务化 | §4 / §19 / §23 的下一步建议；只改提示语言，不新增别名 |
| 可自动处理项 + 默认不展示工程细节 | §3.2-3.4、§11、§15、§21；第三期前只做说明和日志，不扩白名单 |

## 0.1 当前状态核账（2026-08-26）

> 本节是本计划的当前状态入口。后续施工时，旧阶段中的 `[ ]` 保留为原始计划快照；不得只依据旧勾选框判断当前状态，必须同步更新本节和 `docs/plans/2026-08-25-status-and-pending-work.md`。

| 计划区段 | 逐项核账结论 | 代码 / 测试证据 | 剩余工作 |
|---|---|---|---|
| Phase 0：基线审计（0.1-0.7） | `[x]` | 本计划、统一 backlog、四个主 Skill、四个 Agent、runtime 命令和测试已完成交叉盘点 | 后续新增字段或错误码需继续登记 |
| Phase 1：四个主 Skill 最终报告（1.1-1.4，共 13 项） | `[x]` | `skills/webnovel-{init,plan,write,review}/SKILL.md` 均包含作者友好报告契约；`test_prompt_integrity.py`、18/18 behavior eval 通过 | 暂无本阶段阻断项 |
| Phase 2：SubagentRun 返回协议（2.1-2.5，共 5 项） | `[~]` | 四个 Agent 文档均声明 `status/problems/auto_handled/needs_user_action/duration_ms/outputs`；主流程提示也要求汇总 | 当前没有独立 runtime telemetry / 持久化 `subagent_runs`，主要依赖主流程遵守提示协议 |
| Phase 3：异常分类与耗时呈现（3.1-3.7，共 7 项） | `[x]` | `author_error_catalog.json`、`error_catalog.py`、`user_report.py` 已实现；`test_error_catalog.py`、`test_user_report.py` 通过；token 不进入作者报告 | 新增错误码时需同步错误目录 |
| Phase 4：Runtime 报告 Helper（4.1-4.8，共 8 项） | `[x]` | `review_author_view.py` 已被 `review_pipeline.py` 调用；`user_report` CLI 已在统一入口注册；相关 helper 测试通过 | 暂无本阶段阻断项 |
| Phase 5A：过程提示与 Prompt integrity（5A.1-5A.8） | `[x]` | 四个主 Skill 有过程节点、恢复说明、有限裁决和日志约定；Prompt integrity 通过 | 文案变更仍需保持行为级断言 |
| Phase 5B：运行账本与续跑测试（5B.1-5B.6，共 6 项） | `[x]` | `run_ledger.py`、`run_logger.py` 已实现；六个计划测试均存在并通过，全量 pytest 通过 | 其他长路径触点的统一封装列入总 backlog |
| Phase 5C：行为验证（5C.1-5C.8，共 8 项） | `[~]` | fast behavior eval 18/18 通过，覆盖报告分类、缺 artifact、projection retry、blocking 等 fixture | 尚缺真实 Claude Code 会话级端到端验证，以及全部交互裁决分支的自动回放 |
| Phase 6：测试与行为验证（6.1-6.4，共 15 项） | `[x]` | Prompt integrity、helper/runtime tests、package validator、behavior eval 均已存在并通过 | 发布前仍需按环境运行真实冒烟 |
| Phase 7：文档与 README（7.1-7.4，共 8 项） | `[x]` | README、`docs/guides/commands.md`、`docs/operations/operations.md` 已包含报告状态、恢复、日志和自动处理说明 | 文档新增命令时继续同步索引 |

### 核账结论

- `[x]` 已完成：Phase 0、1、3、4、5A、5B、6、7 的计划交付物和本地验证已具备证据。
- `[~]` 部分完成：Phase 2 的 subagent runtime 汇总，以及 Phase 5C 的真实宿主/交互行为验证。
- `[ ]` 当前新增待办：只保留在统一 backlog 中，不在本计划重复维护第二套未来任务清单。
- 总体状态为：**部分完成**。这不影响已有作者报告 helper 和静态行为验证，但不能宣称完整作者体验闭环已完成。

## 1. 目标

本计划把 `webnovel-writer` 的交付体验从“流程执行完以后由主 agent 自行总结”改成“每次都有稳定、可读、可信的作者回执”。

核心交付：

1. 统一最终报告规范：所有主 Skill 结尾都输出固定三段式报告，并以一句总状态开头。
2. 全局作者友好约束：中文、少术语、不静默、自动处理要说明、技术细节按需展开。
3. 阶段化报告模板：分别补强 `/webnovel-init`、`/webnovel-plan`、`/webnovel-write`、`/webnovel-review` 的最终汇报要求。
4. Subagent 返回协议：主流程能汇总 `context-agent`、`reviewer`、`data-agent`、`deconstruction-agent` 的状态、问题、自动处理与耗时。
5. 异常分类：所有问题归入“已自动处理 / 建议确认 / 必须处理”，重点暴露 subagent 失败、跳过、重试和输出不完整。
6. 耗时可见：记录已耗时和关键步骤耗时；长时间无进展时说明可能原因和是否影响结果，不承诺固定完成时间。
7. 术语翻译：工程词默认翻译成作者能理解的写作语义。
8. Runtime helper：新增统一报告 helper，优先消费已有 `project-status`、`doctor`、`write-gate`、`review-pipeline`、`chapter-commit`、`projection_log` 等结构化输出。
9. 过程易用性：在长流程执行中提供清晰进度、少打扰确认、可恢复状态和作者可理解的卡点说明。
10. 断点续跑：重复执行同一主命令时，能识别已完成步骤，从最近可信断点继续，而不是要求作者记补跑命令。
11. 交互式裁决：必须用户处理的问题优先给有限选项，减少“自己去改文件”的认知负担。
12. 技术溯源：作者报告保持清爽，同时把工程细节写入本地日志，便于故障反馈和开发排查。
13. 错误目录：把 runtime 错误码映射为作者能理解的原因、影响和下一步动作。
14. 审查作者视图：在审查报告顶部提供一句结论和最多 3 条可执行修改建议。
15. 下一步建议：每条主命令结束后给出任务化说明和可复制命令，不新增命令别名。

---

## 2. 背景

当前项目底层流程已经比较完整：

- `project-status` 能判断项目阶段和下一步。
- `doctor` 能给阶段感知体检。
- `write-gate` 已覆盖写前、提交前、提交后三个边界。
- `review-pipeline` 能规范化审查结果、生成报告并落库。
- `chapter-commit` 能生成写后事实并驱动 state / index / summary / memory / vector 投影。
- `projection_log` 能定位投影状态。

问题不在于缺少检查，而在于这些检查结果没有稳定地翻译给作者：

1. 最终回复格式不稳定，作者每次要重新判断“到底完成了没有”。
2. 技术细节、JSON、命令输出容易直接暴露，阅读负担偏重。
3. 某些降级、跳过、重试或自动处理只存在于流程内部，最终汇报不一定说明。
4. subagent 成败、输出完整性和耗时没有统一汇总。
5. `init / plan / write / review` 四条主流程的成功标准清楚，但“如何交付给作者”的要求不够清楚。
6. 长流程执行过程中，作者不一定知道当前做到哪一步、为什么在等、是否需要介入、能不能中断后继续。
7. 偶发失败后，作者往往需要理解内部步骤和补跑命令，恢复成本偏高。
8. 必须用户裁决的问题容易变成“报错退出 + 长解释”，没有被收敛成清晰选择。

本轮改造不重写写作主链，不新增自动修复大循环；重点补“作者可理解的交付层”。

---

## 3. 设计原则

### 3.0 Claude Code 能力边界

所有改造必须基于 Claude Code 已有能力和本插件可实现的 runtime 能力，不编造宿主不存在的 UI、后台任务或交互机制。

已可依赖的能力：

- Skill 通过 `SKILL.md` 约束流程和最终输出。
- 主流程可使用 Claude Code 的 `Agent` 工具调用已注册 subagent。
- 主流程可使用 `AskUserQuestion` 做关键裁决，前提是该 Skill frontmatter 已允许并且宿主环境支持。
- 主流程可通过 `Read` / `Write` / `Edit` / `Bash` 等工具读取、写入和运行本插件脚本。
- 插件 runtime 可通过 Python CLI 读写 `.webnovel/`、`.story-system/`、日志和中间产物。

不能假设的能力：

- 不能假设 Claude Code 有实时进度条、图形化按钮、后台任务队列或终端内原生选择菜单。
- 不能假设 subagent 会自动返回结构化元数据；需要通过 prompt 协议和主流程记录来实现。
- 不能假设重复运行 Skill 会天然断点续跑；断点续跑必须由本插件 runtime 读取产物、run ledger 和 gate 结果实现。
- 不能假设 AskUserQuestion 可以承担复杂表单；裁决选项应保持 2-3 个短选项。
- 不能假设日志、耗时、恢复点会自动存在；这些必须由脚本或主流程显式记录。

因此，本计划中的“过程提示”是主流程在关键节点输出短提示；“交互式裁决”是基于 `AskUserQuestion` 或普通对话提问的有限选择；“断点续跑”是插件 runtime 的文件与状态检查能力，不是 Claude Code 内置工作流引擎。

### 3.1 作者友好，不工程炫技

默认用作者能理解的中文表达，不直接输出 `subagent`、`artifact`、`projection`、`schema`、`runtime contract` 等工程词。

必要时可以在问题详情中保留文件路径和命令，但默认先讲影响：

```text
“保存本章故事事实”失败，会影响后续查询本章发生过什么。
```

而不是：

```text
data-agent artifact schema_error: extraction_result missing accepted_events
```

### 3.2 问题不静默

以下情况必须在最终报告中出现：

- subagent 调用失败。
- subagent 被用户模式选择跳过。
- subagent 输出不完整。
- reviewer 跳过或 `--minimal` 写 no-review artifact。
- data-agent 三份结果缺失或 schema 不合格。
- `write-gate` 任一阶段 failed。
- `chapter-commit` rejected。
- projection failed / pending / missing。
- RAG 降级。
- 备份失败。
- 耗时异常。

### 3.3 自动处理必须说明

系统自动做过的事要简短说明，包括：

- 自动补跑 projection。
- 自动降级到关键词检索。
- 自动应用白名单内的非阻断定点处理，例如格式整理或明确的错别字修正。
- 自动覆盖旧的 no-review artifact。
- 自动初始化 Git 或退回本地备份。

说明不需要讲全部过程，只说明“处理了什么、是否影响结果”。

### 3.4 技术细节默认隐藏

最终报告优先给结论和影响。只有当用户需要处理时，再给路径、命令或错误类型。

### 3.5 Runtime 优先，提示词兜底

能由 runtime 确认的状态，不靠主 agent 口头判断。

最终报告 helper 优先消费结构化数据：

- `project-status --format json`
- `doctor --format json`
- `write-gate --format json`
- `review-pipeline` payload
- `chapter-commit` payload
- `projection_log`
- subagent run summary

Skill 文档只规定“必须汇报什么”，不让每个 Skill 自己发明报告格式。

### 3.6 过程易用性也是交付的一部分

最终报告只能降低“结束后的不确定感”，不能解决执行过程中的焦虑。

长流程必须让作者持续知道四件事：

1. 当前在做哪一步。
2. 这一步大概会产生什么。
3. 是否需要作者做决定。
4. 如果卡住，卡点是什么、会不会影响已有成果。

过程提示应该短、少术语、少打扰。默认由系统继续推进，只有真正影响创作方向、事实一致性或文件安全时才打断用户。

### 3.7 恢复应优先自动化

“告诉作者怎么恢复”是底线，“作者重新执行同一个命令即可自动续跑”才是目标。

主流程应逐步做到幂等：

- 已完成且可信的产物不重复生成。
- 失败后保留已有正文、审查报告和中间结果。
- 再次执行同一命令时，先检查断点状态，再从最近失败步骤继续。
- 只有产物过期、参数变更或用户明确要求重写时，才重新执行前置步骤。

### 3.8 技术溯源不打扰作者

作者默认看不到 JSON、schema、traceback 和完整命令日志。

但系统需要保留本地溯源材料：

- 用于开发者定位问题。
- 用于用户反馈不可恢复故障。
- 用于 runtime helper 判断断点和步骤状态。

普通报告只给一条低干扰提示：

```text
如需反馈故障，可附上 .webnovel/logs/run_last.log。
```

---

## 4. 统一最终报告规范

所有主 Skill 最终输出统一为：

```text
总状态：已完成 / 部分完成 / 需要你处理 / 未完成。

一、产生的文件与完成情况
- ...

二、过程中遇到的问题与异常耗时
- 已自动处理：...
- 建议确认：...
- 必须处理：...
- 耗时异常：...

三、下一步建议
- ...
```

状态含义：

| 状态 | 含义 |
|---|---|
| 已完成 | 当前阶段产物齐全，关键检查通过，可以进入下一步 |
| 部分完成 | 有主要产物，但存在跳过、降级、未完成项或非阻断问题 |
| 需要你处理 | 当前结果可保存，但必须由用户确认、裁决或补充信息 |
| 未完成 | 关键产物缺失或阻断失败，不能继续下一阶段 |

---

## 5. 术语翻译表（单一事实源）

术语翻译不是每个 Skill 各写一份，而是作为 Author Layer 的单一事实源维护。

首版采用结构化数据，便于 runtime helper 和 prompt integrity 测试复用：

```text
webnovel-writer/references/author_glossary.json
```

可选补一份面向文档阅读的 Markdown 摘要，但实现与测试只以 JSON 为准。

维护规则：

- Skill / Agent 文档可以引用术语，但不得自造不同译法。
- `user_report.py`、`error_catalog.py`、审查作者视图都从同一术语表取作者友好表达。
- 未登记的新工程词默认保留原词，并在报告中优先解释影响；后续再补词表，不临场硬翻。
- 词表测试只检查关键术语是否存在、是否有作者解释，不锁死完整文案。

| 工程词 | 作者友好表达 |
|---|---|
| subagent | 写作助手 / 审查助手 / 资料整理助手 / 拆书助手 |
| context-agent | 写前准备 |
| reviewer | 写作检查 |
| data-agent | 保存本章故事事实 |
| deconstruction-agent | 参考作品拆解 |
| artifact | 中间结果文件 |
| review_results | 写作检查结果 |
| fulfillment_result | 本章目标完成情况 |
| disambiguation_result | 待确认的人名/设定歧义 |
| extraction_result | 本章新发生的故事事实 |
| chapter-commit | 提交本章事实 |
| projection | 更新故事资料 |
| state / index / summary / memory / vector | 状态 / 索引 / 摘要 / 长期记忆 / 检索库 |
| blocking issue | 会影响继续写作的问题 |
| fallback | 临时降级读取 |
| runtime contract | 本章写作要求 |
| schema error | 中间结果格式不完整 |
| pending | 等待确认 |
| rejected | 本章事实未通过提交 |
| accepted | 本章事实已通过提交 |

---

## 6. 修改范围

### 6.1 Skill / Agent 文档

- `webnovel-writer/skills/webnovel-init/SKILL.md`
- `webnovel-writer/skills/webnovel-plan/SKILL.md`
- `webnovel-writer/skills/webnovel-write/SKILL.md`
- `webnovel-writer/skills/webnovel-review/SKILL.md`
- `webnovel-writer/agents/context-agent.md`
- `webnovel-writer/agents/reviewer.md`
- `webnovel-writer/agents/data-agent.md`
- `webnovel-writer/agents/deconstruction-agent.md`

### 6.2 Runtime helper

新增：

- `webnovel-writer/references/author_glossary.json`
- `webnovel-writer/references/author_error_catalog.json`
- `webnovel-writer/scripts/data_modules/author_glossary.py`
- `webnovel-writer/scripts/data_modules/error_catalog.py`
- `webnovel-writer/scripts/data_modules/review_author_view.py`
- `webnovel-writer/scripts/data_modules/user_report.py`
- `webnovel-writer/scripts/data_modules/run_ledger.py`
- `webnovel-writer/scripts/data_modules/run_logger.py`
- `webnovel-writer/scripts/data_modules/tests/test_author_glossary.py`
- `webnovel-writer/scripts/data_modules/tests/test_error_catalog.py`
- `webnovel-writer/scripts/data_modules/tests/test_review_author_view.py`
- `webnovel-writer/scripts/data_modules/tests/test_user_report.py`
- `webnovel-writer/scripts/data_modules/tests/test_run_ledger.py`
- `webnovel-writer/scripts/data_modules/tests/test_run_logger.py`

修改：

- `webnovel-writer/scripts/data_modules/webnovel.py`
- `webnovel-writer/scripts/review_pipeline.py`
- `webnovel-writer/scripts/data_modules/tests/test_webnovel_unified_cli.py`
- `webnovel-writer/skills/webnovel-write/SKILL.md`

### 6.3 Prompt / behavior 测试

修改或新增：

- `webnovel-writer/scripts/data_modules/tests/test_prompt_integrity.py`
- `webnovel-writer/evals/fixtures/behavior/fast.json`

---

## 7. 能力映射与实现边界

| 易用性目标 | 可用 Claude Code 能力 | 插件需新增 / 修改 | 不依赖 |
|---|---|---|---|
| 过程提示 | 主流程自然语言输出 | Skill 增加关键节点提示要求 | 实时进度条 |
| 开始前预期管理 | 主流程开头输出短说明 | Skill 增加流程概览模板 | 后台任务估时系统 |
| 最终报告 | 主流程最终回复 | `user_report.py` 渲染 text/json | Claude Code 自动格式化 |
| subagent 状态汇总 | `Agent` 调用 + 主流程记录 | `SubagentRun` 协议和主流程汇总 | subagent 自动 telemetry |
| 异常分类 | 主流程读取 runtime JSON | `user_report.py` 分类逻辑 | 宿主自动错误分类 |
| 耗时记录 | Bash / Python 计时或主流程记录 | run ledger / helper 记录步骤时间 | Claude Code 内置性能面板 |
| 断点续跑 | Bash 运行 Python CLI，读写本地文件 | `run_ledger.py`、产物可信度检查、gate 复用 | Claude Code 内置 resume 引擎 |
| 交互式裁决 | `AskUserQuestion` 或普通对话提问 | Skill 定义有限选项和处理分支 | 图形化按钮 / 复杂表单 |
| 技术溯源 | Python 写本地日志 | `run_logger.py`、敏感信息过滤 | 宿主自动日志导出 |
| 下一步命令 | 最终报告文本 | `user_report.py` 填入建议命令 | 一键按钮 |

实现原则：

1. 先用现有 Skill / Agent / Bash / Python CLI 能力落地。
2. 任何需要 runtime 判断的能力，都必须有本地文件、JSON 或命令输出作为依据。
3. 任何看起来像 UI 的体验，都只能表现为文本提示、有限提问或最终报告，除非未来另做 Dashboard 改造。
4. 不把 Claude Code 未承诺的行为写成验收标准。

---

## 8. 过程易用性设计

### 8.1 目标

让作者在流程运行中不需要理解内部工程链路，也能知道：

- 现在系统在做什么。
- 这一步为什么必要。
- 是否仍在推进。
- 什么时候需要自己拍板。
- 中途失败时已经完成了哪些部分，能从哪里继续。

过程体验不是把每条命令都打印出来，而是把长流程拆成作者能理解的“当前动作”。

### 8.2 开始前预期管理

长流程开始前，先给作者一个短概览：

```text
开始写第 13 章。本次会经过：整理依据 -> 起草正文 -> 写作检查 -> 润色 -> 保存本章故事事实 -> 更新资料并备份。
不同 API、模型和网络速度差异很大，本流程不承诺固定耗时；中途只有遇到创作裁决或事实冲突时才会问你。
```

预期管理必须包含：

- 本次目标。
- 主要步骤。
- 不承诺固定耗时的说明。
- 是否需要用户守在旁边。

### 8.3 统一过程提示格式

过程提示使用短句，不超过两行：

```text
正在整理本章写作依据：会读取章纲、最近剧情和未回收伏笔。
```

```text
正在保存本章故事事实：这一步会更新摘要、角色状态和后续检索资料。
```

避免：

```text
Running write-gate --stage precommit and validating artifacts...
```

### 8.4 阶段名翻译

| 内部步骤 | 过程提示名称 |
|---|---|
| preflight | 检查项目环境 |
| placeholder-scan | 检查未补齐占位 |
| story-system | 刷新本章写作要求 |
| write-gate prewrite | 写前检查 |
| context-agent | 整理写作依据 |
| draft | 起草正文 |
| reviewer | 写作检查 |
| review-pipeline | 生成检查报告 |
| polish | 润色与排版 |
| data-agent | 保存本章故事事实 |
| write-gate precommit | 提交前检查 |
| chapter-commit | 提交本章事实 |
| write-gate postcommit | 提交后确认 |
| projections retry | 补跑故事资料更新 |
| backup | 备份本章成果 |

### 8.5 少打扰确认策略

默认不打断作者，除非出现以下情况：

| 必须询问 | 原因 |
|---|---|
| init 最终方案确认 | 会写入新书核心设定 |
| 参考作品拆解质量不足但用户想采用 | 可能污染新书创意 |
| plan 发现总纲 / 设定冲突 | 需要创作裁决 |
| write 发现无法定点修复的 blocking issue | 会影响本章继续提交 |
| data-agent 出现低置信度歧义且会影响事实入库 | 后续状态可能写错 |
| commit rejected 后用户仍想继续 | 需要明确风险接受 |
| 文件写入范围异常 | 可能污染其他章节或项目 |

不应询问：

- 普通非阻断审查问题，系统可在润色中处理。
- RAG 降级但不影响当前写作。
- projection retry 可以自动补跑。
- 备份从 Git 降级到本地备份且成功。
- 单纯耗时偏长但结果正常。

### 8.6 长流程进度节点

每个主 Skill 建议最多展示 3-6 个过程节点，不展示每个内部命令。

`/webnovel-init`：

1. 收集故事核心。
2. 整理创意约束。
3. 等待最终确认。
4. 创建项目文件。
5. 生成写作主链基础资料。
6. 验证项目能否进入规划。

`/webnovel-plan`：

1. 读取总纲和已有剧情状态。
2. 补齐设定基线。
3. 规划卷节奏和时间线。
4. 拆分章纲。
5. 写回新增设定。
6. 刷新写作要求。

`/webnovel-write`：

1. 检查写前条件。
2. 整理写作依据。
3. 起草正文。
4. 写作检查与润色。
5. 保存本章故事事实。
6. 提交、更新资料并备份。

`/webnovel-review`：

1. 确认待审章节。
2. 整理审查依据。
3. 执行写作检查。
4. 生成审查报告并落库。
5. 如有阻断问题，等待用户裁决。

### 8.7 卡住时的过程反馈

流程卡住时不要只报错误，要说明三件事：

1. 卡在哪一步。
2. 已经完成了什么。
3. 下一步怎么恢复。

示例：

```text
卡在“保存本章故事事实”：正文和审查报告已经完成，但本章事实提取结果缺少摘要字段。
我会重跑资料整理助手；如果仍失败，会保留正文和审查报告，不会提交不完整事实。
```

### 8.8 可恢复状态提示

流程中断或失败后，最终报告和过程反馈都应说明恢复点：

| 卡点 | 恢复建议 |
|---|---|
| context-agent 失败 | 补齐章纲 / 合同后重跑写章 |
| 起草后 review 失败 | 保留正文，重跑写作检查 |
| review 有 blocking | 定点修复或用户裁决后继续润色 |
| data-agent artifact 缺失 | 重跑保存本章故事事实 |
| precommit failed | 修复中间结果后重跑提交前检查 |
| commit rejected | 修复 missed_nodes / pending / blocking 后重新提交 |
| projection failed | 补跑 `projections retry` |
| backup failed | 手动或重跑 backup，不影响已提交事实 |

### 8.9 作者可控的详细程度

后续可增加可选参数：

```text
--quiet      只显示关键确认和最终报告
--verbose    显示过程节点、异常原因和关键命令
```

首版不强制实现参数，但 Skill 文档应遵循默认“简洁过程提示 + 详细最终报告”的体验。

---

## 9. 断点续跑设计

### 9.1 目标

让作者遇到偶发失败后，不需要理解内部补跑命令。重复执行同一主命令时，系统应自动识别已完成步骤，从最近可信断点继续。

示例：

```text
检测到上一次第 13 章已完成“起草正文”和“写作检查”，但卡在“保存本章故事事实”。
本次将从“保存本章故事事实”继续，不会重写正文。
```

### 9.2 断点状态来源

优先复用现有产物和 gate：

| 步骤 | 可信完成判据 |
|---|---|
| 写前检查 | `write-gate prewrite ok=true` 或当前重新运行通过 |
| 写作依据 | `context-agent` 返回任务书且未过期 |
| 正文起草 | 目标章节正文文件存在且非空 |
| 写作检查 | `review_results.json` 标记目标章节，且 `review-pipeline` 已生成报告 |
| 润色 | 正文修改时间晚于审查报告，且无 anti-ai 阻断记录 |
| 保存事实 | 三份 data artifacts 存在且 `write-gate precommit` 通过 |
| 提交事实 | commit 文件存在且 status accepted |
| 更新资料 | `write-gate postcommit` 通过，projection 五项 done/skipped |
| 备份 | backup 返回成功或存在本章备份记录 |

### 9.3 Run Ledger

首版可以不新增复杂状态机，但建议新增轻量运行账本：

```text
.webnovel/runs/write_ch0013.json
.webnovel/logs/run_last.log
```

`write_ch0013.json` 保存机器可读进度：

```json
{
  "schema_version": "webnovel-run-ledger/v1",
  "command": "webnovel-write",
  "chapter": 13,
  "started_at": "",
  "updated_at": "",
  "steps": [
    {"id": "draft", "label": "起草正文", "status": "done", "outputs": ["正文/第0013章.md"]},
    {"id": "data", "label": "保存本章故事事实", "status": "failed", "problem": "API timeout"}
  ]
}
```

`run_last.log` 保存工程细节：

- 命令。
- JSON 输出摘要。
- traceback。
- subagent 原始异常。
- 耗时。

作者报告不直接展开 `run_last.log`，只在不可恢复故障时提示路径。

### 9.4 幂等策略

重复执行主命令时：

1. 先解析 `PROJECT_ROOT`、章节号和模式参数。
2. 读取 run ledger 和现有产物。
3. 校验已完成步骤是否仍可信。
4. 从第一个不可信或失败步骤继续。
5. 若用户参数改变、正文被手动修改、章纲更新时间晚于正文，则提示是否重跑前置步骤。

### 9.5 必须询问的续跑分支

| 场景 | 处理 |
|---|---|
| 正文存在但本次用户要求重写 | 询问覆盖 / 另存 / 取消 |
| 章纲更新晚于正文 | 询问沿用旧正文还是重新起草 |
| 审查报告来自旧正文 | 自动重跑审查 |
| commit 已 accepted，但用户再次执行写同章 | 询问是否重写本章或只查看状态 |
| backup 失败但 commit 已完成 | 自动重跑 backup，不重写正文 |

### 9.6 阶段落地

第一阶段只做 `/webnovel-write` 的断点续跑，因为它步骤最长、失败点最多。

后续再扩展：

- `/webnovel-plan`：批次级续跑，失败批次重做，不覆盖整卷。
- `/webnovel-init`：用户确认前问答态不强行续跑；生成阶段可按文件补齐。
- `/webnovel-review`：按章节范围跳过已审且正文未变更的章节。

---

## 10. 交互式裁决设计

### 10.1 目标

遇到必须用户处理的问题时，优先给有限选项，而不是让作者自己理解错误并手改文件。

### 10.2 裁决呈现格式

```text
需要你裁决：本章“沈照”的法宝与大纲冲突。

大纲记录：青锋剑
正文写成：紫金葫芦

请选择处理方式：
1. 坚持大纲：自动把正文相关段落改回“青锋剑”
2. 采用新设定：保留“紫金葫芦”，并把设定变更写入故事资料
3. 我手动处理：暂停流程，修改后继续
```

### 10.3 标准裁决类型

| 类型 | 选项 |
|---|---|
| 设定冲突 | 坚持既有设定 / 采用新设定 / 手动处理 |
| 时间线冲突 | 按时间线修正文 / 调整时间线 / 手动处理 |
| 角色 OOC | 按角色卡修正文 / 更新角色变化理由 / 手动处理 |
| 低置信度消歧 | 采用 A / 采用 B / 暂不入库 |
| commit rejected | 修复后重提 / 接受风险但不提交 / 手动处理 |
| 文件写入范围异常 | 取消写入 / 只保留安全文件 / 查看详情 |

### 10.4 与 AskUserQuestion 的关系

在 Claude Code 环境中，优先使用 `AskUserQuestion` 做关键裁决。

选项必须短，并说明影响：

- 推荐项放第一。
- 每个选项说明会改什么。
- 不出现“其他”作为固定选项；用户可自由补充。

### 10.5 不做自动裁决的红线

以下情况不能由系统擅自决定：

- 改变主角长期能力路线。
- 改变核心反派身份。
- 改变卷末高潮结果。
- 将参考作品内容写入新书 canon。
- 覆盖用户手动编辑的正文。
- 把 rejected commit 当作 accepted 继续推进。

---

## 11. 技术溯源与日志

### 11.1 目标

作者报告保持清爽，工程排查材料保留完整。

### 11.2 日志位置

建议：

```text
.webnovel/logs/run_last.log
.webnovel/logs/runs/YYYYMMDD-HHMMSS-{command}.log
```

### 11.3 日志内容

日志包含：

- 命令与参数。
- 解析后的项目根。
- 每个过程节点开始 / 结束时间。
- subagent run summary。
- runtime JSON 输出摘要。
- 异常 traceback。
- 最终 `user-report --format json`。

日志不应包含：

- API key。
- `.env` 原文。
- 用户未确认写入的新书核心设定草稿，除非它已经作为本次运行输入出现。

### 11.4 最终报告中的呈现

只在以下情况展示日志路径：

- 未完成。
- 需要用户处理但问题不容易描述。
- 用户使用 `--verbose`。

示例：

```text
技术详情已保存：.webnovel/logs/run_last.log。反馈故障时可以附上它。
```

---

## 12. Phase 0：基线审计

### 12.1 目标

先确认现有报告、gate 和 agent 输出边界，避免改造后不知道格式漂移来自哪里。

### 12.2 工作项

- [ ] 记录四个主 Skill 的当前最终输出要求。
- [ ] 记录四个 agent 当前输出格式与写入责任。
- [ ] 记录 `project-status`、`doctor`、`write-gate`、`review-pipeline`、`chapter-commit` 的 JSON 字段。
- [ ] 记录现有错误码、repair 文案、gate failure 特征与 projection 状态，作为 `author_error_catalog.json` 初始素材。
- [ ] 记录 `review-pipeline` 可用于作者视图的字段：总分、blocking 数、维度问题、建议项、报告路径。
- [ ] 记录当前文档和 Skill 中已出现的工程词，和 §5 术语表做一次去重。
- [ ] 确认现有测试中哪些是文案级断言，哪些能改为行为级断言。

### 12.3 验收

- 当前可复用的结构化数据源已列明。
- 明确哪些问题只能由 prompt 记录，哪些可以由 runtime helper 读取。
- `author_glossary.json` 与 `author_error_catalog.json` 的首批条目来源清楚，不靠实现时临场猜。

---

## 13. Phase 1：Skill 最终报告契约

### 13.1 目标

先用最小改动让四个主流程在最终回复中遵守统一格式。

### 13.2 `/webnovel-init`

必须汇报：

- 项目目录。
- `.webnovel/state.json`。
- `设定集/世界观.md`、`设定集/力量体系.md`、`设定集/主角卡.md`、`设定集/反派设计.md`。
- `大纲/总纲.md`。
- `.webnovel/idea_bank.json`。
- `.story-system/MASTER_SETTING.json`。
- 是否使用参考作品拆解。
- 用户确认前未写入 canon 的情况。
- 缺失信息是否会影响后续 plan。

工作项：

- [ ] 在 `webnovel-init/SKILL.md` 增加“最终报告要求”段。
- [ ] 将成功标准映射到“三段式报告”。
- [ ] 明确参考作品拆解失败、输入不足或质量不过线时必须进入“建议确认 / 必须处理”。

### 13.3 `/webnovel-plan`

必须汇报：

- `大纲/第{volume_id}卷-节拍表.md`。
- `大纲/第{volume_id}卷-时间线.md`。
- `大纲/第{volume_id}卷-详细大纲.md`。
- 新增设定写回了哪些设定集文件。
- `大纲/第{volume_id}卷-总纲写回.json`。
- `master-outline-sync` 是否完成。
- `update-state` 是否完成。
- Story System 合同是否刷新。
- 占位符、时间线、节点承接是否通过。

工作项：

- [ ] 在 `webnovel-plan/SKILL.md` 增加“最终报告要求”段。
- [ ] 明确时间线回跳、BLOCKER、占位符残留必须报告。
- [ ] 明确只重做失败批次时要说明自动处理内容。

### 13.4 `/webnovel-write`

必须汇报：

- 正文文件路径。
- 写作检查报告路径。
- `.webnovel/tmp/review_results.json`。
- `.webnovel/tmp/fulfillment_result.json`。
- `.webnovel/tmp/disambiguation_result.json`。
- `.webnovel/tmp/extraction_result.json`。
- `.story-system/commits/chapter_{NNN}.commit.json`。
- state / index / summary / memory / vector 更新状态。
- 备份状态。
- 是否可以继续写下一章。

工作项：

- [ ] 在 `webnovel-write/SKILL.md` 增加“最终报告要求”段。
- [ ] 明确 `--fast` 和 `--minimal` 的跳过项必须说明。
- [ ] 明确 `chapter-commit rejected` 时最终状态不得写“已完成”。
- [ ] 明确 projection retry 发生时要说明已自动处理和结果。

### 13.5 `/webnovel-review`

必须汇报：

- 审查报告文件。
- `review_metrics.json`。
- `review_metrics` 是否落库。
- 阻断问题数量。
- 用户裁决状态。
- 如果无阻断，明确可以继续写作。

工作项：

- [ ] 在 `webnovel-review/SKILL.md` 增加“最终报告要求”段。
- [ ] 明确 blocking 问题必须进入“必须处理”或“建议确认”。
- [ ] 明确只保存报告、稍后处理时最终状态为“需要你处理”或“部分完成”。

---

## 14. Phase 2：Subagent 返回协议

### 14.1 目标

让主流程可以稳定汇总每个 subagent 的完成状态、问题、自动处理内容和耗时。

### 14.2 统一协议

主流程为每次 subagent 调用记录一份 `SubagentRun`：

```json
{
  "name": "data-agent",
  "user_label": "保存本章故事事实",
  "status": "completed | partial | failed | skipped",
  "problems": [],
  "auto_handled": [],
  "needs_user_action": false,
  "duration_ms": 0,
  "outputs": []
}
```

字段说明：

| 字段 | 含义 |
|---|---|
| `name` | agent 名称 |
| `user_label` | 作者友好名称 |
| `status` | 完成状态 |
| `problems` | 遇到的问题 |
| `auto_handled` | 自动处理内容 |
| `needs_user_action` | 是否需要用户处理 |
| `duration_ms` | 耗时 |
| `outputs` | 产生或返回的关键产物 |

### 14.3 工作项

- [ ] `context-agent`：上下文不足、legacy fallback、伏笔数据缺失必须可被主流程记录。
- [ ] `reviewer`：正文为空、读取状态失败、维度跳过必须写入 summary 或问题字段。
- [ ] `data-agent`：三份 artifact 写入状态、长时间无进展、pending 消歧必须可被汇总。
- [ ] `deconstruction-agent`：输入不足、质量不过线、降级 quick mode 必须可被汇总。
- [ ] 主 Skill 调用 agent 后，必须记录 `SubagentRun` 供最终报告使用。

### 14.4 验收

- 写章流程最终报告能列出写前准备、写作检查、保存本章故事事实三个助手的状态。
- 任一 agent 跳过、失败、输出不完整时，最终报告不会写成完全成功。

---

## 15. Phase 3：异常分类与耗时呈现

### 15.1 异常分类

所有问题归为三类：

| 类型 | 定义 | 示例 |
|---|---|---|
| 已自动处理 | 系统已补跑、降级或完成白名单内定点处理，不需要用户处理 | projection retry 成功、RAG 降级但不影响结果 |
| 建议确认 | 结果可用，但建议用户看一眼 | 参考拆解质量略低、某个角色命名有歧义但已采用 |
| 必须处理 | 不处理会影响继续写作、提交或一致性 | blocking issue、正文缺失、commit rejected、projection failed |

### 15.2 Error Catalog

`author_error_catalog.json` 是错误到作者行动的映射表，供 `error_catalog.py` 和 `user_report.py` 共同使用。它不改变错误判定，只负责把已知错误翻译成：

- 人话原因。
- 对当前章节 / 后续写作的影响。
- 下一步动作或可复制命令。
- 严重度与异常分类。
- 是否允许自动处理。

未知错误必须诚实降级：

```text
这里遇到一个系统还没有登记过的问题。当前不会把它当成已完成；请先运行 /webnovel-doctor，或反馈时附上日志。
```

错误目录只做翻译和分类；自动处理白名单必须单独显式登记，且第三期前不扩大现有自动处理范围。

### 15.3 耗时呈现

默认只展示：

- 已耗时。
- 当前步骤是否仍在推进。
- 长时间无进展时的可能原因。
- 是否影响已完成结果。

不设置固定耗时阈值。不同 API、模型、网络、章节长度和审查复杂度差异过大，固定阈值会误导作者。

过程提示可以使用相对表达：

```text
“保存本章故事事实”已经运行了一段时间，可能是接口响应较慢或本章新增事实较多；当前不会影响已生成正文。
```

### 15.4 工作项

- [ ] 在 Skill 最终报告要求中加入“异常分类”。
- [ ] 新增 `author_error_catalog.json` 与 `error_catalog.py`。
- [ ] 给 `mainline_ready=false`、`write-gate failed`、`chapter-commit rejected`、projection failed / pending、RAG 降级、artifact schema 不完整等场景建立首批条目。
- [ ] 未命中错误码时降级到“诚实报错 + `/webnovel-doctor` + 日志路径”，不得崩溃或乱翻译。
- [ ] 在 `data-agent.md` 中保留并规范“长时间无进展需说明原因和影响”。
- [ ] 在 runtime helper 中实现耗时格式化。
- [ ] 不做 token 统计，不在最终报告展示 token。

### 15.5 验收

- 最终报告不会把 warning、blocking、auto-handled 混在一起。
- 已知错误能映射为作者可执行下一步，未知错误能诚实降级。
- 长时间无进展的步骤必须有原因推测和影响判断。
- token 不作为用户可见报告项。

---

## 16. Phase 4：Runtime 报告 Helper

### 16.1 目标

新增统一 helper，把结构化运行结果渲染成作者友好报告。

本阶段同时落地 spec 的 Review Author View：在现有审查报告顶部增加作者视图，不改变 reviewer schema、不改变评分和 blocking 判定。

作者视图格式：

```text
本章结论：✅可以继续 / ⚠️建议改 / ⛔必须先改

最值得处理的 1-3 件事：
- ...
```

生成规则：

- `blocking_count > 0`：结论为“必须先改”，最多列 3 条 blocking 或高风险问题。
- 无 blocking 但存在明显建议：结论为“建议改”，最多列 3 条对剧情、人物、节奏最有收益的建议。
- 无 blocking 且建议较轻：结论为“可以继续”，只保留一句说明。
- 技术指标、schema、原始 reviewer 维度放在下方报告细节，不放进顶部结论。

### 16.2 CLI 形态

新增：

```bash
python -X utf8 "${SCRIPTS_DIR}/webnovel.py" --project-root "${PROJECT_ROOT}" user-report \
  --stage write \
  --chapter {chapter_num} \
  --format text
```

支持：

```bash
--stage init|plan|write|review
--chapter N
--volume N
--format text|json
```

### 16.3 数据模型

`user_report.py` 内部使用：

```json
{
  "schema_version": "webnovel-user-report/v1",
  "stage": "write",
  "overall_status": "completed | partial | needs_user | failed",
  "project_root": "",
  "chapter": 0,
  "volume": 0,
  "files": [],
  "issues": {
    "auto_handled": [],
    "needs_confirmation": [],
    "must_handle": []
  },
  "timing": {
    "total_ms": 0,
    "steps": []
  },
  "next_actions": []
}
```

### 16.4 数据来源

| 阶段 | 数据来源 |
|---|---|
| init | 文件存在性、`project-status`、`.story-system/MASTER_SETTING.json` |
| plan | 规划产物文件、`placeholder-scan`、`master-outline-sync` 输出、Story System 合同文件 |
| write | `write-gate` 三阶段、review artifacts、commit payload、projection log、backup 输出、subagent runs |
| review | `review_results.json`、`review_metrics.json`、报告文件、`review_metrics` 表 |

### 16.5 工作项

- [ ] 新增 `review_author_view.py`，从现有 review payload 渲染一句结论 + 最多 3 条可执行建议。
- [ ] 在 `review_pipeline.py` 的报告渲染环节插入作者视图段，不改 reviewer schema。
- [ ] 新增 `user_report.py`。
- [ ] 新增 `webnovel.py user-report` 子命令。
- [ ] 先实现 `write` 阶段报告，因为它最复杂、收益最大。
- [ ] 同步实现 `review` 阶段报告，复用审查作者视图。
- [ ] 最后实现 `init` 和 `plan`。
- [ ] 给 helper 加单元测试，不依赖真实 LLM。

### 16.6 验收

- 审查报告顶部有一句作者可判读结论，且最多 3 条可执行建议。
- 作者视图保留 blocking 数等关键事实，不把必须处理的问题写成“可以继续”。
- `user-report --stage write --format json` 输出稳定 schema。
- `user-report --stage write --format text` 输出三段式中文报告。
- projection failed、commit rejected、missing artifact 等场景能被正确归类。
- helper 输出不包含 token 统计。

---

## 17. Phase 5：断点续跑与交互验证

### 17.1 Prompt integrity

新增或调整断言：

- [ ] 四个主 Skill 都包含过程提示要求。
- [ ] 四个主 Skill 都包含“少打扰确认策略”。
- [ ] `/webnovel-write` 的过程节点不超过 6 个作者可理解阶段。
- [ ] 过程提示使用作者友好阶段名，不直接暴露工程命令作为主提示。
- [ ] 卡住时必须说明卡点、已完成内容和恢复建议。
- [ ] `/webnovel-write` 必须说明重复执行同一命令时可从可信断点继续。
- [ ] 必须用户裁决的问题应优先给有限选项。
- [ ] 技术详情默认写入 `.webnovel/logs/run_last.log`，不直接污染作者报告。

### 17.2 Runtime tests

新增：

- [ ] `test_run_ledger_records_write_step_status`
- [ ] `test_write_resume_skips_completed_draft_and_review`
- [ ] `test_write_resume_rechecks_review_when_chapter_file_changed`
- [ ] `test_write_resume_retries_backup_after_commit_done`
- [ ] `test_run_log_redacts_env_values`
- [ ] `test_user_report_includes_log_path_only_on_failure`

首版如果暂不实现 run ledger，则这些测试先作为 Phase 5 待实现契约，不并入默认必过集合。

### 17.3 Behavior eval

新增：

- [ ] `/webnovel-write` 执行过程中能说明当前处于写前检查、起草、审查、保存事实、提交备份中的哪一段。
- [ ] RAG 降级不打断用户，但最终报告说明。
- [ ] projection retry 自动补跑不询问用户，但过程提示说明正在补跑。
- [ ] blocking issue 无法定点处理时才询问用户。
- [ ] data-agent 输出不完整时说明已保留正文和审查报告，不提交不完整事实。
- [ ] 同章重复运行 `/webnovel-write` 时，不重写已可信正文，自动从失败步骤继续。
- [ ] 设定冲突类 blocking issue 使用有限选项裁决。
- [ ] 不可恢复故障报告中给出 `.webnovel/logs/run_last.log`。

### 17.4 验收

- 作者在长流程中能判断“现在在做什么”。
- 非关键问题不会频繁打断作者。
- 关键创作裁决不会被系统擅自跳过。
- 失败后能看到明确恢复点。
- 偶发失败后，重复执行同一主命令可以从最近可信步骤继续。
- 工程日志可用于排查，但默认不打扰作者。

---

## 18. Phase 6：测试与行为验证

### 18.1 Prompt integrity

新增或调整断言：

- [ ] 四个主 Skill 都包含最终报告要求。
- [ ] 四个主 Skill 都要求总状态 + 三段式报告。
- [ ] `webnovel-write` 必须汇报正文、审查、data artifacts、commit、projection、backup。
- [ ] `webnovel-review` 必须汇报审查报告、metrics 和 blocking 裁决。
- [ ] Agent 协议中必须可汇总 status / problems / auto_handled / needs_user_action / duration。
- [ ] 不要求具体措辞，只检查契约是否存在。

### 18.2 Runtime tests

新增：

- [ ] `test_user_report.py::test_render_write_report_success`
- [ ] `test_user_report.py::test_render_write_report_commit_rejected`
- [ ] `test_user_report.py::test_render_write_report_projection_failed`
- [ ] `test_user_report.py::test_render_review_report_blocking`
- [ ] `test_webnovel_unified_cli.py` 覆盖 `user-report` 注册。

### 18.3 Behavior eval

在 fast eval 中补：

- [ ] `/webnovel-write --minimal` 最终报告必须说明跳过写作检查。
- [ ] data-agent 输出缺失时最终报告不能写“已完成”。
- [ ] projection retry 成功时最终报告归入“已自动处理”。
- [ ] reviewer 有 blocking 时最终报告归入“必须处理”。

### 18.4 验证命令

```bash
python -m pytest webnovel-writer/scripts/data_modules/tests/test_prompt_integrity.py -q --no-cov
python -m pytest webnovel-writer/scripts/data_modules/tests/test_user_report.py -q --no-cov
python -m pytest webnovel-writer/scripts/data_modules/tests/test_webnovel_unified_cli.py -q --no-cov
python -X utf8 webnovel-writer/scripts/run_behavior_evals.py --format json
```

---

## 19. Phase 7：文档与 README

### 19.1 目标

让用户知道每次命令结束后应该如何理解最终报告。

### 19.2 修改范围

- `README.md`
- `docs/guides/commands.md`
- `docs/operations/operations.md`

### 19.3 工作项

- [ ] 在 README 的写章工作流中补“最终报告怎么看”。
- [ ] 在 README 或 commands 文档中补“执行过程中会看到哪些提示”。
- [ ] 在 commands 文档中说明重复执行主命令会优先尝试断点续跑。
- [ ] 在 commands 文档中说明四种总状态。
- [ ] 在 operations 文档中说明哪些情况会询问用户，哪些会自动处理。
- [ ] 在 operations 文档中说明 `.webnovel/logs/run_last.log` 的用途和敏感信息规则。
- [ ] 在 operations 文档中说明异常分类和常见处理。
- [ ] 不写 token 统计说明。

### 19.4 验收

- 用户能从文档理解“已完成 / 部分完成 / 需要你处理 / 未完成”的区别。
- 用户能知道哪些问题可以忽略，哪些必须处理。
- 用户知道遇到偶发失败后可以重新执行原命令。
- 用户知道反馈故障时可以附日志，但平时不需要看日志。

---

## 20. 推荐施工顺序

1. Phase 0：基线审计。
2. Phase 1A：建立 `author_glossary.json`，四个主 Skill 引用同一术语口径。
3. Phase 1B：先改四个主 Skill 的最终报告要求，并补“下一步建议”的任务化尾巴。
4. Phase 3A：建立 `author_error_catalog.json` / `error_catalog.py`，固定异常分类与未知错误降级。
5. Phase 4A：实现 `review_author_view.py`，在审查报告顶部给一句结论 + 最多 3 条建议。
6. Phase 2：补 subagent 返回协议，保证主流程有素材可汇总。
7. Phase 4B：实现 `user_report.py`，先接 `/webnovel-write` 和 `/webnovel-review`。
8. Phase 5A：补过程提示、开始前预期、确认策略和恢复点。
9. Phase 5B：实现 `/webnovel-write` 的 run ledger、日志和断点续跑。
10. Phase 5C：把 blocking 类问题收敛为交互式裁决。
11. Phase 6：补 prompt integrity、unit tests、behavior eval。
12. Phase 7：更新 README / docs。

原因：

- 术语表和错误目录是 Author Layer 的单一事实源，先做能避免后续文案和 helper 各翻各的。
- Skill 契约和下一步尾巴能立刻改善用户可见输出，且风险最低。
- 审查作者视图是最短路径高收益改造，独立于写章主链，适合早交付。
- runtime helper 解决长期一致性，但首版保持只读渲染，不改变写作链路。
- run ledger、自动处理白名单和断点续跑风险更高，放到后面，并优先只覆盖 `/webnovel-write`。

---

## 21. 风险与控制

| 风险 | 影响 | 控制 |
|---|---|---|
| 只改提示词导致格式漂移 | 不同 Skill 最终报告仍不一致 | Phase 4 增加 runtime helper |
| 报告太长 | 作者不想看 | 默认只给三段式，技术细节只在必须处理时展开 |
| 报告太短 | 问题被隐藏 | 明确不可静默场景 |
| 工程词太多 | 作者读不懂 | 使用术语翻译表 |
| helper 过早侵入主流程 | 引入新故障点 | 先做只读渲染，不改变写作链路 |
| 耗时记录不准 | 误导用户 | 先记录步骤级粗粒度耗时，不做精确性能诊断 |
| subagent 无法直接返回协议字段 | 主流程难汇总 | 主流程包一层 `SubagentRun`，不强迫 agent 改原始产物格式 |
| token 统计取消后缺少成本感知 | 少一项工程指标 | token 只留内部观察，不做作者最终报告项 |
| 过程提示太频繁 | 打断作者沉浸感 | 每个主流程最多展示 3-6 个过程节点 |
| 该问不问 | 创作方向或事实状态被系统擅自决定 | 少打扰策略中列明必须询问场景 |
| 不该问却问 | 作者被细碎技术问题打断 | 自动处理类问题默认不询问，只在最终报告说明 |
| 卡住时只报错误 | 作者不知道成果是否丢失 | 卡住反馈必须包含已完成内容和恢复点 |
| 断点续跑误判产物可信 | 用旧正文或旧审查继续提交 | 断点恢复必须检查文件更新时间、章节号、模式参数和 gate 状态 |
| 自动续跑覆盖用户手改 | 用户创作被覆盖 | 检测到正文或章纲有新修改时必须询问 |
| 交互式裁决选项过多 | 用户仍然困惑 | 每次只给 2-3 个明确选择 |
| 日志泄露敏感信息 | API key 或私密配置外泄 | 日志写入前过滤 `.env`、API key、secret 类字段 |

---

## 22. Out of Scope

本计划不包含：

- 自动修复 / 自动重审所有 review blocking issue。
- 新增多轮 reviewer 重审循环。
- 改写 chapter commit 或 projection 主链。
- Dashboard 前端大改版。
- token 成本统计。
- 自动生成 PR / git commit。
- 重构所有 Skill 文案瘦身。
- 实时进度条 UI。
- Dashboard 流程进度可视化。
- 完整事务型工作流引擎。
- 跨所有 Skill 的全量断点续跑；首版优先 `/webnovel-write`。

这些应单独规划。

---

## 23. 最小可落地版本

如果要快速得到收益，建议先做最小版本：

1. 建立 `author_glossary.json`，把术语翻译收成单一事实源。
2. 建立 `author_error_catalog.json`，至少覆盖 `mainline_ready=false`、`write-gate failed`、`chapter-commit rejected`、projection failed / pending、RAG 降级、artifact schema 不完整；未知错误诚实降级到 `/webnovel-doctor`。
3. 给四个主 Skill 增加最终报告要求：总状态 + 三段式报告 + 下一步建议。
4. 给四个 agent 增加可汇总的状态 / 问题 / 自动处理 / 耗时协议。
5. 在 `review_pipeline.py` 顶部增加审查作者视图：一句结论 + 最多 3 条可执行建议。
6. 在 `webnovel-write` 的最终报告中强制汇报：
   - 正文
   - 审查报告
   - data artifacts
   - commit 状态
   - projection 状态
   - 备份状态
   - 下一章是否可继续
7. 暂不实现完整 `user_report.py`，但把 helper 作为下一阶段明确目标。
8. 给 `/webnovel-write` 增加 6 个作者友好过程节点和卡住恢复说明。
9. 在 `/webnovel-write` 中说明重复执行同一命令会尽量从失败步骤继续；实际 run ledger 作为下一阶段。
10. 最终报告的下一步建议包含任务化说明和可复制命令。

最小版本完成后，作者至少能稳定知道：

- 文件有没有生成。
- 本章能不能继续往下写。
- 哪些问题系统已经处理。
- 哪些问题必须自己确认。
- 流程中当前走到哪一步。
- 失败后从哪里恢复。
- 下一步可以直接执行什么命令。

---

## 24. 最终效果

完成后，作者看到的不是一串命令和 JSON，而是一份稳定交付单：

```text
总状态：已完成，可以继续写第 13 章。

一、产生的文件与完成情况
- 正文/第0012章-风雪夜归人.md：已生成并通过写作检查。
- 审查报告/第12章审查报告.md：已生成，无阻断问题。
- 本章故事事实：已保存，状态、摘要、长期记忆和检索库已更新。
- 备份：已完成。

二、过程中遇到的问题与异常耗时
- 已自动处理：检索库更新较慢，系统已等待完成，不影响结果。
- 建议确认：本章新增角色“沈照”已写入故事资料，建议你看一眼名字是否满意。
- 必须处理：无。

三、下一步建议
- 可以继续执行：
  /webnovel-write 13
```

这份报告的价值不是“更好看”，而是让作者每次都能安心判断：这一轮到底靠不靠谱，下一步能不能继续。
