---
title: Freeze the paid-run-ready prompt Canary package
type: task
status: closed
assignee: null
blocked_by:
  - 01-admit-and-replay-one-versioned-prompt-profile.md
  - 02-reduce-one-blinded-cross-domain-prompt-comparison.md
---

# 03: Freeze the paid-run-ready prompt Canary package

**What to build:** 在 runtime 与 offline comparison boundary 都通过后，从已批准 12-case Canary 确定性冻结 4-pair/8-run 私有 comparison package，完成输入批准、命令、盲法、ledger、Proposal 002 hashes 与 clean handoff；到达第一个可能发起 DeepSeek request 的边界时停止并交回 originating session。

**Blocked by:** 01: Admit and replay one versioned Prompt Profile; 02: Reduce one blinded cross-domain prompt comparison.

**Status:** closed (2026-09-04)

**Specification:** [Cross-domain Ideation Prompt qualification](../../../agents/cross-domain-ideation-prompt-spec.md).

- [x] 从当前 hash-pinned、Robert-approved 12-case Canary selection 中按规格确定性选出四个 cluster 各一例；验证每个 case 的 Approved Workshop 与 Approved Target Reference Corpus、当前 bytes/hash、freshness 与 prior-use 状态，不读取或发布 Target contribution。
- [x] 产生 write-once private selection manifest 与 Robert approval artifact，记录 source Canary identity、四类覆盖、canonical tie-break、input hashes、profile ids/hashes、固定 `high/32768/1-generation/3-reflections` 配置及零结果选择声明；tracked docs 只记录 aggregate 与 SHA-256。
- [x] 产生 8-run frozen matrix、2/2 balanced execution order、2/2 balanced blind mapping、0.00 CNY spend ledger、result slots、pair-packet destinations、verdict/reveal/reducer state 与 exact credential-free commands；所有 artifacts 重放为 byte-identical，交叉 hash 闭合。
- [x] 每条命令通过生产 parser/launcher 的零网络可执行性检查，使用项目 `.env` wrapper 但不读取、打印或复制 key；禁止自动费用批准、provider probe、`new-run` admission、`resume` 或任何会创建 live Evidence Chain 的动作。
- [x] 将 Proposal 002 补全为 Plan Gate 候选：记录 exact private artifact hashes、当前代码 commit、dependency lock、验证矩阵行、非权威成本预测、5 CNY 重审批阈值、30 CNY 硬上限及 next-run reservation；state 保持 `proposed`，等待 Robert 回到 originating session 后审批当前官方价格与 Plan Gate。
- [x] Proposal 001、旧 035 24-run matrix 和旧 commands 明确标记 withdrawn/inactive，保留原 bytes 与 0 runs/0.00 CNY 事实；ticket 035 保持 open 但 execution-paused，不能 claim、resume、close 或从旧准备中选 reasoning-effort winner。
- [x] 更新 Canary/Scale Gate 和相关 contract pointers，使执行顺序固定为 Prompt Proposal 002 qualification → Promotion Gate → 新 Design Epoch reasoning-effort proposal；challenger rejected/inconclusive 时 035 继续暂停，绝不回退到已知目标错配的付费 baseline。
- [x] 全量运行 pytest、compileall、目标范围 Black、import/dependency、diff、credential-shape、private/tracked boundary、hash replay 和 Standards/Spec review；提交脱敏 readiness 报告，说明 shellcheck 等不可用检查而不虚构结果。
- [x] 关闭三票并把 map 标为 closed only if 所有 acceptance criteria 通过、所有 commits 已记录、工作树 clean、tracked/private boundaries 无泄漏且 private ledger actual spend 仍为 0.00 CNY。
- [x] 交付一份自含 handoff，列出 clean HEAD、artifact hashes、验证结果、第一条 frozen command、预估/硬上限、Plan Gate 未批准与逐 run `yes` 要求；随后停止，等待 Robert 回 originating session，绝不发起付费 run 或 Downstream Experiment。

## 闭环记录 (2026-09-04)

- **物化清单**: 私有 comparison package 冻结于 `artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/`，包含 `selection-manifest.json`、`selection-approval.json`、`run-matrix.json`、`blind-mapping.json`、`spend-ledger.json` 与 `commands.txt`。
- **账本与预算**: 账本初始支出为 0.00 CNY，5.00 CNY 为累计实际支出重审批阈值，Canary 阶段唯一硬上限为 30.00 CNY（剩余 29.86 CNY），每个 run 前预留 7.08 CNY peak worst-case bound。
- **零网络可执行性**: 8 条 guarded slot 命令全部通过 outer-command 与生产 inner `new-run` parser 严格校验（无 `--reasoning-effort`/`--max-tokens` 违规参数），零网络、零真实请求、零费用。
- **Proposal 002 与 035 状态**: Proposal 002 完整呈现 Plan Gate 候选状态（`state: proposed`）；旧 035 物料标记为 inactive。整个工作流在首个 live provider request 边界前安全悬挂，交回 Robert 决策。

## 对抗性审查修复记录 (2026-09-04, post-close)

> 以下为 commit `3428909` 后首次重冻结的历史状态；v1.1 ledger/commands 已由后文“付费前重冻结记录”的 v1.2 物料取代，仅作为失败演进证据保留。

- Commit `3428909` 落地后按新 schema 重新冻结私有 `spend-ledger.json`：账本升级 `comparison-spend-ledger-v1.1.0`，纳入不变的 0.14 CNY 历史 smoke 支出（`historical_spend_cny=0.14`、`total_stage_spend_cny=0.14`、`comparison_actual_spend_cny=0.00`、`plan_gate_subcap_cny=5.00`、`canary_hard_cap_cny=30.00`、`status=initialized`），新 SHA-256 为 `bec52349eb53b0328cafd67f152d25ce43e2b7e90ad0d1fbbf3f69fd01f03f29`。重冻结流程：先如实触发预期 `PACKAGE_DRIFT`（旧 ledger bytes 与新 schema 不符），删除旧账本后重建，其余五项 artifact 经字节自检零漂移。
- 其余五项冻结 artifact（`selection-manifest.json` / `selection-approval.json` / `run-matrix.json` / `blind-mapping.json` / `commands.txt`）复验字节稳定，SHA-256 与 Proposal 002 记录完全一致；`run-matrix.json` 自 pin（`frozen_matrix_digest` = `c60d72…`）不变。
- Proposal 002 的冻结 hash 清单与 Plan Gate 记录已同步：新 SHA-256、v1.1.0 schema、矩阵级严格不等式 consult 语义与 4.86 CNY tracked 剩余预算。

## 付费前重冻结记录 (2026-09-04, post-close)

- Originating session 的独立 preflight 证明 v1.1.0 `5.00 CNY` subcap 只能在费用发生后拒绝 ingest，且 8 条命令直接进入 `new-run`，没有请求前 aggregate reservation；Robert 批准在零 provider call 边界内修正。
- 受影响的旧 `spend-ledger.json` 与 `commands.txt` 已原样移动到私有 `superseded/v1.1.0-budget-contract/`：旧 SHA-256 分别仍为 `bec52349eb53b0328cafd67f152d25ce43e2b7e90ad0d1fbbf3f69fd01f03f29` 与 `be30d7d81a4aaf6e2b388c122a1d167a6258a50a289119e4cd7b73564ad2ce2a`，未删除或覆盖。
- 新 `spend-ledger.json` 为 `comparison-spend-ledger-v1.2.0`，SHA-256 `56562175984e4a99a4eb734cb1fc6c88527afb1059bc31fc62da1b3093f35d3f`；现行 `commands.txt` SHA-256 `3851ca37ed6fdc9fe2c634238d865693db4f3663859f9d1c6bcedc2b62664af6`。selection manifest、selection approval、run matrix、blind mapping 四项 SHA-256 完全不变。
- 首版 v1.2 self-pin-only `commands.txt`（SHA-256 `0cde44509078974fa43bd79414000f252645c293ff7dee53d8bb8e71558db905`）已原样归档到私有 `superseded/v1.2.0-self-pin-only-command/`；现行命令额外携带 run-matrix file SHA-256 与 5.00 CNY threshold 外部 pin，防止 matrix/ledger 协同改写绕过冻结合同。
- 新命令路径固定为 project credential wrapper → `scripts/run-prompt-comparison-slot` → 请求前 matrix/ledger/slot/budget 校验 → exclusive-create `0600` reservation → 同进程 exec production `new-run`。测试验证越序、外部 pin/opening-balance 漂移与重复 reservation 均在 exec/network 前拒绝。
