---
title: Stage full-dataset execution
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

Must the system and model runs cover all 237 targets immediately?

## Resolution

The system must support all targets and deterministic preprocessing must validate all of them. Model runs start with representative canaries and scale only after isolation, quality, cost, and recovery gates pass and Robert approves expansion.
