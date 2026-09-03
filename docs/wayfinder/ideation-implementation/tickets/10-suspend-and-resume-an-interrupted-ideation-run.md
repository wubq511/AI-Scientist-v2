---
title: Suspend and resume an interrupted Ideation Run
type: implementation
status: open
assignee: null
blocked_by:
  - 09-seal-explicit-non-success-outcomes.md
---

# 10: Suspend and resume an interrupted Ideation Run

**What to build:** 让 environment/storage failure 或 SIGINT/SIGTERM 把 run 留在可解释的 unsealed suspension；operator 只凭 exact `run_id` 验证证据、重新批准剩余成本、提升 writer epoch、重建控制态并继续到与无中断执行等价的 Evidence Chain。

**Blocked by:** 09: Seal explicit non-success outcomes.

**Status:** ready-for-agent

**Contract anchors:** [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md).

- [ ] 每个 operation 通过 run-local staging、durability、hash、rename 与 event append 原子承诺；中断不会留下半承诺 evidence。
- [ ] Approved environment/transport/storage failures suspend 且不 seal；确定性 failure 不能走 resume 路径。
- [ ] Resume CLI 只接受 exact `run_id`，全量验证 canonical evidence，从 events/artifacts 而非 projection 重建 generation、round、history、grounding eligibility 与 in-flight operation。
- [ ] Resume 记录新 writer epoch 与 write-once cost approval；approved orphan 窗口只 quarantine 并记 incident，其他损坏不在本票中被“修复”。
- [ ] 交付 `VM-REPLAY-04`、`VM-FAULT-02` 与 `VM-FAULT-03`，并保持全部已有测试通过。
- [ ] 同步受影响的仓库运行说明，记录脱敏 interruption/resume evidence，且 Robert 完成本票验收。
