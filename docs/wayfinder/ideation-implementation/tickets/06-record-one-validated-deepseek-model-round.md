---
title: Record one validated DeepSeek model round
type: implementation
status: open
assignee: null
blocked_by:
  - 04-admit-an-ideation-run-without-paid-work.md
---

# 06: Record one validated DeepSeek model round

**What to build:** 让 controller 通过 DeepSeek-only adapter 和 recorded/stub transport 完成一个 model round，得到经过 provider-contract 验证的 typed result 或 typed failure、独立 Provider Attempts、usage/cost evidence 与可重放 artifact；本票不发真实请求。

**Blocked by:** 04: Admit an Ideation Run without paid work.

**Status:** ready-for-agent

**Contract anchors:** [Choose the DeepSeek provider and version contract](../../ideation-pipeline/tickets/031-choose-the-deepseek-provider-and-version-contract.md), [Define the DeepSeek adapter contract](../../ideation-pipeline/tickets/022-define-the-deepseek-adapter-contract.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md).

- [ ] Adapter 固定 approved DeepSeek direct/non-streaming Chat Completions/model/tool boundary，caller 只能提供批准的 messages、controlled parameters、output mode 与 opaque user identity。
- [ ] Provider success、usage invariants、reasoning/content separation、serialization 与 centralized redaction 按合同执行，SDK object 和 credential 不越过 adapter boundary。
- [ ] 每个 physical request 产生独立 Provider Attempt；批准的 transient classes 最多重试一次，ambiguous 与 deterministic failures 不隐藏重试或降级。
- [ ] 封闭 failure taxonomy 与 controller disposition 查表一致；recorded response 重放产生相同 canonical artifacts/hashes。
- [ ] 交付 `VM-UNIT-07`、`VM-CONTRACT-022-01`、`VM-CONTRACT-022-02`、`VM-CONTRACT-022-03`、`VM-REPLAY-01` 与 `VM-FAULT-01`，并保持全部已有测试通过。
- [ ] 本票零 network、零真实模型费用；同步受影响的仓库运行说明，记录脱敏 evidence，且 Robert 完成本票验收。
