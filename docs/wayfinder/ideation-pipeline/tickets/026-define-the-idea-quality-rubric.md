---
title: Define the idea quality rubric
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 014-understand-target-to-workshop-semantics.md
  - 018-define-the-workshop-file-contract.md
  - 020-define-the-scoped-retriever-contract.md
  - 032-choose-ideabench-evaluation-fidelity.md
---

## Question

Which evidence-backed criteria distinguish a grounded, non-leaking, non-duplicative, feasible idea from a merely schema-valid output, and which judgments remain qualitative?

## Resolution

2026-08-30 经 grilling 两轮九题由 Robert 批准。Idea Quality Rubric 是一个版本化 criteria 目录，每条 criterion 恰好归入一个执行层：runtime 层只收 evidence-backed 检查，post-seal 层收 Robert 的定性判断。

1. **分层架构**：两层。runtime 层在 [Define control flow, failures, and resume](025-define-control-flow-failures-and-resume.md) 已定的 per-generation finalization gate 上执行，不新增执行点；失败语义只用 025 的封闭词汇（Model-Fixable Error / Terminal Outcome）。post-seal 层走 [Choose IdeaBench evaluation fidelity](032-choose-ideabench-evaluation-fidelity.md) 的 Evaluation Artifact。不设 seal-time 自动层。
2. **Runtime criteria**（在 024 结构校验之后执行）：
   - *Grounding 门槛*（重申 020/025 已定，归入目录）：本 generation 未取得 ≥1 非空 Retrieval Result → FinalizeIdea 作为 Model-Fixable Error 拒绝回灌；run 全程从未取得 → Terminal Outcome `failed`。
   - *Declared Grounding 校验*（新）：`FinalizeIdea` 参数在 idea 对象之外新增 `grounding: [paper_id, ...]`，模型声明 idea 依据本 run 实际检索到的哪些 paper。确定性校验：字段合法、列表非空、每个声明 id 出现在本 run 的 Retrieval Audit Events 中——声明了从未检索的 paper 即机检说谎。违规 = Model-Fixable Error 回灌，错误文本最小、无内部细节。七字段 idea payload 不动（008），声明链接存 sidecar provenance。字段级合约归 [Define the declared grounding contract](038-define-the-declared-grounding-contract.md)；024 的 FinalizeIdea 结构校验相应修订并留有指针。
   - *Payload hygiene scan*（新）：对 FinalizeIdea 提交内容（idea payload 与 grounding 整体）做确定性私有标识符扫描（`case_id`、corpus path/hash、内部标识符模式；模式列表与版本归 027）。命中 = Terminal Outcome `failed`：模型正常路径接触不到这些信息，命中即输入边界被突破，按 025 准则「证据可信度已损」，不允许以模型修复掩盖污染事实。
   - *Run 内去重*（新）：normalized n-gram overlap 对照本 run 前序 ideas（与 018 同机制家族；阈值与规则版本归 027）。近重复 = Model-Fixable Error 回灌（告知与哪个前序 idea 过近，最少信息）；reflection 预算耗尽则该 generation 落 disposition `budget_exhausted`，不终止 run。
3. **Post-seal criteria**（Robert 定性，字段化归 037）：032 已定六项（问题空间匹配度、与 target contribution 的重叠性质、相对 novelty、feasibility 合理性、污染信号检查、泄漏复核）+ 本票新增第七项 *grounding 综合质量*——对照 retrieval audit 与声明链接，判断 idea 是否真正综合了所声明的文献而非挂名引用。
4. **不设条目的维度**：feasible 与 novelty 无 runtime 机检判据，仅 post-seal 定性；跨 run 重复由 Run Isolation 架构保证，只能 post-seal 跨 Evaluation Artifact 比较；idea 复现 target 的污染方向归 032 的 post-seal 检查，rubric 只指针引用。
5. **Non-leaking 术语定准**：idea 侧 = Idea Leakage，由 payload hygiene scan 作防御纵深（主要泄漏控制仍在输入侧 018/020）；Workshop 侧归 018。两术语已入 CONTEXT.md。
6. **载体与版本化**：本 resolution 锁定 criteria 目录、语义、层级归属与失败语义；确切的版本化 tracked file（schema、阈值、模式列表）随实现 ticket 落地（025/034 先例）。Run Specification pin rubric version；criteria 增删改 = 新版本 + Robert 批准。阈值与模式列表归 027，gate 消费归 028，定性字段 schema 归 037。

衍生动作：新建 [Define the declared grounding contract](038-define-the-declared-grounding-contract.md)（blocked_by 本票）；024 追加修订指针；CONTEXT.md 新增 Idea Quality Rubric、Declared Grounding、Idea Leakage 三个术语。

本 ticket 只锁定 rubric 决策；未实现 runtime code、未修改 prompt、未调用模型、未进入 downstream。

> 后续修订（2026-08-30）：[Define the declared grounding contract](038-define-the-declared-grounding-contract.md) 收紧 Declared Grounding eligibility：声明 id 必须 ∈ 本 generation 已返回 Retrieval Results 的 paper_id 并集（本票「本 run 的 Retrieval Audit Events」措辞的子集），与 025 的 per-generation `msg_history` 作用域严格对齐。
