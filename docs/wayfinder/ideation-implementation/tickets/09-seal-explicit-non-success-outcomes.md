---
title: Seal explicit non-success outcomes
type: implementation
status: review
assignee: Robert
blocked_by:
  - 08-correct-model-fixable-actions.md
---

# 09: Seal explicit non-success outcomes

**What to build:** 让完整 control loop 对 Idea Leakage、全 run 无非空 Retrieval Result、retriever/evidence boundary failure 与其他确定性失败产生可解释的 terminal `failed` seal，并保证 terminal 条件不会被较低优先级的模型可修复错误掩盖。

**Blocked by:** 08: Correct model-fixable actions.

**Status:** ready-for-agent

**Contract anchors:** [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Define the idea quality rubric](../../ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md), [Define the declared grounding contract](../../ideation-pipeline/tickets/038-define-the-declared-grounding-contract.md).

- [x] Finalization gate 固定按 raw-submission hygiene、structure、Declared Grounding、within-run duplicate 顺序执行，每轮只报告最高优先级结果。
- [x] Hygiene pattern 命中立即产生可信度受损的 terminal failure；它不能被 parse/structure/grounding feedback 覆盖或让模型修复后继续。
- [x] Run-level no-nonempty-retrieval backstop、确定性 adapter/retriever/evidence failures 与合法 `budget_exhausted` generations 汇总成批准的 Terminal Outcome 和 seal inventory。
- [x] Scripted malformed/unknown action、grounding lie、hygiene hit、duplicate 与 retrieval backstop scenarios 都从真实 CLI/controller seam 抵达预期终点。
- [x] 交付 `VM-CONTRACT-025-02`、`VM-CONTRACT-026-02`、`VM-INTEGRATION-03`、`VM-LEAKAGE-02` 与 `VM-FAULT-04`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，记录脱敏 failure evidence（参见 [non-success-outcomes-evidence.md](../../../research/non-success-outcomes-evidence.md)），且 Robert 完成本票验收。

## Resolution

2026-09-03 经 agent 交付，Robert 验收前状态 `review`。核心落地：

- `FinalizeIdea` gate 重排为固定优先级 hygiene → structure → grounding → duplicate（`ai_scientist/ideation/controller.py`），每轮只报最高优先级一个结果；hygiene scan 对 raw submission bytes 执行，命中即 `hygiene_hit` 事件 + `hygiene-violation.json` 私有 artifact + 立即 terminal `failed` seal，不产生任何模型可见反馈。
- 版本化 hygiene 模式列表 `payload-hygiene-patterns-v1.0.0` 从 023/024 标识符格式推导（case_id 形、SHA-256 hex、UUIDv4、run trust roots、内部证据子树、lifecycle 文件名）；检索 `paper_id`（40-hex）明确不命中。
- Terminal `failed` 封闭词汇三类：controller（hygiene/corrupt/backstop）、provider（022 taxonomy terminal 行）、retriever_evidence（020 boundary/audit 码）；未知 reason fail closed。sealed failed 携带完整 artifact inventory 与 terminal 事件（payload 带 `reason_code`/`reason_kind`/disposition 计数）。
- Suspend 类 adapter 失败保持上抛、不 seal（Run Suspension 归 ticket 10）；合法 `budget_exhausted` generations 在 failed seal 的 `terminal_summary` 中如实保留。
- Run-level retrieval backstop 由抛异常改为 seal terminal `failed`（025 批准的 terminal 语义），`tests/test_sealed_ideation_run.py` 对应断言同步更新。