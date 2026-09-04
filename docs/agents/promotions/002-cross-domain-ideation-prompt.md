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

- **可证伪假设**：在四个方法学差异显著的 Canary cases、相同输入、模型、`reasoning_effort=high`、`max_tokens=32768`、retriever、rubric 和运行预算下，`cross-domain-v1` 相比字节语义保持的 `ml-baseline-v1` 能显著提高 domain-method fit、减少不必要的 ML/benchmark framing，同时不降低 problem-space match、relative novelty、feasibility soundness、grounding synthesis、确定性可靠性或运行可恢复性。
- **单主变量声明**：两臂唯一差异是 Prompt Profile。任何 Workshop/Corpus hash、模型参数、轮次预算、retrieval、action schema、rubric、执行环境或评审流程差异均使 pair 不合格。

## 备选方案

1. **只把 `top ML conferences` 改为 `top venues in the relevant field`**：仍以发表 venue 代替科研价值，并不能修复 AI researcher、conference abstract、algorithmic changes、metrics 与 feasibility 的连锁偏置，排除。
2. **为八个 cluster 各写一套 prompt**：需要把辅助 cluster metadata 提升为模型控制输入，引入错误分类、八套维护分支和新的泄漏/漂移表面；在一个领域中立 prompt 尚未失败前不成立，排除。
3. **立即替换 prompt、不做对照**：无法区分改善、泛化变差或过度纠偏，违反 Evidence Feedback Loop 与 Promotion Gate，排除。
4. **先完成 `high` vs `max` 再修 prompt**：内部比较虽公平，但只会选择谁更擅长执行已知目标错配的任务，产生不可用于新 Design Epoch 的付费证据，排除。

## 对比方案

- **Baseline**：`ml-baseline-v1`，保持当前生产 prompt 的 model-visible 语义；
- **Challenger**：`cross-domain-v1`，采用规格中批准的 multidisciplinary role、field-appropriate methods、领域相称 feasibility、field-neutral Abstract 与 validation-plan 语义；
- **Cases**：从已冻结 12-case Canary 中，对 Genetics & Molecular Biology、Health & Medicine、Social & Behavioral Sciences、Materials Science 各按 canonical case hash 取一例，共 4 对、8 个 Ideation Runs；
- **固定参数**：`reasoning_effort=high`、`max_tokens=32768`、`max_num_generations=1`、`num_reflections=3`，其余 Run Specification 相同；
- **顺序与盲法**：2 对 baseline-first、2 对 challenger-first；2 对 A=baseline、2 对 A=challenger；映射在运行前 hash-frozen，Robert 写完所有可用 verdict 后才能揭盲；
- **验证**：两臂均通过既有 Workshop/Corpus、adapter、retrieval、controller、Evidence Chain、resume、export、leakage、isolation 与 Evaluation Artifact 矩阵；新增 Prompt Profile schema/hash/legacy/resume 和 comparison reducer 契约测试；
- **成本**：8 个 runs 的非权威预测为 1.12–2.24 CNY；比较必须在既有 30 CNY Canary 硬上限内另设 Plan Gate 实际支出子上限，并在 Plan Gate 前重新核对官方价格。每个 run 仍需单独交互批准。

## Pre-registered 判据

1. **完整性**：4 对、8 个 runs 全部获得可验证 Run Seal、sanitized export 和完整 Evaluation Artifact；缺一即 `inconclusive`，不得用完成子集晋升。
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

*尚未启动。当前新增 provider 调用 0 次，Proposal 002 实际支出 0.00 CNY。先完成三个零网络准备 tickets；Robert 回到 originating session 后再决定 Plan Gate。*

## Plan Gate 记录

*待定。Robert 于 2026-09-04 批准了问题判断、领域中立方向、四方法学家族的小规模比较和先暂停 035 的顺序，但没有批准最终私有四例 manifest、当前价格证据、实际支出子上限或任何 provider request。*

## Promotion Gate 记录

*待对比实验完整执行、盲审冻结、揭盲和判据 reduction 后，由 Robert 宣判。*
