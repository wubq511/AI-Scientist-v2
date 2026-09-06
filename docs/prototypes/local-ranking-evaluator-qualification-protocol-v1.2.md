# Local-ranking evaluator qualification protocol v1.2

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Approved correction；no qualification-004 model output inspected**

本文件取代 [qualification v1.1](local-ranking-evaluator-qualification-protocol-v1.1.md) 的
holdout-only preparation binding，但不修改其 evaluator、rubric、`high` effort、isolation 或准入阈值。
v1.1 错把 6 cases / 12 queries 的 spent holdout bundle 登记成 24 items；qualification-003 已完成的
Kimi K3 orientation-1 虽机械验证 12/12 PASS，仍因规模不符而永久排除，不能与后续三路混合。

## 1. Corrected frozen inputs

- Harness commit: `dc18caf fix: assemble full judge qualification input`；
- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.5 protocol SHA-256:
  `1147a4f1a079e72ef7c26d526f3dac03b303602c421f93283e4494a6fcf1f3e8`；
- Combined spent input manifest:
  `artifacts/local-ranking-prototype/spent-qualification-input-v1/attempts/spent-qualification-input-001/manifest.json`，
  schema `local-ranking-spent-qualification-input-v1.0`，SHA-256
  `491ce2f205251098da98b2b4bc03286565864a85e2cf9d63fb2ea5bbea1b64c1`；
- Combined scale: 12 cases / 24 queries，small/medium/large 各 4 cases；
- Deterministic replay:
  `spent-qualification-input-002-replay` 与 attempt 001 的 6/6 files byte-identical；
- Corrected setwise preparation:
  `artifacts/local-ranking-prototype/setwise-v1.5-qualification/attempts/spent-dev-holdout-001/manifest.json`，
  schema `local-ranking-setwise-preparation-v1.1`，SHA-256
  `59ea7fd753d9ee6de0ad0f11da35b9c331aef37c8fa64f526c4734478d062958`；
- Private mapping commitment:
  `339ad6034a7c0e9bd17b55ad57c05fff1a5fc787f3a8d0066752c106442271ec`；
- Tool-less agent SHA-256:
  `5559ff5c9718bb295e6bad25f2747c9ea6ead3c7e5118086ae601f37c65aedfb`。

| evaluator | orientation | items | prompt bytes | prompt SHA-256 |
| --- | ---: | ---: | ---: | --- |
| judge-kimi | 1 | 24 | 264880 | `da6aa0837b86b4d4c785eb5c92d88e8af193ce5bc50e394f218fb9291650dddd` |
| judge-kimi | 2 | 24 | 264880 | `d384f6fba5e85b812088b895c1c8c885fbcddf9011d18a3c177c476fcda8c014` |
| judge-deepseek | 1 | 24 | 264895 | `a241b0c5947004e433cbf4de4a319b85ee9751a744dee0b91e606dad36baf3aa` |
| judge-deepseek | 2 | 24 | 264895 | `2ec9cfb1832ca031ec52d373961dd8975fe8734794f17261ea897f9539c9690b` |

Evaluator profile 由 bundle 原样固定：

- `judge-kimi`: `kimi-code/k3`，provider `managed:kimi-code`，effort `high`；
- `judge-deepseek`: `opencode-go/deepseek-v4-flash`，provider `opencode-go`，effort `high`；
- Kimi Code CLI `0.39.1`；credential-excluded config snapshot 每次绑定。

约 265 KB prompt 明显低于两个候选的已核验 context 上限。资格调用共 4 次；允许的 retry ceiling 仍是仅在
transport failure 且没有可解析 response 时整份 orientation 最多一次，不允许 schema/判断失败后重试或局部修复。
本地 harness 不提供可靠 token/cost telemetry，因此保留 raw invocation 时间与响应字节，不能伪造精确账单；
qualification 已由 Robert 授权，fresh formal evaluator calls 仍需另行报告与批准。

## 2. Execution and qualification gates

新 attempt ID 固定为 `qualification-004`。四个 orientations 必须从四个 fresh sessions 全量执行，使用互斥空
工作目录、空 skills directory、`tools: []`、`subagents: []`，不使用 resume/continue。每次保存 raw
prompt/agent/config/stdout/stderr/timestamps/exit code，经 immutable response extraction 后，再由 v1.1 judge
validator fail closed。任何 unknown side/paper/segment、缺 item、额外字段、support/rationale 越界、
bundle/evaluator mismatch 或 isolation failure 均使整个 orientation 失败。

准入条件为：

1. 四个 orientations 均 24/24 closed validation PASS；
2. 每个模型 orientation 1/2 映射回 candidate 后 winner direction 至少 23/24 一致，且任一
   `stratum × query kind` 不得有 2 个 flips；
3. 任一 orientation 不得无内容解释地至少 18/24 选择同一显示侧；
4. 两模型各自 position-stable items 的 mapped winner agreement 至少 75%；
5. 每个 `stratum × query kind` 机械选择 1 item，共 6 个：最小化
   `SHA256("qualification-v1|" + stratum + "|" + kind + "|" + item_id)`。Controller 在不读取 mapping 时
   核验四个 orientations 的 evidence ref support 均由所指完整 segment 支持，且 winner/分项/rationale
   一致、不奖励纯长度、不使用外部事实；6/6 全过；
6. 四次 model/config/CLI identity 一致，fresh/tool-less/互斥证据完整；不得宣称 two-provider independence。

通过后只生成 `qualified_for_fresh_v1.4_v1.5` receipt，并绑定本协议、两个 parent protocols、corrected
input/preparation manifests、四个 extractions/traces、config snapshot 与 controller audit。Qualification 永久为
`spent_diagnostic_only`，reducer 不得给出 ranker winner。

## 3. Excluded attempts

- qualification-001：hidden quote-length contract，排除；
- qualification-002：exact-copy punctuation failure 暴露 construct mismatch，排除；
- qualification-003：segment-reference mechanical 12/12 PASS，但输入仅 half-scale，排除；
- v1.0/v1.0.1/v1.1 bundles、prompts、outputs 均保留为 immutable failure evidence，不得复制 judgment 到
  qualification-004。
