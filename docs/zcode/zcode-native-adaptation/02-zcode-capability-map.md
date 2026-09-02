# 02 · ZCode 插件能力地图 + Claude Code ↔ ZCode 功能对照矩阵

> 事实来源：`zcode-guide` 官方插件技能组（`zcode-configuration-guide`、`diagnosing-plugins`、`diagnosing-hooks`、`diagnosing-mcp`、`diagnosing-commands`、`diagnosing-skills`），交叉验证本机装机产物（`~/.zcode/cli/plugins/`）。所有规则均标注出处；未标注处为本机验证事实。

## 1. 插件系统核心事实

### 1.1 清单（manifest）

- 探测顺序（第一命中生效）：**`.zcode-plugin/plugin.json` → `.claude-plugin/plugin.json` → `.codex-plugin/plugin.json`**。（diagnosing-plugins §1）
- 必填字段仅 `name`，须匹配 `^[a-z0-9][a-z0-9._-]{0,127}$`；可选 `version`（缺省 `0.0.0`）、`description`、`commands/skills/hooks/mcpServers`、`userConfig`。（§2）
- **记录但不执行**的字段：`agents`、`channels`、`lspServers`、`outputStyles`、`settings`。（§2）
  - 注：`agents` 字段虽「不执行」，但 `agents/` 约定目录仍会被自动发现——本插件 4 个子代理在 v6.5.0（清单无任何组件声明）装机下已出现在会话中，属本机验证事实。
- 组件路径校验：绝对路径或逃逸插件根的路径会被拒绝。（pitfall 3）

### 1.2 组件字段写法（本机验证样本）

| 插件 | 声明 | 效果 |
|------|------|------|
| token-meter 1.0.0（本地 marketplace） | `"hooks": "hooks", "commands": "commands"`（字符串=目录名） | ✅ 装机工作 |
| browser-use 0.4.x（官方） | `"skills": "skills"` | ✅ |
| computer-use 0.5.13（官方） | `"skills": "skills"` + 内联 `mcpServers` | ✅ MCP server 注册 |

### 1.3 marketplace

- 格式：`{ name, plugins[], pluginRoot?, allowCrossMarketplaceDependenciesOn? }`；`plugins[].source` 支持相对路径 / `directory` / `github` / `git` / `url` / `git-subdir`；**`npm`、`pip` 不支持**。（diagnosing-plugins §2）
- marketplace 源可从 GitHub 仓库、Git URL、**本地目录**、文件添加。（§3）
- 装机产物链（本机验证）：
  1. `~/.zcode/cli/plugins/known_marketplaces.json` 登记源（directory 源记 `source.path`）；
  2. 源仓库克隆到 `~/.zcode/cli/plugins/marketplaces/<marketplace-id>/`（含 `.git`）；
  3. 插件本体按版本复制到 `~/.zcode/cli/plugins/cache/<marketplace-id>/<plugin>/<version>/`（无 `.git`，= marketplace source 指向目录的完整复制）；
  4. `~/.zcode/cli/plugins/installed_plugins.json` 登记 `id = <name>@<marketplace>`、`installPath`、`version`、`source`、`cacheTransactionId`；
  5. `~/.zcode/cli/config.json` → `plugins.enabledPlugins["<name>@<marketplace>"] = true`。
- marketplace 探测位置的双重先例：`claude-plugins-official`（github 源）用**仓库根** `marketplace.json`；`webnovel-writer-marketplace` / `token-meter-marketplace`（directory 源）用 `.claude-plugin/marketplace.json`——两种位置均被 ZCode 解析成功（本机 known_marketplaces 均有 pluginCount 记录）。

### 1.4 无 CLI 装卸通道

`zcode` 命令不在 PATH（本机验证）。装卸途径：GUI（Settings → Plugin Management）或**文件级操作**——zcode-configuration-guide 明确「an agent repairs configuration by reading and editing the underlying files directly」。本任务采用文件级（见 05 runbook）。

## 2. 七种 Hook 事件（全集）

`SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PermissionRequest`、`PostToolUse`、`PostToolUseFailure`、`Stop`。
- matcher 为**大小写敏感正则**；工具事件匹配工具名，别名 `Task ↔ Agent`、`ApplyPatch → Write/Edit`。（diagnosing-hooks §2）
- `type: "command"`：`timeout` 单位**秒**；`type: "process"`：`timeoutMs` 毫秒。
- 模板变量（命令串与参数中展开 + 注入环境变量）：`${CLAUDE_PROJECT_DIR}`/`${ZCODE_PROJECT_DIR}`、`${CLAUDE_SESSION_ID}`；plugin hooks 专属：`${CLAUDE_PLUGIN_ROOT}`/`${ZCODE_PLUGIN_ROOT}`、插件数据目录。
- 输出协议：stdout 严格 JSON schema（多余键直接失败）或退出码（0 过 / 2 阻断 / 其他报错）；`additionalContext` 注入会话；`PreToolUse` 可返回 `allow/ask/deny`；`Stop` 可请求继续（至多 3 次）。
- **插件 hooks 无需 `hooks.enabled: true`**——任一插件贡献 hook 即自动启用 runner。（§1）

## 3. MCP（本任务最大增强杠杆）

- 插件 MCP 来源：`<pluginRoot>/.mcp.json` 或清单 `mcpServers` 字段；键命名空间 `plugin:<plugin>:<server>`。（diagnosing-mcp §1）
- stdio schema：必填 `command`（字符串）；可选 `args[] / cwd / env / enabled / timeoutMs`。**未知键 → 整个 server 被丢弃**。（§2）
- **模板变量 `${...}` 只在插件提供的 MCP server 中展开**：`${CLAUDE_PLUGIN_ROOT}`/`${ZCODE_PLUGIN_ROOT}`、`${CLAUDE_PROJECT_DIR}`、`${user_config.KEY}`。配置文件作用域的 MCP **不**展开。（§1/§2，本任务 MCP 设计的依据）
- 插件 MCP 与用户/工作区/CLI 各作用域的 server 一样**会话启动即自动信任连接**。（§1）
- 默认超时 30000ms，可 `timeoutMs` 调整。
- userConfig（清单字段）：`type ∈ string|number|boolean|directory|file`，含 `title/description/default/required/sensitive`；值在 GUI（插件详情 → Advanced）填写，敏感值目前无法持久化。（diagnosing-plugins §2）

## 4. Commands 与 Skills 发现

- **Commands**：`.md` 文件 + frontmatter；嵌套目录以冒号连接——`commands/webnovel/write.md` → `/webnovel:write`。按规范化命令名去重，首个命中生效（用户作用域 > 工作区 > 插件）。（zcode-configuration-guide）
- **Skills 发现顺序**：显式根 → `~/.zcode/skills` → `~/.agents/skills` → 工作区 `.zcode/skills`（逐级向上）→ `.agents/skills` → **启用中的插件根**（最低）。同路径身份者全部发现、同名仅加载第一个（高优先级遮蔽低优先级）。
- 插件的 skills 在会话中带插件前缀暴露（本机验证：`webnovel-writer:webnovel-write`），用户可用 `/skill-name` 触发 Skill 工具调用。
- AGENTS.md：用户级 `~/.zcode/AGENTS.md` 先注入、工作区 `<repo>/AGENTS.md` 后注入（后者可收窄/覆盖前者）。插件**不能**贡献 AGENTS.md。

## 5. 功能对照矩阵（Claude Code ↔ ZCode）

| 能力 | Claude Code（现状） | ZCode（目标态） | 迁移动作 |
|------|---------------------|-----------------|----------|
| 插件清单 | `.claude-plugin/plugin.json` | `.zcode-plugin/plugin.json`（第一优先探测） | 迁移目录 + 声明组件 |
| marketplace 清单 | `.claude-plugin/marketplace.json` | 同 schema；根 `marketplace.json`（github 源先例）与 `.claude-plugin/`（directory 源先例）均可 | 双位置镜像（见 03 §D1） |
| Hook 事件 | 含 `Notification/SubagentStop/PreCompact/SessionEnd` | 恰 7 种（多 `PermissionRequest/PostToolUseFailure`，少 Claude 专属 4 种） | 现用 4 事件全兼容；新增 ZCode 独有事件为增强项 |
| Hook 模板变量 | `${CLAUDE_*}` | `${CLAUDE_*}` 与 `${ZCODE_*}` 双名展开 | hooks.json 改 `ZCODE_*`，脚本读 env 双名回退 |
| 插件根环境变量 | `CLAUDE_PLUGIN_ROOT` | `CLAUDE/ZCODE_PLUGIN_ROOT` 均注入 | 同上 |
| skills frontmatter | `allowed-tools` 等容忍 | 兼容（本机 6.5.0 事实验证） | 不动结构，清措辞 |
| agents | `agents/*.md`（frontmatter tools/model/color） | 同布局自动发现（本机事实验证） | 不动结构 |
| 斜杠命令 | `/webnovel-*`（Claude 命令目录，本插件未用） | `commands/webnovel/*.md` → `/webnovel:*` | **新增**（增强） |
| 插件 MCP | `.mcp.json` | 清单 `mcpServers` + 模板变量 + `${user_config.*}` | **新增**（增强） |
| 插件配置 | 无对应面 | `userConfig`（GUI 填写） | **新增**（增强） |
| 热重载 | `/reload-plugins` | 无对应命令；重启会话/应用 | 文档措辞替换 |
| 本地试装 CLI | `claude --plugin-dir <path>` | 无 CLI；本地 marketplace（directory 源）安装 | 安装指引重写 |
| 装卸通道 | CLI + GUI | GUI 或文件级编辑注册表 | 05 runbook |

## 6. ZCode 能力强化清单（本插件可用面）

1. **插件自带 MCP server**：把 `webnovel.py` 只读查询面（status/doctor/setting/entity/rag/meter/timeline）暴露为结构化工具，模型不再背 Bash 命令行咒语；会话自动连接。设计见 04。
2. **userConfig → MCP env**：`bookProjectRoot`（directory 类型）GUI 配置，经 `${user_config.bookProjectRoot}` 注入 MCP 环境变量，解决「会话 cwd ≠ 书项目根」的定位问题。
3. **`/webnovel:*` 斜杠命令**：短名入口 + `argument-hint`，与 skills 形成双通道。
4. **ZCode 独有 hook 事件**（本次仅评估不实施）：`PostToolUseFailure` 可做失败写日志观测；`PermissionRequest` 可对书项目敏感路径加询问闸。
5. **AGENTS.md 工作区注入**：`webnovel init` 生成的书项目应自带 `AGENTS.md`（ZCode 工作区指令），把写作硬规则注入每个写作会话——插件不能贡献 AGENTS.md，但**项目模板可以**。
6. **Dashboard 与 Playwright MCP 的组合**：ZCode 工作区常备 Playwright MCP（本工作区 `.zcode/config.json` 已接），`/webnovel:dashboard` 可指引用 Playwright 做只读面板验收——写进 skill 文档即可，零代码。
