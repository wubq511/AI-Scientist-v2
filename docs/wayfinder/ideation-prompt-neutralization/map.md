---
title: Qualify a Domain-Neutral Ideation Prompt
label: wayfinder:map
status: closed
---

# Qualify a Domain-Neutral Ideation Prompt

## 当前运行状态（2026-09-06）

Robert 已批准采用 `cross-domain-v1`，并明确抛弃 baseline、不保留回退；`new-run` 默认 cross-domain，baseline 的新建与恢复均退役。原矩阵未通过预注册门槛，采用依据另行披露为 post-evidence-adoption。以下 tickets 与 Decisions 是历史交付记录，当前效力以 [002 裁决记录](../../agents/comparison-002-promotion-criteria.md) 为准。

## Authority

- [Cross-domain Ideation Prompt specification](../../agents/cross-domain-ideation-prompt-spec.md)
- [Promotion Proposal 002](../../agents/promotions/002-cross-domain-ideation-prompt.md)
- [Optimization Promotion Gate](../../agents/promotion-gate.md)
- [Canary and Scale Gates](../../agents/canary-and-scale-gates.md)

Ticket frontmatter is authoritative for status and blocking edges. This effort delivers a paid-run-ready, zero-spend prompt comparison checkpoint. It ends before the first live provider request and does not resume ticket 035.

## Tickets

1. [Admit and replay one versioned Prompt Profile](tickets/01-admit-and-replay-one-versioned-prompt-profile.md)
2. [Reduce one blinded cross-domain prompt comparison](tickets/02-reduce-one-blinded-cross-domain-prompt-comparison.md)
3. [Freeze the paid-run-ready prompt Canary package](tickets/03-freeze-the-paid-run-ready-prompt-canary-package.md)

## Decisions so far

<!-- Add one line per closed ticket. -->
- Ticket 01 (closed 2026-09-04): 封闭、版本化 Prompt Profile seam 落地——`ml-baseline-v1`（字节级 golden 保持生产 baseline）与 `cross-domain-v1`（规格批准的领域中立 challenger）登记入 hash-pinned registry；`new-run` 强制 `--prompt-profile`，v1.1.0 Run Request/Admission pin id/contract-version/bundle-hash/registry-hash；fresh/resume/validation/export 全链同一 profile，legacy v1.0.0 恒解释为 baseline；生产 default 不变，零网络零费用完成。
- Ticket 02 (closed 2026-09-04): 离线 comparison boundary 落地——新模块 `ai_scientist/ideation/comparison.py` 提供四 cluster canonical-hash 选择（pinned 已批准 Canary identity、拒绝 contribution 字段进入选择流）、4 对/8-run frozen matrix（2/2 顺序平衡 + 单变量断言 + self-pin）、frozen blind mapping（2/2 A 侧平衡 + `REVEAL_BLOCKED`/`VERDICT_AFTER_REVEAL` fail-closed reveal gate）、脱敏 pair packet（禁元数据扫描）、credential-free parser-contract 命令、append-only spend ledger（0.00 起；5 CNY 重审批阈值；30 CNY 请求前硬 reservation；Plan Gate ≠ 逐 run）、fail-closed result ingestion（真实 sealed chain 校验 + Evaluation coverage）、write-once verdict（封闭四枚举）与 9 门槛 deterministic reducer；当前 65 个测试含 E2E 与 guarded runner 负向合同，零网络、零 credential、零费用；最终私有 selection manifest 留给 ticket 03。
- Ticket 03 (closed 2026-09-04): 付费运行就绪的 Canary comparison package 冻结——从已批准 12-case Canary 中按规格经确定性 tie-break 选定四跨领域 cases（Materials, Social, Genetics, Health）；在私有目录 `artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/` 物化 6 项冻结 artifacts（清单、批准、8-run 矩阵、平衡双盲、0.00 CNY 花费账本、8 条生产 parser 校验通过命令）与空 vault；Proposal 002 补齐全部私有物料 SHA-256 并设为 `proposed` 等待 Plan Gate 审批；旧 035 标记 inactive 并暂停；保持零网络调用、零真实支出（0.00 CNY），安全悬挂并交回 Robert 决策。
- 对抗性审查修复（commit 3428909）：Plan Gate 改为矩阵级严格实际支出守卫（per-run 7.08 bound 归 admission seam）、账本纳入 0.14 CNY 历史 smoke 支出并在 ingest 强制子上限、pair packet 以 sealed idea hash 绑定证据链、verdict 判据对齐 pair-level 预注册语义、selection 重算 canonical hash 防伪造；spend-ledger 重冻结为 v1.1.0，其余五项冻结物料字节稳定。
- 付费前预算合同修正（Robert 批准，2026-09-04）：确认 v1.1 的 5 CNY 事后 ingest 拒绝不能阻止已发生费用，故升级为 v1.2——5 CNY 明确定义为 observed-spend 重审批阈值，30 CNY 是按 next-run 7.08 CNY peak bound 请求前 reservation 的唯一硬上限；冻结命令改经 `scripts/run-prompt-comparison-slot` 并携带 matrix file SHA-256/threshold 外部 pin，runner 复核 immutable 0.14 CNY opening balance，越序、漂移、重复/并发 slot 在 provider 前 fail closed；旧 ledger/commands 私有 bytes 保留在 `superseded/`，其余四项冻结物料不变，Proposal 002 仍为 `proposed`。
- Execution-code 单变量修正（Robert 批准，2026-09-04，commit `ac34ab7`）：确认 frozen matrix 缺少执行代码 pin，跨 commit 执行会把 runtime 变化混入单变量归因。首个 slot reservation 现在 exclusive-create package 私有 `0600` `execution-code-pin.json`（`comparison-execution-code-pin-v1.0.0`，记录当前 clean Git HEAD）；slot runner 在 exec 前解析 clean HEAD（dirty worktree 以 `DIRTY_WORKTREE` 拒绝）并要求等于 pin；后续 slot 缺 pin 以 `EXECUTION_CODE_PIN_MISSING` 拒绝，commit drift 以 `EXECUTION_CODE_PIN_MISMATCH` 拒绝且不写 reservation；result ingestion 逐 run 比对 sealed `admission.code.commit` 与 pin；pin 并发/重复创建 fail closed，stale pin 永不静默删除，更换 pinned commit 需 Robert 显式批准新 Design Epoch。六项冻结物料 hash 不变，私有 package 复测零状态变化，全量 766 passed。
