# Local-ranking atomic Pro/max calibration result v2.3

日期：2026-09-03（Asia/Shanghai）  
协议：[Formal 003 preparation contract v1.0](local-ranking-atomic-formal-003-preparation-contract-v1.0.md) 与
[live execution amendment v1.0](local-ranking-atomic-formal-003-live-execution-amendment-v1.0.md)  
结果：**FAIL at frozen r1 early stop；Codex 独立复核接受 semantic evidence**

## 1. Frozen result

- evaluator：`opencode-go/deepseek-v4-pro`，`reasoning_effort=max`；
- runtime source commit：`8ea6443e5a4424fe3068a48a8b3d40c5ddfa56aa`；
- profile manifest SHA-256：`6be3471c0f774f7d88ebfb06cbf322a5dcba1910d5f3b73e87c515248d30762b`；
- `r1/o1`：24 logical / 24 physical，24 valid，trace SHA-256
  `9ae539995a6d1707cfd921105f367ffda2066cf5906a32f855f3437ab324da7a`；
- `r1/o2`：24 logical / 25 physical，24 valid / 1 deterministic invalid，trace SHA-256
  `d151e780384e35d7d92daaec36226ebee9639fb46c6163d47b53917711e6cebd`；
- 48 个 valid attempts 的 provider response IDs 全部非空且全局唯一；
- pair result SHA-256：`5e26f1e7fd5fedfdc25a16908d4dca6211a34202219a837526658c8fcfe07dfd`。

Pair 的 `stable_count=20/24`，低于冻结门槛 `22/24`；`stable_directional_count=13`，因此不是全
`tie`/`both_bad` 退化。四个 mirror-unstable items 是 `lr-dev-02-focused`、`lr-dev-04-focused`、
`lr-dev-05-focused` 与 `lr-hol-06-focused`。按预注册早停规则，终态为 `stop_profile_failed`，不得运行
`r2`、`r3` 或 winner-driven retry。

唯一 invalid 是 `r1/o2/call-021/attempt-1`：provider 以 `finish_reason=length` 结束，forced tool stream 未完成，
validator 记为 `PROVIDER_RESPONSE_FAILED`；exact same request 的 attempt 2 valid。该失败属于冻结 retry policy，
不改变 semantic 分母，也没有 response ID/receipt 被误计入 valid evidence。

## 2. Independent verification

Codex 未使用 subagent、未读取 credential、未发 model-producing request，完成以下独立检查：

1. 重算 usage snapshots、execution summary、output archive、Windows verifier、两路 run-result/trace 与 pair hashes，
   全部和交付值一致；
2. 从 49 份 attempt/execution result 独立聚合出 48 valid、1 invalid、0 exhausted，并确认 48/48 valid response IDs
   唯一；
3. 只用 frozen bundle、本地 wheels 与 Python 3.13.7，在 unset `OPENCODE_GO_API_KEY` 且不传 Kimi config 的条件下
   re-enter 两路 `atomic_runner`，均从现有 evidence 返回 `pass`；在 fresh scratch 重建的 pair bytes 与正式文件完全一致；
4. 通过既有 SSH 对 Windows 保留目录做只读检查：archive SHA-256
   `00ecfc5d8d9a8a45650e06fe004338184fb8cfcd753337de771914419bd39f44`、verifier SHA-256
   `befaa4841301c0f08607cd7d55a73620662c345db8545329607c92d35579429f` 与 Mac 一致；verifier 明确记录
   `offline=true`、`credentials_accessed=false`、两路与 pair 均 PASS。

这些检查表明 `20/24` 是 evaluator 的 semantic mirror-stability failure，不是漏题、抄写、schema、transport、
跨平台或证据链失败。Pro/high 的独立 r1 也为 `20/24`，但两次只重合两个 unstable items；这支持“当前 DeepSeek
profile 对若干接近判断存在位置敏感性”，不支持把某四题永久认定为坏题。

## 3. Cost-accounting correction

Kimi 生成的 `controller/live-r1-execution-summary.json` 将 `receipt_cost_totals` 写成 `null`，ticket/session log
同时声称“receipt schema 无 cost 字段”。该说法不正确：48 份成功的 receipt 都在强校验字段
`identity.cost` 中记录字符串 `"0"`，聚合 receipt-reported cost 为 `0`。总 tokens 仍是 prompt 151,664、
completion 187,484、reasoning 163,195、total 339,148。

这是 derived summary 的小型事实错误，不影响任何 request、response、attempt、trace 或 pair result。为保持已经归档并经
Windows 核验的 evidence identity，本复核不覆盖原 summary/archive/verifier；本节作为显式 correction，以 raw、hash-bound
receipts 为最终依据。`cost=0` 也不表示没有额度消耗：usage rolling/weekly/monthly 从 `7/36/42%` 上升到
`12/42/45%`。

## 4. Conclusion and recommended next decision

DeepSeek Pro/high 与 Pro/max 都未达到同一个预注册的最低 mirror-stability 门槛，因此 DeepSeek ladder 在当前 atomic
contract 下已经耗尽。继续 r2/r3、重复 r1、提高 retry 次数或事后降低 `22/24` 都只会在看到结果后改变规则，不能形成
可信的 qualification。当前 Pro/max profile 不准进入 fresh Kimi K3 panel qualification。

这次 calibration 不产生 BM25/E5 candidate vote，所以它不证明 BM25 科学胜出，也不证明 E5 与 BM25 等价。结合正式
holdout 已经 `inconclusive`、E5 的 consensus 优势仅 `0.008299`，以及 E5 额外模型/依赖/资源成本，最小合理产品决策是：
**停止继续为本 ticket 搭建新 evaluator ladder，采用 BM25 作为 v1 的 parsimony default；把“没有得到科学 winner”作为
已知不确定性保留。**

该产品选择与 ticket 关闭仍待 Robert 明确批准。若未来目标从“选择一个可交付的 v1 默认值”变为“证明哪一个 ranker
科学更优”，应另开新的研究问题，使用新的 model family 或重做 ambiguity-aware rubric/data 设计；不能把它伪装成 formal
003 的续跑。
