# Local-ranking evaluator profile calibration result 013

Run date: 2026-09-01（Asia/Shanghai）
Status: **INCOMPLETE — one Flash/max SSE stream ended before stop and `[DONE]`**

适用协议：
[profile calibration v1.2](local-ranking-evaluator-profile-calibration-protocol-v1.2.md)。本 attempt 使用
`opencode-go/deepseek-v4-flash` / `max`，每组两个 orientations 并发、组间串行。

## 1. Mechanical execution

| replicate | orientation | transport outcome | provider response ID | total tokens / last observed | local validator |
| --- | ---: | --- | --- | ---: | --- |
| 1 | 1 | complete SSE | `router-a7e87d9179c41b6b7b989c8609a704d5` | 101,522 | 24/24 PASS |
| 1 | 2 | complete SSE | `router-c9cc499d3623c05355b1dde3b6566221` | 97,961 | 24/24 PASS |
| 2 | 1 | complete SSE | `router-921fd5ccb08ea1ec5706cdda7bcc26da` | 101,456 | 24/24 PASS |
| 2 | 2 | complete SSE | `router-78b927844fe343d947b8082de07f9377` | 94,559 | 24/24 PASS |
| 3 | 1 | **truncated before terminal** | `router-30e965ad8626b8100bc73d0773bb2f08` | 79,036 | not run |
| 3 | 2 | complete SSE | `router-aa66501e6e3e61f47a6bf87eb01cb7ae` | 98,998 | intentionally not finalized |

Replicate 3 orientation 1 保存了 2,495,472 bytes raw SSE，SHA-256
`3bd8c7ed860e5d196ea8324bfc57e449562d62e8131117d1d97f693e0901e819`。它包含 7,131 个 data events；最后一个
正常 chunk 仍只有 `reasoning_content`、`finish_reason=null`，累计 usage 为 prompt 58,064、completion 20,972、
total 79,036。随后直接出现 `{"choices":[],"cost":"0"}` billing sidecar，连接结束；整个流没有 terminal
`stop`、没有 `[DONE]`、没有完整 JSON judgment。

Harness 因 sidecar 出现在 `[DONE]` 前而 fail closed，原始错误记录为
`INVALID_PROVIDER_RESPONSE: OpenCode Go stream chunk is invalid`。机械证据表明更准确的分类是
`STREAM_INCOMPLETE`；这项分类修正不把失败流变成 PASS，也不允许恢复或拼接内容。

## 2. Protocol consequence

本 attempt 按预注册规则判 `INCOMPLETE`，不是 evaluator semantic FAIL：

- 不运行 profile aggregator，不计算或展示任何 mirror score；
- 不 finalize replicate 3 orientation 2，也不读取其 judgment semantics；
- 不在 qualification-013 内 retry 或补发 orientation 1；
- 不升级到 Pro/high 来掩盖 transport failure；
- 五份完整 response 和一份截断 response 都只作 infrastructure evidence，不复用到新 attempt 或 panel。

## 3. Smallest controlled next step

五路完整 max calls 加一条并发条件下的截断，不能证明并发是根因，但已经说明 full-size max stream 的 provider
capacity/持续连接仍是脆弱变量。下一 attempt 先修正 fail-closed error taxonomy，然后保持 exact bundles、requests、
model 和 aggregate gates 不变，把六路改为严格串行。这样只移除并发负载一个可控变量；不能通过挑选已成功的五路
来缩短新矩阵。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
