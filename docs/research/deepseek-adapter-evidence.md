# DeepSeek Adapter 验证证据 (Ticket 06)

本文档记录 Implementation Ticket [06: Record one validated DeepSeek model round](../wayfinder/ideation-implementation/tickets/06-record-one-validated-deepseek-model-round.md) 交付的 6 项验证矩阵行（`VM-UNIT-07`、`VM-CONTRACT-022-01`、`VM-CONTRACT-022-02`、`VM-CONTRACT-022-03`、`VM-REPLAY-01`、`VM-FAULT-01`）的测试结果与脱敏证据。

---

## 1. 验证矩阵交付结果

| 验证行 ID | 目标与条款 | 对应测试 | 结果 | 耗时 |
|---|---|---|---|---|
| `VM-UNIT-07` | 封闭 16 枚举 failure taxonomy 查表；严格映射 7 类 `suspend` 与 9 类 `terminal`，未知 code 拒 | `test_failure_taxonomy_lookup_table_completeness_and_classification`, `test_failure_taxonomy_retryable_subset` | **PASS** | < 0.01s |
| `VM-CONTRACT-022-01` | 参数白名单：仅批准 5 项字段，拒绝任意 model/temperature/top_p/penalties/seed/extra_body/stream/tools；SDK 隐式重试显式禁用（`max_retries=0`） | `test_adapter_allowlist_accepts_valid_request`, `test_adapter_allowlist_json_object_mode`, `test_adapter_allowlist_rejects_disallowed_parameters` (9 项), `test_adapter_allowlist_rejects_invalid_field_values` (10 项), `test_sdk_implicit_retries_disabled_in_client_options` | **PASS** | 0.03s |
| `VM-CONTRACT-022-02` | Provider-success 判定：required fields、model 精确匹配 `deepseek-v4-pro`、`finish_reason="stop"`、content 非空、json_object 模式顶级对象校验、Usage 四项不变量 fail closed | `test_provider_success_happy_path`, `test_provider_success_json_object_mode_valid`, `test_provider_success_json_object_mode_invalid` (5 项), `test_provider_success_rejects_model_mismatch`, `test_provider_success_finish_reason_dispositions` (5 项), `test_provider_success_rejects_empty_content` (3 项), `test_provider_success_rejects_unexpected_tool_calls`, `test_provider_success_usage_invariants_fail_closed` (5 项) | **PASS** | 0.05s |
| `VM-CONTRACT-022-03` | Stub transport 逐条触发；重试约束：≤2 attempts、仅批准 transient 故障重试 1 次、`timeout_ambiguous` 与 `transport_ambiguous` 绝不重试、Retry-After > 60s 立即返回 | `test_retry_transient_rate_limited_succeeds_on_second_attempt`, `test_retry_transient_fails_after_two_attempts`, `test_timeout_ambiguous_does_not_retry`, `test_transport_ambiguous_does_not_retry`, `test_rate_limited_retry_after_exceeded_does_not_wait_inside_adapter` | **PASS** | 0.06s |
| `VM-REPLAY-01` | Recorded provider responses 重放：跨独立 run 执行，生成 byte-identical 的 `request.json`、`response.json` 及匹配的 SHA-256 哈希 | `test_recorded_response_replay_canonical_artifacts` | **PASS** | 0.02s |
| `VM-FAULT-01` | Transport 故障注入：16 类 failure taxonomy 全覆盖逐条注入，验证 retry disposition 与 suspend/terminal 分级查表完全一致 | `test_fault_injection_all_16_codes` (16 项全覆盖) | **PASS** | 0.12s |

附加安全与隐私验证：
- `test_centralized_secret_redaction`：集中脱敏函数有效清除 Bearer token 与各类 API key；
- `test_credential_never_in_persisted_request_artifact`：落地私有证据链中的 `request.json` 仅包含语义参数，绝对零 credential 留存。

---

## 2. 自动化执行汇总

- **测试套件执行**：`python -m pytest -v tests/test_deepseek_adapter.py`
  - 结果：`70 passed in 2.16s`
- **全量自动化测试套件执行**：`python -m pytest -q`
  - 结果：`433 passed in 47.80s`（原有 363 项测试全量保持通过，新增 70 项全部通过）
- **静态代码检查**：
  - `python -m compileall ai_scientist tests` -> exit code 0
  - `python -m black --check ai_scientist/ideation/deepseek.py tests/test_deepseek_adapter.py` -> 2 files left unchanged

---

## 3. 证据脱敏与零成本声明

- **零真实模型费用**：全部测试使用 `StubTransport` 与 `RecordedTransport`；未产生任何外部 HTTP 请求，未消耗任何真实 token。
- **零网络调用**：测试期间网络隔离，零 DNS 查询与远程服务依赖。
- **凭证安全**：无真实 `DEEPSEEK_API_KEY` 进入代码库、测试 fixture、临时 run 根目录、工作日志或 Git commit。
