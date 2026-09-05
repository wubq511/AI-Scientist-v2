---
title: 交付独立复核与稳定的成对盲评
type: implementation
status: closed
assignee: null
blocked_by:
  - 01-deliver-single-idea-ai-evaluation.md
---

**Triage:** ready-for-agent

## Parent

[AI 辅助 Ideation 评审规格](../../../agents/ai-assisted-ideation-evaluation-spec.md)

## What to build

把同一材料包交给两个不同 model families 的独立评审，汇总逐维共识与分歧；从两个匿名 idea 构建可换位的 pair 评审，交付可回链的稳定比较结果或 incomparable。复用第一票的材料、输出持久化和 schema 校验，不让第二位评审看到第一位答案。

使用 prompt-engineer 编写成对模板，涵盖 domain-method fit 与 ML intrusion。交付一个单条与一个独立合成 pair 的小规模试评入口、fixtures 和报告格式；不增加第三模型、专家平台或多轮辩论。

## Acceptance criteria

- [x] 相同七维 prompt 和证据可发给两个隔离 evaluator；配置和实际响应保留 exact model ID 与 model family，不能把同模型的两个人设当两位独立模型。（评审执行配置 write-once 强制异 family/异 exact model id（`REVIEW_CONFIG_FAMILIES_NOT_DISTINCT`/`REVIEW_CONFIG_MODELS_NOT_DISTINCT`），family 为声明值逐字记录并标注未认证；slot 目录 `ai/primary/`、`ai/second/` 完全隔离）
- [x] 单条每维只有两方有效、同 verdict 才形成共识；一致负面保留为负面；冲突和弃权为 unresolved；无效/缺失响应另行标记。（`aggregate-review`：consensus/conflict/abstained/incomplete_evaluator 四态；coverage ∈ {complete_resolved, complete_unresolved, invalid, missing}，invalid/missing/unvalidated 独立记账不能伪装完成；一致 `unsound` 共识保留负面且底线 violated）
- [x] pair packet 不含 arm 身份、成本与预期 winner；每位 evaluator 独立完成 A/B 与 B/A，共四次，不在同一上下文提醒其保持前次答案。（方向 payload key+文本双向扫描 `PAIR_PACKET_BLIND_LEAK`；换位对称性专项断言；`(slot, direction)` 四个独立上下文各自 write-once 存储与校验）
- [x] 程序还原匿名内容后，只有四个有效结果一致才输出稳定 winner 或 tie；其余为 incomparable；质量下限独立保留。（`reduce-pair-review` 盲映射还原：position_flip/evaluator_conflict/incomparable_judgment/missing_valid_record 逐因记录；每臂质量底线取自其双评审共识记录，不被整体偏好覆盖）
- [x] 模型不自填来源哈希或作者身份；跨包响应、假引文和协议版本错配不能合并。（provenance 恒 user_supplied、author_type=AI 由程序写入；引用逐字核验 + 跨方向引用失败专项测试；`PAIR_REQUEST_DRIFT`/`PAIR_PACKAGE_DRIFT`/`POLICY_DRIFT`/`REVIEW_CONTRACT_MISMATCH` 阻断；还原时记录↔响应哈希链与重推导逐字比对）
- [x] 有效结果不能因方向不理想而重跑；无效格式显式记录失败，任何修复调用都有物理调用和成本记录。（程序无重评路径；还原记录 write-once + supersedes；无效响应保留原始字节并显式报错；修复调用的物理计数/费用责任写入 smoke runbook 第 0/3 节）
- [x] fixtures 证明一致、负面、分歧、弃权、换位翻转、不同 evaluator 的偏好冲突和无效响应均得到正确外部状态。（`tests/test_ai_pair_review.py` 17 项 + `tests/test_ai_review_evaluation.py` 中 ticket 02 新增 14 项，逐场景对应）
- [x] 真实 smoke 的基础计划固定为单条两次加合成 pair 四次；执行前提供模型配置、token/费用边界与出站范围。当前 slot 1 若作诊断演示，披露暴露，不作 prompt 优化后的独立测试证据。（[ai-review-smoke-runbook.md](../../../agents/ai-review-smoke-runbook.md)：六次调用序列、config 模板含 real_call_authorization、报告字段、slot 1 暴露披露要求）
- [x] 真实报告包含引文、已知缺陷检出、误报/弃权、分歧、换位、调用/延迟/费用；无专家 gold 不报科研准确率，无人工计时不估造节省比例。（runbook 第 4 节报告必填字段表 + 禁止表述清单）
- [x] 编码验收和真实模型效果验收分开。无付费授权时交付可执行入口与离线报告，明确真实 smoke 尚未执行；有授权时交付六次真实结果与失败记录，不能只交 prompt。（离线证据 [ai-pair-review-offline-validation-evidence.md](../../../research/ai-pair-review-offline-validation-evidence.md) 顶部与「未执行项」明确真实 smoke 未执行、无付费授权）

## Blocked by

- [交付单条 idea 的 AI 评审与证据卡](01-deliver-single-idea-ai-evaluation.md)

## Handoff

本票完成后，可独立评审单条或一对 idea，无需接入正式 comparison。下一票可基于离线稳定合同编码；正式启用仍需真实 smoke 达到规格中的最低检错要求。

## Resolution

2026-09-05 交付（离线编码验收）：

- **评审执行配置**：`evaluation register-review-config`（workspace 级 write-once `artifacts/evaluations/ai-review-config.json`），封闭 schema、异 family/异 model id 强制、pinned prompt 版本绑定、可选 `real_call_authorization` 声明；config SHA-256 进共识/还原记录。
- **布局迁移**：单评审响应/记录/证据卡迁入 per-slot 目录（`ai/primary/`、`ai/second/`），`ai/consensus/` 存双评审共识；v1 人工 artifact 与单评审行为零回归。
- **双评审**：`evaluation aggregate-review` 逐维共识/分歧/弃权/不完整记账 + coverage 四态 + pre-registered 质量底线 + 中文共识卡（md/html）；聚合时对每 slot 记录做全链完整性重验（含响应文本哈希链与记录↔响应重推导比对）。
- **成对盲评**：`ai_scientist/ideation/ai_pair_review.py` + `evaluation export-pair-package` / `import-pair-response` / `validate-pair-review` / `reduce-pair-review`；确定性匿名 pair 包（C###/A###/B### source 编排 + 私有 blind mapping/registry）、四上下文独立评审、盲映射还原（stable winner/tie 或 incomparable + 原因分类学）、质量底线独立携带、中文还原报告（md/html）。
- **成对模板**：`ai-review-prompt-pair-v1.md`（`pair-review-v1`，prompt-engineer 编写，含 domain-method fit 与 unjustified-ML-intrusion 判断定义、tie≠incomparable、引用与「推断：」规则、五个合成边界例），SHA-256 pin 于 `contract.py`。
- **CLI**：六个新子命令 + `--evaluator-slot` 参数；stdlib-only import 闭包扩展并 pin（`tests/test_ideation_import_contract.py`）。
- **验证**：全量 pytest **841 passed**（基线 810 + 新增 31）；black/compileall 通过。真实六次 smoke **未执行**（无付费授权），执行入口与报告字段见 [ai-review-smoke-runbook.md](../../../agents/ai-review-smoke-runbook.md)。
- **合同与矩阵**：[ai-review-authoring-contract-v2.md](../../../agents/ai-review-authoring-contract-v2.md) 追加双评审与成对章节；validation-matrix 新增 VM-QUAL-03（versioned addendum 二）；CONTEXT.md 新增 6 个术语。
