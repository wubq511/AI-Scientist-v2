# Local-ranking atomic Pro/high calibration result v2.0

Run date: 2026-09-01（Asia/Shanghai）  
Protocol: [Atomic Pro/high calibration protocol v2.0](local-ranking-atomic-pro-high-calibration-protocol-v2.0.md)  
Result: **FAIL at frozen r1 early stop; r2/r3 were not called**

## 1. Evidence identity

- model-output source commit：`b2d9161f8bda25fac2dce19bdeed573d84d22b8e`
- protocol commit：`bb950c2e8ce864a67235ccdb71da0e138ae35fa3`
- pair validator commit：`e480338d7d71e253834d60c2fcfafcdf4dfd0f30`
- profile manifest SHA-256：
  `c436a6c15483d7497c3bcd565ba9f7b97460ce66f4a85e957b88919ebd059d67`
- r1/o1 trace SHA-256：
  `3307a8cde20c131840784d9c30758c7851291acc633af36906060f8377dbedae`
- r1/o2 trace SHA-256：
  `acf42eedcba852938d4acfe9c6d64e83c1afd9e1b429e039da7ef30e034a2649`
- pair result SHA-256：
  `4802502f46558b6ded022d5d8eb43a19f156e9587285b7af4e9430f97cbcd974`
- provider/model/effort：`opencode-go` / `deepseek-v4-pro` / `high`

## 2. Frozen gate result

| replicate | mirror stable | minimum | stable directional | decision |
| --- | ---: | ---: | ---: | --- |
| `r1` | `20/24` | `22/24` | 14 | `stop_profile_failed` |

四个 mirror-unstable items：

- `lr-dev-02-focused`
- `lr-dev-05-focused`
- `lr-hol-01-broad`
- `lr-hol-02-broad`

Orientation 1 winner distribution 为 left 6、right 10、tie 6、both_bad 2；orientation 2 为 left 10、right 6、
tie 6、both_bad 2。总体分布在镜像后对称，但具体 4 个 item 没有保持 candidate direction；实验单位是 item，
因此总体计数对称不能覆盖 pair-level mismatch。

`stable_directional_count=14`，所以这不是全 tie/both_bad 退化。真正触发早停的是 `20 < 22`。按冻结协议，
该事实在 r1 完成时已经使 profile qualification 不可能；r2/r3 的 96 logical calls 没有发出，也不得事后补跑
来挑选更好的三组。

## 3. 执行完整性

- r1/o1：24/24 first-attempt valid，0 retry，24 physical calls；
- r1/o2：24/24 first-attempt valid，0 retry，24 physical calls；
- 合计：48 logical = 48 physical，0 invalid、0 retry、0 exhausted；
- 48 个 provider response IDs 全部由 orientation resolver 验证为非空且唯一；
- 每个 call 的 request、raw SSE、safe headers、response、receipt、execution result 与 copied ledger 可重放；
- r1/o1 wall 535.452s；r1/o2 wall 568.609s；每个 orientation 内 concurrency 上限 4；
- run-result SHA-256：o1
  `9883fdf52e2a6a3f98405558d3f8024b46bad42c8172470ccea134256bfe81cd`，o2
  `3a132287faeba88438856a325307ad032435025657a2bb3dc0d6515790427858`。

因此 FAIL 不能归因于长 JSON 漏题、ID 抄写、schema error、transport retry 或调用不完整；Atomic redesign 已经
成功隔离了这些 bookkeeping 变量，剩余失败直接落在当前 Pro/high/profile/rubric/evidence 的 mirror stability。

## 4. Usage 与 cost

| orientation | prompt | completion | reasoning | total | receipt cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| r1/o1 | 58,864 | 108,230 | 102,127 | 167,094 | `0` |
| r1/o2 | 58,864 | 114,100 | 108,112 | 172,964 | `0` |
| total | 117,728 | 222,330 | 210,239 | 340,058 | `0` |

调用前 usage 为 rolling 0%、weekly 18%、monthly 33%；调用后为 rolling 16%、weekly 25%、monthly 36%，状态均
为 `ok`。调用后 snapshot SHA-256：
`298eb7738b222e7db08a63451fe28fea873434a0d382534a56da362b1fa158ba`。Receipt cost 为 0 不等于没有 quota
消耗；usage percentage 已明确上升。

## 5. 结论与下一步

DeepSeek Pro/high 在 atomic contract 下仍未达到最低 operational reproducibility，不能担任后续 panel judge。
这不证明 DeepSeek Pro 模型族永远不能裁判，也不证明四个 unstable items 存在客观唯一答案；它只否决当前
provider/model/high/profile 组合。

按预先冻结的 ladder，下一步允许使用同一 inputs/contract、全新 provider responses 测试 Pro/max。不得改 rubric、
unstable items、门槛或 token ceiling，也不得复用本次 48 votes。Pro/max 需要新的 usage snapshot、profile manifest
和 pre-output protocol；若 Pro/max 也在 r1 失败，再决定是否停止 DeepSeek 方案或修改 rubric/data design。
