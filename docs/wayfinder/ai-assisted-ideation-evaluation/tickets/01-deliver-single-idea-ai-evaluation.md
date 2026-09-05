---
title: 交付单条 idea 的 AI 评审与证据卡
type: implementation
status: closed
assignee: zcode-coding-agent
blocked_by: []
---

**Triage:** ready-for-agent

## Parent

[AI 辅助 Ideation 评审规格](../../../agents/ai-assisted-ideation-evaluation-spec.md)

## What to build

从一个 sealed Ideation Run 出发，使用现有 evaluation 命令交付匿名材料包、可供 AI 使用的版本化 prompt、响应导入与验证，以及七维中文证据卡。产物诚实标记为单评审建议，可独立供 Robert 阅读；本票不赋予 comparison 晋升效力。

先追加必要的评估术语和 v2 authoring 约定，再实现新模式。使用项目 prompt-engineer 技能编写单条评审模板与输出 schema，复用现有组装、hash linkage、持久化与 CLI 行为；不建设新服务或通用 provider SDK。

## Acceptance criteria

- [x] 原生成期 rubric 和 finalized idea 语义保持不变；旧版人工 Evaluation Artifact 可读且不被重写。
- [x] 一个 sealed run 经 CLI 完成材料导出、fixture 响应导入、引用验证和证据卡生成；unsealed/corrupt run 不能进入评审。
- [x] 材料包含必要的原文和明确的完整性范围；model-visible 部分不含 profile、winner 意图和运行元数据；包外哈希绑定真实 idea 与 seal。
- [x] 七维沿用原 verdict 枚举，另有独立的 insufficient_evidence 状态；缺材料时 verdict 为空，理由明确所缺材料。
- [x] 每个有依据的判断能回链 source ID 和原文短片段；来源存在与语义支持在输出中明确分开。
- [x] AI 作者、实际验证工具与 Robert 决定分开记录；手工导入响应不伪装成工具执行过的真实 provider 调用。
- [x] 输出 schema、prompt version 和 authoring contract 一起版本化；保留原始响应与修订，错误输入不能产生已验证 artifact。
- [x] 证据卡呈现建议、理由、引用、假设与未决问题，无数字总分、虚构专家资历或未经校准的置信度。
- [x] 通过正常、缺材料、假引文、引用不支持、注入文本、领域方法、换位测试所需材料及无效响应等必要 fixtures；测试走最高 CLI seam。
- [x] 交付模板、schema、边界示例、使用说明和离线验证报告。说明单评审模式的证据限度，不声称科研质量已验证。

## Blocked by

None (can start immediately).

## Handoff

本票交付后单条证据卡即可使用。所有真实调用需要运行配置与现有费用/出站授权；无授权也能完整交付导出/导入与离线编码验收。

## Resolution

2026-09-05 由 coding agent 按 [规格](../../../agents/ai-assisted-ideation-evaluation-spec.md) 完成离线编码验收；未发生任何真实模型调用或付费生成。

1. **术语与 v2 authoring 约定先行**：[ai-review-authoring-contract-v2.md](../../../agents/ai-review-authoring-contract-v2.md) 固化版本族（contract `evaluation-authoring-contract-v2.0.0`、材料包/记录/导入 schema、`single-review-v1` prompt 版本，全部 pin 于 `contract.py`）；CONTEXT.md 新增 AI Review Record / Review Material Package / Evidence Card 术语；validation-matrix 追加 VM-QUAL-02 行与版本化修订说明。v1 人工 Evaluation Artifact 合同（037）与 coverage 语义逐字节不变，AI 文件隔离在 `ai/` 子目录。
2. **评审模板与输出 schema**：用 prompt-engineer 技能编写 `ai_scientist/ideation/policies/ai-review-prompt-single-v1.md`（SHA-256 pin），含任务角色（不捏造专家资历）、材料即数据边界、诚实边界（none_found 限于材料范围、novelty 只对给定 target）、七维「判断什么/不得推导」表、弃权规则、JSON 输出契约与五个合成边界例（正常 judged / 审计范围弃权 / 材料内指令 / 合法领域方法 / 无依据 ML framing），不含当前正式矩阵材料。
3. **匿名确定性材料包**：`evaluation export-review-package` 产出两层包——model-visible payload（Workshop 原文、idea 七字段、Target Comparator、审计范围声明、sidecar 绑定检索操作的**全部**论文节选并标注 declared_grounding）只含包内 `S###` 匿名 source ID；私有外层绑定 run/seal/idea 哈希并保存真实 paper_id registry。无时间戳、重复导出逐字节一致（换位评审同料）。`import`/`validate` 从链上重推导并比对磁盘字节，篡改即 `REVIEW_PACKAGE_DRIFT`。
4. **响应导入与验证**：`evaluation import-review-response` write-once 保存原始响应，provenance 恒为 `user_supplied`（导入层结构上无法声称程序执行过模型调用），解析失败显式 exit 1 且保留原文；`evaluation validate-review` fail-closed 校验（七维枚举 + 独立 `insufficient_evidence` 弃权、judged 无引用须「推断：」标记、伪造 source `CITATION_SOURCE_NOT_FOUND`、quote 非逐字 `CITATION_QUOTE_NOT_FOUND`、线性 supersedes），通过后 write-once 提交 `ai/vNNNN.json` 并渲染中文证据卡；`evaluator.author_type=AI`、`audit.validated_by=ai_scientist.ideation.ai_review.validate_ai_review`、Robert 决定三角色分离。
5. **验证**：`tests/test_ai_review_evaluation.py` 23 项（八个边界 fixture 类 + CLI seam + v1 共存 + 注入惰性 + 换位材料确定性 + 引文不支持/跨 run 引用/request 漂移/审计引用规则）；全量 `pytest -q` 810 passed（基线 787，零回归）；black/compileall 通过；两轴 code-review 后修复 9 条发现，见 [ai-review-offline-validation-evidence.md](../../../research/ai-review-offline-validation-evidence.md)。
6. **真实数据管道演示**：slot 1 在 /tmp throwaway 副本上跑通全链（对真实工作区零写入）；demo 响应标注 `offline-demo`/`fixture-response-not-a-model`，是管道演示而非模型评审意见，不回填真实矩阵。
7. **证据限度**：离线 fixtures 只证明软件契约。单评审证据卡是未经专家校准的 AI 建议，无晋升效力；真实 smoke（六次基础调用）需 exact model 配置、费用上界与出站授权，未执行项已在报告中单列。
