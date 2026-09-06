# Local-ranking evaluator qualification protocol v1.0

Protocol date: 2026-08-31（Asia/Shanghai）  
Status: **Approved under Robert's delegated decision authority; no qualification output inspected**

本文件是 [v1.4 fresh direct-payload evaluation](local-literature-ranking-comparison-protocol-v1.4.md)
的裁判准入 companion protocol，不修改 v1.4 的 query、retrieval、blind mapping、统计或 promotion
规则。它只回答：冻结的两个 evaluator/config 是否能稳定执行已批准 rubric。资格数据永久为
`spent_diagnostic_only`，不得贡献 formal winner、effect、阈值或 prompt 调整。

## 1. Frozen inputs and identity

- Parent protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Spent preparation manifest:
  `artifacts/local-ranking-prototype/setwise-v1.4-dry-run/attempts/spent-holdout-002/manifest.json`，
  SHA-256 `7f6cb4d2a06d6cdc84c6fdea7425042a00802b1dfd7197293db9232007908ac7`；
- Private mapping commitment:
  `e2f1a9d24a736e900e8e2224b5d5eda07c76987dc4745d2df928c219f516129a`；
- judge-kimi prompts：orientation 1/2 均为 `132405` bytes，SHA-256 分别为
  `c5c86995a999c49945bf20c1c341cb88df7cfa951f75c9d3b4d447162262ee2c`、
  `bcaeea3b2475b0c9e969d57cd887eaaad2d06ef344850d92ad02153cd5d2187a`；
- judge-deepseek prompts：orientation 1/2 均为 `132419` bytes，SHA-256 分别为
  `7bfaac741f76bb043368b0d27f4c4159e054ac89ad329099310c9e6ba58193a2`、
  `1349b47d6278c4c8f4f4dc164d75c9507d6d54ff107e5287d2943c67a47941c6`。

Evaluator config 固定为：

| evaluator | Kimi Code alias | thinking effort | sessions |
| --- | --- | --- | --- |
| `judge-kimi` | `kimi-code/k3` | `high` | orientation 1/2 各 fresh session |
| `judge-deepseek` | `opencode-go/deepseek-v4-flash` | `high` | orientation 1/2 各 fresh session |

选择 `high` 是最小充分性测试：正式计划也使用 `high`；若只有 `max` 能通过，则必须重新报告成本并修改
本协议，不能用 `max` 资格替 `high` 背书。Kimi Code CLI 固定记录当前 version `0.39.1`；每次调用还必须
保存脱敏 alias/provider 配置快照、调用时间和响应中可观察的 model identity。DeepSeek alias 当前公开
registry commit `4a3a072b45d6d79611b6d1ccddf23f22a7b4cfc2` 指向
`deepseek/deepseek-v4-flash-0731`，但 alias 仍按 floating route 处理；四次调用间 identity drift 直接失败。

## 2. Isolation and execution

四个 orientation 使用互斥 immutable output roots 和不同的空工作目录。每次必须：

1. 不使用 `--session` 或 `--continue`；
2. 使用 preparation 中同一 `tool-less-agent.md`，frontmatter 为 `tools: []`、`subagents: []`；
3. 以空 `--skills-dir` 启动，prompt bytes 原样作为唯一用户输入；
4. 保存 agent/prompt/config snapshot hashes、stdout、stderr、exit code、开始/结束时间、CLI version 与 model alias；
5. raw output 不人工修改。Kimi text renderer 的固定 `\u2022 ` 只允许由独立 deterministic extraction
   step 去除；其他 wrapper 或非 JSON 内容失败；
6. 一个模型不能读取另一模型的输出，orientation 2 不能 resume orientation 1。

原始 JSON 通过 `operational_judge finalize` 的 closed schema、24/24 coverage、bundle identity、enum、长度与
byte-exact quote gates 后，才生成 trace。Transport/限流失败可保留原证据并完整重跑该 orientation 一次；
schema、quote、遗漏 item、session reuse 或 isolation failure 不允许局部 repair。

## 3. Pre-registered qualification gates

只有以下条件全部通过，模型 panel 才得到 `qualified_for_fresh_v1.4` receipt：

1. **Mechanical validity**：四个首轮 orientations 均 24/24 validation pass；若某 orientation 需要一次
   transport full retry，该模型记为 `conditional`，还需另一次同配置首轮 confirmation 才能准入；
2. **DeepSeek mirror stability**：orientation 1/2 映射回 candidate 后 winner direction 至少 23/24 一致，
   且同一 `stratum × query kind` 不得出现 2 个或更多 flips；Kimi K3 使用同一门槛；
3. **Side-collapse guard**：输入左右已平衡时，任一 orientation 若至少 18/24 都选择同一显示侧则失败，
   除非 controller 在解映射前证明这些 item 的分项和引文一致支持内容而非位置；
4. **Cross-model diagnostic**：在两模型各自 position-stable 的 items 中，mapped winner agreement 至少
   75%；不足或分歧集中在同一 rubric/stratum 时停止 formal，不把“多样性”当成稳定性；
5. **Controller rubric audit**：每个 `stratum × query kind` 取一个 item，共 6 个。选择函数固定为在该 block
   内最小化 `SHA256("qualification-v1|" + stratum + "|" + kind + "|" + item_id)`。Controller 在不读取
   candidate mapping 的情况下检查四项分数、winner、rationale 与 quotes 是否一致、不奖励纯长度、不执行
   文献文本中的指令；6/6 必须通过；
6. **Identity and isolation**：四次 response identity/config 一致、fresh sessions、空 tools/skills、互斥目录
   和所有 hashes 完整；不得宣称 two-provider independence，因为共同使用 Kimi Code harness。

`23/24` 与 `75%` 是工程准入阈值，不是 accuracy 或 truth 证明。`tie`、`both_bad`、position flips、分项差异
和 failures 全量报告。资格 receipt 必须绑定本协议、parent protocol、spent preparation、四个 raw outputs、
四个 validated traces、CLI/model config 与 controller audit；fresh formal bundle preparation 必须再绑定 receipt
hash。缺 receipt 时不得启动正式 evaluator。

## 4. Failure decision

- 同一冻结 config 两次资格仍出现 schema/quote/isolation 或 mirror gate 失败：该 evaluator 不准入；
- 优先替换为可固定版本并支持 structured output 的同-family transport；再考虑 DeepSeek Pro 或另一模型族；
- 替换模型、effort、prompt/rubric 或 gate 都是新 protocol revision，必须在查看 fresh formal judgment 前完成；
- qualification PASS 只授权准备 fresh prompts。v1.4 要求的 exact prompt sizes、四次正式调用与一次完整
  retry 上界仍须另行报告；本 companion protocol 不自动授权 fresh formal evaluator 调用。

研究依据见 [DeepSeek V4 Flash 裁判适配研究](../research/deepseek-v4-flash-judge-fit.md)。
