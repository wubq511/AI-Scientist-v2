---
id: 002-cross-domain-ideation-prompt
state: proposed
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
- **顺序与盲法**：2 对 baseline-first、2 对 challenger-first；2 对 A=baseline、2 对 A=challenger；映射在运行前 hash-frozen，Robert 写完所有可用 verdict 后才能揭盲；
- **验证矩阵行**：VM-CONTRACT-COMPARE-01, VM-CONTRACT-COMPARE-02, VM-CONTRACT-COMPARE-03, VM-CONTRACT-COMPARE-04, VM-CONTRACT-018-02, VM-CONTRACT-019-01, VM-CONTRACT-020-02, VM-CONTRACT-026-02, VM-INTEGRATION-01, VM-REPLAY-02, VM-LEAKAGE-01, VM-LEAKAGE-02, VM-LEAKAGE-04, VM-ISOLATION-01, VM-ENV-01, VM-QUAL-01；
- **环境与依赖锁定**：Python 3.13 参考栈，锁定 `requirements.txt` 与 `requirements-dev.txt`；
- **成本与预算核算**：
  - 8 个 runs 的非权威预测为 1.12–2.24 CNY（参考 live smoke 实测 0.14 CNY/run）；
  - Canary 阶段总硬上限：30.00 CNY；
  - 历史已发生实际支出：0.14 CNY（单 case smoke 产生）；
  - 当前 Canary 阶段剩余预算：29.86 CNY；
  - 拟议本提案 Plan Gate 实际支出子上限：`plan_gate_subcap_cny = 5.00 CNY`；
  - 子上限约束的是矩阵级实际支出（stage 总账含 0.14 CNY 历史 smoke 支出的 opening balance），严格不等式防溢出；每个 run 的 7.08 CNY 最坏 bound 仅属于 live admission 交互批准 seam，不进入子上限算术。
  - 每个 run 仍受 7.08 CNY 单次准入最坏上限校验，且需 Robert 交互式逐 run 批准。

## Pre-registered 判据

1. **完整性**：4 对、8 个 runs 全部获得可验证 Run Seal、sanitized export 和完整 Evaluation Artifact；缺一即 `inconclusive`，不得用完成子集晋升。
  - pair packet 的 idea payload 现以 per-arm sealed idea SHA-256 绑定到 Evidence Chain，verdict 与 packet hash 在 reduction 处复核（`VERDICT_PACKET_MISMATCH` fail closed）。
2. **盲审胜负**：揭盲后 challenger 至少胜 3 对，baseline 胜 0 对；tie 不计胜，`incomparable` 使矩阵不完整。
3. **Domain-method fit**：challenger 至少 2 对严格优于 baseline，且 4 对中没有任何一对更差。评审必须区分“合理采用 ML”与“无问题/证据依据的 ML intrusion”。
4. **既有质量底线**：challenger 不得引入 `problem_space_match=mismatched`、`feasibility_soundness=unsound`、`grounding_synthesis=name_dropped`、contamination signal 或 leakage；任一出现自动拒绝。
5. **Deterministic Regression Budget**：零容忍。profile schema/hash、Run Request/Admission、resume、replay、Evidence Chain、export、leakage、isolation、import/dependency 与 CLI 任一 baseline-pass/challenger-fail 均自动拒绝。
6. **截断与异常**：challenger 不得新增 `finish_reason=length`、completion truncation、terminal failure、unresumable suspension、physical attempt 或仅 challenger 出现的异常模式。
7. **成本与延迟**：challenger 实际总成本不得超过 baseline 的 2.0 倍；challenger 端到端中位延迟不得超过 baseline 的 2.0 倍；总实际支出不得突破 Plan Gate 子上限或 30 CNY Canary 总上限。
8. **Fail-closed 结果**：任何判据未通过均保持现有代码默认，但 035 和 Scale Gate 继续暂停；“challenger 未通过”不等于“已知目标错配 baseline 合格”。

## 预期失败模式

1. 领域中立措辞过于宽泛，导致 proposal 缺少可操作的验证设计；
2. 保留的 `Experiments` key 继续把非实验研究拉回实验或 benchmark framing；
3. “不要默认 ML”被模型过度解释，导致本应使用计算方法的 case 回避合理 ML；
4. Workshop/检索文献提供的领域信号不足，challenger 只能生成泛化模板；
5. 两臂除 prompt 外出现 Run Specification drift，使 pair 失去可比性；
6. 盲包泄露 profile、执行顺序、成本、延迟或模型元数据；
7. 任一 run 失败、挂起、截断或因预算停止，矩阵变为 inconclusive；
8. 实际成本显著高于 smoke 外推，触发 Plan Gate 子上限或 Canary 硬上限。

## 实验证据

*尚未启动付费调用。当前新增 provider 调用 0 次，Proposal 002 实际支出 0.00 CNY。准备工作（Tickets 01/02/03）已全部完成，全套离线对比物料已冻结落盘，等待 Robert 在 originating session 审批 Plan Gate。*

### 冻结私有对比物料清单 (SHA-256)

所有对比物料均物化于被 `.gitignore` 保护的私有目录 `artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/`：

- **4-Case 选集清单 (`selection-manifest.json`)**：`b09488322ce934e1aca1ce3020791240a23c6f55a68eee2dc66a14c3076bc83f`
- **选集批准记录 (`selection-approval.json`)**：`9944dc5e4d00fc6aaec1f541ccc6bb7481bca8a36e3634a3a6e63bcf49e893ba`
- **8-Run 运行矩阵 (`run-matrix.json`)**：`c8a9217ffcf60718cc132ef04688bdf0bd3bd23758f0e54373993e1237d78ef4`（自验签 `matrix_sha256`: `c60d72748d8ab6aa06e712332e4bee2b4b7cf275b7f34ba58c210c09f5d963c3`）
- **双盲平衡映射 (`blind-mapping.json`)**：`a605f3755b7bfeeb6497f6e27a9bc1e3f6f36822155497f1c9f19d85388f0a9e`
- **初始花费账本 (`spend-ledger.json`)**：`bec52349eb53b0328cafd67f152d25ce43e2b7e90ad0d1fbbf3f69fd01f03f29`（账本 schema 已升级为 `comparison-spend-ledger-v1.1.0`，包含 0.14 CNY 历史 smoke 支出 opening balance）
- **CLI 运行命令 (`commands.txt`)**：`be30d7d81a4aaf6e2b388c122a1d167a6258a50a289119e4cd7b73564ad2ce2a`

### 代码与运行基准

- **当前准备完成 Commit SHA**：`3428909f939a510534b481327c7c674f541e9956`（对抗性审查修复后的当前 HEAD，覆盖 Ticket 03 最终提交）
- **依赖栈基准**：Python 3.13.2 reference stack, pinned dependencies.

## Plan Gate 记录

- **状态**：`proposed`（Plan Gate 候选已完备，等待审批）
- **准备完成日期**：2026-09-04
- **拟议审批内容**：
  - 4-case selection manifest 与 8-run frozen matrix 散列；
  - 2/2 执行顺序平衡与 2/2 A/B 双盲映射；
  - 拟议实际支出子上限 `5.00 CNY`：Plan Gate 为矩阵级严格不等式 consult 守卫（总 stage 支出须严格低于子上限与 30.00 CNY 硬上限，enforcement 于 result ingestion fail-closed `SUBCAP_EXCEEDED`）；本提案 runs 剩余可支配 tracked 预算 = 5.00 − 0.14 = 4.86 CNY（Canary 阶段剩余 29.86 CNY/30.00 CNY 硬上限）；
  - 3 胜 0 负盲审胜负、domain-method fit 改善、ML intrusion 不增与 2.0× Regression Budget 门槛；
  - 声明：Plan Gate 审批仅批准矩阵级架构与子上限，不替代每个 run 准入前的独立交互式费用确认。

## Promotion Gate 记录

*待对比实验完整执行、盲审冻结、揭盲和判据 reduction 后，由 Robert 宣判。*
