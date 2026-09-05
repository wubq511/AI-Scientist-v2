# AI 评审真实 smoke 执行证据（六次基础调用 + 修复调用台账）

日期：2026-09-05。执行手册：[ai-review-smoke-runbook.md](../agents/ai-review-smoke-runbook.md)；合同：[ai-review-authoring-contract-v2.md](../agents/ai-review-authoring-contract-v2.md)。本报告逐项引用程序产物中的数值，不手工美化。

## 结论

六次基础真实调用（单条 ×2 + 合成 pair ×4）全部完成并通过程序验证，runbook 第 5 节四个完成条件全部满足：

1. **真实响应被解析与回链**：6 条 head 评审记录 + 共识记录 + 还原记录全部落盘、哈希可核（见下文产物清单）；
2. **已知明显缺陷未被一致漏过**：合成 pair 的预设缺陷 F1 被**两个模型、两个方向（4/4）**检出，且都以包内矛盾原文作为拒绝证据；
3. **故意缺失的证据未被冒充存在**：全部维度均为 judged、弃权数为 0——本轮材料完整，弃权路径由离线 fixtures 覆盖，真实路径未被触发（如实记录，视为本轮未测项）；
4. **换位不制造稳定假 winner**：四条记录的显示侧 verdict 全部还原到同一内容侧（干净臂），还原结果三项判断全部 `stable`，`position_flip`/`evaluator_conflict`/`incomparable_judgment` 均为 0。

smoke 只证明流程可用与最低检错行为；不证明双模型优于单模型，不证明跨领域效果。无专家 gold，不报告科研准确率。

## 执行配置

| 项 | 值 |
|---|---|
| primary | DeepSeek `deepseek-v4-pro`（api.deepseek.com，thinking enabled，`reasoning_effort=max`，`response_format=json_object`，max_tokens 32768） |
| second | Moonshot `k3-256k`（Kimi Code 订阅计划，api.kimi.com/coding/v1，`reasoning_effort=max`，max_tokens 32768） |
| prompt 版本 | 单条 `single-review-v2`；pair `pair-review-v1` |
| 执行 config | 真实工作区与 pair 工作区各注册一份；因端点实际模型 id 与占位 id 不符，经 `--supersede` 留档修订一次（`kimi-k3` → `k3-256k`，旧 config sha `b6a86661…` 归档，新 sha `80788656…`） |
| 授权 | Robert 授权发送与两模型选型；DeepSeek 按 pinned 价格表计费，Kimi 消耗订阅额度（边际费用 0） |
| 日期与费率 | 2026-09-05（周六），DeepSeek 全程 off-peak（input cache-miss 4.5 / output 13.5 CNY 每百万 token） |

## 预设缺陷与检出结果

合成 pair `pair-26a4d610d5a637dc`（case `case-589dbcb35662706939b2f0d6dfd32800`）：

- content_1 = 干净臂（主动学习等变势筛选），content_2 = 缺陷臂（声子压温日程）；
- 预设缺陷 **F1**（登记于执行前 seeded-flaws 台账，不进任何模型可见内容）：缺陷臂 Abstract 称目标研究 "at ambient pressure with no diamond anvil cell"，与包内 C003 摘要（SCXRD 87–171 GPa、金刚石压腔激光加热合成）直接矛盾，仅凭材料即可证伪。

检出结果：**4/4**（primary/ab `a_better`、primary/ba `b_better`、second/ab `a_better`、second/ba `b_better`——全部指向干净臂），每个记录的 overall_preference 证据都同时引用了缺陷臂的误述句与 C003 的矛盾句。已知误报（预期无缺陷处出现负面判定）：**0**（`unjustified_ml_intrusion` 四条记录均判 `equal`）。

## 引用核验、弃权、分歧

| 记录 | refs_quote_verified/refs_total | 弃权维度 |
|---|---|---|
| 单条 primary（deepseek-v4-pro） | 13/13 | 0 |
| 单条 second（k3-256k） | 18/18 | 0 |
| pair primary/ab | 9/9 | — |
| pair primary/ba | 7/7 | — |
| pair second/ab | 10/10 | — |
| pair second/ba | 11/11 | — |

- 单条共识：**31/31** 引用逐字通过；七维全部 `consensus`（0 conflict）、coverage `complete_resolved`、pre-registered 质量底线 `clean`。
- pair 还原：**37/37** 引用逐字通过；三项判断（overall_preference / domain_method_fit / unjustified_ml_intrusion）还原后全部 `stable`，overall_preference 收敛到 content_1；`incomparable` 判断数 0。
- 模型分歧：**0**（单条无 conflict 维度；pair 无 evaluator_conflict）。
- 弃权：**0**——材料完整使弃权路径未被真实触发，见「诚实边界」。

## 物理调用台账（14 次 = 基础 6 + 追加 8）

| # | 调用 | 配置 | 结果 | 延迟 | tokens (in/out) | DeepSeek 费用 CNY |
|---|---|---|---|---|---|---|
| 1 | pair-ab primary | high 档 | validated（后被 #7 supersedes） | 106s | 6521/7511 | 0.1307 |
| 2 | pair-ba primary | high 档 | validated（后被 #8 supersedes） | 108s | 6521/7033 | 0.1243 |
| 3 | single attempt1 | high 档, max_tokens 8192 | ⚠️ finish=length、content 为空（reasoning 独占预算），payload 归档 | 132s | 5440/8192 | 0.1351 |
| 4 | single attempt2 | high 档, max_tokens 32768 | 校验拒绝 `AUDIT_STATEMENT_REF_REQUIRED`（r0001 保留） | 120s | 5440/9043 | 0.1466 |
| 5 | single attempt3 | high 档原样重试 | 同规则拒绝（r0002 保留）→ 判定 prompt v1 显著性缺陷 | 140s | 5440/11281 | 0.1768 |
| 6 | single attempt4 | **single-review-v2** | validated v0001（后被 #11 supersedes） | 167s | 5538/10781 | 0.1705 |
| 7 | pair-ab primary | **max 档**（Robert 指令：双模型统一 max） | validated v0002 | 97s | 6534/6437 | 0.1163 |
| 8 | pair-ba primary | max 档 | validated v0002 | 81s | 6534/5472 | 0.1033 |
| 9 | single max | max 档 | 校验拒绝 `CITATION_QUOTE_NOT_FOUND`：S011 引文把 "per-paper" 写成 "per-package"（r0004 保留） | 175s | 5551/12719 | 0.1968 |
| 10 | single max 重试 1 | max 档 | 拒绝：引文错标来源（S006 实为 idea 原文句，r0005 保留） | 140s | 5551/11937 | 0.1863 |
| 11 | single max 重试 2 | max 档 | 全部引用通过，validated v0002 | 121s | 5551/8198 | 0.1357 |
| 12 | single second | Kimi max 档 | 一次通过 validated | 275s | 5506/15406 | 订阅额度 |
| 13 | pair-ab second | Kimi max 档 | 一次通过 validated | 239s | 6506/9378 | 订阅额度 |
| 14 | pair-ba second | Kimi max 档 | 一次通过 validated | 153s | 6506/5531 | 订阅额度 |

- **DeepSeek 合计 1.6224 CNY**（11 次调用，off-peak）；**Kimi 边际费用 0**（订阅计划内，tokens 如上记录）。
- 修复调用的每一笔都保留原始响应（r0001–r0006 与归档 payload），无任何删除或改写。
- 思考量（reasoning tokens，head 记录对应调用）：DeepSeek max 档 4.6k–6.0k；Kimi max 档 4.1k–12.5k。

## 过程中的两次合同级修复（均有代码与测试）

1. **prompt v1 → v2**：两次独立调用（#4、#5）在同一规则上失败（`contamination_signal` judged 未引用 audit_statement 来源）。维度表把该维度描述成纯「引用可解释性」判断，模型按表行事不会联想审计锚定——机检规则正确，prompt 显著性不足。v2 仅将该机械要求写显眼（诚实边界、维度表、例 2），一次通过（#6）。commit `dd2f02f`，842 passed。
2. **执行 config 的留档 supersede**：write-once config 钉的占位模型 id 与订阅端点实际 id 不符。新增 `--supersede`：普通二次注册仍 `ARTIFACT_EXISTS` fail closed；supersede 把旧 config 字节 rename 留档后注册修订版，返回归档 sha256。commit `902d2af`，843 passed。

## 抄写滑误处理协议（Robert 指定，本轮未触发）

逐字核验的职能是防伪造引用，不是要求模型完美转写。协议：引文有明确原文对应的一词滑写、或来源 ID 错标但引文在包内唯一存在的，作为文书性错误人工对照原文更正、逐条记台账、更正文本重新走全部机检；包内找不到出处的引文属伪造，响应作废；verdict/rationale 永不修改。本轮最终采纳的响应无需修正（#9、#10 两次被拒响应保留原样，未采用）。轮内另一次险情：预检脚本曾用 ab 排布 sources 对照 ba 响应，误报 9 处「A↔B 互换」——以 ba 渲染的请求 sources 重查为 0 问题，属检查工具错误而非模型错误，如实记录。

## max 档观察（小样本，如实记录）

- DeepSeek：3 次 max 档 single 中 2 次出现引用滑写（#9 一词改写、#10 来源错标），1 次全对；high 档 1 次（#6）全对。样本不足以下结论，但方向上 max 档的逐字引用保真度更差。
- Kimi：3 次 max 档全部一次通过（引用 0 问题），且 pair-ba 方向的 A/B 框架完全正确。
- 判断质量面（缺陷检出、换位一致性）两种 effort 档无差异。

## 暴露披露（development/diagnostic 标记）

- slot 1（run `1143a894-1230-4ee1-b41a-f801cc50c027`，idea 0）的匿名评审材料包在本轮**被用入真实评审实验且结果被开发者观察**（含 ticket 01 会话中的只读管道演示）。降级为 development/diagnostic 的原因是「用入实验 + 观察结果」造成的开发集污染，与数据是否出站无关（本地调用同样触发）；其响应此后不得充当 prompt 优化后的未见测试证据，正式评估应使用未暴露的 run。
- 合成 pair 的两臂为合成的 sealed run（非真实 interview 数据），仅用于流程与检错验收，不进入任何真实评估矩阵。
- 密钥处理：DeepSeek 与 Kimi key 均存于仓库 `.env`（gitignored，0600），全程未回显、未入日志；本报告与所有入库文档不含任何密钥。

## 关键产物清单（哈希可核）

- 单条（真实工作区 `artifacts/evaluations/1143a894-…/ideas/000000/ai/`，gitignored 本地）：`primary/v0002.json`（head，sha `5a0fd17e…`）、`second/v0001.json`、`consensus/v0001.json`（sha `133bbe49…`）、共识卡 `consensus-card.md/.html`；被拒/被取代响应 `primary/responses/r0001–r0006` 全部保留。
- pair（/tmp 工作区，原始证据已归档至 `artifacts/evaluations-smoke-pair-archive/`，gitignored 本地）：四记录 + `reduction/v0001.json`（sha `b9c55872…`）+ `pair-report.md/.html`；seeded 缺陷台账 `seeded-flaws.json`；构建脚本 `build_smoke_pair.py`（重建确定性：pair id 与请求 SHA 不变）。
- 发送层证据：`send-meta.json`（14 次调用的 status/latency/tokens/request sha）、失败 payload `failed-attempts/`，随归档目录保存。

## 未执行项与后续

- 弃权路径的真实触发（需故意缺失材料的 fixture run）；
- 修复调用后的语义支持核验（`semantic_support_verification` 恒为 `not_performed`，合同既有边界）；
- 双模型 vs 单模型的效果对比、跨领域泛化——规格明确不在 smoke 验收范围。
