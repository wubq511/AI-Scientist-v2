---
title: Compare DeepSeek Reasoning Effort on a Governed Canary
label: ready-for-agent
---

# DeepSeek Reasoning Effort Canary 比较规格

> **Execution withdrawn (2026-09-04):** 该规格绑定的 Promotion Proposal 001 已在零 paid runs、零实际支出时撤回。当前 production prompt 对跨领域 IdeaBench 存在 ML 目标错配；在 [domain-neutral Prompt Profile 资格验证](cross-domain-ideation-prompt-spec.md)通过 Promotion Gate、开启新 Design Epoch 并取得新的 reasoning-effort Plan Gate 前，不得执行本文的 24-run matrix 或复用其 commands。

## Problem Statement

可审计的 live DeepSeek 执行路径和单 Case smoke 已经完成，但 Robert 仍没有证据判断 `reasoning_effort=high` 与 `reasoning_effort=max` 哪一个更适合 ideation，也不知道当前 `max_tokens=32768` 是否足以避免 reasoning 或最终 JSON 截断。若凭一次 smoke、主观印象或事后挑选成功样本决定参数，后续 Canary、Scale Gate 与终波将建立在不可比较的设计状态上。

现有 Canary v1.0 还包含一个阻塞性的选集矛盾：它要求 12 个 cases，同时要求 8 个 clusters 全覆盖、Health & Medicine、Genetics & Molecular Biology、Neuroscience & Cognitive Sciences 各 2 个、其余 5 个 clusters 各 1 个；这些配额合计只有 11。已有的 `lr-op-*` 12-case operational batch 是为 local-ranking 设计的，cluster 分布和 edge-case 覆盖都不符合本 Canary，不能因准备方便而复用。

因此 ticket 035 需要一份在花钱前锁定的比较规格：先修正 Canary 选集合同并冻结 fresh 12-case inputs，再在相同 Run Specification 下做 paired `high`/`max` 比较，通过现有 Evidence Chain 与 Robert-only post-seal Evaluation Artifact 得出可审计结论，同时把实际支出限制在 30 CNY Canary 硬上限内。

## Solution

将 Canary 契约升为 v1.1：保留 11 个基础 cluster 配额，把第 12 个明确定义为 constraint-driven edge slot。该 slot 可来自任意 cluster，只用于补足基础 11 个未覆盖的硬性 edge requirement；若全部硬性 requirement 已覆盖，则选择第二个已知 edge case。候选只使用批准的 routing metadata、reference availability 与 prior-use 状态确定性产生，Robert 从合规候选中冻结最终 12 个，随后每个 case 都必须形成 Approved Workshop 与 Approved Target Reference Corpus。

以当前 baseline `reasoning_effort=high` 为 control、`max` 为 challenger。12 个 cases 各运行一对 Ideation Runs，保持 Workshop、Corpus、model、prompt、retriever、rubric、generation/reflection budgets 与 `max_tokens=32768` 完全相同，唯一主变量是 reasoning effort。执行顺序配对、串行、平衡且预先冻结；每个 run 仍执行独立 preflight、7.08 CNY 最坏估价和 Robert 的交互式费用批准。

每个 sealed run 均执行静态验证、sanitized export 和 Robert-only Evaluation Artifact。成对结果再进入隐藏 arm identity 的 write-once A/B comparison artifact；全部判断冻结后才揭示 arm mapping。只有 challenger 达到预注册质量门槛、deterministic 零回退、无截断，并满足成本与延迟 Regression Budget 时才进入 Promotion Gate；否则保留 `high`。`max_tokens=32768` 只做充分性观测，不在同一次比较中引入第二个 completion-limit challenger。

## User Stories

1. As Robert, I want ticket 035 to compare the two approved reasoning-effort candidates, so that the final parameter is evidence-backed rather than intuitive.
2. As Robert, I want the comparison plan frozen before any paid call, so that seeing results cannot move the success threshold.
3. As Robert, I want the Canary arithmetic contradiction corrected explicitly, so that the final 12-case set is actually reproducible.
4. As Robert, I want the original eleven cluster quotas preserved, so that the contract correction changes only the missing twelfth-slot semantics.
5. As Robert, I want the twelfth case to be constraint-driven, so that it adds edge coverage rather than arbitrary volume.
6. As Robert, I want all eight clusters represented, so that a parameter winner is not selected from one scientific domain.
7. As Robert, I want Health & Medicine, Genetics & Molecular Biology, and Neuroscience & Cognitive Sciences represented at least twice before the edge slot, so that the priority domains retain their approved coverage.
8. As Robert, I want one case at the eligible reference-count minimum, one at the median, and one at the maximum, so that prompt and retrieval pressure are observed across the corpus-size range.
9. As Robert, I want one case with exactly three references, so that the smallest legal corpus is exercised.
10. As Robert, I want one case containing an unavailable reference abstract, so that the approved exclusion semantics are exercised without fabricating content.
11. As Robert, I want the Canary cases to be fresh relative to prior ranking batches and the smoke case, so that earlier inspection and tuning do not contaminate the comparison.
12. As Robert, I want selection to fail closed if the frozen dataset cannot satisfy all constraints, so that the agent cannot silently relax the contract.
13. As Robert, I want only opaque `case_id` values in runtime and tracked summaries, so that Target Paper identity stays private.
14. As Robert, I want to approve the exact final 12-case manifest, so that deterministic filtering does not remove the human dataset gate.
15. As Robert, I want every selected case to have an Approved Workshop, so that draft or leaking Workshop content cannot enter a paid run.
16. As Robert, I want every selected case to have an Approved Target Reference Corpus, so that retrieval cannot escape the frozen local literature boundary.
17. As Robert, I want the README-compatible Workshop rendering retained for ticket 035, so that ticket 036 can later reuse the winner as its baseline arm.
18. As Robert, I want `high` to remain the baseline and `max` to remain the sole challenger, so that the comparison has one major variable.
19. As Robert, I want both arms to retain `max_tokens=32768`, so that completion-limit observations do not confound the reasoning-effort comparison.
20. As Robert, I want each case to produce one paired `high`/`max` comparison, so that domain and input differences are controlled within case.
21. As Robert, I want arm order balanced and fixed before execution, so that time-of-day or provider drift does not systematically favor one arm.
22. As Robert, I want provider calls serialized during the official off-peak period, so that budget and evidence remain easy to audit.
23. As Robert, I want every Ideation Run to pass its normal clean-tree preflight, so that comparison evidence remains commit-pinned.
24. As Robert, I want every run to display its own worst-case estimate and require an interactive `yes`, so that Plan Gate approval is never mistaken for spend approval.
25. As Robert, I want the aggregate actual spend capped at 30 CNY, so that an unexpectedly expensive arm cannot consume an open-ended budget.
26. As Robert, I want execution to stop before a new run whose 7.08 CNY worst-case bound does not fit the remaining aggregate budget, so that the hard cap is enforceable before the request.
27. As Robert, I want environment failures to use the approved suspend/resume path, so that a network interruption does not become a quality loss.
28. As Robert, I want model-behaviour failures eligible for at most one fresh run with a new approval, so that retries cannot turn into uncontrolled selection or spend.
29. As Robert, I want deterministic, leakage, isolation, and Evidence Chain failures to remain hard blockers, so that apparent idea quality cannot override trustworthiness.
30. As Robert, I want every completed run statically validated and sanitized-exported, so that the pairwise result is linked to trustworthy run evidence.
31. As Robert, I want one valid Evaluation Artifact for every finalized idea, so that no successful-looking run enters the comparison without qualitative review.
32. As Robert, I want to remain the only author of qualitative judgments, so that the comparison does not introduce an LLM judge or numeric surrogate.
33. As Robert, I want A/B packets to hide reasoning effort, run order, usage, cost, and latency, so that quality judgment is not biased by configuration prestige or expense.
34. As Robert, I want pairwise judgments to be write-once and rationale-bearing, so that arm identities are revealed only after decisions are frozen.
35. As Robert, I want `max` to win at least seven of twelve pairs while `high` wins no more than two, so that promotion requires a clear paired advantage.
36. As Robert, I want ties and incomparable pairs to count for neither arm, so that ambiguous evidence cannot be converted into a win.
37. As Robert, I want the challenger rejected on any deterministic, leakage, or truncation regression, so that quality gains cannot buy evidence corruption.
38. As Robert, I want `max` aggregate actual cost and median latency limited to at most twice `high`, so that its operational burden remains proportionate.
39. As Robert, I want `high` retained whenever `max` does not satisfy every promotion criterion, so that the fail-closed baseline remains stable.
40. As Robert, I want `max_tokens=32768` retained only if all 24 comparison runs avoid completion truncation, so that the limit has direct Canary evidence.
41. As Robert, I want any observed truncation routed to a separate single-variable proposal, so that ticket 035 does not tune two variables post hoc.
42. As Robert, I want an incomplete or budget-truncated comparison reported as inconclusive, so that partial pairs cannot name a winner.
43. As Robert, I want a sanitized comparison report with hashes, outcomes, cost, latency, failures, and gate results, so that the decision can be audited without exposing private scientific content.
44. As Robert, I want ticket 036 to remain untouched until ticket 035 has an approved winner or retained baseline, so that Workshop variants compare against one stable reasoning configuration.
45. As Robert, I want all raw prompts, responses, reasoning, ideas, targets, pair mappings, credentials, and provider response identifiers to remain private, so that evidence publication does not leak protected inputs.
46. As Robert, I want the work to stop at ideation evaluation, so that no BFTS, code experiment, plotting, write-up, or review stage is entered.

## Implementation Decisions

- **Authority and sequence**: ticket 035 is the next Wayfinder frontier and remains ahead of ticket 036. The Canary v1.1 contract correction, exact input approval, Promotion Proposal, paid paired runs, Evaluation Artifacts, blinded comparison, Promotion Gate decision, and ticket resolution form one governed prototype sequence.
- **Canary v1.1 arithmetic correction**: retain the eleven base slots implied by the existing cluster rule: two each from Health & Medicine, Genetics & Molecular Biology, and Neuroscience & Cognitive Sciences, plus one from each other cluster. Add one independent constraint-driven edge slot that may belong to any cluster; the extra slot does not alter the eleven base quotas.
- **Edge requirements**: the final set must include at least one case whose eligible corpus has the dataset minimum reference count, one at the median, one at the maximum, one with exactly three references, and one whose source references include an unavailable abstract handled by the approved corpus policy. Minimum, median, and maximum are recomputed from the hash-pinned eligible population; the current dataset snapshot is 3, 8, and 36.
- **Edge-slot choice**: after satisfying the eleven base quotas, assign the extra slot to the rarest still-unmet hard requirement, measured by eligible-candidate count. Ties use the fixed priority `exactly-three references`, `unavailable reference abstract`, `maximum reference count`, `median reference count`, followed by canonical candidate hash. If the base eleven already satisfy every requirement, the slot takes the canonical-first additional known edge case from the least represented eligible cluster; candidate-count and canonical-hash ties are deterministic.
- **Freshness boundary**: exclude the completed smoke case and every Target Paper previously used by formal local-ranking development, holdout, or operational batches. Existing `lr-op-*` Workshop and Corpus approvals cannot be repurposed as ideation Canary approvals. If exclusions make the constraints unsatisfiable, preparation stops and requests a versioned contract revision.
- **Human selection gate**: deterministic preparation emits only compliant candidate choices and a private metadata summary. Robert freezes the exact twelve cases; subsequent Workshop and Corpus preparation binds to that immutable selection manifest. Selection cannot use generated ideas, Target contribution similarity, or observed model performance.
- **Input baseline**: ticket 035 uses the approved README-compatible four-section Workshop rendering. Every case independently passes Workshop deterministic validation, semantic leakage review, Corpus validation, and Robert approval before entering any Run Specification.
- **Plan Gate status**: Robert approved this comparison plan on 2026-09-04. The first Promotion Proposal records that approval, the fixed hypothesis, one-major-variable claim, thresholds, cost envelope, expected failure modes, and the hashes of the eventual selection and input manifests before paid execution.
- **Hypothesis**: `reasoning_effort=max` is promoted only if it yields a clear paired qualitative advantage over `high` without deterministic, leakage, truncation, cost, latency, retry, or failure regression. Otherwise the current `high` baseline remains pinned.
- **Experimental unit**: one unit is a pair of fresh Ideation Runs for the same Ideation Case. There are twelve pairs and twenty-four runs. With three model rounds per run, the planned topology is seventy-two logical provider requests and at most one hundred forty-four physical attempts under the existing at-most-two-attempt adapter policy.
- **Single variable**: paired arms differ only in `reasoning_effort=high` versus `reasoning_effort=max`. Model/provider/version, endpoint, non-streaming mode, thinking mode, prompt, action protocol, Workshop, Corpus, retriever, ranking, rubric, `max_num_generations=1`, `num_reflections=3`, `max_tokens=32768`, dependency lock, and validation policy remain identical.
- **Execution order**: runs are serial and case-paired. A canonical hash of the selection manifest and case identity determines which arm executes first; the ordering algorithm enforces six high-first and six max-first pairs. The complete order is frozen before the first paid request and cannot be reordered based on outcomes.
- **Spend control**: the smoke-calibrated operating forecast is 3.36–6.72 CNY for all twenty-four runs; it is not an authorization ceiling. The aggregate Canary hard cap is 30 CNY. Before every run, actual cumulative Canary spend plus that run's 7.08 CNY peak/all-miss/two-attempt bound must not exceed 30 CNY; otherwise execution stops before admission. Each run retains its own interactive Robert approval.
- **Failure handling**: preflight rejection creates no provider request. Environment-class failures suspend and may resume the same run. A model-behaviour failure may receive at most one fresh-run rerun for that case and arm, with a new estimate and approval. Corrupt evidence, isolation violation, leakage, deterministic contract failure, or a second model-behaviour failure blocks that pair. No provider, model, endpoint, prompt, validation, or parsing fallback is allowed.
- **Run qualification**: only non-corrupt sealed runs with valid static Evidence Chains, byte-idempotent sanitized exports, and complete Evaluation Artifact coverage can enter a pair. A terminal failed run remains failure evidence but cannot be treated as a lower-quality idea.
- **Blind quality comparison**: each complete pair receives a private A/B packet containing only the two Evaluation Brief views needed for qualitative comparison. It excludes reasoning-effort identity, run order, usage, cost, latency, and provider identifiers. A balanced deterministic mapping is sealed before review and revealed only after Robert writes a write-once pair verdict from `a_better`, `b_better`, `tie`, or `incomparable` with rationale.
- **Promotion thresholds**: after reveal, `max` must win at least seven of twelve pairs and `high` must win no more than two. Ties and incomparable pairs count for neither arm. All twelve pairs must be complete; a partial, budget-truncated, or blocked matrix is `inconclusive`, not a win.
- **Regression Budgets**: deterministic validation, leakage, isolation, evidence integrity, and completion truncation have zero tolerance. Challenger aggregate actual cost must be no more than twice baseline aggregate actual cost, and challenger median end-to-end run latency must be no more than twice baseline median. Challenger cannot introduce a max-only terminal failure, unresumable suspension, or additional physical-attempt total. Any unbudgeted regression automatically rejects promotion.
- **Completion-limit conclusion**: retain `max_tokens=32768` if all twenty-four qualified runs have no `finish_reason=length`, no completion truncation, and no budget-exhausted disposition attributable to completion capacity. Any such event makes completion-limit evidence inconclusive and requires a later, separately approved single-variable challenger; ticket 035 does not lower or raise the limit in place.
- **Promotion result**: `max` is merely evidence-complete until Robert applies the Promotion Gate to the pre-registered criteria. An explicit `promoted` decision opens a new Design Epoch and updates the pinned reasoning effort. Every other complete outcome retains `high`; an inconclusive outcome leaves ticket 035 open for Robert to revise, narrow, or stop.
- **Evidence publication**: raw selection data, Target identities, Workshop provenance, corpora, prompts, responses, reasoning, ideas, provider IDs, Evaluation Artifacts, pair mappings, and credentials stay in private ignored roots. The repository receives only the versioned contract/proposal, sanitized commands and hashes, aggregate outcomes, cost/latency summaries, failure attribution, gate result, and ticket resolution.
- **Premise-collapse rule**: this plan assumes the single smoke's cost is directionally useful and that twenty-four runs can complete inside 30 CNY. If cost is materially higher, the remaining-budget gate truncates safely and the result becomes inconclusive; the agent must not weaken approval or quality thresholds to finish the matrix.

## Testing Decisions

- Good tests assert governed external outcomes: a compliant and hash-stable 12-case manifest, rejected noncompliant selections, exact base quotas plus one edge slot, prior-use exclusion, approved input status, frozen run order, aggregate budget refusal, qualified Evidence Chains, complete Evaluation Artifact coverage, blind mapping integrity, pair verdict immutability, and deterministic promotion reduction. They do not assert helper call order or private implementation layout.
- The first highest seam is the existing Workshop/Corpus prepare–validate–approve boundary. Exercise it against the final manifest and against adversarial candidates that violate cluster quota, freshness, reference-count coverage, unavailable-abstract handling, approval status, or source hashes.
- The second highest seam is the existing lifecycle CLI boundary: `new-run`, `resume`, static `validate`, sanitized `export`, and `evaluation`. Reuse the live-smoke path; do not add a second provider runner or a fourth runtime injection seam.
- A small offline comparison boundary may materialize and validate selection, order, blind mapping, pair verdicts, spend ledger, and final reduction. Its tests use synthetic opaque cases and sealed-run fixtures; they never require a live credential, real Target identity, or network call.
- Deterministic selection replay must produce byte-identical manifest bytes and the same ordered candidate choices from the same dataset and prior-use hashes. Any source, policy, or exclusion-list drift fails before input approval.
- Budget tests cover exact-bound admission, one-cent-over refusal, accumulated actual spend, failed/suspended runs, rerun accounting, and the rule that a Plan Gate never substitutes for per-run approval.
- Blinding tests prove six mappings per arm position, no reasoning-effort/configuration/cost/latency/provider metadata in A/B packets, write-once pair verdicts, and reveal only after all available judgments are frozen.
- Reducer tests cover the exact promotion boundary: seven `max` wins and at most two `high` wins passes only when all Regression Budgets pass; six `max` wins, three `high` wins, incomplete pairs, any zero-tolerance regression, more than 2× cost/median latency, or max-only failure rejects or returns inconclusive as specified.
- Completion-limit tests prove that any length finish, completion-capacity truncation, or attributable budget exhaustion prevents a 32768 sufficiency claim; zero such events across twenty-four qualified runs permits retaining 32768 but not claiming a universally sufficient limit.
- Existing transport, adapter, retrieval, controller, evidence, resume, export, evaluation, dependency, import, and CLI tests remain unchanged unless the prototype exposes a real contract defect. If tracked code changes, Python 3.13 clean-environment full pytest, compileall, Black, import/dependency checks, and Standards/Spec review are mandatory before the first paid run.
- Paid runs themselves are evidence production, not automated tests. Each records exact commit, dependency lock, private input hashes, configuration, timestamps, attempt topology, usage, finish reason, latency, actual cost, outcome, validation, artifact hashes, and failures without exposing protected payloads.

## Out of Scope

- Executing or resolving ticket 036, preparing B-guarded Workshop variants, or comparing Workshop fields during ticket 035.
- Opening the Scale Gate, choosing terminal-wave size or budget, running the terminal wave, or generating all 237 cases.
- Reusing the live smoke as one paired result; its commit, input selection, ordering, and blinding were not frozen for this comparison.
- Reusing the local-ranking operational batch as the ideation Canary, even if some individual Workshop or Corpus files are mechanically valid.
- Adding a second model, provider, endpoint, API format, LLM judge, numeric idea score, online literature search, provider-native tool, or automatic qualitative evaluator.
- Changing prompts, action schema, retriever/ranker, Workshop rendering, Corpus semantics, model version, temperature, generation count, reflection count, evidence schema, rubric criteria, or failure taxonomy.
- Comparing smaller or larger completion limits in the same matrix, dynamically increasing tokens after truncation, or choosing a limit from observed token percentiles without a new Plan Gate.
- Parallel provider execution, batch cost approval, automatic typing of `yes`, hidden spend authorization, or exceeding the 30 CNY aggregate cap.
- Repairing, overwriting, resealing, exporting, evaluating, or promoting from a corrupt run; substituting failed cases after outcomes are known; or dropping unfavorable pairs.
- Publishing raw Target Paper identity, Workshop text, Corpus content, prompts, responses, reasoning, ideas, provider response IDs, credentials, host identity, absolute private paths, Evaluation Artifacts, or blind mappings.
- BFTS, downstream code experiments, plotting, LaTeX writing, paper generation, automated review, deployment, public release, or merging to `main`.

## Further Notes

- Robert approved Canary v1.1's constraint-driven twelfth slot and this ticket 035 Plan Gate on 2026-09-04. That approval authorizes the governed preparation and comparison plan; it does not approve the exact final 12-case manifest or any individual provider request.
- The confirmed testing seams are the existing input prepare–validate–approve boundary and the existing CLI-to-sealed-evidence lifecycle. The optional offline comparison boundary is isolated from production runtime and exists only to make selection, blinding, spend reduction, and promotion arithmetic reproducible.
- The starting live-smoke evidence is a successful, valid one-case `high` run costing 0.14 CNY. It calibrates the operating forecast but is not a comparison sample and does not remove the 7.08 CNY per-run worst-case approval bound.
- Before paid work, the next session must recheck the official DeepSeek model, endpoint, parameter and pricing contract, confirm the credential only by presence and authenticated preflight outcome, and never print or persist the credential value.
- Phase independence is deliberate: Canary v1.1 contract plus frozen inputs and a Plan Gate proposal form a useful zero-cost preparation checkpoint. Paid execution begins only after that checkpoint is committed, clean, and Robert has approved the exact private selection.
- Robert 指定跨会话边界：下一会话只交付上述 zero-cost preparation checkpoint，完成后必须停止并回到当前会话；不得在下一会话启动任何 DeepSeek Ideation Run。付费阶段由当前会话在重新核验 clean commit、官方价格、credential readiness、剩余 Canary 预算和逐 run 交互批准后继续。
- The repository's local Markdown tracker remains authoritative. Ticket 035 must be claimed before preparation work and remains open until evidence and Robert's Promotion Gate decision resolve both reasoning effort and the 32768 sufficiency observation.
