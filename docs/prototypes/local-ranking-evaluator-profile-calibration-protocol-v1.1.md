# Local-ranking evaluator profile calibration protocol v1.1

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-011 output**

本协议把已通过
[streaming qualification 004](local-ranking-opencode-go-stream-qualification-result-004.md) 的 SSE transport 应用到
原批准的 Flash/high 三组镜像校准。三组规模和 aggregate gates 继续以
[profile calibration v1.0](local-ranking-evaluator-profile-calibration-protocol-v1.0.md) 为准；
qualification-007/008/009/010 与 stream probes 全部保留但不进入新分母。

## 1. Frozen profile, harness, and requests

- Preparation commit: `8557c373d61b876ced1a2790a51937cd6ecb3926`；
- Provider/model/effort: `opencode-go` / `deepseek-v4-flash` / `high`；
- Streaming adapter SHA-256:
  `79cfed00222da6c3ea550bb4d37b1278935b9c5027348ce55d61a532fc98d84b`；
- Profile aggregator SHA-256:
  `ae19f3da83aed0a80eae98cfc99f033f57d873252a04b41aee00295655ed49d3`；
- Preparation root:
  `artifacts/local-ranking-prototype/evaluator-profile-calibration-v1/preparations/flash-high-sse-v1`。

| orientation | bundle SHA-256 | request bytes | request SHA-256 | manifest SHA-256 |
| ---: | --- | ---: | --- | --- |
| 1 | `10b57768cdd367e91f445ffe0a9aa61f563c3b63c42f4efd4af555eb55cf391b` | 269577 | `1777634ffbd2d34c51b290ef00d384321b93da1475ac48f0838290faee5897f5` | `c09f87507477868ef8aaa2af3933a0ca681479437b8844032593564954d34100` |
| 2 | `aee43f68db7406d511766d5a38b4529659c7ac49211f8e2aff428e37704ab1c9` | 269577 | `60286c3ba3e8f0d3910fa63f238f3c2fd141b0f55ab361070f44c7c00017f284` | `9ab0a86d5d107115065cf89490147299efebd07a5d327f2d3ce358e61ad0ff4a` |

两个 requests 固定 `stream=true`、不含 `stream_options`，其他 model-visible fields 与 qualification-007 的
对应 non-streaming requests 相同。原 exact-payload retention authorization 继续适用，receipt 如实记录
retention unconfirmed/user-authorized，不声称 ZDR。

## 2. Fresh attempt and concurrency

根 attempt ID 固定为 `qualification-011-flash-high-sse`，包含 `replicate-1/2/3`，每组两个 orientations。

每组 O1/O2 允许同时运行，最大并发 2；三个 replicates 依次执行。Streaming full-size 单路已经 24/24 PASS，
但没有并发 full-size 证据，因此不提高到并发 3–4。任一路最多等待 15 分钟，不高频轮询。

六路 execution/result 目录互斥且 write-once。必须得到六个唯一 provider response IDs；不得复用 transport
probe、旧 qualification output 或同一 stream body。

## 3. Per-call gates and failure semantics

每一路必须通过 v1.0.2 streaming receipt gates和原 `operational_judge finalize` 24/24 closed validator。

- HTTP 429/5xx、network/remote protocol、SSE truncation 或 provider terminal failure：attempt 标记
  `incomplete` 并停止，不计为 semantic profile FAIL；
- JSON/schema/coverage/evidence/local validator failure：profile reliability FAIL 并停止；
- 不在同一 attempt retry、repair、补 `[DONE]`、拼接另一 call 或只重发不利 items。

只有六路全部 mechanical PASS 后才运行 profile aggregator；此前不计算、展示或选择任何 mirror score。

## 4. Aggregate PASS gates

Profile 必须同时满足：

1. 每组 mirror stable 至少 `22/24`；
2. 至少两组达到原始 `23/24` gate；
3. pooled 至少 `69/72`；
4. 六个 response IDs 唯一；
5. 六路使用同一 frozen SSE transport、每个 orientation 只有一个 frozen request/bundle hash。

固定三组全部进入聚合；不得挑最好一组、追加第四组或把 qualification-007 的 `22/24` 加入分母。

## 5. Conclusion boundary

PASS 后停止 profile ladder，并用 Flash/high SSE 与 Kimi K3 运行一个全新的双模型 panel qualification；本次六路
outputs 不复用为 panel votes。FAIL 后才进入 `Flash/max` streaming synthetic qualification。INCOMPLETE 则先处理
基础设施，不能直接升级模型掩盖 transport failure。

无论结果如何，calibration 仍是 anonymous spent diagnostic：不打开 private mapping、不运行 candidate reducer、
不计算 BM25/E5 winner，也不进入 Downstream Experiment。
