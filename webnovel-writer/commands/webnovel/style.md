---
description: 文风域（宪法迁移/指纹/金句库，M3）
allowed-tools: Bash, Read
---

# /webnovel:style

```bash
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" style-domain migrate
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" style-domain fingerprint [--chapter {N}]
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" style-domain golden-add --chapter {N} --text "{金句}"
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" style-domain golden-feed --id {G-NNN}
python -X utf8 "<ZCODE_PLUGIN_ROOT>/scripts/webnovel.py" learn --from-journal --volume {N}
```

$ARGUMENTS 按动词路由。指纹与 style_anchor 已自动进入写前上下文（M3/T17）；金句 feed 后进入台词金句素材表（作者手写来源）。
