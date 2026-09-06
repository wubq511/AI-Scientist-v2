# 模型可修复动作与反馈闭环验证证据（Ticket 08）

## 验证背景与范围

本证据文档对应 implementation ticket [08: Correct model-fixable actions](../wayfinder/ideation-implementation/tickets/08-correct-model-fixable-actions.md)，证明在单次 Ideation Run 的单个 generation 执行周期内，当模型输出遇到可修复的动作解析错误、未授权动作、检索参数异常、FinalizeIdea 结构不符、Declared Grounding 违背门禁或 Run 内创意近重复时，系统将其统一分类为 **Model-Fixable Error**，记录到操作工件与事件流中，并将最小、稳定、脱敏的反馈文本回灌至下一轮 reflection prompt，而不是直接中断 Run、静默跳过或污染后续 generation。若 reflection 轮次耗尽仍未纠正，generation 以 `budget_exhausted` 状态正常收尾，不影响 Run 级别其他成果及终局 Seal 封印。

验证过程全程在隔离沙盒内运行，采用确定性 `StubTransport`，**零外部网络调用、零真实模型费用**，未触发 downstream 阶段。

---

## 验证矩阵映射

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 结果 |
|---|---|---|---|---|
| **VM-CONTRACT-024-03** | FinalizeIdea 结构校验；封闭两键对象、7 字段 typed structure、非空检查、类型与 Name 正则严格校验，无静默修剪与隐式修复 | 杜绝缺失/多余字段或伪造结构落盘 | 024, 026, 038 | **PASS**（`tests/test_model_fixable_actions.py`） |
| **VM-CONTRACT-025-01** | 统一模型可修复错误反馈（5 大类：parse、unknown action、invalid arguments、retriever 双码、structure/gate/grounding/duplicate）；每错消耗 1 轮；落盘 `feedback.txt` 并发 `action_outcome` 事件；反馈精简脱敏 | 统一反馈管道，严禁吞错、静默 break 或泄漏路径/堆栈 | 024, 025, 038 | **PASS**（`tests/test_model_fixable_actions.py`） |
| **VM-CONTRACT-026-01** | Declared Grounding 契约落地；实现 `INVALID_GROUNDING`、`EMPTY_GROUNDING`、`UNRETRIEVED_PAPER` 三码；单 generation 检索文献范围隔离，拒绝跨 generation 偷渡文献 | 门禁与声明证据链真实可信，说谎立即截获 | 026, 038 | **PASS**（`tests/test_model_fixable_actions.py`） |
| **VM-INTEGRATION-02** | 端到端错误修复与自愈剧本：检索 → 结构违规 → 未检索文献引用 → 自愈纠错成功 → 成功封印并验证哈希链 | 证明模型可在控制循环中依据反馈逐步修正最终达标 | 024, 025, 026, 038 | **PASS**（`tests/test_model_fixable_actions.py`） |

---

## 核心实现与契约落地

### 1. 封闭两键与七字段非空结构校验（Tickets 024, 038）
- **封闭参数对象**：`FinalizeIdea` 的 `ARGUMENTS` 必须为包含且仅包含 `{"idea", "grounding"}` 的 JSON 对象。多余键抛出 `INVALID_IDEA_STRUCTURE`，缺失 `idea` 抛出 `INVALID_IDEA_STRUCTURE`，缺失 `grounding` 抛出 `INVALID_GROUNDING`。拒绝任何静默过滤或隐式修补。
- **七字段规范**：
  - 必须包含且仅包含：`Name`, `Title`, `Short Hypothesis`, `Related Work`, `Abstract`, `Experiments`, `Risk Factors and Limitations`；
  - `Name` 必须满足 `^[a-z0-9_]+$`，严禁空格或大写字符；
  - 5 个标量文本字段均须为非空字符串（strip 后长度 > 0）；
  - 2 个列表字段必须为非空 list，且内部元素均为非空字符串；
  - 含有空字节 `\x00` 或代理对字符时直接以 `PAYLOAD_CORRUPT` 终端终止，非模型可修复。

### 2. 模型可修复错误闭环机制（Ticket 025）
- **受控错误白名单**：系统定义 `MODEL_FIXABLE_ERROR_CODES`，严格限制为 12 个 approved 错误码：
  `PARSE_ERROR`, `UNKNOWN_ACTION`, `INVALID_ARGUMENTS_JSON`, `INVALID_QUERY`, `QUERY_TOO_LONG`, `GATE_REJECTED`, `INVALID_IDEA_STRUCTURE`, `INVALID_GROUNDING`, `EMPTY_GROUNDING`, `UNRETRIEVED_PAPER`, `DUPLICATE_IDEA_NAME`, `DUPLICATE_IDEA`。
  所有其余系统错误（如 `PAYLOAD_CORRUPT`, `HASH_MISMATCH`, `ADMISSION_TAMPERED`, `PATH_ESCAPE`）一律 Fail Closed 终止 Run。
- **操作工件与事件流留痕**：
  - 调用 `_record_model_fixable_error`，将错误描述写入当前操作目录下的 `artifacts/operations/<op_seq:06d>/attempts/<attempt_seq:06d>/feedback.txt`；
  - 发送 `action_outcome` 事件，载荷标记 `outcome = "model_fixable_error"`，记录 `action`, `error_code`, `feedback`，并在 `artifact_refs` 中引用该反馈文件。
- **反馈信息精简化与脱敏（Minimal & Actionable）**：
  - 反馈内容仅包含针对模型决策动作的引导提示，绝不包含宿主机本地绝对路径、文件 sha256、Python 调用栈或敏感内网元数据；
  - 将反馈字符串赋予 `last_tool_results`，在下一 reflection 轮次注入 `IDEA_REFLECTION_PROMPT`。

### 3. Declared Grounding 契约与严格生命周期隔离（Tickets 026, 038）
- **三个错误码精确分流**：
  - `INVALID_GROUNDING`：参数不是字符串列表、存在空白字符、路径分隔符或**重复的 paper_id**（严禁静默去重）；
  - `EMPTY_GROUNDING`：列表为空；
  - `UNRETRIEVED_PAPER`：引用的 `paper_id` 不属于当前 generation 检索得到的文献集合（错误提示中明确指出违背的具体 `paper_id`）。
- **Generation 间严格隔离**：
  - `generation_retrieved_paper_ids` 集合在每个 generation 开始前重置清空；
  - 上一 generation 检索到的文献，必须在当前 generation 重新执行 `SearchLiterature` 命中后方可声明，杜绝跨 generation 凭空记忆或幻觉引用；
  - 当前 generation 未进行有效检索即调用 `FinalizeIdea`，将被门禁拦截并返回 `GATE_REJECTED` 反馈。

### 4. 创意去重与预算耗尽处理（Tickets 025, 026）
- **Run 内去重**：
  - 检查 `validated_idea["Name"]`（精确比对，报错 `DUPLICATE_IDEA_NAME`）；
  - 检查 `validated_idea["Title"]`（大小写与首尾空白归一化比对，报错 `DUPLICATE_IDEA`）；
  - 均视为模型可修复错误，引导模型提交新颖方案。
- **预算耗尽（Budget Exhaustion）**：
  - 若 generation 耗尽 `num_reflections` 轮次仍未成功 finalize，触发 `generation.finished`，disposition 标记为 `budget_exhausted`，`idea_index = None`；
  - 计数器 `disposition_counts["budget_exhausted"] += 1`；
  - 控制流优雅移交至下一个 generation，不使整个 Run 崩溃；
  - 只要 Run 级别至少发生过一次非空文献检索，Run 依然正常封印成功。

---

## 验证测试套件

新建并运行 `tests/test_model_fixable_actions.py`，全量覆盖以下场景：

1. **`test_vm_contract_024_03_closed_two_key_object_and_seven_fields`**：
   - 验证缺失字段、未知附加字段、非法 Name 格式、空字符串、空列表等均抛出 `INVALID_IDEA_STRUCTURE`；
   - 验证合法七字段通过。
2. **`test_vm_contract_026_01_declared_grounding_codes_and_eligibility`**：
   - 验证空列表触发 `EMPTY_GROUNDING`；
   - 验证非 list、重复 ID（无静默去重）、首尾空格、路径分隔符触发 `INVALID_GROUNDING`；
   - 验证未检索文献触发 `UNRETRIEVED_PAPER` 并在错误提示中点名未检索的 paper_id。
3. **`test_vm_contract_025_01_model_fixable_errors_unified_feedback`**：
   - 连续构造 4 个错误：PARSE_ERROR（无 ACTION 块）、UNKNOWN_ACTION（代码执行伪动作）、INVALID_ARGUMENTS_JSON（损坏 JSON 语法）、INVALID_QUERY（缺失 query 参数）；
   - 证明每轮均写入 `feedback.txt`，发出 `outcome = "model_fixable_error"` 事件，无 traceback/绝对路径/hash，第 5 轮检索成功；
   - 证明 Run 最终以 `terminal_outcome = "success"` 封印。
4. **`test_vm_integration_02_model_fixable_recovery_script`**：
   - 完整自愈剧本：检索 → 结构违规（缺失 Abstract） → 声明未检索文献 → 纠正所有问题后 Finalize；
   - 验证 4 轮 reflection 轮次计数准确，事件链完全连续，`verify_chain` 核验通过，accepted idea 落盘。
5. **`test_near_duplicate_recovery_and_budget_exhaustion`**：
   - 验证 Generation 1 提交与 Generation 0 标题相同的近重复创意被截获，随后自愈提交独立创意成功接收；
   - 验证耗尽预算时的 `budget_exhausted` 状态记录与 Seal 汇总。
6. **`test_cross_generation_declared_grounding_isolation`**：
   - 证明 Generation 0 检索的文献不能直接作为 Generation 1 的依据；Generation 1 未经检索直接使用触发 `GATE_REJECTED` 反馈并在预算耗尽后转为 `budget_exhausted`。

---

## 测试执行结果汇总

```bash
# 1. 专属测试套件验证
$ python -m pytest tests/test_model_fixable_actions.py -v
======================== 6 passed, 6 warnings in 2.22s =========================

# 2. 既有密封 Run 套件验证（无破坏性回归）
$ python -m pytest tests/test_sealed_ideation_run.py -v
======================== 15 passed, 6 warnings in 3.26s ========================

# 3. 全量测试套件执行
$ python -m pytest -q
495 passed, 6 warnings in 52.05s

# 4. 代码编译与 Black 格式检查
$ python -m compileall ai_scientist tests
Listing 'ai_scientist'...
Listing 'tests'...
$ python -m black --check ai_scientist/ideation tests/test_model_fixable_actions.py tests/test_sealed_ideation_run.py
All done! ✨ 🍰 ✨
22 files would be left unchanged.
```

所有新增与存量检查全部一次性绿灯通过，验证链条完整闭合。
