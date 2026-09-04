---
title: Qualify a Domain-Neutral Ideation Prompt
label: wayfinder:map
status: open
---

# Qualify a Domain-Neutral Ideation Prompt

## Authority

- [Cross-domain Ideation Prompt specification](../../agents/cross-domain-ideation-prompt-spec.md)
- [Promotion Proposal 002](../../agents/promotions/002-cross-domain-ideation-prompt.md)
- [Optimization Promotion Gate](../../agents/promotion-gate.md)
- [Canary and Scale Gates](../../agents/canary-and-scale-gates.md)

Ticket frontmatter is authoritative for status and blocking edges. This effort delivers a paid-run-ready, zero-spend prompt comparison checkpoint. It ends before the first live provider request and does not resume ticket 035.

## Tickets

1. [Admit and replay one versioned Prompt Profile](tickets/01-admit-and-replay-one-versioned-prompt-profile.md)
2. [Reduce one blinded cross-domain prompt comparison](tickets/02-reduce-one-blinded-cross-domain-prompt-comparison.md)
3. [Freeze the paid-run-ready prompt Canary package](tickets/03-freeze-the-paid-run-ready-prompt-canary-package.md)

## Decisions so far

<!-- Add one line per closed ticket. -->
- Ticket 01 (closed 2026-09-04): 封闭、版本化 Prompt Profile seam 落地——`ml-baseline-v1`（字节级 golden 保持生产 baseline）与 `cross-domain-v1`（规格批准的领域中立 challenger）登记入 hash-pinned registry；`new-run` 强制 `--prompt-profile`，v1.1.0 Run Request/Admission pin id/contract-version/bundle-hash/registry-hash；fresh/resume/validation/export 全链同一 profile，legacy v1.0.0 恒解释为 baseline；生产 default 不变，零网络零费用完成。
