---
title: Qualify a Domain-Neutral Ideation Prompt Before Paid Canary
label: ready-for-agent
---

# 跨领域 Ideation Prompt 资格验证规格

## Problem Statement

Robert 需要系统从 IdeaBench 跨领域数据中生成有文献依据、问题空间匹配、方法学合理且可验证的科研构想。当前生产 prompt 却完整保留了 AI Scientist-v2 面向机器学习研究的上游目标：把模型设定为 AI researcher，要求成果可发表于 top ML conferences，以 conference format 写摘要，并在验证方案中给出 precise algorithmic changes 和 evaluation metrics。

这些约束与数据和任务目标不一致。当前 237 个已聚类 Target Papers 覆盖 Environmental Sciences、Genetics & Molecular Biology、Health & Medicine、Materials Science、Neuroscience & Cognitive Sciences、Public Health & Policy、Social & Behavioral Sciences、Technology & Engineering 八个领域；原始任务只要求生成科研 idea，并未要求所有构想成为 ML 论文。现有 prompt 因而会把本来适合湿实验、临床研究、观察研究、定性研究、政策评估、材料表征或理论分析的问题不必要地改写为算法与 benchmark 题目。

该问题在 ticket 035 首次付费矩阵前被发现。虽然 `reasoning_effort=high` 与 `max` 两臂共享同一 prompt，内部比较仍可归因于 reasoning effort，但其结论只适用于一个目标错配的生成任务，不能支撑跨领域 Ideation Pipeline。现有 035 冻结命令还包含生产 `new-run` 不接受的模型参数，因此不能作为可运行的付费计划继续使用。

## Solution

先暂停 reasoning-effort Canary，并在任何新增付费调用前资格验证一个领域中立 Prompt Profile。生产系统提供封闭、版本化的 Prompt Profile 身份：`ml-baseline-v1` 保留当前 prompt 的字节级语义作为 control，`cross-domain-v1` 作为 challenger。`new-run` 只接受已登记的 profile id，不接受自由文本、路径、任意模型参数或外部 prompt；解析后的 profile id、canonical prompt hash 和 profile contract version 必须进入 Run Specification、Run Request 与 Run Admission。fresh run 和 resume 都只能根据已准入的 profile 重建相同 model-visible prompt。

`cross-domain-v1` 将研究角色改为 multidisciplinary research scientist，把目标改为与 Workshop 和检索文献所属科学领域相称的 rigorous、grounded、high-impact research contribution。它不假定问题属于机器学习，也不假定 computational method 必需；只有当研究问题和文献证据证明必要时，才引入模型、算法、benchmark 或 quantitative metric。feasibility 必须考虑领域相称的资源、数据、设备、时间、伦理、安全和监管约束。

为保持既有 Evidence Chain、Evaluation Artifact 和下游隔离合同，七字段 idea payload 暂不改名。`Experiments` 字段改解释为 field-appropriate validation plan，可包含实验、观察研究、定性研究、仿真、计算分析、形式分析或证明；每项说明什么证据支持或证伪构想，仅在适当时要求 outcome、measure 或 evaluation criterion。`Abstract` 改为简洁的研究构想摘要，不再要求 conference format；`Title` 要求 clear and informative，不要求 catchy。reflection 明确检查方法与证据是否适合当前领域。工具面仍只有 `SearchLiterature` 和 `FinalizeIdea`，Declared Grounding、检索边界和 action schema 不变。

资格验证使用现有冻结 12-case Canary 的确定性四例子集：Genetics & Molecular Biology、Health & Medicine、Social & Behavioral Sciences、Materials Science 各一例；同一 cluster 内以 canonical case hash 选择，不读取 Target contribution 或运行结果。每个 case 运行 baseline/challenger 一对，共 4 对、8 个串行 Ideation Runs；两臂固定同一 Workshop、Corpus、model、`reasoning_effort=high`、`max_tokens=32768`、generation/reflection budgets、retriever、rubric 与验证规则，唯一主变量是 Prompt Profile。执行顺序和 A/B 映射各自 2/2 平衡并在结果前冻结。

付费执行采用两层预算语义。`5.00 CNY` 是累计实际支出的 Plan Gate **重审批阈值**：某个已单独批准的 run 可以在结算后跨过阈值，但下一 slot 必须停止并重新取得 Robert 批准；它不是无法由事后账本保证的“硬子上限”。`30.00 CNY` 是唯一 Canary **硬上限**：每个 provider request 前，用当前 stage 实际支出加该 run 按官方高峰价格计算的 `7.08 CNY` 最坏上界做 reservation，只有 projected ceiling `<= 30.00 CNY` 才可进入生产 `new-run`。冻结命令必须经过同进程 slot runner，在 exec 前验证 matrix、ledger、顺序和 write-once slot reservation；重复/并发启动同一 slot fail closed。生产 admission 的逐 run 费用提示和交互式 `yes` 继续保留。

全部 run sealed、静态验证、sanitized export 和 Evaluation Artifact 完成后，Robert 在隐藏 Prompt Profile、调用顺序、成本、延迟和 provider metadata 的 pair packet 上做 write-once 判断。`cross-domain-v1` 只有在 4 对完整、至少胜 3 对、baseline 胜 0 对、domain-method fit 至少两对严格改善且无一对变差、unjustified ML intrusion 不增加，并且 deterministic、grounding、feasibility、成本、延迟、重试和截断 Regression Budgets 全部通过时，才可进入 Promotion Gate。任何残缺、预算停止或未满足门槛的结果均不得晋升，也不得恢复旧 035 付费矩阵。

## User Stories

1. As Robert, I want ideation to optimize for scientifically valuable ideas, so that venue-specific proxies do not replace the actual task.
2. As Robert, I want the system prompt to support all eight dataset clusters, so that non-ML cases are not forced into an ML framing.
3. As Robert, I want the research role to be multidisciplinary, so that the model selects methods appropriate to the current field.
4. As Robert, I want the prompt to infer disciplinary context from the Approved Workshop and retrieved literature, so that private cluster metadata remains outside model context.
5. As Robert, I want ML methods used only when justified, so that computation is a possible method rather than a mandatory answer.
6. As Robert, I want the prompt to avoid a fixed conference target, so that journal-oriented and non-conference disciplines remain valid.
7. As Robert, I want the Abstract to summarize the research idea rather than imitate a conference submission, so that output form stays field-neutral.
8. As Robert, I want a clear and informative title rather than a catchy title, so that scientific precision is not traded for marketing language.
9. As Robert, I want the existing seven-field payload retained during qualification, so that prompt comparison is not confounded by a schema migration.
10. As Robert, I want `Experiments` to represent a validation plan, so that observational, qualitative, theoretical and formal work can be expressed without fabrication.
11. As Robert, I want experimental studies to remain supported, so that domain neutrality does not suppress legitimate experiments.
12. As Robert, I want observational studies to remain supported, so that causal or descriptive evidence need not be mislabeled as an experiment.
13. As Robert, I want qualitative studies and policy analysis to remain supported, so that social and public-policy questions receive appropriate methods.
14. As Robert, I want simulations and computational analyses to remain supported, so that legitimate computational work is not overcorrected away.
15. As Robert, I want formal analyses and proofs to remain supported, so that theoretical ideas are not forced to invent datasets or metrics.
16. As Robert, I want validation activities to name supporting or falsifying evidence, so that every proposal remains testable in its own methodological tradition.
17. As Robert, I want metrics requested only where appropriate, so that qualitative and theoretical validity is not reduced to arbitrary numbers.
18. As Robert, I want feasibility to include data and equipment access, so that plausible-looking proposals do not assume unavailable infrastructure.
19. As Robert, I want feasibility to include ethics, safety and regulation, so that clinical, human-subject and hazardous-material ideas are not treated like software benchmarks.
20. As Robert, I want feasibility to include time and team constraints, so that a proposal's validation plan is operationally credible.
21. As Robert, I want reflection to challenge domain-method mismatch, so that an initially misplaced method can be corrected before finalization.
22. As Robert, I want Related Work and novelty requirements retained, so that domain neutrality does not weaken literature-based differentiation.
23. As Robert, I want Declared Grounding unchanged, so that the prompt change cannot weaken evidence attribution.
24. As Robert, I want the Scoped Literature Retriever unchanged, so that prompt qualification cannot expand the literature boundary.
25. As Robert, I want the model-visible action set unchanged, so that prompt work cannot introduce code execution or Downstream Experiment actions.
26. As an operator, I want Prompt Profiles selected by a closed identifier, so that arbitrary prompt injection is unavailable.
27. As an operator, I want free-form prompt paths and text rejected, so that paid runs always use reviewed prompt bytes.
28. As an operator, I want the resolved profile identity and hash recorded before admission, so that every run has an auditable prompt identity.
29. As an operator, I want legacy Run Specifications interpreted as `ml-baseline-v1`, so that historic evidence retains its original meaning.
30. As an operator, I want resume to use the admitted profile rather than the current default, so that an interrupted run cannot cross Design Epochs.
31. As Robert, I want unknown or drifted profile identities to fail closed, so that replay never guesses which prompt was used.
32. As Robert, I want sanitized evidence to reveal only profile identity and hash, so that auditability does not publish private prompt history or case content.
33. As Robert, I want the baseline profile to reproduce current prompt semantics, so that the control arm is genuine rather than reconstructed from memory.
34. As Robert, I want the challenger and baseline to differ only in Prompt Profile, so that causal attribution remains defensible.
35. As Robert, I want four methodologically different cases, so that a cross-domain claim is not inferred from one biomedical or computing example.
36. As Robert, I want subset selection frozen before outputs, so that favorable cases cannot be chosen post hoc.
37. As Robert, I want two baseline-first and two challenger-first pairs, so that execution order is balanced.
38. As Robert, I want two A=baseline and two A=challenger mappings, so that pair labels do not reveal identity.
39. As Robert, I want all eight runs complete before a quality conclusion, so that partial evidence cannot promote the challenger.
40. As Robert, I want pair review to hide profile, order, cost and latency, so that quality judgment is not anchored by operational metadata.
41. As Robert, I want domain-method fit judged explicitly, so that ML intrusion cannot hide inside a superficially novel idea.
42. As Robert, I want legitimate ML usage distinguished from unjustified ML intrusion, so that the challenger is not rewarded for merely avoiding computation.
43. As Robert, I want existing rubric dimensions protected by Regression Budgets, so that domain fit does not come at the cost of grounding, novelty or feasibility.
44. As Robert, I want challenger cost and median latency limited to 2.0 times baseline, so that a wording improvement remains operationally acceptable.
45. As Robert, I want any new truncation, retry or failure mode to block promotion, so that qualitative gains cannot conceal reliability regressions.
46. As Robert, I want a 5 CNY reapproval threshold plus a 30 CNY pre-run hard-cap reservation, so that observed spend pauses for renewed consent and no request can exceed the Canary budget under its registered worst-case bound.
47. As Robert, I want every provider request separately estimated and approved, so that this specification never becomes spend authorization.
48. As Robert, I want all implementation tickets to stop before the first paid run, so that I can return to the originating session for live execution.
49. As Robert, I want old 035 commands marked inactive rather than overwritten, so that the failed preparation remains auditable.
50. As Robert, I want reasoning-effort comparison restarted only after prompt promotion, so that its winner is selected against the intended cross-domain objective.
51. As Robert, I want a rejected challenger to leave 035 halted, so that failure to find a good replacement does not make the known-wrong baseline acceptable.
52. As Robert, I want no Target identity, prompt response, reasoning, idea or credential in tracked artifacts, so that the established privacy boundary remains intact.
53. As Robert, I want the work remain ideation-only, so that prompt qualification cannot trigger BFTS, code experiments, plotting, writing or review.

## Implementation Decisions

- **Prompt Profile is the single new control seam.** It is a closed, versioned run input, not a dependency-injection interface. The only initial values are `ml-baseline-v1` and `cross-domain-v1`; callers cannot supply prompt bytes, paths, fragments, templates or unregistered identifiers.
- **Profile identity is part of the Run Specification.** New Run Request and Run Admission schema versions record profile id, contract version and SHA-256 of the complete canonical system/reflection prompt bundle. The controller verifies the hash before the first model operation.
- **Legacy evidence remains valid.** Admissions created before Prompt Profiles are interpreted exclusively as `ml-baseline-v1`. Validators and exporters accept both the legacy and new schema versions with version-specific closed semantics; no historical artifact is rewritten.
- **Resume is admission-driven.** A resumed run reconstructs prompt bytes from its admitted profile and rejects unsupported identity or hash drift. It never uses a mutable default and never upgrades an old run to the challenger.
- **Baseline remains pinned until Promotion Gate.** Adding `cross-domain-v1` makes it executable for governed comparison but does not make it the production default. A default change occurs only after an explicit `promoted` decision and opens a new Design Epoch.
- **Canonical cross-domain role text:** “You are an experienced multidisciplinary research scientist. Propose rigorous, high-impact research ideas appropriate to the scientific field described by the Workshop and the retrieved literature. Be creative, but do not assume the problem belongs to machine learning or that a computational method is required. Each proposal should stem from a clear question, observation, or hypothesis and explain how it differs materially from the existing literature.”
- **Canonical cross-domain method text:** “Use methods and evidence appropriate to the field. Computational models, algorithms, benchmarks, and quantitative metrics should appear only when justified by the research question and literature. Keep the proposal feasible for a realistic research team, accounting for relevant resource, data, equipment, time, ethical, safety, and regulatory constraints.”
- **Field descriptions are exact semantic requirements.** `Title` becomes clear and informative; `Abstract` is an approximately 250-word research summary covering question, motivation, approach, expected contribution and validation logic; `Experiments` becomes a concrete field-appropriate validation plan supporting experiments, observational studies, qualitative studies, simulations, computational analyses, formal analyses and proofs.
- **Reflection becomes field-aware.** It retains quality, novelty, feasibility, clarity, simplicity and tool-result integration, and additionally checks whether the proposed methods, evidence and feasibility assumptions fit the scientific field.
- **Unchanged model-visible contract:** Workshop injection order, previous-idea diversity prompt, `SearchLiterature`, `FinalizeIdea`, action framing, seven payload keys, Declared Grounding and JSON formatting stay unchanged except for the approved field descriptions and reflection criterion.
- **No cluster-conditioned branch.** Cluster labels serve only deterministic private subset selection and aggregate reporting. They never enter a Prompt Profile or model-visible payload.
- **Comparison subset is deterministic.** Select one case from each of four named clusters inside the already frozen and approved 12-case Canary; ties use canonical case hash. The selection must occur without inspecting target contributions or model outputs.
- **Comparison is one-major-variable.** Both arms use `reasoning_effort=high` and `max_tokens=32768`; Prompt Profile is the only differing Run Specification field. A machine check rejects any matrix with additional arm differences.
- **Offline comparison artifacts are complete before spend.** The preparation boundary produces selection manifest, approvals, balanced order, blind mapping, guarded exact commands, spend ledger, result-ingestion state, pair-packet plan and deterministic reducer. It contains no credential and cannot issue provider requests.
- **Promotion threshold is fixed.** Four complete pairs are mandatory; challenger needs at least three wins and zero baseline wins. Domain-method fit must improve on at least two pairs and regress on none; unjustified ML intrusion cannot increase; existing deterministic and qualitative Regression Budgets must pass.
- **Operational budgets are fixed at Plan Gate.** Challenger aggregate actual cost and median end-to-end latency may not exceed 2.0 times baseline; no challenger-only truncation, terminal failure, unresumable suspension, retry increase or new failure pattern is allowed. The exact CNY rates are revalidated immediately before Plan Gate. `5.00 CNY` is an observed-spend reapproval threshold, not a hard cap; `30.00 CNY` is reserved before every run using the registered high-price worst-case bound. Crossing the threshold is recorded rather than hidden, then blocks the next slot. Crossing the hard cap is prevented before provider work.
- **Live comparison commands are guarded and serial.** Every command carries the frozen matrix file SHA-256 and the `5.00 CNY` reapproval threshold. `scripts/run-prompt-comparison-slot` checks those external pins, the immutable `0.14 CNY` opening balance and all ledger arithmetic, requires `run_index = ingested_entries + 1`, recomputes `7.08 CNY` from the pinned price table, writes an exclusive `0600` slot reservation, and immediately execs production `new-run`. A stale reservation blocks retry until it is reconciled against the Evidence Chain; it is never silently deleted.
- **Known-bad preparation is retained, not repaired.** Proposal 001 and its private 24-run commands are withdrawn/inactive with zero paid runs and zero spend. They remain immutable evidence of why the sequence changed.

## Testing Decisions

- Good tests assert externally observable governed behavior: accepted/rejected profile ids, canonical prompt bytes and hashes, Run Request/Admission pins, fresh/resume equivalence, legacy interpretation, Evidence Chain validation, sanitized export, comparison balance, blinding, spend reduction and promotion arithmetic. They do not assert helper call order or internal string-concatenation structure.
- The highest runtime seam is the existing `new-run`/`resume` lifecycle exercised with recorded or mock transport through Run Admission, controller execution, Run Seal, validation and export. Both profiles must complete this seam with zero external network and no real credential.
- Pure contract tests supplement the lifecycle seam by proving byte-stable profile rendering, exact baseline preservation, absence of hard-coded ML venue/algorithm/metric mandates in the challenger, unchanged tool/action schema, and rejection of unknown or drifted profiles.
- Schema compatibility tests validate legacy and new Run Request/Admission documents separately, prove legacy means baseline, and prove a new profile cannot be injected into a legacy document or substituted during resume.
- Security tests prove profile selection accepts identifiers only, rejects paths/free text/unknown keys, never enters the Authorization header, and does not cause prompt text, case content or credentials to enter sanitized output.
- The highest comparison seam consumes synthetic opaque cases and sealed-run fixtures from deterministic subset selection through balanced order, blind packet construction, write-once verdict, reveal and final reduction. It remains zero-network and credential-free. (Ticket 02 plus the paid-boundary remediation deliver `ai_scientist/ideation/comparison.py`, `scripts/run-prompt-comparison-slot` and `tests/test_prompt_comparison.py`; the E2E test drives eight real synthetic sealed runs through the production lifecycle and reduces them byte-identically.)
- Comparison tests cover exact four-cluster membership, canonical tie-break, 2/2 execution-order balance, 2/2 A/B mapping balance, same-case input hashes, exact one-variable arm diff, guarded command shape and production-parser-valid inner `new-run` argv.
- Reducer boundary tests cover 3–0 promotion, 2–0 rejection, any baseline win, incomplete pair, domain-method regression, increased unjustified ML intrusion, deterministic failure, truncation, retry increase, more than 2.0 times cost or latency, and budget exhaustion.
- Spend tests cover initialization at zero, append-only per-run actual cost, failed/suspended/retried run accounting, threshold crossing without accounting loss, next-slot reapproval refusal, exact hard-cap reservation acceptance, one-cent-over refusal, sequential slot enforcement, duplicate reservation refusal and the rule that Plan Gate approval never approves an individual run.
- Existing transport, adapter, retrieval, controller, evidence, resume, export, evaluation, dependency, import and CLI tests must stay green. Full pytest, compileall, targeted Black, import/dependency checks, diff checks and Standards/Spec review are required before the paid handoff.

## Out of Scope

- Renaming or removing any of the seven idea payload fields during this comparison.
- Creating per-cluster, per-domain or dynamically generated prompts.
- Exposing cluster labels, Target metadata, Target contribution or routing fields to the model.
- Changing Workshop derivation, Target Reference Corpus contents, BM25 policy, retrieval payload, action schema, Declared Grounding or post-seal production rubric.
- Changing provider, model alias, API protocol, temperature, generation count, reflection count, `reasoning_effort` or `max_tokens` between prompt arms.
- Resuming Proposal 001, executing its 24-run matrix, selecting a reasoning-effort winner or claiming completion-limit sufficiency before prompt promotion.
- Using an LLM judge, numeric IdeaBench score, automatic semantic evaluator or post-hoc quality threshold.
- Any provider request while implementing or closing the three preparation tickets. Paid execution begins only after Robert returns to the originating session and approves the Plan Gate plus each run's cost prompt.
- Scale Gate, terminal wave, all-237 execution, BFTS, code experiments, plotting, LaTeX writing, paper generation, automated review, deployment or public release.

## Further Notes

- Robert approved this design direction and direct publication to tickets on 2026-09-04. This approval covers the zero-cost specification and preparation work; it is not the Promotion Plan Gate and not spend authorization.
- The confirmed test seams are the existing lifecycle boundary and one offline comparison boundary. No generic fourth dependency-injection seam is introduced.
- The live smoke's 0.14 CNY actual cost is only a rough planning observation. Eight analogous runs suggest approximately 1.12 CNY, while scaling Proposal 001's forecast gives approximately 1.12–2.24 CNY; both are non-authoritative until the current official price contract is rechecked.
- This plan assumes the Approved Workshop and retrieved literature contain enough disciplinary signal for one domain-neutral prompt. If blind evidence shows generic or methodologically vague outputs, `cross-domain-v1` is rejected and 035 stays halted; field metadata or schema changes require a new separately approved design.
- The three implementation tickets deliberately stop at a clean, hash-frozen, zero-spend paid-run handoff. Robert will complete them in another session, then return here for the prompt comparison's Plan Gate and interactive live runs.
- On return, adversarial preflight found that the original v1.1 ledger enforced its `5.00 CNY` label only after spend occurred and was not connected to frozen commands. Robert approved the zero-network v1.2 remediation on 2026-09-04: honest reapproval-threshold semantics, pre-run hard-cap reservation and a guarded slot runner. This approval repairs preparation only; it is still not the Proposal 002 Plan Gate or spend authorization.
