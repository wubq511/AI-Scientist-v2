# 002 比较矩阵执行结果与 Promotion 判据（待 Robert 终裁）

**日期**：2026-09-06
**状态**：生成端 8/8 slot 全部 sealed success 并 ingest；评审端 4 对盲评全部完成；**pair 3、pair 4 无法产出 stable AI verdict（诚实结果，未重跑）**。Promotion 裁决权在 Robert。

---

## 1. 执行与费用现状

| 项 | 数值 |
|---|---|
| 生成端 actual（8 slot） | 0.79 CNY |
| 生成端 forfeited（slot 1/3 零 idea quarantine） | 0.33 CNY |
| 生成端合计 | 1.12 CNY（远低于 5.00 重审批阈值 / 30.00 硬上限） |
| 评审端台账（22 笔） | 2.15 CNY（Kimi 订阅零边际；DeepSeek 全部 off-peak） |
| 封印 run | 8/8 success，每个 1 finalized idea |
| 执行 pin | ea88dd0f（supersede 链 7 跳，Robert 批准的 Design Epoch） |

## 2. 四对盲评结果（AI 双评审 + 成对盲评，全部 write-once 留证）

| pair | case | overall | fit | intrusion | floor | AI verdict |
|---|---|---|---|---|---|---|
| 1 Materials | 589dbcb3 | challenger 胜 | challenger 胜 | equal | 双 clean | **已入 vault**（challenger 胜） |
| 2 Social | 2a08725c | challenger 胜 | challenger 胜 | baseline 更少 | c1 clean / c2 unresolved | **已入 vault**（challenger 胜） |
| 3 Genetics | 5f3f2126 | incomparable（Kimi position flip：ab tie→ba content_2） | incomparable（同因） | incomparable（ab equal→ba content_1） | 双 clean | **fail-closed 拒绝** |
| 4 Health | 8c6ddd33 | stable challenger 胜 | incomparable（两 slot 均 ab content_1→ba tie，position_flip） | incomparable（evaluator_conflict） | 双 clean | **fail-closed 拒绝** |

补充事实：
- pair 2 的 baseline 臂（slot 3，d65859af）floor unresolved：feasibility_soundness 双评审冲突（primary questionable / second sound）——reducer 已按规则携带该 unresolved，不影响 overall 判定方向，但 Robert 应知情。
- pair 3 的 flip 全部来自 Kimi（slot second）：A/B 向给 tie/equal，B/A 向给出明确偏好——即同内容换位后判断不一致。
- pair 4 的 overall 四方向一致指向 challenger；但 fit 与 intrusion 两个维度无法定论。
- 生成端其余 deterministic Regression Budgets（finish_reasons、重试、截断、成本、延迟）在 ingest 门全部通过（8/8 COMPARISON_IDENTITY_MISMATCH/INPUT_HASH_DRIFT 零异常）。

## 3. 规格判据逐条对照（002 spec 固定 Promotion threshold 节）

判据原文：「4 对完整、challenger 至少胜 3 对、baseline 胜 0 对、fit 至少两对严格改善且无一对变差、unjustified ML intrusion 不增加、Regression Budgets 全部通过」。

| 判据 | 现状 | 结论 |
|---|---|---|
| 4 对完整 | 4 对两臂齐备、双评审 complete、盲评 4 方向齐 | ✅（但 pair 3/4 无 stable verdict） |
| challenger ≥ 3 胜 | 只有 2 对有 stable AI verdict，且都是 challenger 胜 | ❌ 最多 2 胜 |
| baseline 胜 0 | 现有 2 verdict 中 baseline 0 胜 | ✅（暂时） |
| fit ≥ 2 严格改善且无变差 | pair 1/2 严格改善；pair 3/4 fit 不可判 | 无法满足「无一对变差」的全称检验（2 对不可判） |
| intrusion 不增加 | pair 1 equal、pair 2 baseline 更少；pair 3/4 不可判 | 部分满足 |
| Regression Budgets | 8/8 ingest 门通过 | ✅ |

**按规格字面**： incomparable 计入任何一方（canary spec §36「ties and incomparable pairs count for neither arm」），challenger 最多 2 胜 < 3，且 fit/intrusion 的全称检验无法在不可判的 2 对上完成 → **本矩阵无法产出 promote 结论**（non-promote/inconclusive）。

## 4. 待 Robert 裁决的处置选项

程序已强制：不重跑 AI 盲评（`AI_PAIR_NOT_STABLE` write-once，绝不 rerun to taste）。

1. **接受现状（推荐）**：以「2 胜 0 负 2 不可判 + fit/intrusion 部分不可判」如实出 reduction 文档，结论 = 不满足晋升门槛（矩阵 inconclusive）。这符合规格预注册语义；cross-domain-v1 不进 Promotion Gate，也不恢复旧 035 矩阵。
2. **Robert 人工盲评 pair 3/4**：走人工通道 `verdicts/`。注意 reducer 强制一次 reduction 内 AI 与人工混用 fail closed（EVALUATION_PROTOCOL_MISMATCH）——启用人工通道意味着**全部 4 对都走人工判定**（AI verdict 作废出通道，评审费用 2.15 CNY 沉没），Robert 需重做 pair 1/2 的人工盲评。
3. **Design Epoch 重开**：换评审配置（如换第二评审员模型解决 Kimi 位置翻转敏感度）后重新执行受影响 pair——这是新 Design Epoch，需要 Robert 显式批准新的预算与规格修订，当前证据保留为 development/diagnostic。

## 5. 暴露材料声明义务（Robert 已定）

slot 1 baseline 臂（1143a894）在真实 smoke 中被开发者观察，属 development/diagnostic 证据；Promotion 裁决中其权重由 Robert 明示。本报告按此义务披露。

## 6. 证据坐标

- 盲评 reduce 记录：`artifacts/evaluations/pairs/{pair-5e8017d85c25e967, pair-ef345a69ecf04a5f, pair-7341153cf8a39b8f, pair-d14e07c3c59c739f}/reduction/v0001.json`
- AI verdicts：`artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/vault/ai-verdicts/`（2 份）
- 评审共识卡：`artifacts/evaluations/<run_id>/ideas/000000/ai/consensus/v0001.json`（8 份）
- 评审台账：`artifacts/evaluations/evaluation-cost-ledger.json`（22 笔，total 2.15）
- 生成端台账：包内 `spend-ledger.json`（8 entries + 2 forfeited，total 1.26 含历史 smoke 0.14）
- packet sha（派生自 ingest 后 sealed 证据，已与 reduce 复核一致）：pair 1 7887c361…、pair 2 0247acce…、pair 3 b4c67e21…、pair 4 83e122e8…
