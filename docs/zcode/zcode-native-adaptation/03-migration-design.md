# 03 · 改造方案（设计决策 D1–D12）

> 依据：[01 现状审计](01-current-state-audit.md)、[02 能力地图](02-zcode-capability-map.md)。
> 总原则：**纯 ZCode 本体 + 可验证的安装链路 + 最小侵入**。每项决策记录「决定—理由—错了的代价」，实施中的偏离须回写 [ledger](2026-09-03-zcode-native-adaptation-ledger.md)。

## D1 · 清单布局：内层迁移 `.zcode-plugin/`，外层 marketplace.json 双位置镜像

**决定**
- 内层插件：`.claude-plugin/plugin.json` → **`.zcode-plugin/plugin.json`**（删除旧目录，不做双清单——Claude Code 不再是目标宿主）。
- 外层仓库：`marketplace.json` 放**仓库根**（github 源先例）+ 保留 `.claude-plugin/marketplace.json` 镜像（directory 源先例）。两处内容一致，由 `sync_plugin_version.py` 同步维护。

**理由**
- 内层是「插件本体」，纯 ZCode 定位要求第一优先探测位；token-meter 装机证明 `.zcode-plugin/` 完全可用。
- marketplace 探测位置官方未文档化，两种布局各有装机先例；双镜像把「未来 UI 刷新/重装」的探测风险压到零，维护成本仅一个同步函数。

**错了的代价**：若 ZCode directory 源只认 `.claude-plugin/marketplace.json`，单放根清单会导致 UI 侧 marketplace 刷新失败——双镜像已消除该风险；若两者都不认（无证据），回退为手工文件级装卸（05 runbook 本就覆盖）。

## D2 · 版本策略：7.0.0 → 7.1.0

minor bump（宿主适配 + MCP/commands/userConfig 新增强，无破坏性变更）。同步点：内层 `plugin.json`、外层两处 `marketplace.json`、根 `README.md` 版本表、`releases/v7.1.0.md`（`validate_release_notes.py` 校验链路保持可用）。

## D3 · 组件显式声明

`plugin.json` 声明：`"skills": "skills", "hooks": "hooks", "agents": "agents", "commands": "commands", "mcpServers": {…内联…}`。
- `agents` 字段在 ZCode「记录不执行」，但声明无害且自描述；实际加载走 `agents/` 目录自动发现（v6.5.0 事实验证）。
- 字符串目录形式以 token-meter/browser-use 装机样本为准。

## D4 · 环境变量统一：`ZCODE_*` 优先，`CLAUDE_*` 回退

**决定**
- `hooks/hooks.json`：4 处命令模板串 `${CLAUDE_PLUGIN_ROOT}` → `${ZCODE_PLUGIN_ROOT}`，`${CLAUDE_SESSION_ID}` 保留（ZCode 原生展开名，无 `ZCODE_SESSION_ID` 变体）。
- 脚本读 env 处统一改为 `ZCODE_* or CLAUDE_*` 双名模式：
  - `hooks/session_start.py`：`ZCODE_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT or __file__ 推导`；`ZCODE_PROJECT_DIR or CLAUDE_PROJECT_DIR or cwd`。
  - `scripts/project_locator.py`：`ENV_CLAUDE_PROJECT_DIR` 读取点全部加 `ZCODE_PROJECT_DIR` 优先。
- `CLAUDE_HOME/WEBNOVEL_CLAUDE_HOME`（config.py、project_locator.py 的 Claude 配置目录探测）：新增 `WEBNOVEL_ZCODE_HOME`/`ZCODE_HOME` 优先，旧名保留回退。

**理由**：ZCode 双名等价展开，但纯 ZCode 插件应主用原生名；保留 `CLAUDE_*` 回退使脚本在两种宿主下均可运行（多宿主 ADR 的 adapter 原则）。

## D5 · 脚本 `.zcode-plugin` 探测顺序

`sync_plugin_version.py`、`validate_plugin_package.py`、`validate_release_notes.py`、`run_behavior_evals.py` 中所有 `.claude-plugin` 硬编码改为探测函数：**先 `.zcode-plugin/plugin.json`，后 `.claude-plugin/plugin.json`**（与 ZCode 宿主探测顺序一致）。marketplace 侧同理（根 `marketplace.json` → `.claude-plugin/marketplace.json`）。对应测试同步更新（test_validate_plugin_package.py / test_validate_release_notes.py 增加双布局用例）。

## D6 · hooks 事件面：保留现有 4 事件，不新增事件

现有 4 事件（SessionStart/UserPromptSubmit/PreToolUse/PostToolUse）+ 现有 matcher 全部兼容。`PermissionRequest`/`PostToolUseFailure` 增强评估为「有价值但无当前痛点」，列入 04 §5 未来项，本次不做（YAGNI + 控制回归面）。

## D7 · skills / agents：结构不动，措辞清理

- frontmatter（`allowed-tools`/`tools/model/color`）不动——ZCode 全兼容。
- 正文 Claude 措辞分类替换（01 §2.7 表）；历史文档（docs/decisions、docs/reports、releases/）**不回改**。
- `/reload-plugins` 相关指引 → 「重启 ZCode 会话生效」。

## D8 · MCP server（本任务核心增强，详细设计在 04）

纯标准库 stdio MCP server（`mcp/server.py`），adapter 模式 subprocess 调 `webnovel.py`（多宿主 ADR 约束：不复制 runtime）。清单内联声明，模板变量定位插件根。

## D9 · userConfig：`bookProjectRoot`

`{type: directory, required: false}`，经 `${user_config.bookProjectRoot}` 注入 MCP env `WEBNOVEL_BOOK_ROOT`；`project_locator.py` 增加该变量支持（优先级：显式 `--project-root` > 环境变量 > cwd 向上探测 > last-used）。

## D10 · commands：`/webnovel:*` 8 个薄壳

`commands/webnovel/{status,doctor,query,write,plan,review,init,learn,dashboard}.md`（9 文件——status/doctor 为直接 CLI 壳，其余 7 个为对应 skill 的短名入口，frontmatter 带 `argument-hint`）。**修正：8 skill 对应 8 个命令 + status 独立 = 9 个文件；`/webnovel:status` 亦作为 CLI 壳。**

## D11 · 仓库级文档更新

- 根 `AGENTS.md`：技术栈声明（ZCode Plugin）、常用命令（pytest / validate / marketplace 安装）、目录结构（`.zcode-plugin`）、当前状态段落刷新。
- 内外 `README.md`：ZCode 安装说明（本地 marketplace directory 源 + GUI 安装步骤 + 文件级 runbook 指针）、版本表 7.1.0。
- `releases/v7.1.0.md`：发版说明（ZCode 原生化 + MCP + commands + userConfig）。

## D12 · 顺手修复：`run_tests.ps1` 陈旧路径

`.claude/scripts/…` → `webnovel-writer/scripts/…`（与根 `pytest.ini` 的 testpaths 一致），smoke/full 两模式路径同改。理由：测试链健康属于本任务验证依赖，且该脚本当前必然损坏（上游布局遗留）。

---

## 改动面汇总（预计触碰文件）

| 区域 | 文件 | 动作 |
|------|------|------|
| 清单 | `webnovel-writer/.zcode-plugin/plugin.json` | 新增（迁移+组件声明+7.1.0） |
| 清单 | `webnovel-writer/.claude-plugin/` | 删除 |
| 清单 | 根 `marketplace.json`（新）+ `.claude-plugin/marketplace.json`（更新） | 双镜像 |
| hooks | `hooks/hooks.json` | 模板变量改 `ZCODE_*` |
| hooks | `session_start.py` | env 双名 |
| scripts | `project_locator.py`、`data_modules/config.py` | env 双名 + `WEBNOVEL_BOOK_ROOT` |
| scripts | `sync_plugin_version.py`、`validate_plugin_package.py`、`validate_release_notes.py`、`run_behavior_evals.py` | `.zcode-plugin` 探测 + marketplace 双位置同步 |
| scripts | `run_tests.ps1` | 路径修复 |
| 测试 | `scripts/tests/test_validate_plugin_package.py`、`test_validate_release_notes.py` | 双布局用例 |
| MCP | `mcp/server.py`（新）+ `mcp/tests/` | MCP server + 测试 |
| commands | `commands/webnovel/*.md`（新 ×9） | 斜杠命令 |
| skills | 8 个 SKILL.md | 措辞清理 |
| agents | 4 个 md | 措辞清理（如有命中） |
| 文档 | 根/内层 README、AGENTS.md、`releases/v7.1.0.md` | 更新 |
| 文档 | `docs/zcode/zcode-native-adaptation/*` | 本文档集 |

**回归红线**：`python -m pytest`（根 pytest.ini，含 `--cov-fail-under=80`）全绿；`validate_plugin_package.py` / `validate_release_notes.py` 通过；装机后 8 skills + 4 agents + 9 commands + MCP server 全部出现且 hooks 正常注入。
