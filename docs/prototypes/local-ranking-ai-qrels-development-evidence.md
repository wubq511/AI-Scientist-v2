# Local ranking AI qrels：development evidence 与 holdout receipts

日期：2026-08-31
状态：AI judging chain 完成；允许进入三套 qrels 的 development sensitivity comparison
适用协议：approved v1.1 + v1.2 + v1.2.1

## 1. 结论

Judge-A、judge-B 与 blind judge-C 已完成 development；完整 consensus qrels 通过 fail-closed
validator。Holdout 的 A/B/C 与 consensus 也已完成验证，但明文仍留在 projectless sealed boundary，
本仓库和 controller 没有接收 holdout labels、分布、disagreement count/rate 或 ranking metrics。

Development 的 label-level agreement 不足以证明 qrels 是 human gold，但也没有预注册的单项
diagnostic veto。下一步必须分别用 judge-A、judge-B、consensus 三套完整 development qrels 运行
相同 rankers。只有 promotion 与 winner direction 在三套 qrels 上一致，才可冻结 finalists；否则
结果直接记为 `inconclusive`，不调整 rubric、judge、prompt 或 margin。

## 2. 实际 judges 与 provenance

| Role | Actual runtime/model | Scope |
|---|---|---|
| judge-A | Kimi Code / `kimi-k3` | development + holdout 全量 pointwise |
| judge-B | Kimi Code / `deepseek-v4-flash` | development + holdout 全量 pointwise |
| judge-C | Codex / `gpt-5.6-sol` / `xhigh` | 只看 A/B disputed original items |

原 A/B bundles 误写了 Codex profiles。v1.2.1 的 metadata-only rebind 已验证 item、rubric、
judgment semantics 与 qrels 不变，并保留 superseded artifacts。Holdout 的共享 raw-draft 路径
导致 judge-B draft 被覆盖；其 canonical trace/qrels/result 仍完整，rebind 明确记录
`validated_trace_reconstruction` provenance degradation。该偏差不得用于打破任何 winner tie。

## 3. Development artifacts

| Artifact | SHA-256 / count |
|---|---|
| judge-A actual bundle | `f6fb131cc1f049809be4079cdc2d3816ea96d3e22361cff4f036cbd3bc1a6c1e` |
| judge-A rebound qrels | `81d764ef53202701e16ece11545d2362badcd359c6bdd548ec8bd17dcfcf88f7` |
| judge-A rebound trace | `7dd3f8d53acd600f016ccdaeb786598e65048333a46db6e15a006cba29fe2e08` |
| judge-B actual bundle | `76b683b4fff5bdc5adfb46d69646ae7d295b9eb4770174630d8a10964151f1e5` |
| judge-B rebound qrels | `f3818eff25a416499376450da46408c7f80ce71e2b2341abfd7281a867fe5f16` |
| judge-B rebound trace | `852cbbd03a00c6d23f926d30d9b86c32cf80c24587e676449903c753683d809c` |
| blind adjudication bundle | `9aaf2c2319b0263fad0779caa4a8a378c7c0230060845192ac9b8a1da6521014` / 73 items |
| judge-C draft | `255b19d9eb84c2ac0214c641592036215a3b998569826104453e2b12390e2a93` |
| judge-C partial adjudication qrels | `34cda90d24498f21a39c99e75cae75e43fd0050af58696753a2d35aa147a99be` / 73 items |
| judge-C trace | `7026e13684140604d8a72633fd51cb6cf50627c88a6e5f4e991aedc8e2cb0e7c` |
| consensus qrels | `beb301eaaa51260fcfc26e34de1de593a453419abeebf4aa7b7f901ebb874869` / 176 items |
| consensus trace | `edccb1a020b87788b318c662a445fa5b48c6507ec5ee44cff6c9b343b3b1c8ad` |
| agreement diagnostics | `1db6deee2416f084108277f9d822dfc39879a0d4b0821881981f82396c805272` |

Judge-C 首次 finalize 失败并已保留：通用 parser 错误要求 73-item adjudication 覆盖全部 176
query-paper pairs。修复后，partial artifact 使用独立
`local-ranking-adjudication-qrels-v1.0` schema；validator 逐字段把每个 item 回绑 frozen input，
而 `local-ranking-qrels-v1` 仍只允许完整覆盖。Partial artifact 禁止输入 ranker；只有 176-item
consensus 是完整 qrels。

## 4. Development diagnostics

| Diagnostic | Result |
|---|---:|
| Exact paper-grade agreement | 126 / 176 = 71.59% |
| Linear-weighted Cohen's kappa | 0.6561 |
| `1↔2` boundary disagreement | 7 / 176 = 3.98% |
| Grade gap ≥ 2 | 2 / 176 = 1.14% |
| Both relevant, exact segment/support match | 0 / 34 |

`1↔2` 的 7 个 items 分布在 4 条 queries：`lr-dev-03-broad` 2 个、
`lr-dev-04-broad` 1 个、`lr-dev-04-focused` 2 个、`lr-dev-06-focused` 2 个。Exact support
为 0 表示两位 judge 在都判 relevant 时仍没有选择完全相同的 segment-grade/span payload；因此
protocol 把这些 items 保守地全部交给 C。它说明证据选择不稳定，不能把 AI qrels 宣称为 gold；
最终工程结论必须通过三套 qrels 的 ranker-direction sensitivity gate。

## 5. Holdout sealed receipts

| Artifact | Receipt |
|---|---|
| adjudication bundle | `862b367d35c723a72d95eb5ad87d9f8b18548fd30151133880b5f2f97a17c2e9` |
| judge-C partial qrels | `24b869991e47c26f7f25436f2e9313d542996d9df478a1c83a19bf75799817e9` |
| judge-C partial trace | `17ecedae7e73b69f1e514093f1a3a6775c049d0cadf25c55b41f1da1cbdcf25e` |
| consensus qrels | `f263876d5b3dbebf58b1ebd969d75acae51a35e804cffbb31e87978901a4b890` |
| consensus trace | `97fc9a92ed23aeaffa3ae70729277e513478ccf0b68f2831c99113447c01ceab` |
| judge-C validator | PASS |
| consensus validator | PASS |

Sealed roots：

- `.../local-ranking-judge-c-consensus/sealed/judge-c-holdout-v2`
- `.../local-ranking-judge-c-consensus/sealed/consensus-holdout-v2`

本报告故意不记录 holdout disputed-item count、grade distribution、label content 或 disagreement
rate。Finalists 与所有参数冻结前不得解封。
