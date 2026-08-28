---
title: Retain auditable run evidence
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

Which run evidence must be retained, and what may enter Git?

## Resolution

Retain queries, retrieved papers, prompts, responses, reflections, failures, and validations as immutable, gitignored raw artifacts. Commit sanitized manifests, schemas, statistics, conclusions, and work logs. Never record secrets.
