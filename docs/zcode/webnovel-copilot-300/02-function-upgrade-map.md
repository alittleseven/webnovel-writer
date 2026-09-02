# 02 · 功能点逐项升级方案

> 基座 = 本仓 v7.1.0 全功能面。每项：现状 → 升级方案 → 需求映射（N=用户需求 / A=B线连贯差距 / B=B线设定工坊 / W=质量审阅建议）。
> 升级分四个方向：**主权**（作者治理层）、**连贯**（300 章）、**设定**（战力/技能工坊）、**质量**（成稿质量并轨）。

## 1. Skills（8 个）

| Skill | 现状 | 升级方案 | 映射 |
|-------|------|---------|------|
| `webnovel-init` | 六组采集（project/protagonist/relationship/golden_finger/world/constraints）→ 生成设定集七件套 + 合同树 + git 初始化 | ①增加**作者画像采集**（节奏偏好/雷点/修改习惯自述，入 `作者/author_model.md` 播种）；②金手指环节接**设定工坊提案**（替代纯访谈）；③生成**素材域播种**（11 张 CSV 从插件 references 复制为活层起点 + 空使用轨迹）；④新书可选「总纲分阶段模式」开关 | N1/N3/N8 |
| `webnovel-plan` | 拆总纲→卷纲→章纲；CSV 检索；追读力分析；产出 volume/chapter 合同 | ①**总纲三区阶段视图**（已写卷详案冻结区/当前卷活跃区/未来卷锚点区），regen 只作用于选定区且走版本画廊；②**卷纲时间线视图**（章×故事内时间×事件×伏笔点×战力锚点），落盘 `大纲/卷纲/第NN卷-时间线.md`；③**章纲批量生成**（一批 ≤8 张，产出到 `大纲/章纲/`，front matter 含章号/节点/禁区/时间锚）；④**伏笔排期表**（每条伏笔挂「最晚回收章」→ 逾期扫描器）；⑤批量产出后统一走作者确认（一次确认一批，非逐张） | N2/N6/N7, A3/A7 |
| `webnovel-write` | 六步链（上下文→起草→审查→润色→提交→备份）+ 断点续跑 + 门禁 | ①**stale 消费**：起草前读 journal 影响标记，章纲/定版素材有未消化修改时在任务书前置「作者已改」摘要；②质量轨并轨：`--drafts N` 多稿择优、prose 维审查、上一章原文尾段（W1-W3）；③**承诺账本联动**：起草前列出本章应推进的伏笔/承诺（v7 决策卡已有雏形，v6 侧补齐） | N2-N4, A3, W1-W3 |
| `webnovel-review` | 5 维事实审查 + 指标落库 + 报告 | ①增第 6 维 **prose**（文笔/AI 味，基于程序化 prose_check）；②增**战力一致性专项**（对照锚点表查越级/通胀，A2）；③增**知识边界检查**（角色是否用了不应知信息——reviewer 已有此维但缺「谁知道什么」数据源，接名册+信息差条目）；④报告尾部附质量趋势摘要（W 类） | A1/A2, W2 |
| `webnovel-query` | 只读查询设定/角色/伏笔/状态 | ①增**战力查询面**（实体战力轨迹、越级战例账本、通胀曲线）；②增**素材查询**（活层/定版/使用轨迹）；③增**journal 查询**（作者改过什么、影响什么） | N5/N9 |
| `webnovel-learn` | 用户口述成功模式 → project_memory pattern | ①**被动学习为主**：`--from-journal` 从修改 diff 归纳（作者改了什么=作者要什么的最强信号）；②pattern 结构化（evidence_excerpt + metrics_snapshot）；③高分章自动候选（W9）；④author_model 双层回写（用户层偏好类型/项目层文风指纹） | N1, W9 |
| `webnovel-doctor` | 体检目录/文件/JSON/SQLite/RAG/Dashboard | 增**治理层体检**：journal 完整性（未留账的 git diff）、stale 清单、定版与引用一致性、伏笔逾期清单、战力锚点表健康、素材使用率统计、regen 画廊积压 | N2-N7 |
| `webnovel-dashboard` | 只读可视化面板 | 增**作者工作台视图**（治理层视图组）：总纲三区状态、卷冻结进度、journal 时间线、素材使用热力、战力通胀曲线、stale/逾期红点。保持只读红线（写操作仍走命令/会话） | N2-N7 |

## 2. Agents（4 个）

| Agent | 现状 | 升级方案 | 映射 |
|-------|------|---------|------|
| `context-agent` | 五段写作任务书（load-context 基础包） | ①消费 **stale 摘要**（作者修改前置段）；②上下文增 `prev_chapter_tail`/`style_anchor`/`reader_signal`（W1/R4/R6）；③素材装配从定版层取（带版本号引用） | N3, W1/W4/W6 |
| `reviewer` | 5 维事实审查 | 增 prose 维与战力专项输入（prose_check 报告 + 锚点表作为证据源） | A2, W2 |
| `data-agent` | 提取 fulfillment/disambiguation/extraction 三 artifact | ①增**素材使用轨迹写入**（本章用了哪些活层/定版素材条目，落 `素材/使用轨迹.jsonl`）；②增**战力事件提取**（突破/越级/新技能 → 锚点账本） | N3/N4, A2 |
| `deconstruction-agent` | 参考书拆解（init 阶段） | 扩展为**素材工坊的拆书通道**：作者投喂任意文本 → 抽取桥段/爽点/设定零件入活层素材（打 `来源:拆书` 标记，与作者手写区分） | N3, B2 |

## 3. CLI 子命令（36 个，按升级分组）

**新增命令（治理层，A 线 M0-M2 规格 + 本方案扩展）**

| 新命令 | 功能 | 映射 |
|--------|------|------|
| `author-sync` | 会话启动扫描 `git diff` → 语义分类（大纲/素材/设定/正文/其他）→ journal 追加 → stale 标记 → 影响分析输出 | N1-N7 |
| `author-journal` | journal 查询（按域/时间/文件过滤；`--stats` 出修改习惯统计） | N1 |
| `freeze` | 卷收尾冻结：快照当前卷依赖的大纲区/素材活层/战力体系 → `定版` 目录；生成冻结清单 | N2-N6 |
| `impact` | 影响分析：对指定文件变更输出引用反查（哪些章/素材/合同受影响）+ 三选项裁决建议 | N2-N5 |
| `power-check` | 战力确定性校验：锚点表一致性 + 越级取胜依据 + 通胀曲线 vs 卷纲里程碑 | N5, A2 |
| `power-ledger` | 越级战例账本查询/登记 | A2 |
| `foreshadow-scan` | 伏笔逾期扫描（承诺账本 × 最晚回收章 × 当前章号） | A3 |
| `material-review` | 素材卷审：使用率统计（0 token）+ 归纳/合并/淘汰建议清单（LLM 建议走会话，统计走脚本） | N3/N4 |
| `regen` | regen 画廊管理：列版本/diff 两版/采纳一版/丢弃 | N2/N6/N7 |

**升级的既有命令**

| 命令 | 升级 | 映射 |
|------|------|------|
| `timeline-check` | 从「单调性校验」升级为「时间线视图导出」（md 表格：章×故事内时间×事件×伏笔点×战力锚点）+ 年龄/修龄推演（A4） | N6, A4 |
| `master-outline-sync` | 增三区阶段语义：只同步活跃区；已写卷区变更走 impact+retcon | N2 |
| `story-system` | 合同生成消费定版素材（带版本引用）；章纲合同从 `大纲/章纲/` 批量卡读取 | N3/N7 |
| `knowledge` | 实体查询合并**知识边界**输出（该实体每个信息点：哪些角色知道、从哪章知道） | A1 |
| `style` | StyleSampler 接线（高分章自动采样 + 写前 style_anchor 注入，W6） | W6 |
| `context`/`memory-contract` | load-context 增 `prev_chapter_tail`/`style_anchor`/`reader_signal`/`stale_notes` 四 section（W1/R4） | W1/W4 |
| `doctor` | 见 webnovel-doctor 条 | — |
| `init` | 见 webnovel-init 条（素材播种/画像采集/分阶段开关） | — |
| `backup` | 卷收尾自动触发 `freeze`（备份与冻结同事务） | N2-N6 |
| `meter` | 保持（ZCode 用量库只读） | — |

**不动**：where/preflight/project-status/write-gate/projections/user-report/run-ledger/run-log/use/index/state/rag/entity/memory/migrate/status/update-state/archive/chapter-commit/review-pipeline/placeholder-scan/v7 系（v7_cache/v7_write 由质量轨与设定轨另行增强）。

## 4. Hooks（4 个）

| Hook | 升级 |
|------|------|
| `session_start` | 链入 **author-sync**（作者上次会话后的修改留账+影响分析，作为会话开场上下文的一部分注入）——这是「修改触发记录」的主入口 |
| `guard_runtime_write` | 保持只拦 AI 路径；**显式放行作者路径**（文件 owner=作者编辑器写入的判定不做——机制上 git 已兜底，本 hook 只防 AI 直写运行时文件） |
| `chapter_meter` / `chapter_body_trace` | 不动 |

## 5. ZCode 面（插件/MCP/命令）

| 面 | 升级 |
|----|------|
| MCP server（9 工具） | 增治理层只读工具：`webnovel_journal`、`webnovel_stale`、`webnovel_power`（锚点+通胀）、`webnovel_material`（素材查询）、`webnovel_foreshadow`（逾期扫描）——全部只读，写操作仍走会话/skill |
| `/webnovel:*` 命令 | 增 `/webnovel:sync`（手动触发 author-sync+影响报告）、`/webnovel:freeze`（卷收尾冻结向导）、`/webnovel:forge`（设定工坊入口）、`/webnovel:materials`（素材工作台会话模式） |
| `webnovel init` 模板 | 书项目 AGENTS.md 模板（ZCode 工作区指令，写作硬规则每会话注入——上一任务已列为未来项，此处并轨） |
| userConfig | 增 `authorSovereignty`（默认 on：启用治理层）与 `draftCount`（W3 的按书默认档） |

## 6. 数据层与资产

| 层 | 现状 | 升级 | 映射 |
|----|------|------|------|
| git 正典 | 书项目独立 git 仓（v7 已验证 settle 原子提交） | 升格为**唯一真源**：合同/索引/缓存全部声明为编译产物，`verify` 命令随时可「删光重建对账」（v7_cache 已有此不变量，推广到全部投影） | P1/P7 |
| `.story-system/` 合同树 | 写前真源（master/volume/chapter/review + anti_patterns） | 定位调整：**从「真源」降为「编译产物」**——由 `大纲/`+`素材/定版/`+`设定/` 经 story-system 命令生成；作者改大纲后重新编译而非直接改合同 | 批判一 |
| `.webnovel/` 投影 | 写后 read-model（state/index/summaries/memory/vectors） | 保持；增 stale 标记与素材使用轨迹的消费 | N3 |
| v7 story-repo | book.yaml/定稿/大纲/工作区/演化（fantasy01 38 章实跑） | **扩展为六域**：增 `素材/`、`作者/`、`文风/` 三域（目录契约见 05） | N1-N7 |
| 承诺/伏笔 | v6 override_ledger + v7 决策卡豁免 | 统一为**承诺账本**（`大纲/条目/`）：伏笔 F/悬念 S/感情线 R 三类，每条挂最晚回收章，foreshadow-scan 扫逾期 | A3 |
| references 资产 | 9 CSV + 共享 md（质量审阅已列接线/盲区项） | 质量轨 W5/W7/W8/W9 并轨执行（孤儿接线、触发面扩容、盲区补齐） | W5-W9 |
| templates | 37 题材 | 系统流/都市异能补厚（W14）；增「素材播种包」模板（每题材 11 张 CSV 起始内容） | N3, W14 |

## 7. 写章链路（v6/v7 双链）

| 链路 | 升级 |
|------|------|
| v6 六步链 | 质量轨 W1-W4 并轨（上一章原文/文笔度量/多稿/反馈闭合）+ stale 消费 + 素材轨迹写入 |
| v7 写路径 | ①决策卡增「素材引用声明」（本章用哪些定版条目）与「战力事件预告」（预期突破/越级→机检对账）；②机检增上限告警与承诺推进检查（W12）；③settle 后触发使用轨迹与锚点账本写入 |
| 双格式守卫 | 保持（迁移期结束后 v6 链退役另议） |

## 8. 升级全景速查（需求 × 落点）

| 需求 | 主要落点（文档/里程碑） |
|------|------------------------|
| N1 作者为主+习惯记录 | 04 治理层 / 07 F-01 / M0+M3 |
| N2 总纲分阶段 | 07 F-02 / M1 |
| N3/N4 素材 | 05 素材域 / 06 素材卡 / 07 F-05 F-06 / M2 |
| N5 战力 | 06 战力 schema / 07 F-08 F-09 / M4 |
| N6 卷纲时间线 | 07 F-03 / M1 |
| N7 章纲批量 | 07 F-04 / M1 |
| N8 设定工坊 | 07 F-08 / M4 |
| N9 300 章连贯 | A1-A8 分落 M1/M4/M5 |
| 质量（W1-W10） | M5 质量轨整编 |
