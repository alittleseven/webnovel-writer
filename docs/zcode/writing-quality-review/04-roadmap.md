# 04 · 实施路线图（W1-W10 串行队列）

> 对齐项目既有「单线执行队列」模式：严格串行，一步一验证，不并行铺开。每步含改动面、验收命令、预计触碰文件。执行前须按项目惯例出各步 spec 增补；本路线图只锁定顺序与范围。
> 依赖关系：W1→W2→W4 有数据依赖（R4 消费 R2 的维度与 R1 的 section 框架）；其余按价值排序。

## 队列

### W1 · 上下文连续性包（R1 + R10 + R5）
- 改动：`load-context` 新增 `prev_chapter_tail`（默认 1600 字，不可 DROP）；recent_summaries 截断方向改「新章优先」；DROP_ORDER 把 author_style_patterns/style_contract 提入永不丢弃集合；饱和策略改为按比例压缩 memory_pack 子层。
- 验收：饱和压力测试（合同+记忆全满构造）断言三段保全；`python -m pytest scripts/data_modules/tests/test_context_budget.py test_memory_contract_adapter.py`；真实书项目 `memory-contract load-context --chapter N` 输出含原文尾段。
- 预计触碰：`context_budget.py`、`memory_contract_adapter.py`、`context_manager.py`（对齐）、两处测试文件。

### W2 · 文笔度量两件套（R2）
- 改动：新 `scripts/prose_check.py`（词库数据化：polish-guide 十四类词表抽成 `references/csv/anti-ai-lexicon.csv`；检测项：高频词命中/长句比例/said tag 占比/同句式连击/解释段长度/段落方差）；reviewer 增第 6 维 prose（category 产出集加入 ai_flavor）；Step 4 契约改为附 prose_check 结果；review-pipeline 激活 ai_flavor→anti_patterns.json 既有回流。
- 验收：构造含已知套话的样章，prose_check 报出位置与计数；reviewer 六维输出；`run_behavior_evals.py` 更新对应断言全绿。
- 预计触碰：新脚本+词库 CSV、`reviewer.md`、`webnovel-write/SKILL.md`、`review_schema.py`（若需扩枚举说明）、行为评测 fixture。

### W3 · 多稿迭代（R3）
- 改动：`/webnovel-write --drafts N`（默认 2）；新 `references/draft-rubric.md`（6 项 rubric）；择优与定向重写一次的流程段；`draft_evaluations` 落库。
- 验收：`--drafts 2` 真书实跑一章，产出两稿+择优记录+落库行；`--fast/--minimal` 行为不变（回归）。
- 预计触碰：`webnovel-write/SKILL.md`、新 rubric 文件、`index_manager.py`（表）。

### W4 · 反馈断源闭合（R4，依赖 W1/W2）
- 改动：chapter-commit 投影链新增 reading_power 投影（从 data-agent front matter + 合同兑现数据）；`load-context` 新增 `reader_signal` section（追读力/钩子分布/爽点统计/审查趋势，各 ≤400 字）；`get-reader-signals` 补 review_trend；context-agent 第 4 段消费说明更新。
- 验收：写一章后 `chapter_reading_power` 自动有记录；连续同型钩子两章后第三章任务书出现差异化提醒；checklist_score 无恒 False 项。
- 预计触碰：投影路由/`index_projection_writer.py`、`index_reading_mixin.py`、`memory_contract_adapter.py`、`context-agent.md`。

### W5 · 文风锚点与孤儿接线（R6 + R7 + R8）
- 改动：高分章投影自动 style extract + `style_anchor` section 注入；naming-and-voice-gaps/golden-finger-templates/desire-description 三孤儿接线；write CSV 触发条件 5→9；loading-map 同步登记。
- 验收：三章后新章上下文含本书高分样本；触发场景可见对应内容；loading-map 对账零漂移（暂以 R15 脚本或人工核对）。
- 预计触碰：`style_sampler.py` 接线、`context-agent.md`、`webnovel-init/SKILL.md`、`webnovel-write/SKILL.md`、`reference-loading-map.md`。

### W6 · 学习闭环升级（R9）
- 改动：pattern 结构化（evidence_excerpt/metrics_snapshot）；高分章自动候选 pattern；近重复合并；注入 10→20；学习有效性对比报告。
- 验收：`/webnovel-review` 高分章后收到候选建议；注入扩容生效；报告可生成。
- 预计触碰：`project_memory.py`、`webnovel-learn/SKILL.md`、`memory_contract_adapter.py`、新报告脚本。

### W7 · 机检加强与字数口径（R12）
- 改动：v7 上限告警/承诺推进存在性检查/占位符正则扩展/字数口径统一/机检回退对齐书史；v6 write-gate 同源上限告警。
- 验收：v7_write 单测新增四分支；超长与空承诺样文被报出。
- 预计触碰：`v7_write.py`、`prewrite_validator.py`、相关测试。

### W8 · 排序信号升级（R13）
- 改动：orchestrator 语义过滤改实体+关键词组重合度；删 `_length_score`；主路径引入排序。
- 验收：代称召回对比测试；长而空 vs 短而实排序断言。
- 预计触碰：`memory/orchestrator.py`、`context_ranker.py`、测试。

### W9 · 技法盲区与结构补齐（R11 + R14）
- 改动：幽默/POV/修辞/亲密戏/商业文案五类条目与共享 md；系统流/都市异能模板补厚；CSV 分类收敛。
- 验收：`validate_csv.py` 0 错；检索命中抽测；模板行数达标。
- 预计触碰：CSV×N、`shared/`、`templates/genres/`。

### W10 · 卫生收尾（R15 + R16 + R17 + R18）
- 改动：引用接线对账脚本并入发版校验；methodology 节拍接卷纲；trend 报告接入 `/webnovel:status`；死旋钮实现或删除（倾向实现场景类型感知组装）。
- 验收：对账脚本报出并清零既有 22 项漂移；策略卡与卷纲一致；`/webnovel:status` 含趋势行。
- 预计触碰：新校验脚本、`writing_guidance_builder.py`、`commands/webnovel/status.md`、`context_weights.py`。

## 排期建议与风险

- **首月聚焦 W1-W4**（P0 全量）：这四步完成后，「写得好」才第一次拥有与「不写崩」对等的基础设施（连续性输入 + 度量 + 迭代 + 反馈）。
- **W3 的默认档位**需要作者决策：`--drafts 2` 作为默认会翻倍起草成本——本任务准绳是不考虑 token，但落地时建议 book.yaml 可配 `write.drafts`，作者按书选择。
- **W2 的 rubric 校准**依赖 W3 落库数据（rubric 分 vs 审查分相关性），首轮先人工复盘，数据够后再调权重。
- 每步完成后在本文档勾选并回写证据；发现顺序需要调整时在 [任务 README](README.md) 登记变更理由。
