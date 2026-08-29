---
title: Keep the runtime ideation-only
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

Which environment is required for this task?

## Resolution

Provide a minimal ideation-only environment for dataset preparation, local retrieval, model calls, logging, and validation, with a portable CPU FP32 reference path. An optional inference accelerator is allowed only after a scoped evidence gate proves material end-to-end benefit, identical observable payloads, no operator fallback, and acceptable dependency cost; it must never become required. Exclude accelerator-dependent assumptions, GPU training, LaTeX, BFTS, plotting, and other downstream-only dependencies.
