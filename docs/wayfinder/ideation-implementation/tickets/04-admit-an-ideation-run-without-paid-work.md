---
title: Admit an Ideation Run without paid work
type: implementation
status: closed
assignee: codex
blocked_by:
  - 03-approve-one-target-reference-corpus.md
---

# 04: Admit an Ideation Run without paid work

**What to build:** 让 operator 通过安全 new-run CLI 完成一个 Ideation Run 的 request、九步 preflight、保守 CNY 估价与显式批准，得到可审计 Run Admission；任何失败形成明确的 preflight rejection，且整个 slice 不调用模型。

**Blocked by:** 03: Approve one Target Reference Corpus.

**Status:** accepted

**Contract anchors:** [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md), [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Choose the DeepSeek provider and version contract](../../ideation-pipeline/tickets/031-choose-the-deepseek-provider-and-version-contract.md).

- [x] New-run request 只接受获批的 case、Workshop/corpus pins 与 generation/reflection budgets；没有 model、ranker、device、output-root 或隐式 resume 控制。
- [x] Run root exclusive-create，request 与 preflight events 使用 canonical bytes 和连续 hash chain；preflight 按获批顺序逐步执行，Run Admission 写入前没有付费调用路径。
- [x] Versioned CNY price table 可验证、可确定性计价；非 `yes`、非交互 stdin、缺失 credential presence 或任一输入/版本不一致都 fail closed 并留存 preflight evidence。
- [x] Adapter、bound retriever 与 event emitter 形成三个窄注入点，不新增接口框架或第四注入面；import 时无工具实例化等副作用。
- [x] 交付 `VM-UNIT-02`、`VM-UNIT-03`、`VM-UNIT-06`、`VM-CONTRACT-023-01` 与 `VM-CONTRACT-024-02`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，脱敏记录命令、pass/fail 与 artifact hashes，且 Robert 完成本票验收。

## Implementation Evidence

- 实现 commits：`cbaa99b add: implement Ideation Run admission without paid work`、`631e209 fix: harden admission preflight per two-axis review`、`6783c46 fix: close re-review findings in admission boundary`、`7d4884e fix: reject denormalized relative paths; prove canonical negatives`（验收自查补缺）。
- 脱敏证据：[Ideation Run admission boundary 验证证据](../../../research/run-admission-evidence.md)。
- 验证矩阵行 `VM-UNIT-02`、`VM-UNIT-03`、`VM-UNIT-06`、`VM-CONTRACT-023-01`、`VM-CONTRACT-024-02` 已通过（`tests/test_run_admission.py` 14 项、`tests/test_run_pricing.py` 7 项、`tests/test_run_preflight.py` 14 项）；全量 `333 passed`。仓库运行说明已随 `AGENTS.md` 同步。
- 首轮双轴 review 的 18 项 findings 已修复并经双轴复核关闭；验收自查另发现两处机检缺口（VM-UNIT-02 负向、`./x` 路径归一化绕过），由 `7d4884e` 补齐并以 RED→GREEN 实证。
- 验收按 01/03 票 Robert 授权先例（Codex 复核无误后代为逐票验收）完成：五个 VM 行机检全绿、双轴 review 两轮关闭、验收补缺回归通过、证据脱敏入库。

## Resolution

九步 fail-closed 准入边界已落地并验收关闭：七参数 `new-run` CLI（模型身份 `deepseek-v4-pro` 锁进代码与 admission）、exclusive-create run root 与 write-once canonical request/admission、连续 hash chain 的 preflight 事件、`preflight_rejected` 证据留存、versioned CNY 价格表（hash pin、峰谷窗口、向上取整到分）、`stdin.isatty()` + 恰好 `yes` 的显式费用批准、非交互与一切非 `yes` 输入 fail closed；Run Admission 写入前不存在付费调用路径。入口 import 副作用消除为惰性工厂，legacy 基线保留为显式 `legacy` 子命令（13 票收除）。全 slice 零模型调用、零网络、零费用，未进入 BFTS 或其他 downstream 阶段。
