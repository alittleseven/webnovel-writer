# Ledger · zcode-native-adaptation 执行账本

> 格式：每条 Ruling 记录「决定 — 理由 — 错了的代价」；每步完成回写证据。与 [plan](2026-09-03-zcode-native-adaptation-plan.md) 的 S 编号对应。

## Ruling 记录

| # | 日期 | S | 决定 | 理由 | 错了的代价 |
|---|------|---|------|------|-----------|
| R1 | 2026-09-03 | — | 方案文档集先行提交在 master（10db9f9），再拉 tmp/zcode 实施 | Human 指令顺序（文档→计划→分支→实施）；方案属仓库资产应在两分支可见 | 若顺序颠倒，master 缺审计文档 |
| R2 | 2026-09-03 | S8 | MCP server 用 `sys.executable` 而非 `python` 启动子进程 | server 本身由 python 启动，`sys.executable` 保证解释器一致（uv/venv 环境也成立） | 极端场景解释器不一致 → 查询失败，可退回 `"python"` |
| R3 | 2026-09-03 | S14 | 缓存目录 `6.5.0` 改名 `.bak` 后**改回原名**，保留为惰性回滚产物 | 改名瞬间打断了运行中会话的 PreToolUse hook（退出码 2=阻断），所有 Bash/Write/Edit 被拒；经桌面终端 `mv` 恢复 | 若不恢复：本会话无法继续任何写操作；教训已写入 runbook §4.5 |
| R4 | 2026-09-03 | S12 | `test_hooks.py` 断言随 hooks.json 变量名同步更新为 `${ZCODE_PLUGIN_ROOT}` | 断言的意图是「无本地绝对路径泄漏 + 用插件根模板变量」，变量名本身随宿主演进 | 无——意图保留，仅换合法变量名 |
| R5 | 2026-09-03 | S5 | 指针/registry/`.env` 默认目录改为「`~/.zcode` 有数据则优先，否则 `~/.claude`」 | 兼容既有数据（本机 registry 在 `~/.claude`）同时让 ZCode 新用户落 `~/.zcode` | 若默认硬切 `~/.zcode`：既有绑定静默丢失 |

## 步骤证据

| S | 状态 | 证据（命令/结果/commit） |
|---|------|------------------------|
| S1 | [x] | `tmp/zcode` 自 master 10db9f9 拉出，`git branch --show-current`=tmp/zcode |
| S2 | [x] | `.zcode-plugin/plugin.json`（7.1.0，组件+mcpServers+userConfig）；`.claude-plugin/` 已删；validate 仅报 README 版本差（预期，S11 消除） |
| S3 | [x] | 根 `marketplace.json` + `.claude-plugin/marketplace.json` 镜像，均 7.1.0 |
| S4 | [x] | 四脚本双探测 + 测试 13 用例绿（test_validate_plugin_package ×9 + release_notes ×5，其中新增 zcode 布局 ×4） |
| S5 | [x] | hooks.json 5 处 `${ZCODE_PLUGIN_ROOT}`；locator/config 双名；`WEBNOVEL_BOOK_ROOT` 接入；test_project_locator 8 用例绿；preflight 无书项目时干净报错 |
| S6 | [x] | run_tests.ps1 路径修复，smoke 33 用例通过，退出码 0 |
| S7 | [x] | skills/agents/templates/references 的 claude 命中清零（env 变量名除外）；内层 README 安装章节 ZCode 化 |
| S8 | [x] | `mcp/server.py`（~430 行）+ 26 测试绿；装机路径实跑 tools/list=9 |
| S9 | [x] | manifest env 增 `WEBNOVEL_PROJECT_DIR`；README userConfig 章节落位 |
| S10 | [x] | `commands/webnovel/` 9 文件（status/doctor/query/write/plan/review/init/learn/dashboard） |
| S11 | [x] | sync --check「in sync: 7.1.0」；validate_plugin_package 0 错 0 警；validate_release_notes OK；README 徽章/安装/命令表 + CHANGELOG + AGENTS.md + releases/v7.1.0.md |
| S12 | [x] | 全量 `python -X utf8 -m pytest`：**1142 passed / cov 81.82%（≥80）**；行为评测 **22 PASS / 0 FAIL** |
| S13 | [x] | 5 个逻辑提交：de623de（清单迁移）/ 30fd4fd（env 原生化）/ 2fb7d3e（措辞）/ ab17ef8（MCP+commands）/ 2accfde（发版文档） |
| S14 | [x] | 三 JSON 备份 `.bak-zcode-adaptation`；enabledPlugins/installed 条目移除；6.5.0 改名后因 R3 教训**改回原名保留**；6.2.1→6.2.1.bak |
| S15 | [x] | known_marketplaces source.path→新仓库；marketplaces 克隆整替换（旧克隆留 `.old`）；cache 7.1.0 落位（排除 .git/__pycache__ 等）；installed 登记 7.1.0（新 UUID）+ 重新启用；装机副本 preflight/MCP 冒烟通过 |
| S16 | [x] | 本账本回写；runbook §4.5 教训；主仓库子模块指针提交；check-workspace 自检 |

## 最终状态

- 分支：tmp/zcode @ <见下方收尾提交>
- 版本：v7.1.0（manifest/marketplace×2/README 三处同步，sync --check 通过）
- 装机：v7.1.0 @ `C:\Users\a6748\.zcode\cli\plugins\cache\webnovel-writer-marketplace\webnovel-writer\7.1.0`，enabledPlugins=true
- 回滚产物：cache 6.5.0（原名保留）、6.2.1.bak、marketplaces/…old、三 JSON `.bak-zcode-adaptation` 备份
- 重启验证：**待 Human 重启 ZCode 后按 [05 runbook §4](05-install-reinstall-runbook.md) 7 项清单确认**（8 skills/4 agents/9 commands/webnovel MCP connected/hooks 注入与阻断/userConfig 字段/CLI 冒烟）
