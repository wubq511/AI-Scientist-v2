# Local ranking v1.4：fresh direct-payload evaluation 对抗性审查

日期：2026-08-31
适用范围：Wayfinder ticket 021；已冻结的 BM25 与 E5 finalists；旧 formal holdout 得到
`inconclusive` 后的新一轮证据设计。
状态：**protocol review complete / implementation pass；尚未授权任何真实模型调用**

## 结论

当前方向可以继续，但现有 future-revision 草案**不能原样成为正式协议**。它做对了四件事：不复用
已经看过的 holdout、冻结 BM25/E5、直接观察下游 evidence consumer、用跨模型与位置互换降低单一
LLM judge 偏差。它仍有六个会使结论失真的缺口：

1. 所谓 `end-to-end ideation-consumer` 实际只测“固定 query 后的一次 evidence memo 消费”，没有测
   ideation model 自己生成 query、反思、再次检索和 `FinalizeIdea` 的完整闭环；必须缩小构念名称，
   不能冒充最终 idea quality。
2. `24 queries` 来自 `12 cases × 2 queries`，两个 query 共享 Workshop 与 corpus，不是 24 个独立
   实验单位。原拟的“至少 16/24 可判别且其中 2/3 获胜”既忽略聚类，也没有足够的不确定性约束。
3. 冻结 consumer 仍可能随机；每个 arm/query 只生成一份 memo 会把一次偶然采样误当 ranker 效果。
4. byte-exact quote validator 只能证明引文来自允许文本，不能证明 claim 被引文蕴含、没有歪曲或
   覆盖完整。`source provenance` 与 `semantic support` 必须分成 hard/soft 两层。
5. “本地隔离 agent 只读 bundle”目前只是 prompt 约束。如果 agent 仍有 repo、shell 或网络工具，
   就不能声称 judge isolation 已被强制。必须使用 tool-less/stateless 调用，或能实际限制 filesystem
   与 network 的执行边界。
6. `union top-6` 与 full-corpus ceiling 改变了 evidence budget；若拿它们直接阻断 BM25/E5 选择，
   却没有 matched top-6 controls 和冻结阈值，就无法区分“互补性”与“只是给了更多文本”。

进一步删去不必要的中间层后，本审查推荐的 v1.4 primary 是：**两个隔离 evaluator 直接盲评原始
BM25/E5 top-3 payload sets，不再先调用第三个 consumer 生成 evidence memo**。这能删除尚未冻结的
consumer config、memo sampling noise、claim/quote 二次失真和大量付费调用。它回答的是 set-level
evidence utility，不是完整 end-to-end ideation quality。

因此本审查给出 **conditional pass**：可以立即实现 v1.4 的文档、schema、sampler、validators、
统计器和旧数据 dry-run；但在 evaluator 隔离方式、fresh sampling 与下述 E5 非对称 promotion rule
全部 hash-freeze 前，不能抽取正式 fresh cases，更不能开始正式 judgments。

## 1. 审查方法与证据等级

本文使用三个明确标签：

- **Confirmed**：仓库 artifact/contract 或一手论文直接支持的事实；
- **Inference**：从已确认事实推导、但尚未由本项目新实验验证的判断；
- **Decision**：为 ticket 021 选择的可执行规则；这是预注册产品决策，不伪装成行业标准。

审阅的项目材料包括：

- [v1.1 基础协议](../prototypes/local-literature-ranking-comparison-protocol.md)、
  [v1.2 AI-qrels overlay](../prototypes/local-literature-ranking-comparison-protocol-v1.2.md)、
  [v1.2.1 provenance correction](../prototypes/local-literature-ranking-comparison-protocol-v1.2.1.md)
  与 [v1.3 Windows 执行补充](../prototypes/local-literature-ranking-comparison-protocol-v1.3.md)；
- [formal holdout 后的补救设计](../prototypes/local-ranking-inconclusive-next-step-research.md)；
- [ticket 021](../wayfinder/ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md)、
  [Scoped Literature Retriever contract](../wayfinder/ideation-pipeline/tickets/020-define-the-scoped-retriever-contract.md)
  与 [safe ideation entry](../wayfinder/ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md)；
- [正式输入准备证据](../prototypes/local-ranking-input-preparation.md) 与 2026-08-31 session log。

外部证据只采用论文原文、正式 proceedings、NIST/TREC 或作者机构页面，见文末来源。

## 2. 已确认的当前边界

### 2.1 旧 holdout 已经用完

**Confirmed**：旧 holdout 的 A/B/consensus winner direction 已被 controller 读取，并据此提出了
新的 consumer evaluation、judge panel、position swap 和 decision rule。Dwork 等人的 adaptive
data analysis 工作说明，分析方法由同一 holdout 的既有结果驱动时，普通 holdout 的泛化保证会
失效；安全复用需要专门机制，本项目没有部署这种机制（[Science 2015](https://pubmed.ncbi.nlm.nih.gov/26250683/)，
[NeurIPS 2015 full paper](https://proceedings.neurips.cc/paper_files/paper/2015/file/bad5f33780c42f2588878a9d07405083-Paper.pdf)）。

**Decision**：旧 development 与旧 holdout 全部标为 `spent_diagnostic_only`。它们可以用于 prompt、
schema、validator、统计器和失败恢复 dry-run，但不能贡献新 winner vote、阈值选择或正式效果估计。

### 2.2 “222 个未使用 cases”不等于“222 个已批准 cases”

**Confirmed**：现有材料支持“234 个 eligible candidates 中用了 12 个，剩余 222 个未进入旧实验”；
但 immutable approval 只绑定了旧的 12 个 Workshop/corpus bundles。把剩余集合称为 `approved universe`
不准确。

**Decision**：fresh batch 必须重新经过 deterministic selection、Workshop derivation/validation、
abstract-only corpus validation、semantic approval、query authoring、length preflight 和 formal-input
materialization。未完成这些步骤的 case 只能叫 `unused eligible candidate`。

### 2.3 finalists 与工程边界可以继续冻结

**Confirmed**：BM25 与 E5 的实现、参数、segmentation、`paper_cap=3`、CPU FP32 reference path、
Windows bulk executor 和 canonical payload 已经冻结并通过工程 gates。旧实验的失败是 evaluation
direction 不稳定，不是 scorer 或 Windows runtime 失败。

**Decision**：v1.4 不重开 scorer、title weight、phrase、RRF、cap 或依赖搜索。fresh evidence 只替换
case/query 与 downstream measurement；任何 ranker 参数变化必须另起 revision 和另一批 untouched data。

## 3. 评测构念：方向正确，但必须降级“end-to-end”表述

TREC RAG 把 retrieval、augmented generation 和 full RAG 分层评测，并分别检查 relevance、response
completeness 与 attribution；这说明 retrieval relevance 和生成结果不是同一个构念
（[TREC 2025 RAG overview](https://trec.nist.gov/pubs/trec34/papers/Overview_rag.pdf)）。ICLERB 也把
retriever 按其对冻结 LLM 下游任务的效用进行比较，而不是假定 semantic relevance 等于 downstream
utility（[ICLERB](https://arxiv.org/abs/2411.18947)）。

**Confirmed**：本项目真实 runtime 中，query 是 ideation model 的 tool input，模型可以在反思循环中
再次检索；当前 v1.4 草案却使用预先写好的 broad/focused query，再让一个 consumer 把 top-3 payload
写成 evidence memo。

**Inference**：这个受控实验比 pointwise synthetic qrels 更接近实际用途，也更容易把差异归因给
ranker；但它只证明“固定 query、固定 top-3 输入对固定 memo consumer 的影响”，不能证明整个 ideation
agent 的最终想法更好。

**Decision**：primary construct 正式命名为：

> `blind setwise top-3 evidence utility for AI ideation`

正式 evaluator 直接看到 `query + anonymous left/right top-3 titles + exact Retrieval Segments`，判断哪一
个 evidence set 更能帮助 AI ideation：是否有直接支持、互补覆盖、具体机制/限制以及明显遗漏。它不看
ranker identity、score 或旧 qrels。这个 setwise pairwise task 不等于旧的 pointwise paper grades：
它直接比较相同 model-visible budget 下的整组证据，也不要求先生成二次摘要。

允许的结论是“在本批 frozen cases/queries、abstract-only corpus 和 top-3 budget 下，哪个 ranker 的
原始 evidence set 被两个冻结 AI evaluators 跨位置一致判断为更有用”。禁止写成 human preference、
expert topical truth、完整 ideation quality 或普适 retrieval superiority。真正的 downstream consumer
或 end-to-end 结论必须等安全 ideation runtime 与最终 consumer config 落地后，用完整 tool loop 的
独立 canary 验证；不再用它阻塞 ticket 021。

## 4. LLM evaluator：位置互换必要，但不充分

### 4.1 已知偏差

**Confirmed**：LLM pairwise judges 有 position、verbosity 和 self-enhancement bias；MT-Bench 工作明确
报告这些限制（[Zheng et al.](https://arxiv.org/abs/2306.05685)）。ACL 2024 的受控实验显示，仅改变
候选顺序就可能显著改变结果（[Wang et al.](https://aclanthology.org/2024.acl-long.511/)）。同一模型
作为生成者与评估者还可能出现 self-preference；NeurIPS 2024 给出了 self-recognition 与
self-preference 的实验关联（[Panickssery et al.](https://proceedings.neurips.cc/paper_files/paper/2024/hash/7f1f0218e45f5414c79c0679633e47bc-Abstract-Conference.html)）。

多模型 panel 通常优于单一 judge，但它降低的是部分 model-family bias，不会自动产生 human gold；PoLL
在多个数据集上显示 diverse-family panel 的收益，结论仍依赖其具体任务和 panel
（[Verga et al.](https://openreview.net/pdf?id=6AjeDjlg3d)）。搜索 relevance 的一手研究还发现，LLM
对 prompt 的简单改写会出现不可预测差异，因此高质量 gold/calibration 仍重要
（[Thomas et al., SIGIR 2024](https://www.microsoft.com/en-us/research/uploads/prod/2023/09/LLMs_for_relevance_labelling__SIGIR_24_.pdf)）。

### 4.2 本项目可接受的最小 judge panel

**Decision**：Robert 提供的 `kimi-k3` 与 `deepseek-v4-flash` 可以作为最低双模型 panel，但要记录：

- 它们是两个 model families；若都经 Kimi Code 编排，不能写成 two-provider independence；
- 相对于未来可能使用的 `deepseek-v4-pro` ideation consumer，DeepSeek evaluator 仍属于同 family
  sensitivity，不是独立 gold；
- 两个 judge 的一致是必要 gate，不是两份独立统计样本，也不能证明判断正确。

每个模型使用两个 fresh sessions：orientation-1 和逐 item 完全镜像的 orientation-2。每个 query 的
left/right mapping 由冻结 seed 独立决定，整体尽量平衡；禁止一个 bundle 中所有 BM25 固定为 A。
第二个 bundle 只能交换 sides，不能改 rubric、标点、字段顺序、item order 或其他上下文。item order
按 evaluator-specific seed 冻结，因此同一 evaluator 的两个 orientations 顺序相同、两个 evaluator
之间顺序不同；四个 session 的原始输出全部保留。左右分配在每个 `stratum × query kind` 区块内平衡，
避免 position 与 corpus size/query kind 混杂。

每个 judge 必须输出 closed schema：

- `winner ∈ {left,right,tie,both_bad}`；
- 两侧各自的 `direct_support`、`query_usefulness`、`coverage_diversity`、`specificity`；
- `catastrophic_omission_side ∈ {left,right,neither}`；
- 简短 rationale，只能引用当前 payload 中的 paper/segment IDs。

同一模型两种 orientation 映射回内容后 `winner` direction 不一致，该 query 对该 judge 为
`position_unstable`。量表分数差异完整保留并作为稳定性诊断，但不要求四个分数字段逐项完全一致；否则
轻微量表噪声会把同方向判断错误地丢弃。两个模型各自 position-stable、但 winner direction 不一致时，
该 query 为 `cross_model_unresolved`；不增加第三票，不多数表决。`catastrophic_omission` 只有在两个模型、
两个位置四次映射后都指向同一候选时才计入 systematic omission gate。position swap 同时吸收位置偏差
和部分 sampling noise，但不能把两者区分，也不等于完整的重复稳定性实验。

### 4.3 隔离必须由执行边界强制

**Decision**：正式 judge bundle 和路径中不能出现 `BM25`、`E5`、旧 winner、scores、qrels、另一
judge 输出或 mapping key。mapping key 由 controller seal，直到四个 outputs 均通过 hash/schema
validation 后才解封。

正式 evaluator 必须满足以下二选一：

1. stateless/tool-less model call，只把 exact bundle bytes 放入请求；或
2. 操作系统/agent sandbox 只挂载一个自包含 input bundle 与独占 output directory，禁用 repo、shell、
   network 和其他会话历史。

仅在 prompt 中写“不要读取仓库”不构成 isolation evidence。若本地 agent 无法强制该边界，结果只能
标 `context-minimized`，不能进入正式 winner gate；应改用 tool-less 调用。四个输出目录必须互斥，
避免再次发生 shared-path overwrite。

## 5. Source faithfulness：确定性 validator 的能力边界

ALCE 将生成质量、citation correctness 和 citation completeness 分开评估，并显示“生成中有 citation”
不代表 citation support 完整（[Gao et al., EMNLP 2023](https://aclanthology.org/2023.emnlp-main.398/)）。

**Confirmed**：`paper_id` allowlist、segment identity、segment text、offset/hash 与 top-3 payload
identity 都能由本地 validator 确定性证明。

**Inference**：直接展示原始 payload 删除了 consumer-generated claim，因此不会出现“正确 quote 支撑
错误 memo claim”的二次失真；但 validator 仍不能决定某个原始 segment 对 query 是否有语义帮助。

**Decision**：v1.4 把两层证据分开：

1. **Deterministic hard gates**：left/right 都必须是 frozen ranker 的 exact canonical top-3 payload；
   paper/segment membership、text、offset/hash 与 budget 全部匹配；无 score、ranker name、外部来源或
   额外摘要。失败不得由 judge preference 挽救。
2. **Semantic judge fields**：segment 是否直接支持 query、集合是否具体/互补、是否存在明显遗漏。
   它们是 synthetic judgments，必须保留 disagreement，不能写成 deterministic proof。

直接 payload 方案不再存在 consumer memo schema/quote repair。retriever boundary/determinism 失败会
淘汰 ranker；judge JSON invalid 只允许同一 prompt/config 事前冻结的一次 fresh-session retry，仍失败
则整个 evaluator orientation 不完整，禁止人工修文或只补某些不利 items。

## 6. 样本量、聚类与不确定性

### 6.1 现有 `16/24 + 2/3` 规则不能支撑严谨 winner

**Confirmed**：两个 query 共享一个 case 的 Workshop/corpus，实验单位具有层级结构。NIST 关于 topic
set size 的研究指出，IR 评价误差取决于 topic 数和观察到的效果差异，topic 数不能脱离效果量选择
（[Voorhees & Buckley](https://www.nist.gov/publications/effect-topic-set-size-retrieval-experiment-error)）。
NIST UMBRELA 的一手结果也展示了 run-level Kendall `tau=0.890` 与 per-topic `tau=0.553` 的明显差距，
说明较好的整体 system ordering 不等于每个 topic 稳定
（[NIST/UMBRELA](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=959054)）。

**Inference**：若最低只有 16 个 resolved query，`2/3` 即至少 11 wins；在把 query 错当独立 Bernoulli
试验的宽松前提下，11/16 的 exact sign-test 单侧 `p≈0.105`、双侧 `p≈0.210`。因此它最多是产品启发式，
不是不确定性受控的 winner evidence。

### 6.2 采用 case-level paired randomization

IR 文献比较了 paired tests，并强调检验应对应所报告的 statistic；randomization/bootstrap/t-test 在
经典 TREC 设置中表现接近，而简化的 sign/Wilcoxon 可能行为较差
（[Smucker, Allan & Carterette](https://ciir-publications.cs.umass.edu/getpdf.php?id=744)）。NLP 的正式
指南同样要求根据配对结构和 metric 选择 test（[Dror et al., ACL 2018](https://aclanthology.org/P18-1128/)）。

**Decision**：统计单位固定为 12 个 cases，query 只是 case 内两个重复测量：

1. 映射四次 judge 后，每 query 得到 `s_q ∈ {-1,0,+1,unresolved}`；正号固定代表 E5，负号代表
   BM25，`tie/both_bad=0`。`unresolved` 在 effect estimator 中保守记 0，但必须单独报告，不能称 tie。
2. 每 case 的 `d_i=(s_broad+s_focused)/2`；primary effect 为
   `Δ=(1/12) * Σ d_i`，范围 `[-1,1]`。
3. primary uncertainty 使用 exact case-level paired sign-flip randomization：枚举 `2^12=4096` 个
   `ε_i∈{-1,+1}`。E5 promotion 的 primary test 固定为
   `mean(ε_i d_i) >= Δ_observed` 的 one-sided tail；同时计算
   `|mean(ε_i d_i)| >= |Δ_observed|` 的 two-sided descriptive p-value。不做多次中途查看。
4. 另以固定 seed 做 case-cluster bootstrap 95% CI 作为描述性不确定性；由于只有 12 clusters，CI
   不能用于宣称小效果或 equivalence。
5. query-level win/tie/loss、broad/focused、small/medium/large strata 和两 judges 的结果全部展示，
   但不再把 24 query 当 24 个独立样本。

### 6.3 E5 非对称 promotion gate

**Decision**：本 ticket 的工程问题不是对称地寻找“谁更强”，而是：E5 的额外模型、环境、内存和冷启动
成本是否换来足够大的 setwise utility。BM25 是较轻 reference/default；证明责任在 E5。这个非对称
loss function 必须在 fresh data 前预注册，不能看结果后采用。

只有同时满足以下条件，E5 才从 BM25 default 获得 promotion：

- retrieval 与 deterministic source-boundary gates 全部通过；
- 至少 `18/24` queries 跨两模型、跨两位置可判别，且每个 corpus-size stratum 至少 `5/8` 可判别；
- `Δ >= 1/3`，即全体 24 queries 上至少约 8 个 E5 净 stable-win equivalents；
- 预注册的 exact case-level **one-sided** randomization `p <= 0.05`；two-sided p 同时报告，但不作为
  产品 promotion gate；
- broad/focused 与三个 corpus-size strata 的 point estimate 不出现材料性反向；
- E5 没有两位 judges 跨位置一致确认的新增 systematic catastrophic omission。

该门槛故意只允许“大且跨 case 稳定”的 E5 收益通过。若 E5 不通过，不需要反向证明 BM25 科学上更强；
结论是 `E5 material utility gain not demonstrated`，按已冻结 loss function 采用 BM25 工程默认。
只有 BM25 也以同样 effect/uncertainty 标准出现强反向证据时，报告才可额外描述 BM25 setwise direction，
但部署决策不依赖这项反向检验。Resolution 必须把默认选择标为 **parsimony deployment choice**，不能
标 relevance/utility scientific winner。

12 cases 只在这个非对称、只晋升大效果的工程 gate 下是合理最小规模：它有意接受“中小但真实的 E5
收益可能检不出”的 false-negative 风险，以避免为不确定收益引入额外 runtime 成本。它不能证明
equivalence，也不支持对其他用户、领域或完整 ideation loop 的一般化。若目标改为对称 scientific
superiority 或 equivalence，12 cases 不够，必须先做 power/topic-size design 并增加 fresh cases。

## 7. 为什么 primary 应直接评原始 top-3，而不是两层 memo

**Decision**：支持直接盲评原始 top-3 payload，取代“ranker → consumer memo → evaluator”两层方案，
理由如下：

- ticket 021 要选择的是 ranker；直接 setwise comparison 保持唯一变化就是 ranker payload；
- 原始 segment 本来就是 production model-visible contract，不需要另造一个尚未存在的 memo contract；
- 去掉 consumer 后，没有 consumer sampling、JSON repair、claim entailment、consumer self-style 与
  `reasoning_effort` 尚未冻结等混杂；
- 只需 Robert 启动 Kimi/DeepSeek 的四个隔离 orientation sessions，调用量和人工链更可行；
- 它仍能测旧 pointwise qrels 没测到的 set coverage、互补性、直接可用性与 top-3 budget 效果。

代价是结论更窄：evaluator 同时扮演 synthetic AI consumer 与 judge。因此必须坚持双模型、双位置、
unresolved 不投票和不外推 human/end-to-end utility。两层 memo 方案可在最终 ideation consumer 落地后
作为独立 canary，不再是关闭 ticket 021 的 gate。

## 8. Fresh batch 的选择与封存

**Decision**：

1. 先在 spent cases 上完成所有 prompt/schema/validator/statistics dry-run，再冻结 v1.4 hash；
2. 从 222 个 unused eligible candidates 中按 hash seed 机械选择，不得由 controller 根据标题或旧
   failure pattern 手挑；总计 12 cases，覆盖 `small/medium/large` 各 4 个，至少两个领域，并保留
   reference-count 与 vocabulary-overlap spread；
3. selection objective、排除原因和 seed 在读取任何新 ranker output 前冻结；
4. 完成新的 Workshop/corpus approval chain 后，由只读 Approved Workshop 的 fresh query-author
   context 生成 broad/focused queries；它不能看 reference text、ranker outputs、旧 labels 或旧 winner；
5. 新 12 cases 全部是 formal evaluation，不从其中再调 prompt、阈值或重复次数；
6. 一旦任何人读取 fresh arm mapping/judgment，semantic prompt、rubric、aggregation 或 decision
   rule 就不得改变。若必须改变，整批降级为 spent diagnostic 并另取 fresh cases。

纯实现 bug 若在未解封 mapping/judgment 前被 deterministic validator 发现，可以在保留旧 attempt、
证明语义不变、递增版本并对所有 arms 全量重跑后继续；任何可能受 outcome 影响的修改都不适用此例外。

## 9. Union/full-corpus diagnostics

**Inference**：`BM25 top-3 ∪ E5 top-3` 优于两个 top-3 可能来自互补文献，也可能只来自 6 篇比 3 篇
信息更多；full corpus 还引入不同 context length、dilution 与成本。当前草案不能从这些 arms 推导具体
机制。

**Decision**：v1.4 只比较冻结 BM25 top-3 与 E5 top-3。Union/full-corpus 不参与 winner vote，也不在
本批 formal evidence 解封后追加。若未来仍要诊断 evidence budget，必须另开预登记 revision，至少加入
`BM25 top-6`、`E5 top-6` 与 `deduplicated union top-6` 三个 matched-budget arms；它只能区分“top-3
budget 不足”和“跨 ranker complementarity”，不能追溯改变本次 primary decision。full-corpus ceiling
因 context 规模不齐与成本更大，同样留给独立 revision。

## 10. 停止、失败与报告规则

**Decision**：

- 固定 `12 cases / 24 queries`，不因中途 direction、p-value 或费用趋势提前停止；
- 四个 judge sessions 全部完成并验 hash 后才解封 arm mapping；
- 不追加第三 judge、不改 tie policy、不选择性重跑；invalid JSON 只允许协议已包含的同配置一次重试；
- provider/model alias、prompt、tool permissions、session identity、call parameters、raw outputs、usage、
  timestamps、hashes 和 failures 全部记录；actual model provenance 不得再只信 bundle 自报字段；
- fresh batch 缺 case、缺 arm、缺 repeat、隔离失败或 judge bundle 泄漏时，formal result 为
  `incomplete/invalid`，不能把剩余样本重新计算成 winner；
- 同时报告 effect、exact p、cluster CI、resolved/unresolved、position consistency、cross-model
  agreement、validator failure、catastrophic omissions、strata 与真实成本；禁止只报总票数；
- 同一数据上只有一个 primary comparison；本 revision 不追加 top-6/full-corpus stage。

## 11. 最终实施顺序

1. 写 v1.4 overlay，明确 direct top-3 setwise 构念、case-level statistic、fresh-data rule、judge
   schema、失败和成本上限；
2. 实现 opaque sampler、pair-bundle schema、hard validator、mirror-pair builder、judge validator、
   consensus reducer 与 exact `2^12` randomization report；
3. 用旧 spent cases 做 direct-payload 全链路无效力 dry-run；修完后冻结代码/协议 hashes；
4. 选择、准备、批准 12 个 fresh cases 与 24 queries；
5. Windows 从 clean commit 运行 BM25/E5 bulk retrieval，Mac 只做 controller、bundle 和 evidence review；
6. 生成四个 exact prompts，给出 context feasibility、一次 frozen retry 上界的 token/费用并取得 Robert
   批次批准；
7. 把四份 exact prompts 交给 Robert 启动 Kimi/DeepSeek fresh isolated sessions；
8. validate、seal、解映射、运行固定统计，写 decision record。E5 未通过 promotion gate 时按 parsimony
   policy 选 BM25 只能是工程默认，不关闭科学不确定性。

## 12. 对抗性总评

| 风险 | 原方案状态 | 修订后处置 |
|---|---|---|
| 旧 holdout adaptive leakage | 已识别 | 永久 `spent_diagnostic_only`；只用于 dry-run |
| 构念过度外推 | 高风险 | 改名为 single-retrieval evidence-consumption utility |
| 24 query 伪重复 | 高风险 | 12 case 为统计单位；exact paired sign-flip |
| 小样本把无显著误当等效 | 高风险 | 只晋升大且稳定的 E5 收益；否则不证明 E5 值得 promotion |
| consumer 随机性 | 原方案未冻结 | primary 删除 memo consumer；以后 end-to-end canary 再单独处理 |
| judge position/self bias | 部分处理 | 双位置、跨 family、一致才 resolved；不多数票 |
| judge filesystem/network leakage | 未强制 | tool-less 或真实 sandbox，否则不得进入 formal gate |
| exact quote 被误当语义证明 | 高风险 | provenance hard gate 与 semantic judge 分层 |
| union 多给文本造成混淆 | 未处理 | matched top-6 conditional diagnostic；不参与 primary |
| optional stopping/选择性重跑 | 未完全写明 | 固定 N、固定 retries、全量完成后一次解封 |

**最终判断**：经过上述修订，direct-payload 实验能以可执行成本回答一个严格受限但真实有用的问题，
并能在没有足够证据时诚实返回 `E5 material utility gain not demonstrated`。它仍不是专家人工 gold
或完整 ideation end-to-end 实验；如果文档保留这一边界，v1.4 值得实施。如果拒绝 case-level
analysis、E5 非对称证明责任或真实隔离，继续运行只会得到更精致的合成投票，不能解决旧 holdout 已
暴露的测量不稳定。

## 一手来源

- Cynthia Dwork et al. [The reusable holdout](https://pubmed.ncbi.nlm.nih.gov/26250683/), Science 2015；
  [Generalization in Adaptive Data Analysis and Holdout Reuse](https://proceedings.neurips.cc/paper_files/paper/2015/file/bad5f33780c42f2588878a9d07405083-Paper.pdf), NeurIPS 2015.
- Shivani Upadhyay et al. [Overview of the TREC 2025 RAG Track](https://trec.nist.gov/pubs/trec34/papers/Overview_rag.pdf), NIST/TREC.
- Amine Al Ghossein et al. [ICLERB](https://arxiv.org/abs/2411.18947), 2024.
- Lianmin Zheng et al. [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685), 2023.
- Peiyi Wang et al. [Large Language Models are not Fair Evaluators](https://aclanthology.org/2024.acl-long.511/), ACL 2024.
- Arjun Panickssery et al. [LLM Evaluators Recognize and Favor Their Own Generations](https://proceedings.neurips.cc/paper_files/paper/2024/hash/7f1f0218e45f5414c79c0679633e47bc-Abstract-Conference.html), NeurIPS 2024.
- Pat Verga et al. [Replacing Judges with Juries](https://openreview.net/pdf?id=6AjeDjlg3d), 2024.
- Paul Thomas et al. [Large Language Models can Accurately Predict Searcher Preferences](https://www.microsoft.com/en-us/research/uploads/prod/2023/09/LLMs_for_relevance_labelling__SIGIR_24_.pdf), SIGIR 2024.
- Shivani Upadhyay et al. [A Large-Scale Study of Relevance Assessments with LLMs Using UMBRELA](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=959054), NIST/ICTIR 2025.
- Ellen Voorhees and Chris Buckley. [The Effect of Topic Set Size on Retrieval Experiment Error](https://www.nist.gov/publications/effect-topic-set-size-retrieval-experiment-error), SIGIR 2002/NIST.
- Mark Smucker, James Allan, Ben Carterette. [A Comparison of Statistical Significance Tests for Information Retrieval Evaluation](https://ciir-publications.cs.umass.edu/getpdf.php?id=744), CIKM 2007.
- Rotem Dror et al. [The Hitchhiker's Guide to Testing Statistical Significance in NLP](https://aclanthology.org/P18-1128/), ACL 2018.
- Tianyu Gao et al. [Enabling Large Language Models to Generate Text with Citations](https://aclanthology.org/2023.emnlp-main.398/), EMNLP 2023.
