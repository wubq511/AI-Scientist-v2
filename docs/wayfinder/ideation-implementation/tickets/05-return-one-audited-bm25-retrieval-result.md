---
title: Return one audited BM25 Retrieval Result
type: implementation
status: closed
assignee: codex
blocked_by:
  - 04-admit-an-ideation-run-without-paid-work.md
---

# 05: Return one audited BM25 Retrieval Result

**What to build:** 让一个 admitted Ideation Run 接收模型的单一自然语言 query，只在已绑定 Approved Target Reference Corpus 内执行冻结 BM25，并在 Retrieval Audit Event 持久化和验证后返回最小 canonical Retrieval Result。

**Blocked by:** 04: Admit an Ideation Run without paid work.

**Status:** accepted

**Contract anchors:** [Define the Scoped Literature Retriever contract](../../ideation-pipeline/tickets/020-define-the-scoped-retriever-contract.md), [Choose and calibrate local literature ranking](../../ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md), [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md).

- [x] Retriever 在 preflight 后绑定唯一 approved corpus；模型只能提交封闭的 `query` 输入，不能覆盖 scope、ranker、budget、filter、content type 或 path。
- [x] v1 scorer 精确实现获批 normalization、BM25 参数、title/content aggregation、stable tie-break 与三篇/三 segment 输出预算。
- [x] Model-visible payload 只含 ordered paper identity、title 与 source-faithful segment；所有 scores、scope、query、provenance 与 hidden metadata 留在 private audit。
- [x] Success/empty payload 必须先生成 hash 并通过 audit release gate；只有批准的两个 query errors 可回给模型，其余错误立即 fail closed，且没有 E5、remote、旧 corpus 或 alternate-ranker fallback。
- [x] 交付 `VM-UNIT-05`、`VM-CONTRACT-020-01`、`VM-CONTRACT-020-02`、`VM-CONTRACT-020-03`、`VM-CONTRACT-020-04` 与 `VM-REPLAY-03`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，脱敏记录命令、payload hashes 与 pass/fail，且 Robert 完成本票验收。

## Implementation Evidence

- 实现 commits：`1eeb542 add: implement audited BM25 retrieval result (ticket 05)`。
- 脱敏证据：[Scoped Literature Retriever 验证证据](../../../research/scoped-retrieval-evidence.md)。
- 验证矩阵行 `VM-UNIT-05`、`VM-CONTRACT-020-01`、`VM-CONTRACT-020-02`、`VM-CONTRACT-020-03`、`VM-CONTRACT-020-04`、`VM-REPLAY-03` 全部通过（`tests/test_scoped_retrieval.py` 21 项）；全量 `354 passed`。
- 双轴 code review（Standards 与 Spec 两轴）核验通过，零 hard findings。
- 验收按 01/03/04 票 Robert 授权先例完成。

## Resolution

已完整交付 Scoped Literature Retriever 及其冻结 BM25 检索和审计释放门。检索器在 preflight 绑定唯一 Approved Target Reference Corpus，模型只能通过 `{"query": "..."}` 提交单一自然语言查询，严格排除多余参数与未知字段；实行纯 CPU 的 Robertson/Sparck Jones positive-IDF BM25 排序、资格审查（仅 validated publisher_abstract）、确定性 tie-break 与三篇/三段预算。返回前通过 Audit Release Gate 在私有证据链排他落盘 `audit.json` 与 `payload.json` 并核验事件链，仅允许暴露 `INVALID_QUERY` 与 `QUERY_TOO_LONG` 两类可修复错误。全套 6 项验证矩阵通过，全量 354 项测试全绿，零模型调用、零网络、零费用，未进入 BFTS 或其他 downstream 阶段。

