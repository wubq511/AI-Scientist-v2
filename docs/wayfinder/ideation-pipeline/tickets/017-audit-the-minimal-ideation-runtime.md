---
title: Audit the minimal ideation runtime
type: task
status: closed
assignee: runtime_audit
blocked_by: []
---

## Question

What imports, packages, commands, and platform assumptions are actually required to run preprocessing, ideation, and validation without installing or importing downstream dependencies?

## Resolution

[Minimal ideation runtime audit](../../../research/minimal-ideation-runtime-audit.md), verified by static import trace and an isolated Python 3.11.15 venv import test: the current ideation entry runs CPU-only with only `anthropic`, `backoff`, `openai`, `requests`, and `tiktoken` beyond the standard library, and no downstream module is transitively reachable. `requirements.txt` mismatches this reality: `requests` is undeclared, `tiktoken` is imported but unused, many declared packages serve only downstream stages or are never imported, and nothing is pinned. Run-time Semantic Scholar access still sits on the entry path pending the Scoped Literature Retriever, `DeepSeek-V4-Pro-0813` is absent from `AVAILABLE_LLMS`, output/resume uses a fixed file beside the workshop input with no run identity, and no preprocessing or idea-validation code exists yet. These facts feed `Define the safe ideation entry`, `Define run identity and evidence layout`, and the DeepSeek adapter tickets; the dependency policy question graduates into `Define the minimal runtime dependency contract`.
