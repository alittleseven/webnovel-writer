# Genre Taxonomy Convergence Plan

日期：2026-06-04
状态：输入归一化基础已存在；taxonomy index 与全链路统一仍待完成（2026-08-25 核对）

当前代码已具备 `resolve_genre()`、`_normalize_genre_key()` 和 `GENRE_INPUT_ALIASES` 等分散归一化逻辑，但尚未完成单一 taxonomy index 和所有入口统一。剩余工作以 `docs/plans/2026-08-25-status-and-pending-work.md` 为准。

## 目标

把题材体系收敛到 CSV 已采用的 15 个 `canonical_genre`，同时保留 37 个中文题材模板作为初始化阶段的可叠加 preset。

一句话原则：

> CSV canonical 是检索主干；taxonomy index 是用户输入层真源；模板文件是 preset；平台细分、套路、形式全部标签化。

## 已核实事实

- `webnovel-writer/templates/genres/*.md` 当前实际数量是 37 个。
- 37 个模板只在初始化链路中直接读取：
  - `skills/webnovel-init/SKILL.md` 提示按用户题材读取 `templates/genres/`。
  - `scripts/init_project.py` 通过 `_normalize_genre_key()` 后拼 `templates/genres/{key}.md`。
- 当前至少有三处题材输入归一逻辑，且输出命名空间不同：
  - `scripts/init_project.py::_normalize_genre_key()`：用户输入 -> 模板文件名。
  - `scripts/reference_search.py::resolve_genre()`：用户输入/平台标签/legacy -> 15 canonical。
  - `scripts/data_modules/genre_aliases.py::GENRE_INPUT_ALIASES`：用户输入 -> 模板/profile 旧画像 key 的前置标签。
- 现有映射规模不能再粗略按几十条估算：
  - `PLATFORM_TO_CANONICAL` 34 keys。
  - `_LEGACY_GENRE_MAP` 27 keys。
  - 两者去重后 54 keys，重叠 7 keys。
  - 加上 15 canonical 和 `全部`，当前 `resolve_genre()` 可处理 67 个 distinct 输入。
  - 再并入 `_normalize_genre_key()` / `GENRE_INPUT_ALIASES` 的 15 条输入 alias，taxonomy 输入覆盖集合是 78 个 distinct labels。
  - 再并入 37 个模板文件 stem，完整覆盖集合当前是 92 个 distinct labels/stems。
- `_normalize_genre_key()` 与 `GENRE_INPUT_ALIASES` 当前 15 条内容完全一致，是重复真源。
- `state.json` 当前 schema 是 `project_info.genre`，不是顶层 `project.genre`。
- legacy `project.genre` 消费者不止 plan/write：
  - `skills/webnovel-init/SKILL.md`
  - `skills/webnovel-plan/SKILL.md`
  - `skills/webnovel-write/SKILL.md`
  - `skills/webnovel-review/SKILL.md`
  - `scripts/data_modules/context_manager.py`
  - `scripts/data_modules/memory_contract_adapter.py`
- `context_manager.py` 当前是 `project.genre` 优先，`project_info.genre` 兜底；目标状态应反转为 `project_info` 优先。
- `memory_contract_adapter.py` 当前 fallback 链是 Story Contracts route -> protagonist genre -> legacy `state.project.genre`，不读取 `project_info.genre`；目标状态应增加 `project_info` 并把 legacy `project.genre` 放最后。
- `story_system_engine.py::_route()` 包含 keyword/alias match、explicit genre fallback、inferred genre fallback；全部未命中时会抛 `StorySystemRoutingError`，不是静默 fallback。
- `references/csv/题材与调性推理.csv` 当前实际 route rows 是 26 条；测试应覆盖真实 CSV 全量 rows，不写死 26 或 27。
- `references/genre-profiles.md` 已定位为 fallback，高频题材主链已迁入 Story Contracts。

## 核心设计边界

### 1. 两个命名空间不能混淆

统一 resolver 不代表只有一个输出值。必须显式区分：

- `canonical_genre`：用于 CSV 检索、Story System、裁决规则、新项目 `project_info.genre`。
- `template_files`：用于 init 加载 `templates/genres/*.md`。

典型冲突：

- 旧 init 行为：`玄幻 -> 修仙.md`。
- 旧 reference 行为：`resolve_genre("玄幻") -> 玄幻`。

新 resolver 必须同时表达这两件事：

```python
GenreResolution(
    raw_label="玄幻",
    canonical_genre="玄幻",
    template_files=["修仙.md"],
    matched_labels=["玄幻"],
    route_tags=[],
    trope_tags=[],
    format_tags=[],
    unresolved=[],
    warnings=[]
)
```

### 2. 硬题材枚举

唯一硬枚举继续使用 15 个 canonical：

```text
都市 玄幻 仙侠 奇幻 科幻
历史 悬疑 游戏 古言 现言
幻言 年代 种田 快穿 衍生
```

这些值用于：

- CSV `适用题材`
- `裁决规则.csv` 的 `题材`
- Story System 的 `canonical_genre`
- `reference_search.py --genre`
- 新项目 `state.json.project_info.genre`

### 3. Taxonomy Index

新增 `webnovel-writer/references/taxonomy/genre-index.csv`。它不是单纯模板清单，而是用户输入层的唯一 taxonomy 数据真源。

建议字段：

```csv
label,canonical_genre,label_type,template_file,route_tags,trope_tags,format_tags,aliases,notes
修仙,玄幻,preset,修仙.md,,,,"玄幻;玄幻修仙;修仙/玄幻;修真","preserve old init: 玄幻 loads 修仙.md"
都市脑洞,都市,platform,都市脑洞.md,都市脑洞,,,"都市奇闻",
高武,都市,platform,高武.md,高武,,,"都市高武",
电竞,游戏,platform,电竞.md,游戏电竞,,,"电竞文;游戏电竞",
直播文,现言,format,直播文.md,,,直播文,"直播;直播带货;主播",
克苏鲁,悬疑,preset,克苏鲁.md,克苏鲁,,,"克系;克系悬疑",
规则怪谈,悬疑,route,规则怪谈.md,规则怪谈,,,"规则动物园;规则类",
知乎短篇,现言,format,知乎短篇.md,,,知乎短篇,"知乎体;盐选;小程序短篇",
历史古代,历史,platform,历史古代.md,历史古代,,,"",
青春甜宠,现言,platform,青春甜宠.md,青春甜宠,,,"青春",
游戏体育,游戏,platform,游戏体育.md,游戏体育,,,"网游;竞技;体育",
民国言情,年代,platform,民国言情.md,民国言情,,,"",
武侠,历史,legacy,,,,,,legacy without template
```

规则：

- 每个 `templates/genres/*.md` 必须在 index 中有且只有一行 `template_file` 指向它。
- `label` 与 `aliases` 使用同一查找空间，必须唯一，不能映射到多个 canonical。
- `aliases` 使用 `;` 分隔；如字段含逗号，必须用 CSV 引号包裹。
- 不带模板文件的 platform/legacy alias 也必须进入 index，不能留在 Python 硬编码字典里。
- `canonical_genre` 必须属于 15 canonical 或 `全部`。
- `label_type` 取值建议：`canonical`、`platform`、`route`、`trope`、`format`、`preset`、`legacy`。
- 不再单独设 `template_type`，避免与 `label_type` 重叠；模板用途由 `label_type` 与 tag 列共同表达。
- `GENRE_PROFILE_KEY_ALIASES` 暂不迁入 index。它输出的是英文 profile section key，与 canonical/template 命名空间不同；Phase 1-5 只迁移输入 alias，保留 profile key 映射并重命名/注释清楚。

### 4. Resolver Contract

新增共享 loader/resolver，例如 `scripts/genre_taxonomy.py`：

```python
GenreResolution(
    raw_label="知乎短篇风的规则怪谈",
    canonical_genre="悬疑",
    matched_labels=["规则怪谈", "知乎短篇"],
    template_files=["规则怪谈.md", "知乎短篇.md"],
    route_tags=["规则怪谈"],
    trope_tags=[],
    format_tags=["知乎短篇"],
    unresolved=[],
    warnings=[]
)
```

兼容原则：

- `reference_search.resolve_genre()` 保留为 wrapper，只返回 canonical 或原值，用于现有调用点。
- `_normalize_genre_key()` 不再拥有 alias 字典；如果暂时保留，只能委托 taxonomy resolver 返回首个 `template_file` 的 stem。
- `data_modules/genre_aliases.py` 不再维护 `GENRE_INPUT_ALIASES`；只保留 profile key 映射，或通过 taxonomy 先得到 template/profile lookup label。
- Story System 不改变 `_route()` 的 route table 匹配语义，只把输入 canonical 化能力接到同一 wrapper。
- loader 使用缓存，例如 `functools.lru_cache`，避免高频路径重复读 CSV。

### 5. Resolver 匹配算法

Phase 1.5 必须先定义并测试算法，不靠隐式行为：

1. 归一化输入：trim、全角/半角符号统一、大小写无关、去除多余空白。
2. 分隔符拆 token：支持 `+`、`＋`、`/`、`、`、`,`、`，`、`|`、`与`。
3. exact match 优先：token 命中 `label` 或任一 alias 时直接加入匹配结果。
4. longest substring match 兜底：对完整原始输入按 label/alias 长度倒序扫描，支持 `知乎短篇风的规则怪谈` 这种复合自然语言输入。
5. 去重与冲突处理：
   - 同一 `template_file` 只保留一次。
   - `route/platform/canonical/preset` 优先决定 `canonical_genre`。
   - `format/trope` 可追加 tags 和模板，但不应压过 route/platform 的 canonical。
   - 多个高优先级标签指向不同 canonical 时，返回 `warnings=["ambiguous_canonical"]`；init 交互层应展示推断结果并允许用户确认。
6. 未匹配片段进入 `unresolved`，wrapper 保持旧行为：`resolve_genre()` 返回原值而不是直接报错。

## State Schema

新 init 项目写入：

```json
{
  "project_info": {
    "genre": "悬疑",
    "genre_label": "知乎短篇风的规则怪谈",
    "genre_tags": {
      "route": ["规则怪谈"],
      "trope": [],
      "format": ["知乎短篇"],
      "templates": ["规则怪谈", "知乎短篇"]
    }
  }
}
```

兼容读取顺序：

1. `project_info.genre`
2. `project_info.genre_label`
3. legacy `project.genre`
4. 配置 fallback

写入新项目时不再新增顶层 `project.genre`。

## 改动范围

### 必改

- `templates/genres/*.md`
  - H1 标题中文化。
  - 不移动文件。
- `references/taxonomy/genre-index.csv`
  - 覆盖 37 个模板。
  - 覆盖 `PLATFORM_TO_CANONICAL`、`_LEGACY_GENRE_MAP`、`_normalize_genre_key()`、`GENRE_INPUT_ALIASES` 的 label/alias 集合。
- `scripts/genre_taxonomy.py`
  - 新增共享 CSV loader/resolver。
- `scripts/reference_search.py`
  - 删除硬编码 `PLATFORM_TO_CANONICAL` 与 `_LEGACY_GENRE_MAP`。
  - `resolve_genre()` 改为调用 taxonomy wrapper。
- `scripts/init_project.py`
  - init 时用 taxonomy 解析用户原始题材。
  - `project_info.genre` 写 canonical。
  - 读取模板时按 `template_file` 加载 preset，不再按原始输入精确拼路径。
- `scripts/data_modules/genre_aliases.py`
  - 移除 `GENRE_INPUT_ALIASES`。
  - 保留并注释 `GENRE_PROFILE_KEY_ALIASES`，说明它属于 fallback profile key 命名空间。
- `scripts/data_modules/context_manager.py`
  - 当前是 `project.genre` 优先；改为 `project_info.genre` / `genre_label` 优先，legacy `project.genre` 兜底。
- `scripts/data_modules/memory_contract_adapter.py`
  - 当前不读 `project_info`；增加 `project_info.genre` / `genre_label` 到 fallback 链，并把 legacy `project.genre` 放最后。
- `skills/webnovel-init/SKILL.md`
  - 主体题材只展示 15 canonical。
  - 修正 legacy `project.genre` shell snippet。
  - 说明可输入 preset/套路/形式，但运行时会映射到 canonical。
- `skills/webnovel-plan/SKILL.md`
  - 修正所有 legacy `project.genre` shell snippet。
- `skills/webnovel-write/SKILL.md`
  - 修正 legacy `project.genre` shell snippet。
- `skills/webnovel-review/SKILL.md`
  - 修正 legacy `project.genre` shell snippet。
- `templates/output/state-schema.md`
  - 加入 `project_info.genre_label` 与 `project_info.genre_tags` 示例。
- `scripts/validate_csv.py`
  - 增加 taxonomy index 双向校验。
  - 增加三份旧字典到 index 的 symmetric diff 校验。
- 相关测试
  - `reference_search` resolver 兼容测试。
  - `init_project` state/schema/template 加载测试。
  - Story System 真实 CSV route 端到端测试。
  - 所有 SKILL.md 读取 `genre` 的 grep/fixture 校验。

### 应改

- `references/csv/genre-canonical.md`
  - 明确 `题材与调性推理.csv` 的 `题材/流派` 是 route tag，不是 canonical enum。
- `references/csv/README.md`
  - 补充 taxonomy index、template preset、canonical 的关系。
- `references/index/reference-loading-map.md`
  - 更新 init 阶段题材模板加载规则。
- `references/genre-profiles.md`
  - 把 `project.genre` 文档表述修正为 `project_info.genre`，并标注 fallback 定位。

### 暂不改

- 不大规模重写 9 张核心 CSV 内容。
- 不删除 37 个模板。
- 不把 `templates/genres/` 立即拆成 `canonical/` 和 `presets/` 子目录。
- 不批量迁移用户已有项目的 `state.json`，只提供兼容读取。
- 不把 `genre-profiles.md` 重新升级为主真源。
- 不在 Phase 1-5 迁移 `GENRE_PROFILE_KEY_ALIASES` 到 index；它属于 profile fallback 命名空间，后续单独评估。

## 分阶段计划

### Phase 1: Taxonomy Index 与模板校验

范围：

- 新增 `references/taxonomy/genre-index.csv`。
- 覆盖现有 37 个模板文件。
- 把以下集合全部纳入 index 的 `label` 或 `aliases`：
  - `GENRE_CANONICAL` 15 项和 `全部`。
  - `PLATFORM_TO_CANONICAL` 34 keys。
  - `_LEGACY_GENRE_MAP` 27 keys。
  - `_normalize_genre_key()` 15 keys。
  - `GENRE_INPUT_ALIASES` 15 keys。
  - 37 个模板文件 stem。
- index 可用一行承载多个 alias，所以不要求 92 行，但要求 coverage 集合无遗漏。
- 所有模板 H1 中文化，去掉英文括号。
- 新增校验：
  - 实际 `templates/genres/*.md` 数量与 index `template_file` 双向一致。
  - 每个 `template_file` 存在且唯一。
  - 每个 `canonical_genre` 属于 15 canonical 或 `全部`。
  - 每个 `label`/`alias` 唯一，不能映射到多个 canonical。
  - 旧字典 keys 与 index label/alias 做 symmetric diff，diff 必须为空或显式列入 allowlist。

不改运行逻辑。

验证：

```powershell
(Get-ChildItem -Path webnovel-writer\templates\genres -Filter *.md | Measure-Object).Count
python -X utf8 webnovel-writer\scripts\validate_csv.py
```

### Phase 1.5: Resolver Contract 先落地

范围：

- 新增共享 taxonomy loader/resolver。
- 定义结构化 `GenreResolution`。
- 实现并测试第 5 节的 exact + longest substring 匹配算法。
- 给 `reference_search.resolve_genre()`、`init_project` 模板解析、`genre_aliases` profile key lookup 写清楚委托关系。
- 明确 `GENRE_PROFILE_KEY_ALIASES` 保留在 `genre_aliases.py`，但输入 alias 来源改为 taxonomy。
- 在测试中先证明旧行为不丢：
  - `PLATFORM_TO_CANONICAL` 原有用例全部通过 index resolver。
  - `_LEGACY_GENRE_MAP` 原有用例全部通过 index resolver。
  - `_normalize_genre_key()` 原 alias 用例全部能解析到相同模板文件。
  - `GENRE_INPUT_ALIASES` 原 alias 用例全部能得到相同 profile lookup label。

这一阶段的目标是拆掉“多真源”的设计风险，再进入调用点迁移。

### Phase 2: 迁移运行时调用点

范围：

- `reference_search.py` 删除硬编码映射，改用 taxonomy。
- `init_project.py` 删除本地 alias 字典，按 `GenreResolution.template_files` 加载模板。
- `story_system_engine.py` 保持 `_route()` 的 keyword/alias/fallback/exception 顺序，内部 canonical resolve 改用同一 wrapper。
- `genre_aliases.py` 输入 alias 迁移到 taxonomy，profile key 只处理 profile section/key 兼容。
- 增加 lint/grep，禁止新增 `PLATFORM_TO_CANONICAL`、`_LEGACY_GENRE_MAP`、`GENRE_INPUT_ALIASES` 这类硬编码输入 dict。

验证：

- `都市日常 -> 都市`
- `宫斗宅斗 -> 古言`
- `玄幻言情 -> 幻言`
- `规则怪谈 -> 悬疑`
- `网游 -> 游戏`
- `玄幻 -> canonical 玄幻，同时 init 模板选中修仙.md`
- `克系 -> canonical 悬疑或按 index 配置，同时 init 模板选中克苏鲁.md`
- `知乎短篇风的规则怪谈 -> canonical 悬疑，同时模板包含规则怪谈.md 和 知乎短篇.md`

### Phase 3: Init 写入与 schema 消费者修正

范围：

- `init_project.py` 写入 `project_info.genre`、`project_info.genre_label`、`project_info.genre_tags`。
- `skills/webnovel-init/SKILL.md`、`skills/webnovel-plan/SKILL.md`、`skills/webnovel-write/SKILL.md`、`skills/webnovel-review/SKILL.md` 的 genre 读取改为：
  - `project_info.genre` 优先。
  - `project_info.genre_label` 可作为展示/诊断。
  - legacy `project.genre` 兜底。
- `memory_contract_adapter.py` 与 `context_manager.py` 同样改为 `project_info` 优先。
- 更新 `templates/output/state-schema.md`。

兼容策略：

- 老项目只含 `project.genre` 时继续可读。
- 新项目不再写 `project.genre`。
- 非 canonical 老值通过 taxonomy resolver 兼容，不直接崩溃。

验证：

- init 新项目 state schema 测试。
- 四个 SKILL.md 中 shell snippet 的读取逻辑测试或 grep 校验。
- memory/context fallback 测试。

### Phase 4: Story System 真实 CSV 端到端验证

范围：

- 增加真实 CSV route 覆盖测试，使用 `webnovel-writer/references/csv/题材与调性推理.csv`。
- 对每个 route row：
  - 如果 `关键词` / `意图与同义词` / `题材别名` 有值，取第一个可用 alias 作为 query，断言 `_route()` 不抛异常，且通常为 `keyword_or_alias_match`。
  - 如果 alias 字段为空，则用 `题材/流派` 或 `canonical_genre` 作为 explicit genre fallback 输入，断言不抛异常。
- 断言：
  - 不抛 `StorySystemRoutingError`。
  - `route.canonical_genre` 属于 15 canonical。
  - `route.genre_filter == route.canonical_genre`，除非 canonical 是空或 `全部`。
  - 未知 query + 未知 genre 仍应抛 `StorySystemRoutingError`，保持现有失败语义。
- 当前真实 CSV 是 26 rows，但测试应按实际行数动态覆盖，不写死 26 或 27。

验证：

```powershell
$env:PYTHONUTF8='1'; python -m pytest webnovel-writer\scripts\data_modules\tests\test_story_system_engine.py -q --no-cov
$env:PYTHONUTF8='1'; python -m pytest webnovel-writer\scripts\data_modules\tests\test_story_system_cli.py -q --no-cov
```

### Phase 5: Skill 与文档收口

范围：

- `webnovel-init/SKILL.md`
  - 主体题材展示 15 canonical。
  - preset/套路/形式用示例说明，不混入硬枚举。
- `webnovel-plan/SKILL.md`、`webnovel-write/SKILL.md`、`webnovel-review/SKILL.md`
  - 确认 genre snippet 均为 `project_info` 优先。
- `references/csv/genre-canonical.md`
  - 明确 canonical、route tag、trope tag、format tag 的边界。
- `references/csv/README.md`
  - 写明 CSV 只接受 canonical，taxonomy index 负责用户输入层。
- `references/index/reference-loading-map.md`
  - 更新模板加载规则。
- `references/genre-profiles.md`
  - 明确 fallback 触发条件。

### Phase 6: 可选目录重构

只有前五阶段稳定后再做。

目标结构：

```text
templates/genres/
  index.csv
  canonical/
    都市.md
    玄幻.md
  presets/
    都市异能.md
    规则怪谈.md
    知乎短篇.md
```

这一步路径影响大，必须单独提交。

## genre-profiles.md Fallback 规则

`genre-profiles.md` 只在以下场景使用：

1. 老项目没有 Story Contracts，无法从 `.story-system` 取得 route/profile。
2. `story_contracts.master.route.primary_genre` 为空，且 protagonist/state fallback 有 genre。
3. 用户显式启用了 legacy profile fallback。

目标优先级：

1. Story Contracts 的 route/profile。
2. `project_info.genre_label` 或 `project_info.genre` 经 taxonomy resolve 后的结果。
3. legacy `project.genre`。
4. 配置项 fallback genre。

`genre_profile_excerpt` 只能作为补充 context，不能覆盖 Story System contract 的 route 决策。

## 建议提交拆分

1. `docs(genres): address taxonomy plan review`
2. `chore(genres): add taxonomy index and normalize headings`
3. `feat(genres): add taxonomy resolver`
4. `refactor(genres): migrate genre resolution call sites`
5. `feat(init): persist canonical genre and genre tags`
6. `docs(genres): update skill and csv taxonomy guidance`
7. 可选：`refactor(genres): split canonical and preset templates`

## 风险与控制

- 风险：CSV index 变成又一份真源。
  控制：Phase 2 必须删除 Python 硬编码输入映射，并加 grep/lint 防回潮。

- 风险：模板命名空间与 canonical 命名空间混淆。
  控制：`GenreResolution` 同时返回 `canonical_genre` 与 `template_files`，调用点只取自己需要的字段。

- 风险：`玄幻 -> 修仙.md` 这类历史行为丢失。
  控制：在 index 中显式建模，并加回归测试。

- 风险：`系统流`、`知乎短篇` 等默认 canonical 有争议。
  控制：index 中标注 `label_type`；init 交互层展示推断结果，用户不同意时可显式指定 canonical。

- 风险：Story System route 被 resolver 行为变化破坏。
  控制：Phase 4 使用真实 `题材与调性推理.csv` 全量 route rows 做端到端测试，并保留未知输入抛错语义。

- 风险：schema 读取点漏改，继续读 `project.genre`。
  控制：Phase 3 增加四个 SKILL.md、memory/context 的 grep 校验和兼容读取测试。

- 风险：`GENRE_PROFILE_KEY_ALIASES` 孤立。
  控制：Phase 1-5 明确保留它，但移除输入 alias；文件注释清楚它只服务 fallback profile key。

## 完成标准

- 37 个模板全部有 index 映射，且 index 与实际文件双向一致。
- index 覆盖旧映射和模板 stem 的 label/alias 集合，symmetric diff 为空或仅有显式 allowlist。
- 所有模板标题纯中文。
- `PLATFORM_TO_CANONICAL`、`_LEGACY_GENRE_MAP`、`GENRE_INPUT_ALIASES` 不再以硬编码输入 dict 存在。
- `_normalize_genre_key()` 不再维护本地 alias。
- `GENRE_PROFILE_KEY_ALIASES` 的归属已明确，且不与 canonical/template resolver 混用。
- `reference_search.py`、`init_project.py`、`genre_aliases.py` 使用同一 taxonomy resolver 作为输入归一真源。
- 新 init 项目写入 canonical `project_info.genre`，并保存 `genre_label` 与 `genre_tags`。
- 老项目 `project.genre` 仍可兼容读取，但不是新写入 schema。
- 所有 SKILL.md 中 genre 读取均为 `project_info.genre` 优先。
- 真实 Story System route CSV 全量端到端测试通过，未知输入仍抛 `StorySystemRoutingError`。
- `validate_csv.py`、prompt integrity 与全量 pytest 通过。
