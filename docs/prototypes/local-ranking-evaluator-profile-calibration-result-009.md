# Local-ranking evaluator profile calibration result 009

Run date: 2026-09-01（Asia/Shanghai）
Status: **INCOMPLETE — remote protocol failure under staggered concurrency 2**

适用协议：
[profile calibration v1.0.1](local-ranking-evaluator-profile-calibration-protocol-v1.0.1.md)。本 attempt 排除
qualification-008 outputs，从六个 fresh calls 重新开始；replicate 1 orientation 2 比 orientation 1 晚约 45 秒
入场。

## 1. Observed execution

- Orientation 1 从 `2026-09-01T01:57:20.849163Z` 运行到
  `2026-09-01T02:04:21.551316Z`，随后 `RemoteProtocolError`；transport-error SHA-256
  `c4b7eeadb3d6f53c0d05d58705946067a663d2c66d1ef5cf10972d2b5eb085bb`。
- Orientation 2 HTTP 200、`cost="0"`、total tokens `88,959`、provider response ID
  `router-f233d1b7ac237d25c17af548e337beaa`；raw response SHA-256
  `a4c7eba64b48d8746e22ddb91f2c95fc505e67d8e5d0f0eacffd5179ff6dfee4`。

按冻结规则，orientation 2 不进入 local semantic validation，replicate 2/3 不启动，qualification-009
不计算 mirror score。所有 outputs 保留但不得复用。

## 2. Concurrency conclusion

qualification-008 在同时入场的并发 2 下出现 HTTP 500；qualification-009 在 staggered concurrency 2 下出现
远端断连。两次都表现为同一并发窗口内一条 full-size request 成功、另一条失败。它仍不能证明因果关系，
但已经是足以改变执行拓扑的重复操作证据：当前 OpenCode Go route 不应同时承载两条约 58k input tokens、
约 31k–35k output tokens 的 judge calls。

下一 attempt 必须严格串行，不能提高到并发 3–4。该变化只减少 provider admission/connection pressure，
不改变 evaluator task 或 qualification gates。
