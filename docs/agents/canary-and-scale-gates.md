# Canary 与扩量 Gate 契约

历史版本 v1.2 · 2026-09-04 · 来源 [跨领域 Ideation Prompt 资格验证规格](cross-domain-ideation-prompt-spec.md)、ticket [Compare DeepSeek reasoning effort and completion limits](../wayfinder/ideation-pipeline/tickets/035-compare-deepseek-reasoning-effort-and-completion-limits.md) 与规范 [DeepSeek Reasoning Effort Canary 比较规格](deepseek-reasoning-effort-canary-spec.md)（Robert 于 2026-09-04 批准先资格验证 domain-neutral Prompt Profile、暂停并撤回旧 035 Plan Gate；v1.1 同日批准 Canary 算术修正与选择语义；首版 v1.0 于 2026-08-30 经 ticket 028 批准）。

本契约定义从「零真实调用」到「终波」的执行阶段、Canary 集的选择规则、成本与质量预算、失败处理，以及打开扩量 gate 的全部条件。修订规则同 027 验证矩阵：任何修订 = 新版本号 + Robert 批准。

## 交付收尾修订（v1.4 · 2026-09-06 · Robert 授权，终波不执行）

Robert 于 2026-09-06 授权交付收尾并明示「扩量你自行判断有没有意义。如果不是必要的话就不做」。据此裁决并落账：

- **扩量 gate 满足但终波不执行**。gate 六项条件实测状态：①硬阻断清零（12 runs 全生命周期零 VM-LEAKAGE-02 hygiene 命中、零 Run Isolation 违规、零 preflight 绕过；VM-QUAL-01 Evaluation Artifact 100% 覆盖）；②12/12 已执行 canary case 的 sealed run Terminal Outcome = `success`；③028 消费者矩阵行全部通过（12-case 执行期内 validate/export/评审链无一行失败，离线 pytest 899 passed）；④实际成本 1.34 CNY（含 0.14 历史 smoke）在 ¥30 包络内，单 run 实测 0.07–0.13 CNY 已校准；⑤Robert 于 2026-09-06 授权收尾并明示扩量按必要性自判；⑥`cross-domain-v1` 已按 Robert 的 post-evidence-adoption 决定成为唯一 production prompt（`ml-baseline-v1` 已退役）。
- **必要性裁决**：终波（预期 ~50 runs）只增加样本量、不增加叙事维度。max Canary 已达成 8 cluster 全覆盖、12/12 success、双 AI 评审七维全部达标共识（relative_novelty 12/12 beyond_target、feasibility 12/12 sound、contamination 12/12 none_found）、34/34 attempt `finish_reason=stop` 零截断；Evidence Feedback Loop 叙事所需的中途修正与失败发现（002 评审协议位置翻转、035 admission 参数统一修正、run 8 引文滑误三次修复）已在 canary 期全部发生并留证。执行终波与交付截止时间直接冲突。**终波正式裁定不执行，扩量 gate 关闭（gate-passed, final-wave-waived）。**
- 036（Workshop 变体比较）同日以 `no-comparison-executed` 关闭，理由同上；详见 ticket 036 Resolution 与 [wayfinder map 全闭记录](../wayfinder/ideation-pipeline/map.md)。
- 本契约完成历史使命：三波结构执行至 canary 波，后续任何付费 ideation 执行属新契约范畴，不受本契约约束。

## 当前执行修订（v1.3 · 2026-09-06）

Robert 已采用 `cross-domain-v1`（Proposal 002，post-evidence-adoption），并明确指定后续生成使用 `reasoning_effort=max`，无需再比较 high/max 或衡量选型性价比。此修订取代 v1.2 中“先取得新的 reasoning-effort proposal/胜方”的执行前提；selection 规则与既有实际预算不因该决定重置。

当前工作为单配置 12-case Canary，基础 12 runs；历史 high runs 不替代 max coverage。复用已批准输入与现有双 AI 单条评审，无 reasoning-effort pair 评审。completion limit 暂留 32768 并观察真实截断。评审来源、费用口径及合法批内预授权沿用各自后续已批准修订；本段不恢复已废弃的人工独占评审或仅交互式授权限制。

## 阶段结构（三波）

1. **smoke**：1 个 case、单次 Ideation Run，晃出 adapter、估价偏差、证据链落盘的首跑缺陷。
2. **canary**：12 个 case；Prompt Profile 采用决定已完成，当前用 `cross-domain-v1` + `max` 做单配置运行与质量验收；036 为后置可选比较。
3. **终波**：规模不在本契约锁死，由扩量 gate 按面试叙事需要与 canary 实测成本决定（预期量级 ~50）。**面试任务不要求全量 237**；系统对 237 的支持与预处理验证义务由 009 独立成立，不以模型跑全量为前提。

## Canary 集选择规则 (v1.1)

- 规模 12 个 case：
  - **基础 11 个 slot (8 clusters 全覆盖)**：Health & Medicine、Genetics & Molecular Biology、Neuroscience & Cognitive Sciences 重点领域各 2 个，其余 5 个 cluster（Environmental Sciences, Materials Science, Public Health & Policy, Social & Behavioral Sciences, Technology & Engineering）各 1 个；
  - **第 12 个 slot (Constraint-Driven Edge Slot)**：独立边缘槽位，可来自任意 cluster，专门用于补足基础 11 个未覆盖的硬性 edge requirement；若全部硬性 requirement 已覆盖，则选择第二个已知 edge case。
- **硬性边缘与分层要求 (全量 12 cases 需共同满足)**：
  - eligible reference 数覆盖 min / median / max 档（基于锁定候选池重算，当前 IdeaBench 数据集快照为 3、8、36；新鲜候选池快照为 3、7、32）；
  - 至少 1 个 case 为仅 3 条 reference 的 target（最小合法语料边缘）；
  - 至少 1 个 case 含不可恢复 reference abstract（按获批语料政策标记为 `not_published`，真实边缘）；
  - 至少 1 个 `strategy=2` target。
- **边缘槽位选取与 Tie-Break 规则**：
  - 满足基础 11 个 cluster 配额后，第 12 个 slot 优先分配给候选池中最稀缺的未满足硬性 requirement（以符合条件的 eligible 候选数衡量）；
  - 若稀缺度并列，按固定优先级仲裁：`exactly-three references` → `unavailable reference abstract` → `maximum reference count` → `median reference count`，最后以确定性 canonical candidate hash 决胜；
  - 若基础 11 个已覆盖全部硬性要求，该 slot 取候选数最少 cluster 中按 canonical hash 排序的第一名边缘案例。
- **新鲜度与排除边界**：
  - 严格排除已完成的 smoke case (`case-229e495f82a24cff9e6082aa058955b9`) 以及 formal local-ranking 占用的全部 24 个 targets（development 6、holdout 6、operational 12）；
  - 绝不因准备方便而复用 `lr-op-*` 批次；若新鲜候选集无法满足所有硬性约束，选集 fail-closed 并停止，不得静默放宽。
- **流程与门禁**：
  - 仅依据批准的 routing metadata、reference 数与 prior-use 状态确定性筛选候选池；
  - 名单本体为私有 manifest（含真实 `paperId`，gitignored），由 Robert 审查不泄露内容的候选摘要后点定并冻结；repo 只提交本规则、分层摘要与名单 SHA-256。

## 成本预算

- canary 阶段（smoke + canary 上的一切真实调用，含 035/036 与失败重跑）**¥30 硬上限**，低谷期执行。
- 031 的逐 run 估价、逐 run 批准在 smoke 与 canary 阶段不变；smoke 首跑得出实测单 run 成本后，后续每次估价按实测重校准。
- **执行优先队列**：smoke 与 Proposal 002 已完成 → 新配置 max 单臂 12-case Canary（035）→ 必要失败处理 → 036（若另行执行）或扩量交付。Proposal 001 的旧 035 24-run matrix 继续撤回，不得执行或计为 max evidence。
- 接近上限时从队尾截断（036 最先被牺牲）。预算耗尽导致 gate 要求的 case 未完成时，不擅自追加预算，回到 Robert 决定追加或收缩 Canary。
- 终波预算包络不设死数：在扩量 gate 处按 canary 实测成本估算，由 Robert 连同终波规模一并批准。

## 失败处理

- 环境类：走 025 的 suspend/resume。
- 模型行为类（`budget_exhausted`、model-fixable 轮次耗尽等）：归因留证，同 case 起新 run 重跑一次；再败则该 case 挂起并写入报告。
- 疑似设计缺陷：不就地修补，作为 Evidence Feedback Loop 发现走 029 promotion gate，修复批准后新 run 重跑。

## 扩量 gate（打开条件，全部满足 + Robert 批准）

1. **硬阻断清零**：canary 阶段无任何 VM-LEAKAGE-02 runtime hygiene 命中、无 Run Isolation 违规迹象、无 preflight 绕过或 Run Admission 缺失、无 VM-QUAL-01 要求的 Evaluation Artifact 链接缺失。
2. 每个**已执行**的 canary case 最终有一个 Terminal Outcome = `success` 的 sealed run（允许按失败处理规则重跑；因预算截断未执行的 case 不算失败，但 gate 决策权回到 Robert）。
3. 验证矩阵中标注消费者 028 的行全部通过：VM-CONTRACT-018-02、VM-CONTRACT-019-01、VM-CONTRACT-020-02、VM-CONTRACT-026-02、VM-INTEGRATION-01、VM-REPLAY-02、VM-LEAKAGE-01、VM-LEAKAGE-02、VM-LEAKAGE-04、VM-ISOLATION-01、VM-ENV-01、VM-QUAL-01。
4. 实际成本在 ¥30 包络内，实测单 run 成本已校准，终波估算与规模已提交。
5. Robert 审读 canary 的 Evaluation Artifact 与失败归因后明确批准；同一次批准中确定终波规模与预算包络。
6. `cross-domain-v1` 或后续获批替代 Prompt Profile 已通过 Promotion Gate；已知 ML 目标错配的 `ml-baseline-v1` 不得作为打开 Scale Gate 的 production prompt。Prompt comparison rejected 或 inconclusive 时，Scale Gate 保持关闭。

## 终波执行条款

- 串行执行、低谷期；分 2 批，批间设轻量检查点（成本 + Terminal Outcome 分布摘要，Robert 确认继续）。
- Evaluation Artifact 维持逐 run 100% 强制（032 的 canary 规则延伸），不引入抽样机制——终波量级下 Robert 可读完。
- **修订 031**：终波改为按批批准——批内逐 run 列出估价行，一次批准覆盖该批；canary 阶段的逐 run 批准不受此修订影响。

## 证据纪律

沿用 010：原始证据（运行日志、估价记录、批准记录、manifest）本地保留（gitignored、immutable）；repo 只提交脱敏摘要——命令、commit SHA、pass/fail、相关 hash。永不记录 secrets。
