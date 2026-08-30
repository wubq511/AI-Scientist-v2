# Local ranking 是否需要论文全文

Decision date: 2026-08-30（Asia/Shanghai）

Status: **Approved decision for ticket 021 v1.1**

## 结论

Ticket 021 的第一轮正式比较采用 **题名 + publisher abstract**，不要求、也不混入论文全文。这个决定只批准摘要级 paper ranking；它不证明全文没有价值，也不把摘要级结果外推成 full-text passage retrieval 结论。

全文应作为后续独立的数据政策比较，而不是为了“数据越多越好”直接加入 v1。只有当真实 Ideation Runtime 准备稳定使用 `official_full_text`，并且来源、许可、覆盖、分段和回链都可冻结时，才值得建立 paired abstract-vs-full-text protocol。

## 从问题本质推导

当前 Scoped Literature Retriever 要解决的不是“在全世界论文中发现文献”，而是：在一个 Target 已经限定好的 3–36 篇 references 中，依据自然语言问题把最有用的 papers 和 source-faithful evidence 排在前面。

因此，是否需要全文取决于三个条件，而不是行业惯例：

1. **真实 runtime 的可用输入**：当前 raw reference snapshot 和原有 Semantic Scholar adapter 都稳定提供题名与摘要；12 个 proposal bundles 也全部是 `publisher_abstract`。全文不是当前系统已经拥有却被丢弃的字段。
2. **任务所需的信息粒度**：判断一篇 reference 是否与研究问题相关，题名与摘要通常足以支持第一阶段 paper ranking；具体实验参数、限制、负结果和段落级论据可能只存在于全文，那属于更细的 evidence retrieval 能力。
3. **公平比较的前提**：只有部分 papers 有可复用全文时，混合输入会把“ranker 好坏”与“哪些 paper 恰好有全文、正文有多长、如何分段”混在一起。这样无法归因，也会使 BM25、dense 和 aggregation arms 面对不同的长度与 segment-count 分布。

## 常见论文检索系统实际使用什么

没有“论文检索都使用全文”这一事实。常见系统是三类：

| 系统/路线 | 可检索内容 | 对本项目的启示 |
| --- | --- | --- |
| PubMed | 核心记录是 citation metadata、题名、摘要、MeSH 等字段；结果页链接到可用全文，但 PubMed 记录本身不包含论文全文 | 高覆盖的专业论文发现可以建立在题名/摘要/主题词之上 |
| SPECTER / SPECTER2 | 科学论文表示使用题名与摘要；SPECTER 论文明确把两者拼接成 document representation | 摘要级 dense scientific retrieval 是成熟、可复现的路线，不是残缺的临时方案 |
| Google Scholar | 支持抓取和索引可访问的 scholarly full text，但依赖网页/PDF 可抓取性 | 全文可以增强发现，但它不是一个覆盖一致、可直接冻结到本地实验的数据源 |
| Europe PMC | 同时覆盖 abstracts 和一部分可合法读取/复用的全文，并支持 section-level full-text search | 全文检索有价值，但覆盖与可识别 section 比例不均，必须单独建模 |
| OpenAlex | work search 可以查题名、摘要和有全文索引的 subset；也提供单独的 title-and-abstract search | 混合索引在大型发现系统中可行，但全文仍只是 subset，不代表本地 frozen corpus 应无条件混合 |

一手依据：

- [PubMed Help](https://pubmed.ncbi.nlm.nih.gov/help/) 说明 PubMed records 包含 citation information 和 abstracts，全文由 publisher/PMC 等外部来源链接提供。
- [SPECTER 论文](https://aclanthology.org/2020.acl-main.207.pdf) 明确用 paper title + abstract 构建 scientific document embedding；[SPECTER2 repository](https://github.com/allenai/SPECTER2) 也把输入论文表示为题名与摘要的拼接。
- [Google Scholar inclusion guidelines](https://scholar.google.com/intl/en/scholar/inclusion.html) 要求站点允许 crawler 访问全文才能进行 full-text indexing，说明覆盖依赖来源可访问性。
- [Europe PMC Help](https://europepmc.org/help) 区分 abstracts、可读取全文与可复用 OA subset，并说明 section-level coverage 随来源结构变化。
- [OpenAlex search documentation](https://help.openalex.org/api/searching/) 说明 work search 查询题名、摘要和 full-text subset，同时保留字段级检索。

## 全文是否一定提高效果

不一定。基于 TREC 2007 Genomics relevance judgments 的对照研究发现：把整篇全文当作一个 indexing unit，并没有稳定优于 abstract-only；把全文切成 paragraph-sized spans 后，才稳定优于摘要检索。见 [Is searching full text more effective than searching abstracts?](https://pmc.ncbi.nlm.nih.gov/articles/PMC2695361/)。

这说明真正有价值的变量不是“有没有全文”本身，而是：

- query 所需证据是否通常被摘要省略；
- 全文是否按 source-faithful、可回链的短 segments 检索；
- ranker 是否处理好长文档和 segment-count bias；
- 全文覆盖是否足够一致，不会让 availability 决定排名。

## 对 021 v1.1 的批准边界

批准：

- 12 个 cases 的 frozen corpus 只包含题名与 validated `publisher_abstract`；
- 所有 ranker 使用完全相同的 source text；
- 021 的结果用于选择 **abstract-level local paper ranker**；
- qrels 可以判断 paper relevance 和摘要 segment 是否提供直接证据。

不批准或不声称：

- 不把未批准的 PDF、publisher HTML、citation contexts 或生成摘要填入 corpus；
- 不用部分 paper 的全文与其他 paper 的摘要混跑后归因给 ranker；
- 不用这轮数据校准 full-text segmentation、multi-segment aggregation 或 full-text segment cap；
- 不声称摘要已经覆盖完整方法、实验细节、限制或负结果。

## 何时重新打开全文路线

只有下面条件同时具备，才启动独立 v2 comparison：

1. 真实 runtime 已确定需要全文级 evidence，而不只是 paper discovery；
2. official source、许可/复用边界、source bytes、provenance 和 content hashes 可冻结；
3. 在同一批 papers 上建立 paired `abstract-only` 与 `segmented-full-text` 输入，不能让 membership 或 availability 成为混杂变量；
4. segmentation 对所有 rankers 相同、可重放、能精确回链，并通过 length/segment-count bias fixtures；
5. 预注册 paper relevance、segment EvidenceHit、latency、memory 和 payload budget，再判断全文是否带来足以抵消复杂度的净收益。

在这些条件出现前，补全文会扩大数据工程和验证面，却不能更可靠地回答 021 当前的 ranker 选择问题。
