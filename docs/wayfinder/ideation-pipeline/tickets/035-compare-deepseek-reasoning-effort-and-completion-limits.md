---
title: Compare DeepSeek reasoning effort and completion limits
type: prototype
status: open
assignee: agent
blocked_by:
  - 029-define-the-optimization-promotion-gate.md
---

## Question

在相同的代表性 canary、冻结输入、prompt、adapter、validation 和 idea-quality rubric 下，`reasoning_effort=high` 与 `reasoning_effort=max` 哪一个产生更高质量的 ideation 结果；首轮 `max_tokens=32768` 是否足以避免 reasoning 或最终 JSON 截断，以及在不降低质量的前提下应保留什么 completion limit？比较必须记录输入、配置、输出、usage、`finish_reason`、延迟、成本与失败，先给出该次运行的成本预估并取得 Robert 批准，不得进入 Downstream Experiment。

**Specification:** [DeepSeek Reasoning Effort Canary 比较规格](../../../agents/deepseek-reasoning-effort-canary-spec.md).

## Notes

- 2026-08-30 [Define canaries and scale gates](028-define-canaries-and-scale-gates.md) 已定：本票的比较在共享 12-case Canary 集上运行，双臂共 24 次真实调用，计入 canary 阶段 ¥30 硬上限，执行顺序位于 smoke 之后、失败重跑与 036 之前（见 `docs/agents/canary-and-scale-gates.md` v1.0）。
- 2026-09-04 Robert 批准上述规格中的 Canary v1.1 constraint-driven 第 12 slot 与 035 Plan Gate；该批准不替代最终 12-case manifest 批准或逐 run 费用批准。本票随后在 zero-cost preparation 中被 claim，但从未开始 paid execution。
- 2026-09-04 **execution paused**：Robert 在首个 paid run 前确认 production prompt 与跨领域数据目标错配，Promotion Proposal 001 已以 0 runs / 0.00 CNY 撤回，原 24-run matrix 与 commands 只保留为 inactive evidence。先完成 [domain-neutral Prompt Profile 资格验证规格](../../../agents/cross-domain-ideation-prompt-spec.md)及其 [独立 tracker](../../ideation-prompt-neutralization/map.md)；只有 Prompt Proposal 002 经 Promotion Gate 后，才可在新 Design Epoch 重新规格化、估价和批准本票。当前 `assignee: agent` 仅作为 execution hold，任何会话不得执行旧命令或把旧 Plan Gate 当费用授权。
