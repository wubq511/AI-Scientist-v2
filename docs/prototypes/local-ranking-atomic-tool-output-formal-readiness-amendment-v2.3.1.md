# Atomic tool-output formal-readiness 补修合同 v2.3.1

日期：2026-09-02（Asia/Shanghai）

状态：**repair supplement authorized；live calls remain unauthorized**

基线：`c4bbb2e25acdbbc778cfb2915ff8dad51605fa81`

上游合同：[Atomic tool-output v2.3 独立复核与 formal-readiness 修复合同](local-ranking-atomic-tool-output-formal-readiness-review-v2.3.md)

## 1. 结论

`c4bbb2e` 已正确关闭 v2.3 review 发现的大部分 blocker，且双解释器 187 tests、真实 legacy/canary replay、
版本族配对、Unicode failure ledger、profile/current-manifest binding 与 frozen request hashes 均已独立复验。
但它还不是 formal-ready：独立对抗性复核发现三个可执行 bypass，以及一个与 smoke transport 证明直接相关的
metering 缺口。Fresh `pro-max-calibration-003-tool-output` 继续禁止；下一步只做本合同限定的 validator/gate 补修。

这些是证据真实性门，不是新的模型质量准入门槛：不改变 rubric、packet、model、effort、token ceiling、retry、
semantic gates 或 concurrency，也不新增 first-attempt-valid、latency、token、cost 或 tie-rate 阈值。

## 2. Blockers

### S1 — runner 未绑定 current atomic family

`run_orientation` 只校验 transport manifest 与 atomic manifest 的 hashes/identity，没有要求 atomic manifest 必须是
current v2.5 + `forced_submit_judgment_tool`。将 spent atomic v2.4 重新包装成 v3.1 transport 后，runner 可以进入
live execution；这违反 legacy/canary 只读、不得 resume live 的冻结边界。

### S2 — smoke validator 接受自洽但不完整的 evidence 子集

当前 `_smoke_evidence_files` 只检查 receipt/result 自己声明的文件。删除 raw SSE、chunks、safe headers 与 timestamps，
再把 receipt/result 改成只声明 `response.json` / `receipt.json`，`validate-smoke-call` 仍 PASS。Smoke 的问题本身是
transport 是否真实成立，因此 raw wire evidence 与其 deterministic derivations 是必要证据，不是可选附件。

### S3 — smoke validator 接受缺失 usage/cost

把成功 receipt 的 `usage` 和 `identity.cost` 都改成 `null` 并重算内部 hashes 后，validator 仍 PASS。上游合同要求
验证 usage/cost；缺失值不能证明调用账本完整。只要求字段存在、类型合法和数值非负，不设任何性能或价格门槛。

### S4 — frozen canary hash 可由 Python caller 覆盖

`prepare_profile(... expected_canary_summary_sha256=...)` 把本应唯一冻结的 canary summary hash 暴露为生产参数。
CLI 没有该开关，但 Python caller 可以传入任意替代 hash，违反 exact binding。

## 3. Frozen minimal fix

1. `run_orientation` 在读取 credential、创建输出或提交 request 前，必须同时要求：
   - atomic manifest schema 为 current v2.5；
   - atomic `response_submission=forced_submit_judgment_tool`；
   - transport manifest schema 为 current v3.1；
   - transport `response_submission=forced_submit_judgment_tool`。
   Legacy/canary 的 read/replay/diagnose 继续由非执行 validator 完成，runner 不承担旧 run 的诊断入口。
2. 成功 smoke receipt 的 `files` keys 必须恰好为：
   `chunks.jsonl`、`finished-at.txt`、`http-status.txt`、`response-headers.json`、`response.json`、
   `started-at.txt`、`stream-body.sse`。成功 execution-result 的 `files` 必须恰好为上述集合再加
   `receipt.json`；每个 hash 都与磁盘 bytes 一致。
3. Strong smoke validation 必须从 `stream-body.sse` 重新调用 frozen tool-stream extractor，并验证：
   - 重建 arguments 的 canonical bytes 等于 `response.json`；
   - 重建 chunks 的 canonical JSONL 等于 `chunks.jsonl`；
   - 重建 identity、diagnostics、usage 与 receipt 对应字段 exact equal；
   - tool name、model、finish reason、tool-call ID、request/preparation bindings 与 exact probe arguments 仍满足
     v2.3 contract。
4. 成功 smoke 的 `usage` 必须是合法非空 object，`identity.cost` 必须是可解析、有限、非负的 decimal string。
   只检查账本完整性，不对 tokens/cost 数值设置 admission threshold。
5. 删除 `prepare_profile` 的 `expected_canary_summary_sha256` 参数；production path 只能比较模块内冻结的
   `TRANSPORT_CANARY_SUMMARY_SHA256`。测试如需构造 synthetic fixture，只能在 test process monkeypatch 常量，不能
   保留可由生产 caller 使用的 override。
6. 不改变任何 writer/output schema version，也不改变既有成功 canary 的 tool schema、prompt 或 request bytes。

## 4. Scope

允许修改：

- `prototypes/local_ranking/atomic_opencode_go.py`
- `prototypes/local_ranking/atomic_runner.py`
- `prototypes/local_ranking/atomic_profile.py`
- `tests/test_local_ranking_atomic_opencode_go.py`
- `tests/test_local_ranking_atomic_judge.py`
- `prototypes/local_ranking/README.md`
- `docs/wayfinder/ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md`

本合同文件由 Codex 在实现前冻结，不属于 Kimi implementation diff。不得修改 `AGENTS.md`，不得新增 dependency，
不得修改 frozen artifacts，不能读取 credential、连接 Windows 或发送 model/API request。

## 5. Required proofs

1. 新增真实 negative tests：spent atomic v2.4 + 伪装 current transport 被 runner 在任何 HTTP 调用和输出前拒绝；
   legacy atomic 也同样拒绝。
2. 新增 smoke negatives：删除任一必需 raw/derived file、缩减任一 file map、raw SSE 与 derived response/chunks/receipt
   不一致、`usage=null`、`cost=null` 均 fail closed。
3. 真实 canary `smoke-001` 通过增强 validator；真实 canary `call-021` attempt replay SHA-256 继续精确等于
   `5d620f2807f584071d444dc842811f2ea266f43e1811c44d926814e73ff75252`。
4. 真实 v2.2 r1/o1 的 25 attempts 继续全部可读；legacy/canary diagnostic validators 保持可用。
5. production `prepare_profile` signature 不再包含 canary-hash override；错误 summary bytes 必须以
   `CANARY_SUMMARY_MISMATCH` 拒绝，真实 frozen summary 必须通过。
6. Frozen hashes 保持：tool schema
   `fa2cea71b0c41b87ef7743010656cd819d871ab2e8a95fcff2f8518cd11a859c`、prompt
   `4d8b409ebd6a3b24aed74e6ec230cd8b83950858de6a068b7e4f63a5501134ef`、request
   `7445fd80b52c1b4da594f46fe28d0811f22efb35be8edf188a2d823499588cb4`。
7. Python 3.13 reference 与当前 Mac compatibility interpreter 的 full pytest 全绿；Black、compileall、
   `git diff --check` 与本次 touched Python files 的 Ruff 全绿；full Ruff 只能保留已披露的 7 个 untouched baseline。

实现形成一个 clean commit：`fix: close atomic formal readiness bypasses`。随后只提交本次 session log，停止并交回
Codex。补修通过后仍不得自行 prepare/run formal 003；Codex 必须先冻结 profile、Windows bundle、usage snapshot、
execution order 与实际 r1 budget，再向 Robert 单独申请 live-call 授权。
