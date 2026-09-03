# 命令详解

> 口径：v8.0.0（ZCode 插件）。三层命令面：① 8 个 skill（`/webnovel-<name>`）；② 13 条 `/webnovel:<name>` 短名命令（薄壳，前 8 条转发同名 skill，后 5 条转发 CLI 治理子命令）；③ 统一 CLI `webnovel.py` 子命令；另有会话自动挂载的 `webnovel` MCP 服务（14 只读工具）。

## Skill 命令（在 ZCode 中使用；`/webnovel:<name>` 短名等价）

### `/webnovel-init`

初始化小说项目，生成目录结构、设定模板和状态文件。

产出：

- `.webnovel/state.json`（运行时状态）
- `设定集/`（世界观、力量体系、主角卡、金手指设计、反派设计等）
- `大纲/总纲.md`、`大纲/爽点规划.md`
- `.env.example`（RAG 配置模板）

### `/webnovel-plan [卷号]`

生成卷级规划与章节大纲。

```bash
/webnovel-plan 1
/webnovel-plan 2-3
```

### `/webnovel-write [章号]`

执行完整章节创作流程（`context-agent` 先 research 并生成写作任务书 → 按任务书起草正文 → 审查 → 润色 → 数据落盘）。

```bash
/webnovel-write 1
/webnovel-write 45
```

### `/webnovel-review [范围]`

对已有章节做多维质量审查。

```bash
/webnovel-review 1-5
/webnovel-review 45
```

### `/webnovel-query [关键词]`

查询角色、伏笔、节奏、状态等运行时信息。

```bash
/webnovel-query 萧炎
/webnovel-query 伏笔
```

### `/webnovel-learn [内容]`

从当前会话或用户输入中提取可复用写作模式，写入项目记忆。

```bash
/webnovel-learn "本章的危机钩设计很有效，悬念拉满"
```

产出：`.webnovel/project_memory.json`

### `/webnovel-dashboard`

启动只读可视化面板，查看项目状态、实体关系、章节与大纲内容。

```bash
/webnovel-dashboard
```

说明：

- 默认只读，不会修改项目文件
- 前端构建产物已随插件发布，无需本地 `npm build`

### `/webnovel-doctor [--chapter N] [--deep]`

只读体检当前网文项目，检查阶段应有文件、JSON、SQLite、RAG 配置、Python 依赖与 Dashboard 产物，并给出影响和修复建议。

```bash
/webnovel-doctor
/webnovel-doctor --chapter 12
/webnovel-doctor --deep
```

说明：

- 不写入项目，不安装依赖，不启动服务
- 会先判断当前项目阶段，init 刚结束时不会按终态项目误报

## 仅命令形式的 5 条 `/webnovel:*`（v8 新增，无同名 skill）

| 命令 | 转发到 | 用途 |
|---|---|---|
| `/webnovel:status` | `webnovel.py project-status` | 阶段、断点、计量一行短状态 |
| `/webnovel:materials` | `webnovel.py materials …` | 素材工作台会话：十表状态 / 装配预览 / 入库三通道（AI 归纳 / 拆书 / 工坊采纳）/ 卷审裁决 |
| `/webnovel:forge` | `webnovel.py forge …` | 设定工坊：境界 / 功法 / 法宝 / 命名四生成器；提案模式——AI 只提议、作者只确认、确认后才落设定域 |
| `/webnovel:power` | `webnovel.py power check` | 战力校验：跨阶依据完备性 / 境界链矛盾（high，阻断）/ 通胀偏差（medium） |
| `/webnovel:style` | `webnovel.py style-domain …` | 文风域：风格契约迁移为文风宪法 / 指纹计算 / 金句库喂入 |

## MCP 服务 `webnovel`（会话自动挂载，只读）

14 个工具全部是 CLI 子命令的薄壳转发，不暴露写路径：`webnovel_where` / `webnovel_project_status` / `webnovel_doctor` / `webnovel_setting_read` / `webnovel_timeline_check` / `webnovel_meter` / `webnovel_rag_search` / `webnovel_knowledge` / `webnovel_context` / `webnovel_materials_status` / `webnovel_materials_assemble` / `webnovel_power_check` / `webnovel_foreshadow_scan`（强制 `--no-apply`）/ `webnovel_reader_signals`。书项目根来自 userConfig `bookProjectRoot`（注入 `WEBNOVEL_BOOK_ROOT`），留空走探测链。

## 统一 CLI（命令行使用）

所有 CLI 命令的入口都是 `webnovel.py`，格式：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" <子命令> [参数]
```

### v8 治理子命令（书仓六域，v7 书仓可用）

| 子命令 | 动作 | 说明 |
|---|---|---|
| `domains` | `init` / `check` | 六域目录契约：一键补骨架（作者手改永不覆盖）/ 体检 |
| `author-sync` | — | 作者手改留账：git diff → 六域分类 → journal + stale 提醒（0 token；SessionStart hook 自动跑） |
| `materials` | `list` / `validate` / `assemble` / `seed` / `log` / `trajectory` / `propose` / `candidates` / `adopt` / `discard` / `review` / `apply-ruling` | 素材十表：状态 / 校验 / 装配预览（定版 + 活层 top-K）/ 题材播种 / 章后使用轨迹 / 入库画廊三通道（propose → candidates → adopt 或 discard）/ 卷审统计 / 裁决落盘 |
| `regen` | `save` / `list` / `diff` / `adopt` / `discard` | 总纲 regen 画廊（只增不改，采纳才入正典） |
| `style-domain` | `migrate` / `fingerprint` / `golden-add` / `golden-list` / `golden-feed` | 文风宪法迁移 / 指纹 / 金句库 |
| `learn` | `learn --from-journal` / `apply` / `show` | 学习闭环：卷级归纳 → 作者确认 → author_model 回写（注意 `learn learn --from-journal` 的子动作位置参数，见缺口 N9） |
| `power` | `extract` / `validate` / `battle` / `inflate` / `check` | 战力锚点提取与校验、战例 / 通胀账本、硬 ① ② 阻断校验 |
| `forge` | `prepare` / `save` / `adopt` / `confirm` / `list` | 设定工坊提案流；`confirm` 才写设定域并留 `power_anchor_sync` / `contract_rebuild` 标记 |
| `prose-check` | — | 程序化文笔六项：高频词 / 长句比例 / said tag / 连续同主语 / 纯解释段 / 段落方差 |
| `drafts` | `record` / `choose` / `link` / `report` | 多稿择优：rubric 六维评分 → 取均分最高稿 → 回填审查分 |
| `promise-ledger` | `create` / `list` / `update` | 承诺账本（伏笔 F- / 悬念 S- / 感情线 R-）状态机 |
| `foreshadow-scan` | `scan` / `pending` | 逾期扫描（存在逾期非零退出 = 门禁）/ 本章应推进项 |
| `name-check` | — | 新名 vs 名册正名 / 别名：编辑距离 + 相似度 + 包含三重检查 |
| `volume-reconcile` | — | 卷纲-实际三方对账（节点覆盖率 / 伏笔兑现 / 战力里程碑）→ `大纲/卷纲/第NN卷-对账报告.md` |
| `freeze` | — | 卷收尾冻结 + retcon 三选项裁决 |
| `timeline` | `build` / `sync` | 卷纲时间线视图导出（含年龄推演）/ 反向对账（默认 dry-run） |
| `chapter-batch` | `confirm` | 章纲批量确认（自检 warning 不阻断） |
| `zones` / `impact` / `knowledge boundary` | — | 总纲三区迁移与状态 / 影响反查 / 信息差知识边界 |

各子命令的完整参数以 `webnovel.py <子命令> -h` 输出为准。

### 作者友好运行体验

`/webnovel-init`、`/webnovel-plan`、`/webnovel-write` 和 `/webnovel-review` 结束时都会输出统一最终报告。报告不直接输出原始 JSON、traceback 或长命令日志，而是先给一句总状态，再分三段说明：产生的文件与完成情况、过程中遇到的问题与异常耗时、下一步建议。

总状态有四种：

- **已完成**：目标产物和关键校验都通过。
- **部分完成**：主要产物已保留，但存在跳过项、自动处理项或待确认事项。
- **需要你处理**：系统停在安全位置，需要作者裁决创作方向、事实取舍、文件覆盖或 blocking 问题。
- **未完成**：关键产物没有可信生成，需要按报告建议重跑或排查。

长流程执行中只显示少量过程提示，说明当前阶段和会产生什么。自动补跑投影、重新 emit 缺失合同这类幂等操作不会打断作者，但会出现在最终报告里。重复执行同一条主命令时，系统会优先检查可信断点；首版断点续跑重点覆盖 `/webnovel-write`，尽量从失败点继续，而不是重写已可信完成的正文、审查、提交或备份。

## Story System 主链

推荐按以下顺序执行：

1. 生成合同

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" story-system "玄幻退婚流" --chapter 12 --persist --emit-runtime-contracts --format both
```

2. 提交章节

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" chapter-commit \
  --chapter 12 \
  --review-result ".webnovel/tmp/review_results.json" \
  --fulfillment-result ".webnovel/tmp/fulfillment_result.json" \
  --disambiguation-result ".webnovel/tmp/disambiguation_result.json" \
  --extraction-result ".webnovel/tmp/extraction_result.json"
```

3. 检查主链健康

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" preflight --format json
```

其中 `.story-system/` 是主链真源，`.webnovel/*` 是投影/read-model。

### 常用工具子命令

| 子命令 | 说明 |
|--------|------|
| `where` | 打印当前解析出的项目根目录 |
| `preflight` | 校验 CLI 环境、脚本路径和项目根是否可用 |
| `project-status` | 输出机器可读短状态（phase、目标章节、下一步），不占用旧 `status` |
| `doctor` | 阶段感知项目体检（目录、文件、DB、RAG、依赖、Dashboard） |
| `write-gate` | 写章自然边界校验（`prewrite` / `precommit` / `postcommit`） |
| `projections` | 从已有 commit 补跑或重放 projection |
| `user-report` | 渲染作者友好的最终报告，可输出 text/json |
| `run-ledger` | 记录写章步骤状态，或生成 `/webnovel-write` 断点续跑建议 |
| `run-log` | 写入脱敏运行日志 `.webnovel/logs/run_last.log` |
| `use <路径>` | 绑定当前工作区使用的书项目 |

示例：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" user-report --stage write --chapter 12 --format text
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" run-ledger write-resume --chapter 12 --format text
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" run-log --event write_failed --payload-json "{\"chapter\":12,\"reason\":\"projection timeout\"}"
```

### 数据模块子命令

| 子命令 | 说明 |
|--------|------|
| `index` | 索引管理（`process-chapter`、`stats` 等） |
| `state` | 状态管理 |
| `rag` | RAG 向量索引（`index-chapter`、`stats` 等） |
| `entity` | 实体链接 |
| `context` | 上下文管理 |
| `style` | 风格采样 |
| `migrate` | state.json → SQLite 迁移 |

### 运维子命令

| 子命令 | 说明 |
|--------|------|
| `status` | 宏观创作健康报告（`--focus all` / `--focus urgency`），仍转发到 `status_reporter.py` |
| `update-state` | 手动更新状态 |
| `backup` | 备份管理 |
| `archive` | 归档管理 |
| `extract-context` | 提取章节上下文（`--chapter N --format json`） |

### 长期记忆子命令

| 子命令 | 说明 |
|--------|------|
| `memory stats` | 查看总量、分类统计 |
| `memory query` | 按 category/subject/status 过滤查询 |
| `memory dump` | 导出完整 scratchpad 内容 |
| `memory conflicts` | 查看同主键 active 冲突项 |
| `memory bootstrap` | 从 index.db 与 summaries 回填初始长期记忆 |
| `memory update` | 对指定章节结果执行手动映射写入 |

示例：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" memory stats
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" memory query --category character_state --subject xiaoyan
```

### Story System 子命令

| 子命令 | 说明 |
|--------|------|
| `story-system "<题材>" --persist` | 写入合同种子（`MASTER_SETTING.json` 等） |
| `story-system "<题材>" --emit-runtime-contracts --chapter N` | 生成运行时合同 + 写前校验 |
| `chapter-commit --chapter N` | 提交章节 commit（可附带 review/fulfillment/disambiguation/extraction 结果） |
| `write-gate --chapter N --stage prewrite` | 写前检查项目阶段、Story System 合同和占位符 |
| `write-gate --chapter N --stage precommit` | 提交前检查正文和四类 commit artifacts |
| `write-gate --chapter N --stage postcommit` | 提交后检查 commit 与 projection 状态 |
| `projections retry --chapter N` | 基于已有 commit 补跑单章 projection |
| `projections replay --from-chapter A --to-chapter B` | 按章节范围重放 projection |
| `user-report --stage write --chapter N` | 汇总本次写章产物、问题和下一步建议 |
| `run-ledger record-write-step --chapter N` | 记录写章关键步骤的状态、输入输出、问题和耗时 |
| `run-ledger record-subagent --run-id <id> --name <agent> --status <status>` | 持久化一次 Agent 的状态、问题、自动处理、耗时和输出 |
| `run-ledger get-subagent-runs [--stage <stage>] [--chapter N]` | 查询作者报告使用的 Agent 运行记录 |
| `run-ledger write-resume --chapter N` | 根据可信断点输出续跑建议，不自动覆盖文件 |
| `run-log --event <name>` | 写入脱敏日志，供不可恢复故障排查 |
| `story-events --chapter N` | 查询指定章节事件 |
| `story-events --health` | 事件链健康检查 |
| `memory-contract` | 记忆合同管理 |
| `review-pipeline --chapter N --review-results <file>` | 审查流水线 |

示例：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" story-system "玄幻退婚流" --persist
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" chapter-commit --chapter 12 --review-result .webnovel/tmp/review.json
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" story-events --health
```

产物：

- `story-system --persist` → `.story-system/MASTER_SETTING.json`
- `--emit-runtime-contracts` → `volumes/*.json` 与 `reviews/*.review.json`
- `chapter-commit` → `commits/*.commit.json`
- `story-events` → 读取 `events/*.events.json` 或 `index.db.story_events`
