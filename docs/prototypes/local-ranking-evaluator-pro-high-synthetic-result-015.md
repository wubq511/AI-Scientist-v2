# Local-ranking evaluator Pro/high synthetic qualification result 015

Run date: 2026-09-01（Asia/Shanghai）
Status: **FAIL — transport passed, exact bundle identity failed**

适用协议：
[Pro/high synthetic protocol v1.0](local-ranking-evaluator-pro-high-synthetic-protocol-v1.0.md)。只执行了唯一一次
授权 synthetic call，没有 retry。

## 1. Transport outcome

- HTTP 200，3,173 个 SSE data events，normal stop、`[DONE]`、billing sidecar 与 `cost="0"` 全部存在；
- Response model `deepseek-v4-pro`，provider response ID
  `bfe361ba-4f1e-4166-b06b-adf37e06a2fc`；
- Receipt requested effort `high`，`reasoning_execution_proven=false`；
- Usage: prompt 1,567、completion 3,169、reasoning 2,510、total 4,736 tokens；
- Raw SSE SHA-256:
  `75a71a69dee1c08dbaa9580c8cbdad7cd0cb9af4d3de5991038acd9898ec50d0`；
- Canonical response SHA-256:
  `a778b47a1b1b5490f890e2dd335bbd2f0d2e7921b6bb71f5b9b18f05d9e52ea8`；
- Receipt SHA-256:
  `931c962fe1954584e84b52a8d09179fbd60decb0f096610730eb0b53fabe2899`。

这证明 OpenCode Go 当前接受 `deepseek-v4-pro/high` exact SSE request，并返回了目标 wire model；但 transport
PASS 不等于 evaluator PASS。

## 2. Terminal semantic failure

Frozen bundle 的 self-hash 应为：

```text
e88de828dc4a3e28791d72262104e459b73efb3009bd7904d6792f1dc783b9c1
```

Model 返回：

```text
e88de828dc4a3e28791d72262104e459b73efb3009bd7904d2f1dc783b9c1
```

返回值漏掉字符，不能绑定 exact bundle。Evaluator object 和 judgment count 虽为正确形状，本地 finalizer 仍按
`HASH_MISMATCH` fail closed；没有生成 trace，也没有人工修复 hash 后继续检查 winner。

## 3. Decision

Qualification-015 判 profile reliability FAIL，Pro/high 不进入 full-size calibration。按已批准 ladder，下一步是
最后一档 `deepseek-v4-pro/max` 的独立 synthetic qualification。Pro/high response 不复用，不只重发错误字段；
若 Pro/max 仍 FAIL，则停止 profile ladder，不降低 gate。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
