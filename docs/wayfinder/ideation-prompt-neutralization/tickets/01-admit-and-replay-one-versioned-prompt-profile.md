---
title: Admit and replay one versioned Prompt Profile
type: implementation
status: closed
assignee: agent
blocked_by: []
---

# 01: Admit and replay one versioned Prompt Profile

**What to build:** 让 operator 能通过现有安全 Ideation Run lifecycle 选择封闭、版本化的 baseline 或 cross-domain Prompt Profile，并让 fresh run、resume、validation 与 sanitized export 始终使用 Run Admission 固定的同一 profile；全票只使用 recorded/mock transport，不发起真实 provider request。

**Blocked by:** None (can start immediately).

**Status:** closed (2026-09-04, implemented and verified; see session log `work-logs/sessions/2026-09-04_12-44.md` appended entry).

**Specification:** [Cross-domain Ideation Prompt qualification](../../../agents/cross-domain-ideation-prompt-spec.md).

- [x] `new-run` 只接受 `ml-baseline-v1` 与 `cross-domain-v1` 两个 profile id；自由 prompt 文本、路径、fragment、未知 id 和额外配置键全部 fail closed，且不开放任意 `reasoning_effort`、`max_tokens`、model、provider 或 endpoint 覆盖。
- [x] 新 Run Request 与 Run Admission 使用新版本封闭 schema（`run-request-v1.1.0` / `run-admission-v1.1.0`），记录 resolved profile id、profile contract version 与完整 canonical prompt bundle SHA-256（外加 registry hash）；admission 前验证 registry 与 hash，admission 后 controller 再验证一次才允许 model operation。
- [x] `ml-baseline-v1` 的 system、generation、reflection、tool/action 和 idea-field model-visible 语义与当前生产 baseline 一致（SHA-256 golden：system `d2c000…62d`，generation `b933e8…035`，reflection `8ed8f5…47f7`，对照实现前 HEAD 提取的字节）；`cross-domain-v1` 精确实现规格批准的 multidisciplinary role、field-appropriate methods/feasibility、field-neutral Abstract/Title/validation-plan 与 field-aware reflection。
- [x] 两个 profiles 的工具面都严格保持 `SearchLiterature` + `FinalizeIdea`，七字段 idea payload、Declared Grounding、Workshop 注入、previous-idea diversity 与 action/JSON protocol 不变。
- [x] fresh run 只从已解析 profile 构造 prompt；resume 只从原 Run Admission 的 profile id/hash 重建，拒绝 registry drift、hash mismatch、unknown version 或试图改 profile 的 resume，不读取 mutable default。
- [x] legacy Run Request/Admission、sealed evidence、export 和 suspended resume 保持可验证；缺少 profile 字段的 legacy admission（v1.0.0）永远解释为 `ml-baseline-v1`，不随未来默认值变化或被改写；legacy 文档不得携带 profile 字段。
- [x] sanitized manifest 只公开安全的 profile id/version/hash，不公开 prompt text、Workshop、Target、retrieval text、response、reasoning、idea、provider id 或 credential；private Provider Attempt request 继续保留实际 model-visible prompt 以供链内审计。
- [x] 使用 recorded/mock transport 从 CLI/parser 到 admission、controller、seal、static validation、export 和 resume 对两个 profiles 做端到端零网络测试（`tests/test_prompt_profile_lifecycle_e2e.py`，12 tests）；另有 byte-stability、baseline preservation、cross-domain forbidden-mandate、unknown/drifted profile 与 legacy compatibility 契约测试（`tests/test_prompt_profiles.py`，17 tests）。
- [x] 同步 prompt diff 围栏（024 修订注）、Run Specification、safe-entry（pipeline spec 三处修订）和 validation-matrix（v1.1，新增 VM-CONTRACT-024-04/05/06、VM-CONTRACT-023-04）的权威合同，使新增 seam 被明确批准且不被误解为第四个 dependency-injection seam；运行全量 pytest（691 passed）、compileall、目标范围 Black、import/dependency 与 diff 检查。
- [x] 提交脱敏验证证据并关闭本票；全程不读取活动 credential 值、不调用 DeepSeek、不产生费用、不改变生产默认 profile（default 仍为 `ml-baseline-v1`，cross-domain-v1 仅可被显式选择进入 governed comparison）、不启动 4-pair comparison 或 ticket 035。

## Implementation notes

- 新模块 `ai_scientist/ideation/profiles.py`：封闭、版本化 profile registry（in-code 常量 + `contract.PROMPT_PROFILE_REGISTRY_SHA256` hash pin），`resolve_profile` / `validate_profile_field` / `resolve_admission_profile` / 三个 render 函数。Registry SHA-256：`658fcb028e5d649a1a08caae7824684d7fe8e95af6c494970c2f45f2071822d7`；profile bundle SHA-256：`ml-baseline-v1` = `0eef0489b59e0c6883c2e9c0dac351e1eac5ce53309513d59c7f7c3b9c748793`，`cross-domain-v1` = `735eda9eddf74a58eec4917234c5fe6960c476ed7905e15d9e3496dde3a21992`（canonical bundle 文档含 system/generation/reflection/tool-descriptions/tool-names 模板与 contract version）。
- `admission.py`：`NewRunRequest` 增加 `prompt_profile_id`（默认 `ml-baseline-v1`，但 CLI 强制显式传入）；`validate()` 在 Step 1 fail-closed 解析 profile；request/admission 文档携带封闭四键 `prompt_profile` pin。
- `controller.py`：构造时 `resolve_admission_profile(admission)`（admission 后、model 前的第二次验证）；`_run_loop` / `_run_resumed` / `_execute_generation` / `rebuild_resume_plan` 全部经 profile 渲染 prompt，fresh 与 resume 路径同一 seam。`IDEA_GENERATION_PROMPT` / `IDEA_REFLECTION_PROMPT` / `build_system_prompt` / `build_tool_catalog` 保留为 canonical evidence（测试从 HEAD 提取 golden）。
- `resume.py`：admission pin 复核增加 profile 字段重验证 + request/admission pin 一致性；legacy admission 无 profile 字段恒 baseline；new-schema admission 缺字段 fail closed。
- `evidence.py`：validator 接受 v1.0.0/v1.1.0 两版本 request/admission；对每个 admission 重解析 profile；sanitized manifest 新增只含 id/version/hash 的 `prompt_profile` 段；`FORBIDDEN_KEY_PATTERNS` 增补三个模板键作纵深防御。
- `run_store.py`：schema 版本 v1.1.0 + 双版本支持常量。
- CLI：`new-run` 新增必需 `--prompt-profile <id>`；command 记录包含该 flag；`--help` 中不含任何模型/provider/endpoint/prompt 文本覆盖旗标。
- 生产 default 不变（`ml-baseline-v1`）；`cross-domain-v1` 已可执行但仅在 comparison 中显式选用。

## 对抗性审查修复记录 (2026-09-04, post-close)

- Commit `3428909`（fix: close adversarial review findings in comparison boundary）落地后，本票 deliverable 未受实质影响：F7 死代码清理触及的是共享 comparison 代码（`ai_scientist/ideation/comparison.py` + `tests/test_prompt_comparison.py`），不涉及本票的 profile seam（`profiles.py` / `admission.py` / `controller.py` / `resume.py` / `evidence.py` / `run_store.py`）。
- 本票的 baseline 字节保持声明已在 post-close 对立审查中独立复验：从实现前 commit `849336b` 重算 golden hashes（system `d2c000…62d`、generation `b933e8…035`、reflection `8ed8f5…47f7`，外加 registry/bundle hash），与当前 `profiles.py` 渲染输出五个组件逐一比对完全相同；该结论不受 commit `3428909` 任何修复影响。