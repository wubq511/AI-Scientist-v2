---
title: Choose and calibrate local literature ranking
type: prototype
status: open
assignee: Robert
blocked_by:
  - 018-define-the-workshop-file-contract.md
  - 020-define-the-scoped-retriever-contract.md
---

## Evidence

- [小规模冻结文献语料的本地排序技术路线调研](../../../research/local-literature-ranking-alternatives.md)
- [Local literature ranking：runtime 与最小 dense model 调研](../../../research/local-ranking-runtime-and-dense-model.md)
- [本地文献排序最小公平比较协议（approved v1.0）](../../../prototypes/local-literature-ranking-comparison-protocol.md)
- [Local ranking 正式输入就绪检查](../../../prototypes/local-ranking-input-readiness.md)
- [Local ranking 正式输入准备证据](../../../prototypes/local-ranking-input-preparation.md)
- [Local ranking Windows dense smoke](../../../prototypes/local-ranking-windows-dense-smoke.md)

## Question

Which minimal ranking approach returns useful evidence from 3–36 allowed references, and how will a cheap prototype compare relevance, determinism, dependencies, latency, and failure cases before Robert chooses it?

## Current state

Robert 已批准 comparison protocol，并授权从第一性原理冻结原未决项。v1.0 采用 Python 3.13.7 + mandatory CPU FP32 reference path、pinned `intfloat/e5-small-v2` dense challenger、12 cases / 24 queries、延时盲复核、固定 normalization/resource/promotion/output-budget rules。

Throwaway harness 已实现：strict allowlist-only schemas、input/qrels/model/environment-lock hash verification、lexical/RRF scoring、deterministic payload、candidate-isolated worker、typed failure capture、immutable attempt evidence 与 one-command replay 均已落地。加上 runtime-evidence tests 后共 26 项 tests，在 Mac ambient Python 3.14.6 与临时 Python 3.13.7 reference runtime 均通过。Windows SSH 已恢复，并在 `D:\python.exe` 3.13.7 下通过 bundle transfer、`compileall`、lexical/RRF fixture 与 pinned E5 dense smoke；持久工作根目录为 `D:\AI-Scientist-v2-workspace`。尚未生成真实 qrels 或运行 development/holdout。

正式输入盘点发现 approved case bundles 为 0：仓库只有 ignored raw dataset、contracts 和 diagnostic fixture，不能把 raw rows 偷换成 Approved Workshop/Corpus。因此 development/holdout input preparation 必须等待上游 approved artifacts；这个 gate 不阻塞独立的环境准备。

Windows/macOS Python 3.13 locks 已用 `uv 0.12.4`、binary-only resolution 和 distribution hashes 生成；Windows fresh venv 已按 Windows lock 安装。Pinned E5 六文件 manifest 与 weight hash 校验通过，两次 Windows CPU FP32 diagnostic attempts 均成功，跨 attempt canonical payload hashes 完全一致；E5 worst observed cold p95 8.786 s、warm p95 29.641 ms、build 0.193 s、peak RSS 422,768,640 bytes、model 134,410,262 bytes、environment 836,643,909 bytes，均通过 v1.0 complexity gates。

本 smoke 只证明 frozen runtime 可行，不是 ranker relevance 证据。Evidence-hardening commit `d065002` 已在 Windows fresh attempt 验证：frozen lock、environment/model bytes 与 direct/conservative resource verdict 均写入 raw evidence，三条 candidates 全部 `pass`；Python socket probe 返回 typed `NETWORK_ACCESS_DENIED`，attempt-03 payload hashes 与前两个 attempts 完全一致。Input preparation 已形成 12-case proposal、12 个 zero-error pending corpus bundles 与 12 份 deterministic-validation-passed Workshop drafts，并由第二 attempt 对 52 个 selection/corpus artifacts 完成 byte-identical replay；但 independent semantic review 与 Robert corpus/case approval 尚未完成，因此 approved cases 仍为 0。批准后由隔离的新会话只看 Approved Workshops 起草 queries，再进入 blind qrels。Finalists 冻结后再做 Windows 10 次 fresh-process replay，且只有 dense 成为 finalist 时才在 Mac 安装 neural stack做 cross-platform replay。在 Robert 审阅真实 development/holdout 结果并选择 winner 前，本 ticket 保持 open，不能写 Resolution 或更新 map 为最终 ranking 决策。
