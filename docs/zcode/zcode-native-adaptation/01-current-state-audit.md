# 01 · 现状审计：v7.0.0 的 Claude 依赖面全清单

> 审计日期：2026-09-03 · 审计对象：`master@6a335ec`（v7.0.0）
> 方法：目录结构遍历 + `grep` 全仓扫描（`.claude-plugin|CLAUDE_|claude|Claude Code`）+ 与 ZCode 装机产物（cache 6.5.0）比对。

## 1. 仓库双层结构

```
webnovel-writer/                    ← 外层仓库（marketplace + 开发资产）
├── .claude-plugin/
│   └── marketplace.json            ← 【Claude 布局】marketplace 清单（name: webnovel-writer-marketplace）
├── webnovel-writer/                ← 内层插件本体（ZCode 安装时整体复制进 cache）
│   ├── .claude-plugin/
│   │   └── plugin.json             ← 【Claude 布局】插件清单（v7.0.0，无组件声明）
│   ├── skills/（8 个）
│   ├── agents/（4 个 + evals/）
│   ├── hooks/（4 个脚本 + hooks.json）
│   ├── scripts/（CLI + data_modules 70+ 模块 + tests）
│   ├── references/ templates/ dashboard/ evals/
│   └── README.md LICENSE
├── docs/（architecture/decisions/plans/reports/…）
├── releases/（各版本发版说明）
├── tests 资产：pytest.ini（根）、sitecustomize.py、requirements.txt
└── AGENTS.md README.md CHANGELOG.md
```

ZCode 6.5.0 装机产物（`~/.zcode/cli/plugins/cache/webnovel-writer-marketplace/webnovel-writer/6.5.0/`）= 内层插件目录的完整复制（顶层 diff 为空，不含 `.git`）。

## 2. 依赖面分类清单

### 2.1 清单文件（改造主目标）

| 文件 | 现状 | ZCode 期望 |
|------|------|-----------|
| 内层 `.claude-plugin/plugin.json` | 仅元数据（name/version/description/author/homepage/repository/license/keywords 含 `"claude-code"`），**无组件声明** | `.zcode-plugin/plugin.json`（探测第一优先）；可选声明 `commands/skills/hooks/mcpServers/agents` 组件字段 |
| 外层 `.claude-plugin/marketplace.json` | `{name, plugins:[{name, version:7.0.0, source:"./webnovel-writer", …}]}` | 同 schema（ZCode 兼容）；官方 marketplace 用仓库根 `marketplace.json` |

### 2.2 环境变量（hooks 与脚本运行时）

| 变量 | 使用位置 | ZCode 行为 |
|------|---------|-----------|
| `CLAUDE_PLUGIN_ROOT` | `hooks/hooks.json`（4 处命令模板串）、`hooks/session_start.py:32` | ZCode 同样展开（plugin hooks 专属） |
| `CLAUDE_SESSION_ID` | `hooks/hooks.json`（chapter_meter）、`hooks/chapter_meter_hook.py:60` | ZCode 同样展开 |
| `CLAUDE_PROJECT_DIR` | `scripts/project_locator.py`（4 处）、`hooks/chapter_meter_hook.py:35`、`hooks/chapter_body_trace.py:22`、`hooks/session_start.py:33` | ZCode 同样展开（另有 `ZCODE_PROJECT_DIR` 别名；meter/trace 两脚本已写 `CLAUDE_PROJECT_DIR or ZCODE_PROJECT_DIR` 回退） |
| `CLAUDE_HOME` / `WEBNOVEL_CLAUDE_HOME` | `scripts/project_locator.py:63`、`scripts/data_modules/config.py:21` | ZCode 不提供；属「Claude 配置目录」探测逻辑 |

### 2.3 hooks（4 事件，全部在 ZCode 支持的 7 事件内）

| 事件 | matcher | 脚本 | ZCode 兼容性 |
|------|---------|------|-------------|
| `SessionStart` | `*` | `session_start.py`（注入项目状态 additionalContext） | ✅ matcher 匹配 startup/resume/clear/compact |
| `UserPromptSubmit` | — | `chapter_meter_hook.py`（token 计量注入；已读 ZCode 用量库） | ✅ |
| `PreToolUse` | `Write\|Edit\|MultiEdit` / `Bash` | `guard_runtime_write.py`（拦截对 Story System 运行时文件的直写） | ✅（`MultiEdit` 在 ZCode 无此工具名，正则无害；ZCode 有 `ApplyPatch`→`Write/Edit` 别名映射） |
| `PostToolUse` | `Write\|Edit\|MultiEdit` | `chapter_body_trace.py` | ✅ |

未使用 ZCode 独有事件：`PermissionRequest`、`PostToolUseFailure`（增强机会，见 04 文档）。

### 2.4 skills / agents frontmatter

- 8 个 skill（write/plan/query/review/init/learn/doctor/dashboard）frontmatter 含 `allowed-tools: Read Write Edit Grep Bash Agent AskUserQuestion` —— ZCode 全部有对应工具，✅ 兼容。
- 4 个 agent（context/data/reviewer/deconstruction）frontmatter 含 `tools / model: inherit / color` —— ZCode 会话中均已作为 `webnovel-writer:*` 子代理出现，✅ 兼容（v6.5.0 装机事实验证）。

### 2.5 脚本硬编码 `.claude-plugin` 路径（改名会波及）

| 脚本 | 硬编码点 |
|------|---------|
| `scripts/sync_plugin_version.py:11-12` | `PLUGIN_JSON_PATH` / `MARKETPLACE_JSON_PATH` 常量 |
| `scripts/validate_plugin_package.py:83,91,97,114,213` | 插件根探测、marketplace 探测、校验目标 |
| `scripts/validate_release_notes.py:41` | 读 plugin.json 版本 |
| `scripts/run_behavior_evals.py:24` | 插件根探测 |

对应测试：`scripts/tests/test_validate_plugin_package.py`、`scripts/tests/test_validate_release_notes.py`。

### 2.6 陈旧/损坏资产（顺手修复项）

- `scripts/run_tests.ps1`：`PYTHONPATH` 与 pytest 路径指向 `.claude/scripts/…` —— 外层仓库无此目录（上游布局遗留，当前必然跑不起来）。正确路径为 `webnovel-writer/scripts/…`（与根 `pytest.ini` 一致）。

### 2.7 文档与措辞（47 个文件命中 `claude`，分类）

| 类别 | 代表 | 处理策略 |
|------|------|---------|
| 元数据 keywords | plugin.json `"claude-code"` | 改 `zcode` |
| 安装指引 | 内外 README、AGENTS.md 的 `claude --plugin-dir …` | 改 ZCode marketplace 安装说明 |
| 会话操作 | skills 正文提及 `/reload-plugins`（Claude 命令） | 改为「重启会话」 |
| 宿主称谓 | 大量 "Claude Code"/"claude" 字样 | 统一 "ZCode"（历史决策文档 docs/ 下的按归档处理，不回改历史） |
| 环境变量名 | 见 2.2 | 统一 `ZCODE_*` 优先 + `CLAUDE_*` 回退 |
| 历史文档 | `docs/decisions/`、`docs/reports/`、`releases/*.md` | **不改**（审计痕迹，保持历史原貌） |

### 2.8 已有的 ZCode 适配存量（避免重复劳动）

- `scripts/data_modules/chapter_meter.py` / `webnovel.py meter`：已读 ZCode 用量库（含子代理），有测试 `test_chapter_meter.py`。
- `hooks/chapter_meter_hook.py` / `chapter_body_trace.py`：已有 `ZCODE_PROJECT_DIR` 回退。
- `docs/decisions/2026-09-02-多宿主适配立项决策.md`：明确「首期宿主 = ZCode」「adapter 模式：只调 `webnovel.py` 不复制 runtime」——本任务的 MCP server 设计遵循该约束。

### 2.9 版本与发版资产

- 版本号出现位置：内层 `plugin.json`、外层 `marketplace.json`、根 `README.md` 版本表（`sync_plugin_version.py` 负责三处同步 + `releases/` 说明校验 `validate_release_notes.py`）。
- 本任务版本策略：**7.1.0**（minor：宿主适配 + 新增强，无破坏性 API 变更）。
