---
title: Evaluate every finalized idea after seal
type: implementation
status: open
assignee: null
blocked_by:
  - 11-validate-and-export-a-trustworthy-evidence-chain.md
---

# 12: Evaluate every finalized idea after seal

**What to build:** 让 Robert 在 non-corrupt Run Seal 之后，为每个 finalized idea 组装 private Evaluation Brief、填写七项 categorical judgment、验证为 immutable Evaluation Artifact，并只读核算全部 sealed runs 的 coverage。

**Blocked by:** 11: Validate and export a trustworthy Evidence Chain.

**Status:** ready-for-agent

**Contract anchors:** [Choose IdeaBench evaluation fidelity](../../ideation-pipeline/tickets/032-choose-ideabench-evaluation-fidelity.md), [Define the idea quality rubric](../../ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md), [Define the post-seal evaluation artifact contract](../../ideation-pipeline/tickets/037-define-the-post-seal-evaluation-artifact-contract.md).

- [ ] Assemble 只读取 sealed、non-corrupt run、final idea/grounding/retrieval evidence 与 private Target Paper comparator，生成可重建 brief 和预填 linkage skeleton。
- [ ] Validate 强制 canonical closed schema、hash linkage、七项 approved enums 与非空 rationales、authoring audit 和 linear supersedes；失败 draft 不成为 artifact。
- [ ] 每个 finalized idea 独立计一份 artifact，包括 terminal `failed` run 中已成功 committed 的 ideas；不产生 numeric score、overall score、LLM judgment 或 sanitized stub。
- [ ] Read-only coverage 对 seal inventory 给出 `covered`、`draft_only`、`missing`，不改写 run evidence 或 evaluation artifacts。
- [ ] 交付 `VM-QUAL-01`，并保持全部已有测试通过；Robert 的 verdict 内容本身不作机器判分。
- [ ] 同步受影响的仓库运行说明，记录脱敏 schema/coverage evidence，且 Robert 完成本票验收。
