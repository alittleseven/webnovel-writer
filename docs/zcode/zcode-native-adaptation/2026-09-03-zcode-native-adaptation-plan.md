# 实施计划 · webnovel-writer ZCode 原生化改造（16 步串行队列）

> Spec 指针：[2026-09-03-zcode-native-adaptation-spec.md](2026-09-03-zcode-native-adaptation-spec.md)
> 执行方式：**严格串行，不并行**；每步完成即勾选 `[x]` 并附验证证据（命令+结果）到 [ledger](2026-09-03-zcode-native-adaptation-ledger.md)；任一步验证失败先修复或回写 Ruling，不得跳步。
>
> **全局约束**
> - 工作目录：外层仓库根 `C:\lgq\ai-workspace\projects\zcode-plugins\webnovel-writer`；分支 `tmp/zcode`。
> - Python 一律 `python -X utf8`（Windows GBK 红线）；中文 commit 用 UTF-8 文件 + `git commit -F`。
> - 提交纪律：一个逻辑改动一个 commit（commit-discipline 技能）；只 stage 本任务文件。
> - 回归基线：根 `pytest.ini`（testpaths=data_modules/tests + scripts/tests，`--cov-fail-under=80`）。
> - 只读红线：MCP 工具面全部只读；薄壳红线：commands/MCP 不含业务逻辑。

---

## Phase A · 分支与清单迁移

### S1 · 创建 `tmp/zcode` 分支
- [ ] `git checkout -b tmp/zcode`（自 master@6a335ec；方案文档集已先行提交在 master）
- 验证：`git branch --show-current` = `tmp/zcode`；`git status` 干净。

### S2 · 内层清单迁移 `.zcode-plugin/plugin.json`
- [ ] 新建 `webnovel-writer/.zcode-plugin/plugin.json`：name=webnovel-writer、version=7.1.0、description、author、license=GPL-3.0、keywords=[webnovel,zcode,skills,agents,mcp,rag]、组件声明 `skills/skills、hooks/hooks、agents/agents、commands/commands`、`mcpServers`（04 §1.3 定义）、`userConfig`（04 §2 定义）
- [ ] 删除 `webnovel-writer/.claude-plugin/` 目录
- 验证：`python -X utf8 webnovel-writer/scripts/validate_plugin_package.py`（此时预期因 marketplace 版本未同步而报版本不一致——若报清单缺失/结构错误则为失败）。

### S3 · 外层 marketplace.json 双位置 + 版本 7.1.0
- [ ] 新建根 `marketplace.json`（name=webnovel-writer-marketplace 不变、plugin version=7.1.0、description 改 ZCode 措辞、source="./webnovel-writer"）
- [ ] 更新 `.claude-plugin/marketplace.json` 为同内容镜像
- 验证：`python -X utf8 webnovel-writer/scripts/sync_plugin_version.py --check`（或等价只读校验；若该脚本无 --check 则运行写入模式后 `git diff` 确认三处一致）。

### S4 · 发版脚本双布局探测 + 测试更新
- [ ] `sync_plugin_version.py`：PLUGIN_JSON_PATH 探测 `.zcode-plugin`→`.claude-plugin`；MARKETPLACE 双位置读写（以根为准、镜像 `.claude-plugin/`）
- [ ] `validate_plugin_package.py`：`_is_plugin_root`/`_plugin_root`/`_repo_root`/manifest 校验目标全部改双探测；校验目标 glob 覆盖 `.zcode-plugin`
- [ ] `validate_release_notes.py`：plugin.json 路径改双探测
- [ ] `run_behavior_evals.py`：插件根探测改双探测
- [ ] 测试：`scripts/tests/test_validate_plugin_package.py` 增 `.zcode-plugin` 布局用例（含组件字段校验）；`test_validate_release_notes.py` 同步
- 验证：`python -X utf8 -m pytest webnovel-writer/scripts/tests -q --no-cov`（目标子集全绿）+ S2/S3 的两个验证命令重跑通过。

## Phase B · 运行时适配

### S5 · 环境变量原生化（hooks + 定位器）
- [ ] `hooks/hooks.json`：4 处 `${CLAUDE_PLUGIN_ROOT}` → `${ZCODE_PLUGIN_ROOT}`（`${CLAUDE_SESSION_ID}` 保留）
- [ ] `hooks/session_start.py`：`ZCODE_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT`、`ZCODE_PROJECT_DIR or CLAUDE_PROJECT_DIR`
- [ ] `scripts/project_locator.py`：`ENV_CLAUDE_PROJECT_DIR` 各读取点改 `ZCODE_PROJECT_DIR` 优先（常量与调用点同步，`allow_last_used` 判定同改）；`CLAUDE_HOME` 探测加 `WEBNOVEL_ZCODE_HOME`/`ZCODE_HOME` 优先
- [ ] `scripts/data_modules/config.py`：同上 HOME 探测双名
- [ ] 新增 `WEBNOVEL_BOOK_ROOT` 支持（`project_locator` 环境提示链：显式参数 > `WEBNOVEL_BOOK_ROOT` > `ZCODE/CLAUDE_PROJECT_DIR` > cwd 向上）
- [ ] 测试：`test_project_locator.py` 补 ZCODE_PROJECT_DIR / WEBNOVEL_BOOK_ROOT 用例
- 验证：`python -X utf8 -m pytest webnovel-writer/scripts/data_modules/tests/test_project_locator.py -q --no-cov`；`python -X utf8 webnovel-writer/scripts/webnovel.py preflight`（无书项目环境下应正常报「未找到项目」类输出而非 traceback）。

### S6 · 修复 `run_tests.ps1` 陈旧路径
- [ ] `.claude/scripts/…` → `webnovel-writer/scripts/…`（PYTHONPATH、smoke、full 三处）
- 验证：`powershell -File webnovel-writer/scripts/run_tests.ps1 -Mode smoke` 退出码 0。

### S7 · Claude 措辞清理（skills/agents/模板/内层 README）
- [ ] 8 个 SKILL.md：`/reload-plugins`→重启会话说明、宿主称谓、`claude --plugin-dir` 类指引改 ZCode 安装指引（指向 05 runbook / marketplace 安装）
- [ ] 4 个 agents md + templates/output/index-schema.md：称谓清理（如有）
- [ ] 内层 `README.md`：安装/使用章节改 ZCode 流程
- 红线：不改历史文档（docs/decisions、docs/reports、releases/、CHANGELOG 正文——CHANGELOG 仅追加 7.1.0 条目于 S11）
- 验证：`grep -rn "reload-plugins\|--plugin-dir" webnovel-writer/skills webnovel-writer/agents webnovel-writer/templates` 无命中；`grep -rni "claude" webnovel-writer/skills webnovel-writer/agents webnovel-writer/templates` 命中数归零或仅剩 env 回退注释。

## Phase C · ZCode 原生增强

### S8 · MCP server `mcp/server.py` + 测试
- [ ] 新建 `webnovel-writer/mcp/server.py`：newline-delimited JSON-RPC 2.0 stdio；实现 initialize/notifications-initialized/tools/list/tools/call/ping；9 工具路由（04 §1.2 表）；subprocess 调 `scripts/webnovel.py`（`sys.executable -X utf8`，timeout=25s，capture+解析 JSON 或文本透传）
- [ ] 新建 `webnovel-writer/mcp/__init__.py`、`webnovel-writer/mcp/tests/test_server.py`：协议握手、tools/list 数量与 schema 键、每工具参数→子命令映射、4 个失败分支（非 JSON/超时/非零退出/未知工具）
- [ ] `pytest.ini` testpaths 增 `webnovel-writer/mcp/tests`（如需）；确认 cov 覆盖计入
- 验证：`python -X utf8 -m pytest webnovel-writer/mcp/tests -q --no-cov` 全绿；手工冒烟：`echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python -X utf8 webnovel-writer/mcp/server.py` 返回合法 initialize 响应。

### S9 · userConfig 联动收尾
- [ ] 确认 S2 清单 userConfig 字段与 S5 `WEBNOVEL_BOOK_ROOT` 链路闭合（MCP env 注入名一致）
- [ ] 内层 README 增 userConfig 配置说明（GUI 路径 + 留空行为）
- 验证：`python -X utf8 -c "import json;json.load(open('webnovel-writer/.zcode-plugin/plugin.json',encoding='utf-8'))['userConfig']['bookProjectRoot']['type']=='directory'"` 输出 True；文档段落存在。

### S10 · `/webnovel:*` 9 个命令薄壳
- [ ] 新建 `webnovel-writer/commands/webnovel/{status,doctor,query,write,plan,review,init,learn,dashboard}.md`（04 §3 表；frontmatter：description + argument-hint（如适用）+ allowed-tools）
- 验证：`ls webnovel-writer/commands/webnovel | wc -l` = 9；每文件 frontmatter 可被 `python -X utf8` 简单解析（无 YAML 语法错误）。

## Phase D · 文档、发版与全量回归

### S11 · 仓库级文档 + 发版说明
- [ ] 根 `AGENTS.md`：技术栈（ZCode Plugin）、常用命令（pytest/validate/marketplace 装机指针）、目录结构（`.zcode-plugin`、`mcp/`、`commands/`）、当前状态刷新
- [ ] 根 `README.md`：版本表加 7.1.0 行（`(当前)` 标记迁移）、安装章节改 ZCode、badge 版本同步
- [ ] `CHANGELOG.md` 追加 7.1.0 条目
- [ ] 新建 `releases/v7.1.0.md`（ZCode 原生化 + MCP + commands + userContext 要点 + 升级/装机指引）
- [ ] `sync_plugin_version.py` 写入模式跑一遍，`git diff` 确认无意外漂移
- 验证：`python -X utf8 webnovel-writer/scripts/validate_release_notes.py` 通过；`sync_plugin_version --check`（或写入后 diff 为空）。

### S12 · 全量回归 + 打包校验
- [ ] `python -X utf8 -m pytest`（根 pytest.ini 全量，含 cov≥80）
- [ ] `python -X utf8 webnovel-writer/scripts/validate_plugin_package.py`
- [ ] `python -X utf8 webnovel-writer/scripts/run_behavior_evals.py`（如需书项目 fixture，按其 README/默认 fixture 跑）
- 验证：三条命令退出码 0。

### S13 · 分支提交整理
- [ ] 按逻辑分组提交（清单迁移 / 运行时适配 / 措辞 / MCP / commands / 文档发版），UTF-8 文件 + `git commit -F`
- 验证：`git log --oneline tmp/zcode ^master` 条目清晰；`git status` 干净。

## Phase E · 装机（按 [05 Runbook](05-install-reinstall-runbook.md) 执行）

### S14 · 卸载旧插件（6.5.0 缓存改名留存）
- [ ] 备份三个 JSON → 删 enabledPlugins 键 → 删 installed_plugins 条目 → `cache/…/6.5.0` 改名 `6.5.0.bak`、`6.2.1` 改名 `6.2.1.bak`
- 验证：JSON 可解析、键已移除。

### S15 · marketplace 换源 + 落 7.1.0 装机产物
- [ ] known_marketplaces source.path → 新路径；marketplaces 克隆整目录替换为新仓库 HEAD 副本
- [ ] 建 `cache/…/7.1.0/`，复制插件本体（排除 .git/__pycache__/*.pyc/.pytest_cache）
- [ ] installed_plugins.json 新条目（7.1.0、新 UUID）；enabledPlugins 置 true
- 验证：`python -X utf8 <cache>/…/7.1.0/scripts/webnovel.py preflight` 行为正常；三 JSON 解析通过。

### S16 · 收尾：验证清单交付 + 指针同步 + 工作区自检
- [ ] 产出「重启后验证清单」交付给 Human（05 §4 的 7 项，含 MCP/命令/hooks 检查点）
- [ ] ledger 回写全部 Ruling 与最终状态；plan 全部勾选
- [ ] 插件仓库最终 commit（如 S13 后有文档回写）；主仓库同步子模块指针 commit
- [ ] 工作区根运行 `tools/scripts/check-workspace.ps1`
- 验证：check-workspace 无未提交项；ledger 无未闭环 Ruling。

---

## 风险登记

| 风险 | 缓解 |
|------|------|
| ZCode directory 源不认根 `marketplace.json` | D1 双位置镜像已消除；05 走文件级装卸不依赖 UI 刷新 |
| MCP `command:"python"` PATH 不含 python | token-meter hooks 同通道每会话实跑（本机已验证）；失败则 runbook 记录改绝对解释器路径的修复步骤 |
| `${user_config.bookProjectRoot}` 展开为空串 | server/env 侧把空串视为未设置（`or None`），回落 cwd 探测 |
| cov<80 红线被新模块拖低 | S8 测试与实现同步写；mcp 模块行数控制在可覆盖范围 |
| hooks.json 改 `ZCODE_PLUGIN_ROOT` 后不展开 | ZCode 官方双名支持（diagnosing-hooks §2）；装机后验证清单 #4 兜底 |
