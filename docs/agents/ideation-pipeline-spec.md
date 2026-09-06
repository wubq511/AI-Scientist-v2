---
title: Implement the Auditable Ideation-Only Pipeline
label: ready-for-agent
---

# 可审计的 Ideation-Only Pipeline 实现规格

## Problem Statement

Robert 需要把现有 AI Scientist v2 的 idea generation 路径改造成一个适合个人面试项目、能够按计划稳定运行且结果可解释的 ideation-only 系统。当前路径会从任意 Workshop 文本启动，运行时访问全局 Semantic Scholar，走通用多 provider 调用，把 ideas 写回 Workshop 旁的可变 JSON；它没有把 Target Paper 隔离、冻结 references、运行准入、失败语义、resume、成本批准与可审计证据连成一个可信边界。

因此，即使一次运行产出了看似合理的 idea，Robert 也无法可靠回答：模型到底看到了什么、文献是否只来自当前 Target Paper 的 references、idea 是否泄漏了 held-out contribution、失败是否被静默跳过、运行能否重放、结果能否与其他 run 隔离，以及某次设计优化是否真的改善了效果。

实现必须在本项目实际批准的输入、平台、provider 与执行流程下稳定工作，完整落实已经批准的合同，但不为假设性部署环境、未知调用方或未计划的扩展加入额外框架、兼容层、fallback 或泛化防御。

## Solution

在保留现有 generation、reflection、action 与七字段 idea payload 基线的前提下，直接收紧现有 ideation 路径：先离线准备并批准 identity-free Workshop File 与 per-case frozen corpus，再通过唯一安全 CLI 将它们 pin 进一个隔离的 Ideation Run。运行时模型只能调用绑定到该 corpus 的 Scoped Literature Retriever，并通过 DeepSeek-only adapter 使用获批 provider；每个输入、操作、尝试、结果、失败与验证事实形成不可变 Evidence Chain，运行最终被 seal，或以明确的 suspension / terminal failure 收束。

系统用确定性验证、record/replay、隔离与故障注入证明实现符合合同；真实模型执行再按 smoke、Canary 与终波 gate 逐步放量。每个 finalized idea 在 seal 后由 Robert 通过结构化 Evaluation Artifact 做定性比较，结果只服务 Evidence Feedback Loop 与面试叙事，不声称复现 IdeaBench 官方指标。

## User Stories

1. As Robert, I want each Ideation Case to be addressed by an opaque `case_id`, so that the model-visible workflow cannot reveal the Target Paper identity.
2. As Robert, I want Workshop derivation to use only the Target Paper title and raw abstract, so that hidden summaries and target-authored citation contexts cannot leak the answer into generation.
3. As Robert, I want every Workshop File to use one canonical four-section rendering, so that its bytes and semantics can be validated consistently.
4. As Robert, I want a Workshop Abstract to describe a neutral problem space rather than the Target Paper contribution, so that multiple materially different research directions remain possible.
5. As Robert, I want deterministic leakage scans and an independent semantic review before Workshop approval, so that copied or paraphrased target answers are rejected before a model call.
6. As Robert, I want rejected Workshop drafts and their validation evidence retained, so that failures are visible without becoming runtime inputs.
7. As Robert, I want Workshop provenance kept in a private manifest, so that derivation remains auditable without exposing the Target Paper to the model.
8. As Robert, I want every target-reference membership set frozen before ideation, so that a run cannot silently search beyond its assigned references.
9. As Robert, I want each Target Reference Corpus to be self-contained and bound to one case, so that runtime does not depend on a global paper catalog or cross-case joins.
10. As Robert, I want Reference Content labeled by its real source type and provenance, so that full text, publisher abstracts, citation contexts, and derived text cannot be confused.
11. As Robert, I want missing optional metadata recorded as warnings rather than guessed, so that corpus preparation stays evidence-based and proportionate.
12. As Robert, I want every corpus build and validation attempt to be immutable, so that a later success cannot erase how an earlier attempt failed.
13. As Robert, I want a corpus to become approved only after deterministic validation, focused exceptional-content review, version approval, and the applicable scale approval, so that a locally valid file does not bypass human control.
14. As an operator, I want runtime preflight to pin exact Workshop and corpus identities, hashes, approvals, and policy versions, so that an Ideation Run uses the intended inputs or does not start.
15. As an operator, I want one safe new-run entry and one run-id-only resume entry, so that mutable output paths, implicit reloads, and accidental configuration drift are unavailable.
16. As Robert, I want preflight to estimate a worst-case CNY cost and require the approved confirmation before paid work, so that model spending is explicit and bounded.
17. As Robert, I want credentials read only from the local environment and excluded from artifacts, logs, commits, and messages, so that the evidence workflow never becomes a secret-distribution channel.
18. As Robert, I want the ideation runtime to use the approved DeepSeek direct alias and a single non-streaming Chat Completions adapter, so that the transport surface stays narrow and attributable.
19. As Robert, I want provider-native web search and native tools disabled, so that all model-visible literature comes through the project-controlled retriever.
20. As an operator, I want each physical provider attempt recorded and validated independently, so that hidden SDK retries and false HTTP-success states cannot distort cost or evidence.
21. As an operator, I want provider failures returned through a stable typed taxonomy, so that the controller can apply the approved suspend-or-terminal decision without guessing.
22. As Robert, I want `reasoning_effort` and `max_tokens` exposed only through controlled, pinned configuration, so that Canary evidence can choose their values without redesigning the runtime.
23. As Robert, I want the Workshop rendering variant exposed through a controlled version seam, so that ticket 036 can compare variants without changing unrelated implementation.
24. As a model inside an Ideation Run, I want `SearchLiterature` to accept only a natural-language `query`, so that I can seek evidence without selecting a corpus, ranker, filter, or result budget.
25. As Robert, I want the retriever bound to exactly one Approved Target Reference Corpus during preflight, so that neither the model nor later code can switch scope.
26. As Robert, I want local ranking to use the frozen v1 BM25 contract, so that retrieval is deterministic, light, and already justified by the completed comparison.
27. As Robert, I want E5 retained only as diagnostic evidence and never as a runtime fallback, so that the shipped design does not overstate an inconclusive scientific comparison.
28. As a model inside an Ideation Run, I want Retrieval Results to contain only stable paper identity, title, and source-faithful bounded segments, so that useful evidence arrives without private audit metadata.
29. As Robert, I want a Retrieval Audit Event persisted and validated before its payload is released to the model, so that every visible result can be traced to its exact scope and policy.
30. As Robert, I want retrieval boundary, audit, or corpus failures to stop the run rather than trigger remote, stale-corpus, or alternate-ranker fallback, so that evidence remains trustworthy.
31. As Robert, I want the original generation and reflection loop preserved, so that the adaptation changes required boundaries without silently changing the baseline idea-generation behavior.
32. As a model inside an Ideation Run, I want parse, action-input, finalization-structure, and declared-grounding errors returned as minimal corrective feedback, so that a paid reflection round can repair a model-fixable mistake.
33. As Robert, I want every generation to end as `finalized` or `budget_exhausted`, so that non-finalizing behavior is retained as evidence rather than hidden.
34. As Robert, I want FinalizeIdea to preserve the seven-field idea payload and carry Declared Grounding beside it, so that compatibility and provenance are both maintained.
35. As Robert, I want Declared Grounding limited to papers returned in the same generation, so that the model cannot claim literature it did not actually see for that idea.
36. As Robert, I want finalization checks to run in the approved fixed order, so that leakage cannot be masked by a lower-priority model-fixable error.
37. As Robert, I want deterministic payload hygiene and within-run duplicate checks, so that private identifiers terminate an untrustworthy run while ordinary near-duplicates can be corrected.
38. As Robert, I want every Ideation Run to own an opaque identity, immutable specification, isolated artifacts, and isolated mutable state, so that one run cannot contaminate another.
39. As an operator, I want accepted ideas committed immediately with their evidence events, so that interruption does not discard work that was already accepted.
40. As an operator, I want environment-class failures to suspend an unsealed run and deterministic contract failures to seal it as failed, so that resume is offered only when it can preserve meaning.
41. As an operator, I want resume to reconstruct state from canonical events and artifacts under the same Run Specification, so that mutable projections cannot become the source of truth.
42. As Robert, I want corrupt runs preserved but barred from resume, export, replay, evaluation, and promotion, so that damaged evidence is never repaired into apparent trustworthiness.
43. As Robert, I want private raw evidence retained locally and sanitized evidence produced from a positive allowlist, so that runs remain auditable without committing sensitive content.
44. As Robert, I want recorded provider responses and deterministic retrieval inputs to replay to the same canonical artifacts, so that reproducibility is demonstrated without another paid call.
45. As Robert, I want every run to finish with an explicit `success`, `failed`, or `preflight_rejected` outcome, or remain visibly suspended without a seal, so that state is never inferred from a file's mere presence.
46. As Robert, I want every finalized idea evaluated after seal against the private Target Paper through a structured artifact, so that qualitative judgment is separated from generation evidence.
47. As Robert, I want qualitative evaluation to use categorical verdicts and rationales rather than numeric benchmark scores, so that the result cannot be mistaken for an IdeaBench metric reproduction.
48. As Robert, I want evaluation coverage to be machine-checkable while authorship remains human-controlled, so that missing judgments are visible without introducing an LLM judge.
49. As Robert, I want real execution staged as smoke, fixed Canary, and approved terminal waves, so that isolation, quality, recovery, and cost failures surface before scale-out.
50. As Robert, I want the Canary budget and Scale Gate enforced from recorded evidence, so that expansion happens only after the agreed conditions pass.
51. As Robert, I want evidence-motivated design changes to pass Plan Gate and Promotion Gate against pre-registered criteria, so that a promising observation cannot silently rewrite the pinned design.
52. As an implementer, I want a minimal precisely pinned runtime dependency set and a separate development tool set, so that the ideation path can run without downstream packages.
53. As an implementer, I want a Python 3.13 portable CPU reference path, so that the runtime does not acquire an unnecessary accelerator dependency.
54. As an implementer, I want external behavior tested through the input-preparation and ideation CLI seams, so that implementation modules can change without invalidating the specification tests.
55. As Robert, I want the system designed only for the approved project conditions and contracts, so that implementation effort is spent on planned reliability rather than speculative general-purpose defenses.
56. As Robert, I want BFTS, code experiments, plotting, write-up, and review to remain unreachable from the ideation entry, so that the project cannot accidentally enter a Downstream Experiment.

## Implementation Decisions

### Scope and change strategy

- Implement one ideation-only destination covering target-scoped preparation, local literature retrieval, idea generation, validation, evidence, and post-seal evaluation. Downstream execution is structurally outside the destination. Authority: [Set the ideation-only destination](../wayfinder/ideation-pipeline/tickets/001-set-the-ideation-only-destination.md), [Keep the runtime ideation-only](../wayfinder/ideation-pipeline/tickets/013-keep-the-runtime-ideation-only.md).
- Modify the existing ideation path in place. Preserve the existing generation/reflection/finalization behavior until a later evidence-backed promotion changes it; do not create a parallel framework or general-purpose orchestration layer. Authority: [Modify the existing ideation path](../wayfinder/ideation-pipeline/tickets/005-modify-the-existing-ideation-path.md), [Preserve a compatible baseline](../wayfinder/ideation-pipeline/tickets/006-preserve-a-compatible-baseline.md).
- Implement only behavior demanded by an approved contract and this project's supported operating conditions. Do not add speculative threat models, multi-provider compatibility, automatic fallbacks, unused policy abstraction, or defenses for hypothetical public/multi-tenant deployment. This parsimony rule does not weaken explicitly approved isolation, integrity, leakage, secret, or fail-closed conditions. Authority: tickets 005, 006, 013 and [Define the minimal runtime dependency contract](../wayfinder/ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md).

### Workshop and corpus preparation

- Workshop derivation is an offline preparation activity. Its private source allowlist is the Target Paper title plus raw abstract; `abstract_summary`, reference contexts, and corpus content may validate leakage but may not generate the Workshop. The model-visible artifact is canonical four-section English Markdown with an opaque filename and private provenance manifest. Authority: [Prevent Target Paper idea leakage](../wayfinder/ideation-pipeline/tickets/007-prevent-target-paper-idea-leakage.md), [Understand target-to-workshop semantics](../wayfinder/ideation-pipeline/tickets/014-understand-target-to-workshop-semantics.md), [Define the Workshop File contract](../wayfinder/ideation-pipeline/tickets/018-define-the-workshop-file-contract.md).
- An Approved Workshop requires deterministic structural/leakage validation and independent semantic review. Failed attempts remain immutable rejected drafts; no raw-abstract, old-workshop, cluster-only, or cross-target fallback is allowed.
- Each case receives a self-contained, canonical Target Reference Corpus with exact membership, typed source-faithful Reference Content, field-level provenance, validation report, manifest, hashes, and isolated evidence. Preparation may use only exact-identity authority sources; runtime never enriches or repairs. Authority: [Freeze literature before ideation](../wayfinder/ideation-pipeline/tickets/003-freeze-literature-before-ideation.md), [Audit metadata gaps and enrichment sources](../wayfinder/ideation-pipeline/tickets/016-audit-metadata-gaps-and-enrichment-sources.md), [Define the frozen corpus contract](../wayfinder/ideation-pipeline/tickets/019-define-the-frozen-corpus-contract.md), [Understand dataset routing metadata](../wayfinder/ideation-pipeline/tickets/033-understand-dataset-routing-metadata.md).
- Corpus validation is deterministic and non-repairing. Optional bibliographic gaps are warnings; schema, membership, identity, eligible-content, provenance, quarantine, or hash failures reject the bundle. Approval combines zero-error validation, focused review of exceptions, approved versions, and the current scale approval.

### Scoped retrieval and frozen local ranking

- Replace runtime Semantic Scholar access with a Scoped Literature Retriever constructed only after preflight binds one Approved Target Reference Corpus. Its model-controlled input is exactly one non-empty natural-language query; scope, ranker, budgets, filters, content type, and paths remain runtime-controlled. Authority: [Define the Scoped Literature Retriever contract](../wayfinder/ideation-pipeline/tickets/020-define-the-scoped-retriever-contract.md).
- The model-visible result is a versioned canonical payload containing ordered papers and source-faithful segments only. Scores, provenance, query, corpus identity, hidden metadata, generated summaries, and target-derived routing fields remain private.
- Persist and validate the Retrieval Audit Event before releasing a success or empty payload. Model-fixable query errors use only the two approved codes; boundary, policy, ranking, eligibility, audit, or evidence failures terminate through the controller without fallback.
- Freeze v1 ranking as lexical normalization plus positive-IDF BM25 with `k1=1.6`, `b=0.5`, `title_weight=1`, max content-segment aggregation, no phrase bonus, no raw-score threshold, three papers maximum, and one segment per paper. Equal paper scores use canonical paper identity as tie-break. Authority: [Choose and calibrate local literature ranking](../wayfinder/ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md).
- E5 and other prototype candidates remain diagnostic/rejected evidence. They are neither production dependencies nor fallback rankers, and the specification makes no claim that BM25 is a general scientific winner.

### DeepSeek adapter and cost boundary

- Add a transport-neutral, DeepSeek-only adapter for direct, non-streaming Chat Completions using the approved floating `deepseek-v4-pro` alias, thinking enabled, provider web/native tools disabled, and credentials read only from local `DEEPSEEK_API_KEY`. Keep legacy providers outside the new path rather than deleting them. Authority: [Choose the DeepSeek provider and version contract](../wayfinder/ideation-pipeline/tickets/031-choose-the-deepseek-provider-and-version-contract.md), [Define the DeepSeek adapter contract](../wayfinder/ideation-pipeline/tickets/022-define-the-deepseek-adapter-contract.md).
- Adapter requests accept only validated ordered messages, controlled `reasoning_effort`, explicit `max_tokens`, closed output mode, and opaque run-scoped user identity. Unknown parameters and caller overrides of provider-controlled fields fail closed.
- Every physical request yields a serializable Provider Attempt. Provider success requires the approved response invariants; usage is validated rather than estimated, retries are limited to the approved transient classes, and every failure belongs to the approved closed taxonomy.
- Cost accounting uses the approved versioned CNY price table. New-run and resume preflight calculate the conservative upper bound and record Robert's confirmation before paid work; actual cost is derived per attempt from provider usage and attempt-start price period.
- `reasoning_effort` and `max_tokens` remain open Canary parameters owned by [Compare DeepSeek reasoning effort and completion limits](../wayfinder/ideation-pipeline/tickets/035-compare-deepseek-reasoning-effort-and-completion-limits.md). Implementation provides one controlled versioned configuration seam but does not choose final values or create parameter-specific implementation work.

### Safe entry and control flow

- Keep one safe ideation entry in the existing path. New-run accepts only the approved case, Workshop/corpus pins, generation budget, and reflection budget; it does not expose model selection, output roots, device selection, ranker selection, or implicit resume. Resume accepts only an exact `run_id`. Authority: [Define the safe ideation entry](../wayfinder/ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md). Amended 2026-09-04 (ticket 01 of ideation-prompt-neutralization): `new-run` additionally requires the closed, versioned `--prompt-profile <id>` accepting only registered ids (`ml-baseline-v1`, `cross-domain-v1`); prompt bytes, paths, fragments, unknown ids, and any model/provider/endpoint override remain rejected, and the resolved profile id + contract version + canonical prompt-bundle SHA-256 join the Run Request and Run Admission pins. This is a closed run input, not a fourth dependency-injection seam.
- Remove import-time side effects. Pass the adapter, bound retriever, and event emitter into the controller through the three approved narrow interfaces, without introducing interface frameworks or additional injection layers.
- Preflight follows the approved ordered admission sequence: validate the CLI request, create and record the run request, bind clean code identity, validate Workshop, validate corpus, construct the bound retriever, check credential presence, obtain cost approval, then write Run Admission. No model request may precede admission.
- Enforce the ideation-only import closure through a development-time allowlist test. The model-visible action set is exactly `SearchLiterature` and `FinalizeIdea`; no code-execution or downstream action is reachable.
- Preserve the baseline outer generation loop and inner reflection loop. Each round performs one model call and one action outcome. Parse, unknown-action, invalid-action-input, finalization-structure, approved retriever-input, grounding, and within-run duplicate failures return the minimal Model-Fixable Error and consume a reflection round. Authority: [Define control flow, failures, and resume](../wayfinder/ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md).
- Each generation ends as `finalized` or `budget_exhausted`. A run succeeds only after the complete control flow and run-level gates; deterministic contract failures seal `failed`, preflight rejection seals `preflight_rejected`, and approved environment failures suspend without a seal.

### Finalization and idea quality

- Preserve the original seven-field idea payload and store provenance beside it. FinalizeIdea accepts the closed pair of `idea` plus Declared Grounding; prompt edits are limited to the already approved tool-description, arguments, and example regions. Authority: [Separate idea payloads from evidence](../wayfinder/ideation-pipeline/tickets/008-separate-idea-payloads-from-evidence.md), [Define the declared grounding contract](../wayfinder/ideation-pipeline/tickets/038-define-the-declared-grounding-contract.md).
- Declared Grounding is a non-empty, duplicate-free list of paper identities returned to the model in the same generation. Its three errors remain model-fixable; the declaration is stored in sidecar provenance rather than added to the idea payload.
- Finalization applies the fixed order: raw-submission hygiene, idea structure, Declared Grounding, then within-run duplicate detection. Hygiene leakage is terminal; the other approved failures are model-fixable. Authority: [Define the idea quality rubric](../wayfinder/ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md).
- Runtime does not attempt to score semantic novelty or feasibility. Those judgments remain Robert's post-seal responsibility.

### Run identity, evidence, failure, and resume

- Give each Ideation Run a global opaque identity and immutable Run Specification. Domain identity, writer fencing, logical operation order, physical attempt order, event order, and generation/round indexes remain separate coordinates. Resume retains the run identity; rerun and replay create a new run. Authority: [Define run identity and evidence layout](../wayfinder/ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md). Amended 2026-09-04 (ticket 01 of ideation-prompt-neutralization): new-schema Run Request/Admission documents (`run-request-v1.1.0` / `run-admission-v1.1.0`) additionally pin the resolved Prompt Profile identity — profile id, profile contract version, and the SHA-256 of the complete canonical prompt bundle plus the registry hash; legacy v1.0.0 documents are interpreted exclusively as `ml-baseline-v1` and are never rewritten or upgraded.
- Persist write-once request/admission artifacts, immutable versioned events, hash-linked artifact references, non-authoritative projections, and a terminal Run Seal. Private raw evidence and tracked sanitized evidence remain separate; sanitized export starts from an empty allowlisted object.
- Commit each operation atomically through run-local staging, hash, rename, directory durability, and event append. Accepted ideas are committed immediately. Resume validates the chain, quarantines the approved rename-before-event orphan case, reconstructs controller state from canonical evidence, advances the writer epoch, and re-estimates remaining cost.
- Treat evidence corruption as a permanent trust boundary: preserve the run, but do not repair, resume, seal, export, replay, evaluate, or promote from it. Environment/storage failures follow the approved suspension rules; deterministic failures follow the approved terminal rules.
- Retain complete private evidence locally and commit only sanitized schemas, manifests, statistics, conclusions, and work logs. Secrets, target identity, prompts, responses, reasoning, retrieval text, ideas, provider response IDs, host identity, and absolute paths do not enter sanitized evidence. Authority: [Retain auditable run evidence](../wayfinder/ideation-pipeline/tickets/010-retain-auditable-run-evidence.md), [Trust layered validation and isolated runs](../wayfinder/ideation-pipeline/tickets/011-trust-layered-validation-and-isolated-runs.md). Amended 2026-09-04 (ticket 01 of ideation-prompt-neutralization): the sanitized manifest additionally exposes only the safe prompt-profile identity (resolved profile id, profile contract version, bundle hash); prompt text, templates, and any model-visible bytes stay out of sanitized output, while the private Provider Attempt `request.json` retains the actual model-visible prompt for in-chain audit.

### Post-seal evaluation and staged execution

- After a non-corrupt Run Seal, assemble private reading material and let Robert author one canonical Evaluation Artifact per finalized idea. Each of the seven criteria uses a closed categorical verdict plus rationale; there is no numeric score or overall benchmark field. Authority: [Choose IdeaBench evaluation fidelity](../wayfinder/ideation-pipeline/tickets/032-choose-ideabench-evaluation-fidelity.md), [Define the post-seal evaluation artifact contract](../wayfinder/ideation-pipeline/tickets/037-define-the-post-seal-evaluation-artifact-contract.md).
- Evaluation remains outside the run's Evidence Chain, links back by hashes, preserves superseded versions, and exposes deterministic assemble, validate, and read-only coverage behavior. Robert is the only qualitative evaluator; no LLM judge is introduced.
- Support deterministic preparation validation for all targets, but execute paid model work in three waves: one-case smoke, fixed twelve-case Canary, then a Robert-approved terminal wave. Apply the approved Canary selection, cost ceiling, failure handling, Scale Gate, batching, and evaluation-coverage rules. Authority: [Stage full-dataset execution](../wayfinder/ideation-pipeline/tickets/009-stage-full-dataset-execution.md), [Canary 与扩量 Gate 契约](canary-and-scale-gates.md).
- Workshop rendering remains an open Canary parameter owned by [Compare Workshop specificity and rendering](../wayfinder/ideation-pipeline/tickets/036-compare-workshop-specificity-and-rendering.md). Implementation provides a controlled version seam while keeping the approved canonical baseline; it does not select a variant in advance.
- Route evidence-driven improvements through the approved Promotion Proposal, Plan Gate, one-major-variable comparison, Regression Budgets, and Promotion Gate. Bug fixes use normal validation, while unresolved product decisions return to Wayfinder. Authority: [Govern evidence-driven optimization](../wayfinder/ideation-pipeline/tickets/012-govern-evidence-driven-optimization.md), [Optimization Promotion Gate](promotion-gate.md).

### Dependencies and platform responsibility

- Split runtime, retained upstream/downstream, and development dependencies into three precisely pinned contracts. The runtime set is exactly the implemented ideation import closure; packages leave when their last runtime consumer leaves. Authority: [Audit the minimal ideation runtime](../wayfinder/ideation-pipeline/tickets/017-audit-the-minimal-ideation-runtime.md), [Define the minimal runtime dependency contract](../wayfinder/ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md).
- Python 3.13 is the reference minor and the portable CPU path is mandatory. Compatibility candidates and evidence runs follow the repository's existing platform rules rather than adding requirements here.
- Mac/Windows responsibilities remain exactly those in the repository instructions: Mac controls editing, ordinary runs, remote-provider calls, and evidence review; Windows handles bulk local-ranking evidence and offline verification where applicable. This specification adds no platform or raw-float parity requirement.

## Testing Decisions

- A good test observes a public workflow or contract result: exit status, typed result/error, canonical payload, immutable artifact, hash, event sequence, Run Seal, or reconstructed state. Tests must not assert helper call order, private class layout, SDK object shape, or prototype implementation details.
- Use two highest practical user-level seams. One offline input-preparation seam exercises `prepare → validate → approve`; one ideation CLI seam exercises new-run and resume. They remain separate because human approval is a deliberate lifecycle boundary between prepared inputs and an admitted Ideation Run.
- Inside the ideation CLI, use only the three approved injection seams: DeepSeek adapter, bound Scoped Literature Retriever, and event emitter. Normal evidence tests use real local storage; the emitter seam injects storage/interruption failures only where required. No fourth dependency-injection surface is introduced.
- Input preparation must deliver `VM-CONTRACT-018-01`, `VM-CONTRACT-018-02`, `VM-CONTRACT-019-01`, `VM-CONTRACT-019-02`, `VM-REPLAY-02`, `VM-LEAKAGE-01`, and `VM-LEAKAGE-04` from the [Validation Matrix](validation-matrix.md).
- Deterministic primitives must deliver `VM-UNIT-01` through `VM-UNIT-07`. These narrow unit tests are justified only for pure contract primitives such as canonical bytes, schema closure, hashing, ranking, cost, and taxonomy lookup.
- The retriever seam must deliver `VM-CONTRACT-020-01` through `VM-CONTRACT-020-04` and `VM-REPLAY-03`. BM25 scoring and canonical payload golden cases reuse the existing local-ranking prototype's public-payload and determinism testing style; runtime acceptance is asserted at the retriever result rather than the prototype harness.
- The adapter seam uses a deterministic transport stub and recorded responses to deliver `VM-CONTRACT-022-01` through `VM-CONTRACT-022-03`, `VM-REPLAY-01`, and `VM-FAULT-01`. Development tests perform no live provider request and incur no cost.
- The real evidence store plus the approved failure injection must deliver `VM-CONTRACT-023-01` through `VM-CONTRACT-023-03`, `VM-REPLAY-04`, `VM-ISOLATION-01` through `VM-ISOLATION-03`, `VM-FAULT-02`, and `VM-FAULT-03`.
- The ideation CLI/controller seam must deliver `VM-CONTRACT-024-01` through `VM-CONTRACT-024-03`, `VM-CONTRACT-025-01`, `VM-CONTRACT-025-02`, `VM-CONTRACT-026-01`, `VM-CONTRACT-026-02`, `VM-INTEGRATION-01` through `VM-INTEGRATION-03`, `VM-LEAKAGE-02`, `VM-LEAKAGE-03`, and `VM-FAULT-04`.
- Minimal-environment delivery must run `VM-ENV-01` through `VM-ENV-04`: the Python 3.13 clean environment and CPU reference path are blocking; compatibility candidates are recorded as specified by the matrix. Platform execution follows repository responsibilities without adding unapproved parity checks.
- Post-seal tools must deliver `VM-QUAL-01` by checking that every required finalized idea links to a schema-valid Evaluation Artifact. The categorical human verdicts themselves are not machine-tested.
- Prior art is the repository's existing subprocess replay test, strict closed-schema negative tests, deterministic input selection/build tests, BM25 golden scoring tests, canonical payload hash comparisons, isolated-attempt behavior, and offline replay evidence. Reuse their observable style, not their comparison-only directory layout or candidate abstractions.
- All tests above are zero-network and zero-cost. Paid smoke/Canary/terminal-wave execution is separate runtime evidence governed by the Canary and Scale Gate contract and requires the applicable Robert approval.

## Out of Scope

- BFTS, code experiments, plotting, LaTeX write-up, automated review, paper generation, or any other Downstream Experiment.
- Runtime global/remote literature search, provider-native web search, cross-case retrieval, fuzzy runtime enrichment, or fallback to stale/alternate corpora.
- E5, RRF, hybrid retrieval, alternate rankers, remote rankers, or any ranker fallback in v1.
- Selecting final `reasoning_effort`, `max_tokens`, or Workshop rendering variant before the approved Canary comparisons close tickets 035 and 036.
- Reproducing IdeaBench metrics, claiming benchmark comparability, introducing an LLM evaluator, or assigning numeric idea-quality scores.
- Multi-provider support in the new ideation path, deleting the retained legacy provider code, migrating to Responses API, or supporting arbitrary third-party callers.
- Accelerator-required execution, GPU training, dense-model runtime dependencies, or new cross-platform parity promises beyond repository rules.
- Public deployment, multi-tenant hardening, network service exposure, generalized sandboxing, speculative attack defenses, or compatibility layers not required by an approved contract and the project's actual operating conditions.
- Generating implementation tickets, implementing runtime code, running a model/Canary, closing ticket 030, merging, pushing, publishing, or releasing as part of this specification stage.

## Further Notes

- This is the single implementation specification for the entire Wayfinder destination. It is a decision index: linked ticket resolutions and contract documents remain authoritative when detail differs or later receives an approved versioned amendment.
- The existing ideation script is a baseline to modify, not evidence that this specification is implemented. The local-ranking prototype proves selected ranking behavior and testing techniques; it is not the production runtime or a general framework to preserve.
- `reasoning_effort`, `max_tokens`, and Workshop rendering variant are the only named Canary-stage open parameters. The implementation should expose controlled pins for them without creating separate implementation slices whose purpose is to decide their values.
- The v1 local-ranking decision is frozen as BM25 by parsimony under inconclusive winner evidence. Future replacement requires fresh evidence and the Optimization Promotion Gate; it must not reuse spent formal votes or reinterpret E5 as a scientific loser.
- The next delivery stage is `to-tickets`, which must create tracer-bullet implementation tickets tied to this spec and concrete Validation Matrix rows. Ticket 030 remains open until both this spec and that implementation ticket set are approved.
