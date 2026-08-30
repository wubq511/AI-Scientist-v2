# Local ranking 正式输入就绪检查

Check date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本检查只判断 approved comparison inputs 是否已经存在，不读取 raw Target Paper、reference content 或 holdout judgment，不生成替代数据。

## 结论

正式 development/holdout 仍不能开始，但 case/Workshop/corpus blocker 已解除。当前 `input-approval-001` 按 exact hashes 批准了 12 个满足 split/size strata 的 cases、12 个 zero-error abstract-only corpus bundles 与 12 份 deterministic-validation-passed Workshops；可合法进入 comparison protocol 的 **approved cases 现为 12**。

剩余 blocker 是：24 条 broad/focused queries 尚未由隔离上下文起草和冻结；4 篇较长摘要尚待 pinned E5 tokenizer exact 512-token preflight，并可能需要共同 abstract segmentation；paper/segment qrels 尚未 blind judgment/seal。以上完成前不能运行 development/holdout。

这不是 harness failure。Harness、双平台 locks 与 Windows fresh environment 可以独立准备；但 raw interview dataset 不能被直接重命名或包装成 approved input，也不能用 diagnostic fixture 代替真实 qrels。

## 只读盘点

当前可见数据/证据包括：

- ignored raw inputs：`data/raw/filtered_references.csv`、`data/raw/ideabench_clustering.json`、`data/raw/target_papers.csv`；
- private diagnostic output：`artifacts/local-ranking-prototype/diagnostic-v1/`；
- private immutable input-preparation attempts：`artifacts/local-ranking-prototype/input-preparation-v1/attempts/`，当前 proposal 为 `inputs-007`，byte-identical replay 为 `inputs-008-replay`；
- private immutable input approval：`inputs-007/approvals/input-approval-001/`，approval manifest SHA-256 为 `389c5ebcabe5774e2e380d75fc39baa03913b7b9cda82de3087012ca8a22c86e`，query-author packet manifest SHA-256 为 `aca55098a6167840fe7b36bfec3d128f07f4d15477c4869617a5d338ebf51ef8`；
- tracked contracts、research、fixture 和 harness。

当前不存在：

- frozen broad/focused queries；
- pinned-tokenizer-passed formal Retrieval Segments；
- blinded paper/segment qrels 或 sealed holdout qrels。

## Fail-closed 边界

在剩余 artifacts 出现并通过各自合同前：

1. Query author 只能读取 approved query-author packet，不读取 Target authoring input、reference content、qrels 或 ranker output；
2. 不把未经共同 segmentation/length preflight 的长摘要静默截断给 dense arm；
3. 不运行正式 candidate matrix 或 resource/relevance promotion；
4. 不创建 ranking result 文档，不选择 winner；
5. 可以继续 exact tokenizer preflight、formal input adapter、blind qrels form 和与 qrels 无关的 diagnostic fixture 验证。

## 解除条件

由一个未读取 Target/corpus content 的新会话只看 `input-approval-001/query-author-packet/`，起草并冻结每 case 的 broad/focused query；然后用 pinned tokenizer 验证全部 formal segments，必要时先批准并冻结共同 abstract segmentation。Reference content 仅在 blind qrels 阶段向 Robert 展示，holdout judgments 在 finalists 冻结前保持 sealed。详细证据见 [Local ranking 正式输入准备证据](local-ranking-input-preparation.md) 和 [Local ranking 是否需要论文全文](local-ranking-full-text-decision.md)。
