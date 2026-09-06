# Local-ranking OpenCode Go streaming qualification result 004

Run date: 2026-09-01（Asia/Shanghai）
Status: **PASS — synthetic 1/1 and full-size 24/24 completed over SSE**

适用协议：
[v1.0](local-ranking-opencode-go-stream-qualification-v1.0.md)、
[v1.0.1](local-ranking-opencode-go-stream-qualification-v1.0.1.md)、
[v1.0.2](local-ranking-opencode-go-stream-qualification-v1.0.2.md)。stream-001/003 保持 FAIL 并排除。

## 1. Synthetic result

`stream-004-synthetic` 从 `2026-09-01T06:07:02.149409Z` 到
`2026-09-01T06:07:27.462050Z`：

- HTTP 200 / `text/event-stream` / `cost="0"`；
- 1,064 data events，唯一 `stop`、`[DONE]` 和 post-DONE cost sidecar；
- response ID `router-c057b8f2a8ef92a101bb03d6320aec3a`；
- usage prompt/completion/total `1548/3676/5224`；
- streaming receipt SHA-256
  `50f266b886db0cc2f54bf66133a42fde2542944e64fe9111130f229c278a4c5c`；
- original local validator 1/1 PASS，trace SHA-256
  `df981603c369abc9152cee0a17b1f6ba4346767ee0565bfbdc1d4167cbcf485e`。

## 2. Full-size result

`stream-002-full-orientation-1` 从 `2026-09-01T06:07:46.177993Z` 到
`2026-09-01T06:13:18.670994Z`，约 5 分 32 秒：

- exact 269,577-byte orientation-1 request；
- HTTP 200 / `text/event-stream` / `cost="0"`；
- 10,950 data events，31,232 content bytes；
- 唯一 `stop`、`[DONE]` 和 post-DONE cost sidecar；
- response ID `router-1e04ef6ebfbf6d25ffc05d94c3bd7628`；
- usage prompt/completion/total `58043/37827/95870`；
- raw SSE SHA-256
  `4870677955ea57be92c4f45610f07b40c549430d64e8686946faab43e1505417`；
- streaming receipt SHA-256
  `63639b55c1a74abab4ea2f77806707e12d9f16b4985a500e1d531282a47b810f`；
- original local validator 24/24 PASS，trace SHA-256
  `59810f7dd75ea36bfe1c8fdb70db13acd334a825be58fdc0995123c2759546b9`。

## 3. Decision

Streaming transport candidate PASS。与 qualification-008/009/010 的 non-streaming HTTP 500/remote disconnect
相比，同规模 full request 在持续 SSE traffic 下完整结束，支持“长 non-streaming connection 是主要 failure
surface”的当前最佳解释。一次 PASS 不能证明 streaming 永不发生 mid-stream cutoff，因此后续 calibration 仍
保留 no-retry、完整 terminal 和 local validator gates。

两份 probe outputs 只用于 transport qualification，不得成为三组 mirror replicate 或 candidate vote。下一步
只授权用同一 streaming adapter、exact O1/O2 bundles 和六个 fresh response IDs 启动新的 Flash/high 三组
calibration；private mapping 继续 sealed。
