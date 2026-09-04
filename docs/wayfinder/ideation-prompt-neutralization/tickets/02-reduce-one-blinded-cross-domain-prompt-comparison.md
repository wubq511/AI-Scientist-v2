---
title: Reduce one blinded cross-domain prompt comparison
type: implementation
status: open
assignee: null
blocked_by:
  - 01-admit-and-replay-one-versioned-prompt-profile.md
---

# 02: Reduce one blinded cross-domain prompt comparison

**What to build:** 在 Prompt Profile 已可审计运行后，提供一个完整的离线 comparison boundary，用 synthetic sealed evidence 证明从四例选择、8-run 顺序、盲包、实际支出累计、write-once verdict 到 Promotion reduction 的全流程可确定性重放；全票不使用真实 case 内容、credential 或 provider。

**Blocked by:** 01: Admit and replay one versioned Prompt Profile.

**Status:** ready-for-agent

**Specification:** [Cross-domain Ideation Prompt qualification](../../../agents/cross-domain-ideation-prompt-spec.md).

- [ ] comparison input 只接受已批准 12-case Canary manifest identity 与四个规定 cluster；每个 cluster 以 canonical case hash 选择一例，拒绝缺 cluster、重复 case、非 Canary case、source hash drift 或读取 Target contribution/result 后再选择。
- [ ] 生成严格 4 对、8 runs 的 frozen matrix，exactly 2 对 baseline-first、2 对 challenger-first；两臂除 Prompt Profile id/hash 外，Workshop/Corpus hashes、model、reasoning effort、max tokens、generation/reflection budgets、retriever、rubric 与 runtime controls 必须逐字段相同。
- [ ] 生成独立 frozen blind mapping，exactly 2 对 A=baseline、2 对 A=challenger；model-visible/Robert-visible pair packet 隐藏 profile、执行顺序、cost、latency、usage、attempt count 和 provider metadata，且 reveal 在所有可用 write-once verdict 冻结前 fail closed。
- [ ] 生成 credential-free exact commands，只使用生产 parser 实际支持的参数与项目 credential wrapper；命令文本不得含 key、环境赋值、自动 `yes`、Target title 或 unsupported `--reasoning-effort`/`--max-tokens` 参数，并以 parser contract 测试证明可执行。
- [ ] append-only spend ledger 从 0.00 CNY 开始，能按 run ingest success、failed、suspended、resume 与 physical attempts 的实际 usage/cost；精确执行 Plan Gate 子上限、30 CNY Canary 总上限、exact-bound acceptance 与 one-cent-over refusal，且不能把 Plan Gate 当逐 run 批准。
- [ ] result ingestion 在产生 pair packet 前验证 Run Specification/profile identity、case/input hashes、Run Seal、Evidence Chain、sanitized export、Evaluation Artifact coverage、finish reason、attempt topology、latency 和 actual cost；不完整、corrupt、drifted 或 cross-case evidence fail closed。
- [ ] Robert pair verdict 使用 `a_better`、`b_better`、`tie`、`incomparable` 封闭结果，并记录 overall、domain-method fit、unjustified ML intrusion 与 rationale；artifact write-once，不能覆盖、删除不利 verdict 或在 reveal 后补判。
- [ ] deterministic reducer 实现规格全部门槛：3–0 quality threshold、4/4 completeness、domain-method 至少两对改善且零回退、ML intrusion 不增加、既有 rubric 底线、deterministic 零容忍、无 challenger-only truncation/failure/retry，以及 cost/median-latency 2.0 倍包络。
- [ ] synthetic tests 覆盖每个边界与失败分支，并证明相同输入产生 byte-identical manifest、matrix、blind mapping、ledger state、pair packets 和 reduction；测试不得访问网络、活动 `.env`、真实 Target identity 或 private live-run artifacts。
- [ ] 提交脱敏 schema、命令形状、测试结果和 rollback 证据并关闭本票；不生成最终私有 selection、不修改 Proposal 002 state、不调用模型、不产生费用、不执行 ticket 035 或 Downstream Experiment。
