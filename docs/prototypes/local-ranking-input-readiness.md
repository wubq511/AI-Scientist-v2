# Local ranking 正式输入就绪检查

Check date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本检查只判断 approved comparison inputs 是否已经存在，不读取 raw Target Paper、reference content 或 holdout judgment，不生成替代数据。

## 结论

正式 development/holdout 当前不能开始。仓库中没有任何已经通过既定 admission gates 的 `Approved Workshop` 或 `Approved Target Reference Corpus` bundle，因此可合法进入 comparison protocol 的 cases 为 0，无法冻结 12 cases / 24 queries，也不能生成 Robert blind qrels form。

这不是 harness failure。Harness、双平台 locks 与 Windows fresh environment 可以独立准备；但 raw interview dataset 不能被直接重命名或包装成 approved input，也不能用 diagnostic fixture 代替真实 qrels。

## 只读盘点

当前可见数据/证据只有：

- ignored raw inputs：`data/raw/filtered_references.csv`、`data/raw/ideabench_clustering.json`、`data/raw/target_papers.csv`；
- private diagnostic output：`artifacts/local-ranking-prototype/diagnostic-v1/`；
- tracked contracts、research、fixture 和 harness。

当前不存在：

- Approved Workshop Markdown + private Workshop Manifest；
- per-case approved corpus bundle 的 `corpus.json`、`bundle-manifest.json`、`validation-report.json` 与 evidence；
- approved `case_id` roster；
- development/holdout split manifest；
- frozen broad/focused queries；
- blinded paper/segment qrels 或 sealed holdout qrels。

## Fail-closed 边界

在上述 artifacts 出现并通过各自合同前：

1. 不读取 reference content 来反向构造 query；
2. 不把 raw target/reference rows 当成 approved cases；
3. 不运行正式 candidate matrix 或 resource/relevance promotion；
4. 不创建 ranking result 文档，不选择 winner；
5. 可以继续进行与 case/qrels 无关的 binary lock、model artifact、offline import/inference 和 diagnostic fixture preflight。

## 解除条件

正式 comparison input preparation 需要上游先产出至少 12 个满足 protocol strata 的 approved case bundles。随后才按 protocol 执行：Codex 只看 Approved Workshop 起草每 case 的 broad/focused query，Robert 在相同边界内审核；reference content 仅在 blind qrels 阶段向 Robert 展示，holdout judgment 在 finalists 冻结前保持 sealed。
