# Spec：v7 写前链路补全（v8-gap-review 阶段一 P1-1 / P1-2）

> 档位：Architectural（改变 `/webnovel:write` 与 `v7_write` 的组件关系；新增 settle 门禁接口）
> 状态：**待 Human 批准**（brainstorming 第 6 步落盘；方案分叉已裁决：C + 显式 bypass）
> 上游：`docs/zcode/v8-gap-review-3rounds/README.md` 阶段一表格；`docs/cursor/项目复审/2026-09-04-项目复审报告.md` P1-6 / 步骤 6
> 下游：批准后 → writing-plans 出 `…-plan.md`（同目录）→ TDD 实现 → code-review → finishing

## 1. 背景与目标

**现状（均有证据）**：
- `v7_write.build_context_pack` 仅输出 7 section（`v7_write.py:141-190`）；v8 在 M3/M5/M6 建成的 stale_notes / author_model / style_anchor / reader_signal / pending_promises 等构建器只接进了 v6 `context_manager`，v7 书仓写章时看不到（gap-review C 类）。
- `v7_write.settle`（`:368-480`）只跑 `run_checks`，不读 `.webnovel/tmp/review_results.json`、不跑 prose_check、不校验素材引用（D1-D3 / N10）；reviewer 的 blocking 语义在 v7 路径形同虚设。
- **`v7_write.py` 没有任何 skill / command / agent 调用**（全仓 `*.md` grep 仅命中 `migrate_v6_to_v7.py` 与自身）；`/webnovel:write` SKILL 全程 v6 链；`settle` 只有 Python API；`pack` 子命令构造的 decision `entities=[]`，实体 section 经 CLI 永远为空（`v7_write.py:503-510`）。

**目标**：在 v7 书仓上，`/webnovel:write` 能走到 v7 链，写前上下文包含 v8 已建成的治理信号，settle 前有审查 / 文笔 / 素材引用三道门禁，且门禁只能被显式、留痕地绕过。

**成功标准（抄 v8-gap-review 阶段一原文）**：
- P1-1：「fantasy01 ch42 上下文包含 stale_notes、账本应推进项、author_model 三段；饱和测试三段保全」
- P1-2：「构造 blocking 审查 → settle 拒绝；引用不存在 ID → 报错」

## 2. 非目标

- 不重写 `v7_write` 为 v6 合同链；不做 write-gate 全量移植（gap-review「明确不做」）。
- 不动 v6 路径任何行为（v6 = 回归基线；`context_manager` 只被调用，不被修改）。
- 不在本阶段实现 P2-x / P3-x / P4-x（章纲闸、后置钩子、doctor 治理组）；settle 后置钩子（P3-1）留接口不实现。
- 不引入 v6-only 概念到 v7 包：`memory_pack` / `story_contracts` / `runtime_status` / `prewrite_validation` / `active_rules` / `genre_profile` 依赖 `.webnovel/state.json` 与 `.story-system/`，v7 书仓无对应事实源——gap-review C 类清单是用 v6 section 名做差集得来，不是 v7 的需求清单。**本 spec 只补 v7 有事实源的 section**（§4.2 列表），其余六项记为「不适用 v7」，若 Human 认为其中某项必须有，在批准时点名。

## 3. 方案与裁决

| 方案 | 内容 | 否决/采纳理由 |
|---|---|---|
| A | 按 gap-review 原文只扩 `v7_write.py` 独立链，14 section 各自重新读文件；skill 接线另立项 | ❌ 重复实现 M3/M5/M6 已有构建器；且做完 skill 仍调不到，投入不可达 |
| B | 让 v6 写链 / `context_manager` 兼容 v7 书仓布局，`v7_write` 退为迁移与 settle 工具 | ❌ `context_manager` 949 行、139 字段 config 深绑 `.webnovel/state.json`；改它违反「不动 v6」 |
| **C（采纳，Human 2026-09-04）** | `/webnovel:write` 按 `book.yaml` 分流到 v7 链；`v7_write` 补 settle CLI；`build_context_pack` 直接调用 v8 各域模块的读函数（它们本就是对 v7 书仓写的） | ✅ 零重复实现、可达、v6 不动 |

settle 审查门禁绕过语义（Human 裁决）：**显式 `--force-review-bypass "<理由>"` 才可跳过，理由写进正文 front matter（`审查绕过:`）与 journal**。

## 4. 设计

### 4.1 组件关系（改动面）

```
/webnovel:write SKILL ──Step 0 检测 book.yaml──┬─ 无 → v6 链（不变）
                                              └─ 有 → v7 链：
   webnovel.py v7-write decision → pack → (草稿, drafts 择优) → check
   → reviewer 直写 .webnovel/tmp/review_results.json（沿用 v6 约定）
   → webnovel.py prose-check → webnovel.py v7-write settle [--force-review-bypass 理由]
```

- 新增 `webnovel.py v7-write` 转发子命令（薄壳 → `v7_write.main`），与其余转发一致；MCP 不新增工具（写路径不暴露）。
- `v7_write.main` 新增 `settle` 子命令；`pack` 子命令改为可选 `--json` 读决策 JSON（无则回退读决策卡文本解析 `关键实体:` 行），修掉 entities 恒空。

### 4.2 `build_context_pack` 新增 section（P1-1）

| section | 事实源（已存在的读函数） | 默认配额 | 缺失行为 |
|---|---|---|---|
| `stale_notes` | `author_journal.unconsumed_stale(repo)` | 800 | 空列表 → 省略 |
| `pending_promises` | `promise_ledger.pending_for_chapter(repo, chapter=N)` | 1000 | 无账本目录 → 省略 |
| `author_model` | `author_model.load_author_model_section(repo)` | 800 | 无 `作者/author_model.md` → 省略 |
| `style_anchor` | `style_domain.build_style_anchor_section(repo)` | 500 | 无高分样本 → 省略 |
| `style_contract` | `style_domain.constitution_path(repo)` 原文前 N 字 | 600 | 无宪法 → 省略 |
| `reader_signal` | `reader_signal_builder.build_reader_signal(repo)` | 500 | 无追读力数据 → 省略 |
| `materials` | `material_store.assemble_materials(repo, top_k=book.yaml/userConfig materialTopK)` | 1500 | 无素材域 → 省略 |
| `outline_excerpt` | 当卷详细大纲 `## 第N章` 小节：先找 `大纲/卷纲/第NN卷-详细大纲.md`，回退 `第NN卷.md`（P2-1 统一路径前的兼容读） | 800 | 无 → 省略 |
| `protagonist` | `v7_cache.find_entity(book.yaml 主角名)` + 名册卡正文 | 600 | 无 → 省略 |
| `pov_discipline` | 决策卡 `pov` ≠ 主角 → 注入 `references/pov-management.md` 的非主角视角段（N11） | 400 | pov 为主角或缺 → 省略 |

- 配额进 `V7_SECTION_QUOTAS`，可被 `book.yaml context_budget.sections` 覆盖（既有机制）。
- **保护与丢弃顺序**（对齐 v6 PROTECTED/DROP 语义）：`decision_card` / `prev_chapter_tail` / `stale_notes` / `pending_promises` 为 PROTECTED（只截不丢）；总预算超限时按 `materials → reader_signal → style_contract → outline_excerpt → protagonist → pov_discipline → style_anchor → author_model → roster → recent_summaries → entities` 顺序整段丢弃，`stats` 新增 `dropped_sections`。
- `_render_pack_markdown` 改为按 section 声明表渲染（标题 + 类型），不再硬编码六个名字。
- 每个读函数调用包 `try/except` → 失败记 `stats["section_errors"][name]`，不阻断打包。

### 4.3 `settle` 三门禁（P1-2）

前置于 `run_checks` 之后、唯一写入路径检查之前，任一不过 → `RuntimeError`，不落盘、不 commit：

| 门 | 判定 | 绕过 |
|---|---|---|
| ① 审查 | 读 `<repo>/.webnovel/tmp/review_results.json`；**文件不存在 → 拒绝**（「未审查」与「审查有阻断」同级）；`review_result.blocking_count > 0` → 拒绝 | `--force-review-bypass "<理由>"`：放行，front matter 加 `审查绕过: <理由>`，journal 追加 `settle_review_bypass` 事件（含 blocking_count 与理由） |
| ② 文笔 | 对净稿跑 `prose_check.check_prose`；`flagged` 非空 → 拒绝，报告列出 flagged 项 | 同一个 bypass 开关覆盖（理由同样留痕）；不单设开关，避免开关蔓延 |
| ③ 素材引用 | 决策卡 / decision JSON 的 `材料引用` 列表逐条 `material_usage.resolve_ref(repo, ref)`；任一解析失败 → 拒绝并列出未解析 ID | **不可绕过**（引用不存在是数据错误，不是判断题） |

- 门①② 结果写入 `result["gates"]`（供 skill 最终报告）。
- **待 Human 确认的默认值**：门② 是否对 `paragraph_variance` / `long_sentences` 这类风格性项降为 warning（不阻断）？本 spec 默认**全部阻断**，理由：bypass 已存在，宁严勿松；若实写中误报率高再在 P3 调。

### 4.4 CLI 接口

```
v7_write.py settle --repo R --chapter N --draft 工作区/草稿-NNNN.md --json 决策.json
                   [--summary-file F | --summary "…"] [--no-commit]
                   [--force-review-bypass "理由"]
退出码：0 成功 / 2 门禁拒绝（stderr 一行 + JSON 明细）/ 1 其他错误
v7_write.py pack   --repo R --chapter N [--json 决策.json]
webnovel.py v7-write <上述任一>   （转发）
```

### 4.5 SKILL 接线（`skills/webnovel-write/SKILL.md`）

- Step 0 增「书仓形态判定」：`PROJECT_ROOT/book.yaml` 存在 → 进「v7 分支」小节，否则原流程不变。
- 「v7 分支」小节按 §4.1 顺序列命令，reviewer / data-agent 调用方式不变（reviewer 仍直写 `review_results.json`），settle 命令后附「门禁被拒时：改稿重审，或作者明确要求时 `--force-review-bypass`，理由必须来自作者原话」。
- 行为评测 `run_behavior_evals.py` 增一条：SKILL 文本含 v7 分支且含 `--force-review-bypass` 留痕说明。

## 5. 数据与兼容

- 不改任何既有文件格式；新增 front matter 键 `审查绕过`（可选）；journal 新事件类型 `settle_review_bypass`（`author_journal.append_events` 既有 API，`validate_journal` 需接受新类型——查其白名单，若有则加入）。
- `book.yaml context_budget.sections` 新键名与 §4.2 一致；旧书无键 → 默认配额，零行为变化。

## 6. 验收清单（W1：引用方案原文）

| # | 方案原文 | 验证 |
|---|---|---|
| 1 | 「fantasy01 ch42 上下文包含 stale_notes、账本应推进项、author_model 三段」 | 在 fantasy01 副本构造：改一份卷纲不消费 → stale；账本一条 10 章内到期；`作者/author_model.md` 存在 → `pack --chapter 42` 输出含三节标题；测试 `test_v7_write_pack_sections.py` 用 tmp 书仓断言三节 |
| 2 | 「饱和测试三段保全」 | 总预算压到 4000，其他 section 塞满 → `dropped_sections` 非空但 `stale_notes` / `pending_promises` / `decision_card` 仍在 |
| 3 | 「构造 blocking 审查 → settle 拒绝」 | tmp 书仓写 `review_results.json` blocking_count=1 → `settle` 退出 2，定稿目录无新文件，git 无新 commit；加 `--force-review-bypass "作者要求"` → 成功且 front matter 含 `审查绕过`、journal 含事件 |
| 4 | 「引用不存在 ID → 报错」 | decision `材料引用: ["X-999"]` → 退出 2，消息含 `X-999`；`--force-review-bypass` 不放行 |
| 5 | 无审查文件 → 拒绝 | 不写 `review_results.json` → 退出 2 |
| 6 | prose 门 | 构造 said tag 超阈值净稿 → 拒绝；bypass 放行 |
| 7 | pack entities 修复 | `pack --json` 后 `entities` 非空 |
| 8 | 回归 | 全量 pytest ≥ 1455 passed，覆盖率 ≥ 80；`validate_reference_wiring` drift=0；行为评测全 PASS；v6 既有 `test_context_manager*` 不改一行 |

## 7. 约束

- 每个任务先写失败测试（TDD）；测试用 tmp 书仓（`book.yaml` + `定稿/` 骨架），不依赖 fantasy01；fantasy01 只做最终冒烟。
- 不修改 `context_manager.py`、`write_gates/*`、任何 v6 测试。
- 所有新增读取 `try/except` 降级，打包永不因单个域缺失失败。
- 中文路径 / `-X utf8` / 长路径原语（`long_paths`）沿用既有约定。
- 提交粒度：P1-1（pack）与 P1-2（settle）至少两个 commit；SKILL 接线单独 commit。

## 8. 风险

- fantasy01 `.webnovel/tmp/review_results.json` 由 reviewer 直写的 schema 若与 `review_pipeline.build_review_artifacts` 产出不同（顶层 `review_result` 有无），门① 需兼容两种（顶层或嵌套 `blocking_count`）——实现时先读真仓样本确认。
- `assemble_materials` top-K 默认值与 userConfig `materialTopK` 的传递路径（env `WEBNOVEL_MATERIAL_TOPK`？）需在 plan 阶段核实。
- 阶段一完成后 P3-1（settle 后置钩子）会再改 `settle`；本次把门禁与后置分别收敛为 `_run_gates()` / `_run_post_hooks()`（后者本次为空壳）以降低下次改动面。
