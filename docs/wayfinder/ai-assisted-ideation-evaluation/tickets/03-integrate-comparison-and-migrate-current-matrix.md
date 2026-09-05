---
title: 接入比较流程并保留当前矩阵证据
type: implementation
status: open
assignee: null
blocked_by:
  - 02-deliver-independent-and-pairwise-review.md
---

**Triage:** ready-for-agent

## Parent

[AI 辅助 Ideation 评审规格](../../../agents/ai-assisted-ideation-evaluation-spec.md)

## What to build

把 v2 AI Evaluation Artifact 与稳定 pair 结果接入既有 comparison ingestion/reduction，让 Robert 不再逐条代写 AI verdict；保留旧人工模式。已完成但未决的评审可被记账并继续收集后续样本，同时对相关质量门槛维持未决。

交付当前矩阵的兼容迁移：剩余生成继续运行于原 pin 的 clean worktree，新的 post-seal 评估独立版本化；保留 slot 1、冻结命令与旧成本。首先追加评估职责与 Promotion Proposal 修订，明确首条输出之后修改评审协议的证据限度，再接入运行行为。代码交付包含离线迁移 rehearsal 和可执行操作手册，不以完成剩余付费 runs 为验收前提。

## Acceptance criteria

- [ ] v2 与旧人工模式通过明确版本分支进入 coverage/ingestion；不生成冒用 Robert 的旧 artifact，不放松其他 seal/input/export/admission 校验。
- [ ] coverage 区分缺失、无效、完成已决和完成未决；完成未决可继续后续 slot，但不能制造质量通过；缺失与无效仍不能 ingest。
- [ ] 新的评估 protocol manifest 绑定材料版本、prompt、模型、汇总规则与评估代码；跨协议混用在 reduction 拒绝。
- [ ] pair 完整性、稳定结果与七维质量底线共同决定建议；Robert 的接受/拒绝与 AI 作者记录分离。
- [ ] 现有 Proposal 的原始预注册记录保留，修订不移动胜负、domain-method fit、质量和回归阈值；明确本轮为首条输出后的评估方法修订。
- [ ] 只有获批准的修订版 Gate 能消费相应 AI 结果；旧 Gate 继续拒绝。没有真实 smoke 验收不能正式启用，但不阻断离线实现。
- [ ] 生成端继续通过原 pin 的 production admission 与冻结命令运行；评估端变化不修改 slot 1 admission、seal 或 idea，不自动 supersede pin 或重跑现有 run。
- [ ] 私有材料按现有相对布局和哈希在隔离工作区交接；一个权威 ledger 串行推进；中断后可核对哪份状态最新，不允许双端重复计费或跳 slot。
- [ ] 临时工作区完整 rehearsal 证明旧生成 pin、新评估模式、评估后 ingestion/记账、下一 slot 顺序检查及 reduction 可协作；当前漂移工作区的旧 runner 仍拒绝启动。
- [ ] 评审实际费用单列，不改写生成费用；向 Robert 展示合并口径和未授权支出，不静默扩展旧预算。
- [ ] 全量 pytest 及相关 CLI/comparison 集成验证通过；提供真实迁移前置条件、操作顺序、失败保留方式和恢复说明。保留未推送状态，不部署、不自动晋升。

## Blocked by

- [交付独立复核与稳定的成对盲评](02-deliver-independent-and-pairwise-review.md)

## Handoff

正式执行仍需已批准的评估修订、已通过的真实 smoke、可用 provider 配置及现有逐 run 费用确认。用户把本票交给编码 agent 不等于授权其发起剩余所有付费生成。
