---
title: Qualify Auditable Live Ideation Execution
label: wayfinder:map
status: open
---

# Qualify Auditable Live Ideation Execution

## Authority

- [Live smoke execution specification](../../agents/live-smoke-execution-spec.md)
- [Ideation pipeline implementation specification](../../agents/ideation-pipeline-spec.md)
- [Canary and Scale Gates](../../agents/canary-and-scale-gates.md)
- [Delivery and Handoff](../../agents/delivery-and-handoff.md)

Ticket frontmatter is authoritative for status and blocking edges. This effort bridges the completed zero-network implementation into the first approved live smoke; it does not claim or execute tickets 035/036.

## Tickets

1. [Enable auditable live DeepSeek execution](tickets/01-enable-auditable-live-deepseek-execution.md)
2. [Qualify one auditable live smoke run](tickets/02-qualify-one-auditable-live-smoke-run.md)

## Decisions so far

- **01: Enable auditable live DeepSeek execution**: Promoted `httpx==0.28.1` as the sole runtime third-party dependency; implemented production `HttpTransport` with strict security settings (`verify=True`, `follow_redirects=False`, `trust_env=False`, 10s connect timeout, 3600s monotonic streaming wall-clock deadline, zero client retries, and runtime secret scrubbing); wired `_run_new_run` bare CLI to execute after admission by default; confirmed 100% pass across 12 zero-network mock transport tests and 640 full repository tests.
