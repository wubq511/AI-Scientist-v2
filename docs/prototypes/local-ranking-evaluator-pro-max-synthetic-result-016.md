# Local-ranking evaluator Pro/max synthetic qualification result 016

Run date: 2026-09-01（Asia/Shanghai）
Status: **PASS — Pro/max exact SSE profile passed transport and 1/1 semantic gates**

适用协议：
[Pro/max synthetic protocol v1.0](local-ranking-evaluator-pro-max-synthetic-protocol-v1.0.md)。只执行了一次
synthetic call，没有 retry。

## 1. Evidence

- Window: `2026-09-01T07:32:00.662028Z` → `2026-09-01T07:32:39.079294Z`；
- HTTP 200，2,789 个 SSE data events，normal stop、`[DONE]`、billing sidecar、`cost="0"`；
- Response model `deepseek-v4-pro`，provider response ID
  `33815762-338e-4c9e-80cd-bed25e171b7c`；
- Receipt requested effort `max`，`reasoning_execution_proven=false`；
- Usage: prompt 1,577、completion 2,785、reasoning 2,204、total 4,362 tokens；
- Raw SSE SHA-256:
  `441da25851603cd70503202efca726ed8d7ac1c11f245f4f101dc4d64f8a9ec3`；
- Canonical response SHA-256:
  `760113f3698e9d794ab45554c8b7deaa5a23a3507d74bc792ff85237a22309c8`；
- Receipt SHA-256:
  `dc5bca070e4f7ce6972355646de6e377b5419297ab72dec68ac29947d30b3d5b`；
- Local trace SHA-256:
  `d8c41a39a253f1b61bc8c3c411f458ffce51d77315c4c6d85ade11c6f1c4b808`。

## 2. Gate decision

Model exact 抄回 bundle self-hash
`0b088922de87b73fa65b30822972ae4fbeffb1758b2c455fd9e566622409cb99` 与 Pro/max evaluator identity；本地
finalizer 1/1 PASS，winner 为预注册的 `left`。因此 qualification-016 PASS。

这只证明一次 synthetic request 的 profile/transport/closed-output 能力，不证明 full-size 24-item coverage、
mirror stability 或 reasoning 内部实现。

## 3. Next step

现在允许生成全新的 Pro/max full-size bundles/prompts/requests，并在 live output 前冻结三组 calibration。由于
Flash/max 在并发矩阵中出现过 premature stream end，Pro/max 从第一路开始严格串行；qualification-016 output
不进入 calibration 或 panel votes。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
