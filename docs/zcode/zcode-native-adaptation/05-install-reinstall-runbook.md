# 05 · 卸载与重装 Runbook（文件级操作手册）

> 背景：`zcode` CLI 不存在；GUI 操作无法由 agent 驱动本应用自身。zcode-configuration-guide 授权 agent 直接编辑配置文件。本手册操作对象全部为本机用户目录，**改完必须重启 ZCode（或新开会话）才生效**。
> 新插件源：`C:\lgq\ai-workspace\projects\zcode-plugins\webnovel-writer`（外层仓库；插件本体在内层 `webnovel-writer/`，marketplace source = `./webnovel-writer`）。
> 旧装机：marketplace `webnovel-writer-marketplace` → 旧路径 `C:\lgq\ai-workspace\projects\claude-plugins\webnovel-writer`，插件版本 6.5.0。

## 0. 涉及文件清单

| 路径 | 角色 |
|------|------|
| `~/.zcode/cli/config.json` | `plugins.enabledPlugins` 开关 |
| `~/.zcode/cli/plugins/installed_plugins.json` | 装机登记（版本、installPath、source、cacheTransactionId） |
| `~/.zcode/cli/plugins/known_marketplaces.json` | marketplace 源登记（directory 源记 `source.path`） |
| `~/.zcode/cli/plugins/marketplaces/webnovel-writer-marketplace/` | marketplace 源克隆（含 `.git`） |
| `~/.zcode/cli/plugins/cache/webnovel-writer-marketplace/webnovel-writer/<version>/` | 插件版本化装机副本 |

> Windows 下 `~` = `C:\Users\a6748`。所有 JSON 编辑用 Python（`json` 模块读写，UTF-8，保持既有缩进风格），避免手工编辑引入 BOM/尾逗号。

## 1. 卸载旧插件（v6.5.0）

```powershell
# 1) config.json：删除 enabledPlugins["webnovel-writer@webnovel-writer-marketplace"]
# 2) installed_plugins.json：删除 id=webnovel-writer@webnovel-writer-marketplace 的条目
# 3) 删除缓存目录：cache/webnovel-writer-marketplace/（整目录，含 6.2.1/6.5.0 两个历史版本）
```

marketplace 登记与克隆**保留 id 不动、原地改指向**（见 §2），等效于「换源不换 marketplace」——`webnovel-writer@webnovel-writer-marketplace` 这个组件标识在新装机后保持不变，历史配置（如未来 userConfig 值）不受扰动。

## 2. marketplace 换源（旧路径 → 新路径）

```powershell
# 1) known_marketplaces.json：
#    marketplaces[id=webnovel-writer-marketplace].source.path
#      "C:\\lgq\\ai-workspace\\projects\\claude-plugins\\webnovel-writer"
#      → "C:\\lgq\\ai-workspace\\projects\\zcode-plugins\\webnovel-writer"
#    （name/description 以新源 marketplace.json 为准刷新；lastUpdated 更新为当前时间）
# 2) marketplaces/webnovel-writer-marketplace/：整目录替换为新仓库当前 HEAD 的干净副本（含 .git）
#    —— 与 ZCode「克隆源仓库到该目录」的行为对齐
```

> 注意：新源 marketplace.json 的 `name` 必须仍为 `webnovel-writer-marketplace`（id 稳定的前提）。

## 3. 重装 v7.1.0（模拟 ZCode 安装产物）

```powershell
# 1) 建版本缓存目录：
#    cache/webnovel-writer-marketplace/webnovel-writer/7.1.0/
# 2) 复制插件本体（内层目录完整内容，排除 .git / __pycache__ / *.pyc / .pytest_cache）到上述目录
# 3) installed_plugins.json 追加条目：
{
  "id": "webnovel-writer@webnovel-writer-marketplace",
  "name": "webnovel-writer",
  "marketplace": "webnovel-writer-marketplace",
  "version": "7.1.0",
  "installPath": "C:\\Users\\a6748\\.zcode\\cli\\plugins\\cache\\webnovel-writer-marketplace\\webnovel-writer\\7.1.0",
  "installedAt": "<now ISO8601 Z>",
  "updatedAt": "<now ISO8601 Z>",
  "scope": "user",
  "source": "./webnovel-writer",
  "cacheTransactionId": "<新 UUIDv4>"
}
# 4) config.json：plugins.enabledPlugins["webnovel-writer@webnovel-writer-marketplace"] = true
```

复制清单（与 6.5.0 装机副本顶层一致 + 新增件）：
`.zcode-plugin/ · agents/ · commands/ · hooks/ · mcp/ · skills/ · scripts/ · references/ · templates/ · dashboard/ · evals/ · README.md · LICENSE · .gitignore`

## 4. 装机后验证清单（需重启 ZCode / 新会话）

| # | 验证点 | 判据 |
|---|--------|------|
| 1 | 插件版本 | Settings → Plugin Management → webnovel-writer 显示 7.1.0；会话 skill 前缀 `webnovel-writer:` 的 8 个 skill 均可发现 |
| 2 | 斜杠命令 | `/` 菜单出现 `/webnovel:status` … `/webnovel:dashboard` 9 条 |
| 3 | MCP server | Settings → MCP 出现 `webnovel`（built-in 标记）且 connected；会话内可调用 `mcp__webnovel__webnovel_where` 类工具 |
| 4 | hooks | 新会话首条消息后出现 webnovel 项目状态注入（SessionStart/`chapter_meter` 链路）；对运行时文件的直写被 `guard_runtime_write` 阻断（可低风险试探一次） |
| 5 | agents | Agent 工具可用类型含 `webnovel-writer:context-agent` 等 4 个 |
| 6 | userConfig | 插件详情 → Advanced 出现「书项目根目录」directory 字段 |
| 7 | CLI 冒烟 | 在书项目内：`python -X utf8 <installPath>/scripts/webnovel.py preflight` 通过；`webnovel_doctor` MCP 工具返回体检 JSON |

## 5. 回滚方案

- 保留旧缓存即可秒回滚：恢复 `installed_plugins.json` 中 6.5.0 条目（installPath 指回 `…\webnovel-writer\6.5.0`）、config.json 开关键、marketplace source.path 指回旧路径，重启。
- 本 runbook 执行前先备份三个 JSON（`*.bak-zcode-adaptation`）。旧缓存目录（6.5.0）在 §1.3 中删除——**如需保留回滚能力，改为把 6.5.0 目录改名留存（`6.5.0.bak`）而非删除**（ZCode 只按 installed_plugins.json 的 installPath 定位，改名目录不会被扫描）。本任务采用「改名留存」。
