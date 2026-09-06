# Local-ranking OpenCode Go streaming qualification result 003

Run date: 2026-09-01（Asia/Shanghai）
Status: **FAIL — validator treated cumulative usage as immutable totals**

适用协议：
[streaming qualification v1.0.1](local-ranking-opencode-go-stream-qualification-v1.0.1.md)。只运行 synthetic；
full-size request 未启动。

Synthetic call 返回完整 SSE，raw body 445,650 bytes，SHA-256
`a8e5c55dbc1fcefcc152d325f7e732a95d6bc3ddc9c62658d9cd1b67e19207c1`。Adapter 以
`INVALID_PROVIDER_RESPONSE / Stream usage totals changed between chunks` 拒绝，validation-error SHA-256
`dac06fdd1dbacb912a90cdf45f941dbc95b9bbcad835a6ca673f101fed17725d`。

只读 metadata 显示 provider 在几乎每个 reasoning/content chunk 上发送 cumulative usage：

- `prompt_tokens` 固定为 `1548`；
- `completion_tokens` 从 `1` 单调增加到最终 `4456`；
- 每个 chunk 的 `total_tokens` 均等于 prompt + 当前 completion；
- response ID 和 model 始终唯一，但 `created` 是单调递增的 chunk timestamp，而不是固定的 response timestamp；
- 最后顺序仍为唯一 `finish_reason=stop`、final `choices=[]` usage、`[DONE]`、唯一 cost sidecar。

因此 v1.0.1 的“core totals 必须从第一次出现起完全相同”仍是错误的 provider-shape assumption。正确的
construct-irrelevant gate 应当要求 prompt 固定、completion/total 单调不回退、每个 chunk 内部算术一致，并将
最后一个 usage snapshot 记录为 final usage。Identity 应要求 response ID/model 固定、`created` 单调不回退，
并同时记录 first/last timestamp。

stream-003 永久 FAIL，不 repair、不追认、不进入 local validator，也不启动 full-size。修正只能应用于新提交、
新协议和新 synthetic attempt；model-visible task 与 semantic gates 不变。
