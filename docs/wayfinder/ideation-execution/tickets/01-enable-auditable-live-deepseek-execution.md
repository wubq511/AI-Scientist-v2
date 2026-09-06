---
title: Enable auditable live DeepSeek execution
type: implementation
status: closed
assignee: agent
blocked_by: []
---

# 01: Enable auditable live DeepSeek execution

**What to build:** 让 operator 能通过现有安全 `new-run` 入口在完成 preflight、显式费用批准和 Run Admission 后调用 DeepSeek direct API，并让 `resume` 通过同一真实 transport 续跑被中断的 run；整个实现和验证 slice 不发起真实网络请求。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

**Specification:** [Auditable live DeepSeek execution and one-case smoke](../../../agents/live-smoke-execution-spec.md).

**Contract anchors:** [Choose the DeepSeek provider and version contract](../../ideation-pipeline/tickets/031-choose-the-deepseek-provider-and-version-contract.md), [Define the DeepSeek adapter contract](../../ideation-pipeline/tickets/022-define-the-deepseek-adapter-contract.md), [Define the safe ideation entry](../../ideation-pipeline/tickets/024-define-the-safe-ideation-entry.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md), [Define the minimal runtime dependency contract](../../ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md).

- [x] 生产 transport 实现现有 `Transport.send` 契约，用精确锁定的 `httpx==0.28.1` 向固定 DeepSeek direct Chat Completions endpoint 发送 canonical JSON bytes，返回现有 `TransportResponse`，不引入 OpenAI SDK、`curl`、新协议层或第四个注入 seam。
- [x] Credential 只从本地 `DEEPSEEK_API_KEY` 读取并仅用于 Authorization header；request artifact、response/failure evidence、events、stdout/stderr、测试 fixture、Git diff 和 sanitized export 均不含 credential 或活动 credential-derived 字符串。
- [x] Transport 强制 TLS 验证、禁止 redirect、忽略 ambient proxy/`.netrc`、不接受 caller URL/header/certificate/proxy/retry override；connect timeout 为 10 秒，每个 physical attempt 有不会被 keep-alive bytes 延长的 60 分钟绝对 wall-clock deadline。
- [x] Transport/HTTP client 自身零重试；429/500/503、`Retry-After`、timeout、disconnect、TLS/network failure 全部交回现有 adapter 转换为批准的 typed taxonomy，只有 adapter 能根据封闭规则产生第二个 attempt。
- [x] `new-run` 保持七参数 allowlist，不再在 Admission 后静默返回未执行成功；必须先完成九步 preflight、费用批准与 Admission 才能调用生产 transport。`resume` 只接受 exact `run_id` 并默认复用同一 transport。
- [x] Stub/recorded adapter 注入和全部已有可观察语义保持；新测试在 zero-network mock 中证明 exact method/origin/path/body、credential 隔离、redirect/proxy 阻断、keep-alive body、raw-body evidence、typed failures、absolute deadline、adapter-only retry 以及 `new-run`/`resume` CLI 端到端接线。
- [x] Runtime/development/retained dependency contracts、import allowlist、CLI help baseline 和仓库运行说明与最终执行闭包一致；Python 3.13 clean environment 的全量 pytest、CLI mock smoke、compileall、Black、import/dependency checks 全绿。
- [x] 对本票 diff 做 Standards/Spec 双轴 review 并关闭所有阻断 findings；提交脱敏的 commands、environment lock、pass/fail、hash 和 rollback 证据，全票零真实 provider call、零模型费用、零 downstream execution，且 Robert 完成本票验收。
