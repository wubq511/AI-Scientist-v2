# 真实低谷期单 Case Live Smoke 运行证据报告 (Ticket 02)

## 1. 验证背景与目标范围

本报告对应 ideation-execution 路径的 ticket [02: Qualify one auditable live smoke run](../wayfinder/ideation-execution/tickets/02-qualify-one-auditable-live-smoke-run.md)，依据规范文档 [Auditable live DeepSeek execution and one-case smoke](../../agents/live-smoke-execution-spec.md) 执行并归档。

### 1.1 核心目标
在 Ticket 01 建立可审计的真实 DeepSeek 执行通道之后，在官方优惠/低谷时段，针对已批准的单一私有 Case (`case-229e495f82a24cff9e6082aa058955b9`) 执行一次完整的真实付费端到端 Smoke 运行。验证涵盖从前置交互式费用批准、DeepSeek V4 Pro 真实调用、状态机与文献检索控制循环、显式封印（Terminal Outcome: `success`），到静态证据链严密校验、脱敏发布导出、以及 post-seal 定性评测覆盖的全生命周期。

### 1.2 严格边界与红线遵从
- **单 Case 范围限定**：仅运行单一经批准的私有 Case，固定参数 `max_num_generations=1`、`num_reflections=3`、`reasoning_effort=high`、`max_tokens=32768`；绝不触碰或声称关闭 Ticket 035/036，绝不启动 12-case Canary 或批量矩阵评测。
- **阶段边界**：Ideation 阶段在生成与定性评测完成即告终止，严禁进入 BFTS、代码生成、实验运行、论文撰写或审稿流程。
- **信息脱敏**：本报告及 Git 追踪物中绝不包含 API Key、Prompt 原文、模型思维链推理原文、构想详细内容、Target Paper 真实明文身份、Provider 内部 Response ID、凭证值或主机绝对路径。

---

## 2. 为什么本次运行结果绝对可信 (Trustworthiness)

本次 Live Smoke 产出的科学与工程结论建立在以下不可篡改的证据支柱之上：

1. **强密码学 Hash 链绑定 (Cryptographic Hash Chain)**：
   - 运行前通过 Git Commit SHA、工作区 Clean 状态、数据源与 Workshop Manifest 的 SHA-256 严密锁定输入；
   - 运行过程中产生的 23 个结构化事件以 SHA-256 逐项哈希链接，形成连续、不可逆的单向证据链；
   - 最终产物由 `seal.json` 封印，明确固定 Terminal Outcome 为 `success`，并封印全部 13 个产物的校验和。
2. **严苛的静态证据链验证 (Fail-Closed Static Validation)**：
   - 运行完成后，执行 `perform_ideation_temp_free.py validate`，工具通过纯标准库独立验证器对证据链进行了全量静态重算；
   - 验证确认：无篡改、无事件缺失、无悬挂产物、哈希链完全闭合，状态判定为 `valid`。
3. **白名单正向脱敏与门禁扫描 (Sanitized Export)**：
   - 通过 `perform_ideation_temp_free.py export` 将私有证据链导出到 `evidence/ideation-runs/f7bddd3e-cd3c-4f66-9b6d-7d30c25c1db0/`；
   - 导出器采用正向白名单机制，仅提取无害元数据；并通过全部 10 项发布门禁扫描（确认无私有路径、无密钥、无 Prompt/Reasoning 泄露），产出幂等文件。
4. **100% 覆盖的人工定性评审 (Human-in-the-Loop Post-Seal Evaluation)**：
   - 严格遵循 Ticket 12 与合同 037 规范，为该 Run 的构想组装 Hash 链接的评估简报；
   - 由 Robert 作为唯一定性判分者完成 draft 审定，经由工具执行闭合 Schema 与语义约束机检后写入不可覆写的 `v0001.json`；
   - `list-coverage` 证明覆盖率为 100%（`covered: 1, draft_only: 0, missing: 0`），绝不依赖不可靠的数字打分或 LLM Judge。
5. **完备的回归测试守护 (100% Green Test Suite)**：
   - 仓库内全部 641 个自动化测试用例在 Python 3.14 环境下 100% 通过（耗时 81s），无任何回归破坏。

---

## 3. 运行成本分析与估算偏差复盘

在实际请求 API 前，准入模块根据声明的最高预算与模型峰值费率计算了保守成本上限，并获得交互式批准。运行结束后，记录的真实扣费呈现出极大的经济优势：

| 成本指标 | 保守估算上限 (Peak Rate, All Miss) | 实际发生值 (Off-Peak Actual) | 偏差幅度 |
|---|---|---|---|
| **输入成本 (Cache Miss)** | 1.77 CNY | 0.038 CNY | -97.8% |
| **输出成本 (含 Reasoning)** | 5.31 CNY | 0.103 CNY | -98.0% |
| **总计金额 (CNY)** | **7.08 CNY** | **0.14 CNY** | **-98.0% (节省 6.94 CNY)** |

### 3.1 偏差来源剖析
1. **时段优惠**：运行安排在北京时间低谷时段（UTC 05:30 左右），命中了 DeepSeek 官方公布的半价计费区间；
2. **保守预算余量**：准入时的估算模型假设每次推理均打满 `max_tokens=32768` 且每轮发生最大 2 次重试（Worst-Case Bound）；而实际运行时，模型在各轮次均一次性生成成功，未发生任何超时或重试；
3. **Token 分布细节**：
   - **Operation 1 (Round 0 初始构想与初搜)**: Prompt 1,069 tokens, Completion 381 tokens (含 206 思考 tokens), 耗时 8.7s, 扣费 0.01 CNY；
   - **Operation 3 (Round 1 检索反思与批判)**: Prompt 2,058 tokens, Completion 888 tokens (含 519 思考 tokens), 耗时 18.0s, 扣费 0.03 CNY；
   - **Operation 5 (Round 2 深度反思与创意定稿)**: Prompt 3,745 tokens, Completion 6,290 tokens (含 5,174 思考 tokens), 耗时 149.6s, 扣费 0.10 CNY；
   - **全流程 Token 消耗总计**: 14,431 tokens（含 5,899 reasoning tokens），总耗时约 176s。

---

## 4. 运行体验发现与第一性原理优化

### 4.1 痛点发现：深度思考期的交互静默
在实际运行过程中，用户在终端交互确认输入 `yes` 后，经历了长达约 2.5 分钟的无终端输出等待期。
- **根本原因**：DeepSeek V4 Pro 处于 `reasoning_effort=high` 模式下，针对复杂的跨文献反思与方案定稿进行深度探索，单次调用生成了超过 5,100 个 reasoning tokens，耗时达 149.6 秒。此前为了保证 CLI 的 `sys.stdout` 输出为严格的纯 JSON（供管道下游如 `jq` 安全消费），控制器未向终端输出任何中间过程信息，导致用户面临“是否卡死或未响应”的困惑。

### 4.2 解决方案：第一性原理驱动的非破坏性进度回显
依据第一性原理设计并实施了体验优化：
1. **通道正交隔离**：
   - 保持 `sys.stdout` 100% 为只读、纯净、幂等的机器可读 JSON 输出，不添加任何非 JSON 字符；
   - 将所有人类友好的实时进度信息定向输出至 `sys.stderr`；
2. **TTY 感知与零开销**：
   - 仅当 `sys.stderr.isatty()` 为真（交互式终端环境）或显式传入测试缓冲流时才激活回显；在自动化非交互管道中保持静默；
3. **适量生动的状态反馈 (含 Emoji)**：
   - 准入与批准：`✓ 费用已批准，Run 准入成功 (Run ID: ...)，正在启动推理与检索控制循环...`；
   - 探索轮次：`🚀 [Generation 1/1] 开始探索科研构想...`；
   - 模型思考与完成：`🧠 [Model] 正在调用 DeepSeek 进行第 2 轮反思批判 (深度推理中)...` -> `✨ [Model] 推理完成 (耗时 149.6s | 消耗 6290 tokens (含思考 5174 tokens) | 费用 0.10 CNY)`；
   - 文献检索：`🔍 [Tool] 执行文献检索 SearchLiterature -> 命中 N 篇相关文献`；
   - 构想接受：`💡 [Idea] 创意定稿接受成功: "..." (声明引用 N 篇文献)`；
   - 证据封印：`🔒 [Seal] Run 证据链封印完成 (Terminal Outcome: success, Run ID: ...)`。
4. **架构与单元测试验证**：
   - 修复并优化了 `IdeationController` 初始化结构，新增单元测试 `test_cli_seam_progress_stream_emits_expected_markers`；
   - 验证通过，既满足了终端人类操作者的确定性安全感，又丝毫不破坏已有契约与数据结构。

---

## 5. 脱敏证据链清单与 Hash 索引

本 Run 产生的所有私有物料受 `.gitignore` 保护，其脱敏哈希索引如下：

| 证据项 | 路径 / 标识 | SHA-256 校验和 / 属性 |
|---|---|---|
| **Run 标识符** | `run_id` | `f7bddd3e-cd3c-4f66-9b6d-7d30c25c1db0` |
| **Case 标识符** | `case_id` | `case-229e495f82a24cff9e6082aa058955b9` |
| **准入请求凭证** | `admission.json` | `f41750bd6b02188e04f7ddd79c3ef239067c9b2e9772abdf9ddca725a897ca90` |
| **最终封印文档** | `seal.json` | `c58b36238df4589d011a83d4d5a231d452b35eee1a475ae65758f2da54fa88fa` |
| **事件链尾部 Hash** | Final Event Hash | `a7ef55fe638d1855610a0af059ed6a2521af73480321908e56692db36ae4894c` |
| **生成构想成果** | `idea.json` (Index 0) | `e3f60d52bd3f947f361b19edc2b8418590210fda207a97b866ae5777df607894` |
| **脱敏导出清单** | `evidence/.../manifest.json` | `3ade05a1aae8ebb9aae750a605bc0a244ddaedbc8e9ca781b4d4780a9b9c3535` |
| **脱敏导出事件** | `evidence/.../events.json` | `13e19fcb16ac05650ec1fe82542bffe58ea10b6ff19e9bcf09a5bcff9863fef1` |
| **定性评估报告** | `brief.md` (Index 0) | `d510d02e9f809a5d72e3954c7612dfe0e8e4d4b3da76646f774183e7aacbe242` |
| **定性评估定稿** | `v0001.json` (Index 0) | `dc1b6dbe5c0bb6fee3bb8a931648a3292cd50cd4f3c00d47c2cc9b4b07ebabf6` |

---

## 6. 验收与交付结论

- [x] 成功执行单一 Case 的真实 DeepSeek V4 Pro Smoke 运行；
- [x] 终端交互计费批准流程与实际计费记录完整闭环；
- [x] 静态证据链验证、脱敏发布导出双重通过；
- [x] 组装并完成了人工定性评估（覆盖率 100%）；
- [x] 解决了长时间模型思考时的交互反馈痛点，经 TDD 单元测试验证且回归通过；
- [x] 本票证明目标全部达成，Ticket 02 满足关闭条件。
