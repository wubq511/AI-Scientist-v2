# Local-ranking atomic bounded-retry contract correction v2.2

Protocol date: 2026-09-02（Asia/Shanghai）  
Status: **Approved correction; supersedes only the Atomic v2.0/v2.1 two-attempt ceiling**

## 1. 决策

每个 Atomic logical call 的 physical-attempt 上限从 2 改为 4。attempt 2-4 仍然只能由上一 attempt 的机器可判定
invalid 触发，并且必须满足：

- exact identical prompt/request bytes；
- 同一 provider/model/reasoning effort/token ceiling；
- 不向模型反馈 validator error；
- 不读取或依据 private `reasoning_content` 做 retry 决策；
- 首个 valid 自动入账，之后禁止任何 retry；
- attempt 4 仍 invalid 时停止为 `incomplete`，不得再提高上限。

本修正不放宽 closed schema、enum/type、non-empty grounded rationale、visible handle、blinding、receipt、唯一
provider response ID 或 mirror stability gates。First-attempt validity 和 retry count 继续只报告，不新增准入门槛。

## 2. 触发证据

`pro-max-calibration-002` 使用已修正 rationale contract 的 fresh `r1/o1`：

- 23/24 first attempts 为 valid；
- `call-021` 两次均是 HTTP 200、完整 SSE、`finish_reason=stop`、唯一 response ID；
- attempt 1 消耗 14,197 tokens，却只生成 `{": 0}{": 0}`；
- attempt 2 消耗 11,991 tokens，却只生成 `{":":","}`；
- 两个 visible responses 都没有 winner、scores、handles 或 rationale，validator 只能判 `INVALID_SCHEMA`；
- orientation 共 25 physical calls、183,518 tokens、receipt cost 合计 `0`，最终正确停止为 `incomplete`。

因此这不是 Pro/max semantic PASS 或 FAIL，也不能通过解析已有 response 恢复。它证明：在 144 logical-call 的
profile 中，2 次机械尝试不足以可靠地区分“模型无法判断”与“provider/model finalization 偶发退化”。

## 3. 第一性原理与对抗性审查

重试的边界不是“多抽几个答案”，而是“在尚未产生任何可入账语义答案时，是否允许再次尝试”。这两次退化
response 没有可提取 label；trigger 不依赖 winner、scores、方向或与 mirror 的一致性。因此 bounded invalid-only
retry 不会在多个有效答案中挑一个有利答案。

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 把 23/24 当完整 orientation | 拒绝 | 缺失可能与难题相关，会改变分母并产生选择偏差 |
| 从 private reasoning 推断答案 | 拒绝 | reasoning 不是 contracted visible response，且 controller 不能代模型补 verdict |
| 自动修复 `{": 0}{": 0}` | 拒绝 | 没有足够语义信息，任何“修复”都是猜测 |
| 静默删除旧 `run-result` 后原地续跑 | 拒绝 | 会覆盖历史失败边界，无法审计协议修订 |
| 改用 undocumented `json_schema` | 暂不采用 | OpenCode Go 只把该模型列为 OpenAI-compatible Chat Completions；当前公开说明没有承诺此模型的 `json_schema` 能力 |
| 改成新的文本/XML grammar | 暂不采用 | 23/24 首轮已经证明现有 schema 通常可行；先做更小、不会改变 semantic payload 的修正 |
| 无限重试直到 valid | 拒绝 | 无法封顶成本，也会隐藏不可靠 profile |
| 显式 amendment 后只续 `call-021` | 采用 | 前两次仍 invalid，其他 23 个 first-valid 在新旧规则下完全相同 |

[OpenCode Go 当前模型表](https://opencode.ai/docs/go/)把 `deepseek-v4-pro` 绑定到
`/v1/chat/completions` 和 OpenAI-compatible SDK，但没有为本模型声明更强的 schema-constrained endpoint。本次
不根据“OpenAI-compatible”推断所有 OpenAI structured-output 扩展必然可用。

选择 4 而不是在每次失败后继续加 1，是一次性设置有限闭包：最多 3 次 retry 足以显著降低偶发机械失败造成
整组作废的概率，又保留清晰的 operational failure 信号。以本次约 `2/25≈0.08` 的粗略 attempt invalid rate
做纯说明性独立近似，144 calls 在二次上限下至少一次 exhaustion 的概率约 60%，四次上限下降到约 0.6%；真实
失败可能按 item 相关，因此该计算只解释设计方向，不冒充统计证明或准入 gate。

## 4. Mechanical continuation 与预算

初步方案要求 24 题全 fresh，复核后判定它过度保守。rationale v2.1 修正时不能复用旧 run，是因为新 validator
会把旧 attempt 1 追认为 valid，导致已经存在的 attempt 2 违反 `retry-after-valid`。本次不同：`call-021`
attempts 1/2 在新旧规则下都仍是 invalid，完全没有可入账语义；其他 23 calls 都是各自首个 valid。扩大未来
invalid ceiling 不会改变这 25 个 attempts 的状态、选择顺序或语义。

因此允许对 `pro-max-calibration-002/r1/o1` 做显式、可审计的 mechanical continuation：

1. 原 v2.1 `run-result=incomplete`、attempts 1/2 和全部 receipts 保持 immutable；
2. v2.2 sidecar 绑定旧 profile/run/attempt hashes、修正 commit、新 transport manifest 和 amendment 理由；
3. 23 个 first-valid calls 原样 carry forward，并用 v2.2 resolver 重验；
4. 只对 `call-021` 发 attempt 3；valid 则立即停止，invalid 才允许 attempt 4；
5. combined trace 同时列出旧、新 attempts 及各自 provider response IDs，不复制或改写 model-owned bytes；
6. amendment 发生在 orientation 2 之前，controller 尚未观察任何 mirror-stability 结果，因此不能由 profile
   PASS/FAIL 方向驱动。

后续 orientations 使用同一批已冻结 atomic prompts，但重新生成绑定 4-attempt policy 的 transport/profile
manifest。Profile 仍为 144 logical calls；理论最坏上限变为 576 physical calls，但它不是调用目标。正常
first-valid 时仍为 144；只对 invalid calls 增加 attempts，replicate-level early stop 继续生效。实际 tokens、
延迟、retry 分布和 quota 必须完整报告。

## 5. Schema 与验证要求

- atomic preparation：`local-ranking-atomic-preparation-v2.3`；
- atomic attempt：`local-ranking-atomic-attempt-v2.4`；
- orientation trace：`local-ranking-atomic-orientation-trace-v2.4`；
- orientation result：`local-ranking-atomic-orientation-result-v2.2`；
- transport preparation：`local-ranking-atomic-opencode-go-preparation-v2.1`；
- orientation run/round：`local-ranking-atomic-orientation-run-v2.1` /
  `local-ranking-atomic-execution-round-v2.1`；
- profile manifest：`local-ranking-atomic-profile-manifest-v2.1`。

Tests 必须证明：attempt 4 首次 valid 可被确定性选择；四次 invalid 必须停止；attempt 序列必须从 1 连续；任何
valid 后 retry 仍 fail closed；resume 不能重发 ambiguous partial attempt；profile worst-case budget 精确为 576；
v2.2 resolver 可重验 v2.1 的 `atomic-preparation-v2.2` 与 `atomic-attempt-v2.3`，但只写新版本 artifacts。
