# 06 · 数据文档（Schema 与数据格式）

> 全部为纯文本（md/yaml/csv/jsonl）。原则：能从 git 历史推导的不另存字段；机器可校验的结构用 yaml/jsonl，人类可编辑的用 md。

## 1. 数据资产总表

| 资产 | 位置 | 形态 | 写者 | 读者 |
|------|------|------|------|------|
| journal | `作者/journal.jsonl` | jsonl append-only | author-sync/系统 | impact/author_model/学习闭环 |
| stale 标记 | `.webnovel/stale.json` | json（可重建） | author-sync | load-context/plan/write |
| author_model | `作者/author_model.md` | md（LLM 生成+作者可改） | M3 归纳器+作者 | context-agent |
| style_profile | `文风/指纹.yaml` | yaml（脚本可算） | 指纹计算器 | context-agent/style_anchor |
| 素材卡 | `素材/活/*.csv` | csv（10 张） | 作者/AI 归纳/拆书 | 装配器/工坊 |
| 定版 manifest | `素材/定版/v{NN}/manifest.json` | json | freeze | impact/装配器 |
| 使用轨迹 | `素材/使用轨迹.jsonl` | jsonl | data-agent/settle | material-review/impact |
| 战力锚点 | `设定/力量锚点.yaml` | yaml | 作者（工坊采纳）/事件提取 | power_check/reviewer |
| 越级战例账本 | `设定/力量锚点.yaml` 内表段 | yaml | data-agent | power_check |
| 承诺条目 | `大纲/条目/{伏笔,悬念,感情线}/*.md` | md+front matter | plan/data-agent/作者 | foreshadow-scan/write |
| 章纲卡 | `大纲/章纲/NNNN.md` | md+front matter | plan 批量/作者 | story-system 编译/context-agent |
| 信息差条目 | `设定/信息差.md` | md（表格） | data-agent/作者 | knowledge/reviewer |
| regen 画廊 | `大纲/regen/**`、`设定/regen/工坊/**` | md+diff | regen | 作者采纳 |
| 演化事件链 | `演化/run-ledger.jsonl`、`signals.jsonl` | jsonl | settle/freeze/retcon | doctor/dashboard |

## 2. 章纲卡 front matter（批量生成的基本单元）

```yaml
---
章号: 39
标题: 纸债
卷: 2
状态: draft            # draft → confirmed（作者确认）→ written → frozen（随卷）
时间锚: 第41日·夜      # 故事内时间（timeline-check 推演输入）
节点: [CBN: 发现账本异常, CPN: 与赵姓汉子对峙, CEN: 熊铁山出手]
禁区: [主角不得暴露金手指]
承诺推进: [F-003: 揭示部分真相]
战力事件: []            # 预告：预期突破/越级（机检对账用）
素材引用: [桥段:TR-012, 场景:SP-007]   # 装配与轨迹写入用
字数目标: 2400
---
# 章纲正文（自由结构：场景序列/情绪弧/钩子设计）
```

## 3. journal.jsonl 事件格式

```jsonc
// 一行一事，append-only
{
  "ts": "2026-09-03T14:22:31+08:00",
  "actor": "author",              // author | system | ai
  "action": "edit",               // edit | adopt | freeze | retcon | settle | regen | discard | learn
  "domain": "章纲",               // 总纲|卷纲|章纲|条目|素材|设定|战力|正文|文风|其他
  "path": "大纲/章纲/0039.md",
  "change_kind": "content|style|fact|structure|add|delete",
  "diff_stat": {"ins": 12, "del": 4},
  "summary": "把对峙场景从酒楼改到码头",   // LLM 分类时生成（≤30字），脚本分类时留空
  "impact": ["context-stale:0039", "timeline:recheck"],  // 影响标记（stale/重校验/引用反查）
  "session": "zcode-2026-09-03-a"  // 可选：触发会话
}
```

分类策略：脚本先按路径+diff_stat 做**域与结构分类**（0 token）；`summary` 与 `change_kind` 的语义细化由会话启动时的 LLM 批量补全（一次调用处理全部新事件，非逐条）。

## 4. stale.json（影响标记，可重建）

```json
{
  "generated_at": "...",
  "items": [
    {"target": "chapter:0039", "reason": "章纲被作者修改", "since": "...", "consumed": false},
    {"target": "material:v01:TR-012", "reason": "定版素材修改", "affected_chapters": [35, 38]}
  ]
}
```

消费规则：context-agent 装配时把未消费的 stale 转为任务书前置段「作者已改」；write 完成后标记 consumed。

## 5. author_model（md，项目层）与 跨书偏好（yaml，用户层）

```markdown
<!-- 作者/author_model.md：每卷归纳一次 + 作者随时可改（改了也进 journal） -->
## 节奏偏好
- 冲突导入偏早（前 300 字内），见 35/37/38 章修改模式
## 雷点（作者改掉过什么）
- 删过 3 次「心中暗道」类内心套话（journal 2026-09-01~05）
## 修改习惯
- 常改对话口气（占修改 42%），很少动战斗结果
## 当前书特定要求
- …
```

```yaml
# 作者/跨书偏好.yaml
节奏: {冲突前置: true, 章末必留钩: true}
雷点: [圣父文, 无代价金手指, 大段设定倾泻]
审稿习惯: {偏好裁决选项数: 3, 接受AI建议率: 0.6}   # 统计脚本维护
```

## 6. style_profile（指纹，脚本可算）

```yaml
# 文风/指纹.yaml（由定稿正文统计，每次 settle 后增量更新）
句长: {均值: 21.4, p90: 44, 方差: 118}
段落: {均值字数: 96, 单段上限命中率: 0.04}
对话占比: 0.38
said_tag_ratio: 0.27
高频口头禅: [{词: "倒是", 每章频次: 2.1}, ...]
标点: {破折号率: 0.9/千字, 省略号率: 1.2/千字}
金句样本: [{章: 37, 摘录: "纸比人命贵。"}]   # 与金句库.md 联动
```

## 7. 素材卡 CSV 列约定（10 张活层表）

统一列骨架（各表可加专属列）：

```csv
id,名称,分类,核心摘要,详细展开,正例,反例,来源,状态,备注
TR-012,火葬场四阶段·决裂,桥段,……,…,…,…,作者手写,active,作者2026-09-02新增
SP-007,码头夜战,场景,…,…,…,…,拆书:某书第41章,active,
```

- `来源`：`作者手写 | AI归纳 | 拆书:<出处> | 工坊采纳:<提案id> | 播种:<题材包>`——author_model 与 material-review 的关键分组维度；
- `状态`：`active | 衰减（N 卷未用）| 归档`——material-review 维护；
- 定版快照 = 目录复制 + manifest（不改造 csv 本身）。

## 8. 战力锚点（`设定/力量锚点.yaml`，双层模型的硬校验层）

```yaml
spec: power-anchor/1
境界链:
  - {序: 1, 名: 聚气, 差距描述: "可敌 3 名凡人武者", 寿元: 常人}
  - {序: 2, 名: 凝罡, 差距描述: "压制聚气，非越级不可胜", 寿元: +20}
越级规则:
  跨1阶: 需列依据（金手指/代价/外因 任一）
  跨2阶: 必须金手指+代价双列，且卷纲有预告
战例账本:   # data-agent 从正文提取，作者可改
  - {章: 37, 对阵: "苏小白 vs 赵姓汉子", 结果: 胜, 跨阶: 1, 依据: [代价: 折损纸人一具, 外因: 夜战]}
通胀记录:   # settle 时追加
  - {章: 38, 主角锚点: 凝罡(2), 事件: 突破, 卷纲里程碑: "卷二末凝罡", 偏差: 提前2章}
```

校验语义（power_check）：①正文战例的跨阶数 vs 依据完备性（硬）；②战例与境界链矛盾（硬）；③通胀偏差连续超阈值（软提示，对账卷纲）。

## 9. 信息差条目（`设定/信息差.md` 表格）

```markdown
| 信息点 | 知晓者 | 知晓章 | 泄露禁忌 |
|--------|--------|-------|----------|
| 主角能吃灾 | 苏小白 | 1 | 不得在第3卷前让名册角色知晓 |
| 账本真相 | 熊铁山 | 41 | 对主角隐瞒至卷三 |
```

消费者：reviewer（角色知识边界维的证据源）、knowledge 查询。

## 10. 定版 manifest（`素材/定版/v{NN}/manifest.json`）

```json
{
  "volume": 2,
  "frozen_at": "...",
  "source_files": [{"path": "素材/活/桥段.csv", "sha1": "...", "rows": 108}],
  "outline_range": ["第27章", "第52章"],
  "power_anchor_sha1": "…",
  "notes": "卷二冻结；含作者 09-02 手写新增 5 条"
}
```

## 11. 演化事件链（保持 v7 形态，增两类事件）

`freeze(N)` / `retcon(N)` / `adopt(regen)` 事件追加至 `演化/run-ledger.jsonl`，与 journal 互查（doctor 校验两边一致）。

## 12. 数据不变量（doctor 校验清单）

1. journal 无未分类事件积压（脚本分类必达，summary 可异步）；
2. 使用轨迹引用的 (条目, 定版版本) 在对应 manifest 中存在；
3. 力量锚点战例的章号均有对应定稿正文；境界链序单调；
4. 条目状态机合法（open→推进中→已回收/作废；retcon 只能由 journal+演化双记录触发）；
5. `.story-system/` 合同与正典编译一致（重建对账）；
6. stale 无超过一卷未消费的项。
