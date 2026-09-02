# 03 · 优化建议（R1 ～ R18，P0-P3 分级）

> 分级准绳（只看文章质量收益，不看实施成本——按 Human 指令「不考虑时间与 token」）：
> - **P0**：直接抬高每一章成稿质量上限，或闭合已断裂的最高价值回路；
> - **P1**：修复断链/接线，让已建成资产生效；
> - **P2**：补盲区、加强闸；
> - **P3**：卫生与可维护性。
> 每条含：方案 / 落点 / 验收标准。关联发现见 [02-findings](02-findings.md)。

## P0 · 抬高质量上限

### R1 起草上下文引入「上一章原文尾段」（对应 F-01）
**方案**：把 v7 的 `prev_chapter_tail` 机制反向接入 v6 主链——`load-context` 新增 `prev_chapter_tail` section：读取上一章 `accepted` 正文（或定稿正文）**尾部 1200-2000 字原文**，标记为不可 DROP（与 story_contracts 同级保护）。上上章维持摘要但修正截断方向（见 R10）。可配：book.yaml / state `context.prev_chapter_tail_chars`，默认 1600。
**落点**：`DM/memory_contract_adapter.py`（新 section）、`DM/context_budget.py`（配额 + DROP_ORDER 排除）、`agents/context-agent.md`（任务书「接住上章」段改为基于原文尾段的语气/钩子复述）。
**验收**：load-context 输出含上一章原文尾段；饱和压力测试（合同+记忆全满）下该 section 不被丢弃；任务书第 2 段出现对上章结尾语气/钩子的具体接续指令。

### R2 文笔维度度量落地：程序化 Anti-AI 检测器 + prose 审查维（对应 F-02/F-07/F-18）
**方案**：两件套——
1. **程序化检测器** `scripts/prose_check.py`：把 style-adapter 已有的量化标准脚本化——高频词库命中计数（复用 polish-guide A-N 十四类词表，做成 CSV/JSON 数据）、>40 字长句比例、said tag 占比、连续同句式检测、纯解释段长度、段落长度方差。输出结构化报告（每项：阈值/实测/命中位置）。Step 4 的 `anti_ai_force_check` 从自报改为**必须附 prose_check 结果**。
2. **reviewer 增设第 6 维 prose**（或独立轻量 style-reviewer）：基于 prose_check 输出 + 通读，产出 `ai_flavor` category issue（激活 F-07 的反模式回流链）。pacing 维同理激活（见 R12 的上限闸联动）。
**落点**：新 `scripts/prose_check.py` + 词库数据文件；`agents/reviewer.md`（维度 6）；`skills/webnovel-write/SKILL.md` Step 4 契约；`DM/review_pipeline.py`（ai_flavor 落 anti_patterns.json 已有实现，激活即可）。
**验收**：一章含已知 AI 套话的测试文本被 prose_check 报出具体位置；reviewer 输出 dimension_results 覆盖 6 维；连续两章出现同一套话时第三章任务书第 4 段出现对应 anti_pattern。

### R3 多稿迭代：起草-自评-重写循环（对应 F-03）
**方案**：`/webnovel-write` 增加 `--drafts N`（默认 2，`--fast/--minimal` 保持 1）：
- 每稿独立起草（同任务书，可微调 temperature 提示语）；稿间互不可见；
- 用一份**固定质量 rubric**（钩子强度/情绪弧/场景必要性/信息密度/对话声线区分/结尾未完感，每项 1-5 分 + 一句话理由）对 N 稿自评；
- 取最高分稿进入 Step 3；若全部低于阈值（如均分 <3.5），按 rubric 最弱项生成一次定向重写（最多 1 次）。
- Rubric 自评结果落库（`draft_evaluations`），与最终审查分对照，长期校准 rubric。
**落点**：`skills/webnovel-write/SKILL.md`（Step 2 扩展）；新 `references/draft-rubric.md`；`DM/index_manager.py`（落库表）。
**验收**：`--drafts 2` 产出两稿与择优记录；rubric 分与后续审查分的相关性可查；默认模式章均质量（审查分 + prose_check）对比基线有可测提升。

### R4 闭合反馈断源：reading_power 自动生产 + 趋势进主路径（对应 F-05/F-06）
**方案**：
1. **生产端**：chapter-commit 投影链新增 `reading_power` 投影——从 data-agent 的 extraction/摘要 front matter（已有 hook_type/hook_strength 字段）+ `爽点与节奏` 合同兑现数据自动落 `chapter_reading_power` 表；
2. **消费端**：`load-context` 新增 `reader_signal` section（近期追读力/钩子类型分布/爽点模式统计/审查趋势摘要，各限 400 字），`index get-reader-signals` 补 review_trend 字段。
**落点**：`DM/index_projection_writer.py` 或新投影路由、`DM/memory_contract_adapter.py`、`DM/index_manager.py:1342-1348`、`agents/context-agent.md`（第 4 段消费说明）。
**验收**：写完一章后 `chapter_reading_power` 有自动写入记录；连续两章同型钩子后第三章任务书出现「钩子类型差异化」提醒；checklist_score 不再被恒 False 项拉低。

## P1 · 修复断链，让已建成资产生效

### R5 DROP_ORDER 重排：文风层提为不可丢（对应 F-04）
**方案**：`author_style_patterns`、`style_contract` 提入永不丢弃集合（与 story_contracts 同级）；饱和时改为**先按比例压缩各 memory_pack 子层配额**，再按现有顺序丢。配额总和超预算的结构性问题另修（可把总预算默认提到 24000，或按书配置——不考虑 token 成本，宁大勿丢）。
**落点**：`DM/context_budget.py:51-63`、`DM/config.py`。
**验收**：饱和压力测试下文风层完整注入；`test_context_budget.py` 更新断言。

### R6 StyleSampler 接线：高分章文风锚点（对应 F-08）
**方案**：accepted 且 overall_score ≥85 的章节在投影时自动 `style extract`（采样 1-2 段代表性原文）；`load-context` 注入 `style_anchor` section（1 段 300-500 字本书高分原文 + 一句「语气节奏参照」），与 R1 互补（R1 保连续性，R6 保风格基准）。
**落点**：投影链挂 `DM/style_sampler.py`、`DM/memory_contract_adapter.py`。
**验收**：写过 3 章后新章上下文含本书自己的高分段落样本；style_samples.db 非空。

### R7 孤儿资产接线（对应 F-09）
**方案**：
- `naming-and-voice-gaps.md` → context-agent 第 3 段（人物）组装时按需读，或 write 触发条件「多角色对话」时与写作技法同读；
- `golden-finger-templates.md` → init 金手指采集阶段读（替换纯访谈）；
- `desire-description.md` → 言情/狗血类题材 Step 4 按需读；
- `market-positioning.md`/`plot-frameworks.md`/`outline-structure.md` → init/plan 对应步骤接线或显式登记退役。
**落点**：`agents/context-agent.md`、`skills/webnovel-init/SKILL.md`、`skills/webnovel-write/SKILL.md` Step 4、`references/index/reference-loading-map.md`（登记同步）。
**验收**：loading-map 全部资产要么在加载链要么显式登记退役；触发对应场景时内容出现在起草/润色输入。

### R8 写作期 CSV 触发面扩容（对应 F-10）
**方案**：write 触发条件从 5 个扩到 9 个——新增：高潮/打脸/兑现场景→`爽点与节奏`；进入已知桥段（章纲标注或合同命中）→`桥段套路`；新配角/关系冲突→`人设与关系`；金手指/设定展开→`金手指与设定`。同时把这四表列入 context-agent 的按需补查命令（`reference_search.py --skill write`）。
**落点**：`skills/webnovel-write/SKILL.md:37-40`、`agents/context-agent.md`。
**验收**：fallback（无合同）项目写作期四表可达；检索结果进入起草输入。

### R9 学习闭环升级：结构化 pattern + 自动挖掘 + 效果验证（对应 F-14）
**方案**：
- pattern 结构化：新增 `evidence_excerpt`（高分正文片段 ≤150 字）与 `metrics_snapshot`（当章审查分/维度分）字段；
- 自动挖掘：`/webnovel-review` 或 chapter-commit 后，对 overall_score ≥85 的章自动建议 3 条候选 pattern（对话/钩子/节奏各取最突出维度），作者一键确认入册（`/webnovel-learn` 从纯手记升级为半自动）；
- 近重复合并：type 相同且描述相似度（编辑距离或 embedding）超阈值时合并并提升 importance；
- 效果验证：pattern 注入前后各 5 章的审查分/prose_check 分对比，季度输出「学习有效性报告」；
- 注入上限 10→20 条，配合 R5 后不再受 DROP 威胁。
**落点**：`scripts/project_memory.py`、`skills/webnovel-learn/SKILL.md`、`DM/memory_contract_adapter.py`、新报告脚本。
**验收**：高分章 30 秒内得到候选 pattern；注入扩容生效；有效性报告可生成。

### R10 摘要截断方向修正 + 双路径语义统一（对应 F-11/F-12）
**方案**：recent_summaries 改为「新章优先」截断（ch-1 完整、ch-2 承受截断）；降级路径 ContextManager 的风格契约/project_memory 行为对齐主路径（2000 字契约 + top10 精选），或在降级时于输出 meta 标注「风格层降级」让任务书可感知。
**落点**：`DM/context_budget.py:92-114`、`DM/context_manager.py:287,291`。
**验收**：饱和测试下 ch-1 摘要完整；两路径输出 diff 中风格层差异消除或显式标注。

## P2 · 补盲区、加强闸

### R11 技法盲区补齐五类（对应 F-16）
**方案**：按缺口优先级补 CSV 条目与共享 md——幽默/喜剧技法（吐槽节奏、错位喜感、严肃场景的反差处理，≥8 条入写作技法表）；POV 管理（单章视角纪律、多 POV 切换规则、视角越界自检，新共享 md + 场景写法条目）；修辞正向素材（白描/通感/节奏句法变式，扩充写作技法表「修辞」分类）；亲密戏尺度（分级写法模板，接 R7 的 desire-description）；商业文案（简介/上架公告/卷末感言模板，新表或入命名规则表扩列）。
**落点**：`references/csv/*.csv`、`references/shared/`。
**验收**：`validate_csv.py` 通过；对应题材写作期可检索命中；loading-map 登记。

### R12 v7 机检加上限与承诺推进检查（对应 F-15）
**方案**：超上限（>书史 max 或 6000 硬顶）产生 high issue「疑似灌水」（不阻断，进审查）；承诺检查升级为「承诺关键词在正文有对应推进」（可先做存在性匹配，语义判断交 reviewer）；占位符正则补 `XXX/???/{…}/未完`；统一 check 与 settle 字数口径（都用 body_clean）；机检回退改为书史均值×0.75（与提示词一致）。v6 侧 write-gate 增加同源字数上限告警。
**落点**：`scripts/v7_write.py:23-25,246-274,343-345`、`DM/prewrite_validator.py`。
**验收**：超长测试文本被标记；承诺未推进被报出；两处字数一致。

### R13 排序信号升级：实体重合度替代子串（对应 F-13）
**方案**：memory/orchestrator 的语义过滤从子串包含改为「章纲实体 + 关键词组重合度」（复用 entity_linker 索引的实体别名表）；删除 `_length_score` 或改为信息密度代理（实体/引用密度）。主路径 adapter 对 memory_pack 子层引入同一排序。
**落点**：`DM/memory/orchestrator.py:96-108`、`DM/context_ranker.py:238-265`。
**验收**：使用代称/同义词的记忆条目不再漏检；构造对比测试（长而空 vs 短而实）排序正确。

### R14 题材模板补厚 + CSV 分类收敛（对应 F-17）
**方案**：系统流/都市异能模板补至与规则怪谈同级厚度（流派细分、金手指边界、卷级结构各补全）；写作技法 CSV 分类 45→≤15（合并单条分类入大类），场景写法 60 类型做两级归并。CSV 分类字段变更走 `validate_csv.py` 校验与迁移说明。
**落点**：`templates/genres/系统流.md` 等、`references/csv/写作技法.csv`、`场景写法.csv`。
**验收**：模板行数达标；分类收敛后检索召回抽测不降。

## P3 · 卫生

### R15 自知文档对账自动化（对应 F-19）
**方案**：新校验脚本（或并入 `validate_plugin_package.py`）：扫描 references/templates 全部文件 ↔ loading-map 登记 ↔ skills/agents 实际引用三方对账，输出「未登记/未接线/登记步骤号漂移」清单；gap-register 的缺口条目加状态列并在校验中核对。
**落点**：新 `scripts/validate_reference_wiring.py` + CI/发版链。
**验收**：当前 22 项漂移全部被报出；修复后清零。

### R16 methodology 节拍接卷纲（对应 F-20）
**方案**：`build_methodology_strategy_card` 的 stage 判定改为读当前卷纲节拍（章纲 chapter_directive 的节拍字段，缺失回退现有 %5）。
**落点**：`DM/writing_guidance_builder.py:121-127`。
**验收**：有节拍标注的章策略卡与卷纲一致。

### R17 quality_trend_report 接入入口（对应 F-21）
**方案**：`/webnovel-review` 完成后自动跑一次 trend 摘要附在报告尾部；或 `/webnovel:status` 命令输出近 10 章趋势一行。
**落点**：`skills/webnovel-review/SKILL.md`、`commands/webnovel/status.md`。
**验收**：作者无需手动跑脚本即可看到趋势。

### R18 死旋钮清理（对应 F-22）
**方案**：二选一——实现 battle/emotion 模板与 early/late 阶段的真实差异化（上下文 section 大小/取舍随场景变化），或删除这些权重与配置项（诚实化）。倾向前者：场景类型感知的上下文组装对质量有实际价值（战斗章多给场景写法检索结果、情感章多给情绪节拍参考）。
**落点**：`DM/context_weights.py`、`DM/context_manager.py:170-175`、`DM/config.py:285-288`。
**验收**：战斗章与情感章的上下文组成可观测差异，或配置项移除。

---

## 优先级 × 收益矩阵（速览）

| 建议 | 关联发现 | 质量收益机制 | 级 |
|------|---------|-------------|----|
| R1 上一章原文 | F-01 | 连续性/文气 | P0 |
| R2 文笔度量落地 | F-02/07/18 | 可发现→可改进 | P0 |
| R3 多稿迭代 | F-03 | 结构质量上限 | P0 |
| R4 反馈断源闭合 | F-05/06 | 越写越好 | P0 |
| R5 文风层不可丢 | F-04 | 长篇后期稳定性 | P1 |
| R6 文风锚点 | F-08 | 风格一致性 | P1 |
| R7/R8 资产接线 | F-09/10 | 弹药可达 | P1 |
| R9 学习闭环升级 | F-14 | 复利效应 | P1 |
| R10 截断方向 | F-11/12 | 摘要质量 | P1 |
| R11-R14 盲区与闸 | F-13/15/16/17 | 品类覆盖 | P2 |
| R15-R18 卫生 | F-19/20/21/22 | 可维护性 | P3 |
