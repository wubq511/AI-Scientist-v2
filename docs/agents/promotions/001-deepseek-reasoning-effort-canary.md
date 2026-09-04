---
id: 001-deepseek-reasoning-effort-canary
state: plan-approved
filer: agent
created: 2026-09-04
---

## 问题与证据

在 Ticket 01/02 建立可审计的真实 DeepSeek 执行通道并完成单 Case smoke 运行（`run_id: f7bddd3e-cd3c-4f66-9b6d-7d30c25c1db0`，实测耗费 0.14 CNY、耗时 176s，产出首个封印成功的 grounded idea 并完成 100% 定性评审）之后，当前系统缺乏实证数据判断 `reasoning_effort=high` 与 `reasoning_effort=max` 哪一个在科研构想生成中质量更优，亦无法确认首轮配置的 `max_tokens=32768` 是否足以完全避免 reasoning 思维链或最终 JSON 载荷截断。

若仅凭经验直觉选定参数，后续 Canary 与 Scale Gate 证据将建立在未经验证的设计基线之上。因此依据 ticket [035: Compare DeepSeek reasoning effort and completion limits](../../wayfinder/ideation-pipeline/tickets/035-compare-deepseek-reasoning-effort-and-completion-limits.md) 与规范 [DeepSeek Reasoning Effort Canary 比较规格](../deepseek-reasoning-effort-canary-spec.md)，启动首个严格治理的 Optimization Promotion 流程。

- 脱敏 Smoke 证据：[真实低谷期单 Case Live Smoke 运行证据报告](../../research/live-smoke-execution-evidence.md)
- 本地原始 Smoke 证据：`artifacts/ideation-runs/f7bddd3e-cd3c-4f66-9b6d-7d30c25c1db0/`

## 假设

- **可证伪假设**：在代表性 Canary 集、相同输入、prompt、retriever、rubric 与 `max_tokens=32768` 约束下，`reasoning_effort=max` 产生的构想定性评审质量明显优于 baseline `reasoning_effort=high`，且不引起确定性破坏、截断、失败率上升，且实际成本与中位延迟增幅控制在 2.0× Regression Budget 内。
- **单主变量声明**：Challenger 与 Baseline 仅在单一主变量 `reasoning_effort` 存在差异（Baseline 为 `high`，Challenger 为 `max`）。模型版本（`deepseek-v4-pro` alias）、API 协议、提示词、四段式 Workshop、检索参数（BM25 `k1=1.6, b=0.5, paper_cap=3`）、轮次预算（`max_num_generations=1, num_reflections=3`）、最大完成令牌数（`max_tokens=32768`）、以及验证和评测规则完全一致。

## 备选方案

1. **主观推断与经验主义选择**：凭 smoke 成功经验直接宣布 `high` 胜出或凭直觉切换至 `max`。
   - *取舍*：缺乏样本多样性与因果对比证据，极易引入确认偏误，违反 Evidence Feedback Loop 核心纪律，已排除。
2. **多变量同时网格搜索**：在同一批次同时交叉对比 `reasoning_effort`（`high` / `max`）与 `max_tokens`（`16384` / `32768` / `65536`）。
   - *取舍*：混淆因果归因，成倍消耗有限的 Canary 预算（超出 30 CNY 硬上限），已排除；本提案锁定 `max_tokens=32768` 仅作充分性观测，若有截断另起单变量提案。
3. **复用 Local-Ranking 既有批次**：复用 `lr-op-*` 等 12 个历史 case。
   - *取舍*：其抽样分布不满足 8 clusters 全覆盖与重点 cluster 权重，缺乏 3-ref 真实边缘，数据便利性不可凌驾于实验严谨性，已排除。

## 对比方案

- **Baseline Run Specification**：当前固定配置（`reasoning_effort=high`, `max_tokens=32768`）；
- **Challenger Run Specification**：仅变更推理强度（`reasoning_effort=max`, `max_tokens=32768`）；
- **Canary 集**：Canary v1.1 经 Robert 批准的 12 paired cases（涵盖 8 clusters 全覆盖、重点领域各 2、1 个 constraint-driven edge slot、覆盖 min/median/max 档、含 3-ref 与不可恢复 abstract 真实边缘）；
- **执行拓扑**：12 对、24 次 Ideation Runs，串行执行于低谷优惠期；预先冻结 6 对 high-first、6 对 max-first 确定性顺序；
- **验证矩阵行清单**：VM-CONTRACT-018-02, VM-CONTRACT-019-01, VM-CONTRACT-020-02, VM-CONTRACT-022-01, VM-CONTRACT-026-02, VM-INTEGRATION-01, VM-REPLAY-02, VM-LEAKAGE-01, VM-LEAKAGE-02, VM-LEAKAGE-04, VM-ISOLATION-01, VM-ENV-01, VM-QUAL-01；
- **成本估价**：Smoke 实测校准预测总支出 3.36–6.72 CNY；全流程受 30 CNY Canary 硬上限约束，每 run 准入前需经 7.08 CNY 最坏上限校验与 Robert 交互批准。

## Pre-registered 判据

1. **质量晋升门槛 (Promotion Threshold)**：
   - 全量 12 对必须 100% 完成并封印；
   - 经隐藏推理强度、成本、延迟与调用顺序的盲审 A/B Evaluation Packet 评审后，Robert 写入一次性裁定；
   - 揭盲后，`max` 必须至少胜出 7 对，且 `high` 胜出不得超过 2 对（即 `max_wins >= 7` 且 `high_wins <= 2`）；
   - 平局（`tie`）与不可比（`incomparable`）不归入任何一方胜场。
2. **完整性与中立性要求**：
   - 任何因预算截断、未恢复中断或门禁失败导致的残缺矩阵，一律判为 `inconclusive`，自动维持 baseline `high`，严禁以部分样本宣告胜出。
3. **分维度 Regression Budget**：
   - **Deterministic 层**：零容忍。任何 baseline 为 pass 而 challenger 为 fail 的静态门禁或测试行，直接触发自动拒绝（reject）；
   - **截断与容量**：零容忍。24 次 run 中发生任何 `finish_reason=length` 或内容截断，自动否决 32768 充分性结论，并拒绝晋升；
   - **成本包络**：Challenger 12 runs 实际总支出不得超过 Baseline 12 runs 实际总支出的 2.0 倍；
   - **延迟包络**：Challenger 12 runs 端到端耗时中位数不得超过 Baseline 中位数的 2.0 倍；
   - **异常与失败**：Challenger 不得产生仅在 max 臂出现的不可恢复挂起、非预期重试激增或非预期的异常模式。

## 预期失败模式

1. **深度推理耗时过长触发环境超时**：由 controller 捕获转为 Run Suspension，走 suspend/resume 恢复；
2. **Completion 长度超限截断**：若模型耗尽 32768 tokens 产生残缺 JSON，留存证据，自动拒绝晋升并维持 `high`；
3. **反思批判缺乏多样性**：模型在深度反思轮次中生成相似度过高的 query 或重构方案，被去重机制拒绝；
4. **累计支出超出 30 CNY 硬上限**：系统在准入估价前 fail-closed 停止，结果记录为 inconclusive；
5. **两臂定性构想质量无显著差异**：若平局居多导致 `max` 胜场未达 7 场，自动 fail-closed 维持 baseline `high`。

## 实验证据

*实验尚未启动（处于付费前准备阶段，实际已发生调用 0 次，实际支出 0.00 CNY）。待后续阶段完成后回填脱敏证据摘要。*

## Plan Gate 记录

- **批准日期**：2026-09-04
- **批准人**：Robert
- **批准内容**：Canary v1.1 选集修正、单主变量 `high` vs `max` 对比方案、双盲 Evaluation Artifacts 裁决机制、7 胜 2 负质量晋升门槛、2.0× 成本与延迟 Regression Budget、以及 30 CNY 硬上限。
- **锁定版本**：[DeepSeek Reasoning Effort Canary 比较规格](../deepseek-reasoning-effort-canary-spec.md)（label: `ready-for-agent`）。

## Promotion Gate 记录

*待对比实验执行、脱敏证据归档、双盲评审完成并揭盲后，由 Robert 对照 Pre-registered 判据正式宣判。*
