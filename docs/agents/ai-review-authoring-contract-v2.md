# AI 评审 authoring contract v2（单评审 + 双评审 + 成对盲评）

日期：2026-09-05  
状态：已实现（ticket [01-deliver-single-idea-ai-evaluation](../wayfinder/ai-assisted-ideation-evaluation/tickets/01-deliver-single-idea-ai-evaluation.md) 单评审；ticket [02-deliver-independent-and-pairwise-review](../wayfinder/ai-assisted-ideation-evaluation/tickets/02-deliver-independent-and-pairwise-review.md) 双评审与成对盲评）；本文件是机器校验行为的合同化说明，不授权付费调用。  
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
| 单评审 prompt 版本 | `single-review-v2`（模板 `ai_scientist/ideation/policies/ai-review-prompt-single-v2.md`，SHA-256 pin 于 contract.py；v1 历史版本在 git 历史中，旧 v1 响应不可与 v2 合并） |
| 评审执行配置 schema | `evaluation-review-execution-config-v1.0.0`（ticket 02） |
| 双评审共识记录 schema | `evaluation-ai-review-consensus-record-v2.0.0`（ticket 02） |
| 成对包 schema | `evaluation-pair-package-v1.0.0`（ticket 02） |
| 成对 model-visible 材料 schema | `evaluation-pair-materials-v1.0.0`（ticket 02） |
| 成对模型输出契约 | `ai-pair-review-response-v1.0.0`（ticket 02） |
| 成对评审记录 schema | `evaluation-ai-pair-review-record-v2.0.0`（ticket 02） |
| 成对还原记录 schema | `evaluation-ai-pair-reduction-record-v2.0.0`（ticket 02） |
| 成对评审 prompt 版本 | `pair-review-v1`（模板 `ai_scientist/ideation/policies/ai-review-prompt-pair-v1.md`，SHA-256 pin 于 contract.py；ticket 02） |

## 文件布局

```
artifacts/evaluations/<run_id>/ideas/<idea_index>/
  brief.md              # v1：人工阅读材料（不变）
  draft.json            # v1：人工填写中草稿（不变）
  v0001.json            # v1：人工 Evaluation Artifact（不变）
  ai/
    review-package.json # 匿名材料包（确定性、可重导出、逐字节一致）
    review-request.txt  # 渲染好的待发送请求（pinned 模板 + model_payload）
    primary/            # 评审一（slot）的隔离上下文（ticket 02 起按 slot 分目录）
      responses/rNNNN.json # 该 slot 导入的原始响应，write-once，user_supplied provenance
      vNNNN.json           # 该 slot 校验通过的 AI 评审记录，write-once + 线性 supersedes
      evidence-card.md     # 该 slot 的中文证据卡（确定性渲染，可重生成）
      evidence-card.html   # 同上，浅色单文件网页渲染
    second/             # 评审二（slot）：与 primary 完全隔离的同构目录
    consensus/
      vNNNN.json        # 双评审共识记录（ticket 02），write-once + 线性 supersedes
      consensus-card.md # 中文共识卡（确定性渲染）
      consensus-card.html
```

证据卡的权威内容以评审记录为准；md 与 html 是同一记录的两种确定性渲染，html 面向阅读（维度中文名、verdict 色标、弃权高亮），颜色仅为阅读辅助，不改变任何枚举语义。

## 材料包与信任边界

- **两层结构**：外层（`run_id`、`case_id`、`seal_sha256`、idea 哈希绑定、私有 `source_registry`）只在本地；`model_payload` 是评审模型可见的全部内容。model-visible 部分不含 run 身份、Prompt Profile 身份、baseline/challenger 映射、成本、运行顺序或期望结果；论文身份以包内 `S001…` 匿名 source ID 呈现，真实 `paper_id` 只存在于私有 registry。
- **来源**：Workshop 原文、sealed idea 七字段（逐字段可引用）、Target Comparator（title/DOI + abstract_summary + 完整 abstract，仅 post-seal 评审可见）、审计范围声明、sidecar 绑定检索操作返回的**全部**论文节选（含 Declared Grounding 之外的论文，逐条标注 `declared_grounding`）。
- **确定性**：材料包是 sealed run + pinned rubric + pinned prompt 模板的确定性函数；重复导出逐字节一致，成对 A/B、B/A 换位评审使用同一份 model payload。`import`/`validate` 都会从链上重推导并与磁盘字节比对（`REVIEW_PACKAGE_DRIFT` fail closed），`review-request.txt` 同样与 pinned 渲染结果比对（`REVIEW_REQUEST_DRIFT`）——操作者实际发送的请求不能无声漂移。
- **审计范围声明**（`audit_statement`，同时是可引用 source）：逐项列出检查的 complete/incomplete 与范围。当前派生事实：生成期 payload hygiene 对 finalized idea 通过；Workshop 语义审批通过（仅覆盖 Workshop 文本）；检索释放记录完整（限 sidecar 绑定操作）；**provider 训练侧污染审计 incomplete/not_performed**。判断受声明范围约束，incomplete 相关维度必须弃权或明确限定范围。

## 响应契约与验证规则

模型按 `single-review-v2` 模板输出一个 JSON 对象（`task: single_idea_review` + 七维 `dimensions`）。每维仅六个字段：`assessment_status`、`proposed_verdict`、`rationale`（中文）、`evidence_refs`、`key_assumptions`、`missing_information`。

v2 修订（2026-09-05，真实 smoke 证据驱动）：v1 模板下两次独立真实调用（不同响应）均在 `contamination_signal` 判 `judged` 时未引用 `audit_statement` 来源而触发 `AUDIT_STATEMENT_REF_REQUIRED`——维度表对 `contamination_signal` 的描述使模型不会联想到审计锚定。v2 仅做机械性强化：在「诚实边界」、维度表与边界例 2 中显式写明 `contamination_signal`/`leakage_review` 判 `judged` 时必须至少一条引用指向 `audit_statement` 来源。响应契约与校验规则不变。

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

一张证据卡 = 一个模型在一份材料上的一次可回链建议。它不能排除：模型共同错误、语义支持错判、材料范围外的污染与泄漏。两位异家族独立评审、换位检查与分歧保留由 ticket 02 交付（见上文「双评审汇总」与「成对盲评」）；单评审证据卡只用于 Robert 阅读与诊断，不改变任何 gate 行为。离线 fixtures 通过只证明软件契约；模型判断质量未经真实 smoke 验证前不得声称有效（见离线验证报告）。

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

## 评审执行配置（ticket 02）

独立复核的前提是两位评审确实来自不同 model families。执行配置（review execution config）是 workspace 级 write-once 文件 `artifacts/evaluations/ai-review-config.json`，由 Robert 用 `evaluation register-review-config --config-file <f>` 注册：

- 封闭 schema：恰好两个 evaluator（`slot` ∈ {`primary`, `second`}），各含 `provider`、exact `model_id` 与操作者声明的 `model_family`。family 分类是声明值，程序无法验证模型谱系，只强制**两个 slot 的 family 不得相同**（`REVIEW_CONFIG_FAMILIES_NOT_DISTINCT`——同模型的两个人设不是两位独立评审）、**exact model id 不得相同**（`REVIEW_CONFIG_MODELS_NOT_DISTINCT`），并逐字记录声明值、标注「程序未认证」。
- `prompt_versions` 在**注册时**必须精确匹配当前 pinned 的 `single-review-v2` / `pair-review-v1`（`REVIEW_CONTRACT_MISMATCH`）；**加载时**只做封闭 schema 校验，不再与当前常量重比——模板是合同内的版本化修订，注册声明不因会话中途的版本升级被追溯作废，版本兼容由每条 request/记录自带的 `prompt_version` 逐 artifact 强制。`real_call_authorization`（approved_by/approved_at/token_budget/cost_boundary/outbound_scope）为可选声明，注册本身不构成付费授权。
- 注册 write-once：重复注册（即使内容相同）`ARTIFACT_EXISTS`。config SHA-256 进共识记录与成对还原记录（`review_config_sha256`）。
- 已注册 config 时，`validate-review` 与 `validate-pair-review` 强制把响应声明的 provider/model_id 绑定到对应 slot（`REVIEW_CONFIG_MISMATCH`）；`aggregate-review` / `reduce-pair-review` 必须存在已注册 config（`REVIEW_CONFIG_NOT_FOUND`）。

## 双评审汇总（ticket 02）

两位评审各自走完整的单评审链路（export → 独立上下文 import → validate），存储在各自的 slot 目录；互相看不到对方的响应或记录。`evaluation aggregate-review --run-id <r> --idea-index <n>` 在两侧都已验证后合并：

- **逐维共识规则**：两方均 `judged` 且 `proposed_verdict` 相同 → `consensus`（保留双方原始 rationale，供核查共同错误）；verdict 不同 → `conflict`；任一方弃权 → `abstained`；某侧无已验证记录 → `incomplete_evaluator`。后三者都是 unresolved，并列双方理由。
- **一致负面保留为负面**：两位评审一致认为 `unsound`/`mismatched` 等负面 verdict 时，共识 verdict 原样保留为负面。
- **coverage 四态**：`complete_resolved`（七维全部共识）/ `complete_unresolved`（两方完成但有弃权或分歧）/ `invalid`（存在无效响应）/ `missing`（至少一侧缺少已验证记录或未验证）。invalid 与 missing 永远不能伪装成 complete_unresolved；slot 状态 vocabulary 为 `valid` / `invalid`（head 响应不可解析）/ `unvalidated`（已导入未验证）/ `missing`。
- **质量底线（pre-registered quality floor）**：五维问题判定（`problem_space_match=mismatched`、`feasibility_soundness=unsound`、`grounding_synthesis=name_dropped`、`contamination_signal=signal_found`、`leakage_review=leak_found`）任一达成共识即 `violated`；五维全部有共识且无问题判定即 `clean`；否则 `unresolved`。底线与整体结论独立，未决不等于通过。
- **防篡改再验证**：聚合时对每个 slot 的 head 记录做完整性重验——closed schema、run/case/seal/idea/包哈希/prompt/rubric 绑定、slot 与 `author_type=AI`、user_supplied provenance、线性 supersedes 链，并对绑定响应做深度校验（响应文本哈希、重解析一致、记录 judgments 与响应重推导逐字一致）；任何篡改 fail closed，不产出共识记录。
- 共识记录写入 `ai/consensus/vNNNN.json`（write-once + 线性 supersedes），并渲染中文共识卡 `consensus-card.md` / `.html`。共识卡是诚实的汇总建议：无晋升效力，宣称「双评审与换位检查降低但不能消除共同错误」。

## 成对盲评（ticket 02）

`ai_scientist/ideation/ai_pair_review.py` 从同一 case 的两个不同 sealed idea 构建可换位的匿名成对比较，全部产物位于 `artifacts/evaluations/pairs/<pair_id>/`：

### 导出与盲映射

- `evaluation export-pair-package --run-id-a <a> --idea-index-a <i> --run-id-b <b> --idea-index-b <j>` 推导确定性 pair 包（`pair-package.json`）+ 两个方向的待发送请求（`pair-request-ab.txt` / `pair-request-ba.txt`）。重复导出逐字节一致；`pair_id = "pair-" + sha256(canonical{arms, case_id})[:16]`。
- 匿名内容 `content_1` / `content_2` 按 (run_id, idea_index) 排序固定；盲映射 `ab: {arm_a: content_1, arm_b: content_2}`、`ba: {arm_a: content_2, arm_b: content_1}`。两位评审各自在**独立上下文**完成 A/B 与 B/A，共四次；没有任何机制在同上下文提醒其保持前次答案。
- 方向 payload 把共享 case 材料（Workshop、target abstract_summary、abstract，逐字节核验相同 `PAIR_MATERIAL_MISMATCH`）编为 `C###` source，两臂各自的 idea 字段、审计声明、检索节选编为 `A###` / `B###` source。model-visible payload 禁止携带 arm 身份、`content_1`/`content_2`、run/case/pair 身份、paper_id、profile 标识、成本或期望 winner——JSON key 与序列化文本双向扫描（`PAIR_PACKET_BLIND_LEAK`）。私有 `source_registry` 与 `blind_mapping` 留在外层文档供程序还原。
- 同 run 同 idea、或两臂 idea 载荷逐字节相同 → `PAIR_ARMS_IDENTICAL`；防御性的 case/target 不匹配 → `PAIR_CASE_MISMATCH` / `PAIR_TARGET_MISMATCH`。

### 四次独立评审与还原

- `import-pair-response` / `validate-pair-review` 按 `(evaluator slot, direction)` 四个隔离上下文存储与校验（`<slot>/<direction>/responses/rNNNN.json` + `vNNNN.json`），复用单评审的全部 fail-closed 规则（封闭 schema、三判断封闭枚举、引用逐字核验、「推断：」规则、request/pair 包漂移 `PAIR_REQUEST_DRIFT` / `PAIR_PACKAGE_DRIFT`、pinned 模板 `POLICY_DRIFT`、user_supplied provenance、线性 supersedes、config 绑定）。响应与 `(pair_id, direction, slot)` 强绑定，导入坐标不符 `IDENTITY_MISMATCH`。
- 成对响应契约（`ai-pair-review-response-v1.0.0`）：`task: pair_idea_review` + 三个判断——`overall_preference` / `domain_method_fit` ∈ {`a_better`, `b_better`, `tie`, `incomparable`}，`unjustified_ml_intrusion` ∈ {`a_more`, `b_more`, `equal`, `incomparable`}（均为显示侧 pair-relative 判断）。任一 `incomparable` 必须 `missing_information` 非空。
- `evaluation reduce-pair-review --pair-id <p>` 把四个显示侧 verdict 经盲映射还原到内容空间后归并：
  - **稳定结果**：四个有效判断指向同一内容（或四者全 tie / equal）→ `stable`，输出 `content_value`；
  - **incomparable**：其余一切——`position_flip`（同一 slot 在两方向偏好不同显示位）、`evaluator_conflict`（两 slot 各自一致但偏好不同内容）、`incomparable_judgment`（有效判断返回 incomparable）、`missing_valid_record`（任一上下文 invalid/unvalidated/missing，逐个点名）——原因逐条记录；
  - **有效结果不因方向不理想重跑**：程序不提供任何「重评以获得更好结果」的路径；无效格式显式记录失败并保留原始响应，任何修复调用都是新的物理调用与成本记录（真实 smoke 的费用责任在执行配置与 runbook）。
  - 还原时对全部四条记录做与双评审同级的完整性重验（响应哈希链 + 重推导 + 记录比对），篡改 fail closed；协议版本错配（模板漂移、prompt 版本不符、config 缺失）阻止合并。
- **质量底线独立保留**：每臂的底线状态取自该 idea 的双评审共识记录（`not_evaluated` / `clean` / `unresolved` / `violated`），随还原记录携带，永不被整体偏好覆盖。
- 产物：`reduction/vNNNN.json`（write-once + supersedes，含臂绑定、四方向记录引用、还原结果、质量底线）与中文还原报告 `pair-report.md` / `.html`（私有侧写明 content↔run 绑定与原因分类学）。

### CLI（ticket 02 新增六个子命令）

```bash
# 0. 注册评审执行配置（两位异 family 评审；write-once）
python ai_scientist/perform_ideation_temp_free.py evaluation register-review-config \
  --config-file <review-execution-config.json>

# 双评审（单条 idea，两位评审各一次）
python ai_scientist/perform_ideation_temp_free.py evaluation import-review-response \
  --run-id <r> --idea-index <n> --evaluator-slot {primary,second} ...   # 其余参数同上
python ai_scientist/perform_ideation_temp_free.py evaluation validate-review \
  --run-id <r> --idea-index <n> --evaluator-slot {primary,second}
python ai_scientist/perform_ideation_temp_free.py evaluation aggregate-review \
  --run-id <r> --idea-index <n>

# 成对盲评（两次导出之外共四次评审调用）
python ai_scientist/perform_ideation_temp_free.py evaluation export-pair-package \
  --run-id-a <a> --idea-index-a <i> --run-id-b <b> --idea-index-b <j>
python ai_scientist/perform_ideation_temp_free.py evaluation import-pair-response \
  --pair-id <p> --evaluator-slot {primary,second} --direction {ab,ba} \
  --response-file <f> --provider <p> --model-id <m> --responded-at <ts> \
  --supplied-by <who> --imported-by <who>
python ai_scientist/perform_ideation_temp_free.py evaluation validate-pair-review \
  --pair-id <p> --evaluator-slot {primary,second} --direction {ab,ba}
python ai_scientist/perform_ideation_temp_free.py evaluation reduce-pair-review --pair-id <p>
```

exit 约定与单评审一致（exit 0 成功 / exit 1 canonical JSON 错误；pair import 的解析失败同样保留原始响应并 exit 1）。

### 成对模式的证据限度

稳定 pair 结果是「两个不同 model family 的评审、在两个方向上一致收敛」的还原结论。它不能排除两模型的共同错误、语义支持错判、材料范围外的污染；它没有晋升效力——正式 comparison 消费 AI 评审记录需要 evaluation protocol manifest 与修订后的 Promotion Gate（ticket 03，另行实现），旧 Gate 继续拒绝 AI 记录。离线 fixtures 通过只证明软件契约；模型判断质量属六次真实 smoke（单条 ×2 + 合成 pair ×4）的验收对象，见 [ai-review-smoke-runbook.md](ai-review-smoke-runbook.md) 与离线验证证据报告。

## Comparison 接入（ticket 03）

本节是 v2 合同在 governed comparison 边界的消费侧实现说明（离线编码验收；执行顺序与前置条件见 [ai-review-migration-runbook.md](ai-review-migration-runbook.md)）。它只改变「谁可以担任判分角色」与「未决如何记账」，不改动 Proposal 002 的任何 pre-registered 判据。

### 评估协议清单（evaluation protocol manifest）

- 位置与注册：write-once `artifacts/evaluations/evaluation-protocol-manifest.json`（schema `evaluation-protocol-manifest-v1.0.0`）。CLI：`evaluation build-evaluation-protocol --out <f>`（从运行时代码 + 已注册 `ai-review-config.json` 重推导出确定性骨架，调用方只负责归档）→ `evaluation register-evaluation-protocol --manifest-file <f> --registered-by <who>`（write-once；重复注册把旧字节归档为 `evaluation-protocol-manifest-archived-<ts>.json`，永不删除）。
- 绑定内容：protocol id `ai-review-evaluation-protocol-v1`、汇总规则 id `ai-review-aggregation-v1`、authoring contract `evaluation-authoring-contract-v2.0.0`、prompt 版本（`single-review-v2` / `pair-review-v1`，注册时与代码常量重比，不符 `REVIEW_CONTRACT_MISMATCH`）、全部材料 schema 版本（11 项，注册时从代码重推导，漂移 `EVALUATION_PROTOCOL_MISMATCH`）、rubric schema、abstention policy（coverage 四态词汇表 + `unresolved_blocks_quality_pass: true`）与 `evaluator_binding_sha256`（= 已注册 `ai-review-config.json` 的 SHA-256）。
- 修订性质披露：manifest 固定携带 `revision_disclosure`（“post-first-output evaluation-protocol revision…”）——逐字不匹配即拒绝，防止把本修订冒充事前注册的人工盲评或独立科研验证。
- 加载重验：`load_evaluation_protocol` 每次加载都重算 config hash 并入档比对；config 被 supersede 后 manifest 立即不可加载（`EVALUATION_PROTOCOL_MISMATCH`）——两个协议下的记录不能合并。

### 覆盖分支（coverage branch）

- `evaluation list-ai-coverage`（schema `evaluation-ai-review-coverage-v1.0.0`）对每个 sealed run × finalized idea 用与 `aggregate-review` 相同的完整性重验推导五态：`missing`（至少一侧无已验证记录）/ `invalid`（存在不可解析响应）/ `unaggregated`（两侧有效但尚无共识记录）/ `complete_resolved` / `complete_unresolved`。
- ingestion 的 `_evaluation_coverage_for_run` 返回显式通道描述符：v1 人工 `evaluation_artifact_v1`（历史语义不变）或 v2 AI `evaluation_artifact_v2_ai`。缺失/无效 AI coverage fail closed（`EVALUATION_ARTIFACT_MISSING` / `EVALUATION_ARTIFACT_INVALID`；`unaggregated` 视为缺失——诚实汇总是协议的必需步骤）；`complete_resolved` 与 `complete_unresolved` 都 ingest；一个 run 同时携带两通道 fail closed（`EVALUATION_CHANNEL_CONFLICT`，一个矩阵一把判分尺）。

### AI 判定通道（vault `ai-verdicts/`）

- ComparisonVault 新增 write-once `ai-verdicts/` 目录（`record_ai_verdict` / `load_ai_verdict` / `ai_verdicts`），与 Robert 盲审 `verdicts/` 完全分离：AI 判定不满足 `verdicts_frozen`，不参与人工揭盲门槛；揭盲后记录 AI 判定同样 `VERDICT_AFTER_REVEAL`。
- AI 判定文档（schema `comparison-ai-verdict-v1.0.0`）在 content space 表达：`overall_preference`、`domain_method_fit`、`unjustified_ml_intrusion` 与每臂 `quality_floor` 状态，携带 `authorship.kind = ai_pair_reduction` 与 pair/config 哈希绑定。
- `ai_verdict_to_display` 把 content-space 文档投影到显示臂（核验两臂 run 绑定与 ingest 事实一致），产出与人工 verdict 相同的封闭枚举；`ai_verdict_facts` 组装 reducer 消费的判定 dict，绑定与人工通道相同的 `packet_sha256`——reducer 的 `VERDICT_PACKET_MISMATCH` 检查原样生效。

### 消费链（consume → record → reduce）

1. `consume_pair_reduction`（comparison_ai）：按 (case_id, 两臂 sealed run/idea) 定位恰好一条 complete + stable 的 pair 还原记录（`AI_PAIR_REDUCTION_NOT_FOUND` / `_AMBIGUOUS`），从 sealed 链重推导 pair 包、重验四个方向记录哈希与 head 还原记录（与 `reduce_pair_review` 同级完整性重验）；`AI_PAIR_NOT_COMPLETE` / `AI_PAIR_NOT_STABLE` 一律不可 ingest（绝不因结果不理想重跑）。要求已注册协议 manifest，且 package 的 `evaluation-protocol-pin.json` 里的 `review_config_sha256` 必须等于当前工作区 config 哈希。
2. `record_comparison_ai_verdict`：把消费结果写入 package vault 的 `ai-verdicts/`（write-once；case 已存在记录 `ARTIFACT_EXISTS`）。CLI：`evaluation record-comparison-ai-verdict --package-dir <p> --case-id <c> --baseline-run-id <b> --challenger-run-id <ch> --pair-index <n> --packet-sha256 <sha> --recorded-by <who>`。
3. reducer `reduce_prompt_comparison` 新增可选参数 `ai_verdicts` + `evaluation_protocol`，每个 pre-registered 闸门原样生效（3-0、domain-method fit、ML intrusion、rubric floor 经投影后的每臂 floor 状态、deterministic、challenger-only 异常、2.0× 包络、30 CNY 硬上限）。

### 新闸门与混用纪律

- `ai_quality_floor_unresolved`：每臂质量底线取自双评审共识记录；`violated` 由既有 rubric-floor 闸门拒绝，`unresolved` / `not_evaluated` 由本闸门拒绝（未决状态仍阻止晋升判断，符合规格 §5）。
- `evaluation_protocol`：reduction 文档内记录 `protocol_id`、`aggregation_rules_id` 与 `revision_disclosure`——消费结果永远自带「首条输出后修订」披露。
- 混用拒绝：一个 reduction 内 AI 与人工 verdict 并存 → `EVALUATION_PROTOCOL_MISMATCH`（矩阵全部 8 条结果使用同一评估协议）；有 `ai_verdicts` 而无 manifest → `EVALUATION_PROTOCOL_MISMATCH`（旧 Gate 继续拒绝 AI 记录）。
- 字节稳定：不传 `ai_verdicts`/`evaluation_protocol` 的 reduction 输出与修订前逐字节一致（无新闸门 key），人工通道完全不受影响。

### 评审费用台账与合并报告

- 独立 hash 链接台账 `artifacts/evaluations/evaluation-cost-ledger.json`（schema `evaluation-cost-ledger-v1.0.0`）：call kind 封闭枚举 `single_review` / `pair_review` / `repair`，记录物理调用次数与 CNY 成本；append-only（`entry_seq` 连续）、总额从条目重算、`last_entry_sha256` 哈希链接、落盘前检测并发修改（`EVALUATION_COST_LEDGER_DRIFT`）。CLI：`evaluation init-evaluation-cost-ledger --created-by`、`record-evaluation-cost …`、`evaluation-cost-report --package-dir <p>`。
- `merged_cost_report`（schema `evaluation-cost-merged-report-v1.0.0`）是只读合并视图：生成账本的金额字段逐字带入，评审台账另列，并携带固定披露「AI 评审调用费用不在生成 Plan Gate 批准范围内，需 Robert 单独显式授权」——评审费用永不静默扩展生成预算。

### 证据限度

本节的全部行为处于**离线编码验收**状态（全量 pytest 879 passed，迁移 rehearsal 见 `tests/test_comparison_migration_rehearsal.py` 与 `tests/test_evaluation_costs.py`）。真实六次基础 smoke 已于 2026-09-05 执行并通过（4/4，证据 [ai-review-real-smoke-evidence.md](../research/ai-review-real-smoke-evidence.md)）；但真实迁移未执行、评估协议修订未获 Robert 显式批准，因此旧 Gate 在批准前继续拒绝 AI 记录，本合同的 comparison 消费语义不构成任何晋升效力或付费授权。
