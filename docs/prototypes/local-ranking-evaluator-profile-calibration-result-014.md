# Local-ranking evaluator profile calibration result 014

Run date: 2026-09-01（Asia/Shanghai）
Status: **FAIL — serialized Flash/max returned an incomplete 20/24 judge draft**

适用协议：
[profile calibration v1.3](local-ranking-evaluator-profile-calibration-protocol-v1.3.md)。本 attempt 严格按
`r1/o1 → r1/o2` 串行执行；第二路触发 terminal semantic gate 后，脚本按协议停止，没有启动其余四路。

## 1. Observed execution

| replicate | orientation | SSE | provider response ID | total tokens | local validator |
| --- | ---: | --- | --- | ---: | --- |
| 1 | 1 | complete；normal stop/DONE；cost 0 | `router-ce6f51c4b0c7c2e7661846bd3ebd9cdb` | 101,726 | 24/24 PASS；trace `a578f7e205a499d9d4357479134b320f986b02fa844ac2121f810a0c7ddfb808` |
| 1 | 2 | complete；normal stop/DONE；cost 0 | `router-3a114fc8ac47b858c9b158c495686d15` | 84,272 | **FAIL：20/24 coverage** |

Orientation 2 canonical response 本身是可解析 JSON，bundle/evaluator identity 也正确，但 judgments 缺少四个
预期 item：`lr-dev-02-focused`、`lr-dev-03-broad`、`lr-dev-05-broad`、`lr-dev-05-focused`。本地 finalizer 返回
`INCOMPLETE_JUDGE_DRAFT`，没有生成 trace/result，也没有补字段或接受部分覆盖。

两路 raw SSE SHA-256 分别为
`1cd39a5e4df8f01f4db593ad13772dc29586927a5029ade33f576d05268dca7c` 与
`c59e27ab793add798be465517a05c4e1006898a365fee03715ddaeb656dd29ae`；receipt SHA-256 分别为
`96640baeb61f3df4907991a4d6a190f26b9066d20992ec46b2b65907690813b6` 与
`c82ff4dc90dfc67d2e3d37eb5ace149bcfd4e685bf603956169cfd54aebf1f8d`。

## 2. Decision

严格串行后没有再出现 qualification-013 的截断，但 full-size max profile 仍无法可靠地产生 exact 24-item
closed output。Coverage failure 是协议预注册的 profile reliability FAIL，因此：

- `Flash/max` 不批准为 panel evaluator；
- 不运行 mirror aggregator，也不从唯一完整 pair 计算稳定性；
- 不继续 qualification-014 的其余四路，不 retry 缺失 orientation；
- 不把 qualification-013 的五份成功 output 补入本矩阵。

按已批准 ladder，下一步进入 `deepseek-v4-pro/high` 的独立 synthetic SSE qualification。只有 synthetic
transport、profile identity、1/1 validator 与预注册 winner 全过，才考虑新的 full-size calibration。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
