# webnovel-writer — 项目约定

> 继承全局 AGENTS.md 和工作区 AGENTS.md，以下规则优先。

## 技术栈

- Python 3.10+ / pytest
- Claude Code Plugin（skills + agents + hooks + scripts）
- Dashboard 前端：预打包 dist/，不需要 npm build

## 常用命令

```powershell
# 运行测试
python -m pytest

# 本地加载插件到 Claude Code 测试
claude --plugin-dir "C:\lgq\ai-workspace\projects\claude-plugins\webnovel-writer\webnovel-writer"

# CLI 预检（替换 <book-root> 为实际书项目路径）
python -X utf8 scripts/webnovel.py --project-root "<book-root>" preflight
```

## 目录结构

```
webnovel-writer/              ← 外层仓库根（marketplace 清单）
└── webnovel-writer/          ← 内层插件本体（skills/agents/hooks/scripts）
    ├── .claude-plugin/
    ├── skills/
    ├── agents/
    ├── hooks/
    └── scripts/
```

⚠️ 插件本体在内层目录，`--plugin-dir` 指向内层。

## 当前状态

- 主开发分支：v6.3.0（原 fix/temp，2026-08-30 定名；下一步开发在 v7-tmp）
- 上游：lingfengQAQ/webnovel-writer v6.2.1
- 本地改造版本：v6.3.0（本地已 tag，待作者确认后推送发布）
- 远程：git@github.com:alittleseven/webnovel-writer.git

## OpenCode 工作区规则：任务状态必须与代码同步

- 本项目的代码、测试结果和 Git 提交记录是状态判断的事实依据；计划、审计和清单文档不能单独证明功能已完成。
- 每个 OpenCode 任务 / todo 必须写清 WHERE、HOW、WHY、EXPECTED RESULT，并在任务开始前核对 `git status`、相关代码和现有测试。
- 文档状态统一使用：`[x]` 已完成且有代码/测试证据，`[~]` 部分完成并注明剩余项，`[ ]` 未完成，`[blocked]` 被明确阻塞，`[superseded]` 被新方案取代。
- 完成代码、修复或迁移后，必须在同一任务中更新对应清单和计划的状态、证据（文件/测试/commit）及剩余工作；不得只改代码不改状态文档。
- 发现文档与代码不一致时，先在 `docs/plans/2026-08-25-status-and-pending-work.md` 登记实际状态，再同步相关文档；该清单是当前待办的唯一入口，历史方案只保留设计背景。
- `[x]` 只能在相关测试或可复现命令通过后标记；未验证的实现只能标为 `[~]` 或 `[ ]`。提交前再次检查文档状态、代码差异和测试结果。
- 不新增未被项目要求支持的状态文件或 `code_state` 字段；使用 OpenCode 原生 todo 状态和 Git/测试证据即可。

## 注意事项

- Windows 下运行 Python 脚本必须加 `-X utf8` 避免 GBK 编码问题
- 中文 commit message 用 UTF-8 文件 + `git commit -F` 方式提交
- `.tmp/` 和 `.tmp_story_system_engine/` 是临时目录，已在 .gitignore 中
- 修改 scripts/*.py 后可用 `/reload-plugins` 热重载，无需重启 Claude Code
