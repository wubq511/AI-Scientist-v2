# 本地文献排序比较协议 v1.6：OpenCode Go direct judge overlay

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Approved under Robert's provider constraint and delegated first-principles decision authority；live qualification pending**

本文件只覆盖 [v1.5](local-literature-ranking-comparison-protocol-v1.5.md) 的模型输出根字段、DeepSeek
transport、运行 evidence 与数据治理闸门。v1.4–v1.5 的 fresh cases、BM25/E5、top-3 payload、rubric、
segment-reference judgment、双镜像、双模型、统计单位、promotion gate 和停止规则全部不变。

Robert 已明确要求 DeepSeek 使用 `provider=opencode-go`，禁止改用 DeepSeek 官方 provider。对应的一手证据见
[OpenCode Go structured transport 核对](../research/opencode-go-structured-transport.md)。此前冻结的
qualification v1.4 official Responses 路线在任何 official API call、credential read 或付费发生前被本文件取代；
它只保留为已拒绝的设计证据。

## 1. 第一性原理修正

本实验要测的是 setwise evidence judgment，不是模型复制控制器元数据的能力。qualification-004/005 中，
DeepSeek 的 24 个主体 judgments 在 schema-only diagnostic 后均能通过，重复失败来自 `schema_version`
错误或缺失；`attestation` 又只是模型自报，不能证明 fresh session、无工具或无外部来源。

因此 v1.2 model draft 的根字段固定为且只允许：

```text
bundle_sha256, evaluator, judgments
```

- `bundle_sha256` 与 `evaluator` 暂保留为最小 misrouting/binding guard；
- `schema_version` 由 validator、trace、mapping、preparation 与 statistics envelope 生成，不再要求模型回显；
- fresh session、tools、subagents、provider、endpoint、request/response hashes、timestamps、usage/cost 由
  execution receipt 证明，不再使用模型 `attestation`；
- judgment 内部的 exact closed schema、24/24 coverage、visible segment reference、support/rationale 边界与
  semantic gates 不变。

对应 bundle/draft-contract/trace/mapping/preparation schemas bump 至 `v1.2`，statistics report bump 至
`v1.2`。v1.1 outputs 只保留为 immutable failure evidence，不能与 v1.2 混合。

## 2. Frozen evaluator transports

| evaluator | provider | transport | model | effort |
| --- | --- | --- | --- | --- |
| judge-kimi | `managed:kimi-code` | Kimi Code CLI fresh/tool-less session | `kimi-code/k3` | `high` |
| judge-deepseek | `opencode-go` | direct non-streaming Chat Completions | `deepseek-v4-flash` | requested `high` |

DeepSeek request candidate 固定为：

```text
POST https://opencode.ai/zen/go/v1/chat/completions
model=deepseek-v4-flash
stream=false
response_format={"type":"json_object"}
reasoning_effort=high
max_tokens=32768
```

`opencode-go/deepseek-v4-flash` 只是本地 provider/model selector；wire model 必须是
`deepseek-v4-flash`。API key 可从 `OPENCODE_GO_API_KEY` 或本机 Kimi Code 的
`providers.opencode-go.api_key` 内部读取，禁止进入 request artifact、日志或 commit。

OpenCode Go 官方 endpoint matrix 只确认该模型使用 `/chat/completions`。first-party registry/source 支持把
`json_object` 与 snake-case `reasoning_effort=high` 作为实测候选，但 Go 文档没有承诺两者的完整 raw wire
语义；`/responses`、`response_format=json_schema`、`strict` 和 reasoning 实际执行均不得写成已确认能力。

正式 candidate qualification 前先用不含 interview 内容的 synthetic request 验证目标账号接受 request
shape。随后仍必须用全部 12 spent cases / 24 queries 全量验证 judgment 能力；synthetic PASS 不能替代后者。

## 3. Direct execution evidence

每次 DeepSeek orientation 使用独立 immutable attempt，并保存：

- exact canonical request bytes/hash、endpoint、requested model 与 registry snapshot；
- started/finished timestamps、HTTP status、allowlisted response headers、raw response bytes/hash；
- response `id/model/created/usage/cost` 的实际形状；
- 从唯一 `finish_reason=stop` assistant content 解析出的 canonical draft；
- provider receipt 和独立 `operational_judge finalize` trace/result。

HTTP 200、`json_object` 被接受或 `cost="0"` 都不等于科学 PASS。`cost="0"` 只表示没有从 Zen balance
扣款，不表示没有消耗 Go quota。Model response 必须再通过完整本地 closed/semantic validator。

Adapter 不自动 retry。单次 frozen orientation 只有连接失败、gateway 429、500/502/503/504 且未收到完整
2xx body 时，才可按之后 qualification protocol 预注册的上限用新 attempt ID 整体重试；400/401/403、
finish reason 非 `stop`、JSON/schema/coverage/semantic failure 都是 terminal。禁止静默降级到 Kimi renderer、
DeepSeek 官方、`/responses`、另一 model 或另一 effort。

## 4. Fair restart and qualification boundary

模型可见 prompt/schema 变化对两个 evaluators 一视同仁。下一次 qualification 必须让 Kimi K3 两个 fresh
sessions 与 DeepSeek direct 两个 fresh requests 全部从零运行；qualification-004/005 的任何 PASS 不得复用。
原 v1.2 qualification gates 继续适用：24/24 mechanical、mirror 至少 23/24、block flip、side-collapse、
cross-model 至少 75%、预注册 6-item blind grounding audit 与 exact identity/isolation evidence。

Qualification 永久为 `spent_diagnostic_only`，不生成 ranker winner，也不授权 fresh v1.4 evaluation。

## 5. 2026-09-01 data-retention gate

OpenCode Go privacy 页面目前仍把 DeepSeek 写为 `Not used / 0 days*`，但脚注明确说 current ZDR agreement
只有效到 **2026-08-31**。在 2026-09-01 没有更新或单独确认的情况下，不能声称当前仍是 0-day retention。

因此：

1. synthetic transport probe 可执行，因为不得包含 interview、Workshop、query 或真实 corpus 内容；
2. 含真实 spent query 的 24-item qualification，以及 fresh/private formal calls，在以下任一条件满足前停止：
   - OpenCode 发布覆盖调用日的新 ZDR/retention 证明；或
   - Robert 在看到未确认 retention 风险后，明确授权发送该 exact hash-bound payload；
3. 即使之后获准，也必须在 receipt 中记录调用日 privacy 页面状态，不得回溯宣称 ZDR。

这个闸门只限制外发数据，不阻止本地 bundle preparation、hash/replay、validator、synthetic transport probe、
协议审查或测试。
