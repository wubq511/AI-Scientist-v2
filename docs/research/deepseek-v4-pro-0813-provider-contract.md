# DeepSeek-V4-Pro-0813 Provider Contract Research

Research date: 2026-08-28 (Asia/Shanghai)

Scope: official DeepSeek API/Open Platform documentation and first-party DeepSeek policies only. No paid or authenticated API request was made. Consequently, this note distinguishes documented facts from facts that still require an account-level smoke test or a provider decision.

## Conclusion

`DeepSeek-V4-Pro-0813` is the **current model version name**, not the model identifier accepted by DeepSeek's own API. On 2026-08-28, the official DeepSeek API maps the request model ID `deepseek-v4-pro` to model version `DeepSeek-V4-Pro-0813`. Its canonical OpenAI-compatible Chat Completions base URL is `https://api.deepseek.com`, and the HTTP request uses `POST /chat/completions` with `Authorization: Bearer <DeepSeek API key>`. [DeepSeek first API call](https://api-docs.deepseek.com/) and [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/).

This is not yet a fully reproducible **checkpoint-pinned** contract. DeepSeek documents `deepseek-v4-pro` as an alias for the latest version and says the calling method/model name remains unchanged when the served version is updated. It does not document a direct-API request ID such as `deepseek-v4-pro-0813`. The August 13 change log confirms that the GA update was rolled out behind the unchanged alias. [DeepSeek V4 Pro update](https://api-docs.deepseek.com/updates/#deepseek-v4-pro-update).

Therefore the implementable contract is provisional:

- If the intended provider is DeepSeek's own Open Platform and a floating alias is acceptable, use the Chat Completions contract below.
- If the recruitment requirement means the exact `0813` checkpoint must remain pinned even after DeepSeek changes the alias, Robert or the recruiter must identify/approve a provider that exposes a versioned model ID. That provider would need a separate contract for endpoint, pricing, errors, and data handling.
- Do not guess that `DeepSeek-V4-Pro-0813` or `deepseek-v4-pro-0813` is accepted by `api.deepseek.com`; neither appears in the official direct Chat Completions request schema. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

## Provider and endpoint

| Contract item | Confirmed value | Confidence / boundary |
| --- | --- | --- |
| Provider | DeepSeek Open Platform, operated by Hangzhou DeepSeek Artificial Intelligence Co., Ltd. | The operator is named in the current [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html). The recruitment brief itself does not name a provider, so using DeepSeek direct remains a decision, not a fact supplied by the task. |
| API style | OpenAI-compatible Chat Completions and Responses API | DeepSeek says its API is compatible with OpenAI and can be used through the OpenAI SDK by changing configuration; its detailed compatibility tables show that this is not complete OpenAI parameter parity. [First API call](https://api-docs.deepseek.com/) and [Responses API guide](https://api-docs.deepseek.com/guides/responses_api/). |
| Base URL | `https://api.deepseek.com` | Canonical quick-start value. The SDK constructs `/chat/completions` or `/responses`; direct requests are `POST https://api.deepseek.com/chat/completions` and `POST https://api.deepseek.com/responses`. [First API call](https://api-docs.deepseek.com/) and [Responses API reference](https://api-docs.deepseek.com/api/create-response/). |
| Authentication | DeepSeek account API key, sent as `Authorization: Bearer $DEEPSEEK_API_KEY` | API keys are created through the DeepSeek Platform and must not be exposed in client-side code. [First API call](https://api-docs.deepseek.com/) and [Open Platform Terms, section 2.2](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html). |
| Request model ID | `deepseek-v4-pro` | This is the only Pro ID listed in the direct Chat Completions schema. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/). |
| Served version on research date | `DeepSeek-V4-Pro-0813` | Official mapping as of this note. [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/). |
| Version-pinned direct ID | **unknown / not documented** | The official update explicitly retains `deepseek-v4-pro` for the latest version. [Change log](https://api-docs.deepseek.com/updates/#deepseek-v4-pro-update). |

Both a base URL with and without `/v1` appear in DeepSeek-authored integration guides. The canonical general-purpose quick start and OpenAI SDK example use `https://api.deepseek.com` without `/v1`; the adapter should follow that canonical form rather than relying on an integration-specific variant. [First API call](https://api-docs.deepseek.com/).

## Recommended request contract

Use non-streaming Chat Completions for the first adapter version because its V4 Pro contract is fully documented, matches the existing adapter style, and yields one auditable response object. The current official Responses API also supports V4 Pro, but adopting it is optional and would be a wider interface change. This recommendation does not require or authorize a live model call. [Responses API guide](https://api-docs.deepseek.com/guides/responses_api/).

```jsonc
{
  "model": "deepseek-v4-pro",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high",
  "max_tokens": "<explicit integer fixed by the later run policy>",
  "response_format": {"type": "json_object"},
  "stream": false,
  "user_id": "<opaque-run-scoped-id>"
}
```

The documented message roles are `system`, `user`, `assistant`, and `tool`; `messages` must contain at least one entry. The Pro model is text-only in this API contract: image input is documented for the separate `deepseek-v4-flash-vision-exp` model. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

`/chat/completions` is stateless at the conversation level: the client must supply all conversation history on every turn. This does **not** mean DeepSeek does not retain or cache request data; conversation state, context caching, and policy retention are separate concerns. [Multi-round Conversation](https://api-docs.deepseek.com/guides/multi_round_chat/) and [Context Caching](https://api-docs.deepseek.com/guides/kv_cache/).

`user_id` is optional, must match `[a-zA-Z0-9\-_]+`, and may be at most 512 characters. DeepSeek states that it provides content-safety, KV-cache, and scheduling isolation. For this project, it should be an opaque, non-personal, unique Ideation Run identifier so different runs do not share the default cache-isolation bucket. This is a project implication derived from DeepSeek's isolation contract, not a claim that cache reuse itself changes model semantics. [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).

When using the OpenAI SDK, both `thinking` and `user_id` are DeepSeek extensions and belong under `extra_body`; the JSON above shows the raw HTTP body shape. [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) and [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).

## Response contract

A successful non-streaming call returns an OpenAI-style `chat.completion` object. The evidence chain should retain at least:

- top-level `id`, `created`, `model`, and `system_fingerprint`;
- `choices[0].message.content`;
- `choices[0].message.reasoning_content` when thinking is enabled;
- `choices[0].message.tool_calls` when present;
- `choices[0].finish_reason`;
- `usage.prompt_tokens`, `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, `completion_tokens`, `completion_tokens_details.reasoning_tokens`, and `total_tokens`.

These fields and their semantics are defined by the official [Chat Completions API response schema](https://api-docs.deepseek.com/api/create-chat-completion/). The documented `finish_reason` values are `stop`, `length`, `content_filter`, `tool_calls`, and `insufficient_system_resource`. A final-idea response is complete only when its expected terminal reason and local schema validation both pass; `length`, `content_filter`, and `insufficient_system_resource` must not be treated as valid final JSON merely because the HTTP status was 200.

`system_fingerprint` represents the backend configuration, but DeepSeek does not state that it uniquely proves the dated checkpoint. Logging it improves traceability but does not solve the floating-alias problem. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

For streaming, the API emits data-only SSE chunks and terminates with `data: [DONE]`. The project does not need streaming for its initial auditable adapter; if it is later enabled, raw chunk order, the terminal chunk, and final usage must be preserved. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

## Thinking and sampling controls

| Control | Documented behavior |
| --- | --- |
| `thinking.type` | `enabled` or `disabled`; default is `enabled`. With the OpenAI SDK it must be sent via `extra_body={"thinking": {"type": "enabled"}}`. |
| `reasoning_effort` | Native values are `low`, `high`, and `max`; default is `high`. Compatibility inputs `medium` and `xhigh` are mapped to `high`. |
| `temperature` | Range `0` to `2`, default `1`, but it has **no effect in thinking mode** and is silently accepted. |
| `top_p` | Range up to `1`, default `1`, but it has **no effect in thinking mode**. |
| `presence_penalty`, `frequency_penalty` | Deprecated and ignored. |
| `max_tokens` | Limits generated completion tokens; input plus generated tokens must fit the context window. Official model limits are 1M context and a maximum 384K output. The Chat Completions schema does not state a default, so the adapter must set it explicitly. |
| `stop` | One string or up to 16 stop sequences. |
| `seed` | **unknown / not documented** in the official Chat Completions request schema. It must not be presented as supported or used as a reproducibility guarantee. |

The thinking-mode behavior is documented in [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/); the general fields and deprecated penalties are documented in [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/); context/output limits are documented in [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/).

Because thinking mode ignores the sampling controls and no seed contract is documented, API reruns cannot be assumed deterministic. Reproducibility must come from immutable input/configuration/evidence logs and fixture-based replay tests, not from claiming identical generation.

## Structured output

Chat Completions supports `response_format: {"type": "json_object"}`, which promises syntactically valid JSON, not conformance to an application JSON Schema. The prompt must explicitly ask for JSON and should include the expected shape. DeepSeek warns that otherwise the model can emit whitespace until the token limit; even with JSON mode, content may occasionally be empty, and output can be truncated when `finish_reason` is `length`. [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) and [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

Consequences for the final idea contract:

- always perform local JSON parsing and schema validation;
- reject empty content, truncated output, extra/missing fields, and semantic validation failures;
- record every failed attempt separately rather than overwriting it;
- do not claim Chat Completions `json_object` provides JSON Schema enforcement.

The current Responses API supports `deepseek-v4-pro` at `POST /responses`. Its `text.format` accepts `text`, `json_object`, or `json_schema`; for the last option, `name` and `schema` are required and the output is documented to conform to that JSON Schema. It remains stateless (`previous_response_id` and `conversation` are unsupported), and `store` is unsupported/always reported as false. Unsupported Responses parameters are silently ignored, so the adapter must send an allowlisted request rather than assuming OpenAI parity. [Responses API reference](https://api-docs.deepseek.com/api/create-response/) and [Responses API guide](https://api-docs.deepseek.com/guides/responses_api/).

Responses API JSON Schema could reduce malformed final-output attempts, but local schema validation remains mandatory. Because the existing project already uses a Chat Completions-style model boundary and Chat JSON mode plus local validation is sufficient for the approved compatibility baseline, choosing Responses API would be a separate design decision rather than a hidden adapter change.

## Tool use

Chat Completions supports function tools only, with at most 128 functions. `tool_choice` can be `none`, `auto`, `required`, or a named function. The model returns tool arguments as a JSON string, and the official schema warns that arguments may be invalid JSON or contain hallucinated parameters; the client must validate before executing anything. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/).

There is a narrower compatibility conflict for thinking mode: DeepSeek's official Oh My Pi integration guide says V4 thinking mode rejects `tool_choice`, although the generic Chat Completions schema documents the field. The safe initial contract is to omit `tool_choice` while thinking is enabled unless a later approved smoke test proves the intended combination. [Using DeepSeek with Oh My Pi](https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/).

Thinking mode supports tool calls. Whenever a request carries `tools`, all earlier assistant `reasoning_content` must be replayed in subsequent requests, including turns on which no tool was called; omitting it produces HTTP 400. [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/).

Strict tool-argument JSON Schema is Beta-only: use `https://api.deepseek.com/beta` and set `strict: true` on every function. The supported schema subset is documented, and invalid/unsupported schemas are rejected. This beta feature is not needed to enforce the final idea JSON and should not silently become a production dependency. [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/).

The Responses API additionally exposes a provider-executed `web_search` tool. It must not be included in this project's request allowlist: using it would bypass the Target Reference Corpus and violate the Scoped Literature Retriever boundary. Only the project's target-scoped local retrieval function may be exposed to the model. [Responses API guide](https://api-docs.deepseek.com/guides/responses_api/).

## Limits, keep-alive, and pricing

The published V4 Pro concurrency limit is 500 in-flight requests per account, independent of how many API keys the account uses; exceeding it returns 429. DeepSeek publishes no V4 Pro RPM or TPM quota in this document. [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).

While waiting, a non-streaming HTTP response may contain empty keep-alive lines; a streaming response may contain SSE `: keep-alive` comments. If inference has not begun after 10 minutes, the server closes the connection. Parsers and timeouts must account for this behavior. [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).

Current official DeepSeek-direct prices as of 2026-08-28 are USD per 1M tokens:

| V4 Pro billing item | Off-peak | Peak |
| --- | ---: | ---: |
| Input, context-cache hit | $0.022 | $0.044 |
| Input, context-cache miss | $0.66 | $1.32 |
| Output, including reasoning tokens in completion usage | $1.98 | $3.96 |

Peak windows are Monday-Friday 01:00-04:00 UTC and 06:00-10:00 UTC; all other times are off-peak. DeepSeek reserves the right to change prices, so an Ideation Run manifest must snapshot the price page/date rather than treating these numbers as permanent. [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/).

Context caching on disk is automatic. Cache hits are best-effort; unused cache entries are usually cleared after a few hours to a few days. Responses expose hit/miss token counts. [Context Caching](https://api-docs.deepseek.com/guides/kv_cache/).

## Failure semantics

DeepSeek documents these HTTP statuses:

| Status | Provider meaning | Adapter disposition implied by the contract |
| --- | --- | --- |
| 400 | Invalid request format | Terminal configuration/request failure; preserve provider body. A missing tool-turn `reasoning_content` can also cause 400. |
| 401 | Authentication failure | Terminal until credential configuration changes. Never log the key. |
| 402 | Insufficient account balance | Terminal until the account is funded. Do not silently switch providers. |
| 422 | Invalid parameters | Terminal contract mismatch; preserve parameter names but redact sensitive content. |
| 429 | Rate/concurrency limit | Retriable with bounded backoff; no official `Retry-After` contract is documented. |
| 500 | DeepSeek server error | Official guidance is to retry after a brief wait. |
| 503 | Server overloaded | Official guidance is to retry after a brief wait. |

The provider meanings and official suggestions come from [Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/). The bounded-retry/terminal classification is an adapter design implication. DeepSeek does not document idempotency keys, a standard error-body schema, a request-ID header, retry ceilings, billing behavior after a disconnected/ambiguous attempt, or an SLA on these pages; each is **unknown**. Therefore every retry must be a separately logged attempt and must never overwrite the ambiguous prior attempt.

Provider-side failures also arrive inside successful response objects through `finish_reason`; JSON-mode empty content is a documented failure case. HTTP 200 is not sufficient validation. [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) and [JSON Output](https://api-docs.deepseek.com/guides/json_mode/).

## Data retention and confidentiality

The current Chinese privacy policy explicitly says it applies to DeepSeek APIs. It states that DeepSeek may collect prompts/inputs and service logs, and the English policy says personal data may be used to improve/train models and technologies. It offers a right/settings choice to opt out of training, but the official API documentation does not state whether that account setting applies to API traffic or provide an API-specific zero-retention/no-training switch. [DeepSeek Privacy Policy scope (Chinese)](https://cdn.deepseek.com/policies/zh-CN/deepseek-privacy-policy.html) and [DeepSeek Privacy Policy (English)](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html).

The privacy policy gives no fixed API prompt/output retention duration. It says personal data, including input data, may be kept for as long as the account exists when needed to provide services, and longer for legal, contractual, security, business, or claims purposes. It says collected personal data is processed and stored in the People's Republic of China. [DeepSeek Privacy Policy: retention and storage](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html#how-long-do-we-keep-your-personal-data).

Separately, the inference service automatically persists disk KV-cache units and usually clears unused ones within hours to days. `user_id` provides KV-cache isolation, but that is not a promise of zero data retention and does not override the privacy policy. [Context Caching](https://api-docs.deepseek.com/guides/kv_cache/) and [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).

Until Robert or the recruiter confirms that the source papers, workshop files, prompts, and outputs may be sent under these terms, the adapter must not send confidential, unpublished, personal, or interview-private content to the official endpoint. Public-paper text still requires the project to decide whether provider training/retention is acceptable.

## Unknowns that block a final provider decision

The following are not established by current official documentation and must not be guessed:

1. Whether the recruitment requirement allows the floating direct alias `deepseek-v4-pro`, or demands a permanently pinned `0813` checkpoint.
2. Which provider/account/endpoint the recruiter expects; the model version name alone does not identify the inference provider.
3. Whether the DeepSeek account's data-training opt-out applies to API traffic, whether it is enabled, and whether an enterprise zero-retention agreement exists.
4. A supported `seed`, deterministic-generation guarantee, idempotency key, request-ID header, `Retry-After` header, RPM/TPM quota, latency SLA, or API-specific fixed retention duration.
5. Whether `system_fingerprint` is stable or unique enough to prove a dated model checkpoint.
6. The actual account concurrency allocation, region eligibility, balance, and credential validity; these require account access and a separately approved smoke test.

## Information required from Robert or the recruiter

- Expected provider and base URL, if already prescribed.
- Whether exact checkpoint pinning is mandatory or the direct `deepseek-v4-pro` latest-version alias is acceptable.
- A DeepSeek API key supplied only through a local secret/environment mechanism, never in chat, source, logs, or commits.
- Confirmation that the account may be charged and the allowed canary budget.
- Confirmation of the account's training opt-out / data-retention setting or any enterprise data-processing terms.
- Confirmation that the materials sent in prompts may be processed and stored in the People's Republic of China under DeepSeek's policy.
- Approval of the initial mode (`thinking=enabled`, explicit `reasoning_effort`, explicit `max_tokens`, Chat Completions JSON mode) after the provider and confidentiality questions are settled.

## Minimal no-cost validation before any paid Ideation Run

Once credentials and the provider decision exist, a later implementation ticket should perform a narrowly scoped canary rather than a production run:

1. verify the documented model ID through the provider's model-list/account surface if available;
2. send one non-sensitive minimal request with an explicit spend ceiling;
3. capture response `model`, `system_fingerprint`, finish reason, usage, cache fields, and raw error semantics;
4. verify JSON mode with local schema rejection of empty/truncated output;
5. verify a mocked retry path without deliberately causing paid server errors;
6. record that no BFTS, experiment, plotting, write-up, or review stage was imported or invoked.

This validation is intentionally not performed in this research ticket.
