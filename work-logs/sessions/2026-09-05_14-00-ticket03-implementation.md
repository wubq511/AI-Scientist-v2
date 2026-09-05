# Session 记录 - 2026-09-05 14:xx（ticket 03 实现会话）

**[进行中] ticket 03 接入 comparison：离线编码验收完成，待文档回写与 commit**

**工作内容：**
- 按 [03-integrate-comparison-and-migrate-current-matrix](docs/wayfinder/ai-assisted-ideation-evaluation/tickets/03-integrate-comparison-and-migrate-current-matrix.md) 实现 AI 评审与 comparison 的接入（Explore subagent 先出 10 项代码结构报告）。
- 新模块 `ai_scientist/ideation/evaluation_protocol.py`：write-once `evaluation-protocol-manifest.json`（`evaluation-protocol-manifest-v1.0.0`），绑定 protocol id `ai-review-evaluation-protocol-v1`、aggregation rules、prompt 版本、11 项材料 schema、review config 哈希与 post-first-output 修订披露；注册时全量重推导，加载时重验 config 绑定（config supersede 后 fail closed）。
- `ai_review.py` 新增只读 `list_ai_review_coverage`（`evaluation-ai-review-coverage-v1.0.0`）：逐 idea 覆盖四态 + `unaggregated`，复用 aggregate 的全链重验。
- `comparison.py`：ingestion coverage 改双版本分支（v1 人工通道不变 / v2 AI 通道），missing/invalid/unaggregated fail closed，complete_resolved/complete_unresolved 可 ingest，双通道并存 `EVALUATION_CHANNEL_CONFLICT`；`ComparisonVault` 增 write-once `ai-verdicts/` 独立通道（与 Robert 人工 `verdicts/` 分离，AI verdict schema `comparison-ai-verdict-v1.0.0`，绑 packet hash）；`validate_ai_verdict_document` / `ai_verdict_to_display`（content→display 投影，role-anchored 枚举跨映射方向验证）/ `ai_verdict_facts`；`reduce_prompt_comparison` 增 `ai_verdicts` + `evaluation_protocol` 参数——AI verdict 消费必须注册协议（无协议 `EVALUATION_PROTOCOL_MISMATCH`，旧 Gate 继续拒绝），AI+人工混用 fail closed，9 个原门槛逐项不变，新增 `ai_quality_floor_unresolved`（未决底线拒绝晋升）与 `evaluation_protocol`（修订披露写进 reduction 文档）两门；无 AI verdict 时 reduction 字节不变（已测）。
- 新模块 `comparison_ai.py`：`consume_pair_reduction`（定位唯一 complete+stable 还原记录并全链重验）与 `record_comparison_ai_verdict`（经 package 的 `evaluation-protocol-pin.json` 校验 config 绑定后写入 vault，write-once）。
- 新模块 `migration.py`：冻结 package 文件核验（六文件相对布局 + 哈希）、handoff manifest 双向校验、ledger recency 比较（same/local_newer/remote_newer/ambiguous fail closed）。
- 新模块 `evaluation_costs.py`（subagent 实现，已验收）：独立评审费用台账 `evaluation-cost-ledger-v1.0.0`（hash-chain、单/双评审/修复三类条目、物理调用数、CNY 费用）+ `merged_cost_report` 合并口径（含未授权支出披露）。
- CLI 新增 8 个 evaluation 子命令（build/register-evaluation-protocol、list-ai-coverage、record-comparison-ai-verdict、init/record-evaluation-cost、evaluation-cost-report、verify-migration-package）；import 闭包 pin 更新。
- 测试：`tests/test_comparison_migration_rehearsal.py` 17 项（协议注册拒绝场景、迁移 package 核验、handoff round-trip、ledger recency、双工作区 E2E：双评审→pair 还原→AI verdict→reducer 消费、协议强制、人工路径字节稳定）+ `tests/test_evaluation_costs.py` 23 项（subagent）。
- 投影语义专项验证：三种映射方向 + role-anchored 枚举断言通过（domain_method_fit `challenger_better` 不随显示臂翻转）。

**结果：**
- ✅ 全量 pytest **883 passed**（基线 843 + 40）；compileall 通过；改动文件 black 通过；CLI smoke（cost ledger 两次记账、协议注册链、list-ai-coverage）通过。
- ✅ 真实迁移/真实 smoke 未执行（无授权）；rehearsal 为离线双工作区证明。

**问题与状态：**
- 文档回写由后台 subagent 进行中（Promotion Proposal 修订附录、VM-QUAL-04、authoring contract 更新、迁移操作手册、ticket 03 关票、map/CONTEXT）。

**Code review（双轴，871a813 基线）：**
- Standards 轴：5 项可行动发现已修——CLI 死参数 --pair-index、协议 manifest 同秒归档覆盖（改 exclusive-create 序列号）、comparison_ai 重复常量改 import、reducer Gate 5/5b 投影去重、migration 死参数与 _now 重复。
- Spec 轴：3 项发现已修——verify_generation_package_compatibility 跨 slug 拼凑改单 package 定位（歧义/篡改 matrix fail closed）；_ai_coverage_for_run 吞篡改错误改 fail closed（re-raise）；补两项关键测试：完整 4 对 AI 矩阵 promote/reduce E2E（gates 2-4 消费 AI verdicts）与无 AI 参数 reduction 字节稳定 golden 断言；漂移工作区拒绝测试（EXECUTION_CODE_PIN_MISMATCH + stale pin 保留）补齐 ticket AC。
- 计数修正：文档 13/14 项与 879 passed 全部更正为 17 项 / 883 passed。

**相关 Commit：**
- 196b566 协议 manifest → dd238c4 coverage → 6fb0d98 AI verdict 通道+reducer 门 → 20b702b comparison_ai 桥 → 5dfd6a5 migration+cost ledger → 27db76e CLI → 67aba35 测试 → 3e11f64/5d40c13 文档 → 6138d3b work-log → c0e879a standards 修复 → 3706b05 spec 修复。
# Session 记录 - 2026-09-05 21:xx（三项 Robert 决定落账）

**工作内容：**
- Robert 批准第 1、3 项并回答第 2 项后，执行三项决定的落账：
  1. **评估协议修订批准 → 已注册**：`evaluation build-evaluation-protocol`（骨架从运行代码 + 已注册 config 重推导）→ `evaluation register-evaluation-protocol --registered-by Robert`。`artifacts/evaluations/evaluation-protocol-manifest.json` registered_at 2026-09-05T13:45:29Z，SHA-256 `8dc34cfa75396d12fcd1136d22a9ec8a6f560d261ee4097b38f53002b87f0847`，绑定 config `807886…dce30`。修订版 Promotion Gate 对 AI 记录的消费自此可用；旧 Gate 保留并继续拒绝 AI 结果。
  2. **slot 1 处置 → AI 双评审**：核实中发现 runbook 4(b) 原文「slot 1 人工 + 其余 7 条 AI」与 reducer 混用 gate 矛盾（代码正确：任一 AI verdict 存在则全部 8 条结果必须同通道，混用 `EVALUATION_PROTOCOL_MISMATCH`，spec §138「八条结果统一同一评估协议」）——文档错误，代码符合 spec。向 Robert 说明并修正后，Robert 选 AI 双评审（路径 a）；暴露材料以 development/diagnostic 身份参与，Promotion 裁决明示权重。
  3. **评审费用上限 → 不设固定总额上限**：授权边界 = 逐次调用前确认 + 台账逐笔记账 + 每 slot `evaluation-cost-report` 合并披露；量级依据（smoke 实测 token 推算）：4 对 pair 全 AI 评审 DeepSeek 预期 ≈2.3 CNY（单条 8 次 ≈0.17 + pair 方向 8 次 ≈0.12，Kimi 订阅边际 0），含修复重试最坏 ≈4.6 CNY；显著超量级暂停汇报。
- runbook 修正三处：状态行（未批准 → 已批准待执行）、前置条件 1（批准 + manifest 哈希落账）、前置条件 5（不设上限的授权边界）、第 4 节（选定路径 a + 更正 4(b) 语义 + 声明暴露处理方式）、第 3 节第 4 步（ingest/reduce 为库函数直调，无 CLI 包装——修正「沿用既有 comparison CLI」的失实表述，装配以 rehearsal 测试为准）。
- map.md 增 2026-09-05 决策行；ticket 03 未完成项更新为已批准状态。

**结果：**
- ✅ 协议注册链 CLI 验证通过（build → register → 注册后 manifest 字段完整）。
- 真实迁移仍未执行（下一步按 runbook 第 2 节建 pin worktree `d733ffed…` 后从第 1 步开始）。

# Session 记录 - 2026-09-05 22:xx（真实迁移启动：slot 1 归账）

**工作内容：**
- Explore subagent 调研四项执行机制，关键发现：(1) 主区 .env 含 Moonshot 三键会被 pinned with-project-env 拒绝（仅允许单条 DEEPSEEK_API_KEY）→ worktree 单独写最小 .env 规避；(2) production admission 的 yes 必须 tty 交互输入，无非交互通道（APPROVAL_UNAVAILABLE fail closed），机器禁止代打；(3) slot 1 的单条双评审已被真实 smoke 完成（1143a894 idea 0 complete_resolved、floor clean、consensus sha 133bbe49）。
- 真实迁移准备：建 pin worktree `AI-Scientist-v2-pin`（d733ffed，clean）；冻结包 + 4 case workshops/corpora 复制；六文件双侧哈希核验全过；ledger recency same_state；worktree verify-migration-package CLI 不存在（旧代码，符合预期，用逐文件哈希核验）；evaluation-protocol-pin.json 已生成（config 8078…dce30）；evaluation-cost-ledger.json 已初始化（created_by Robert）。
- Robert 首跑 run-index 2 被 `PREVIOUS_SLOT_NOT_INGESTED` 拒绝——串行纪律正确生效：slot 1 替换 run 1143a894 从未 ingest 归账（ledger 0 entries）。
- 归账：1143a894 按**矩阵 slot 1** ingest（非 run_index 2；LEDGER_SLOT_DRIFT 首次失败后依据 _validate_ledger_arithmetic frozen-slot-order 规则与 test_ledger_v13_forfeited_accounting 先例更正）——quarantine 记 slot 1 forfeit 0.10，替换 run 以 run_index 1 ingest，actual 0.08（2 attempts，terminal success）。ledger 现状：entries=[slot1 1143a894 0.08]，forfeited=[966d0fdc 0.10]，total 0.32，status ingesting。
- ledger 同步 worktree，recency same_state 复核；authorize_next_comparison_run(run_index=2) dry-run 通过（projected ceiling 7.40 ≤ 30.00，total 0.32 < 5.00 阈值）。

**结果：**
- ✅ slot 2 启动门已开，等 Robert 交互重跑冻结命令（yes 批准）。
- 注意：`authorize_next_comparison_run` 与 ledger ingest 的 run_index 语义 = **矩阵 slot 序号**（替换 run 归其占用的 slot，不按执行顺序递增）。

# Session 记录 - 2026-09-05 23:xx（slot 2 全链完成：run 2 + pair 1 AI 判定入 vault）

**工作内容：**
- Robert 交互执行 run-index 2 成功：run `8a136ac4-8ac0-4545-9624-63d8270c9663`（case 589dbcb3，cross-domain-v1 臂）sealed success，1 finalized idea。
- handoff 回收：生成端 export sanitized evidence + `migration_handoff_manifest`（42 文件含 spend-ledger、run 全链、evidence 导出）→ 复制回评估端 → `verify_handoff_manifest` 全过。
- 归账：slot 2 actual 0.13 CNY（3 attempts）ingest 进 ledger（total 0.45）。
- 完整 `ingest_comparison_result` 首跑 `EVALUATION_ARTIFACT_MISSING`（coverage 门正确生效）→ 先做双评审再 ingest。
- run 2 idea 0 双评审：export-review-package → primary（DeepSeek max，237s，0.2443 CNY，一次 validated）+ second（Kimi 首调 HTTP 504 网关超时 300s 保留原错误 → 重试 292s validated，订阅零边际）→ aggregate `complete_resolved`、floor clean、0 conflict。评审台账 2 笔（total 0.24 → 0.47 前段）。
- **合同级修正（Robert 批准选项 A）**：`export-pair-package` 对 pair 1 `PAIR_PACKET_BLIND_LEAK`——baseline 臂 sealed idea 的 Related Work 自引 3 处 `Paper ID <哈希>`（declared-grounding 风格，属 idea 正文内容），与 pair 盲评 secrets 清单里的 paper_id 冲突。诊断确认：哈希指向共享语料的参考文献而非臂身份，不构成臂泄漏；单评审无此检查、slot 3-8 大概率复现。修复：`ai_pair_review.py` secrets 移除 paper_id（run/case/profile/pair 身份保持 fail closed）+ 回归测试 `test_export_pair_package_allows_paper_ids_inside_idea_text` + authoring contract 修正注记。全量 **884 passed**（基线 883+1）；commits `73e1091`+`99ee349`。
- pair 1 盲评（`pair-5e8017d85c25e967`）：4 次调用全一次 validated（primary ab 99s/ba 90s，second ab 154s/ba 127s），reduce `stable`：overall_preference content_2（=challenger）、fit content_2、intrusion equal、双臂 floor clean。评审台账 pair_review 2 笔（DeepSeek 0.23 / Kimi 0.00，评审台账 total 0.47）。
- `record-comparison-ai-verdict` 写入 vault `ai-verdicts/`（write-once）：packet sha 7887c361…（经 pair-filtered matrix + 两臂 ingest 重推导，facts_sha256 与之一致），document sha f8b69052…。
- ledger 同步 worktree，recency `same_state`。

**结果：**
- ✅ pair 1 AI 判定通道完成：challenger（cross-domain）胜、fit 优、intrusion 平、floor 双 clean。与 Robert 已选 AI 双评审路径一致；暴露材料（baseline 臂）以 development/diagnostic 身份参与，Promotion 裁决时明示权重。
- 注意：`validate-pair-review` 重复执行会追加 vNNNN（同响应 supersedes 链，head 判定不变）——操作时 validate 一次即可。
- 注意：`build_pair_packets_from_ingested` 要求全部 pair 两臂齐备；单 pair 场景用 pair-filtered matrix + case-filtered mappings 构包（packet 字节只依赖该 pair 的行）。
- 费用：生成端 total 0.45；评审台账 total 0.47（primary single 0.24 + repair 0.00 + pair DeepSeek 0.23 + Kimi 0.00）。
---

# Session 记录 - 2026-09-06 00:xx（批内预授权规格修订 + 全自动执行启动）

**工作内容：**
- Robert 批准「规格修订全自动（最快）」：批准 002 spec §26 + canary spec §123（禁止项）修订，将「batch cost approval / automatic typing of yes」改为「write-once 批内预授权」合法通道（禁止项保留自动打 yes 与隐藏授权）。
- 实现：新建 `ai_scientist/ideation/comparison_preauthorization.py`（schema comparison-preauthorization-v1.0.0；build/write-once/covering 解析；env `COMPARISON_PREAUTHORIZATION`；错误码 PREAUTHORIZATION_UNREADABLE / _CEILING_DRIFT / _SLOT_NOT_COVERED 全 fail closed，env 已设不覆盖绝不回退交互提示）；admission step 8 接入（命中时 approval 换 preauthorization_admission_field，出处逐字入 Run Admission）。测试 12 条（tests/test_comparison_preauthorization.py），import contract 闭包补 `comparison_preauthorization`。commit `4586ea5`，全量 896 passed。
- Kimi「限流」复核（Robert 要求）：三次非流式调用全部精确 ~300s 被 nginx 504 掐断、唯一成功 291.6s 压线、流式探针 351.8s 完整成功 → **非限流，是网关 300s 硬超时**；流式为后续 Kimi 评审固定方案（send_pair_stream.py / send_single_stream.py）。
- 执行 pin governed supersede 链（Robert 逐项批准）：2d368976 → 4586ea5（预授权修订）→ 22bbe25（幂等重入）→ 316dbc4（epoch 接受硬ening）→ bdb3156（测试收尾），记录 seq-2…seq-5 归档齐全。
- 幂等 reservation 重入（Robert 选定方案）：reserve_comparison_slot 对「同 argv sha + authorization + price table + commit ∈ 当前 pin ∪ superseded epochs」的 seq-1 重入复用原 reservation（reused=True）；任何漂移仍 COMPARISON_SLOT_ALREADY_RESERVED；quarantined slot 仍必须走 seq-2 替换链。动机：slot 3 首次启动先写 reservation 后被 MISSING_CREDENTIAL 拒（零花费），重跑被 write-once 挡死且无治理出口。commits `22bbe25`/`316dbc4`/`bdb3156`；88/88 + 全量 896 passed。
- slot 3 首跑 ef939515 sealed **failed**：generation 0 耗尽预算（INVALID_ARGUMENTS_JSON → GATE_REJECTED×2 → FINAL_ROUND_FINALIZE_REQUIRED），0 idea，RETRIEVAL_BACKSTOP_FAILED，actual 0.23；quarantine（ZERO_FINALIZED_IDEA）→ forfeited 0.33 入账 → 替换 run d65859af（run-003-seq-2）sealed success 1 idea。
- 全自动通道验证：slot 3 两次 admission 的 cost.approval 均记录 confirmed_with=batch_preauthorization、doc sha 0eee415d、7.08 上界；slot 4 试启动被 PREVIOUS_SLOT_NOT_INGESTED 正确拒绝（slot 3 未 ingest）。
- slot 3 评审链进行中：export-review-package 完成（request sha be79a5b9）；流式双评审调用后台执行。

**结果：**
- ledger：entries=[slot1 0.08, slot2 0.13]，forfeited=[0.10, 0.23]，actual 0.21，status ingesting。评审链 slot 3 调用中。
- .env 恢复单键纪律（ideation 端），评审端四键副本在 /tmp（0600）。

**决策记录：**
- 幂等重入接受 governed epoch commit（而非仅当前 pin）：reservation 写于 4586ea5、HEAD 已至 22bbe25，硬比较会自锁；与 quarantine 的 admission-commit 规则（接受 superseded epoch）一致。
- Kimi 评审一律流式（网关 300s 超时，非限流）；DeepSeek 保持非流式 + response_format json_object。
- ingest 顺序纪律确认：先双评审（EVALUATION_ARTIFACT_MISSING 门）再 ingest，再下一 slot 启动（PREVIOUS_SLOT_NOT_INGESTED 门）——流水线并行仅限「当前 slot 生成 ↔ 前一 slot 评审」。

**相关 Commit：**
- 4586ea5 add: Robert-approved batch preauthorization for frozen comparison slots
- 22bbe25 add: idempotent reservation re-entry for identical frozen slot relaunch
- 316dbc4 fix: idempotent reservation re-entry accepts governed code epochs
- bdb3156 test: keep CLI duplicate-launch guard ahead of idempotent re-entry

# Session 记录 - 2026-09-06 00:xx 前后（slot 6/7/8 全自动完成 + pair 3/4 盲评，矩阵 8/8）

**工作内容（全自动批处理，Robert 预授权范围内）：**
- slot 6（baseline arm pair 3，case-5f3f2126）：run `8e757f49` sealed success（1 idea，3 attempts，actual 0.11）。双评审（Kimi 流式 75s / DeepSeek 161s）complete_resolved、floor clean；ingest 0.11；ledger actual 0.62（6/8）。
- slot 7（challenger arm pair 4，case-8c6ddd33）：run `055879c7` sealed success（2 attempts，actual 0.08）。双评审 complete_unresolved、floor clean——6/7 维一致，唯一冲突 target_contribution_overlap（primary materially_different vs second partial_overlap）；ingest 0.08；ledger actual 0.70（7/8）。
- slot 8（baseline arm pair 4）：run `fa0557eb` sealed success（2 attempts，actual 0.09）。双评审 complete_unresolved、floor clean——6/7 维一致，同一 target_contribution_overlap 冲突模式；ingest 0.09；ledger actual 0.79（**8/8 全部 ingest 完成**，forfeited 0.33，status ingesting）。
- pair 3 盲评（pair-7341153cf8a39b8f）：4 方向全一次 validated，Kimi 流式 37s/62s 零失败。reduce = **全三维度 incomparable**（Kimi slot second 在 ab 给 tie/equal、ba 给 content_2/content_1，position_flip）。`record-comparison-ai-verdict` fail-closed 拒绝（AI_PAIR_NOT_STABLE）——按合同不重跑，诚实入账。评审台账 +0.40（DeepSeek ab 0.2414 + ba 0.1543）。
- pair 4 盲评（pair-d14e07c3c59c739f）：overall_preference **stable content_1**（=challenger 055879c7），但 domain_method_fit position_flip（两 slot 均 ab content_1 / ba tie）、unjustified_ml_intrusion evaluator_conflict → AI verdict 仍 fail-closed 拒绝（非 stable 判定不能进 reducer）。floor 双 clean。评审台账 +0.26（DeepSeek 0.1482 + 0.1153）。
- 评审台账现状：22 entries，total 2.15 CNY（Kimi 全部订阅零边际）。

**矩阵 4 对现状（全 AI 评审通道）：**
- pair 1（case-589dbcb3，Materials）：challenger 8a136ac4 胜（overall+fit content_2，intrusion equal，双 floor clean）→ AI verdict 已入 vault。
- pair 2（case-2a08725c，Social）：challenger c9bf7255 胜（overall+fit content_1，baseline intrusion 更少，floor content_1 clean/content_2 unresolved）→ AI verdict 已入 vault。
- pair 3（case-5f3f2126，Genetics）：全维度 incomparable（Kimi 位置翻转）→ 无 AI verdict。
- pair 4（case-8c6ddd33，Health）：overall challenger 胜但 fit/intrusion 维度翻转 → 无 AI verdict。

**结果：**
- 生成端矩阵 8/8 完成（actual 0.79 + forfeited 0.33 = 1.12，远低于 5.00 重审批阈值与 30.00 硬上限）；评审端 22 笔 2.15 CNY。
- 待 Robert 终裁：pair 3/4 的 incomparable 处置（规格语义「ties and incomparable count for neither」→ 2 胜 0 负 2 incomparable 不满足「至少胜 3 对」→ 矩阵结论倾向 non-promote/inconclusive；处置选项：接受现状出 reduction、或 Robert 人工盲评通道补 pair 3/4——需 Robert 决定，不重跑 AI）。
- 注意：pair 3/4 的 reduction 记录与全部证据链已完整留证（write-once），任何时候可复核。
