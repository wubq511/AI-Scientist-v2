---
title: Choose the DeepSeek provider and version contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 015-establish-the-deepseek-provider-contract.md
---

## Question

Which provider/base URL is authorized, is DeepSeek direct's floating `deepseek-v4-pro` alias acceptable for the requested `DeepSeek-V4-Pro-0813`, and what credential, spend, training opt-out, retention, processing-location, thinking mode, and web-search restrictions must Robert approve before any call?

## Resolution

Robert 批准以下 provider/version 合同：

- 使用 DeepSeek Open Platform 直连，base URL 为 `https://api.deepseek.com`，请求 model ID 为 `deepseek-v4-pro`。2026-08-29 复核时，官方 Models & Pricing 仍将其映射到任务要求的 `DeepSeek-V4-Pro-0813`。本任务周期短，因此接受这一浮动 alias，不增加长期 checkpoint 漂移防护，也不得把它表述成永久版本锁定。[官方 provider research](../../../research/deepseek-v4-pro-0813-provider-contract.md)
- 训练 opt-out、retention 和中国境内处理不作为这个个人任务的 gate。输入按 ideation 质量和效果选择，同时继续服从已决的 Target Paper idea-leakage 防护、Target Reference Corpus 边界与通用 secret 禁入规则。
- Credential 仅通过本地 `DEEPSEEK_API_KEY` 提供；不得进入聊天、源码、commit、日志或命令输出。当前环境尚未配置该变量，只有在获批的真实 canary 前才需要提供。
- 不设统一固定预算。每次真实运行前必须按计划调用数、输入 token 估算、显式 `max_tokens`、cache 假设和峰谷价格给出预计与最坏成本，经 Robert 对该次运行人工批准后方可调用；禁止把一次批准扩张为后续运行或批量执行授权。
- 启用 thinking，但不凭直觉固定 `reasoning_effort`。`high` 与 `max` 都是候选，最终选择交给 [Compare DeepSeek reasoning effort and completion limits](035-compare-deepseek-reasoning-effort-and-completion-limits.md)，使用相同 canary 输入和质量标准做 Ideation 配置验证；该验证不是 Downstream Experiment。
- 原有 provider 继续使用全局 `MAX_NUM_TOKENS = 4096`。DeepSeek 首轮 canary 使用显式 `max_tokens=32768`；`finish_reason=length` 必须判为失败。后续只根据实际 reasoning/output usage 和质量证据调整，并在调整后的真实运行前重新估算成本、取得批准。
- 禁止 DeepSeek provider 自带的 `web_search`；模型只能使用项目的 Scoped Literature Retriever，以维持 Target Reference Corpus 边界。

本 ticket 未调用 DeepSeek、未使用 credential、未产生费用，也未决定 Chat Completions 与 Responses API 的 adapter 形状；后者仍属于 [Define the DeepSeek adapter contract](022-define-the-deepseek-adapter-contract.md)。

**2026-08-30 修订指针**：[Define canaries and scale gates](028-define-canaries-and-scale-gates.md) 将本票「逐 run 批准」修订为：**终波按批批准**（批内逐 run 列估价行，一次批准覆盖该批，批间检查点可中止）；smoke 与 canary 阶段的逐 run 估价批准维持不变。
