---
title: Define canaries and scale gates
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 015-establish-the-deepseek-provider-contract.md
  - 016-audit-metadata-gaps-and-enrichment-sources.md
  - 026-define-the-idea-quality-rubric.md
  - 027-define-the-validation-and-test-matrix.md
---

## Question

Which targets form a representative canary set, what cost and quality budgets apply, and which explicit gates and Robert approval permit scaling toward all 237 targets?

## Resolution

2026-08-30 经 grilling 三轮由 Robert 批准。完整契约落为独立文档 [docs/agents/canary-and-scale-gates.md](../../agents/canary-and-scale-gates.md)(v1.0),本 Resolution 只记决策摘要。

### 关键重构

Robert 将预算纪律定为成本驱动：canary 阶段 ¥30 硬上限（低谷期执行）;**面试任务不要求全量 237**,终波规模由面试需要决定。因此原 Question 中 "scaling toward all 237 targets" 的框架被修订——终波规模在扩量 gate 处按 canary 实测成本与面试叙事需要批准（预期 ~50）,009 的「系统支持全部 237」义务不受影响。

### 决策摘要

- **三波结构**:smoke(1 case)→ canary(12 case)→ 终波;Canary 集为 028 首跑验证与 035/036 比较实验共享的固定集合。
- **Canary 选择**:8 cluster 全覆盖（三大 cluster 各 2、其余各 1、含 1 个 strategy=2),reference 数覆盖 min/median/max 档，刻意纳入 2-3 个边缘案例（不可恢复 abstract、3-reference);规则筛选候选池 + Robert 点定；名单私有 manifest,repo 只存规则 + 摘要 + SHA-256。
- **成本**:¥30 硬上限覆盖 canary 阶段一切真实调用；执行优先队列 smoke → 035 high(12)→ 035 max(12)→ 重跑 → 036（裁剪为 3-case 变体臂，baseline 复用 035 胜方）;队尾截断，预算冲突回到 Robert。
- **质量门槛**：硬阻断清零（hygiene 命中 / isolation 违规 / preflight 绕过 / VM-QUAL-01 artifact 缺失）+ 每个已执行 case 最终有 success sealed run;gate 条件直接引用矩阵行 ID。
- **失败处理**：环境类 suspend/resume(025)；模型行为类归因 + 重跑一次 + 再败挂起；设计缺陷走 029 promotion gate。
- **终波**：串行、低谷期、2 批 + 批间检查点；Evaluation Artifact 维持逐 run 100% 强制，不引入抽样；**修订 031 为终波按批批准**(canary 阶段逐 run 批准不变）。

### 衍生动作

- 新建契约文档 `docs/agents/canary-and-scale-gates.md`(v1.0);CONTEXT.md 新增 Canary、Scale Gate 术语。
- 031 追加 028 修订指针；035/036 追加共享 Canary 与 ¥30 预算队列指针。
- 030 的 blocked_by 中本票一项随之解除（029 仍 open)。

本 ticket 只锁定 canary 与扩量决策；未实现 runtime code、未调用模型、未进入 downstream。
