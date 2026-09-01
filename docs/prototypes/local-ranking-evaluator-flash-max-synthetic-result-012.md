# Local-ranking evaluator Flash/max synthetic qualification result 012

Run date: 2026-09-01（Asia/Shanghai）
Status: **PASS — Flash/max exact SSE profile passed transport and 1/1 semantic gates**

适用协议：
[Flash/max synthetic protocol v1.0](local-ranking-evaluator-flash-max-synthetic-protocol-v1.0.md)。本 attempt
只发送一次 synthetic checksum request，没有 retry，也没有发送 full-size payload。

## 1. Observed execution

- Window: `2026-09-01T06:41:21.623569Z` → `2026-09-01T06:42:03.142844Z`；
- HTTP 200，643 个 SSE data events，唯一 normal `stop`、`[DONE]` 与 billing sidecar；
- Provider response ID: `router-4e7fb3f90a6e27cddbedfac85238ca13`；
- Usage: prompt 1,563、completion 2,210、total 3,773 tokens；
- Response model: `deepseek-v4-flash`；receipt requested effort: `max`；
- Cost: `"0"`；
- Raw SSE SHA-256:
  `2ec8133458a74f00812b3b3768192a8f77bff3038fef48c3bd50d28df603092e`；
- Canonical response SHA-256:
  `aa662fa7989fb9d44d5cbec7ab599a9ec1c41d6bd9ea1d786103fa47ffd24f52`；
- Receipt SHA-256:
  `057c301c13ef188427696b491c9fe6998a9d080e280649ba3c189faacad19ebb`；
- Local trace SHA-256:
  `03608d0ddcbedb70a07884a6ba039cf92855649edef7c3116bee64b8cb214b7d`。

## 2. Gate decision

Request/manifest/bundle 均绑定 `deepseek-v4-flash/max`，SSE identity、累计 usage、JSON object、cost 和
write-once evidence gates 全部通过。`operational_judge finalize` 为 1/1 PASS，唯一 judgment winner 为预注册的
`left`。因此 qualification-012 判定 PASS。

Receipt 仍明确记录 `reasoning_execution_proven=false`：本结果证明 provider 接受并回显了该 request profile，
不能证明内部推理档位的实现细节或 full-size evaluator 稳定性。

## 3. Authorized next step

现在只允许从同一 spent anonymous task 确定性生成新的 `max` evaluator bundles/prompts/requests，并在 live output
前冻结 Flash/max 三组 mirror-calibration 协议。qualification-012 response 不进入校准分母，也不复用为 panel
vote。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
