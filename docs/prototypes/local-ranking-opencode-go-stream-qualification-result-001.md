# Local-ranking OpenCode Go streaming qualification result 001

Run date: 2026-09-01（Asia/Shanghai）
Status: **FAIL — validator rejected provider bookkeeping shape; no output reused**

适用协议：
[streaming qualification v1.0](local-ranking-opencode-go-stream-qualification-v1.0.md)。只运行了预登记顺序中的
synthetic request；full-size request 未启动。

## 1. Observed transport

Synthetic call 在约 6.4 秒内返回 HTTP 200 / `text/event-stream`，raw SSE body 99,043 bytes，SHA-256
`b27b97e285863a9008449b03d63871b27357409820c9a1f27d5202f10ed64eb8`。Adapter 保存完整 stream 后，以
`INVALID_PROVIDER_RESPONSE / Stream usage changed between chunks` fail closed；validation-error SHA-256
`8d2c788ae3a5e77d69215b1a397c14bad0d878efd9f1c9849c42a97f51760237`。

失败发生在 transport parser，未生成 canonical response/receipt，也未调用 `operational_judge finalize`。

## 2. Bookkeeping-only diagnosis

只读 chunk metadata、不给旧 attempt 写回任何文件后，确认 provider 实际序列为：

1. 一个正常 `finish_reason=stop` content chunk，同时给 core usage
   `1469/1089/2558`；
2. 一个 `choices=[]` usage chunk，core totals 不变，只补充 `cached_tokens=0`；
3. `[DONE]`；
4. 一个唯一、最后、exact keys 为 `choices/cost` 的 billing sidecar，`choices=[]`、`cost="0"`。

原 parser 把 usage detail enrichment 错当成 totals drift，并要求 `[DONE]` 是绝对最后 data event。两条都是未从
provider shape 证实的 construct-irrelevant assumptions。诊断版本可以完整重建一个 JSON object，并观察到唯一
response ID、model `deepseek-v4-flash`、`finish_reason=stop`，但该诊断不得让 stream-001 追认为 PASS。

## 3. Fail-closed consequence

- `stream-001-synthetic` 永久保留为 FAIL；
- 不 repair、不生成旧 attempt canonical response、不运行 local judge validator；
- 不启动 `stream-002-full-orientation-1`；
- 新 parser 只能在新提交、新协议和新 synthetic attempt 中重新 qualification；
- model、prompt、JSON contract、semantic validator 与 full-size request 均不因该失败改变。
