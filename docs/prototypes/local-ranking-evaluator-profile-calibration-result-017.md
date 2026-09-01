# Local-ranking evaluator profile calibration result 017

Run date: 2026-09-01（Asia/Shanghai）
Status: **FAIL — Pro/max produced a non-visible evidence reference**

适用协议：
[profile calibration v1.4](local-ranking-evaluator-profile-calibration-protocol-v1.4.md)。本 attempt 严格串行；
`r2/o1` 触发 terminal semantic gate 后立即停止，没有运行余下三路。

## 1. Observed execution

| replicate | orientation | SSE/profile | provider response ID | total tokens | local validator |
| --- | ---: | --- | --- | ---: | --- |
| 1 | 1 | complete Pro/max；cost 0 | `019e8790-4654-4eb7-af74-f5a3c8a20e3e` | 82,251 | 24/24 PASS；trace `8fac9971961dcacc07f75422953f94c5c42d6a6aabbdd00405b49c35e7e7460c` |
| 1 | 2 | complete Pro/max；cost 0 | `5962445f-509b-46b4-96a2-1d882f92c188` | 85,431 | 24/24 PASS；trace `c9fa9192ff43affe189712e84ec8d82057eb469c11cd8e98901f0b976919d081` |
| 2 | 1 | complete Pro/max；cost 0 | `47d4ae65-ce6f-492f-bfe7-3b4e6115e4a9` | 87,529 | **FAIL：invalid evidence reference** |

三路 raw SSE SHA-256 依次为
`f03efa48f8c6cc51b7e2b49c10b96091ccb8477b4cf78116cb12518ab852efbc`、
`f9211b4de17f2c1880cfd740dfd2c6112045e771de318b668135d949a2b8189a`、
`b0b537ee29cf29d9df560a17870c8db0d61c9d786b56fd211163158c2ca7dbbc`。Receipt SHA-256 依次为
`c5a1ca969e214c93fa793e1274ca68421916d0ac2f00296b3b7f97764f646d7f`、
`84f5f886263296ad222947c9275d21c7a510279122dae121ac2e2e344e54567b`、
`1caa4eed67e19a6f34d7f0ae9696a9ab9c6951ca96f3233f70535715c90edd03`。

## 2. Terminal evidence failure

`r2/o1` 返回了 24 judgments、正确 bundle/evaluator identity 和可解析 closed JSON，但
`lr-dev-04-focused` 的一个 evidence ref 声称左侧存在 paper
`1e43c7084bdcb6b3102afaf301cce10faead2702` / segment
`1e43c7084bdcb6b3102afaf301cce10faead2702-s01`。该 side/paper/segment tuple 不在这个 item 的可见左侧证据中；
另一个右侧 ref 可见。本地 validator 返回 `INVALID_EVIDENCE_REFERENCE`，没有用相似 paper、另一侧或另一 item
替代它，也没有生成该路 trace。

这不是 transport failure：SSE、model identity、stop/DONE、usage、cost 和 24-item coverage 全部通过。它是
full-size evaluator grounding reliability FAIL。

## 3. Final ladder decision

`Pro/max` 不批准为 panel evaluator，且不运行 mirror aggregator。既定 ladder 至此全部结束：

- Flash/high：三组 mirror stability `22/24、20/24、22/24`，pooled `64/72`，FAIL；
- Flash/max：曾 transport INCOMPLETE；串行重跑又出现 20/24 coverage，FAIL；
- Pro/high：synthetic exact bundle hash copying FAIL；
- Pro/max：synthetic PASS，但 full-size evidence grounding FAIL。

按照冻结 stop rule，不继续 Pro/max 余下三路、不追加第四组、不降低 gate，也不再重复直到过线。下一步若继续，
必须先批准新的 evaluator task/output-contract 设计或另一模型族，并做新的最小比较，而不是把现有任何 output
拼成 panel。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
