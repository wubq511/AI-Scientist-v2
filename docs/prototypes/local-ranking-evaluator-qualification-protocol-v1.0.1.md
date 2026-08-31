# Local-ranking evaluator qualification protocol v1.0.1

Protocol date: 2026-08-31（Asia/Shanghai）  
Status: **Approved deterministic-contract correction; no v1.0.1 model output inspected**

本文件覆盖 [qualification protocol v1.0](local-ranking-evaluator-qualification-protocol-v1.0.md)
的 exact input/bundle binding，并公开此前遗漏的 quote 长度约束。v1.0 的 evaluator、`high` effort、
isolation、mechanical/mirror/side-collapse/cross-model/controller audit/identity gates 与 failure decision
全部保持不变；本 revision 不读取 mapping、不改变 relevance rubric、不修改 winner 规则，也不使用 fresh data。

## 1. 为什么必须版本化

v1.0 首个 `Kimi K3 / orientation-1` invocation exit code 为 0，raw response extraction 通过，但 judge
validator 在 `lr-hol-01-focused` 返回 `QUOTE_NOT_EXACT`。模型 quote `noiseless and noisy` 是 visible
segment 的 byte-exact substring，但只有 19 Unicode scalars；validator 已要求 20–500，旧 prompt 和 public
draft contract 却未披露该限制。

这是 hidden deterministic contract，而不是模型引用了不存在的内容。旧 attempt
`artifacts/local-ranking-prototype/evaluator-qualification-v1/attempts/qualification-001` 完整保留；raw stdout
SHA-256 `1219adb66f9c09e415d54906a447bc0c6be49838e414aec747e9a390b68f308a`，extraction receipt
SHA-256 `cdacaa0410ff5eff6709e11150271bad930ffdfaabd31c35bb90b905d875b524`。不得补一个字符、只重跑
失败 item、把旧输出纳入资格统计，或继续执行旧 bundle 的另外三个 calls。

修复 commit `147a241 fix: disclose judge quote length gate` 将 bundle/preparation schema bump 到 `v1.0.1`，
并在 public draft contract 与 prompt 中同时声明：每条 quote 必须包含 20–500 Unicode scalars 且为 visible
segment 的 byte-exact substring。Validator 语义未改变，回归测试要求四份 prompt 都显示这一规则。

## 2. Corrected frozen inputs

- Parent v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Corrected spent preparation:
  `artifacts/local-ranking-prototype/setwise-v1.4-dry-run/attempts/spent-holdout-003-quote-contract/manifest.json`，
  schema `local-ranking-setwise-preparation-v1.0.1`，SHA-256
  `bd38345e82ec9f5d75f2ed3aefcda5084f3cc7c7b5a19420396db747af6971cd`；
- Private mapping commitment:
  `c6ebae6f7b0809308da24b66e04a86511e17c327ae13d7e860dc3c714310b868`；
- Tool-less agent SHA-256:
  `5559ff5c9718bb295e6bad25f2747c9ea6ead3c7e5118086ae601f37c65aedfb`；
- judge-kimi orientation 1/2 prompts：各 `132480` bytes，SHA-256
  `4320bed37d1ca5196f6299ecfa84fe97f10dd4e107b7e7cd6c8f9bcb249fd862`、
  `5f73a4d0ad3dc928493f490083fce55622c560b7f7e67a3e00f202024553223c`；
- judge-deepseek orientation 1/2 prompts：各 `132494` bytes，SHA-256
  `7a1e7ab0b313b273139eb6f7da2bcc31f4bdd9ba96f23f29648c88f4b64d6a73`、
  `45966b19f3980f0792c6bac7a0f0be1c3fce7eda302e98bf6aeff2360eef886f`。

新 qualification attempt 必须从四个 fresh sessions 全量开始，仍使用：

| evaluator | Kimi Code alias | effort | orientations |
| --- | --- | --- | --- |
| `judge-kimi` | `kimi-code/k3` | `high` | 1、2 |
| `judge-deepseek` | `opencode-go/deepseek-v4-flash` | `high` | 1、2 |

资格结果仍只允许 `qualified_for_fresh_v1.4` 或 fail/conditional；不得输出 ranker winner。Fresh formal calls
仍需另行报告 exact prompt sizes、调用上界与 retry 上界，本 revision 不自动授权正式调用。
