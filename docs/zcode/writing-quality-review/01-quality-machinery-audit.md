# 01 · 质量机制盘点：六章成稿质量是怎么被（不）保障的

> 路径约定：`skills/`、`agents/`、`scripts/`、`references/` 均指 `webnovel-writer/` 内层插件目录下；`DM` = `scripts/data_modules/`。

## 0. 写作主链全景（v6 `/webnovel-write`）

```
预检 preflight --all
  → 刷新合同树 story-system + write-gate(prewrite)
  → Step 1  context-agent：load-context 基础包 → 五段写作任务书
  → Step 2  主流程按需 CSV 检索（5 个触发条件）→ 只根据任务书起草
  → Step 3  reviewer：5 维事实审查（一轮）→ review-pipeline 落库
  → Step 4  润色：修 issue → 风格适配 → 排版 → Anti-AI 终检（自报）
  → Step 5  data-agent 提取三份 artifact → precommit gate → chapter-commit → 五投影
  → Step 6  备份 + user-report + meter stop
```

质量相关的六个子系统逐一盘点如下。

## 1. 起草输入（决定成稿质量上限的子系统）

**机制**：context-agent（`agents/context-agent.md`）以 `memory-contract load-context` 为主入口（:24），基础包含 11 个 section（contracts / runtime_status / memory_pack / outline / recent_summaries / protagonist / progress / active_rules / urgent_loops / genre_profile_excerpt / author_style_patterns / style_contract），总预算 20000 字符（`DM/context_budget.py:16-29`），压缩为五段自然语言任务书（开篇委托 / 这章的故事 / 这章的人物 / 怎么写更顺 / 收在哪里）。

**强**：数据权重明确（用户要求 > 章纲 > MASTER_SETTING > reasoning > CHAPTER_COMMIT > CSV）；任务书「不暴露系统术语」的翻译层设计好；设定 L0/L2 分层按需展开；伏笔按紧急度输出。

**弱**：
- 起草模型**看不到上一章原文**——recent_summaries 每章仅 500 字（`DM/memory_contract_adapter.py:204-207`），latest_commit 收缩为 300 字摘要（`DM/context_budget.py:131-145`）。铁律要求「上章有钩子本章必须回应」（`agents/context-agent.md:56`），但模型手里只有二手摘要。v7 管线的 `prev_chapter_tail`（定稿正文尾段 1200 字，`scripts/v7_write.py:33,168-172`）已解决此问题，却未接入 v6 主链。
- **上下文预算工程以牺牲文风为代价**：12 个 section 配额合计 30200 > 总预算 20000，饱和时按 DROP_ORDER 依次丢——`memory_pack.episodic` 之后第 2 个被丢的就是 `author_style_patterns`（`DM/context_budget.py:51-63`），成熟书项目（合同+记忆饱满）会系统性丢失文风修正层、题材切片、主角卡、近章摘要。
- StyleSampler（高分章原文样本回注，`DM/style_sampler.py:250-272`）**完全未接线**——CLI 存在但无任何 skill/agent/load-context 调用。
- 双路径语义不一致：主路径与降级路径（`DM/context_manager.py`）对同一数据的行为不同（风格契约 2000 字 vs L0 摘要 240 字；project_memory 精选 top10 vs 整包注入）。
- 摘要截断方向错误：ch-2 先插入、ch-1 后插入，配额超限时**紧邻上一章的摘要反而先被截**（`DM/context_budget.py:92-114` 的 insertion-order 处理）。
- 排序信号弱：相关性 = recency×0.7 + frequency×0.3 + 关键字 bonus（`DM/context_ranker.py:238-265`），无语义/实体信号；`_length_score` 按摘要长度给分（:257-262）——**奖励冗长而非信息密度**；主路径 adapter 甚至完全不排序。

## 2. 事实一致性审查（当前最強的子系统）

**机制**：reviewer agent 只查 5 维（setting/timeline/continuity/character/logic），只报可验证问题、必须有 evidence、不评分不评价文笔（`agents/reviewer.md:11-17,76-82`）；review-pipeline 罚分制算兼容分（critical=35/high=15/medium=6/low=2，`DM/review_schema.py:36-41`）落 SQLite `review_metrics`；write-gate 三段门禁（prewrite/precommit/postcommit）；chapter-commit 自动 accepted/rejected；v7 侧另有 settle 前机检（字数下限/占位符/标题/承诺非空/名册 advisory，`scripts/v7_write.py:246-274`）。

**强**：维度结论强制逐项输出（无问题也要 pass）；审查者与起草者分离；blocking 问题必须修复或用户裁决才能过 precommit；失败只补跑失败步骤。

**弱**：
- **文笔/节奏被明确排除在审查之外**（`agents/reviewer.md:79`「写得不够好不是 issue」）——schema 里的 `ai_flavor`、`pacing` 两维因 agent 指令约束**永远不产出数据**（ai_flavor 连兼容枚举说明都没进，:126）。
- 审查只跑一轮；blocking 定点修复后**不复审**（`skills/webnovel-write/SKILL.md:170`）——修复本身可能引入新的事实/连贯问题。
- v7 机检字数**只查下限不查上限**（MAX_WORDS=6000 只进元数据不进判定，`scripts/v7_write.py:25,262,273-274`）；承诺检查仅「非空或有豁免」（:253-254）；占位符正则覆盖窄（:23）；check 与 settle 的字数口径不一致（:246 vs :343-345）。

## 3. 润色与 Anti-AI（文笔质量的唯一落点，且是自报的）

**机制**：Step 4 按序执行「修 issue → 网文化规则 → Anti-AI 终检 → 毒点规避」（`skills/webnovel-write/references/polish-guide.md:35-41`）；Anti-AI 有完整 7 层规范与 200+ 高频词库（:98-210）；style-adapter 有量化改写标准（>40 字长句 <10%、said tag 占比 ≤30%、开头 200-400 字入冲突等，`references/style-adapter.md:27-63`）。

**强**：词库分层细致（A-N 十四类套话）；红线明确（只改表达不改事实）；分题材风格加权。

**弱**：
- **`anti_ai_force_check` 是主 agent 自报契约**——polish-guide 自认「词频仅作为提醒，不再作为硬性门槛」（:46），`scripts/` 全目录无任何程序化 anti-AI 检测实现。style-adapter 里那些**本可程序化的量化标准**（长句比例、said tag 占比、解释段长度）没有任何一个被脚本化。
- **Anti-AI 完全后置**：Step 2 起草时刻意不带 Anti-AI 指导（SKILL.md:124「不加载 core-constraints/anti-ai-guide」），初稿的句式规整、信息过密等**结构性 AI 味**生成时不管，事后「只改表达」的洗稿对结构问题收效有限——这是明确的设计权衡，但在「只看质量」准绳下值得重估。
- 修复后无复审（见 §2）。

## 4. 写作技法资产（总量充实，接线漏损严重）

**机制**：references+templates 约 1.26 万行、9 张 CSV 共 739 条（正反例四层结构：大模型指令/核心摘要/详细展开/正例/反例），`validate_csv.py` 实跑 0 错 0 警。消费链：init/plan 直读共享 md + 直调 CSV；write 期靠 story-system 合同路由（`题材与调性推理.csv` → 推荐表检索 → `裁决规则.csv` 注入 `CHAPTER_BRIEF.writing_guidance`）+ 主流程 5 个按需触发条件（`skills/webnovel-write/SKILL.md:37-40`）。

**强**：cool-points-guide（六爽点/30-40-30/信息差/打脸四步）方法论完整；CSV 正反例质量高（反例直指 AI 通病）；题材模板 37 个全覆盖 genre-index 映射。

**弱**（接线断点与盲区）：
- **完全孤儿**：`references/shared/naming-and-voice-gaps.md`（63 行，对话声线/命名缺陷正反例——全插件唯一深挖语言层缺陷的资产）、`templates/golden-finger-templates.md`（473 行）、`skills/webnovel-write/references/writing/desire-description.md`（311 行，欲念/渴望描写）——gap-register 曾登记「naming-and-voice-gaps 主服务 write Step 2」为已完成，实际从未接线。
- **写作期不可达**：`人设与关系.csv`（101 条）与 `金手指与设定.csv`（104 条）无任何 skill 直调，全靠合同路由间接命中；write 的 5 个触发条件不含 `桥段套路`（108 条）与 `爽点与节奏`（104 条）两张最大表——fallback 场景下写作期失去它们。
- **技法盲区**：幽默/喜剧（0 命中）、POV 管理（无系统指引）、修辞句法正向素材（白描/通感 0 命中）、亲密戏尺度、商业文案（上架/简介）——五类接近空白。
- 题材模板厚度不均：系统流 97 行 vs 规则怪谈 305 行；写作技法 CSV 分类 45 种过散（20+ 个分类仅 1 条），稀释检索召回。
- 账实不符：loading-map 有 3 处漂移（plan 直调场景写法系夸大、步骤号过时、4 个孤儿未登记）；gap-register 三个 P1 缺口已补未销账。

## 5. 质量度量回路（骨架完整，两条关键链路断裂）

**机制**：review_metrics 落库（总分/维度分/严重度计数）→ `get_review_trend_stats`（`DM/index_reading_mixin.py:220-279`）→ 低分区间识别 → 写作指导生成（「优先修复近期低分问题」「均分低则减少跳场」等，`DM/writing_guidance_builder.py:206-275`）+ 必做清单（:278-449）→ checklist 完成分再落库形成趋势。`chapter_reading_power` 表 schema 完整（钩子类型/强度/爽点模式/微兑现/硬违反，`DM/index_reading_mixin.py:16-49`），消费端齐备（写前上下文、dashboard、quality_trend_report）。

**弱**：
- **审查得分回流不达主路径**：`writing_guidance` / `reader_signal` / `review_trend` 只存在于降级路径（extract-context / ContextManager）的 payload；主入口 load-context 的 sections 不含它们（`DM/memory_contract_adapter.py:160-300`）；context-agent 的补查命令 `index get-reader-signals` 也不返回 review_trend（`DM/index_manager.py:1342-1348`）——而 context-agent.md:80 明确要求第 4 段消费「writing_guidance + 审查得分趋势」，主链上无从满足。
- **追读力指标无生产者**：`chapter_reading_power` 唯一写入口是手工 CLI（`DM/index_manager.py:1414-1428`），全库无自动调用；data-agent 摘要 front matter 已有 hook_type/hook_strength 字段（`agents/data-agent.md:45-46`）却没接投影。结果：`钩子差异化/爽点去重` 指导永不触发（前提是 usage 非空，`DM/writing_guidance_builder.py:226-238`），checklist 的 hook_diversification 完成判定恒 False（:459-461），**系统性拉低 checklist_score 并污染趋势基线**。
- ai_flavor → `.story-system/anti_patterns.json` → runtime 合同 → 任务书第 4 段的回流设计完整（`DM/review_pipeline.py:155`、`DM/review_schema.py:199-228`），但前提是 reviewer 产 ai_flavor issue——当前指令不产，**整条回流空转**。
- quality_trend_report 未接入任何 skill/command（纯离线）。
- evals 全是流程行为断言（frontmatter/字符串契约/门禁失败关闭），**无任何文本质量评测**。

## 6. 学习闭环（自然语言便签级）

**机制**：`/webnovel-learn` 把用户认可的写法存入 `.webnovel/project_memory.json`（pattern_type + 自然语言 description + importance，`scripts/project_memory.py:49-92`）；写前经 `_load_author_style_patterns` 按 importance 取前 10 条、每条截 200 字注入（`DM/memory_contract_adapter.py:302-349`）。

**弱**：
- 「成功」= 用户主观认可，与审查得分/追读力无关——**高分章不会自动变成 pattern**，全库无自动提取代码；
- 无结构化特征（不含正文片段、无量化证据）、近重复不去重（仅完全相同跳过）、只增不删；
- 注入上限 10 条 × 200 字，且是 DROP_ORDER 第 2 位（见 §1）；
- **无效果验证**——pattern 注入后下一章得分是否改善，无任何回路测量。

## 7. 一轮成稿：没有迭代空间

主链设计为「起草一次 → 审查一轮 → 定点修复 → 润色」——没有第二稿，没有 best-of-N，没有「自我重读后重写」。审查修复与润色都是**局部修补**，无法解决初稿的结构性问题（ pacing 失衡、场景冗余、情绪弧平淡）。在「不考虑 token 成本」的准绳下，这是最大的闲置质量杠杆：同一个任务书生成 2-3 稿再择优/融合，或初稿完成后按 rubric 自评一次再整体重写，通常比任何单点修补的边际收益都大。
