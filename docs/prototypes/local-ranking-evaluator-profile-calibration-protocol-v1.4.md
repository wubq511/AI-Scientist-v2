# Local-ranking evaluator profile calibration protocol v1.4

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-017 output**

本协议运行批准 profile ladder 的最后一个 full-size candidate：
[Pro/max synthetic qualification-016](local-ranking-evaluator-pro-max-synthetic-result-016.md) 已 PASS。现在验证
`opencode-go/deepseek-v4-pro` / `max` 在同一 24-item 匿名双镜像任务上的 closed-output 与重复稳定性。

## 1. Frozen profile and exact inputs

- Preparation source commit: `e4adbf0eb8c72fa2cdf06a45f644e1db86bdaaa4`；
- Streaming adapter SHA-256:
  `9106ae5eceb374650ff38a5411acc16d2b9d81eb5b8a17ef4398128172ecce79`；
- Profile aggregator SHA-256:
  `ae19f3da83aed0a80eae98cfc99f033f57d873252a04b41aee00295655ed49d3`；
- Provider/model/effort: `opencode-go` / `deepseek-v4-pro` / `max`；
- Preparation root:
  `artifacts/local-ranking-prototype/evaluator-profile-calibration-v1/preparations/pro-max-sse-v1`；
- Attempt: `qualification-017-pro-max-sse-serial`。

| orientation | bundle file SHA-256 | bundle self-hash | prompt SHA-256 | request bytes | request SHA-256 | manifest SHA-256 |
| ---: | --- | --- | --- | ---: | --- | --- |
| 1 | `9e98b1f9c9e4ffe5c57c3c81219a03c50717a0729bd3447e82c4ca174d898e5c` | `4e8d2db1983dfab5055624a12790bb9ac77d56a3424c62af6d9434e92900f7f2` | `9654a83ae2e2b2924fe33aa2de14d2ad6251e4e956d6ca9450a9b48104aea27b` | 269,579 | `6be9ceab0ad068d0e3ca070104fad486371cbbceae13579d5a10a02a0265c97a` | `3d8b7e9d360e9b536baf918bb584aecd0c58c5d667e84bbd03fa68226290d388` |
| 2 | `b8ccd49bca0e1cb6c6c23d07229f0d875195504ef297fc3f8d02ecb10504aa10` | `800e994595c74be2d6fa5b71adfc673acc126ec1939560f8636064ee2adbf4f3` | `ac2d1e6f5311263e81b38ee197923e4bc84487eb561a7a9a62ed8ed259fb679e` | 269,579 | `c7bda55e589bf678805bb7095959ee890bfc2e9bf21eeb042a841e922b78f159` | `93edae2c3583fea4e8fa1cff1f82f59347a9937fef44a1f33da4657ce0af58d0` |

Bundles 从同一 spent anonymous pair 确定性派生：只更换 bundle ID、evaluator model/effort 与相应 hashes/prompt；
items、顺序、左右分配、rubric、schema 和 visible evidence 不变。Requests 固定 SSE、JSON object、
`max_tokens=32768`、不含 `stream_options`。

## 2. Serialized fresh matrix

基于 qualification-013 的 premature stream end，本 attempt 从一开始严格串行，固定顺序：

```text
r1/o1 → r1/o2 → r2/o1 → r2/o2 → r3/o1 → r3/o2
```

最大并发 1；每路最长 15 分钟。六路目录 write-once、response IDs 必须唯一，不复用任何 Flash 或 synthetic
output。任一路 transport/terminal failure 使 attempt `INCOMPLETE` 并立即停止；JSON/hash/evaluator/coverage/
evidence/local validator failure 使 profile reliability FAIL 并立即停止。不 retry、repair 或替换单路。

## 3. Aggregate gates

只有六路全部通过 exact Pro/max receipt、normal SSE completion、`cost="0"` 和本地 24/24 validator 后才聚合。
PASS 必须同时满足：

1. 每组 mirror stable 至少 `22/24`；
2. 至少两组达到 `23/24`；
3. pooled 至少 `69/72`；
4. 六个 response IDs 唯一；
5. exact bundle/request/model/effort/transport identity 一致。

固定三组全部进入分母；不得挑最好一组、追加第四组、混入历史 output 或降低 gate。

## 4. Final decision boundary

PASS 后停止 ladder，并以 Pro/max SSE 与 Kimi K3 运行全新的双模型 panel qualification；本 calibration output 不
复用为 panel votes。若 semantic FAIL 或在串行条件下 INCOMPLETE，整个既定 profile ladder 停止。后续只能在
新批准协议下重构 evaluator task/output contract 或选择另一模型族，不能继续重复直到过线。

无论结果如何，本 calibration 都不打开 private mapping、不运行 candidate reducer、不计算 BM25/E5 winner，也
不进入 Downstream Experiment。
