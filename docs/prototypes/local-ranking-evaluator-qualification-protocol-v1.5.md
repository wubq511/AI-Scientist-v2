# Local-ranking evaluator qualification protocol v1.5

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Technical protocol approved；live 24-item calls blocked by v1.6 data-retention gate**

本文件取代 [qualification v1.4](local-ranking-evaluator-qualification-protocol-v1.4.md) 的 DeepSeek official
route，并把 [evaluator v1.6](local-literature-ranking-comparison-protocol-v1.6.md) 的 OpenCode Go direct transport、
model draft v1.2 与数据闸门应用到一次新的全量 qualification。v1.4 没有发送 official request、读取
credential 或产生费用；其 preparation 只保留为被取代的设计证据。

Corrected 12-case/24-query spent input、Kimi K3、双镜像、high effort、blind mapping、controller audit 与原
准入阈值不变。qualification-001 至 qualification-006 全部保留且排除；任何旧 judgment 均不得复用。

## 1. Frozen preparation

- Preparation commit: `f4142b3 add: freeze opencode transport qualification`；
- Base v1.4 protocol SHA-256:
  `9aea0d6e2bffd39a28bfd9af07160dad3d3db7e8f25b7c69172365e3a3ed95fc`；
- Evaluator v1.6 protocol SHA-256:
  `13a3b034df1b83be51e861b4b78f0327cd4f5aaaf386677cf00a5d030b83f789`；
- Combined spent input manifest SHA-256:
  `491ce2f205251098da98b2b4bc03286565864a85e2cf9d63fb2ea5bbea1b64c1`；
- Setwise preparation:
  `artifacts/local-ranking-prototype/setwise-v1.6-qualification/attempts/spent-dev-holdout-001-opencode-go`；
- Setwise manifest SHA-256:
  `676600c8243bbf2b498cbc93c2125626d22b55076649df8e88392e90a67401ac`；
- Private mapping commitment/SHA-256:
  `61c52447cdf57348ca5d91f654c38f51b2a9942b51dbf974483936e366838168`；
- Tool-less agent SHA-256:
  `5559ff5c9718bb295e6bad25f2747c9ea6ead3c7e5118086ae601f37c65aedfb`。

四个 bundles 均为 schema `local-ranking-setwise-judge-bundle-v1.2`、24 items，model-visible root contract
只含 `bundle_sha256/evaluator/judgments`。Orientation 2 已机械验证为 orientation 1 的逐 item exact
left/right swap，query、item order 与其他字段不变。

| evaluator | transport | orientation | prompt bytes | prompt SHA-256 |
| --- | --- | ---: | ---: | --- |
| Kimi K3 | Kimi Code CLI 0.39.1 | 1 | 265151 | `2ede7f8a5613c290aef3e75697daf047440a56282ff76ee6022c10169e6866cc` |
| Kimi K3 | Kimi Code CLI 0.39.1 | 2 | 265151 | `01f7e16fcf3c914dc0911ceae7669294be1c3c8808e16c40860f8daedd9cc05a` |
| DeepSeek V4 Flash | OpenCode Go direct Chat | 1 | 265181 | `4c4dbaf1d674008a53aa1412332176c0a53ea693bed411e11d257fd2cb06a750` |
| DeepSeek V4 Flash | OpenCode Go direct Chat | 2 | 265181 | `220752c4e9eb4f5295cc911f9923942961baaf4bf7c861d1520966c41f11a1f3` |

DeepSeek exact credential-free requests：

| orientation | request bytes | request SHA-256 | preparation manifest SHA-256 |
| ---: | ---: | --- | --- |
| 1 | 269578 | `9c085636616fd1d90a0769ea54d2ef37d4b50be1219bd3798f3f0e61bd908765` | `189cc9ff2ac4f24c44757071c8cf4652c5d3303885d51684032ff8012a4742b2` |
| 2 | 269578 | `2c47348451dc09d78807c026171ad4ea000fba69618e7dee9a86f856e968f243` | `e415b29032e31fcca12c4af6d1898847527cd6582e9459e137985e0df5fbc2f3` |

两份 requests 固定 OpenCode Go `/chat/completions`、wire model `deepseek-v4-flash`、non-streaming、
`response_format=json_object`、`reasoning_effort=high`、`max_tokens=32768`。Synthetic qualification v1.0
已对同一账号/request shape 取得：HTTP 200、`cost="0"`、prompt/completion/total tokens
`1548/4566/6114`、本地 1/1 PASS、winner `left`；receipt/trace SHA-256 分别为
`e932c12acb8dbe8139a625fac2a966127314bc5021c77eb2235e84ec49afc991`、
`1ec1c01b7a0c21d498211aa61d58fe4a24a7a08ed49f5f9fdb674cf4eb0c0ec0`。这只验收 transport shape，
不替代 24-item qualification。

## 2. Attempt, order, and execution isolation

新 attempt ID 固定为 `qualification-007`。只有 v1.6 data-retention gate 满足后，按以下顺序执行：

1. DeepSeek orientation 1 direct request；
2. 仅在 24/24 local PASS 后执行 DeepSeek orientation 2；
3. 仅在 DeepSeek 两路 PASS 后执行 Kimi K3 orientation 1 fresh tool-less session；
4. 最后执行 Kimi K3 orientation 2 fresh tool-less session。

这个顺序先测试仍风险较高的 direct full-size transport，避免 panel 已失败后继续消耗 Kimi quota。四个输出
目录互斥且 immutable；Kimi 使用两个全新 workspace/session、exact `kimi-code/k3`、provider
`managed:kimi-code`、effort `high`、空 tools/subagents/skills，并保存 agent/config/prompt/stdout/stderr/
timestamps/exit。DeepSeek 保存 exact request、raw response、safe headers、timestamps、status、identity、usage、
cost 与 adapter receipt；credential 不进入任何 evidence。

本 protocol 不预授权 retry。Network、HTTP、renderer、JSON、schema、coverage 或 semantic failure 都保留原
attempt 并终止 qualification-007；不得修改 JSON、补字段、续旧 session、重发不利 items、改变顺序或降级
provider/model/effort。

运行等待使用长间隔：DeepSeek 单次最多 3 分钟后检查，Kimi 单次最多 5 分钟后检查；不做高频轮询。

## 3. Mechanical and judgment gates

每一路必须同时满足：

- exact prompt/request/model/provider/effort/identity evidence；
- 24/24 items，closed v1.2 root/judgment schemas，无 unknown/duplicate/missing IDs；
- bundle/evaluator exact binding，1–4 visible segment refs，support/rationale bounds 与 forbidden-text gates；
- 两个 orientations 映射回匿名 arms 后，至少 23/24 winner directions 一致；
- 每个 `stratum × query kind` block 至少一次 side flip，且不是全 left、全 right、全 tie 或全 both_bad；
- 两模型各自 position-stable 后，stable directions 的 cross-model agreement 至少 75%。

任何一项失败都不打开 mapping、不运行 reducer、不追加第三裁判。

## 4. Pre-registered six-item blind grounding audit

在四路 mechanical PASS 后、打开 private mapping 前，controller 先从公开 selection + bundles + traces 选择
6 items：对每个 `small/medium/large × broad/focused` block，取
`SHA256("qualification-v1.5|<stratum>|<kind>|<item_id>")` 最小者。选择只依赖公开 identity/stratum/kind，
不读取 side mapping、candidate identity 或 winner direction。

逐 item 同时审查两个 models、两个 orientations：visible segment 是否真正支持 evidence support、winner 与
四项 scores 是否自洽、是否奖励纯长度/流畅/熟悉度、是否使用 bundle 外事实。任一 selected item 的任一路
grounding FAIL，整个 panel 不准入。

只有 mechanical、mirror、side、cross-model 与 6-item audit 全 PASS 后，才可打开 mapping 计算 qualification
diagnostics。Mapping 仍不得用于修改 prompt、threshold、audit selection 或重跑。

## 5. Data-retention authorization gate

OpenCode Go 页面在 2026-09-01 仍只证明 DeepSeek ZDR agreement 有效到 2026-08-31。24-item prompts 含真实
spent query/corpus 内容；“spent”只表示不能再贡献 winner，不表示数据已经公开。

因此 qualification-007 calls 在以下任一条件满足前禁止启动：

1. OpenCode 发布覆盖调用日的新 DeepSeek ZDR/retention 证明；或
2. Robert 明确授权把上述 exact prompt hashes 发送到当前 retention 未确认的 OpenCode Go route。

若走条件 2，receipt 必须记录“retention unconfirmed / user-authorized exact payload”，不得写成 ZDR。Kimi
orientations 不先行，因为它们不能单独形成合格 panel，先跑只会制造可能无法使用的新 judgment。

## 6. Conclusion boundary

Qualification 永久是 `spent_diagnostic_only`。PASS 只生成“这两个 exact model/transport profiles 可用于
一次 fresh v1.4/v1.6 formal panel”的 receipt；不产生 BM25/E5 winner、不改变 promotion gate、不授权 fresh
formal calls。Fresh batch 仍需自己的 exact prompts、调用授权与当日 privacy check。
