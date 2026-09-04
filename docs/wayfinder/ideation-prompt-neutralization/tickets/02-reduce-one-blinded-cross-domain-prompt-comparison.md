---
title: Reduce one blinded cross-domain prompt comparison
type: implementation
status: closed
assignee: agent
blocked_by:
  - 01-admit-and-replay-one-versioned-prompt-profile.md
---

# 02: Reduce one blinded cross-domain prompt comparison

**What to build:** 在 Prompt Profile 已可审计运行后，提供一个完整的离线 comparison boundary，用 synthetic sealed evidence 证明从四例选择、8-run 顺序、盲包、实际支出累计、write-once verdict 到 Promotion reduction 的全流程可确定性重放；全票不使用真实 case 内容、credential 或 provider。

**Blocked by:** 01: Admit and replay one versioned Prompt Profile.

**Status:** closed (2026-09-04, implemented and verified; see session log appended entry).

**Specification:** [Cross-domain Ideation Prompt qualification](../../../agents/cross-domain-ideation-prompt-spec.md).

- [x] comparison input 只接受已批准 12-case Canary manifest identity 与四个规定 cluster；每个 cluster 以 canonical case hash 选择一例，拒绝缺 cluster、重复 case、非 Canary case、source hash drift 或读取 Target contribution/result 后再选择。
- [x] 生成严格 4 对、8 runs 的 frozen matrix，exactly 2 对 baseline-first、2 对 challenger-first；两臂除 Prompt Profile id/hash 外，Workshop/Corpus hashes、model、reasoning effort、max tokens、generation/reflection budgets、retriever、rubric 与 runtime controls 必须逐字段相同。
- [x] 生成独立 frozen blind mapping，exactly 2 对 A=baseline、2 对 A=challenger；model-visible/Robert-visible pair packet 隐藏 profile、执行顺序、cost、latency、usage、attempt count 和 provider metadata，且 reveal 在所有可用 write-once verdict 冻结前 fail closed。
- [x] 生成 credential-free exact commands，只使用项目 credential wrapper、guarded slot runner 与生产 parser 实际支持的参数；命令文本不得含 key、环境赋值、自动 `yes`、Target title 或 unsupported `--reasoning-effort`/`--max-tokens` 参数，并以 parser contract 测试证明可执行。
- [x] append-only spend ledger 从 0.00 CNY 开始，能按 run ingest success、failed、suspended、resume 与 physical attempts 的实际 usage/cost；`5.00 CNY` 为累计实际支出重审批阈值，`30.00 CNY` 为使用 next-run worst-case reservation 的硬上限，exact-bound 接受、one-cent-over 拒绝，且 Plan Gate 不得替代逐 run 批准。
- [x] result ingestion 在产生 pair packet 前验证 Run Specification/profile identity、case/input hashes、Run Seal、Evidence Chain、sanitized export、Evaluation Artifact coverage、finish reason、attempt topology、latency 和 actual cost；不完整、corrupt、drifted 或 cross-case evidence fail closed。
- [x] Robert pair verdict 使用 `a_better`、`b_better`、`tie`、`incomparable` 封闭结果，并记录 overall、domain-method fit、unjustified ML intrusion 与 rationale；artifact write-once，不能覆盖、删除不利 verdict 或在 reveal 后补判。
- [x] deterministic reducer 实现规格全部门槛：3–0 quality threshold、4/4 completeness、domain-method 至少两对改善且零回退、ML intrusion 不增加、既有 rubric 底线、deterministic 零容忍、无 challenger-only truncation/failure/retry，以及 cost/median-latency 2.0 倍包络。
- [x] synthetic tests 覆盖每个边界与失败分支，并证明相同输入产生 byte-identical manifest、matrix、blind mapping、ledger state、pair packets 和 reduction；测试不得访问网络、活动 `.env`、真实 Target identity 或 private live-run artifacts。
- [x] 提交脱敏 schema、命令形状、测试结果和 rollback 证据并关闭本票；不生成最终私有 selection、不修改 Proposal 002 state、不调用模型、不产生费用、不执行 ticket 035 或 Downstream Experiment。

## Implementation notes

- 新模块 `ai_scientist/ideation/comparison.py`（stdlib-only，无新依赖，不进入 CLI import closure——它是离线 boundary，由测试与 ticket 03 的冻结工具消费，与 `prepare_ideation_inputs` 不在 entry closure 的先例一致）。
- **Selection seam**（`select_comparison_cases` / `build_selection_manifest`）：只接受 pinned 的已批准 12-case Canary manifest SHA-256（`APPROVED_CANARY_SELECTION_MANIFEST_SHA256`，即 Robert 批准的 `aae9d766…bb2f`），且输入必须是完整 12-case、每 case 的 cluster ∈ `CANARY_CLUSTERS` 八 cluster 闭集（伪造子集/非 Canary case → `CANARY_IDENTITY_UNAPPROVED`）；四 cluster 常量 `COMPARISON_CLUSTERS`；每 cluster 取 canonical case hash 最小者（完整 64-hex digest，无 tie）；输入类型 `CanaryCase` 只有 identity 字段（case_id/cluster/canonical_hash/target_row_sha256/source_row_snapshot_sha256），不存在 content 字段——测试证明 manifest 序列化与 poisoned CSV 值（contribution/route_result）零交集；缺 cluster（`MISSING_CLUSTER`）、重复 case/target（`DUPLICATE_CANARY_*`，两分支各有独立测试）、manifest identity 不符（`CANARY_IDENTITY_UNAPPROVED`）、row/dataset snapshot drift（`SOURCE_HASH_DRIFT`，dataset hash 也复核）全部 fail closed。
- **Frozen matrix**（`build_frozen_matrix` / `build_matrix_document` / `assert_single_variable_matrix`）：seed = selection manifest canonical SHA-256；每 pair 执行顺序按 `sha256(seed|arm_order|case_id)` 奇偶 + canonical-hash 再平衡（共享 `_balanced_partition` 原语），硬断言恰好 2 baseline-first / 2 challenger-first；single-variable 机器校验（`assert_single_variable_matrix`）覆盖 case/cluster/budgets/model/reasoning_effort/max_tokens/workshop/corpus pins、retriever policy version、rubric version 与 runtime controls（`MAX_ATTEMPTS_PER_OPERATION`）——两臂除 prompt profile id 外任一字段不同 → `ARM_SPECIFICATION_DRIFT`；`build_matrix_document` 对每对先跑同一断言并自带 self-pin（`frozen_matrix_digest` = 不含 pin 的 canonical bytes，ingest/reduction 复核同一 digest）；matrix/blind/verdict/reduction 的相同输入 byte-identical 由测试证明。
- **Blind mapping + pair packet**（`build_blind_mapping` / `blind_mapping_document` / `assert_blind_mapping_document_shape` / `build_pair_packet`）：`sha256(seed|blind_mapping|case_id)` 奇偶 + 再平衡（共享 `_balanced_partition` 原语），恰好 2 对 A=baseline / 2 对 A=challenger；mapping 文档独立序列化（`blind_mapping_sha256`）；`ComparisonVault.reveal` 要求全部 required write-once verdict 已冻结否则 `REVEAL_BLOCKED`，reveal 文档本身 write-once，reveal 后写 verdict → `VERDICT_AFTER_REVEAL`。pair packet 只含 case 身份 + 两个匿名化 idea payload（A/B）；blinding 扫描是**结构级**的：packet 内任何位置的禁键（`PAIR_PACKET_FORBIDDEN_KEYS`：profile pin、cost/latency/usage/attempt/provider/reasoning_effort/max_tokens 等元数据字段名）或 idea payload 之外的 profile 身份值命中即 `PAIR_PACKET_BLINDING_VIOLATION`；模型生成的 idea 文本不被扫描（合法英文词如 "cost-effective" 不是盲法泄漏）。reducer 只经 `reveal_document`（vault 落盘的 write-once `reveal.json`）消费 mapping——未过 reveal gate 的 identity 无法进入 reduction。
- **Commands**（`build_comparison_commands` / `_assert_command_contract` / `prepare_comparison_slot_launch`）：冻结形状为 `python scripts/with-project-env -- python scripts/run-prompt-comparison-slot --package-dir … --matrix-sha256 … --reapproval-threshold-cny 5.00 --run-index N`；slot runner 先以命令携带的外部 pins 校验 matrix bytes、ledger threshold 与 immutable 0.14 CNY opening balance，再重建内层 production `new-run` argv 并喂给 `_build_parser().parse_args()`，校验 ledger 顺序和预算后立即 `exec`。命令禁断 `--reasoning-effort/--max-tokens/--model/…`、key/token 形状、`yes` 管道与 env 赋值。
- **Spend ledger 与 pre-run reservation**（`initialize_comparison_ledger` / `ingest_run_actual_cost` / `authorize_next_comparison_run` / `reserve_comparison_slot` / `plan_gate_approval_document`）：0.00 CNY 起、append-only 且按 frozen slot 顺序；5.00 CNY 是 observed-spend 重审批阈值，跨越后如实记账为 `reapproval_required` 并阻止下一 slot；30.00 CNY 是请求前硬上限，按当前总账 + 从 pinned 高峰价格重算的 7.08 CNY bound reservation，exact 30.00 接受、30.01 拒绝。每个 slot 在 exec 前写入 exclusive-create `0600` reservation，重复/并发启动拒绝；Plan Gate 仍不替代 production admission 的逐 run `yes`。
- **Result ingestion**（`ingest_comparison_result`）：按序验证 matrix self-pin（`frozen_matrix_digest` 复核）→ `validate_evidence_chain(check_sealed=True)` → request/admission 的 profile pin/case_id/model 参数/budgets → frozen matrix slot 的 workshop/corpus hash pin → sanitized export 存在且 `prompt_profile.profile_id`/case_id 一致 → Evaluation Artifact coverage（复用 `list_evaluation_coverage`，要求 covered idea）→ 从 sealed event chain 派生 `RunMetrics`（terminal_outcome、finish_reasons、physical_attempt_count、Σ`provider_attempt.finished.duration_ms` latency、Σcost_cny，cost/duration 解析带 `ArithmeticError` guard）。`deterministic_validation_passed` 是本次 ingestion 实际运行的 gate（chain/seal/export/coverage/identity pins）的合取结果——fail closed 路径根本不产生 metrics；reducer 的零容忍门槛消费该标志。corrupt/drift/cross-case → `COMPARISON_IDENTITY_MISMATCH`/`INPUT_HASH_DRIFT`/`SANITIZED_EXPORT_MISSING`/`EVALUATION_ARTIFACT_MISSING` 等 fail closed。
- **Verdict**（`PairVerdict` / `verdict_document` / `ComparisonVault`）：封闭枚举 `a_better|b_better|tie|incomparable`；`domain_method_fit{improved,unchanged,worse,incomparable}`、`unjustified_ml_intrusion{increased,unchanged,decreased,incomparable}`、`rubric_floor`（`clean` 或 `mismatched/unsound/name_dropped/signal_found/leak_found`）三映射逐臂校验；rationale 非空；verdict 文件 exclusive-create write-once（覆盖 → `ARTIFACT_EXISTS`）。
- **Reducer**（`reduce_prompt_comparison`）：签名收 `reveal_document`（vault 落盘的 write-once reveal.json——reducer 只能经它消费 blind mapping，内部 `assert_blind_mapping_document_shape` 重新校验）；9 个门槛逐项记录（completeness→incomplete；quality 3–0；domain-method ≥2 改善 & 0 回退；ML intrusion 不增；rubric floor 双臂扫描；deterministic 零容忍（消费 ingestion 的 `deterministic_validation_passed` 合取标志）；challenger-only truncation/terminal failure/retry 增加；cost ≤2.0× 与 median e2e latency ≤2.0×；30 CNY hard-cap 合规，并记录是否达到重审批阈值）；输出 `reduction.json` 含逐门槛证据、`revealed_pair_profiles` 与冻结矩阵自带 digest pin；相同输入 byte-identical。
- **测试**：`tests/test_prompt_comparison.py` 当前 65 个测试；除原 selection/matrix/blind/ingestion/verdict/reducer/E2E 覆盖外，新增 threshold crossing、exact/one-cent-over hard-cap reservation、ledger arithmetic/slot identity、guarded outer command、matrix/threshold/opening-balance drift、production inner parser、CLI 越序拒绝与 write-once reservation 重复/并发拒绝。全程零网络、零真实 provider、零费用；不读活动 `.env`。
- **Rollback 证据**：本票新增面全部是 additive（一个新模块 + 两个测试文件 + 文档）；无生产模块行为修改，回滚 = revert 本票 commits 即可，生产 lifecycle 与 ticket 01 seam 不受影响。
- **边界声明**：最终私有 4-case selection manifest、Proposal 002 hash 补全、8-run 私有 package 冻结与命令零网络可执行性落盘属于 ticket 03；本票只交付并测试 boundary 函数本身。全程未调用 DeepSeek、实际支出 0.00 CNY、Proposal 002 未修改、ticket 035 未执行。

## 对抗性审查修复记录 (2026-09-04, post-close)

> 以下为 commit `3428909` 当时的历史状态；其中 v1.1 budget/subcap 语义已被后文“付费前预算合同修正”的 v1.2 合同取代，不再是当前执行依据。

- Commit `3428909`（fix: close adversarial review findings in comparison boundary）关闭本票 deliverable 的全部实质发现：
  - **F1/F2（Plan Gate 算术 + 历史支出核算）**：`plan_gate_next_run_allowed` 改为矩阵级严格不等式守卫（总 stage spend 需严格低于子上限与 30.00 CNY 硬上限），不再接收 per-run worst-case bound；逐 run 的 7.08 CNY 最坏 bound 仅属于 live admission 审批 seam。ledger 升级 `comparison-spend-ledger-v1.1.0`，纳入不变的历史 opening balance `0.14` CNY（`historical_spend_cny` + `total_stage_spend_cny`），移除旧 `current_actual_spend_cny`；`ingest_run_actual_cost` 在 ingest 处以 fail-closed `SUBCAP_EXCEEDED` 强制子上限。
  - **F3（packet↔sealed-run 证据链绑定）**：`build_pair_packets_from_ingested` 成为 live packet 的唯一授权构造器，消费 ingested RunMetrics 与 frozen blind mapping；packet 携带 per-arm sealed idea `idea_sha256`（源自 sealed Evidence Chain）；`PairFacts` 要求 `packet_sha256`；reducer 在 verdict 绑定到不同 packet 时 fail closed `VERDICT_PACKET_MISMATCH`。
  - **F5（原 reducer Gate 6 空转）**：以 recorded enforcement statement（`enforced_at: result_ingestion` + `ingested_gates` 列表）替代，确定性零容忍由 fail-closed result ingestion 结构性保证。
  - **F6（verdict 判据语义）**：`VERDICT_SCHEMA_VERSION` 升 `comparison-pair-verdict-v1.1.0`；`domain_method_fit`（`challenger_better|tie|baseline_better|incomparable`）与 `unjustified_ml_intrusion`（`increased|unchanged|decreased|incomparable`）改为 pair-level 标量（在盲包上以 challenger 相对 baseline 判定），`rubric_floor` 保持 per-arm；Gate 3 计 improved = `challenger_better` ≥ 2、regressed = `baseline_better` = 0。
  - **F7（死代码与记录漂移）**：移除未使用构造/死路径。
  - **F10（selection 防伪造）**：selection seam 重算 canonical hashes，伪造 → `CANARY_HASH_FORGERY`。
- 修复后全量测试 753 passed；Rollback 声明维持：修复全部落在 additive comparison boundary（`ai_scientist/ideation/comparison.py` + `tests/test_prompt_comparison.py`），生产 lifecycle 与 ticket 01 seam 不受影响。

## 付费前预算合同修正 (2026-09-04, post-close)

- Originating session 在准备 Plan Gate 时确认 commit `3428909` 的“ingest 时 subcap fail-closed”仍是事后证据拒绝，无法阻止已经发生的 provider 费用；而 frozen commands 也未调用 aggregate guard。Robert 明确批准在任何付费调用前修正。
- ledger 升级至 v1.2.0：`plan_gate_subcap_cny` 改为诚实的 `plan_gate_reapproval_threshold_cny=5.00`；跨越阈值仍记录实际费用并阻止下一 slot。唯一硬上限为 30.00 CNY，每个 run 前用 pinned price table 重算的 7.08 CNY peak bound reservation。
- 新增 `scripts/run-prompt-comparison-slot` 与 exclusive-create slot reservation，冻结命令不再能绕过 aggregate preflight；原生产 `new-run` cost prompt 和逐 run `yes` 保持不变。旧 v1.1 ledger/commands 私有 bytes 保存在 `superseded/v1.1.0-budget-contract/`，不删除失败证据。
