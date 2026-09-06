---
title: Enable Auditable Live DeepSeek Execution and Qualify One Smoke Run
label: ready-for-agent
---

# 可审计真实 DeepSeek 执行与单 Case Smoke 规格

## Problem Statement

Robert 已经完成并关闭可审计 ideation-only pipeline 的 13 张实现票，但当前可执行系统仍停在「真实输入准入 + 离线 stub/recorded transport 验证」：DeepSeek adapter 有严格请求、响应、重试、失败分类、成本和 Evidence Chain 契约，但没有可从唯一安全 CLI 到达 DeepSeek direct API 的生产 HTTP transport。Bare `new-run` 只完成 Run Admission，`resume` 也没有默认的真实 transport，因此仓库还无法执行已批准的 1-case smoke，更不能按契约进入 035/036 Canary 比较。

如果用临时 Python injector、隐藏环境开关或另一个无契约 runner 发起请求，则真实执行会绕开已批准的入口面、resume 路径、依赖契约和 clean-environment 验证；这样即使获得一次 HTTP 200，也不能证明交付系统可运行。

## Solution

在不扩大 CLI 参数面、不新增注入 seam、不改变 controller/retriever/evidence 语义的前提下，为现有 DeepSeek adapter 提供一个使用精确锁定 HTTP 依赖的生产 transport。`new-run` 继续使用现有七参数入口，完成九步 preflight、显式费用批准和 Run Admission 后，才通过该 transport 执行付费工作；`resume` 通过同一 transport 继续 exact `run_id`，不产生第二条真实执行路径。

先在全部 zero-network mock 与 Python 3.13 clean environment 中验证 transport、CLI、resume、失败分类、绝对 deadline、credential 隔离和 raw-response evidence，并提交一个独立可回滚的 readiness 变更。然后使用现有 approved Workshop/Corpus 的单一 case，在低谷时段按 `1 generation × 3 reflections`、`reasoning_effort=high`、`max_tokens=32768` 执行一次真实 smoke。这次付费执行的峰值保守上界为 7.08 CNY，必须在运行当次由 Robert 单独批准；本规格的批准不替代运行费用批准。

## User Stories

1. As Robert, I want the completed offline ideation pipeline to have one supported live-provider path, so that a real smoke validates the delivered system rather than a throwaway harness.
2. As an operator, I want `new-run` to keep its approved seven-parameter surface, so that live execution cannot introduce model, endpoint, ranker, device, or output-root overrides.
3. As an operator, I want `new-run` to finish all nine preflight steps and write Run Admission before any HTTP request, so that paid work never precedes approval.
4. As Robert, I want the exact per-run worst-case CNY bound shown before execution, so that approving this specification cannot be mistaken for approving model spend.
5. As Robert, I want the live smoke cost approval to remain an exact interactive `yes`, so that automation cannot silently spend against the Canary budget.
6. As an operator, I want `resume` to use the same live transport as `new-run`, so that a suspended live run does not require a separate runner or configuration path.
7. As Robert, I want the transport to implement the existing transport-neutral adapter contract, so that provider validation and Evidence Chain semantics remain authoritative.
8. As Robert, I want the provider host, path, model, thinking mode, streaming mode, and request shape fixed by the approved contract, so that callers cannot redirect private scientific content.
9. As Robert, I want the API credential read only from `DEEPSEEK_API_KEY`, so that secrets never become CLI arguments, source code, request artifacts, logs, commits, or chat content.
10. As Robert, I want ambient HTTP proxy variables ignored by the live transport, so that prompts cannot be routed through an undeclared intermediary.
11. As Robert, I want TLS verification enabled and redirects disabled, so that a provider response cannot move the request to an unapproved origin.
12. As an operator, I want a 10-second connection timeout and a 60-minute absolute attempt deadline, so that a stalled provider does not hold the run indefinitely even if keep-alive bytes continue arriving.
13. As an operator, I want non-streaming keep-alive whitespace accepted before the JSON body, so that documented DeepSeek waiting behaviour is not misclassified as malformed JSON.
14. As Robert, I want the exact response body bytes observed at the transport boundary retained through the existing Provider Attempt evidence path, so that later replay validates what the adapter actually parsed.
15. As Robert, I want response status, allowed headers, duration, response identity, usage, and cost handled by the existing adapter, so that transport wiring does not create a second evidence schema.
16. As an operator, I want network, timeout, TLS, and disconnect failures converted into the approved typed failure taxonomy, so that the controller applies suspend-or-terminal behaviour without guessing.
17. As Robert, I want the HTTP client to perform no implicit retries, so that only the existing adapter's bounded retry policy can create a second physical attempt.
18. As Robert, I want retryable HTTP responses such as 429/500/503 to retain their status and `Retry-After` evidence, so that approved retry behaviour remains observable.
19. As Robert, I want authentication and balance failures to remain explicit deterministic evidence, so that the runner cannot switch accounts, providers, models, or endpoints.
20. As a maintainer, I want the one live HTTP dependency promoted into the runtime dependency contract with an exact pin, so that the declared clean environment matches the real execution closure.
21. As a maintainer, I want the import allowlist and dependency tests to fail if undeclared provider libraries enter the ideation path, so that the live bridge remains minimal.
22. As a maintainer, I want all transport behaviour testable without network access through the existing transport and CLI seams, so that tests never consume credentials or model budget.
23. As a maintainer, I want the normal programmatic adapter injection seam preserved, so that recorded/stub tests remain deterministic after the production default is added.
24. As an operator, I want CLI output and exit statuses to continue distinguishing sealed, preflight-rejected, resume-rejected, and suspended outcomes, so that live execution remains script-observable.
25. As Robert, I want one approved case with an approved Workshop and approved Target Reference Corpus used for smoke, so that provider mechanics are tested without expanding dataset scope.
26. As Robert, I want the smoke to request one idea with up to three model rounds, so that SearchLiterature, FinalizeIdea, and one model-fixable recovery opportunity can be exercised within a bounded spend.
27. As Robert, I want the smoke to retain the currently approved `high` effort and 32768 completion limit, so that it qualifies the baseline without prematurely deciding ticket 035.
28. As Robert, I want the smoke executed during an official off-peak window when practical, so that actual cost is minimized while the conservative approval remains peak-priced.
29. As Robert, I want the smoke to preserve every success, failure, suspension, usage record, and actual cost in private evidence, so that a negative result is still a useful Evidence Feedback Loop observation.
30. As Robert, I want a successful smoke Evidence Chain statically validated and sanitized-exported, so that live output proves the validation/export handoff rather than only provider reachability.
31. As Robert, I want an Evaluation Brief assembled for every finalized smoke idea, so that the first live result reaches the approved post-seal evaluation boundary.
32. As Robert, I want to remain the only author of qualitative Evaluation Artifact verdicts, so that smoke qualification does not introduce an LLM judge or synthetic quality claim.
33. As Robert, I want a model-behaviour failure eligible for at most one fresh-run retry under a new cost approval, so that smoke can recover without turning into an open-ended spending loop.
34. As Robert, I want design-shaped failures routed through the Optimization Promotion Gate rather than patched in place, so that the smoke does not mutate the baseline while evidence is incomplete.
35. As Robert, I want ticket 035 to remain unclaimed until the live smoke has produced trustworthy evidence, so that the 24-run comparison does not amplify a transport or admission defect.
36. As Robert, I want all tracked smoke conclusions to be sanitized and all prompts, responses, reasoning, ideas, target identity, provider IDs, credentials, and absolute paths to stay private, so that reproducibility does not leak interview data.

## Implementation Decisions

- **Delivery shape**: create one execution-stage effort after the completed 13-ticket implementation effort. Split it into a zero-cost live-execution readiness slice and a blocked paid-smoke qualification slice. The first slice is independently mergeable and useful even if credentials or spend approval delay the second.
- **Single supported entry**: `new-run` becomes the supported admit-and-execute command. It retains exactly the approved seven arguments; successful preflight, explicit cost approval, and Run Admission are mandatory before the controller may call the provider. `resume` retains exactly one `run_id` argument and uses the same production transport. No `--execute`, endpoint/model switch, hidden environment flag, alternate runner, or second CLI is added.
- **Existing seam only**: the production transport implements the current synchronous `Transport.send` boundary and returns the current `TransportResponse`. Stub and recorded transports remain unchanged. Adapter, bound retriever, and event emitter remain the only three injected boundaries.
- **HTTP client**: use `httpx==0.28.1` directly rather than the OpenAI SDK or a subprocess `curl` wrapper. It is promoted from development-only use to the exact runtime dependency. This avoids SDK request normalization/implicit behaviour and avoids credential-bearing subprocess control while reusing a dependency already exercised in repository transport prototypes.
- **Endpoint and request**: send canonical JSON bytes by HTTPS `POST` to the fixed DeepSeek direct Chat Completions endpoint. Authentication is one `Authorization: Bearer` header built from `DEEPSEEK_API_KEY`; request evidence continues to contain only the canonical JSON payload and never headers. Content type is JSON, streaming remains false, thinking remains enabled, provider native tools/web search remain absent, and redirects are rejected.
- **Network isolation**: TLS certificate verification is mandatory; ambient proxy and `.netrc` configuration are ignored; redirects are disabled; the transport accepts no caller-provided URL, headers, certificate policy, proxy, retry, or client object in production.
- **Timeout semantics**: connection establishment has a 10-second timeout. The whole physical attempt has an absolute 60-minute wall-clock deadline enforced above per-read inactivity timeouts, so documented keep-alive whitespace cannot extend an attempt forever. Deadline expiry and uncertain disconnects preserve the approved ambiguous/suspend taxonomy and are never automatically reissued by the transport.
- **Retry ownership**: the HTTP client and transport perform zero retries. The existing adapter remains the only owner of the at-most-two-attempt policy and the only interpreter of `Retry-After` for approved transient responses.
- **Response boundary**: return the observed response body bytes, normalized response headers, HTTP status, and measured duration through the existing transport result. The adapter remains solely responsible for parsing, provider invariants, redaction, typed failure mapping, usage validation, price calculation, Provider Attempt artifacts, and event emission.
- **CLI default and test injection**: production CLI invocation selects the production transport after admission; tests and library callers may still inject a stub/recorded adapter through the existing seam. A bare production command must never silently fall back to admission-only success after the live bridge ships.
- **Dependency and documentation contract**: update runtime/development dependency roles, import-closure expectations, CLI observable help, repository instructions, and clean-environment evidence in the same readiness slice. Retained upstream/downstream dependencies remain separate.
- **Smoke case and budget**: the first live smoke uses the already approved private case and its current Workshop/Corpus pins. It fixes `max_num_generations=1`, `num_reflections=3`, `reasoning_effort=high`, and `max_tokens=32768`. With three rounds, two attempts per round, 32768 worst-case input tokens per round, and 32768 output tokens per round, the approved peak-price upper bound is 7.08 CNY.
- **Approval boundary**: approval of this specification authorizes writing the readiness implementation and ticket documents only. The live smoke still requires a clean committed worktree, current price-page verification, locally configured credential, sufficient account balance, and the existing interactive per-run cost approval. No credential value is requested through Codex.
- **Smoke completion**: a mechanically successful smoke ends with a non-corrupt sealed run, static chain validation, sanitized export, and an assembled Evaluation Brief for every finalized idea. Robert authors the categorical verdicts; validated Evaluation Artifacts establish complete smoke evaluation coverage.
- **Failure handling**: preflight rejection makes no provider call. Environment/ambiguous failures leave the run suspended according to the existing taxonomy. Deterministic provider/contract failures seal failed. A model-behaviour failure may create at most one new run only after a fresh estimate and approval. Suspected design defects stop and enter the approved Promotion Gate; there is no provider/model/endpoint/validation fallback.
- **Stage boundary**: completion of this spec does not select `reasoning_effort`, change `max_tokens`, choose a Workshop variant, claim 035/036, select the final 12-case Canary, or open the Scale Gate. A trustworthy smoke is the prerequisite for that later work.
- **Premise-collapse rule**: this design assumes the live DeepSeek response conforms to the currently approved Chat Completions contract. If the account-level smoke reveals an incompatible response shape or behaviour, preserve the failed/suspended evidence and reopen the relevant versioned adapter decision; do not add permissive parsing or runtime fallback.

## Testing Decisions

- Good tests assert public contract outcomes: exact outgoing method/origin/path/body, absence of credential in artifacts and errors, returned status/body/headers/duration, typed failure, attempt count, event sequence, seal/suspension state, CLI exit status, and dependency/import closure. They do not assert `httpx` private types, helper call order, coroutine layout, or socket implementation details.
- The first highest seam is the existing `Transport.send` contract with an in-process mock HTTP transport. It proves exact canonical request bytes, fixed destination, credential header use without persistence, TLS/redirect/proxy policy, raw response capture, duration, keep-alive whitespace, connection failure, TLS failure, disconnect, HTTP errors, and absolute deadline without external network.
- The second highest seam is the existing `new-run` / `resume` CLI-controller seam. It proves no request before Admission, production-default transport selection, successful sealed flow through an injected HTTP mock, suspended resume through the same path, unchanged parameter allowlists, and stable exit/output semantics.
- Adapter retry tests continue to prove that the transport does not retry, the adapter retries only approved transient classes, `Retry-After` stays bounded, and ambiguous failures are never retried.
- Security tests scan request, response, failure, event, stdout/stderr, sanitized export, and repository diff fixtures for active or token-shaped credentials. They prove ambient proxy variables and redirects cannot redirect model-visible payloads.
- Dependency tests prove `httpx==0.28.1` is the only ideation runtime package, development and retained-upstream files keep distinct roles, and the entry import allowlist matches the implemented closure.
- Clean-environment validation uses Python 3.13 with exact runtime and development contracts, runs the full pytest suite, CLI help and preflight/live-mock smoke, compileall, Black, and the import/dependency contract. Python 3.12/3.14 remain compatibility candidates under existing repository policy.
- Prior art is the current DeepSeek adapter recorded/stub tests, sealed-run CLI seam, suspend/resume fault injection, preflight pty approval tests, import/dependency contract tests, and repository `httpx.MockTransport` transport prototypes. Reuse their observable testing style, not their prototype output layouts or alternate provider contracts.
- The readiness slice performs zero real network and zero model spend. The live smoke is not a test-suite action: it runs only after a clean commit and distinct human cost approval, and records commit SHA, input hashes, command, provider/model configuration, timestamps, usage, actual cost, output paths, validation, failures, and output hashes.
- After implementation, run a two-axis Standards/Spec review over the readiness diff and close all blocking findings before any paid smoke.

## Out of Scope

- Executing or closing ticket 035 or 036, choosing `high` versus `max`, changing the 32768 completion limit, or promoting a Workshop rendering variant.
- Selecting or executing the final 12-case Canary, running 24 comparison arms, performing a failure rerun without a new approval, opening the Scale Gate, or executing the terminal wave.
- Adding Responses API, Anthropic-format transport, OpenAI SDK, `curl`, provider-native tools, web search, multi-provider support, alternate endpoint/model fallback, or runtime-configurable network controls.
- Changing generation/reflection prompts, action protocol, retrieval ranking, corpus semantics, Workshop semantics, idea schema, Declared Grounding, Evidence Chain schemas, failure taxonomy, resume semantics, evaluation rubric, or sanitized export policy.
- Adding a fourth dependency-injection seam, a background service, concurrent model calls, a daemon, a queue, or an external secret manager.
- Sending credentials, prompts, responses, reasoning, ideas, Target Paper identity, provider response IDs, host identity, or absolute paths to Git or sanitized evidence.
- BFTS, code experiments, plotting, LaTeX writing, automated review, paper generation, deployment, publishing, merging to `main`, or any other downstream workflow.

## Further Notes

- Robert approved this specification direction on 2026-09-04 and explicitly requested specification and ticket publication before implementation. No runtime code or paid request is authorized by document publication alone.
- The current DeepSeek base URL was reachable without credentials during planning and returned HTTP 401 as expected. This proves network reachability only; credential validity, account balance, regional/account access, real response shape, latency, usage, and billing remain smoke evidence.
- The current official Chinese pricing page matches the repository's registered CNY table: V4 Pro peak rates are 0.30 CNY cache-hit input, 9.0 CNY cache-miss input, and 27.0 CNY output per million tokens; off-peak is half. Prices must be rechecked immediately before the paid smoke because the provider reserves the right to change them.
- The process environment inspected during planning did not contain `DEEPSEEK_API_KEY`. Robert should configure it locally only after readiness implementation and review; its value must never be pasted into a command transcript or conversation.
- The approved smoke case already has hash-consistent Approved Workshop and Approved Target Reference Corpus artifacts. Their private identities and paths remain outside tracked tickets and sanitized reports.
- The independently mergeable sequence is: publish this spec and two tickets; implement and validate live-execution readiness without network; commit a clean tree; obtain credential and per-run cost approval; execute and evaluate one smoke; only then prepare the fixed Canary selection and work ticket 035.
