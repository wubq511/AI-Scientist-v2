---
title: Admit and replay one versioned Prompt Profile
type: implementation
status: open
assignee: null
blocked_by: []
---

# 01: Admit and replay one versioned Prompt Profile

**What to build:** 让 operator 能通过现有安全 Ideation Run lifecycle 选择封闭、版本化的 baseline 或 cross-domain Prompt Profile，并让 fresh run、resume、validation 与 sanitized export 始终使用 Run Admission 固定的同一 profile；全票只使用 recorded/mock transport，不发起真实 provider request。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Specification:** [Cross-domain Ideation Prompt qualification](../../../agents/cross-domain-ideation-prompt-spec.md).

- [ ] `new-run` 只接受 `ml-baseline-v1` 与 `cross-domain-v1` 两个 profile id；自由 prompt 文本、路径、fragment、未知 id 和额外配置键全部 fail closed，且不开放任意 `reasoning_effort`、`max_tokens`、model、provider 或 endpoint 覆盖。
- [ ] 新 Run Request 与 Run Admission 使用新版本封闭 schema，记录 resolved profile id、profile contract version 与完整 canonical prompt bundle SHA-256；admission 前验证 registry 与 hash，admission 后 controller 再验证一次才允许 model operation。
- [ ] `ml-baseline-v1` 的 system、generation、reflection、tool/action 和 idea-field model-visible 语义与当前生产 baseline 一致；`cross-domain-v1` 精确实现规格批准的 multidisciplinary role、field-appropriate methods/feasibility、field-neutral Abstract/Title/validation-plan 与 field-aware reflection。
- [ ] 两个 profiles 的工具面都严格保持 `SearchLiterature` + `FinalizeIdea`，七字段 idea payload、Declared Grounding、Workshop 注入、previous-idea diversity 与 action/JSON protocol 不变。
- [ ] fresh run 只从已解析 profile 构造 prompt；resume 只从原 Run Admission 的 profile id/hash 重建，拒绝 registry drift、hash mismatch、unknown version 或试图改 profile 的 resume，不读取 mutable default。
- [ ] legacy Run Request/Admission、sealed evidence、export 和 suspended resume 保持可验证；缺少 profile 字段的 legacy admission 永远解释为 `ml-baseline-v1`，不得随未来默认值变化或被改写。
- [ ] sanitized manifest 只公开安全的 profile id/version/hash，不公开 prompt text、Workshop、Target、retrieval text、response、reasoning、idea、provider id 或 credential；private Provider Attempt request 继续保留实际 model-visible prompt 以供链内审计。
- [ ] 使用 recorded/mock transport 从 CLI/parser 到 admission、controller、seal、static validation、export 和 resume 对两个 profiles 做端到端零网络测试；另有 byte-stability、baseline preservation、cross-domain forbidden-mandate、unknown/drifted profile 与 legacy compatibility 契约测试。
- [ ] 同步 prompt diff 围栏、Run Specification、safe-entry 和 validation-matrix 的权威合同，使新增 seam 被明确批准且不被误解为第四个 dependency-injection seam；运行全量 pytest、compileall、目标范围 Black、import/dependency 与 diff 检查并完成 Standards/Spec review。
- [ ] 提交脱敏验证证据并关闭本票；全程不读取活动 credential 值、不调用 DeepSeek、不产生费用、不改变生产默认 profile、不启动 4-pair comparison 或 ticket 035。
