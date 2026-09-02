---
description: 书项目短状态（阶段、断点、计量）
allowed-tools: Bash
---

# /webnovel:status

输出当前书项目的机器可读短状态。

优先用 MCP 工具 `webnovel_project_status`（若会话中可用）；否则运行：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" project-status --format json
```

对输出做一句话解读：当前阶段、最近断点、计量是否闭合。不要修改任何文件。
