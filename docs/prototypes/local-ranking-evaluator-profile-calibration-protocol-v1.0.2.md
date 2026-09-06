# Local-ranking evaluator profile calibration protocol v1.0.2

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Frozen serial recovery before qualification-010 output**

本文件只处理 qualification-008/009 的重复 provider infrastructure failure。
[v1.0](local-ranking-evaluator-profile-calibration-protocol-v1.0.md) 的 profile、exact requests、三组规模、
全部 aggregate gates、anonymous evidence boundary 和 no-retry 规则不变；
[v1.0.1](local-ranking-evaluator-profile-calibration-protocol-v1.0.1.md) 的 staggered concurrency 2 被本文件取代。

## 1. New attempt and isolation

新根 attempt ID 固定为 `qualification-010-flash-high`。qualification-008/009 的全部 outputs 均保留但排除；
六个 fresh calls 重新开始，provider response IDs 必须互异。

## 2. Serial schedule

六次调用严格按以下顺序运行，任意时刻最多一个 live request：

1. replicate 1 orientation 1；
2. replicate 1 orientation 2；
3. replicate 2 orientation 1；
4. replicate 2 orientation 2；
5. replicate 3 orientation 1；
6. replicate 3 orientation 2。

每一路 transport 成功后立即运行 local validator，但 mirror/aggregate metrics 只有六路全部 mechanical PASS 后才
计算。仍不在同一 attempt 内 retry；HTTP 429/5xx/network failure 使 qualification-010 `incomplete` 并停止。

串行是当前 evidence-supported 最大安全并发。它不声称 Mac 负责模型推理：Mac 只作为 controller 发送 API
request 和校验 evidence，实际模型计算仍由 OpenCode Go provider 完成。
