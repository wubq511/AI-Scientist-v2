---
title: Define the optimization promotion gate
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 023-define-run-identity-and-evidence-layout.md
  - 026-define-the-idea-quality-rubric.md
  - 027-define-the-validation-and-test-matrix.md
---

## Question

What issue template, hypothesis record, comparison method, regression threshold, and approval step turn Evidence Feedback Loop findings into accepted design changes?


## Resolution

2026-08-30 经 grilling 两轮九题由 Robert 批准。完整契约落为独立文档 [docs/agents/promotion-gate.md](../../../agents/promotion-gate.md)（v1.0），本 Resolution 只记决策摘要。

### 定位与边界

- 路由规则：「更好」→ promotion，「错了」→ bugfix（豁免，走正常 commit + 验证矩阵既有行测试），「还没定」→ wayfinder。凡证据驱动的设计变更——calibration-pending 阈值收紧、版本化规则集修订、prompt 围栏内文本、retrieval ranking 参数、模型参数化——一律过本 gate。

### 机制

- 载体：版本化契约文档 `docs/agents/promotion-gate.md` + 提案实例 `docs/agents/promotions/NNN-<slug>.md`（脱敏提交、原始证据本地留存，010）；契约修订 = 新版本 + Robert 批准。
- 双 gate：Plan Gate（花钱前批准假设、pre-registered 判据、对比方案与成本估价，024 逐次估价纪律）+ Promotion Gate（只对照 Plan Gate 锁定的判据宣判，不引入新裁量）。
- 对比方法：baseline = 当前 pin 的 Run Specification 在同一 Canary 集（身份归 028）上对照，challenger 仅差一个主变量（012）；证据 = 验证矩阵行 ID（deterministic 层两侧全绿）+ 假设点名的改进指标 + Robert 对两侧 Evaluation Artifacts 的结构化质量比较（032/037）。
- Pre-registration：pass/fail 判据 + 分维度 Regression Budget（deterministic 零容忍、成本包络、质量语句）为必填字段，Plan Gate 锁定；超预算或预算外维度意外回退 = 自动 reject。
- Design Epoch：每次 promotion 开启新 epoch，canary/scale 证据仅同 epoch 内可比，028 的 scale gate 只消费当前 epoch 证据；由既有 spec pins（023/027/034）天然实现，不新增 runtime 字段。
- 生命周期：`proposed → plan-approved → evidence-complete → promoted | rejected`，pre-promoted 任意状态可 `withdrawn`；fail-closed 缺省 = pin 住的设计不变；agent 与 Robert 均可提案，两道 gate 仅 Robert 批准。
- 回滚 = 假设为「旧版本更好」的 Promotion Proposal，Plan Gate 可采纳已有证据批准零新增成本方案；紧急 fail-closed halt 免 gate、永远立即，设计变更永不跳过 gate。

衍生动作：CONTEXT.md 新增 Optimization Promotion、Promotion Proposal、Plan Gate、Promotion Gate、Regression Budget、Design Epoch 六术语；map 追加索引行。030 的 blocked_by 中本票一项随之解除（030 仍待 028）。

本 ticket 只锁定 promotion gate 决策；未实现 runtime code、未调用模型、未进入 downstream。
