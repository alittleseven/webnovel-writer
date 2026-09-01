# v7 Story-Repo 写路径使用指南

> 适用：v7 story-repo 仓库（`book.yaml` + `定稿/` 结构，见 [story-repo-spec](../architecture/story-repo-spec-2026-06-10.md)）。
> v6 链路（`/webnovel-write` 全流程）不受本页影响；v7 三脚本位于插件 `webnovel-writer/scripts/` 下，是 v6 命令面之外的新入口。

## 一页流程

```
迁移（一次性）          缓存（可随时删）         写一章（每章循环）
migrate_v6_to_v7  →   v7_cache rebuild    →   v7_write decision → pack → (草稿) → check → settle
```

## 1. 迁移：`migrate_v6_to_v7.py`

```bash
python migrate_v6_to_v7.py --project-root <v6书仓> --output <v7仓路径>
```

- 只读源书仓（零写入）；输出目录已存在则拒绝。
- 生成 `book.yaml`、`定稿/`（正文 spec 命名 `NNNN-标题.md` + 中文键 front matter）、`设定/`、`记忆/章摘要/`、`大纲/`、git 初始提交。
- ≥3 章的书自动预填 `context_budget.sections.prev_chapter_tail`（按书史章均字数，clamp 1200–3000）。

## 2. 缓存：`v7_cache.py`

```bash
python v7_cache.py rebuild --repo <v7仓>    # 从源文件全量重建 .cache/index.db
python v7_cache.py verify  --repo <v7仓>    # 删缓存→重建→快照等价（CI 验收项）
python v7_cache.py snapshot --repo <v7仓>   # 打印查询面快照
```

- `.cache/` 是唯一持久派生物，**可随时整目录删除**，下次查询自动重建。
- 查询面：`get_chapter` / `find_entity` / `get_summary`（Python API）。实体来源 = `名册.md` 单表 + `名册/<正名>.md` 目录（同名目录优先）。

## 3. 写一章：`v7_write.py`

```bash
# ① 决策卡（作者界面单位；JSON 字段见下方决策卡节）
python v7_write.py decision --repo <v7仓> --json 决策内容.json
# ② 上下文包（20,000 字符预算；stats 含 truncated_sections / budget_used_ratio）
python v7_write.py pack --repo <v7仓> --chapter 38
# ③ 草稿落 工作区/草稿-NNNN.md（LLM/作者）
# ④ 机检（字数契约 / 占位符 / 标题一致 / 承诺或豁免 / 名册 advisory）
python v7_write.py check --repo <v7仓> --chapter 38 --draft 工作区/草稿-0038.md --json 决策内容.json
# ⑤ 作者验收通过后 settle（原子 git commit：正文+章摘要+名册新实体）
python -c "from v7_write import settle; ..."   # settle 走 Python API
```

要点：

- **机检是硬闸**：下限 = 目标字数×0.75；`check` 退出码 2 = 拒绝 settle。
- **唯一写入路径**：settle 前经 `dual_format_guard` 校验同一章节未在 v6 侧落定（`STORY_REPO_ROOT` 配置）。
- **settle 原子性**：任一步失败自动回滚（定稿零变更），git index 一并清理。
- **名册新实体**：决策卡 `new_entities` 列表 → settle 写 `定稿/设定/名册/<正名>.md` → 重建缓存后可查询。
- **配额按书覆盖**（可选）：`book.yaml` 增 `context_budget:` 节（`total:` 总预算 / `sections:` 节配额），优先级 显式参数 > book.yaml > 内置默认。

## 已知边界（v7.0）

- 承诺结转（spec §5）未实现：机检仅校验「承诺非空或显式豁免」；承诺档案读写排期 v7.1。
- 决策卡 `new_entities` 与缓存的同步依赖 rebuild（首查自动触发）。
