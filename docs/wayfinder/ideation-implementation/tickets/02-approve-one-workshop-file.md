---
title: Approve one Workshop File
type: implementation
status: open
assignee: null
blocked_by:
  - 01-establish-the-testable-ideation-foundation.md
---

# 02: Approve one Workshop File

**What to build:** 让 Robert 能从一个 Target Paper 的允许字段与候选 draft 出发，得到 canonical、identity-free、两层验证通过且带完整私有 provenance 的 Approved Workshop；失败 candidate 作为 rejected attempt 留存，不能进入 Ideation Run。

**Blocked by:** 01: Establish the testable ideation foundation.

**Status:** ready-for-agent

**Contract anchors:** [Prevent Target Paper idea leakage](../../ideation-pipeline/tickets/007-prevent-target-paper-idea-leakage.md), [Understand target-to-workshop semantics](../../ideation-pipeline/tickets/014-understand-target-to-workshop-semantics.md), [Define the Workshop File contract](../../ideation-pipeline/tickets/018-define-the-workshop-file-contract.md), [Define the validation and test matrix](../../ideation-pipeline/tickets/027-define-the-validation-and-test-matrix.md).

- [ ] Offline preparation 只把 Target Paper title 与 raw abstract 作为 derivation source；其他私有字段只用于验证，不能成为 model-visible content。
- [ ] Workshop 使用获批四段 canonical rendering、opaque case identity 与独立 private manifest，并记录 immutable derivation/validation attempts。
- [ ] Deterministic gate 覆盖 schema、bytes、identity 与 exact/normalized/n-gram leakage；independent semantic decision 与 derivation attempt 分离。
- [ ] 任一 gate 失败只产生 rejected draft，不产生 Approved Workshop，也不回退到 raw abstract、旧 Workshop、cluster-only 或其他 case 输入。
- [ ] 交付 `VM-UNIT-01`、`VM-UNIT-04`、`VM-CONTRACT-018-01`、`VM-CONTRACT-018-02` 与 `VM-LEAKAGE-01`，并保持全部已有测试通过。
- [ ] 脱敏记录 fixtures、规则版本、命令、pass/fail 与 hashes，且 Robert 完成本票验收。
