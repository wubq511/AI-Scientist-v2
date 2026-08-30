# 本地文献排序比较协议 v1.2.1：实际 judge provenance 修正

Protocol date: 2026-08-31（Asia/Shanghai）

Status: **Approved operational correction / before any ranking run**

Decision ticket: `Choose and calibrate local literature ranking`

本文件是
[v1.2 AI-qrels overlay](local-literature-ranking-comparison-protocol-v1.2.md) 的窄幅修正。
v1.2 SHA-256 保持：

```text
d96deed31926de41f5b5f145e4d2183c61af0c95e8b5ec84be577de03b008a89
```

除本文覆盖的 judge identity 与一次 holdout raw-draft collision 外，v1.2 和 v1.1 全部条款继续
生效。本修正在任何 formal development/holdout ranking 前完成；controller 尚未读取 holdout
labels、grade distribution、disagreement 或 ranking metrics。

## 1. 为什么必须修正

v1.2 最初冻结的 A/B bundles 声明 `gpt-5.6-sol` / `gpt-5.5`。Robert 没有用这两个 Codex
tasks 完成判断，而是把完全相同的 isolated prompt/bundles 分别交给 Kimi Code harness 中的
`kimi-k3` 与 `deepseek-v4-flash` sessions。两个 validator 只验证 draft 中的 declared profile
与 bundle 相等，无法验证实际执行模型，因此原 result 的模型字段不是真实 provenance。

Judgment content、item/rubric/input bytes 与 visible boundary 没有因此变化；但在显式修正前，
这些 artifacts 不能进入正式比较。禁止直接改写原文件或把错误字段解释为真实模型。

## 2. 覆盖 v1.2 §2.1 的实际角色

| Role | Actual harness/model | Reasoning record | 职责 |
| --- | --- | --- | --- |
| judge-A | Kimi Code / `kimi-k3` | `provider-managed-not-exposed` | 全量独立 A judgments |
| judge-B | Kimi Code / `deepseek-v4-flash` | `provider-managed-not-exposed` | 全量独立 B judgments |
| judge-C | Codex / `gpt-5.6-sol` | `xhigh` | 只盲评 A/B disagreement items |

A/B 现在是不同 model families/harness sessions；这降低 shared-model bias，但不能证明 consensus
等于 human gold。Actual session identifiers 只写入 private immutable rebind sidecars，不进入 tracked
文档或日志正文。

## 3. 允许的 metadata-only rebind

为避免重做已经在 blind boundary 内完成的 336 judgments，允许一次 fail-closed provenance rebind：

1. 新 bundle 必须与 source bundle 的 formal input、base protocol、rubric、forbidden context、
   instructions、item set、每个 item payload 完全相等；只允许 revision hash 与 judge profile 改变；
2. source draft/trace 必须先对 source bundle 重新验证；
3. judgment grades、rationales、segment grades 与 supporting quotes 的 canonical semantic hash 必须
   在 rebind 前后完全相等；
4. private sidecar 记录 source/target bundle、source draft 或 trace、actual session、rebound draft、
   qrels、trace 与 result hashes；
5. 原错误 artifacts 不删除、不覆盖，并明确标为 superseded provenance attempts；
6. rebind 后必须再次通过 exact quote、coverage、qrels schema 与 input hash validators。

任何 item/rubric/text/judgment 变化都不是 rebind，必须失败并由对应 isolated judge 重做。

## 4. Holdout shared-path collision

A/B 两个外部 sessions 都使用了 `/Users/robertwu/sealed/holdout/draft.json`。Kimi 后写覆盖了
DeepSeek raw draft；两者使用不同 validator output subdirectories，因此 A/B canonical
`qrels.json`、`trace.json`、`result.json` 均仍存在，且 user-reported hashes 与本机 SHA-256 一致。

处理规则：

- Kimi 使用仍存在的 raw draft 做正常 rebind；
- DeepSeek 只允许从其 canonical validated trace 反向构造 rebound draft。Trace 已完整保存每个
  grade、rationale、segment grade、exact quote/span，因此 judgment 语义可精确保持；
- rebind sidecar 必须标 `source_representation=validated_trace_reconstruction` 与
  `original_raw_draft_available=false`，并保留原 result 中记录的 raw-draft SHA-256；
- 这是 provenance degradation，不是 judgment failure。最终报告必须披露；若 A/B/consensus 的
  winner direction 不一致，本偏差不得用于打破 tie，结果仍为 `inconclusive`。

以后每个 judge/split 必须使用独占 sealed directory；共享输出路径是禁止条件。

## 5. judge-C 与 seal

完成 A/B actual-model rebind 后，controller 可对 development traces 生成 blind disagreement packet。
Holdout 的 rebind 与 disagreement extraction 由 judge-C task 在 sealed 文件边界内执行；controller
在 finalists/参数冻结前只接收新 A/B/C bundle、trace、qrels hashes 与 validator pass/fail，不能
接收 disagreement count/rate 或 label content。

Judge-C 只读：actual-model A/B bundles、validated traces 与确定性工具生成的 original disputed
items。它不得读取 A/B labels/rationales；工具内部读取 traces 只用于 equality diff，并保证输出
packet 不含 prior judgments。Development adjudication 可解封；holdout consensus 保持 sealed。
