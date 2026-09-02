# 04 · 系统架构

## 1. 七层模型（承接 docs/gpt 研究线的分层语言，落到本仓实现）

```
L7  作者主权层（本方案新增）
    author-sync / journal / freeze / impact / regen 画廊 / author_model·style_profile
L6  会话编排层（ZCode 壳）
    skills×8+ / agents×4 / hooks×4 / MCP(14+) / /webnovel:* 命令(13+)
L5  工作流层
    v6 写章六步链 / v7 决策卡-机检-settle 链 / plan 规划链 / review 审查链
L4  领域服务层（统一 CLI webnovel.py，36→45+ 子命令）
    治理命令组 / 索引与投影 / 记忆与 RAG / 战力与素材 / 度量与报告
L3  确定性内核（纯脚本，无 LLM）
    git 事务 / 时间线推演 / 伏笔逾期 / 锚点校验 / 字数与占位符 / prose_check / 命名冲突
L2  数据层
    git 正典（书仓六域） → 编译产物（.story-system 合同 / .webnovel 投影 / .cache 索引）
L1  宿主（ZCode；可替换——P7 硬规则：L4 以下宿主无关）
```

关键依赖方向：L7 依赖 L3/L2（不依赖 LLM）；L6 只做触发与呈现；一切写正典的操作收口在 L4 的 git 事务（settle/freeze/retcon/采纳）。

## 2. 真源与编译产物（数据治理核心）

```
        作者编辑（任何编辑器）                AI 提案（会话/工坊/regen）
              │                                    │
              │ 免门禁，直接写                      │ 写入草稿区（regen/画廊/工作区）
              ▼                                    ▼
┌───────────────────────── git 正典（书仓六域，唯一真源）─────────────────────────┐
│  大纲域  正文域(定稿)  设定域  素材域(活/定版/轨迹)  作者域  演化域              │
└──────────────────────────────────────────────────────────────────────────────┘
              │ author-sync（diff→分类→journal→stale→impact）        │ settle/freeze/采纳
              ▼                                                    ▼
     作者域 journal.jsonl（append-only）              编译产物（可删可重建）：
     author_model / style_profile                     .story-system/ 合同树
                                                        .webnovel/ 投影（index.db 等）
                                                        .cache/（v7 缓存）
                                                        上下文包 / 任务书
```

规则：
1. **编译产物不手改**：合同由 `story-system` 从正典编译；作者改大纲后重新编译（`master-outline-sync` 升级版处理三区语义）。`webnovel doctor` 校验「正典→产物」一致性，漂移即报。
2. **AI 提案永不直接进正典**：regen 画廊（大纲/素材归纳/设定工坊）、工作区（v7 决策卡/草稿）都是草稿区；采纳动作 = git 事务（作者显式触发或 settle 链内确认）。
3. **journal 是唯一 append-only 副本**：作者行为（修改/采纳/裁决）与系统事件（freeze/retcon/stale）同流，`演化/` 目录的机器事件链（run-ledger/signals）保持 v7 既有形态并与之互查。

## 3. 治理层状态机（冻结生命周期）

```
                 ┌──────── 作者/AI 生成 ────────┐
                 ▼                             
            [ draft 草稿 ] ──作者采纳──▶ [ active 生效 ]
                 │  regen 画廊（≤3 版 + diff）      │
                 │  不满意→再生成（进画廊，永不覆盖）  │ 卷收尾 freeze
                 ▼                                ▼
            [ discarded 丢弃 ]                 [ frozen 定版 ]
                                                  │ 作者修改（触发 impact）
                                                  ▼
                                          [ change 裁决 ] ──三选项──▶ [ frozen' / retcon(N) / 还原 ]
                                                  │
                                                  └─▶ journal + 影响清单 + 引用反查
```

状态载体：`大纲/`（总纲三区）、`素材/`（活/定版）、`设定/`（含战力锚点）。状态本身不存数据库——由目录位置 + 演化事件 + git 历史推导（P7：能推导的不另存）。

## 4. 上下文装配管线（写作时刻）

```
正典选择器（确定性脚本）                       增强器（质量轨）
  章纲卡（活跃区，stale 检查）                   + prev_chapter_tail（上一章原文尾段，W1）
  合同（编译产物，含 anti_patterns）              + style_anchor（本书高分样本，W6）
  设定 L0/L2 分层（命中展开）                    + reader_signal（追读力+审查趋势，W4）
  素材装配 = 定版层(带版本) + 活层精选 top-K      + stale_notes（作者修改前置段）
  名册 + 承诺账本（本章应推进项）                  + author_model/style_profile 精选
       │
       ▼  20k-24k 字符预算（W5：文风层永不丢；饱和先压记忆层）
  context-agent → 五段任务书 → 起草（--drafts N 择优，W3）
```

## 5. 模块划分（代码仓内新增/改造）

```
webnovel-writer/（插件本体）
├── scripts/
│   ├── author_sync.py        # L7：diff 扫描/分类/journal/stale/impact（M0）
│   ├── freeze_manager.py     # L7：冻结/定版快照/冻结清单（M1）
│   ├── impact_analyzer.py    # L7：引用反查/三选项裁决建议（M1）
│   ├── regen_gallery.py      # L7：版本画廊管理（M1）
│   ├── material_store.py     # 素材三层读写/装配选择器（M2）
│   ├── material_review.py    # 使用率统计+归纳建议（M2）
│   ├── author_model.py       # 画像双层模型+从 journal 归纳（M3）
│   ├── power_schema.py       # 战力锚点抽取/账本（M4）
│   ├── power_check.py        # 锚点校验/通胀曲线（M4）
│   ├── foreshadow_scan.py    # 承诺账本逾期扫描（M5，A3）
│   ├── knowledge_boundary.py # 信息差条目管理（M5，A1）
│   ├── prose_check.py        # 程序化文笔检测（M5，W2）
│   └── webnovel.py           # 统一 CLI 挂载以上全部
├── skills/…（L6 编排改造）      mcp/server.py（只读工具扩至 14+）  commands/webnovel/（+4）
```

既有模块不动清单：memory/、index_*、story_system、chapter_commit、v7_write/v7_cache、review_pipeline、dashboard（只加视图）。

## 6. 关键时序（三视图）

**会话启动**（author-sync 主入口）：
`SessionStart hook → author-sync：git diff HEAD..工作区 + 上次 journal 水位 → 分类（六域+类型）→ journal 追加 → stale 标记（章纲/素材/设定/时间线）→ 影响摘要注入会话（作者语言，≤10 行）`

**卷收尾**（freeze）：
`backup --volume N → freeze：快照 大纲区/素材活层/战力锚点 → 素材/定版/v{NN}/ + 冻结清单 → material-review 建议 → 作者确认 → git commit(freeze 事务)`

**定版修改**（retcon）：
`作者改定版文件 → 下次 author-sync 识别 frozen-change → impact：引用章反查（使用轨迹）+ 资产反查（锚点/承诺）→ 三选项裁决 → 作者选择 → 执行（含全书 retcon 修改清单）→ journal + 演化/retcon(N) 事件 → git commit(retcon 事务)`
