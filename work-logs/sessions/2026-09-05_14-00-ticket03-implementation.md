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