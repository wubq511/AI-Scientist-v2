---
title: Guarantee Comparison Run Convergence and Slot Replacement
label: ready-for-agent
---

# 比较矩阵收敛保障与 Slot 更替规格

## Problem Statement

Robert 按已批准的 Proposal 002 执行 4-pair / 8-run Prompt Profile 盲测矩阵时，slot 1 的 Ideation Run 以 `success` Terminal Outcome 正常 seal，却没有产出任何 finalized idea：合同内的轮次管理指令从未强制收敛（末轮指令甚至暗示存在"下一次 attempt"），模型在三轮内合法地全部选择 SearchLiterature。这不是模型故障，而是仪器结构性失效——每个 run 是否产出 artifact 完全取决于模型自愿收敛，剩余 7 个 run 在两个臂上都有同样的失效概率。

在冻结合同下，这样的 run 永远无法进入 pair packet（packet 要求每个 sealed run 恰好持有一个 finalized idea）；本应拦截它的 ingest evaluation-coverage 闸门是不可达代码（判定函数只返回布尔值，而调用点检查 `None`），零产出 run 会"ingest 成功"并在 packet 构建时才爆炸；串行 slot 链没有跳过或替换机制——整个矩阵在已发生真实支出（0.10 CNY）的情况下硬死锁。任何代码修复都会移动 Git HEAD 并与 slot 1 锁定的 execution-code pin 冲突，使该 run 在新旧 pin 下都无法 ingest。

## Solution

两层修复，各自解决不同层级的失效。

**Layer 1 — 末轮确定性收敛（仪器保证）。** Ideation Controller 在最后一个 reflection round 上把 model-fixable 结果（解析失败、未知 action、选择 SearchLiterature、可修复的 FinalizeIdea 闸门拒绝）从"消耗整轮"改为"记录封闭的末轮纠正结果，并在同一 operation 的第二个 attempt 内纠正重问一次"。纠正请求携带显式的必须 FinalizeIdea 指令与具体失败反馈；仅当该 operation 恰好只消耗了一个物理 attempt 时才发起，且纠正调用禁用内部传输重试——物理 attempt 数永不超过 2，已批准的 7.08 CNY 最坏上界与冻结命令保持有效。模型自愿收敛的 run 与非末轮的 model-visible 字节逐字不变；两个 Prompt Profile 的模板零改动，被测变量零污染。纠正仍不收敛的 run 落 `budget_exhausted`，由 Layer 2 承接。

**Layer 2 — Slot 更替（合同容忍）。** 修复 ingest coverage 闸门为真正 fail-closed 后，无 finalized idea 的 sealed run（success 或 failed）不再可 ingest，唯一合法出口是 quarantine：一条 write-once 记录完整保存 run 身份、sealed 结果、实际成本、admission commit、reservation hash 与原因；其实际支出作为 forfeited spend 进入账本，计入 30.00 CNY 硬上限与 5.00 CNY 重审批阈值；同一 matrix slot 随后可用**完全相同的冻结命令**重新 reserve（reservation 文档带序号与 supersedes 链），每次重跑仍需 Robert 的逐 run 交互式批准。execution-code pin 获得显式的、经 Robert 批准的 supersede 路径：旧 pin 字节逐字保留，write-once supersede 记录链接新旧 commit，旧 epoch 的 sealed run 在 ingest 上继续 fail-closed。

迁移时，slot 1 的零产出 run 成为 quarantine 机制的第一个实例（0.10 CNY  forfeited 入账），矩阵以同一套冻结物料重开。

## User Stories

1. As Robert, I want every comparison run to deterministically end with a finalized idea, so that the matrix cannot produce empty arms.
2. As Robert, I want the convergence guarantee to live in the controller rather than in prompt text, so that it never depends on the model's voluntary compliance.
3. As Robert, I want the final-round correction to apply identically to both arms, so that the compared variable stays the Prompt Profile alone.
4. As Robert, I want convergent runs' model-visible bytes unchanged, so that happy-path evidence remains byte-comparable with the frozen contract semantics.
5. As Robert, I want the corrective re-ask to fit within the already-approved two-attempt worst case, so that the 7.08 CNY bound and frozen commands stay valid.
6. As Robert, I want no third physical attempt when a transport retry already consumed the second, so that approved cost bounds are never exceeded.
7. As Robert, I want a run that still refuses to finalize to end as `budget_exhausted`, so that residual non-convergence is handled by slot replacement rather than deadlock.
8. As Robert, I want the corrective instruction to carry the specific failure feedback, so that the model can actually repair its answer.
9. As Robert, I want final-round fixable FinalizeIdea gate rejections to also receive the corrective attempt, so that salvageable runs are not lost to fixable errors.
10. As Robert, I want non-final rounds' behavior unchanged, so that the contracted exploration freedom of earlier rounds is preserved.
11. As an operator, I want the correction recorded as a closed outcome code in the event chain, so that a resumed run reproduces the corrective request byte-identically.
12. As an auditor, I want the corrective attempt persisted as attempt 2 of the same operation with its own request and response artifacts, so that the Evidence Chain shows exactly what the model was asked.
13. As an operator, I want the ingest evaluation-coverage gate to actually reject zero-idea runs, so that unusable runs fail fast at ingest instead of exploding at packet build.
14. As an auditor, I want the previously unreachable coverage-gate path covered by a test, so that the gate cannot silently regress again.
15. As Robert, I want a sealed run without a finalized idea to be quarantinable, so that its slot can be retried.
16. As an auditor, I want quarantine to be a write-once record, so that forfeited runs remain permanent evidence.
17. As an auditor, I want the quarantine record to carry the run's identity, sealed outcome, actual cost, admission commit, reservation hash and reason, so that every forfeiture is fully attributable.
18. As an operator, I want quarantine to fail closed for runs holding a finalized idea, so that usable evidence can never be discarded.
19. As an operator, I want quarantine to fail closed for unsealed runs, so that a Run Suspension must be resumed to a Terminal Outcome first.
20. As an operator, I want quarantine to fail closed for already-ingested runs, so that ledgered results are immutable.
21. As an operator, I want quarantine to verify the run's admission commit belongs to a recorded code epoch, so that only legitimately admitted runs can be quarantined.
22. As an operator, I want a run mapped to its matrix slot by its case and arm identity, so that quarantine cannot be applied to the wrong slot.
23. As Robert, I want forfeited spend to count toward the 30.00 CNY hard cap, so that failed attempts cannot launder budget.
24. As Robert, I want forfeited spend to count toward the 5.00 CNY reapproval threshold, so that repeated failures trigger re-approval.
25. As an auditor, I want forfeited entries kept in a separate list from ingested entries, so that the sequential slot invariant and per-slot result identity stay intact.
26. As an auditor, I want every ledger total to remain recomputable from its entries, so that arithmetic drift stays fail-closed.
27. As an operator, I want the ledger schema version bumped and old-version files rejected, so that mixed-schema accounting is impossible.
28. As Robert, I want to re-run a quarantined slot with the same frozen command, so that the frozen material set stays byte-identical.
29. As an operator, I want the replacement reservation to be a new write-once sequenced document linked to its predecessor, so that reservation history is complete.
30. As an operator, I want re-reservation to require a quarantine record covering the latest reservation, so that an occupied slot still fails closed without one.
31. As an operator, I want the slot-order gate unchanged, so that a later slot still cannot start before the replacement run ingests.
32. As Robert, I want every replacement run to require my fresh interactive approval, so that every spend stays individually approved.
33. As Robert, I want re-pinning to require my explicit approval record, so that code epochs change only by governance.
34. As an auditor, I want the old pin bytes preserved verbatim and a write-once supersede record linking old and new commits, so that epoch transitions are auditable.
35. As an operator, I want old-epoch sealed runs to keep failing ingest after re-pin, so that mixed-epoch results cannot enter the matrix.
36. As an operator, I want quarantine to be the only exit for old-epoch zero-idea runs, so that slot 1's forfeited run has exactly one defined disposal.
37. As Robert, I want slot 1's forfeited 0.10 CNY recorded in the ledger, so that stage accounting stays honest.
38. As an operator, I want re-freezing to assert the run-matrix and commands bytes unchanged, so that the frozen-material drift check is exercised.
39. As Robert, I want the Proposal 002 amendment to record the root cause, the two-layer design, the schema bumps and the slot 1 disposal, so that the governance trail is complete.
40. As Robert, I want all new behavior proven by deterministic offline tests with zero provider calls, so that the fix itself costs nothing.

## Implementation Decisions

- 修改的模块只有两个：Ideation Controller（末轮纠正）与 comparison 边界模块（coverage 闸门修复、quarantine、账本、reservation 序号化、pin supersede）。runner CLI、admission、Prompt Profile registry、冻结合同文本全部不变。
- Controller 末轮纠正机制：末轮 model-fixable 结果记录为新增的封闭 outcome code（指示名 `FINAL_ROUND_CORRECTION`），照旧产出 feedback artifact 与 action_outcome 事件；仅当该 operation 恰好消耗一个物理 attempt 时，以相同 operation sequence、初始 attempt 2 发起纠正调用，且该调用内部传输重试禁用；纠正请求 = 原轮 messages + controller 常量纠正后缀 + 具体反馈文本；纠正结果重新进入正常 dispatch，FinalizeIdea 走既有 finalize 路径；仍不收敛或 attempt 预算已被传输重试占用时落 `budget_exhausted`。
- Resume 可重现性：纠正后缀是否注入由事件链中记录的纠正 outcome 决定，resume 重建轮次 prompt 时按同一规则重放，字节一致。
- 新接口：`quarantine_comparison_run`（校验 sealed、零 finalized idea、未 ingest、(case, arm) 唯一映射 slot、最新 reservation 未被覆盖、admission commit 属于已记录 epoch）与 `supersede_execution_code_pin`（旧 pin 字节移入 superseded 区、写 write-once supersede 记录、创建新 pin）。
- 新文档 schema：quarantine 记录 `comparison-run-quarantine-v1.0.0`；reservation 文档升 `comparison-run-reservation-v1.2.0`（新增 `reservation_seq` 与 `supersedes_reservation_sha256`）；pin supersede 记录（链接 old/new commit、reason、时间戳）。
- 账本 schema v1.2.0 → v1.3.0：新增 `forfeited_entries` 独立列表与 `forfeited_spend_cny` 派生字段；`comparison_actual_spend_cny` 语义不变（仅 ingested）；`total_stage_spend_cny` = historical + ingested + forfeited；硬上限、重审批阈值、reservation 投影守卫全部使用含 forfeited 的总额；ingested entries 的严格顺序 [1..N] 与 run_id 唯一不变式不变，run_id 跨两列表唯一，同一 run_index 在两个列表中各至多出现一次。
- Reservation 序号派生：`seq = 1 + 该 slot 的 quarantine 记录数`；seq ≥ 2 要求最新 quarantine 覆盖最新 reservation，否则维持 `COMPARISON_SLOT_ALREADY_RESERVED`。
- Epoch 成员校验：run 的 admission commit ∈ 当前 pin ∪ supersede 记录中的历史 pin；旧 epoch run 在 ingest 继续 `EXECUTION_CODE_PIN_MISMATCH`，唯一出口是 quarantine。
- 迁移操作序列（属发起会话职责，不在本规格的实施范围）：旧 v1.2.0 账本字节逐字移入 `superseded/`（既有先例），生产 freezer 幂等重写六项物料并断言 run-matrix 与 commands 字节不变；pin supersede 到新 HEAD；quarantine slot 1 的零产出 run（forfeited 0.10 CNY 入账）；Robert 以同一条冻结命令重跑 slot 1。
- 为什么用 controller 强制而非 prompt 强制：prompt 层面的保证是概率保证，且已被 slot 1 证伪；profile 模板是被测变量，必须保持冻结。
- 为什么 forfeited spend 计入上限：花掉的钱就是花掉了，否则失败循环可以绕过硬上限。

## Testing Decisions

- 好测试的标准：只在既有 seam 上断言外部可观察行为（事件、artifact、账本、拒绝码），确定性、全离线、零 provider 调用；不断言内部实现细节。
- Seam 1（最高，既有）：comparison slot 边界——prepare/reserve/ingest/quarantine/ledger 经合成 E2E harness 驱动，真实 git workspace + 脚本化 transport。Prior art：`tests/test_prompt_comparison.py` 72 测试与模块级 8-run envelope fixture、`tests/comparison_synthetic.py` 的 sealed-run 助手。
- Seam 2（既有）：controller 模型边界——StubTransport 脚本化响应穿过生产 adapter 与真实 controller。Prior art：`tests/test_model_fixable_actions.py` 的恢复脚本、`tests/test_sealed_non_success_outcomes.py` 的 budget-exhausted 配方（与生产失效逐字同构）。
- Seam 3（既有）：runner CLI 腿 subprocess，clean/dirty worktree 双态。Prior art：既有 pin 测试中的 CLI 腿。
- 零 idea sealed run 的测试配方复用 sealed-non-success 测试；本规格不引入任何新 seam。
- TDD 先红后绿；每个 commit 提交前跑全量套件；happy-path 字节等价性必须显式断言（收敛 run 的任何 request 不含纠正字节）。

## Out of Scope

- run-matrix、commands、Prompt Profile 模板、预算数字（30.00 / 5.00 / 7.08）、runner 脚本的任何变更。
- 迁移序列的执行（重冻结、pin supersede、quarantine、slot 1 重跑交付）——属发起会话。
- BFTS、实验、绘图、写作、评审等一切下游阶段。
- 多 idea run、verdict/reducer 语义变更、"不收敛判负"之类的评分语义。
- prompt 内容本身的进一步优化（被测变量冻结）。

## Further Notes

- 本规格是 Proposal 002 的 remediation 规格；治理落账（修订案、Validation Matrix 新行、ticket 02/03 post-close 补记）随实施的 docs commit 完成，并应把本规格链接进 Proposal 002 修订记录。
- 实施中发现 coverage 闸门 `EVALUATION_ARTIFACT_MISSING` 自引入起不可达（判定函数只返回布尔值）；本规格将其修复为真正的 fail-closed，并以测试锁定。
- slot 1  forfeited 成本 0.10 CNY 由事件链中 adapter 打戳的 `cost_cny` 精确求和（0.02 + 0.02 + 0.06），已含周末低谷费率。
- pin 更换 pinned commit 按既有纪律需 Robert 显式批准新 Design Epoch；他对本修复方向的确认即覆盖此次 re-pin，迁移时须在 supersede 记录的 reason 中引用该批准。
- 实施会话的 handoff 包：`/tmp/ai-scientist-v2-handoff.hrEPFn/`（`HANDOFF.md` + `PLAN.md`，PLAN.md 含精确 seam、TDD 清单与 commit 序列）；本规格是该会话 code-review 的 Spec 轴依据。
