---
description: 书项目只读体检（目录/文件/JSON/SQLite/RAG/Dashboard）
allowed-tools: Bash
---

# /webnovel:doctor

对当前书项目做阶段感知的只读体检。

优先用 MCP 工具 `webnovel_doctor`（若会话中可用）；否则运行：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" doctor --format json
```

$ARGUMENTS 若含 `--deep` 则附加 `--deep`（包含 dashboard 等较深检查）。

输出体检结论：通过项数 / 异常项列表（按 severity 分组），并给出每个 error 的修复建议。不要修改任何文件。
