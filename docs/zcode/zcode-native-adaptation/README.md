# ZCode 原生化改造 · 任务文档集

> 任务名称：`zcode-native-adaptation`
> 立项日期：2026-09-03
> 执行分支：`tmp/zcode`（自 `master` 拉出）
> 版本目标：v7.0.0 → **v7.1.0**
> 上游决策链：[ADR · 多宿主适配立项决策（2026-09-02）](../../decisions/2026-09-02-多宿主适配立项决策.md) —— 本任务是该 ADR「首期单宿主 = ZCode」的具体实施，并将范围从「adapter 正式化」扩展为「完整 ZCode 原生化 + 原生能力增强」。

## 任务目标

1. **纯 ZCode 插件**：插件本体从 Claude Code 插件格式（`.claude-plugin/`）迁移为 ZCode 原生格式（`.zcode-plugin/`），清理全部 Claude 专属残留（措辞、环境变量、路径硬编码、文档）。
2. **ZCode 原生增强**：利用 ZCode 独有/强调的能力面强化插件——插件自带 **MCP server**（结构化查询书项目数据）、**userConfig**（GUI 配置书项目根路径）、**斜杠命令**（`/webnovel:*` 短入口）。
3. **可维护的安装链路**：marketplace 指向本仓库新位置 `C:\lgq\ai-workspace\projects\zcode-plugins\webnovel-writer`，卸载旧装机、从新路径重装，并留下可复现的装卸手册。

## 文档地图

| 文档 | 内容 | 读者时机 |
|------|------|----------|
| [01-current-state-audit.md](01-current-state-audit.md) | 现状审计：v7.0.0 中全部 Claude 依赖面清单（清单文件、环境变量、hooks、skills/agents、脚本硬编码、文档措辞） | 改造前 |
| [02-zcode-capability-map.md](02-zcode-capability-map.md) | ZCode 插件能力地图（权威事实 + 出处），以及 Claude Code ↔ ZCode 逐项功能对照矩阵 | 设计依据 |
| [03-migration-design.md](03-migration-design.md) | 改造方案：12 项设计决策（清单策略、版本策略、环境变量、脚本探测顺序……） | 实施依据 |
| [04-enhancement-design.md](04-enhancement-design.md) | ZCode 原生增强方案：MCP server 工具面设计、userConfig、commands、hooks 增强 | 实施依据 |
| [05-install-reinstall-runbook.md](05-install-reinstall-runbook.md) | 卸载旧插件 + 从新路径重装的文件级操作手册（含回滚与验证清单） | 装机时 |
| [2026-09-03-zcode-native-adaptation-spec.md](2026-09-03-zcode-native-adaptation-spec.md) | Spec 摘要（审计链三件套之一） | 审批记录 |
| [2026-09-03-zcode-native-adaptation-plan.md](2026-09-03-zcode-native-adaptation-plan.md) | 实施计划：16 步串行队列，每步含改动面与验证命令（审计链三件套之二） | 实施队列 |
| [2026-09-03-zcode-native-adaptation-ledger.md](2026-09-03-zcode-native-adaptation-ledger.md) | 执行账本：Ruling 记录（决定—理由—代价）（审计链三件套之三） | 实施过程中回写 |

## 关键结论速览

- **兼容性现状**：ZCode 对 Claude Code 插件是「兼容识别」而非「原生」——`.claude-plugin/` 会被探测，hooks 事件、`${CLAUDE_PLUGIN_ROOT}` 模板变量、skills/agents frontmatter 均能工作。v6.5.0 装机即依赖这层兼容。
- **原生化收益**：`.zcode-plugin/` 是 ZCode 探测的第一优先位置；声明式组件字段（`skills`/`hooks`/`agents`/`commands`/`mcpServers`）让插件结构自描述。
- **最大增强点**：模板变量展开（含 `${ZCODE_PLUGIN_ROOT}`、`${user_config.KEY}`）**只在插件提供的 MCP server 中生效**，这使「插件自带 Python stdio MCP server」和「GUI 配置注入书项目路径」两个能力成为可能，且均有官方插件（computer-use）与本地插件（token-meter）的装机先例。
- **安装链路**：无 `zcode` CLI；装卸走文件级操作（`installed_plugins.json` / `known_marketplaces.json` / `marketplaces/` 克隆 / `cache/` 版本目录 / `config.json` 开关），zcode-guide 技能明确授权 agent 直接编辑这些文件。

## 范围边界

**做**：内层插件本体原生化、脚本/文档适配、MCP server、userConfig、commands、marketplace 更新、装卸与验证。
**不做**：第二个宿主（Codex 等，ADR 已否决）；v7 写路径架构变更；dashboard 前端重打包；GitHub 远程发布（`git push` 需作者另行确认）。
