---
title: Establish the testable ideation foundation
type: implementation
status: open
assignee: codex
blocked_by: []
---

# 01: Establish the testable ideation foundation

**What to build:** 建立可重复、可测试的 ideation 开发地基：精确区分最小 runtime、保留的 upstream/downstream 与开发依赖，锁定当前入口的 import closure，并在不改变 runtime 行为的前提下让 clean Python 3.13 环境能够运行完整现有验证。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Contract anchors:** [Preserve a compatible baseline](../../ideation-pipeline/tickets/006-preserve-a-compatible-baseline.md), [Audit the minimal ideation runtime](../../ideation-pipeline/tickets/017-audit-the-minimal-ideation-runtime.md), [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define the minimal runtime dependency contract](../../ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md).

- [ ] 三类依赖各有精确 pin，最小 runtime 集中的每个包都能指向当前使用方，开发工具不进入 runtime 契约，保留代码所需的 upstream/downstream 包不冒充 fork runtime。
- [ ] pytest 地基与 baseline smoke 可在 Python 3.13 clean environment 中重复执行，且修改前后的 ideation CLI 可观察行为一致。
- [ ] 准入 import guard 覆盖入口的传递闭包、内部模块精确 allowlist 与第三方 top-level allowlist；新增未声明模块或依赖时测试失败。
- [ ] 交付 `VM-CONTRACT-024-01` 与 `VM-ENV-01`，并保持全部已有测试通过。
- [ ] 仓库说明不再声称项目没有自动化测试；本票不修改任何 runtime 行为。
- [ ] 脱敏记录环境 lock、命令、pass/fail 与 commit evidence，且 Robert 完成本票验收。
