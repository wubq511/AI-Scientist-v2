---
title: Define the declared grounding contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 026-define-the-idea-quality-rubric.md
---

## Question

What exact argument schema, field semantics, paper_id eligibility and limits, error codes, prompt surfacing, and merge into the FinalizeIdea structure validation of [Define the safe ideation entry](024-define-the-safe-ideation-entry.md) define the Declared Grounding mechanism decided by [Define the idea quality rubric](026-define-the-idea-quality-rubric.md)?

## Resolution

2026-08-30 经 grilling 两轮七题由 Robert 批准。Declared Grounding 字段级合约如下，服从 026 的 rubric 决策与 020/024/025 的既有边界。

### 参数形状与语义

- `FinalizeIdea` 参数为封闭两键 object：`{"idea": {...}, "grounding": [...]}`；未知键 = 结构违规，禁止静默丢弃（020 先例）。
- `grounding` 是 JSON array of non-empty strings，元素为本 generation 已返回的 `paper_id`；重复 id = 违规（不静默去重）；数组顺序无语义。
- 语义：模型声明本 idea 依据哪些**本 generation 实际检索到并返回**的 paper。合法但为空的列表 = 违规（必须声明 ≥1 依据）。
- v1 不设数字上限：自然上界 = 检索预算 × top_k；过度声明完整留证，由 post-seal grounding 综合质量（026 第七项）判定；若 canary 证据显示泛滥，经 Evidence Feedback Loop 再加版本化上限。

### Eligibility 集合（收紧 026 措辞）

- 声明 id 必须 ∈ **本 generation** 已返回 Retrieval Results 的 paper_id 并集——`msg_history` 作用域为单 generation（025），模型只能合法声明它本 generation 见过的证据。026 写「本 run 的 Retrieval Audit Events」，此处收紧为其子集，026 留有指针。
- 集合由 controller 从本 generation `literature_retrieval` operation 的私有 audit artifacts 派生，永不进 model context。

### 错误码与失败语义

- 封闭三码，全部 Model-Fixable Error 回灌（消耗一轮 reflection，025 语义），文本最小、可操作、无内部细节：
  - `INVALID_GROUNDING`：字段缺失、类型错误、空字符串元素、重复 id；
  - `EMPTY_GROUNDING`：合法但为空的列表；
  - `UNRETRIEVED_PAPER`：声明了本 generation 未返回的 id（说谎检测，指出哪个 id）。
- 确切文案以版本化 tracked file 随实现 ticket 落地。

### Finalization gate 检查顺序（固定优先级）

1. **Payload hygiene scan**：对 raw submission bytes 执行，JSON parse 失败也照扫；命中 → Terminal Outcome `failed`。terminal 条件永远优先检测，不得被任何 model-fixable 反馈掩盖。
2. 024 结构校验（七字段、类型、非空）。
3. Declared Grounding 校验（三码）。
4. Run 内去重（阈值归 027）。

每轮只报优先级最高的一个失败（025：每轮恰好一个 action 结果）；下次 attempt 从头重跑全部检查。

### Prompt 呈现（修订 024 diff 围栏）

- 024「Prompt diff 限于系统 prompt 的工具描述段」扩大为：工具描述段 + 系统 prompt 中 FinalizeIdea 相关的 ARGUMENTS 行与 IDEA JSON 示例块，示例直接展示 `{"idea": {...}, "grounding": [...]}`——描述与示例必须一致。024 留有指针。
- 确切 prompt 文本以版本化 tracked file 随实现 ticket 落地，hash pin 进 Run Specification。

### 版本化与证据归属

- FinalizeIdea contract 版本升级；rubric version 引用该版本，Run Specification 两者都 pin。
- 声明的 grounding 列表存 idea sidecar provenance（008/023），finalize event 只放 artifact ref，不内嵌。
- Resume 无新规则：eligibility 集合从同一批复盘 audit artifacts 重建（025 已重放重建各 generation 检索标记）。

本 ticket 只锁定 Declared Grounding 字段级合约；未实现 runtime code、未修改 prompt、未调用模型、未进入 downstream。