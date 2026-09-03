---
title: Approve one Target Reference Corpus
type: implementation
status: open
assignee: null
blocked_by:
  - 02-approve-one-workshop-file.md
---

# 03: Approve one Target Reference Corpus

**What to build:** 让 Robert 能从 target-reference membership 与已冻结 authority evidence 构建、验证并批准一个 self-contained Target Reference Corpus；同一流程能够对当前全部 targets 做确定性预处理验证，但不运行模型。

**Blocked by:** 02: Approve one Workshop File.

**Status:** ready-for-agent

**Contract anchors:** [Freeze literature before ideation](../../ideation-pipeline/tickets/003-freeze-literature-before-ideation.md), [Audit metadata gaps and enrichment sources](../../ideation-pipeline/tickets/016-audit-metadata-gaps-and-enrichment-sources.md), [Define the frozen corpus contract](../../ideation-pipeline/tickets/019-define-the-frozen-corpus-contract.md), [Understand dataset routing metadata](../../ideation-pipeline/tickets/033-understand-dataset-routing-metadata.md).

- [ ] 每个 case 的 canonical corpus、manifest、machine-replayable validation report 与 private evidence 自包含，并以 opaque `case_id` 和 exact membership/hashes 绑定。
- [ ] Reference Content 使用真实 source type、status、text hash 与 field-level provenance；target contexts、intents、influence 与 dynamic ranking fields 被 quarantine。
- [ ] Validator 对全部 error 条款 fail closed、不自动修复；optional metadata 缺口保留为 warning，failed/successful build attempts 均不可覆盖。
- [ ] 同一 source、membership、versions 与 rules 重建得到相同 corpus/bundle identity；当前全部 targets 的 deterministic preprocessing validation 可完成且不发模型请求。
- [ ] 交付 `VM-CONTRACT-019-01`、`VM-CONTRACT-019-02`、`VM-REPLAY-02` 与 `VM-LEAKAGE-04`，并保持全部已有测试通过。
- [ ] 脱敏记录输入 identities、命令、pass/fail、warnings 与 hashes，且 Robert 完成本票验收。
