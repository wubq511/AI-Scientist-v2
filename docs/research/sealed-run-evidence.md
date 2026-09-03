# Ideation Run 封印与 Happy Path 验证证据（Ticket 07）

## 验证背景与范围

本证据文档对应 implementation ticket [07: Seal one grounded Ideation Run](../wayfinder/ideation-implementation/tickets/07-seal-one-grounded-ideation-run.md)，证明在准入（Admission，Ticket 04）之后，系统保留批准的 baseline generation/reflection 循环，通过 `SearchLiterature`（Ticket 05）获得文献证据，模型提交满足七字段规范的 idea payload 与 Declared Grounding（Ticket 038），在进入下一 generation 之前原子持久化 accepted idea 及其 sidecar，循环结束后进行 Run 级 backstop 检查，发出 `terminal` 事件并生成最终的 `seal.json`（Terminal Outcome = `success`）。

验证全程在隔离沙盒内运行，采用确定性 `StubTransport`，**零外部网络调用、零真实模型费用**，未触发 downstream 阶段。

---

## 验证矩阵映射

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 结果 |
|---|---|---|---|---|
| **VM-INTEGRATION-01** | happy path: preflight → retrieval → FinalizeIdea → seal; 断言 event 序列合法、hash chain 连续、Terminal Outcome = `success` | 各契约组合后整圈可运行 | 011, 023, 024, 025 | **PASS**（`tests/test_sealed_ideation_run.py`） |

---

## 核心实现与契约落地

### 1. 基线循环与控制流语义（Tickets 006, 024, 025）
- **外层循环**：`max_num_generations` 次生成；
- **内层循环**：`num_reflections` 轮迭代，第 0 轮使用基线 `idea_generation_prompt`，后续使用 `idea_reflection_prompt`；
- **单 generation 历史作用域**：`msg_history` 在每次 generation 开始时清空；
- **创意库传承**：上一 generation 的 accepted idea 序列化进入 `prev_ideas_string`，在后续 generation 的 user prompt 中注入，推动创意多样性；
- **模型可见工具面**：严格限制为 `SearchLiterature` 与 `FinalizeIdea`，禁止代码执行工具与下游触发。

### 2. 七字段 Idea 与 Sidecar 物理分离（Tickets 008, 023, 038）
- **Idea Payload**：严格保持原始 7 字段结构（`Name`, `Title`, `Short Hypothesis`, `Related Work`, `Abstract`, `Experiments`, `Risk Factors and Limitations`），存为规范 JSON `artifacts/ideas/<idea_index:06d>/idea.json`；
- **Declared Grounding**：模型声明依据的文献 ID 列表，存为 `artifacts/ideas/<idea_index:06d>/grounding.json`；
- **Sidecar Provenance**：包含声明证据、时间戳、generation/reflection 坐标、文献检索 operation 序号及 hashes，存为 `artifacts/ideas/<idea_index:06d>/sidecar.json`；
- **原子提交（Atomic Commit）**：Idea 接受后立即持久化上述三个 artifacts 并发出 `operation.finished`、`action_outcome` 及 `generation.finished` 事件，绝不等待 run 结束才落盘，保证中断时不丢失已确认成果。

### 3. Declared Grounding 说谎防御与门禁顺序（Ticket 038）
FinalizeIdea 执行四级顺序检查：
1. **Payload Hygiene Scan**：防探测泄漏；
2. **结构校验**：恰好 7 字段、5 个非空 string、2 个非空 string list；
3. **Declared Grounding 校验**：非空 list of string、无重复项、且每个 `paper_id` 必须属于本 generation 检索返回的文献集合（说谎检测：`UNRETRIEVED_PAPER`）；
4. **Run 内去重**。

### 4. 终局 Seal 与完整证据链（Tickets 023, 025）
- **Run 级 Backstop 校验**：全 run 必须至少获得一次非空文献检索结果，否则 fail closed 判定为终端失败；
- **Terminal 事件**：记录 `outcome = "success"`、disposition counts（finalized/budget_exhausted）及 idea 总数；
- **Seal 封印**：生成 `seal.json`，固定：
  - `schema_version`: `run-seal-v1.0.0`
  - `terminal_outcome`: `success`
  - `request_sha256` 与 `admission_sha256`
  - `final_event`: `{event_seq, event_hash}`
  - `artifact_inventory`: 包含所有 operation attempts、ideas 及 sidecar 文件的严格字典序排序清单（含 length 与 SHA-256）；
- **哈希链连续性验证**：`store.verify_chain(run_id)` 实时校验 1..N 完整事件链条。

---

## 证据事件流样本（脱敏）

以单 generation、双 reflection round 为例：
```text
Event 00000001: preflight_started
Event 00000002: preflight_step (clean_worktree)
Event 00000003: preflight_step (workshop_approval)
Event 00000004: preflight_step (corpus_approval)
Event 00000005: preflight_step (retriever_binding)
Event 00000006: preflight_step (credential_presence)
Event 00000007: preflight_step (cost_approval)
Event 00000008: admitted (admission_sha256 pin)
Event 00000009: generation.started (gen_idx: 0)
Event 00000010: provider_attempt.finished (op_seq: 1, attempt_seq: 1)
Event 00000011: operation.finished (model_inference, op_seq: 1)
Event 00000012: operation.finished (literature_retrieval, op_seq: 2, papers returned)
Event 00000013: action_outcome (SearchLiterature -> tool_result)
Event 00000014: provider_attempt.finished (op_seq: 3, attempt_seq: 1)
Event 00000015: operation.finished (model_inference, op_seq: 3)
Event 00000016: operation.finished (idea_finalization, op_seq: 4, idea/grounding/sidecar refs)
Event 00000017: action_outcome (FinalizeIdea -> finalize_accepted)
Event 00000018: generation.finished (disposition: finalized, idea_index: 0)
Event 00000019: terminal (outcome: success, idea_count: 1)
Final: seal.json written referencing Event 00000019 and full artifact inventory
```

---

## 第一性原理对抗性审查与安全加固

在 Happy Path 基础上，从第一性原理对控制流、证据存储、门禁校验及状态机开展了全面的对抗性审查，实施了 6 项防御性加固并编写了专属测试：

1. **准入留痕篡改防御（Admission Tampering Defense）**：
   - 入口处不仅核验 `admission.json` 与 `workshop` 内容哈希，还实时比对 Event 00000008（`admitted`）中的 `admission_sha256` 锚点，若磁盘文件被篡改立即 fail-closed（抛出 `ADMISSION_TAMPERED`）。
2. **Idea Artifact 路径与白名单防御（Strict Path White-list）**：
   - `write_idea_artifact` 强制文件名封闭在 `{"idea.json", "grounding.json", "sidecar.json"}` 内，并限制 `0 <= idea_index <= 999999`，杜绝任何 `../` 逃逸、非法扩展名或任意文件写入。
3. **Run 内部跨 Generation 创意重名排斥（Run-Internal Deduplication）**：
   - 后续 generation 尝试提交与本 Run 前序 Accepted Idea 相同 `Name` 时，立即拦截（抛出 `DUPLICATE_IDEA_NAME`），防止创意被静默覆盖或重复计量。
4. **无检索直接 Finalize 拦截（Unretrieved Finalization Gate）**：
   - 证明若模型在未进行有效检索的 generation 中直接调用 `FinalizeIdea`，将被门禁拦截（抛出 `GATE_REJECTED`）。
5. **标量字段二进制与代理字符清洗（String Hygiene & Name Spec）**：
   - 强制 `Name` 必须满足 `^[a-z0-9_]+$` 规范（全小写、无空格、允许下划线）；
   - 对所有 7 字段及 Grounding 条目扫描 `\x00` 与 Unicode Surrogate Pair（`0xD800..0xDFFF`），拦截 `PAYLOAD_CORRUPT`。
6. **Seal 终局文档自洽性校验与前后双重链核验（Dual Chain Verification）**：
   - 在追加 `terminal` 事件后、写 `seal.json` 前，以及写 `seal.json` 后，分别全量调用 `verify_chain`；
   - `write_seal` 校验目标 `run_id`、`schema_version` 及必须字段完备性。

---

## 自动化测试与质量指标

- **新增专属测试**：`tests/test_sealed_ideation_run.py` 包含 15 项集成与对抗性测试：
  - `test_vm_integration_01_happy_path_seals_ideation_run`（VM-INTEGRATION-01 Happy Path 完整闭环）
  - `test_cli_seam_executes_and_seals_run`（CLI 入口 seam 集成运行）
  - `test_multi_generation_happy_path_seals_multiple_ideas`（多 generation 库传承与多 idea 封印）
  - `test_validate_idea_structure_enforces_seven_fields`（结构校验七字段单元）
  - `test_validate_declared_grounding_enforces_paper_eligibility`（Declared Grounding 与说谎校验）
  - `test_system_prompt_adheres_to_tool_and_grounding_fence`（Prompt diff 围栏机检）
  - `test_adversarial_tampered_admission_json_is_rejected`（对抗性：准入篡改检测）
  - `test_adversarial_tampered_workshop_is_rejected`（对抗性：Workshop 篡改检测）
  - `test_adversarial_unallowed_idea_artifact_filename_is_rejected`（对抗性：非法文件名路径逃逸拦截）
  - `test_adversarial_invalid_idea_index_is_rejected`（对抗性：非法 idea_index 拦截）
  - `test_adversarial_duplicate_idea_name_in_run_is_rejected`（对抗性：重名 idea 拦截）
  - `test_adversarial_finalize_without_prior_retrieval_is_rejected`（对抗性：未检索直接提交门禁拦截）
  - `test_adversarial_idea_structure_rejects_surrogates_and_null_bytes`（对抗性：控制字符/代理字符拦截）
  - `test_adversarial_declared_grounding_rejects_whitespace_and_path_separators`（对抗性：Grounding 路径注入与空格拦截）
  - `test_adversarial_seal_rejects_invalid_schema_or_missing_fields`（对抗性：非法封印结构拦截）
- **测试通过率**：全量回归测试套件 489 项测试 100% 通过（489 passed in 51.35s）；
- **静态代码检查**：`python -m compileall ai_scientist tests` exit code 0；
- **代码格式规范**：`black --check` exit code 0。
