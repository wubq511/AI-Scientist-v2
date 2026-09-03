---
title: Return one audited BM25 Retrieval Result
type: implementation
status: open
assignee: null
blocked_by:
  - 04-admit-an-ideation-run-without-paid-work.md
---

# 05: Return one audited BM25 Retrieval Result

**What to build:** 让一个 admitted Ideation Run 接收模型的单一自然语言 query，只在已绑定 Approved Target Reference Corpus 内执行冻结 BM25，并在 Retrieval Audit Event 持久化和验证后返回最小 canonical Retrieval Result。

**Blocked by:** 04: Admit an Ideation Run without paid work.

**Status:** ready-for-agent

**Contract anchors:** [Define the Scoped Literature Retriever contract](../../ideation-pipeline/tickets/020-define-the-scoped-retriever-contract.md), [Choose and calibrate local literature ranking](../../ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md), [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md).

- [ ] Retriever 在 preflight 后绑定唯一 approved corpus；模型只能提交封闭的 `query` 输入，不能覆盖 scope、ranker、budget、filter、content type 或 path。
- [ ] v1 scorer 精确实现获批 normalization、BM25 参数、title/content aggregation、stable tie-break 与三篇/三 segment 输出预算。
- [ ] Model-visible payload 只含 ordered paper identity、title 与 source-faithful segment；所有 scores、scope、query、provenance 与 hidden metadata 留在 private audit。
- [ ] Success/empty payload 必须先生成 hash 并通过 audit release gate；只有批准的两个 query errors 可回给模型，其余错误立即 fail closed，且没有 E5、remote、旧 corpus 或 alternate-ranker fallback。
- [ ] 交付 `VM-UNIT-05`、`VM-CONTRACT-020-01`、`VM-CONTRACT-020-02`、`VM-CONTRACT-020-03`、`VM-CONTRACT-020-04` 与 `VM-REPLAY-03`，并保持全部已有测试通过。
- [ ] 同步受影响的仓库运行说明，脱敏记录命令、payload hashes 与 pass/fail，且 Robert 完成本票验收。
