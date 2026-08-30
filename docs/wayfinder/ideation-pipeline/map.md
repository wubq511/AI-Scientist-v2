---
title: Design an Auditable Ideation-Only Pipeline
label: wayfinder:map
status: open
---

# Design an Auditable Ideation-Only Pipeline

## Destination

一份经 Robert 批准、决策完整的规格与实现 ticket map，把本 fork 改造为可复现的 ideation-only 系统：准备 target-scoped 输入、仅从配套 references 检索文献、调用 `DeepSeek-V4-Pro-0813`、隔离每次运行、校验每个输出，并通过可审计的 Evidence Feedback Loop 持续改进设计，全程不进入 downstream 阶段。

## Notes

- 仅限规划：解决本 map 期间不实现 destination 交付物。
- 认领 ticket 前先读 `AGENTS.md`、`CONTEXT.md`、相关 work logs 和 `docs/agents/issue-tracker.md`。
- 人类决策用 `wayfinder`、`grilling`、`domain-modeling`；primary-source 事实用 `research`。
- 每项架构、数据集、模型/API、检索、评估和范围决策都必须经 Robert 批准。
- 需要 Robert 阅读的报告和文档用中文撰写（专业术语可保留英文）；代码、标识符、命令和 commit message 保持英文。

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [Set the ideation-only destination](tickets/001-set-the-ideation-only-destination.md): 规划一个可信的 ideation 系统，带证据驱动的设计反馈环。
- [Name the ideation domain](tickets/002-name-the-ideation-domain.md): 区分 Ideation Run、Run Isolation 和 Downstream Experiment。
- [Freeze literature before ideation](tickets/003-freeze-literature-before-ideation.md): enrichment 可使用公开来源；运行时检索保持本地且 fail closed。
- [Keep the Wayfinder local](tickets/004-keep-the-wayfinder-local.md): 在单独批准远程发布前，使用本地 Markdown tracker。
- [Modify the existing ideation path](tickets/005-modify-the-existing-ideation-path.md): 保持直接修改的变更面，不建独立子系统。
- [Preserve a compatible baseline](tickets/006-preserve-a-compatible-baseline.md): 先隔离必要改动，再开展证据驱动的优化。
- [Prevent Target Paper idea leakage](tickets/007-prevent-target-paper-idea-leakage.md): Workshop File 只暴露 topic，不暴露 target 的创新点或结果。
- [Separate idea payloads from evidence](tickets/008-separate-idea-payloads-from-evidence.md): 保留七字段 idea schema，provenance 另存其旁。
- [Stage full-dataset execution](tickets/009-stage-full-dataset-execution.md): 支持全部 targets，先验证 canary，批准后方可扩量。
- [Retain auditable run evidence](tickets/010-retain-auditable-run-evidence.md): 保留本地原始证据，提交脱敏的 manifest 与摘要。
- [Trust layered validation and isolated runs](tickets/011-trust-layered-validation-and-isolated-runs.md): 确定性、replay 与定性证据共同支撑结果。
- [Govern evidence-driven optimization](tickets/012-govern-evidence-driven-optimization.md): 用证据比较可行备选，再选最简有效设计。
- [Keep the runtime ideation-only](tickets/013-keep-the-runtime-ideation-only.md): 保留可移植 CPU FP32 reference path；推理加速只能通过独立证据门槛后作为可选 backend，不含 downstream 依赖。
- [Understand target-to-workshop semantics](tickets/014-understand-target-to-workshop-semantics.md): IdeaBench 让 target 内容不参与生成；recruiter 特有的 Workshop transform 需要显式泄漏策略。
- [Establish the DeepSeek-V4-Pro-0813 provider contract](tickets/015-establish-the-deepseek-provider-contract.md): DeepSeek 直连仅以浮动 alias 提供目标版本，provider 与版本锁定决策仍开放。
- [Audit metadata gaps and enrichment sources](tickets/016-audit-metadata-gaps-and-enrichment-sources.md): 精确标识符覆盖全部论文；三个 abstract 与 provenance/完整性缺口需要显式 corpus 策略。
- [Understand dataset routing metadata](tickets/033-understand-dataset-routing-metadata.md): 路由即 target-reference 配对；辅助 edge/category 字段不进入模型可见的检索。
- [Audit the minimal ideation runtime](tickets/017-audit-the-minimal-ideation-runtime.md): 历史 Python 3.11 CPU test cell 证明现有 ideation 入口只需五个包（一个未声明、一个未使用）；这证明兼容性而非继续锁定 runtime minor，依赖契约仍待决策。
- [Define the Workshop File contract](tickets/018-define-the-workshop-file-contract.md): 以 target `title + raw abstract` 私下派生严格四段、identity-free 的英文 Workshop；通过确定性与独立语义验证后才准入 ideation，身份和审计证据留在 private manifest。
- [Define the frozen corpus contract](tickets/019-define-the-frozen-corpus-contract.md): 每个 case 使用可确定性复现、field-level 可追溯且分层验证通过的 self-contained corpus bundle，runtime 只接受显式 pin 的 Approved Target Reference Corpus。
- [Choose the DeepSeek provider and version contract](tickets/031-choose-the-deepseek-provider-and-version-contract.md): 采用 DeepSeek direct 的浮动 V4 Pro alias；credential 保持本地，每次真实运行逐次估价审批，thinking 参数由后续 canary 实证选择。
- [Define the Scoped Literature Retriever contract](tickets/020-define-the-scoped-retriever-contract.md): 模型只提交 query；本地 retriever 在唯一 approved corpus 内返回最小 source-faithful paper evidence，并以 deterministic ranking、private audit release gate 与 fail-closed errors 阻止越界或降级。
- [Define the DeepSeek adapter contract](tickets/022-define-the-deepseek-adapter-contract.md): 采用 DeepSeek-only non-streaming Chat Completions adapter，以严格 allowlist、typed attempts、bounded retry、fail-closed validation、私有原始证据和官方人民币价格快照隔离 provider transport 与 ideation controller。
- [Define run identity and evidence layout](tickets/023-define-run-identity-and-evidence-layout.md): 每次 run 以最小 opaque identity、固定 raw/sanitized roots、immutable event hash chain、terminal seal 与 fail-closed cross-run guards 隔离状态并保留完整 Evidence Chain。
- [Define the safe ideation entry](tickets/024-define-the-safe-ideation-entry.md): 原地改造现有 CLI：准入清单式导入守卫、六参数 new-run CLI、九步 fail-closed preflight（末道为估价批准）、versioned 价格表按 attempt 开始时段计价、prompt diff 限于工具描述段、FinalizeIdea 结构校验、三注入缝。
- [Define the minimal runtime dependency contract](tickets/034-define-the-minimal-runtime-dependency-contract.md): 三文件结构（runtime 最小集 / upstream 保留清单 / dev 工具）全部精确 pin；最小集 = 实际 import 闭包且随使用方同生同灭，确切清单由实现 ticket 落地。
- [Define control flow, failures, and resume](tickets/025-define-control-flow-failures-and-resume.md): baseline 循环不变，模型可修复错误统一回灌、per-generation finalization gate，失败按 suspend/terminal 封闭二值分级，中断立即 abort 且 operation 原子，resume 重放重建加费用重估，orphan 规则修订为 quarantine（023 留指针）。
- [Choose IdeaBench evaluation fidelity](tickets/032-choose-ideabench-evaluation-fidelity.md): Target Paper 仅作 sealed qualitative comparator——Robert 判分的结构化 post-seal Evaluation Artifact，canary 阶段逐 run 强制——不复现任何官方指标；报告以术语纪律与 "Evaluation fidelity" 专节区分本适配与官方复现，并主动披露 DeepSeek 参数化污染 caveat。
- [Define the idea quality rubric](tickets/026-define-the-idea-quality-rubric.md): 两层 rubric——runtime 收 declared grounding 说谎检测、payload hygiene 扫描（命中即 terminal）与 run 内去重，post-seal 为 032 六项加 grounding 综合质量；feasible/novelty 仅定性，跨 run 重复归 Run Isolation。
- [Define the declared grounding contract](tickets/038-define-the-declared-grounding-contract.md): FinalizeIdea 封闭两键加扁平 `grounding` id 数组，per-generation eligibility（收紧 026 措辞）、三码 model-fixable 回灌、gate 固定优先级 hygiene 最先；prompt diff 围栏扩大至 ARGUMENTS/示例块（024 留指针）。
- [Define the post-seal evaluation artifact contract](tickets/037-define-the-post-seal-evaluation-artifact-contract.md): 每 finalized idea 一份 private canonical JSON artifact——七项 enum+rationale（无数值分）、run/seal/idea/target 全 hash 链接、assemble→validate 两阶段、自含审计、线性 supersedes、fail-closed 校验；无 sanitized stub，覆盖率由只读 list-coverage 核算。
- [Define the validation and test matrix](tickets/027-define-the-validation-and-test-matrix.md): 九层验证矩阵落为独立契约文档 `docs/agents/validation-matrix.md`——索引既有 runtime gate、新定义开发期测试层；委托阈值走版本化规则集 + 契约可推导值 + calibration-pending 三类；证据沿用 010；028/029/030 以行 ID 消费。
- [Define the optimization promotion gate](tickets/029-define-the-optimization-promotion-gate.md): 确立 Optimization Promotion 机制——证据驱动的设计变更过双 gate（Plan/Promotion）+ pre-registered 判据与 Regression Budget，bugfix 与未定设计豁免；Design Epoch 证据可比性规则供 028 引用；契约落 `docs/agents/promotion-gate.md` v1.0。
- [Define canaries and scale gates](tickets/028-define-canaries-and-scale-gates.md): 三波结构（smoke 1 → canary 12 → 终波）+ 分层 Canary（035/036 共享、含边缘案例、名单私有）；¥30 硬上限优先队列；Scale Gate = 硬阻断清零 + 逐 case success + 矩阵 028 行 + Robert 批准；终波规模由 gate 按面试需要定（预期 ~50，不要求全量 237），031 修订为终波按批批准；契约落 `docs/agents/canary-and-scale-gates.md` v1.0。

## Not yet specified

<!-- see "Fog of war": in-scope fog you can't ticket yet; graduates as the frontier advances -->

- 最终面试叙事应如何优先呈现失败或降级 run 中浮现的发现。

## Out of scope

<!-- see "Out of scope": work ruled beyond the destination; closed, never graduates -->

- BFTS、代码实验、绘图、LaTeX write-up、自动 review、`launch_scientist_bfts.py`。
- GPU/accelerator 训练、把任何 accelerator 设为必需，以及仅 downstream 阶段使用的依赖；未通过独立证据 gate 的推理 backend 同样排除。
- Ideation Run 期间的全局或远程文献检索。
- 直接修改即可满足时，另建独立 ideation 子系统或框架。
- 未经 Robert 单独批准，发布 tracker 内容或仓库变更。
