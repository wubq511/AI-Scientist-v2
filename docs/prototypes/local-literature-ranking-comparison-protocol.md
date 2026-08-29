# 本地文献排序最小公平比较协议

Protocol date: 2026-08-30（Asia/Shanghai）
Status: **Approved / pre-registered v1.0**
Decision ticket: `Choose and calibrate local literature ranking`

这是一个 throwaway comparative prototype 的预注册协议，不是 production implementation。Robert 已于 2026-08-30 批准协议方向，并授权从第一性原理解决未决项；下文已冻结 v1.0 的输入、候选、评价、runtime 与决策规则。Harness 已实现并通过 tracked fixture 的本地验证；这不等于已经准备 qrels、安装 dense 依赖、下载模型、运行正式 development/holdout，或选择最终 ranker。

## 1. 本协议要回答的唯一问题

在每个 case 只有 3–36 篇 approved references、runtime 必须 local/offline，并具有可移植的 CPU FP32 reference path 的条件下，哪一个最小 ranking configuration 能在固定 evidence budget 内返回最有用的 source-faithful paper/segment evidence，同时满足：

- 不越过当前 Approved Target Reference Corpus；
- observable determinism 与稳定 tie-break；
- Windows/macOS 可重放；
- 可接受的冷启动、warm-query latency、内存、磁盘与依赖成本；
- 明确、可审计、fail-closed 的失败行为。

本协议同时校准 scorer、title/segment field handling、paper aggregation 与 paper/segment cap。v1 不使用 raw-score relevance threshold：不同 scorer 的分数不可直接比较，而语料至多 36 篇，返回固定 top candidates 不会造成规模问题。它不比较 ANN/index architecture：所有 arms 都 exhaustive score-all，不允许 first-stage pruning 漏掉 eligible candidate。

## 2. 决策权与停止线

- Prototype 只产生比较证据；Robert 是最终 decision owner。
- 未完成 blind holdout 前，不按 development 结果选择 production ranker。
- 任一 hard invariant 失败的 candidate 直接不合格，即使 relevance metric 更高。
- 若 holdout 不能区分 finalist，结论必须是 `inconclusive`，增加冻结 query/case 后重跑；不得按直觉挑选。
- 本 ticket 只做规划与 throwaway evidence，不修改 production retriever，不进入 BFTS、实验、绘图、write-up 或 review。

## 3. 已锁定边界

所有 candidates 必须共享以下条件：

1. 输入只来自同一 exact Approved Target Reference Corpus bundle：normalized query、title、eligible Reference Content/Retrieval Segments。
2. 禁止读取 Target Paper、Workshop hidden text、citation count、venue、year、publication type、Target-derived metadata、previous queries/results、remote API 或 undeclared global resource。
3. 所有 scorer 面对完全相同的 eligible papers、Retrieval Segments、query bytes、segmentation、result budget 与 evaluation procedure。
4. Paper 是 ranking/output unit，同一 `paper_id` 最多一次；segment selection 与 paper aggregation 分开评价。
5. Paper 最终顺序是 approved score 降序，再按 stable `paper_id` 升序；segment 最终顺序是 segment score 降序，再按 canonical content-item order 与 source start position。
6. 不允许 candidate failure 时改用另一 ranker、联网、读 alternate/stale corpus 或降低 validation。
7. Dense/fusion arm 不能看到比 lexical arm 更多或更少的正文。无法公平处理 approved full-text segment 的模型不进入正式比较。

## 4. 预注册假设

| ID | 待验证假设 | 能推翻它的证据 |
| --- | --- | --- |
| H1 | 在 N≤36 的限定语料中，透明 lexical ranker 已足够，复杂模型没有稳定净收益 | Dense 或 fusion 在 blind holdout 上跨 query 稳定提高 graded relevance/evidence hit，且通过全部成本与 determinism gates |
| H2 | BM25 的 TF saturation/length normalization 比简单 IDF coverage/TF-IDF 有净收益 | 简单 baseline 在 holdout 上等效或更好，BM25 只增加参数而不修复 failure case |
| H3 | DPH 这类不同概率假设能暴露 BM25 在极小 corpus statistics 下的缺陷 | DPH 在预注册 diagnostic 与 holdout 上没有独立 wins，或产生更严重的 small-N instability |
| H4 | Title signal 与固定 top-m aggregation 能减少单个偶然 segment 支配 paper ranking | Field/top-m ablation 没有改善 evidence hit，或引入 title/segment-count bias |
| H5 | Lexical 与 dense 的错误具有互补性，RRF 可能胜过最佳单模型 | RRF 只复制最佳 arm 的结果、放大较弱 arm 的错误，或收益小于预注册 complexity margin |

## 5. 冻结 evaluation set

### 5.1 Case split

使用 12 个 approved cases，先冻结再运行任何 ranker：

| Split | Cases | Queries | 用途 |
| --- | ---: | ---: | --- |
| Development | 6 | 12 | 小网格校准、淘汰明显失败 candidate、选 finalist |
| Blind holdout | 6 | 12 | 一次性最终比较；打开后不得调参 |

每个 split 各覆盖三个 corpus-size strata，每层 2 个 case：`small=3–8`、`medium=9–18`、`large=19–36`。在可用数据允许时，每个 split 还必须覆盖：

- 至少两个学科领域；
- abstract-only corpus 与包含 approved official-full-text segments 的 corpus；
- segment 数量较均匀与明显不均匀的 corpus；
- title 与 content vocabulary 高重合、低重合的 corpus。

若当前 approved bundles 不能满足这些 strata，协议停止；不得用未批准 raw/alternate content 填补。

### 5.2 Query creation

每个 case 固定两条英文自然语言 query：

1. `broad`: 从 Approved Workshop 可见问题域出发的广义 evidence need；
2. `focused`: 更具体的机制、方法或限制问题，但不能包含 Target Paper identity、held-out contribution、target-created method/acronym 或答案式措辞。

Query author 只看 Approved Workshop，不看 Target Paper、ranker output 或 qrels。Query text、类型、author、创建依据与 SHA-256 在第一次 ranker run 前冻结。Prototype 不使用“从某个 reference 原句反向构造”的 known-answer query 作为 relevance 主证据；这类 query 只允许进入 diagnostic fixtures。

执行角色固定为：Codex 只基于 Approved Workshop 起草每个 case 的 `broad`/`focused` query，Robert 在同一可见边界内批准或改写；任何一方都不得在此步骤读取 reference content。最终采用的 query author/reviewer identity 与改写记录进入 private manifest。

### 5.3 Blind qrels

Relevance reviewer 只看到 `query + eligible paper title + eligible Retrieval Segments`，看不到 candidate identity、scores、rank position、Target Paper 或 previous result。

- Paper relevance：`0=无关`、`1=背景相关`、`2=能提供直接有用证据`、`3=核心证据`。
- Segment evidence：`0=无用`、`1=部分支持`、`2=直接支持 query`。
- 所有 paper 都做 paper-level judgment；每个 grade≥2 paper 的全部 eligible segments 都标 0–2，并至少有一个 grade=2 segment，否则明确记录 `no_supporting_segment` 数据问题。Grade 0/1 paper 的 segments 对 direct `EvidenceHit` 视为非命中，不额外增加全量 segment 标注负担。
- Development qrels 可以在调参前解封；holdout qrels 保持 sealed，到 finalists 和所有参数冻结后才解封。
- Robert 是 authoritative relevance reviewer；AI 只可生成无身份的标注表和一致性检查，不能代替 gold judgment。
- 随机抽取 15% 的 query-paper judgments（至少 30 条，若总量不足则全部），在首次标注至少 24 小时后重新盲标；对应的最佳 segment judgment 一并复核。抽样 seed、两轮原始 judgment 与差异全部保留。
- 以四级 paper relevance 计算 weighted Cohen's kappa。`kappa >= 0.70` 且相差两级以上的 judgment 不超过复核样本 5% 才通过 qrels-stability gate；否则先 blind adjudication 并重做该 split 的 15% 稳定性抽样，仍失败则结果必须记为 `inconclusive`。

不引入第二位 reviewer 作为执行依赖：当前决策目标是选择 Robert 自己使用的检索器，权威效用判断应来自 Robert；延时盲重复用于检测同一评价者的漂移。未来若结果要对外宣称普适性，必须另写 protocol revision，引入独立 reviewer 与 inter-rater analysis。

## 6. Diagnostic fixtures

真实 qrels 之外，所有 candidates 必须通过同一组确定性 fixtures：

- single paper、3 papers、36 papers；
- all-zero/OOV query、single-token query、phrase-heavy query、very-long valid query；
- acronym、hyphen、Unicode、case variation 与 repeated terms；
- title-only lexical hit、content-only hit、title/content 冲突；
- 相同 score tie、near-tie、重复 segment 与 segment-count imbalance；
- publisher abstract 与 official-full-text segment 混合；
- 非法 query、缺模型文件、corrupt model/hash、offline network denial；v1 无 threshold，eligible corpus 非空时不设置“合法 empty”fixture。

Fixtures 只验证行为、边界和 metric direction，不进入 relevance aggregate，也不能替代真实 qrels。

## 7. Candidate matrix

### 7.1 固定 normalization baseline

第一轮 lexical arms 共用 `lexical_normalization_v1`，顺序固定为：

1. 输入必须是有效 Unicode string；trim 后为 1–256 个 Unicode scalar values，否则是 typed input error，不允许静默截断。
2. Unicode NFC，然后 `casefold()`。
3. 将 Unicode category `Pd` 的 dash 映射为 ASCII `-`；将 `U+2018`、`U+2019`、`U+02BC` 映射为 ASCII apostrophe；将连续 Unicode whitespace 折叠为一个 ASCII space 并再次 trim。
4. 以 Python Unicode semantics 使用 regex `[^\W_]+(?:[-'][^\W_]+)*(?:\+{1,2}|#)?` 提取 token。
5. 保留数字、重复词、内部连字符/撇号以及 `C++`/`C#` 式后缀；不 stemming、不用外部 stopword list、不做 synonym/ontology expansion。

Harness 必须为 `COVID-19`、`C++`、`C#`、possessive/apostrophe、Unicode dash、组合字符、casefold expansion、数字和 emoji 边界保存 golden tokens。normalization version 与 normalized query 都进入 private audit。

Dense arm 读取相同 normalized natural-language query 与相同 source-faithful segment text，但使用 pinned tokenizer。加上 `query: ` prefix 后不得超过 512 tokens；超过即 typed input error，不允许 silent truncation。Candidate segment 加上 `passage: ` 后也不得超过 512 tokens；若超限，必须由所有 arms 共用、已批准的 upstream segmentation 修复，不能由 dense arm 私自裁剪。

### 7.2 Stage A：scorer screen

所有 arms 先只用 segment text、`max(segment_score)` paper aggregation、不设 relevance threshold、返回完整 paper ranking，从而隔离 scorer 差异：

1. `idf_coverage`: unique query-term IDF coverage；最透明 sanity baseline。
2. `tfidf_cosine`: raw TF + pinned smoothed IDF + cosine。
3. `bm25`: 只在 development split 比较预注册小网格：`k1 ∈ {0.8, 1.2, 1.6}`、`b ∈ {0.0, 0.5, 0.75}`。
4. `dph`: parameter-free classical challenger；公式与 zero/short-document guard 固定。
5. `dense_biencoder`: pinned `intfloat/e5-small-v2`，exact score-all。

Lexical 公式固定如下；除 DPH 明确使用 `log2` 外，其余 logarithm 用 natural log。Stage A 的 collection statistics 以全部 eligible content segments 为 document collection；Stage B title score 以全部 paper titles 为独立 field collection，不能让 title-weight candidate 改写 content statistics：

- `idf_coverage`: `idf(t)=ln((N+1)/(df(t)+1))+1`；score 是 query unique tokens 中、出现在 segment 的 token 之 IDF sum，除以全部 query unique-token IDF sum。
- `tfidf_cosine`: `weight(t,d)=raw_tf(t,d)*(ln((N+1)/(df(t)+1))+1)`，query 使用 binary TF；score 是 query/segment vectors 的 cosine，zero vector 得 0。
- `bm25`: Robertson/Sparck Jones positive IDF `ln(1+(N-df+0.5)/(df+0.5))`，query term frequency 不额外加权；`avgdl=0`、empty segment 或非有限值必须 fail closed。
- `dph`: 对每个匹配 query term 令 `f=tf/dl`（当 `tf=dl` 时固定为 `0.99999`）、`norm=(1-f)^2/(tf+1)`，term contribution 为 `norm * [tf*log2((tf*avgdl/dl)*(N/F)) + 0.5*log2(2*pi*tf*(1-f))]`；`F` 是 collection term frequency，query term weight 固定为 1。`tf=0` contribution 为 0；empty segment、无效 collection statistics 或非有限结果必须 fail closed。Golden values 对齐 [Terrier 5.x `DPH.java`](https://github.com/terrier-org/terrier-core/blob/5.x/modules/core/src/main/java/org/terrier/matching/models/DPH.java)，但 implementation 不得依赖 Java/Terrier runtime。

Dense identity 固定为：

```text
model_id: intfloat/e5-small-v2
revision: ffb93f3bd4047442299a41ebb6fa998a38507c52
weight_file: model.safetensors
weight_bytes: 133466304
weight_sha256: 45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1
license: MIT
query_prefix: "query: "
passage_prefix: "passage: "
pooling: attention-mask-aware average pooling
normalization: L2
score: dot product
max_length: 512
embedding_dimension: 384
dtype: float32
reference_device: cpu
```

只允许从该 revision 准备 `config.json`、`model.safetensors`、`special_tokens_map.json`、`tokenizer.json`、`tokenizer_config.json` 和 `vocab.txt`；实际下载 bytes 的 SHA-256 全部写入 manifest。使用 `AutoTokenizer`/`AutoModel`、`model.eval()` 与 `torch.inference_mode()`，第一轮不引入 `sentence-transformers`。禁止 runtime 自动选 model、加载 `.bin` 权重或下载 `main/latest`。

Reference dependency snapshot 固定为 `Python==3.13.7`、`torch==2.13.0`、`transformers==5.16.1`、`numpy==2.5.2`、`psutil==7.2.2`、`pytest==9.1.1`。选择 3.13.7 是因为 Windows 已有该 stable patch，Mac 可由 `uv` 安装相同 patch，能以最小设备改动得到同 ABI/patch 的跨平台证据；它不是永久项目 patch。Implementation 必须在 Windows/macOS 分别生成完整 transitive lock 与 wheel hashes，禁止 source build；snapshot 只有通过 fresh-environment preflight 才可用于正式 evidence。

### 7.3 Stage B：field、aggregation 与 complementarity ablation

Stage A 后只保留 development best lexical scorer；dense 仅在通过 dependency/determinism preflight 后保留。比较：

- title weight：`0, 1, 2`；
- paper aggregation：`max` 与 `mean(top-2)`，不足两个 eligible segments 时按实际数量求 mean；
- `sum(all)` 只在 best lexical scorer 上作为 segment-count bias negative control；
- fixed phrase/proximity bonus 只在 best lexical scorer 上做 `off/on` ablation；
- dense 合格时，比较 best lexical 与 dense 的 RRF，`k ∈ {10, 60}`，不混合原始 scores。

禁止完整笛卡尔积 sweep。顺序固定为：先 scorer，后 title/aggregation，再 phrase/fusion。前一阶段没有进入下一阶段的 arm 不得借后续参数复活。

Field/aggregation 定义固定为：title 由同一 scorer 独立打分（dense 使用 `passage: <title>`）；paper score 为 `content_aggregation + title_weight * title_score`。`max` 与 `mean(top-2)` 只聚合 eligible content segments。Phrase ablation 只用于 best lexical：先将同一 query 下所有 content/title base scores min-max 到 `[0,1]`（全相同则为 0），再计算 distinct adjacent query bigrams 的 contiguous-match coverage，最终 unit score 为 `0.9*normalized_base + 0.1*phrase_coverage`。RRF 在 paper rankings 上计算；同 rank contribution 为 `1/(k+rank)`，最终同分按 `paper_id`。为了产生与 paper fusion 一致且不混合原始分数的 evidence order，每篇 paper 内的 segment order 使用两个 source arms 各自的 per-paper segment rank、相同 `k` 做 RRF；segment 同分回到 canonical content-item order、source start position 和 `segment_id`。

### 7.4 Output budget calibration

Scorer family、field handling 与 aggregation 冻结后，只在 development split 比较以下离散 payload policies：

- `paper_cap ∈ {3, 5}`；
- `segments_per_paper ∈ {1, 2}`；
- `total_segment_cap = 6`；
- segment 长度使用获批 upstream segmentation 的共同上限，不允许 scorer-specific truncation；
- 不设 raw-score relevance threshold。

先选择 mean `EvidenceHit@budget` 最高的 policy；差值不超过 0.02 时选择 mean canonical payload UTF-8 bytes 更少者，再同分选择更小 `paper_cap`、更小 `segments_per_paper`。冻结后只在 holdout 运行一次。若 development 中大量 top results 全为 grade 0，可在不解封 holdout 的前提下提出 v1.1 threshold protocol；v1.0 不临时校准不可比的 raw scores。

### 7.5 明确不进入第一轮

BM25L/BM25+、QLD、RM3/Rocchio、MeSH/ontology expansion、SPLADE、ColBERT、cross-encoder、LTR/active learning、citation graph、MMR、ANN/HNSW/IVF 不进入第一轮。只有第一轮保留的可诊断 failure 明确对应其机制优势时，才另写 protocol revision；不能在看过 holdout 后临时添加。

## 8. Metrics 与 complexity cost

### 8.1 Relevance metrics

Primary metric：paper-level `nDCG@5`（graded qrels）。

Secondary metrics：

- `Recall@3`、`Recall@5`，其中 grade≥2 视为 relevant；
- `MRR`，以第一篇 grade≥2 paper 为命中；
- `EvidenceHit@budget`：model-visible returned segments 中是否至少有一个 grade=2 segment；
- grade=3 paper catastrophic miss 数；
- query-level win/tie/loss 和逐 query error analysis；
- title bias、segment-count bias、abstract/full-text 分层结果。

不把单一平均分当成充分证据；必须同时展示每条 query 的 paired result 和 failure cases。

### 8.2 Determinism and boundary metrics

- 同一 Windows fresh process 重放 10 次：paper/segment order 与 canonical payload SHA-256 必须 10/10 相同。
- Finalists 在 Windows 与 macOS 各重放 3 次：最终 canonical payload SHA-256 必须全部一致；内部 float bit pattern 可以不同，但不得改变 observable result。
- Eligible candidate count/identity 必须逐 arm 完全一致；boundary/forbidden-field/network access violations 必须为 0。
- 所有 error fixture 必须产生预注册 typed failure；alternate-ranker 或 network fallback 次数必须为 0。

### 8.3 Runtime/dependency metrics

在最大 corpus stratum 上分别记录：

- 5 个 fresh process 的 cold start latency（process spawn 到 scorer ready）；
- 一次性 corpus representation build latency；
- 30 次 warm query 的 p50/p95 latency；
- peak resident memory；
- Python/package lock、wheel availability、model artifact bytes、完整 isolated environment bytes；
- 安装/离线重建步骤、license 与失败日志。

v1.0 complexity gates：

- Normative runtime 是 Python 3.13.7 + CPU FP32；每次 run 记录 OS、CPU 与 lock hash。所有 relevance 横向比较必须走同一 Windows CPU environment。
- warm p95 `<=1.0 s/query`；cold-start p95 `<=15 s`；最大 corpus representation build `<=60 s`；peak RSS `<=4 GiB`。
- Pinned model files `<=256 MiB`；完整 isolated environment `<=3 GiB`；不允许 source build。
- 正式比较期间必须 offline；所有 artifacts 在运行前下载、hash 并 pin。

CPU reference path 是 portability 和 attribution 要求，不是永久禁止 accelerator。只有 CPU 违反 warm、cold 或 corpus-build latency gate，且 batching/thread-count 优化后仍失败，才额外 benchmark `torch.xpu` 或 macOS MPS；accelerator 不得改变 relevance finalist。它只有同时满足以下条件才可成为可选 deployment backend：end-to-end latency 至少快 `2x`、没有 unsupported/fallback operators、所有 canonical paper/segment payload 与 CPU fixtures 完全一致、额外 environment 不超过 `1 GiB`，并独立锁定 backend/driver。Windows DirectML 因旧 PyTorch 约束和 maintenance-mode 风险不进入候选。CPU path 无论如何都必须保留并通过 correctness gates。

任一 gate 的变更都属于 protocol deviation，必须在解封 holdout 前批准并形成新 protocol version。

## 9. Promotion 与最终选择规则

### 9.1 Development promotion

每个 mechanism family 最多一个 configuration 进入 blind holdout。最多三个 finalists：

1. 最简合格 lexical baseline；
2. development best single scorer；
3. 仅当 lexical/dense 至少各修复一个对方的 grade≥2 miss 时，保留 best RRF。

### 9.2 Holdout decision rule

先应用 hard invariants，再看 relevance：

1. Boundary、offline、typed-failure、determinism 或 reference-runtime gate 任一失败，candidate rejected。
2. 在合格 candidates 中，如果更简单方案的 holdout `nDCG@5` 与最佳方案差值 ≤0.03，且 `Recall@5` 无下降、没有新增 grade=3 catastrophic miss，则选择更简单方案。
3. 更复杂方案只有满足以下任一路径且不违反 complexity gate 时才获得推荐资格：a) mean `nDCG@5` 至少提高 0.05，并且按逐 query `nDCG@5`（绝对差 ≤0.01 记 tie）计算的 `wins-losses >= 3`；b) 修复至少 2 条 query 的 grade=3/grade≥2 catastrophic miss、不新增同类 miss，且 mean `nDCG@5` 不比简单方案低超过 0.03。
4. 差值落在 `(0.03, 0.05)`、query-level wins 不稳定、qrels-stability gate 失败或 sample 不完整时，结果记为 `inconclusive`。
5. Paper cap 与 segments-per-paper 只在 winner family 内按 7.4 使用 development qrels 校准；随后对 holdout 做一次 frozen evaluation，不得反复打开 holdout 调整。v1.0 没有 threshold。

这些 margins 是 prototype 的预注册 decision policy，不是通用 IR 行业标准；Robert 可在首次运行前修改，运行后不得追溯修改。

## 10. Windows/macOS execution topology

### 10.1 角色分工

- Mac：controller、编辑 protocol/harness、准备 immutable input bundle、触发 SSH、收回结果、做轻量 smoke/review。
- Windows：唯一 full-matrix executor，使用 `D:\AI-Scientist-v2-workspace\` 下的 `repo/`、`envs/`、`model-cache/`、`artifacts/` 与 `tmp/` 存储 isolated Python 3.13 reference environment、pinned model cache、输入副本与 raw outputs。
- Mac 只对 finalists 做 cross-platform replay；若 dense 未进 finalist，Mac 不安装 neural stack。

Windows 当前已通过 existing SSH key 做连通性检查和 lexical/RRF tracked-fixture replay，`D:\python.exe` 为 3.13.7；硬件基线为 16-core CPU、约 32 GiB RAM、约 283 GiB `D:` free space。正式 run 仍必须在 `environment.json` 重新采集且不得保存 IP、用户名或 hostname 到 tracked evidence；workspace path 只进入 private execution evidence，不进入 model payload。

### 10.2 数据传输

- 代码、protocol、frozen inputs 与 pinned model artifacts 先形成 manifest 和 SHA-256，再经现有 SSH/Wi-Fi 复制一次。
- Windows 运行只读本地副本，不对网络挂载目录打分，不在每个 query 往返传 corpus/model。
- 运行后只回传 manifest、raw outputs、metrics、logs 与 hashes；payload 很小。
- 当前 Wi-Fi 6 足够，不要求 USB-C 数据线。只有实测传输不稳定时，才改用明确的 Ethernet direct link；网络路径变化不能改变 input hashes。

### 10.3 Reproducibility controls

- Python 3.13.7、per-platform package lock、model revision/hash 和 OS/CPU metadata 全部记录。Python 3.12/3.14 只是 compatibility candidates；Python 3.11 只保留历史审计证据，不是本 prototype target。
- Full relevance matrix 强制 CPU FP32 execution；neural arm 显式关闭 GPU/MPS/XPU/DirectML 自动选择。只有 8.3 的 evidence gate 触发后，accelerator 才在独立 performance cell 中测试。
- 固定 deterministic seed；`PYTHONHASHSEED`、BLAS/thread count 和 tokenizer parallelism 显式记录。
- 正式 run 设置 library offline flags，并以 network-denied fixture 验证不会在线 fallback。
- Full matrix 全部在同一 Windows environment 完成 latency comparison；不能把一个 arm 的 Windows latency 与另一个 arm 的 Mac latency横向比较。

## 11. Evidence layout 与 replay

Harness 使用 scoped raw-output ignore rule。实际 evidence 结构如下，不能复用 production Ideation Run 的 `run_id` 或冒充 Retrieval Audit Event：

```text
artifacts/local-ranking-prototype/<comparison_id>/   # private, gitignored
├── inputs-manifest.json
├── attempts/<attempt_id>/
│   ├── protocol.json
│   ├── comparison-summary.json
│   └── failure.json                           # attempt 级失败时存在
└── runs/<candidate>/<attempt_id>/
│   ├── command.json
│   ├── scores.jsonl
│   ├── payloads.jsonl
│   ├── metrics.json
│   ├── failure.json                           # candidate 失败时替代 scores/metrics
│   └── stderr.log

docs/prototypes/
├── local-literature-ranking-comparison-protocol.md
└── local-literature-ranking-comparison-result.md   # run 后才创建
```

每个 attempt 至少记录：Git commit SHA、protocol/config hash、input/query/qrels hashes 和 counts、exact command、OS/CPU/Python/dependencies/model identifiers、parameters、start/end timestamps、raw output/log hashes、metrics、latency/resource usage、failures 与 protocol deviations。Secrets、SSH identity、host/IP 和 absolute private paths不得进入 tracked summary。

唯一 replay 入口是：

```bash
python -m prototypes.local_ranking.run --protocol <frozen-protocol.json>
```

该入口已由 tracked fixture 验证。正式 protocol 仍须先冻结真实 input/qrels、完整 dependency locks 与（若包含 dense arm）model manifest；fixture 输出不是 ranking 决策证据。

## 12. 执行顺序与审批点

1. **Protocol approval — complete**：Robert 已批准由本协议冻结 case/query 数量、人工 judgment、candidate matrix、metrics、margins、resource gates 和 Windows/Mac 分工。
2. **Harness implementation/review — implementation complete, review evidence recorded**：已实现 isolated throwaway harness、formula/golden fixtures、strict qrels ingestion 与 one-command replay；tracked tests 覆盖 input identity、metric direction、failure capture 和 immutable attempt。正式数据接入前仍需复核 protocol JSON 与 approved corpus adapter 的边界。
3. **Environment smoke — lexical/RRF fixture complete**：Mac 已用 `uv` 获取临时 Python 3.13.7 并通过 19 项 harness tests；Windows 已通过 SSH 在 `D:\python.exe` 3.13.7 下完成最小 bundle transfer、`compileall` 与 5-candidate lexical/RRF fixture replay，临时 run 目录已清理。两端均未安装 neural stack。剩余 environment smoke 是建立 fresh isolated locks、校验 pinned dense artifacts，并在 Windows/Mac 对实际 finalists 做 offline replay；不读取 holdout qrels。
4. **Freeze inputs**：冻结 protocol/config、cases、queries、qrels、完整 dependency locks、model artifacts 与 hashes。
5. **Development run**：只用 development split 校准并冻结最多三个 distinct finalists。
6. **Blind holdout**：一次性运行、解封和比较；保留全部失败与偏差。
7. **Decision gate**：把 side-by-side evidence 交给 Robert；只有 Robert 看过结果并批准 winner 后，才在 ticket 写 Resolution、关闭 ticket 并更新 Wayfinder map。Production implementation 需要单独 authorization。

## 13. 已解决决策与剩余工作

v1.0 已解决此前所有 protocol-level 未决项：12 cases / 24 queries、Robert 延时盲复核、`lexical_normalization_v1`、pinned E5、Python 3.13 + CPU reference-first policy、`0.03/0.05` margins、resource gates、离散 output budget，以及 no-threshold v1 policy。

剩余的是执行证据，不是继续拍脑袋选参数：准备 approved cases/queries/qrels、生成 per-platform lock、做 fresh/offline dense smoke、准备并校验 pinned dense artifacts、运行 development 与 blind holdout。任何实际 winner、可选 accelerator backend 或 production ranker 仍必须由这些结果决定；`Choose and calibrate local literature ranking` 因此保持 open。
