# Local-ranking OpenCode Go streaming qualification v1.0

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before live streaming output**

本协议只验证 OpenCode Go Chat SSE streaming 能否消除 qualification-008/009/010 已观察到的 long
non-streaming connection failure。Robert 已批准该 material transport change。Model、effort、prompt、bundle、
rubric、JSON draft contract 和 local semantic validator 均不改变。

## 1. Frozen implementation and request identity

- Harness commit: `f36f1dd534863b3fa0b6b13531ff031683dcec68`；
- Streaming adapter SHA-256:
  `3d63ad27facc59d3b2d7daf455967a34a0a6ba074340b0dad098a7009d60e472`；
- Provider/model/effort: `opencode-go` / `deepseek-v4-flash` / `high`；
- Endpoint: `POST https://opencode.ai/zen/go/v1/chat/completions`；
- Output ceiling: `max_tokens=32768`；
- Response format: `json_object`；
- `stream_options` 不发送。

Synthetic request：

- Preparation root:
  `artifacts/local-ranking-prototype/opencode-go-stream-qualification-v1/attempts/stream-001-synthetic/request`；
- Bundle SHA-256:
  `696b5b8ca0b67106c56f0c8bb324490295bf677fc07a9af7f2eaf0ad8dd15180`；
- Prompt SHA-256:
  `7de9d42c340738bce0953727314422af5dc32b572f12d89434177345a2b037f7`；
- Request: 5,644 bytes，SHA-256
  `721b81dc87897feaafc2819c8bfee4601b5a4d959c052c28d31508416093ba94`；
- Preparation manifest SHA-256:
  `6a0adefc8517c1a53116e5684140c07fd1ed3503538e5c2acff722e815baa83e`。

Full-size request：

- Preparation root:
  `artifacts/local-ranking-prototype/opencode-go-stream-qualification-v1/attempts/stream-002-full-orientation-1/request`；
- Bundle SHA-256:
  `10b57768cdd367e91f445ffe0a9aa61f563c3b63c42f4efd4af555eb55cf391b`；
- Prompt SHA-256:
  `4c4dbaf1d674008a53aa1412332176c0a53ea693bed411e11d257fd2cb06a750`；
- Request: 269,577 bytes，SHA-256
  `1777634ffbd2d34c51b290ef00d384321b93da1475ac48f0838290faee5897f5`；
- Preparation manifest SHA-256:
  `c09f87507477868ef8aaa2af3933a0ca681479437b8844032593564954d34100`。

两份 streaming requests 与其对应的 non-streaming requests 做逐字段 comparison，唯一差异均为
`stream: false → true`。Synthetic packet 不含 interview/Workshop/query/真实 corpus；full-size orientation 1
仍是已授权的 exact spent payload，retention 状态继续记录为 unconfirmed/user-authorized，不声称 ZDR。

## 2. Call order and no-retry boundary

严格串行运行：

1. `stream-001-synthetic` 唯一一次 live request；
2. 只有其 SSE transport receipt 与 1/1 local validator PASS 后，才运行
   `stream-002-full-orientation-1` 唯一一次 live request；
3. 只有 full-size SSE receipt 与 24/24 local validator PASS 后，才允许为新的三组 mirror calibration
   冻结后续协议。

本协议不授权 retry。HTTP/network、SSE、identity、finish、JSON 或 local validation 失败均保留原 attempt 并
停止；不得 repair stream、补 `[DONE]`、拼接旧 non-streaming output 或把 full-size probe 计入 calibration。

## 3. SSE transport gates

每次 live call 必须同时满足：

- HTTP 200 且 `content-type` 包含 `text/event-stream`；
- 完整保存 raw SSE body、safe headers、timestamps、status 与每个 JSON chunk；
- SSE 只含 comment/keepalive 与 `data:` events，UTF-8 可解析；
- content chunks 的 provider response ID、model、created identity 全程一致；
- model 必须是 `deepseek-v4-flash`，不得出现 refusal 或 tool calls；
- finish reason 只能有一个 `stop`，terminal 后不得继续 content；
- 必须收到唯一且最后的 `[DONE]`；
- 拼接后的 content 必须是一个 JSON object；
- usage/cost 若 provider 提供则 fail-closed 校验；若未提供则如实记录 `null`，不得估算；
- canonical response 必须继续通过原 `operational_judge finalize`，synthetic 为 1/1、full-size 为 24/24。

Raw SSE 是 transport evidence，不用于人工修正 model draft。Streaming PASS 只证明该 exact route 能完成这一
synthetic 和一条 full-size request；不证明后续六路一定成功，也不证明重复调用统计独立。

## 4. Stop and conclusion boundary

若任一 probe FAIL，不启动新的 calibration，Flash/high 的 semantic 状态仍只有 qualification-007 的
`22/24 FAIL`，并继续研究 output-budget/task decomposition 或另一 provider transport。

若两路 PASS，只授权准备新的 streaming mirror-calibration protocol；仍不打开 private mapping、不运行
candidate reducer、不计算 BM25/E5 winner，也不进入 Downstream Experiment。
