---
title: Define control flow, failures, and resume
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 022-define-the-deepseek-adapter-contract.md
  - 023-define-run-identity-and-evidence-layout.md
  - 024-define-the-safe-ideation-entry.md
---

## Question

How should generation, tool calls, reflections, finalization, atomic writes, retries, interruption, resume, and partial failure behave while preserving compatibility and Run Isolation?

## Resolution

Robert 批准以下控制流、失败与 resume 合同（两轮 grilling，全部按推荐）。它固化 generation/tool/reflection/finalization 主循环、失败分级、中断与 resume 行为，不放宽 020/022/023/024 的任何既定合同。

### 控制流骨架（兼容 baseline）

- 循环结构逐字保留（006/024）：外层 `max_num_generations` 个 generation，内层 `num_reflections` 轮（第 0 轮 generation prompt，其余 reflection prompt），每轮一次 `model_inference` operation、恰好一个 action；`msg_history` 作用域为单 generation；prompt 文本逐字不动。
- 一轮 = 一次 model call + 一个 action 结果；action 结果三选一：tool result / Model-Fixable Error / finalize accepted。

### 模型可修复错误统一回灌

- 无法 parse、未知 action、参数 JSON 非法、FinalizeIdea 结构违规（024）、retriever `INVALID_QUERY`/`QUERY_TOO_LONG`（020）统一为 Model-Fixable Error：作为该轮 tool result 回灌，消耗一轮 reflection；错误文本最小、无内部细节。
- 废除 baseline 的静默 break（parse 失败放弃 generation）与 print-only（未知 action 模型不可见）两条路径；每个付费轮次要么推进、要么产生显式反馈。

### Finalization gate 与检索预算（固化 020 委派项）

- 检索 call budget 为结构性：轮次即预算，generation 检索上界 = `num_reflections`，作为版本化 policy 常量记录；不引入独立计数器。
- Per-generation gate：本 generation 未取得 ≥1 个非空 Retrieval Result 时，FinalizeIdea 作为 Model-Fixable Error 拒绝回灌。
- Run 级 backstop（020）：run 全程从未取得非空 Retrieval Result → Terminal Outcome `failed`。

### Generation Disposition 与 Terminal Outcome

- 每个 generation 记录终局事件，disposition 为封闭枚举 `finalized` | `budget_exhausted`；generation 级失败不终止 run，作为模型行为证据继续下一个。
- Run 的 sealed Terminal Outcome 三枚：`success`（控制流完整走完且全部 run 级 gates 通过；yield 0..N 个 ideas 均合法，计数与各 disposition 入 seal）、`failed`、`preflight_rejected`（024）。Run Suspension 不是 Terminal Outcome，不 seal。

### 失败分级映射（封闭二值表）

- 判定准则：同一 Run Specification 下 resume 是否有意义——环境修好后有意义 → suspend；确定性失败同 spec 必重演或证据可信度已损 → terminal。
- **Suspend**（环境类，run 停于 unsealed 可 resume 状态）：adapter `authentication`、`insufficient_balance`、`rate_limited`、`provider_transient`、`resource_exhausted`、`timeout_ambiguous`、`transport_ambiguous`；storage/IO 失败（磁盘满、权限、fsync）。
- **Terminal `failed`**（契约/确定类，seal 后新 `run_id` 重做）：adapter `configuration`、`model_mismatch`、`truncated`（调 `max_tokens` = 新 spec = 新 run）、`content_filtered`、`empty_content`、`invalid_json`、`unexpected_tool_call`、`malformed_response`、`unknown_provider_failure`；retriever boundary/policy/audit 失败（020）；evidence 完整性失败；020 run 级 backstop。
- 实现查表，不临场判断；controller 不对 adapter 已判 terminal 的失败做任何额外重试、降级或静默跳过。

### 中断与 per-operation 原子性

- SIGINT/SIGTERM 立即 abort，不等待在途调用（单 attempt deadline 最长 60 分钟，022）。
- Per-operation 原子性：operation 要么完整承诺（artifacts 持久化+hash → event 入链），要么不留任何已承诺痕迹。
- 优雅中断时 writer 尽力追加 `interrupted` 事件；kill -9/断电无事件，由 resume 的 023 链验证兜底，语义相同。
- FinalizeIdea 被接受后立即承诺 idea artifact + 事件，再进入下一 generation；废除 baseline 末尾一次性写盘，中断不丢任何已接受 idea。

### Resume

- CLI：`python ai_scientist/perform_ideation_temp_free.py resume --run-id <uuid>`，无其他参数（Run Specification 不可变）。
- 流程：023 全量 resume gates → 从 canonical events+artifacts 重放重建控制态（generation index、reflection round、msg_history、idea archive、last_tool_results、各 generation 非空检索标记；projection 仅 head 匹配时作便利，否则丢弃重建）→ 在途 operation 按同 `operation_seq`、新 `attempt_seq` 重执行（语义输入相同，符合 023 operation 定义）。
- 费用：resume 按剩余工作重估上界，展示已花费 vs 原批准，重新取得 `yes`；批准事实记入 `resumed` 事件引用的 write-once approval artifact（`artifacts/validations/` 下），`admission.json` 保持 write-once。
- Preflight 期间中断：resume 从头重跑 preflight（幂等，无付费调用发生）。
- 同一 operation 的第 3+ 次物理 attempt 仅可能由 resume 重执行产生，由 resume 费用重估覆盖；adapter 单次调用内 ≤2 attempts 不变（022）。

### 原子写入、staging 与 023 修订

- 承诺路径：staging 写入 → fsync → SHA-256 → rename 至 final path → fsync 目录 → 追加 event（event 文件自身同走 staging+rename）。
- Staging 位于当前 run root 内、UUIDv4 固定模板命名；resume 验证链后 best-effort 清空；staging bytes 永不入证据。
- 修订 023 orphan 规则：rename→event 落盘间存在微秒级崩溃窗口，orphan final artifact 不再直接判 run corrupt；resume 时隔离至 quarantine 区、记录 incident、继续——event 从未引用这些 bytes，链完整性不受影响。已在 023 追加修订指针。

### Controller transition events（三层，全走 023 envelope）

1. Lifecycle（无 operation block）：`preflight_started`、每 preflight step 一条、`admitted`（引用 admission hash）、`preflight_rejected`、`resumed`（writer_epoch++ 与 approval artifact ref）、`interrupted`（best-effort）、`terminal`（最终事件，payload 带 outcome 与 disposition 计数；seal.json 引用其 hash，023 顺序不变）。
2. Generation/round：`generation.started` / `generation.finished`（disposition + idea_index 或 null）；每轮一条 action outcome 事件（action 类别 + tool_result / model_fixable_error / finalize_accepted，feedback 文本走 artifact）。
3. Operation/attempt：`operation.started/finished/failed`（typed failure class + suspend/terminal disposition）；`operation_kind` 封闭枚举 = `model_inference` / `literature_retrieval` / `idea_finalization`；每物理 attempt 一条 attempt 事件（022）；020 Retrieval Audit Event 即 `literature_retrieval` operation 的 private artifacts/payload。
- Payload 永不内嵌 prompt/response/idea bytes，只放 artifact refs；closed versioned schema。
- 精确枚举字符串与 payload schema 不逐字钉死：照 034 先例，本票锁定层级、成员与规则，确切 schema 以 versioned tracked files 随实现 ticket 落地。

本票只锁定控制流、失败与 resume 合同；未实现 runtime code、未调用模型、未进入 downstream。
