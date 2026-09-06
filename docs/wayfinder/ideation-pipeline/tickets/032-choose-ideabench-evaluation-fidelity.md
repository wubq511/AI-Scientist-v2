---
title: Choose IdeaBench evaluation fidelity
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 014-understand-target-to-workshop-semantics.md
---

## Question

Should this project reproduce any official IdeaBench metrics or use the Target Paper only as a sealed qualitative comparator, and how must the report distinguish a recruiter-specific AI Scientist adaptation from an official benchmark reproduction?

## Resolution

2026-08-30 经 grilling 两轮七题由 Robert 批准：

1. **评估目的**：仅服务 Evidence Feedback Loop 与面试叙事；明确排除 benchmark 可比性主张。输入侧是 bespoke Workshop transform，生成模型 `DeepSeek-V4-Pro-0813` 对 2024 targets 的参数化污染未排除，任何官方口径数字与 published 结果不可比。
2. **保真度档位**：Target Paper 仅作 sealed qualitative comparator，不复现任何官方指标（BERTScore / idea overlap / Insight Score）。post-seal 评估读取 `abstract_summary`（官方 ground-truth 锚点）与完整 abstract，产出固定字段的结构化对照记录：问题空间匹配度、与 target contribution 的重叠性质（recover / 部分重叠 / materially different）、相对 novelty、feasibility 合理性、污染信号检查（reference 无法解释的 target 独有命名或逐字短语）、泄漏复核。未来如需定量信号，独立 ticket 增补。
3. **判分者**：Robert 为唯一判分者；工具仅组装 side-by-side 对照材料。引入任何 LLM judge 属独立模型/API 决策，另票批准。
4. **粒度**：canary 阶段每个产生 final idea 的 sealed run 强制链接一份 Evaluation Artifact；扩量后是否改抽样归 028/009 的 scale gate 决策。
5. **报告红线**：统一术语 "AI Scientist adaptation over an IdeaBench subset"，禁止以官方指标名（IdeaBench score / Insight Score 等）指称本项目任何结果；最终实验报告专设 "Evaluation fidelity" 一节，显式声明复现了什么、未复现什么、为何不可比，并主动披露 DeepSeek 参数化污染 caveat。
6. **票际边界**：本票只定 stance 与表述规则；idea 质量 rubric 归 [Define the idea quality rubric](026-define-the-idea-quality-rubric.md)；系统级验证矩阵归 027。
7. **解封与证据归属**：Target Paper 在 output freeze 后才可读；评估为 post-seal 独立 Evaluation Artifact，自带审计记录，不进该 run 的 Evidence Chain。

衍生动作：新建 [Define the post-seal evaluation artifact contract](037-define-the-post-seal-evaluation-artifact-contract.md)（blocked_by 026）；map 中「DeepSeek 是否 memorize 2024 Target Paper」的 fog 条目被本决策吸收（污染信号检查 + 报告主动披露；残余的"是否真被训练过"不可验证、永不毕业），已从 Not yet specified 清除。CONTEXT.md 新增术语 Evaluation Artifact。
