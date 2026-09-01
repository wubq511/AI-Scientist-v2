# Qualification-007 external-data authorization

Authorized at: 2026-09-01T01:18:17Z  
Actor: Robert  
Status: **Approved under qualification protocol v1.5 condition 2**

Robert 在被明确告知 OpenCode Go DeepSeek retention/ZDR 于调用日未获新证明、以及 exact payload 的内容边界后，
选择条件 B 并回复：

> 批准，选择 B 。你不用担心这么多，这个对我们任务本身没有影响就行，其他的不用管

授权允许把以下两个已冻结、不可修改的 qualification-007 prompts 发送到
`https://opencode.ai/zen/go/v1/chat/completions`，provider `opencode-go`、wire model
`deepseek-v4-flash`：

| orientation | prompt bytes | prompt SHA-256 | request SHA-256 |
| ---: | ---: | --- | --- |
| 1 | 265181 | `4c4dbaf1d674008a53aa1412332176c0a53ea693bed411e11d257fd2cb06a750` | `9c085636616fd1d90a0769ea54d2ef37d4b50be1219bd3798f3f0e61bd908765` |
| 2 | 265181 | `220752c4e9eb4f5295cc911f9923942961baaf4bf7c861d1520966c41f11a1f3` | `2c47348451dc09d78807c026171ad4ea000fba69618e7dee9a86f856e968f243` |

Evidence 必须记录 `retention unconfirmed / user-authorized exact payload`，不能把本授权改写成 ZDR 证明。
其他 execution、validation、no-retry、blind mapping 与 conclusion boundaries 继续以
[qualification protocol v1.5](local-ranking-evaluator-qualification-protocol-v1.5.md) 为准。
