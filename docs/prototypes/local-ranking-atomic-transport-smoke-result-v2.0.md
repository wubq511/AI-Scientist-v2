# Local-ranking atomic transport smoke result v2.0

Run date: 2026-09-01（Asia/Shanghai）  
Protocol: [Atomic transport smoke protocol v2.0](local-ranking-atomic-transport-smoke-v2.0.md)  
Result: **PASS — semantic scheduler max concurrency frozen at 4**

## 1. 冻结身份

- source commit：`23cb14d95522f9c751bf57418461c4b8d1f6bb6f`
- protocol commit：`5dce8ca539be722ffb1d554403f9bca756de00d0`
- preparation manifest SHA-256：
  `89a6d0da77f56e8318041dfd32e8f937345214b65da86041ca0cf73908c0ab51`
- output result SHA-256：
  `b57460388033dd6ced38f7f45bb7b175bea6e55d74137ae83faa44fb71c44d9e`
- provider/model/effort：`opencode-go` / `deepseek-v4-pro` / `high`
- request profile：JSON object、SSE、`max_tokens=16384`
- frozen concurrency：4
- output root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/transport-smoke-001/output`

## 2. 调用前后状态

调用前 authenticated usage snapshot：

- rolling：0%，`ok`；
- weekly：18%，`ok`；
- monthly：33%，`ok`；
- public model list HTTP 200，包含 `deepseek-v4-pro`。

调用后 snapshot 仍为 rolling 0%、weekly 18%、monthly 33%，全部 `ok`。百分比粒度没有显示本批变化；实际
usage 与 cost 以逐 call provider receipts 为准，不能据此声称调用没有资源消耗。

## 3. 逐 call 证据

| call | duration | prompt / completion / reasoning / total tokens | cost | provider response ID | receipt SHA-256 |
| --- | ---: | --- | ---: | --- | --- |
| `smoke-001` | 2.911s | 148 / 55 / 40 / 203 | `0` | `ef4dc62c-6c11-498f-80f0-9ce9e1aa698b` | `4868a20498da1b0dffc463eef915a8487d6a2734f93e55b367bca7aa16e6a3ee` |
| `smoke-002` | 2.634s | 148 / 52 / 37 / 200 | `0` | `674bdca3-15eb-4292-86cd-583173bc6aa6` | `5135f240b9640ce7abcaad03c05ad7a7e45a3a38760d85665a1cdfa2852c4e19` |
| `smoke-003` | 2.512s | 148 / 42 / 27 / 190 | `0` | `4f2c209e-6273-4e65-9c09-a15cf9424fbe` | `ce58191208f876722303c1e92004f5886a206e492953e4c0ff038cde0a3a70c7` |
| `smoke-004` | 2.310s | 148 / 52 / 37 / 200 | `0` | `202f2f6a-9996-4bc8-96d3-c82b6cadb927` | `9885dbd8387fc0cde448d39e8c13f7647e9894ba7464efbbc4ee2a3e2f23bafb` |

合计 prompt 592、completion 201、reasoning 141、total 793 tokens；receipt cost 合计 `0`。最早 start 到最晚
finish 为 2.911 秒，四个 call 的时间区间重叠，证明 scheduler 实际并发执行，不是串行完成后再汇总。

## 4. Gate 结果

- 4/4 HTTP 200、`text/event-stream`、normal terminal + `[DONE]`：PASS；
- 4/4 exact probe closed JSON 且没有串 call：PASS；
- 4/4 model identity 与 requested `deepseek-v4-pro` 一致：PASS；
- 4/4 canonical receipts 绑定 preparation/prompt/request/response：PASS；
- 4 个 provider response IDs 非空且唯一：PASS；
- raw SSE、safe headers、timestamps、usage、cost、response 和 receipt 全部 write-once 保存：PASS。

因此不需要创建 concurrency 2 或 1 的 fallback smoke。后续 Pro/high semantic calibration scheduler 的并发上限
冻结为 4，但每个 semantic logical call 仍遵守 first-valid、最多两次 physical attempts；并发 PASS 不降低任何
语义或证据完整性要求。

## 5. 不能从本结果推出什么

本结果不能推出 DeepSeek Pro/high 能稳定判断文献集合，也不能推出 BM25/E5 winner。四个 probe 的答案仅用于
验证 transport 和隔离；不得复用为 calibration 或 panel votes。下一步必须另行冻结六个 semantic orientation
manifests、144 logical-call budget、retry state machine 和 early-stop receipts，之后才能运行 Pro/high calibration。
