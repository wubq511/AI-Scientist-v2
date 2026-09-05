---
title: 接入比较流程并保留当前矩阵证据
type: implementation
status: closed
assignee: null
blocked_by:
  - 02-deliver-independent-and-pairwise-review.md
---

**Triage:** ready-for-agent

## Parent

[AI 辅助 Ideation 评审规格](../../../agents/ai-assisted-ideation-evaluation-spec.md)

## What to build

把 v2 AI Evaluation Artifact 与稳定 pair 结果接入既有 comparison ingestion/reduction，让 Robert 不再逐条代写 AI verdict；保留旧人工模式。已完成但未决的评审可被记账并继续收集后续样本，同时对相关质量门槛维持未决。

交付当前矩阵的兼容迁移：剩余生成继续运行于原 pin 的 clean worktree，新的 post-seal 评估独立版本化；保留 slot 1、冻结命令与旧成本。首先追加评估职责与 Promotion Proposal 修订，明确首条输出之后修改评审协议的证据限度，再接入运行行为。代码交付包含离线迁移 rehearsal 和可执行操作手册，不以完成剩余付费 runs 为验收前提。

## Acceptance criteria

- [x] v2 与旧人工模式通过明确版本分支进入 coverage/ingestion；不生成冒用 Robert 的旧 artifact，不放松其他 seal/input/export/admission 校验。（`_evaluation_coverage_for_run` 双版本分支 `evaluation_artifact_v1`（语义不变）/`evaluation_artifact_v2_ai`；AI 判定文档 `authorship.kind=ai_pair_reduction` 只写入 vault `ai-verdicts/`，绝不生成 v1 人工文档；seal/profile/input/sanitized-export/matrix identity 校验原样——tests/test_comparison_migration_rehearsal.py 人工通道 byte-stability E2E）
- [x] coverage 区分缺失、无效、完成已决和完成未决；完成未决可继续后续 slot，但不能制造质量通过；缺失与无效仍不能 ingest。（`evaluation list-ai-coverage`（`evaluation-ai-review-coverage-v1.0.0`）五态 missing/invalid/unaggregated/complete_resolved/complete_unresolved；ingest 时缺失/无效/未汇总 fail closed（`EVALUATION_ARTIFACT_MISSING`/`EVALUATION_ARTIFACT_INVALID`），complete_resolved/complete_unresolved 可 ingest；manifest `unresolved_blocks_quality_pass=True` + reducer `ai_quality_floor_unresolved` 阻止未决制造质量通过）
- [x] 新的评估 protocol manifest 绑定材料版本、prompt、模型、汇总规则与评估代码；跨协议混用在 reduction 拒绝。（evaluation_protocol.py：protocol id `ai-review-evaluation-protocol-v1`、aggregation `ai-review-aggregation-v1`、prompt `single-review-v2`/`pair-review-v1`、11 项材料 schema 与 `evaluator_binding_sha256`，注册时全部从运行时代码重推导；reduction 无 manifest 或 AI/人工混用 `EVALUATION_PROTOCOL_MISMATCH`，config supersede 后 manifest 加载失败）
- [x] pair 完整性、稳定结果与七维质量底线共同决定建议；Robert 的接受/拒绝与 AI 作者记录分离。（comparison_ai.consume_pair_reduction 只接受恰好一条 complete + stable 的还原记录（`AI_PAIR_REDUCTION_NOT_FOUND`/`_AMBIGUOUS`/`AI_PAIR_NOT_COMPLETE`/`AI_PAIR_NOT_STABLE`），每臂质量底线从双评审共识记录携带；AI 判定存 vault `ai-verdicts/`（`comparison-ai-verdict-v1.0.0`），与 Robert 盲审 `verdicts/` 分离，揭盲后记录 `VERDICT_AFTER_REVEAL`）
- [x] 现有 Proposal 的原始预注册记录保留，修订不移动胜负、domain-method fit、质量和回归阈值；明确本轮为首条输出后的评估方法修订。（002 proposal 追加 versioned addendum 二，只登记消费侧工具与效力边界，判据文本未动；manifest 固定 `EVALUATION_PROTOCOL_REVISION_STATEMENT`（post-first-output revision），reduction `evaluation_protocol` 闸门逐字携带披露）
- [x] 只有获批准的修订版 Gate 能消费相应 AI 结果；旧 Gate 继续拒绝。没有真实 smoke 验收不能正式启用，但不阻断离线实现。（reducer 不传 `ai_verdicts` 时输出与修订前逐字节一致（旧 Gate 继续拒绝 AI 记录）；有 `ai_verdicts` 无 manifest 即 `EVALUATION_PROTOCOL_MISMATCH`。真实六次基础 smoke 已于 2026-09-05 执行并通过（4/4，证据 docs/research/ai-review-real-smoke-evidence.md）；正式激活仍需 Robert 显式批准修订 + 真实迁移执行 + 费用授权——离线交付物已完整）
- [x] 生成端继续通过原 pin 的 production admission 与冻结命令运行；评估端变化不修改 slot 1 admission、seal 或 idea，不自动 supersede pin 或重跑现有 run。（migration 工具全部只读（verify 类），不写 pin、不摸 sealed run；当前主工作区 HEAD `871a813f…` 超 pin，生成侧继续要求 pin worktree（既有 `EXECUTION_CODE_PIN_MISMATCH`/`DIRTY_WORKTREE` 行为保持）；运行手册「明确不做」声明不自动 supersede、不重跑已 seal run）
- [x] 私有材料按现有相对布局和哈希在隔离工作区交接；一个权威 ledger 串行推进；中断后可核对哪份状态最新，不允许双端重复计费或跳 slot。（migration.py：`verify_generation_package_compatibility`（相对布局 + `FROZEN_PACKAGE_FILES` 六文件哈希）、`migration_handoff_manifest`/`verify_handoff_manifest`（往返逐字节核验，缺失 `MIGRATION_HANDOFF_DRIFT`）、`ledger_recency_comparison`（same_state/local_newer/remote_newer，同进度字节歧义 `MIGRATION_LEDGER_AMBIGUOUS` 交 Robert 按 reservation/quarantine 证据裁决）；串行顺序写入 ai-review-migration-runbook 第 3 节）
- [x] 临时工作区完整 rehearsal 证明旧生成 pin、新评估模式、评估后 ingestion/记账、下一 slot 顺序检查及 reduction 可协作；当前漂移工作区的旧 runner 仍拒绝启动。（tests/test_comparison_migration_rehearsal.py 14 项：合成 sealed runs 经 ingestion → `record-comparison-ai-verdict` 写入 vault `ai-verdicts/` → reducer E2E、协议必需拒绝、人工通道 byte-stability、迁移包验证往返+漂移、handoff 往返+缺失检测、ledger recency 同/新/歧义/跨矩阵；漂移工作区拒绝沿袭 VM-CONTRACT-COMPARE-05，runbook 第 2 节要求生成限于 pin worktree）
- [x] 评审实际费用单列，不改写生成费用；向 Robert 展示合并口径和未授权支出，不静默扩展旧预算。（evaluation_costs.py：独立 append-only + hash-linked 台账 `evaluation-cost-ledger-v1.0.0`（call kind `single_review`/`pair_review`/`repair`、physical_call_count、总额重算、并发写检测）；`merged_cost_report`（`evaluation-cost-merged-report-v1.0.0`）生成金额逐字带入 + `unauthorized_spend_disclosure`（评审费用不在生成 Plan Gate 批准范围内）；CLI init/record/report）
- [x] 全量 pytest 及相关 CLI/comparison 集成验证通过；提供真实迁移前置条件、操作顺序、失败保留方式和恢复说明。保留未推送状态，不部署、不自动晋升。（全量 pytest **879 passed**（基线 843 + 13 + 23）；black/compileall/CLI smoke 通过；[ai-review-migration-runbook.md](../../../agents/ai-review-migration-runbook.md) 含前置条件（Robert 批准修订、smoke 证据、provider 配置、逐 run 费用确认、评审预算单列）、两工作区拓扑与六冻结文件哈希、串行纪律、slot 1 处置、失败保留、恢复/回退与「明确不做」；未推送、未部署、未自动晋升）

## Blocked by

- [交付独立复核与稳定的成对盲评](02-deliver-independent-and-pairwise-review.md)

## Handoff

正式执行仍需已批准的评估修订、已通过的真实 smoke、可用 provider 配置及现有逐 run 费用确认。用户把本票交给编码 agent 不等于授权其发起剩余所有付费生成。执行手册见 [ai-review-migration-runbook.md](../../../agents/ai-review-migration-runbook.md)。

## Resolution

2026-09-05 交付（离线编码验收）：

- **评估协议清单**：`ai_scientist/ideation/evaluation_protocol.py` + CLI `evaluation build-evaluation-protocol --out <f>` / `register-evaluation-protocol --manifest-file <f> --registered-by <who>`；write-once `artifacts/evaluations/evaluation-protocol-manifest.json`（`evaluation-protocol-manifest-v1.0.0`，protocol id `ai-review-evaluation-protocol-v1`、aggregation `ai-review-aggregation-v1`、prompt 版本、11 项材料 schema、rubric、abstention policy 与 `evaluator_binding_sha256`），注册从运行时代码重推导，加载重验 config hash（supersede 后 `EVALUATION_PROTOCOL_MISMATCH`），固定 post-first-output `revision_disclosure`。
- **覆盖分支**：`evaluation list-ai-coverage`（`evaluation-ai-review-coverage-v1.0.0`）五态（missing/invalid/unaggregated/complete_resolved/complete_unresolved），与 `aggregate_review` 同级完整性重验；ingestion `_evaluation_coverage_for_run` 双版本分支，missing/invalid/unaggregated fail closed、complete_* 可 ingest、双通道 `EVALUATION_CHANNEL_CONFLICT`。
- **AI 判定通道**：ComparisonVault write-once `ai-verdicts/`（`record_ai_verdict`/`load_ai_verdict`/`ai_verdicts`），schema `comparison-ai-verdict-v1.0.0`，与 Robert 盲审 `verdicts/` 分离，揭盲后 `VERDICT_AFTER_REVEAL`；`validate_ai_verdict_document`/`ai_verdict_to_display`/`ai_verdict_facts`（content-space → 显示臂投影，核验臂 run 绑定，同 packet hash 绑定）。
- **消费链**：`ai_scientist/ideation/comparison_ai.py` `consume_pair_reduction`（定位恰好一条 complete+stable 还原记录、重推导 pair 包与四方向记录、协议绑定 `evaluation-protocol-pin.json`）+ CLI `record-comparison-ai-verdict`；reducer `reduce_prompt_comparison` 新增可选 `ai_verdicts` + `evaluation_protocol`，新闸门 `ai_quality_floor_unresolved`（unresolved/not_evaluated 拒晋升）与 `evaluation_protocol`（披露），AI/人工混用拒绝，无 AI 参数输出逐字节不变。
- **评审费用台账**：`ai_scientist/ideation/evaluation_costs.py` + CLI `init-evaluation-cost-ledger` / `record-evaluation-cost` / `evaluation-cost-report --package-dir <p>`；`evaluation-cost-ledger-v1.0.0` 独立 hash 链接 append-only，`merged_cost_report`（`evaluation-cost-merged-report-v1.0.0`）只读合并 + 未授权支出披露。
- **迁移辅助**：`ai_scientist/ideation/migration.py` `verify_generation_package_compatibility`（CLI `evaluation verify-migration-package --expected-sha256 NAME=SHA256`）、`migration_handoff_manifest`/`verify_handoff_manifest`、`ledger_recency_comparison`；均只读，不写 pin、不摸 sealed run。
- **CLI 与闭包**：8 个新 evaluation 子命令；import 闭包扩展并 pin（`tests/test_ideation_import_contract.py` 加入 comparison_ai/evaluation_costs/evaluation_protocol/migration）。
- **验证**：迁移 rehearsal `tests/test_comparison_migration_rehearsal.py`（14 项）+ `tests/test_evaluation_costs.py`（23 项）；全量 pytest **879 passed**（基线 843）；black/compileall/CLI smoke 通过。
- **文档**：002 proposal versioned addendum 二、validation-matrix VM-QUAL-04 + 修订说明三、[ai-review-authoring-contract-v2.md](../../../agents/ai-review-authoring-contract-v2.md)「Comparison 接入」、[ai-review-migration-runbook.md](../../../agents/ai-review-migration-runbook.md)、CONTEXT.md 术语 6 条。
- **未完成（需 Robert 批准/执行）**：真实迁移未执行；评估协议修订未获 Robert 显式批准（旧 Gate 继续拒绝 AI 记录）；真实迁移所需逐 run 费用确认与评审费用预算上限未批准；slot 1 处置路径（AI 双评审或人工 validate）未由 Robert 选定；未推送、未部署、未自动晋升。真实六次基础 smoke 已于 2026-09-05 执行并通过（4/4，证据 [ai-review-real-smoke-evidence.md](../../../research/ai-review-real-smoke-evidence.md)）。
