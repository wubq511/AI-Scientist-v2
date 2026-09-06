---
title: Approve one Target Reference Corpus
type: implementation
status: closed
assignee: codex
blocked_by:
  - 02-approve-one-workshop-file.md
---

# 03: Approve one Target Reference Corpus

**What to build:** 让 Robert 能从 target-reference membership 与已冻结 authority evidence 构建、验证并批准一个 self-contained Target Reference Corpus；同一流程能够对当前全部 targets 做确定性预处理验证，但不运行模型。

**Blocked by:** 02: Approve one Workshop File.

**Status:** accepted

**Contract anchors:** [Freeze literature before ideation](../../ideation-pipeline/tickets/003-freeze-literature-before-ideation.md), [Audit metadata gaps and enrichment sources](../../ideation-pipeline/tickets/016-audit-metadata-gaps-and-enrichment-sources.md), [Define the frozen corpus contract](../../ideation-pipeline/tickets/019-define-the-frozen-corpus-contract.md), [Understand dataset routing metadata](../../ideation-pipeline/tickets/033-understand-dataset-routing-metadata.md).

- [x] 每个 case 的 canonical corpus、manifest、machine-replayable validation report 与 private evidence 自包含，并以 opaque `case_id` 和 exact membership/hashes 绑定。
- [x] Reference Content 使用真实 source type、status、text hash 与 field-level provenance；target contexts、intents、influence 与 dynamic ranking fields 被 quarantine。
- [x] Validator 对全部 error 条款 fail closed、不自动修复；optional metadata 缺口保留为 warning，failed/successful build attempts 均不可覆盖。
- [x] 同一 source、membership、versions 与 rules 重建得到相同 corpus/bundle identity；当前全部 targets 的 deterministic preprocessing validation 可完成且不发模型请求。
- [x] 交付 `VM-CONTRACT-019-01`、`VM-CONTRACT-019-02`、`VM-REPLAY-02` 与 `VM-LEAKAGE-04`，并保持全部已有测试通过。
- [x] 脱敏记录输入 identities、命令、pass/fail、warnings 与 hashes，且 Robert 完成本票验收。

## Implementation Evidence

- 证据与脱敏摘要：[Target Reference Corpus approval boundary 验证证据](../../../research/corpus-approval-evidence.md)。
- 交付验证矩阵行：`VM-CONTRACT-019-01`、`VM-CONTRACT-019-02`、`VM-REPLAY-02` 与 `VM-LEAKAGE-04`（全部通过，见 `tests/test_corpus_approval.py`）。
- 全量自动化测试：`298 passed in 19.31s`（含新增 10 项语料契约测试）。
- 全量 237 个 Targets 确定性预处理离线验证：100% 通过（237/237 passed, 0 failures, 耗时约 7 秒）。
- 真实私有 smoke candidate `case-229e495f82a24cff9e6082aa058955b9` 经 Robert 决策正式核准，进入 `approved` 状态。

## Resolution

已建立严格隔离的离线 Target Reference Corpus 构建、验证与批准边界：
1. 稳定 CLI 入口 `python -m ai_scientist.prepare_ideation_inputs corpus {build,validate,approve,validate-all}`；
2. 架构生命周期严格隔离为 `contract.py`、`corpus_build.py`、`corpus_validation.py`、`corpus_approval.py` 与门面 `corpus.py`；
3. 冻结权威证据政策 `reference-authority-v1.json`（SHA-256: `65b0d9aa5942eb164370fb6d7162fbd6b4a629488a6093e0e0ebfd44eb1e6a5f`）有效覆盖 Europe PMC 1490 字符完整摘要、JMLR 官方 1327 字符完整摘要与 JAMA Invited Commentary（标为 `not_published`，杜绝坏值 `falls,` 冒充摘要）；18 篇缺失 venue 记录保留为 null 并产生非阻塞 warning；
4. 严格 Quarantine 隔离封死 `targetPaperId`、`contexts`、`intents`、`citationCount`、`isInfluential` 等进入 `corpus.json`；
5. 确定性检验器只读 fail-closed，对 11 类 error 规则全量拦截且绝不自动改写语料；
6. 零模型调用、零网络外联、零模型费用，未进入 BFTS 或其他 downstream 阶段。
