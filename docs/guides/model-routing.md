# 模型路由操作卡（S11 / D5）

> 目标：审查（reviewer）、事实提取（data-agent）、写前研究（context-agent）三个子代理路由到便宜模型，正文起草保持当前模型——对标 AI_NovelGenerator 的分阶段模型路由。
> 适用宿主：ZCode / Claude Code（插件 agent 的 frontmatter `model` 字段是宿主读取的路由点）。

## 现状

- 三个子代理的 frontmatter 均为 `model: inherit`（跟随主会话模型）——质量基线，也是默认回滚值。
- 宿主侧（`~/.zcode/cli/config.json`）**没有**按 agent 覆写模型的配置键（2026-08-30 核实）；唯一路由点是插件 agent 文件的 frontmatter。

## 切换步骤（每代理一行改动）

1. 选定宿主可用的便宜模型标识：在 ZCode **Settings → Subagents** 查看当前生效的 agent 与可用模型；或用你账号已知的低价档模型名。
2. 编辑三个文件的首行 frontmatter（`projects/claude-plugins/webnovel-writer/webnovel-writer/agents/` 下）：
   - `reviewer.md`、`data-agent.md`、`context-agent.md`
   - 把 `model: inherit` 改为 `model: <便宜模型标识>`
3. 重启 ZCode（或 `/reload-plugins`）后生效。
4. **回滚**：三处改回 `model: inherit` 即可，无数据迁移。

## 冒烟验证（改完必做）

1. 跑一次 `/webnovel-review <N>`（或任意会触发 reviewer 的流程）——子代理能正常派发、返回合规 JSON 即通过；若派发失败，说明模型标识不被宿主接受，回滚。
2. 对比 token-meter 统计：`/tokens last 5` 查看切换前后每轮消耗。

## 质量抽检协议（验收口径）

- 同一章正文，分别在 `inherit` 与便宜模型下各跑一次 reviewer；
- 人工比对两份问题清单：阻断类问题（事实矛盾/连续性硬伤）是否同等检出；
- 抽检通过 → 保留路由；漏检阻断问题 → 该代理回滚 `inherit`（宁可贵不可漏）。
- 建议顺序：先路由 `data-agent`（结构化提取，风险最低）→ `reviewer` → `context-agent`。

## 成本预期

- 参考实测（fantasy01 第 35 章，均为 inherit）：context-agent 618k / data-agent 467k / reviewer 262k，三代理合计 134.8 万 tokens/章。
- 若三代理切到约 1/5 单价的模型，理论节省约 **100 万 tokens/章的等值成本**；以 D1 章级计量实测为准。
