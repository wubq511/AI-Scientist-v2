---
id: 002-cross-domain-ideation-prompt
state: plan-approved
filer: Robert
created: 2026-09-04
---

## 问题与证据

当前唯一生产 ideation prompt 来自面向 machine-learning research subfield 的上游 AI Scientist-v2 baseline，包含 `AI researcher`、`top ML conferences`、`conference format`、`precise algorithmic changes`、固定 `evaluation metrics` 与通用 `academic lab` 资源表述。该目标与本项目的跨领域 IdeaBench 数据和原始任务不一致。

本地 237 个已聚类 targets 覆盖八个科学领域；其中 Health & Medicine 与 Genetics & Molecular Biology 各 76 个，另有 Environmental Sciences、Materials Science、Neuroscience & Cognitive Sciences、Public Health & Policy、Social & Behavioral Sciences、Technology & Engineering。原始任务要求生成科研 idea、为每个 Target Paper 派生 Workshop，并把检索限制在对应 references，没有要求所有构想成为 ML 论文。

首个社会/行为科学 live smoke 最终方案引入 RoBERTa fine-tuning、macro-F1 与 domain transfer。单例不足以证明 prompt 的因果效果，但与显式 ML 指令方向一致，构成需要比较验证的早期行为信号。静态审计同时确认现有 prompt 测试只检查工具和 grounding 围栏，没有领域中立性回归断言。

- 规格：[跨领域 Ideation Prompt 资格验证规格](../cross-domain-ideation-prompt-spec.md)
- 治理依据：[Optimization Promotion Gate](../promotion-gate.md)
- 私有原始证据：现有 live smoke、冻结 Canary selection 和本提案后续生成的 comparison package；均保留在 gitignored roots。

## 假设

- **可证伪假设**：在四个方法学差异显著的 Canary cases、相同输入、模型、`reasoning_effort=high`、`max_tokens=32768`、retriever、rubric 和运行预算下，`cross-domain-v1` 相比字节语义保持的 `ml-baseline-v1` 能显著提高 domain-method fit、减少不必要的 ML/benchmark framing，同时不降低 problem-space match、relative novelty、feasibility soundness、retrieval grounding synthesis 与整体可用性。

## 对比方案

- **Baseline**：`ml-baseline-v1`，保持当前生产 prompt 的 model-visible 语义；
- **Challenger**：`cross-domain-v1`，采用规格中批准的 multidisciplinary role、field-appropriate methods、领域相称 feasibility、field-neutral Abstract 与 validation-plan 语义；
- **Cases**：从已冻结 12-case Canary 中，对四个 pre-registered clusters 依据确定性 `canonical_case_hash` 仲裁各选出一例，共 4 对、8 个 Ideation Runs：
  - `Materials Science`: `case-589dbcb35662706939b2f0d6dfd32800`
  - `Social & Behavioral Sciences`: `case-2a08725ced2acab00c56dc9db7d4a7c3`
  - `Genetics & Molecular Biology`: `case-5f3f2126efc376031caf6acf4d1d4c59`
  - `Health & Medicine`: `case-8c6ddd334df3bf058720ac8f14ce3db6`
- **固定参数**：`reasoning_effort=high`、`max_tokens=32768`、`max_num_generations=1`、`num_reflections=3`、`model=deepseek-v4-pro`，retriever policy v1.0，rubric v1.0.0，其余 Run Specification 逐字段完全相同；
- **执行代码 pin**：8 个 run 必须在同一 clean Git HEAD 下执行。首个 slot reservation 以 exclusive-create `0600` 写入 package 私有的 `execution-code-pin.json`；之后每个 slot 启动时要求当前 clean HEAD 等于 pin（dirty worktree 以 `DIRTY_WORKTREE` 拒绝），result ingestion 逐 run 比对 `admission.code.commit` 与 pin（`EXECUTION_CODE_PIN_MISMATCH` fail closed）。stale pin 永不静默删除；更换 pinned commit 需 Robert 显式批准新 Design Epoch；
- **顺序与盲法**：2 对 baseline-first、2 对 challenger-first；2 对 A=baseline、2 对 A=challenger；映射在运行前 hash-frozen，Robert 写完所有可用 verdict 后才能揭盲；
- **验证矩阵行**：VM-CONTRACT-COMPARE-01, VM-CONTRACT-COMPARE-02, VM-CONTRACT-COMPARE-03, VM-CONTRACT-COMPARE-04, VM-CONTRACT-018-02, VM-CONTRACT-019-01, VM-CONTRACT-020-02, VM-CONTRACT-026-02, VM-INTEGRATION-01, VM-REPLAY-02, VM-LEAKAGE-01, VM-LEAKAGE-02, VM-LEAKAGE-04, VM-ISOLATION-01, VM-ENV-01, VM-QUAL-01；
- **环境与依赖锁定**：Python 3.13 参考栈，锁定 `requirements.txt` 与 `requirements-dev.txt`；
- **成本与预算核算**：
  - 8 个 runs 的非权威预测为 1.12–2.24 CNY（参考 live smoke 实测 0.14 CNY/run）；
  - Canary 阶段总硬上限：30.00 CNY；
  - 历史已发生实际支出：0.14 CNY（单 case smoke 产生）；
  - 当前 Canary 阶段剩余预算：29.86 CNY；
  - 拟议本提案 Plan Gate 累计实际支出重审批阈值：`plan_gate_reapproval_threshold_cny = 5.00 CNY`；它不是硬上限。某个已逐 run 批准的请求可能在结算后跨过阈值，账本必须如实记录并在下一 slot 前要求重新审批；
  - Canary 唯一硬上限为 `30.00 CNY`。每个 run 前由 guarded slot runner 按当前 stage 实际支出加 `7.08 CNY` 高峰最坏上界做 reservation，只有 projected ceiling `<= 30.00 CNY` 才会立即 exec 生产 `new-run`；
  - 每个 run 仍需 Robert 在生产 admission 中交互式逐 run 批准 `7.08 CNY` 最坏上界。Plan Gate、aggregate reservation 与逐 run `yes` 三者互不替代。

## Pre-registered 判据

1. **完整性**：4 对、8 个 runs 全部获得可验证 Run Seal、sanitized export 和完整 Evaluation Artifact；缺一即 `inconclusive`，不得用完成子集晋升。
  - pair packet 的 idea payload 现以 per-arm sealed idea SHA-256 绑定到 Evidence Chain，verdict 与 packet hash 在 reduction 处复核（`VERDICT_PACKET_MISMATCH` fail closed）。
2. **盲审胜负**：揭盲后 challenger 至少胜 3 对，baseline 胜 0 对；tie 不计胜，`incomparable` 使矩阵不完整。
3. **Domain-method fit**：challenger 至少 2 对严格优于 baseline，且 4 对中没有任何一对更差。评审必须区分“合理采用 ML”与“无问题/证据依据的 ML intrusion”。
4. **既有质量底线**：challenger 不得引入 `problem_space_match=mismatched`、`feasibility_soundness=unsound`、`grounding_synthesis=name_dropped`、contamination signal 或 leakage；任一出现自动拒绝。
5. **Deterministic Regression Budget**：零容忍。profile schema/hash、Run Request/Admission、resume、replay、Evidence Chain、export、leakage、isolation、import/dependency、CLI 与 execution-code pin（`admission.code.commit` 必须等于 pinned clean HEAD）任一 baseline-pass/challenger-fail 或 drift 均自动拒绝。
6. **截断与异常**：challenger 不得新增 `finish_reason=length`、completion truncation、terminal failure、unresumable suspension、physical attempt 或仅 challenger 出现的异常模式。
7. **成本与延迟**：challenger 实际总成本不得超过 baseline 的 2.0 倍；challenger 端到端中位延迟不得超过 baseline 的 2.0 倍；每个 live slot 必须通过 `current stage actual + 7.08 CNY <= 30.00 CNY` 的请求前硬上限 reservation。累计实际支出达到 `5.00 CNY` 时，下一 slot 必须重新取得 Plan Gate 批准；已逐 run 批准请求产生的阈值跨越被记录，不伪装成可事后撤销的硬限额。
8. **Fail-closed 结果**：任何判据未通过均保持现有代码默认，但 035 和 Scale Gate 继续暂停；“challenger 未通过”不等于“已知目标错配 baseline 合格”。

## 预期失败模式

1. 领域中立措辞过于宽泛，导致 proposal 缺少可操作的验证设计；
2. 保留的 `Experiments` key 继续把非实验研究拉回实验或 benchmark framing；
3. “不要默认 ML”被模型过度解释，导致本应使用计算方法的 case 回避合理 ML；
4. Workshop/检索文献提供的领域信号不足，challenger 只能生成泛化模板；
5. 两臂除 prompt 外出现 Run Specification drift，使 pair 失去可比性；
6. 盲包泄露 profile、执行顺序、成本、延迟或模型元数据；
7. 任一 run 失败、挂起、截断或因预算停止，矩阵变为 inconclusive；
8. 实际成本显著高于 smoke 外推，触发 `5.00 CNY` 重审批阈值，或使下一 run 的 `7.08 CNY` reservation 无法装入 `30.00 CNY` Canary 硬上限。
9. 执行代码在矩阵期间漂移（跨 commit 运行或 dirty worktree 启动），把 runtime 变化混入单变量归因；由 execution-code pin 在 slot 启动与 ingestion 两处 fail closed 防护。

## 实验证据

*尚未启动付费调用。当前新增 provider 调用 0 次，Proposal 002 实际支出 0.00 CNY。准备工作（Tickets 01/02/03）已全部完成，全套离线对比物料已冻结落盘，等待 Robert 在 originating session 审批 Plan Gate。*

### 冻结私有对比物料清单 (SHA-256)

所有对比物料均物化于被 `.gitignore` 保护的私有目录 `artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/`：

- **4-Case 选集清单 (`selection-manifest.json`)**：`b09488322ce934e1aca1ce3020791240a23c6f55a68eee2dc66a14c3076bc83f`
- **选集批准记录 (`selection-approval.json`)**：`9944dc5e4d00fc6aaec1f541ccc6bb7481bca8a36e3634a3a6e63bcf49e893ba`
- **8-Run 运行矩阵 (`run-matrix.json`)**：`c8a9217ffcf60718cc132ef04688bdf0bd3bd23758f0e54373993e1237d78ef4`（自验签 `matrix_sha256`: `c60d72748d8ab6aa06e712332e4bee2b4b7cf275b7f34ba58c210c09f5d963c3`）
- **双盲平衡映射 (`blind-mapping.json`)**：`a605f3755b7bfeeb6497f6e27a9bc1e3f6f36822155497f1c9f19d85388f0a9e`
- **初始花费账本 (`spend-ledger.json`)**：`12708349c183a2fafbeb352fdf84abcec972c3275b5029e609b9173045b985ed`（`comparison-spend-ledger-v1.3.0`；含 0.14 CNY 历史 opening balance、5.00 CNY 重审批阈值与 30.00 CNY 硬上限；2026-09-05 修订案重冻结后更新，旧 v1.2.0 字节 `56562175…` 逐字归档于私有 `superseded/v1.2.0-pre-quarantine/spend-ledger.json`）
- **CLI 运行命令 (`commands.txt`)**：`3851ca37ed6fdc9fe2c634238d865693db4f3663859f9d1c6bcedc2b62664af6`（8 条命令均经项目 credential wrapper 进入 `scripts/run-prompt-comparison-slot`，并携带 frozen matrix file SHA-256 与 `5.00 CNY` threshold 外部 pin，不再绕过 aggregate preflight）
- **执行代码 pin (`execution-code-pin.json`)**：付费期 runtime 产物，当前不存在；首个 slot reservation 时 exclusive-create（`0600`，`comparison-execution-code-pin-v1.0.0`），其 hash 在创建后纳入对账记录，不改动上列冻结物料。

### 代码与运行基准

- **当前准备完成 Commit SHA**：`ac34ab773ae1f1882b89c8c30e7fb7cd87f2f7e9`（execution-code pin 修复 commit；覆盖首 slot write-once pin、后续 slot clean-HEAD 等值、ingestion `admission.code.commit` 比对与 stale pin 保留）。此前为 `696176c9a9395601e2fcba23b02f3555aa46c179`（付费前 budget/slot guard 修复）。
- **依赖栈基准**：Python 3.13.2 reference stack, pinned dependencies.
- **零网络验证**：`tests/test_prompt_comparison.py` 72 passed；Prompt Profile 相关聚焦集 104 passed；全量 suite 766 passed；真实私有 package 的越序 slot 在 reservation/provider 前以 `PREVIOUS_SLOT_NOT_INGESTED` 拒绝，dirty worktree 下 slot 1 启动以 `DIRTY_WORKTREE` 拒绝，两次检查均未产生 pin/reservation 状态变化。新增 provider 调用 0 次，新增实际支出 0.00 CNY。

## Plan Gate 记录

- **状态**：`plan-approved`（Robert 于 2026-09-05 批准；执行模式经比较后选定方案 A：保持串行合同，利用周末低谷时段执行，人工盲审与 provider 等待流水线化；并行方案未采纳）
- **批准 Artifact**：私有 package 内 `plan-gate-approval.json`（write-once `0600`，`comparison-plan-gate-approval-v1.1.0`），SHA-256 `6ad3b448bd439b7ae6b028dafda4c1c22107e73928ebb780eaf364ce62c5f003`；记录 `approved_by=Robert`、`planned_runs_count=8`、stage 总账 `0.14 CNY`、重审批阈值 `5.00 CNY`、硬上限 `30.00 CNY`、`scope=matrix_reapproval_threshold_not_per_run`
- **准备完成日期**：2026-09-04
- **已批准内容**：
  - 4-case selection manifest 与 8-run frozen matrix 散列；
  - 2/2 执行顺序平衡与 2/2 A/B 双盲映射；
  - 累计实际支出重审批阈值 `5.00 CNY`：stage 总账当前为 `0.14 CNY`，距离下一次重审批触发点为 `4.86 CNY`；阈值不是硬上限，任何跨越都必须如实入账，并在下一 slot 前暂停；
  - Canary `30.00 CNY` 硬上限：当前剩余 `29.86 CNY`，每个 slot 前用当时实际总账加 `7.08 CNY` 峰值最坏上界做 reservation；exact `30.00` 可进入，`30.01` fail closed；同一 slot 在 exec 前写入 write-once `0600` reservation，重复/并发启动拒绝；
  - 执行代码 pin：首个 slot reservation 在私有 package 写入 write-once `execution-code-pin.json`（记录批准当时的 clean Git HEAD）；之后 7 个 slot 与全部 8 次 ingestion 必须等于该 commit，任何 drift/dirty/missing 均 fail closed，stale pin 保留为证据；
  - 3 胜 0 负盲审胜负、domain-method fit 改善、ML intrusion 不增与 2.0× Regression Budget 门槛；
  - 声明：Plan Gate 审批仅批准矩阵级架构与重审批阈值，不替代每个 run 准入前的独立交互式费用确认，也不替代请求前的 30 CNY aggregate reservation。

## 收敛保障与 Slot 更替修订 (2026-09-05, remediation)

- **修订案状态**：`plan-approved`（Robert 于 2026-09-05 确认两层修复方向并批准编码实施；正式规格见[比较矩阵收敛保障与 Slot 更替规格](../comparison-convergence-slot-replacement-spec.md)，`ready-for-agent`）。
- **根因（已确认）**：slot 1 run `966d0fdc-8add-4980-a818-c8cb3157e38b` 以 `success` 正常 seal 但 0 个 finalized idea——三轮全部 SearchLiterature，末轮反思指令（baseline profile 模板）无强制收敛语义且"In the next attempt"暗示存在下一轮。定性为仪器结构性缺陷而非模型故障：是否产出 artifact 完全取决于模型自愿收敛，其余 7 个 run 在两臂上均有同样失效概率。实际支出 0.10 CNY（事件链 `provider_attempt.finished.cost_cny` 之和：0.02+0.02+0.06，含周末低谷费率）。
- **合同缺陷**：现行合同下零产出 run 会在 pair packet 构建时才以 `RUN_CORRUPT` 爆炸（packet 要求每 run 恰好一个 finalized idea）；ingest 的 evaluation-coverage 闸门因判定函数只返回 bool 而不可达（`EVALUATION_ARTIFACT_MISSING` 自引入未触发过）。串行 slot 链无跳过/更替机制，矩阵在已发生真实支出下硬死锁；任何代码修复都会移动 HEAD 并与 slot 1 锁定的 execution-code pin 冲突。
- **Layer 1 — 末轮确定性收敛（controller）**：最后一个 reflection round 的 model-fixable 结果（解析失败、未知 action、SearchLiterature、可修复 FinalizeIdea 闸门拒绝）不再消耗整轮，而是记录封闭 outcome `final_round_correction`（末轮搜索为新封闭错误码 `FINAL_ROUND_FINALIZE_REQUIRED`），并在同一 operation 的 attempt 2 发起一次纠正重问：request = 原轮 messages + controller 常量纠正后缀 + 具体反馈，纠正调用禁用内部传输重试——物理 attempts ≤ 2，已批准 7.08 CNY 最坏上界与冻结命令保持有效。仅当该 op 恰好只消耗 attempt 1 时才纠正（attempt 2 已被传输重试占用则不再发起，直接 `budget_exhausted`）。模型自愿收敛的 run 与非末轮的 model-visible 字节逐字不变；两个 Prompt Profile 模板零改动，被测变量零污染；resume 按事件链重建纠正 request，字节一致。纠正仍不收敛 → `budget_exhausted`，由 Layer 2 承接。
- **Layer 2 — Slot 更替（comparison）**：coverage 闸门修复为真正 fail-closed 后，零 finalized idea 的 sealed run（success 或 failed）不可 ingest，唯一合法出口是 quarantine：write-once `0600` 记录 `comparison-run-quarantine-v1.0.0` 保存 run 身份、sealed 结果、事件链派生的实际成本、admission commit、covering reservation hash 与原因 `ZERO_FINALIZED_IDEA`，前置校验（已 seal、零 idea、未 ingest、(case, arm) 唯一映射冻结 slot、最新 reservation 未被覆盖、admission commit 属于已记录 epoch）全部 fail closed；实际支出作为 forfeited entry 进入账本计入 30.00 硬上限与 5.00 重审批阈值。被 quarantine 的 slot 可用同一条冻结命令重新 reserve（reservation 升 `comparison-run-reservation-v1.2.0`，新增 `reservation_seq` 与 `supersedes_reservation_sha256`，seq = 1 + 该 slot quarantine 记录数；seq ≥ 2 要求最新 quarantine 覆盖最新 reservation），每次重跑仍需 Robert 逐 run 交互式批准。execution-code pin 获得显式 supersede 路径：旧 pin 字节逐字移入 `superseded/`、write-once supersede 记录链接新旧 commit 与批准 reason；旧 epoch sealed run 在 ingest 继续 `EXECUTION_CODE_PIN_MISMATCH`，唯一出口是 quarantine。
- **账本 schema**：`comparison-spend-ledger-v1.2.0 → v1.3.0`：新增 `forfeited_entries` 独立列表与 `forfeited_spend_cny` 派生字段；`comparison_actual_spend_cny` 语义不变（仅 ingested）；`total_stage_spend_cny` = historical + ingested + forfeited；硬上限、重审批阈值与 reservation 投影守卫全部使用含 forfeited 的总额。ingested entries 的严格顺序 [1..N] 与 run_id 唯一不变式不变；run_id 跨两列表唯一。同一 slot 在重跑链上可产生多条 forfeited 条目（每条对应一个真实的零产出 run），全部计入总额——本条对规格字面（"同一 run_index 在两个列表中各至多出现一次"）作了诚实记账方向的解释：seq-3 需要第二条 quarantine 记录，而第二次失败的钱同样必须入账，否则失败循环可洗白预算。
- **slot 1 处置（已批准；迁移序列由 originating session 执行）**：run `966d0fdc` 以 quarantine 退出，forfeited 0.10 CNY 入账；账本总额 0.14 + 0.10 = 0.24 CNY，slot 1 投影 0.24 + 7.08 = 7.32 ≤ 30.00 ✓ 且低于 5.00 重审批阈值；随后以同一条冻结命令重跑 slot 1。迁移序列：重冻结（旧 v1.2.0 ledger 字节移入私有 `superseded/v1.2.0-pre-quarantine/`；六项物料幂等重写，断言 run-matrix `c8a9217f…` 与 commands `3851ca37…` 字节不变，仅 spend-ledger 变为 v1.3.0 新字节）→ pin supersede 到新 HEAD（reason 引用本修订批准）→ quarantine `966d0fdc` → 交付同一条 frozen slot 1 命令。重冻结完成后，本文件"冻结私有对比物料清单"的 spend-ledger SHA-256 应更新为 v1.3.0 新值，其余五项不变。
- **实现与验证**：commits `bf92ea0`（coverage gate 修复）、`2d61d6a`（controller 末轮收敛）、`dec4058`（slot 更替）、`a02d8cd`（评审修正）；全量 pytest 787 passed，零 provider 调用、零新增支出；Validation Matrix 新增 VM-CONTRACT-COMPARE-06；ticket 02/03 已补记。
- **实现偏差记录**：adapter（`deepseek.py`）新增 `max_attempts` 参数——规格字面写"修改的模块只有两个"，但"纠正调用禁用内部传输重试"必须在 adapter 的 attempt 循环上实现；默认值保持既有行为，属规格要求的最小机制。

## Post-Seal AI 评审工具化说明 (2026-09-05, versioned addendum)

- **范围**：仅登记工具存在与效力边界，不修改本提案任何 pre-registered 判据、Regression Budget 或盲审语义。post-seal 单条 idea 的 AI 评审已按 [AI 辅助 Ideation 评审规格](../ai-assisted-ideation-evaluation-spec.md) 与 authoring contract v2 完成离线编码验收（tracker ticket 01，评审记录 schema `evaluation-ai-review-record-v2.0.0`，VM-QUAL-02）。
- **效力边界**：AI 评审记录作者类型为 AI、无晋升效力；本提案对比矩阵的判分在 ticket 03 的评审修订获 Robert 显式批准前，仍完全由 Robert 按 v1 人工 Evaluation Artifact 合同执行；旧 Promotion Gate 对 AI 记录继续拒绝。采用 AI 评审替代人工判分属于「首条输出产生后的评估协议修订」，须披露并单独批准，本条不构成该批准。
- **费用边界**：本 addendum 登记的离线验收零 provider 调用、零支出；真实 smoke（六次基础调用）属未来执行输入，需 exact model 配置、费用上界与数据出站授权，并按既有 stage 预算口径单独列项。

## 评估协议修订说明 (2026-09-05, versioned addendum 二 — ticket 03)

- **范围**：ticket 03 交付的是**消费侧离线机制**，不是判据修订。已实现并离线验收：comparison ingestion 的 AI 双评审覆盖分支（`evaluation_artifact_v2_ai`，与 v1 人工 `evaluation_artifact_v1` 分支并列）、ComparisonVault 的 write-once AI 判定通道（`ai-verdicts/`，schema `comparison-ai-verdict-v1.0.0`，与 Robert 盲审 `verdicts/` 分离）、以及 reducer 在已注册的评估协议清单（`evaluation-protocol-manifest-v1.0.0`，protocol id `ai-review-evaluation-protocol-v1`）下的 AI 消费与新闸门。全部机制见 [ai-review-authoring-contract-v2.md](../ai-review-authoring-contract-v2.md) 的「Comparison 接入（ticket 03）」一节，执行顺序见 [ai-review-migration-runbook.md](../ai-review-migration-runbook.md)。
- **判据不变**：本修订**不改动**任何 pre-registered 判据——盲审胜负 3-0、domain-method fit（challenger ≥2 对严格优于且无任何一对更差）、既有质量底线（`problem_space_match`/`feasibility_soundness`/`grounding_synthesis`/contamination/leakage 任一命中自动拒绝）、deterministic zero tolerance、challenger-only 异常零容忍、2.0× 成本/延迟包络、30.00 CNY 硬上限与 5.00 CNY 重审批阈值全部保持。修订只把「谁可以担任判分角色」从 Robert 唯一人工改为可标识作者的 AI 评审记录，并为其划出显式边界：判分工具换人，判据与阈值不动。
- **单一协议纪律**：矩阵全部 8 条结果必须使用同一个评估协议（要么全部 v1 人工、要么全部 v2 AI），reducer 对混用 fail closed（`EVALUATION_PROTOCOL_MISMATCH`）；`complete_unresolved` 覆盖可 ingest 并允许后续 slot 继续，但未决质量底线（`unresolved`/`not_evaluated`）由 `ai_quality_floor_unresolved` 闸门阻止晋升判断（未决状态仍阻止受影响的晋升判断）。
- **修订性质披露**：本修订按规格第 7 节与 manifest 固定披露文本标记为**首条输出产生后的评估协议修订**（`post-first-output evaluation-protocol revision`）——判定角色自 Robert 人工 artifact 移至可标识作者的 AI 评审记录，判据不变；**不是**事前注册的人工盲评，也不是独立科研验证。该披露逐字进入 manifest（`EVALUATION_PROTOCOL_REVISION_STATEMENT`）与每次含 AI 判定的 reduction 文档的 `evaluation_protocol` 闸门。
- **效力边界**：上述机制全部处于离线编码验收状态（全量 pytest 883 passed，black/compileall 通过；迁移 rehearsal 见 `tests/test_comparison_migration_rehearsal.py` 与 `tests/test_evaluation_costs.py`）。六次基础评审 smoke 已于 2026-09-05 执行并通过（4/4 完成条件，证据 [ai-review-real-smoke-evidence.md](../../research/ai-review-real-smoke-evidence.md)），但**正式激活仍需要**：Robert 对本修订的显式批准 + 按迁移 runbook 的真实迁移 smoke/执行 + 每个 run 的逐 run 费用确认。旧 Promotion Gate 在批准前继续拒绝 AI 记录（reducer 无 `ai_verdicts` 参数时输出与修订前逐字节一致）。
- **费用边界**：评审实际费用单列于新的 hash 链接 AI 评审费用台账（`evaluation-cost-ledger.json`，schema `evaluation-cost-ledger-v1.0.0`，`evaluation init-evaluation-cost-ledger` / `record-evaluation-cost` / `evaluation-cost-report --package-dir` 合并只读报告，报告含未授权支出披露），**从不静默扩展**生成端 30.00 CNY 硬上限口径——评审费用不占用生成预算，且不在生成 Plan Gate 批准范围内，需要 Robert 单独、显式批准其上限。

## Promotion Gate 记录

*待对比实验完整执行、盲审冻结、揭盲和判据 reduction 后，由 Robert 宣判。*
