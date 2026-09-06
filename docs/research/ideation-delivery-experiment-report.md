# Ideation-Only 交付实验报告

状态：交付收尾版 v1.0 · 2026-09-06 · 经 Robert 授权的自动化收尾执行（「我批准相关操作……直到完成 delivery-and-handoff」；扩量必要性由 agent 裁决并经 Robert 认可）

## 1. 目标与范围

本项目仅覆盖 ideation：target-scoped 输入准备、本地冻结语料内的文献检索、idea 生成与校验。AI Scientist v2 的任何 downstream 阶段（BFTS、代码实验、绘图、LaTeX 写作、自动 review）均未执行，不在本交付范围内。本文全部结果仅涉及 idea 生成环节；IdeaBench 适配为 sealed qualitative comparator，未复现任何官方指标。

上游任务：把 AI Scientist v2 fork 改造为可复现、可审计的 ideation-only 系统——准备 target-scoped 输入、仅从配套 references 检索文献、调用 `DeepSeek-V4-Pro-0813`、隔离每次运行、校验每个输出，并通过可审计的 Evidence Feedback Loop 持续改进设计。

## 2. 设计原则与决策索引

设计权威是 wayfinder 决策 map 与契约文档，本节只做索引，不复述：

- **决策 map**：[Design an Auditable Ideation-Only Pipeline](../wayfinder/ideation-pipeline/map.md)（2026-09-06 全闭，38 张决策票索引见 map 的 Decisions so far）。
- **实现票单**：[ideation-implementation map](../wayfinder/ideation-implementation/map.md)（13 张 VM-anchored tracer-bullet 票全部关闭）。
- **核心契约**：[Ideation pipeline spec](../agents/ideation-pipeline-spec.md)（运行时语义）、[Validation matrix](../agents/validation-matrix.md)（验收行）、[Delivery and handoff](../agents/delivery-and-handoff.md)（交付链与话术边界）、[Canary and scale gates](../agents/canary-and-scale-gates.md)（三波执行与扩量 gate，v1.4 落账终波不执行）、[Promotion gate](../agents/promotion-gate.md)（设计变更治理）、[Cross-domain prompt spec](../agents/cross-domain-ideation-prompt-spec.md)（Prompt Profile 身份与比较协议）。
- **关键裁决链**：031 采用 DeepSeek direct 浮动 alias → 020/021 冻结 BM25 本地检索（k1=1.6, b=0.5, title_weight=1, max aggregation, paper_cap=3）→ 022/024 DeepSeek non-streaming adapter + 九步 fail-closed 准入 → 002 比较矩阵后 Robert 采用 `cross-domain-v1` 并退役 `ml-baseline-v1` → 035 期 Robert 直接指定 `reasoning_effort=max`（`1b84128` 单源 pin）→ 2026-09-06 扩量裁决：终波不执行、036 no-comparison-executed，map 全闭。

## 3. 方法

### 3.1 三波结构（契约 [028](../agents/canary-and-scale-gates.md)）

1. **smoke（1 case）**：私有 `case-229e495f…`，2026-09-03 低谷期执行，`run_id f7bddd3e`，Terminal Outcome `success`，实际 0.14 CNY（对照 7.08 CNY 峰值保守上界 -98%），23 事件 hash 链完整，[证据报告](live-smoke-execution-evidence.md)。
2. **canary（12 case）**：两个阶段——
   - **002 Prompt 比较矩阵**（8 runs，4 case × 2 profile）：`ml-baseline-v1` vs `cross-domain-v1`，reasoning_effort=high，双 AI 评审 + 成对盲评；Robert 看到证据后 post-evidence-adoption 采用 `cross-domain-v1` 并退役 baseline（裁决见 [002 promotion criteria](../agents/comparison-002-promotion-criteria.md)）。
   - **035 max Canary**（12 runs，12 case 单配置）：`cross-domain-v1` + `reasoning_effort=max` + `max_tokens=32768`，双 AI 评审（primary: deepseek-v4-pro；second: moonshot k3-256k）。
3. **终波（~50）**：**经 2026-09-06 扩量裁决不执行**——canary 证据已覆盖全部叙事需要（见 §6 与 [canary-and-scale-gates v1.4](../agents/canary-and-scale-gates.md)）。

### 3.2 Canary 选集（已批准 manifest，sha256 `aae9d766…`）

Robert 2026-09-04 批准的 12-case 名单：8 clusters 全覆盖（Health & Medicine 3、Genetics & Molecular Biology 2、Neuroscience & Cognitive Sciences 2、其余 5 clusters 各 1），硬性边缘全覆盖——min_ref(3)×2（slots 1、11）、median_ref(7)×2（slots 4、7）、max_ref(32)（slot 3）、`strategy=2` target（slot 4）、不可恢复 reference abstract（slot 12，`not_published` 真实边缘）。100% 新鲜：不含 smoke case 与 24 个 local-ranking 占用 targets。名单本体私有（gitignored），repo 只提交分层摘要与 SHA-256。

### 3.3 每次执行的固定语义

每次 Ideation Run：九步 fail-closed 准入（末道费用批准；比较包内 Robert 批量预授权 write-once 替代逐 run 交互）→ 本地冻结 BM25 检索（模型只提交 query，不能选择/切换 corpus）→ 3 轮 reflection 生成循环 → FinalizeIdea 结构 + declared grounding + payload hygiene 终局门 → 显式 seal（Terminal Outcome）→ 静态验证器独立重算 hash 链 → 白名单脱敏导出 → 逐 run 100% Evaluation Artifact → 记账。

## 4. 结果

### 4.1 运行覆盖与 Terminal Outcome

**035 max Canary（交付主矩阵）**：12/12 sealed `success`，每 run 1 个 finalized idea，零失败、零暂停、零卫生命中、零 forfeited。执行代码 pin `1b84128`；run-matrix digest `f73b2af8…`；批量预授权 write-once（Robert 批准记录在 `run-preauthorization.json`，早期草稿在 `superseded/` 保留审计链）。

| slot | cluster | run_id | refs 边缘 | 双 AI 评审 coverage |
|---|---|---|---|---|
| 1 | Environmental Sciences | `eb0ca2d0` | min_ref(3) | complete_unresolved |
| 2 | Genetics & Mol Bio | `5b185dec` | — | complete_resolved |
| 3 | Genetics & Mol Bio | `0838bcf1` | max_ref(32) | complete_unresolved |
| 4 | Health & Medicine | `6561a348` | median_ref(7), strategy=2 | complete_unresolved |
| 5 | Health & Medicine | `4db3c50b` | — | complete_unresolved |
| 6 | Materials Science | `1c1178b6` | — | complete_unresolved |
| 7 | Neuroscience & Cognitive | `362deff3` | median_ref(7) | complete_resolved |
| 8 | Neuroscience & Cognitive | `46b4b22a` | — | complete_unresolved |
| 9 | Public Health & Policy | `875f41ac` | — | complete_unresolved |
| 10 | Social & Behavioral | `79711a59` | — | complete_resolved |
| 11 | Technology & Engineering | `d84de057` | min_ref(3) | complete_unresolved |
| 12 | Health & Medicine | `5dc54c4b` | 不可恢复 abstract | complete_resolved |

（coverage 语义：`complete_resolved` = 七维全部共识判定；`complete_unresolved` = 存在证据不足型弃权维度，按协议如实保留，不强填。）

**002 比较矩阵（8 runs）**：8/8 sealed `success`，生成 0.79 CNY + forfeited 0.33 CNY；4 对盲评中 2 对 stable challenger 胜、2 对 `AI_PAIR_NOT_STABLE` fail-closed 拒绝（诚实保留，不重跑到满意）。

### 4.2 成本

| 阶段 | 实际支出 | 说明 |
|---|---|---|
| smoke | 0.14 CNY | 单 case，-98% vs 保守上界 |
| 002 矩阵生成 | 1.12 CNY | 8 slot（0.79）+ 2 forfeited（0.33） |
| 035 max Canary 生成 | 1.20 CNY | 12 runs（含 0.14 历史余额口径，见台账） |
| AI 评审（全部阶段） | 2.61 CNY | 25 笔台账：pair_review 1.21 + single_review 0.94 + repair 0.46 |
| **Canary 阶段总支出** | **约 2.32 CNY 生成 + 2.61 CNY 评审** | 硬上限 ¥30，使用率 <16% |

035 单 run 生成成本 0.07–0.13 CNY（off-peak 实测费率），峰值保守上界 7.08 CNY/run 仅作 reservation 预留。34 次生成 attempt 共 141,196 tokens（prompt 72,005 + reasoning 47,837）。

### 4.3 生成质量与 completion limit

- **34/34 provider attempt `finish_reason=stop`，零 `length` 截断**；单 attempt 最大 completion 6,499 tokens，远低于 32768 保留值。32768 无截断证据，但这不构成对更大规模任务的普遍充分性声明。
- 每次生成 attempt 由 run-local 原子提交 + writer-epoch fencing 隔离；resume 路径经全链重验证（ticket 10 语义）。

### 4.4 Evaluation Artifact 汇总（035 max Canary，12 run 全覆盖）

两位独立评审对每个 finalized idea 各自评审后逐维聚合（evidence_ref 逐字回链校验通过才成为有效记录）：

| 维度 | 共识判定分布 | 弃权 |
|---|---|---|
| relative_novelty | 12/12 `beyond_target` | 0 |
| feasibility_soundness | 12/12 `sound` | 0 |
| contamination_signal | 12/12 `none_found` | 0 |
| leakage_review | 11/12 `clean` | 1（run 6） |
| grounding_synthesis | 11/12 `synthesized` | 1（run 4） |
| problem_space_match | 10/12 `aligned` | 2（runs 5、8） |
| target_contribution_overlap | 4/12 `materially_different`、3/12 `partial_overlap` | 5（runs 1、3、5、9、11） |

84 维判定中 75 维达成共识（89.3%），9 个弃权如实保留。无任何维度出现负面共识（无 `within_target`、无 `questionable`、无 `leak_found`、无 `not_synthesized`）。弃权全部为证据不足型未决（评审对 target 贡献重叠等证据不足时按协议弃权），不是流程故障。

### 4.5 验证矩阵执行面

12-case 执行期内：每 run seal → `validate` valid → sanitized export → 双评审 → aggregate → ingest 链全部通过；VM-LEAKAGE-02 runtime hygiene 零命中；VM-QUAL-01 Evaluation Artifact 覆盖 100%；离线 pytest 899 passed（2026-09-06 复跑）；`compileall`/black 通过。

## 5. Evaluation fidelity 专节

（032 硬性要求）

- **术语纪律**：本文「Evaluation」一律指 sealed qualitative comparator——对每份 finalized idea 的结构化定性判定（七维 enum + rationale，无 numeric score、无 LLM judge 汇总分）。它**不是** IdeaBench 官方指标复现，不产生任何可与传统 pipeline 对比的数字分数。
- **与官方复现的区分**：IdeaBench 官方流程（LLM-as-judge 打分、novelty/feasibility 量化排序）未执行；Target Paper 在本系统中仅作为 post-seal 对照材料，用于判断 idea 与 target 的相对新颖性与贡献重叠，全程 sealed、不参与生成。
- **DeepSeek 参数化污染 caveat**：生成与 primary 评审同为 DeepSeek 系（deepseek-v4-pro）；`contamination_signal` 的机检范围限于本材料包，provider 侧训练数据暴露不可审计（各评审记录中 S011 审计范围声明逐字保留）。因此 12/12 `none_found` 只表示「材料包内未发现信号」，**不构成无训练污染的证明**。second 评审（moonshot k3-256k）跨家族复核缓解但不能消除该 caveat。

## 6. 失败与降级 run 的发现（Evidence Feedback Loop）

独立成节，先于结论呈现。这些中途失败与修复是本项目叙事的转折点，也是验证纪律价值的直接证据。

### 6.1 现象 → 证据链 → 决策 → 验证

**发现 1：单模型评审的位置翻转不稳定性（002 矩阵）**
- 现象：pair 3、pair 4 的成对盲评中，moonshot（kimi）评审在 A/B 与 B/A 两个方向给出不一致判断（ab tie → ba content_2），触发 `AI_PAIR_NOT_STABLE`。
- 证据链：4 份 pair reduction 记录（`artifacts/evaluations/pairs/*/reduction/v0001.json`）逐方向保留。
- 决策：程序拒绝重跑到通过（write-once，绝不 rerun to taste）；Robert 基于其余 stable 证据做 post-evidence-adoption 采用决定，不宣称预注册门槛通过。
- 验证：002 裁决记录逐条对照原判据表，如实标注 non-promote/inconclusive 与采用决定的修订性质。

**发现 2：reasoning_effort 双源配置缺陷（035 期）**
- 现象：admission 的 `reasoning_effort` 唯一来源是 `contract.py DEFAULT_REASONING_EFFORT`，而 `COMPARISON_REASONING_EFFORT` 解耦为 high，导致合成夹具 ingest 失败。
- 证据链：失败归因记录 + 修复 commit。
- 决策：Robert 指定「直接用 max」后，两源统一跟随单一 pin（`1b84128`），消除第二可变源。
- 验证：899 tests 全绿 + 035 执行包 digest 重算通过。

**发现 3：引文逐字校验在真实评审中的价值（035 run 8）**
- 现象：primary 评审连续 3 次 `CITATION_QUOTE_NOT_FOUND`——模型引用时丢掉引文首词（"Fit cross-validated…" 写成 "Cross-validated…"）。
- 证据链：3 次失败 attempt + 第 4 次成功，成本如实记入 evaluation-cost-ledger entries 23–25（0.46 CNY）。
- 决策：fail-closed 引文校验不放宽；文书性滑误走修复重试通道。
- 验证：run 8 最终 consensus v0004 六维共识达成，引文逐字回链通过。

**发现 4：评审费用与生成费用的账本分离**
- 现象：AI 评审引入后两类费用（生成 vs 评审）口径不同（评审含订阅端点零边际调用）。
- 决策：独立 `evaluation-cost-ledger`（write-once、hash-linked、25 笔 2.61 CNY）与生成 spend-ledger 分离，合并只读报告携带未授权支出披露。
- 验证：`tests/test_evaluation_costs.py` 23 项 + 迁移 rehearsal 17 项。

### 6.2 降级处理记录

- 002 slot 1 baseline 臂材料在真实 smoke 中被开发者观察 → 降级 development/diagnostic，采用裁决中明示权重（排除该对后采用依据依然成立）。
- pair 3/4 无 stable verdict → 诚实保留为不可判，不进入任何胜场统计。

## 7. 局限、caveats 与附录

### 7.1 局限与 caveats

1. **样本量**：交付主矩阵为单配置 12 runs，无统计功效声明；七维判定为定性共识，不支持跨模型或跨配置的显著性比较。
2. **无对照臂**：035 max Canary 是单配置运行验收；不构成 max 优于 high 的证据（reasoning-effort 选择由 Robert 直接指定，非实证比较）。
3. **评审弃权**：9/84 维度弃权如实保留；弃权集中度最高的是 `target_contribution_overlap`（5/12），反映评审在该维度上证据门槛严格。
4. **DeepSeek 参数化污染 caveat**：见 §5，全程适用。
5. **输入复用**：035 矩阵 4 个 case 与 002 矩阵共享已批准输入（复用不等于全新独立测试）；其余 8 个 case 为该输入集首次用于生成。
6. **32768 充分性**：仅在本 Canary 的任务分布上无截断证据，不外推。
7. **终波未执行**：~50 run 终波经必要性裁决放弃；对「样本量更大时结论是否稳定」没有证据。
8. **单机单卡环境**：全部执行于 Mac 控制器 + DeepSeek 远程 API，未经 Windows 执行器交叉验证（本任务无本地排序 bulk 计算，不触发该拓扑要求）。

### 7.2 附录：命令、commit 与 hash 索引

- **执行入口**：`python ai_scientist/perform_ideation_temp_free.py new-run`（七参数 + admission 批准）；`validate` / `export`（Evidence Chain）；评审与比较 CLI 见 [migration runbook](../agents/ai-review-migration-runbook.md)。
- **关键 commit**：执行 pin `1b84128`（reasoning max 单源）、`707ba22`（cross-domain-v1 唯一化）、`0c4e45d`（HEAD at delivery）。
- **运行证据**：私有 `artifacts/ideation-runs/<run_id>/`（request/admission/events/seal）；脱敏发布 `evidence/ideation-runs/<run_id>/`。
- **评审证据**：`artifacts/evaluations/<run_id>/ideas/000000/ai/`（primary/second/consensus）。
- **台账**：`artifacts/ideation-inputs/comparisons/035-max-canary/spend-ledger.json`（12 entries）；`artifacts/evaluations/evaluation-cost-ledger.json`（25 entries）。
- **输入 hash**：canary selection manifest `aae9d766…`、run-matrix digest `f73b2af8…`、逐 case workshop/corpus SHA-256 见 run-matrix.json。
- **验收**：pytest 899 passed（2026-09-06）；VM 行通过情况见 §4.5 与 [validation matrix](../agents/validation-matrix.md)。

### 7.3 话术检查声明

本报告入库前已按 [delivery-and-handoff](../agents/delivery-and-handoff.md) 禁用措辞清单逐项核对（6 项全部通过，核对记录见同 commit 的 session log）：未声称运行 BFTS/实验/绘图/write-up/review；未声称生成论文或复现 IdeaBench 官方指标；未暗示 downstream 能力被验证；未声称全局/远程文献检索；未声称 GPU/accelerator 训练；DeepSeek 参数化结论均携带 §5 污染 caveat。