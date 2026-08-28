---
title: Establish the DeepSeek-V4-Pro-0813 provider contract
type: research
status: closed
assignee: deepseek_contract
blocked_by: []
---

## Question

Using official provider sources, what endpoint, exact model identifier, authentication, request/response semantics, supported controls, limits, pricing, and failure behavior define `DeepSeek-V4-Pro-0813`?

## Resolution

[Official-provider research](../../../research/deepseek-v4-pro-0813-provider-contract.md) confirms that DeepSeek direct currently serves `DeepSeek-V4-Pro-0813` through floating request alias `deepseek-v4-pro`; no pinned direct `0813` ID is documented. The endpoint, controls, pricing, failure semantics, caching, and data policy are documented, but provider choice, checkpoint guarantee, account policy, credentials, and spend remain unresolved human decisions.
