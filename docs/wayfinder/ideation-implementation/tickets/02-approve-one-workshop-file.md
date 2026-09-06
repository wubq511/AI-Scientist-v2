---
title: Approve one Workshop File
type: implementation
status: closed
assignee: codex
blocked_by:
  - 01-establish-the-testable-ideation-foundation.md
---

# 02: Approve one Workshop File

**What to build:** 让 Robert 能从一个 Target Paper 的允许字段与候选 draft 出发，得到 canonical、identity-free、两层验证通过且带完整私有 provenance 的 Approved Workshop；失败 candidate 作为 rejected attempt 留存，不能进入 Ideation Run。

**Blocked by:** 01: Establish the testable ideation foundation.

**Status:** accepted

**Contract anchors:** [Prevent Target Paper idea leakage](../../ideation-pipeline/tickets/007-prevent-target-paper-idea-leakage.md), [Understand target-to-workshop semantics](../../ideation-pipeline/tickets/014-understand-target-to-workshop-semantics.md), [Define the Workshop File contract](../../ideation-pipeline/tickets/018-define-the-workshop-file-contract.md), [Define the validation and test matrix](../../ideation-pipeline/tickets/027-define-the-validation-and-test-matrix.md).

- [x] Offline preparation 只把 Target Paper title 与 raw abstract 作为 derivation source；其他私有字段只用于验证，不能成为 model-visible content。
- [x] Workshop 使用获批四段 canonical rendering、opaque case identity 与独立 private manifest，并记录 immutable derivation/validation attempts。
- [x] Deterministic gate 覆盖 schema、bytes、identity 与 exact/normalized/n-gram leakage；independent semantic decision 与 derivation attempt 分离。
- [x] 任一 gate 失败只产生 rejected draft，不产生 Approved Workshop，也不回退到 raw abstract、旧 Workshop、cluster-only 或其他 case 输入。
- [x] 交付 `VM-UNIT-01`、`VM-UNIT-04`、`VM-CONTRACT-018-01`、`VM-CONTRACT-018-02` 与 `VM-LEAKAGE-01`，并保持全部已有测试通过。
- [x] 脱敏记录 fixtures、规则版本、命令、pass/fail 与 hashes，且 Robert 完成本票验收。

## Implementation Evidence

- 实现 commits：`c51d68b add: implement Workshop approval boundary`、`c7c8367 fix: harden Workshop approval contract`、`11e5cb6 fix: enforce frozen Workshop preparation`。
- 证据与进展 commit：`6ca3d3f add: record workshop approval evidence and progress`。
- 脱敏证据与 smoke 摘要：[Workshop approval boundary 验证证据](../../../research/workshop-approval-evidence.md)。
- 阻断矩阵行 `VM-UNIT-01`、`VM-UNIT-04`、`VM-CONTRACT-018-01`、`VM-CONTRACT-018-02` 与 `VM-LEAKAGE-01` 已全部通过；Robert 明确授权进行审查验收并关闭本票。

## Resolution

已建立严格隔离的离线 Workshop 准入与审批边界：
1. 稳定 CLI 入口 `python -m ai_scientist.prepare_ideation_inputs workshop {prepare,validate,approve}`，生命周期严格隔离在 `preparation.py`、`validation.py` 与 `approval.py`；
2. Preparation 阶段只允许 Target Paper `title` 与 raw `abstract` 作为 authoring source，其他私有字段（`abstract_summary`、identifiers、reference `contexts`）隔离在私有验证包中；
3. 严格执行四段 canonical rendering（UTF-8, NFC, LF, 单末尾 newline）与 opaque `case_id` 绑定，封死任何跨 Target 目录篡改与 TOCTOU 窗口；
4. 两层门禁完整闭环：确定性门禁覆盖 schema、bytes、opaque identity 与三层 leakage（exact、normalized、8-token overlap）；独立评审人 9 项语义检查与 derivation actor 严格互斥；任一失败仅留存不可篡改的 rejected attempt，绝不 fallback 或生成 Approved Workshop；
5. Python 3.13.7 clean environment 全量 288 tests 通过（专项 30 tests），Black 校验触及 12 个文件全部 unchanged，compileall 零报错，所有 fixtures、规则 digest 与命令结果均已脱敏记录入库。未调用模型、未发生网络请求、未进入 downstream。
