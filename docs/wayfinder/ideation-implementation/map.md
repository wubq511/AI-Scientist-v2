---
title: Implement the Auditable Ideation-Only Pipeline
label: wayfinder:map
status: closed
---

# Implement the Auditable Ideation-Only Pipeline

## Authority

- [Implementation specification](../../agents/ideation-pipeline-spec.md)
- [Validation Matrix](../../agents/validation-matrix.md)
- [Delivery and Handoff](../../agents/delivery-and-handoff.md)

Ticket frontmatter is authoritative for status and blocking edges. Each ticket is a tracer-bullet implementation slice, and every acceptance set cites the Validation Matrix rows it delivers. Tickets 035/036 remain in the planning map for Canary-stage parameter decisions and are not duplicated here.

## Tickets

1. [Establish the testable ideation foundation](tickets/01-establish-the-testable-ideation-foundation.md)
2. [Approve one Workshop File](tickets/02-approve-one-workshop-file.md)
3. [Approve one Target Reference Corpus](tickets/03-approve-one-target-reference-corpus.md)
4. [Admit an Ideation Run without paid work](tickets/04-admit-an-ideation-run-without-paid-work.md)
5. [Return one audited BM25 Retrieval Result](tickets/05-return-one-audited-bm25-retrieval-result.md)
6. [Record one validated DeepSeek model round](tickets/06-record-one-validated-deepseek-model-round.md)
7. [Seal one grounded Ideation Run](tickets/07-seal-one-grounded-ideation-run.md)
8. [Correct model-fixable actions](tickets/08-correct-model-fixable-actions.md)
9. [Seal explicit non-success outcomes](tickets/09-seal-explicit-non-success-outcomes.md)
10. [Suspend and resume an interrupted Ideation Run](tickets/10-suspend-and-resume-an-interrupted-ideation-run.md)
11. [Validate and export a trustworthy Evidence Chain](tickets/11-validate-and-export-a-trustworthy-evidence-chain.md)
12. [Evaluate every finalized idea after seal](tickets/12-evaluate-every-finalized-idea-after-seal.md)
13. [Contract the legacy path and prove handoff readiness](tickets/13-contract-the-legacy-path-and-prove-handoff-readiness.md)

## Decisions so far

- [Establish the testable ideation foundation](tickets/01-establish-the-testable-ideation-foundation.md)：以三类精确依赖合同、入口传递 import allowlist、Python 3.13 clean-environment 全量 pytest 与逐字节 CLI baseline 建立零 runtime 行为漂移的可测试地基。
- [Approve one Workshop File](tickets/02-approve-one-workshop-file.md)：以离线 prepare/validate/approve 三阶段生命周期隔离、严格四段 canonical rendering、exact/normalized/8-token leakage 确定性门禁与独立评审人九项语义检查建立零泄露、带不可篡改 attempt provenance 的 Workshop 审批边界。
- [Approve one Target Reference Corpus](tickets/03-approve-one-target-reference-corpus.md)：以生命周期隔离的 build/validate/approve 流程、冻结权威证据政策（修复 3 篇损坏摘要与 18 条缺失 venue 警告）、全量 fail-closed 11 项确定性检验器与严格 Quarantine 隔离建立自包含的语料审批边界，并完成全量 237 个 Targets 的离线零成本预处理验证。
- [Admit an Ideation Run without paid work](tickets/04-admit-an-ideation-run-without-paid-work.md)：以七参数 new-run CLI、exclusive-create run root、canonical write-once request/admission 与连续 hash chain 事件、versioned CNY 价格表（hash pin + 峰谷时段）及 exact-`yes` 交互批准建立九步 fail-closed 准入边界；任何 preflight 失败留存 `preflight_rejected` 证据且无 admission、无付费路径，入口 import 副作用消除。
- [Seal explicit non-success outcomes](tickets/09-seal-explicit-non-success-outcomes.md)：以固定优先级 finalization gate（hygiene parse 前照扫 raw bytes → structure → grounding → duplicate，每轮只报最高优先级）、版本化 payload hygiene 模式列表（命中即 terminal，不回灌不掩盖）、controller/provider/retriever_evidence 三类封闭 terminal 失败词汇与完整 artifact inventory，使 hygiene 命中、run 级 retrieval backstop 与确定性 adapter/retriever/evidence 失败都产生可解释的 terminal `failed` seal；suspend 类失败与 storage/IO 失败保持 unsealed（ticket 10 接管）。
- [Suspend and resume an interrupted Ideation Run](tickets/10-suspend-and-resume-an-interrupted-ideation-run.md)：以 run-local staged atomic commit 与 writer-epoch fencing 保证 per-operation 原子性，SIGINT/SIGTERM 立即 abort 并尽力追加 `interrupted` 事件；resume 只凭 exact `run_id` 全量复核链与 admission pins、quarantine approved-window orphan、从 canonical events/artifacts 重建控制态、按剩余工作重估费用并重新批准（新 writer epoch + write-once approval artifact），续跑到与无中断执行等价的 Evidence Chain；确定性失败与证据损坏 fail closed 不可 resume，preflight 中断从头幂等重跑。
- [Validate and export a trustworthy Evidence Chain](tickets/11-validate-and-export-a-trustworthy-evidence-chain.md)：以静态校验器对事件链、seal 与产物做单调哈希及完整性核验，确定性判定 `RUN_CORRUPT` 且不可修复/恢复/封印/导出/重放；以正向白名单导出器（空对象构造、发布门禁全面扫描、原子重命名提交、字节级幂等）导出脱敏证据；以跨 run/路径/符号链接强隔离（拦截私有历史证据作为运行时输入、拦截跨 run 读写与全攻击集）和 write-once attempt 语义杜绝覆盖篡改，并以离线重放验证器证明执行决定论。
- [Evaluate every finalized idea after seal](tickets/12-evaluate-every-finalized-idea-after-seal.md)：以 pinned 版本化七项 rubric 策略（SHA-256 锁定、漂移即 `POLICY_DRIFT`）、sealed + non-corrupt 硬前提、沿事件链逐字节核验的 retrieval 摘录（各层形状 fail-closed）与 Workshop Manifest 绑定的私有 Target comparator 组装可重建 Evaluation Brief；以全确定性 fail-closed validate（封闭 schema、全 hash linkage、封闭 enums、非空 rationale、authoring audit、linear supersedes）提交 write-once 定稿；以只读三态 coverage（corrupt/unevaluable run 单列不计入）交付 VM-QUAL-01；每个 finalized idea 独立计一份 artifact（含 terminal `failed` run 已 committed ideas），全程无 numeric/overall score、无 LLM judgment。
- [Contract the legacy path and prove handoff readiness](tickets/13-contract-the-legacy-path-and-prove-handoff-readiness.md)：删除入口 `legacy` 子命令与全部 legacy 机器，新 ideation entry 传递 import closure 收紧为纯标准库（import guard 双层清单锁定，BFTS/downstream/global Semantic Scholar 不可达）；`requirements.txt` 成为空 runtime 合同，四个 legacy 包移入 `requirements-upstream.txt` 服务 retained 代码；修复入口在 Python ≤3.13 的 `Path` 注解 import 缺陷；Python 3.13.7 clean venv 628 项 pytest 全绿 + 裸 venv CLI 通过，3.12/3.14 候选按矩阵记录；全量 diff 双轴 review 关闭全部阻塞发现（含移除未登记的 `IDEATION_EXECUTE` 隐藏执行开关、DeepSeek 常量单源化）。

## Closure（2026-09-06）

全部 13 张实现票关闭（各票矩阵行 pytest 全绿 + Robert 逐票验收），总终验完成：VM-ENV-01 干净环境全量 899 passed、`compileall`/black 通过、baseline 以来整段 diff 已经双轴 code-review。运行期收尾（canary 执行、扩量裁决、终波豁免）见 [ideation-pipeline map](../ideation-pipeline/map.md)（同日全闭）与 [experiment report](../../research/ideation-delivery-experiment-report.md)。本 map 使命完成，置 closed。
