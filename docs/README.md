# 文档中心

`docs/` 目录按功能分区整理，方便查阅。

## 目录索引

### 架构

- [`architecture/overview.md`](./architecture/overview.md)：系统架构、Agent 分工、Story System 设计
- [`architecture/plugin-runtime-hardening-spec-2026-06-04.md`](./architecture/plugin-runtime-hardening-spec-2026-06-04.md)：基于优秀 Claude Code 插件调研的运行时可靠性重构 spec
- [`architecture/plugin-runtime-hardening-plan-2026-06-04.md`](./architecture/plugin-runtime-hardening-plan-2026-06-04.md)：运行时可靠性重构实施计划、修改范围与影响分析
- [`architecture/multi-agent-adaptation-spec-2026-06-05.md`](./architecture/multi-agent-adaptation-spec-2026-06-05.md)：基于 v6.1.0 现状的多宿主与多智能体适配 spec
- [`architecture/context-minimal-writing-flow-plan-2026-06-05.md`](./architecture/context-minimal-writing-flow-plan-2026-06-05.md)：Skills / Agents / References 上下文减负、读取方式与 token 优化重构计划（v3）
- [`archive/architecture/current-system-diagnosis.md`](./archive/architecture/current-system-diagnosis.md)：历史系统状态诊断

### 使用指南

- [`guides/commands.md`](./guides/commands.md)：Skill 命令与 CLI 子命令速查
- [`guides/rag-and-config.md`](./guides/rag-and-config.md)：RAG 检索链路、环境变量与配置
- [`guides/genres.md`](./guides/genres.md)：37 个题材模板与复合题材规则

### 运维

- [`operations/operations.md`](./operations/operations.md)：项目目录结构、运维命令、备份恢复
- [`operations/plugin-release.md`](./operations/plugin-release.md)：插件发版流程与版本同步

### 项目状态与待办（当前入口）

- [`zcode/v8-gap-review-3rounds/README.md`](./zcode/v8-gap-review-3rounds/README.md)：v8.0.0 后 41 项功能缺口 + 4 阶段 11 任务修复计划——**当前待办入口**
- [`cursor/项目复审/2026-09-04-项目复审报告.md`](./cursor/项目复审/2026-09-04-项目复审报告.md)：v8.0.0 发版后全项目复审（P0/P1/P2 + 建议执行顺序）
- [`plans/2026-08-25-status-and-pending-work.md`](./plans/2026-08-25-status-and-pending-work.md)：`[superseded]` v6.3.0 时期的状态清单，只作历史

### 方案集（按任务成套：spec / plan / ledger / 审计）

- [`zcode/webnovel-copilot-300/`](./zcode/webnovel-copilot-300/README.md)：v8「作者主权 + 300 章连贯」八件方案文档（01 需求 → 08 实施计划）
- [`zcode/zcode-native-adaptation/`](./zcode/zcode-native-adaptation/README.md)：v7.1 ZCode 原生化 spec / plan / ledger + 装卸手册
- [`zcode/writing-quality-review/`](./zcode/writing-quality-review/README.md)：写作质量机制审计与路线图
- [`zcode/v8-migration-gap-audit/`](./zcode/v8-migration-gap-audit/README.md)：v6→v7/v8 功能继承缺口审计（28 项）
- [`cursor/`](./cursor/)：Cursor 宿主产出（审查报告 / 分析），按任务名分目录

### 报告与决策

- [`reports/`](./reports/)：S 系列专项复盘（预算配额、设定卡验证、v7 垂直切片、配额时机）与 2026-09-02 全面审阅 / 增量审阅
- [`decisions/`](./decisions/)：ADR（多宿主适配立项）
- [`tasks/architecture-audit-fix-ledger.md`](./tasks/architecture-audit-fix-ledger.md)：架构审计修复台账
- 根下 [`full-project-analysis-2026-08-24.md`](./full-project-analysis-2026-08-24.md) / [`full-project-analysis-v2-2026-08-24.md`](./full-project-analysis-v2-2026-08-24.md) / [`code-review-2026-08-24.md`](./code-review-2026-08-24.md)：2026-08-24 三份分析（历史）

### 记忆系统

- [`memory/long-term-memory-architecture-v2.md`](./memory/long-term-memory-architecture-v2.md)：长期记忆架构说明

### 研究与外部方案

- [`research/long-term-memory-research-report.md`](./research/long-term-memory-research-report.md)：长期记忆论文与开源方案调研
- [`research/storyteller-paper-summary.md`](./research/storyteller-paper-summary.md)：STORYTELLER 论文总结

### 归档

- [`archive/superpowers/README.md`](./archive/superpowers/README.md)：历史架构 spec 与设计文档导航

## 分类原则

- `architecture/`：系统结构与技术架构
- `guides/`：使用者需要查阅的命令、配置、题材说明
- `operations/`：运维、发版、备份与恢复
- `memory/`：长期记忆架构说明
- `research/`：论文总结与外部方案调研
- `reports/` / `plans/` / `decisions/`：工作区统一四类（分析报告 / 实施计划 / ADR）
- `zcode/<任务名>/`、`cursor/<任务名>/`：按宿主与任务成套的方案集与产出
- `archive/`：历史架构快照、spec 与设计计划

## 推荐阅读顺序

1. 先看 [`../README.md`](../README.md) 了解安装与基本使用
2. 再看 [`architecture/overview.md`](./architecture/overview.md) 了解整体架构
3. 需要配置检索时看 [`guides/rag-and-config.md`](./guides/rag-and-config.md)
4. 需要使用命令时看 [`guides/commands.md`](./guides/commands.md)
5. 排查运行问题时看 [`operations/operations.md`](./operations/operations.md)
