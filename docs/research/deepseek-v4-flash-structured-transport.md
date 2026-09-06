# DeepSeek V4 Flash structured transport 核对

研究时间：2026-09-01T04:34:56+08:00  
研究范围：DeepSeek 官方 `POST /responses`、`deepseek-v4-flash`、non-streaming、thinking `high`、
JSON Schema structured output；只使用 DeepSeek 官方 API 文档与 first-party guide。  
未执行：没有调用模型，没有读取 credential，没有发送 authenticated request，没有产生费用，也没有修改协议或实现。

## 结论

**官方直连 DeepSeek Responses API 已具备本项目裁判调用所需的 transport 能力。**建议用：

- endpoint：`POST https://api.deepseek.com/responses`；
- model：`deepseek-v4-flash`；
- thinking：`"reasoning": {"effort": "high"}`；
- structured output：`"text": {"format": {"type": "json_schema", "name": ..., "schema": ...}}`；
- non-streaming：`"stream": false`；
- 禁止 tools、sampling 参数和未进入 allowlist 的兼容字段。

这比通过 Kimi Code CLI 抽取渲染后的 JSON 更适合正式裁判 evidence，因为 API 原始 response 同时提供
terminal status、response/model identity、ordered output items、cache/reasoning usage 和结构化输出约束。

但能力边界必须写准确：

1. `json_schema` 是 Responses API 的正式 request surface；Chat Completions 当前只正式列出
   `json_object`，二者不能混用字段形状。
2. 官方 reference 说输出符合给定 JSON Schema，但没有说明支持的 JSON Schema draft/关键字全集，也没有为
   Responses `text.format` 文档化 `strict` 字段。实现不得自行添加 `strict: true`，必须继续做本地 schema 与
   semantic validation。
3. `deepseek-v4-flash` 是浮动别名。当前官方规格页把它对应到 `DeepSeek-V4-Flash-0731`，但 response
   schema 只提供 `model`，没有 immutable checkpoint ID 或 backend fingerprint。因此一次响应最多证明
   “官方 endpoint 在该时间返回了 `deepseek-v4-flash`”，不能单凭 response 证明永久固定 0731 权重。
4. 本次没有付费 smoke test；目标账号可用性、当前 SDK 兼容性和 `high + json_schema + 本项目具体 schema`
   的实机表现仍是待验证项。正式使用前应做一个不进入科学结果的最小 qualification call。

官方依据：

- [Responses API reference](https://api-docs.deepseek.com/api/create-response/)
- [Responses API guide and compatibility table](https://api-docs.deepseek.com/guides/responses_api/)
- [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [Token & Token Usage](https://api-docs.deepseek.com/quick_start/token_usage/)
- [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)
- [Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)
- [DeepSeek API changelog](https://api-docs.deepseek.com/updates/)

## 1. Structured output 与 thinking 的官方契约

### 1.1 `json_schema` 支持状态

DeepSeek Responses reference 把以下三种 `text.format` 明确列为合法值：

- `{"type": "text"}`；
- `{"type": "json_object"}`；
- `{"type": "json_schema", "name": ..., "schema": ...}`。

其中 `name` 与 `schema` 在 `type=json_schema` 时必填，官方描述是输出符合所给 JSON Schema。
[Responses API reference](https://api-docs.deepseek.com/api/create-response/)

这与旧的 Chat Completions JSON mode 不同。后者的正式 `response_format` 只保证 valid JSON object，官方还
提醒可能偶发 empty content，并要求合理设置 token limit 避免截断。
[JSON Output guide](https://api-docs.deepseek.com/guides/json_mode/)

因此本项目裁判应使用 Responses `text.format=json_schema`，不能把 Chat 的
`response_format={"type":"json_object"}` 当成等价 structured output。

### 1.2 未被官方承诺的部分

当前 reference 没有说明：

- 支持哪个 JSON Schema draft；
- 是否支持全部 JSON Schema 关键字；
- schema 大小或嵌套深度上限；
- Responses `text.format` 是否接受或需要 `strict`；
- provider 在 content filter 或 output truncation 时是否还能保持 schema。

所以安全边界是：只使用项目已经冻结、相对保守的 object/array/string/number/enum/required/
`additionalProperties: false` 等结构；发送前本地校验 schema 自身，返回后重新做 JSON parse、closed schema
和业务语义校验。provider structured output 是第一道约束，不是最终 authority。

### 1.3 `high` effort 的 exact shape

Responses API 使用嵌套字段：

```json
"reasoning": {"effort": "high"}
```

官方 mapping 为：

| requested | actual |
| --- | --- |
| `none` | 关闭 thinking |
| `minimal` / `low` | `low` |
| `medium` / `high` / `xhigh` | `high` |
| `max` | `max` |

thinking 默认开启且默认 effort 是 `high`，但 evidence run 仍应显式发送 `high`，避免依赖未来可能变化的
默认值。`max_output_tokens` 同时覆盖 visible output 与 reasoning tokens；预算不足会让整个 response
`incomplete`。thinking 模式下 `temperature` 与 `top_p` 不生效，官方为兼容性会接受但忽略它们，所以
不要发送这些字段来制造“低温更稳定”的假证据。
[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)

## 2. 最小请求形状

推荐直接冻结并 hash 下列 JSON bytes；`<...>` 均由 controller 在调用前确定，不允许 adapter 猜测：

```json
{
  "model": "deepseek-v4-flash",
  "instructions": "<frozen evaluator instruction>",
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "input_text", "text": "<frozen blinded comparison packet>"}
      ]
    }
  ],
  "reasoning": {"effort": "high"},
  "max_output_tokens": 32768,
  "text": {
    "format": {
      "type": "json_schema",
      "name": "local_ranking_judgments_v1",
      "schema": {
        "type": "object",
        "properties": "<exact frozen local schema properties>",
        "required": "<all required top-level keys>",
        "additionalProperties": false
      }
    }
  },
  "stream": false,
  "user": "<opaque run-scoped identifier>"
}
```

说明：

- `input` 也可以是纯字符串；这里显式使用 message/content item 是为了让 request evidence 结构稳定。
- `instructions` 是 system-level instruction。DeepSeek 会把 Responses 的 `developer` role 当成 `user`，
  所以不要用 `developer` 承载裁判规则。
- `user` 必须是非隐私的 opaque ID，字符集 `[a-zA-Z0-9\-_]`，最长 512；若当前实验不需要隔离，宁可省略，
  不要填姓名、邮箱或 case 文本。
- 不发送 `tools` / `tool_choice`，也不发送 `web_search`。裁判只读冻结 packet。
- 不发送 `store`、`previous_response_id`、`service_tier`、`prompt`、`truncation`、`metadata` 等字段。
  DeepSeek Responses 是 stateless，且兼容表明确说明多种 unsupported 参数会被**静默忽略**。request
  allowlist 必须在本地拒绝未知字段，不能把 HTTP 200 当成参数已生效证明。
- 示例中的 `32768` 只是实施起点，不是新协议决定；正式值应由实际 schema 最坏输出长度加 reasoning 余量
  预先测算并写入 attempt manifest。改变该值会改变裁判配置。

官方字段与兼容性依据：[Responses API reference](https://api-docs.deepseek.com/api/create-response/)、
[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)、
[Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)。

## 3. Exact response shape 与解析规则

non-streaming 成功响应是一个 `response` object。thinking 模式下，官方示例的 ordered `output` 先放
`reasoning` item，再放 `message` item：

```json
{
  "id": "<response id>",
  "object": "response",
  "created_at": 1753000000,
  "status": "completed",
  "model": "deepseek-v4-flash",
  "output": [
    {
      "type": "reasoning",
      "id": "<reasoning item id>",
      "status": "completed",
      "content": [
        {"type": "reasoning_text", "text": "<reasoning>"}
      ],
      "summary": []
    },
    {
      "type": "message",
      "id": "<message item id>",
      "status": "completed",
      "role": "assistant",
      "content": [
        {"type": "output_text", "text": "<JSON text>", "annotations": []}
      ]
    }
  ],
  "usage": {
    "input_tokens": 0,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens": 0,
    "output_tokens_details": {"reasoning_tokens": 0},
    "total_tokens": 0
  },
  "store": false,
  "parallel_tool_calls": true,
  "previous_response_id": null,
  "error": null,
  "incomplete_details": null
}
```

实现不要只读取 SDK convenience property `response.output_text`。安全解析顺序是：

1. 保存 HTTP status、非秘密 response headers 和原始 body bytes，计算 SHA-256；
2. JSON parse 整个 body，检查 `object == "response"`；
3. 只接受 `status == "completed"`、`error == null`、`incomplete_details == null`；
4. 检查 `model == "deepseek-v4-flash"`；
5. 允许 ordered `reasoning` items，但不把 reasoning text 当裁判结论；
6. 因本次请求没有 tools，遇到 `function_call`、`web_search_call` 或未知 item 直接失败；
7. 要求恰好一个 completed assistant `message`，且恰好一个 `output_text`；空文本、多个候选文本或
   incomplete item 都失败；
8. 对 `output_text.text` 做 JSON parse、本地 frozen schema validation、item coverage/binding/evidence-ref
   等 semantic validation；
9. 检查 usage 均为非负整数，且 `total_tokens == input_tokens + output_tokens`；原始 usage 与派生成本分开保存。

原始 reasoning 可能包含输入片段和服务端思维链，应留在 private/ignored raw evidence 中；tracked receipt 只放
hash、status、model、usage、时间与本地 validator 结果，不复制 reasoning 正文。

官方 response schema：[Responses API reference](https://api-docs.deepseek.com/api/create-response/)。

## 4. 模型身份能证明到哪里

当前官方 Models & Pricing 页面写明：

- request ID：`deepseek-v4-flash`；
- 当前 model version：`DeepSeek-V4-Flash-0731`；
- context：1M；max output：384K；thinking/non-thinking、JSON Output、Responses API 均支持。

[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

2026-07-31 changelog 也说明对外调用继续使用 `deepseek-v4-flash`，该别名访问“latest version”。
[DeepSeek API changelog](https://api-docs.deepseek.com/updates/)

这意味着别名会滚动更新。Responses schema 的身份相关字段只有：

- `id`：本次 response 的唯一 ID，不是 checkpoint ID；
- `created_at`：响应创建时间；
- `model`：响应使用的 model ID。

reference 没有列 `system_fingerprint`、model revision、weight hash 或 deployment ID。最严谨的 evidence
标签应是：

> DeepSeek official API `deepseek-v4-flash`, response model observed at `<created_at>`；调用时官方规格页
> advertised `DeepSeek-V4-Flash-0731`。

不得把它缩写成“已密码学证明使用固定 0731 checkpoint”。如果 protocol 必须冻结 exact checkpoint，当前
官方 API 契约不够；需要 DeepSeek 提供 immutable model ID/版本字段，或在 protocol 中明确接受 provider
managed floating alias。四个裁判 calls 之间至少要逐次核对 response `model`、记录时间并禁止跨已知官方
版本切换窗口混批。

## 5. Usage telemetry 与价格

Responses 返回：

- `usage.input_tokens`；
- `usage.input_tokens_details.cached_tokens`；
- `usage.output_tokens`；
- `usage.output_tokens_details.reasoning_tokens`；
- `usage.total_tokens`。

`reasoning_tokens` 是 `output_tokens` 的细分，成本计算不要再额外加一次 reasoning。官方 token guide 要求以
API 返回的 usage 为实际 token 用量依据。
[Responses API reference](https://api-docs.deepseek.com/api/create-response/)、
[Token & Token Usage](https://api-docs.deepseek.com/quick_start/token_usage/)

截至研究时间，`deepseek-v4-flash` 的官方单价（USD / 1M tokens）为：

| token | off-peak | peak |
| --- | ---: | ---: |
| input cache hit | $0.007 | $0.014 |
| input cache miss | $0.22 | $0.44 |
| output（含 reasoning） | $0.66 | $1.32 |

工作日 peak 时段为 UTC 01:00–04:00、06:00–10:00，即 Asia/Shanghai 09:00–12:00、14:00–18:00；
其他时段 off-peak。价格会变化，所以 evidence 应保存 usage 与查询时间，不要只保存当时计算出的美元数。
[Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

派生成本公式：

```text
cached = usage.input_tokens_details.cached_tokens
uncached = usage.input_tokens - cached
estimated_cost =
    cached   / 1_000_000 * input_cache_hit_rate
  + uncached / 1_000_000 * input_cache_miss_rate
  + usage.output_tokens / 1_000_000 * output_rate
```

实现必须检查 `0 <= cached <= input_tokens`。这是按公开价与 usage 估算，不等同于最终账单；账单、赠送余额
与 provider 调整不应进入科学 winner 逻辑。

## 6. 失败语义与 retry policy

### 6.1 HTTP 层

官方错误码：

| HTTP | 含义 | 本项目处理 |
| --- | --- | --- |
| 400 | request format invalid | terminal；修实现/请求，不能原样重试 |
| 401 | authentication failed | terminal；不得把 credential 写入日志 |
| 402 | insufficient balance | terminal；补余额后开启新 attempt |
| 422 | invalid parameters | terminal；修参数后开启新 attempt |
| 429 | rate limit | 可 bounded retry；保留原 attempt |
| 500 | server error | 短暂等待后可 bounded retry |
| 503 | server overloaded | 短暂等待后可 bounded retry |

[Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/)

最小策略：单个 frozen orientation 最多 `1 initial + 1 retry`；只对未收到完整 2xx body 的网络错误、429、
500、503 重试，使用有 jitter 的 backoff，并优先尊重响应若提供的 `Retry-After`。每次都是独立 attempt，
独立保存 request/response/hash/时间/usage；不得覆盖第一次，也不得自动切到 Chat Completions、Kimi Code、
其他 provider 或另一个 model。

DeepSeek 没有文档化 idempotency-key 契约。timeout/disconnect 后服务器是否已完成、是否计费是 ambiguous；
retry 可能产生第二份不同且再次计费的输出，不能冒充同一调用的透明恢复。

### 6.2 HTTP 200 内的失败

Responses 的 top-level `status` 可以是 `in_progress`、`completed`、`incomplete`、`failed`。non-streaming
只有同时满足 `completed + error=null + incomplete_details=null` 才算 transport success。

- `incomplete_details.reason=max_output_tokens`：reasoning 或 JSON 被截断，整个 attempt 失败；正式 frozen
  config 下不能临时加 token 续跑。
- `incomplete_details.reason=content_filter`：整个 attempt 失败；不得读取残留 output 当裁判结论。
- `status=failed`：保存 `error.code/message` 后失败；是否开启新 whole-orientation attempt 由预注册 retry
  规则决定。
- schema-invalid、coverage 缺失、空 JSON：即使 top-level completed 仍是本地 validation failure，不得修补
  provider 输出。

官方 terminal semantics：[Responses API reference](https://api-docs.deepseek.com/api/create-response/)、
[Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)。

### 6.3 长等待与连接

官方说明请求等待期间：non-streaming 可能持续返回空行；streaming 会返回 SSE `: keep-alive` 注释；若请求
10 分钟仍未开始 inference，服务端会关闭连接。自写 HTTP parser 必须允许 JSON body 前的空白，并把
连接关闭记录为 transport failure；不要靠每几十秒轮询模型任务。
[Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/)

## 7. 最小安全实现建议

1. 新建一个只服务 DeepSeek official Responses 的小 adapter；固定 scheme/host/path/model，request 使用
   exact-key allowlist。不要复用 Kimi Code CLI renderer，也不要运行 agent/tools。
2. 若仓库已有并锁定兼容版本的 OpenAI Python SDK，可使用
   `OpenAI(base_url="https://api.deepseek.com").responses.create(...)`；否则优先用现有 HTTP 依赖直接
   `POST /responses`，不要只为一次 transport 再引入 agent CLI。无论哪种方式，都记录 client/SDK version。
3. credential 只从进程环境或系统 secret store 读取；request artifact 永远不含 Authorization header，异常
   和日志对 headers 做 allowlist 而不是黑名单脱敏。
4. 调用前冻结 canonical request JSON、schema、prompt、model/effort/max token 与 SHA-256；调用后原样保存
   raw body，再从副本解析。request evidence 与 retry attempt 不可覆盖。
5. 只接受第 3 节的 terminal/output invariants；provider JSON Schema 成功后仍运行现有 closed local
   validator。禁止人工清洗 Markdown fence、拼接多个 content block 或修 JSON。
6. private raw artifact 保存 provider response；tracked receipt 保存 response/request hashes、`id`、
   `created_at`、`model`、status、usage、estimated cost、validator result 和公开价格快照时间。
7. 先用 spent qualification packet 做一次 `high + 项目 schema` account-level smoke test；通过只能证明
   transport/机械准入，不能生成 BM25/E5 winner。失败时停在 qualification，不消耗 fresh formal data。

### 最终判定

| 问题 | 判定 |
| --- | --- |
| 官方 `deepseek-v4-flash` 支持 Responses API | **Confirmed** |
| Responses 支持 `json_schema` structured output | **Confirmed** |
| Responses 支持显式 `reasoning.effort=high` | **Confirmed** |
| 返回 model/response/usage/failure diagnostics | **Confirmed** |
| response 能证明 immutable 0731 checkpoint | **No** |
| 官方定义完整 JSON Schema subset / `strict` 字段 | **Not documented** |
| 当前目标账号与具体 schema 实机组合已验证 | **No；需要最小 smoke test** |
| 是否适合作为本项目最小安全正式 transport | **Yes，前提是 fail-closed adapter + qualification** |
