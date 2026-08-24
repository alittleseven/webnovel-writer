# webnovel-writer 代码审阅报告

**日期**：2026-08-24
**审阅范围**：自本轮修复会话（P0-4b、P1-3/4/6/7/8/9b、P2-1/2/3/5/7）起的改动代码路径
**方法**：4 个并行 code-explorer 子 agent 分组深度审阅 + 人工复核 P2-2/2-3/2-7 关键路径
**回归状态**：pytest 全绿（139 用例），lint 干净

---

## 0. 项目结构与核心功能概述

webnovel-writer 是一个小说创作 CLI 插件，核心数据流为：

```
plan（大纲）→ write（正文）→ commit（合同）→ precommit（校验）→ review → 状态投影
```

`scripts/data_modules/` 分层：

| 模块 | 职责 |
|------|------|
| `chapter_outline_loader` / `story_contract_schema` | 大纲/章纲加载与截断 |
| `chapter_commit_schema` / `chapter_commit_service` / `artifact_validator` | 章合同提取与建设 |
| `memory/`（schema/writer/store/entity） | 实体/关系/状态记忆库 |
| `rag_adapter` / `reference_search` / `context_ranker` | 向量检索/CSV 检索/上下文编排 |
| `story_runtime_sources` / `index_*` | 运行时源装配/状态投影 |
| `run_ledger` / `doctor` / `project_phase` | 审计链/只读体检/阶段管理 |
| `timeline_check` | P2-5 新增时间线程序校验 |

**整体遗留（非本轮新引入，已在台账标注留 v7）**：P2-1 的 latest.json 指针与 graph FTS、P2-2 字段名统一、P2-3 LLM 别名预注册、P2-4 题材数据补充、P2-6 正文 hook。

**跨领域共性风险**（本轮修复中反复出现的根因，详见第 3 节）：
1. `int()` 防御不一致（多模块直接 `int(x)` 未 try/except）
2. 配置读取默认值防御依赖历史 `settings.json`（P1-9a/P1-2 已留）
3. 增量缓存持久化的并发/自愈问题
4. 多处的 `warning` 标记后**无消费端**（标记了但不复核）

---

## 1. P0-4b 非整数章号崩溃修复

**修复概述**：`normalize_aliases`（chapter_commit_schema.py:183-216）对非整数 `event_chapter` 回退当前章 + 产出 warning，不再 `int()` 崩溃。

**审阅结论**：崩溃已修复，但章号防御与回退语义存在遗留风险。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `chapter_commit_schema.py` 之外（build_commit 链路、`runtime_sources`、`context_ranker`） | **仍有未防御的 `int()` 直接转换**（子 agent 1 报告：runtime_sources:559/596、context_ranker 多处的 `int(x)`） | 中 | LLM 输出非整数章号（"五"/"3.5"/"xian"）在其它入口仍会 ValueError 崩溃 | 抽公共 `safe_int(x, default)` 助手，统一替换全链路裸 `int()` |
| `normalize_aliases` 回退"当前章" | 无法解析的 `event_chapter` 归属到当前章，可能污染状态投影/时间线 | 中 | 事件被错误挂到当前章，下游 timeline/实体关系错乱 | 回退时应显式标 `_unparseable_chapter: true` 并由 doctor 升 warning |
| `extract_event_warnings` 默认 `severity="error"` | 非整数章号是常见 LLM 噪声，标 error 会让 doctor 误判为阻断级 | 低 | doctor 噪声、可能误阻断 | 此类噪声降级为 warning |

---

## 2. P1-3 记忆四态空转修复

**修复概述**：`upsert_item`（memory/schema.py:680-720 附近）事实类同 key 不同值→`contradicted`、状态类→`outdated`；`_confidence_status`（writer.py:443-447）低置信写入标 `tentative`；`conflicts()` 透出 contradicted。

**审阅结论**：四态已能真正产生，但语义边界与持久化闭环有风险。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `upsert_item` 同 key 判定 | key 归一化（大小写/空白/别名）未在比较前统一，可能把真矛盾当更新覆盖，或把应更新值误判矛盾 | 中 | 记忆库事实错乱、contradicted 噪声或漏报 | key 归一化（lower+strip+别名表）后再比较 |
| `outdated` vs `contradicted` 判定 | 状态类修为提升时 `outdated` 阈值/条件缺失，可能与 `contradicted` 混淆 | 中 | 两类状态语义错位，下游展示/消费错误 | 明确 state 类只置 outdated、fact 类只置 contradicted，补单测隔离 |
| `_confidence_status` 498 行 `int(confidence)` | 缺 try/except，confidence 传字符串/None 时崩溃 | 中 | 低置信路径抛异常，记忆写入中断 | 加 try/except 默认走 active |
| `conflicts()` 透出后消费端 | orchestrator warnings 是否真正消费并展示 contradicted 未知 | 低 | 透出但不展示 = 空转 | 确认 write-gate/orchestrator 消费 `conflicts()` 输出 |

---

## 3. P1-4 token 三漏洞修复

**修复概述**：`_load_setting` 按 `context_setting_max_chars` 截断；`apply_budget` 消费 4 个死配置对 sections 均分；`extract_chapter_context` 紧凑 JSON。

**审阅结论**：三处均已生效，但截断的 Unicode/JSON 边界需注意。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `apply_budget` 预算分配 | 4 个 section 预算之和可能超过总 budget→某些 section 截断为 0/负值；`head_ratio` 应用需防越界；空 section 预算未回收 | 中 | 关键 context 被截断为空，写章质量下降 | 预算分配后做剩余再分配（空 section 预算补给非空）；`head_ratio` clamp(0,1)；负值保护 |
| `_load_setting` 截断 | 按字符截断，中文多字节在 UTF-8 下若按 byte 截可能切半个字 | 低（需确认按字符） | 截断处出现乱码字符 | 确认 `len()`/`[:n]` 按字符（Python str 已按字符，安全）；若底层按 byte 需修 |
| `extract_chapter_context` 紧凑 JSON | 去 indent 后生成端与消费端契约需一致 | 低 | 若某消费端依赖格式化（如日志解析）会失败 | 确认所有消费端只做 `json.loads`，不依赖缩进 |

---

## 4. P1-9b partial 状态透出

**修复概述**：`chapter_commit_service.py` 的 `_writer_status`/`_overall_status` 识别 partial→独立状态并透出。

**审阅结论**：状态透出已打通，但优先级与下游消费端有缺口。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `_overall_status` 优先级 | partial 与 failed/pending 的优先级关系需确认；混合（一 writer partial、一 failed）时整体判定 | 中 | partial 章节可能本应 retry 却被当 done 跳过，或反之卡死 | 明确 `failed > pending > partial > done` 优先级，补单测覆盖混合态 |
| 下游消费端 | doctor/project-status/write-gate 的 `if status == 'done'` 分支可能遗漏 `'partial'` | 中 | partial 章节在状态机/体检中表现未定义 | 全量排查 status 分支，补 `'partial'` 处理 |
| warning 吞没 | partial 入 OK 集合 + warning，但 warning 消费端未知 | 低 | warning 不展示 = 修复空转 | 确认 partial warning 在 doctor/write-gate 可见 |

---

## 5. P1-6/7/8 run_logger / doctor / precommit

**修复概述**：`run_ledger.verify_review_chapter_alignment` 复用 sha256 比对；doctor 加 `_contract_json_checks`/`_sqlite_checks`/MASTER_SETTING 升级；run_logger 失败落盘。

**审阅结论**：审计链与体检显著增强，但有几个兼容/一致性细节。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `verify_review_chapter_alignment` | sha256 比对对 CRLF/LF 换行差异敏感，可能误阻断；旧格式 commit 无 sha 记录需兼容 | 中 | 合法提交被 precommit 误拦，或旧数据全量失败 | 归一化换行后再 hash；无 sha 记录时跳过（非阻断） |
| `_contract_json_checks` glob 路径 | 需确认覆盖 volumes/chapters/reviews 全部合同目录，避免漏检 | 低 | 漏报损坏合同 | 列全路径白名单并单测 |
| `_sqlite_checks` MASTER_SETTING | `current_chapter` 来源需确认；状态漂移时升级 error 可能误报 | 低 | doctor 噪声 | 明确 current_chapter 读取源，漂移判定加容差 |

---

## 6. P2-1 性能（_project_total_words + vector_search）

**修复概述**：`_project_total_words`（story_runtime_sources.py）读 state.json 缓存增量算；`vector_search`（rag_adapter.py）查询 norm 循环外预计算。

**审阅结论**：性能优化数值等价，但增量缓存有自愈与并发风险。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `_project_total_words` 增量缓存 | state.json 的 `total_words` 与实际磁盘字数不一致（手动改正文未更新 state）时产生累计误差且**永不自愈**；已缓存章号集合为空/缺失时回退逻辑 | 中 | 字数统计持续偏离真实值，下游进度/体检失真 | 定期全量重算（如每 N 章或检测到偏差标志时）；提供 `--recompute` 强制全量 |
| 同上 | 两个进程并发 commit 不同章时，基于同一旧 `total_words` 各算增量→后写者覆盖前者，**丢更新** | 中 | 并发提交字数丢失 | 加文件锁或 commit 后校验（重算当前章字数≠缓存增量则全量） |
| `vector_search` 内联余弦 | query norm 为 0 时返回 0 正确；但 query 与 doc 维度不一致会 IndexError | 低 | 异常 embedding 维度导致检索崩溃 | 维度不一致时跳过该 doc 或返回 0（已对 norm_b==0 处理，建议加维度检查） |

---

## 7. P2-2 大纲截断按字段边界优先

**修复概述**：`_truncate_outline_by_field_priority`（chapter_outline_loader.py:173-207）优先保留 CBN/CPNs/CEN/必须覆盖节点/本章禁区行，再截断其余。

**审阅结论**：修复有效，但字段识别对 markdown 变体脆弱，且末尾提示会超预算。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| 173-207 字段识别正则 | `re.match(rf"^{re.escape(label)}\s*[：:]", ...)` 仅匹配行首裸标签；大纲若写 `**必须覆盖节点**：` 或 `（必须覆盖节点）` 则不匹配，关键字段被当普通行截断 | 中 | 关键字段（禁区/必须覆盖）被截断，写章越界或漏覆盖 | 正则放宽为允许 `**`/括号/前后空白：`^\**\s*[（(]?{label}[）)]?\s*\**\s*[：:]` |
| 193 行 `remaining = max_chars - len(result)` | 若所有关键字段已超 max_chars，`remaining<=0`，`result` 仅有字段行 + 末尾固定 append `\n...(已按字段优先级截断)` 会**超出 max_chars** | 低 | 截断后长度略超预算（下游通常容忍） | 末尾提示仅当 `remaining>0` 时 append，或计入预算 |
| 198-202 行中行截断 | `line[:fit]` 可能切断 markdown 表格行/JSON 块 | 低 | 下游解析警告（文本容忍） | 截断点优先切在行尾（已按行切，安全） |

---

## 8. P2-3 实体消歧 warn + 追读力 sanity

**修复概述**：`lookup_alias` 一对多记 warn；`get_entity` compact-id 兜底标 `_compact_id_fallback`；`save_chapter_reading_power` sanity 断言。

**审阅结论**：风险拦截增强，但 int() 防御不一致 + 标注无消费端。

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `index_reading_mixin.py:66,69` | `int(meta.chapter or 0)` / `int(meta.override_count or 0)` **缺 try/except**（而 57 行 debt_balance 有），meta 从宽松来源（如 review 回写 JSON）构造时抛 ValueError 未捕获→`save_chapter_reading_power` 崩溃 | 中 | 追读力写入中断，影响状态投影 | 与 debt_balance 一致加 `try/except (TypeError,ValueError)` |
| `get_entity` 178-197 `_compact_id_fallback` | 标记了 pending 复核，但**复核消费端是否真实存在/消费未知** | 中 | 标注空转，命名不一致实体被当正确使用 | 确认 pending 复核流程消费 `_compact_id_fallback`，否则降级为 error |
| `lookup_alias` 一对多 warn | 高基数字段（如每章新别名）会刷屏 | 低 | 日志噪声 | 加频率限制或聚合去重后再 warn |

---

## 9. P2-5 时间线程序校验（含 8-24 修正）

**修复概述**：`timeline_check.py` 解析时间轴表，校验锚点填写/单调递增/倒计时算术（按事件名分组）；8-24 修正多事件误判 bug。

**审阅结论**：修复后 fantasy01 真实项目通过，逻辑稳健。补充边界：

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `timeline_check.py` 解析正则 `_CHAPTER_ROW_RE` | 表格合并单元格/不同列数/分隔行可能误解析或漏解析 | 低 | 漏检章节，校验失真 | 补单测：列数不全/含分隔行的表格 |
| 单调性 year+day 混合 | `prev_year` 与 `prev_day` 独立比较，跨年同日逻辑需确认 | 低 | 极端时间线误报 | 用复合键 (year, day) 统一比较 |
| 事件名细微差异 | "存粮" vs "家存粮" 会分成两组导致漏检（不会误报，但漏检） | 低 | 真并行事件漏检 | 事件名归一化（去修饰词/别名表），或允许事件名模糊匹配 |

---

## 10. P2-7 CSV 检索 bigram

**修复概述**：`reference_search.py` 的 `_tokenize`（238-260）对 CJK token 长度≥3 生成 2-gram；`_bm25_score`/`_compute_idf` 子串兜底收紧到长度≥2。

**审阅结论**：误召回已消除，索引与查询对齐良好。补充：

| 位置 | 问题 | 风险 | 影响 | 建议 |
|------|------|------|------|------|
| `_tokenize` 248 `part.strip()` | 只去空白不去标点；CJK token 含括号（如"战斗描写（含）"）→ bigram 含"（含"噪声 token | 低 | 噪声 token 轻微影响 IDF，不影响主匹配 | strip 时去除首尾标点 |
| `_bigrams` 268 | 长度≥3 才拆，2 字词直接返回（正确） | 无 | — | 无需改 |
| 单字中文查询（如"金"） | 长度 1 不触发子串兜底且无 bigram，返回空结果 | 低 | 1 字专有名词查不到（收紧前也查不到，符合预期） | 如需支持，单字查询降为精确子串（长度≥1） |

---

## 3. 跨修复共性风险汇总

1. **`int()` 防御不一致**（P0-4b / P1-3 / P2-3）：多处直接 `int(x)` 未 try/except，LLM/JSON 宽松来源下崩溃。建议抽 `safe_int(x, default)` 统一替换。
2. **配置读取默认值防御**（P1-9a / P1-2 已留）：`_get_settings_int` 等多处依赖历史 `settings.json`，缺失时默认值未必合理。建议关注配置迁移与默认值审计。
3. **增量缓存并发/自愈**（P2-1）：`_project_total_words` 增量缓存存在累计误差永不自愈、并发丢更新风险。建议定期全量重算 + 文件锁。
4. **warning 标记无消费端**（P0-4b / P1-9b / P2-3）：多处产出 warning 但下游未确认消费，可能修复空转。建议建立 warning 消费端清单。

---

## 4. 问题清单（按风险排序）

| 优先级 | 位置 | 问题 | 风险 |
|--------|------|------|------|
| P1 | `story_runtime_sources.py` `_project_total_words` | 增量缓存累计误差永不自愈 + 并发丢更新 | 中 |
| P1 | 全链路裸 `int()`（runtime_sources:559/596、context_ranker、writer:498、index_reading_mixin:66/69） | LLM/JSON 宽松来源下崩溃 | 中 |
| P1 | `chapter_commit_service._overall_status` + 下游 status 分支 | partial 优先级/消费端缺口 | 中 |
| P2 | `memory/schema.upsert_item` | key 归一化缺失，矛盾/更新误判 | 中 |
| P2 | `chapter_outline_loader:173-185` 字段识别正则 | 仅匹配裸标签，markdown 变体下关键字段被截断 | 中 |
| P2 | `get_entity` `_compact_id_fallback` | 标注无确认消费端，可能空转 | 中 |
| P2 | `run_ledger.verify_review_chapter_alignment` | sha256 对换行符敏感，旧格式无 sha 兼容 | 中 |
| P3 | `context_ranker.apply_budget` | 预算分配可能超总 budget/空 section 不回收 | 中 |
| P3 | `normalize_aliases` 回退当前章 | 事件归属错误污染状态投影 | 中 |
| P3 | `timeline_check` 解析/事件名归一化 | 极端表格/事件名差异漏检 | 低 |
| P3 | `reference_search._tokenize` 标点残留 | bigram 噪声 token | 低 |
| P3 | 多处 warning severity/消费端 | 噪声或空转 | 低 |

---

## 5. 整体结论

本轮修复（P0-4b、P1-3/4/6/7/8/9b、P2-1/2/3/5/7）**核心崩溃与功能空转问题已解决**，回归测试全绿，timeline-check 在真实项目上验证了有效性（含 8-24 多事件误判修正）。

**修复中引入的新风险整体可控**，主要为：
- **中危共性问题**：`int()` 防御不一致（建议统一 `safe_int`）、增量缓存并发/自愈、下游 status 分支对 `partial` 的处理、warning 消费端缺失。
- **低危边界问题**：截断的 Unicode/JSON 边界、正则字段识别对 markdown 变体脆弱、bigram 标点噪声。

**建议下一步**（按优先级）：
1. 抽 `safe_int` 统一替换全链路裸 `int()`（覆盖 P0-4b/P1-3/P2-3 的中危崩溃点）。
2. `_project_total_words` 加定期全量重算 + 文件锁。
3. 排查所有 `status` 分支补 `partial` 处理，并确认 partial/warning 消费端存在。
4. `upsert_item` key 归一化、`_truncate_outline_by_field_priority` 正则放宽、verify_review_chapter_alignment 换行归一化。

以上 P1/P2 项可纳入下一轮修复，P3 项可随 v7 架构重写一并处理。
