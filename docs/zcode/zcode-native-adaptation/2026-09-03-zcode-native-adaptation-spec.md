# Spec · webnovel-writer ZCode 原生化改造

> 日期：2026-09-03 · 分支：`tmp/zcode` · 版本：7.0.0 → 7.1.0
> 状态：已获 Human 批准（任务指令即批准：文档 → 分支 → 严格按文档实施 → 装机）

## 问题

webnovel-writer v7.0.0 是 Claude Code 插件（`.claude-plugin/`），在 ZCode 中靠兼容层运行（marketplace 装机 6.5.0）。存在三层差距：
1. **身份差距**：清单、环境变量、措辞均为 Claude 专属；`.zcode-plugin/` 才是 ZCode 第一优先探测位。
2. **能力差距**：未使用 ZCode 独有的插件 MCP server、userConfig、模板变量注入（`${ZCODE_PLUGIN_ROOT}`/`${user_config.*}` 仅插件 MCP 展开）。
3. **链路差距**：marketplace 指向旧路径 `projects/claude-plugins/webnovel-writer`；无 CLI 装卸通道，需文件级 runbook。

## 方案（要点）

- **迁移**：内层清单 `.claude-plugin/` → `.zcode-plugin/plugin.json` + 组件显式声明；外层 marketplace.json 根位置 + `.claude-plugin/` 双镜像；环境变量 `ZCODE_*` 优先 `CLAUDE_*` 回退；4 个脚本改双布局探测；hooks.json 模板变量原生化；47 处 Claude 措辞分类清理（历史文档除外）。
- **增强**：纯标准库 stdio MCP server（9 个只读工具，adapter 调 `webnovel.py`，不复制 runtime）；userConfig `bookProjectRoot` 注入 MCP env；`/webnovel:*` 9 个薄壳命令；init 模板生成书项目 AGENTS.md。
- **装机**：卸载 6.5.0（缓存改名留存可回滚）→ marketplace 换源至新路径 → 模拟安装产物落 7.1.0 → 重启验证 7 项清单。

## 成功标准

1. `python -m pytest`（根 pytest.ini，含 cov≥80）全绿；
2. `validate_plugin_package.py` / `validate_release_notes.py` 通过；
3. 版本三处同步 7.1.0（plugin.json / 两处 marketplace.json / README 版本表）+ `releases/v7.1.0.md` 存在；
4. 装机重启后：8 skills + 4 agents + 9 commands + `webnovel` MCP（connected）+ hooks 注入/阻断 + userConfig 字段全部可见可用；
5. `tools/scripts/check-workspace.ps1` 通过（插件仓库与主仓库均已提交）。

## 约束

- 只读红线：MCP 不暴露写路径工具。
- adapter 红线：MCP/命令均为薄壳，业务只在 skill/CLI（多宿主 ADR）。
- 历史文档不回改；`git push` 不做（远程操作需作者确认）。
- 实施串行（单队列），每步验证通过才进下一步。

## 详细文档

[01 审计](01-current-state-audit.md) · [02 能力地图](02-zcode-capability-map.md) · [03 改造方案](03-migration-design.md) · [04 增强方案](04-enhancement-design.md) · [05 装卸 Runbook](05-install-reinstall-runbook.md) · [06 实施计划](2026-09-03-zcode-native-adaptation-plan.md) · [07 账本](2026-09-03-zcode-native-adaptation-ledger.md)
