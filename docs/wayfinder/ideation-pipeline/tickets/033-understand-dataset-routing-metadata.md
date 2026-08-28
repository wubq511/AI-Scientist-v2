---
title: Understand dataset routing metadata
type: research
status: closed
assignee: target_semantics
blocked_by: []
---

## Question

From the official IdeaBench paper/code and provided files, what do target `strategy`, the eight clusters, reference `contexts`, `intents`, and `isInfluential` mean; which are generation inputs, evaluation/routing metadata, or unsafe target-authored content; and which semantics remain undocumented?

## Resolution

[Primary-source research](../../../research/dataset-routing-metadata.md) confirms that `strategy` records target-collection provenance, clusters support post-hoc category analysis, `intents` were used only by reference filtering, and `contexts` are target-authored citation-edge text that must remain quarantined from ideation. `isInfluential` is stored but otherwise undocumented and unused. Official generation reads none of these fields; it routes by `targetPaperId` and exposes only matched reference abstracts.
