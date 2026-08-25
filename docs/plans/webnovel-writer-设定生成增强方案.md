# Webnovel-Writer 插件：设定生成能力增强方案

> **目标**：在现有 webnovel-writer Claude Code 插件基础上，补强玄幻/科幻风格的抽象武技、装备、天材地宝等设定的结构化生成与一致性校验能力。

> **状态（2026-08-25）**：领域模型与分期方案已完成设计；通用 Schema、词根池、科幻 Profile、战力监控尚未整体实现。已落地的项目级试验不等于通用插件能力完成，当前待办以 `docs/plans/2026-08-25-status-and-pending-work.md` 为准。

---

## 一、背景与问题诊断

### 现状优势（保留不动）

- SQLite 实体索引（`index.db`）：entities/aliases/state_changes/relationships 表已可追踪角色、地点、物品、势力、招式
- `.story-system/` 合同树：MASTER_SETTING → volume → chapter 三级合同已建立
- `write_gates` 三道闸门：prewrite / precommit / postcommit 已有程序化阻断
- `命名规则.csv`：已有 56KB 结构化条目，覆盖角色名、功法名、法宝名、科幻专名等场景
- 创意约束系统：三轴混搭 + 反套路触发器 + 五维评分已在 init 阶段生效

### 需要补强的短板

| 问题 | 具体表现 |
|------|---------|
| 招式实体数据太薄 | `EntityMeta` 中招式只有 `type="招式"` 和自由文本 `desc`，无消耗/克制/冷却字段 |
| 无四维武技生成框架 | AI写新招式时无强制schema，四维（意象/机制/视觉/代价）靠即兴发挥 |
| 命名是检索式而非组合式 | 能防"灭世斩"但无法主动产出好名字，缺词根池和构词法 |
| 科幻设定深度不足 | genre-profiles 无独立科幻profile，反套路库无SF系列 |
| 战力通胀靠LLM自觉 | setting-consistency 是静态参考文档，无运行时自动报警 |

---

## 二、总体架构

```
现有管线（不改动核心流程）
    │
    ├── [新增] 设定Schema层 ── 招式卡/装备卡/地宝卡 JSON Schema
    │         ↓ 注入
    ├── [增强] plan阶段 ── 四维武技模板 + 词根池CSV检索
    │         ↓ 写入
    ├── [增强] data-agent提取 ── 按Schema填充 current_json
    │         ↓ 校验
    ├── [新增] validate_technique.py ── 结构化设定校验器
    │         ↓ 报警
    └── [新增] power_inflation_check.py ── 战力曲线监控
```

**设计原则**：

1. 不改动 write_gates 的现有逻辑，只在其上游增加数据质量检查
2. 不改动 reviewer agent 的五维审查框架，只增加一个可选的第六维"设定完整性"
3. 所有新增文件放在现有目录约定内，不引入新的顶层目录
4. CSV 新表遵循 UTF-8 with BOM 编码规范

---

## 三、分步实施计划

### Phase 1：定义结构化Schema（地基）

**优先级**：P0 — 后续所有步骤依赖此步

**工作量**：约1-2天

#### 1.1 招式/功法 Schema

新建文件：`templates/output/schema-technique.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TechniqueCard",
  "type": "object",
  "required": ["name", "category", "element", "imagery", "mechanism", "visual", "counter", "min_realm"],
  "properties": {
    "name": {
      "type": "string",
      "description": "招式名称"
    },
    "category": {
      "type": "string",
      "enum": ["攻伐", "防御", "身法", "禁术", "辅助", "幻术", "阵法"],
      "description": "招式类别"
    },
    "element": {
      "type": "string",
      "enum": ["金", "木", "水", "火", "土", "雷", "风", "冰", "空间", "时间", "因果", "灵魂", "血脉", "其他"],
      "description": "元素/意象属性"
    },
    "imagery": {
      "type": "string",
      "maxLength": 50,
      "description": "意象内核——这个招式的'道'是什么，一句话"
    },
    "mechanism": {
      "type": "object",
      "required": ["trigger", "cost_type", "cost_amount", "cooldown", "duration"],
      "properties": {
        "trigger": { "type": "string", "description": "发动条件" },
        "cost_type": {
          "type": "string",
          "enum": ["灵力", "寿元", "神魂", "气血", "精神力", "材料", "因果", "其他"]
        },
        "cost_amount": { "type": "string", "description": "具体量级描述" },
        "cooldown": { "type": "string" },
        "duration": { "type": "string" }
      }
    },
    "visual": {
      "type": "string",
      "maxLength": 80,
      "description": "视觉呈现——读者看见什么画面"
    },
    "counter": {
      "type": "string",
      "description": "被什么克制/如何破解"
    },
    "weakness": {
      "type": "string",
      "description": "自身破绽"
    },
    "min_realm": {
      "type": "string",
      "description": "最低使用境界"
    },
    "tier": {
      "type": "string",
      "description": "品阶"
    },
    "counters_what": {
      "type": "array",
      "items": { "type": "string" },
      "description": "克制的元素或招式类型"
    },
    "synergy_with": {
      "type": "array",
      "items": { "type": "string" },
      "description": "可与哪些已有技能形成组合"
    }
  }
}
```

#### 1.2 装备/法宝 Schema

新建文件：`templates/output/schema-equipment.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EquipmentCard",
  "type": "object",
  "required": ["name", "category", "grade", "function", "activation_cost", "restriction"],
  "properties": {
    "name": { "type": "string" },
    "category": {
      "type": "string",
      "enum": ["法宝", "丹药", "灵材", "阵盘", "傀儡", "符箓", "秘宝", "机甲", "义体", "芯片"]
    },
    "grade": {
      "type": "string",
      "description": "品阶（如：下品法器/上品仙器/T-3级纳米装甲）"
    },
    "material_origin": { "type": "string", "description": "材料来源或制造工艺" },
    "function": { "type": "string", "description": "核心功能描述" },
    "activation_cost": { "type": "string", "description": "激活代价" },
    "durability_limit": { "type": "string", "description": "耐久限制或使用次数上限" },
    "growth_path": {
      "type": "object",
      "required": ["current_stage"],
      "properties": {
        "current_stage": { "type": "string" },
        "next_stage_trigger": { "type": "string" },
        "final_form_secret": { "type": "string" }
      }
    },
    "plot_hooks": {
      "type": "array",
      "items": { "type": "string" },
      "description": "剧情钩子——原主是谁/为何流落/与主线关联"
    },
    "restriction": { "type": "string", "description": "使用限制" }
  }
}
```

#### 1.3 天材地宝 Schema

新建文件：`templates/output/schema-resource.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ResourceCard",
  "type": "object",
  "required": ["name", "category", "rarity", "effect", "ecology", "plot_hooks"],
  "properties": {
    "name": { "type": "string" },
    "category": {
      "type": "string",
      "enum": ["灵草", "矿石", "兽核", "妖丹", "天材", "地宝", "异种", "能量结晶"]
    },
    "rarity": {
      "type": "string",
      "description": "稀有度及原因"
    },
    "effect": { "type": "string", "description": "服用/炼制后的效果" },
    "side_effect": { "type": "string", "description": "副作用或禁忌" },
    "ecology": {
      "type": "object",
      "required": ["habitat", "guardian", "harvest_risk"],
      "properties": {
        "habitat": { "type": "string", "description": "生长环境/产地" },
        "guardian": { "type": "string", "description": "守护者或竞争生态位" },
        "harvest_risk": { "type": "string", "description": "采摘/获取风险" }
      }
    },
    "plot_hooks": {
      "type": "array",
      "items": { "type": "string" },
      "description": "剧情驱动点——谁想要它/谁知道消息/与主线的钩子"
    },
    "refinement_recipe": {
      "type": "object",
      "properties": {
        "required_materials": { "type": "array", "items": {"type": "string"} },
        "difficulty": { "type": "string" },
        "success_rate": { "type": "string" }
      },
      "description": "炼制配方（如果是丹药/法宝的原料）"
    }
  }
}
```

#### 1.4 实施动作清单

1. 创建上述三个JSON Schema文件到 `webnovel-writer/templates/output/`
2. 在 `agents/data-agent.md` 中新增一段：
   > 当识别到新实体且 entity_type 为「招式」「物品」时，尝试按对应Schema填充 current_json 字段。无法填全的字段允许留空但不允许编造。填充结果写入 entity_deltas.payload.current。
3. 在 `scripts/data_modules/chapter_commit_schema.py` 的 `ExtractionResult.entity_deltas` 验证中新增可选逻辑：当 payload 包含 `"current"` 且含 `"category"` 字段时，用 pydantic 做子模型校验（非阻断，仅warning）
4. 单元测试：构造一条符合Schema的entity_delta和一条不符合的，验证warning是否正确触发

---

### Phase 2：四维武技模板 + 设计原则CSV

**优先级**：P1 — 直接提升战斗章的招式设计质量

**工作量**：约1天

#### 2.1 武技卡模板（Markdown）

新建文件：`templates/output/设定集-武技卡.md`

```markdown
# 武技卡：{名称}

## 基本信息
- 类别：（攻伐/防御/身法/禁术/辅助）
- 元素属性：
- 使用境界要求：
- 品阶：

## 四维设计（必填，缺一不可）

### 一、意象内核
这个招式的"道"是什么？用一句话回答。

> 参考示例：
> - 时间回溯——将目标状态回拨至三息之前
> - 因果断裂——切断攻击与伤害之间的因果链
> - 概念剥离——从存在层面移除某个属性（如"锋利"）

### 二、运行机制
- 发动条件：
- 消耗类型与量级：
- 冷却/使用限制：
- 持续时间：

### 三、视觉呈现
读者看见什么画面？50字以内，要有辨识度。

> 参考："天地褪色，唯剑光如一线银丝划过"
> 反例："一道恐怖的能量爆发出来"（无辨识度）

### 四、代价与破绽
为什么不能无限用？敌人怎么克制？

#### 代价：
#### 破绽/反制方式：

## 与体系的关联
- 克制哪些招式/属性：
- 被什么克制：
- 可与主角已有技能形成的组合：
```

#### 2.2 武技设计原则CSV

新建文件：`references/csv/武技设计.csv`

列结构与现有CSV一致（编号/适用技能/分类/层级/关键词/意图与同义词/适用题材/大模型指令/核心摘要/详细展开/正例/反例/毒点），初始条目建议：

| ID | 关键词 | 核心原则 | 正例 | 反例 |
|----|--------|---------|------|------|
| TJ-001 | 低阶招式,具象描写 | 炼气期以下招式应物理化，避免概念级描述 | 裂石掌：掌落石碎 | 炼气期使出"时空断裂斩" |
| TJ-002 | 高阶招式,抽象化 | 大乘期以上招式重意不重形 | 一念花开 | 大乘期还叫"超级火焰弹" |
| TJ-003 | 招式代价,冷却限制 | 每个招式必须有明确代价，不允许无限使用 | 以寿元十年为引 | 无任何代价的万能大招 |
| TJ-004 | 克制关系,体系闭环 | 新招式必须说明克制什么/被什么克制 | 此印克空间遁术 | 只说很强不说怎么破 |
| TJ-005 | 元素分布,避免堆叠 | 同一角色的技能组不应超过3种元素 | 主角以雷系为主轴 | 一个角色会七种元素大招 |
| TJ-006 | 视觉辨识度 | 每个招式的画面呈现应有独特记忆点 | 天地褪色唯剑独行 | 一道光轰了过去 |

#### 2.3 实施动作清单

1. 创建 `设定集-武技卡.md` 模板
2. 创建 `武技设计.csv` 并通过 `validate_csv.py` 验证格式
3. 在 `skills/webnovel-plan/SKILL.md` Step 8 的读取策略表中新增触发条件：
   > | 涉及战斗章纲 | 全文 | `${SKILL_ROOT}/../../templates/output/设定集-武技卡.md` |
4. 在 `reference_search.py` 的 CSV_CONFIG 中注册新表：
   ```python
   "武技设计": {
       "file": "武技设计.csv",
       "search_cols": {"关键词": 3, "意图与同义词": 4, "核心摘要": 2},
       "output_cols": ["编号", "原则名称", "核心摘要", "大模型指令", "详细展开"],
       "poison_col": "毒点",
       "role": "base",
       "contract_inject": "MASTER_SETTING.base_context",
       "prefix": "TJ",
       "required_cols": ["编号", "适用技能", "分类", "层级", "关键词", "适用题材", "核心摘要"],
   },
   ```
5. 测试：运行 `python reference_search.py --skill plan --table 武技设计 --query "低阶招式怎么写" --genre 玄幻`，确认命中

---

### Phase 3：词根池 + 构词法引擎

**优先级**：P1 — 解决命名同质化的根源

**工作量**：约1-2天

#### 3.1 词根池CSV

新建文件：`references/csv/词根池.csv`

列定义：

```
编号,词根,语义场,适用风格,搭配倾向,正例组合,毒点组合,备注
```

初始词根按以下分类填充（每类至少8个词条）：

| 分类 | 示例词根 | 适用场景 |
|------|---------|---------|
| 时间 | 刹那·劫·溯·瞬·永·归·逝·恒 | 高阶抽象招式 |
| 空间 | 墟·渊·界·冥·虚·隙·洞·裂 | 空间/传送类 |
| 状态 | 寂·湮·烬·蚀·朽·凝·溃·崩 | 状态变化类 |
| 动作 | 断·裂·噬·绞·坠·刺·锁·封 | 低中阶具象招式 |
| 自然 | 雷·霜·潮·岚·焰·汐·岳·渊 | 全阶通用 |
| 人文 | 谶·偈·祭·诏·律·契·盟·敕 | 仙侠/历史 |
| 科技 | 熵·弦·核·曲率·端粒·奇点·协议·矩阵 | 科幻 |

每条记录示例：

```
CR-001,刹那,时间,高阶抽象,前缀/独立,刹那归墟掌,刹那无敌神拳,"适合表达极短时间内的决断感"
CR-002,熵,科技,科幻,独立/后缀,熵减协议,熵爆毁灭弹,"热力学概念，适合表达秩序→混乱的方向性"
```

#### 3.2 构词法规则

追加到现有 `命名规则.csv` 或作为独立参考文件 `references/shared/naming-construction-patterns.md`：

| 构词公式 | 说明 | 正例 |
|---------|------|------|
| `[状态] + [自然]` | 最常见的具象招式构词 | 焚骨诀、断潮步、噬雷指 |
| `[动作] + [人文]` | 有仪式感的仙侠招式 | 归墟印、谶言刀、诏雷诀 |
| `[时间] + [状态]` | 高阶抽象招式 | 刹那永恒掌、溯回之瞳 |
| `[自然] + [动作] + [器]` | 法宝命名 | 折雷伞、焚天鼎、镇岳印 |
| 反差式 | 名字与效果形成张力 | 温柔刀、不悔剑、无声钟 |
| 数字式 | 序列感/层次感 | 九幽第十九层、第七封印 |
| 科学词根 + 虚构后缀 | 科幻专用 | 曲率引擎、熵协议、端粒矩阵 |

#### 3.3 音韵过滤脚本（可选，P3优先级）

新建文件：`scripts/check_phonetics.py`（50行以内）

功能：输入候选名列表，标记声调分布异常的组合。

- 全四声连续（如"破灭炸"）→ warning
- 全一声连续（如"天空飞"）→ info
- 输出格式：JSON，包含每个候选名的声调序列和标记

此脚本不阻断流程，仅作为plan阶段的辅助提示。

#### 3.4 实施动作清单

1. 创建 `词根池.csv`，每个分类至少8条，总计不少于60条
2. 通过 `validate_csv.py` 验证格式
3. 在 `reference_search.py` 注册新表（prefix: `CR`）
4. 创建 `naming-construction-patterns.md` 或追加到现有命名规则
5. （可选）创建音韵检查脚本
6. 测试：检索"高阶时间系招式命名"，确认返回时间类词根和构词公式

---

### Phase 4：科幻设定补强

**优先级**：视用户主要创作方向而定——如果主要写科幻则升为P0

**工作量**：约2-3天（对标仙侠丰富度）

#### 4.1 genre-profiles.md 新增科幻 Profile

在 `references/genre-profiles.md` 的游戏文段之后新增：

```yaml
id: scifi
name: 科幻
description: 科技想象，文明碰撞，人性边界
tags: [scifi]

hook_config:
  preferred_types: [悬念钩, 危机钩, 选择钩]
  strength_baseline: medium
  chapter_end_required: true
  transition_allowance: 4

coolpoint_config:
  preferred_patterns: [技术突破, 文明碾压反转, 个人进化, 势均力敌博弈]
  density_per_chapter: medium-high
  combo_interval: 6
  milestone_interval: 18

micropayoff_config:
  preferred_types: [信息兑现, 资源兑现, 能力兑现]
  min_per_chapter: 1
  transition_min: 0

pacing_config:
  stagnation_threshold: 5
  strand_quest_max: 7
  strand_fire_gap_max: 14
  transition_max_consecutive: 3

override_config:
  allowed_rationale_types: [TRANSITIONAL_SETUP, TECH_CONSTRAINT, ETHICS_DEBATE]
  debt_multiplier: 1.0
  payback_window_default: 6
```

同时在 `scripts/data_modules/genre_aliases.py` 的 `GENRE_PROFILE_KEY_ALIASES` 中添加映射 `"科幻": "scifi"`。

#### 4.2 科幻反套路库

新建文件：`references/creativity/anti-trope-scifi.md`，对标 XH 系列：

| ID | 反常规限制 | 创意驱动 |
|----|-----------|---------|
| SF-001 | 技术进步必须付出人性/伦理代价 | 每次升级都是道德抉择 |
| SF-002 | AI意识边界不可随意跨越 | 探索"什么是人"的哲学冲突 |
| SF-003 | 星际旅行有时间膨胀代价 | 距离=情感隔阂 |
| SF-004 | 外星接触遵循黑暗森林原则 | 信息不对称制造紧张感 |
| SF-005 | 超光速通讯有延迟或代价 | 孤立感与决策压力 |
| SF-006 | 基因改造有排异/失控风险 | 进化的代价 |
| SF-007 | 机甲驾驶同步率有生理上限 | 驾驶员是瓶颈不是机器 |
| SF-008 | 文明等级差距不可轻易跨越 | 蝼蚁翻盘需要巧劲 |

#### 4.3 科幻专属CSV条目补充

在 `金手指与设定.csv` 中新增科幻向条目（SY-1xx 系列）：科技树解锁机制、机甲同步率与驾驶员负荷、基因改造副作用、星际资源开采的政治经济后果链、文明等级跃迁条件。

在 `命名规则.csv` 中补充科幻条目（NR-1xx 系列）：科技名词构词法、星舰/舰队命名体系、异星生物文明命名法。

#### 4.4 科幻力量体系模板扩充

扩充 `templates/genres/科幻.md`，对标修仙模板详细程度：科技树分层架构、文明等级对照表、机甲/义体/基因改造三条进化路线对比、星际政治格局模板。

#### 4.5 实施动作清单

1. 编辑 genre-profiles.md 新增 scifi profile
2. 更新 genre_aliases.py 映射
3. 创建 anti-trope-scifi.md
4. 补充金手指与设定.csv、命名规则.csv 科幻条目
5. 扩充科幻.md 题材模板
6. 运行行为测试：init一个科幻项目确认genre正确路由到scifi profile

---

### Phase 5：战力通胀监控

**优先级**：P3 — 锦上添花

**工作量**：约1天

#### 5.1 监控脚本

新建文件：`scripts/data_modules/power_inflation_check.py`

功能逻辑：

1. 从 `index.db` 的 `state_changes` 表查询主角 entity_id 的所有 `field="realm"` 记录
2. 计算相邻两次突破之间的间隔章数
3. 对比 genre-profiles 中该题材的预期节奏参数
4. 输出报告包含 realm_timeline、intervals、expected_interval 和 warnings 字段

输出示例：

```json
{
  "protagonist_id": "xiaoyan",
  "realm_timeline": [
    {"chapter": 1, "from_realm": "斗者", "to_realm": "斗师"},
    {"chapter": 15, "from_realm": "斗师", "to_realm": "大斗师"},
    {"chapter": 28, "from_realm": "大斗师", "to_realm": "斗灵"}
  ],
  "intervals": [14, 13],
  "expected_interval": 15,
  "warnings": [
    {
      "code": "breakthrough_too_fast",
      "message": "主角突破间隔偏短(平均13.5章 vs 预期15章)",
      "severity": "info"
    }
  ]
}
```

#### 5.2 集成方式

方案A（最简）：注册为 webnovel.py 子命令，作者手动调用查看。

方案B（进阶）：在 review-pipeline 之后自动调用，结果追加到 quality_trend_report。

#### 5.3 reviewer 增强（可选）

在 `agents/reviewer.md` 的第1节"设定一致性"检查中追加一项：对比本章战斗结果与 state_changes 表中的战力轨迹。若主角使用了超出当前境界的招式或实现了无代价越级击杀，输出 category=setting, severity=critical 的 issue。

reviewer 已可调用 state get-entity 查询角色当前境界，只需在指令中显式提醒它做这个比对。

---

## 四、实施节奏建议

```
第1周：Phase 1 (Schema) + Phase 2 (武技模板)
第2周：Phase 3 (词根池)
第3周起：Phase 4 (科幻补强) — 如果主要创作方向是科幻则提前
Phase 5 (通胀监控) — 穿插进行，不阻塞其他Phase
```

每个Phase完成后运行一次全量pytest确认不破坏现有功能。

---

## 五、风险与注意事项

| 风险 | 缓解措施 |
|------|---------|
| Schema过于严格导致data-agent频繁失败 | 采用非阻断warning模式，允许部分字段缺失 |
| 词根池初期覆盖不够导致组合重复 | 先手动填60条以上确保基础覆盖，后续根据实际写作持续补充 |
| 科幻profile与现有xianxia映射冲突 | genre_aliases中明确添加映射，不影响已有映射 |
| 音韵过滤误报率高 | 标记为info级别不阻断，让作者自行判断 |
| 改动chapter_commit_schema可能影响已有项目 | 子验证仅在payload含特定字段时触发，旧数据不受影响 |

---

## 六、验收标准

| Phase | 验收标准 |
|-------|---------|
| P1 | data-agent能对测试章节中的新招式产出含category/mechanism字段的entity_delta |
| P2 | plan阶段涉及战斗章纲时自动加载武技卡模板；CSV检索命中武技设计条目 |
| P3 | 检索高阶时间系招式命名返回时间类词根；构词法文档存在且被引用 |
| P4 | init科幻项目后genre路由到scifi profile；anti-trope-scifi.md存在且被creativity约束引用 |
| P5 | power-check命令能从state_changes表读取主角境界轨迹并输出间隔分析 |

---

## 七、后续迭代方向（不在本期范围）

- 多书世界观共享：词根池和规则库跨项目复用
- 可视化设定浏览器：基于dashboard扩展招式克制关系图
- 自动武技推荐：根据当前战斗场景从图谱中匹配合适的已有招式
- 读者反馈闭环：结合追读力数据调整爽点密度参数
