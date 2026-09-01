# Local-ranking evaluator profile calibration result 008

Run date: 2026-09-01（Asia/Shanghai）
Status: **INCOMPLETE — provider HTTP 500 before the frozen three-replicate matrix completed**

适用协议：
[profile calibration v1.0](local-ranking-evaluator-profile-calibration-protocol-v1.0.md)。本 attempt 使用
`opencode-go/deepseek-v4-flash` / `high`，每组两个 orientations 并行、最大并发 2，组间串行。

## 1. Observed execution

| replicate | orientation | outcome | total tokens | evidence |
| --- | ---: | --- | ---: | --- |
| 1 | 1 | HTTP 200；24/24 local PASS | 93,274 | trace `8208a89d16c8f30f2d7f38c70eb4b24f212a8b5ba6dc877e535631715f98191a` |
| 1 | 2 | HTTP 200；24/24 local PASS | 89,318 | trace `6d2bce18bba3582cddec0d6be57fb04984d999367dc84028f90d178768c162bf` |
| 2 | 1 | HTTP 500；`Internal server error` | unavailable | raw response `a70aed996c08d1241be84d0134dfd458c3ad2f494e584d872acbe2a789329fdb` |
| 2 | 2 | HTTP 200；未进入 local semantic validation | 91,724 | raw response `026c945eb981e13295f3e43790c3fe047a83af2ae4e58d99adbf88600916067f` |

三个成功 response 的 provider IDs 互异，均记录 `cost="0"`。失败 orientation 在约 67 秒后收到 provider
HTTP 500，body 只有 `{"error":{"message":"Internal server error","type":"error"},"type":"error"}`；
没有证据把它归因于 prompt schema、model judgment 或本地 validator。

## 2. Fail-closed consequence

协议已预登记 HTTP 5xx 使整个 qualification-008 `incomplete`，而不是 semantic FAIL。因此：

- 不计算 replicate 1 mirror score；
- 不 finalize 或读取 replicate 2 orientation 2 的 judgment semantics；
- 不启动 replicate 3；
- 不复用任何 qualification-008 output 到下一 attempt；
- 不打开 private mapping、不运行 candidate reducer、不改变 profile ladder。

这次失败还提供了一个操作证据：OpenCode Go 在两个 full-size requests 同时入场时至少出现过一次 HTTP 500。
它不能证明并发必然导致 500，但足以否定在下一 attempt 直接提高到并发 3–4。
