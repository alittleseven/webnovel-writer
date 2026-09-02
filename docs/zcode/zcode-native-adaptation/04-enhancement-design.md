# 04 · ZCode 原生增强方案

> 核心思路：ZCode 相对 Claude Code 多出的「插件 MCP + userConfig + 命令冒号命名 + 模板变量仅插件 MCP 展开」这一组能力，恰好补齐本插件三个长期痛点：
> 1. 模型查询书项目数据要靠 Bash 拼 `webnovel.py` 长命令（易错、无结构化输出契约）；
> 2. 书项目根定位依赖 cwd/指针文件，跨工作区使用不稳；
> 3. 用户入口名长（`/webnovel-writer:webnovel-write`）且依赖 skill 触发纪律。

## 1. MCP server `webnovel`（内层 `mcp/server.py`）

### 1.1 架构

```
ZCode 会话启动
  └─ 自动连接 plugin MCP（清单 mcpServers，模板变量展开）
       └─ python -X utf8 ${ZCODE_PLUGIN_ROOT}/mcp/server.py   ← 纯标准库 stdio JSON-RPC（MCP 协议）
            └─ subprocess: python -X utf8 <plugin>/scripts/webnovel.py <subcommand> --json …
                 └─ 复用既有 data_modules 全部逻辑（adapter 模式，不复制 runtime）
```

- **传输**：MCP stdio = 按行分隔的 JSON-RPC 2.0（newline-delimited），实现 `initialize` / `notifications/initialized` / `tools/list` / `tools/call` / `ping`。
- **依赖**：零第三方依赖（标准库 `json/sys/subprocess/os/pathlib`）——插件用户无需 `pip install`。
- **调用约定**：`subprocess.run([sys.executable, "-X", "utf8", webnovel_py, …], capture_output=True, timeout=25, env=继承)`，解析 stdout JSON；非 JSON 输出按文本透传并标注 exit code。
- **书项目根解析**：每个工具接收可选 `project_root` 参数；缺省时按 `WEBNOVEL_BOOK_ROOT`（来自 userConfig 注入）→ cwd 向上探测（复用 `project_locator` 逻辑，通过 `webnovel.py --project-root` 的解析器完成，server 自身不做二次实现，只透传）。

### 1.2 工具面（9 个，全部只读）

| 工具名 | 底层子命令 | 用途 | 参数 |
|--------|-----------|------|------|
| `webnovel_where` | `where` | 解析并返回当前生效的书项目根（调试/自检） | `project_root?` |
| `webnovel_project_status` | `project-status` | 机器可读项目短状态（阶段、断点、计量） | `project_root?` |
| `webnovel_doctor` | `doctor` | 阶段感知只读体检（目录/文件/JSON/SQLite/RAG） | `project_root?` |
| `webnovel_setting_read` | `setting-read` | 读设定文件原文（L2 按需展开） | `path`（必填）, `project_root?` |
| `webnovel_timeline_check` | `timeline-check` | 卷时间线单调性/倒计时算术校验 | `volume?`, `project_root?` |
| `webnovel_meter` | `meter` | 章级 token 计量（读 ZCode 用量库，含子代理） | `chapter?`, `project_root?` |
| `webnovel_rag_search` | `rag`（search 转发） | 参考资料语义检索 | `query`（必填）, `top_k?`, `project_root?` |
| `webnovel_knowledge` | `knowledge` | 实体/设定知识查询（实体图谱、状态） | `query`（必填）, `project_root?` |
| `webnovel_context_budget` | `context` | 写前上下文预算与组装预览 | `chapter`（必填）, `project_root?` |

**只读红线**：不暴露任何写路径工具（init/commit/update-state 等仍走 skill 编排 + Bash，保留人工审阅语义）。MCP 降低的是「读」的成本，不是「写」的门槛。

### 1.3 清单声明（D3）

```json
"mcpServers": {
  "webnovel": {
    "command": "python",
    "args": ["-X", "utf8", "${ZCODE_PLUGIN_ROOT}/mcp/server.py"],
    "env": {
      "WEBNOVEL_PLUGIN_ROOT": "${ZCODE_PLUGIN_ROOT}",
      "WEBNOVEL_BOOK_ROOT": "${user_config.bookProjectRoot}",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1"
    },
    "timeoutMs": 60000
  }
}
```

- `command: "python"`：与 hooks 同一解释器通道（token-meter hooks 每会话实跑，PATH 已验证可用）。
- `timeoutMs: 60000`：doctor 首次冷跑可能超 30s 默认值。
- 会话内工具名将呈现为 `mcp__webnovel__webnovel_status` 风格（server 名 `webnovel`）。

### 1.4 测试策略（覆盖率红线 80%）

`mcp/tests/test_server.py`：
- 协议层：initialize 握手 → tools/list 返回 9 工具 schema → tools/call 走 mock subprocess（成功 JSON / 非 JSON 文本 / 超时 / 非零退出码四分支）。
- 路由层：每个工具 → 断言拼出的 webnovel.py 子命令与参数。
- 用 `subprocess.run` monkeypatch，不起真进程（真进程冒烟在装机后验证）。

## 2. userConfig：`bookProjectRoot`

```json
"userConfig": {
  "bookProjectRoot": {
    "type": "directory",
    "title": "书项目根目录",
    "description": "当前工作区绑定的书项目路径；留空则按 cwd 向上探测 + 全局指针解析。",
    "required": false
  }
}
```

- GUI 入口：Settings → Plugin Management → webnovel-writer 详情 → Advanced。
- 生效路径：`${user_config.bookProjectRoot}` → MCP env `WEBNOVEL_BOOK_ROOT` → `project_locator` 新增该 env 读取（优先级见 03 §D9）。
- 边界：该值只影响 MCP 查询与脚本默认值；skill 显式 `--project-root` 永远最高优先。

## 3. 斜杠命令 `/webnovel:*`（9 个薄壳）

布局：`commands/webnovel/<name>.md` → ZCode 命令名 `/webnovel:<name>`。

| 命令 | 形态 | 内容要点 |
|------|------|---------|
| `/webnovel:status` | CLI 壳 | 指示运行 `webnovel.py project-status` + 解读要点（含 MCP 工具可用时优先用 `webnovel_project_status`） |
| `/webnovel:doctor` | CLI 壳 | 同上，映射 doctor |
| `/webnovel:query` | skill 壳 | `argument-hint: "<实体/设定/伏笔关键词>"`；指示调用 skill `webnovel-writer:webnovel-query` 并透传参数 |
| `/webnovel:write` | skill 壳 | `argument-hint: "[章号] [--fast\|--minimal]"`；转发 webnovel-write |
| `/webnovel:plan` | skill 壳 | 转发 webnovel-plan |
| `/webnovel:review` | skill 壳 | 转发 webnovel-review |
| `/webnovel:init` | skill 壳 | 转发 webnovel-init |
| `/webnovel:learn` | skill 壳 | 转发 webnovel-learn |
| `/webnovel:dashboard` | skill 壳 | 转发 webnovel-dashboard |

frontmatter 统一：`description`（一句话）+ `argument-hint`（如适用）+ `allowed-tools`（壳命令收敛为 `Bash Skill`）。**命令是薄壳不做业务**：全部业务仍在 skill/CLI，避免双实现漂移。

## 4. init 模板增强：书项目 AGENTS.md

`init_project.py` 生成的书项目骨架新增 `AGENTS.md`（ZCode 工作区指令，每次写作会话自动注入）：
- 内容：硬规则摘要（禁直写运行时文件、正文命名规范、计量 hook 说明）+ 指向项目内 `.webnovel/` 约定文档。
- 实现为模板文件 + init 写入；存量项目可通过 `webnovel.py doctor` 提示补生成（本次仅做新项目生成，不做迁移器——记入未来项）。

## 5. 未来项（本次明确不做，防止范围蔓延）

| 项 | 前置条件 |
|----|---------|
| `PostToolUseFailure` hook 失败观测 | 出现真实的失败可观测痛点 |
| `PermissionRequest` hook 敏感路径闸 | ZCode 权限模型实跑验证后 |
| MCP 写路径工具（proposal/settle 类） | v7 写路径多章实跑稳定后 |
| `pythonCommand` userConfig（自定义解释器） | 验证 `${user_config.*}` 可用于 command 字段 |
| 存量书项目 AGENTS.md 迁移器 | init 模板稳定后 |
