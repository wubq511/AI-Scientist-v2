---
title: 交付独立复核与稳定的成对盲评
type: implementation
status: open
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

- [ ] 相同七维 prompt 和证据可发给两个隔离 evaluator；配置和实际响应保留 exact model ID 与 model family，不能把同模型的两个人设当两位独立模型。
- [ ] 单条每维只有两方有效、同 verdict 才形成共识；一致负面保留为负面；冲突和弃权为 unresolved；无效/缺失响应另行标记。
- [ ] pair packet 不含 arm 身份、成本与预期 winner；每位 evaluator 独立完成 A/B 与 B/A，共四次，不在同一上下文提醒其保持前次答案。
- [ ] 程序还原匿名内容后，只有四个有效结果一致才输出稳定 winner 或 tie；其余为 incomparable；质量下限独立保留。
- [ ] 模型不自填来源哈希或作者身份；跨包响应、假引文和协议版本错配不能合并。
- [ ] 有效结果不能因方向不理想而重跑；无效格式显式记录失败，任何修复调用都有物理调用和成本记录。
- [ ] fixtures 证明一致、负面、分歧、弃权、换位翻转、不同 evaluator 的偏好冲突和无效响应均得到正确外部状态。
- [ ] 真实 smoke 的基础计划固定为单条两次加合成 pair 四次；执行前提供模型配置、token/费用边界与出站范围。当前 slot 1 若作诊断演示，披露暴露，不作 prompt 优化后的独立测试证据。
- [ ] 真实报告包含引文、已知缺陷检出、误报/弃权、分歧、换位、调用/延迟/费用；没有专家 gold 时不报告科研准确率，没有人工计时不估造节省比例。
- [ ] 编码验收和真实模型效果验收分开。无付费授权时交付可执行入口与离线报告，明确真实 smoke 尚未执行；有授权时交付六次真实结果与失败记录，不能只交 prompt。

## Blocked by

- [交付单条 idea 的 AI 评审与证据卡](01-deliver-single-idea-ai-evaluation.md)

## Handoff

本票完成后，可独立评审单条或一对 idea，无需接入正式 comparison。下一票可基于离线稳定合同编码；正式启用仍需真实 smoke 达到规格中的最低检错要求。
