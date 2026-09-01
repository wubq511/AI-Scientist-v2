# Local-ranking evaluator profile calibration protocol v1.0.1

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Frozen execution recovery before qualification-009 output**

本文件只处理
[qualification-008](local-ranking-evaluator-profile-calibration-result-008.md) 的 provider HTTP 500。
[v1.0](local-ranking-evaluator-profile-calibration-protocol-v1.0.md) 的 profile、两份 exact requests、三组规模、
全部 aggregate gates、anonymous evidence boundary 和 no-retry 规则保持不变。

## 1. New attempt

新根 attempt ID 固定为 `qualification-009-flash-high`。qualification-008 的所有成功与失败 outputs 均保留但
排除；qualification-009 从六个全新的 provider calls 开始，仍要求六个 response IDs 互异。

## 2. Admission staggering

每组仍允许最大并发 2，但 orientation 2 在 orientation 1 启动约 45 秒后才入场。三个 replicates 依次执行。
这个变化只减少 simultaneous admission pressure，不改变 request bytes、side assignment、model-visible prompt、
judgment task 或 aggregate metric。

不提高到并发 3–4：qualification-008 已在并发 2 下观察到 full-size request HTTP 500，此时提高并发会增加
基础设施 failure surface，而不是提高可归因的 evaluator evidence throughput。

## 3. Failure semantics

同一 attempt 内仍不 retry。若再次出现 HTTP 429、5xx 或 network timeout，qualification-009 继续按 v1.0
标记 `incomplete` 并停止；不得拼接 qualification-008/009 outputs。JSON/schema/coverage/evidence validation 与
mirror aggregate gates 不变。
