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

## 自动化测试与复现命令

执行环境：macOS (Apple Silicon), Python 3.14.6 / 3.13.7 clean venv。

```bash
# 1. 针对 Ticket 05 的全新单元与契约测试
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
- `tests/test_scoped_retrieval.py`: 21 passed in 0.07s
- `tests/test_run_admission.py` + `tests/test_run_preflight.py`: 28 passed in 27.93s
- `tests/test_ideation_import_contract.py`: 1 passed in 0.04s
- 全量测试套件：`354 passed in 48.21s`（开工基线 333 项全部保持）
- Compileall: exit code 0
- Black check: 4 files unchanged, exit code 0
