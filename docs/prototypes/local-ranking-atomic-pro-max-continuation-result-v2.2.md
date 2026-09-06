# Local-ranking atomic Pro/max 机械 continuation 结果 v2.2

结果日期：2026-09-02（Asia/Shanghai）  
协议：[Pro/max mechanical continuation protocol v2.2](local-ranking-atomic-pro-max-continuation-protocol-v2.2.md)  
结果：**INCOMPLETE / STOP**

## 1. 结果

只重新执行了 `call-021`；其他 23 个 first-valid calls 均未重发。

| attempt | HTTP/SSE | total tokens | 可见字节数 | provider response ID | semantic validator |
| ---: | --- | ---: | ---: | --- | --- |
| 3 | pass | 15,615 | 48 | `chatcmpl-R7YywPddW5uP9ABXoKwf09Pb` | `INVALID_SCHEMA` |
| 4 | pass | 8,083 | 116 | `chatcmpl-ROkjkNUdwSklX0PJx46wGdZA` | `INVALID_SCHEMA` |

两次调用使用的 request SHA-256 均为
`0916cfca6f3fca8a00c48c9b728af82e9395a98187cf673d511bc0b204998cdb`，与 attempts 1/2 完全相同。Attempt 3
再次只返回一个损坏的根字段；attempt 4 在一个 object 中混合了损坏的 JSON key/value 与响应指令文本。两份响应
都没有六个合同字段，也没有任何可由机器提取的 winner/scores/handles/rationale。

Attempt artifact SHA-256：

- attempt 3：`76899f4eac6920fac8f954b6655704717a6dbbc739ac29b4af0916fa8ac243b3`；
- attempt 4：`263c06c6f6969c69542a0e28e06f07373cc320521183746e837bc83d16a33354`。

四次 attempt 上限已经耗尽；没有发送 attempt 5。由于 `call-021` 仍无 valid judgment，没有生成 combined
orientation trace；r1/o2、r2、r3 均未执行。

## 2. 汇总执行证据

原 r1/o1 加 continuation：

- 27 physical calls；
- 27 unique provider response IDs；
- prompt tokens 67,334；
- completion tokens 139,882，其中大量为 provider-reported reasoning tokens；
- total tokens 207,216；
- receipt cost 合计 `0`；
- 23 个 logical calls 均为 first-valid；
- `call-021` 连续四次 transport success、schema invalid；
- rolling/weekly/monthly usage 从 `9/32/40%` 变为 `10/32/40%`；
- 调用后 usage snapshot SHA-256：
  `ac4ff6e03e2b81dd62864f47f7e18c49dbbc94dddc96844ef54a3f8069140aa2`。

## 3. 这证明了什么

这不是 Pro/max 选择了错误 winner 的证据：它从未对 `call-021` 产出合同内的 winner。也不能再把这一行为解释为
一次偶发的 malformed response。同一题连续四次失败，而其他 23 题均 first-valid，说明在当前 OpenCode Go Chat
Completions request 下，长 Pro/max reasoning 与 JSON-object finalization 存在题目特异的交互问题。

拒绝继续重复同一 request。再次提高 attempt ceiling 会掩盖系统性的 operational failure，并在没有新增设计信息的
前提下继续消耗 tokens。

## 4. 已批准的下一合同

进一步对抗性审查后，拒绝把 prompt-enforced JSON 作为 primary：它仍把 serialization 可靠性押在自由文本遵循
上。Robert 已批准 [Atomic tool-output contract v2.3](local-ranking-atomic-tool-output-contract-v2.3.md)：保留
DeepSeek V4 Pro/max reasoning，以 forced `submit_judgment` tool arguments 提交六字段 judgment，再由现有本地
validator 生成 canonical response。

只有 OpenCode Go tool canary 机器失败时，才允许 separately frozen、带左右镜像完整 examples 的 JSON-object
fallback。本 result 的旧 23 votes、四次 invalid 与未来 canary 均不得进入 fresh calibration votes；实现代理也
不得在没有单独调用授权时发送 canary。
