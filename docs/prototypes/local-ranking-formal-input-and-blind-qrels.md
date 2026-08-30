# Local ranking 正式输入与盲评表

Date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本记录覆盖 24 条 query 的冻结审批、正式 Retrieval Segment 物化与 blind qrels 表生成；没有生成 relevance judgment，也没有运行任何 ranker。

## 结论

Query 与 formal input 两个 blocker 已解除：12 个 cases 的 24 条 query 已原样批准，168 篇 approved papers 已物化为 180 个所有 arms 共用的 source-faithful segments。Development/holdout 输入都通过 harness schema 与 pinned E5 exact token-length checks；两次 fresh-process materialization byte-identical。

当前唯一数据 blocker 是 Robert 的 blind qrels judgment。Development 共 176 个 query-paper judgments，holdout 共 160 个。两份本地离线 HTML 表已经生成，页面只展示 `query + paper title + Retrieval Segments`，不展示 scorer/candidate、分数、排名、Target Paper 或 previous result。

## Query 冻结与审批

隔离 query-author attempt：

```text
artifacts/local-ranking-prototype/query-authoring-v1/attempts/queries-001/query-manifest.json
```

- 12 cases / 24 queries，每个 case 恰好 `broad` + `focused`；
- query manifest SHA-256：`aa9875353b6d16ab24eabd525c2620074737bbe70b4feb5a3481d2d3471cb8e1`；
- authoring session 逐文件验证 Approved Workshop packet hash，并声明未读取 Target、corpora/references、qrels 或 ranker output；
- controller 对 frozen bytes 做 schema、ID、text hash、scalar count、normalization、packet/protocol binding 复核；
- 根据 Robert 此前“从第一性原理出发，自行研究并决定是否批准”的明确授权，controller **原样批准**，`rewrite_count=0`。已经接触 reference content 的 controller 没有改写 query；若审批失败，只能退回新的隔离 author attempt。

Immutable approval：

```text
artifacts/local-ranking-prototype/query-approval-v1/attempts/query-approval-001/result.json
```

SHA-256：`a5fdf90d77654fbfb29f8a6f1ba22c75ff14376dfb6639496fea40056a05c105`；`query-approval-002-replay/result.json` 与它 byte-identical。

## Formal input 物化

新增 throwaway adapter `prototypes/local_ranking/formal_input.py`：

1. fail closed 验证 input approval、approved corpora、query packet、query manifest、query approval、v1.1 protocol 和 tokenizer hashes；
2. 用 pinned `tokenizers==0.23.1` 与 exact `e5-small-v2` tokenizer 计算 `query: `、`passage: title`、`passage: segment` 的完整 encoded length，计入 special tokens；
3. 只对超过 512-token boundary 的 abstract 使用已批准的 sentence-first、zero-overlap、full-coverage segmentation；
4. 输出 harness 可直接读取、按 split 分离的 canonical `local-ranking-input-v1`；
5. 生成 private audit、blind packet 和本地 self-contained HTML review form，不生成 placeholder qrels。

Hardened attempts：

```text
artifacts/local-ranking-prototype/formal-input-v1/attempts/formal-input-005/
artifacts/local-ranking-prototype/formal-input-v1/attempts/formal-input-006-replay/
```

两份目录 byte-identical；各自 `manifest.json` SHA-256 均为 `80bbcf04e37588fce88182e5a2bce327329d30051b7a25c48c4ff13afade3296`。`formal-input-001/002` 的 input/audit bytes 与 hardened attempts 相同，但页面请求了不存在的 favicon，浏览器控制台出现无害 404；`formal-input-003/004` 修复 favicon 后，code review 又发现 paper grade 从 2/3 切回 0/1 时，隐藏 segment 的 visual checked state 没有同步清空，重新切回会造成界面与保存 state 不一致。所有 immutable attempts 均保留，005/006 同时修复这两个 UI 问题并 supersede 前四次；formal input/audit/packet bytes 从 001 到 006 都未改变。

## Exact 结果

| 检查 | 结果 |
|---|---:|
| Cases | 12（development 6 + holdout 6） |
| Queries | 24（每 split 12） |
| Papers | 168（development 88 + holdout 80） |
| Segments | 180 |
| Segments/paper | 157×1、10×2、1×3 |
| Max query input | 44 tokens |
| Max title input | 53 tokens |
| Max segment input | 512 tokens |
| Source reconstruction | 168/168 pass |
| 与 approved length probe offsets/tokens/hashes | 168/168 exact match |
| Development paper judgments | 176 |
| Holdout paper judgments | 160 |

Formal input hashes：

- development `input.json`：`a7bcc349275626d5babb87dced480791a88bb5749242ec3f4b58e706dccaabbb`；
- holdout `input.json`：`2d0533d6af377c6652435df91a290f85bdd7e1410eebe4b21ad8f7a4c351ebf2`；
- private `audit.json`：`ba4254867cd4a66ff0d254938ae572561530057c69a52261c362b8009e07546b`。

Formal audit 的 raw segmentation identity 使用可运行 `paper_id/segment_id`，因此它自己的 segmentation hash 与早期 privacy-hashed length probe 表示不同；将两者统一投影为 `case_id + hashed paper_id + source/offset/token/text hashes` 后，168 条 records 完全相等。不能仅比较两个采用不同记录 schema 的 aggregate hash。

## Blind review form

`prototypes/local_ranking/blind_review.py` 生成无外部资源的单文件 HTML：

- paper 顺序由 frozen hash 确定，与任何 candidate ranking 无关；
- 中文 rubric，英文原文保留；浏览器翻译只能作为理解辅助；
- 选择 paper grade 2/3 后才展开全部 eligible segments；
- 自动保存到当前浏览器 `localStorage`；
- incomplete paper/segment judgments、或“至少一个直接 segment”和 `no_supporting_segment` 不满足互斥关系时拒绝导出；
- 导出严格的 `local-ranking-qrels-v1` JSON。

真实浏览器验收通过：页面载入无 console error；paper grade 2 会展开 segment ratings；未完成 176 条 development judgments 时导出被拒绝；页面本身无外部网络依赖。

## 下一步与封存边界

Robert 需要完成两份盲评：

1. Development 表完成后，把导出的 `qrels-development.json` 交给 controller 做 schema/hash 校验；
2. Holdout 表也应在看见任何 ranking result 前完成，但导出的 `qrels-holdout.json` 由 Robert 自行封存，finalists 与参数冻结前不得交给 controller；
3. 初次 judgment 后至少 24 小时，再按冻结 seed 重标每个 split 的 15%（至少 30 条），通过 qrels-stability gate 后才允许把相应 qrels 用于正式比较。

在这些 judgment 完成前，不创建 formal ranking protocol、不运行 development/holdout、不选择 winner。
