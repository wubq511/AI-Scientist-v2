# Local-ranking evaluator qualification protocol v1.3

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Approved explicit-output-contract correction；no qualification-005 output inspected**

本文件仅覆盖 [qualification v1.2](local-ranking-evaluator-qualification-protocol-v1.2.md) 的 model-visible
output contract 与 exact prompt binding。v1.2 的 corrected 12-case/24-query input、双模型双镜像、`high` effort、
isolation、retry ceiling 和全部 qualification gates 保持不变。

## 1. Why v1.2 failed closed

qualification-004 的 Kimi K3 两路均 24/24 mechanical PASS。DeepSeek V4 Flash orientation-1 返回 24 个
judgments，但把 bundle root schema `local-ranking-setwise-judge-bundle-v1.1` 写入 response；validator 要求 nested
`draft_contract.schema_version` 的 `local-ranking-setwise-judge-draft-v1.1`，因此原 attempt 按规则 FAIL，未启动
orientation-2，也没有修复 response。

只读诊断把该单一字段替换为已公开的 draft schema 后，其余 24 judgments 全部通过。由于旧 prompt 同时出现两个
schema 常量，却没有明确写出 response 应复制哪一个，该失败不能区分 setwise judgment 能力。v1.3 因而在任何
qualification-005 output 产生前，把以下 validator-enforced、construct-irrelevant 规则直接写入 prompt：

- exact response schema 与 attestation；
- winner/catastrophic enums、每个 item 恰好一次；
- unique visible refs、trimmed support 与 rationale 长度；
- 禁止推断 retrieval method、ground-truth label 或 prior result。

不修改 bundle、数据、side mapping、rubric、分数、资格阈值或 validator。为保持模型间公平，Kimi 和 DeepSeek
全部重新运行，不能复用 qualification-004 的 Kimi PASS。

## 2. Frozen binding

- Harness commit: `64cdfab fix: expose judge output contract`；
- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.5 protocol SHA-256:
  `1147a4f1a079e72ef7c26d526f3dac03b303602c421f93283e4494a6fcf1f3e8`；
- Corrected combined input manifest SHA-256:
  `491ce2f205251098da98b2b4bc03286565864a85e2cf9d63fb2ea5bbea1b64c1`；
- Explicit-contract preparation:
  `artifacts/local-ranking-prototype/setwise-v1.5-qualification/attempts/spent-dev-holdout-002-explicit-contract/manifest.json`，
  schema `local-ranking-setwise-preparation-v1.1`，SHA-256
  `b71fc9b932193d4481520fc0920c635e0cc088165c85b5408e4afd2ce074f7ab`；
- Private mapping commitment:
  `339ad6034a7c0e9bd17b55ad57c05fff1a5fc787f3a8d0066752c106442271ec`；
- Tool-less agent SHA-256:
  `5559ff5c9718bb295e6bad25f2747c9ea6ead3c7e5118086ae601f37c65aedfb`。

| evaluator | orientation | items | prompt bytes | prompt SHA-256 |
| --- | ---: | ---: | ---: | --- |
| judge-kimi | 1 | 24 | 265418 | `d0000586c252e58dbba376c1ae96f9887903aac132e40269282f525589a38461` |
| judge-kimi | 2 | 24 | 265418 | `df4d90a153e428f015b3547f75871d514fa5c19caa900ae5dc816f1a6cdbf69b` |
| judge-deepseek | 1 | 24 | 265433 | `2bb30068533f50badd48ae5df057e1b6e23623d17013bcde161ea7e7d82ea67e` |
| judge-deepseek | 2 | 24 | 265433 | `fbce8d08b934af46e0bdaf4ce43032252c1109f866719d7ee5025833866ad98d` |

新 attempt ID 固定为 `qualification-005`。四路必须为 fresh/tool-less/互斥工作目录，Kimi Code CLI `0.39.1`；
Kimi `kimi-code/k3` 与 DeepSeek `opencode-go/deepseek-v4-flash` 均使用 `high`。完整准入条件和失败处理以
v1.2 第 2 节为准；qualification-001 至 qualification-004 全部保留且排除。
