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
  - 结果：`111 passed in 2.17s`（基线 70 项 + 对抗性加固 41 项）
- **全量自动化测试套件执行**：`python -m pytest -q`
  - 结果：`474 passed in 47.94s`（原有 363 项测试全量保持通过，新增 111 项全部通过）
- **静态代码检查**：
  - `python -m compileall ai_scientist tests` -> exit code 0
  - `python -m black --check ai_scientist/ideation/deepseek.py tests/test_deepseek_adapter.py` -> 2 files left unchanged

---

## 3. 证据脱敏与零成本声明

- **零真实模型费用**：全部测试使用 `StubTransport` 与 `RecordedTransport`；未产生任何外部 HTTP 请求，未消耗任何真实 token。
- **零网络调用**：测试期间网络隔离，零 DNS 查询与远程服务依赖。
- **凭证安全**：无真实 `DEEPSEEK_API_KEY` 进入代码库、测试 fixture、临时 run 根目录、工作日志或 Git commit。

---

## 4. 第一性原理对抗性审查与加固记录

针对 DeepSeek Adapter 作为不可信外部模型网关与私有证据链之间的核心边界，从第一性原理（信任边界、状态一致性、计费审计、Unicode 安全与协议鲁棒性）深挖 7 处边界弱点并实施彻底加固：

1. **强制 Audit Release Gate 审计放行门（Critical）**：
   - *攻击面*：若 caller 实例化 adapter 未绑定 `store` 或 `run_id` 并调用 `execute_round`，可能导致模型推理结果在无审计事件链、无物理留痕的情况下被私自放行使用。
   - *加固*：在 `execute_round` 入口实施 fail closed 强校验，若 `store` 或 `run_id` 任一缺失，立即抛出 `AUDIT_RELEASE_GATE_FAILED`，坚决杜绝零审计旁路调用。
   - *验证*：`test_adversarial_audit_release_gate_fails_closed_without_run_or_store`（覆盖 store/run_id 各种缺失组合）。

2. **HTTP 响应头大小写不敏感归一化（High）**：
   - *攻击面*：HTTP 规范定义 Header 不区分大小写。网关或代理可能返回 `Retry-After: 120` 或 `RETRY-AFTER: 120`，原生字典查找 `headers.get("retry-after")` 会失配返回 None，导致无法识别超长退避而错误阻塞或继续重试。
   - *加固*：在 `TransportResponse` 中自动将所有 header key 转换为小写规范存储，确保大小写不敏感。
   - *验证*：`test_adversarial_case_insensitive_retry_after_header`（覆盖 `Retry-After`、`RETRY-AFTER`、`rEtRy-AfTeR` 等）。

3. **完整兑现「失败 Attempt 也计费」契约（High）**：
   - *攻击面*：当 Provider 返回 HTTP 200 但因 `truncated`（`length`）或 `resource_exhausted` 导致 round 失败时，物理 token 实际已被消耗且产生了真实费用。若 failure 记录与事件遗漏 `cost`，会导致证据链成本统计失真。
   - *加固*：在捕获此类响应级失败时，若存在有效 `usage`，调用价格表计算真实 CNY 成本，注入 `ModelRoundFailure.cost`，在 `failure.json` 中落盘结构化计费证据，并在 `provider_attempt.finished` 事件 payload 中记录 `cost_cny`。
   - *验证*：`test_adversarial_failed_attempt_records_actual_cost_when_usage_present`。

4. **Wire Bytes 原生捕获与非重序列化（Ticket 023 契约闭环）（High）**：
   - *攻击面*：若落盘 `response.json` 时对 `parsed_body` 重新执行 `canonical_json_bytes`，会改变 Provider 网关实际返回的原生 representation bytes（例如空格、键序或浮点表现），违反 Ticket 023「即使 media type 是 JSON，也不得在 capture 后为了套用项目 canonical rendering 而重新序列化再 hash」的死命令。
   - *加固*：落盘 `response.json` 直接保存 `transport_resp.body`（Wire Bytes 原生切片），实现 bit-for-bit 原始哈希锁存。
   - *验证*：`test_adversarial_wire_bytes_preservation_in_response_artifact`。

5. **输入 Scalar String 与非法 Unicode 严格防线（Medium）**：
   - *攻击面*：Prompt 内容中若包含未配对的 Unicode 代理字符（Surrogate pair `0xD800..0xDFFF`）或空字节 `\x00`，在后续 UTF-8 编码或跨进程传输时会导致 Python 底层未捕获的 `UnicodeEncodeError` 异常，绕过类型化 failure 机制；全白空格 content 亦可能污染 prompt context。
   - *加固*：在 `validate_request` 中显式检验标量字符串，禁止 `\x00`、Surrogate 字符与全白字符串，统一抛出 typed `configuration` terminal failure。
   - *验证*：`test_adversarial_surrogate_and_null_byte_rejection`。

6. **System Message 排位与重入唯一性（Medium）**：
   - *攻击面*：乱序插入的 `system` prompt（如置于 `user` 之后或出现多个 `system`）可能引发不同供应商网关未定义的行为或安全性穿透。
   - *加固*：强制限制 `system` 角色消息仅允许出现在 `messages[0]`，且最多出现一次。
   - *验证*：`test_adversarial_system_message_ordering_and_multiplicity`。

7. **User ID 安全标识符格式限制（Medium）**：
   - *攻击面*：不安全的 `user_id`（包含空格、换行符、反斜杠、控制字符或超长字符串）可能在内部路由、统计或审计聚合中被利用进行注入攻击。
   - *加固*：强制正则 `^[A-Za-z0-9_\-\.]{1,128}$` 校验，确保为纯净安全的 opaque ASCII 标识符。
   - *验证*：`test_adversarial_invalid_user_id_formats`。

