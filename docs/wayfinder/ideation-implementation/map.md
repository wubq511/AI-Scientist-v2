---
title: Implement the Auditable Ideation-Only Pipeline
label: wayfinder:map
status: open
---

# Implement the Auditable Ideation-Only Pipeline

## Authority

- [Implementation specification](../../agents/ideation-pipeline-spec.md)
- [Validation Matrix](../../agents/validation-matrix.md)
- [Delivery and Handoff](../../agents/delivery-and-handoff.md)

Ticket frontmatter is authoritative for status and blocking edges. Each ticket is a tracer-bullet implementation slice, and every acceptance set cites the Validation Matrix rows it delivers. Tickets 035/036 remain in the planning map for Canary-stage parameter decisions and are not duplicated here.

## Tickets

1. [Establish the testable ideation foundation](tickets/01-establish-the-testable-ideation-foundation.md)
2. [Approve one Workshop File](tickets/02-approve-one-workshop-file.md)
3. [Approve one Target Reference Corpus](tickets/03-approve-one-target-reference-corpus.md)
4. [Admit an Ideation Run without paid work](tickets/04-admit-an-ideation-run-without-paid-work.md)
5. [Return one audited BM25 Retrieval Result](tickets/05-return-one-audited-bm25-retrieval-result.md)
6. [Record one validated DeepSeek model round](tickets/06-record-one-validated-deepseek-model-round.md)
7. [Seal one grounded Ideation Run](tickets/07-seal-one-grounded-ideation-run.md)
8. [Correct model-fixable actions](tickets/08-correct-model-fixable-actions.md)
9. [Seal explicit non-success outcomes](tickets/09-seal-explicit-non-success-outcomes.md)
10. [Suspend and resume an interrupted Ideation Run](tickets/10-suspend-and-resume-an-interrupted-ideation-run.md)
11. [Validate and export a trustworthy Evidence Chain](tickets/11-validate-and-export-a-trustworthy-evidence-chain.md)
12. [Evaluate every finalized idea after seal](tickets/12-evaluate-every-finalized-idea-after-seal.md)
13. [Contract the legacy path and prove handoff readiness](tickets/13-contract-the-legacy-path-and-prove-handoff-readiness.md)

## Decisions so far

- [Establish the testable ideation foundation](tickets/01-establish-the-testable-ideation-foundation.md)：以三类精确依赖合同、入口传递 import allowlist、Python 3.13 clean-environment 全量 pytest 与逐字节 CLI baseline 建立零 runtime 行为漂移的可测试地基。
- [Approve one Workshop File](tickets/02-approve-one-workshop-file.md)：以离线 prepare/validate/approve 三阶段生命周期隔离、严格四段 canonical rendering、exact/normalized/8-token leakage 确定性门禁与独立评审人九项语义检查建立零泄露、带不可篡改 attempt provenance 的 Workshop 审批边界。
- [Approve one Target Reference Corpus](tickets/03-approve-one-target-reference-corpus.md)：以生命周期隔离的 build/validate/approve 流程、冻结权威证据政策（修复 3 篇损坏摘要与 18 条缺失 venue 警告）、全量 fail-closed 11 项确定性检验器与严格 Quarantine 隔离建立自包含的语料审批边界，并完成全量 237 个 Targets 的离线零成本预处理验证。
- [Admit an Ideation Run without paid work](tickets/04-admit-an-ideation-run-without-paid-work.md)：以七参数 new-run CLI、exclusive-create run root、canonical write-once request/admission 与连续 hash chain 事件、versioned CNY 价格表（hash pin + 峰谷时段）及 exact-`yes` 交互批准建立九步 fail-closed 准入边界；任何 preflight 失败留存 `preflight_rejected` 证据且无 admission、无付费路径，入口 import 副作用消除。
