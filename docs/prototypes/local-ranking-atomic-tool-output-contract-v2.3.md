# Local-ranking atomic tool-output contract v2.3

Contract date: 2026-09-02（Asia/Shanghai）  
Status: **Robert approved; frozen for implementation and bounded canary execution**  
Supersedes: only the Pro/max atomic response-submission transport; v2.2 retry、rubric、packet 与 semantic gates 不变

## 1. 决策

DeepSeek V4 Pro/max 不降 reasoning effort，也不再通过 final `content` 手写嵌套 JSON。新的 primary transport
使用一个不会实际执行的 forced function/tool call `submit_judgment`：模型在 `tool_calls[0].function.arguments`
中提交六字段 judgment，controller 负责拼接 arguments、解析、执行既有本地 validator，并把通过验证的对象写成
canonical `response.json`。

本合同的目标是把两类问题分开：

- 模型负责比较左右 evidence sets 并给出语义判断；
- provider/tool envelope 与 controller 负责可靠传递结构，不要求模型在自由文本 final channel 中完成 JSON
  punctuation bookkeeping。

`reasoning_content` 可以很长，这是 Pro/max 的预期行为。它与普通 `content` 都必须原样保存在 raw SSE/chunks
evidence 中，但两者均不得被解析、修复或用于生成/覆盖六字段 judgment。

## 2. 触发证据

`pro-max-calibration-002/r1/o1/call-021` 在相同 JSON-object request 下连续四次：

- HTTP 200、SSE 完整、唯一 provider response ID；
- 分别消耗 14,197、11,991、15,615、8,083 total tokens；
- provider 均正常结束，却只产生损坏 JSON；attempt 4 还把输出指令自我提醒泄漏到 final `content`；
- 四次都没有可入账的 winner/scores/handles/rationale。

其他 23 calls 均 first-valid，因此当前证据不是 Pro/max semantic FAIL，也不是整个 stream parser 丢包；问题位于
特定 item 与自由文本 JSON finalization 的交界。继续提高 retry ceiling、增加 max tokens 或降低 reasoning effort
都没有直接命中该失败边界。

DeepSeek 官方说明 thinking mode 将 `reasoning_content` 与最终 `content` 分开，并支持 tool calls：

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)

OpenCode Go 当前只公开 `deepseek-v4-pro` 的 OpenAI-compatible Chat Completions endpoint，没有承诺透传 DeepSeek
official beta strict mode。因此本合同不依赖 provider `strict:true`，本地 validator 始终是唯一 validation authority：

- [OpenCode Go models and endpoints](https://opencode.ai/docs/go/)

## 3. 不变边界

以下内容必须保持不变：

- provider/model：`opencode-go/deepseek-v4-pro`；
- `reasoning_effort=max`；
- `max_tokens=16384`；
- `stream=true`；
- atomic public packet、query、左右 top-3 evidence bytes、rubric 与 score semantics；
- `winner ∈ {left,right,tie,both_bad}`；
- 四个 `0/1/2` score fields；
- catastrophic omission 与 visible evidence-handle grounding rules；
- 每个 logical call 最多四次 physical attempts；
- 只对机器可判定 invalid 做 exact-request、no-error-feedback retry；
- first valid 自动入账，valid 后禁止 retry；
- max concurrency 4、replicate early-stop 与全部既有 semantic gates；
- 不调用外部检索工具，不向 evaluator 暴露 controller IDs、retrieval methods、prior labels 或 prior results。

Atomic prompt 中旧的 `No tools are available` 必须精确改为：没有 external/retrieval tools；唯一可用的
`submit_judgment` 只用于提交本题结果。旧的 `Return exactly one JSON object` 指令必须替换为“exactly one
`submit_judgment` call”，其余 rubric 与 blinding 文字保持语义一致。由于 prompt bytes 改变，所有 live inputs
必须重新物化并绑定新 hashes。

## 4. Primary request contract

Request 的 closed schema 与值必须为：

- `max_tokens=16384`；
- `messages=[{"role":"user","content": atomic_prompt_text}]`，其中 `atomic_prompt_text` 必须与 atomic
  manifest 绑定的 `prompt.txt` UTF-8 bytes 一致；
- `model="deepseek-v4-pro"`；
- `reasoning_effort="max"`；
- `stream=true`；
- `tool_choice={"type":"function","function":{"name":"submit_judgment"}}`；
- `tools` 必须恰好包含一个 function：name=`submit_judgment`，description=`Submit the final blind evidence-set
  judgment for this single item.`，`parameters` 必须与下方 `SUBMIT_JUDGMENT_SCHEMA` object 完全相等。

Primary request 中禁止出现 `response_format`、其他 tools、实际 tool execution、第二轮 tool result message、
temperature/top-p 或 validator error feedback。`strict:true` 不进入 frozen request；如果未来要验证 provider strict
能力，必须另立合同，不能静默加入。

`SUBMIT_JUDGMENT_SCHEMA` 使用 provider-portable JSON Schema subset：

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "catastrophic_omission_side": {
      "type": "string",
      "enum": ["left", "right", "neither"]
    },
    "evidence_handles": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["L1", "L2", "L3", "R1", "R2", "R3"]
      }
    },
    "left_scores": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "coverage_diversity": {"type": "integer", "enum": [0, 1, 2]},
        "direct_support": {"type": "integer", "enum": [0, 1, 2]},
        "query_usefulness": {"type": "integer", "enum": [0, 1, 2]},
        "specificity": {"type": "integer", "enum": [0, 1, 2]}
      },
      "required": ["coverage_diversity", "direct_support", "query_usefulness", "specificity"]
    },
    "rationale": {"type": "string"},
    "right_scores": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "coverage_diversity": {"type": "integer", "enum": [0, 1, 2]},
        "direct_support": {"type": "integer", "enum": [0, 1, 2]},
        "query_usefulness": {"type": "integer", "enum": [0, 1, 2]},
        "specificity": {"type": "integer", "enum": [0, 1, 2]}
      },
      "required": ["coverage_diversity", "direct_support", "query_usefulness", "specificity"]
    },
    "winner": {
      "type": "string",
      "enum": ["left", "right", "tie", "both_bad"]
    }
  },
  "required": [
    "catastrophic_omission_side",
    "evidence_handles",
    "left_scores",
    "rationale",
    "right_scores",
    "winner"
  ]
}
```

Provider schema 只负责引导。`evidence_handles` 的 1–4、unique、side/winner consistency、rationale non-empty 与
visible grounding 继续由现有本地 validator 执行，不能因 provider 接受 tool call 而放松。

## 5. SSE extraction 与 fail-closed rules

Tool-mode extractor 必须：

1. 验证全部 content-bearing chunks 的 response ID、model、created monotonicity 与 choice index；
2. 按 `tool_calls[].index` 拼接 fragmented function name/arguments，并绑定稳定 tool-call ID；
3. 只接受 exactly one tool call、index 0、name=`submit_judgment`；
4. 接受 provider `finish_reason` 为 `tool_calls` 或 `stop`，但必须同时满足完整 tool call 与唯一 terminal event；
5. arguments 必须是 UTF-8、可解析为一个 JSON object；不得补括号、删 Markdown、截取子串或容错修复；
6. 把 arguments object 直接交给现有 atomic response validator；validator 通过后才写 canonical
   `response.json`；
7. 普通 `content` 可以为空或存在，只报告字节数并保留 raw evidence，不能供应或覆盖 judgment fields；
8. `reasoning_content` 只验证 wire type并原样留在 raw evidence，不拼入 response、不做 retry decision；
9. multiple tool calls、wrong tool name、missing/invalid arguments、refusal、ambiguous partial stream、非 allowlisted
   finish reason 均 fail closed；
10. receipt 必须绑定 request、tool schema、prompt、atomic manifest、raw SSE、chunks、canonical response、provider
    response ID、tool-call ID、finish reason、usage、cost 与 validation status hashes。

Transport-invalid 和 semantic-validator-invalid 都可以按 v2.2 policy 做 exact-request retry；trigger 只能读取机器错误
码，不能读取 winner、scores、mirror direction 或 private reasoning。四次仍 invalid 时 logical call exhausted，profile
状态为 `incomplete`。

## 6. Canary 与调用授权边界

Robert 于 2026-09-02 明确授权承担 primary implementation 的 Kimi Code/Kimi K3 agent，在以下前置条件全部满足后，
无需再次等待 Codex 或用户 checkpoint，即可直接执行本节限定的最多 5 个 live physical calls：

- exact contract implementation 已完成，完整 tests、Black、Ruff、compileall 与 diff check 全部通过；
- 实现已形成一个 coherent clean commit，`HEAD` 与该 commit 一致且 tracked working tree clean；
- prepare-only manifests 与 exact request bytes 从该 commit 生成，全部 bindings/hashes 已验证；
- 调用前 usage snapshot 已记录；
- implementation agent 已记录 commit SHA、request/manifest hashes、准确命令、provider/model/effort/max tokens、
  timestamps 与 evidence paths，且不把 secret 写入源码、日志或交接文档。

调用顺序固定为：

1. 一个不含 interview/corpus data 的 synthetic forced-tool transport probe；
2. synthetic valid 后，使用 spent `pro-max-calibration-002/r1/o1/call-021` 做 stress canary；
3. stress canary 沿用 exact-request retry，最多四次、first-valid stop；
4. synthetic 最多 1 call，stress 最多 4 calls，总上界 5 physical calls；
5. 两类 canary 均为 `spent_transport_only`，不得产生或复用 semantic vote；
6. synthetic invalid 时不发送 stress canary；stress 四次 exhausted 时不创建正式 profile。

Synthetic 必须先于 stress 执行；stress attempts 也必须串行执行，因为下一次 retry 只有在前一次机器判定 invalid 后
才有授权。该最多 5-call delegation 在 canary PASS 或 FAIL 时立即结束。Implementation agent 必须保留 raw evidence，
回报 implementation SHA、验证结果、manifest/request hashes、调用前后 usage、response IDs、tokens/cost、validator
outcomes 与 evidence hashes/paths，然后停止并交回 Codex 复核。

本授权**不包括** fresh `pro-max-calibration-003-tool-output`、JSON-example fallback、第五次 stress attempt、任何额外
canary、模型族变更，或对 rubric、packet、model、effort、token ceiling、retry 与 semantic gates 的修改。Synthetic
invalid 或 stress exhausted 时，implementation agent 不得自行设计替代方案；canary PASS 时也必须在 full fresh
calibration 前停止。独立复核保留在高成本 scientific evidence 边界，而不是放在用于验证本实现的 disposable canary
之前；复核后可继续使用同一个 Kimi Code session，无需更换 agent。

不新增 first-attempt-valid-rate gate。Primary tool transport 的最小 scale gate 只是：synthetic valid，且 spent
`call-021` 在既有四次上限内产生一个完整 valid judgment。真正的跨 24-item operational evidence由下一步 fresh
r1/o1 提供。

## 7. Fresh calibration boundary

Primary canary 通过后，必须从包含本合同实现的新 clean commit 冻结
`pro-max-calibration-003-tool-output`：

- 六个 orientations 全部生成 fresh atomic prompts、tool requests 与 provider responses；
- 旧 Pro/max 23 个 valid judgments、旧 `call-021` 四次 invalid 以及 canary outputs 全部只作 spent diagnostics；
- 禁止把新 `call-021` 与旧 23 judgments 拼成 orientation；transport/prompt 改变可能影响 semantic output，混用会
  产生 heterogeneous measurement instrument；
- 仍按 r1/o1 → r1/o2 → replicate pair gate → 必要时 r2/r3 的顺序执行；
- 任一 logical call 四次 exhausted 时 profile=`incomplete`；
- 既有 semantic gates 不变：每 replicate 至少 `22/24` mirror stable、pooled 至少 `69/72`、每 replicate
  至少一个 stable directional judgment；
- 不新增首轮 valid-rate、latency、token 或 tie-rate admission gate；这些继续完整报告。

若 Pro/max 通过，后续与 Kimi K3 的 panel qualification 仍必须使用全新 calls；calibration votes 不得复用为
candidate votes。

## 8. 唯一 fallback

只有 primary canary 因机器可判定 tool transport/schema invalid 而停止时，才允许另立并冻结 JSON-example
fallback；不能由 winner、scores、mirror direction 或“不喜欢答案”触发。

Fallback 必须：

- 恢复 `response_format={"type":"json_object"}`；
- 保持 model/effort/max tokens/rubric/packet/validator/retry 不变；
- 在 prompt 中加入两份完全 synthetic、互为左右镜像的完整 JSON examples，使字段格式明确且不偏向某一 side；
- 使用新 request/prompt/schema versions 与全新 hashes；
- 重走 synthetic → spent `call-021` 的最多 5-call canary；
- canary 通过后只能创建 fresh `pro-max-calibration-003-json-example`，不得复用 primary/旧 votes。

DeepSeek 官方 JSON Output 文档要求 prompt 包含 JSON 格式 example，并说明该模式仍可能返回 empty content：
[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)。

Fallback canary 仍失败时，停止 `DeepSeek V4 Pro + OpenCode Go` evaluator profile。不得继续尝试 prompt-only JSON、
自定义 line/XML grammar、自动修复 malformed JSON、解析 reasoning、按答案反馈错误或第五次 retry。更换模型族属于
后续独立决策，不在本合同中预选。

## 9. Schema versions 与兼容性

Primary implementation 写入以下新版本：

- atomic preparation：`local-ranking-atomic-preparation-v2.4`；
- atomic attempt：`local-ranking-atomic-attempt-v2.5`；
- orientation trace/result：`local-ranking-atomic-orientation-trace-v2.5` /
  `local-ranking-atomic-orientation-result-v2.3`；
- transport preparation：`local-ranking-atomic-opencode-go-preparation-v3.0`；
- execution receipt/result：`local-ranking-atomic-opencode-go-receipt-v3.0` /
  `local-ranking-atomic-opencode-go-execution-v2.1`；
- orientation run/round：`local-ranking-atomic-orientation-run-v2.2` /
  `local-ranking-atomic-execution-round-v2.2`；
- profile manifest：`local-ranking-atomic-profile-manifest-v2.2`。

Legacy v2.2 artifacts 必须保持 immutable，并只允许 read/replay/diagnostic validation；新 prepare/execute 不得写旧
schema versions。Primary 与 fallback manifests 必须有显式 `response_submission` enum，禁止根据 request shape 静默
推断模式。

## 10. Implementation 与验证范围

Primary 实现修改以下 8 个 tracked files：

- `prototypes/local_ranking/atomic_judge.py`；
- `prototypes/local_ranking/atomic_opencode_go.py`；
- `prototypes/local_ranking/opencode_go_stream.py`；
- `tests/test_local_ranking_atomic_judge.py`；
- `tests/test_local_ranking_atomic_opencode_go.py`；
- `tests/test_local_ranking_opencode_go_stream.py`；
- `prototypes/local_ranking/README.md`；
- ticket 021。

不得增加新 runtime dependency 或 service。Tests 至少覆盖：

- exact forced-tool request 与 schema hash；
- fragmented tool-call ID/name/arguments 的正确拼接；
- wrong/multiple/missing tool call、malformed arguments、refusal、terminal 后继续输出全部 fail closed；
- `finish_reason=tool_calls|stop` allowlist；
- ordinary content/reasoning 不进入 judgment；
- tool arguments 经过现有 handle/rationale/closed-schema validator；
- exact-request retry、first-valid stop、attempt-4 exhaustion、resume partial-call guard 不退化；
- legacy v2.2 evidence 可读但不能由新 writer 生成；
- repeated prepare 对相同 input 产生 byte-identical manifests/requests；
- full suite、Black、Ruff、compileall 与 `git diff --check`。

实现交付只到 code/tests/docs/prepare-only fixtures。不得创建 live output directory，不得读取凭据，不得发送
synthetic、spent 或 formal model call。

## 11. 明确拒绝

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| 降低 Pro/max reasoning | 拒绝 | 长 reasoning 是预期，失败发生在 final submission |
| 提高 `max_tokens` | 拒绝 | 四次均正常 stop，不是 length truncation |
| 第五次或无限 exact retry | 拒绝 | 已观察 item-specific systematic failure，继续重复没有新信息 |
| 从 reasoning 恢复答案 | 拒绝 | reasoning 不是 contracted judgment，会引入 controller interpretation |
| 自动修复 malformed JSON | 拒绝 | 缺少六字段时任何修复都会猜测语义 |
| 只换 `call-021` 后拼接旧 23 votes | 拒绝 | 新旧 prompt/transport 是不同 measurement instrument |
| prompt-only JSON / line / XML | 拒绝 | 无 provider/tool envelope，仍把 serialization 可靠性押在自由文本遵循上 |
| 为 scale 新增 first-valid-rate gate | 拒绝 | 既有 bounded retry 已直接处理机械 invalid；正式 operational completeness 才是必要边界 |
