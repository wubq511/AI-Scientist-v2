# 中断挂起与恢复验证证据(Ticket 10)

## 验证背景与范围

本证据文档对应 implementation ticket [10: Suspend and resume an interrupted Ideation Run](../wayfinder/ideation-implementation/tickets/10-suspend-and-resume-an-interrupted-ideation-run.md),证明:

1. **Per-operation 原子承诺**:每个 operation 经 run-local staging → fsync → SHA-256 → rename → event append 原子落链;在任一承诺点注入 SIGKILL 式中断都不留下半承诺 evidence(023 修订的 rename→event 窗口只产生 orphan final artifact,不被判 corrupt);
2. **Suspend 不 seal**:SIGINT/SIGTERM 立即 abort(不等待在途调用),writer 尽力追加 `interrupted` 事件;approved suspend 类失败(adapter 7 码 + storage/IO)原样上抛,run 保持 unsealed;确定性失败(terminal 分级、preflight_rejected、证据损坏)一律不能走 resume 路径;
3. **Resume 等价性**:operator 只凭 exact `run_id`,经全量链验证 + admission pin 复核 + orphan quarantine + 新 writer epoch + write-once 剩余成本批准后,从 canonical events/artifacts(而非 projection)重建 generation/round/msg_history/grounding eligibility/in-flight operation,继续到与无中断参考执行**语义等价的 Evidence Chain**;
4. **Preflight 期间中断**:resume 从头重跑幂等 preflight(无付费调用),cost approval 仍在 Run Admission 内,不产生 `resumed` 事件。

验证全程确定性:`StubTransport` / 注入 store seam(`_rename_staged`/`_stage_bytes`/`append_event` 故障注入),真实本地存储,**零网络调用、零真实模型费用**,未进入 downstream 阶段。

---

## 验证矩阵映射

| 行 ID | 检查项 | 结果 | 证据 |
|---|---|---|---|
| **VM-REPLAY-04** | 中断的 run 经批准后 resume,抵达与无中断执行等价的最终 Evidence Chain | **PASS**(`tests/test_suspend_resume.py`) | round-1 transport 调用中 SIGINT → orphan request quarantine → resume 重建 msg_history 后重发的 round-1 请求与参考请求**逐字节相等**(`sent_requests` 三段比对);semantic trace + artifact byte map 双重等价断言 |
| **VM-FAULT-02** | 在承诺路径各阶段(staging、rename、event append)注入中断,无半承诺 evidence 且 resume 等价 | **PASS**(同上,7 个成功剧本 + 2 个终局失败剧本参数化) | 崩溃点覆盖:model request/response artifact rename、`provider_attempt.finished`/`operation.finished`/`action_outcome`(tool_result 与 finalize_accepted)/`generation.finished`/`terminal` 事件 append、`seal.json` rename;每个剧本断言 seal 结果、trace 等价、byte map 等价、恰一个 epoch-2 `resumed` 事件、approval artifact 引用、`verify_chain` 闭合,并断言 approval artifact 中 `remaining_model_rounds` 与真实剩余模型轮次一致 |
| **VM-FAULT-03** | storage/IO 失败(写盘失败、磁盘满)归类 suspend,永不 seal | **PASS**(同上) | ENOSPC staging 失败与 event append I/O 失败均以 `STORAGE_WRITE_FAILED` 上抛、run 无 seal.json、无 `interrupted` 事件;健康 store resume 后抵达参考链 |

辅助回归:重复 suspend/resume 循环(epoch 1→2→3,两次 `interrupted` + 两次 `resumed`,approval artifact 各一份)、suspend 类 provider 失败(429×2 耗尽单次调用预算 → `operation.failed` disposition=suspend → resume 于物理 attempt 3 成功,attempt 序列 `[1,2,3,1]`)、admission 提交与 `admitted` 事件间的崩溃窗口补全、preflight 中断重跑、CLI `resume` exit 0/2/3、CLI admission 中断报告的 run_id。

---

## 核心实现与契约落地

### 1. Staged atomic commit 与 writer epoch fencing(`run_store.py`)

- 所有已承诺字节(artifacts、events、request/admission/seal)统一走 `_commit_file`:run root 内 UUID 命名 staging 写入 → fsync → SHA-256 → `os.rename` 至 final path(已存在即 fail closed,write-once)→ 目录 fsync;
- `writer_epoch` 作为 fencing token:链上 epoch 单调不减,过期 writer 的 append 以 `STALE_WRITER_EPOCH` fail closed;无 epoch 的 lifecycle 前缀(preflight)豁免;
- `clear_staging`(resume 验证链后 best-effort 清空,staging bytes 永不入证据)、`quarantine_artifact`(orphan 字节移至 `quarantine/<incident>/`,离开 `artifacts/` 命名空间,返回 incident 记录)、`list_committed_artifact_paths` 支撑 resume 流程。

### 2. 信号驱动立即 abort(`errors.py` + `controller.py` + `deepseek.py`)

- `RunInterrupted(BaseException)`:派生自 BaseException,使 adapter transport 映射、retriever audit 记录、storage 清理等 `except Exception` 路径永远不会吞掉或重分类操作员中断;
- `controller.run()` 的 `_signal_interrupt_guard()` 把 SIGINT/SIGTERM 转为 `RunInterrupted`,writer 尽力追加 `interrupted` 事件后原样上抛;kill -9/断电无事件,由 resume 的链验证兜底,语义相同(025);
- Adapter `execute_round(..., initial_attempt_seq=...)`:resume 重执行在同一 `operation_seq` 下以新物理 attempt_seq 继续,单次调用内 ≤2 attempts 预算不变;第 3+ 次物理 attempt 仅可能由 resume 产生(022/025);
- `parse_stored_response_content`:resume 重建从已承诺 response.json 字节重新解析并复验模型可见内容,校验不过即证据损坏 fail closed。

### 3. Resume gates、quarantine 与费用重估(`resume.py`)

`resume_run` 只接受 exact `run_id`,按序执行:身份/存在/seal gates(`INVALID_RUN_ID`/`RUN_NOT_FOUND`/`RUN_ALREADY_SEALED`)→ 全量 `verify_chain` + 每个 artifact ref 的存在/哈希/长度复核(失败即 `RUN_CORRUPT`,不「修复」)→ `preflight_rejected` run 拒绝 resume(`RUN_PREFLIGHT_REJECTED`)→ admission pin 逐项复核(workshop、corpus、price table、code commit、credential 在场)→ staging 清理与 orphan quarantine(`orphans_quarantined` 事件记录 incident)→ `rebuild_resume_plan` 重建控制态 → 按剩余工作重估上界(展示 original bound / 已花费 / remaining bound / projected total)→ 交互 `yes` 批准 → write-once `artifacts/validations/resume-approval-<epoch>.json` + `resumed` 事件(引用 approval artifact)。

- 剩余轮次只计**尚需模型调用**的轮次:响应已承诺的 replay 轮(PendingResponse)不重复计数;`admission.json` 保持 write-once;
- 已承诺 terminal 事件而 seal 缺失的 run,resume 补写 canonical seal(`SealTerminalCompletion`);terminal 失败已承诺而 terminal 事件/seal 被切断的 run,resume 从链上 provider_failure evidence 重建相同 reason 并 seal `failed`(`SealFailedCompletion`)——确定性失败的 seal 义务不被中断豁免;
- Preflight 期间中断:无 admission.json 且无 `admitted` 事件 → 从头重跑幂等 preflight;admission 已承诺而 `admitted` 事件被切断的批准窗口 → epoch-less 补写同一事件。

### 4. 控制态重建(`rebuild_resume_plan`,controller.py)

从事件链重放:accepted ideas 与 archive 字符串、generation disposition 计数、run 级非空检索标记、当前 generation 的 msg_history/last_tool_results/retrieved_paper_ids;in-flight operation 按封闭窗口归一为 `PendingReexecute`(同 operation_seq、下一 attempt_seq 重执行)/`PendingResponse`(响应已承诺,replay 其 retrieval/finalize 动作,孤立的 retrieval 请求按自身坐标重执行)/bookkeeping 补承诺(被切断的 `operation.finished`/`action_outcome`/`generation.finished` 以新 epoch 补写, payload 与 live 路径逐字段一致)。窗口之外的一律 `RUN_CORRUPT`。

### 5. CLI seam(`perform_ideation_temp_free.py`)

- `resume --run-id <uuid>`,无其他参数(Run Specification 不可变);exit 0 = 已 seal,exit 2 = resume_rejected(stderr 结构化 JSON),exit 3 = suspended(stdout 结构化 JSON,run 保持 unsealed);
- `new-run` 拆为 admission/execute 两相位:admission 失败 exit 2(preflight_rejected),execute 相位的 `STORAGE_WRITE_FAILED`/`ModelRoundError`(suspend 类)/`RunInterrupted`/`KeyboardInterrupt` exit 3 且报告 run_id;admission 期间中断同样报告已铸造的 run_id,operator 可只凭它 resume。

---

## 验证测试套件

`tests/test_suspend_resume.py`(34 项,全零网络零费用):

- Slice 1(4 项):staged commit 无残留、write-once 排他、stale epoch fencing、storage 失败类型化;
- Slice 2(4 项):SIGINT/SIGTERM 立即 abort + `interrupted` 事件 + 在途 request orphan;resume attempt 坐标与单次调用预算;
- VM-FAULT-02(9 项参数化):7 个成功剧本 + 2 个终局失败剧本,逐崩溃点断言等价链;
- VM-REPLAY-04(1 项):round-1 SIGINT → 请求逐字节重放等价;
- 重复 suspend/resume 循环(1 项):epoch 1→2→3;
- VM-FAULT-03(2 项):ENOSPC 与 event append I/O 失败;
- Resume gates(8 项):非法/未知 run_id、已 seal、preflight_rejected、链篡改、referenced artifact 缺失、非交互批准不可用、批准拒绝可重试、suspend 类 provider 失败于下一物理 attempt 恢复;
- Preflight 中断重跑(1 项)、admitted 事件窗口补全(1 项)、CLI exit codes(2 项,含 admission 中断 run_id 报告)。

等价性断言基于两个归一化投影:`_semantic_trace`(剔除 lifecycle 事件、suspend 失败簿记、epoch/链坐标/耗时,保留事件类型、operation 坐标、pipeline position、payload、artifact ref 角色)与 `_artifact_byte_map`(`response.json`/`payload.json`/`idea.json`/`grounding.json` 内容哈希,attempt 坐标归一)。

---

## 测试执行结果汇总

```bash
$ python -m pytest tests/test_suspend_resume.py -q
34 passed, 6 warnings in ~15s

$ python -m pytest -q
544 passed, 6 warnings in ~70s

$ python -m compileall -q ai_scientist
(exit 0)

$ python -m black --check ai_scientist/ideation ai_scientist/perform_ideation_temp_free.py tests
55 files would be left unchanged
```

所有新增与存量检查全量绿灯,Evidence Chain 验证闭合。
