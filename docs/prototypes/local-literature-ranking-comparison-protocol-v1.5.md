# 本地文献排序比较协议 v1.5：segment-reference evaluator overlay

Protocol date: 2026-08-31（Asia/Shanghai）  
Status: **Approved under Robert's delegated first-principles decision authority；fresh judgments 未开始**

本文件只覆盖 [v1.4](local-literature-ranking-comparison-protocol-v1.4.md) 第 5–6 节中的 evaluator
evidence locator schema 与 judge-protocol provenance。v1.4 的 fresh cases、query/input hashes、BM25/E5、
top-3 budget、anonymous mirrored sides、rubric、两个 models、统计单位、promotion gate、停止规则与 formal
call 单独授权要求全部不变。Formal input 继续绑定 v1.4；judge bundle 同时绑定 v1.4 base protocol 与本
v1.5 evaluator overlay。

## 1. 为什么不再要求模型逐字复制 quote

Spent qualification 暴露了两类失败：

1. v1.0 prompt 未公开 validator 的 20-scalar 下限，Kimi K3 给出的 19-scalar quote 实际逐字存在；
2. 公开限制后的 v1.0.1 中，K3 把 source 的 `CVA-Net) for` 抄成 `CVA-Net for`，其判断、paper/segment
   identity 和另外两条 quotes 均完整，但严格 substring gate 拒绝整个 24-item orientation。

逐字抄写不是本实验的目标构念。Bundle 已以 hash 固定每个完整 visible segment，且每个 paper 在 payload
中只有一个 selected segment。Quote substring 只能证明模型复制了一段存在的文字，不能证明它与 query、
评分或 rationale 相关；反过来，一个括号错误也不能证明 setwise utility 判断无效。依赖 full-orientation
retry 直到“这次刚好没抄错”会引入选择性成功和额外费用。

因此证据定位改为 **visible segment reference**。它保留不可伪造的 side/paper/segment provenance，把语义
grounding 交给预注册 controller blind audit 和跨模型/跨位置一致性，而不再用字符复制精度代理判断能力。

## 2. Frozen judgment schema v1.1

每个 judgment 仍含：

- `item_id`；
- `winner ∈ {left,right,tie,both_bad}`；
- 左右各 `direct_support/query_usefulness/coverage_diversity/specificity ∈ {0,1,2}`；
- `catastrophic_omission_side ∈ {left,right,neither}`；
- bounded `rationale`；
- `evidence_refs`：1–4 个 closed objects，每个恰含
  `side`、`paper_id`、`segment_id`、`support`。

`support` 是 20–500 Unicode scalars 的简短说明，解释该 visible segment 为什么支持当前评分；它不是原文
quote，不要求 substring。Local validator 必须证明 side/paper/segment tuple 在当前 item 中唯一可见；
left/right winner 至少引用 winner side，`tie/both_bad` 至少各引用一侧；任何未知 ID、额外字段、越界文本、
forbidden candidate identity 或缺 item 均 fail closed。

Public bundle 继续包含 exact segment text、source pointer、bundle self-hash 和 mapping commitment。Validated
trace 保留完整 `evidence_refs` 与 rationale。Controller 预注册 6-item blind rubric audit 时必须逐条确认：

1. support statement 确实由所指 segment 支持；
2. winner 与四项分数不自相矛盾；
3. 没有奖励纯长度、措辞流畅或模型熟悉度；
4. 没有使用 bundle 外事实或执行文献中的指令。

任一 audit item grounding 失败，panel 不准入 fresh formal calls。

## 3. Provenance and versioning

- Bundle/draft/trace/mapping/preparation schemas bump 到 `v1.1`；旧 v1.0/v1.0.1 artifacts 只作失败证据；
- `operational_judge prepare` 必须同时读取 v1.4 base protocol 与本 v1.5 evaluator protocol，分别记录 hash；
- side assignment seed 同时绑定两个 protocol hashes，但 orientation 2 仍只是逐 item 左右交换；
- evaluator profile 固定记录完整 Kimi Code alias、provider ID 与 `high` reasoning effort；draft 必须原样回显；
- qualification receipt 必须绑定 v1.5 hash；future formal judge preparation 还必须绑定通过的 receipt hash；
- 任何后续 evidence schema、support length、rubric 或 validator 语义变化都需要新 revision 和 spent 全量重验。

本 revision 不授权剩余 qualification 或 fresh formal model calls；调用授权仍以 exact prompts 与成本报告为准。
