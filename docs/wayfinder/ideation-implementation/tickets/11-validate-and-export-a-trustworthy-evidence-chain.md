---
title: Validate and export a trustworthy Evidence Chain
type: implementation
status: completed
assignee: null
blocked_by:
  - 10-suspend-and-resume-an-interrupted-ideation-run.md
---

# 11: Validate and export a trustworthy Evidence Chain

**What to build:** 让 operator 能验证并按 positive allowlist 导出一个 sealed Evidence Chain，让开发期 offline verifier 能从 recorded evidence 证明 replay determinism，同时证明跨 run/path 访问、覆盖式 attempt 与 corrupt evidence 无法伪装成可信输入或可提交产物。

**Blocked by:** 10: Suspend and resume an interrupted Ideation Run.

**Status:** completed

**Contract anchors:** [Retain auditable run evidence](../../ideation-pipeline/tickets/010-retain-auditable-run-evidence.md), [Trust layered validation and isolated runs](../../ideation-pipeline/tickets/011-trust-layered-validation-and-isolated-runs.md), [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md).

- [x] Validator 证明 event chain、seal、inventory、artifacts 与 canonical hashes 完整；missing/hash mismatch/broken chain/invalid event 等 corruption 被稳定判定。
- [x] Corrupt run 保留原证据，但不能 repair、resume、seal、export、replay、evaluation 或 promotion；合法 recorded evidence 只进入批准的开发期 offline replay verifier，不成为其他 Ideation Run 的 runtime input 或 parent relation。
- [x] Exact-run、exclusive-create、path 与 symlink guards 拒绝 `latest`/glob、absolute/parent/backslash escape、跨 run 读写和复用其他 run bytes。
- [x] Sanitized exporter 从空对象按 allowlist 构造，并通过 schema、canonical/linkage、forbidden key/path/credential/target scans；失败不留下可提交 root。
- [x] Immutable attempt/worker 语义覆盖 runtime 与保留的 ranking comparison evidence；重跑不能覆盖既有 attempt。
- [x] 交付 `VM-CONTRACT-023-02`、`VM-CONTRACT-023-03`、`VM-LEAKAGE-03`、`VM-ISOLATION-01`、`VM-ISOLATION-02` 与 `VM-ISOLATION-03`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，记录脱敏 validation/export evidence，且 Robert 完成本票验收。
