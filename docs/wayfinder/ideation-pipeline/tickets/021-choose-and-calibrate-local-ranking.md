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
- [Development Stage A 结果](../../../prototypes/local-literature-ranking-comparison-result.md)
- [Windows CPU thread-count 执行补充 v1.3](../../../prototypes/local-literature-ranking-comparison-protocol-v1.3.md)
- [Local ranking 是否需要论文全文](../../../prototypes/local-ranking-full-text-decision.md)
- [Local ranking 正式输入就绪检查](../../../prototypes/local-ranking-input-readiness.md)
- [Local ranking 正式输入准备证据](../../../prototypes/local-ranking-input-preparation.md)
- [E5 512-token 边界与摘要长度政策研究](../../../prototypes/e5-length-policy-research.md)
- [Local ranking 长度政策最小比较](../../../prototypes/local-ranking-length-policy-comparison.md)
- [Local ranking 正式输入与盲评表](../../../prototypes/local-ranking-formal-input-and-blind-qrels.md)
- [Local ranking Windows dense smoke](../../../prototypes/local-ranking-windows-dense-smoke.md)
- [Formal holdout inconclusive 后的补救设计研究](../../../prototypes/local-ranking-inconclusive-next-step-research.md)
- [v1.4 fresh direct-payload evaluation 对抗性审查](../../../research/local-ranking-v1.4-adversarial-protocol-review.md)
- [本地文献排序比较协议 v1.4（approved operational overlay）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.4.md)
- [DeepSeek V4 Flash 裁判适配研究](../../../research/deepseek-v4-flash-judge-fit.md)
- [Local-ranking evaluator qualification protocol v1.0](../../../prototypes/local-ranking-evaluator-qualification-protocol-v1.0.md)
- [Local-ranking evaluator qualification protocol v1.0.1（quote contract correction）](../../../prototypes/local-ranking-evaluator-qualification-protocol-v1.0.1.md)

## Question

Which minimal ranking approach returns useful evidence from 3–36 allowed references, and how will a cheap prototype compare relevance, determinism, dependencies, latency, and failure cases before Robert chooses it?

## Current state

Robert 已批准 comparison protocol、v1.2 AI-qrels overlay 与在任何 ranking 前完成的 v1.2.1 actual-judge provenance correction。v1.1 的 Python 3.13.7 + mandatory CPU FP32 reference path、pinned `intfloat/e5-small-v2` dense challenger、12 cases / 24 queries、题名 + `publisher_abstract` relevance scope、固定 normalization/resource/promotion/output-budget rules 继续生效；overlays 只覆盖 qrels authority、stability、holdout sealing 与真实执行模型绑定，不原地修改 hash-bound v1.1/v1.2。

Throwaway harness 已实现：strict allowlist-only schemas、input/qrels/model/environment-lock hash verification、lexical/RRF scoring、deterministic payload、candidate-isolated worker、typed failure capture、immutable attempt evidence 与 one-command replay 均已落地。Windows SSH 已恢复，持久工作根目录为 `D:\AI-Scientist-v2-workspace`。Development Stage A 已从 clean `2c1b332` 完成：三套 qrels 共 39/39 arms success、跨 qrels payload identity 完全一致、全部 resource gates pass。Cold-start measurement 已与 corpus-build 分离，旧的重复计时 evidence 不用于淘汰 dense。

正式输入盘点最初发现 approved case bundles 为 0；随后完成了独立、不可变的 input preparation 与 approval chain，没有把 raw rows 直接重命名成 Approved Workshop/Corpus。

Windows/macOS Python 3.13 locks 已用 `uv 0.12.4`、binary-only resolution 和 distribution hashes 生成；Windows fresh venv 已按 Windows lock 安装。Pinned E5 六文件 manifest 与 weight hash 校验通过，两次 Windows CPU FP32 diagnostic attempts 均成功，跨 attempt canonical payload hashes 完全一致；E5 worst observed cold p95 8.786 s、warm p95 29.641 ms、build 0.193 s、peak RSS 422,768,640 bytes、model 134,410,262 bytes、environment 836,643,909 bytes，均通过 v1.0 complexity gates。

本 smoke 只证明 frozen runtime 可行，不是 ranker relevance 证据。Evidence-hardening commit `d065002` 已在 Windows fresh attempt 验证：frozen lock、environment/model bytes 与 direct/conservative resource verdict 均写入 raw evidence，三条 candidates 全部 `pass`；Python socket probe 返回 typed `NETWORK_ACCESS_DENIED`，attempt-03 payload hashes 与前两个 attempts 完全一致。

Input preparation 已形成 12-case proposal、12 个 zero-error corpus bundles 与 12 份 deterministic-validation-passed Workshop drafts，并由第二 attempt 对 52 个 selection/corpus artifacts 完成 byte-identical replay。Robert 随后授权 Codex 从第一性原理研究并决定 input/full-text policy；逐案语义审计、全部 reference-title inspection、结构化 abstract audit 与一手资料调研支持批准全部 12 cases。`input-approval-001` 已用 immutable sidecars 绑定 selection、Workshop、corpus、validator 与 v1.1 protocol hashes，approved cases 现为 12。

v1.1 正式 relevance comparison 明确采用题名 + `publisher_abstract`，不混入覆盖不均的全文；结论只支持 abstract-level local paper ranking。Pinned E5 exact tokenizer preflight 已完成：11/168 篇（5 cases）完整 `passage: ` inputs 超过 512，最大 1101；统一前截断会丢 8,458 source characters。已批准 512 仅作为 E5 单 segment hard boundary，并冻结只分割这 11 篇、所有 arms 共用、sentence-aware、zero-overlap、full-coverage、可精确回链的 segmentation。

隔离 query-author session 已只基于 Approved Workshop packet 冻结 24 条 queries；controller 在 Robert 的 delegated authority 下原样批准、未改写 query bytes。Formal adapter 随后物化 168 papers / 180 shared segments，max query/title/segment exact inputs 为 44/53/512 tokens；两个 hardened fresh-process attempts byte-identical，并生成了中文规则、本地离线的 development/holdout blind packets。

人工 qrels blocker 已由 v1.2/v1.2.1 正式替换。实际 judge-A 是 Kimi Code `kimi-k3`，judge-B 是 Kimi Code `deepseek-v4-flash`；两者 development/holdout 均完成 fail-closed validation。原 bundles 错误声明 Codex model，现已冻结 actual-model bundles，并以只改 provenance、不改 qrels/judgment semantics 的 sidecar 重新绑定 development。A/B 共用 holdout raw-draft 路径导致 DeepSeek draft 被 Kimi 覆盖，但 DeepSeek canonical qrels/trace/result 仍完整且 hashes 匹配；v1.2.1 允许从 validated trace 重建并强制披露该 provenance degradation。

Development A/B 在 grade、segment 或 exact-span 上共有 73 个 disputed items；不含 prior labels/rationales 的 blind packet 已由 judge-C=`gpt-5.6-sol`/`xhigh` 全部裁决。Development consensus 完整覆盖 176 items；holdout A/B/C/consensus 也已通过 validator，但标签继续 sealed。A/B exact paper-grade agreement 为 71.59%，linear-weighted kappa 0.6561，`1↔2` boundary disagreement 3.98%，grade gap≥2 为 1.14%；diagnostics 不冒充真实性门槛。

Stage A sensitivity gate 已通过：三套 qrels 都选择 E5 为 best single scorer、BM25 为 best lexical；Stage B 冻结 BM25 `k1=1.6,b=0.5`，并因双方都有对方遗漏的 grade≥2 papers 而保留 RRF ablation。Windows 1/4/8/16-thread probe 的 12-query payload 完全一致；16-thread 将 corpus build total 缩短 7.75x，后续 formal evidence 按 approved v1.3 使用 16 threads，1-thread CPU FP32 path 继续保留。Stage B1 title ablation 18/18 arms success：BM25 与 E5 均冻结 `title_weight=1`；E5 的 exact primary optimum 在 judge-A 有轻微差异，但 finalist direction、Recall 与 catastrophic-miss 改善不变并已完整披露。Stage B2 phrase ablation 6/6 arms success，off/on 的 12/12 payloads 与全部 relevance metrics 完全相同，因此冻结 `phrase_bonus=false`。Stage B3 12/12 arms success；RRF-k10/60 均被 E5 在三套 qrels 的 nDCG/Recall 上支配，故拒绝。Stage B4 12/12 arms success；两 finalists 的 cap3/cap5 EvidenceHit 与 ranking metrics 相同，按 payload bytes tie-break 均冻结 `paper_cap=3`。两个 development finalists 的全部参数已冻结：BM25 baseline 与 E5 best single scorer。Windows scoring-only 10-run 与 macOS stable 3-run gate 均已通过；两平台的 observable payload byte-identical，全部 resource gates pass。Formal holdout 随后从 clean `d44e8b2` 一次性运行：三套 comparison 与 6/6 candidate gates 全部成功，但 judge-A 选择 BM25、judge-B 名义选择 E5、consensus 的 E5 优势只有 `0.008299`。这违反 v1.2 的 same-direction gate，因此 result=`inconclusive`；不得多数票、重跑、调参或生成以 same-direction 为前提的 Robert utility card。

后续对抗性审查确认：已批准 experiment matrix 完整执行，但旧 pointwise synthetic qrels 与旧 holdout 均不能回答 top-3 evidence-set 对 AI ideation 的直接效用，也不能再提供无偏 winner vote。v1.4 operational overlay 已获 Robert 授权并冻结为 fresh direct-payload evaluation：从未使用 eligible candidates 机械选择新的 12 cases（small/medium/large 各 4），重新走 Workshop/corpus/query approval chain；primary 只比较冻结 BM25/E5 top-3，不加入不等预算的 union/full-corpus arm。两个不同 model families 各做两次镜像、fresh、tool-less orientation；统计单位是 12 cases，采用 exact case-level sign-flip，并由 E5 承担非对称 promotion burden。未过门槛只支持保留 BM25 的 parsimony default，不支持宣称 BM25 科学胜出或两者等价。

v1.4 harness 已实现 fresh sampler、operational formal-input path、formal input/selection/protocol/candidate payload hash binding、四路匿名镜像 bundle、`tools: []` judge contract、byte-exact quote validator、position/cross-model unresolved reducer、exact `2^12` randomization、case-cluster bootstrap 与 frozen promotion gates。69 个仓库测试通过；旧 holdout 的真实 BM25/E5 payload 已完成全链机械 dry-run，并被 reducer 强制标为 `spent_diagnostic_only`。下一阶段是在本 commit 后抽取 fresh batch 并完成新的 approval/query/formal-input chain，再交给 Windows 批量生成候选 payload。任何 Kimi/DeepSeek 正式 evaluator 调用仍需先报告 exact prompt size/context feasibility、调用上界与费用并取得单独批准。本 ticket 保持 open；在 fresh formal result 前不能写 Resolution、更新 map 或实现 production ranker。
