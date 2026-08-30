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

## Question

Which minimal ranking approach returns useful evidence from 3–36 allowed references, and how will a cheap prototype compare relevance, determinism, dependencies, latency, and failure cases before Robert chooses it?

## Current state

Robert 已批准 comparison protocol，并授权从第一性原理冻结原未决项。v1.0 采用 Python 3.13.7 + mandatory CPU FP32 reference path、pinned `intfloat/e5-small-v2` dense challenger、12 cases / 24 queries、延时盲复核、固定 normalization/resource/promotion/output-budget rules。

Throwaway harness 已实现：strict allowlist-only schemas、input/qrels/model hash verification、lexical/RRF scoring、deterministic payload、candidate-isolated worker、typed failure capture、immutable attempt evidence 与 one-command replay 均已落地。加上 pinned-model preparation 后共 22 项 tests，在 Mac ambient Python 3.14.6 与临时 Python 3.13.7 reference runtime 均通过。Windows SSH 已恢复，并在 `D:\python.exe` 3.13.7 下通过最小 bundle transfer、`compileall` 与 5-candidate lexical/RRF fixture replay；临时 run 目录已清理，持久工作根目录为 `D:\AI-Scientist-v2-workspace`。尚未下载 E5、生成真实 qrels 或运行 development/holdout。

正式输入盘点发现 approved case bundles 为 0：仓库只有 ignored raw dataset、contracts 和 diagnostic fixture，不能把 raw rows 偷换成 Approved Workshop/Corpus。因此 development/holdout input preparation 必须等待上游 approved artifacts；这个 gate 不阻塞独立的环境准备。

Windows/macOS Python 3.13 locks 已用 `uv 0.12.4`、binary-only resolution 和 distribution hashes 生成；Windows fresh venv 已按 Windows lock 安装并确认 5 个 direct versions。下一步是在该环境准备/校验 pinned E5 artifacts并完成 offline dense fixture smoke；在 Robert 审阅真实 development/holdout 结果并选择 winner 前，本 ticket 保持 open，不能写 Resolution 或更新 map 为最终 ranking 决策。
