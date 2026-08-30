# Local ranking 正式输入就绪检查

Check date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本检查只判断 approved comparison inputs 是否已经存在，不读取 raw Target Paper、reference content 或 holdout judgment，不生成替代数据。

## 结论

正式 development/holdout 仍不能开始，但 blocker 已从「没有候选输入」缩小为明确的 HITL approval gate。当前已有 12 个满足 split/size strata 的 private case proposals、12 个 zero-error pending corpus bundles 与 12 份 deterministic-validation-passed Workshop drafts；由于 Workshop 尚待 independent semantic review、corpus policy/canary evidence 尚待 Robert 批准，可合法进入 comparison protocol 的 **approved cases 仍为 0**，暂不能冻结 24 queries 或生成 Robert blind qrels form。

这不是 harness failure。Harness、双平台 locks 与 Windows fresh environment 可以独立准备；但 raw interview dataset 不能被直接重命名或包装成 approved input，也不能用 diagnostic fixture 代替真实 qrels。

## 只读盘点

当前可见数据/证据包括：

- ignored raw inputs：`data/raw/filtered_references.csv`、`data/raw/ideabench_clustering.json`、`data/raw/target_papers.csv`；
- private diagnostic output：`artifacts/local-ranking-prototype/diagnostic-v1/`；
- private immutable input-preparation attempts：`artifacts/local-ranking-prototype/input-preparation-v1/attempts/`，当前 proposal 为 `inputs-007`，byte-identical replay 为 `inputs-008-replay`；
- tracked contracts、research、fixture 和 harness。

当前不存在：

- **Approved** Workshop Markdown + private Workshop Manifest（drafts 与 deterministic reports 已存在，但 semantic review pending）；
- **Approved** corpus bundle（12 份 `corpus.json`、`bundle-manifest.json`、`validation-report.json` 与 evidence 已机械生成并 zero-error，但 approval pending）；
- approved `case_id` roster（12-case proposal 已冻结到 hash，但尚待 Robert 批准）；
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

Robert 先审阅 `inputs-007` 的 private semantic-review packet，批准或退回逐 case Workshop，并批准当前 corpus policy versions 与 12-case proposal。通过后新写 immutable approval sidecar 与 final approved manifests，不能覆盖 pending artifacts；随后由一个未读取 Target/corpus content 的新会话只看 Approved Workshop 起草每 case 的 broad/focused query，Robert 在相同边界内审核。Reference content 仅在 blind qrels 阶段向 Robert 展示，holdout judgment 在 finalists 冻结前保持 sealed。详细证据见 [Local ranking 正式输入准备证据](local-ranking-input-preparation.md)。
