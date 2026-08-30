# Local ranking 正式输入就绪检查

Check date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本检查只判断 approved comparison inputs 是否已经存在，不读取 raw Target Paper、reference content 或 holdout judgment，不生成替代数据。

## 结论

正式 development/holdout 仍不能开始，但 case/Workshop/corpus、query 与 formal segmentation blocker 均已解除。当前 `input-approval-001` 按 exact hashes 批准了 12 个满足 split/size strata 的 cases、12 个 zero-error abstract-only corpus bundles 与 12 份 deterministic-validation-passed Workshops；隔离 session 起草的 24 条 query 已原样批准；168 篇 papers 已按共同长度政策 materialize 为 180 个 formal segments。

当前唯一数据 blocker 是 paper/segment qrels 尚未由 Robert blind judgment/seal。Development/holdout 本地离线盲评表已经生成；完成 judgments 与至少 24 小时后的 stability reassessment 前不能运行正式 comparison。Pinned E5 exact checks 全部通过：max query/title/segment inputs 分别为 44/53/512 tokens，获批政策没有裁掉 abstract。

这不是 harness failure。Harness、双平台 locks 与 Windows fresh environment 可以独立准备；但 raw interview dataset 不能被直接重命名或包装成 approved input，也不能用 diagnostic fixture 代替真实 qrels。

## 只读盘点

当前可见数据/证据包括：

- ignored raw inputs：`data/raw/filtered_references.csv`、`data/raw/ideabench_clustering.json`、`data/raw/target_papers.csv`；
- private diagnostic output：`artifacts/local-ranking-prototype/diagnostic-v1/`；
- private immutable input-preparation attempts：`artifacts/local-ranking-prototype/input-preparation-v1/attempts/`，当前 proposal 为 `inputs-007`，byte-identical replay 为 `inputs-008-replay`；
- private immutable input approval：`inputs-007/approvals/input-approval-001/`，approval manifest SHA-256 为 `389c5ebcabe5774e2e380d75fc39baa03913b7b9cda82de3087012ca8a22c86e`，query-author packet manifest SHA-256 为 `aca55098a6167840fe7b36bfec3d128f07f4d15477c4869617a5d338ebf51ef8`；
- private immutable length-policy probes：`artifacts/local-ranking-prototype/length-policy-v1/attempts/length-003/` 与 `length-004/`，两个 `result.json` byte-identical，SHA-256 为 `fedd7fc747f587903d1c4f5329ec59c0242e9ac57a7c48f72cee70a97ea79083`；
- private immutable query draft/approval：`query-authoring-v1/attempts/queries-001/query-manifest.json` 与 `query-approval-v1/attempts/query-approval-001/result.json`；
- private immutable formal inputs：`formal-input-v1/attempts/formal-input-005/` 与 byte-identical `formal-input-006-replay/`，manifest SHA-256 为 `80bbcf04e37588fce88182e5a2bce327329d30051b7a25c48c4ff13afade3296`；
- tracked contracts、research、fixture 和 harness。

当前不存在：

- blinded paper/segment qrels 或 sealed holdout qrels。

## Fail-closed 边界

在剩余 artifacts 出现并通过各自合同前：

1. Development qrels 完成前不运行 development candidate matrix；
2. Holdout qrels 由 Robert 封存，finalists 与所有参数冻结前 controller 不得读取；
3. 不把长摘要静默截断给 dense arm，也不偏离已批准的 180-segment formal input；
4. 不创建 ranking result 文档，不选择 winner；
5. 可以继续 qrels schema/identity validation 与 24 小时后的 stability reassessment tooling。

## 解除条件

Robert 完成两份 blind qrels；development 导出交给 controller 校验，holdout 导出由 Robert 自行封存。初次 judgment 至少 24 小时后，每个 split 冻结抽取 15%（至少 30 条）重标并通过 stability gate。详细证据见 [Local ranking 正式输入与盲评表](local-ranking-formal-input-and-blind-qrels.md)、[Local ranking 正式输入准备证据](local-ranking-input-preparation.md)、[Local ranking 长度政策最小比较](local-ranking-length-policy-comparison.md) 和 [Local ranking 是否需要论文全文](local-ranking-full-text-decision.md)。
