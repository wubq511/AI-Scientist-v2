# Local ranking formal holdout 得到 `inconclusive` 后的补救设计研究

日期：2026-08-31
适用范围：ticket 021 的 BM25 与 E5 两个已冻结 finalists；不重新调参，不进入下游实验阶段。

## 结论

当前 formal holdout 已经用完，不能再增加 judge、换聚合规则或根据已看到的 winner direction 重新解释它。这样做属于看过测试结果后再改变分析方法，会产生 adaptive overfitting；Dwork 等人的 reusable-holdout 工作说明，分析选择受已观察结果影响时，会出现虚假的泛化结论，而本项目没有预先部署可复用 holdout 机制。最简单可靠的处理是：把现有 holdout 永久降级为诊断证据，任何新的 winner 结论只来自新冻结、从未运行过的 topics/cases。来源：[Dwork et al., *The reusable holdout*, Science 2015](https://pubmed.ncbi.nlm.nih.gov/26250683/)。

本项目真正需要回答的不是“哪个排序器更像某个 LLM judge”，而是：哪一组检索结果能让**冻结的 ideation consumer** 产生更有用、可回链且不越界的研究证据。Robert 是决策 owner，但不是这里最合适的领域 relevance assessor；此前要求他做 12 张人工 utility card 仍把关键评测负担推给了缺少相应领域经验的人，不能作为默认补救方案。

因此，本研究的最终推荐改为 **AI-consumer-first 的 fresh paired evaluation**：

1. 冻结现有 BM25/E5 及全部参数，不再调旧 development 或 holdout；
2. 从仍未使用的 approved universe 中新建 `12 cases × 2 queries = 24 queries` 的 untouched batch；
3. 用冻结的真实 ideation consumer 把每个匿名 top-3 evidence payload 转成结构化中文 evidence memo，BM25/E5 只改变输入 evidence；
4. 用两个真正不同 provider/model family 的 blind pairwise evaluators 做 `A/B` 与 `B/A` 位置互换复核；只有跨 evaluator、跨位置一致的 choice 才计入 utility direction；
5. 用本地 validator 对每个 memo 的 paper identity、exact quote、citation coverage、越界来源和 schema 做 deterministic hard gates；AI preference 不能挽救 source-faithfulness failure；
6. 同时运行两个**只作诊断、不直接获选 production**的上界：`BM25 top-3 ∪ E5 top-3`（最多 6 篇）用于检查 complementary recall，输入长度允许时再加 full-corpus context ceiling，用于检查“top-3 排序”本身是否是错误瓶颈；
7. 若 BM25/E5 仍无材料性 operational-utility 差异，才按预注册的运维策略选 BM25。该结论只能写成“未证明 E5 的额外成本带来净效用”，不能写成 BM25 relevance superiority；若 union/full-corpus 明显胜过两者，则不能选 BM25 或 E5，而应重开 evidence budget/cascade 设计。

该方案把 Robert 的人工任务降为**审阅最终 decision record 并批准或拒绝推荐**，不要求他给论文打分，也不要求他完成 12 个盲选。若未来需要可发表的专家 topical-superiority 主张，再另行增加领域专家评测；它不是当前个人 ideation runtime 的必要 gate。

不推荐把现有 holdout 交给更多模型投票，也不推荐用外部 benchmark 或 citation recovery 的 winner 直接替代本地决策。它们能回答不同的辅助问题，但不能回答冻结 ideation consumer 在这个小型、已审批文献集合中的实际效用。

## 1. 已知事实与证据边界

[ticket 021](../wayfinder/ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md) 已记录：

- finalists 已冻结为 BM25 与 E5，二者均为 `title_weight=1`、`phrase_bonus=false`、`paper_cap=3`；
- formal holdout 只运行了一次，全部工程 gates 通过；
- judge-A 选择 BM25，judge-B 名义选择 E5，consensus 中 E5 的优势只有 `0.008299`；
- 结果违反预注册的 same-direction gate，所以合法结果是 `inconclusive`；
- judge-A=`kimi-k3`、judge-B=`deepseek-v4-flash`，本来就是不同 model families。换言之，当前失败不能简单归因于“两个 judge 实际是同一个模型”。

[v1.2 protocol](local-literature-ranking-comparison-protocol-v1.2.md) 与 [v1.2.1 provenance correction](local-literature-ranking-comparison-protocol-v1.2.1.md) 已预先禁止在这种结果下多数票、重跑、调 judge prompt 或生成以 same-direction 为前提的 Robert utility card。补救设计必须是一次新的、事前冻结的实验，而不是修改旧实验的判定标准。

LLM qrels 在 run-level system ordering 上可能与人工 qrels 高度相关，但这不能保证它能稳定区分两个接近的 finalists。NIST/UMBRELA 的研究报告在 TREC DL 2023 上得到自动与人工 nDCG@20 的 run-level Kendall `tau=0.890`，同时明确把该结果限定在粗粒度 system comparison，不能据此证明 individual-topic 或 near-best-system 判断可靠。来源：[Upadhyay et al., ICTIR 2025 / NIST](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=959054)。另一项直接比较人工与 LLM relevance assessments 的研究发现，自动评测会改变 system ordering，并提醒以 LLM 同时生成系统内容和评价内容存在 circularity 风险。来源：[Clarke & Dietz, 2024](https://arxiv.org/pdf/2412.17156)。这与当前“不同 judges 对接近 finalists 给出相反 winner”一致。

## 2. 先区分两个不同的评价目标

### 2.1 Topical relevance

问题是“这篇论文是否确实回答该 query，证据是否由题名/摘要支持”。它需要领域知识、明确 rubric 和可核查 span。领域专家或经少量专家 gold 校准的 AI judge 更适合回答这个问题。

### 2.2 Ideation-consumer operational utility

实际 runtime 中，retrieval payload 的直接消费者是 ideation model；Robert 负责定义任务、边界和最终批准，不会逐篇完成领域检索。因此产品问题应写成：“同一个冻结 consumer 在只替换 BM25/E5 evidence payload 时，哪一侧更稳定地产生 source-faithful、具体、互补且可用于后续 ideation 的 evidence memo？”

ICLERB 的核心发现正是：传统 semantic relevance 与文档对下游 LLM 的实际效用不是同一个构念，retriever 应按其是否改善冻结 consumer 的下游表现评估。来源：[Al Ghossein et al., *ICLERB*, 2024](https://arxiv.org/abs/2411.18947)。这不证明 AI 自评天然可靠；它只说明本项目此前把 pointwise qrels 当主终点，本身就没有直接测最终用途。

Thomas 等人的第一方 relevance 研究仍给出重要边界：真实 searcher feedback 是 personal preference 的最好 gold，未校准 LLM 不能冒充人类偏好。来源：[Thomas et al., SIGIR 2024](https://www.microsoft.com/en-us/research/wp-content/uploads/2023/09/LLMs_for_relevance_labelling__SIGIR_24_.pdf)。但当前目标不是发表“所有人都偏好哪个 ranker”，而是选择服务 AI ideation runtime 的工程配置。故本轮可以用跨 provider 的 AI-consumer operational evidence 作主信号，同时把结论严格限定到冻结 consumer、prompt、query 分布和 abstract-only corpus；不声称 human utility 或 expert topical truth。

Robert 不应再被要求独自给全部 paper-query pairs 做专家级 topical grades，也不应默认承担 12 次人工盲选。若他自愿抽查少量卡片，只能作为 veto/diagnostic，不作为 protocol 完成条件。

## 3. 补救方案比较

| 方案 | 实际回答的问题 | 成本与人工量 | 主要偏差/失败模式 | 是否需要新冻结 topics | 对 ticket 021 的定位 |
|---|---|---|---|---|---|
| 真正不同的 model-family panel | 多种 synthetic judge 对 topical rubric 的敏感性 | 2 个全量 judge + 第 3 个只裁分歧；人工可为 0 | shared prompt bias、模型训练数据重叠、模型对 1/2 边界定义不同；多数票会掩盖 construct instability | **需要**；旧 holdout 加 judge 是 post hoc | 仅作 topical-risk/sensitivity guard，不作 winner 多数票 |
| 少量领域专家 calibration | AI rubric 是否接近领域专家的 topical judgment | 推荐 24 个 judgments，按领域分给具备相应能力的专家；还需独立 calibration split | 专家之间也会分歧；单一专家/单一领域不能覆盖全部 cases | **需要独立 calibration topics**，之后还要 untouched evaluation topics | 最强的 human topical 校准方案；不能代替 consumer operational evaluation |
| First-party blind pairwise utility | 哪个 top-3 对 Robert 本人更有用 | 12 个匿名 A/B choices；约一次短评审 | Robert 不是跨领域 relevance 专家，且已明确不适合承担该人工量；小样本不能声称普遍 superiority | **需要** | 可选 veto/diagnostic，不再作为默认 primary |
| 下游 ideation-consumer end-to-end | 排序差异是否真的改变冻结 consumer 的 evidence artifact | 推荐 24 queries 的 paired runs；需要跨 provider blind pairwise evaluation 与本地引用 validator | consumer 随机性、模型先验与 evaluator bias；必须位置互换、跨家族一致并严格限域 | **需要**，且须事前冻结 consumer/prompt/config | 最贴近实际 runtime，推荐作为 primary |
| Union / full-corpus context ceiling | 两个 ranker 的互补结果或全部摘要是否明显优于任一 top-3 | union 每 query 最多 6 篇；full corpus 当前样本最大约 7,457 英文词，fresh batch 仍需 preflight | 改变 evidence budget、可能触发 long-context dilution；不能事后直接升为 production winner | **需要** | 只作诊断；明显获胜时说明问题在 cap/cascade，而非 BM25/E5 二选一 |
| Known-item / citation-context task | 能否找回一篇已知被引用的论文 | 可自动生成 positives，人工接近 0 | observed citation 不是唯一 relevant paper；citation bias；可能偏爱 citation-trained dense model | 不用本地 topics，但要独立公开数据 | 只检验检索机制/回链能力，不回答开放式 workshop utility |
| 外部科学检索 benchmark | 在另一个科学检索分布上的一般能力 | 无本地人工 qrels；需适配 corpus/metric，计算成本中等到高 | corpus 数量级、领域、query 形式与本项目 `3–36` 篇 approved local corpus 不同 | 不需要本地 topics | 作为外部有效性支持，不能替代本地 winner |

### 3.1 不应把“更多 model-family votes”当补救

JudgeBlender 证明，多种不同模型的 panel 在某些 TREC 设置中能改善 system-ranking correlation；其三模型 majority variant 在所测设置中优于单模型，但论文也显示没有一种 judge aggregation 在所有指标上都最好。来源：[JudgeBlender, SIGIR 2024](https://bhaskar-mitra.github.io/files/3701716.3715536.pdf)。

本项目已满足“不同 model families”这一最低条件，却仍发生 winner reversal。这是重要的失败证据：问题不是缺一张选票，而是 synthetic topical metric 对两个接近 finalists 不稳定。在旧 holdout 上增加第三、第四 judge 再投票，会利用已知分歧改变规则；在新 topics 上使用跨 provider/model-family judges是可行的，但它们应输出 sensitivity range 与 catastrophic misses，而不是把多数票冒充个人效用。

若采用 AI panel，每个 judge 应在独立隔离 task 中工作，只收到同一版本的 query、候选文献、rubric 和允许证据字段；不得收到 ranker 身份、排名结果、其他 judge labels/rationales 或旧 holdout winner。第三 judge 只收到原始 disputed items。隔离能减少直接信息泄漏，但不能创造独立的人类真值。

### 3.2 少量专家 calibration 应与新 holdout 分开

如果要校准 judge prompt/rubric，专家标签不能来自最终 evaluation split，因为看完标签后修改 rubric 又会污染 evaluation。推荐先建立 calibration-only split，并冻结如下小样本：

- 2 个此前未使用的 cases、每 case 2 个 queries；
- 每 query 6 个 paper-query pairs，共 24 个 judgments；
- 每 query 覆盖 AI judges 一致认为 relevant、发生分歧/低置信的 boundary items，以及按固定 seed 随机抽取的 items；
- 专家只看 query、题名、摘要和可回链证据，不看 ranker、rank、其他 labels；
- 专家反馈只用于一次性澄清 rubric/示例，随后冻结 judge protocol；最终 winner 仍在另一个 untouched batch 上决定。

“24”不是文献给出的通用统计阈值，而是本项目的最小工程预算：每个 query 都需要覆盖，因为 query interpretation error 会在同一 query 的 papers 内成簇出现；同时它把专家负担从全部 336 个 judgments 降到 24 个。若 cases 跨多个专业领域，应把 24 个 judgments 按领域分给相应专家，不能让一个不具备领域能力的人替所有领域背书。

LARA 展示了用 LLM probability 主动挑选最有价值的人工 labels，再校准其余 predictions 的方法，并在 TREC-7/8、Robust04、TREC-COVID 上验证；但它依赖稳定可获得的 label probabilities 和更完整的校准管线。来源：[LARA, SIGIR 2025](https://arxiv.org/pdf/2411.06877)。对本项目总计数百项的小规模 comparison，完整 active-learning 系统属于过度工程；借用其原则、优先让专家看 boundary/disagreement items 即可。

### 3.3 First-party blind pairwise 是可选的人类信号，不是默认 gate

若 Robert 自愿提供 first-party 信号，新 batch 中每个 query 可只展示两个匿名 top-3 列表，左右顺序用预先封存的固定 seed 随机化。选项应为：

- 左侧更有用；
- 右侧更有用；
- 两侧同样有用；
- 两侧都无用；
- 信息不足/看不懂。

界面不得出现 `BM25`、`E5`、分数、synthetic qrels、旧 holdout 结论或 arm 的稳定位置。Robert 不需要判断“论文在学术上是否正确”，只判断哪组证据更帮助自己的任务，并可查看题名、完整摘要、直接证据 span 和 paper identity。这样把人工量从 336 个绝对 grades 降为 12 个直接选择。

若实际执行该可选分支，应事前冻结一个**操作性 effect-size rule**，而不是事后选择最有利的统计口径：至少 8 个 query 给出可判别的单边选择，且某 arm 至少取得 `2/3` 的可判别选择，才称为观察到材料性的 first-party direction。该规则是本项目的产品决策阈值，不是学术显著性结论；样本太小，不能把它写成普遍的检索 superiority。

若选择执行但没有 arm 达到该门槛：

- 对“哪一个更受 Robert 偏好”保持 `inconclusive`；
- 允许按**预注册的部署策略**选择 BM25，因为现有 evidence 未证明 E5 的个人效用增益足以抵消其额外模型、环境、内存和启动成本；
- Resolution 必须写成“在未观察到材料性 utility 差异时采用轻量默认”，不能写成“BM25 relevance 更高”。

### 3.4 End-to-end 最接近最终价值，应作为本项目下一轮 primary

TREC RAG 把 retrieval、augmented generation 与 full RAG 分开评测，说明 retrieval relevance 与最终生成质量是不同构件，不能互相替代。来源：[TREC 2024 RAG Track proceedings](https://trec.nist.gov/pubs/trec33/index.html)、[TREC 2025 RAG overview](https://trec.nist.gov/pubs/trec34/papers/Overview_rag.pdf)。

下一轮应在**运行任何新结果前**预注册：固定 ideation consumer 的 model、prompt、reasoning/completion config、输入 budget 和输出 schema，只交换 BM25/E5 payload；输出统一为结构化中文 evidence memo，每条 claim 必须绑定 `paper_id` 与 exact source quote。工程 validator 检查 schema、quote byte-exactness、paper/corpus 边界、citation coverage 和重复 identity。推荐使用 `12 cases × 2 queries = 24 queries`；若 provider 不能保证采样级可复现，应对每个 arm 做 paired repeats，并把重复间方差写入结果。

匿名 memo 由两个不同 provider/model-family evaluators 独立做 pairwise comparison；每一对同时以 `A/B` 与 `B/A` 两种位置展示，position swap 后翻转的判断作废。只有两个 evaluator 都给出同一 content winner、且位置互换一致，才把该 query 计为可判别。这样仍是 synthetic operational evidence，但比 pointwise paper grade 更直接测量实际消费结果，也显式拒绝 position bias 和单一 judge preference。

该 phase 会产生真实 provider 成本。执行前必须等 ideation consumer 的 exact configuration 冻结，给出调用数、token 与最坏成本估算，并按现有 provider/canary 合同单独获得批准；本研究报告本身不授权 API 调用。

该阶段真正回答“检索器是否改善 ideation consumer”，但会混入 consumer stochasticity，所以必须 paired、重复并严格限域。它是一个全新的 fresh evaluation，不解释或重写旧 holdout。

### 3.5 Union 与 full-corpus ceiling 能检验是否问错了二选一问题

旧结果显示 BM25/E5 各自能找回对方 top-5 缺失的 grade≥2 papers；RRF 排序没有把这种互补性转化为更高 qrels metric，但这不等于“让 consumer 看到两侧 union”也无效。新 protocol 应将去重后的 `BM25 top-3 ∪ E5 top-3` 作为 diagnostic context，最多 6 篇，保持 source-faithful segments；它不参与 BM25/E5 winner vote，只回答固定 top-3 是否过早丢弃互补证据。

当前 12 cases 的全部摘要规模约为每 case 468–7,457 个 whitespace words。若 fresh case 的 exact consumer-tokenizer preflight 通过，还可增加 stable-paper-id 顺序的 full-corpus context ceiling。这个 control 不是合规 production ranker；它只估计“理想地不丢任何候选时”能提高多少 downstream utility。若 union 或 full-corpus 明显胜过两个 top-3 arms，下一步应重新校准 evidence budget/cascade，而不是为了关闭 ticket 强选 BM25/E5。

### 3.6 Known-item 与 citation-context 只能做诊断

Citation recommendation 常把真实 citation context 作为 query、已出现的 citation 作为 positive，并以 MRR/F1 等评估找回能力。来源：[Bhagavatula et al., NAACL 2018](https://aclanthology.org/N18-1022/)。S2ORC 则提供 citation mention 到论文对象的结构化链接，可用于构造此类任务。来源：[Lo et al., S2ORC](https://arxiv.org/abs/1911.02782)。

这种任务便宜、客观、无需 Robert 给 qrels，但“被作者引用”不等于“唯一相关”，也不等于“对当前 workshop query 有用”；citation practices 还包含领域、年代和作者网络偏差。更重要的是，本项目禁止从 target-derived text 构造会泄漏答案的正式 query。因此它只能在独立公开数据上测试 known-item recovery，不能拿来决定本地开放式 query 的 winner。

### 3.7 外部 benchmark 只能提供外部有效性

最接近本项目任务表面的公开 benchmark 是 LitSearch：它包含 597 个现实的科学文献检索 queries，目标是直接找相关论文。来源：[LitSearch](https://arxiv.org/abs/2407.18940)。BEIR 覆盖 18 个 retrieval datasets，包括 TREC-COVID、NFCorpus、SciFact 等科学或生物医学任务，适合检查 lexical/dense 方法的一般稳健性。来源：[BEIR paper](https://openreview.net/pdf?id=wCu6T5xFjeJ)、[BEIR official repository](https://github.com/beir-cellar/beir)。SciRepEval 则涵盖 scientific document 的 classification、regression、ranking 和 search 等 24 项任务，并显示模型很难跨任务格式泛化。来源：[SciRepEval, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.338/)。

这些 benchmark 的 corpus 常比本项目每 case `3–36` 篇 approved papers 大几个数量级，query 领域、candidate generation、全文可用性和指标也不同。它们能发现明显的 mechanism failure，不能证明在本地小 corpus 中哪个 top-3 更有用。若运行，只能固定现有 BM25/E5，不调参，预先选择一个最接近的 benchmark（优先 LitSearch），并把结果列为 supporting evidence；外部 winner 与本地 consumer operational utility 冲突时，应报告 distribution/construct conflict，而不是覆盖本地结果。

## 4. 是否必须新冻结 topics/cases

答案是必须。凡是会参与 winner 选择的 evidence，都不能再来自当前 formal holdout。

推荐准备：

1. **fresh operational-evaluation split**：12 个新 cases、24 个新 queries，用于冻结 consumer 的 paired evaluation；
2. **可选 expert calibration split**：只有项目以后要主张 expert topical superiority 时，才另取 2 个新 cases、4 个新 queries 做 rubric calibration；不能与 operational evaluation 重叠。

新 cases 应来自此前未使用的 approved universe，继续覆盖原协议的 corpus-size strata 和至少两个领域。query author 不能看到 BM25/E5 outputs、旧 holdout labels、scores 或 winner direction；先冻结 query、case manifest、hash、rubric 和 decision rule，再运行任一 ranker。如果没有足够的全新 approved cases，应接受 ticket 暂时 `inconclusive`，不能用近义改写旧 query 冒充新 holdout。

旧 holdout 仍有价值，但用途只能是：证明两个 synthetic judges 对 near-tied finalists 不稳定、审计工程 gates、设计未来 failure taxonomy。它不能再贡献 winner vote、阈值选择或 prompt tuning。

## 5. 最小推荐 protocol（future revision）

### Phase 0：冻结边界

- 将旧 holdout 标记为 `spent_diagnostic_only`，保存全部 hashes 与原始证据；
- 保留 BM25/E5 的 exact implementation、依赖、参数、segmentation、`paper_cap=3`；
- 禁止重新打开 development tuning、RRF、title weight、phrase bonus 或 cap 搜索；
- 在生成结果前冻结新 cases/queries、匿名化 seed、输出模板、评价选项和下述 decision rule。

### Phase 1：冻结 consumer 与评测器

- 使用项目最终会采用的 ideation consumer；必须先冻结 exact provider/model、prompt、reasoning/completion config、输入预算、输出 schema 与失败行为；
- 输出为中文 evidence memo；每条 claim 都必须引用一个 model-visible `paper_id` 和 exact source quote；禁止 consumer 使用 corpus 外来源补答案；
- 冻结两个不同 provider/model-family evaluators、pairwise rubric、`A/B` 与 `B/A` position-swap 规则；evaluator 看不到 ranker identity、旧 qrels、scores 或旧 winner；
- 在任何真实调用前给出调用量、token 与最坏成本估算，并按 provider/canary 合同取得该批授权。

### Phase 2：fresh paired evaluation

- 12 个未用 cases，每 case 2 个 query，共 24 queries；继续分层覆盖 small/medium/large corpus 与多个领域；
- BM25/E5 各运行一次 deterministic retrieval；全部现有工程、隔离、资源和回链 gates 保持 fail closed；
- consumer 对两个匿名 payload 做相同次数 paired runs；若 API 无确定性保证，至少做预注册 repeats，禁止看到结果后只重跑不利一侧；
- 两个 evaluators 对匿名 evidence memos 做双位置 pairwise judgments；position-inconsistent 或 evaluator-disagreed query 记为不可判别，不以第三票强行决胜；
- 本地 validator 对每份 memo 的 schema、allowed paper IDs、exact quotes、citation coverage 和 source boundary 出具 hash-bound verdict；
- 同步运行 union context diagnostic；fresh input 通过 exact token preflight 时再运行 full-corpus ceiling。二者不直接参与 BM25/E5 winner vote。

### Phase 3：预注册 decision

1. 若任一工程/隔离/回链 gate 失败：该 arm 不可部署，AI preference 不能挽救；
2. 至少 16/24 queries 必须形成跨 evaluator、跨位置一致的可判别判断；若一个 arm 在这些 query 中取得至少 `2/3` wins，且不存在被两位 evaluator 一致认定的系统性 catastrophic omission，才推荐为冻结 consumer 的 operational winner；
3. 若未达到上述门槛：结果记为 `no demonstrated operational-utility difference`，按预注册 parsimony policy 采用 BM25 工程默认，但不得声称 relevance superiority；
4. 若 union/full-corpus diagnostic 显著优于两个 top-3 arms，或大量 memo 都无用：不是 BM25/E5 平局，而是 evidence budget/cascade/input contract 失败；本 ticket 不应强选 winner，应另写 revision；
5. 若项目需要可发表的 human/expert superiority，以上 AI-consumer 证据不够，必须另建 expert-judged fresh evaluation。

### Phase 4：可选人类或外部诊断

Robert 可自愿抽查少量匿名 cards，结果只作 veto/diagnostic，不是完成条件。Known-item/citation tasks、LitSearch/BEIR 与可选 expert calibration 都必须使用独立数据并事前登记用途；不得追加为旧 holdout 的事后 tie-break。

## 6. 最终判断

- **能回答本项目实际问题的推荐方案**：fresh topics 上的 paired ideation-consumer evaluation，加跨 provider/position-stable pairwise evaluation 与 deterministic source-faithfulness hard gates；Robert 不承担论文打分或 12 次盲选。
- **能检查是否问错了二选一问题的诊断**：union context 与可行时的 full-corpus ceiling；若它们明显更好，应改 evidence budget/cascade，而不是强选 BM25/E5。
- **能改善 human topical validity 的补充**：独立 calibration split 上约 24 个领域专家 judgments；只有要做专家/普适主张时才需要。
- **不应重复的方案**：在已用 holdout 上继续增加 LLM judge 或改为多数票。即使换成更多模型家族，也只能产生新的 post-hoc aggregation。
- **最接近最终产品价值且应优先的方案**：paired downstream ideation-consumer evaluation；它有 API 成本和随机性，因此必须先冻结配置、估价、授权和 repeats。
- **仅辅助诊断**：known-item/citation-context tasks、LitSearch、BEIR、SciRepEval。
- **新冻结 topics/cases 是必要条件**：任何参与 winner 决策的 evidence 都必须来自未看过、未运行过的新数据；当前 holdout 永久只读、只作诊断。

这一路径避免让 Robert 承担 336 个专家级 qrels 或 12 次人工盲选，也不把 AI 多数票伪装成人类真值。它直接测量冻结 AI consumer 的实际产物，把 exact quote/corpus boundary 交给 deterministic validator，把主观 utility 限定为跨 provider、跨位置一致的 synthetic operational signal；没有观察到材料性收益时，才以明确的成本策略选择较轻方案。
