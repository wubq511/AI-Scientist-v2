# Scoped Literature Retriever 验证证据

日期：2026-09-03

Implementation ticket：[Return one audited BM25 Retrieval Result](../wayfinder/ideation-implementation/tickets/05-return-one-audited-bm25-retrieval-result.md)

验证矩阵：`VM-UNIT-05`、`VM-CONTRACT-020-01`、`VM-CONTRACT-020-02`、`VM-CONTRACT-020-03`、`VM-CONTRACT-020-04`、`VM-REPLAY-03`

## 结论

Scoped Literature Retriever（`retrieval.py`）已完整落地并通过验证：
1. **输入边界封闭**：模型调用仅接受 `{"query": "..."}` 单一自然语言参数；任何多余参数、类型错误、trim 后为空、超过 256 标量字符或无有效 token 均被拦截并抛出受控错误（`INVALID_QUERY` / `QUERY_TOO_LONG`）。
2. **作用域严格绑定**：检索器由 preflight 绑定唯一 Approved Target Reference Corpus，每次检索逐字节重验文件存在性及 SHA-256，任何篡改立即 fail closed；模型无法覆盖或切换语料。
3. **资格审查与文献排除**：仅允许 `status == "validated"` 且 `type == "publisher_abstract"` 的段落参与检索；排除全文、派生文本与隐藏元数据；全语料无合格文献时 fail closed，不伪装成空结果。
4. **冻结 BM25 排序**：严格按照 Ticket 021 决议执行 Robertson/Sparck Jones positive-IDF BM25（$k_1 = 1.6, b = 0.5, title\_weight = 1.0, phrase\_bonus = \text{False}, aggregation = \text{"max"}$）；论文同分按 `paper_id` 升序稳定 tie-break；段落同分按 `content_item_order`、`source_start`、`segment_id` 升序 tie-break；严格遵守 3 篇论文、每篇 1 个段落、总计不超过 3 个段落的预算。
5. **最小 Model-Visible Payload**：Payload 仅含有序论文的 `paper_id`、`title` 与 `segments[content_type, text]`；所有分数、解释、内部标识符留在私有审计中。
6. **Audit Release Gate**：在释放结果给模型前，强制在私有证据链落盘 `payload.json` 与 `audit.json`，并追加 `operation.finished` 事件，经由对盘核验与哈希链校验确认后方才返回 payload；任何持久化或核验失败立即 fail closed。
7. **纯 CPU 与零网络**：全部计算采用标准库实现，纯本地 CPU FP32 路径，零网络、零外部模型调用、无 E5/remote fallback。

---

## 验证矩阵覆盖明细

| 行 ID | 检查项 | 验证结果 | 对应测试（`tests/test_scoped_retrieval.py`） |
|---|---|---|---|
| **VM-UNIT-05** | ranking 与 payload 构造: 确定性排序、稳定 tie-break、payload allowlist、payload SHA-256 | PASS | `test_bm25_positive_idf_and_length_normalization`<br>`test_ranking_enforces_paper_tie_break_lexicographically`<br>`test_ranking_enforces_segment_tie_break`<br>`test_output_budget_and_payload_allowlist` |
| **VM-CONTRACT-020-01** | retriever input 校验: 恰好 `{"query": 非空 string}`; unknown field/类型/trim 空/超长拒绝, 无静默改写 | PASS | `test_input_validation_accepts_valid_natural_language_query`<br>`test_input_validation_rejects_non_dict_arguments`<br>`test_input_validation_rejects_unknown_fields`<br>`test_input_validation_rejects_empty_or_whitespace_query`<br>`test_input_validation_rejects_non_string_query`<br>`test_input_validation_rejects_query_exceeding_scalar_limit`<br>`test_input_validation_rejects_unpaired_surrogates`<br>`test_input_validation_rejects_query_with_no_searchable_tokens` |
| **VM-CONTRACT-020-02** | scope binding: 模型/query/tool call 不能选择、覆盖、切换 corpus | PASS | `test_scope_binding_fails_closed_if_corpus_file_tampered`<br>`test_scope_binding_fails_closed_if_corpus_file_missing`<br>`test_scope_binding_fails_closed_if_corpus_case_mismatch` |
| **VM-CONTRACT-020-03** | eligibility: `derived_text`/`contexts`/`intents`/hidden text 等排除; 无 eligible content 的 record 不成结果; 全空 ≠ 合法 empty | PASS | `test_eligibility_skips_records_with_only_ineligible_content`<br>`test_eligibility_fails_closed_if_no_eligible_candidates_in_corpus` |
| **VM-CONTRACT-020-04** | audit release gate: audit event 未持久化+校验则 payload 不释放; 对模型仅暴露 `INVALID_QUERY`/`QUERY_TOO_LONG` | PASS | `test_audit_release_gate_persists_and_verifies_evidence`<br>`test_audit_release_gate_fails_closed_if_disk_verification_fails`<br>`test_input_error_records_failed_operation_event` |
| **VM-REPLAY-03** | 同 pinned corpus + 同 normalized query 重复检索 → 相同有序 payload 与 SHA-256 | PASS | `test_replay_produces_identical_canonical_payloads_and_hashes` |

---

## 对抗性审查与安全加固

在首轮实现与验证后，开展了全面的对抗性审查，识别并加固了 6 处潜在攻击面与边缘故障：

1. **跨论文 Segment ID 碰撞（Critical）**：
   - *攻击面/缺陷*：`corpus_build.py` 生成的语料中各论文段落默认 ID 常为 `item-01`。若直接以 `segment_id` 作为 `segment_stats` 词典键，后出现的论文会覆盖先出现论文的段落文本，导致语料统计量缩减为 1，且全部论文均与最后一篇论文的文本错误对比打分。
   - *加固措施*：在 `load_eligible_candidates` 中对段落 ID 实施论文前缀全限定：`segment_id = f"{paper_id}:{content_id}"`，并在 `test_adversarial_duplicate_content_id_across_papers_does_not_collide_in_bm25` 中实证排序隔离。
2. **语料重复记录与重复段落检测（High）**：
   - *攻击面/缺陷*：恶意或损坏的语料若含重复 `paper_id` 或篇内重复 `content_id`，会造成标题静默折叠或输出重复论文（违反 Ticket 021 “不得重复 paper” 规则）。
   - *加固措施*：加入 `seen_paper_ids` 与 `seen_content_ids` 判重集合，遇到重复立即 fail closed（`INVALID_CORPUS`）。
3. **Audit Release Gate 绕过防护（High）**：
   - *攻击面/缺陷*：若调用方在未绑定 `run_id` 的情况下调用 `search()`，原逻辑跳过了 release gate 直接返回 payload，形成零审计调用后门。
   - *加固措施*：`search()` 强制要求存在 `run_id` 与 `store`，否则立即 fail closed 抛出 `AUDIT_RELEASE_GATE_FAILED`，杜绝未留痕结果释放。
4. **异构字典键参数走样防护（Medium）**：
   - *攻击面/缺陷*：当模型/调用方传入含有非字符串键的字典（例如 `{1: "bad", "query": "..."}`），Python 3 的 `sorted(extra_keys)` 会抛出原生 `TypeError`，使错误跳出受控词汇体系。
   - *加固措施*：统一为 `sorted(str(k) for k in extra_keys)`，确保始终抛出受控的 `INVALID_QUERY`。
5. **统一输入异常证据留痕（Medium）**：
   - *攻击面/缺陷*：`normalize_query` 前的未知参数（如 `top_k`）此前直接在外部报错，未在私有证据链中记录操作失败。
   - *加固措施*：Step 1 采用统一 try-except 块，将一切输入异常（参数未知、类型不符、query 缺失、超长等）均作为 `input_error` 落盘 `audit.json` 并追加 `operation.failed` 事件。
6. **零 Token 候选语料拦截（Medium）**：
   - *攻击面/缺陷*：文献标题或正文若全由标点符号构成（无有效 token），可能引发除以零或虚假评分。
   - *加固措施*：对齐原型 `schema.py` 规则，强制要求 eligible 标题与段落正文均具备至少一个有效 token，否则 fail closed（`INVALID_CORPUS`）。

---

## 自动化测试与复现命令

执行环境：macOS (Apple Silicon), Python 3.14.6 / 3.13.7 clean venv。

```bash
# 1. 针对 Ticket 05 的全新单元、契约与对抗性测试
python -m pytest tests/test_scoped_retrieval.py -v

# 2. 准入与入口回归测试
python -m pytest tests/test_run_admission.py tests/test_run_preflight.py -v

# 3. 依赖与导入契约测试
python -m pytest tests/test_ideation_import_contract.py -v

# 4. 全量自动化测试套件
python -m pytest -q

# 5. 代码编译与代码规范检查
python -m compileall ai_scientist tests
python -m black --check ai_scientist/ideation/retrieval.py ai_scientist/ideation/run_store.py ai_scientist/ideation/admission.py tests/test_scoped_retrieval.py
```

### 运行结果
- `tests/test_scoped_retrieval.py`: 30 passed in 0.25s（21 项基线测试 + 9 项对抗性加固测试）
- `tests/test_run_admission.py` + `tests/test_run_preflight.py`: 28 passed in 27.93s
- `tests/test_ideation_import_contract.py`: 1 passed in 0.04s
- 全量测试套件：`363 passed in 49.77s`（开工基线 333 项全部保持）
- Compileall: exit code 0
- Black check: 4 files unchanged, exit code 0

