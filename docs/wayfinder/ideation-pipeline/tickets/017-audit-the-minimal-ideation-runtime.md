---
title: Audit the minimal ideation runtime
type: task
status: closed
assignee: runtime_audit
blocked_by: []
---

## Question

What imports, packages, commands, and platform assumptions are actually required to run preprocessing, ideation, and validation without installing or importing downstream dependencies?

## Resolution

[最小 ideation runtime 审计](../../../research/minimal-ideation-runtime-audit.md)（静态 import 追踪 + 隔离 Python 3.11.15 venv 实证）：现有 ideation 入口在标准库之外只需 `anthropic`、`backoff`、`openai`、`requests`、`tiktoken`，CPU-only，且无 downstream 模块被传递导入。`requirements.txt` 与此不符：`requests` 未声明、`tiktoken` 被 import 但未使用、多个已声明包仅服务 downstream 或从未被 import、且全无版本锁定。运行时 Semantic Scholar 仍在入口路径上，待 Scoped Literature Retriever 替换；`DeepSeek-V4-Pro-0813` 不在 `AVAILABLE_LLMS`；输出/resume 使用 workshop 旁的固定文件，无 run identity；preprocessing 与 idea validation 代码尚不存在。这些事实输入给 `Define the safe ideation entry`、`Define run identity and evidence layout` 和 DeepSeek adapter 相关 tickets；依赖策略问题已升格为 `Define the minimal runtime dependency contract`。
