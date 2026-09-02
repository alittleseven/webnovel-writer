# 02 · 发现清单（F-01 ～ F-22）

> 严重级定义（以「对生成章节文章质量的影响」为准）：
> - **S1 结构性**：直接压低成稿质量上限，且影响每一章；
> - **S2 断链**：机制已建成但未生效，修复成本低、收益直接；
> - **S3 局部**：影响特定场景/题材/长篇后期；
> - **S4 卫生**：不直接影响单章质量，影响可维护性与资产可信度。

## S1 结构性发现

### F-01 起草模型看不到上一章原文
- **现象**：写前上下文中上一章信息 = recent_summaries 500 字摘要 + latest_commit 300 字收缩摘要；正文原文 0 字进入起草。
- **证据**：`DM/memory_contract_adapter.py:204-207`（ch-2/ch-1 各 `text[:500]`）、`DM/context_budget.py:131-145`（latest_commit 收缩为 `extraction_summary[:300]`）；v7 已有解法 `scripts/v7_write.py:33,168-172`（prev_chapter_tail = 定稿尾段 1200 字）但未接 v6 主链。
- **影响**：文气/口吻/场景切光的连续性全靠二手摘要；「上章钩子本章必须回应」的铁律（`agents/context-agent.md:56`）在无原文的情况下只能回应摘要转述的钩子，钩子力度与语气常对不上。长篇「越写越散」的主观感受很大程度源于此。

### F-02 文笔质量在度量体系中完全缺席
- **现象**：全链路没有任何一个环节系统性地度量或把关文笔/语言质量。
- **证据**：reviewer 明确排除（`agents/reviewer.md:79`「不评价文笔质量」）；`ai_flavor` 维度死链（reviewer category 规范只允许 5 值，:126，ai_flavor 不在产出集）；`pacing` 维度同样不产出（该维度分恒 100）；`anti_ai_force_check` 为自报契约（`skills/webnovel-write/references/polish-guide.md:46,85`，`scripts/` 无程序化实现）；evals 无文本质量评测（`evals/fixtures/behavior/fast.json` 全为流程断言）。
- **影响**：文笔只能靠润色阶段的词库替换兜底；「这章写得平/水/尬」无法被发现、无法回流、无法趋势观测。

### F-03 一轮成稿，无迭代空间
- **现象**：起草一次、审查一轮（blocking 修复后不复审）、润色为局部修补；无第二稿/best-of-N/自评重写机制。
- **证据**：`skills/webnovel-write/SKILL.md:26`（审查只跑一轮）、:170（修复后不重新调用 reviewer）；流程表中无任何重写步骤。
- **影响**：初稿的结构性问题（节奏失衡、场景冗余、情绪弧平淡、信息密度不均）无法通过后续局部修补解决。在不考虑 token 成本的前提下，这是最大的闲置质量杠杆。

### F-04 文风记忆在上下文饱和时最先被牺牲
- **现象**：12 个 section 配额合计 30200 > 默认总预算 20000；饱和时按 DROP_ORDER 丢整段，`author_style_patterns` 排第 2、`genre_profile_excerpt` 排第 3，随后 progress/active_rules/protagonist/recent_summaries 依次出局。
- **证据**：`DM/context_budget.py:16-29`（配额）、:51-63`（DROP_ORDER）、`DM/config.py:223-225`（总预算 20000）。
- **影响**：书越写越长、合同与记忆越饱满（恰恰是最需要文风稳定的时期），沉淀的作者文风修正与题材切片越容易整体丢失——学习闭环（§6）与本条叠加后近乎失效。

## S2 断链发现（机制已建成、未生效）

### F-05 追读力/钩子/爽点指标无生产者
- **证据**：`chapter_reading_power` 唯一写入口为手工 CLI `index save-chapter-reading-power`（`DM/index_manager.py:1414-1428`），全库无自动调用；data-agent 摘要 front matter 已有 hook_type/hook_strength（`agents/data-agent.md:45-46`）但投影链不落该表。
- **影响**：写前指导「钩子差异化/爽点去重」永不触发（前提 usage 非空，`DM/writing_guidance_builder.py:226-238`）；checklist hook_diversification 恒未完成（:459-461），系统性拉低 checklist_score 污染趋势基线；dashboard 追读力视图恒空。

### F-06 审查得分趋势不进主写作路径
- **证据**：主入口 load-context 的 sections 不含 writing_guidance/reader_signal/review_trend（`DM/memory_contract_adapter.py:160-300`）；`index get-reader-signals` 不返回 review_trend（`DM/index_manager.py:1342-1348`）；含这些字段的 payload 仅存在于降级路径 extract-context（`agents/context-agent.md:98`）；而 `agents/context-agent.md:80` 要求任务书第 4 段消费「writing_guidance + 审查得分趋势」。
- **影响**：连续几章某维度低分（如连贯性滑坡）不会自动变成下一章的写作强调点；「越写越好」的反馈回路只对降级路径生效。

### F-07 ai_flavor 反模式回流空转
- **证据**：回流设计完整——reviewer 产 ai_flavor issue → `anti_patterns.json`（`DM/review_pipeline.py:155`、`DM/review_schema.py:199-228`）→ runtime 合同 → 任务书第 4 段；但 reviewer 指令不产 ai_flavor category（`agents/reviewer.md:126`）。
- **影响**：「这章出现了 XX 套话，下章别再犯」的自动学习不存在；与 F-02 叠加，Anti-AI 完全依赖当章词库。

### F-08 StyleSampler 高分风格样本回注未接线
- **证据**：`DM/style_sampler.py:250-272`（select_samples_for_chapter）无任何 skill/agent/load-context 调用；CLI `webnovel style` 是唯一入口（`DM/webnovel.py:780,902`）。
- **影响**：「用这本书自己的高分段落做文风锚点」的机制形同虚设；与 F-01 叠加，起草模型既看不到上一篇怎么写、也看不到写得最好的那篇怎么写。

### F-09 孤儿技法资产（建成未接线）
- **证据**：`references/shared/naming-and-voice-gaps.md`（63 行，对话声线/命名缺陷正反例，全插件零引用；gap-register L31/L76 登记「已完成」实为未接线）；`templates/golden-finger-templates.md`（473 行，全库零引用）；`skills/webnovel-write/references/writing/desire-description.md`（311 行，loading-map L101 登记为「保守保留」）；另有 `market-positioning.md`（424 行）、`plot-frameworks.md`（243 行）、`outline-structure.md`（213 行）三个未登记孤儿。
- **影响**：多角色同腔、副词套路化（naming-and-voice-gaps 正面针对的缺陷）只能靠 CSV 5 条对话条目 + style-adapter 71 行兜底；金手指设计质量完全依赖模型自身；言情关键场景技法不可达。

### F-10 写作期 CSV 触发面过窄
- **证据**：write 的 5 个触发条件（`skills/webnovel-write/SKILL.md:37-40`）不含 `桥段套路`（108 条）、`爽点与节奏`（104 条）；`人设与关系.csv`（101 条）与 `金手指与设定.csv`（104 条）无任何 skill 直调（全靠合同路由间接命中，fallback 场景不可达）。
- **影响**：四张最大最厚的表在起草期的可达性依赖合同路由健康；纯 v6 老项目/降级场景写作期失去主要技法弹药。

## S3 局部发现

### F-11 摘要截断方向错误（新章让旧章）
- **证据**：adapter 按升序组装 ch-2、ch-1（`DM/memory_contract_adapter.py:204-207`），配额 1000 必然超限，`_apply_dict_quota` 按 insertion order 截断（`DM/context_budget.py:92-114`）——紧邻的 ch-1 摘要先被截、ch-2 保全。
- **影响**：最相关的上一章信息反而更不完整。

### F-12 双路径语义不一致
- **证据**：风格契约主路径 2000 字（`DM/memory_contract_adapter.py:351-359`）vs 降级路径 L0 摘要 240 字（`DM/context_manager.py:287` + `DM/settings_digest.py:21`）；project_memory 主路径精选 top10×200 字（:326-349）vs 降级路径整包注入（`DM/context_manager.py:291`）。
- **影响**：入口降级时写作质量隐性劣化且无提示。

### F-13 排序信号弱且奖励冗长
- **证据**：相关性 = recency×0.7 + frequency×0.3（`DM/context_ranker.py:238-255`）；hook bonus 靠关键字表（:23,264-265）；`_length_score = len/1200`（:257-262）奖励长摘要；语义过滤是子串包含（`DM/memory/orchestrator.py:96-108`）；主路径 adapter 不排序。
- **影响**：上下文的相关性质量随书长衰减；冗长低密度的记忆条目挤占预算。

### F-14 学习闭环为自然语言便签级
- **证据**：pattern = type + 自然语言 description（`scripts/project_memory.py:78-91`）；成功信号仅用户主观认可（`skills/webnovel-learn/SKILL.md:28`），无自动从 review metrics 挖掘；近重复不去重（:70-74）；注入 10 条上限；无效果验证回路。
- **影响**：长期使用积累近重复条目；真正的高分写法（可从审查数据发现）不自动沉淀；「学到的」是否有效未知。

### F-15 v7 机检缺口
- **证据**：字数只查下限（MAX_WORDS=6000 仅进元数据，`scripts/v7_write.py:25,262,273-274`）；机检回退 800 与书史校准脱节（:261）；check 与 settle 字数口径不一致（:246 vs :343-345）；承诺仅查非空/豁免（:253-254）；占位符正则窄（:23，不含 XXX/???/花括号）；名册仅 advisory（:256-258）。
- **影响**：超长灌水章无闸；承诺系统（v7.1 规划）落地前的形式检查不防「承诺列了但正文没推进」。

### F-16 技法盲区五类
- **证据**：幽默/喜剧 0 命中（9 张 CSV）；POV 管理无系统指引（仅 1 条「视角」分类行）；修辞句法正向素材单薄（白描/通感 0 命中）；亲密戏尺度无指引（desire-description 孤儿）；商业文案（简介/上架）无指引。
- **影响**：都市日常/轻喜剧、女频多视角、言情关键场景等品类写作质量缺乏技法支撑。

### F-17 题材模板与 CSV 结构性偏科
- **证据**：系统流模板 97 行 vs 规则怪谈 305 行（`templates/genres/`）；写作技法 CSV 分类 45 种、20+ 分类仅 1 条（`references/csv/写作技法.csv`）；场景写法 60 类型中 43 个仅 1 条。
- **影响**：高频题材（系统流/都市异能）初始化质量反而低于小众题材；长尾分类稀释检索召回。

### F-18 Anti-AI 后置的设计权衡值得重估
- **证据**：Step 2 起草明确不加载 Anti-AI 指导（`skills/webnovel-write/SKILL.md:124`「已内化到任务书」，但 context-agent 铁律段仅 4 行，`agents/context-agent.md:53-57`）；Anti-AI 全部压力在 Step 4「只改表达不改事实」的洗稿。
- **影响**：句式规整、信息过密等**结构性** AI 味在生成时不受约束，事后局部改写难以根治——表现为「每章都洗但每章都有 AI 底味」。

## S4 卫生发现

### F-19 loading-map / gap-register 账实不符
- **证据**：loading-map 登记计划直调「场景写法」实无（L58 vs `skills/webnovel-plan/SKILL.md:63-65`）；步骤号系统性过时（L41-45 vs review SKILL 实际 Step 3/8）；4 个孤儿未登记；gap-register 三个 P1 缺口已补未销账（L88-93）。
- **影响**：自知文档可信度下降，后续按图施工会走错。

### F-20 methodology 节拍与卷纲脱钩
- **证据**：`stage = chapter % 5` 猜 build_up/confront/release（`DM/writing_guidance_builder.py:121-127`），与真实卷纲节拍无关。
- **影响**：方法论策略卡给出与实际剧情结构无关的节奏建议。

### F-21 quality_trend_report 未接入任何入口
- **证据**：全 skills/commands 无引用（离线脚本）。
- **影响**：趋势报告需要作者手动跑，形成了「有数据没人看」。

### F-22 死旋钮：模板权重与阶段权重
- **证据**：`DM/context_weights.py:12-38` 四模板权重恒正、只做包含过滤（`DM/context_manager.py:170-175`）；battle/emotion 模板与 early/late 动态权重从不改变任何 section 实际大小；`DM/config.py:285-288` 的阶段 bonus 无消费者。
- **影响**：声称的「按场景类型/故事阶段自适应上下文」实际不存在；配置面给作者假象。
