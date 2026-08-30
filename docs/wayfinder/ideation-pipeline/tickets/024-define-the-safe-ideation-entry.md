---
title: Define the safe ideation entry
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 017-audit-the-minimal-ideation-runtime.md
---

## Question

How should the existing ideation CLI and imports be changed directly so the allowed path is clear, testable, has a portable CPU FP32 reference path, and is unable to trigger BFTS, experiments, plotting, write-up, or review?

## Resolution

Robert 批准以下安全 ideation 入口合同（三轮 grilling，全部按推荐；价格机制按 Robert 简化）。入口即原地改造的 `perform_ideation_temp_free.py`；「无法触发 downstream」由准入清单式导入守卫在测试层强制。

### 入口身份与调用

- 原地修改 `ai_scientist/perform_ideation_temp_free.py`，保留文件名、`python ai_scientist/perform_ideation_temp_free.py` 直接脚本调用与 `sys.path` hack；不改名、不新建子系统（服从 005/006）。
- 消除 import 期副作用（工具实例化等收进工厂函数）；adapter(022)、retriever(020)、event emitter(023) 以三个窄接口注入缝传入（无 ABC 仪式），测试用 fake 注入，无网络、确定性。
- Workshop 注入机制不变：整文件读入 prompt，但输入只能是 Approved Workshop。

### Downstream 不可触发

- 准入清单式导入图守卫测试：从入口模块走传递闭包，双层清单——`ai_scientist.*` 内部模块精确清单 + 第三方 top-level 包清单（stdlib 不管）；任何新增模块/依赖必须显式更新清单，否则 fail。守卫进 pytest，在 027 矩阵占位。不做运行期导入检查。
- 模型可见工具面固定写死在代码里：`SearchLiterature`（中性名，描述不泄漏 scope 机制）+ `FinalizeIdea`；无代码执行工具；未知 action 拒绝。
- Prompt diff 限于系统 prompt 的工具描述段；FinalizeIdea 七字段规范与 generation/reflection prompt 逐字不动（006 基线）。

### CLI 面（new-run)

- 参数：`--case-id`、`--workshop <path>`、`--workshop-sha256`、`--corpus <path>`、`--corpus-sha256`(bundle 级 identity hash)、`--max-num-generations`、`--num-reflections`。
- 移除：`--model`（模型身份锁进 Run Specification，使用 031 批准的 DeepSeek 浮动 alias）、旧 `--workshop-file` 语义、一切输出路径参数（roots 固定，023)。无 device/accelerator flag——检索后端固定 CPU FP32(013);v1 无 run-spec 配置文件。
- `<workshop>.json` 兄弟文件与 `reload_ideas` 隐式 resume 消失；ideas 为 run-scoped 不可变 artifacts。resume CLI 扩展归 025。

### Preflight 序列（fail closed)

1. CLI 请求 schema 校验（失败 = run 外 entry error，无 run)。
2. 铸造 `run_id`,exclusive-create run root，写 `request.json`。
3. 验证 clean worktree，记录 commit SHA。
4. 验证 Approved Workshop:canonical bytes hash + private manifest approval status + contract/validation 版本 + `case_id` 一致。
5. 验证 Approved Corpus：按 019 清单全项（pin 一致、重算 hashes、validation report 对应同一 bundle、版本兼容）。
6. 构造绑定 corpus 的 retriever（无模型调用），验证 policy 版本。
7. 检查 `DEEPSEEK_API_KEY` 存在性（不读值、不记录；真实 auth/balance 由 adapter typed failure 暴露）。
8. 计算费用上界并展示，取得 Robert 显式批准。
9. 写 `admission.json` pin 全部输入——此后才允许首次付费调用。

任一步失败：run 标记 preflight rejected，证据按 023 永久保留，禁止 fallback。

### 定价（修订 022 快照机制）

- Versioned 价格表：repo 内受版本管理文件，含高峰/低谷 × cache hit/miss/output 费率、时段窗口、source URL、登记日期；一次登记 + Robert 批准，官方调价才更新（重新批准）；表 hash pin 进 `admission.json`;preflight 按当前时间查表。缺失或 hash 不符 fail closed。此方案替代 022 的每运行冻结快照，022 留有指针。
- 估价批准交互：打印上界明细（恒按高峰价、全 cache miss、声明 token 预算、≤2 attempts),stdin 输 `yes` 确认，其他一切视为拒绝；非交互环境 fail closed。批准事实（时间戳、上界金额、价格表 hash）记入 `admission.json`。
- 跨高低谷时段：上界恒按高峰价计算，跨时段不击穿批准；实际费用逐 attempt 按其**开始时刻**所在时段费率结算（022 已定按 attempt 时段计价，本票精确定义「所在时段」= attempt 开始时刻）；单个跨边界 attempt 按开始时刻算，属确定性近似，误差被高峰价上界覆盖。

### FinalizeIdea 结构校验

- v1 规则：恰好七字段（008 基线）、类型正确（五个 string + `Experiments`/`Risk Factors and Limitations` 为 list)、全部非空；纯结构校验，语义质量归 026。
- 违规 = 模型可修复错误，错误信息作为 tool result 反馈进 reflection；预算耗尽后的处置归 025。

### 边界

重试/失败/resume 状态机 → 025;requirements 与版本锁定 → 034；完整测试矩阵 → 027（本票贡献导入守卫一条）;prompt 文本优化走 Evidence Feedback Loop;thinking 参数由获批 canary 实证（031)。

本 ticket 只锁定入口设计决策；未修改 runtime code、未调用模型、未进入 downstream。

> 后续修订（2026-08-30）：[Define the idea quality rubric](026-define-the-idea-quality-rubric.md) 修订 FinalizeIdea 结构校验：参数在 idea 对象之外新增 `grounding: [paper_id, ...]`，七字段 idea payload 本身不变；Declared Grounding 校验失败按 025 作为 Model-Fixable Error 回灌。字段级合约与 prompt 呈现方式由 [Define the declared grounding contract](038-define-the-declared-grounding-contract.md) 决定。

> 后续修订（2026-08-30）：[Define the declared grounding contract](038-define-the-declared-grounding-contract.md) 落定上述字段级合约，并扩大 prompt diff 围栏：工具描述段之外，系统 prompt 中 FinalizeIdea 相关的 ARGUMENTS 行与 IDEA JSON 示例块亦可修改，示例直接展示 `grounding` 键，保证描述与示例一致、避免模型照矛盾示例白烧付费轮次。

> 后续指针（2026-08-30）：[Define the validation and test matrix](027-define-the-validation-and-test-matrix.md) 已关闭；本票委托的导入守卫 pytest 占位落为 `docs/agents/validation-matrix.md` 的 VM-CONTRACT-024-01，preflight 逐步 fail-closed 测试为 VM-CONTRACT-024-02。
