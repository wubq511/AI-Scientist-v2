# Delivery and Handoff

版本: v1.0(2026-08-30,经 ticket [Define final delivery and commit sequence](../wayfinder/ideation-pipeline/tickets/030-define-final-delivery-and-commit-sequence.md) 三轮 grilling 由 Robert 批准;该 ticket 随 spec 与实现票单批准而关闭,见末节)

本文档定义从 wayfinder map 到可复现 handoff 的交付链与纪律。它受版本治理——任何修订 = 新版本 + Robert 批准。本契约只定交付规则:实现票单由 to-tickets 的 quiz 环节定,canary 与扩量归 [canary-and-scale-gates.md](canary-and-scale-gates.md),优化晋升归 [promotion-gate.md](promotion-gate.md),验证行定义归 [validation-matrix.md](validation-matrix.md)。本文引用其行 ID 与条款,不重开决策。

## 交付链

```
wayfinder(决策,map 即本仓库 ideation-pipeline)
  → /to-spec(合成一份规格)
  → /to-tickets(tracer-bullet 垂直切片票)
  → /implement(tdd + /code-review + commit,逐票)
  → canary / 终波(按 028)
  → experiment report + interview narrative
```

- **to-spec 启动条件**:ticket 021(本地排序选型)关闭之后。021 的胜方 ranking 是 retriever 实施的直接输入。
- **开放参数**:`reasoning_effort`、`max_tokens`、Workshop 变体三者由 035/036 在 canary 期决定;spec 中将它们显式标为开放点,实现票只建"参数可配置"的口子,不为它们留实现票。
- **map 寿命**:wayfinder map 跨实施期存活,随 035/036 在 canary 期关闭而全闭。035/036 是决策票,只是证据来得晚,不违反 plan-only 纪律。

## 规格(to-spec)

- **一份 spec** 覆盖整个 destination(destination 字面要求),不按波次拆分。
- Problem/Solution 从用户视角写;Implementation Decisions 分节对应契约域,**每节以引用方式点名契约文档与 ticket resolution 作为决策权威**——spec 是索引不是仓库,同 map 原则。Testing Decisions 直接引用 validation matrix 行 ID。
- 落点:`docs/agents/`,committed,是 handoff 证据链的一部分。

## 实现票(to-tickets)

- 落点:`docs/wayfinder/ideation-implementation/`——一个极简 `map.md`(指向 spec 作为权威)+ `tickets/NN-<slug>.md`(to-tickets 本地模板内容 + frontmatter `status`/`blocked_by`,沿用 [issue-tracker.md](issue-tracker.md) 的 frontier 语义)。
- **偏离说明**:to-tickets 默认落 `.scratch/`;本 repo `.scratch` 未被 gitignore,且 handoff 可复现性要求票单可审计,故落 `docs/wayfinder/`。这是刻意的 repo 级适配。`docs/task/` 为 ignored private,排除。
- **切片约束(本票钉死,票单由 quiz 定)**:
  1. 每票 acceptance criteria **必须引用 validation matrix 行 ID**("该票交付 VM-X 行且 pytest 全绿");不接受无矩阵锚点的验收标准。
  2. **第一票 = 地基票**:VM-ENV-01 干净环境 + VM-CONTRACT-024-01 导入守卫 + 034 依赖三文件落地,不改任何运行时行为(006 兼容基线);顺手修正 AGENTS.md 中已过时的 "no automated test suite" 陈述。
  3. 改动既有 ideation 路径时按 **expand–contract** 保基线可运行(006),contract 留到最后一票。
  4. 每票必须映射到至少一个已关闭契约票;映射不上的内容不许进票单(防止实施期偷渡未决策设计)。

## 验收与提交

- **票关闭** = 该票声明的矩阵行 pytest 全绿 + 脱敏摘要入库 + **Robert 逐票验收**(可借 `/code-review` 辅助,对照矩阵与契约)。
- **commit 纪律**:单分支 `codex/isophany-interview-task`;ticket ≠ 单 commit,票内按 tdd 节奏小步提交;每 commit 必须通过全部已存在矩阵行(矩阵"测试归属"行);imperative + `add:`/`fix:` 前缀;契约类变更与其测试同 commit。session log 与回填纪律(record-session-progress 步骤 2)不变。
- **总终验**:全部实现票关闭后,VM-ENV-01 干净 venv + 最小依赖全量跑一遍,并对 baseline 以来整段 diff 做一次 `/code-review`。
- **运行期验收不重复造**:028 的 Scale Gate 是运行期 gate,本文只引用。
- 合并 `main` 与任何远程发布 = 单独批准事项,handoff 完成后另行决定。

## 仓库说明文件

- 凡改变 runtime 行为、命令或契约的票,`AGENTS.md` 随该票同一 commit 同步(AGENTS.md 自身 "keep them current" 要求)。
- `README.md` 维持现有 fork-scope 标注,不动 upstream 正文。
- handoff 收尾时跑一次全文一致性扫尾(neat-freak 场景)。

## Experiment report

- **committed、中文、`docs/research/` 下**;原始证据按 010 留本地,报告只引用路径与脱敏摘要。
- 七节骨架:
  1. 目标与范围(逐字使用末节"固定 scope 声明段")
  2. 设计原则与决策索引(引用 map 与契约文档,不复述)
  3. 方法(三波结构、canary 选集规则,引用 028)
  4. 结果(脱敏统计:成功率、成本、逐 case Terminal Outcome、Evaluation Artifact 汇总)
  5. Evaluation fidelity 专节(032 硬性要求:术语纪律 + 与官方复现的区分 + DeepSeek 参数化污染 caveat)
  6. 失败与降级 run 的发现(见下节叙事纪律)
  7. 局限、caveats 与附录(命令、commit SHA、hash 索引)

## Interview narrative

- 落点:`docs/task/`(private,ignored;个人面试策略不进 repo)。事实内容与 report 同源同 hash,只换叙述视角。中文撰写,如需英文面试版届时从 report 派生。
- **叙事脊柱 = Evidence Feedback Loop**:canary 暴露的失败/降级是故事的第二幕转折点;每个发现按"现象 → 证据链 → promotion gate 决策 → 验证"讲;失败发现**独立成节、先于最终结果呈现**,不收进 limitations。此节回答了 map 曾有的雾「最终面试叙事应如何优先呈现失败或降级 run 中浮现的发现」。

## Downstream 话术边界

- **固定 scope 声明段**(report 与叙事第一节逐字使用):

  > 本项目仅覆盖 ideation:target-scoped 输入准备、本地冻结语料内的文献检索、idea 生成与校验。AI Scientist v2 的任何 downstream 阶段(BFTS、代码实验、绘图、LaTeX 写作、自动 review)均未执行,不在本交付范围内。本文全部结果仅涉及 idea 生成环节;IdeaBench 适配为 sealed qualitative comparator,未复现任何官方指标。

- **禁用措辞清单**(对照 map 的 Out of scope,入库前逐项核对):
  1. 不得声称或暗示运行了 BFTS/代码实验/绘图/write-up/review(`launch_scientist_bfts.py` 从未执行);
  2. 不得声称生成了论文、经过 peer review、或复现了 IdeaBench 官方指标;
  3. 不得暗示 downstream 能力已被验证;
  4. 不得声称运行时使用了全局或远程文献检索;
  5. 不得声称 GPU/accelerator 训练或将 accelerator 设为必需;
  6. 涉及 DeepSeek 参数化的结论必须携带 032 的污染 caveat。
- **话术检查**:report/叙事入库前把禁用清单当 checklist 逐项核对,"话术检查通过"随该 commit 的脱敏摘要记录。

## Handoff 完成定义

以下全部成立,handoff 才算完成:

1. spec 与实现票单经 Robert 批准(to-spec/to-tickets 产出);
2. 全部实现票关闭(每票矩阵行全绿 + Robert 逐票验收);
3. Scale Gate 通过、终波执行完毕;
4. 035/036 随 canary 证据关闭(wayfinder map 随之全闭);
5. report 与叙事文档入库/就位,话术检查通过;
6. AGENTS.md 一致性扫尾完成。

**ticket 030 的关闭条件 = 第 1 项**:030 交付的是"交付序列的定义"而非交付本身;spec 与票单批准后,由该 session 补写 Resolution、关闭 030、更新 map gist,并清算已回答的雾。
