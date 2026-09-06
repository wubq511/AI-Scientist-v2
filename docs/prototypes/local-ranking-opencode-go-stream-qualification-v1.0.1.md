# Local-ranking OpenCode Go streaming qualification v1.0.1

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Frozen bookkeeping correction before stream-003 output**

本文件只修正
[stream-001](local-ranking-opencode-go-stream-qualification-result-001.md) 暴露的 OpenCode Go SSE
bookkeeping shape。Model、effort、synthetic input、full-size input、prompt、request bytes、JSON draft contract、
local semantic validator、调用顺序和 no-retry 规则继续以
[v1.0](local-ranking-opencode-go-stream-qualification-v1.0.md) 为准。

## 1. Corrected harness and new synthetic attempt

- Harness commit: `663860315cc5a31288989d4193f00fef8baac602`；
- Streaming adapter SHA-256:
  `a481a38e3645aedb788737cf05adaa06a7657d01f6a6485f8af2ccb96ad1e280`；
- New synthetic attempt: `stream-003-synthetic`；
- Preparation root:
  `artifacts/local-ranking-prototype/opencode-go-stream-qualification-v1/attempts/stream-003-synthetic/request`；
- Request: 5,644 bytes，SHA-256
  `721b81dc87897feaafc2819c8bfee4601b5a4d959c052c28d31508416093ba94`；
- Preparation manifest SHA-256:
  `6a0adefc8517c1a53116e5684140c07fd1ed3503538e5c2acff722e815baa83e`。

新 request 与 stream-001 byte-identical；旧 output 完全排除。若 stream-003 PASS，继续使用 v1.0 已冻结但从未
发送的 `stream-002-full-orientation-1` request；其 bytes/hash 不变。

## 2. Corrected construct-irrelevant gates

Usage 允许多个 chunks 逐步补充 details，但必须满足：

- `prompt_tokens/completion_tokens/total_tokens` 在所有 usage chunks 中完全相同；
- detail key 只能从 absent 变为一个具体非负值；
- 已出现的 detail value 不得改变；
- total 必须始终等于 prompt + completion。

`[DONE]` 之后只允许零个或一个 billing sidecar。若存在，它必须是绝对最后的 data event、exact root keys
`choices/cost`、`choices=[]`、cost 为非负有限 decimal string。它不含 model content，不算作 terminal 后继续
输出。其他任意 post-`[DONE]` event 继续 fail closed。

这些变化不读取、修改或评价 model draft；只接受 provider 已观察到的 usage enrichment 与 billing envelope。
Content identity、唯一 `finish_reason=stop`、terminal 后禁止 content、JSON/local validator 和全部 v1.0 gates
保持不变。

## 3. Fail-closed boundary

stream-001 永久 FAIL，诊断 parser 对其成功重建不得追认旧 attempt。stream-003 仍只有一次 live call；失败不
retry、不启动 full-size。只有 stream-003 SSE receipt + 1/1 local PASS 后，才运行 v1.0 的 full-size probe。
