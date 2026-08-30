---
title: Define final delivery and commit sequence
type: grilling
status: open
assignee: Robert
blocked_by:
  - 027-define-the-validation-and-test-matrix.md
  - 028-define-canaries-and-scale-gates.md
  - 029-define-the-optimization-promotion-gate.md
---

## Question

How should implementation tickets, granular commits, reviews, work logs, run evidence, repository instructions, experiment report, and interview narrative form one reproducible handoff without claiming downstream work?

## Decision

2026-08-30 经 grilling 三轮由 Robert 批准。完整契约落为独立文档 [docs/agents/delivery-and-handoff.md](../../agents/delivery-and-handoff.md)(v1.0),本节只记决策摘要。

- **交付链**:wayfinder(决策)→ `/to-spec`(一份规格,落 `docs/agents/`,引用而不复述契约)→ `/to-tickets`(垂直切片票,落 `docs/wayfinder/ideation-implementation/`)→ `/implement`(tdd + code-review,单分支逐票提交)→ canary/终波(028)→ report(`docs/research/`,中文,committed)+ narrative(`docs/task/`,private)。
- **启动时机**:to-spec 待 021 关闭;035/036 留 open 至 canary 期,其三个参数(`reasoning_effort`/`max_tokens`/Workshop 变体)在 spec 中为显式开放点。
- **切片约束**:每票 acceptance criteria 引用矩阵行 ID;第一票为不改行为的地基票;改既有路径用 expand–contract(006);每票必须映射到已关闭契约票。
- **验收**:票关闭 = 矩阵行全绿 + 脱敏摘要 + Robert 逐票验收;commit 沿用既有纪律;合并 main/远程发布单独批准。
- **内容侧**:AGENTS.md 随行为变更票同 commit 同步,README 不动;report 七节骨架含 032 的 Evaluation fidelity 专节;narrative 以 Evidence Feedback Loop 为脊柱,失败/降级发现独立成节先于最终结果(回答了 map 的雾);话术边界 = 固定 scope 声明段 + 六条禁用措辞清单 + 入库前 checklist。

**关闭条件**(经 Robert 批准):spec 与实现票单经 Robert 批准后,由该 session 补写 `## Resolution`、关闭本票、更新 map 的 Decisions so far,并清算「面试叙事-失败发现」雾(其答案见契约文档 interview narrative 节)。在此之前本票保持 open。
