# Optimization Promotion Gate

版本:v1.1（2026-09-06：Robert 批准 Proposal 002 定向采用修订；其余流程沿用 v1.0）

v1.0 来源：(2026-08-30,经 ticket [Define the optimization promotion gate](../wayfinder/ideation-pipeline/tickets/029-define-the-optimization-promotion-gate.md) 由 Robert 批准)

本文档定义 Optimization Promotion 机制:把 Evidence Feedback Loop 的发现转变为被接受的设计变更的门槛与流程。它受版本治理——任何修订 = 新版本 + Robert 批准(012)。

## Proposal 002 定向修订（当前生效）

Robert 已批准基于现有改善证据采用 `cross-domain-v1`，并移除 baseline 的执行与回退能力。本决定允许 Proposal 002 在原预注册判据未通过时明确记录 `decision_basis: post-evidence-adoption` 后采用，覆盖本文“不引入新裁量”及“无 promoted 默认不变”条款对本次变更的阻断效力。原始比较结果保持不通过，不能改称预注册成功；原 reducer 和盲评 write-once 记录保持不变。

依据与未知项见 [002 裁决记录](comparison-002-promotion-criteria.md)。采用开启新 Design Epoch；不要求为凑足胜场重跑，不恢复旧付费矩阵。此定向批准不自动授权其他提案修改判据或花费，也不创建通用 override 开关。

## 定位与边界

- **路由规则**:凡 justification 是「证据显示这样更好」的设计变更,一律过本 gate——包括但不限于 calibration-pending 阈值收紧、版本化规则集修订、prompt 围栏内文本、retrieval ranking 参数、模型参数化。一句话判据:**「更好」→ promotion,「错了」→ bugfix,「还没定」→ wayfinder**。
- **豁免一:bugfix**。恢复既定契约符合性的修复不进本流程,走正常 commit + 验证矩阵既有行测试。
- **豁免二:未定设计空间**。尚无契约的设计问题走 wayfinder ticket,不走 promotion。
- 本契约只定晋升机制:Canary 集身份与扩量节奏归 [Define canaries and scale gates](../wayfinder/ideation-pipeline/tickets/028-define-canaries-and-scale-gates.md),验证行定义归 [validation-matrix.md](validation-matrix.md)。本文引用其行 ID,不重开决策。

## 载体与版本治理

- 每个提案 = `docs/agents/promotions/NNN-<slug>.md`,NNN 从 001 顺序编号,不复用。
- 提案文件提交**脱敏版**(命令、commit SHA、pass/fail、hash、脱敏证据引用);原始证据本地保留(gitignored,immutable),沿用 010 纪律。
- 本契约文档的修订 = 新版本号 + Robert 批准。

## 流程:双 Gate

- **Plan Gate**(花钱前):Robert 批准假设、pre-registered 判据、对比方案与成本估价后,对比实验才许执行。遵循 024 的逐次估价批准纪律。
- **Promotion Gate**(证据后):Robert 只对照 Plan Gate 锁定的 pre-registered 判据宣判 `promoted` / `rejected`;**不引入新裁量**——不允许看到结果后移动球门或临时放宽。

## 对比方法

- baseline = 当前 pin 住的 Run Specification,在同一 Canary 集上对照;challenger 与 baseline 仅相差假设声明的**一个主变量**(012)。
- 证据 = 提案点名的验证矩阵行(deterministic 层两侧必须全绿)+ 假设声明的改进指标 + Robert 对两侧 Evaluation Artifacts 的结构化质量比较(032/037)。
- 跨 Run Specification 的历史证据不可比(023 spec immutability),不得用作 baseline 替身。

## Pre-registration 与 Regression Budget

- 提案必须 pre-register:可证伪假设、单主变量声明、pass/fail 判据、分维度 **Regression Budget**(deterministic 零容忍;成本包络;质量语句)。Plan Gate 锁定后不可改。
- 自动 reject 条件:任何 baseline 侧绿、challenger 侧红的 deterministic 矩阵行;实测超出成本包络;违反 pre-registered 质量语句;**预算外维度**出现意外回退(如 retry 率、延迟、异常模式)。

## Design Epoch

- 每次 promotion 开启一个新 **Design Epoch**;canary 与 scale 证据仅在同一 epoch 内可比;[Define canaries and scale gates](../wayfinder/ideation-pipeline/tickets/028-define-canaries-and-scale-gates.md) 的 scale gate 只消费当前 epoch 的证据。
- epoch 不新增 runtime 字段:它由既有 spec pins(023/027/034)天然实现,仅是证据可比性规则。

## 生命周期

`proposed` →(Robert,Plan Gate)→ `plan-approved` →(对比实验执行,脱敏证据归档)→ `evidence-complete` →(Robert,Promotion Gate)→ `promoted` | `rejected`;任何 pre-promoted 状态可由提案人或 Robert 转 `withdrawn`。

- Fail-closed 缺省:没有显式 `promoted`,当前 pin 住的设计不变。
- 提案人:agent(Evidence Feedback Loop 发现)或 Robert;两道 gate 的批准权仅 Robert。

## 回滚与紧急

- **回滚** = 一个假设为「旧版本更好」的 Promotion Proposal;Plan Gate 可采纳已有证据(引发回滚的回归证据),批准零新增成本的对比方案。流程不跳过。
- **紧急**:fail-closed halt 受影响 run 永远立即执行、无需任何 gate;随后的设计变更仍走完整双 gate——时间上压缩,步骤不省略。若问题属违背既定契约(如 hygiene 漏网模式),走 bugfix 通道,不进本流程。

## Promotion Proposal 模板

```markdown
---
id: NNN-<slug>
state: proposed | plan-approved | evidence-complete | promoted | rejected | withdrawn
filer: <agent|Robert>
created: YYYY-MM-DD
---

## 问题与证据
<观察到的现象;脱敏证据引用 + 本地原始证据路径>

## 假设
<可证伪假设;单主变量声明>

## 备选方案
<考虑过的 viable alternatives 与取舍>

## 对比方案
<baseline Run Specification 引用;Canary 集引用(028);验证矩阵行 ID 清单;成本估价>

## Pre-registered 判据
<pass/fail 判据;Regression Budgets:deterministic / 成本 / 质量>

## 预期失败模式
<failure cases>

## 实验证据
<前后对比摘要;观测到的回退;脱敏证据引用>

## Plan Gate 记录
<Robert 批准:日期、估价、锁定判据版本>

## Promotion Gate 记录
<Robert 宣判:promoted|rejected、对照判据的核对结果;若 promoted——受影响的规则集/矩阵版本 bump>
```
