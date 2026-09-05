# Ideation Pipeline

This context defines the language for adapting AI Scientist v2 to generate auditable research ideas from target-scoped literature without entering downstream research execution.

## Language

**Target Paper**:
A paper whose research area defines the topic for one idea-generation case.
_Avoid_: Source paper, query paper

**Workshop File**:
A target-derived, model-visible topic description that scopes one Ideation Run without revealing the Target Paper's held-out contribution or identity.
_Avoid_: Target summary, idea prompt

**Workshop Abstract**:
The model-visible topic narrative in a Workshop File; it describes the research space and is not the Target Paper's abstract or a summary of that paper.
_Avoid_: Target abstract, paper abstract

**Approved Workshop**:
A Workshop File that has passed deterministic and independent semantic validation and is permitted to enter an Ideation Run.
_Avoid_: Generated Workshop, draft Workshop

**Workshop Manifest**:
A private, non-model-visible provenance record that links one Workshop File to its Target Paper and retains the evidence needed to audit that derivation.
_Avoid_: Prompt metadata, Workshop frontmatter

**Target Reference Corpus**:
A self-contained, per-case literature artifact whose membership is the unique set of reference papers associated with one Target Paper and whose frozen form is the sole local literature boundary for that case. Retrieval readiness requires trustworthy identity, searchable-content status, membership proof, and provenance; citation completeness is not required.
_Avoid_: Global corpus, reference pool

**Reference Content**:
Source-faithful paper text retained by a Target Reference Corpus for possible retrieval, labeled by its actual source type such as publisher abstract or official full text. Derived text never assumes the identity of a published abstract.
_Avoid_: Fallback abstract, repaired abstract

**Approved Target Reference Corpus**:
A Target Reference Corpus whose exact bundle identity has passed deterministic validation, focused review of exceptional content, and the approved version and canary gates, and is permitted as an Ideation Run's sole local literature input.
_Avoid_: Generated corpus, latest corpus

**Ideation Case**:
The private association of one Target Paper, one Approved Workshop, and one Target Reference Corpus, addressed at runtime by an opaque `case_id` that does not reveal the Target Paper's identity.
_Avoid_: Dataset row, target ID

**Scoped Literature Retriever**:
A literature query capability bound by runtime preflight to exactly one Approved Target Reference Corpus. The model supplies query text but cannot choose or switch scope; retrieval fails when the boundary cannot be proven.
_Avoid_: Semantic Scholar search, global retriever

**Retrieval Segment**:
A bounded, source-faithful portion of eligible Reference Content used as model-visible literature evidence, with an exact link to its source content and without becoming derived text.
_Avoid_: Generated excerpt, fallback summary

**Retrieval Result**:
A paper-level, model-visible response from a Scoped Literature Retriever containing only stable paper identity, title, and eligible Retrieval Segments; array order expresses relevance.
_Avoid_: Search dump, ranked metadata

**Retrieval Audit Event**:
A private, non-model-visible record that connects one retrieval invocation to its bound corpus, policy, candidates, ranking decisions, returned evidence, and outcome.
_Avoid_: Tool response, model context

**Ideation Pipeline**:
The permitted process from preparing target-scoped inputs through producing and validating research ideas.
_Avoid_: AI Scientist pipeline, experiment pipeline

**Ideation Run**:
One isolated attempt to execute the Ideation Pipeline for one Ideation Case under a fixed run specification. It owns one Evidence Chain, may continue across an approved resume after interruption, and ends when it reaches a sealed terminal outcome; a replay or rerun is a new Ideation Run.
_Avoid_: Experiment, downstream run

**Run Specification**:
The immutable declaration of the exact case, approved inputs, code, model, policies, configuration, and budgets under which an Ideation Run seeks admission. Changing it requires a new Ideation Run.
_Avoid_: Current config, latest inputs

**Run Isolation**:
The guarantee that an Ideation Run cannot read or influence another run's ideas, prompts, reflections, artifacts, or mutable state. Runtime input from a prior run is prohibited unless a future contract explicitly introduces a narrower declared-import mechanism.
_Avoid_: Shared archive, implicit resume

**Run Admission**:
The immutable evidence that preflight bound one Ideation Run to an exact approved input and policy set and permitted ideation work to begin. A rejected run has no Run Admission.
_Avoid_: Latest config, implicit preflight

**Run Seal**:
The immutable terminal evidence that closes an Ideation Run and fixes its outcome and final Evidence Chain boundary. A sealed run cannot resume or accept more evidence.
_Avoid_: Final save, completed flag

**Terminal Outcome**:
The sealed end state of an Ideation Run, exactly one of `success`, `failed`, or `preflight_rejected`, fixed by its Run Seal. A suspended run has no terminal outcome.
_Avoid_: Completed status, exit code

**Run Suspension**:
An unsealed, resumable stop of an Ideation Run caused by external interruption or an environment-class failure, preserving all committed evidence; an approved resume continues the same run under a new writer epoch.
_Avoid_: Paused run, crashed run, implicit resume

**Generation Disposition**:
The recorded terminal result of one proposal generation inside an Ideation Run, exactly one of `finalized` or `budget_exhausted`; a non-finalizing generation is model-behavior evidence and does not by itself terminate the run.
_Avoid_: Generation error, skipped generation

**Model-Fixable Error**:
An action-protocol or tool-input error the model can correct on a later round, fed back as that round's tool result at the cost of one reflection round; never a silent abort or an invisible print.
_Avoid_: Validation error, parse failure

**Idea Quality Rubric**:
The versioned catalog of idea-quality criteria that assigns each criterion to exactly one enforcement layer: runtime evidence-backed checks at the finalization gate, or Robert's post-seal qualitative judgment.
_Avoid_: Quality checklist, idea score

**Declared Grounding**:
The model's declaration, submitted with FinalizeIdea outside the seven-field idea payload, of which papers retrieved in the same Ideation Run the idea builds on; verified deterministically against the run's Retrieval Audit Events.
_Avoid_: Citations, reference list

**Idea Leakage**:
The presence of private, non-model-visible information such as `case_id`, corpus paths or hashes, or internal identifiers in model-submitted FinalizeIdea content; detected by a deterministic payload hygiene scan and distinct from Workshop-side leakage, which is governed by Workshop File validation.
_Avoid_: Payload contamination, target leakage

**Evidence Event**:
An immutable, run-scoped record of one lifecycle, action, output, validation, or failure fact, ordered within its Ideation Run and linked to supporting artifacts where needed.
_Avoid_: Console log, mutable status row

**Evidence Chain**:
The connected record of inputs, decisions, actions, outputs, validations, and failures that explains why an Ideation Run is trustworthy.
_Avoid_: Console log, final result

**Evidence Feedback Loop**:
The repeated use of an Evidence Chain to find weaknesses, propose a design improvement, validate it, and retain what was learned.
_Avoid_: Ad hoc optimization, prompt tweaking

**Optimization Promotion**:
The governed mechanism that turns an Evidence Feedback Loop finding into an accepted design change: a Promotion Proposal takes effect only after passing a Plan Gate and a Promotion Gate, and the pinned design stays unchanged otherwise.
_Avoid_: Ad hoc tuning, silent update

**Promotion Proposal**:
The sanitized, sequentially numbered record of one proposed evidence-motivated design change, carrying the falsifiable hypothesis, one-major-variable declaration, comparison plan, pre-registered pass/fail criteria and Regression Budgets, evidence summary, and both gate decisions.
_Avoid_: Optimization ticket, tweak request

**Plan Gate**:
Robert's approval of a Promotion Proposal's hypothesis, comparison plan, Regression Budgets, and cost estimate, required before any comparison run may begin.
_Avoid_: Informal go-ahead, post-hoc sign-off

**Promotion Gate**:
Robert's final decision on a Promotion Proposal, judged solely against the criteria pre-registered at its Plan Gate without introducing new discretion.
_Avoid_: Merge approval, rubber stamp

**Regression Budget**:
The per-dimension tolerance — deterministic, cost, and quality — pre-registered in a Promotion Proposal; exceeding it, or regressing on an unbudgeted dimension, automatically rejects the proposal.
_Avoid_: Error bar, informal tolerance

**Design Epoch**:
The span of Ideation Runs and their evidence produced under one pinned design state; canary and scale evidence is comparable only within an epoch, and each Optimization Promotion opens a new one.
_Avoid_: Phase, config version

**Evaluation Artifact**:
A private, non-model-visible record produced after a Run Seal that stores Robert's structured qualitative comparison of one finalized idea from that sealed run against its unsealed Target Paper — exactly one artifact per finalized idea, regardless of the run's Terminal Outcome — kept outside that run's Evidence Chain.
_Avoid_: Benchmark score, official metric

**Evaluation Brief**:
The private, tool-assembled side-by-side comparison material — a finalized idea payload with its Declared Grounding and the relevant Retrieval Segments set against the Target Paper's `abstract_summary` and full abstract — that Robert reads to author an Evaluation Artifact. It is reading material, not evidence, and may be regenerated.
_Avoid_: Judge prompt, evaluation report

**AI Review Record**:
The private, write-once v2-authoring record (under `artifacts/evaluations/<run_id>/ideas/<idx>/ai/`) that stores one AI evaluator's evidence-linked seven-dimension suggestion for one finalized idea — original verdict enums plus an independent `insufficient_evidence` status — with the AI author, the validating tool, and any operator decision recorded as separate roles. It is honest engineering-advice evidence with no promotion authority and no claim of expert scientific truth; it never replaces or rewrites a v1 Evaluation Artifact.
_Avoid_: Robert's verdict, judge score, promotion input

**Review Material Package**:
The deterministic, anonymous two-layer export the AI reviewer reads: a model-visible payload (Workshop text, sealed idea fields, the complete retrieval release record of the sidecar-bound operations, Target Comparator, and an honest audit scope statement, identified only by package-internal source IDs) plus a private outer envelope binding run, seal, and idea hashes with the real paper identities. Model-visible parts never contain Prompt Profile identity, baseline/challenger mapping, winner intent, or run metadata.
_Avoid_: Evaluation Brief (that is the human artifact's reading material), prompt, dataset

**Evidence Card**:
The regenerable Chinese rendering of one validated AI Review Record: per-dimension suggested verdicts or abstentions with rationale, verbatim-verified quotes, key assumptions, and open questions, always stating that quote existence is machine-verified while semantic support is not and that a single-review card is not scientific ground truth.
_Avoid_: Evaluation Artifact, review report, verdict

**Validation Matrix**:
The versioned contract (`docs/agents/validation-matrix.md`) cataloging every check across nine layers (unit, contract, integration, replay, leakage, isolation, fault-injection, minimal-environment, qualitative), defining what must pass and what evidence proves each gate; it indexes runtime gates decided elsewhere and defines the development-time tests that prove them.
_Avoid_: Test plan, test suite

**Canary**:
A fixed, Robert-approved set of representative Ideation Cases, selected by documented stratified rules and deliberately including a minority of known edge cases, that serves both first real-run validation and the model-parameter and Workshop-variant comparisons before any scale-out toward the interview-sized final wave.
_Avoid_: Test subset, pilot batch

**Scale Gate**:
The explicit checkpoint of isolation, quality, cost, and recovery conditions plus Robert's approval that must hold before model execution expands beyond the Canary toward an interview-sized final wave; its conditions cite Validation Matrix rows rather than restating them.
_Avoid_: Milestone, sign-off

**Downstream Experiment**:
Any AI Scientist phase after idea generation, including BFTS, code experiments, plotting, write-up, and review; it is outside this project’s scope.
_Avoid_: Ideation Run
