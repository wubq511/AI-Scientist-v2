# 本地文献排序比较协议 v1.4：fresh direct-payload setwise evaluation

Protocol date: 2026-08-31（Asia/Shanghai）
Status: **Approved / pre-registered overlay；真实 evaluator 调用尚未授权**

本文件覆盖 [v1.1 主协议](local-literature-ranking-comparison-protocol.md) 在 formal holdout
得到 `inconclusive` 后的补救评测。v1.1–v1.3 已冻结的 BM25/E5 implementation、参数、
abstract-only corpus、segmentation、`paper_cap=3`、CPU FP32 reference path、Windows bulk executor、
determinism 与 resource gates 全部继续生效。本 overlay 只替换 winner-evidence construct、fresh case
selection、blind evaluator 和统计/决策规则，不重开 scorer、title weight、phrase、RRF 或 output budget。

协议依据与被拒绝方案见
[v1.4 对抗性审查](../research/local-ranking-v1.4-adversarial-protocol-review.md)。

## 1. 唯一问题与结论边界

本轮只回答：在 `12 cases × 2 frozen queries`、题名 + validated publisher abstract、相同 top-3
model-visible budget 下，BM25 或 E5 的**原始 evidence set**是否被两个冻结 AI evaluators 跨位置
一致判断为更适合 AI ideation 使用。

构念名称固定为：

> `blind setwise top-3 evidence utility for AI ideation`

它不是 human preference、专家 topical gold、完整 ideation tool loop、最终 idea quality、equivalence
test 或普适 retrieval superiority。任何结论只适用于本批 balanced fresh cases、queries、abstract-only
corpora、top-3 budget、rubric 与 evaluator models。

## 2. 为什么直接评原始 payload

正式 primary 只有：`ranker -> exact top-3 payload -> blind setwise evaluators`。

拒绝原拟的 `ranker -> consumer-generated memo -> evaluator`，因为尚未冻结的 consumer model、sampling、
JSON repair、claim/quote entailment 与风格会成为新的混杂变量，并产生大量真实调用。直接 setwise
comparison 保持唯一变化是 ranker payload，同时仍能评价旧 pointwise qrels 没直接测量的组内覆盖、
互补性、具体机制/限制和明显遗漏。

Union/full-corpus 不进入 primary。它们改变 evidence budget，不能在没有 matched top-6 controls 时用来
阻断或改写 BM25/E5 结论；如以后需要，只能另作预登记 diagnostic revision。

## 3. Spent data 与 fresh data

旧 development/holdout 永久标为 `spent_diagnostic_only`：

- 允许 dry-run sampler、schema、mirror builder、validator、reducer、statistics 和 failure recovery；
- 禁止贡献 v1.4 winner vote、效果量、阈值调整或 prompt 选择；
- 禁止在旧 holdout 上新增 evaluator 后重新解释旧结果。

正式 batch 从 222 个 `unused eligible candidates` 中机械选择；它们在完成下述 approval chain 前不得称为
approved cases：

1. 绑定旧 12-case selection manifest 为 exclusion set；
2. 使用 source hashes + selection version `local-ranking-operational-case-selection-v1.0.1` +
   spent-manifest hash 派生 seed；每个 stratum 在 maximin fill 前至少有一个 cluster representative；
3. 选择 12 cases，small/medium/large 各 4，最大化 domain coverage，并在不读取 ranker output 的前提下
   保留 reference-count、title/abstract-overlap 与 strategy spread；
4. 重新完成 Workshop derivation、deterministic validation、semantic approval、abstract-only corpus
   validation、query authoring、query approval、E5 tokenizer preflight 与 formal materialization；
5. query author 只读 Approved Workshop，不得读取 references、ranker output、旧 labels 或旧 winner。

新 12 cases 全部属于同一个 formal evaluation split，不从中调 prompt、阈值、样本量或 evaluator。
一旦任何人看到 arm mapping 或 judgment，任何 semantic rule 变化都会使整批降级为 spent diagnostic。

## 4. Frozen finalists

1. BM25：`k1=1.6`、`b=0.5`、`title_weight=1`、`aggregation=max`、
   `phrase_bonus=false`、`paper_cap=3`、`segments_per_paper=1`；
2. E5：pinned `intfloat/e5-small-v2` revision
   `ffb93f3bd4047442299a41ebb6fa998a38507c52`、CPU FP32、`title_weight=1`、
   `aggregation=max`、`paper_cap=3`、`segments_per_paper=1`。

Formal retrieval 在 Windows `D:\AI-Scientist-v2-workspace` 的 clean committed checkout 运行，
Python 3.13.7、frozen Windows lock、16 CPU threads、offline/network deny。Mac 只做 controller、input/prompt
准备、SSH orchestration、evidence review 与 fallback；本轮 scorer/model/output semantics 未改变，因此不重复
Mac bulk/cross-platform matrix。

## 5. Blind pair construction

- 每条 query 的两个 canonical top-3 payload 必须分别与 frozen scorer output hash byte-for-byte 绑定；
- public bundle 只含 query、anonymous left/right titles 和 exact Retrieval Segments；禁止 candidate name、
  score、qrels、旧 winner、mapping key、另一 evaluator 输出或 Target Paper；
- orientation-1 按 protocol hash 派生的顺序，在每个 `stratum × query kind` 区块内以 2/2 平衡 sides
  （全局 12/12）；orientation-2 对每个 item 只交换 left/right，rubric、标点、字段和 item order 不变；
- controller mapping 独立 seal，在四份输出全部通过 hash/schema validation 前不得解封；
- 四个 evaluator 输出目录互斥且 immutable，禁止共享 draft path。

Deterministic hard gate 验证：input/payload/protocol hashes、query/case identity、top-3 budget、paper membership、
title、segment text/source pointer、左右镜像、无额外字段和 forbidden text。Semantic usefulness 不由本地
validator 伪装证明。

## 6. Evaluators 与真实隔离

Evaluator panel 固定为：

| ID | Harness | Model | Orientations |
| --- | --- | --- | --- |
| judge-kimi | Kimi Code CLI | `kimi-k3` | 1、2，各 fresh session |
| judge-deepseek | Kimi Code CLI | `deepseek-v4-flash` | 1、2，各 fresh session |

二者是不同 model families；若都经 Kimi Code 编排，不声称 two-provider independence，也不冒充 human
gold。每个 orientation 使用一个显式 custom agent，frontmatter 固定 `tools: []`、`subagents: []`；完整
bundle bytes 嵌入 prompt，模型不能读取 filesystem、repo、shell、network、skills、MCP 或旧 session。
[Kimi Code 官方 custom agent 文档](https://moonshotai.github.io/kimi-code/en/customization/agents)确认空
`tools` allowlist 会禁用全部 tools，并在执行前再次强制检查；formal runner 必须保存 agent file、prompt、
CLI version、model alias、fresh session evidence、stdout/stderr、exit code 与 hashes。

每个 item 的 closed judgment 包含：

- `winner ∈ {left,right,tie,both_bad}`；
- 左右各 `direct_support/query_usefulness/coverage_diversity/specificity ∈ {0,1,2}`；
- `catastrophic_omission_side ∈ {left,right,neither}`；
- 1–4 个当前 side/paper/segment 内的 byte-exact evidence quotes；
- bounded rationale；不得引用外部事实或未显示内容。

Invalid JSON/schema 只允许预登记的一次**完整 orientation、同 model/config、fresh session** retry；不得只补
不利 items、人工改 JSON 或沿用旧会话。

## 7. Reducer 与统计单位

同一 model 两个 orientations 映射回匿名 arm 后：

- winner direction 必须一致；否则该 query 对该 model 为 `position_unstable`。两侧分项差异完整记录，
  但不因量表轻微波动丢弃同方向判断；
- 两个 models 的 stable winner 一致才得到 query outcome；否则为 `cross_model_unresolved`；
- `catastrophic_omission` 只有在两个 models、两个 orientations 四次映射后都指向同一候选时才成立；
- `tie` 与 `both_bad` 映射为 0，但分别报告；unresolved 在 effect estimator 中保守记 0，不能称为 tie；
- 不增加第三票、不多数表决。

正号固定代表 E5，负号固定代表 BM25：

```text
s_q = +1 (E5 stable win), -1 (BM25 stable win), 0 (tie/both_bad/unresolved)
d_i = (s_broad + s_focused) / 2
Delta = mean(d_i for 12 cases)
```

`Delta` 范围为 `[-1,1]`。统计单位是 12 cases，不把共享 Workshop/corpus 的 24 queries 当成 24 个
独立样本。Primary uncertainty 枚举 `2^12=4096` 个 case-level sign flips，E5 promotion 使用固定 one-sided
tail `mean(epsilon_i*d_i) >= Delta_observed`；同时报告 two-sided exact p-value。固定-seed case-cluster
bootstrap 95% CI 只作描述，不用于 equivalence 或小效果结论。

## 8. 非对称 E5 promotion gate

BM25 是较轻 reference/default；E5 的 model artifact、环境、内存和 cold start 只有在材料性收益被证明时
才值得引入。此 loss function 在 fresh data 前冻结。

E5 只有同时满足以下条件才 promotion：

1. 两个 finalists 的 retrieval、boundary、determinism 与 resource gates 全部通过；
2. 至少 18/24 queries 跨两 models/两 positions 可判别，且每个 corpus-size stratum 至少 5/8；
3. `Delta >= 1/3`；
4. exact case-level one-sided sign-flip `p <= 0.05`；
5. broad/focused 与三个 strata 的 point estimate 不出现符号为负的材料性反向
   （任一分组 `Delta <= -0.25` 即失败）；
6. E5 没有两个 models 跨位置稳定确认的新增 systematic catastrophic omission：同一 stratum 至少
   2 queries 或全体至少 3 queries 指向 E5 即视为 systematic。

若 E5 未通过，合法结论是 `E5 material utility gain not demonstrated`，选择 BM25 只能记录为
`parsimony deployment choice`，不得写成 BM25 relevance/utility scientific winner。12 cases 有意只检测
大且跨 case 稳定的收益；它可能漏掉真实中小 E5 收益，不能证明二者相等。

## 9. 停止与失败规则

- 固定 12 cases / 24 queries，不中途查看 mapping、direction 或 p-value；
- 四个 orientations 全部完成并验证后才解封 mapping、只计算一次 formal statistic；
- 缺 case、缺 arm、payload drift、bundle 泄漏、tools 未禁用、session resume、hash/schema 失败、选择性
  retry 或 output collision 均使 formal attempt `invalid/incomplete`，不能对剩余样本重算；
- deterministic implementation bug 只有在 mapping 未解封、旧 attempt 完整保留、语义未变且所有 arms
  全量重跑时才可用新版本修复；
- 同时报 effect、exact p、bootstrap CI、resolved/tie/both_bad/unresolved、position stability、cross-model
  agreement、strata、catastrophic omissions、runtime/cost 和全部 failures，禁止只报总票数。

## 10. 实施与授权顺序

1. 实现并测试 sampler、formal split、pair builder、tool-less prompts、judge validator、reducer 与 statistics；
2. 用旧 spent holdout 做无效力 dry-run，冻结 protocol/code/tests hashes并提交；
3. 再机械选择 fresh candidates，完成新的 input approval 与 query chain；
4. Windows 从 clean commit 运行 frozen BM25/E5；
5. controller 生成四个 hash-bound tool-less prompt，并报告 bundle tokens/bytes、调用数和一次完整 retry 的
   最坏上界；
6. Robert 批准该批真实 evaluator 调用后，才运行四个 fresh sessions；
7. validate、seal、解映射、运行固定 reducer，写 ticket decision record。

协议获批不等于真实模型费用获批。本文件不授权任何 Kimi/DeepSeek 调用，也不授权 production retriever
implementation。
