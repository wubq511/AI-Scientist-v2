# Local-ranking atomic Pro/high calibration protocol v2.0

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Frozen before semantic model output**

## 1. 决策问题

本次实验只判断：删除 24-item 长输出 bookkeeping 后，`opencode-go/deepseek-v4-pro/high` 对同一批 spent
BM25/E5 top-3 evidence sets 的选择，能否在三组 fresh mirrored replicates 中满足已批准的位置稳定性 contract。

这是 evaluator calibration，不是新的 holdout，也不产生可复用的 BM25/E5 candidate vote。无论 PASS/FAIL，
这些 outputs 都标记为 spent calibration evidence；后续 panel 必须重新调用。

## 2. 冻结实现与总 manifest

- source commit：`b2d9161f8bda25fac2dce19bdeed573d84d22b8e`
- profile manifest：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-high-calibration-001/input/profile-manifest.json`
- profile manifest SHA-256：
  `c436a6c15483d7497c3bcd565ba9f7b97460ce66f4a85e957b88919ebd059d67`
- usage snapshot SHA-256：
  `223ac954fbf6e79a25725e5a2a6b4709d819db5672fee88993207f44648dca17`
- frozen transport smoke result SHA-256：
  `b57460388033dd6ced38f7f45bb7b175bea6e55d74137ae83faa44fb71c44d9e`
- provider/model/effort：`opencode-go` / `deepseek-v4-pro` / `high`
- endpoint/profile：Chat Completions JSON object SSE，`max_tokens=16384`
- scheduler max concurrency：4
- input root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-high-calibration-001/input`
- output root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-high-calibration-001/output`

调用前 quota snapshot 为 rolling 0%、weekly 18%、monthly 33%，三个 status 均为 `ok`；model list 包含
`deepseek-v4-pro`。这只证明当前允许发起已冻结预算，不保证调用免费或一定成功。

## 3. 六个 orientation bindings

| replicate | orientation | atomic manifest SHA-256 | transport manifest SHA-256 |
| --- | ---: | --- | --- |
| `r1` | 1 | `68da192f7273869ecd6ace0af7114d850ce85ac634caaad193f90d1e91bd0915` | `ed3d15f5f031d1471c057168942c8f32c190f1a4a26b29891018331245beff73` |
| `r1` | 2 | `f8e02bad1abbb2658d739378efd86bd36fd2d7dbfcb9f3dd1909e1de07049d4b` | `9020218afe0270ac69e46a146639992b3260b3657dc871299cd5a4b96ef670be` |
| `r2` | 1 | `ea07ae975047ce914f916bab171f45fb23325ec7febf0c94b35ebc54c4b416a5` | `f7fcc86507bfb927579772293e43664bef3f1ea64cc8b7e6bbcc2d3828cd6d27` |
| `r2` | 2 | `547f9e9f5cc312075e231e07df0fe5ac6c499b755534dcf8417d30c6b888aa14` | `17faf4eed39b7caba1234e9334c133377508639171e36d4ac26717da6396584b` |
| `r3` | 1 | `396872249c2fb6bae06f7f27563a610452de88233ca9df30a73284e74d873db1` | `6463adc5027f95aa1827a0f2cda78dbefd3c7c743ec21ebb37a65061d0c02247` |
| `r3` | 2 | `478257c7f22d1ee62f53caeae0f376cd17635eb584f352aa72f0eb4386cdd52f` | `321e83d1f61f3a3595edfa0881297f606d72eeb0fb4a5026f672c18383590f3c` |

每个 orientation 恰好 24 logical calls。144 个 prompts 共 1,666,278 bytes，单 prompt 8,996–14,503
bytes，mean 11,571.4 bytes。所有 replicates 对同一 orientation 复用 exact source/input bytes，但必须产生 fresh
provider responses。

## 4. 调用与 retry budget

- 总 logical-call 上限：`24 × 2 × 3 = 144`；
- 每个 logical call 最多 2 个 physical attempts；最坏 physical-call 上限 288；
- attempt 2 只由机器可判定 invalid 触发：transport/HTTP/SSE/截断/非 JSON/closed-schema/handle validation；
- attempt 2 使用 exact 同一 request bytes，不回传错误；
- attempt 1 valid 后禁止任何 retry；winner、score、mirror mismatch 或“不喜欢答案”不能触发 retry；
- execution failure 也写入 canonical ledger 并消耗一次 physical attempt；
- 若中断时完整 `execution-result.json` 已存在，可从证据重建 ledger，不重新调用；若 execution result 未完成，
  fail closed 并停止，不猜测请求是否已被 provider 接受。

Smoke 的 4 calls cost 均为 `0`，但本实验不预设正式 calls 也免费。逐 call usage/cost 必须保留并汇总；成本数值
是观测项，不是语义 gate。

## 5. 固定执行顺序与早停

严格按以下顺序串行完成 orientations，每个 orientation 内最多 4 并发：

1. `r1/o1`，再 `r1/o2`；
2. 计算 r1 mirror stable 与 stable directional counts；
3. 只有 r1 仍可能 PASS 才执行 `r2/o1`、`r2/o2`；
4. 计算 r2 后 pooled maximum；
5. 只有 profile 仍可能 PASS 才执行 `r3/o1`、`r3/o2`；
6. 三组全部完成后运行 frozen aggregator 一次。

早停只在结论数学上已经不可能改变时发生：

- 任一 logical call 两次都 invalid：该 profile run 为 `incomplete`，停止；
- 任一已完成 replicate stable `<22/24`：profile FAIL，停止；
- 任一 replicate stable directional count 为 0：profile FAIL，停止；
- 前两组 pooled stable `+24 <69`：profile FAIL，停止；
- r1 为 22 必须继续；不得因 winner direction 或当前结果“不理想”早停。

未执行的 calls 不算 failure，也不能随后绕过早停补跑。

## 6. Qualification gates

三组均完成时，PASS 当且仅当：

- 每组 mirror stable ≥`22/24`；
- pooled mirror stable ≥`69/72`；
- 每组 stable directional count >0；
- 六条 traces 的全部非空 provider response IDs 唯一；
- evaluator/source/hash/retry/attempt coverage 全部一致且可重放。

First-attempt validity、retry count、winner distribution、tokens、latency 与 cost 只报告，不新增准入门槛。

PASS 后，DeepSeek Pro/high 成为首个可用于后续 fresh panel qualification 的 DeepSeek profile；不再运行 Pro/max。
FAIL 后才用全新 outputs、全新 profile manifest 运行 Pro/max。`incomplete` 先归因于执行未完成，不能冒充 semantic
FAIL，也不能自动升级 max。
