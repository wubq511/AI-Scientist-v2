# Max Reasoning Canary 结果报告（ticket 035）

状态：执行完成，待 Robert 验收 · 2026-09-06 · 执行规格 [Max reasoning Canary 执行规格](deepseek-reasoning-effort-canary-spec.md)（2026-09-06 修订节）

## 执行摘要

Robert 于 2026-09-06 明确指示「直接用 max」并批准全自动化执行（「我现在批准你直接跑大模型调用……我批准」）。本报告是这次批准的交付结果。

**核心结论：12/12 case 全部成功完成，`reasoning_effort=max` + `max_tokens=32768` 无任何截断，实际总成本 1.34 CNY（Canary 硬上限 30 CNY 的 4.5%），双 AI 单条评审 12/12 完成聚合。completion limit 32768 有直接证据支持保留。**

## 运行覆盖

固定配置：`cross-domain-v1` prompt profile、`deepseek-v4-pro`、`reasoning_effort=max`、`max_tokens=32768`、`max_num_generations=1`、`num_reflections=3`、retriever policy v1.0、rubric v1.0.0。执行代码 pin：`1b84128`（reasoning max pin commit）。已批准的 12-case selection manifest（sha256 `aae9d766…`）与 Workshop/Corpus approvals 全部复用，prior-use 标识如实保留。

| # | cluster | run_id | outcome | 双 AI 评审 |
|---|---|---|---|---|
| 1 | Environmental Sciences | eb0ca2d0 | success | complete_unresolved |
| 2 | Genetics & Mol Bio | 5b185dec | success | complete_resolved |
| 3 | Genetics & Molecular Biology | 0838bcf1 | success | complete_unresolved |
| 4 | Health & Medicine | 6561a348 | success | complete_unresolved |
| 5 | Health & Medicine | 4db3c50b | success | complete_unresolved |
| 6 | Materials Science | 1c1178b6 | success | complete_unresolved |
| 7 | Neuroscience & Cognitive Sciences | 362deff3 | success | complete_resolved |
| 8 | Neuroscience & Cognitive Sciences | 46b4b22a | success | complete_unresolved |
| 9 | Public Health & Policy | 875f41ac | success | complete_unresolved |
| 10 | Social & Behavioral Sciences | 79711a59 | success | complete_resolved |
| 11 | Technology & Engineering | d84de057 | success | complete_unresolved |
| 12 | Health & Medicine (edge: unavailable abstract) | 5dc54c4b | success | complete_resolved |

8 个 cluster 全覆盖；edge requirements（min_ref(3)×2、max_ref(32)、median_ref、exactly-3-references、unavailable reference abstract）由既有 selection manifest 满足。历史 high runs 保留为历史证据，未计入 max coverage。

## Completion limit 观测（32768 充分性）

全部 34 次 provider attempt 的 `finish_reason` 均为 `stop`，零 `length` 截断。单 attempt 最大输出 6,499 tokens（run 5），推理 token 单 attempt 最高 7,462（评审侧），远低于 32768。**32768 在本 Canary 中无截断证据，按规格保留；这不构成对更大规模任务的普遍充分性声明。**

## 成本与延迟

- 生成实际支出：12 runs 合计 **1.14 CNY**（off-peak 实测费率结算，逐 run 见 package spend-ledger）；加 smoke 历史余额，Canary 阶段累计 **1.34 CNY**。
- 最坏上界 7.08 CNY/run 仅作预留，未接近；每 run 1–3 次 physical attempt，无重试消耗。
- AI 评审支出：累计 2.61 CNY（含 run 8 的 3 次 citation-repair 重试），记录于 evaluation-cost-ledger entries 23–25。
- 逐 run 延迟与 usage 在各 run Evidence Chain 内可回链（`artifacts/operations/*/attempts/*/response.json` 的 usage 与 audit）。

## 双 AI 单条评审质量汇总

两位独立评审（primary: deepseek-v4-pro；second: moonshot k3-256k）对 12 个 finalized idea 各自评审后聚合：

- **relative_novelty**：12/12 `beyond_target`
- **feasibility_soundness**：12/12 `sound`
- **contamination_signal**：12/12 `none_found`
- **leakage_review**：11/12 `clean`，1 弃权（run 6）
- **grounding_synthesis**：11/12 `synthesized`，1 弃权（run 4）
- **problem_space_match**：10/12 `aligned`，2 弃权（runs 5、8）
- **target_contribution_overlap**：4/12 弃权（runs 1、3、5、9）——评审对 target 贡献重叠证据不足时按协议弃权，不强填

84 个维度判定中 76 个达成共识判定（90.5%），8 个弃权如实保留，未强行投票。所有 evidence_ref quote 通过逐字回链校验后才成为有效记录。

**Run 8 评审修复记录**：primary（deepseek）连续 3 次在 S007 引文逐字校验失败（第 3 次重试成功）。根因是模型在引用时丢掉引文首词（"Fit cross-validated…" 写成 "Cross-validated…"），非材料缺陷。3 次修复调用的成本如实记入 evaluation-cost-ledger（entries 23–25）。这印证了 fail-closed 引文校验在真实评审中的价值。

## 失败、未决与限制

- 生成阶段零失败、零暂停、零卫生命中；无 forfeited slots。
- 评审弃权维度如上，均为证据不足型未决，不是流程故障。
- 本矩阵是单配置运行验收：**没有 high 对照臂，不构成 max 优于 high 的证据，也不需要**。reasoning-effort 选择已由 Robert 直接指定并结束。
- 四个 case 与 002 矩阵共享已批准输入（复用不等于全新独立测试）；其余 8 个 case 为该输入集首次用于生成。

## 扩量建议

按 canary-and-scale-gates v1.3 的执行队列，Canary 已完成。实测单 run 成本 0.07–0.13 CNY（off-peak）支持以 ~50 run 终波估算总生成成本约 3.5–8 CNY（不含评审）。扩量 gate 决策（终波规模与预算）待 Robert 批准；036（Workshop 变体比较）若执行，以本 max Canary 结果为基线臂。

## 私有证据位置

- 生成：`artifacts/ideation-runs/<run_id>/`（seal、events、operations、exports）
- 评审：`artifacts/evaluations/<run_id>/ideas/000000/ai/`（primary/second/consensus、evidence cards）
- 台账：`artifacts/ideation-inputs/comparisons/035-max-canary/spend-ledger.json`（12 entries，总 1.34 CNY 含 0.14 历史）
- 预授权：`artifacts/ideation-inputs/comparisons/035-max-canary/run-preauthorization.json`（Robert 批准记录，sha256 见文件；两份早期草稿在 `superseded/` 保留审计链）