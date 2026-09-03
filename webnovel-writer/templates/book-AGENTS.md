# 本书项目写作约定（AGENTS.md 模板）

> 本文件由 `webnovel.py domains init` 生成（已存在则永不覆盖）。适用于所有在本目录工作的 AI 会话。

## 书仓即正典

- 本目录是一个独立 git 仓库，**文件 + git 历史是唯一真源**；`.story-system/`、`.webnovel/`、`.cache/` 都是编译产物，可删可重建。
- 任何结构化状态以文件为准：大纲/条目/素材/设定/正文/作者域，全部纯文本，可直接手改。

## 作者主权三句话

1. **你（作者）改任何文件立即生效**，没有门禁；改动会在下次 `author-sync` 时进 journal 留账。
2. **AI 的一切结构性写入都是提案**：进 `regen/` 画廊或工作区，经你采纳（adopt/confirm/settle）才成正典。
3. **冻结不是锁**：卷收尾 freeze 做快照；之后改定版内容会得到「影响清单 + 三选项裁决」。

## 六域速览

| 域 | 你日常碰 | 说明 |
|----|---------|------|
| 大纲/ | 总纲、卷纲、章纲、条目 | 条目=承诺账本（伏笔F/悬念S/感情线R），挂最晚回收章 |
| 素材/ | 活/*.csv | 十张表，直接编辑即生效；AI 归纳与拆书先进 `素材/regen/` 画廊 |
| 设定/ | 世界观、力量体系、名册、信息差、力量锚点.yaml | 力量锚点由 `power extract --apply` 半自动生成 |
| 定稿/正文/ | （AI 写、你可改） | 改动走 journal + 影响分析 |
| 文风/ | 宪法.md、金句库.md、指纹.yaml | 金句库是你标记的高分片段，可自喂进素材 |
| 作者/ | journal、author_model、跨书偏好 | author_model 由卷级 `learn` 归纳、你确认后生效 |

## 常用命令

```bash
python -X utf8 "<插件>/scripts/webnovel.py" --project-root . author-sync     # 会话开始：作者修改留账
python -X utf8 "<插件>/scripts/webnovel.py" --project-root . doctor          # 只读体检
python -X utf8 "<插件>/scripts/webnovel.py" --project-root . foreshadow-scan scan --chapter {N}
python -X utf8 "<插件>/scripts/webnovel.py" --project-root . power check --chapter {N}
python -X utf8 "<插件>/scripts/webnovel.py" --project-root . freeze freeze --volume {N}   # 卷收尾
```

更多入口见插件 README 与 `/webnovel:*` 命令。
