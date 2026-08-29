---
title: Compare DeepSeek reasoning effort and completion limits
type: prototype
status: open
assignee: null
blocked_by:
  - 029-define-the-optimization-promotion-gate.md
---

## Question

在相同的代表性 canary、冻结输入、prompt、adapter、validation 和 idea-quality rubric 下，`reasoning_effort=high` 与 `reasoning_effort=max` 哪一个产生更高质量的 ideation 结果；首轮 `max_tokens=32768` 是否足以避免 reasoning 或最终 JSON 截断，以及在不降低质量的前提下应保留什么 completion limit？比较必须记录输入、配置、输出、usage、`finish_reason`、延迟、成本与失败，先给出该次运行的成本预估并取得 Robert 批准，不得进入 Downstream Experiment。
