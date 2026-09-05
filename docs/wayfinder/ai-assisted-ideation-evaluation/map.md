# AI 辅助 Ideation 评审

## Goal

让 AI 承担可回链的七维初评与独立复核，Robert 负责工程决策；在现有 evaluation/comparison 工作流中减少人工负担，保留对材料不足、模型分歧和科学结论范围的诚实表达。

规格：[AI 辅助 Ideation 评审规格](../../agents/ai-assisted-ideation-evaluation-spec.md)。

## Decisions so far

- 2026-09-05：Robert 批准 AI 评审方向，要求简约但保证必要的质量与效果；本会话仅设计，编码交其他 agent。
- 2026-09-05：Robert 明确批准三票顺序与依赖，以及 evaluation CLI 和 comparison ingestion/reduction 两个验收边界；不新增 UI。
- 两位评审独立、证据可回链、允许未决；没有第三模型投票或必需的专家平台。小样本 smoke 不被写成跨领域效果证明。
- 使用仓库已配置的 Local Markdown Issue Tracker；frontmatter 的 open/closed 与 blocked_by 决定 frontier，ready-for-agent 作为 triage 标记，不替换 status 语义。
- 2026-09-05：[交付单条 idea 的 AI 评审与证据卡](tickets/01-deliver-single-idea-ai-evaluation.md) — 单评审模式离线编码验收完成：pinned `single-review-v1` 模板与 authoring contract v2 版本族、匿名确定性材料包、`user_supplied` 响应导入、引用逐字核验、七维枚举 + `insufficient_evidence` 弃权、write-once 记录与中文证据卡；19 项新测试、全量 806 passed、v1 人工流程零改动；真实 smoke 未执行，需费用/出站授权。

## Tickets

1. [交付单条 idea 的 AI 评审与证据卡](tickets/01-deliver-single-idea-ai-evaluation.md)
2. [交付独立复核与稳定的成对盲评](tickets/02-deliver-independent-and-pairwise-review.md)
3. [接入比较流程并保留当前矩阵证据](tickets/03-integrate-comparison-and-migrate-current-matrix.md)

## Not yet specified

无阻断离线编码的产品问题。真实 provider/model 配置、出站材料与费用批准属于执行输入，运行前记录；模型效果未验证前不声称已合格。
