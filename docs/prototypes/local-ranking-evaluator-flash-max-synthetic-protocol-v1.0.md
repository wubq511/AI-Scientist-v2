# Local-ranking evaluator Flash/max synthetic qualification protocol v1.0

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-012 live output**

本协议执行
[profile calibration v1.0](local-ranking-evaluator-profile-calibration-protocol-v1.0.md) 已批准的顺序：
`Flash/high` 在 [qualification-011](local-ranking-evaluator-profile-calibration-result-011.md) 以 `64/72`
mirror stability 正式 FAIL 后，只先验证 `opencode-go/deepseek-v4-flash` / `max` 的 SSE request/profile identity。
本 synthetic packet 不含 interview、Workshop、真实 query、真实 corpus 或旧 judgment。

## 1. Frozen harness and exact packet

- Harness commit: `4a4d6e48e1b6e0ec9c47be0f9ba64ec434f42ee5`；
- Streaming adapter SHA-256:
  `0e1efb1f35b98b64e8be33a57166d25e8c25424d6eec2029b4d58989e0dac8f2`；
- Adapter tests SHA-256:
  `cfeac6feb16a22f13abaa38f58c91d39167ef6846074048e4dbc5dce88c96f4a`；
- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.6 protocol SHA-256:
  `13a3b034df1b83be51e861b4b78f0327cd4f5aaaf386677cf00a5d030b83f789`；
- Attempt: `qualification-012-flash-max-synthetic`；
- Bundle: 3,591 bytes，SHA-256
  `59f67dd120a4447181c50d66897a7ead91dc250f2e2fec02e93332766a06f6f7`；
- Prompt: 5,180 bytes，SHA-256
  `80a7ba7e1154f5b18f9d0f27327b376fcaa3c366f0e2a57eb43f1c6e35480d52`；
- Request: 5,642 bytes，SHA-256
  `e3ae16e34962e0aa6139f5658b25c4b314fbb9d49f07ea9be280f0b13a91be0b`；
- Preparation manifest SHA-256:
  `0214e3b746aa937add69502fe09c275d253c36e3ec3a424a7e23c3b7e81bca5d`。

Bundle 由原 synthetic checksum task 确定性派生：只把 `bundle_id` 改为
`opencode-go-synthetic-flash-max-orientation-1`、把 evaluator `reasoning_effort` 改为 `max`，然后重算
self-hash 并由原 prompt renderer 生成新 prompt。Model-visible task、items、rubric 和 output contract 不变。

## 2. One-call boundary

唯一授权调用固定为：

```text
POST https://opencode.ai/zen/go/v1/chat/completions
model=deepseek-v4-flash
reasoning_effort=max
stream=true
response_format={"type":"json_object"}
max_tokens=32768
messages=[one exact 5,180-byte synthetic prompt]
```

不发送 `stream_options`，credential 只从本机 Kimi Code 的 `providers.opencode-go.api_key` 内部读取。本 attempt
不授权 retry；network、HTTP、SSE、identity、JSON、semantic validator 或 cost gate 任一失败，都保留原始
output 并停止，不切换 provider、endpoint、model 或 effort。

## 3. PASS gates

必须同时满足：

1. preparation schema `v1.1` 把 bundle、request、`deepseek-v4-flash/max` identity 互相绑定；
2. HTTP 200、`text/event-stream`、唯一 response ID、model identity 固定、一个 normal `stop`、唯一 `[DONE]`；
3. raw SSE、chunks、safe headers、timestamps、usage、cost 与 canonical response 全部保存并通过累计 metadata gates；
4. receipt 记录 `reasoning_effort_requested=max`，但保持 `reasoning_execution_proven=false`；
5. model draft 与 bundle evaluator exact match，并通过 `operational_judge finalize` 1/1；
6. synthetic judgment winner 必须为 `left`，因为只有 left 三段直接解释 checksum corruption detection；
7. response `cost="0"`。

## 4. Stop and conclusion boundary

PASS 只证明该账号在此时接受 Flash/max exact request，并能在一次 synthetic task 上返回机械和语义均有效的
SSE response；不证明 reasoning 实际执行、full-size 稳定性、统计独立性或模型永久版本。PASS 后也只能先生成
绑定 `max` evaluator identity 的新 full-size bundles/requests，并在新冻结协议下运行原三组 aggregate gates。

无论结果如何，本 attempt 不打开 private mapping、不运行 candidate reducer、不计算 BM25/E5 winner，也不进入
Downstream Experiment。
