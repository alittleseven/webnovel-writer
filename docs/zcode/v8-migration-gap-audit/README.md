# v8 迁移缺口审计报告（v6→v7/v8 功能继承缺口全清单）

> 审计时间：2026-09-04｜审计范围：`migrate_v6_to_v7.py` 迁移结果 + v8 增强在 v7 路径上的覆盖度
> 触发事件：fantasy01 实写验收中，第 40 章标题与详细大纲不一致（自造「封仓」vs 规划「灾前夜」）
> 关联方案：docs/zcode/webnovel-copilot-300/（08 §M5-M7）、docs/zcode/writing-quality-review/

## 1. 根因链

```
migrate_v6_to_v7.py 只迁 outlines=3（总纲/节拍表/卷纲），漏了详细大纲
    ↓
仓里没有逐章规划可查
    ↓
建章纲卡时从节拍表粗粒度节拍 + 自身叙事逻辑推导标题
    ↓
标题/节点全自造，与作者逐章规划不一致
    ↓
reviewer 没有对照物（详细大纲不在仓里），4 轮审查 6 维全过但标题始终错
```

**一句话：不是「功能没对照」，是「迁移器少搬一份文件，导致后续每一层都缺参照物」。**

## 2. 缺口全清单

### A. 迁移器缺口（数据未搬）

| # | 缺失文件/目录 | 影响 | 严重级 | 状态 |
|---|-------------|------|--------|------|
| A1 | `大纲/第1卷-详细大纲.md` | 致命：无逐章标题/节点/禁区→章纲卡全自造 | 致命 | ✅ 已手动补入 `大纲/卷纲/` |
| A2 | `设定集/增强设定/` 10 文件 | 重要：能力机制卡（灾厄熔炉/灾痕感知/裂之力）、战力锚点卡（熊铁山营地/战力天花板）、物品卡（半截撬棍）、资源卡（灾源）——reviewer setting 维证据源 | 重要 | ✅ 已补入 `定稿/设定/增强设定/` |
| A3 | `大纲/第1卷-总纲写回.json` | 中等：卷 2 锚点计划 + 伏笔写回数据 | 中等 | ✅ 已补入 `大纲/卷纲/` |
| A4 | `审查报告/` 39 文件 | 低：v6 历史审查记录，有参考价值 | 低 | ✅ 已补入 |

迁移器 `migrate_v6_to_v7.py` 的 skip 理由（「v7 由角色卡/世界观承接」）对 A2 不成立——能力卡（灾厄熔炉·吞灾转化.md）和战力锚点卡（现世公开战力天花板.md）的内容不在角色卡或世界观中。

### B. 章纲批量自检缺校验（5 项）

`create_chapter_batch` 的 `self_check_batch` 只查 4 项（节点非空/字数范围/承诺前缀/时间锚批内重复），缺以下校验：

| # | 缺失校验 | 实际后果 | 严重级 |
|---|---------|---------|--------|
| B1 | 标题 vs 详细大纲一致性 | **40 章标题写错**（已发生） | 致命 |
| B2 | 承诺推进 ID 是否存在于承诺账本 | 可引用不存在的 F-999，逾期扫描不报、reviewer 不查 | 重要 |
| B3 | 人物是否存在于名册/定稿 | 可凭空引入新角色，reviewer 事后才报（反馈滞后） | 重要 |
| B4 | 时间锚跨批单调递增 | 只查批内重复，不查跨批/跨定稿递增，可时间倒流 | 重要 |
| B5 | 战力事件与力量锚点境界链一致性 | 可写「突破金丹」而境界链只有炼气→筑基 | 中等 |

### C. v7 上下文包缺 14 个 v8 section（最大缺口）

v7 `build_context_pack`（`v7_write.py`）只有 7 个 section；v6 路径（`memory_contract_adapter.py`）有 21 个。**v8 的 M0-M7 增强全部建在了 v6 路径上，v7 路径没有同步。**

| # | 缺失 section | 来源里程碑 | 对写作的影响 |
|---|-------------|-----------|-------------|
| C1 | `stale_notes` | M5/T22 | 作者已改提醒不进上下文，AI 不知道作者改了什么 |
| C2 | `reader_signal` | M5/T25 | 追读力/审查趋势/差异化提醒不进上下文 |
| C3 | `author_style_patterns` | M3/T16 | 作者模型不进上下文 |
| C4 | `style_contract` | M3/T15 | 风格契约不进上下文 |
| C5 | `story_contracts` | M1 | 写前合同不进上下文 |
| C6 | `urgent_loops` | v6 已有 | 紧急伏笔不进上下文 |
| C7 | `active_rules` | v6 已有 | 活跃规则不进上下文 |
| C8 | `protagonist` | v6 已有 | 主角状态不进上下文 |
| C9 | `progress` | v6 已有 | 进度不进上下文 |
| C10 | `outline` | v6 已有 | 章纲摘要不进上下文 |
| C11 | `memory_pack` | v6 已有 | 记忆编排不进上下文 |
| C12 | `prewrite_validation` | v6 已有 | 写前校验不进上下文 |
| C13 | `genre_profile_excerpt` | v6 已有 | 题材画像不进上下文 |
| C14 | `runtime_status` | v6 已有 | 运行时状态不进上下文 |

**意味着在 fantasy01（v7 书仓）上写章，AI 看不到作者模型、文风锚点、追读力信号、紧急伏笔、作者已改提醒。**

### D. v7 settle 缺 v8 质量门禁（3 项）

v7 settle 只查 4 项（字数 ≥min / 占位 / 标题匹配 / 承诺非空或豁免），缺：

| # | 缺失门禁 | 实际后果 |
|---|---------|---------|
| D1 | reviewer blocking 检查 | 审查发现 critical/blocking 问题仍可 settle |
| D2 | prose_check 门禁 | 文笔检测 flagged 仍可 settle |
| D3 | 素材引用存在性检查 | 章纲卡引用不存在的素材 ID 不报错 |

### E. 其他链路断裂（3 项）

| # | 缺口 | 影响 |
|---|------|------|
| E1 | foreshadow-scan pending 不自动注入 v7 决策卡 | 本章应推进项需手动跑后粘贴 |
| E2 | reader_power 投影只挂 v6 chapter-commit | v7 settle 不触发追读力自动落账 |
| E3 | author_model / style_anchor 不进 v7 上下文包 | M3 的文风/作者模型在 v7 仓上不生效 |

## 3. 优先级与修复建议

| 优先级 | 类别 | 修复方案 | 预估工作量 |
|--------|------|---------|-----------|
| **P0** | B1 | `create_chapter_batch` 检测 `大纲/卷纲/第NN卷-详细大纲.md` 存在时，自动提取 `## 第N章：标题`，card 标题不一致则告警 | 小 |
| **P0** | C 全部 | 把 v8 section 注入 v7 `build_context_pack`（复用 `memory_contract_adapter` 的逻辑，逐 section 迁移） | 中 |
| **P1** | B2-B5 | `self_check_batch` 增加账本存在性/名册存在性/时间锚递增/境界链检查 | 中 |
| **P1** | D1-D3 | v7 `settle()` 前增加 review_results.json 的 blocking 检查 + prose_check | 小 |
| **P2** | E1-E3 | v7 settle 后调用 reading_power / foreshadow pending（同 v6 路径的模式） | 小 |
| **P2** | A2 | 修 `migrate_v6_to_v7.py` 的 skip 逻辑（增强设定应迁入而非跳过） | 小 |

## 4. 已修复项

| 修复 | 提交 |
|------|------|
| 详细大纲迁入 `大纲/卷纲/第01卷-详细大纲.md` | fantasy01 仓 |
| 40-49 章纲卡按详细大纲重写（标题/节点/禁区对齐） | fantasy01 仓 |
| 增强设定 10 卡迁入 `定稿/设定/增强设定/` | c1c5fb6 |
| 总纲写回.json 迁入 | c1c5fb6 |
| 审查报告 39 文件迁入 | c1c5fb6 |
| 增强设定加入 `validate_reference_wiring.py` 豁免 | cff0ef0 |

## 5. 关于「v8 功能是否与 v6 一致」的总结

| 功能 | v6 | v7/v8 | 一致？ |
|------|----|-------|--------|
| 标题提取 | 自动从详细大纲 `## 第N章：标题` 提取 | 手动填入 card dict，无校验 | ❌ |
| 章节文件命名 | `第NNNN章-标题.md`（标题来自大纲） | `NNNN.md`（无标题） | ⚠️ |
| 时间锚校验 | timeline_check 单调递增 | 仅批内重复检查 | ⚠️ |
| 承诺推进检查 | 不查存在性 | R12 加了渐进前缀匹配（非阻断） | ⚠️ |
| 上下文包 | 21 个 section（含全部 v8 增强） | 7 个 section（缺 14 个） | ❌ |
| settle 门禁 | write-gate + blocking 检查 | 仅字数/占位/标题/承诺非空 | ⚠️ |
| 素材轨迹 | chapter-commit 自动落账 | settle 后需手动跑 `materials log` | ⚠️ |
| 文风指纹 | settle_style_domain 挂 chapter-commit | settle 后需手动跑 | ⚠️ |
| 追读力投影 | reading_power 挂 chapter-commit | v7 settle 不触发 | ⚠️ |
| 增强设定迁移 | 不适用（v6 原生） | 迁移器 skip（理由错误） | ❌ |

**本质：v8 的 M0-M7 增强全部建在了 v6 的 `memory_contract_adapter` / `ContextManager` 路径上。fantasy01（v7 story-repo）走的是 `v7_write.py` 路径——两条路各写各的，v8 增强没有同步到 v7。这就是 08 方案里「并轨增强」想要解决但还没做完的事。**
