---
title: Record one validated DeepSeek model round
type: implementation
status: closed
assignee: codex
blocked_by:
  - 04-admit-an-ideation-run-without-paid-work.md
---

# 06: Record one validated DeepSeek model round

**What to build:** 让 controller 通过 DeepSeek-only adapter 和 recorded/stub transport 完成一个 model round，得到经过 provider-contract 验证的 typed result 或 typed failure、独立 Provider Attempts、usage/cost evidence 与可重放 artifact；本票不发真实请求。

**Blocked by:** 04: Admit an Ideation Run without paid work.

**Status:** accepted

**Contract anchors:** [Choose the DeepSeek provider and version contract](../../ideation-pipeline/tickets/031-choose-the-deepseek-provider-and-version-contract.md), [Define the DeepSeek adapter contract](../../ideation-pipeline/tickets/022-define-the-deepseek-adapter-contract.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md).

- [x] Adapter 固定 approved DeepSeek direct/non-streaming Chat Completions/model/tool boundary，caller 只能提供批准的 messages、controlled parameters、output mode 与 opaque user identity。
- [x] Provider success、usage invariants、reasoning/content separation、serialization 与 centralized redaction 按合同执行，SDK object 和 credential 不越过 adapter boundary。
- [x] 每个 physical request 产生独立 Provider Attempt；批准的 transient classes 最多重试一次，ambiguous 与 deterministic failures 不隐藏重试或降级。
- [x] 封闭 failure taxonomy 与 controller disposition 查表一致；recorded response 重放产生相同 canonical artifacts/hashes。
- [x] 交付 `VM-UNIT-07`、`VM-CONTRACT-022-01`、`VM-CONTRACT-022-02`、`VM-CONTRACT-022-03`、`VM-REPLAY-01` 与 `VM-FAULT-01`，并保持全部已有测试通过。
- [x] 本票零 network、零真实模型费用；同步受影响的仓库运行说明，记录脱敏 evidence，且 Robert 完成本票验收。

## Implementation Evidence

- 实现文件：`ai_scientist/ideation/deepseek.py`、`tests/test_deepseek_adapter.py`。
- 脱敏证据：[DeepSeek adapter 验证证据](../../../research/deepseek-adapter-evidence.md)。
- 验证矩阵交付：`VM-UNIT-07`、`VM-CONTRACT-022-01`、`VM-CONTRACT-022-02`、`VM-CONTRACT-022-03`、`VM-REPLAY-01`、`VM-FAULT-01` 全部交付并通过（70 项新增测试全绿，全量回归 `433 passed in 47.80s`）。
- 双轴审查（Standards 轴与 Spec 轴）全部通过，零 hard findings。

## Resolution

DeepSeek-only adapter 与 model round 执行逻辑已落地并验收关闭：
1. 固化直连 `https://api.deepseek.com` 与 `deepseek-v4-pro` 浮动别名，显式禁用 SDK 隐式重试（`max_retries=0`），caller 只能提供 messages、controlled parameters、output mode 与 user identity，任何未知参数或覆盖尝试立即 fail closed（`configuration` 终端错误）；
2. 固化 Provider Success 强判据：严格比对模型 ID、要求 `finish_reason="stop"`、content 非空、json_object 模式顶级字典结构及 Usage 四项不变量（`prompt=hit+miss`、`total=prompt+completion`、`0<=reasoning<=completion`、全非负整数），违规即终端失败，不使用 tokenizer 伪造或估算；
3. 固化 16 枚举封闭 Failure Taxonomy 与严格二值查表（7 个 suspend，9 个 terminal）；每个物理请求排他落盘 `request.json`、`response.json`/`failure.json`，计算基于时段与真实 usage 的 CNY 费用，并发出 `provider_attempt.finished` 事件；仅批准的 3 类 transient 故障最多重试 1 次（单 operation ≤2 attempts），`timeout_ambiguous` 与 `transport_ambiguous` 绝不重试；
4. 交付全部 6 项验证矩阵行，全套 433 项自动化测试全绿，零模型调用、零外部网络、零费用，未进入 BFTS 或其他 downstream 阶段。

