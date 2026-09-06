---
title: Understand target-to-workshop semantics
type: research
status: closed
assignee: target_semantics
blocked_by: []
---

## Question

From primary sources and the provided dataset, what role does the Target Paper play, what information should become a Workshop File, and which content would leak the target contribution or invalidate the intended benchmark?

## Resolution

[Primary-source research](../../../research/target-to-workshop-semantics.md) confirms that IdeaBench keeps Target Paper content out of generation and uses it as a held-out evaluation comparator; only the target ID routes its reference abstracts. The recruiter's Target→Workshop transformation is bespoke. `abstract_summary`, target identifiers, target-authored `contexts`, methods, designs, results, and conclusions are answer-bearing and unsafe for ideation input. Exact Workshop policy remains a Robert-approved decision.
