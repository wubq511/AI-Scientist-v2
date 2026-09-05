# AI 评审双评审与成对盲评离线验证证据（ticket 02）

日期：2026-09-05。对应 implementation ticket [02-deliver-independent-and-pairwise-review](../wayfinder/ai-assisted-ideation-evaluation/tickets/02-deliver-independent-and-pairwise-review.md)，authoring contract 见 [ai-review-authoring-contract-v2.md](../agents/ai-review-authoring-contract-v2.md)，真实 smoke 执行入口见 [ai-review-smoke-runbook.md](../agents/ai-review-smoke-runbook.md)。

## 验证范围声明（诚实边界）

- **本报告只覆盖离线编码验收**：deterministic fixtures 证明软件契约（评审执行配置、双评审隔离与汇总、成对包匿名导出、四次独立评审、盲映射还原、还原报告与质量底线携带）。
- **未验证**：真实模型评审质量、双模型优于单模型、跨领域效果。六次基础真实 smoke（单条 ×2 + 合成 pair ×4）是效果验收对象；执行前不得把「offline fixtures 通过」表述为「评审效果通过」。
- **真实 smoke 尚未执行**：当前无付费授权，本会话没有发生任何付费 API 调用或真实模型评审响应；全部测试响应为离线 fixture。
- 编码验收与真实模型效果验收按票面要求分开：本票交付可执行入口（六个 CLI 子命令 + runbook）与离线报告；有授权后的六次真实结果与失败记录留待执行时交付。

## 验证矩阵映射

| 行 ID | 检查项 | 结果 | 证据 |
|---|---|---|---|
| **VM-QUAL-03** | 双评审共识与成对盲评还原的机检面（见 [validation-matrix](../agents/validation-matrix.md) 修订说明） | **PASS**（`tests/test_ai_pair_review.py` 17 tests + `tests/test_ai_review_evaluation.py` 37 tests 中 ticket 02 新增 14 项） | 见下 |

## 已验证行为

### 评审执行配置（两个隔离 evaluator）

1. **注册 golden**：`register-review-config` 校验封闭 schema、恰好两个 slot、pinned prompt 版本（`single-review-v1`/`pair-review-v1`），write-once 落盘 `artifacts/evaluations/ai-review-config.json`；重复注册（含内容相同）`ARTIFACT_EXISTS`；结果含 config SHA-256 与两 slot 的声明值。
2. **独立性强制**：同 model family → `REVIEW_CONFIG_FAMILIES_NOT_DISTINCT`（同模型的两个人设不是两位独立评审）；同 exact model id → `REVIEW_CONFIG_MODELS_NOT_DISTINCT`；prompt 版本不符 → `REVIEW_CONTRACT_MISMATCH`。三种拒绝均不落盘。
3. **声明值的诚实记录**：family 是操作者声明，程序不认证，逐字记录并标注「声明值，程序未认证」；config 的 SHA-256 进入共识记录与还原记录（`review_config_sha256`）。
4. **绑定检查**：config 已注册时 `validate-review` / `validate-pair-review` 强制响应声明的 provider/model_id 匹配该 slot 的 config 绑定（不匹配 `REVIEW_CONFIG_MISMATCH`）；`aggregate-review` / `reduce-pair-review` 无 config 即 `REVIEW_CONFIG_NOT_FOUND`。

### 双评审汇总（单条 idea）

5. **slot 隔离**：`import-review-response` / `validate-review` 按 `--evaluator-slot {primary,second}` 写入 `ai/<slot>/responses/rNNNN.json` 与 `ai/<slot>/vNNNN.json`；同一响应文本可分别导入两个 slot，各自独立版本化，互不覆盖。slot 布局迁移后 v1 人工 artifact 与单评审行为零回归（23 项既有测试全过）。
6. **共识规则**（`aggregate-review` golden）：两方 judged 同 verdict → `consensus` 并保留**双方原始 rationale**；verdict 不同 → `conflict`；任一方弃权 → `abstained`；缺侧记录 → `incomplete_evaluator`。全部七维共识时 coverage = `complete_resolved`。
7. **一致负面保留为负面**：两 slot 一致 `unsound` → 共识 verdict 原样 `unsound`、质量底线 `violated`（有专项测试）。
8. **unresolved 保真**：单维分歧 → 该维 `conflict`、coverage `complete_unresolved`；floor 维弃权 → `abstained`、底线 `unresolved`（`consensus_verdict: null`）。
9. **invalid/missing 不伪装完成**：某 slot 只有不可解析响应 → slot 状态 `invalid`、coverage `invalid`；无响应 → `missing`；已导入未验证 → `unvalidated`——三种状态在共识记录 `evaluators` 块中独立记账，judgments 侧记 `incomplete_evaluator`，永不计入 `complete_unresolved`（有专项测试）。
10. **防篡改再验证**：聚合时对每 slot head 记录重验封闭 schema、run/case/seal/idea/包哈希/prompt/rubric 绑定、slot 与 `author_type=AI`、user_supplied provenance、线性 supersedes 链、响应文本哈希链（响应文本 ↔ 导入记录 ↔ 记录三方一致）与「记录 judgments ≡ 响应重推导」逐字比对；篡改响应文件 → `HASH_MISMATCH`（有专项测试）。重聚合产生 v0002 supersedes v0001，per-slot 记录字节不动。
11. **共识卡**：`consensus-card.md`/`.html` 由记录确定性渲染，含两位评审声明模型与 family、coverage 与质量底线中文标注、逐维双侧理由；HTML 自包含（无脚本、无外部资源）。

### 成对盲评（两个匿名 idea）

12. **导出 golden**：`export-pair-package` 从同 case 两个 sealed run 推导确定性 pair 包 + 双方向请求；重复导出逐字节一致；`pair_id` 为 canonical `{arms, case_id}` 的 16-hex 截断。盲映射固定 `ab: {arm_a: content_1, arm_b: content_2}` / `ba: {arm_a: content_2, arm_b: content_1}`。
13. **盲包匿名性**：方向 payload（model-visible）断言不含 case_id、两个 run_id、pair_id、`content_1`/`content_2`、profile 标识（`ml-baseline-v1`/`cross-domain-v1`）、`expected_winner`、`cost_cny`；程序侧还有 key 名 + 序列化文本双向扫描（`PAIR_PACKET_BLIND_LEAK`）。共享材料编为 `C001–C003`，两臂 idea 字段/审计声明/检索节选编为 `A###`/`B###`；**换位对称性有专项断言**（ab 的臂 A 文本集合 ≡ ba 的臂 B 文本集合，反之亦然）。真实身份只在外层 `arms`/`blind_mapping`/`source_registry`（私有）。
14. **臂合法性**：同 run 同 idea → `PAIR_ARMS_IDENTICAL`；两 run 的 idea 载荷逐字节相同 → 同样拒绝。
15. **四次独立上下文**：`(primary|second) × (ab|ba)` 各自存储 `responses/rNNNN.json` + `vNNNN.json`，导入记录绑定 `(pair_id, direction, slot)` 与包/请求哈希；同一上下文重复导入追加序号（write-once）。provenance 恒为 `user_supplied`；声明 provider/model_id 与 config 绑定强制一致。
16. **成对响应校验**：三判断封闭枚举（`overall_preference`/`domain_method_fit` ∈ {a_better,b_better,tie,incomparable}；`unjustified_ml_intrusion` ∈ {a_more,b_more,equal,incomparable}）；引用逐字核验（伪造 quote → `CITATION_QUOTE_NOT_FOUND`、伪造 source → `CITATION_SOURCE_NOT_FOUND`）；judged 无引用须「推断：」开头；任一 incomparable 必须 `missing_information` 非空；task 错误/非法枚举 → `INVALID_SCHEMA`；不可解析 head → `REVIEW_RESPONSE_INVALID_FORMAT`。
17. **跨方向合并阻断**：针对 ab payload 撰写的响应（引用臂 A 的 Short Hypothesis 原文）在 ba 上下文校验即 `CITATION_QUOTE_NOT_FOUND`——同一显示位在不同方向展示不同内容，伪造的跨包引用无法通过逐字核验。请求漂移 `PAIR_REQUEST_DRIFT`、pair 包篡改 `PAIR_PACKAGE_DRIFT`、模板篡改 `POLICY_DRIFT` 均先于任何落盘触发。
18. **还原规则**（`reduce-pair-review`，四方向 verdict 经盲映射还原到内容空间）：
    - **稳定 winner**：两位评审各自在两方向一致偏好同一内容 → `stable` + `content_value`（专项测试）；
    - **稳定 tie**：四者全 tie → `stable tie`（专项测试）；
    - **换位翻转**：某 slot 恒偏好显示位 A（ab 选 content_1、ba 选 content_2）→ `position_flip`、incomparable（专项测试）；
    - **评审偏好冲突**：两 slot 各自内部一致但偏好不同内容 → `evaluator_conflict`、incomparable（专项测试）；
    - **无效响应**：任一上下文只有不可解析响应 → `missing_valid_record` 逐上下文点名、coverage `incomplete`；缺一次验证同路处理（专项测试 ×2）；
    - **全部 incomparable**：四者一致 incomparable → `incomparable_judgment`、不产生稳定结果（专项测试）。
19. **有效结果不重跑**：程序无任何「重评有效结果」路径；还原记录 write-once + supersedes，修订只能新增版本且旧记录逐字节保留。
20. **质量底线独立携带**：每臂底线状态取自其 idea 的双评审共识记录（无共识记录 → `not_evaluated`）；一臂 `violated`（一致 unsound）另一臂 `clean` 时，整体偏好不受影响（稳定 tie 仍 stable），底线状态随还原记录与报告独立呈现（专项测试）。
21. **还原报告**：`pair-report.md`/`.html` 由还原记录确定性渲染，私有侧明示 content↔run 绑定与原因分类学；HTML 自包含无脚本。协议版本错配（模板/包/config 缺失或漂移）阻止合并（`POLICY_DRIFT`/`PAIR_PACKAGE_DRIFT`/`REVIEW_CONFIG_NOT_FOUND`）。
22. **CLI 全链路**：六个新子命令（`register-review-config`、`aggregate-review`、`export-pair-package`、`import-pair-response`、`validate-pair-review`、`reduce-pair-review`）的 subprocess 级成功/失败 exit code 与 canonical JSON 输出均有测试；单条 `import-review-response`/`validate-review` 的 `--evaluator-slot` 参数（默认 `primary`）兼容旧调用。

## 两轴 code-review 修正记录

Standards/Spec 两条轴共 6 类发现，修复 5 类：

- **fail-closed 回归（Standards 近硬伤）**：slot 化 import 迁移时丢了 responses 目录的 symlink 前置检查，预先放置的符号链接可重定向 write-once 响应落盘位置——`import_review_response` 与 `import_pair_response` 均在 mkdir 前补回 `SYMLINK_FORBIDDEN`；
- **validate-pair-review 的 config 要求与合同不对齐（Spec）**：合同规定「已注册 config 时」才强制绑定，实现却无条件要求——改为与单条 `validate_ai_review` 相同的条件语义，并补测试（无 config 可 validate；config 注册后 reduce 仍强制；仅一条有效记录时 reduce 走 incomplete 而非静默稳定）；
- **runbook「引用有效数/总数」来源写错（Spec）**：共识/还原记录只携带 `refs_total`，`refs_quote_verified` 须从 per-slot / per-direction 记录求和——runbook 第 4 节已改正；
- **死代码与重复（Standards judgement）**：删除从未引用的 `_CONSENSUS_STATES`/`_COVERAGES`/`_SLOT_STATES`；pair 模块复用 `ai_review` 的 `_verify_supersedes_chain`（参数化为 record-kind label，删除未用 run/idea 参数与内联循环）、`RESPONSES_DIRNAME` 与 `_SINGLE_EVALUATOR_KEYS`（别名 `PAIR_EVALUATOR_KEYS`）；
- 提交拆分：按仓库惯例拆 feat/docs 两个 commit（见 git log），不把文档关票与代码混在一个提交里。

记录为判断项未修复：`_pair_record_state` 与 `_slot_record_state` 仍是两个模块内的平行实现（共享底层 helper，完整合并需跨模块抽象，留待 ticket 03 统一收敛）；CLI argparse 的 slot choices 硬编码与文件既有 parser 风格一致；`QUALITY_FLOOR_PROBLEM_VERDICTS` 与 `comparison.py` 的 `RUBRIC_FLOOR_PROBLEM_VALUES` 是有意的跨阶段镜像（语义锚点在注释中声明）。

## 测试与命令记录

- `python -m pytest tests/test_ai_pair_review.py tests/test_ai_review_evaluation.py -q` → **54 passed**（pair 17 + 单条/双评审 37）；
- `python -m pytest tests/test_ideation_import_contract.py -q` → **1 passed**（`ai_scientist.ideation.ai_pair_review` 加入期望 stdlib-only 闭包）；
- `python -m pytest -q`（全量）→ **841 passed**（基线 810 + 新增 31）；
- `python -m compileall ai_scientist` → 通过；`python -m black --check`（本票全部改动文件）→ 通过（仓库其余历史文件未触碰、未重排）；
- 环境：macOS arm64，仓库 Python 3.13 reference 环境；无新增第三方依赖（runtime import 闭包仍为 stdlib + httpx）。

## 关键产物清单

- `ai_scientist/ideation/ai_pair_review.py`：pair 包推导/导出、四次独立 import/validate、盲映射还原、还原报告渲染；
- `ai_scientist/ideation/ai_review.py`：评审执行配置、slot 化 import/validate（`ai/primary/`、`ai/second/` 布局）、`aggregate_review` + 共识卡；
- `ai_scientist/ideation/policies/ai-review-prompt-pair-v1.md`：pinned 成对模板 `pair-review-v1`（SHA-256 `3e0bf6e3b78927f1c752a738a10021c42f05714dbe35af0830b8710445f94778`，pin 于 `contract.py`）；
- `ai_scientist/ideation/contract.py`：新增七个 schema/prompt 版本 pin；
- `ai_scientist/perform_ideation_temp_free.py`：六个新 CLI 子命令 + `--evaluator-slot`；
- `docs/agents/ai-review-authoring-contract-v2.md`（双评审与成对章节）、`docs/agents/ai-review-smoke-runbook.md`（六次调用计划 + config 模板 + 报告字段）、validation-matrix VM-QUAL-03 行、CONTEXT.md 新术语。

## 未执行项（真实 smoke，待授权）

- 六次基础真实评审调用（单条 ×2 + 合成 pair ×4）及其修复调用的物理计数、延迟与费用统计——需要 exact model 配置、费用上界与数据出站授权后按 runbook 执行；
- 含材料内部可证伪缺陷的合成 pair 的真实构造与「预期错误」登记；
- 修订单（revision）与 evaluation protocol manifest、修订版 Promotion Gate 的接入属 ticket 03 的交付面，本票未触碰 comparison 链路。
