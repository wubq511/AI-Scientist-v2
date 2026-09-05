# AI 辅助 Ideation 评审

## Goal

让 AI 承担可回链的七维初评与独立复核，Robert 负责工程决策；在现有 evaluation/comparison 工作流中减少人工负担，保留对材料不足、模型分歧和科学结论范围的诚实表达。

规格：[AI 辅助 Ideation 评审规格](../../agents/ai-assisted-ideation-evaluation-spec.md)。

## Decisions so far

- 2026-09-05：Robert 批准 AI 评审方向，要求简约但保证必要的质量与效果；本会话仅设计，编码交其他 agent。
- 2026-09-05：Robert 明确批准三票顺序与依赖，以及 evaluation CLI 和 comparison ingestion/reduction 两个验收边界；不新增 UI。
- 两位评审独立、证据可回链、允许未决；没有第三模型投票或必需的专家平台。小样本 smoke 不被写成跨领域效果证明。
- 使用仓库已配置的 Local Markdown Issue Tracker；frontmatter 的 open/closed 与 blocked_by 决定 frontier，ready-for-agent 作为 triage 标记，不替换 status 语义。
- 2026-09-05：[交付单条 idea 的 AI 评审与证据卡](tickets/01-deliver-single-idea-ai-evaluation.md) — 单评审模式离线编码验收完成：pinned `single-review-v1` 模板与 authoring contract v2 版本族、匿名确定性材料包、`user_supplied` 响应导入、引用逐字核验、七维枚举 + `insufficient_evidence` 弃权、write-once 记录与中文证据卡；19 项新测试、全量 806 passed、v1 人工流程零改动；真实 smoke 未执行，需费用/出站授权。
- 2026-09-05：[交付独立复核与稳定的成对盲评](tickets/02-deliver-independent-and-pairwise-review.md) — 双评审与成对盲评离线编码验收完成：write-once 评审执行配置（两 slot 强制异 model family/异 exact model id，family 为声明值）、per-slot 隔离布局（`ai/primary/`、`ai/second/`）+ `aggregate-review` 逐维共识（一致负面保留、conflict/abstain/invalid/missing 独立记账）、pinned `pair-review-v1` 成对模板、匿名确定性 pair 包（key+文本双向盲泄漏扫描、换位对称）、四上下文独立评审、盲映射还原（仅四有效结果收敛才 stable；position_flip/evaluator_conflict/incomparable/missing_valid_record 逐因记录）、每臂质量底线独立携带、中文共识卡与还原报告；六个新 CLI 子命令；31 项新测试、全量 841 passed、stdlib-only 闭包保持；真实六次 smoke 未执行（无付费授权），执行入口见 ai-review-smoke-runbook。
- 2026-09-05：真实六次 smoke 执行完成（基础 6 + 修复/重跑 8 = 14 次物理调用）——runbook 四个完成条件 4/4；seeded 缺陷 4/4 检出（双模型双方向引用矛盾原文）、单条共识 `complete_resolved`（31/31 引用）、pair 还原三项全 stable 收敛干净臂（37/37 引用）、模型分歧与 position_flip 均为 0；证据报告 [ai-review-real-smoke-evidence.md](../research/ai-review-real-smoke-evidence.md)。执行中发现并落地两项合同级修正：pinned prompt `single-review-v1`→`v2`（审计锚定规则显式化，两次独立失败驱动，commit `dd2f02f`）；执行 config 新增留档 `--supersede`（占位 model id 与 Kimi Code 端点实际 `k3-256k` 不符，commit `902d2af`）。config prompt_versions 相等性改为仅注册时强制（加载只验封闭 schema，版本兼容由每条 request/记录自带 prompt_version 承担）。quote 滑误处理协议（文书性滑误人工更正+台账+重过机检，无出处引文属伪造作废）与 max 思考强度观察记录在证据报告。slot 1 材料已用入真实实验并观察结果，降级 development/diagnostic（原因是开发集污染，与出站无关）。当前 pin：primary=deepseek/deepseek-v4-pro、second=moonshot/k3-256k（Kimi Code 订阅端点 api.kimi.com/coding/v1），双模型统一 max reasoning effort；全量 843 passed。

## Tickets

1. [交付单条 idea 的 AI 评审与证据卡](tickets/01-deliver-single-idea-ai-evaluation.md)
2. [交付独立复核与稳定的成对盲评](tickets/02-deliver-independent-and-pairwise-review.md)
3. [接入比较流程并保留当前矩阵证据](tickets/03-integrate-comparison-and-migrate-current-matrix.md)

## Not yet specified

无阻断离线编码的产品问题。真实 provider/model 配置、出站材料与费用批准属于执行输入，运行前记录；模型效果未验证前不声称已合格。
