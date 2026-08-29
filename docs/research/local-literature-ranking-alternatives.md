# 小规模冻结文献语料的本地排序技术路线调研

Research date: 2026-08-29（Asia/Shanghai）

> Runtime policy update（2026-08-30）：本文最初以当时的 Python 3.11 CPU-only 草案作为比较边界。经设备盘点与官方 runtime 调研，当前权威 policy 已改为 **Python 3.13 reference minor + mandatory CPU FP32 reference path + evidence-gated optional accelerator**。这不会改变本文对 ranking mechanism 的筛选结论；详见 [runtime 与最小 dense model 调研](local-ranking-runtime-and-dense-model.md) 和 [批准版 comparison protocol](../prototypes/local-literature-ranking-comparison-protocol.md)。

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本报告只扩展 prototype 的候选技术空间并做项目适配判断；不选择最终方案，不修改 retriever contract、ticket、map 或 runtime。

## 结论

候选绝不只有 BM25、local dense embedding 和笼统的 hybrid。成熟检索系统中至少还能找到以下机制族：

- TF-IDF/vector-space 与更简单的 IDF-weighted term coverage；
- Boolean、fielded、phrase/proximity scoring；
- query-likelihood language model、DFR/DPH/PL2；
- BM25L、BM25+、BM25F 等 BM25 变体；
- pseudo-relevance feedback（PRF）、RM3、Rocchio 和 controlled-vocabulary expansion；
- learned sparse retrieval（如 SPLADE）；
- late interaction（如 ColBERT）与 query-document cross-encoder；
- learning-to-rank（LTR）、active learning、citation-graph/document recommendation；
- rank fusion（如 RRF）与 diversity reranking（如 MMR）；
- passage/segment 到 paper 的 `max`、`top-m`、`sum/mean` 等聚合策略。

但这些名称混合了四个不同层次的问题，不能平铺成一组互斥的“ranker”：

1. **候选发现架构**：全量精确打分，还是 inverted/ANN index 先召回一部分；
2. **相关性 scorer**：TF-IDF、BM25、QLD、DFR、dense、cross-encoder 等；
3. **paper/field/segment 聚合**：title 如何加权，多个 segment 如何形成 paper score，返回哪些 segment；
4. **排序后处理**：PRF/query expansion、fusion、diversification、LTR/active learning。

对本项目，最先应锁定的架构基线是：**对当前 case 的全部 eligible papers 和 Retrieval Segments 做 exhaustive score-all；不使用 ANN，也不设可能漏掉 approved paper 的 first-stage candidate retrieval。** 3–36 篇论文的规模不需要用近似召回换速度；exact scan 反而最容易审计、重放、做稳定 tie-break 和解释合法 empty。Faiss 官方把 `IndexFlatL2`/`IndexFlatIP` 明确列为 exhaustive exact search，而 HNSW/IVF 为 non-exhaustive；Semantic Scholar 开源的 S2 search reranker 也明确写道，文档足够少时可以不要 first-stage ranker（[Faiss index table](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)、[S2 search reranker](https://github.com/allenai/s2search#readme)）。

建议进入第一轮 prototype 的不是十几个独立系统，而是一组能回答关键假设的最小、正交候选：

1. IDF-weighted overlap / cosine TF-IDF，作为透明 lexical sanity baseline；
2. BM25，外加 title/segment 分字段处理；只有实际 segment 长度分布证明需要时，再加入 BM25L/BM25+；
3. 一个不同概率假设的 classical challenger：Dirichlet query likelihood（QLD）和/或 parameter-free DPH；
4. 一个 pinned local bi-encoder embedding，使用 exact score-all，不使用 ANN；
5. lexical 与 dense 的 deterministic RRF，避免直接混合不可比的原始分数；
6. 对最佳 lexical scorer 做 phrase/proximity bonus 的 ablation；
7. paper aggregation 至少公平比较 `max segment` 与固定 `top-m` 聚合；`sum all segments` 只作为长度偏置的负对照。

SPLADE、ColBERT、cross-encoder、PRF/RM3、MeSH/ontology expansion、LTR/active learning、citation graph 和 MMR 都是实在存在的路线，但不应默认进入第一轮。它们分别需要更重的模型依赖、额外全局资源、稳定 relevance feedback/qrels、被合同禁止的 metadata，或一个尚未获批的“相关性之外还要多样性”的目标。

以上是 prototype 候选集建议，不替 Robert 做最终选型。

## 研究边界与项目约束

判断依据来自已批准的 `Define the frozen corpus contract` 和 `Define the Scoped Literature Retriever contract`：

- 每个 case 只有 3–36 篇冻结、validated、approved references；
- runtime 完全 local/offline，Python 3.13 reference minor，并保留 mandatory CPU FP32 reference path；
- ranker 只能读取 normalized query、title、eligible source-faithful content/Retrieval Segments；
- paper 是结果和排序单位，同一 `paper_id` 最多一次；
- citation count、venue、year、publication type、Target-derived metadata、previous feedback/state 等不得作为 ranker 输入；
- 相同 pinned corpus、policy/version 和 query 必须产生相同的 paper/segment 顺序和 canonical payload；
- 禁止 remote/provider/global fallback，也禁止失败时换 alternate ranker；
- prototype 只产生比较证据，最终方案由 Robert 批准。

因此，大规模 benchmark 上的平均优势不能直接外推。本项目真正要测的是：在极小、已限定 candidate set 中，哪个 scorer 与哪个 segment aggregation 能把有用原始证据排到固定 context budget 内，同时满足 replay 和跨平台 observable determinism。

## 架构基线：exhaustive score-all，不把 ANN 当作 ranking model

### 为什么这是独立于 scorer 的决定

ANN/HNSW/IVF 解决的是“大量向量不能逐个比较”的候选发现成本，不决定 embedding 本身是否表达相关性。Faiss 的官方索引表把 Flat L2/IP 标为 exhaustive，把 HNSW 与 IVF 标为 non-exhaustive；其 FAQ 还指出，当 IVF 探测所有 inverted lists 时已经退化为 exact brute-force，Flat 会更快（[Faiss indexes](https://github.com/facebookresearch/faiss/wiki/Faiss-indexes)、[Faiss FAQ](https://github.com/facebookresearch/faiss/wiki/FAQ)）。

本项目每次最多只有 36 篇 paper。即使一篇拆成若干 bounded segments，数量也远低于需要近似索引的量级。因此，无论 scorer 是 lexical、dense 还是 cross-encoder，prototype 都应：

1. 先枚举全部 eligible papers/segments；
2. 对每个候选精确计算 score；
3. 在 paper 层聚合；
4. 统一以 score 降序、stable `paper_id` 升序 tie-break；
5. 再按 approved cap/threshold 裁剪。

这不排斥使用倒排结构计算 corpus statistics，也不排斥预计算 frozen embeddings；它只排斥“索引先漏掉一部分候选”。S2 search reranker 的官方 README 同样将 first-stage ranker 描述为大规模 pipeline 的常规组成，同时明确 few-enough documents 时可以直接 rerank 全部候选（[AllenAI `s2search`](https://github.com/allenai/s2search#readme)）。

### 对本项目的收益

- **相关性评价更纯**：不会把 ANN recall failure 误判为 scorer failure；
- **empty 可解释**：empty 只能来自 approved threshold，而不是 approximate search 没找到；
- **可审计**：audit event 可以记录全部 candidate/segment scores；
- **可重放**：无 index training、graph traversal、probe-count 等隐藏状态；
- **实现更轻**：lexical scorer 可用小型 Python 数据结构，dense scorer 可直接矩阵/逐向量计算；
- **公平比较**：所有 scorer 面对同一个完整 candidate set。

结论：Lucene/Terrier/Pyserini/Faiss 可以作为公式与系统行为参考；它们的大规模 candidate retrieval machinery 不是本项目 architecture dependency。

## 候选机制族

### 1. IDF-weighted overlap 与 TF-IDF/vector space

经典 vector-space model 把 query/document 表示为 term-weight vectors，再用 cosine similarity 比较；Lucene 的 `TFIDFSimilarity` 官方文档也按 weighted vectors 和 cosine 说明该模型（[Salton, Wong & Yang, 1975](https://doi.org/10.1145/361219.361220)、[Lucene `TFIDFSimilarity`](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/TFIDFSimilarity.html)）。

**本项目适配：高，适合作为第一轮 baseline。**

- 实现和解释成本最低；term contribution、IDF、title boost 都能完整记录；
- 无模型文件、无网络、无 PyTorch；固定 tokenizer/normalization 后容易跨平台重放；
- 能暴露 dense/复杂模型是否真的优于“只要稀有 query terms 对上即可”的简单策略。

局限是 exact-token vocabulary mismatch，且 N=3–36 时 IDF 估计很离散。它不应被当成最终默认，只应作为必须击败的透明基线。还可以加入一个更简单的 `matched unique query terms / query terms` 或 IDF-weighted coverage，帮助判断 TF saturation/length normalization 到底提供了多少净收益。

### 2. Boolean、fielded 与 phrase/proximity evidence

SQLite FTS5 的官方语法支持 phrase、NEAR、column filters 和 AND/OR/NOT；Terrier 支持 BM25F/PL2F 等 field models，以及 DFR/MRF proximity modifiers（[SQLite FTS5 query syntax](https://www.sqlite.org/fts5.html)、[Terrier retrieval configuration](https://github.com/terrier-org/terrier-core/blob/5.x/doc/configure_retrieval.md)）。

**本项目适配：作为 scorer feature/ablation 高，作为严格 filter 低。**

- title 与 source content 的信息密度不同，field-aware weighting 是直接相关的；
- scientific phrases、缩写和多词术语相邻出现时，proximity/phrase bonus 可能比独立 unigram 更可信；
- 规则是离散、透明、确定的。

但 model input 是自然语言 query，不是用户编写的 Boolean expression。默认 strict AND 会因一个未命中 token 产生大量 false empty；NOT、field filter 和 prefix 也不是当前 model-visible contract 的控制项。因此建议只比较：

- unigram base score；
- normalized query 中稳定识别出的 bigram/phrase bonus；
- 有界 unordered-window proximity bonus；
- title 与 segment 的固定 field weights。

不要把自然语言 query 直接交给 Lucene/SQLite query parser，也不要让 parser 的语法解释成为隐藏 policy。

### 3. Query-likelihood language models（QLD/JM）

query-likelihood 为每个 document 建语言模型，按该模型生成 query 的可能性排序；smoothing 用 collection model 避免 unseen term 概率为零。Lucene 当前同时实现 Dirichlet 和 Jelinek–Mercer language-model similarities；Dirichlet implementation 明确暴露 `mu` smoothing parameter（[Ponte & Croft, 1998](https://ciir.cs.umass.edu/pubfiles/ir-120.pdf)、[Lucene similarities](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/package-summary.html)、[Lucene `LMDirichletSimilarity`](https://lucene.apache.org/core/7_6_0/core/org/apache/lucene/search/similarities/LMDirichletSimilarity.html)）。

**本项目适配：中，值得作为一个 classical challenger。**

优点是与 BM25 不同的概率假设，且仍然 local、CPU、可解释。问题是 collection language model 只从 3–36 篇论文估计，极小 corpus 中一个 paper 的词频会显著改变背景概率；`mu`/`lambda` 也必须在 frozen canary 上校准，不能照搬 Lucene 默认值。它适合回答“BM25 saturation 是否真是这里的最佳 lexical assumption”，不适合一开始就增加多个 smoothing 变体。

### 4. DFR / DPH / PL2 / information-based models

DFR 按 term 在 document 中相对随机模型的 divergence 赋权。Lucene 当前提供 DFR、information-based、divergence-from-independence 等 families；Terrier 列出 PL2、DPH、DLH、DFRee 等，并把 DPH 标为 parameter-free（[Amati & van Rijsbergen, 2002](https://eprints.gla.ac.uk/3798/)、[Lucene similarities](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/package-summary.html)、[Terrier weighting models](https://github.com/terrier-org/terrier-core/blob/5.x/doc/configure_retrieval.md#weighting-models-and-parameters)）。

**本项目适配：中。**

- DPH 的 parameter-free 性质对没有大规模 tuning set 的项目有吸引力；
- DFR 是 BM25/TF-IDF 之外的成熟 unsupervised lexical family；
- scorer contribution 可以逐 term 审计。

主要风险仍是 N 太小，collection frequency 的统计稳定性需要真实 corpora 验证。第一轮最多加入 DPH 或 PL2 中一个，不应把 Terrier 的几十种组合全部 sweep；否则 prototype 会变成对 canary 的多重比较和过拟合。

### 5. BM25 variants：BM25L、BM25+、BM25F

BM25 的 `k1` 控制 TF saturation，`b` 控制 length normalization；Lucene 当前默认分别为 1.2 和 0.75，但也明确允许调参（[Lucene BM25 tuning](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/package-summary.html)）。

- BM25L 针对 standard BM25 对 very long documents 的过度惩罚，通过平移 normalized TF 处理该问题（[Lv & Zhai, “When Documents Are Very Long, BM25 Fails!”](https://experts.illinois.edu/en/publications/when-documents-are-very-long-bm25-fails/)）；
- lower-bounded TF normalization/BM25+ 保证一个实际出现的 query term 不会因文档很长而接近“未出现”的贡献（[Lv & Zhai, “Lower-Bounding Term Frequency Normalization”](https://doi.org/10.1145/2063576.2063584)）；
- BM25F 不是简单把 title score 与 body score 线性相加，而是在 BM25 saturation 前聚合各 field 的 normalized term frequencies（[Robertson, Zaragoza & Taylor, 2004](https://doi.org/10.1145/1031171.1031181)）。

**本项目适配：BM25F 思路高；BM25L/BM25+ 条件适配。**

title 与 eligible content 天然是不同 fields，直接比较一个 BM25F-like variant 有意义。BM25L/BM25+ 是否需要则取决于 segmentation：如果所有 Retrieval Segments 都有相近的有界长度，long-document defect 已被大幅削弱；如果 publisher abstracts 与 full-text segments 长度仍悬殊，再加入一个 lower-bounded variant 才有证据价值。

不要同时无约束 sweep `k1 × b × title weight × segment aggregation × variant`。先锁 normalization/segmentation，再做小的预注册参数网格和 held-out canary，避免从 3–36 篇 corpus 上“调出”偶然最优值。

### 6. Pseudo-relevance feedback、RM3、Rocchio 与 query expansion

RM3 从第一次排序的 top feedback documents 估计 relevance model，再与原 query 插值；Anserini/Pyserini 的官方实现显式暴露 `fb_docs`、`fb_terms` 和 `original_query_weight`，并执行 second-pass search。Terrier 也支持 Bo1/Bo2/KL query expansion，真正 relevance feedback 则要求 qrels（[Lavrenko & Croft, 2001](https://ciir.cs.umass.edu/pubfiles/ir-225.pdf)、[Anserini RM3 source](https://github.com/castorini/anserini/blob/master/src/main/java/io/anserini/rerank/lib/Rm3Reranker.java)、[Terrier query expansion](https://github.com/terrier-org/terrier-core/blob/5.x/doc/configure_retrieval.md#query-expansion)）。

**本项目适配：延期。**

它可以弥补术语不一致，但当前没有 per-query relevance labels；pseudo feedback 只能假设第一次 top papers 相关。在 3–36 篇小 corpus 中，top 1–3 篇几乎就是整个扩展模型的来源，早期错误很容易自我强化并造成 query drift。它还引入 second-pass state；虽然可做成确定性计算，但 audit 和参数面明显扩大。

建议只有在第一轮证据明确显示“gold paper 因同义词/术语差异长期被 lexical scorer 漏排”，且 dense/proximity 仍不能解决时，再把 RM3/Rocchio 作为第二轮受控候选；expanded terms 和全部 first-pass scores 必须进入 audit。

### 7. Controlled vocabulary / ontology expansion

PubMed Automatic Term Mapping 会把无 field tag 的词依次映射到 Subject Translation Table（含 MeSH）、journal、author 等索引；MeSH 是 NLM 用来标引 MEDLINE/PubMed 的受控词表（[PubMed Help: Automatic Term Mapping](https://pubmed.ncbi.nlm.nih.gov/help/#how-pubmed-works-automatic-term-mapping-atm)、[NLM MeSH](https://www.ncbi.nlm.nih.gov/mesh)）。

**本项目适配：默认淘汰，特定领域可延期。**

- 当前 237 cases 跨多个学科，MeSH 只覆盖 biomedical vocabulary；
- 受控词表是额外全局资源，必须离线 vendoring、pin version/hash、声明 license 和映射 policy；
- corpus records 没有 approved subject headings，不能静默用外部 metadata 扩展；
- query mapping 错误会变成不可见的 semantic rewrite。

如果未来 canary 只针对医学子集，并且 Robert 单独批准 pinned MeSH 作为 declared ranker resource，可把“原 query + 可审计 synonym expansion”做成独立 prototype。它不是通用 v1 候选。

### 8. Latent semantic indexing（LSI/LSA）

LSI 对 term-document matrix 做 truncated SVD，把 query/document 投影到低维 latent space，以缓解 synonymy/polysemy（[Deerwester et al., 1990](https://doi.org/10.1002/%28SICI%291097-4571%28199009%2941%3A6%3C391%3A%3AAID-ASI1%3E3.0.CO%3B2-9)）。

**本项目适配：淘汰第一轮。**

3–36 documents 太少，case-local SVD basis 容易由单篇论文主导，rank 和维度选择没有可靠校准样本；跨 case 重建不同 latent spaces 也降低可解释性。使用一个 frozen global basis 又会引入额外未声明 corpus/resource。它比 TF-IDF 多了线性代数和参数，却不具备现代 pretrained embedding 的外部语义知识，不是这里的高价值比较臂。

### 9. Learned sparse retrieval（SPLADE/uniCOIL）

SPLADE 用 masked-language-model head 学习 query/document 的 sparse term expansion 和 term weights，输出仍可由 inverted index 处理。Pyserini 把 learned sparse、dense、BM25 和 hybrid 明确列为不同 representation families；其 SPLADE 指南需要 transformer encoder、model checkpoint 和 Lucene impact index（[SPLADE v2 paper](https://arxiv.org/abs/2109.10086)、[NAVER SPLADE source](https://github.com/naver/splade)、[Pyserini learned-sparse guide](https://github.com/castorini/pyserini/blob/master/docs/conceptual-framework3.md)）。

**本项目适配：延期。**

它兼具 lexical sparsity 和 learned expansion，理论上能填补 exact term mismatch；但对 N≤36，inverted-index efficiency 没有价值，留下的主要收益来自一个重量级 pretrained model。它增加 PyTorch/Transformers、model artifact、subword tokenizer 和 cross-platform numeric behavior。Pyserini 的 reproduction notes 也明确区分 neural inference 的小幅 nondeterminism与预计算权重的 deterministic retrieval（[Pyserini SPLADE reproduction](https://github.com/castorini/pyserini/blob/master/docs/experiments-spladev2.md)）。只有轻量 baseline 失败后，才值得和 dense/cross-encoder 比较净收益。

### 10. Scientific document embeddings：SPECTER/SPECTER2

SPECTER 用 citation graph 作为训练时 document-relatedness signal，推理时从 title+abstract 产生 paper embedding；SPECTER2 增加 task-format-specific adapters，其中 ad-hoc query adapter 编码短文本 query，proximity adapter 编码 title+abstract candidate papers（[SPECTER paper](https://aclanthology.org/2020.acl-main.207/)、[SPECTER2/SciRepEval paper](https://aclanthology.org/2023.emnlp-main.338/)、[SPECTER2 ad-hoc query model card](https://huggingface.co/allenai/specter2_adhoc_query)）。

**本项目适配：作为 dense candidate 有条件适配，不是无条件首选。**

优势是训练域与学术文献一致，而且 inference 不需要读取当前 paper 的 citation graph。风险是：

- 它的标准 candidate input 是 title+abstract；对 official-full-text segments 的适配没有同等直接的官方保证；
- 模型权重在训练时编码了全球 citation supervision，必须被视为需要 pin/hash/license 的 declared ranking resource，而不是“只读本 corpus”就自然透明；
- 模型和 adapter 依赖较重；
- PyTorch 官方不保证跨 release/platform 的 bitwise reproducibility。项目要求的是最终有序 payload 一致，因此仍可通过固定版本、CPU backend、stable tie-break 和跨平台 fixture 证明 observable determinism，但不能只声明 seed 即通过（[PyTorch reproducibility](https://docs.pytorch.org/docs/2.9/notes/randomness.html)）。

如果第一轮保留一个 dense arm，应先确认它能公平处理本项目批准的 content types；不要让 SPECTER2 只看 abstract、而 lexical scorer 看 full-text segments，然后把差异误判为 ranking model 差异。

### 11. Late interaction（ColBERT）

ColBERT 分别编码 query/document tokens，再用 late interaction 的细粒度 matching 计算相关性；它相对 cross-encoder 可预计算 document representations，同时比单向量 bi-encoder 保留更多 token-level interaction（[ColBERT paper](https://arxiv.org/abs/2004.12832)）。官方实现依赖 PyTorch/Transformers/Faiss，并注明 training/indexing 需要 GPU，虽然提供 CPU runtime environment（[ColBERT repository](https://github.com/stanford-futuredata/ColBERT)）。

**本项目适配：淘汰第一轮。**

N≤36 时，其大规模 index/pruning 优势消失；剩下的潜在 relevance gain 要付出 token embeddings、模型 artifact、复杂依赖和 determinism validation。若 bi-encoder 明显漏掉精确 scientific term interactions，且 cross-encoder CPU latency不合格，late interaction 才值得后续比较。

### 12. Cross-encoder reranking

Cross-encoder 对每个 `(query, document/segment)` pair 联合编码并直接输出 relevance score。Sentence Transformers 官方文档指出它通常比 bi-encoder 更准确，但必须逐 pair 计算，因此更慢，常用于 rerank first-stage top-k（[Cross-encoder usage](https://www.sbert.net/docs/cross_encoder/usage/usage.html)、[CrossEncoder API](https://www.sbert.net/docs/package_reference/cross_encoder/model.html)）。

**本项目适配：技术上可行，但延期。**

这里的 N 很小，逐 pair score-all 反而使 cross-encoder 比在 web-scale retrieval 中更可行；它是值得保留的真正替代路线，不应被误归为 dense embedding。然而第一轮的目标是 minimal：cross-encoder 会引入最重的 CPU latency、model/dependency 和 truncation/segment policy，且现成 MS MARCO reranker 与跨领域 scientific queries 存在 domain mismatch。只有 classical/dense baseline 在真实 relevance judgments 上不足，才进入 gated second round。

### 13. Learning-to-rank 与 PubMed Best Match

PubMed Best Match 是典型两阶段系统：BM25 first stage 后，对 top 500 以 LambdaMART rerank；训练数据来自历史 user searches，并使用 query-document、document 和 query features。PubMed 当前 help 说明 learned ranker 组合超过 150 个 signals，包括 publication type/year 等 document features（[NCBI Best Match paper](https://pubmed.ncbi.nlm.nih.gov/30153250/)、[PubMed Best Match help](https://pubmed.ncbi.nlm.nih.gov/help/#algorithm-for-finding-best-matching-citations-in-pubmed)）。Terrier 也支持把多个 weighting models/features 交给 learned ranking model（[Terrier LTR](https://github.com/terrier-org/terrier-core/blob/5.x/doc/configure_retrieval.md#learning-to-rank)）。

**本项目适配：当前淘汰。**

没有足量 query-level qrels、click logs 或跨 case 可迁移的 relevance labels，无法训练或校准 LTR；PubMed 的 publication date/type/usage 等重要 signals 还被当前 ranker input contract 明确禁止。手写 linear combination 不是“轻量 LTR”，而是未经证据批准的 feature weighting。

### 14. Active learning 与 systematic-review screening

ASReview 是公开实现的 active-learning literature screening system：reviewer 持续标注 relevant/not relevant，模型用这些 decisions 迭代更新下一批 prioritization；默认配置使用 TF-IDF 特征和 classifier/balancing/query strategy（[ASReview paper](https://www.nature.com/articles/s42256-020-00287-7)、[ASReview workflow/source](https://github.com/asreview/asreview)、[ASReview default model source](https://github.com/asreview/asreview/blob/main/asreview/models/models.py)）。

**本项目适配：当前淘汰。**

ASReview 解决的是几百/几千 records 的交互式 inclusion screening，不是一次自然语言 query 对 3–36 approved references 的 stateless evidence ranking。当前 retriever 明确不能读取 previous queries/results 或 mutable state，也没有每次 tool call 的 human labels。ASReview 提醒我们：若未来获得 reliable relevance feedback，supervised prioritization 是一条路线；它不提供当前 ticket 可直接采用的 scorer。

### 15. Citation graph / paper-to-paper recommendation

Semantic Scholar 同时提供 Academic Graph search 与“给定正/负 seed papers”的 Recommendations API；SPECTER/SPECTER2 也利用 citation relationships 训练 document embeddings（[Semantic Scholar API tutorial](https://www.semanticscholar.org/product/api/tutorial)、[SPECTER](https://aclanthology.org/2020.acl-main.207/)）。

**本项目适配：runtime graph ranking 淘汰；citation-supervised pretrained text model 有条件适配。**

PageRank、co-citation、bibliographic coupling、citation count 或 seed-paper recommendation 都需要 graph/metadata，而当前 ranker 只能读 normalized query、title 和 eligible content；用 reference graph 还可能把“重要/相近”混成“回答当前 query”。SPECTER 的差别在于 citation graph只用于离线预训练，当前 inference 仍读 text；若 model artifact 被明确批准、pin 和验证，它可以作为 dense scorer，而不能被描述成 runtime citation ranking。

### 16. Rank fusion

RRF 把多个系统的 rank positions 转成 reciprocal-rank contributions 后相加，不要求原始 scores 在同一尺度；原始论文在多个 TREC runs/LETOR 数据上比较了这种简单 fusion（[Cormack, Clarke & Büttcher, 2009](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/)）。Pyserini 的 reproducible experiments 也使用 RRF 融合 BM25 与 dense rankings（[Pyserini RRF example](https://github.com/castorini/pyserini/blob/master/docs/experiments-wiki-corpora.md)）。

**本项目适配：高，适合第一轮 hybrid baseline。**

RRF 比直接 `alpha * BM25 + beta * cosine` 更少依赖 score normalization，排序过程也容易审计。但 N 只有 3–36，经典 `k=60` 会让相邻 rank contribution 很接近；`k` 不能未经验证照搬。prototype 应把 RRF 当作“是否互补”的测试，不预设 fusion 必然胜过最佳单模型。

### 17. Diversification / MMR

MMR 逐步选择同时满足 query relevance 和对已选结果 novelty 的候选，可用于 document reranking 和 passage selection（[Carbonell & Goldstein, 1998](https://www.cs.cmu.edu/afs/cs/Web/People/jgc/publication/MMR_DiversityBased_Reranking_SIGIR_1998.pdf)）。

**本项目适配：延期。**

MMR 优化的不是纯 relevance；它引入 document-document 或 segment-segment similarity、`lambda` 和顺序依赖。若 ideation 的 context budget 很小且同一 paper/不同 papers 的 top segments 高度重复，它可能提高 evidence coverage；但也可能把最相关的重复证据降权。必须先由 Robert 批准“在固定 relevance floor 后最大化 coverage/diversity”作为目标，并定义 redundancy gold labels，不能偷偷塞进 ranking score。

## Paper ranking 与 segment aggregation 必须分开

当前合同规定 paper 是结果单位，但 evidence 来自 paper 内的 Retrieval Segments。任何 scorer 都仍需回答两个独立问题：

1. 一个 segment 与 query 多相关；
2. 多个 segment 如何汇成一个 paper score，以及哪些 segment 随 paper 返回。

长文档检索研究确实把这看作独立设计面。PARADE 比较了 passage signals 的多种聚合，并发现“一个局部 passage 足以回答”的 collection 与“相关信号分散在全文”的 collection 适合不同策略；复杂 representation aggregation 也不总是优于简单 max（[PARADE paper](https://eprints.gla.ac.uk/298257/)）。

### 候选 aggregation

| 方法 | 适合假设 | 主要风险 | 第一轮角色 |
| --- | --- | --- | --- |
| `max(segment_score)` | 一处强 source-faithful evidence 就足以使 paper relevant | segment 多的长 paper 有更多“撞上高分”的机会；一个 spurious hit 可支配 paper | 必测 baseline |
| `mean(top-m)` / fixed top-m aggregate | relevance 需要少量多处证据，抑制单一偶然高分 | `m`、不足 `m` 时的处理需要固定；可能稀释单个 decisive segment | 必测 challenger |
| `sum(top-m)` | 多个相关 segments 应累积贡献 | 即使 `m` 固定，score scale 仍随有效 segment 数变化 | 可与 mean 二选一 |
| `sum(all)` | relevance 在全文广泛分布 | 强烈偏向 segment 数/文档长度，跨 abstract/full text 不公平 | 负对照，不建议默认 |
| title + segment score | title 提供高密度 topic signal，segment 提供证据 | field weight 与 saturation 若处理不当会重复计数 | 必测 field ablation |
| segment MMR | 返回的 passages 应减少重复并扩大 coverage | 目标从 relevance 变为 relevance+novelty，需额外 similarity 与 `lambda` | 延期 |

第一轮应把“paper score aggregation”与“model-visible segment selection”分别记录。例如 paper 可以按 `max` 或 `top-m` 排名，但返回 segments 始终从该 paper 内按原始 segment relevance 选前 `s` 个，并用 canonical content-item order/source start 作 tie-break。这样才能判断 paper 排错还是 evidence 选错。

还应避免一个常见不公平：把整篇 official full text 拼成一个长 document 给 lexical ranker，却把它分段给 dense ranker。所有 arms 必须共用同一 approved segmentation，或明确把 segmentation 作为单独 factorial variable。

## 真实系统给本项目的参考，而不是直接依赖结论

| 系统 | 提供的机制参考 | 为什么不直接作为 v1 依赖 |
| --- | --- | --- |
| Apache Lucene | TF-IDF/VSM、BM25、Boolean、DFR、IB、QLD/JM、per-field Similarity，且官方文档给出参数与公式入口（[Lucene similarities](https://lucene.apache.org/core/10_3_1/core/org/apache/lucene/search/similarities/package-summary.html)） | Java/index lifecycle 与本项目 Python reference runtime、N≤36 不成比例；适合对照公式和解释，不代表需要嵌入 Lucene |
| Terrier | BM25/TF-IDF/LM、几十种 DFR、BM25F/PL2F、proximity、PRF、LTR（[Terrier config](https://github.com/terrier-org/terrier-core/blob/5.x/doc/configure_retrieval.md)） | Java 平台和大规模 experiment framework 过重；庞大 model menu 会诱发无监督 sweep |
| Anserini/Pyserini | reproducible IR baselines、BM25、RM3/Rocchio、learned sparse、dense、hybrid/RRF（[Anserini](https://github.com/castorini/anserini)、[Pyserini search](https://github.com/castorini/pyserini/blob/master/docs/usage-search.md)） | 当前 Pyserini 安装文档以 Python 3.12 构建并依赖 Lucene/Faiss/model stacks；可作为 reference oracle，不应默认成为 minimal runtime dependency（[Pyserini installation](https://github.com/castorini/pyserini/blob/master/docs/installation.md)） |
| SQLite FTS5 | phrase/NEAR/Boolean/columns，内建 BM25 和 column weights；Python 常见环境已有 SQLite（[FTS5](https://www.sqlite.org/fts5.html)） | FTS5 的 `k1=1.2,b=0.75` 是 hard-coded，score 符号与常见 BM25 相反，`MATCH` 先过滤 non-matches；不同 Python/OS build 是否含同一 FTS5/tokenizer 也需实证。适合做 formula/behavior oracle，不适合直接取代可校准 score-all implementation |
| PubMed Best Match | BM25 first stage + LambdaMART rerank；Automatic Term Mapping/MeSH；展示 LTR 与 controlled vocabulary 在有大规模 logs/metadata 时如何用（[Best Match](https://pubmed.ncbi.nlm.nih.gov/30153250/)、[PubMed Help](https://pubmed.ncbi.nlm.nih.gov/help/)） | logs、publication metadata 和 global biomedical index 都不在当前 allowed inputs；不是本地小语料 scorer |
| Semantic Scholar / S2 search | academic LTR、text fields、citation/static features、scientific embeddings；开源 reranker明确允许 few-doc score-all（[S2 reranker](https://github.com/allenai/s2search)、[Explicit Semantic Ranking](https://ai2-website.s3.amazonaws.com/publications/Explicit_Semantic_Ranking.pdf)） | 开源 reranker artifact 约 10 GB compressed/17 GB uncompressed并要求 17 GB+ RAM，且依赖 venue/authors/key citations 等 forbidden fields；只借鉴“academic search is multi-signal”和“small N 可无 first stage” |
| ASReview | title/abstract screening 的 active-learning loop、simulation 和 transparent decision log（[ASReview](https://github.com/asreview/asreview)） | 需要 human relevance labels 和 mutable iteration，目标是 screening，不是 stateless query retrieval |

SQLite FTS5 特别值得借鉴但不宜直接锁定。其官方 `bm25()` 支持对 columns 赋不同权重，证明 title/content field weighting 是成熟的轻量实现模式；但 `k1`/`b` 固定、只给 `MATCH` rows 打分和 tokenizer/build variance 都与本 ticket 的“校准、score-all、跨平台证明”冲突（[FTS5 `bm25()`](https://www.sqlite.org/fts5.html#the_bm25_function)）。

## 建议的第一轮 prototype 候选集

### 共同 architecture 与数据面

- exhaustive enumerate 全部 eligible papers/segments；
- 所有 arms 使用相同 normalized query、tokenizer input、segmentation 和 content eligibility；
- 不使用 ANN、HNSW、IVF 或 first-stage top-k pruning；
- 每个 scorer 输出完整 candidate/segment score table；
- paper/segment 都使用合同规定的 stable tie-break；
- model artifact、tokenizer、formula、float dtype、dependency version、parameter grid 和 policy hash 全部 pin/audit；
- threshold 与 output cap 在 scorer 比较之外单独校准。

### Scoring arms

1. **Lexical sanity baseline**：IDF-weighted unique-term coverage + cosine TF-IDF（二者实现成本都很低，可判断 cosine/TF 是否有净收益）。
2. **BM25 baseline**：固定可解释 grid 的 `k1,b`；title/content 分字段 ablation。
3. **BM25 family challenger**：优先 BM25F-like field TF aggregation；仅当长度统计显示强异质性时加 BM25L 或 BM25+ 中一个。
4. **Classical probabilistic challenger**：QLD 和 DPH 至少选一个；若二者实现/验证成本都很低，可以都留到第一次筛选后再淘汰。
5. **Phrase/proximity ablation**：只叠加在最佳 lexical arm 上，使用固定 bigram/window policy。
6. **Dense challenger**：一个 pinned、offline、CPU-capable bi-encoder，exact score-all；必须能处理同一 approved content policy并通过 cross-platform payload-order fixture。
7. **Fusion challenger**：最佳 lexical arm + dense arm 的 RRF；小网格校准 `k`，不默认采用 `60`。

### Paper/segment aggregation arms

- `max segment`；
- fixed `top-m` mean 或 sum（二选一后再小网格校准 `m`）；
- title 作为独立 field 的 on/off/weight ablation；
- `sum all` 仅作 length-bias negative control；
- 返回 segment selection 与 paper score 分开评价。

### 比较指标

除了 ticket 已有的 relevance、determinism、dependencies、latency 和 failure cases，至少还要分开记录：

- paper-level `Recall@k`、MRR/nDCG（有 graded judgments 时）；
- segment-level evidence hit/coverage；
- 合法 empty、all-zero、OOV、single-token、phrase-heavy、very long query；
- title-only lexical hit、abstract vs official-full-text、同一 paper 多高分 segments；
- score ties、near-ties 与跨 macOS/Linux/Windows 的最终有序 payload/hash；
- cold-start（加载 model/index）与 warm query latency；
- dependency/model artifact size、许可证、离线安装和 Python 3.13 Windows/macOS wheel availability。

没有 frozen query set 和 independent relevance judgments 时，任何“更相关”的结论都不可信。ASReview/PubMed 的价值正说明了监督信号的重要性；本 prototype 不应拿 Target Paper、citation metadata 或模型自评偷偷代替 qrels。至少需要 Robert/独立 reviewer 在看不到 ranker identity 的条件下对 canary query-paper/segment 做 relevance judgments，并将 tuning cases 与 final comparison cases 分开。

## 明确淘汰或延期项

### 第一轮明确不做

- HNSW、IVF、PQ、ANN/vector database：规模错配并引入 approximate recall failure；
- Lucene/Terrier/Pyserini 作为 production dependency：机制有用，runtime 过重；
- case-local LSI/SVD：样本太小、维度不稳、解释收益不足；
- citation count/PageRank/co-citation/bibliographic coupling：输入合同禁止，且衡量 importance/relatedness 不等于 query relevance；
- PubMed Best Match/S2 LTR 复刻：缺少 logs/qrels，并依赖 forbidden metadata；
- ASReview active-learning loop：没有每次 query 的 human feedback，且违反 stateless boundary；
- remote embedding/rerank/search API 或无结果 fallback：直接违反 offline/fail-closed contract。

### 证据不足时延期

- RM3/Rocchio/Bo1 PRF：先证明 lexical miss 来自 vocabulary mismatch，而不是 query/segmentation 问题；
- MeSH/UMLS/ontology expansion：只在单领域、pinned vocabulary、单独批准后；
- SPLADE：先证明简单 lexical+dense 无法满足 relevance；
- ColBERT：先证明需要 token-level semantic interaction，且依赖/CPU latency可接受；
- cross-encoder：小 N 下可行，但只有 baseline 不足时才值得承担 model/runtime 成本；
- MMR/diversification：先批准 diversity/coverage objective 和 relevance floor；
- learned score calibration/LTR：先积累足量、独立、冻结的 qrels，避免在同一小 canary 上训练和宣称胜出。

## 来源核验与不确定性

本轮只使用 primary sources：原始论文、系统所有者的官方文档、官方源代码/模型卡。没有使用博客或第三方“最佳实践”作为结论依据。

已核验的关键事实包括：

- Lucene/Terrier 确实实现 TF-IDF、BM25、DFR、LM、field/proximity 等 families；
- Anserini/Pyserini 的 RM3、sparse/dense/hybrid/RRF 路径可在官方 source/docs 定位；
- PubMed Best Match 的 BM25→LambdaMART 两阶段与训练 signals 来自 NCBI 论文/Help；
- ASReview 的 active-learning workflow 与 default TF-IDF/classifier config 来自官方 paper/repo；
- SPECTER/SPECTER2 的 citation-supervised scientific embeddings 与 ad-hoc query adapter 来自 ACL paper/official model card；
- Faiss exact/approximate index distinctions、PyTorch reproducibility limitation、SQLite FTS5 BM25/column weights 均来自官方 docs。

仍有以下不确定性，必须由 prototype 而不是文献类推解决：

1. 当前真实 ideation queries 的长度、术语形式和 phrase density 尚未形成 frozen evaluation set；
2. official full-text 的最终 segment length/count 分布尚未在本 ticket 中固定；
3. 没有现成 qrels，无法仅凭系统文献判断 BM25、QLD、DPH、dense 谁在本项目更相关；
4. neural scorer 的浮点输出不保证跨平台 bitwise identical，但最终排序/payload 可能仍稳定，必须用 near-tie fixtures 实证；
5. SPECTER2 的 title+abstract design 与 mixed abstract/full-text-segment policy 是否公平兼容尚未验证；
6. 小语料下 RRF `k`、BM25 `k1/b`、QLD `mu`、field weights、`top-m` 和 threshold 都不能照搬大规模默认值；
7. 文献系统通常优化 discovery、clicks 或 screening workload，本项目优化的是固定 approved corpus 内、受 context budget 限制的 source-faithful evidence retrieval，目标函数不同。

因此，本报告扩大并筛选了候选空间，但没有产生最终 ranker 决策。
