---
title: Correct model-fixable actions
type: implementation
status: open
assignee: null
blocked_by:
  - 07-seal-one-grounded-ideation-run.md
---

# 08: Correct model-fixable actions

**What to build:** 让同一 generation 遇到可修复的 parse、action、arguments、FinalizeIdea structure、retriever input、Declared Grounding 或 duplicate 错误时，把最小可操作反馈送入下一 reflection round，而不是静默 break、print-only 或污染其他 generation。

**Blocked by:** 07: Seal one grounded Ideation Run.

**Status:** ready-for-agent

**Contract anchors:** [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Define the idea quality rubric](../../ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md), [Define the declared grounding contract](../../ideation-pipeline/tickets/038-define-the-declared-grounding-contract.md).

- [ ] FinalizeIdea 使用封闭两键对象、七字段非空 typed idea 与 duplicate-free per-generation grounding；unknown/missing/invalid content 不被静默修复。
- [ ] 所有批准的 Model-Fixable Error 作为该轮唯一 action result 回灌并消耗一轮；反馈最小、稳定且不暴露内部 path/hash/stack。
- [ ] Declared Grounding 三个 error codes 与 per-generation eligibility 精确实现；下一 attempt 从完整 gate 起点重验。
- [ ] 近重复 idea 可修复；reflection 预算耗尽产生 `budget_exhausted` Generation Disposition，而不是伪造 idea 或终止整个 run。
- [ ] 交付 `VM-CONTRACT-024-03`、`VM-CONTRACT-025-01`、`VM-CONTRACT-026-01` 与 `VM-INTEGRATION-02`，并保持全部已有测试通过。
- [ ] 同步受影响的仓库运行说明，记录脱敏 run fixture evidence，且 Robert 完成本票验收。
