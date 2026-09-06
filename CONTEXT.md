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

**Review Execution Config**:
The workspace-level write-once registration (`artifacts/evaluations/ai-review-config.json`) binding the two evaluator slots — provider, exact model id, and operator-declared model family — to the pinned prompt versions. The program cannot verify family lineage, so it only enforces that the two declared families and exact model ids differ (two personas of one model are not two independent evaluators), records the declared values verbatim as uncertified, and lets every aggregation re-verify records against this binding.
_Avoid_: API key material, prompt template, budget approval

**Evaluator Slot**:
One of the two isolated review contexts (`primary`, `second`) created by the Review Execution Config. Each slot stores its own imported responses, validated records, and evidence card under `artifacts/evaluations/<run_id>/ideas/<idx>/ai/<slot>/`; nothing carries one slot's answers into the other, and a consensus record may only merge records whose declared provider/model ids match the slot's binding.
_Avoid_: Persona, retry slot, model alias

**Dual-Review Consensus Record**:
The write-once per-dimension merge of the two slots' validated single-review records: only two valid, same-verdict judgments form a consensus (a shared negative stays negative); conflicts, abstentions, invalid, and missing slots stay separately accounted as unresolved and can never masquerade as complete. It carries the pre-registered quality floor independently and has no promotion authority.
_Avoid_: Vote tally, final grade, promotion input

**Pair Package**:
The deterministic, anonymous two-arm export built from two different sealed ideas of one case: model-visible direction payloads (A/B and the swapped B/A) present shared case material as `C###` and each arm's content as `A###`/`B###` sources, while the private outer document holds the arms' real bindings, the blind mapping, and the source registry. Direction payloads are scanned fail-closed for arm identity, run/case/pair identity, paper ids, cost, or expected-winner leakage.
_Avoid_: Comparison pair packet (that is the comparison stage's artifact), blind dataset

**Pair Reduction Record**:
The write-once restoration of the four pair reviews (two evaluator slots × two directions) from display-side verdicts back to anonymous content: only four valid judgments converging on the same content (or four ties) yield a stable result; position flips, evaluator conflicts, incomparable judgments, and missing/invalid records are incomparable with recorded reasons. Each arm's quality floor state is carried from its Dual-Review Consensus Record and is never overridden by the overall preference.
_Avoid_: Winner declaration, averaged score, promotion verdict

**Evaluation Protocol Manifest**（评估协议清单）:
The write-once registration (`artifacts/evaluations/evaluation-protocol-manifest.json`) that amends the governed comparison's scoring role after its first output: it pins the review execution config hash, prompt versions (single-review-v2 / pair-review-v1), all material schema versions, the aggregation-rules id, and a fixed post-first-output revision disclosure, and every consumption point re-verifies it so records from two protocols can never merge. It only changes who may author the post-seal judgment; pre-registered promotion criteria stay untouched. Offline coding acceptance only — activation requires Robert's explicit approval.
_Avoid_: Prompt config, gate approval, pre-registered blind review

**AI Verdict Channel**（AI 判定通道）:
The write-once `ai-verdicts/` directory of a comparison vault carrying an AI-authored pair verdict (schema `comparison-ai-verdict-v1.0.0`, authorship `ai_pair_reduction`) in anonymous content space, bound to the same packet hash a human verdict binds; it is disjoint from Robert's blinded human `verdicts/` and never satisfies the human reveal gate. Recording after reveal or recording twice fails closed; consuming it in the reducer requires the registered Evaluation Protocol Manifest.
_Avoid_: Robert's verdict, judge score, promotion input

**Evaluation Coverage Branch**（评估覆盖分支）:
The explicit version branch a comparison run's evaluation coverage takes: the unchanged v1 human `evaluation_artifact_v1` channel or the registered-protocol v2 AI `evaluation_artifact_v2_ai` channel (per-idea states missing / invalid / unaggregated / complete_resolved / complete_unresolved). Missing, invalid, and unaggregated fail closed at ingestion; complete_unresolved ingests but unresolved quality floors still block promotion; a run carrying both channels fails closed as a channel conflict.
_Avoid_: Mixed scoring, boolean coverage flag

**Evaluation Cost Ledger**（评审费用台账）:
The separate, append-only, hash-linked ledger (`artifacts/evaluations/evaluation-cost-ledger.json`, schema `evaluation-cost-ledger-v1.0.0`) recording physical AI review call counts and CNY costs (single_review / pair_review / repair); its merged read-only report carries the explicit disclosure that review costs are not covered by the generation Plan Gate approval and never silently extend the generation budget.
_Avoid_: Generation spend ledger, silent budget extension

**Migration Handoff Manifest**（迁移交接清单）:
The hash manifest (`migration-handoff-manifest-v1.0.0`) recording the direction, ledger state, and per-file SHA-256 of a private material round-trip between the generation worktree and the evaluation workspace, so the receiving end proves byte-exact receipt and both ends can tell which state is current. Missing or drifted files fail closed; ambiguity never resolves to guessing.
_Avoid_: Copy log, sync tool

**Ledger Recency Comparison**（台账新旧判定）:
The deterministic comparison of two workspaces' copies of the authoritative spend ledger (entries then forfeited entries, identical bytes as same_state) used before every new slot to decide which side may proceed after an interrupted round-trip. Equal progress with differing bytes fails closed as ambiguous and must be resolved by Robert against reservation/quarantine evidence, never guessed — this prevents double billing or slot skipping.
_Avoid_: Latest timestamp, manual diff

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
