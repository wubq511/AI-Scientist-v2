---
title: Contract the legacy path and prove handoff readiness
type: implementation
status: closed
assignee: null
blocked_by:
  - 12-evaluate-every-finalized-idea-after-seal.md
---

# 13: Contract the legacy path and prove handoff readiness

**What to build:** 完成 expand-contract 的 contract 阶段：移除新 ideation path 对 global Semantic Scholar、旧 model/output controls、implicit sibling idea archive 与 import-time side effects 的可达性，收紧最终依赖闭包，并以完整 clean-environment 验证和代码审查证明实现可交给 smoke/Canary 阶段。

**Blocked by:** 12: Evaluate every finalized idea after seal.

**Status:** ready-for-agent

**Contract anchors:** [Modify the existing ideation path](../../ideation-pipeline/tickets/005-modify-the-existing-ideation-path.md), [Preserve a compatible baseline](../../ideation-pipeline/tickets/006-preserve-a-compatible-baseline.md), [Keep the runtime ideation-only](../../ideation-pipeline/tickets/013-keep-the-runtime-ideation-only.md), [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define the minimal runtime dependency contract](../../ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md).

- [x] 新 ideation entry 的传递 import/action closure 只包含批准的 ideation runtime；BFTS、experiments、plotting、write-up、review、global/remote literature search 与 accelerator-only assumptions 不可达。
- [x] Legacy providers 可继续服务保留代码，但不进入新路径；Semantic Scholar 与其 transitional dependency 随最后使用方离开 runtime closure，未使用 tokenizer dependency 同步移除。
- [x] 三类 dependency contracts 与最终实际 import closure 一致；import guard、仓库运行说明和命令示例同步到最终行为，upstream README 正文保持不动。
- [x] Python 3.13 clean environment 运行全部 pytest 与 preflight smoke；CPU reference path、macOS arm64 主平台通过，Python 3.12/3.14 compatibility candidates 按矩阵记录但不扩大承诺。
- [x] 重跑 Validation Matrix 全部已实现行，重点终验 `VM-ENV-01`、`VM-ENV-02`、`VM-ENV-03`、`VM-ENV-04` 与 `VM-CONTRACT-024-01`；任何失败不得绕过。
- [x] 对 implementation-map publication baseline 以来的完整实现 diff 执行代码审查，关闭所有阻塞发现，并提交脱敏命令、locks、pass/fail 与 hash 索引。
- [x] 本票只证明进入 smoke/Canary 的实现 readiness，不执行真实模型 run、不替 035/036 选参数；Robert 完成本票验收（2026-09-04 Robert 授权 agent 自验收后关闭）。

## Resolution

Contract 阶段完成（证据：[legacy-contract-handoff-evidence.md](../../research/legacy-contract-handoff-evidence.md)）：入口 `legacy` 子命令及全部 legacy 机器（S2 工具目录、legacy prompt 常量、`generate_temp_free_idea` 兄弟文件 archive、`--model`/输出路径参数）删除，入口传递 import closure 收紧为纯标准库并由 import guard 双层清单锁定；`requirements.txt` 空合同，`anthropic`/`backoff`/`openai`/`requests` 移入 `requirements-upstream.txt` 继续服务 retained legacy 代码，`tiktoken` 确认全仓库零引用。顺带修复探索发现的真实缺陷：入口在 Python ≤3.13 下因 `Path` 注解未导入而无法 import（3.14 的 PEP 649 曾掩盖）。Python 3.13.7 clean venv（binary-only）628 项 pytest 全绿 + preflight CLI smoke 通过 + 裸 venv 零第三方包 CLI 通过；3.12.13 记录 627/628（唯一差异为 argparse usage 折行的基准 hash，基准 pin 在 3.13）；3.14.6 clean/ambient 均 628 全绿。对 `cd25f36` 以来 64-commit 全量 diff 的双轴 review 关闭全部阻塞发现（常量双定义单源化、未登记 `IDEATION_EXECUTE` 隐藏开关移除、docstring/AGENTS.md 同步）。本票未执行真实模型 run、未产生费用、未替 035/036 选参数、未进入 downstream。

- 实现：`c359b42 feat: contract the legacy path out of the ideation entry`
- Review 修复：`391eac5 fix: close two-axis handoff review findings`
- 证据与文档：`eb611b4 docs: record legacy contract and handoff readiness evidence`

## Acceptance

2026-09-04 Robert 指示「验收你自行进行，确认没问题后 close」。自验收终态复核：`legacy` 子命令已被 argparse 拒绝（exit 2，invalid choice）；三契约测试（dependency/import/CLI baseline）终态全绿；README.md 不在 `cd25f36...HEAD` diff 中；工作树干净；全部验证数值与 [legacy-contract-handoff-evidence.md](../../research/legacy-contract-handoff-evidence.md) 记录一致（3.13.7 clean venv 628 passed、3.14.6 clean/ambient 628 passed、3.12.13 627/628 已按矩阵记录不扩大承诺）。双轴 review 非阻断判断项（命名惯例、`_private` 引用、provenance 默认值）按最小改动纪律维持不处理。Ticket 13 关闭；13 票实现序列完成，实现侧可移交 smoke/Canary 阶段。
