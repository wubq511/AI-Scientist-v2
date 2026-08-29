---
title: Define the DeepSeek adapter contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 031-choose-the-deepseek-provider-and-version-contract.md
---

## Question

How should the existing LLM client expose the exact requested model, configuration, retry policy, token accounting, structured-response behavior, secret handling, and diagnosable failures without changing unrelated providers?

## Resolution

Robert 批准以下 DeepSeek-only adapter 合同。它服务新的 ideation runtime，但不删除或重构现有 provider；legacy provider 保持原状且不进入新调用路径。

### Transport and migration boundary

- v1 固定使用 DeepSeek direct 的 non-streaming Chat Completions：base URL `https://api.deepseek.com`、model `deepseek-v4-pro`、`stream=false`、thinking enabled，credential 只从本地 `DEEPSEEK_API_KEY` 读取。SDK implicit retries 必须禁用。
- 2026-08-29 的 live 官方 reference、guide、pricing matrix 与 2026-08-13 changelog 均确认 `deepseek-v4-pro` 已原生支持 Responses API。此前“不支持 Pro”的判断来自过期搜索索引，已撤回。[Chat Completions 与 Responses API 研究](../../../research/deepseek-chat-completions-vs-responses.md)
- v1 选择 Chat Completions 不是兼容性妥协：当前 action/reflection/finalization 使用文本协议，Chat 与其直接同构，并正式暴露 `system_fingerprint` 和 cache hit/miss usage，且参数与 tool surface 更窄。Responses 的 `json_schema` 和 item/status model 只有在 schema-driven protocol、fixture coverage、获批 account smoke test 与 paired canary 证明净收益后，才允许通过版本化决策迁移；不得运行时 fallback 或同时支持双 endpoint。
- 项目自有 request/result 类型保持 transport-neutral；controller 不依赖 OpenAI SDK response object 或 Chat-specific tuple。

### Request contract

- 固定字段不得由 caller 覆盖：provider、base URL、model、thinking、non-streaming transport、禁用 provider `web_search`/native tools。
- 每次调用只接受经过验证的 ordered `messages`、`reasoning_effort`、显式 `max_tokens`、`output_mode` 与 run-scoped opaque `user_id`。`reasoning_effort` 只接受 DeepSeek V4 Pro 已支持的枚举；具体档位与 completion limit 由获批 canary 决定。
- `output_mode` 是封闭枚举 `text | json_object`。当前 action/reflection/finalization baseline 固定使用 `text`；`json_object` 只有在 caller 同时提供匹配 prompt contract 和本地 validator 时才能启用。
- 禁止任意 model、base URL、`extra_body` 或未知参数透传；禁止 caller 传入 temperature、top_p、penalties、seed 等会被忽略或造成虚假可控性的字段。Adapter 必须 fail closed，而不是静默丢弃。
- Controller 提供完整、有序的 system/user/assistant 可见历史。Adapter 无状态，不维护隐藏 conversation、cache 或 global state；v1 不接受 tool messages。Provider `reasoning_content` 只进入 private evidence，不回灌下一轮 history。Adapter 不解析 Target 身份，`user_id` 的生成与隐私验证属于 caller。

### Result and provider-success contract

- 成功返回稳定 typed result：visible content、reasoning content、tool calls、requested/response model、response ID、`system_fingerprint`、finish reason、完整 usage、attempt index、latency 和可序列化 raw provider response。不得把 SDK object 泄漏给 controller。
- 每个物理请求都产生一个可序列化 Provider Attempt；自动 retry 也必须独立记录，禁止隐藏额外请求。
- HTTP 200 只有同时满足以下条件才算 provider success：required fields 完整、response model 精确匹配、`finish_reason=stop`、content 非空、usage invariants 成立、无意外 tool calls，并通过所选 output mode 的验证。
- `json_object` 的 adapter-level 验证只负责 non-empty、合法 JSON syntax 和 top-level object；禁止自动修复、剥离 Markdown fence 或猜测字段。Idea schema、retrieval provenance、reflection/finalization state 与语义质量继续由 controller 验证。

### Usage and CNY accounting

- Adapter 原样保留并规范化 prompt、cache-hit prompt、cache-miss prompt、completion、reasoning 和 total tokens；强制所有值为非负整数，且 `prompt=cache_hit+cache_miss`、`total=prompt+completion`、`0<=reasoning<=completion`。缺失或不一致均为 response-contract failure，不得填零或用 tokenizer 估算掩盖。
- Adapter 不计算金额。Run/Evidence layer 在每次真实运行前冻结 DeepSeek 官方中文 CNY price snapshot，记录 source URL、抓取时间、内容 hash、model version 与峰谷规则，以 decimal 按 cache hit、cache miss、output 分项计算，并将最终展示金额向上取整到人民币分。不得从 USD 隐式换汇。
- 运行前费用上界使用高峰单价、全部输入按 cache miss、声明的最大输入/输出 token budget 与最多两个 attempts 计算；仍须逐次取得 Robert 对该次真实运行的批准。实际费用按每个 attempt 的真实 usage 和其所在时段对应的冻结价格计算，失败 attempt 也计入。
- 2026-08-29 官方人民币价中，`deepseek-v4-pro` 每百万 tokens 高峰价为 cache hit 0.30 元、cache miss 9.0 元、output 27.0 元，空闲时段减半；这是快照证据，不是永久常量。若运行时官方 CNY 价格缺失、无法验证或 snapshot 过期，必须 fail closed，不回退到 USD 汇率估算。[官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

### Retry, timeout, and failure contract

- Adapter 最多执行两个总 attempts。只对 HTTP 429/500/503 和 `finish_reason=insufficient_system_resource` 自动重试一次；有效且不超过 60 秒的 `Retry-After` 必须遵守，否则使用 1–5 秒 full jitter。更长的 `Retry-After` 返回 controller，不在 adapter 内等待。
- Connect timeout 初始为 10 秒；单 attempt wall-clock deadline 初始为 60 分钟。Timeout/disconnect 的 provider completion 与 billing 状态未知，分类为 ambiguous 且不得自动重试。后续 timeout 只能依据 canary latency evidence 做版本化调整。
- HTTP 400/401/402/422、`length`、content filter、空输出、model mismatch、JSON/schema/protocol failure 均不自动重试；禁止通过更换 endpoint/model、降级 validation 或修改输入实现隐式恢复。
- Failure taxonomy 是封闭稳定枚举：`configuration`、`authentication`、`insufficient_balance`、`rate_limited`、`provider_transient`、`timeout_ambiguous`、`transport_ambiguous`、`model_mismatch`、`truncated`、`content_filtered`、`resource_exhausted`、`empty_content`、`invalid_json`、`unexpected_tool_call`、`malformed_response`、`unknown_provider_failure`。
- 每个 typed failure 携带 attempt index、retry disposition、HTTP status、脱敏 provider code/message、response ID/model/finish reason、timing 与 evidence pointer/hash。Idea、retrieval、reflection 和 finalization failure 不得伪装成 adapter failure。

### Secrets, evidence, and responsibility boundary

- API key 不得进入 config/result/client serialization、request dump、header dump、日志、异常、evidence 或 Git。所有 provider error 在持久化前经过集中脱敏。
- Private gitignored evidence 保存 allowlisted semantic request、完整 raw provider response/reasoning、failure body 与脱敏错误；committed sanitized manifest 只保存 hashes、非敏感 config、usage、disposition、timing、cost evidence 与 error class。
- Adapter 只负责 provider transport、provider-contract validation、normalization、bounded retry 和 attempt diagnostics。Scoped Literature Retriever、controller action loop、reflection、finalization、idea schema、run identity 和 artifact persistence 均在 adapter 之外。

本 ticket 只定义合同并形成研究与工作记录；未修改 runtime code、未读取 credential、未调用 DeepSeek、未产生费用。
