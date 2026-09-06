# OpenCode Go transport qualification protocol v1.0

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Approved for one synthetic live request；does not authorize spent/private payloads**

本协议只验证目标 OpenCode Go 账号当前是否接受 v1.6 的 direct Chat request shape，并返回可由本地
validator 消费的 JSON。Robert 已明确要求 provider 使用 OpenCode Go、禁止 DeepSeek official，并授权继续当前
qualification 链。本次 packet 不含 interview、Workshop、真实 query、真实 corpus 或旧 judgment。

## 1. Frozen source and packet

- Generator commit: `28ef8aec6478f3b85724c82e7e6355e3092f4849`；
- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.6 protocol SHA-256:
  `13a3b034df1b83be51e861b4b78f0327cd4f5aaaf386677cf00a5d030b83f789`；
- Preparation:
  `artifacts/local-ranking-prototype/opencode-go-transport-qualification-v1/attempts/synthetic-002`；
- Synthetic manifest SHA-256:
  `04adcd533551503be41973c0dbec08ccc821bea74969cf41a25082696114cc74`；
- Bundle: 3,592 bytes, SHA-256
  `696b5b8ca0b67106c56f0c8bb324490295bf677fc07a9af7f2eaf0ad8dd15180`；
- Prompt: 5,181 bytes, SHA-256
  `7de9d42c340738bce0953727314422af5dc32b572f12d89434177345a2b037f7`；
- Request preparation manifest SHA-256:
  `0d51728a6df775632d8ed9151be92b2ee941193afc4fcf6ad9c6f216f1e12a6f`；
- Request: 5,645 bytes, SHA-256
  `04d470f736e74281ec45cb169a7095359212d7585d07e7812c9e747903f6232d`。

`synthetic-001` 是 dirty-source rehearsal，虽与上述 bytes 相同也永久排除；唯一获准输入是 clean
`synthetic-002`。

## 2. Exact request and account gate

唯一调用固定为：

```text
POST https://opencode.ai/zen/go/v1/chat/completions
model=deepseek-v4-flash
stream=false
response_format={"type":"json_object"}
reasoning_effort=high
max_tokens=32768
messages=[one exact 5,181-byte synthetic prompt]
```

2026-09-01T01:10Z 调用前只读 usage snapshot 为 rolling `1% / ok`、weekly `0% / ok`、monthly
`24% / ok`。因此本次应消耗已有 Go quota，不需要 Zen balance fallback；若 response `cost` 不是字符串
`"0"`，停止并报告，不继续任何其他模型调用。Credential 只从本机 Kimi Code 的
`providers.opencode-go.api_key` 内部读取，不进入 request、artifact、日志或 commit。

本协议允许 1 次 initial request，不预授权 retry。Network、429、5xx 或任何不确定状态都保留原 attempt 并
停止；不得复用同一 output path、切 Kimi renderer、DeepSeek official、另一 endpoint/model/effort。

## 3. PASS gates

必须同时满足：

1. HTTP 200，exact `chat.completion`、requested model、一个 `index=0` choice、`finish_reason=stop`；
2. assistant content 是单一 JSON object，usage totals 自洽，response identity/timestamps/raw bytes/hashes 完整；
3. model draft 根字段 exact `bundle_sha256/evaluator/judgments`，本地 `operational_judge finalize` 1/1 PASS；
4. judgment 的 winner 为 `left`，因为只有 left 三段直接解释 checksum corruption detection；
5. receipt 只能记录 `json_object_accepted=true` 与 `reasoning_effort_requested=high`；不能声称 reasoning
   execution 已被证明；
6. response `cost="0"`。

任何 gate 失败都把 transport probe 判 FAIL，不修 JSON、不补字段、不挑选性重试。

## 4. Conclusion boundary

PASS 只证明该账号在该时间接受 exact request shape，并且一次 synthetic response 可通过本地 validator。
它不证明 provider-enforced JSON Schema、immutable model revision、reasoning 实际执行、24-item judgment
能力、ZDR、fresh ranking winner 或 OpenCode Go 的永久 API contract。

无论 PASS/FAIL，本次都不解封 private mapping，也不授权 24-item spent qualification。后者继续受 v1.6
data-retention gate 约束。
