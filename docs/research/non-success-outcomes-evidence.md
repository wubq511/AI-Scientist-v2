# 显式非成功终局封印验证证据（Ticket 09）

## 验证背景与范围

本证据文档对应 implementation ticket [09: Seal explicit non-success outcomes](../wayfinder/ideation-implementation/tickets/09-seal-explicit-non-success-outcomes.md)，证明完整 control loop 对以下确定性失败产生可解释的 terminal `failed` seal，且 terminal 条件不被较低优先级的模型可修复错误掩盖：

1. **Payload hygiene 命中**（Idea Leakage 防御纵深）：FinalizeIdea 提交内容命中私有标识符模式 → 立即 terminal `failed`，不回灌、不可修复；
2. **Run 级 no-nonempty-retrieval backstop**：全程无非空 Retrieval Result → terminal `failed`；
3. **确定性 adapter 失败**：closed taxonomy 中 disposition=terminal 的 provider 失败 → terminal `failed`；suspend 类失败保持上抛、不 seal（Run Suspension 归 ticket 10）；
4. **Retriever/evidence boundary 失败**：corpus hash 不符等 → terminal `failed`，无 fallback；
5. **脚本化对抗模型行为**（malformed/unknown action、grounding 说谎、近重复）：在完整 control loop 中抵达批准的终点（model-fixable 回灌 / `budget_exhausted` disposition）。

验证全程确定性：`StubTransport` 与注入组件，**零网络调用、零真实模型费用**，未进入 downstream 阶段。

---

## 验证矩阵映射

| 行 ID | 检查项 | 结果 | 证据 |
|---|---|---|---|
| **VM-CONTRACT-025-02** | finalization gate 固定优先级：hygiene → 结构 → grounding → 去重；每轮只报最高优先级一个；terminal 条件不被 model-fixable 掩盖 | **PASS**（`tests/test_sealed_non_success_outcomes.py`） | 同轮三重违规（hygiene+structure+grounding）只产生 `hygiene_hit`；七轮优先级剧本逐轮断言 |
| **VM-CONTRACT-026-02** | payload hygiene scan 模式命中即 terminal；run 内去重近重复保持 model-fixable | **PASS**（同上） | `case_id` 命中即封印失败；`DUPLICATE_IDEA_NAME` 保持可修复回灌 |
| **VM-LEAKAGE-02** | Idea Leakage 机检扫描：模式列表由 023/024 标识符格式推导，版本化；命中即 terminal | **PASS**（同上） | `PAYLOAD_HYGIENE_PATTERNS_VERSION = payload-hygiene-patterns-v1.0.0`；扫描记录走 `hygiene-violation.json` 私有 artifact + `action_outcome` 事件 |
| **VM-INTEGRATION-03** | terminal 剧本：hygiene 命中 → `failed`；run 级 backstop → `failed` | **PASS**（同上） | 两条完整 seal 链路：terminal 事件 + seal.json + 完整 artifact inventory 校验 |
| **VM-FAULT-04** | 模型行为故障整圈：malformed/unknown action、grounding 说谎、hygiene 命中、重复 idea 抵达批准终点 | **PASS**（同上 + `tests/test_model_fixable_actions.py` 回归） | 未知动作与说谎回灌消耗轮次后 `budget_exhausted`，run 级 backstop 满足时 run 仍 `success` 封印 |

---

## 核心实现与契约落地

### 1. Finalization gate 固定优先级（Tickets 038/025/026）

`FinalizeIdea` 分支按以下固定顺序执行，每轮只报最高优先级的一个结果：

1. **Payload hygiene scan**（terminal）：对 raw submission bytes（`ARGUMENTS` 块原文，parse 失败也照扫）执行 `scan_payload_hygiene`；命中 → 记录 `hygiene-violation.json`（仅 pattern_id + span，无密文）+ `action_outcome`（`outcome: "hygiene_hit"`）事件 → 立即 `_seal_failed_run("PAYLOAD_HYGIENE_VIOLATION", ...)`。**不产生任何 feedback 文本，模型不再见到该轮**；
2. 024 结构校验（封闭两键 + 七字段，Model-Fixable）；
3. Declared Grounding 校验（三码，Model-Fixable）；
4. Run 内去重（`DUPLICATE_IDEA_NAME` / `DUPLICATE_IDEA`，Model-Fixable）。

### 2. 版本化 payload hygiene 模式列表（VM-LEAKAGE-02）

`PAYLOAD_HYGIENE_PATTERNS_VERSION = "payload-hygiene-patterns-v1.0.0"`，六组模式全部从 023/024 标识符格式推导：

- `case_id_format`：`case-[0-9a-f]{32}`（024 schema）；
- `sha256_hex`：64 位小写 hex（023 canonical hashes）；
- `uuidv4_format`：canonical lowercase UUIDv4（023 identity model）；
- `run_root_path`：`artifacts/ideation-runs/`、`evidence/ideation-runs/`、`ideation-runs/`（023 trust roots）；
- `internal_evidence_path`：`data/raw/`、`artifacts/operations/`、`artifacts/ideas/`、`artifacts/validations/`、`projections/`、`events/`、`reviews/`（内部证据子树）;
- `internal_artifact_filename`：`admission.json`、`request.json`、`seal.json`、`bundle-manifest.json`、`grounding.json`、`sidecar.json`（lifecycle 文件名）。

**明确不匹配**：检索返回的 `paper_id`（40 位 hex）是模型可见证据（020），不是私有标识符；大写非 canonical hex 同样不命中。误报控制经正负例测试固化。

### 3. Terminal failed seal（Ticket 025 失败分级封闭表）

`_seal_failed_run(reason_code, ...)` 封闭三类 reason：

- `reason_kind="controller"`：`PAYLOAD_HYGIENE_VIOLATION`、`PAYLOAD_CORRUPT`、`RETRIEVAL_BACKSTOP_FAILED`；
- `reason_kind="provider"`：022 closed taxonomy 的 9 个 terminal 失败码（`configuration`、`model_mismatch`、`truncated`、`content_filtered`、`empty_content`、`invalid_json`、`unexpected_tool_call`、`malformed_response`、`unknown_provider_failure`）；
- `reason_kind="retriever_evidence"`：020 boundary/audit 失败码（`AUDIT_RELEASE_GATE_FAILED`、`HASH_MISMATCH`、`IDENTITY_MISMATCH`、`INVALID_CORPUS`、`INVALID_SCORE`、`MISSING_CORPUS`、`NO_ELIGIBLE_CANDIDATES`、`PATH_ESCAPE`、`SYMLINK_FORBIDDEN`）。

未知 reason fail closed（`INVALID_FAILURE_CODE`）。sealed failed 流程：可选 violation detail artifact（如 `artifacts/failures/backstop-violation.json`）→ `terminal` 事件（payload 带 outcome/reason_code/reason_kind/disposition 计数/idea_count + artifact refs）→ `verify_chain` → 完整 `artifact_inventory` → `seal.json`（`terminal_outcome: "failed"`）→ 再次 `verify_chain`。suspend 类 adapter 失败（`authentication` 等 7 码）原样上抛、不产生 seal，Run Suspension 由 ticket 10 接管。

合法 `budget_exhausted` generations 在 failed seal 的 `terminal_summary.disposition_counts` 中如实保留——失败原因与已有产出互不掩盖。

### 4. 与既有回灌语义的关系

- Model-Fixable 回灌路径（ticket 08）全部保留；唯一新增的 terminal 分支是 hygiene scan 与 controller/provider/retriever 确定性失败；
- `test_sealed_ideation_run.py` 中 backstop 测试从「抛出 IdeationInputError」更新为「seal terminal failed」——这是 ticket 09 批准的合同变更（025：terminal failure 产生 seal，不是异常逃逸），其余 14 项断言全部不动。

---

## 验证测试套件

`tests/test_sealed_non_success_outcomes.py`（13 项，全零网络零费用）：

1. `test_payload_hygiene_scan_detects_private_identifier_patterns`：六组模式逐组命中 + 干净科学文本零误报；
2. `test_payload_hygiene_scan_treats_retrieved_paper_ids_as_model_visible`：`paper_id` 与大写 hex 不命中；
3. `test_vm_integration_03_hygiene_hit_seals_failed_run`：case_id 泄漏 → 2 轮模型调用即封印 failed；`hygiene_hit` 事件 + violation report artifact + 空 ideas 目录 + 完整 inventory；
4. `test_vm_contract_025_02_hygiene_hit_not_masked_by_fixable_errors`：同轮 hygiene+structure+grounding 三重违规只报 `hygiene_hit`，无 `model_fixable_error`；
5. `test_vm_contract_025_02_gate_priority_structure_grounding_duplicate`：七轮剧本证明 structure > grounding > duplicate 固定优先级，每轮恰好一个结果；
6. `test_vm_integration_03_retrieval_backstop_seals_failed_run`：全程无非空检索 → failed seal，`budget_exhausted: 1` 合法保留；
7. `test_cli_seam_backstop_failure_seals_failed`：真实 `_run_new_run` CLI seam 输出结构化 JSON（`reason_code: RETRIEVAL_BACKSTOP_FAILED`，exit 0）；
8. `test_terminal_adapter_failure_seals_failed_run`：HTTP 400 → `configuration` terminal → failed seal，`operation.failed` 事件带 `disposition: terminal`；
9. `test_suspend_adapter_failure_does_not_seal`：HTTP 401 → suspend 类失败上抛，run 保持 unsealed 无 seal.json（ticket 10 边界）；
10. `test_retriever_boundary_failure_seals_failed_run`：注入 corpus hash 失败 retriever → `HASH_MISMATCH` failed seal，零重试；
11. `test_payload_corrupt_idea_seals_failed_run`：null byte 提交 → `PAYLOAD_CORRUPT` failed seal；
12. `test_vm_fault_04_fixable_adversarial_scripts_reach_budget_exhausted`：malformed action + 说谎回灌 → `budget_exhausted`，run `success` 封印；
13. `test_vm_fault_04_budget_exhausted_then_run_succeeds_after_prior_retrieval`：6 个 generation 全部说谎耗尽预算，backstop 已被 gen 0 满足 → run `success` 封印（`budget_exhausted: 6`）。

---

## 测试执行结果汇总

```bash
$ python -m pytest tests/test_sealed_non_success_outcomes.py -q
13 passed, 6 warnings in 4.70s

$ python -m pytest tests/test_sealed_ideation_run.py tests/test_model_fixable_actions.py -q
21 passed (backstop 测试按 ticket 09 合同更新为断言 failed seal)

$ python -m pytest -q
508 passed, 6 warnings in 56.57s

$ python -m compileall ai_scientist/ideation tests/test_sealed_non_success_outcomes.py
（exit 0）

$ python -m black --check ai_scientist/ideation tests/test_sealed_non_success_outcomes.py tests/test_sealed_ideation_run.py tests/test_model_fixable_actions.py
23 files would be left unchanged
```

所有新增与存量检查全量绿灯，Evidence Chain 验证闭合。