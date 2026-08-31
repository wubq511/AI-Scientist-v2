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

### 3.3 Stage B1：title weight

Stage B1 从 clean `3f6660140f65e90a135a30786128f2ab31f32487` 运行，三套 qrels 共
18/18 arms success，environment SHA-256 均为
`00c7887d1fe0b860e4d2b33a473b43f556782891c113a55a37d3a324d946d91a`；相同 candidate 的
payload hashes 跨 qrels 完全一致，所有 resource gates pass。

| Family / title weight | judge-A nDCG@5 | judge-B nDCG@5 | consensus nDCG@5 |
|---|---:|---:|---:|
| BM25 / 0 | 0.731710 | 0.715008 | 0.689031 |
| BM25 / 1 | **0.752826** | **0.720736** | **0.711809** |
| BM25 / 2 | 0.739211 | 0.703846 | 0.686265 |
| E5 / 0 | **0.855525** | 0.878195 | 0.865697 |
| E5 / 1 | 0.847909 | **0.897539** | **0.883278** |
| E5 / 2 | 0.851619 | 0.894614 | 0.881222 |

BM25 的 `title_weight=1` 在三套 qrels 上方向完全一致，冻结进入 phrase ablation。

E5 的 exact primary optimum 对 qrels 有轻微敏感性，但不改变 E5 finalist promotion：weight 1
相对 weight 0 在 judge-A nDCG@5 下降 `0.007617`，在 judge-B/consensus 提升
`0.019344/0.017582`；Recall@5 在三套分别提高 `0.007540/0.088095/0.026389`，并将
judge-A/consensus 的 grade-3 catastrophic misses 从 5 降到 2，judge-B 保持 0。Weight 1 与 2
的 nDCG@5 差异在三套都不超过 `0.003710`，miss 数相同；weight 1 在 B/consensus 的 nDCG 和
Recall 更高且 title coupling 更低。因此 development 冻结 E5 `title_weight=1`，同时保留 judge-A
的微小 primary trade-off，不把它表述成跨数据集通用值。

Stage B1 protocols SHA-256：judge-A
`0861d6607de092932fe6c99d637fd101cd278312ced4401d0c32fa29973972cb`、judge-B
`c9f95544711ca8d42cf361f02f578edf07f3f0b03ecda3dee124333fcb71af84`、consensus
`e983e14593865f41f986de470d7b84566d0728560766e603b09f21325418af21`。Windows raw archive
SHA-256 为 `0fcc3a22c60fc906d15a3f025dc256c79a2cf40d96decfc3bf63219455cb75a4`。

### 3.4 Stage B2：phrase bonus

BM25 `k1=1.6,b=0.5,title_weight=1` 的 phrase off/on 在三套 qrels 下产生完全相同的
12/12 payload hashes；nDCG@5、Recall@5、MRR、EvidenceHit 与 grade-3 catastrophic miss 也
逐项相同。三套共 6/6 arms success、resource gates pass，environment SHA-256 均为
`b8dd94c82caf97bb0db89385d60c0dbc05559081489f22bcfe9dd521fcd92ace`。

Phrase bonus 没有可观察收益，因此冻结 `phrase_bonus=false`。这不是“差异太小”的统计判断，
而是本冻结 input 上 canonical result byte-for-byte 无变化；没有理由把额外机制带入 finalist。

Stage B2 protocols SHA-256：judge-A
`3e1842188fd137f32993afb0ac0392b9ff693fdb5b3ef572d60aaf74ddbd5d94`、judge-B
`ce89e96df682f46aeab95b10d9ea7acfb12a3e89f6f12f34d46289a1761126ce`、consensus
`4734ec968b8d2885f634ee89f229287cb72c2f132700278c9c06b6e1abc92f6a`。Windows raw archive
SHA-256 为 `bf1917a3eb5d7be53b4620c1cd51d2c9569eca4f8bab923c76af3b624ca98bbf`。

### 3.5 Stage B3：RRF fusion

| Candidate | judge-A nDCG@5 | judge-B nDCG@5 | consensus nDCG@5 |
|---|---:|---:|---:|
| BM25 | 0.752826 | 0.720736 | 0.711809 |
| E5 | **0.847909** | **0.897539** | **0.883278** |
| RRF k=10 | 0.829576 | 0.827341 | 0.811486 |
| RRF k=60 | 0.810150 | 0.809488 | 0.785695 |

三套共 12/12 arms success、resource gates pass；相同 candidate 的 payload hashes 跨 qrels
完全一致。E5 相对 best RRF k=10 的 nDCG@5 高 `0.018333/0.070198/0.071793`，Recall@5
高 `0.009127/0.032738/0.006944`，judge-A/consensus 各少 2 个 grade-3 catastrophic misses，
judge-B miss 数相同。RRF k=60 更差。

因此 RRF 虽然满足进入 ablation 的 complementarity 前提并通过 complexity gates，却没有把补漏
转化为更好的整体 ranking；两档都拒绝。Development finalists 冻结为两个 distinct families：
BM25 baseline 与 E5 best single scorer。

Stage B3 protocols SHA-256：judge-A
`80922c353271f599f94247cf774268dc1cb2f27fa75d3a8c6ebeb3b23ee5000e`、judge-B
`1286931f1a2164fa51f4356c2d2c5fb4199b7a83e9aaf0d9218f88c152bd77dd`、consensus
`c4ff7db34e5c9e7e30dff40be7489e6957cb7dc066bf4fec8d4ddad3771d14c7`。Environment SHA-256
均为 `00c7887d1fe0b860e4d2b33a473b43f556782891c113a55a37d3a324d946d91a`，Windows raw archive
SHA-256 为 `0cc73e376c07dc6b9282a2dcfdcd1cc9390bdeb9666b1d2205cd4b6ab337f3dd`。

### 3.6 Stage B4：output budget

| Family / paper cap | EvidenceHit A/B/C | Mean payload bytes | nDCG/Recall/miss vs cap 5 |
|---|---:|---:|---|
| BM25 / 3 | 0.833333 / 0.833333 / 0.833333 | **5,215.5** | identical |
| BM25 / 5 | 0.833333 / 0.833333 / 0.833333 | 8,092.3 | baseline |
| E5 / 3 | 0.916667 / 0.916667 / 0.916667 | **5,084.1** | identical |
| E5 / 5 | 0.916667 / 0.916667 / 0.916667 | 7,777.3 | baseline |

三套共 12/12 arms success、resource gates pass；相同 candidate 的 payload hashes 跨 qrels
完全一致。两种 family 的 cap 3/5 `EvidenceHit@budget` 差值都为 0，nDCG@5、Recall@3/5 与
catastrophic misses 也相同。按预注册 tie-break，选择平均 payload 少约 2,877 bytes 的 BM25
cap 3 与少约 2,693 bytes 的 E5 cap 3；`segments_per_paper=1,total_segment_cap=3` 同步冻结。

Stage B4 protocols SHA-256：judge-A
`7b7c2d1e58a0cae989925c47f9a68b259f1f2395807f67b276cca349b432c9ef`、judge-B
`f085412f240a8359d3cef6772a53690d5971bd57e8b343cc8f3f87f2c5ad45cb`、consensus
`af21fec39a901ff398529caa0f537117c9279d8382a4d65cad9331871775013a`。Environment SHA-256
均为 `00c7887d1fe0b860e4d2b33a473b43f556782891c113a55a37d3a324d946d91a`，Windows raw archive
SHA-256 为 `503eb59176a10b9bb0f8a261ad6aa9c82658ec28363b6556ba5f71e16b942094`。

Development finalists 至此完整冻结：

1. BM25：`k1=1.6,b=0.5,title_weight=1,max aggregation,phrase_bonus=false,paper_cap=3`；
2. E5-small-v2：pinned model，`title_weight=1,max aggregation,paper_cap=3`。

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

## 6. Finalist determinism

### 6.1 Windows 10-run

两个 frozen finalists 从 clean `5ffda00d67981e9d3eaa27a89b6fe15db89c220b` 运行 10 个
scoring-only attempts；qrels 不进入 protocol，16 threads、input/model/lock 与 candidate bytes 固定。

- 10/10 attempts success；20/20 candidate runs resource gate pass；
- BM25 与 E5 各自的 12-query payload hash maps 均为 10/10 identical；
- 两个 candidates 的 `payloads.jsonl` 与 `scores.jsonl` 各自也都是 10 份 byte-identical；
- 10 份 environment SHA-256 都是
  `00c7887d1fe0b860e4d2b33a473b43f556782891c113a55a37d3a324d946d91a`；
- E5 cold p95 范围 `5.166–6.620 s`、max case build `3.184–3.439 s`、warm p95
  `22.5–37.2 ms`、peak RSS `509,931,520–512,966,656 B`，全部通过。

Windows raw archive SHA-256 为
`e1dfed55edfb85e9989fbe9d45c0bc11130b296dd79c524f30104e76e73524a2`。每个 attempt 使用不同
protocol/attempt hash 并写入独立 root，没有以一次运行复制成十份。

### 6.2 macOS 3-run

从 clean `91379fa8bf951c2e867f38f44f229372e2e6a270` 建立独立 checkout，并按 macOS
Python 3.13.7 lock 安装只含 finalist 所需依赖的环境。安装后 63/63 tests passed；input、model
manifest 与 lock SHA-256 分别为
`a7bcc349275626d5babb87dced480791a88bb5749242ec3f4b58e706dccaabbb`、
`a0459c80016d083d853c3c3d44c46754b793b005a8a84cca5e1fc2eb3f03bb04`、
`d8d22f84ee831a5627550cc821a1178879bcd3908f9dea224645c56e94b42a3f`。

首次 attempt 在 import 时为新环境生成约 `51.7 MB` `__pycache__`，导致 environment bytes/hash
从安装态改变；该 run 保留为 warm-up deviation，不混入正式稳定集合。之后的 attempts 002/003/004
环境均为 `669,956,676 B`、SHA-256
`7ecf39c553a9343dc70548a5648b4d34cda5a5aec05a2d1a365927e172e5244d`，构成正式 3-run 集合：

- 3/3 attempts success；6/6 candidate runs resource gate pass；
- BM25 与 E5 各自的 12-query payload hash maps、`payloads.jsonl`、`scores.jsonl` 在 macOS 内部
  均为 3/3 identical；
- 两个 finalists 的 observable payload 与 Windows 10-run byte-identical；BM25 score bytes 也跨平台
  identical；
- E5 的 raw float score bytes 在 macOS 与 Windows 间不同，但排序与最终 payload 完全相同，符合
  protocol 对跨平台确定性的定义；
- BM25 cold p95 `0.052–0.054 s`、max case build `0.0056–0.0060 s`、warm p95
  `0.396–0.411 ms`、peak RSS `30.9–31.1 MB`；
- E5 cold p95 `1.636–2.286 s`、max case build `1.136–1.418 s`、warm p95
  `7.089–7.767 ms`、peak RSS `896,991,232–1,178,353,664 B`；全部通过。

macOS raw archive SHA-256 为
`dbc69798438745b47fcdb81a1e13ad8515ecb48678f58d395a77e6eba6a7695d`；从 Windows 转移的
private model/input archive SHA-256 为
`a4a335e0c55a010a543de22589200a3efe538ba557c03c384a255289102672fa`。Windows 10-run 与
macOS stable 3-run 共同完成 finalist determinism gate。

## 7. 保留的失败与下一步

- `stage-a-001`：Windows Git CRLF 改动 environment lock bytes，hash gate 正确拒绝。
- `stage-a-002-lock-bytes`：Windows GBK stdout 无法编码真实 input 的 `U+2009`，worker transport
  正确保留 failure；commit `a406a79` 后统一 UTF-8。
- `stage-a-003-utf8`：39/39 scoring 成功，但 cold-start measurement boundary 错误；relevance
  可审计，resource rejection 不使用。
- `stage-a-004-cold-boundary`：39/39 success，identity、relevance、resource gates 全部通过。

下一步按 sealed receipts 验签并解封 judge-A、judge-B 与 consensus 三套 holdout qrels，然后只对
两个 frozen finalists 做一次正式 holdout 评估。不得依据 holdout 调参、增加 candidate 或重跑择优。
