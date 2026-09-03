---
title: Contract the legacy path and prove handoff readiness
type: implementation
status: open
assignee: null
blocked_by:
  - 12-evaluate-every-finalized-idea-after-seal.md
---

# 13: Contract the legacy path and prove handoff readiness

**What to build:** 完成 expand-contract 的 contract 阶段：移除新 ideation path 对 global Semantic Scholar、旧 model/output controls、implicit sibling idea archive 与 import-time side effects 的可达性，收紧最终依赖闭包，并以完整 clean-environment 验证和代码审查证明实现可交给 smoke/Canary 阶段。

**Blocked by:** 12: Evaluate every finalized idea after seal.

**Status:** ready-for-agent

**Contract anchors:** [Modify the existing ideation path](../../ideation-pipeline/tickets/005-modify-the-existing-ideation-path.md), [Preserve a compatible baseline](../../ideation-pipeline/tickets/006-preserve-a-compatible-baseline.md), [Keep the runtime ideation-only](../../ideation-pipeline/tickets/013-keep-the-runtime-ideation-only.md), [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define the minimal runtime dependency contract](../../ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md).

- [ ] 新 ideation entry 的传递 import/action closure 只包含批准的 ideation runtime；BFTS、experiments、plotting、write-up、review、global/remote literature search 与 accelerator-only assumptions 不可达。
- [ ] Legacy providers 可继续服务保留代码，但不进入新路径；Semantic Scholar 与其 transitional dependency 随最后使用方离开 runtime closure，未使用 tokenizer dependency 同步移除。
- [ ] 三类 dependency contracts 与最终实际 import closure 一致；import guard、仓库运行说明和命令示例同步到最终行为，upstream README 正文保持不动。
- [ ] Python 3.13 clean environment 运行全部 pytest 与 preflight smoke；CPU reference path、macOS arm64 主平台通过，Python 3.12/3.14 compatibility candidates 按矩阵记录但不扩大承诺。
- [ ] 重跑 Validation Matrix 全部已实现行，重点终验 `VM-ENV-01`、`VM-ENV-02`、`VM-ENV-03`、`VM-ENV-04` 与 `VM-CONTRACT-024-01`；任何失败不得绕过。
- [ ] 对 implementation-map publication baseline 以来的完整实现 diff 执行代码审查，关闭所有阻塞发现，并提交脱敏命令、locks、pass/fail 与 hash 索引。
- [ ] 本票只证明进入 smoke/Canary 的实现 readiness，不执行真实模型 run、不替 035/036 选参数；Robert 完成本票验收。
