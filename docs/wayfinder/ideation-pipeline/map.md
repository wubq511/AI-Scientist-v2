---
title: Design an Auditable Ideation-Only Pipeline
label: wayfinder:map
status: open
---

# Design an Auditable Ideation-Only Pipeline

## Destination

A Robert-approved, decision-complete specification and implementation ticket map for adapting this fork into a reproducible ideation-only system. It prepares target-scoped inputs, retrieves literature only from the paired references, calls `DeepSeek-V4-Pro-0813`, isolates every run, validates every output, and continuously improves design through an auditable Evidence Feedback Loop without entering downstream stages.

## Notes

- Planning only: do not implement destination deliverables while resolving this map.
- Read `AGENTS.md`, `CONTEXT.md`, relevant work logs, and `docs/agents/issue-tracker.md` before claiming a ticket.
- Use `wayfinder`, `grilling`, and `domain-modeling` for human decisions; use `research` for primary-source facts.
- Robert must approve every architecture, dataset, model/API, retrieval, evaluation, and scope decision.

## Decisions so far

- [Set the ideation-only destination](tickets/001-set-the-ideation-only-destination.md): plan a trustworthy ideation system with an evidence-driven design feedback loop.
- [Name the ideation domain](tickets/002-name-the-ideation-domain.md): distinguish Ideation Runs, Run Isolation, and Downstream Experiments.
- [Freeze literature before ideation](tickets/003-freeze-literature-before-ideation.md): enrichment may use public sources, while run-time retrieval stays local and fail closed.
- [Keep the Wayfinder local](tickets/004-keep-the-wayfinder-local.md): use a local Markdown tracker until remote publication is separately approved.
- [Modify the existing ideation path](tickets/005-modify-the-existing-ideation-path.md): keep the change surface direct instead of building a separate subsystem.
- [Preserve a compatible baseline](tickets/006-preserve-a-compatible-baseline.md): isolate necessary changes before evidence-driven optimizations.
- [Prevent Target Paper idea leakage](tickets/007-prevent-target-paper-idea-leakage.md): Workshop Files expose topics, not target innovations or results.
- [Separate idea payloads from evidence](tickets/008-separate-idea-payloads-from-evidence.md): retain the seven-field idea schema and store provenance beside it.
- [Stage full-dataset execution](tickets/009-stage-full-dataset-execution.md): support all targets, validate canaries, then scale only after approval.
- [Retain auditable run evidence](tickets/010-retain-auditable-run-evidence.md): preserve raw local evidence and commit sanitized manifests and summaries.
- [Trust layered validation and isolated runs](tickets/011-trust-layered-validation-and-isolated-runs.md): deterministic, replay, and qualitative evidence jointly support results.
- [Govern evidence-driven optimization](tickets/012-govern-evidence-driven-optimization.md): compare viable alternatives by evidence, then choose the simplest effective design.
- [Keep the runtime ideation-only](tickets/013-keep-the-runtime-ideation-only.md): use a minimal CPU environment without downstream dependencies.
- [Understand target-to-workshop semantics](tickets/014-understand-target-to-workshop-semantics.md): IdeaBench holds target content out of generation; the recruiter-specific Workshop transform needs an explicit leakage policy.
- [Establish the DeepSeek-V4-Pro-0813 provider contract](tickets/015-establish-the-deepseek-provider-contract.md): DeepSeek direct exposes the requested version only through a floating alias, leaving provider and pinning decisions open.
- [Audit metadata gaps and enrichment sources](tickets/016-audit-metadata-gaps-and-enrichment-sources.md): exact identifiers cover all papers; three abstracts and provenance/completeness gaps require explicit corpus policy.
- [Understand dataset routing metadata](tickets/033-understand-dataset-routing-metadata.md): routing is the target-reference pair; auxiliary edge/category fields stay outside model-visible retrieval.
- [Audit the minimal ideation runtime](tickets/017-audit-the-minimal-ideation-runtime.md): today's ideation entry runs CPU-only on Python 3.11 plus five packages (one undeclared, one unused); the dependency contract and DeepSeek-V4-Pro-0813 support remain open.

## Not yet specified

- Which optimizations are justified after the compatibility baseline produces evidence.
- Whether any target domain requires literature content beyond the provided metadata and abstracts.
- How the final interview narrative should prioritize findings that emerge from failed or degraded runs.
- Whether `DeepSeek-V4-Pro-0813` memorized any 2024 Target Papers; Workshop decontamination cannot remove parametric contamination.

## Out of scope

- BFTS, code experiments, plotting, LaTeX write-up, automated review, or `launch_scientist_bfts.py`.
- CUDA, GPU, PyTorch training, or dependencies used only by downstream stages.
- Global or remote literature search during an Ideation Run.
- A separate ideation subsystem or framework when direct changes suffice.
- Publishing tracker content or repository changes without Robert's separate approval.
