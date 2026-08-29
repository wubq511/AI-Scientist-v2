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
- [Keep the runtime ideation-only](tickets/013-keep-the-runtime-ideation-only.md): 最小 CPU 环境，不含 downstream 依赖。
- [Understand target-to-workshop semantics](tickets/014-understand-target-to-workshop-semantics.md): IdeaBench 让 target 内容不参与生成；recruiter 特有的 Workshop transform 需要显式泄漏策略。
- [Establish the DeepSeek-V4-Pro-0813 provider contract](tickets/015-establish-the-deepseek-provider-contract.md): DeepSeek 直连仅以浮动 alias 提供目标版本，provider 与版本锁定决策仍开放。
- [Audit metadata gaps and enrichment sources](tickets/016-audit-metadata-gaps-and-enrichment-sources.md): 精确标识符覆盖全部论文；三个 abstract 与 provenance/完整性缺口需要显式 corpus 策略。
- [Understand dataset routing metadata](tickets/033-understand-dataset-routing-metadata.md): 路由即 target-reference 配对；辅助 edge/category 字段不进入模型可见的检索。
- [Audit the minimal ideation runtime](tickets/017-audit-the-minimal-ideation-runtime.md): 现有 ideation 入口在 Python 3.11 CPU 下只需五个包（一个未声明、一个未使用）；依赖契约与 DeepSeek-V4-Pro-0813 支持仍待决策。
- [Choose the DeepSeek provider and version contract](tickets/031-choose-the-deepseek-provider-and-version-contract.md): 采用 DeepSeek direct 的浮动 V4 Pro alias；credential 保持本地，每次真实运行逐次估价审批，thinking 参数由后续 canary 实证选择。

## Not yet specified

<!-- see "Fog of war": in-scope fog you can't ticket yet; graduates as the frontier advances -->

- 兼容基线产出证据后，哪些优化是正当的。
- 是否有 target 领域需要超出已提供 metadata 和 abstract 的文献内容。
- 最终面试叙事应如何优先呈现失败或降级 run 中浮现的发现。
- `DeepSeek-V4-Pro-0813` 是否 memorize 了 2024 年的 Target Paper；Workshop 去污染无法消除参数化污染。

## Out of scope

<!-- see "Out of scope": work ruled beyond the destination; closed, never graduates -->

- BFTS、代码实验、绘图、LaTeX write-up、自动 review、`launch_scientist_bfts.py`。
- CUDA、GPU、PyTorch 训练，以及仅 downstream 阶段使用的依赖。
- Ideation Run 期间的全局或远程文献检索。
- 直接修改即可满足时，另建独立 ideation 子系统或框架。
- 未经 Robert 单独批准，发布 tracker 内容或仓库变更。
