---
title: Evaluate every finalized idea after seal
type: implementation
status: closed
assignee: Robert
blocked_by:
  - 11-validate-and-export-a-trustworthy-evidence-chain.md
---

# 12: Evaluate every finalized idea after seal

**What to build:** 让 Robert 在 non-corrupt Run Seal 之后，为每个 finalized idea 组装 private Evaluation Brief、填写七项 categorical judgment、验证为 immutable Evaluation Artifact，并只读核算全部 sealed runs 的 coverage。

**Blocked by:** 11: Validate and export a trustworthy Evidence Chain.

**Status:** closed

**Contract anchors:** [Choose IdeaBench evaluation fidelity](../../ideation-pipeline/tickets/032-choose-ideabench-evaluation-fidelity.md), [Define the idea quality rubric](../../ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md), [Define the post-seal evaluation artifact contract](../../ideation-pipeline/tickets/037-define-the-post-seal-evaluation-artifact-contract.md).

- [x] Assemble 只读取 sealed、non-corrupt run、final idea/grounding/retrieval evidence 与 private Target Paper comparator，生成可重建 brief 和预填 linkage skeleton。
- [x] Validate 强制 canonical closed schema、hash linkage、七项 approved enums 与非空 rationales、authoring audit 和 linear supersedes；失败 draft 不成为 artifact。
- [x] 每个 finalized idea 独立计一份 artifact，包括 terminal `failed` run 中已成功 committed 的 ideas；不产生 numeric score、overall score、LLM judgment 或 sanitized stub。
- [x] Read-only coverage 对 seal inventory 给出 `covered`、`draft_only`、`missing`，不改写 run evidence 或 evaluation artifacts。
- [x] 交付 `VM-QUAL-01`，并保持全部已有测试通过；Robert 的 verdict 内容本身不作机器判分。
- [x] 同步受影响的仓库运行说明，记录脱敏 schema/coverage evidence，且 Robert 完成本票验收。

## Resolution

2026-09-04 agent 交付并经双轴（Standards + Spec）code-review 修复后关闭。核心落地：

- `evaluation.py` 实现 `assemble_evaluation_brief`：进入评估的硬前提是 sealed + non-corrupt（先跑 `validate_evidence_chain(check_sealed=True)`）；idea/grounding/sidecar 按 seal inventory path+hash 逐字节核验，retrieval 摘录严格沿事件链取回模型实际所见 payload（各层形状 fail-closed 校验，畸形即 `RUN_CORRUPT`/缺 ref 即 `EVALUATION_LINKAGE_INCONSISTENT`）；Target Paper comparator 经 Workshop Manifest 绑定推导并对 target 数据源做 dataset/row 双级 hash 校验。产出确定性 `brief.md`（无时间戳、可覆盖重建）与预填 linkage 的 `draft.json` skeleton（已存在绝不覆盖）。
- `evaluation.py` 实现 `validate_evaluation_artifact`：全确定性 fail-closed 校验（封闭 schema、全 hash linkage、七项封闭 enum、非空 rationale、authoring audit、`brief_sha256` 防 stale、linear supersedes），通过后 O_EXCL write-once 提交 `v%04d.json` 定稿；失败不留定稿、draft 原样保留。
- `evaluation.py` 实现 `list_evaluation_coverage`：只读三态核算（`covered` 要求 supersedes 链 head 通过与 validate 同源的 `mode="final"` 校验；head 非法附 `head_error`）；corrupt 与 unevaluable run 单列且其 ideas 不进三态统计，summary 分别计数；不改写任何 evidence 或 artifacts。
- 版本化 rubric 策略 `policies/idea-quality-rubric-v1.json`（七项 criterion + 封闭 verdict enums）以 SHA-256 pin 进 `contract.py`（schema 版本常量同位），篡改即 `POLICY_DRIFT`；criteria 增删改走新版本 + Robert 批准（026.6）。
- 私有存储布局 `artifacts/evaluations/<run_id>/ideas/<idx>/`（brief/draft/write-once 定稿），`.gitignore` 与逐级 symlink 防护同 run root 同级；terminal `failed` run 中已 committed idea 同样可评估（037.5）；全程无 numeric/overall score、无 LLM judgment、无 sanitized stub（032 红线）。
- CLI 增加 `evaluation assemble|validate|list-coverage` 子命令（结构化 stdout/stderr 与 exit 码）；`--help` baseline hash 与准入导入闭包门禁同步更新。

验收证据（2026-09-04，StubTransport 全零网络零费用）：全量 pytest 628 passed（新增 59 项全量通过，含 21 项负向 draft 参数化、13 项畸形 linkage 形状 fail-closed 参数化、supersedes 链、coverage 三态/异常 run/read-only、CLI seam）；`compileall` 与触及文件 `black` 检查通过（全树 14 处既存 upstream 漂移为基线状态，与本票无关）。脱敏 schema/coverage 说明与运行说明见 [post-seal-evaluation-evidence.md](../../../research/post-seal-evaluation-evidence.md)。
