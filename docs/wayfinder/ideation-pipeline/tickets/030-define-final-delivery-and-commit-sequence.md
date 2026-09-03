---
title: Define final delivery and commit sequence
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 027-define-the-validation-and-test-matrix.md
  - 028-define-canaries-and-scale-gates.md
  - 029-define-the-optimization-promotion-gate.md
---

## Question

How should implementation tickets, granular commits, reviews, work logs, run evidence, repository instructions, experiment report, and interview narrative form one reproducible handoff without claiming downstream work?

## Decision

2026-08-30 经 grilling 三轮由 Robert 批准。完整契约落为独立文档 [docs/agents/delivery-and-handoff.md](../../../agents/delivery-and-handoff.md)(v1.0),本节只记决策摘要。

- **交付链**:wayfinder(决策)→ `/to-spec`(一份规格,落 `docs/agents/`,引用而不复述契约)→ `/to-tickets`(垂直切片票,落 `docs/wayfinder/ideation-implementation/`)→ `/implement`(tdd + code-review,单分支逐票提交)→ canary/终波(028)→ report(`docs/research/`,中文,committed)+ narrative(`docs/task/`,private)。
- **启动时机**:to-spec 待 021 关闭;035/036 留 open 至 canary 期,其三个参数(`reasoning_effort`/`max_tokens`/Workshop 变体)在 spec 中为显式开放点。
- **切片约束**:每票 acceptance criteria 引用矩阵行 ID;第一票为不改行为的地基票;改既有路径用 expand–contract(006);每票必须映射到已关闭契约票。
- **验收**:票关闭 = 矩阵行全绿 + 脱敏摘要 + Robert 逐票验收;commit 沿用既有纪律;合并 main/远程发布单独批准。
- **内容侧**:AGENTS.md 随行为变更票同 commit 同步,README 不动;report 七节骨架含 032 的 Evaluation fidelity 专节;narrative 以 Evidence Feedback Loop 为脊柱,失败/降级发现独立成节先于最终结果(回答了 map 的雾);话术边界 = 固定 scope 声明段 + 六条禁用措辞清单 + 入库前 checklist。

**关闭条件**(经 Robert 批准):spec 与实现票单经 Robert 批准后,由该 session 补写 `## Resolution`、关闭本票、更新 map 的 Decisions so far,并清算「面试叙事-失败发现」雾(其答案见契约文档 interview narrative 节)。在此之前本票保持 open。

## Resolution

2026-09-03，Robert 批准单一 [ideation pipeline implementation specification](../../../agents/ideation-pipeline-spec.md)，并授权在全面自检通过后批准和发布实现票单。自检逐项确认了规格覆盖、Validation Matrix 全行归属、真实 blocking edges、单 fresh-context 粒度、第一票地基约束、expand-contract 顺序与三个 Canary 开放参数边界；原草案中过粗的 model-fixable/terminal 与 resume/isolation 责任被拆开，最终发布 13 张 tracer-bullet tickets 到 [implementation map](../../ideation-implementation/map.md)。

每张票映射至少一个 closed contract、引用其负责的具体 VM 行并要求 Robert 逐票验收；第一票只落依赖/测试/import guard 地基且不改 runtime 行为；中段只在 retriever 与 adapter 两条真正独立的路径并行，随后汇合为完整 Ideation Run；最后一票执行 legacy contract 与全量 handoff 验证。`reasoning_effort`、`max_tokens` 与 Workshop rendering variant 只保留受控 seam，不生成独立 implementation ticket，也未替 035/036 做结论。

面试叙事的剩余雾由已批准 [Delivery and Handoff](../../../agents/delivery-and-handoff.md) 的 Interview narrative 章节关闭：失败/降级发现按“现象 → Evidence Chain → Promotion Gate 决策 → 验证”独立成节，并先于最终结果呈现。Ticket 030 的关闭条件至此满足；035/036 继续保持 open，等待 implementation 后的 Canary evidence。

本次只发布规格与实现票单，没有修改 runtime、调用模型、生成 Canary evidence 或进入 downstream workflow。
