# Local-ranking OpenCode Go streaming qualification v1.0.2

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Frozen cumulative-metadata correction before stream-004 output**

本文件只修正
[stream-003](local-ranking-opencode-go-stream-qualification-result-003.md) 暴露的 cumulative usage 与 chunk
timestamp shape。其余边界继续以
[v1.0](local-ranking-opencode-go-stream-qualification-v1.0.md) 和
[v1.0.1](local-ranking-opencode-go-stream-qualification-v1.0.1.md) 为准。

## 1. Corrected harness and attempt

- Harness commit: `e34fda82898ec90e5b7dd2d859bf8d5579e271fb`；
- Streaming adapter SHA-256:
  `79cfed00222da6c3ea550bb4d37b1278935b9c5027348ce55d61a532fc98d84b`；
- New synthetic attempt: `stream-004-synthetic`；
- Request remains byte-identical: 5,644 bytes，SHA-256
  `721b81dc87897feaafc2819c8bfee4601b5a4d959c052c28d31508416093ba94`；
- Preparation manifest SHA-256:
  `6a0adefc8517c1a53116e5684140c07fd1ed3503538e5c2acff722e815baa83e`。

stream-001/003 outputs 全部排除。若 stream-004 PASS，继续使用从未发送的
`stream-002-full-orientation-1` exact request。

## 2. Cumulative usage and identity gates

每个 usage object 仍须独立满足非负整数与 `total = prompt + completion`。跨 chunks 时：

- `prompt_tokens` 必须固定；
- `completion_tokens` 与 `total_tokens` 必须单调不下降；
- details 可以后来补充，但已出现的 detail value 不得改变；
- receipt 只记录最后一个 usage snapshot，并保留全部 raw chunks 供审计。

Content chunks 的 response ID 与 model 必须固定；`created` 允许单调不下降，receipt 同时记录
`created_first/created_last`。任意 response ID/model change 或 timestamp 回退继续 fail closed。

这些规则覆盖已观察到的两种 provider shape：仅 terminal/final usage，或逐 chunk cumulative usage。它们不允许
usage 回退、不允许 identity 切换，也不改变任何 model content/semantic gate。

## 3. Stop rule

stream-004 只有一次调用。失败不 retry、不启动 full-size；PASS 必须同时包含 SSE receipt 与 1/1 local
validator。旧 stream 的诊断可证明 parser correction，但不能替代新 qualification output。
