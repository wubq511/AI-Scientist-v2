---
title: Trust layered validation and isolated runs
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

What evidence makes an Ideation Run trustworthy, and may runs share mutable idea state?

## Resolution

Trust requires deterministic invariants, integration replay, and qualitative evaluation; an LLM judge cannot replace the first two. Each run must have isolated idea archives, prompts, reflections, artifacts, and resume state so ideas cannot contaminate other runs.
