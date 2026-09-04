---
title: Validate and export a trustworthy Evidence Chain
type: implementation
status: closed
assignee: Robert
blocked_by:
  - 10-suspend-and-resume-an-interrupted-ideation-run.md
---

# 11: Validate and export a trustworthy Evidence Chain

**What to build:** 让 operator 能验证并按 positive allowlist 导出一个 sealed Evidence Chain，让开发期 offline verifier 能从 recorded evidence 证明 replay determinism，同时证明跨 run/path 访问、覆盖式 attempt 与 corrupt evidence 无法伪装成可信输入或可提交产物。

**Blocked by:** 10: Suspend and resume an interrupted Ideation Run.

**Status:** closed

**Contract anchors:** [Retain auditable run evidence](../../ideation-pipeline/tickets/010-retain-auditable-run-evidence.md), [Trust layered validation and isolated runs](../../ideation-pipeline/tickets/011-trust-layered-validation-and-isolated-runs.md), [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md).

- [x] Validator 证明 event chain、seal、inventory、artifacts 与 canonical hashes 完整；missing/hash mismatch/broken chain/invalid event 等 corruption 被稳定判定。
- [x] Corrupt run 保留原证据，但不能 repair、resume、seal、export、replay、evaluation 或 promotion；合法 recorded evidence 只进入批准的开发期 offline replay verifier，不成为其他 Ideation Run 的 runtime input 或 parent relation。
- [x] Exact-run、exclusive-create、path 与 symlink guards 拒绝 `latest`/glob、absolute/parent/backslash escape、跨 run 读写和复用其他 run bytes。
- [x] Sanitized exporter 从空对象按 allowlist 构造，并通过 schema、canonical/linkage、forbidden key/path/credential/target scans；失败不留下可提交 root。
- [x] Immutable attempt/worker 语义覆盖 runtime 与保留的 ranking comparison evidence；重跑不能覆盖既有 attempt。
- [x] 交付 `VM-CONTRACT-023-02`、`VM-CONTRACT-023-03`、`VM-LEAKAGE-03`、`VM-ISOLATION-01`、`VM-ISOLATION-02` 与 `VM-ISOLATION-03`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，记录脱敏 validation/export evidence，且 Robert 完成本票验收。

## Resolution

2026-09-04 agent 交付并经全面对抗性审查验收通过后关闭。核心落地：

- `evidence.py` 实现静态校验器 `validate_evidence_chain`：核验 request/admission/events/seal 完整性、单调递增哈希链、终态一致性、artifact inventory 全量存在性/哈希/长度匹配、检查未清空 staging 与符号链接，违规统一判定 `RUN_CORRUPT`；损坏的 run 保留原证据，绝不就地修复，且拒绝 resume/seal/export/replay。
- `evidence.py` 实现正向白名单脱敏导出器 `export_sanitized_evidence`：仅从空字典按正向白名单构造 `manifest.json` 与 `events.json`，原子重命名提交（在 `evidence/ideation-runs/.staging-<uuid>` 暂存），失败绝不留下半成品根目录；重复导出已存在产物保证 byte-identical 幂等，存在未登记文件或被篡改时 `EXPORT_EXISTS_MISMATCH` 阻断。
- 发布门禁扫描器深度防护：拦截提示词与中间推理私有字段（`prompt`, `messages`, `response`, `reasoning`, `idea` 等）；全面封堵全平台绝对路径（POSIX `/` 与 Windows `C:\`、`D:/`）、路径遍历及私有路径片段（`artifacts/ideation-runs`, `data/raw`）；扫描凭证与活跃 API Key；提取 `target_papers.csv`（包含 `paperId`、DOI、Title、URL、externalIds）敏感身份进行防泄露扫描。
- 跨 Run 与路径防攻击强化：`RunStore` 强制拒绝跨 run 读写（`CROSS_RUN_ACCESS_DENIED`），拒绝 `latest`/glob，`write_artifact` 深度排查路径各级与末端叶节点符号链接（`SYMLINK_FORBIDDEN`）；`admission.py` 在准入入口全面拦截指向 `artifacts/ideation-runs/` 的输入路径（`CROSS_RUN_INPUT_FORBIDDEN`）。
- Attempt 具备不可变 write-once 语义（重跑不能覆盖既有 attempt，`ARTIFACT_EXISTS`）；实现离线验证器 `replay_recorded_run` 证明已记录证据的决定论。
- CLI 增加 `validate` 与 `export` 子命令，对接标准结构化输出与退出码。

验收证据（2026-09-04，全零网络零费用）：全量 pytest 569 passed（新增 25 项全量通过）；`compileall` 与 `black` 检查通过；覆盖破坏性坏链注入、正向白名单脱敏、敏感泄露排查、跨 Run 隔离、全攻击集防御与决定论重放。脱敏摘要见 [evidence-chain-validation-export-evidence.md](../../../research/evidence-chain-validation-export-evidence.md)。
