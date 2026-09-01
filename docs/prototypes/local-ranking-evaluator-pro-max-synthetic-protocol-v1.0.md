# Local-ranking evaluator Pro/max synthetic qualification protocol v1.0

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-016 live output**

本协议执行批准 ladder 的最后一档。Pro/high transport 已通过，但在 synthetic task 上抄错 exact bundle hash，
因此 [qualification-015](local-ranking-evaluator-pro-high-synthetic-result-015.md) FAIL。现在只验证
`opencode-go/deepseek-v4-pro` / `max`；packet 仍是无真实数据的 checksum synthetic task。

## 1. Frozen exact packet

- Harness commit: `8bd1886449e94fcab8fd68df8247fc91f5c6a17b`；
- Streaming adapter SHA-256:
  `9106ae5eceb374650ff38a5411acc16d2b9d81eb5b8a17ef4398128172ecce79`；
- Attempt: `qualification-016-pro-max-synthetic`；
- Bundle: 3,587 bytes，file SHA-256
  `372b3141a996ac684abce6f689253ad3c0b2164618820b59057c92b5927cc7d0`；
- Bundle self-hash:
  `0b088922de87b73fa65b30822972ae4fbeffb1758b2c455fd9e566622409cb99`；
- Prompt: 5,176 bytes，SHA-256
  `b91ab1dc28a5f66b6c6d4e5372f19dd9d129f31ac7b6b769328e431c3f926fce`；
- Request: 5,636 bytes，SHA-256
  `7c8e717dd664e098e605921b3cdc9b3e488609679a24d9c95c7083bbf08f3856`；
- Preparation manifest SHA-256:
  `1e2db040bb9ffc8c8089b94f05daf21a85e94ab6138eb3ffbe7c94075ffe4b0d`。

Bundle 只将同一 synthetic task 的 `bundle_id` 改为 `opencode-go-synthetic-pro-max-orientation-1`，evaluator
改为 `opencode-go/deepseek-v4-pro` / `max`，然后重算 hash/prompt。没有根据 Pro/high 的错误输出改变 task、
rubric、hash gate 或 response schema。

## 2. One-call gates

唯一授权调用：

```text
POST https://opencode.ai/zen/go/v1/chat/completions
model=deepseek-v4-pro
reasoning_effort=max
stream=true
response_format={"type":"json_object"}
max_tokens=32768
messages=[one exact 5,176-byte synthetic prompt]
```

不发送 `stream_options`，不授权 retry。PASS 必须同时满足 HTTP/SSE normal completion、所有 chunk exact Pro model、
唯一 response ID、完整 `[DONE]`、`cost="0"`、usage/identity 单调、receipt requested effort `max`、canonical JSON、
exact bundle self-hash/evaluator、1/1 local validator 和预注册 winner `left`。Receipt 仍不得声称 reasoning execution
已证明。

任何 gate 失败都停止，不修正 Pro/high 所暴露的 hash copying 错误，不切 provider/endpoint/model/effort。

## 3. Final ladder boundary

PASS 后只允许生成新的 Pro/max full-size bundles/requests，并另行冻结三组 calibration。若 synthetic FAIL，整个
profile ladder 立即停止；若 INCOMPLETE，先处理基础设施。即使 synthetic PASS，后续 full-size calibration 仍须
独立通过 24/24 coverage 和全部 mirror aggregate gates。

无论结果如何，本 attempt 不打开 private mapping、不运行 candidate reducer、不计算 BM25/E5 winner，也不进入
Downstream Experiment。
