# OpenCode Go structured transport 核对

研究时间：2026-09-01（Asia/Shanghai）

研究对象：OpenCode Go `deepseek-v4-flash` 的 direct raw HTTP transport。

证据范围：只使用 OpenCode 官方文档、`anomalyco/opencode` 官方源码和
`anomalyco/models.dev` 官方 registry；没有调用模型、没有读取 credential、没有发送 authenticated
request，也没有修改代码或协议。DeepSeek 官方直连不在本报告候选范围内。

源码快照：

- `anomalyco/opencode@04284921ac8f657555b5a182f5ff055f471543e4`（2026-08-31）；
- `anomalyco/models.dev@eda98d420a05fbc3d7c87a8805985d24b2c2b79b`（2026-08-31）。

## 结论

**可以保留逻辑 provider `opencode-go`，绕过 Kimi Code CLI renderer，直接调用 OpenCode Go 的 raw
Chat Completions endpoint。**这会去掉 Kimi Code 的 agent/session/prompt/output-rendering 层，同时继续使用
OpenCode Go API key、Go quota 和 OpenCode Go gateway；它不是 DeepSeek 官方直连。

但“强结构化输出”要分两种含义：

1. **应用层强约束：可行。** direct non-streaming Chat Completions + `json_object` 候选请求 + 本地 closed
   JSON Schema/semantic validator + fail-closed retry，可以得到比 CLI rendered stdout 更干净、可审计的原始
   JSON response。OpenCode 官方 registry 将该模型标为支持 structured output，网关源码也会原样转发
   `response_format`；不过 Go 文档没有逐项公开 `json_object` 的 wire contract，所以正式运行前仍需用 spent
   packet 做一次最小 qualification。
2. **provider-enforced JSON Schema：当前不能确认。** OpenCode Go 文档没有为 `deepseek-v4-flash`
   声明 `response_format.type=json_schema`、`strict` 或 JSON Schema subset；官方源码只能证明字段会被转发，
   不能证明当前隐藏的 upstream deployment 接受并执行该值。不能把 `/responses` 或 Chat `json_schema`
   写成已经成立的 contract。`reasoning_effort` 虽出现在 first-party registry 与 gateway parser 中，
   也没有被 Go 文档确认为 Flash raw HTTP contract；实际是否被当前 backend 执行仍未证实。

因此推荐的 transport 方向是：

```text
provider label = opencode-go
endpoint       = POST https://opencode.ai/zen/go/v1/chat/completions
model          = deepseek-v4-flash
stream         = false
output mode    = json_object candidate + local closed-schema validation
```

不是：

```text
POST https://opencode.ai/zen/go/v1/responses
provider-enforced response_format=json_schema
```

### 能力判定表

| 问题 | 判定 | 证据边界 |
| --- | --- | --- |
| 保留 `provider=opencode-go` | **Yes** | provider 由 Go endpoint/API key 决定；raw request 中 model 用裸 ID |
| 绕过 Kimi Code renderer | **Yes** | 直接收取 Go gateway 的 Chat Completions JSON，不经过 Kimi session/renderer |
| Chat Completions | **Confirmed** | OpenCode Go endpoint matrix 明确列出 |
| Responses API | **No documented support for this model** | `/responses` route 存在不等于 Flash 被分配到该协议；官方表只分配 Chat |
| `response_format=json_object` | **Source-supported, runtime qualification pending** | registry 声明 structured output；gateway passthrough；Go 文档未枚举确切值 |
| `response_format=json_schema` | **Not confirmed** | 无该 model/endpoint 的 OpenCode 官方 contract |
| `reasoning_effort=high` | **Source candidate, runtime unverified** | registry/parser 指向 snake_case `low/high/max`；Go raw API 文档未承诺 backend 执行 |
| immutable model revision | **No** | registry 当前映射到 0731，但 public API 未提供不可变 revision/fingerprint |
| 自动 retry/idempotency | **No documented guarantee** | gateway handler 单次发起 upstream request，没有重试循环 |

## 1. Direct raw API 与 Kimi Code CLI 的边界

### 1.1 Direct raw API 保留了什么

- 调用地址仍在 `opencode.ai/zen/go/v1`；认证仍使用 OpenCode Go API key；额度仍来自 Go subscription 或
  用户显式开启后的 Zen balance fallback。因此 evidence 中的 provider label 可以继续写
  `opencode-go`。
- HTTP payload 中必须发送裸 model ID `deepseek-v4-flash`。`opencode-go/deepseek-v4-flash` 是 OpenCode
  配置中的 provider/model selector，不是 wire model ID。官方 endpoint table 同时列出这两种命名边界。
- OpenCode gateway 仍会做认证、quota、模型路由、upstream model ID 替换、usage/cost 追踪和部分 response
  header 清洗。direct raw API 只是绕过 Kimi Code，不是绕过 OpenCode gateway。

依据：[OpenCode Go endpoint matrix](https://opencode.ai/docs/go/#endpoints)、
[固定源码：Go Chat route](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/go/v1/chat/completions.ts#L1-L13)、
[固定源码：gateway request forwarding](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L169-L256)。

### 1.2 绕过了什么

direct caller 自己构造 `messages` 并读取原始 Chat Completions JSON，不再经过 Kimi Code 的：

- agent/session prompt assembly；
- tool orchestration；
- stdout/Markdown renderer；
- 从 renderer 文本中二次抽取 JSON 的步骤。

这正好移除了当前 closed-output reliability 问题所在的 shared harness。但 response 仍可能在 HTTP 200
内出现空 content、截断、非预期 choice 或 schema-invalid JSON；必须由本地 validator 判失败，不能把
“绕过 renderer”误写成“模型输出必然合规”。

## 2. Endpoint、协议与认证

### 2.1 唯一可冻结的 inference endpoint

OpenCode 官方 Go 页面把 `deepseek-v4-flash` 明确分配给：

```text
https://opencode.ai/zen/go/v1/chat/completions
@ai-sdk/openai-compatible
```

同一表格只给 Grok、GPT 和 Muse 等其他模型分配 `/responses`。虽然官方 server source 中确实存在通用 Go
`/responses` route，但 handler 会按 request format 选择模型配置，并要求选中的 provider format 与入口
format 一致；“route 文件存在”不能推出 Flash 支持 Responses。

依据：[OpenCode Go endpoint matrix](https://opencode.ai/docs/go/#endpoints)、
[固定源码：Go Responses route](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/go/v1/responses.ts#L1-L14)、
[固定源码：format validation](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L191-L205)、
[固定源码：model format selection](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L526-L540)。

### 2.2 Authentication

Go 文档说明订阅后复制 API key；inference route 源码从 `Authorization` header 的第二段读取 key，并由
gateway 对 key、workspace 和 entitlement 做校验。direct caller 应使用标准形式：

```http
Authorization: Bearer <OPENCODE_GO_API_KEY>
Content-Type: application/json
```

报告和 evidence 不得保存该 header。官方源码没有为 Go inference 声明 `x-api-key` 替代形式、key scope、
expiry 或 idempotency key。

依据：[OpenCode Go setup](https://opencode.ai/docs/go/#how-it-works)、
[固定源码：route key parser](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/go/v1/chat/completions.ts#L5-L13)、
[固定源码：authentication](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L674-L808)。

## 3. Structured output

### 3.1 网关会不会吞掉 `response_format`

当前 gateway 的 request-body path 只定位并替换根级 `model`；其余 request bytes 原样 streaming
passthrough。仅当 `stream=true` 且走 OpenAI-compatible upstream 时，gateway 会在末尾补
`stream_options.include_usage=true`。因此 direct non-streaming request 中的 `response_format` 和
`reasoning_effort` 不会被 Kimi 或 gateway renderer 重写。

依据：[固定源码：request body replacement/passthrough](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/requestBody.ts#L90-L105)、
[固定源码：byte passthrough](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/requestBody.ts#L141-L170)。

这只能证明**传输**，不能证明每个 upstream 可选字段的**语义支持**。

### 3.2 `json_object`

first-party models registry 当前把 `opencode-go/deepseek-v4-flash` 继承到
`deepseek/deepseek-v4-flash-0731`；base model metadata 明确写 `structured_output = true`。此外官方
OpenAI-compatible conversion code 保留 `response_format` 字段。三者共同构成“当前实现意图支持
structured/JSON output”的较强证据。

但 OpenCode Go HTTP 文档没有明确列出：

- `response_format: {"type":"json_object"}` 的 request schema；
- 必须出现哪些 prompt 约束；
- empty/truncated/content-filter 情况；
- streaming 组合语义。

因此 `json_object` 可以作为最小 paid qualification 的候选，不应在未实测前宣称 account-level contract
已经验收。

依据：[固定 registry：OpenCode Go model mapping](https://github.com/anomalyco/models.dev/blob/eda98d420a05fbc3d7c87a8805985d24b2c2b79b/providers/opencode-go/models/deepseek-v4-flash.toml#L1-L16)、
[固定 registry：base model capability](https://github.com/anomalyco/models.dev/blob/eda98d420a05fbc3d7c87a8805985d24b2c2b79b/models/deepseek/deepseek-v4-flash-0731.toml#L1-L21)、
[固定源码：OpenAI-compatible `response_format`](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/provider/openai-compatible.ts#L198-L220)。

### 3.3 `json_schema`

**未确认。** `structured_output = true` 在 models.dev schema 中只表示“structured output feature”，
没有区分 `json_object` 与 provider-enforced `json_schema`。Go endpoint matrix、Go request
source 和 model registry 都没有承诺：

- `response_format.type = "json_schema"`；
- `json_schema.strict = true`；
- 支持的 JSON Schema draft/keywords、schema 大小或 nesting limit；
- schema violation 时的 status/error。

OpenCode session SDK 自己也有名为 `json_schema` 的高层 format，但官方实现是注入一个
`StructuredOutput` tool、要求模型调用工具并在本地校验，不是 Go Chat Completions 的
`response_format=json_schema` wire contract，不能把两者混为一谈。

依据：[固定 registry schema：`structured_output` 定义](https://github.com/anomalyco/models.dev/blob/eda98d420a05fbc3d7c87a8805985d24b2c2b79b/README.md#L260-L283)、
[固定源码：OpenCode session structured-output tool](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/opencode/src/session/prompt.ts#L1243-L1286)。

## 4. Reasoning effort：源码候选，不是已确认的 Go HTTP contract

若后续对 direct Chat 做 qualification，最有 first-party source 依据的候选是 flat snake_case：

```json
"reasoning_effort": "high"
```

OpenCode Go 的 first-party registry 对该 model 列出 `reasoning_effort = low|high|max`，并把
`low/high/max` 注册为 reasoning variants。gateway 的 variant parser 同时识别
`reasoningEffort`、`reasoning_effort` 和 `reasoning.effort`，但 request body 随后原样 passthrough；parser
识别某个别名不代表 gateway 会把 camelCase/nested form 规范化为 upstream wire field。因此 direct HTTP
候选不应发送 `reasoningEffort` 或 `reasoning: {effort: ...}`。

依据：[固定 registry：reasoning options](https://github.com/anomalyco/models.dev/blob/eda98d420a05fbc3d7c87a8805985d24b2c2b79b/providers/opencode-go/models/deepseek-v4-flash.toml#L1-L11)、
[固定源码：variant parser](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/variant.ts#L19-L21)。

官方 Go 文档没有为 Flash raw API 声明字段、合法值、默认 effort 或 backend translation。registry/parser
只能证明 OpenCode 工程当前的配置意图与路由识别，不能证明隐藏 upstream 实际执行。因此本报告不能把
`reasoning_effort=high` 标为 confirmed；它必须和 `json_object` 一起通过目标账号最小 qualification。
本次没有调用模型。

## 5. 候选最小 non-streaming request

以下只是下一步 qualification 的候选形状，不是本报告对协议的修改：

```json
{
  "model": "deepseek-v4-flash",
  "messages": [
    {"role": "system", "content": "<frozen evaluator instruction and JSON contract>"},
    {"role": "user", "content": "<hash-bound blinded packet>"}
  ],
  "reasoning_effort": "high",
  "response_format": {"type": "json_object"},
  "max_tokens": 32768,
  "stream": false
}
```

边界：

- `max_tokens=32768` 只是示意值，正式值仍要按冻结 schema 的最坏输出和 reasoning 余量确定；
- 不发送 tools、tool choice、sampling 参数或未验证的兼容字段；
- `stream=false` 可避免 SSE 重组和 gateway 追加的空-choice cost chunk，更适合保存 exact raw body；
- `response_format=json_schema` 和 `strict` 不进入候选；
- response content 必须再次执行 JSON parse、closed schema、coverage、binding、quote 与 semantic validation。

## 6. Response、usage 与 model identity

### 6.1 Raw response 能保留什么

当 caller 与 selected provider 同为 `oa-compat` format 时，response converter 是 identity；non-streaming
gateway 会解析 JSON 以提取 usage/计费，然后把 response 原字段返回，并在能够计算 usage 时增加 `cost`。
官方 helper 识别：

- `usage.prompt_tokens`；
- `usage.completion_tokens`；
- `usage.total_tokens`；
- 可选 `usage.prompt_tokens_details.cached_tokens`；
- 可选 `usage.completion_tokens_details.reasoning_tokens`。

这些 detail 字段在类型和计费代码中是 optional，正式 validator 不应要求 reasoning/cache detail 必然存在。
Go subscription 正常消耗 quota 时，新增的 `cost` 是字符串 `"0"`；它表示本次没有从 Zen balance 扣款，
**不表示没有消耗 Go quota**。若已达 Go 限额并显式开启 balance fallback，`cost` 才可能成为实际 balance
成本字符串。

依据：[固定源码：same-format response identity](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/provider/provider.ts#L215-L227)、
[固定源码：usage normalization](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/provider/openai-compatible.ts#L26-L81)、
[固定源码：response cost injection](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L298-L328)、
[固定源码：occurred cost semantics](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L1002-L1045)。

### 6.2 Model identity 能证明到哪里

未认证的官方 `GET /zen/go/v1/models` 当前返回：

```json
{"id":"deepseek-v4-flash","object":"model","owned_by":"opencode"}
```

`owned_by=opencode` 是目录 owner，不是物理 upstream、checkpoint 或权重 hash。models.dev 固定快照当前将
alias 映射到 `deepseek/deepseek-v4-flash-0731`，但 gateway server 的实际 provider/model routing data
从部署资源加载，源码显示同一 logical model 可以按优先级、权重、sticky session、TPM/TPS 和 provider budget
选择 backend。public response header 又只保留 `content-type` 与 `cache-control`；内部 endpoint/provider model
headers 不会转交 caller。

所以正式 evidence 应同时记录：

- requested provider label `opencode-go`；
- exact endpoint 与 requested model `deepseek-v4-flash`；
- request timestamp；
- models.dev registry commit/hash；
- raw response 中实际出现的 `id`、`model`、`created`、`usage` 与 body hash。

但不得把这些字段写成“密码学证明固定 0731 checkpoint”。

依据：[官方 models endpoint](https://opencode.ai/zen/go/v1/models)、
[固定源码：provider selection](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L555-L670)、
[固定源码：response header allowlist](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L280-L328)。

## 7. 价格与 quota 语义

OpenCode Go 官方当前说明：

- subscription：`$10/month`；每 workspace 只允许一个成员订阅；
- general limits：5 小时 `$12`、weekly `$30`、monthly `$60`，均按 dollar-value usage 计；
- DeepSeek V4 Flash 估算容量：每 5 小时 `7,600` requests、每周 `18,900`、每月 `37,800`；
- Flash 每 1M tokens 的参考价格：
  - off-peak：input `$0.22`、output `$0.66`、cached read `$0.007`；
  - peak：input `$0.44`、output `$1.32`、cached read `$0.014`；
- weekday peak：UTC `01:00–04:00`、`06:00–10:00`；其余时段和周末 off-peak；
- pricing table 的 Flash `Usage` 栏为 `$30`，而全局 monthly limit 为 `$60`。官方 source 通过
  `quotaCost = rawCost * modelInfo.costMultiplier` 把 model multiplier 计入三个 window；因此两列不能自行合并
  成一个新的 cap，也不能把 response `cost="0"` 当作 quota 未消耗；
- 达限后可以继续使用 free models；只有用户同时有 Zen balance 并显式开启 `Use balance` 时，Go 才会在
  达限后回退到 balance，否则请求被阻止；
- 官方明确说 limits 会随使用反馈调整，运行证据必须记录查询日期。

依据：[OpenCode Go usage/pricing](https://opencode.ai/docs/go/#usage-limits)、
[OpenCode Go balance fallback](https://opencode.ai/docs/go/#usage-beyond-limits)、
[固定源码：Go quota cost tracking](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L1159-L1197)。

官方 source 还提供 authenticated `GET /zen/go/v1/usage`，返回 rolling/weekly/monthly 的
`status`、`percent` 和 `resetsAt`；它不返回每次 inference 的模型 output，也不是本次模型调用。
[固定源码：Go usage endpoint](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/go/v1/usage.ts#L10-L158)

## 8. 错误与 retry

### 8.1 Gateway 当前可见错误语义

固定 server source 显示：

| HTTP | Gateway 语义 | Retry 边界 |
| --- | --- | --- |
| `400` | upstream `404` 会被重映射为 `400`；也可能是 provider invalid request | 不应原样重试 |
| `401` | missing/invalid key，也复用于 credits、workspace/user limit、model error | 先按 body `error.type` 分类；不自动重试 |
| `403` | region 或 data-policy rejection | terminal，需外部状态变化 |
| `429` | gateway rate/free/Go/subscription limit；若已知会带 `Retry-After` | 可在未超 attempt cap 时尊重 header |
| `499` | caller disconnected/aborted | 结果与计费可能不确定，不能当透明失败 |
| `500` | 未分类 gateway internal error | 可按预注册策略 bounded retry |
| upstream other | 大体保留 upstream status/body；error message 加 provider 前缀 | OpenCode 未发布通用 retry contract |

gateway 返回给 caller 的 upstream headers 只保留 `content-type` 和 `cache-control`，因此 upstream 自己的
`Retry-After` 不一定可见；gateway 自己生成的 429 会显式加该 header。handler 只调用一次
`providerRequest()`，没有内置 retry loop，也没有公开 idempotency-key contract。

依据：[固定源码：upstream status/response handling](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L270-L328)、
[固定源码：gateway error mapping](https://github.com/anomalyco/opencode/blob/04284921ac8f657555b5a182f5ff055f471543e4/packages/console/app/src/routes/zen/util/handler.ts#L435-L523)。

### 8.2 本项目最小 retry 建议

以下是项目 policy 建议，不是 OpenCode 官方保证：

- 每个 frozen request 最多 `1 initial + 1 retry`；
- 只对连接失败、gateway 429、500/502/503/504 做 bounded exponential backoff + jitter；有
  `Retry-After` 时优先尊重；
- 400/401/403 terminal；先修 request、credential、region 或 entitlement；
- timeout/499 后 upstream 可能已经完成并计入 quota；retry 必须生成新 attempt ID，不能覆盖第一次；
- HTTP 200 但空 content、`finish_reason=length/content_filter`、JSON parse/schema/semantic failure 都算完整
  attempt failure；不得人工去 fence、补 key 或修 JSON；是否允许一次 whole-request retry 必须在运行前冻结；
- 不得自动降级到 Kimi CLI、`/responses`、DeepSeek 官方 endpoint、另一个 provider/model 或另一个 effort。

## 9. 2026-09-01 ZDR 文档过期风险

Go privacy table 仍把 DeepSeek V4 Flash 写为 `Model training: Not used`、`Data retention: 0 days*`，但脚注
同时明确说明 DeepSeek ZDR agreement 按月续签，页面上的“current agreement”只有效到
**2026-08-31**。本报告日期为 2026-09-01，该有效期已经过去。

因此在 OpenCode 更新页面或给出新确认前：

- 不得把当前调用写成已确认 ZDR/0-day retention；
- 含私有 interview data 的正式 request 仍有数据治理 blocker；
- 即使 transport qualification 只用 spent/synthetic packet，也要在 evidence 中记录这项未决风险。

依据：[OpenCode Go privacy](https://opencode.ai/docs/go/#privacy)。

## 10. 最终建议

1. **保留 `provider=opencode-go`，不保留 Kimi CLI 作为正式 transport。** 不采用 DeepSeek 官方 endpoint；
   direct raw HTTP 仍走 Go subscription，但移除已经表现出 closed-output reliability 问题的 Kimi renderer。
2. **使用 non-streaming Chat Completions。** 原样保存 request/response bytes 与 SHA-256；这是当前唯一被 Go
   endpoint matrix 明确分配给 Flash、且 gateway forwarding 行为能由源码证明的 renderer-free 路径。
3. **最小化模型生成的冗余元数据。** 模型只生成裁判语义本身需要的 closed fields；provider/model、
   endpoint、request/response hashes、timestamps、attempt ID、usage、quota/cost 等 provenance 全由 controller
   从 request/response 和运行上下文确定后写入 envelope，不要求模型回显。这样减少漏字段和自报 identity
   的失败面，又不削弱可审计性。
4. **先按 `json_object` + `reasoning_effort=high` 候选做 spent qualification。** 两个 raw 字段都不能只凭
   “OpenAI-compatible”视为已验收；要求首轮 raw content 可 JSON
   parse，并通过 frozen closed schema、coverage、binding 与 semantic validators；记录 usage/model/cost 字段的
   实际形状。
5. **不把 `json_schema`、reasoning execution 或 `/responses` 写成已确认 contract。** 只有 OpenCode 对该 model/endpoint 发布明确文档，
   或另一次经 Robert 批准的 live probe 给出可复现 account-level evidence后，才重新评估。
6. **ZDR 先保持未确认。** 正式发送私有 interview payload 前，需要 OpenCode 更新 2026-09-01 之后的
   retention/ZDR 状态。

最终判定：

> `opencode-go` direct Chat Completions 是当前最直接的 renderer-free transport；它足以构建“raw JSON +
> local fail-closed validation”的强应用层结构化输出，但当前官方证据不足以宣称 provider-enforced
> `json_schema`。
