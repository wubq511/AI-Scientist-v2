# Local-ranking evaluator profile calibration result 010

Run date: 2026-09-01（Asia/Shanghai）
Status: **INCOMPLETE — remote protocol failure also reproduced with concurrency 1**

适用协议：
[profile calibration v1.0.2](local-ranking-evaluator-profile-calibration-protocol-v1.0.2.md)。本 attempt 严格串行，
不复用 qualification-008/009 outputs。

## 1. Observed execution

- Replicate 1 orientation 1：HTTP 200、`cost="0"`、24/24 local PASS，total tokens `96,135`
  （其中 cached input tokens `57,856`），provider response ID
  `router-39c54eee18ce0fab8da866584b97e92b`，trace SHA-256
  `72bc1b2acec8944cf19a93d9a72a1d683ae441db83a06180e4898ee06b463472`。
- Replicate 1 orientation 2：在没有任何其他 live request 的情况下运行约 421 秒，随后
  `RemoteProtocolError`；transport-error SHA-256
  `c4b7eeadb3d6f53c0d05d58705946067a663d2c66d1ef5cf10972d2b5eb085bb`。

按冻结规则，qualification-010 为 `incomplete`：不计算 mirror score，不启动 replicate 2/3，不复用
orientation 1 PASS，也不改变 Flash/high 的 semantic qualification 状态。

## 2. Updated diagnosis

串行仍复现约七分钟后的 remote disconnect，因此“并发 admission pressure 是唯一根因”已被否证。成功调用的
canonical JSON 只有约 32 KB，但 provider usage 报告约 38k completion tokens，说明大量生成预算消耗在
model reasoning 或 gateway 不直接暴露的内容上。当前更符合证据的 failure surface 是长时间 non-streaming
Chat connection，而不是本地 Mac 算力、output JSON 大小或两个请求互相竞争。

OpenCode repository 的 live issue evidence 显示 Go Chat endpoint 对 DeepSeek V4 Flash 支持 SSE streaming
（[#41296](https://github.com/anomalyco/opencode/issues/41296)），同时也报告过长 reasoning stream 的中断
（[#44148](https://github.com/anomalyco/opencode/issues/44148)）。因此 streaming 是一个需要独立 qualification
的最小 transport 修复候选，而不是已经证明有效的解决方案。

在 transport 改变获得批准并完成 synthetic/long-request qualification 前，不再启动新的六路 calibration
attempt，避免继续产生不可归因的 incomplete evidence。
