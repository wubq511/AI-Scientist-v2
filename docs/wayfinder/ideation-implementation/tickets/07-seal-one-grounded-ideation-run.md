---
title: Seal one grounded Ideation Run
type: implementation
status: closed
assignee: Robert
blocked_by:
  - 05-return-one-audited-bm25-retrieval-result.md
  - 06-record-one-validated-deepseek-model-round.md
---

# 07: Seal one grounded Ideation Run

**What to build:** 用 deterministic adapter fixture 打通一个完整 happy path：admission 后保留 baseline generation/reflection loop，经 SearchLiterature 获得 evidence，提交七字段 idea 与 Declared Grounding，立即持久化 accepted idea，最后产生 `success` Run Seal。

**Blocked by:** 05: Return one audited BM25 Retrieval Result; 06: Record one validated DeepSeek model round.

**Status:** closed

**Contract anchors:** [Preserve a compatible baseline](../../ideation-pipeline/tickets/006-preserve-a-compatible-baseline.md), [Separate idea payloads from evidence](../../ideation-pipeline/tickets/008-separate-idea-payloads-from-evidence.md), [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Define the declared grounding contract](../../ideation-pipeline/tickets/038-define-the-declared-grounding-contract.md).

- [x] 外层 generation、内层 reflection、per-generation history 与每轮一次 model call/一个 action outcome 保持批准的 baseline 语义。
- [x] Model-visible action surface 只有 `SearchLiterature` 与 `FinalizeIdea`；Finalized idea 仍为七字段 payload，grounding 与 evidence 存 sidecar。
- [x] Happy path 的 lifecycle、generation/round、operation/attempt events 连续且只引用 immutable artifacts；accepted idea 在进入下一 generation 前完成原子 commit。
- [x] `reasoning_effort`、`max_tokens` 与 Workshop rendering version 只有受控、versioned、Run-Specification-pinned 的 seam，本票不选择 Canary 胜者。
- [x] 交付 `VM-INTEGRATION-01`，并为后续完整 FinalizeIdea contract tests 保留同一 CLI/controller seam；全部已有测试继续通过。
- [x] 本票只用 deterministic fixtures、零真实模型费用；同步受影响的仓库运行说明，记录脱敏 evidence，且 Robert 完成本票验收。
