---
description: 设定工坊（境界/功法/法宝/命名 四生成器，提案模式）
allowed-tools: Bash, Read, Write
---

# /webnovel:forge

四类生成器走提案模式：装配 → 5 组概念提案 → 画廊 → 作者采纳 → 草案 → 确认登记。

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" forge prepare --category {境界|功法|法宝|命名}
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" forge save --category {类} --file {提案.md}
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" forge adopt --category {类} --version {N} --proposal {K}
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" forge confirm --category {类} --draft {草案.md}
```

红线：不生成战力数值；境界/功法类提案必须带「灵魂设定——建议作者自拟，工坊仅给反差参考」；LLM 只提议、作者只确认。
