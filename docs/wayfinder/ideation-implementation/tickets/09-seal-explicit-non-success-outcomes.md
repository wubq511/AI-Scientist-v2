---
title: Seal explicit non-success outcomes
type: implementation
status: closed
assignee: Robert
blocked_by:
  - 08-correct-model-fixable-actions.md
---

# 09: Seal explicit non-success outcomes

**What to build:** 让完整 control loop 对 Idea Leakage、全 run 无非空 Retrieval Result、retriever/evidence boundary failure 与其他确定性失败产生可解释的 terminal `failed` seal，并保证 terminal 条件不会被较低优先级的模型可修复错误掩盖。

**Blocked by:** 08: Correct model-fixable actions.

**Status:** closed

**Contract anchors:** [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Define the idea quality rubric](../../ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md), [Define the declared grounding contract](../../ideation-pipeline/tickets/038-define-the-declared-grounding-contract.md).

- [x] Finalization gate 固定按 raw-submission hygiene、structure、Declared Grounding、within-run duplicate 顺序执行，每轮只报告最高优先级结果。
- [x] Hygiene pattern 命中立即产生可信度受损的 terminal failure；它不能被 parse/structure/grounding feedback 覆盖或让模型修复后继续。
- [x] Run-level no-nonempty-retrieval backstop、确定性 adapter/retriever/evidence failures 与合法 `budget_exhausted` generations 汇总成批准的 Terminal Outcome 和 seal inventory。
- [x] Scripted malformed/unknown action、grounding lie、hygiene hit、duplicate 与 retrieval backstop scenarios 都从真实 CLI/controller seam 抵达预期终点。
- [x] 交付 `VM-CONTRACT-025-02`、`VM-CONTRACT-026-02`、`VM-INTEGRATION-03`、`VM-LEAKAGE-02` 与 `VM-FAULT-04`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，记录脱敏 failure evidence（参见 [non-success-outcomes-evidence.md](../../../research/non-success-outcomes-evidence.md)），且 Robert 完成本票验收。

## Resolution

2026-09-03 agent 交付（commits `55537d0`、`5165d78`），Robert 验收通过后关闭。核心落地：

- `FinalizeIdea` gate 重排为固定优先级 hygiene → structure → grounding → duplicate（`ai_scientist/ideation/controller.py`），每轮只报最高优先级一个结果；hygiene scan 在 ACTION/ARGUMENTS 解析之前对 raw submission bytes 执行（038「JSON parse 失败也照扫」），命中即 `hygiene_hit` 事件 + `hygiene-violation.json` 私有 artifact + 立即 terminal `failed` seal，不产生任何模型可见反馈，畸形提交也不会以 PARSE_ERROR 文本把私有标识符回灌给模型。
- 版本化 hygiene 模式列表 `payload-hygiene-patterns-v1.0.0` 从 023/024 标识符格式推导（case_id 形、SHA-256 hex、UUIDv4、run trust roots、内部证据子树、lifecycle 文件名）；检索 `paper_id`（40-hex）明确不命中。
- Terminal `failed` 封闭词汇三类（`TERMINAL_REASON_KINDS` 单一映射）：controller（hygiene/corrupt/backstop）、provider（022 taxonomy terminal 行）、retriever_evidence（020 boundary/audit 码）；未知 reason fail closed。sealed failed 携带完整 artifact inventory 与 terminal 事件（payload 带 `reason_code`/`reason_kind`/disposition 计数）。
- Suspend 类 adapter 失败与 storage/IO 失败（025 分级表 suspend 行）一律上抛、不 seal（Run Suspension 归 ticket 10）；`run()` 异常兜底只对 terminal 词汇 seal failed。合法 `budget_exhausted` generations 在 failed seal 的 `terminal_summary` 中如实保留。
- Run-level retrieval backstop 由抛异常改为 seal terminal `failed`（025 批准的 terminal 语义），`tests/test_sealed_ideation_run.py` 对应断言同步更新。

验收证据（2026-09-03，全零网络零费用）：全量 pytest 510 passed；compileall 与 black 通过；CLI help 逐字节 baseline 不变；025 二值表封闭互斥、terminal 与 model-fixable 词汇无交集、paper_id 零误报交叉检查通过；独立端到端 CLI 场景（case_id + run-root 泄漏提交）经真实 `_run_new_run` seam 抵达 `failed` seal 且 17 事件链验证通过。脱敏摘要见 [non-success-outcomes-evidence.md](../../../research/non-success-outcomes-evidence.md)。