---
title: Validate max-reasoning canary and completion limits
type: prototype
status: resolved
assignee: agent
blocked_by:
  - 029-define-the-optimization-promotion-gate.md
---

## Question

在已采用的 `cross-domain-v1` 下，统一使用 `reasoning_effort=max` 完成共享 12-case Canary，确认逐 case 的 idea 质量、运行完整性和 `max_tokens=32768` 的实际截断情况。无需再比较 `high` / `max`，无需证明 max 的性价比或相对优势。

**Specification:** [Max reasoning Canary 执行规格](../../../agents/deepseek-reasoning-effort-canary-spec.md).

## Current decision

2026-09-06，Robert 明确指示「不要考虑值不值了，直接用 max」。推理强度选择已经结束；此前建议的四对筛选与原 24-run 比较均取消。此决定是用户指定运行配置，不是模型对比实验的胜出结论。

本票转为单配置 Canary 运行验收，仍为 open：`max` 已选定，但 12-case 新配置覆盖及 completion limit 的充分性尚未验证。后续 agent 使用新 prompt + max 准备运行清单，复用已批准的输入，不重新开展 reasoning-effort 选型。`max_tokens=32768` 暂留，只在真实截断证据出现时处理，不顺带启动 token 参数矩阵。

每个新配置 run 使用现有双 AI 单条评审；本票无 high 对照臂，所以不生成 high/max pair packet 或四方向盲评。已有 high runs 保留为历史证据，不算作 max Canary 完成数。

## Acceptance criteria

- [x] 固定 `cross-domain-v1` + `reasoning_effort=max` 的新运行清单，不使用旧 24-run commands。（`035-max-canary` package run-matrix，12 slots，执行 pin `1b84128`）
- [x] 核对已批准 12-case selection/input manifests，按新配置统计覆盖；记录已有材料的使用/暴露情况，不把复用输入包装为全新独立测试。（selection sha256 `aae9d766…` 全 12 case Workshop/Corpus approved 复用；4 case 与 002 共享输入已在报告中披露）
- [x] 各已执行 case 的 Run Seal、验证、sanitized export、双 AI 单条评审与费用可回链；失败与未决如实保留。（12/12 sealed success、validate valid、exported、评审聚合完成；无失败、无 forfeited）
- [x] 记录 `finish_reason`、有效输出、截断、延迟与实际成本，给出 32768 的实测观察，不报告未经进行的 high/max 胜负。（34/34 attempts finish=stop，零截断；总成本 1.34 CNY）
- [x] 汇总 12-case 跨领域结果及扩量建议；费用按现有有效预算与授权范围执行，准备时重估 max 的调用成本。（[Max Reasoning Canary 结果报告](../../../agents/max-canary-035-results.md)）

## Resolution（2026-09-06）

**已完成并关闭。** Robert 批准全自动化执行（「我现在批准你直接跑大模型调用……我批准」），12 个 max Canary run 于 2026-09-06 凌晨全部完成：8 cluster 全覆盖、全部 sealed success、无截断（`max_tokens=32768` 保留有直接证据）、双 AI 评审 12/12 聚合（8 个维度弃权如实保留）。Canary 阶段累计成本 1.34 CNY（上限 30 CNY）。证据、质量汇总、限制与扩量建议见 [结果报告](../../../agents/max-canary-035-results.md)。reasoning effort 恒定 `max` 已作为执行默认 pin 入 runtime（commit `1b84128`）。036 若执行，以本 Canary 结果为基线臂。

## Notes

- 2026-08-30 [Define canaries and scale gates](028-define-canaries-and-scale-gates.md) 已定：本票的比较在共享 12-case Canary 集上运行，双臂共 24 次真实调用，计入 canary 阶段 ¥30 硬上限，执行顺序位于 smoke 之后、失败重跑与 036 之前（见 `docs/agents/canary-and-scale-gates.md` v1.0）。
- 2026-09-04 Robert 批准上述规格中的 Canary v1.1 constraint-driven 第 12 slot 与 035 Plan Gate；该批准不替代最终 12-case manifest 批准或逐 run 费用批准。本票随后在 zero-cost preparation 中被 claim，但从未开始 paid execution。
- 2026-09-04 **execution paused**：Robert 在首个 paid run 前确认 production prompt 与跨领域数据目标错配，Promotion Proposal 001 已以 0 runs / 0.00 CNY 撤回，原 24-run matrix 与 commands 只保留为 inactive evidence。先完成 [domain-neutral Prompt Profile 资格验证规格](../../../agents/cross-domain-ideation-prompt-spec.md)及其 [独立 tracker](../../ideation-prompt-neutralization/map.md)；只有 Prompt Proposal 002 经 Promotion Gate 后，才可在新 Design Epoch 重新规格化、估价和批准本票。当前 `assignee: agent` 仅作为 execution hold，任何会话不得执行旧命令或把旧 Plan Gate 当费用授权。

- 2026-09-06 **当前指令覆盖以上历史计划**：直接采用 max，解除原 reasoning-effort comparison 的 execution hold；旧 Proposal 001 继续 withdrawn。本票现在执行单配置 Canary 验收，不复活旧 Plan Gate 或命令。
