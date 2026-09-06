# DeepSeek V4 Pro：Chat Completions 与 Responses API 选择研究

研究日期：2026-08-29（Asia/Shanghai）

## 结论

截至本次核对，DeepSeek 官方当前文档已经明确支持用 `deepseek-v4-pro` 调用 Responses API。此前“Responses API 只支持 `deepseek-v4-flash`、尚不支持 Pro”的判断已经过时，不能继续作为设计依据。

当前直接证据有四处，且彼此一致：

- Responses API endpoint reference 把 `deepseek-v4-pro` 列为 `POST /responses` 的合法 `model` 值：[Responses API reference](https://api-docs.deepseek.com/api/create-response/)。
- Responses API compatibility table 把 `deepseek-v4-pro` 列为支持模型：[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)。
- Models & Pricing 的功能矩阵给 V4 Pro 的 Responses API 标记为支持：[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。
- 2026-08-13 V4 Pro GA changelog 同时宣布 V4 Pro API 更新和原生 OpenAI Responses API 支持：[Change Log](https://api-docs.deepseek.com/updates/#deepseek-v4-pro-update)。

不过，**“Pro 支持 Responses API”不等于“本项目应当改用 Responses API”**。从本项目要解决的问题出发，第一版 DeepSeek adapter 应使用 **non-streaming Chat Completions**，但 transport 必须封装在 DeepSeek 专属边界内，不能把 ChatCompletion SDK object 泄漏给 controller。

推荐理由不是“旧代码已经这么写”，而是：

1. 本项目当前需要保留的是原有 `system + messages`、action、reflection、finalization 和 client-owned history 语义；Chat Completions 与这条语义链直接同构。
2. 两种 API 都是 stateless，都要求客户端重放完整历史；DeepSeek Responses 不支持 `previous_response_id`、`conversation` 或 provider-side `store`，因此本项目得不到 OpenAI Responses 常见的服务端状态优势。[Responses API reference](https://api-docs.deepseek.com/api/create-response/)；[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)
3. 当前 baseline 使用文本 `ACTION / ARGUMENTS` envelope，而不是 native function tool 或纯 JSON Schema envelope。Responses 的 `json_schema` 是真实能力增益，但若现在用它重塑 action/finalization 协议，就已经超出“保持兼容 baseline”的 transport 选择。
4. Chat Completions 已提供本项目必需的完整诊断：response ID、实际 model、`system_fingerprint`、reasoning、tool calls、`finish_reason`、cache hit/miss、reasoning token 和 total usage。[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
5. Responses API 会静默忽略多种不支持的参数，且把 `developer` message 当作 `user`；它需要额外的 request allowlist 和 role-mapping 防线。本项目并不需要它支持的 provider `web_search`，反而必须保证该工具永远不会进入请求。[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)

这个结论只选择第一版 transport，不否定以后迁移。若后续把 action protocol 明确版本化为 schema-driven envelope，并通过同输入的 account-level canary 证明 Responses `json_schema` 能显著减少 malformed/repair attempts，而不破坏 idea 质量、tool loop、usage 或诊断，再迁移是合理的。

本研究没有调用 DeepSeek 模型、没有读取 credential、没有发送 authenticated request，也没有产生费用。因此，文档支持状态是 confirmed；实际账号、SDK、组合参数和质量/延迟等运行表现仍按 unknown 处理。

## 研究边界与判定标签

外部资料只使用 DeepSeek 官方 API docs、reference、changelog 和 first-party guides。本地行为依据当前仓库源码与已批准 Wayfinder contract；没有使用博客、论坛、聚合文档或第三方 benchmark 解读。

本文使用四类标签：

- **Confirmed fact**：当前 DeepSeek 官方文档或本地源码直接陈述/展示。
- **Inference**：由 confirmed facts 与本项目约束推出的工程判断。
- **Documentation conflict**：不同时间或不同官方页面给出不一致契约。
- **Unknown / smoke test required**：文档不能证明，必须由后续获批的 account-level smoke test 或付费 comparative canary 验证。

## 先定义问题，而不是先选 API

本项目不是在建设通用 Agent SDK，也不需要保留旧 provider。真正的问题是：

> 如何让 DeepSeek V4 Pro 在冻结的 ideation 行为边界内，可靠完成 action、target-scoped literature retrieval 后的 reflection 与 finalization，同时让每次请求可验证、可审计、可复现，并在任何协议、schema、metadata 或 provider failure 上 fail closed？

因此 transport 的通过条件是：

1. 只允许 DeepSeek direct、`https://api.deepseek.com`、`deepseek-v4-pro`。
2. 支持 non-streaming、thinking enabled、显式 reasoning effort 和 completion limit。
3. 不改变原 action/reflection/finalization baseline，除非另开版本化决策并比较验证。
4. 模型只能访问 controller 管理的 Scoped Literature Retriever；不得启用 provider `web_search`。
5. adapter 必须返回完整 response、usage、stop/failure diagnostics，不能只返回 `(content, history)`。
6. structured output 只能作为 provider 辅助；本地 JSON parse、application schema 和 semantic validation 始终是最终 authority。
7. unsupported parameters、截断、空 content、内容过滤、schema error、认证/余额/配置错误必须 fail closed。
8. 在达到同等 correctness threshold 的方案中，选实现和审计路径更简单的方案。

## 支持状态复核

### Confirmed fact：当前 Pro 支持 Responses API

当前 `POST /responses` request schema 的合法 model values 包含：

- `deepseek-v4-flash`
- `deepseek-v4-pro`
- `deepseek-v4-flash-vision-exp`

来源：[Responses API reference](https://api-docs.deepseek.com/api/create-response/)。Responses guide 的 model compatibility table 和 Models & Pricing 的 feature matrix 给出同样结论：[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)；[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)。

2026-08-13 changelog 的 V4 Pro GA 条目宣布原生 Responses API 支持；这也解释了为什么更早的文档快照可能仍写着“计划后续支持”。[Change Log](https://api-docs.deepseek.com/updates/#deepseek-v4-pro-update)

### Documentation conflict：旧索引快照与当前 live reference

本次检索仍能看到较旧的搜索索引摘要写着“Responses API currently only supports `deepseek-v4-flash`”并计划在 2026 年 8 月初加入 Pro。但打开同一个官方 reference/guide 的当前 live 页面后，合法 model 和 compatibility table 已包含 `deepseek-v4-pro`。

设计判定应以当前 endpoint schema、current compatibility table、current pricing feature matrix 和 dated GA changelog 的交叉证据为准，而不是旧搜索摘要。当前 live 官方页面之间没有发现 Pro 支持状态冲突。

### Unknown：账号级实际可调用性

因为没有进行 authenticated call，以下仍未被本研究实证：

- 当前目标 DeepSeek account 是否实际可用 `deepseek-v4-pro` + `/responses`；
- 账号余额、地区、并发与权限是否允许请求；
- 使用中的 OpenAI Python SDK 是否完整序列化 DeepSeek 所需的 Responses 字段；DeepSeek docs 没有给出最低 SDK version；
- `deepseek-v4-pro` + thinking + `text.format=json_schema` 的组合是否与 schema 单项文档完全一致；
- 两种 endpoint 对相同模型输入的输出质量、latency、token usage 和 billing 是否等价。

这些 unknown 不支持再次声称“不支持”，但在正式切换 transport 前需要最小 account-level smoke test。

## Alternatives

### A. Non-streaming Chat Completions

请求入口是 `POST /chat/completions`，使用 `messages`、`thinking`、`reasoning_effort`、`max_tokens` 和 `stream=false`。[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)

本项目第一版采用这一方案。

### B. Non-streaming Responses API

请求入口是 `POST /responses`，使用 `instructions` / `input`、`reasoning.effort`、`max_output_tokens`、`text.format` 和 `stream=false`。[Responses API reference](https://api-docs.deepseek.com/api/create-response/)

它是可行 transport，但当前不是默认方案。

### C. 同时支持两个 endpoint 并运行时 fallback

拒绝。它会让相同 run 的协议、response shape、stop semantics 和 evidence schema 分叉；当一个 endpoint 失败时静默改用另一个还会隐藏真实故障。项目只用 DeepSeek，不需要以双 transport 换取 provider portability。

若未来迁移，应进行版本化的一次性切换，并保留旧 evidence reader；不得在单次 attempt 内自动 fallback。

### D. 先抽象所有旧 provider 的统一 adapter

拒绝。Robert 已明确后续 runtime 只需要 DeepSeek V4 Pro。为不再使用的 provider 设计最低公分母接口不会增加当前正确性，只会扩大变更面，并可能抹掉 DeepSeek 特有的 reasoning、cache 与 failure fields。

## 按项目指标比较

| 指标 | Chat Completions | Responses API | 本项目判定 |
| --- | --- | --- | --- |
| V4 Pro 当前官方支持 | **Confirmed** | **Confirmed** | 平手；不能再用“不支持 Pro”排除 Responses。 |
| 现有 conversation 语义 | `system + messages`，与本地 `msg_history` 同构 | `instructions + input items`，需要 message/item 映射 | Chat 更直接。 |
| 原 action/reflection/finalization baseline | 可原样发送文本 prompt 并读取单个 assistant content | 也可发送文本，但 item normalization 是额外层；使用 JSON Schema 会改变现有 envelope | Chat 风险更低。 |
| Stateless / resume | 客户端每轮发送完整 history | 同样要求完整 input；`previous_response_id`、`conversation` 不支持，`store=false` | 平手；Responses 没有状态优势。 |
| Thinking control | `thinking.type` + `reasoning_effort` | `reasoning.effort` 同时控制 toggle/effort | 都满足。 |
| Reasoning 输出 | `message.reasoning_content` | 独立 `reasoning` output item | Responses 的类型更清晰；两者都可无损保留。 |
| Non-streaming | 返回单个 ChatCompletion object | 返回单个 Response object | 都满足。 |
| 截断/终止诊断 | `finish_reason`: `stop`、`length`、`content_filter`、`tool_calls`、`insufficient_system_resource` | top-level `status` + `incomplete_details.reason`: `max_output_tokens` / `content_filter` + `error` | Responses 的顶层状态更统一；Chat 的 stop reason 和 resource diagnosis 更具体。 |
| Backend trace | `system_fingerprint` 有正式字段 | 当前 DeepSeek response schema 未列出 `system_fingerprint` | Chat 更利于当前审计，但 fingerprint 也不是 checkpoint proof。 |
| Usage / cache | 显式 prompt cache hit 与 miss、reasoning tokens、total | cached input tokens、reasoning output tokens、total；miss 可由 input-cached 推导但不是独立字段 | 两者都够成本核算；Chat 更完整。 |
| JSON object | 支持 | 支持 | 平手。 |
| JSON Schema | Chat response format 只列 `text` / `json_object` | `text.format` 支持 `json_schema` | Responses 明显更强，但本地 validation 仍不可省。 |
| Local retriever | Chat tools 只支持 function；也可继续用当前文本 action protocol | function + provider `web_search` | 都能用本地 retriever；Responses 必须额外禁止 `web_search`。 |
| Tool budget 可控性 | controller 自行控制；native tool choice 有明确字段 | `max_tool_calls` 被忽略，parallel tool calling 永远启用 | 保留现有 controller loop 时 Chat 更简单。 |
| Unsupported 参数 | thinking 下 sampling 参数会被接受但无效；deprecated penalties 无效 | 多项 Responses 参数会被静默忽略 | 两者都要 allowlist；Responses 的误配置面更大。 |
| Role mapping | `system/user/assistant/tool` 直接映射 | `developer` 被 DeepSeek 当作 `user`；`instructions` 才是 system-level | 当前项目没有 developer role；仍需显式映射测试。 |
| SDK/实现变更 | 当前代码已有 `client.chat.completions.create` 路径 | 需要 `client.responses.create`、item parser 和新的 fixture | Chat 更小。 |
| 长期 provider portability | OpenAI-compatible | OpenAI Responses-compatible | 项目已选择 DeepSeek-only，此项不应主导。 |

事实来源：[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)、[Responses API reference](https://api-docs.deepseek.com/api/create-response/)、[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)、[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。项目语义来源：`ai_scientist/perform_ideation_temp_free.py` 与 `ai_scientist/llm.py`。

## 两种 transport 的最小合法形状

以下只用于说明字段映射，不是可直接执行的 production payload，也不授权调用。

### Chat Completions

```jsonc
{
  "model": "deepseek-v4-pro",
  "messages": [
    {"role": "system", "content": "<approved system prompt>"},
    {"role": "user", "content": "<current ideation prompt>"}
  ],
  "thinking": {"type": "enabled"},
  "reasoning_effort": "<high-or-max-from-later-canary>",
  "max_tokens": "<explicit approved limit>",
  "stream": false,
  "user_id": "<opaque run-scoped id>"
}
```

DeepSeek 官方说明：用 OpenAI SDK 时，`thinking` 和 `user_id` 是 DeepSeek extension，需要按官方示例经 `extra_body` 传入。[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)；[Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)

保留兼容 baseline 时，不应默认给每一轮添加 `response_format=json_object`：当前 controller 期待文本 `ACTION:` / `ARGUMENTS:` envelope。Chat JSON mode 可以作为以后版本化 structured protocol 的 adapter capability，但不是悄悄改变 controller grammar 的理由。

### Responses API

```jsonc
{
  "model": "deepseek-v4-pro",
  "instructions": "<approved system prompt>",
  "input": [
    {"role": "user", "content": "<current ideation prompt>"}
  ],
  "reasoning": {"effort": "<high-or-max-from-later-canary>"},
  "max_output_tokens": "<explicit approved limit>",
  "text": {"format": {"type": "text"}},
  "stream": false,
  "user": "<opaque run-scoped id>"
}
```

不得加入 `web_search`、`web_search_2025_08_26`、`previous_response_id`、`conversation`、`store`、`background`、`metadata`、`prompt` 或其他不在本项目 allowlist 中的字段。DeepSeek 声明多项 unsupported Responses parameters 会被静默忽略，因此“HTTP 200”不能证明请求配置按预期生效。[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)

## Structured output 的真实边界

### Confirmed fact

Chat Completions 的 `response_format` 当前只列出：

- `text`
- `json_object`

DeepSeek 警告 JSON mode 仍可能返回 empty content；prompt 必须明确包含 JSON 要求，并应设置合理 `max_tokens` 以避免截断。[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)；[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)

Responses API 的 `text.format` 还支持：

- `json_schema`，包含 `name` 和 `schema`

官方把它描述为符合所给 JSON Schema 的 structured output。[Responses API reference](https://api-docs.deepseek.com/api/create-response/)

### Inference

Responses `json_schema` 最可能带来的实际价值，是减少 syntax/schema repair attempt 和无效付费输出，而不是替代本地 validation。它不能验证本项目的语义 invariant，例如：

- 必须完成至少一次 non-empty target-scoped retrieval 才能 finalize；
- retrieved paper 必须属于当前 Target Reference Corpus；
- idea 与先前 ideas 的隔离和 novelty；
- finalization 是否发生在允许的 control-flow state；
- 文本字段是否真的有研究意义或忠实使用 related work。

### 对当前选择的影响

当前 action protocol 不是纯 idea schema：每一轮模型先选择 literature search 或 finalization。若立即强制 `json_schema`，必须同时设计 action union、arguments schema、controller parser 和 migration fixtures；这是 control protocol 变更，不是 transport adapter 的免费收益。

因此第一版 Chat adapter 可以保留 text baseline，并在 typed request contract 中预留受控的 `text` / `json_object` mode。是否把整个 action envelope 改成 Responses `json_schema`，应是单独的 prototype/comparative validation，而不是这张 adapter ticket 的隐式决定。

## Thinking 与多轮历史

### Confirmed fact

两种 API 都默认开启 thinking；请求 effort 最终映射为 `low`、`high` 或 `max`。`medium` 和 `xhigh` 都映射到 `high`。[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)

Chat Completions 在 thinking mode 返回 `message.reasoning_content`。若 request 携带 `tools`，官方要求后续请求完整回传此前所有 `reasoning_content`；遗漏会得到 HTTP 400。若 request 不携带 `tools`，历史 reasoning 即使回传也会被忽略。[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)

Responses API 把 reasoning 和 message 作为独立 output items，并支持把 `reasoning` item 放回后续 input；它仍要求客户端重放完整 conversation，因为 `previous_response_id` / `conversation` 不支持。[Responses API reference](https://api-docs.deepseek.com/api/create-response/)；[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)

### Inference

当前 baseline 用文本 action 让 controller 执行 retriever，并没有发送 provider-native `tools`。因此 Chat 对 tool-call reasoning replay 的特殊复杂度在第一版不会触发；adapter 仍应无损保留 reasoning，供 evidence 和未来版本化 tool protocol 使用。

如果未来采用 native tools，Responses 的 item graph 可能比 Chat message fields 更清晰，但 DeepSeek Responses 的 `max_tool_calls` 被忽略、parallel tool calling 永远启用。项目必须由 controller 独立执行 call budget、schema validation 和 target-scope checks，不能把控制权交给 provider。[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)

## Observability 与 fail-closed

### Chat Completions 必须保留

- top-level `id`、`created`、`model`、`system_fingerprint`、`object`；
- `choices[0].message.content`、`reasoning_content`、`tool_calls`；
- `choices[0].finish_reason`；
- `usage.prompt_tokens`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、`completion_tokens`、`completion_tokens_details.reasoning_tokens`、`total_tokens`；
- 可序列化的原始 provider response。

来源：[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

### Responses API 必须保留

- top-level `id`、`created_at`、`model`、`status`、`error`、`incomplete_details`；
- 所有 ordered `output` items，包括 `reasoning`、`message`、`function_call`；
- item-level `id`、`status`、`call_id`、arguments；
- `usage.input_tokens`、`input_tokens_details.cached_tokens`、`output_tokens`、`output_tokens_details.reasoning_tokens`、`total_tokens`；
- 可序列化的原始 provider response。

来源：[Responses API reference](https://api-docs.deepseek.com/api/create-response/)。

### 共同 fail-closed 规则

- HTTP 200 不是成功判据；必须同时通过 transport disposition、expected terminal state、non-empty content、JSON parsing、local application schema 和 semantic validation。
- 不支持的 model、base URL、request field 或 mode 在发送前本地拒绝。
- adapter 不得静默切换 endpoint、model、provider、thinking mode 或 structured mode。
- 每次 retry 是独立 attempt，保留先前 raw evidence；不得覆盖 ambiguous attempt。
- 401、402、400、422 默认 terminal；429、500、503 仅可按后续批准的 bounded retry policy 重试。官方 error meanings：[Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)。
- credential 不进入 request evidence、异常文本、日志或 raw response serialization。

## Failure cases

### Chat Completions

1. `finish_reason=length`：reasoning 或 visible JSON 被截断；terminal validation failure。
2. `finish_reason=content_filter`：内容被省略；terminal attempt failure。
3. `finish_reason=insufficient_system_resource`：provider inference 未正常完成；可否重试由 bounded policy 决定，不能当成功。
4. `finish_reason=tool_calls` 但当前 baseline 不允许 native tool calls：protocol violation。
5. empty content：DeepSeek JSON mode 已明确说明会偶发；必须拒绝。[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
6. malformed action envelope、invalid arguments JSON、idea schema failure：controller/local validator failure。
7. request 携带 native `tools` 却遗漏历史 `reasoning_content`：官方说明会返回 400。[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)

### Responses API

1. `status=incomplete` + `incomplete_details.reason=max_output_tokens`：截断；terminal validation failure。
2. `status=incomplete` + `content_filter` 或 `status=failed`：不得读取残留 message 当成功。
3. 只读取 `output_text` 而丢失 reasoning/function items：evidence 不完整。
4. accidentally allowlisting `web_search`：越过 Target Reference Corpus，属于 scope violation，即使模型结果正确也必须作废。
5. 发送 unsupported parameter 后被静默忽略：配置与 manifest 不一致；若 adapter 没有本地 allowlist，HTTP 200 也不可审计。
6. 把 `developer` role 当作 system policy：DeepSeek 当前把它当 `user`，造成 authority drift。[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)
7. 依赖 `previous_response_id`、`conversation` 或 `store` 恢复 run：这些能力不受支持，resume 会丢上下文。
8. `json_schema` provider success 但本地 semantic validation failure：仍必须拒绝。

### 两者共同

1. 网络 timeout/disconnect 后 billing 和 provider completion 状态不明；DeepSeek docs 没有 idempotency-key contract。
2. 401 credential error、402 balance error、422 parameter error 不得被“换 endpoint”掩盖。
3. 429/500/503 retry 后获得不同内容是合法可能；没有 deterministic seed contract，attempt 必须分别审计。
4. 实际 response `model` 与 allowlisted request model 不一致时 fail closed。
5. provider response shape 缺失 required diagnostics 时 fail closed，而不是给默认零值。

## 推荐 contract 与 migration boundary

### 第一版 contract

- DeepSeek-only adapter，固定 base URL 和 request model；旧 provider 不纳入新 abstraction。
- transport 固定 non-streaming Chat Completions。
- adapter 负责 request allowlist、DeepSeek transport、provider response validation、normalization、attempt diagnostics 和 raw serialization。
- controller 负责 action/reflection/finalization、Scoped Literature Retriever、run state、local schema/semantic validation 和 artifact writes。
- 第一版保持当前文本 action envelope，不发送 provider native tools，也不发送 provider `web_search`。
- adapter 返回项目自有 typed result，而不是 SDK `ChatCompletion`；至少容纳 visible content、reasoning、tool calls、response/model/fingerprint、finish reason、full usage、attempt、latency 和 raw response。
- structured mode 是显式 request intent，不能由 adapter 猜测；当前 baseline 用 `text`。Chat `json_object` 只有在 controller protocol 明确要求且 prompt/validator 同步时才启用。

### 为未来 Responses 迁移保留的边界

项目 typed result 不应把 `choices[0]` 写进 controller contract。可以规范为 transport-neutral concepts：

- `visible_text`
- ordered `reasoning_parts`
- ordered `tool_calls`
- `terminal_disposition`
- `provider_response_id`
- `requested_model` / `response_model`
- normalized usage + raw usage
- backend trace fields（可空但不能伪造）
- raw provider response

Chat 的 `finish_reason` 与 Responses 的 `status/incomplete_details/error` 只在 adapter 内映射到 `terminal_disposition`，raw fields 仍完整保存。这样以后切换 endpoint 不需要重写 controller 或旧 artifact reader。

### 允许迁移的触发条件

满足以下全部条件后再考虑 Responses：

1. action protocol 已经通过单独 ticket/version 改为 schema-driven envelope，或 controller 能在不改变行为的情况下按阶段请求 structured final output；
2. no-cost fixture tests 已证明 message/history、reasoning、tool/function items、usage、incomplete/failed 和 raw serialization 映射完整；
3. 经 Robert 批准费用后，account-level smoke test 证明 Pro + Responses + thinking + explicit output limit + intended structured mode 可用；
4. 同一冻结 canary 的公平比较证明 schema failure/repair 或维护收益超过 migration complexity，且 idea quality、retrieval isolation、latency、usage/cost 没有不可接受退化；
5. ticket 明确批准 audit tradeoff，包括 Responses schema 当前没有列出 `system_fingerprint` 和独立 cache-miss field。

不应因“Responses 是更新接口”或“未来可能更标准”而迁移；本项目已经是 DeepSeek-only，抽象价值必须由具体 failure reduction 或 control-flow 简化证明。

## 最小公平验证计划（本次未执行）

### Hypotheses

- H1：Chat 能在不改变 baseline grammar 的前提下满足全部 transport、thinking、usage、diagnostic 与 fail-closed 要求。
- H2：Responses 的 `json_schema` 在 schema-driven protocol 中会减少 malformed/repair attempts，但不会自动保证 semantic correctness。
- H3：对当前 text baseline，Responses 不会带来可观察的质量收益，其额外 item/parser 与 silent-ignore 风险不值得第一版承担。

### No-cost fixture validation

使用手写、脱敏 response fixtures 覆盖：

- Chat `stop` / `length` / `content_filter` / `tool_calls` / `insufficient_system_resource`；
- Responses `completed` / `incomplete:max_output_tokens` / `incomplete:content_filter` / `failed`；
- reasoning、cache usage、empty content、missing fields、invalid JSON、unknown output item；
- request allowlist 拒绝 model/base URL drift、provider web search、silent-ignore candidates；
- 两种 raw response 都能 normalize 成同一 controller result，但不会丢原始字段。

### 后续付费/account-level smoke（必须另行批准）

1. 用不敏感的最小输入，各发一次 non-streaming Chat 和 Responses 请求；固定 model、thinking effort、output limit、system/user semantics。
2. 分别验证 response model、reasoning、terminal diagnostics、usage 和 raw serialization。
3. Responses 额外验证 `text.format=json_schema`；Chat 额外验证 `json_object` 的 empty/truncation fail-closed。
4. 不传任何 tools，明确验证 raw response 中不存在 `web_search_call`。
5. 记录 latency、token usage、cost 与 output hash；不声称单样本证明质量等价。

若要比较 idea quality，应在同一冻结 Workshop/Target Reference Corpus、相同 prompt、effort、limit、controller、validation 和 rubric 下运行多次 paired canary。那是付费 comparative validation，不属于本次无调用研究。

## 最终判定矩阵

| 判定 | 内容 |
| --- | --- |
| **Confirmed fact** | `deepseek-v4-pro` 当前同时支持 Chat Completions 和 Responses API；两者都支持 non-streaming、thinking、explicit output limit、reasoning 与 usage。 |
| **Confirmed fact** | DeepSeek Responses 是 stateless；`previous_response_id`、`conversation` 和 provider storage 不受支持。 |
| **Confirmed fact** | Responses 支持 `json_schema`；Chat 当前只文档化 `json_object`。 |
| **Confirmed fact** | Responses 支持 provider `web_search` 且会静默忽略若干 unsupported parameters；本项目必须本地 allowlist 并禁止 web search。 |
| **Inference** | 对当前 text action/reflection/finalization baseline，Chat 是满足门槛后最简单、风险最低、审计字段最完整的第一版 transport。 |
| **Inference** | Responses 的真正迁移价值来自 schema-driven protocol 或 item-based native tools，而不是模型质量本身。 |
| **Documentation conflict** | 较旧索引快照仍写 Pro 不支持 Responses；当前 live reference、guide、pricing 与 2026-08-13 changelog 已统一为支持。此前“不支持”结论应撤回。 |
| **Unknown / smoke required** | 目标 account 的实际 endpoint 可用性、SDK minimum/version compatibility、Pro + thinking + `json_schema` 组合表现、两 endpoint 的质量/latency/cost 等价性。 |

## Official sources

- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)
- [Using the Responses API](https://api-docs.deepseek.com/guides/responses_api/)
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- [Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)
- [Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)
- [DeepSeek Change Log](https://api-docs.deepseek.com/updates/)
