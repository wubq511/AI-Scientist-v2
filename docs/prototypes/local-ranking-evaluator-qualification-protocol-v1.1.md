# Local-ranking evaluator qualification protocol v1.1

Protocol date: 2026-08-31（Asia/Shanghai）  
Status: **Approved for segment-reference schema；no v1.1 model output inspected**

本文件以 [qualification v1.0](local-ranking-evaluator-qualification-protocol-v1.0.md) 的双模型双镜像、
`high` effort、isolation、mirror/side-collapse/cross-model/controller audit/identity gates 为基础，并采用
[evaluator overlay v1.5](local-literature-ranking-comparison-protocol-v1.5.md) 的 segment-reference schema。
旧 exact-quote qualification v1.0/v1.0.1 attempts 全部排除，不能复用 output 或贡献资格统计。

## 1. Frozen inputs

- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.5 protocol SHA-256:
  `1147a4f1a079e72ef7c26d526f3dac03b303602c421f93283e4494a6fcf1f3e8`；
- Harness commit: `8505e1c fix: reference judge evidence by segment`；
- Spent preparation:
  `artifacts/local-ranking-prototype/setwise-v1.5-qualification/attempts/spent-holdout-001/manifest.json`，
  schema `local-ranking-setwise-preparation-v1.1`，SHA-256
  `bca64fc52b9d80453624f3b38dda41ea5fbb9c7db58d49dde160e96ec0fa73e9`；
- Private mapping commitment:
  `877e6ee16baf37ac22462e9a1e926d647abab3815beed9301ef7b6e630654335`；
- Tool-less agent SHA-256:
  `5559ff5c9718bb295e6bad25f2747c9ea6ead3c7e5118086ae601f37c65aedfb`。

| evaluator | orientation | prompt bytes | prompt SHA-256 |
| --- | ---: | ---: | --- |
| judge-kimi | 1 | 132747 | `e66ab9d92b6f02d0838bdbcac0ea19b322bec92859d20828108b6f4a50f78dc5` |
| judge-kimi | 2 | 132747 | `71e7e7d97db4b97df2825a288eaf4e5a68c4cf718151b645a13f3ed82010a2ac` |
| judge-deepseek | 1 | 132762 | `a151ce1dde64ec255bb9e1b38f2e8e28c00a68d70dbbd67ce2a8987354645be3` |
| judge-deepseek | 2 | 132762 | `02ff6e8be7e491cdf8fd04177a76a3f7e4f89c1f75d5541ae96ef6dbbdb471ea` |

Evaluator profile 由 bundle 原样固定：

- `judge-kimi`: `kimi-code/k3`，provider `managed:kimi-code`，effort `high`；
- `judge-deepseek`: `opencode-go/deepseek-v4-flash`，provider `opencode-go`，effort `high`；
- Kimi Code CLI `0.39.1`，global thinking enabled/high；credential-excluded config snapshot 每次绑定。

## 2. Execution and gates

新 attempt ID 固定为 `qualification-003`。四个 orientations 从四个 fresh sessions 全量执行，互斥空工作
目录、空 skills directory、`tools: []`、`subagents: []`，不使用 resume/continue。每次保存 raw
prompt/agent/config/stdout/stderr/timestamps/exit code，经过 immutable response extraction，再经过 v1.1 judge
validator。任何 unknown side/paper/segment、缺 item、额外字段、support/rationale 越界、bundle/evaluator mismatch
或 isolation failure 均 fail closed；不允许局部 repair。

准入条件沿用 v1.0 并按 v1.5 grounding 更新：

1. 四个 orientations 均 24/24 closed validation pass；
2. 每个模型 orientation 1/2 映射回 candidate 后 winner direction 至少 23/24 一致，且任一
   `stratum × query kind` 不得有 2 个 flips；
3. 任一 orientation 不得无内容解释地至少 18/24 选择同一显示侧；
4. 两模型各自 position-stable items 的 mapped winner agreement 至少 75%；
5. 每个 `stratum × query kind` 机械选择 1 item，共 6 个：最小化
   `SHA256("qualification-v1|" + stratum + "|" + kind + "|" + item_id)`。Controller 在不读取 mapping
   时核验四个 orientations 的 evidence ref support 均由所指完整 segment 支持，且 winner/分项/rationale
   一致、不奖励纯长度、不使用外部事实；6/6 全过；
6. 四次 model/config/CLI identity 一致，fresh/tool-less/互斥证据完整；不得宣称 two-provider independence。

通过后只生成 `qualified_for_fresh_v1.4_v1.5` receipt，并绑定本协议、两个 parent protocols、preparation、
四个 extractions/traces、config snapshot 与 controller audit。Qualification 永久为 `spent_diagnostic_only`，
reducer 不得给出 ranker winner。Formal fresh calls 仍需单独报告与授权。
