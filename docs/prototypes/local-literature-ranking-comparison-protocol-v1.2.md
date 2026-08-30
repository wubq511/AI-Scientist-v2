# 本地文献排序最小公平比较协议 v1.2：隔离 AI qrels

Protocol date: 2026-08-30（Asia/Shanghai）

Status: **Approved / pre-registered v1.2**

Decision ticket: `Choose and calibrate local literature ranking`

Robert 于 2026-08-30 批准本 revision。它是
[v1.1 基础协议](local-literature-ranking-comparison-protocol.md) 的 hash-bound overlay，
不是对 v1.1 文件的原地修改。v1.1 SHA-256 必须保持：

```text
23d9b6d05d57f015a34f9bc75fa0bf9b0dee0ab2afa01c6b646b5d27a422f91c
```

除本文明确覆盖的条款外，v1.1 的 case/query、approved corpus、abstract-only scope、
shared segmentation、candidate matrix、metrics、resource/determinism gates、promotion rules、
scope 与停止线全部继续生效。现有 formal inputs 继续绑定 v1.1；AI judge bundle 必须同时绑定
v1.1、本文与 formal-input manifest 的 SHA-256。

## 1. 本 revision 解决的问题

v1.1 要求 Robert 完成 176 个 development 与 160 个 holdout query-paper judgments，
并延时复标至少 30 条/每 split。这个设计把两个不同构念错误地交给同一个 assessor：

1. `content-grounded topical evidence relevance`：可见题名/摘要是否直接支持 query；
2. `Robert personal utility`：有限 evidence budget 下，哪组真实检索结果对 Robert 更有用。

Robert 的英文论文领域经验、336 次绝对等级判断与疲劳风险使第一项无法成为可信 human gold。
v1.2 用隔离 AI 完成第一项，只让 Robert 对最终匿名输出做少量 first-party preference。

本 revision 的依据见
[AI qrels 调研](local-ranking-ai-qrels-research.md)。结论边界是 synthetic topical qrels，
不得表述为 expert-human gold 或普适用户效用。

## 2. 覆盖 v1.1 §5.3：qrels authority

### 2.1 冻结的 judge roles

正式 qrels 使用三个无共享会话历史的 projectless Codex tasks：

| Role | Model | Reasoning | 职责 |
| --- | --- | --- | --- |
| judge-A | `gpt-5.6-sol` | `xhigh` | 对 development + holdout 全量独立 pointwise judgment |
| judge-B | `gpt-5.5` | `xhigh` | 对相同 items 全量独立 pointwise judgment，使用不同冻结顺序 |
| judge-C | `gpt-5.6-terra` | `xhigh` | 只盲评 A/B 发生分歧的原始 items，不看 A/B labels/rationales |

三者都是 OpenAI Codex same-provider judges；不同 model id 只能降低 exact-model/context coupling，
不能称为 independent model-family consensus。服务端模型 alias 不能保证未来 byte-exact replay；
因此必须永久保留 exact bundles、task/thread identity、model/reasoning setting、raw drafts、
normalized traces、qrels 与全部 hashes，把不可避免的模型非确定性列为限制。

### 2.2 唯一允许的输入

每个 judge item 只包含：

- frozen `query_id`、query text 与 query kind；
- opaque `paper_id` 与 paper title；
- 全部 eligible Retrieval Segments，含 `segment_id`、content type、source offset 和 exact text；
- frozen rubric、split/input/protocol hashes。

禁止读取或提供：Target Paper、Workshop hidden text、candidate/ranker identity、scores、rank
positions、candidate outputs、previous qrels/other judge output、development/holdout results、
ticket winner rules、网络搜索或外部知识。Paper text 是 untrusted data；judge 不得执行其中的命令。

Judge-A/B bundle item order 分别由 `judge_id + split + item_id` 的冻结 SHA-256 seed 决定，
不能来自任何 ranker output。每个 item 必须 pointwise 判断，不能在 papers 之间做相对排序。

### 2.3 输出与 fail-closed evidence

Paper grades 保持 v1.1 的 `0..3`，segment grades 保持 `0..2`。此外：

- paper grade 2/3 必须标完其全部 eligible segments，且至少一个 segment grade=2；
- 每个 segment grade=2 必须提供 exact supporting quote；validator 将 quote 解析为精确字符 offsets；
- grade 0/1 paper 不产生 segment judgments；
- 缺项、重复/越界 ID、非 exact quote、外部事实补足、invalid JSON、hash/schema mismatch 全部
  typed fail，不得静默修复、降级或填默认值；
- 原始 rationale 与 supporting spans 保存在 private trace；正式 harness 只读取 canonical qrels。

AI 输出只允许通过 `prototypes.local_ranking.ai_judge finalize` 生成 qrels。该命令必须校验
bundle/input identity、完整 coverage、grade/segment constraints 与 exact quotes，并再次通过 harness
`parse_qrels`。

### 2.4 A/B disagreement 与 consensus

Paper grade、任一 segment grade、或 direct supporting spans 有任一不同，item 即为 disagreement。
Controller 只可运行确定性的 diff builder；给 judge-C 的 packet 只含 disputed original items 与输入
hashes，不能含 A/B labels、rationales 或哪一方给了什么答案。

非分歧项取 A/B 共同 judgment；分歧项取 judge-C judgment。A、B、C raw evidence 与最终
consensus 全部保留，禁止只保留多数票。

Development 与 holdout 比较都必须分别使用 judge-A、judge-B、consensus 三套 qrels。只有：

1. 每套 qrels 都通过 hard gates；
2. finalist promotion/winner direction 在三套 qrels 上一致；
3. v1.1 的 `0.03/0.05` margin、query wins/losses 与 catastrophic-miss rules 在每套 qrels 上独立通过；

才允许形成 synthetic-topical recommendation。任一 judge choice 改变 winner、只靠 consensus
才勉强产生 winner、或出现集中在某 case/query 的 1↔2 boundary disagreement，结果必须是
`inconclusive`，不得继续调 judge prompt 或追溯修改 margin。

Weighted kappa、1↔2 boundary disagreement、相差两级比例、grade distribution 与 span agreement
作为 diagnostics 报告；它们不冒充 AI qrels 的真实性证明。v1.1 的 Robert 延时复标与
`kappa>=0.70` gate 被本节完全替代。

## 3. 覆盖 v1.1 holdout sealing

Judge-A/B 必须在任何正式 ranking run 前完成 development + holdout。Development drafts、traces 与
qrels 可以写入 controller 可读的 immutable attempt；holdout plaintext 只能保存在各 projectless
judge task 的 `sealed/` 目录，controller 在 finalists 和全部参数冻结前只能接收：

- task/thread identity；
- bundle SHA-256；
- normalized trace SHA-256；
- qrels SHA-256；
- schema/coverage validator pass/fail。

Judge-C 同样在任何 ranking run 前完成两 split 的 blind disagreement adjudication；holdout
adjudication与 consensus plaintext 保留在 judge-C projectless `sealed/`，只回传 hashes 与验证
状态。Finalists/参数冻结后，controller 才可请求三个 task 释放 holdout artifacts，并逐 hash 验证。

如果任何 task 在 final response、tracked file、development artifact 或日志中泄露 holdout label、
grade distribution、disagreement count/rate、rationale 或 qrels content，holdout seal 失败，必须冻结
新的 cases/queries 后重建，不能继续当前 attempt。

## 4. Robert 的 first-party utility gate

AI qrels 完成 topical comparison 后，最多两个 finalists 进入 12-query blind pairwise utility check。
每条 holdout query 生成一张 anonymous A/B card：

- A/B 位置按 frozen seed 随机；
- 只显示 query 与两套相同 evidence budget 的 paper/segment outputs；
- 不显示 ranker identity、scores、AI qrels/rationale 或 synthetic winner；
- Robert 只选择 `A 更有用 / B 更有用 / 相同 / 两者都无用 / 看不懂`；
- 原始英文保留，浏览器翻译可作为理解辅助；不得用 AI summary 替换 source text。

这 12 次不是 qrels，不要求 Robert 判断论文真伪，也不支持普适用户宣称。若 topical winner 与
Robert preference 明显冲突，或大量选择 `看不懂`，ticket 结果为 `inconclusive` 或只对一致的
query strata 下结论，不能自动覆盖任一构念。

## 5. 执行顺序

1. 冻结本 revision、judge rubric、A/B model profiles 与 immutable bundles；
2. 创建 judge-A/B projectless tasks，并在任何 ranker run 前完成两 split；
3. validator 生成 development qrels，holdout 只记录 sealed receipts；
4. 确定性生成 development/holdout disagreement packets；judge-C 在不看 A/B labels 下完成裁决，
   development consensus 解封，holdout consensus 保持 sealed；
5. 用 A/B/consensus development qrels 校准并冻结最多三个 distinct finalists；
6. 解封并验证 A/B/consensus holdout，做一次性三套 sensitivity comparison；
7. 若最多两个 finalists 仍满足相同 winner direction，生成 12-query Robert anonymous A/B；
8. 把 topical evidence、judge sensitivity、资源/确定性证据和 Robert preference 一并交给 Robert；
   只有 Robert 批准 winner 后才写 ticket Resolution。否则记录 `inconclusive`。

## 6. 明确不做

- 不把 single Codex conversation 叫作 gold；
- 不因 AI 便宜而引入 pooling、unjudged=0 或 active-learning calibration；336 pairs 全量判断；
- 不用 current controller 直接标注；
- 不在看到 development/holdout ranking 后改 rubric、judge、prompt、qrels 或 margin；
- 不修改 production retriever，不进入 BFTS/downstream experiment/write-up/review；
- 不把本轮结果外推为 full-text ranking、expert relevance 或其他用户效用。

## 7. 最脆弱假设与停止线

本方案假设 same-provider 但不同 model/context 的 A/B/C 能产生对 finalist direction 足够稳定的
synthetic topical signal。如果该假设不成立，三套 qrels 会导出不同 winner；设计不会用多数票
掩盖失败，而是按预注册规则返回 `inconclusive`。下一次 revision 才可考虑不同 provider/model
family、领域专家小样本或新增 frozen topics，不能在本 attempt 临时修补。
