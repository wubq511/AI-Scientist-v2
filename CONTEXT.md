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

**Evidence Event**:
An immutable, run-scoped record of one lifecycle, action, output, validation, or failure fact, ordered within its Ideation Run and linked to supporting artifacts where needed.
_Avoid_: Console log, mutable status row

**Evidence Chain**:
The connected record of inputs, decisions, actions, outputs, validations, and failures that explains why an Ideation Run is trustworthy.
_Avoid_: Console log, final result

**Evidence Feedback Loop**:
The repeated use of an Evidence Chain to find weaknesses, propose a design improvement, validate it, and retain what was learned.
_Avoid_: Ad hoc optimization, prompt tweaking

**Evaluation Artifact**:
A private, non-model-visible record produced after a Run Seal that stores Robert's structured qualitative comparison of one sealed run's final idea against its unsealed Target Paper, kept outside that run's Evidence Chain.
_Avoid_: Benchmark score, official metric

**Downstream Experiment**:
Any AI Scientist phase after idea generation, including BFTS, code experiments, plotting, write-up, and review; it is outside this project’s scope.
_Avoid_: Ideation Run
