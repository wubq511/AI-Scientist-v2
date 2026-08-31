# Local literature ranking：development Stage A 结果

日期：2026-08-31。范围：只报告 development scorer screen 与 Windows CPU thread probe；这不是
最终 ranker 决策，不读取或暗示 holdout labels。

## 1. 结论

- Stage A sensitivity gate 通过：judge-A、judge-B、consensus 三套 qrels 都得到同一机制方向。
- `intfloat/e5-small-v2` 是三套 qrels 的 best single scorer，且所有 complexity gates 通过；进入
  Stage B。
- BM25 是三套 qrels 的 best lexical mechanism。冻结 `k1=1.6,b=0.5` 进入 Stage B；它不是靠
  简单多数票选择，而是在三套 qrels 上具有最小 maximum regret，且对唯一名义反转的 judge-B
  只落后 `0.000524 nDCG@5`。
- BM25 与 E5 在三套 qrels 下都能找回对方 top-5 缺失的 grade≥2 papers，因此 RRF
  complementarity ablation 有资格进入 Stage B。
- 后续 Windows formal evidence 使用 16 CPU threads；1-thread reference path 保留且已通过。

## 2. Evidence identity 与可信边界

成功 attempt 为 `stage-a-004-cold-boundary`：

| Item | Value |
|---|---|
| Git commit | `2c1b332aafba13a43b921902f3413a8e9ae641dc`，clean |
| Python / device / dtype | `3.13.7` / CPU / FP32 |
| Environment SHA-256 | `a88ba1e5875e948d6d2fd2f2b40c9a114bea48486fb53cb22c49037668771277` |
| Environment lock SHA-256 | `6ad4e9f0a5aa690345edf349fc6d983dd31dd452220c10e80b39e6a269a302dd` |
| Input SHA-256 | `a7bcc349275626d5babb87dced480791a88bb5749242ec3f4b58e706dccaabbb` |
| Model manifest SHA-256 | `a0459c80016d083d853c3c3d44c46754b793b005a8a84cca5e1fc2eb3f03bb04` |
| judge-A protocol SHA-256 | `fc3958beb9aae3ffbd1b0aea43d83b7735eaf3ed2f68ac402226b32ac3224283` |
| judge-B protocol SHA-256 | `df5922b59cf0e8eb389dc65ef1d58c6a1a579a7b1b56e1104a6487424c65a494` |
| consensus protocol SHA-256 | `162d0f51b84b75a0c8abbffcb8adf156ddc9ec8a11d5030072e1902eb8bad9ed` |
| Windows raw archive SHA-256 | `a676bce751af7d94f24d8b4c529954d8e538affaf3aea449bb57d4605da8bfba` |

三套 comparisons 均为 13/13 candidates success，总计 39/39；13 个 candidates 的 12-query
payload hash maps 在三套 qrels 间逐项相同。它证明 qrels 只用于评价，没有改变 ranker output。
Raw scores、payloads、metrics、commands、stderr、environment 和 frozen protocols 位于
`artifacts/local-ranking-prototype/development-stage-a-*/`；该目录为 private、gitignored evidence。

## 3. Relevance sensitivity

下表列出各 mechanism 的 development `mean nDCG@5`；BM25 行使用本阶段冻结配置
`k1=1.6,b=0.5`。

| Mechanism | judge-A | judge-B | consensus |
|---|---:|---:|---:|
| IDF coverage | 0.677412 | 0.664305 | 0.626544 |
| TF-IDF cosine | 0.713838 | 0.706274 | 0.674782 |
| BM25 | 0.731710 | 0.715008 | 0.689031 |
| DPH | 0.671479 | 0.681446 | 0.641456 |
| E5-small-v2 | **0.855525** | **0.878195** | **0.865697** |

E5 相对冻结 BM25 的绝对 nDCG@5 增益分别为 `+0.123816`、`+0.163187`、
`+0.176666`，方向和幅度都不依赖某一套 synthetic qrels。对应 E5 的 Recall@5 为
`0.719841 / 0.686508 / 0.726389`，BM25 为
`0.598810 / 0.544643 / 0.580556`；E5 的 grade-3 catastrophic miss 总数为
`5 / 0 / 5`，BM25 为 `9 / 3 / 10`。

### 3.1 BM25 configuration

`k1=1.6` 在三套 qrels 都是 BM25 网格的最佳区域。`b=0.5` 与 `b=0.75` 的结果：

| qrels | `b=0.5` | `b=0.75` | `b=0.5` regret |
|---|---:|---:|---:|
| judge-A | **0.731710** | 0.730401 | 0 |
| judge-B | 0.715008 | **0.715532** | 0.000524 |
| consensus | **0.689031** | 0.686372 | 0 |

`b=0.5` 的 maximum regret 为 `0.000524`；`b=0.75` 为 `0.002658`。两者只改变
2–3 条 queries，改变处的 Recall@5 和 grade-3 catastrophic miss 均相同；没有证据支持为
judge-B 的 `0.000524` 名义优势选择更不稳的配置。因此 Stage B 冻结 `k1=1.6,b=0.5`，并把
这项近似 tie 作为 sensitivity 风险保留，不声称通用最优参数。

### 3.2 Complementarity

按 top-5 中 grade≥2 paper 的集合比较，BM25 相对 E5 独有命中数在 A/B/consensus 为
`3 / 2 / 2`，E5 相对 BM25为 `9 / 8 / 8`。两种机制在三套 qrels 下都至少修复一个对方的
paper-level miss，所以满足预注册 RRF eligibility；这不预先保证 RRF 会胜出。

## 4. Corrected resource evidence

`stage-a-003-utf8` 曾把整个 preflight elapsed 记为 cold start，重复包含 corpus build，导致 E5
cold p95 约 67 秒。该数字不符合“process spawn 到 scorer ready”的协议边界，不能用于淘汰
E5。Commit `2c1b332` 新增 worker `total_corpus_build_seconds`，由 parent 从完整 elapsed 中扣除；
缺失、负数、非有限值或大于 elapsed 均 fail closed。新 attempt 没有覆盖旧 evidence。

1-thread Stage A 的三次 E5 重复范围：cold p95 `5.155–5.546 s`、max case build
`26.644–26.846 s`、warm p95 `58.4–59.4 ms`、peak RSS
`474,427,392–475,795,456 B`。model 为 `134,410,262 B`，environment 为
`837,269,534 B`；全部通过 v1.1 gates。所有 lexical arms 也全部通过。

## 5. Windows thread probe

只改变 `thread_count ∈ {1,4,8,16}` 的隔离 E5 probe 得到：

| Threads | Cold p95 | Corpus total | Max case | Warm p95 | Peak RSS | Payload | Gate |
|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 5.546 s | 60.948 s | 26.746 s | 58.4 ms | 474,853,376 B | identical | pass |
| 4 | 5.499 s | 16.539 s | 7.322 s | 22.8 ms | 489,861,120 B | identical | pass |
| 8 | 5.241 s | 9.331 s | 4.065 s | **17.5 ms** | 501,432,320 B | identical | pass |
| 16 | 5.253 s | **7.863 s** | **3.162 s** | 23.8 ms | 509,685,760 B | identical | pass |

Probe protocol SHA-256 为 `78afd8d9c4bfd2a76601a231f41b4b21da4b2fe993bd555b99fedf6d2a6250c8`
（4）、`3b1d92f5c2a94ab933e89de33c968ce5b02974ac437eefbd235aa8f09d19f85d`
（8）、`2703dd2cdb6afb2744f20f04861017625768825539c328a5a0f5b67a3f5e1eca`
（16）；raw archive SHA-256 为
`c9ec9d14835e8ebe2ffd502e8e00e73fe41ce2f15beb5cdaf13533d0863bbd96`。

本 prototype 的耗时由 offline corpus build 主导，因此后续 Windows evidence 使用 16 threads；
8-thread 仅作为未来 latency-sensitive serving 的候选，不在本 ticket 锁定 production runtime。
完整边界见 [v1.3 overlay](local-literature-ranking-comparison-protocol-v1.3.md)。

## 6. 保留的失败与下一步

- `stage-a-001`：Windows Git CRLF 改动 environment lock bytes，hash gate 正确拒绝。
- `stage-a-002-lock-bytes`：Windows GBK stdout 无法编码真实 input 的 `U+2009`，worker transport
  正确保留 failure；commit `a406a79` 后统一 UTF-8。
- `stage-a-003-utf8`：39/39 scoring 成功，但 cold-start measurement boundary 错误；relevance
  可审计，resource rejection 不使用。
- `stage-a-004-cold-boundary`：39/39 success，identity、relevance、resource gates 全部通过。

下一步按 v1.1 Stage B 比较冻结 BM25 与 E5 的 title weight，再做 BM25 phrase ablation 和合格的
RRF `k∈{10,60}`；随后校准 `paper_cap∈{3,5}`。Finalists、参数和 budget 冻结前，holdout
继续 sealed。
