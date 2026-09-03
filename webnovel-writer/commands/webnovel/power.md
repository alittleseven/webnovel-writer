---
description: 战力校验（跨阶依据/境界链矛盾/通胀曲线，A2）
allowed-tools: Bash
---

# /webnovel:power

优先用 MCP 工具 `webnovel_power_check`；否则：

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" power check --chapter {N} --format json
```

$ARGUMENTS 可含锚点管理动作：`extract --apply`（从力量体系.md 抽锚点，作者确认落盘）、`validate`（境界链校验）、`battle`（战例登记）、`inflate`（通胀记录）。

输出：high（越级无依据/依据不完备/无预告/境界链矛盾）逐条列出并给修复方向；medium 通胀提示单列。不要修改任何文件（战例登记除外，属作者确认动作）。
