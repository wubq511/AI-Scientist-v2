# Local-ranking atomic rationale contract correction v2.1

Protocol date: 2026-09-02（Asia/Shanghai）  
Status: **Approved correction; supersedes only the Atomic v2.0 rationale-length rule**

## 1. 决策

删除 Atomic evaluator 对 `rationale` 的独立 `800 Unicode scalars` 上限。新规则只要求：

- `rationale` 是非空字符串；
- 内容只能依据当前 packet 的可见证据；
- 不得泄露 candidate、retrieval method、ground-truth 或 prior-result identity；
- response 仍须满足 exact closed schema、合法 enum/type 和 evidence-handle 回链。

单次生成的资源与失控边界继续由冻结请求参数 `max_tokens=16384` 控制。该 ceiling 是物理执行上限，不是语义
准入门槛。

本修正不改变 winner、四项 scores、catastrophic omission、handle 规则、mirror gates、retry 次数、模型顺序或
early-stop 规则。

## 2. 第一性原理

实验要测的是：同一证据集左右镜像后，模型对 evidence-set utility 的方向判断是否稳定。`rationale` 的用途是让
人或 controller 审计判断有没有依据当前可见证据；它的字符数不是目标变量。

一个硬门槛只有在它防止某种会改变结论的错误、且没有更直接的防线时才应存在：

| 风险 | 直接防线 | `800` 上限是否增加保护 |
| --- | --- | --- |
| 空解释无法审计 | non-empty gate | 否 |
| 引用当前题目外的证据 | packet isolation、visible handles、forbidden-text gate | 否 |
| 漏字段或多字段 | exact closed schema | 否 |
| 无限生成或异常成本 | request `max_tokens=16384` | 否 |
| 长解释影响 winner | winner 是独立 closed-schema 字段，raw response 不由 controller 改写 | 否 |

因此 `800` 是重复且代理错误的门槛。它既不能证明语义正确，也不能发现位置偏差，却会把结构完整、可回链的
判断变成 invalid，并触发额外调用。把上限改成 4096 或 8192 只是把同一个任意边界向后移动；删除重复的语义
上限才是最小设计。

## 3. 触发证据与失败含义

冻结的 `pro-max-calibration-001` 在 `r1/o1` 共完成 26 次物理调用：24 个 first attempts，加上两个 exact-prompt
retries。26/26 transport executions 均成功并有唯一 provider response ID；合计 169,211 tokens，receipt cost
合计 `0`。

只有两个 logical calls 的 first attempt 被判 invalid，原因均只有 rationale 超过 800：

| call | attempt | rationale length | 其他结构 | 结果 |
| --- | ---: | ---: | --- | --- |
| `call-008` | 1 | 826 | closed schema、handles、enums 均完整 | invalid |
| `call-008` | 2 | 524 | 完整 | valid |
| `call-011` | 1 | 879 | 完整 | invalid |
| `call-011` | 2 | 982 | 完整 | invalid |

`call-011` 两次均选择 `tie`，均引用左右两侧可见 handles，且 rationale 对当前证据逐项说明。旧 run 因两次
invalid 正确地停止为 `incomplete`；这说明 v2.0 contract 的 rationale gate 不适合，不说明 Pro/max 的语义
判断失败或通过。

## 4. 防止事后择票

不得用新 validator 追认 `pro-max-calibration-001`：若把 `call-011` attempt 1 追认为 valid，attempt 2 已经存在，
会违反 `first valid` 后禁止 retry 的规则；若只选 attempt 2，则构成事后择票。

因此：

1. `pro-max-calibration-001` 永久保留为 `spent_incomplete_contract_v2.0`；
2. 它的任何 response 都不得作为 calibration vote；
3. v2.1 使用新 preparation/attempt/trace/result schema 和全新 attempt root；
4. 六个 orientations 全部产生 fresh provider responses，不复用 v2.0 votes；
5. Pro/high 的 `20/24` FAIL 保持不变：其 48 个 responses 当时都满足旧上限，删除上限不会改变任何 vote 或
   mirror mapping。

## 5. Schema 与验证

- packet 数据结构保持 `local-ranking-atomic-judge-packet-v2.0`；
- prompt/manifest 改为 `local-ranking-atomic-preparation-v2.2`；
- attempt 改为 `local-ranking-atomic-attempt-v2.3`；
- orientation trace 改为 `local-ranking-atomic-orientation-trace-v2.3`；
- orientation result 改为 `local-ranking-atomic-orientation-result-v2.1`。

Targeted tests 必须证明：超过 800 的 grounded rationale 可入账、空 rationale 仍 fail closed、原有
closed-schema/handle/first-valid/retry-after-valid/attempt-exhaustion 规则均不退化。新 live input 必须在源码与本修正
提交后重新冻结，不能沿用旧 prompt hashes。

