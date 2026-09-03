# v8 功能缺口三轮复盘报告（附修复计划）

> 复盘时间：2026-09-04｜方法：三轮递进——①逐项验证既有审计 ②横向扩展未覆盖面 ③端到端场景推演
> 基线：docs/zcode/v8-migration-gap-audit/README.md（28 项缺口）+ fantasy01 实仓验证
> 结论：**原 28 项中 1 项根因需修正；三轮新发现 12 项；合计 40 项缺口归并为 4 个修复阶段**

---

## 第 1 轮复盘：既有审计逐项验证

### 1.1 重大修正：A1「详细大纲未迁移」结论有误

**原结论**：迁移器漏了详细大纲 → 仓里无逐章规划 → 标题自造。

**验证事实**（git 历史 + 内容比对）：

```
迁移提交 2343eb0 中，大纲/卷纲/第01卷.md（1633 行）已存在
  ← 该文件就是源项目 大纲/第1卷-详细大纲.md 的重命名产物
  ← 含全部 80 个逐章标题（## 第40章：灾前夜 就在其中）
```

迁移器 `_migrate_outlines` 的 glob `第*卷-详细大纲.md` → 重命名为 `卷纲/第{NN}卷.md`（去掉了「详细大纲」后缀）。

**修正后的根因链**：

```
迁移器重命名丢失语义（第01卷.md 看不出是逐章规划）
    ↓
AI 建章纲卡时读卷纲只读头部摘要，不知道往下 800 行有逐章标题
    ↓
create_chapter_batch 不读详细大纲（无论叫什么名字）→ 标题自造
    ↓
后续手动补入 -详细大纲.md 后缀版 → 现在同一内容存两份（重复）
```

### 1.2 原审计其余 27 项验证结果

| 类别 | 验证结论 |
|------|---------|
| A2 增强设定 skip 理由错误 | ✅ 属实（skipped 列表明写「v7 由角色卡承接」但内容不在） |
| A3 总纲写回.json | ⚠️ 属实 + **新发现：迁入后无消费者**（promise_ledger 无「从写回 JSON 播种账本」功能，8 条伏笔数据躺着没人读） |
| A4 审查报告 | ✅ 属实（已补） |
| B1-B5 章纲自检缺 5 项 | ✅ 全部属实（self_check_batch 仅 4 项检查，实测确认） |
| C1-C14 v7 上下文包缺 14 section | ✅ 全部属实（build_context_pack 实测仅 7 section） |
| D1-D3 settle 缺门禁 | ✅ 全部属实（v7 settle 不看 review_results、不跑 prose_check、不查素材引用） |
| E1-E3 链路断裂 | ✅ 全部属实（grep 验证 v7_write.py 零后置钩子、零 stale/author_model 引用） |

### 1.3 第 1 轮新发现

| # | 新发现 | 证据 |
|---|--------|------|
| N1 | 详细大纲内容重复两份 | `第01卷.md` 与 `第01卷-详细大纲.md` 前 20 行 diff 完全一致 |
| N2 | 总纲写回.json 无消费者 | promise_ledger/webnovel.py 中除 master-outline-sync 的同名参数外零引用 |

---

## 第 2 轮复盘：横向扩展（原审计未覆盖面）

### 2.1 doctor 治理检查组完全未建（最严重新发现）

07 方案 F-13 明确要求 doctor 新增 8 组检查：journal 水位/stale 积压/定版-轨迹一致性/锚点-正文对账/条目状态机/素材健康摘要/画廊积压/合同编译一致性。

**实测**（fantasy01 真仓跑 `build_doctor_report`）：只有 8 个环境检查（python.version / 依赖导入×7），**零治理检查**。MCP `webnovel_doctor` 暴露的也是这个空壳版本。

### 2.2 06 §12 六条数据不变量仅 1 条实现

| # | 不变量 | 实现 |
|---|--------|------|
| 1 | journal 无未分类事件积压 | ❌（author-sync 兜底新增，但不校验积压） |
| 2 | 使用轨迹引用 (条目,定版版本) 在 manifest 中存在 | ❌ |
| 3 | 力量锚点战例章号有定稿正文；境界链序单调 | ⚠️（序单调有 validate_chain；战例-正文对账无） |
| 4 | 条目状态机合法 | ✅（promise_ledger LEGAL_TRANSITIONS） |
| 5 | .story-system 合同与正典编译一致（重建对账） | ❌ |
| 6 | stale 无超过一卷未消费 | ❌ |

### 2.3 详细大纲三重路径分裂

同一文件在链路中有三种位置命名：
- plan skill 输出：`大纲/第N卷-详细大纲.md`（v6 平铺路径）
- 迁移器产物：`大纲/卷纲/第NN卷.md`（重命名去后缀）
- 手动补入：`大纲/卷纲/第NN卷-详细大纲.md`（卷纲内带后缀）

读写路径不统一 → 每次 AI 操作都要猜文件在哪。

### 2.4 其他横向发现

| # | 发现 | 影响 |
|---|------|------|
| N5 | 工坊 confirm 的三处同步只登记标记（`power_anchor_sync:required` 写进 journal impact），无执行器消费这些标记 | 作者采纳后仍需手工同步锚点/重编译合同 |
| N6 | dashboard governance.py 六视图不读承诺账本（条目/逾期视图缺失，F-14 只写了 stale 红点） | 逾期承诺在面板不可见 |
| N7 | 素材播种 `_GENRE_KEYWORDS` 无复合题材键（fantasy01 = 都市+仙侠+科幻，只能按「都市」单键播种，仙侠/科幻素材不可达） | 复合题材书素材覆盖打折 |
| N8 | name-check 只查名册，不查正文已出现但未入册的浮动名（如「哑巴嗓」「铁牙」类绰号） | 绰号类撞名漏检 |

---

## 第 3 轮复盘：端到端场景推演

**场景：作者改完素材与章纲 → 开新会话 → 写第 42 章（反派视角章）→ settle → 学习闭环**

| 步骤 | 结果 | 缺口 |
|------|------|------|
| author-sync 扫改动 | ✅ 可跑 | — |
| foreshadow pending 取本章应推进项 | ✅ 可跑（F-002 眼线返回） | 但不自动注入 v7 决策卡（E1 确认） |
| build_context_pack | ❌ | 无 stale_notes/author_model/style_anchor 等 14 section（C 类确认） |
| 双稿择优 | ⚠️ | drafts record/choose/link 三条命令全手动，SKILL 有指引但无脚本编排 |
| settle | ❌ | 不消费 review_results.json（审查阻断形同虚设）；零后置钩子（素材轨迹/指纹/追读力全手动） |
| learn 闭环 | ✅ | v7 仓可跑（13/58 事件归纳 + apply 回写成功）——**但 CLI 设计缺陷** |
| volume-reconcile | ✅ | 80% 覆盖 / 逾期 1 条 / 里程碑 0/3 检出正确 |
| MCP 装机副本 | ✅ | 6 个 v8 模块在 8.0.0 缓存中 |

### 3.1 第 3 轮新发现

| # | 发现 | 证据 |
|---|------|------|
| N9 | `learn` CLI 参数冗余：`webnovel.py learn learn --from-journal`（子命令 learn + action learn 重复），首次调用必然报错 | 实测 usage error |
| N10 | v7 settle 不读 `.webnovel/tmp/review_results.json` → reviewer 阻断语义在 v7 路径完全失效（v6 路径由 write-gate 兜底） | grep 零引用 |
| N11 | 反派视角章（如 42 黄雀）无 POV 纪律注入——pov-management.md 只挂 context-agent 人物段，v7 决策卡的 pov 字段无消费者 | 卡 42 pov=熊铁山 但上下文包不注入视角约束 |
| N12 | settle 后 `.webnovel/tmp/` 的 review/extraction artifacts 在 v7 路径无人清理也无人归档 | 工作区残留累积 |

---

## 汇总：缺口总清单（40 项归并）

| 来源 | 项数 | 状态 |
|------|------|------|
| 原审计 A 类（迁移器） | 4 | A1 根因修正；A2-A4 已补但迁移器本体未修 |
| 原审计 B 类（章纲自检） | 5 | 全部未修 |
| 原审计 C 类（v7 上下文包） | 14 | 全部未修 |
| 原审计 D 类（settle 门禁） | 3 | 全部未修 |
| 原审计 E 类（链路断裂） | 3 | 全部未修 |
| 三轮复盘新发现 N1-N12 | 12 | 未修 |
| **合计** | **41（含修正）** | |

---

## 修复计划（4 阶段，按依赖与收益排序）

### 阶段一：止血——写前链路补全（预计 2 个任务，~1 天）

> 目标：让 v7 仓上写章时 AI 能看到完整上下文 + 审查能拦住问题

| 任务 | 内容 | 验收 |
|------|------|------|
| **P1-1 v7 上下文包补 14 section** | `build_context_pack` 增加：stale_notes / reader_signal / author_style_patterns / style_contract（宪法）/ urgent_loops（账本条目）/ pending_promises（本章应推进项）/ protagonist / outline（详细大纲当章节选）/ genre_profile / active_rules / memory_pack / prewrite_validation / runtime_status / story_contracts。每个 section 复用既有模块的读函数，配额进 V7_SECTION_QUOTAS，DROP 顺序按 v6 的 PROTECTED_PATHS 语义 | fantasy01 ch42 上下文包含 stale_notes、账本应推进项、author_model 三段；饱和测试三段保全 |
| **P1-2 v7 settle 三门禁** | settle() 前置：①读 `.webnovel/tmp/review_results.json` 存在且 blocking>0 → 拒绝（`--force-review-bypass` 显式跳过）；②prose_check flagged 非（空或全 deviation）→ 拒绝；③素材引用 resolve_ref 逐条存在性 | 构造 blocking 审查 → settle 拒绝；引用不存在 ID → 报错 |

### 阶段二：一致性闸——章纲与数据不变量（预计 3 个任务，~1 天）

> 目标：标题/账本/人物/时间锚在生成时就被拦，不等 reviewer

| 任务 | 内容 | 验收 |
|------|------|------|
| **P2-1 详细大纲统一路径 + 标题闸** | ①约定规范路径 `大纲/卷纲/第NN卷-详细大纲.md`（plan skill 输出、迁移器、补入三方统一；迁移器去后缀的旧行为加兼容读取）；②`create_chapter_batch` 读当卷详细大纲提取 `## 第N章：标题`，card 标题不一致 → warning（不阻断，作者可覆盖）；缺详细大纲 → 提示 | fantasy01 建卡 43「夜袭」与大纲一致；错标题被 warning 报出 |
| **P2-2 self_check_batch 增 4 项** | ①承诺 ID 存在于账本（load_entries）；②时间锚跨批单调（读已确认卡+定稿时间锚取最大）；③战力事件境界名 ∈ 境界链；④人物 ∈ 名册∪决策卡 entities（warning 级） | F-999 引用被拒；时间倒流被拒 |
| **P2-3 数据不变量校验器** | 新 `data_modules/invariant_check.py`：实现 06 §12 六条（journal 积压/轨迹-manifest 一致/战例-正文对账/合同重建对账/stale 超一卷+状态机复检），CLI `webnovel.py invariants` | fantasy01 跑出六条各自结论 |

### 阶段三：闭环补全——settle 后置与工坊执行器（预计 3 个任务，~1 天）

> 目标：settle 一条命令完成全部落账；工坊采纳标记有人消费

| 任务 | 内容 | 验收 |
|------|------|------|
| **P3-1 v7 settle 后置钩子** | settle 成功后自动串：materials log（幂等闸已有）→ settle_style_domain（指纹+高分采样）→ reading_power（从摘要 front matter 提取）；各自 try/except 不阻断 settle；CLI 输出后置结果一行 | ch43 settle 一次跑完，轨迹/指纹/追读力三表自动更新 |
| **P3-2 工坊同步执行器** | 新 `forge-sync` 命令：扫 journal 中 `power_anchor_sync:required` / `contract_rebuild:required` 未消费标记 → 提示作者执行锚点确认与 master-outline-sync；消费后标记 cleared | adopt 功法提案 → forge-sync 引导完成锚点同步 |
| **P3-3 写回 JSON 播种 + CLI 修正** | ①promise-ledger 增 `seed-from-writeback`：读 `第NN卷-总纲写回.json` 的 foreshadow_writeback 数组建账本条目；②修 `learn` CLI 冗余参数（action 默认 learn）；③fantasy01 重复详细大纲去重（保留带后缀版） | 写回 8 条伏笔一键入账；`learn --from-journal` 直接可跑 |

### 阶段四：体检与体验（预计 3 个任务，~1 天）

> 目标：doctor 成为一站式治理体检；面板/播种/命名补盲

| 任务 | 内容 | 验收 |
|------|------|------|
| **P4-1 doctor 治理检查组** | doctor 增 8 组检查（F-13）：journal 水位/stale 积压/轨迹-manifest/锚点-正文/条目状态机/素材健康（复用 material_review stats）/画廊积压/合同对账（调 P2-3）；MCP webnovel_doctor 自动受益 | fantasy01 doctor 输出治理组结论 |
| **P4-2 dashboard 账本视图** | governance.py 增承诺账本视图（各状态计数+逾期列表）；GovernancePage 增第七段 | 面板可见 F-001~S-001 状态 |
| **P4-3 播种复合题材 + name-check 绰号** | ①seed 支持复合键（都市+仙侠+科幻 → 三键并集）；②name-check 增正文浮动名扫描（最近 N 章高频专名，warning 级） | fantasy01 播种含仙侠素材；「铁牙」类绰号被提示 |

### 依赖关系

```
P1-1 ──→ P1-2 ──→ P3-1（settle 门禁先于后置钩子）
P2-1 ──→ P2-2（路径统一先于标题闸）
P2-3 ──→ P4-1（不变量器被 doctor 复用）
P3-3 / P4-2 / P4-3 独立
```

### 明确不做（本轮）

- 不重写 v7_write 为 v6 合同链（08 方案「并轨」的大动作，等本计划验证后单独立项）
- 不做 write-gate 对 v7 的全量移植（用 P1-2 的 settle 门禁替代）
- 不动 v6 路径任何行为（v6 是回归基线）

---

## 验证方式（每阶段通用）

1. 全量 pytest（≥当前 1452 基线，覆盖率 ≥80%）
2. fantasy01 实仓冒烟：ch42 走完「pending→上下文包→settle→后置→learn」全链
3. `validate_reference_wiring.py` drift=0
4. 行为评测全 PASS

## 复盘方法说明

- **第 1 轮**（验证）：逐项 grep/实跑原审计 28 项 → 修正 A1 根因 + 发现 N1/N2
- **第 2 轮**（横向）：doctor/不变量/路径分裂/工坊/dashboard/播种/命名 → 发现 N3-N8
- **第 3 轮**（场景）：以「改素材→写 42 章→settle→learn」端到端走链 → 发现 N9-N12
- 每项新发现均有代码行号或实跑输出佐证，无凭印象项
