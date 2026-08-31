# Local-ranking evaluator qualification protocol v1.4

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Technical correction approved；paid DeepSeek calls pending Robert's explicit cost approval**

本文件仅替换 [qualification v1.3](local-ranking-evaluator-qualification-protocol-v1.3.md) 中两次失败的
DeepSeek text transport。Corrected 12-case/24-query input、Kimi K3、双镜像、`high` effort、blind mapping、
controller audit 与全部准入阈值不变。

## 1. Trigger and decision

DeepSeek V4 Flash 在 Kimi Code/OpenCode Go text transport 的两个全量 attempts 中分别：

- qualification-004 orientation-1：24 judgments，但 response schema 误用 bundle schema；
- qualification-005 orientation-2：24 judgments，但完全漏掉已显式要求的 response schema。

两份失败 output 在 schema-only diagnostic 后其余 24 judgments 均可通过，说明当前瓶颈是 closed-output
transport reliability，而不是已观察到的 setwise judgment 内容。按照
[DeepSeek transport research](../research/deepseek-v4-flash-structured-transport.md) 与既有 fallback 顺序，v1.4
保留同一 `deepseek-v4-flash/high`，改用官方 `POST /responses` + `text.format=json_schema`；不先升级 Pro。
Provider schema 之后仍必须通过本地 `operational_judge finalize`，不能把 HTTP 200 当成科学验证。

## 2. Frozen preparation

- Adapter commit: `1aafd39 add: constrain deepseek judge responses`；
- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.5 protocol SHA-256:
  `1147a4f1a079e72ef7c26d526f3dac03b303602c421f93283e4494a6fcf1f3e8`；
- Combined spent input manifest SHA-256:
  `491ce2f205251098da98b2b4bc03286565864a85e2cf9d63fb2ea5bbea1b64c1`；
- Setwise preparation:
  `artifacts/local-ranking-prototype/setwise-v1.5-qualification/attempts/spent-dev-holdout-003-official-responses/manifest.json`，
  SHA-256 `de1198a4b949f68059393e33b4fe6545232771464b13bc2b30240620369fd7de`；
- Private mapping commitment:
  `339ad6034a7c0e9bd17b55ad57c05fff1a5fc787f3a8d0066752c106442271ec`；
- Tool-less agent SHA-256:
  `5559ff5c9718bb295e6bad25f2747c9ea6ead3c7e5118086ae601f37c65aedfb`。

| evaluator | transport | orientation | prompt bytes | prompt SHA-256 |
| --- | --- | ---: | ---: | --- |
| Kimi K3 | Kimi Code CLI 0.39.1 | 1 | 265418 | `d0000586c252e58dbba376c1ae96f9887903aac132e40269282f525589a38461` |
| Kimi K3 | Kimi Code CLI 0.39.1 | 2 | 265418 | `df4d90a153e428f015b3547f75871d514fa5c19caa900ae5dc816f1a6cdbf69b` |
| DeepSeek V4 Flash | official Responses JSON Schema | 1 | 265436 | `5e5b551f1e7f0c0b714afd45f988438ef363a282740bf4e2ef7ceeaca1aa4451` |
| DeepSeek V4 Flash | official Responses JSON Schema | 2 | 265436 | `cf064df4f4caf6214fa4a199628a8c1652fd5f4985a6f52587c929bda063b575` |

DeepSeek exact credential-free requests：

| orientation | preparation manifest SHA-256 | request bytes | request SHA-256 | schema SHA-256 |
| ---: | --- | ---: | --- | --- |
| 1 | `5fc016383169e3b734e8d2fc5131efc6c78c9d92ded9ef89714b9e1f9d07a442` | 273275 | `68cb731f725d746110ad31318645757e85bd7a30c70dc28c9a3083650464a45b` | `2b169216640d716da6198a56146e145b8d0b1e6c68901a76867eb59d6d62bbbd` |
| 2 | `060fd01a83ddc450ed3e4f4db7ec46501292863b9dda944442e1ecb5f92f3548` | 273275 | `f33552e30b605c10285722d3cb7630cf6ec89a1c47b85d4d31d9c38146257a64` | `2be6a28d1d801566fe7af0da5d0d9a12c4e6309f554986dc5ecafed048b83a91` |

Request 固定 `https://api.deepseek.com/responses`、model `deepseek-v4-flash`、
`reasoning.effort=high`、non-streaming、no tools、`max_output_tokens=131072`。Credential 不进入 request、
artifact、日志或 commit；response 必须满足 completed/no error/no incomplete、exact model、单一 output_text、
usage consistency，再交给原 closed semantic validator。

## 3. Calls, cost ceiling, and failure policy

新 attempt ID 固定为 `qualification-006`。先运行 DeepSeek orientation-1 account/schema smoke；只有 provider
和 local validator 都 24/24 PASS 才运行 orientation-2，之后才运行两次 Kimi fresh sessions。任何 prior
judgment 均不得复用。

DeepSeek 官方调用共 2 次。因为尚未调用 provider tokenizer，预算使用更保守的“一 raw request byte 至多按
一 input token”上界：每次 input ≤273,275 tokens，output ≤131,072 tokens。按 2026-09-01 官方 peak
价格（cache-miss input `$0.44/M`、output 含 reasoning `$1.32/M`），两次最坏估算：

```text
2 × (273275 × 0.44 + 131072 × 1.32) / 1_000_000 < USD 0.59
```

当前 off-peak 价格约减半，但授权按 peak `< USD 0.59`。实际成本以 response usage 和调用时公开价格派生，
不是最终账单。Kimi K3 两次使用现有 managed quota，本地 harness 无 USD telemetry，不伪造成本。

只对未收到完整 2xx body 的 network error、HTTP 429/500/503 允许整份 orientation 最多一次新 attempt；
400/401/402/422、completed=false、schema/coverage/local validation failure 都是 terminal，不 retry、不改 schema、
不静默降级到 Chat Completions/JSON object/其他模型。

## 4. Qualification gates

v1.3/v1.2 的 mechanical 24/24、mirror ≥23/24、block flip、side-collapse、cross-model ≥75%、6-item blind
grounding audit、identity/isolation gates 全部原样适用。Qualification 永久为 `spent_diagnostic_only`，通过只
生成 `qualified_for_fresh_v1.4_v1.5` receipt，不产生 ranker winner；fresh formal evaluator calls 仍需独立
exact request/cost authorization。
