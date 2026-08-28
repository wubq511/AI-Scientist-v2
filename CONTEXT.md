# Ideation Pipeline

This context defines the language for adapting AI Scientist v2 to generate auditable research ideas from target-scoped literature without entering downstream research execution.

## Language

**Target Paper**:
A paper whose research area defines the topic for one idea-generation case.
_Avoid_: Source paper, query paper

**Workshop File**:
A topic description derived from a Target Paper that scopes idea generation without serving as a completed research proposal.
_Avoid_: Target summary, idea prompt

**Target Reference Corpus**:
The unique set of reference papers associated with one Target Paper and the sole literature boundary for that case.
_Avoid_: Global corpus, reference pool

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
