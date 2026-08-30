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
- [本地文献排序最小公平比较协议（approved v1.1）](../../../prototypes/local-literature-ranking-comparison-protocol.md)
- [AI qrels 调研与本项目决策](../../../prototypes/local-ranking-ai-qrels-research.md)
- [本地文献排序最小公平比较协议 v1.2（approved overlay）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.2.md)
- [本地文献排序比较协议 v1.2.1（actual judge provenance correction）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.2.1.md)
- [AI qrels development evidence 与 holdout receipts](../../../prototypes/local-ranking-ai-qrels-development-evidence.md)
- [Local ranking 是否需要论文全文](../../../prototypes/local-ranking-full-text-decision.md)
- [Local ranking 正式输入就绪检查](../../../prototypes/local-ranking-input-readiness.md)
- [Local ranking 正式输入准备证据](../../../prototypes/local-ranking-input-preparation.md)
- [E5 512-token 边界与摘要长度政策研究](../../../prototypes/e5-length-policy-research.md)
- [Local ranking 长度政策最小比较](../../../prototypes/local-ranking-length-policy-comparison.md)
- [Local ranking 正式输入与盲评表](../../../prototypes/local-ranking-formal-input-and-blind-qrels.md)
- [Local ranking Windows dense smoke](../../../prototypes/local-ranking-windows-dense-smoke.md)

## Question

Which minimal ranking approach returns useful evidence from 3–36 allowed references, and how will a cheap prototype compare relevance, determinism, dependencies, latency, and failure cases before Robert chooses it?

## Current state

Robert 已批准 comparison protocol、v1.2 AI-qrels overlay 与在任何 ranking 前完成的 v1.2.1 actual-judge provenance correction。v1.1 的 Python 3.13.7 + mandatory CPU FP32 reference path、pinned `intfloat/e5-small-v2` dense challenger、12 cases / 24 queries、题名 + `publisher_abstract` relevance scope、固定 normalization/resource/promotion/output-budget rules 继续生效；overlays 只覆盖 qrels authority、stability、holdout sealing 与真实执行模型绑定，不原地修改 hash-bound v1.1/v1.2。

Throwaway harness 已实现：strict allowlist-only schemas、input/qrels/model/environment-lock hash verification、lexical/RRF scoring、deterministic payload、candidate-isolated worker、typed failure capture、immutable attempt evidence 与 one-command replay 均已落地。Windows SSH 已恢复，并在 `D:\python.exe` 3.13.7 下通过 bundle transfer、`compileall`、lexical/RRF fixture 与 pinned E5 dense smoke；持久工作根目录为 `D:\AI-Scientist-v2-workspace`。正式 ranker comparison 尚未运行。

正式输入盘点最初发现 approved case bundles 为 0；随后完成了独立、不可变的 input preparation 与 approval chain，没有把 raw rows 直接重命名成 Approved Workshop/Corpus。

Windows/macOS Python 3.13 locks 已用 `uv 0.12.4`、binary-only resolution 和 distribution hashes 生成；Windows fresh venv 已按 Windows lock 安装。Pinned E5 六文件 manifest 与 weight hash 校验通过，两次 Windows CPU FP32 diagnostic attempts 均成功，跨 attempt canonical payload hashes 完全一致；E5 worst observed cold p95 8.786 s、warm p95 29.641 ms、build 0.193 s、peak RSS 422,768,640 bytes、model 134,410,262 bytes、environment 836,643,909 bytes，均通过 v1.0 complexity gates。

本 smoke 只证明 frozen runtime 可行，不是 ranker relevance 证据。Evidence-hardening commit `d065002` 已在 Windows fresh attempt 验证：frozen lock、environment/model bytes 与 direct/conservative resource verdict 均写入 raw evidence，三条 candidates 全部 `pass`；Python socket probe 返回 typed `NETWORK_ACCESS_DENIED`，attempt-03 payload hashes 与前两个 attempts 完全一致。

Input preparation 已形成 12-case proposal、12 个 zero-error corpus bundles 与 12 份 deterministic-validation-passed Workshop drafts，并由第二 attempt 对 52 个 selection/corpus artifacts 完成 byte-identical replay。Robert 随后授权 Codex 从第一性原理研究并决定 input/full-text policy；逐案语义审计、全部 reference-title inspection、结构化 abstract audit 与一手资料调研支持批准全部 12 cases。`input-approval-001` 已用 immutable sidecars 绑定 selection、Workshop、corpus、validator 与 v1.1 protocol hashes，approved cases 现为 12。

v1.1 正式 relevance comparison 明确采用题名 + `publisher_abstract`，不混入覆盖不均的全文；结论只支持 abstract-level local paper ranking。Pinned E5 exact tokenizer preflight 已完成：11/168 篇（5 cases）完整 `passage: ` inputs 超过 512，最大 1101；统一前截断会丢 8,458 source characters。已批准 512 仅作为 E5 单 segment hard boundary，并冻结只分割这 11 篇、所有 arms 共用、sentence-aware、zero-overlap、full-coverage、可精确回链的 segmentation。

隔离 query-author session 已只基于 Approved Workshop packet 冻结 24 条 queries；controller 在 Robert 的 delegated authority 下原样批准、未改写 query bytes。Formal adapter 随后物化 168 papers / 180 shared segments，max query/title/segment exact inputs 为 44/53/512 tokens；两个 hardened fresh-process attempts byte-identical，并生成了中文规则、本地离线的 development/holdout blind packets。

人工 qrels blocker 已由 v1.2/v1.2.1 正式替换。实际 judge-A 是 Kimi Code `kimi-k3`，judge-B 是 Kimi Code `deepseek-v4-flash`；两者 development/holdout 均完成 fail-closed validation。原 bundles 错误声明 Codex model，现已冻结 actual-model bundles，并以只改 provenance、不改 qrels/judgment semantics 的 sidecar 重新绑定 development。A/B 共用 holdout raw-draft 路径导致 DeepSeek draft 被 Kimi 覆盖，但 DeepSeek canonical qrels/trace/result 仍完整且 hashes 匹配；v1.2.1 允许从 validated trace 重建并强制披露该 provenance degradation。

Development A/B 在 grade、segment 或 exact-span 上共有 73 个 disputed items；不含 prior labels/rationales 的 blind packet 已由 judge-C=`gpt-5.6-sol`/`xhigh` 全部裁决。Development consensus 完整覆盖 176 items；holdout A/B/C/consensus 也已通过 validator，但标签继续 sealed。A/B exact paper-grade agreement 为 71.59%，linear-weighted kappa 0.6561，`1↔2` boundary disagreement 3.98%，grade gap≥2 为 1.14%；diagnostics 不冒充真实性门槛。

下一步是用 judge-A、judge-B、consensus 三套 development qrels 运行完全相同的 rankers 并做 sensitivity gate；三套必须导出相同 promotion/winner direction，否则直接 `inconclusive`。Robert 不再做 336 条 qrels，只在最多两个 finalists 后做 12-query anonymous first-party utility check。Finalists 冻结后再做 Windows 10 次 fresh-process replay，且只有 dense 成为 finalist 时才在 Mac 安装 neural stack 做 cross-platform replay。在 Robert 审阅真实 development/holdout 与 utility 结果并选择 winner 前，本 ticket 保持 open，不能写 Resolution 或更新 map 为最终 ranking 决策。
