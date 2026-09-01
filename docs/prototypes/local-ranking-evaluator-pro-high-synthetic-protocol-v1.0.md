# Local-ranking evaluator Pro/high synthetic qualification protocol v1.0

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-015 live output**

本协议执行批准 ladder 的第三档：Flash/high mirror stability FAIL，Flash/max 又先后出现 transport INCOMPLETE 与
full-size 20/24 coverage FAIL。现在只验证 `opencode-go/deepseek-v4-pro` / `high` 的 exact SSE profile；
synthetic packet 不含 interview、Workshop、真实 query、真实 corpus 或旧 judgment。

## 1. Frozen harness and packet

- Harness commit: `8bd1886449e94fcab8fd68df8247fc91f5c6a17b`；
- Streaming adapter SHA-256:
  `9106ae5eceb374650ff38a5411acc16d2b9d81eb5b8a17ef4398128172ecce79`；
- Adapter tests SHA-256:
  `17a6309fec06d692141d69995943c57fba8480607ac006b98b565dd46990e7b6`；
- Attempt: `qualification-015-pro-high-synthetic`；
- Bundle: 3,589 bytes，SHA-256
  `48900c275d9a641d5191013717327ba1bd9414c3792d1a8f26c8f4666628a4b9`；
- Prompt: 5,178 bytes，SHA-256
  `2c9659253d6cbe8f4d5164506883328f6ffaf09f98548268fc64b6c3f5d3f7b8`；
- Request: 5,639 bytes，SHA-256
  `61eb671d813ad1015d4097a30670f1280ece20a1db48a86dacb14c27d399c6e2`；
- Preparation manifest SHA-256:
  `d78849d84be1a57a9ee99ea5b68865f4d024068212ab227941e43dec6c73f725`。

Bundle 从同一 synthetic checksum task 确定性派生：只把 `bundle_id` 改为
`opencode-go-synthetic-pro-high-orientation-1`、把 evaluator model alias 改为
`opencode-go/deepseek-v4-pro`，然后重算 self-hash 和 prompt。Task、items、rubric 与 closed output contract 不变。

## 2. One-call boundary and gates

唯一授权调用固定为：

```text
POST https://opencode.ai/zen/go/v1/chat/completions
model=deepseek-v4-pro
reasoning_effort=high
stream=true
response_format={"type":"json_object"}
max_tokens=32768
messages=[one exact 5,178-byte synthetic prompt]
```

不发送 `stream_options`，credential 只从本机 Kimi Code config 内部读取。本 attempt 不授权 retry。PASS 必须同时
满足：

1. preparation v1.1 把 bundle evaluator、request model/effort 与 manifest exact 绑定；
2. HTTP 200、SSE response 每个 content chunk 的 model 都是 `deepseek-v4-pro`、唯一 response ID；
3. 一个 normal `stop`、唯一 `[DONE]`、billing sidecar `cost="0"`，累计 usage/created 不回退；
4. canonical JSON draft 与 bundle evaluator exact match，本地 finalizer 1/1 PASS；
5. synthetic winner 为预注册的 `left`；
6. receipt 记录 `reasoning_effort_requested=high`，但 `reasoning_execution_proven=false`。

任何 network、HTTP、SSE、identity、JSON、coverage、winner 或 cost gate 失败均停止，不 repair、不切 provider、
endpoint、model 或 effort。

## 3. Conclusion boundary

PASS 只允许生成新的 Pro/high full-size bundles/requests 并另行冻结三组 calibration；synthetic output 不进入该
分母。FAIL 后才进入 Pro/max synthetic；INCOMPLETE 先处理基础设施，不用模型升级掩盖 transport failure。

无论结果如何，本 attempt 不打开 private mapping、不运行 candidate reducer、不计算 BM25/E5 winner，也不进入
Downstream Experiment。
