---
title: Suspend and resume an interrupted Ideation Run
type: implementation
status: closed
assignee: Robert
blocked_by:
  - 09-seal-explicit-non-success-outcomes.md
---

# 10: Suspend and resume an interrupted Ideation Run

**What to build:** 让 environment/storage failure 或 SIGINT/SIGTERM 把 run 留在可解释的 unsealed suspension；operator 只凭 exact `run_id` 验证证据、重新批准剩余成本、提升 writer epoch、重建控制态并继续到与无中断执行等价的 Evidence Chain。

**Blocked by:** 09: Seal explicit non-success outcomes.

**Status:** closed

**Contract anchors:** [Define run identity and evidence layout](../../ideation-pipeline/tickets/023-define-run-identity-and-evidence-layout.md), [Define control flow, failures, and resume](../../ideation-pipeline/tickets/025-define-control-flow-failures-and-resume.md).

- [x] 每个 operation 通过 run-local staging、durability、hash、rename 与 event append 原子承诺；中断不会留下半承诺 evidence。
- [x] Approved environment/transport/storage failures suspend 且不 seal；确定性 failure 不能走 resume 路径。
- [x] Resume CLI 只接受 exact `run_id`，全量验证 canonical evidence，从 events/artifacts 而非 projection 重建 generation、round、history、grounding eligibility 与 in-flight operation。
- [x] Resume 记录新 writer epoch 与 write-once cost approval；approved orphan 窗口只 quarantine 并记 incident，其他损坏不在本票中被“修复”。
- [x] 交付 `VM-REPLAY-04`、`VM-FAULT-02` 与 `VM-FAULT-03`，并保持全部已有测试通过。
- [x] 同步受影响的仓库运行说明，记录脱敏 interruption/resume evidence（参见 [interruption-resume-evidence.md](../../../research/interruption-resume-evidence.md)），且 Robert 完成本票验收。

## Resolution

2026-09-04 agent 交付（commits `0c89bbb`、`6d585f3`、`a6a4bbe`、`0573352`、`d2ef30b`），Robert 指示可按机检项自行验收，验收通过后关闭。核心落地：

- `run_store.py` 统一 staged atomic commit(staging→fsync→SHA-256→rename→目录 fsync→event 入链，event 文件同路径）,write-once 排他 fail closed;`writer_epoch` 作为 fencing token，过期 writer 的 append 以 `STALE_WRITER_EPOCH` 拒绝；`clear_staging`/`quarantine_artifact`/`list_committed_artifact_paths` 支撑 resume。
- `RunInterrupted(BaseException)` + controller 信号 guard:SIGINT/SIGTERM 立即 abort 不等在途调用，writer 尽力追加 `interrupted` 事件；kill -9/断电由 resume 链验证兜底。Adapter `initial_attempt_seq` 使 resume 重执行在同一 `operation_seq` 下继续物理 attempt，单次调用 ≤2 attempts 预算不变（022/025)。
- `resume.py` + `rebuild_resume_plan`：只凭 exact `run_id`，全量链验证 + artifact ref 复核 + admission pin 复核 + staging 清理 + approved-window orphan quarantine（记 `orphans_quarantined` incident)，从 canonical events/artifacts 重建控制态（projection 不参与），按剩余工作重估上界并重新取得 `yes`(write-once `resume-approval-<epoch>.json` + `resumed` 事件），续跑到 terminal seal。已承诺 terminal 的 run 由 resume 补 seal;terminal 失败已承诺的 run 由 resume 从 provider_failure evidence 重建相同 reason 补 seal——确定性失败的 seal 义务不被中断豁免。Preflight 期间中断从头重跑幂等 preflight;admission 提交与 `admitted` 事件间的崩溃窗口 epoch-less 补全。
- CLI:`resume --run-id <uuid>` 无其他参数，exit 0 sealed / 2 resume_rejected / 3 suspended;`new-run` 拆 admit/execute 两相位，execute 相位 suspend 类失败 exit 3 且报告 run_id,admission 期间中断同样报告已铸造的 run_id。
- 费用重估只计尚需模型调用的轮次：响应已承诺的 replay 轮不占模型轮次，VM-FAULT-02 逐崩溃点断言 `remaining_model_rounds`。

验收证据（2026-09-04，全零网络零费用）：全量 pytest 544 passed（新增 34 项）;compileall 与 black 通过；CLI help baseline 逐字节一致，`resume --help` 仅接受 `--run-id`;025 suspend/terminal 二值表封闭互斥、suspend 行与合同逐字一致、seal 词汇与 suspend 码无交集交叉检查通过；独立 clean-room 端到端场景经真实 `_run_new_run`/`_run_resume` CLI seam:round-1 SIGINT → exit 3 `RUN_INTERRUPTED`（报告 run_id)→ resume exit 0 sealed success,22 事件链 verify_chain 闭合，semantic trace 与 artifact byte map 与无中断参考 run 完全等价。脱敏摘要见 [interruption-resume-evidence.md](../../../research/interruption-resume-evidence.md)。
