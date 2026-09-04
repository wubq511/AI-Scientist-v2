---
title: Qualify one auditable live smoke run
type: task
status: open
assignee: null
blocked_by:
  - 01-enable-auditable-live-deepseek-execution.md
---

# 02: Qualify one auditable live smoke run

**What to build:** 在第一张票证明真实执行入口符合契约后，使用现有 approved Workshop 与 Approved Target Reference Corpus 运行一个低谷期、单 case、单 generation 的 DeepSeek V4 Pro smoke，并把该 run 从费用批准、provider attempts、Terminal Outcome 一直验证到 Evidence Chain、sanitized export 和 post-seal Evaluation Artifact 覆盖。

**Blocked by:** 01: Enable auditable live DeepSeek execution.

**Status:** ready-for-agent

**Specification:** [Auditable live DeepSeek execution and one-case smoke](../../../agents/live-smoke-execution-spec.md).

**Contract anchors:** [Define canaries and scale gates](../../ideation-pipeline/tickets/028-define-canaries-and-scale-gates.md), [Compare DeepSeek reasoning effort and completion limits](../../ideation-pipeline/tickets/035-compare-deepseek-reasoning-effort-and-completion-limits.md), [Define the validation and test matrix](../../ideation-pipeline/tickets/027-define-the-validation-and-test-matrix.md), [Define the post-seal evaluation artifact contract](../../ideation-pipeline/tickets/037-define-the-post-seal-evaluation-artifact-contract.md).

- [ ] 只有在第一张票关闭、仓库工作树 clean、当前 commit 与 dependency lock 固定、DeepSeek 官方 endpoint/model/parameter/pricing 重新核对、本地 credential 存在且账户可用后，才能准备付费 smoke；检查和记录不暴露 credential 值。
- [ ] Smoke 仅使用已批准的单一私有 case 及其当前 hash-pinned Workshop/Corpus，固定 `max_num_generations=1`、`num_reflections=3`、`reasoning_effort=high`、`max_tokens=32768`、DeepSeek direct non-streaming Chat Completions，不变更 prompt、retriever、rubric 或其他 Canary 参数。
- [ ] 在任何 provider request 前显示峰值费率、全 cache miss、每轮最多两个 attempts 的 7.08 CNY 保守上界，并由 Robert 对该 exact run 交互输入 `yes`；本 spec、本 ticket 或早前批准都不替代这次费用批准。
- [ ] 运行尽量安排在官方低谷时段，且完整保留 commit SHA、dataset/input hashes、reference count、command、provider/model/configuration、timestamps、Provider Attempts、usage、`finish_reason`、latency、实际 CNY cost、Terminal Outcome、validation result、failures 与 output hashes 的私有 Evidence Chain。
- [ ] 任何 preflight rejection 均证明零 provider request；环境/模糊失败按已批准 taxonomy 保持 unsealed suspension，确定性失败 seal `failed`，不做 provider/model/endpoint/validation fallback。模型行为失败最多允许一个新 run，且必须另做当次估价与 Robert 批准；疑似设计缺陷进 Promotion Gate 而不就地修补。
- [ ] 对 sealed smoke 运行执行静态 Evidence Chain validation；非 corrupt 时产生通过全部发布门禁的 byte-idempotent sanitized export，不得修复、重封、导出或评估 corrupt run。
- [ ] 为 smoke 中每个 finalized idea assemble 一份 hash-linked private Evaluation Brief；Robert 作为唯一定性判分者填写 draft，工具验证并写入 write-once Evaluation Artifact，`list-coverage` 证明该 smoke 所有应评 idea 都被覆盖；不使用 LLM judge 或数字分。
- [ ] 提交脱敏 smoke 报告与 session log，记录为什么结果可信、估算与实测成本偏差、成功/失败/降级发现、保留的私有 evidence 路径和脱敏 hash 索引；报告不含 prompt、response、reasoning、idea、Target identity、provider response ID、credential、host identity 或绝对路径。
- [ ] 本票只证明 1-case live smoke；不 claim/close 035/036，不选择最终 reasoning effort/completion limit/Workshop variant，不执行 12-case Canary、24-run 比较、Scale Gate、终波或任何 downstream workflow，且 Robert 完成本票验收。
