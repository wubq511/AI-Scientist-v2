# Local-ranking evaluator profile calibration protocol v1.3

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-014 output**

本协议只修正
[qualification-013](local-ranking-evaluator-profile-calibration-result-013.md) 暴露的 full-size max stream
infrastructure risk。Profile、匿名任务、双镜像、三组 aggregate gates 和 no-retry 规则保持
[v1.2](local-ranking-evaluator-profile-calibration-protocol-v1.2.md) 不变；唯一运行策略变化是把并发 2 降为严格
串行 1。

## 1. Frozen correction and exact inputs

- Harness commit: `a0fa03c33f3ed9112ec48402fd4e6a236800fe00`；
- Streaming adapter SHA-256:
  `f1eae4260401b2d39adc8b01204e5fb2e29214c71c28c7a9a438f60858ca4fc2`；
- Adapter tests SHA-256:
  `569f5fc425031ab12b40159e7bd52918d7c1b0fd2f46cd50855374c10fe38972`；
- Profile aggregator SHA-256:
  `ae19f3da83aed0a80eae98cfc99f033f57d873252a04b41aee00295655ed49d3`；
- Provider/model/effort: `opencode-go` / `deepseek-v4-flash` / `max`；
- Attempt: `qualification-014-flash-max-sse-serial`。

Requests 与 v1.2 byte-identical：orientation 1 为 269,585 bytes、SHA-256
`cc599c8d1c3f6429ced29f8b43cebf56b78eeca1375c4b38a0d2ce27e46ef3b2`；orientation 2 为 269,585 bytes、
SHA-256 `434c3ee80ba8a9367828bbc90abf165cf5ba61e91bf6c6e6e1181957f0e46dd2`。Bundles、prompts、manifests 继续使用
v1.2 表中的 exact hashes，不重新生成或修改。

Parser 只新增一种 fail-closed taxonomy：若 billing sidecar 在 `[DONE]` 前到达，明确返回 `STREAM_INCOMPLETE`。
它不接受缺失 terminal/DONE 的内容、不补 JSON、不改变任何成功流或 judgment semantics。

## 2. Fresh serialized matrix

必须按以下固定顺序运行六次 fresh calls：

```text
r1/o1 → r1/o2 → r2/o1 → r2/o2 → r3/o1 → r3/o2
```

任一时刻最大并发为 1；每路最长等待 15 分钟，不高频轮询。每路写入独立、write-once execution/result 目录，
六个 provider response IDs 必须互异。qualification-013 的五份完整 output 与一份截断 output 全部排除，不能
填入新矩阵。

任一路 HTTP/network/SSE/terminal failure 立即把 qualification-014 判 `INCOMPLETE` 并停止后续调用；
JSON/schema/coverage/evidence/local validator failure 立即判 profile reliability FAIL 并停止。不得在同一 attempt
retry、repair、替换 orientation 或只重发不利 items。

## 3. Unchanged aggregate gates

只有六路都通过 exact profile receipt、normal stop、完整 `[DONE]`、`cost="0"` 与本地 24/24 validator 后，才运行
aggregator。PASS 仍必须同时满足：

1. 每组至少 `22/24`；
2. 至少两组达到 `23/24`；
3. pooled 至少 `69/72`；
4. 六个 response IDs 唯一；
5. 六路 exact bundle/request/profile/transport identity 一致。

不得挑最好一组、追加第四组、降低 gate，或把 qualification-011/013 output 加入分母。

## 4. Interpretation boundary

串行是针对已观察 transport 脆弱性的最小受控干预。若 qualification-014 仍 INCOMPLETE，说明单纯移除本地并发
不足以让该 route 完成可靠的六路矩阵，必须停止并重新研究 provider/output-budget/task decomposition；不能继续
盲目重复。若完整矩阵 semantic FAIL，才按 ladder 进入 Pro/high synthetic qualification。若 PASS，则停止 ladder
并准备全新的 Flash/max + Kimi K3 panel qualification。

无论结果如何，本 calibration 都不打开 private mapping、不运行 candidate reducer、不计算 BM25/E5 winner，也
不进入 Downstream Experiment。
