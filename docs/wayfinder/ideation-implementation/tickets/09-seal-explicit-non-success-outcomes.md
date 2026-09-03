---
title: Seal explicit non-success outcomes
type: implementation
status: open
assignee: null
blocked_by:
  - 08-correct-model-fixable-actions.md
---

# 09: Seal explicit non-success outcomes

**What to build:** 让完整 control loop 对 Idea Leakage、全 run 无非空 Retrieval Result、retriever/evidence boundary failure 与其他确定性失败产生可解释的 terminal `failed` seal，并保证 terminal 条件不会被较低优先级的模型可修复错误掩盖。

**Blocked by:** 08: Correct model-fixable actions.

**Status:** ready-for-agent

**Contract anchors:** [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Define the idea quality rubric](../../ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md), [Define the declared grounding contract](../../ideation-pipeline/tickets/038-define-the-declared-grounding-contract.md).

- [ ] Finalization gate 固定按 raw-submission hygiene、structure、Declared Grounding、within-run duplicate 顺序执行，每轮只报告最高优先级结果。
- [ ] Hygiene pattern 命中立即产生可信度受损的 terminal failure；它不能被 parse/structure/grounding feedback 覆盖或让模型修复后继续。
- [ ] Run-level no-nonempty-retrieval backstop、确定性 adapter/retriever/evidence failures 与合法 `budget_exhausted` generations 汇总成批准的 Terminal Outcome 和 seal inventory。
- [ ] Scripted malformed/unknown action、grounding lie、hygiene hit、duplicate 与 retrieval backstop scenarios 都从真实 CLI/controller seam 抵达预期终点。
- [ ] 交付 `VM-CONTRACT-025-02`、`VM-CONTRACT-026-02`、`VM-INTEGRATION-03`、`VM-LEAKAGE-02` 与 `VM-FAULT-04`，并保持全部已有测试通过。
- [ ] 同步受影响的仓库运行说明，记录脱敏 failure evidence，且 Robert 完成本票验收。
