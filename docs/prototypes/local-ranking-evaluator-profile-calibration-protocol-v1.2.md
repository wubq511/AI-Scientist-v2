# Local-ranking evaluator profile calibration protocol v1.2

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-013 output**

本协议执行已批准 profile ladder 的第二档：
[Flash/high qualification-011](local-ranking-evaluator-profile-calibration-result-011.md) 正式 FAIL，而
[Flash/max synthetic qualification-012](local-ranking-evaluator-flash-max-synthetic-result-012.md) 已 PASS。现在只比较
`opencode-go/deepseek-v4-flash` / `max` 在同一个 24-item 匿名镜像任务上的运行稳定性，不选择 ranker。

## 1. Frozen profile, harness, and requests

- Preparation source commit: `1ce4c2b1a725ddb15b8a01d5b0e94c2169511f46`；
- Provider/model/effort: `opencode-go` / `deepseek-v4-flash` / `max`；
- Streaming adapter SHA-256:
  `0e1efb1f35b98b64e8be33a57166d25e8c25424d6eec2029b4d58989e0dac8f2`；
- Profile aggregator SHA-256:
  `ae19f3da83aed0a80eae98cfc99f033f57d873252a04b41aee00295655ed49d3`；
- Preparation root:
  `artifacts/local-ranking-prototype/evaluator-profile-calibration-v1/preparations/flash-max-sse-v1`。

| orientation | bundle SHA-256 | prompt SHA-256 | request bytes | request SHA-256 | manifest SHA-256 |
| ---: | --- | --- | ---: | --- | --- |
| 1 | `5b499b1fe791e066e090a62ae340d234eddecb15aa9ded4182c358cd43e7e24a` | `37ccd921ef543341956223c85aa2421ff3fabc5672b036c386b06247977282a6` | 269,585 | `cc599c8d1c3f6429ced29f8b43cebf56b78eeca1375c4b38a0d2ce27e46ef3b2` | `0c70d75e400b385182413d62a2b71d9299a1355888a59155ed8e023e5ac67e96` |
| 2 | `83d65dad30612b4c4e7da1313c5c918ced7863b1300f4185305c329afd03c89c` | `61af7448e1cfe4ce645ed609964922cce0bba5ddcbcbdc6e79a90ade7baca357` | 269,585 | `434c3ee80ba8a9367828bbc90abf165cf5ba61e91bf6c6e6e1181957f0e46dd2` | `6a34e646623a2d81476633250a69b82c2887881a30e16daac5c45b3e43fc9731` |

新 bundles 从 qualification-011 使用的同一对 spent anonymous bundles 确定性派生：只更换
`bundle_id`、把 evaluator `reasoning_effort` 改为 `max`、重算 self-hash 和 prompt。Items、顺序、左右分配、
rubric、schema 和 visible evidence 均不变。Requests 固定 `stream=true`、不含 `stream_options`，preparation
schema v1.1 将 bundle、request 与 max identity 绑定。

原 exact spent payload retention authorization 继续适用；receipt 如实记录 retention unconfirmed/user-authorized，
不声称 ZDR。

## 2. Fresh attempt and controlled concurrency

根 attempt ID 固定为 `qualification-013-flash-max-sse`，包含 `replicate-1/2/3`，每组两个 orientations。

每组 O1/O2 同时运行，最大并发 2；三个 replicates 依次执行。任一路最长等待 15 分钟，不高频轮询。六路
execution/result 目录互斥、write-once，必须得到六个唯一 provider response IDs；不得复用 qualification-011/012
或其他历史 output。

## 3. Per-call gates and failure semantics

每一路必须通过 preparation v1.1 profile binding、SSE receipt gates 和原 `operational_judge finalize` 24/24 closed
validator。Receipt 必须同时记录 model `deepseek-v4-flash`、`reasoning_effort_requested=max`、normal stop、完整
`[DONE]`、`cost="0"`；`reasoning_execution_proven` 保持 false。

- HTTP 429/5xx、network/remote protocol、SSE truncation 或 provider terminal failure：attempt 标记
  `incomplete` 并停止，不计为 semantic profile FAIL；
- JSON/schema/coverage/evidence/local validator failure：profile reliability FAIL 并停止；
- 不在同一 attempt retry、repair、补 `[DONE]`、拼接另一 call 或只重发不利 items。

只有六路全部 mechanical PASS 后才运行 aggregator；此前不计算、展示或选择任何 mirror score。

## 4. Aggregate PASS gates

Profile 必须同时满足：

1. 每组 mirror stable 至少 `22/24`；
2. 至少两组达到 `23/24`；
3. pooled 至少 `69/72`；
4. 六个 response IDs 唯一；
5. 六路使用同一 frozen SSE transport、每个 orientation 只有一个 frozen request/bundle hash。

固定三组全部进入聚合；不得挑最好一组、追加第四组或把任何 Flash/high output 加入分母。

## 5. Conclusion boundary

PASS 后停止 profile ladder，并用 Flash/max SSE 与 Kimi K3 运行一个全新的双模型 panel qualification；本次六路
outputs 不复用为 panel votes。FAIL 后才进入 `deepseek-v4-pro/high` 的新 synthetic qualification；INCOMPLETE
则先处理基础设施，不能用升级模型掩盖 transport failure。

无论结果如何，本 calibration 都是 anonymous spent diagnostic：不打开 private mapping、不运行 candidate
reducer、不计算 BM25/E5 winner，也不进入 Downstream Experiment。
