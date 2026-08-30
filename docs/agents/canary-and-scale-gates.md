# Canary 与扩量 Gate 契约

版本 v1.0 · 2026-08-30 · 来源 ticket [Define canaries and scale gates](../wayfinder/ideation-pipeline/tickets/028-define-canaries-and-scale-gates.md)（两轮 grilling 由 Robert 批准）。

本契约定义从「零真实调用」到「终波」的执行阶段、Canary 集的选择规则、成本与质量预算、失败处理，以及打开扩量 gate 的全部条件。修订规则同 027 验证矩阵：任何修订 = 新版本号 + Robert 批准。

## 阶段结构（三波）

1. **smoke**：1 个 case、单次 Ideation Run，晃出 adapter、估价偏差、证据链落盘的首跑缺陷。
2. **canary**：12 个 case，承载首跑验证与 035/036 比较实验（共享同一 Canary 集）。
3. **终波**：规模不在本契约锁死，由扩量 gate 按面试叙事需要与 canary 实测成本决定（预期量级 ~50）。**面试任务不要求全量 237**；系统对 237 的支持与预处理验证义务由 009 独立成立，不以模型跑全量为前提。

## Canary 集选择规则

- 规模 12 个 case；8 个 cluster 全覆盖，Health & Medicine、Genetics & Molecular Biology、Neuroscience & Cognitive Sciences 各 2 个，其余 cluster 各 1 个；其中含 1 个 `strategy=2` target。
- reference 数覆盖 min / median / max 档。
- 刻意纳入 2–3 个已知边缘案例（占少数）：含不可恢复 reference abstract 的 target 1 个、仅 3 条 reference 的 target 1 个。
- 流程：按上述规则确定性筛选候选池，Robert 从候选中点定最终 12 个。
- 名单本体为私有 manifest（含真实 `paperId`，gitignored）；repo 只提交本规则、分层摘要与名单 SHA-256。

## 成本预算

- canary 阶段（smoke + canary 上的一切真实调用，含 035/036 与失败重跑）**¥30 硬上限**，低谷期执行。
- 031 的逐 run 估价、逐 run 批准在 smoke 与 canary 阶段不变；smoke 首跑得出实测单 run 成本后，后续每次估价按实测重校准。
- **执行优先队列**：smoke(1) → 035 arm `reasoning_effort=high`(12) → 035 arm `max`(12) → 失败重跑 → 036 变体臂（3 case 子集，baseline 臂复用 035 胜方的既有 run）。
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

## 终波执行条款

- 串行执行、低谷期；分 2 批，批间设轻量检查点（成本 + Terminal Outcome 分布摘要，Robert 确认继续）。
- Evaluation Artifact 维持逐 run 100% 强制（032 的 canary 规则延伸），不引入抽样机制——终波量级下 Robert 可读完。
- **修订 031**：终波改为按批批准——批内逐 run 列出估价行，一次批准覆盖该批；canary 阶段的逐 run 批准不受此修订影响。

## 证据纪律

沿用 010：原始证据（运行日志、估价记录、批准记录、manifest）本地保留（gitignored、immutable）；repo 只提交脱敏摘要——命令、commit SHA、pass/fail、相关 hash。永不记录 secrets。
