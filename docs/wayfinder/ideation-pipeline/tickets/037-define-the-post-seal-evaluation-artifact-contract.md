---
title: Define the post-seal evaluation artifact contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 026-define-the-idea-quality-rubric.md
---

## Question

What fixed fields, run/case linkage, storage layout, authoring workflow, and validation rules define the Evaluation Artifact that records Robert's structured qualitative comparison of one sealed run's final idea against its unsealed Target Paper, as decided by [Choose IdeaBench evaluation fidelity](032-choose-ideabench-evaluation-fidelity.md)?

## Resolution

2026-08-30 经 grilling 两轮十一题由 Robert 批准。本票把 [Choose IdeaBench evaluation fidelity](032-choose-ideabench-evaluation-fidelity.md) 的 sealed qualitative comparator 立场与 [Define the idea quality rubric](026-define-the-idea-quality-rubric.md) 的七项 post-seal criteria 落成可确定性验证的 private artifact 合同。

1. **载体与格式**：canonical JSON 单文件、schema 版本化，复用 [Define run identity and evidence layout](023-define-run-identity-and-evidence-layout.md) 的 canonical bytes 合同（UTF-8/NFC/key 排序/LF/SHA-256）。artifact write-once：更正不原地改，产生新版本文件并以 `supersedes` 指针指向前版。
2. **存储布局与隐私**：独立 private root `artifacts/evaluations/<run_id>/`，gitignored，按 `run_id` 寻址；实现时必须补 `.gitignore` 条目，与 `artifacts/ideation-runs/` 同等处理。不产出 sanitized stub：评估完成事实属私有过程状态，面试叙事的聚合结论由报告 prose 承载（[Retain auditable run evidence](010-retain-auditable-run-evidence.md) 已允许 commit conclusions）。
3. **Linkage 字段集**：`run_id` + `seal.json` hash（证明对照对象已封定）；final idea 引用用 023 既有机制 `run_id + run-relative path + SHA-256`，不引入 `artifact_id`；`case_id`；Target Paper 引用 = Workshop Manifest 的 source dataset path/hash + canonical target-row hash + 明文 title/DOI（artifact 本身 private，无泄漏顾虑）；`rubric_version` + artifact 自身 `schema_version`。
4. **字段结构**：七项 criterion 每项 = `{verdict: <封闭 enum>, rationale: <非空短文本>}`；禁止数值分与总分（032 红线：不给 benchmark 可比性暗示），不设 overall 汇总字段，整体判断由 Robert 在报告层综合。逐项 enum：
   - 问题空间匹配度：`aligned / adjacent / mismatched`
   - 与 target contribution 的重叠性质：`recover / partial_overlap / materially_different`
   - 相对 novelty：`beyond_target / on_par / below_target`
   - feasibility 合理性：`sound / questionable / unsound`
   - 污染信号检查：`none_found / signal_found`（`signal_found` 时纪律要求 rationale 描述具体信号）
   - 泄漏复核：`clean / leak_found`
   - grounding 综合质量：`synthesized / partially_synthesized / name_dropped`

   rationale 非空、建议 1–3 句、v1 不设硬长度上限。固定 header 含 schema/rubric version、author、timestamps 与上述 linkage。
5. **粒度与触发**：每个 finalized idea 一份 artifact，不论 terminal outcome——`failed` run 中已 finalize 的 idea 同样是有效评估样本。CONTEXT.md 的 Evaluation Artifact 定义相应精确化。
6. **Authoring workflow**：两阶段。`assemble` 读取已 sealed 且非 corrupt 的 raw run 与 private target 记录，产出 private 对照 brief（idea 七字段 + declared grounding + 各 declared paper 的 retrieval segment 摘录 ‖ target `abstract_summary` + 完整 abstract）与预填 linkage 的 skeleton；Robert 填写后 `validate` 验收并写入自含审计字段（032「自带审计记录」）：`assembled_by`、`assembled_at`、`brief_sha256`、`authored_by`、`authored_at`、`validated_by`、`validated_at`、`validation_result`。不另建 index 文件，不做交互式逐项提问 CLI。
7. **子布局与版本**：`artifacts/evaluations/<run_id>/ideas/<zero-padded-idea_index>/` 下 `brief.md`（阅读材料而非证据，重新 assemble 直接覆盖，artifact 审计字段记录当时所看 brief 的 hash）、`draft.json`（填写中工作文件，不计入任何链）、`v<zero-padded seq>.json`（validate 通过后的定稿）。`supersedes` 链线性：只有尚未被 supersede 的最新定稿可被 supersede；某 run/idea 的有效 artifact = 链上最新定稿，旧版仅作历史保留。
8. **Validation 规则**（全部确定性、fail closed）：canonical bytes + 封闭 schema（未知字段 fail）；linkage 完整性（run root 存在、`seal.json` hash 匹配、所引 idea 在 seal inventory 且 hash 匹配、run 非 corrupt——023 已定 corrupt run 禁止进入 evaluation）；`case_id` 与 `request.json` 一致；target 引用与该 case 的 Workshop Manifest 记录一致；`rubric_version` 属于已批准版本、`schema_version` 为当前支持版本；七项齐全、verdict 在 enum 内、rationale 非空；`supersedes` 合法（目标存在、同 run/idea、尚未被 superseded）。任一失败不产生定稿，draft 保留原样，不计入该 run 的强制 artifact，无 Git 侧输出。
9. **覆盖率核算**：只读 `list-coverage` 命令扫描全部 seal inventory × `artifacts/evaluations/`，输出每个 sealed run 每个 finalized idea 的覆盖状态（`covered / draft_only / missing`）；输出 private、不进 Git。覆盖门槛决策不归本票——canary 100% 覆盖的执行与扩量后抽样规则归 [Define canaries and scale gates](028-define-canaries-and-scale-gates.md)，本票只保证覆盖事实可被确定性核算。

衍生动作：CONTEXT.md 精确化 Evaluation Artifact 术语（每 finalized idea 一份）并新增 Evaluation Brief 术语；实现 ticket 落地时须补 `.gitignore` 条目与 assemble/validate/list-coverage 工具（归实现票执行，不在本 map 的规划范围内）。

本 ticket 只锁定 Evaluation Artifact 合同；未实现工具、未读取 run 证据、未调用模型、未进入 downstream。
