# webnovel-writer — 项目约定

> 继承全局 AGENTS.md 和工作区 AGENTS.md，以下规则优先。

## 技术栈

- Python 3.10+ / pytest
- ZCode Plugin（`.zcode-plugin/` 清单：skills + agents + hooks + commands + MCP server）
- MCP server：纯标准库 stdio JSON-RPC（`mcp/server.py`，零第三方依赖）
- Dashboard 前端：预打包 dist/，不需要 npm build

## 常用命令

```powershell
# 运行测试（根 pytest.ini：data_modules + scripts + mcp 三处，覆盖率门槛 80）
python -X utf8 -m pytest

# smoke 快速子集
powershell -File webnovel-writer/scripts/run_tests.ps1 -Mode smoke

# 打包校验 + 发版说明校验 + 版本三处一致性检查
python -X utf8 webnovel-writer/scripts/validate_plugin_package.py
python -X utf8 webnovel-writer/scripts/validate_release_notes.py
python -X utf8 webnovel-writer/scripts/sync_plugin_version.py --check

# CLI 预检（替换 <book-root> 为实际书项目路径）
python -X utf8 webnovel-writer/scripts/webnovel.py --project-root "<book-root>" preflight
```

## 目录结构

```
webnovel-writer/              ← 外层仓库根（marketplace.json 双位置：根 + .claude-plugin/）
└── webnovel-writer/          ← 内层插件本体（.zcode-plugin 清单）
    ├── .zcode-plugin/        ← plugin.json（组件声明 + mcpServers + userConfig）
    ├── skills/               ← 8 个 skill
    ├── agents/               ← 4 个子代理
    ├── commands/webnovel/    ← 13 个 /webnovel:* 斜杠命令（薄壳）
    ├── hooks/                ← 4 个 hook 脚本 + hooks.json（${ZCODE_PLUGIN_ROOT}；SessionStart 会写 .webnovel/ journal）
    ├── mcp/                  ← webnovel MCP server（stdio 只读查询 ×14）+ tests
    ├── scripts/              ← 统一 CLI webnovel.py + data_modules
    └── references/ templates/ dashboard/ evals/
```

⚠️ 插件本体在内层目录；装机走 marketplace（源=外层仓库根），文件级装卸见
`docs/zcode/zcode-native-adaptation/05-install-reinstall-runbook.md`。

## 当前状态

- 当前版本：v8.0.0（作者主权 + 300 章连贯：六域书仓治理 + MCP 14 只读工具 + 13 条命令；`v8-author` 分支，57 提交领先 master，尚未打 tag / 推送）
- 上游：lingfengQAQ/webnovel-writer（v6.2.1 起分叉；上游 v7/v8 路线与本仓无关）
- 远程：git@github.com:alittleseven/webnovel-writer.git
- ZCode 装机：marketplace `webnovel-writer-marketplace` → 本仓库根（directory 源）
- 当前待办入口：`docs/zcode/v8-gap-review-3rounds/README.md`（41 项缺口 + 4 阶段修复计划）与 `docs/cursor/项目复审/2026-09-04-项目复审报告.md` §9；`docs/plans/2026-08-25-status-and-pending-work.md` 已 superseded，只作历史

## OpenCode 工作区规则：任务状态必须与代码同步

- 本项目的代码、测试结果和 Git 提交记录是状态判断的事实依据；计划、审计和清单文档不能单独证明功能已完成。
- 每个 OpenCode 任务 / todo 必须写清 WHERE、HOW、WHY、EXPECTED RESULT，并在任务开始前核对 `git status`、相关代码和现有测试。
- 文档状态统一使用：`[x]` 已完成且有代码/测试证据，`[~]` 部分完成并注明剩余项，`[ ]` 未完成，`[blocked]` 被明确阻塞，`[superseded]` 被新方案取代。
- 完成代码、修复或迁移后，必须在同一任务中更新对应清单和计划的状态、证据（文件/测试/commit）及剩余工作；不得只改代码不改状态文档。
- 发现文档与代码不一致时，先在当前待办入口（见「当前状态」）登记实际状态，再同步相关文档；历史方案只保留设计背景。方案集（`docs/zcode/<任务名>/`）的 spec 每个 F-项都必须在 plan 里有对应 T-项或显式「不覆盖」声明，宣告「全队列完毕」前先做 F→T 反向对账。
- `[x]` 只能在相关测试或可复现命令通过后标记；未验证的实现只能标为 `[~]` 或 `[ ]`。提交前再次检查文档状态、代码差异和测试结果。
- 不新增未被项目要求支持的状态文件或 `code_state` 字段；使用 OpenCode 原生 todo 状态和 Git/测试证据即可。

## 注意事项

- Windows 下运行 Python 脚本必须加 `-X utf8` 避免 GBK 编码问题
- 中文 commit message 用 UTF-8 文件 + `git commit -F` 方式提交
- `.tmp/` 和 `.tmp_story_system_engine/` 是临时目录，已在 .gitignore 中
- 宿主产出文档按宿主分目录：ZCode 方案集放 `docs/zcode/<任务名>/`，Cursor 产出（审查报告 / 分析 / 计划）放 `docs/cursor/<任务名>/`；跨宿主的正式产出仍按工作区分级归 `docs/{research,reports,plans,decisions}/`
- 修改插件组件（skills/hooks/commands/MCP）后需重启 ZCode 会话生效；改 scripts/*.py 则即时生效（每次调用都是新进程）
