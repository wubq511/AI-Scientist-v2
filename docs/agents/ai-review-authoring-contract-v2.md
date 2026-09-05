# AI 评审 authoring contract v2（单评审模式）

日期：2026-09-05  
状态：已实现（ticket [01-deliver-single-idea-ai-evaluation](../wayfinder/ai-assisted-ideation-evaluation/tickets/01-deliver-single-idea-ai-evaluation.md)）；本文件是机器校验行为的合同化说明，不授权付费调用。  
规格：[AI 辅助 Ideation 评审规格](ai-assisted-ideation-evaluation-spec.md)  
前置合同：v1 人工 Evaluation Artifact 合同（[ticket 037](../wayfinder/ideation-pipeline/tickets/037-define-the-post-seal-evaluation-artifact-contract.md)）保持不变。

## 定位

v1 合同规定 Robert 是 post-seal Evaluation Artifact 的唯一作者。v2 authoring contract 在不修改 v1 任何行为的前提下，新增一条可标识作者来源的 AI 评审通道：AI 承担资料对照式初评，输出诚实标记为单评审建议的中文证据卡；它没有晋升效力，不宣称专家科研真值。

与 v1 的关系：

- v1 人工 artifact 的 assemble/validate/list-coverage、存储布局、write-once/supersedes 语义逐字节不变；v2 的全部文件位于每个 idea 目录下新增的 `ai/` 子目录，不参与 v1 的版本扫描与 coverage 核算。
- 七个维度沿用同一 pinned rubric（`idea-quality-rubric-v1.0.0`）的封闭 verdict 枚举；弃权不是新 verdict，而是独立的 `assessment_status=insufficient_evidence` 状态。
- 历史不被改写：旧 artifact 与旧结论原样保留；本文件是版本化的评估决策记录。

## 版本绑定

以下版本一起版本化，由 `ai_scientist/ideation/contract.py` 统一 pin，任一漂移 fail closed：

| 项目 | 值 |
|---|---|
| authoring contract | `evaluation-authoring-contract-v2.0.0` |
| 材料包 schema | `evaluation-review-package-v1.0.0` |
| model-visible 材料 schema | `evaluation-review-materials-v1.0.0` |
| 响应导入记录 schema | `evaluation-review-response-import-v1.0.0` |
| AI 评审记录 schema | `evaluation-ai-review-record-v2.0.0` |
| 模型输出契约 | `ai-review-response-v1.0.0` |
| 单评审 prompt 版本 | `single-review-v1`（模板 `ai_scientist/ideation/policies/ai-review-prompt-single-v1.md`，SHA-256 pin 于 contract.py） |

## 文件布局

```
artifacts/evaluations/<run_id>/ideas/<idea_index>/
  brief.md              # v1：人工阅读材料（不变）
  draft.json            # v1：人工填写中草稿（不变）
  v0001.json            # v1：人工 Evaluation Artifact（不变）
  ai/
    review-package.json # 匿名材料包（确定性、可重导出、逐字节一致）
    review-request.txt  # 渲染好的待发送请求（pinned 模板 + model_payload）
    responses/rNNNN.json # 导入的原始响应，write-once，含 user_supplied provenance
    vNNNN.json          # 校验通过的 AI 评审记录，write-once + 线性 supersedes
    evidence-card.md    # 中文证据卡（由最新记录确定性渲染，可重生成）
    evidence-card.html  # 同一记录的浅色单文件网页渲染（自包含：无脚本、无外部资源，可重生成）
```

证据卡的权威内容以评审记录为准；md 与 html 是同一记录的两种确定性渲染，html 面向阅读（维度中文名、verdict 色标、弃权高亮），颜色仅为阅读辅助，不改变任何枚举语义。

## 材料包与信任边界

- **两层结构**：外层（`run_id`、`case_id`、`seal_sha256`、idea 哈希绑定、私有 `source_registry`）只在本地；`model_payload` 是评审模型可见的全部内容。model-visible 部分不含 run 身份、Prompt Profile 身份、baseline/challenger 映射、成本、运行顺序或期望结果；论文身份以包内 `S001…` 匿名 source ID 呈现，真实 `paper_id` 只存在于私有 registry。
- **来源**：Workshop 原文、sealed idea 七字段（逐字段可引用）、Target Comparator（title/DOI + abstract_summary + 完整 abstract，仅 post-seal 评审可见）、审计范围声明、sidecar 绑定检索操作返回的**全部**论文节选（含 Declared Grounding 之外的论文，逐条标注 `declared_grounding`）。
- **确定性**：材料包是 sealed run + pinned rubric + pinned prompt 模板的确定性函数；重复导出逐字节一致，成对 A/B、B/A 换位评审使用同一份 model payload。`import`/`validate` 都会从链上重推导并与磁盘字节比对（`REVIEW_PACKAGE_DRIFT` fail closed），`review-request.txt` 同样与 pinned 渲染结果比对（`REVIEW_REQUEST_DRIFT`）——操作者实际发送的请求不能无声漂移。
- **审计范围声明**（`audit_statement`，同时是可引用 source）：逐项列出检查的 complete/incomplete 与范围。当前派生事实：生成期 payload hygiene 对 finalized idea 通过；Workshop 语义审批通过（仅覆盖 Workshop 文本）；检索释放记录完整（限 sidecar 绑定操作）；**provider 训练侧污染审计 incomplete/not_performed**。判断受声明范围约束，incomplete 相关维度必须弃权或明确限定范围。

## 响应契约与验证规则

模型按 `single-review-v1` 模板输出一个 JSON 对象（`task: single_idea_review` + 七维 `dimensions`）。每维仅六个字段：`assessment_status`、`proposed_verdict`、`rationale`（中文）、`evidence_refs`、`key_assumptions`、`missing_information`。

确定性校验（全部 fail closed，失败不产生记录）：

- 七维齐全；verdict 严格取 pinned rubric 枚举；`judged` 时 `missing_information` 必须为空、有 verdict；`insufficient_evidence` 时 verdict 必须为 null 且 `missing_information` 非空（说明所缺材料）。
- 每条 `evidence_ref`（`source_id` + `quote` + `claim` + `stance`）经程序核验：source 必须存在（`CITATION_SOURCE_NOT_FOUND`），quote 必须逐字（空白归一后）出现在该 source 原文中（`CITATION_QUOTE_NOT_FOUND`）。**引用存在性 ≠ 语义支持**：语义支持关系不由程序核验，记录与证据卡均如实标注 `not_performed`。
- `judged` 且引用为空时，`rationale` 必须以「推断：」开头说明推理依据（`EVIDENCE_REF_REQUIRED`）。
- `contamination_signal` 与 `leakage_review` 为 `judged` 时，至少一条引用必须指向 `audit_statement` 来源（`AUDIT_STATEMENT_REF_REQUIRED`）：范围性结论必须锚定到包内实际携带的审计事实。
- `task` 不符、未知字段、格式不可解析均为 `INVALID_SCHEMA` / `REVIEW_RESPONSE_INVALID_FORMAT`。

## 作者、验证与决定

- `evaluator.author_type` 恒为 `AI`；`declared_provider` / `declared_model_id` 是导入时声明的值，程序不认证。响应文件导入的 provenance 恒为 `user_supplied` + `supplied_by`：**导入层从不声称程序亲自执行过该模型调用**；将来若有 transport 集成的执行路径，再以新的 provenance kind 版本化。
- `audit.validated_by` 恒为程序工具标识 `ai_scientist.ideation.ai_review.validate_ai_review`，与 AI 作者、Robert 的操作者决定三者分开。Robert 的确认不写入 AI 记录（不发生角色改写）；他的定性结论仍走 v1 人工 artifact 通道。
- 原始响应（`responses/rNNNN.json`）与评审记录（`ai/vNNNN.json`）各自独立版本化、write-once、线性 supersedes；修订通过再次 import + validate 产生新版本，旧版逐字节保留。无效响应保留原始内容，永远不能成为已验证记录。
- 无数字总分、无自报置信度、无专家资历表述；`none_found` 一律限于材料包实际范围。

## 单评审模式的证据限度

一张证据卡 = 一个模型在一份材料上的一次可回链建议。它不能排除：模型共同错误、语义支持错判、材料范围外的污染与泄漏。两位异家族独立评审、换位检查与分歧保留由 ticket 02 交付；本票产物只用于 Robert 阅读与诊断，不改变任何 gate 行为。离线 fixtures 通过只证明软件契约；模型判断质量未经真实 smoke 验证前不得声称有效（见离线验证报告）。

## CLI 使用

```bash
# 1. 导出匿名材料包 + 待发送请求（sealed run, sealed idea）
python ai_scientist/perform_ideation_temp_free.py evaluation export-review-package \
  --run-id <run_id> --idea-index <n>

# 2. 把 artifacts/evaluations/<run_id>/ideas/<n>/ai/review-request.txt 发给评审模型
#    （真实调用前需 exact model 配置、费用上界与数据出站授权），保存模型回复为文件。

# 3. 导入响应（write-once；provenance 恒为 user_supplied）
python ai_scientist/perform_ideation_temp_free.py evaluation import-review-response \
  --run-id <run_id> --idea-index <n> --response-file <model-output.txt> \
  --provider <provider> --model-id <model_id> --responded-at <UTC timestamp> \
  --supplied-by <who provided> --imported-by <who ran import>

# 4. 校验最新响应并生成记录 + 中文证据卡
python ai_scientist/perform_ideation_temp_free.py evaluation validate-review \
  --run-id <run_id> --idea-index <n>

# 修订：重复 2–4（新 rNNNN + 新 vNNNN，supersedes 前版）；旧文件永不改写。
```

exit 0 = 成功；exit 1 = 被拒（stderr 为 canonical JSON 错误，含 code）。`import-review-response` 有一个例外分支：响应已 write-once 落盘但解析失败时，结果 JSON（含 `parse_status: "invalid_format"`、`parse_error` 与保留的 `response_file` 路径）写在 stdout 并 exit 1——原始响应保留、显式报错，二者兼得。
