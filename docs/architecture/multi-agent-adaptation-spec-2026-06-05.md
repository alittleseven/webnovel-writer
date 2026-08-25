# Webnovel Writer 多宿主与多智能体适配 Spec

> 日期：2026-06-05
> 状态：目标规格，尚未启动多宿主实现（2026-08-25 核对）
> 基线：`master` 当前插件形态，`.claude-plugin/plugin.json` 与 marketplace 版本为 `6.1.0`
> 来源：基于 PR #110 的 review 结论重写，修正过期的 7 Skill / hooks / doctor / runtime 状态描述
> 定位：把 Webnovel Writer 在不破坏 Claude Code 现有体验的前提下，演进为可验证、可生成、可降级的多宿主写作插件
> 当前状态：Claude Code 仍是唯一实际支持宿主；`adapters/`、registry、生成器和跨宿主 smoke/eval 尚未形成实现。进入条件与剩余工作见 `docs/plans/2026-08-25-status-and-pending-work.md`。

---

## 1. 背景

PR #110 的方向是对的：Webnovel Writer 不应该永远只被 Claude Code 的表达方式绑定。它已经有完整的写作运行时、Story System、RAG、Dashboard、Agent 分工和发布校验，下一步可以考虑多宿主适配。

但 PR #110 的原始 spec 使用了旧基线：

- 只列出 7 个 Skill，漏掉 `/webnovel-doctor`。
- 把 hooks 描述为“当前未形成 bootstrap”，但当前主干已经有 `hooks/hooks.json`、`session_start.py` 和 `guard_runtime_write.py`。
- 没有把 `project-status`、`doctor`、`write-gate`、`projections retry/replay`、`.webnovel/projection_log.jsonl` 纳入最终形态。
- 新增文档放在 `docs/superpowers/specs/`，但当前 `superpowers` 已归档到 `docs/archive/superpowers/`。

因此，本 spec 以当前 `v6.1.0` 运行时为基线重新定义多宿主适配方案。

---

## 2. 当前真实基线

### 2.1 Claude Code 插件结构

当前插件根为 `webnovel-writer/`，符合官方 `plugin-dev` 对 Claude Code 插件结构的要求：

```text
webnovel-writer/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── context-agent.md
│   ├── data-agent.md
│   ├── deconstruction-agent.md
│   └── reviewer.md
├── skills/
│   ├── webnovel-init/
│   ├── webnovel-plan/
│   ├── webnovel-write/
│   ├── webnovel-review/
│   ├── webnovel-query/
│   ├── webnovel-learn/
│   ├── webnovel-dashboard/
│   └── webnovel-doctor/
├── hooks/
│   ├── hooks.json
│   ├── session_start.py
│   └── guard_runtime_write.py
├── scripts/
├── references/
├── templates/
├── genres/
└── dashboard/
```

### 2.2 当前 8 个 Skill

| Skill | 当前职责 | 多宿主适配时的地位 |
|---|---|---|
| `/webnovel-init` | 初始化新书项目 | 保留为项目创建入口 |
| `/webnovel-plan` | 规划卷纲、章纲、运行时合同 | 保留为规划入口 |
| `/webnovel-write` | 写章主链，调用 gate、agent、commit、projection | 多宿主适配的最高优先级主流程 |
| `/webnovel-review` | 审查章节范围 | 保留为可独立调用的质量入口 |
| `/webnovel-query` | 只读查询项目状态、设定和记忆 | 保留为跨宿主只读查询入口 |
| `/webnovel-learn` | 追加项目经验记忆 | 保留为受控写入入口 |
| `/webnovel-dashboard` | 启动只读 Dashboard | 保留 Claude Code 主路径，其他宿主可降级为 CLI 提示 |
| `/webnovel-doctor` | 阶段感知体检目录、文件、DB、RAG、依赖 | 必须纳入所有宿主的安装后自检路径 |

### 2.3 当前 4 个 Agent

| 当前文件 | 当前职责 | 目标规范名 |
|---|---|---|
| `context-agent.md` | 写前上下文与任务书组装 | `webnovel-context-agent` |
| `reviewer.md` | 多维审查与 blocking issue 输出 | `webnovel-reviewer` |
| `data-agent.md` | 提取 commit artifacts，不直接写 projection | `webnovel-data-agent` |
| `deconstruction-agent.md` | 拆解参考书和结构学习 | `webnovel-deconstruction-agent` |

当前文件名不能直接删除或重命名，因为现有 Skill 文案和用户习惯可能仍引用旧名。目标规范名必须通过兼容迁移引入。

### 2.4 当前 Runtime CLI

所有确定性动作已经统一从 `scripts/webnovel.py` 进入。多宿主适配必须复用这些 runtime 命令，不为每个宿主重写一套业务逻辑。

关键命令：

| 命令 | 作用 |
|---|---|
| `preflight` | 快速环境与项目根检查 |
| `project-status` | 机器可读短状态、phase、下一步 |
| `doctor` | 阶段感知项目体检与修复建议 |
| `write-gate` | 写前、提交前、提交后三个自然边界校验 |
| `story-system` | Story System 合同与运行时数据 |
| `chapter-commit` | 章节事实提交，驱动 projection |
| `projections retry/replay` | 基于已有 commit 补跑或重放投影 |
| `status` | 旧宏观创作健康报告，保持原语义 |

### 2.5 当前 Hook

当前已经存在 Claude Code 插件级 hooks：

- `SessionStart`：只运行 `project-status --format summary`，给新会话提供短状态。
- `PreToolUse`：对直接写 `.story-system/commits/`、`.webnovel/state.json`、`index.db`、`vectors.db`、`memory_scratchpad.json`、`projection_log.jsonl` 等危险路径做兜底阻断。

hook 是轻量守卫，不是业务状态机。

### 2.6 当前验证能力

当前已有两类基础验证：

- `scripts/validate_plugin_package.py`：按官方 `plugin-dev` 思路检查 manifest、Skill / Agent frontmatter、hooks wrapper、README 版本、路径可移植性。
- `scripts/run_behavior_evals.py` + `evals/fixtures/behavior/fast.json`：检查 8 个 Skill 的关键行为契约、Agent 边界、commit/projection、Dashboard 只读语义。

多宿主适配必须扩展这两类验证，而不是新造一套互不相干的检查。

---

## 3. 目标

### 3.1 一句话目标

把 Webnovel Writer 从“Claude Code 单宿主插件”升级为：

> 以现有 Python runtime 和 Story System 为唯一业务核心，向多个宿主生成轻量 adapter 的长篇写作插件。

### 3.2 具体目标

1. 保留 Claude Code 现有安装、Skill、Agent、hook 和 CLI 体验。
2. 让 Codex、Cursor、Gemini CLI、OpenCode、GitHub Copilot CLI 等宿主可以通过 adapter 消费同一套写作能力。
3. 所有宿主都复用 `scripts/webnovel.py` 和 `data_modules`，不复制 Story System、commit、projection、doctor、gate 逻辑。
4. 每个宿主的支持状态必须可验证，有 manifest 校验、smoke 测试和行为 eval。
5. 当宿主不支持 subagent 或 hook 时，有明确降级模式，不假装已经调用了不存在的能力。
6. 所有新增插件组件继续符合官方 `plugin-dev` 的结构、frontmatter、hooks、路径和验证要求。

---

## 4. 非目标

本 spec 不做这些事：

- 不重写 Story System 主链。
- 不拆掉现有 8 个 Skill。
- 不改变 `webnovel.py status` 的旧健康报告语义。
- 不把 `doctor`、`project-status`、`write-gate`、`projection_log` 重新设计成另一套平行系统。
- 不把 hooks 变成隐藏业务流程。
- 不自动启动 Docker、Dashboard、RAG 服务或外部依赖。
- 不把 `docs/superpowers/` 重新作为活跃文档区；活跃架构 spec 进入 `docs/architecture/`。
- 不承诺未经官方文档和本地验证的外部宿主能力。

---

## 5. 设计原则

### 5.1 Runtime 是唯一业务真源

Skill、Agent、hook、adapter 都只是入口或调度层。真正能修改项目事实的动作必须进入 runtime：

```text
Skill / host command
    ↓
webnovel.py
    ↓
data_modules
    ↓
.story-system commit
    ↓
projection read-models
```

任何宿主 adapter 都不能直接写 `.story-system/commits/` 或 `.webnovel/*` read-model。

### 5.2 Claude Code 是第一支持宿主

Claude Code 当前体验必须保持稳定：

- `.claude-plugin/plugin.json` 保持官方位置。
- `skills/`、`agents/`、`hooks/` 保持插件根层级。
- Claude hooks 继续使用 `${CLAUDE_PLUGIN_ROOT}`，符合官方 `plugin-dev`。
- `/webnovel-*` Skill 名称继续有效。

### 5.3 Adapter 尽量薄

各宿主 adapter 只负责：

- manifest / metadata
- tool name mapping
- agent frontmatter 转换
- command 暴露方式
- hook 能力降级
- smoke/eval 启动方式

adapter 不负责：

- 改写写作流程
- 解释 Story System
- 校验 chapter artifacts
- 执行 projection
- 自己维护项目状态

### 5.4 不相信手写矩阵

外部宿主能力变化很快。spec 不把“某宿主现在支持什么”写成不可验证的口头事实。

每个宿主 adapter 必须有自己的 `support.md` 或等价记录，包含：

- 官方文档链接
- 核验日期
- 支持的 manifest 字段
- 支持的 skill / command / agent / hook / MCP 能力
- 不支持能力的降级规则
- 本仓库对应的 smoke 测试命令

### 5.5 UTF-8 First

所有新增脚本和 adapter 生成器必须显式 UTF-8：

- Python 文件头保留 UTF-8。
- 文本读写使用 `encoding="utf-8"`。
- Windows 子进程优先使用 `python -X utf8`。
- 不依赖系统默认 GBK 编码。

### 5.6 渐进迁移

多宿主适配必须逐步引入：

1. 先锁定现状和验证。
2. 再补 adapter 目录与生成器。
3. 再迁移 Agent 规范名和 Skill 文案。
4. 最后接入跨宿主 smoke/eval。

不能一次性重命名 Agent 或大改 Skill，避免破坏 Claude Code 现有用户。

---

## 6. 目标架构

### 6.1 目标结构

最终结构建议如下：

```text
webnovel-writer/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   ├── webnovel-init/
│   ├── webnovel-plan/
│   ├── webnovel-write/
│   ├── webnovel-review/
│   ├── webnovel-query/
│   ├── webnovel-learn/
│   ├── webnovel-dashboard/
│   ├── webnovel-doctor/
│   └── using-webnovel-writer/        # 可选，跨宿主使用说明与工具映射
├── agents/
│   ├── context-agent.md              # 旧名兼容
│   ├── reviewer.md                   # 旧名兼容
│   ├── data-agent.md                 # 旧名兼容
│   ├── deconstruction-agent.md       # 旧名兼容
│   └── aliases.json                  # 可选，声明旧名到规范名的映射
├── hooks/
│   ├── hooks.json                    # Claude Code 源 hook
│   ├── session_start.py
│   └── guard_runtime_write.py
├── adapters/
│   ├── README.md
│   ├── registry.json                 # 宿主 adapter 注册表
│   ├── claude/
│   ├── codex/
│   ├── cursor/
│   ├── gemini/
│   ├── opencode/
│   └── copilot/
├── scripts/
│   ├── webnovel.py
│   ├── validate_plugin_package.py
│   ├── run_behavior_evals.py
│   └── generate_host_artifacts.py    # 新增，生成非 Claude adapter 产物
├── evals/
│   └── fixtures/
├── references/
├── templates/
├── genres/
└── dashboard/
```

说明：

- `adapters/` 是 adapter 源码和模板，不是生成产物。
- `dist/` 用于生成后的宿主包，默认不提交。
- 只有小型、稳定、必须被宿主直接发现的 manifest 可以提交；提交前必须通过 drift check。

### 6.2 业务源与生成产物

| 类型 | 路径 | 是否事实源 | 是否提交 |
|---|---|---:|---:|
| Claude 插件 manifest | `.claude-plugin/plugin.json` | 是 | 是 |
| Skill 源文件 | `skills/*/SKILL.md` | 是 | 是 |
| Agent 源文件 | `agents/*.md` | 是 | 是 |
| Claude hook 源文件 | `hooks/hooks.json`、`hooks/*.py` | 是 | 是 |
| Runtime | `scripts/`、`data_modules/` | 是 | 是 |
| Adapter 模板 | `adapters/<host>/` | 是 | 是 |
| 生成器 | `scripts/generate_host_artifacts.py` | 是 | 是 |
| 非 Claude 生成包 | `dist/<host>/webnovel-writer/` | 否 | 否 |
| 小型宿主 manifest 快照 | `.codex-plugin/plugin.json` 等 | 视宿主而定 | 需 drift check |

---

## 7. 环境变量与路径策略

### 7.1 Claude Code 路径保持不变

在 Claude Code 插件组件里继续使用：

```text
${CLAUDE_PLUGIN_ROOT}
```

这是官方 `plugin-dev` 推荐方式，不能为了跨宿主把 Claude hook 或 Claude Skill 里的路径粗暴替换掉。

### 7.2 Runtime 可增加兼容解析

Python runtime 可以支持更通用的插件根解析顺序：

1. 显式 CLI 参数。
2. `WEBNOVEL_PLUGIN_ROOT`。
3. `CLAUDE_PLUGIN_ROOT`。
4. 当前脚本路径向上推导。

但这属于 runtime 兼容层，不代表 Claude 插件文档主变量要改名。

### 7.3 Skill 文案中的路径写法

Claude Code Skill 里的可执行示例继续用：

```bash
python -X utf8 "${CLAUDE_PLUGIN_ROOT}/scripts/webnovel.py" ...
```

跨宿主说明放到 `using-webnovel-writer` 或 `skills/*/references/host-tools.md`，不要把所有宿主变量塞进每个 Skill 主体。

---

## 8. Skill 适配规范

### 8.1 保留当前 8 个业务 Skill

多宿主适配不能删减当前 8 个 Skill，也不能让 `/webnovel-doctor` 成为 Claude-only 的遗漏项。

每个 Skill 必须满足：

- `SKILL.md` 有 `name` 和具体触发型 `description`。
- 主体只写流程、边界和必要命令。
- 详细工具映射、宿主差异、参考规则放进 `references/`。
- 确定性校验交给 runtime 命令，不靠自然语言提醒。

### 8.2 新增可选总入口 Skill

可以新增：

```text
skills/using-webnovel-writer/SKILL.md
```

用途：

- 给非 Claude 宿主提供统一使用说明。
- 解释当前宿主下的工具名映射。
- 引导先运行 `project-status`，必要时运行 `doctor`。
- 说明不支持 subagent/hook 的降级模式。

限制：

- 不替代 8 个业务 Skill。
- 不复制每个 Skill 的完整流程。
- 不承载题材知识和 Story System schema。

### 8.3 写章 Skill 的硬要求

`webnovel-write` 是多宿主适配的核心验收对象。任何宿主的写章流程都必须保留：

1. 写前调用 `write-gate --stage prewrite`。
2. 提交前调用 `write-gate --stage precommit`。
3. 提交事实只能走 `chapter-commit`。
4. 提交后调用 `write-gate --stage postcommit`。
5. projection 失败时提示 `projections retry --chapter N`。
6. 不能直接手写 read-model。

---

## 9. Agent 适配规范

### 9.1 规范名与旧名兼容

目标规范名使用 `webnovel-` 前缀：

| 旧名 | 规范名 |
|---|---|
| `context-agent` | `webnovel-context-agent` |
| `reviewer` | `webnovel-reviewer` |
| `data-agent` | `webnovel-data-agent` |
| `deconstruction-agent` | `webnovel-deconstruction-agent` |

迁移方式：

1. 先在文档和 adapter registry 中声明映射。
2. 再让生成器为不同宿主输出规范名。
3. 最后逐步修改 Skill 正文使用规范名。
4. 旧名至少保留一个小版本周期，避免破坏现有调用。

### 9.2 Agent 边界

所有宿主都必须遵守现有边界：

- `context-agent` 只负责写前上下文和任务书。
- `reviewer` 只负责审查和 blocking 输出。
- `data-agent` 只产出 commit artifacts，不直接写 projection。
- `deconstruction-agent` 只负责参考拆解和经验沉淀。

### 9.3 无 subagent 宿主的降级模式

如果宿主不能稳定调用 subagent：

- 进入 compatibility mode。
- 主 agent 按同一份任务书和 artifact schema 执行。
- 输出必须明确说明“未调用 subagent，使用兼容模式”。
- 仍然必须通过 `artifact_validator`、`write-gate` 和行为 eval。
- 不允许声称已经调用了不存在的 subagent。

---

## 10. Hook 适配规范

### 10.1 Claude Code hook 保持现状

当前 Claude Code hook 是有效基线：

```text
hooks/hooks.json
hooks/session_start.py
hooks/guard_runtime_write.py
```

必须继续满足官方 `plugin-dev`：

- `hooks/hooks.json` 使用 wrapper 格式：外层包含 `description` 与 `hooks`。
- command hook 使用 `${CLAUDE_PLUGIN_ROOT}`。
- hook 脚本只做轻量、确定性、可快速退出的检查。

### 10.2 其他宿主 hook 可选

其他宿主是否支持 hook，由对应 adapter 的 `support.md` 和 smoke test 决定。

若宿主不支持 hook：

- 不影响核心写作流程。
- 通过 `project-status` / `doctor` / `write-gate` 显式命令补足。
- 不能让某个关键能力只存在于 hook 中。

### 10.3 hook 禁止做的事

hook 不允许：

- 自动写 commit。
- 自动改正文。
- 自动改设定。
- 自动安装依赖。
- 自动启动长驻服务。
- 写入章节流程状态。

---

## 11. Doctor 与状态入口

### 11.1 所有宿主共享同一状态入口

多宿主适配必须统一使用：

```bash
python -X utf8 "<PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" project-status --format summary
```

当短状态显示异常时，再运行：

```bash
python -X utf8 "<PLUGIN_ROOT>/scripts/webnovel.py" --project-root "<PROJECT_ROOT>" doctor --format text
```

### 11.2 不新增第二套 status

`status` 继续保留宏观创作健康报告语义。

短状态只用 `project-status`。

深度体检只用 `doctor`。

### 11.3 doctor 的跨宿主价值

`doctor` 是多宿主适配的安装后第一检查入口，必须能回答：

- 项目根是否解析正确。
- 当前 phase 是什么。
- 当前 phase 应该有哪些文件。
- 目录、JSON、SQLite 是否完整。
- RAG 配置是否存在。
- Python 依赖是否安装。
- Dashboard 产物是否存在。
- projection 是否失败。
- 缺失项怎么修。

---

## 12. Adapter 设计

### 12.1 Adapter registry

新增：

```text
adapters/registry.json
```

建议结构：

```json
{
  "schema_version": "webnovel-host-adapter-registry/v1",
  "hosts": {
    "claude": {
      "tier": "primary",
      "source": ".claude-plugin/plugin.json",
      "supports": ["skills", "agents", "hooks"],
      "smoke": "python -X utf8 scripts/validate_plugin_package.py --format json"
    },
    "codex": {
      "tier": "adapter",
      "source": "adapters/codex/",
      "supports": [],
      "smoke": ""
    }
  }
}
```

`supports` 不能手写猜测，必须由该宿主 `support.md` 和 smoke test 支撑。

### 12.2 每个宿主目录

每个宿主 adapter 至少包含：

```text
adapters/<host>/
├── support.md              # 官方文档核验记录
├── manifest.template.*     # 需要时才有
├── tool-mapping.md         # 工具名与降级规则
├── agent-mapping.json      # 规范 agent 名与宿主表达
└── smoke.md                # 本地验证命令
```

### 12.3 生成器

新增生成器：

```bash
python -X utf8 scripts/generate_host_artifacts.py --target all
python -X utf8 scripts/generate_host_artifacts.py --target codex
python -X utf8 scripts/generate_host_artifacts.py --check
```

生成器负责：

- 读取 adapter registry。
- 读取 Skill / Agent / hook 源文件。
- 生成宿主 manifest。
- 生成宿主 agent 配置。
- 生成宿主 command / skill 入口。
- 生成 drift manifest。

生成器不负责：

- 修改业务源文件。
- 联网下载依赖。
- 改写 Story System schema。
- 运行写作流程。

---

## 13. 验证与 CI

### 13.1 Package validator 扩展

当前 `validate_plugin_package.py` 继续作为基础。后续扩展检查：

- `adapters/registry.json` schema。
- 每个 adapter 是否有 `support.md`。
- 每个 adapter 是否声明 smoke 命令。
- 生成产物是否含本机绝对路径。
- 小型提交 manifest 是否与生成器输出一致。
- `docs/README.md` 是否索引活跃 spec。

### 13.2 Behavior eval 扩展

当前 fast eval 已覆盖 8 个 Skill。后续增加：

- 每个宿主至少一个 install / discover smoke。
- 每个宿主至少一个 `project-status` smoke。
- `webnovel-doctor` 在每个宿主都有可执行说明。
- `webnovel-write` 在至少一个非 Claude 宿主完成兼容模式验收。
- 无 subagent 宿主不得声称调用 subagent。

### 13.3 Drift check

如果提交了任何生成 manifest 或 generated adapter 文件，CI 必须运行：

```bash
python -X utf8 scripts/generate_host_artifacts.py --check
```

失败时说明：

- 哪个源文件变化导致 drift。
- 应该重新运行哪个生成命令。
- 哪些生成文件需要提交。

### 13.4 外部能力核验

每次实现某个宿主 adapter 前，必须重新核验官方文档。

核验结果写入：

```text
adapters/<host>/support.md
```

`support.md` 至少包含：

- 核验日期。
- 官方链接。
- 支持能力。
- 不支持能力。
- 本仓库采用的降级策略。

---

## 14. 迁移计划

### Phase 0：锁定现状

目标：让 spec 和当前主干一致。

改动：

- 新增本 spec 到 `docs/architecture/`。
- 更新 `docs/README.md` 索引。
- 不新增 `docs/superpowers/` 活跃目录。

验收：

- 文档列出 8 个 Skill。
- 文档列出当前 hooks。
- 文档列出 doctor、project-status、write-gate、projections、projection_log。
- `git diff --check` 通过。

### Phase 1：Adapter 研究记录与注册表

目标：先验证外部宿主能力，不写大规模生成器。

改动：

- 新增 `adapters/README.md`。
- 新增 `adapters/registry.json`。
- 为每个目标宿主新增 `support.md`。
- 每个 `support.md` 只记录官方文档核验结果和本项目降级策略。

影响：

- 不影响现有 Claude Code 用户。
- 不影响 runtime。

### Phase 2：Agent 规范名与兼容映射

目标：引入 `webnovel-*` 规范 Agent 名，但不破坏旧名。

改动：

- 新增 `agents/aliases.json` 或等价映射。
- 更新 adapter registry 使用规范名。
- 更新 behavior eval，确保旧名与规范名不会互相漂移。

影响：

- Claude Code 现有 Skill 仍可调用旧名。
- 后续宿主生成优先使用规范名。

### Phase 3：Skill 瘦身与宿主工具映射

目标：减少 Skill 主体中的 Claude-only 工具表达。

改动：

- 新增 `skills/using-webnovel-writer/`。
- 把跨宿主工具映射放到 references。
- 保留 Claude Code 示例中的 `${CLAUDE_PLUGIN_ROOT}`。
- 不把每个宿主的完整说明复制进 8 个业务 Skill。

影响：

- Skill 更短，更容易被不同宿主消费。
- 当前 Claude Code 命令不变。

### Phase 4：生成器与 drift check

目标：让非 Claude adapter 可生成、可检查。

改动：

- 新增 `scripts/generate_host_artifacts.py`。
- 生成 `dist/<host>/webnovel-writer/`。
- 扩展 `validate_plugin_package.py` 检查 adapter。
- CI 增加 drift check。

影响：

- 新增开发工具，不改变用户项目数据。
- 生成文件默认不提交。

### Phase 5：跨宿主 smoke 与行为 eval

目标：证明“能发现、能体检、能执行核心流程或明确降级”。

改动：

- 扩展 `run_behavior_evals.py`。
- 每个宿主至少有 discover / project-status / doctor smoke。
- 至少一个非 Claude 宿主完成 `webnovel-write` 兼容模式验收。

影响：

- 发布前检查时间增加。
- 适配声明更可信。

### Phase 6：发布文档与版本治理

目标：用户知道哪个宿主支持到什么程度。

改动：

- README 增加多宿主支持表。
- `docs/guides/commands.md` 增加非 Claude 使用口径。
- `docs/operations/plugin-release.md` 增加 adapter 发布检查。
- release note 明确每个宿主支持等级。

影响：

- 避免用户误以为所有宿主都已完整支持。
- 降低 issue 中的环境误解。

---

## 15. 风险与控制

| 风险 | 影响 | 控制 |
|---|---|---|
| 外部宿主能力描述过期 | spec 很快失真 | 每个 adapter 用 `support.md` 记录官方核验日期和链接 |
| 为每个宿主复制业务流程 | 逻辑漂移 | adapter 只调 `webnovel.py`，不复制 runtime |
| 重命名 Agent 破坏旧流程 | 现有用户调用失败 | 旧名兼容一个小版本周期以上 |
| hook 被误当业务流程 | 隐藏副作用 | hook 只做状态提示和危险写入兜底 |
| Skill 主体继续膨胀 | token 消耗高 | 详细内容下沉 references，确定性动作下沉 scripts |
| 生成产物漂移 | 发布包和源不一致 | `generate_host_artifacts.py --check` |
| Windows 中文路径失败 | 用户无法运行 | 所有新增 Python I/O 使用 UTF-8，命令用 `python -X utf8` |

---

## 16. 验收清单

最终完成时必须满足：

- [ ] Claude Code 原安装流程不破坏。
- [ ] 8 个现有 Skill 仍可发现。
- [ ] `/webnovel-doctor` 保留并进入多宿主自检路径。
- [ ] 当前 hooks 保持 plugin-dev wrapper 格式。
- [ ] `project-status`、`doctor`、`write-gate`、`projections` 都是跨宿主共享 runtime 入口。
- [ ] `status` 仍保留旧宏观健康报告语义。
- [ ] Agent 规范名有 `webnovel-` 前缀，旧名有兼容映射。
- [ ] 每个 adapter 都有 `support.md`，包含官方文档核验日期和链接。
- [ ] 每个 adapter 都有 smoke 命令或明确阻断原因。
- [ ] 生成器可生成非 Claude 宿主产物。
- [ ] drift check 能发现生成产物不一致。
- [ ] package validator 覆盖 adapter registry、support.md 和 manifest 漂移。
- [ ] behavior eval 覆盖 8 个 Skill 和至少一个非 Claude 兼容写作流程。
- [ ] README 和 release note 明确每个宿主的支持等级。

---

## 17. 简短结论

这次多宿主适配的核心不是“再写一套插件”，而是：

- 保住当前 `v6.1.0` 已经做好的 runtime 基线。
- 把 Claude Code 作为第一宿主继续维护。
- 用 adapter 和生成器把同一套能力暴露给其他宿主。
- 用 doctor、project-status、write-gate、projection log 和 eval 证明它真的能用。

这样改，后续扩展宿主时不会把项目重新打散，也不会让用户在多个看起来相似、实际语义不同的入口里迷路。
