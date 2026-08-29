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
A literature query capability whose results come exclusively from one Target Reference Corpus and fail when that boundary cannot be proven.
_Avoid_: Semantic Scholar search, global retriever

**Ideation Pipeline**:
The permitted process from preparing target-scoped inputs through producing and validating research ideas.
_Avoid_: AI Scientist pipeline, experiment pipeline

**Ideation Run**:
One execution of the Ideation Pipeline for a specific Target Paper.
_Avoid_: Experiment, downstream run

**Run Isolation**:
The guarantee that one Ideation Run cannot read or influence another run's ideas, prompts, reflections, or mutable state unless that input is explicitly declared.
_Avoid_: Shared archive, implicit resume

**Evidence Chain**:
The connected record of inputs, decisions, actions, outputs, validations, and failures that explains why an Ideation Run is trustworthy.
_Avoid_: Console log, final result

**Evidence Feedback Loop**:
The repeated use of an Evidence Chain to find weaknesses, propose a design improvement, validate it, and retain what was learned.
_Avoid_: Ad hoc optimization, prompt tweaking

**Downstream Experiment**:
Any AI Scientist phase after idea generation, including BFTS, code experiments, plotting, write-up, and review; it is outside this project’s scope.
_Avoid_: Ideation Run
