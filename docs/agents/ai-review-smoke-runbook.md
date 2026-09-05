# AI 评审真实 smoke 执行手册（六次基础调用）

日期：2026-09-05。状态：**已执行**（2026-09-05，基础六次 + 修复/重跑共 14 次物理调用；执行证据与结果见 [ai-review-real-smoke-evidence.md](../research/ai-review-real-smoke-evidence.md)）。合同行为见 [ai-review-authoring-contract-v2.md](ai-review-authoring-contract-v2.md)，离线验收证据见 [ai-pair-review-offline-validation-evidence.md](../research/ai-pair-review-offline-validation-evidence.md)。

## 0. 授权门槛（执行前必须全部成立）

1. **付费与出站授权**：Robert 明确批准本次 smoke 的费用上界与数据出站范围。规格第 6 节：本规格与合同文档都不构成授权。
2. **exact model 配置**：两位评审必须来自**不同 model families**（两个人设不算两位独立模型），记 exact model id，不 fallback。写入执行配置前先与 Robert 确认模型选择。
3. **调用边界**：基础调用总数固定为 **6**——单条 idea 评审 ×2（primary/second 各一次）+ 合成 pair ×4（两 slot × ab/ba 两方向）。修复调用（如格式无效后的重发）必须逐次计数并记录物理调用与费用，**不得仅因 verdict 不理想而重跑有效结果**。
4. **token/费用预算声明**：执行前在执行配置的 `real_call_authorization` 中登记 token 上界、费用边界与出站范围声明；评审费用单独列项。

## 1. 执行配置模板（register-review-config 的输入）

`review-execution-config.json`（封闭 schema，占位值执行前替换）：

```json
{
  "schema_version": "evaluation-review-execution-config-v1.0.0",
  "authoring_contract_version": "evaluation-authoring-contract-v2.0.0",
  "prompt_versions": {
    "single": "single-review-v2",
    "pair": "pair-review-v1"
  },
  "evaluators": [
    {
      "slot": "primary",
      "provider": "<provider-1>",
      "model_id": "<exact-model-id-1>",
      "model_family": "<family-of-model-1>"
    },
    {
      "slot": "second",
      "provider": "<provider-2>",
      "model_id": "<exact-model-id-2>",
      "model_family": "<family-of-model-2, 必须不同于 family-1>"
    }
  ],
  "real_call_authorization": {
    "approved_by": "Robert",
    "approved_at": "<UTC timestamp>",
    "token_budget": "<如: 6 次基础调用 × 每次输入/输出 token 上界>",
    "cost_boundary": "<如: 基础六次最坏费用上界, CNY>",
    "outbound_scope": "<如: 单个 sealed run 的匿名评审材料包内容, 不含 data/raw 原始数据集>"
  }
}
```

注册（write-once，注册即冻结）：

```bash
python ai_scientist/perform_ideation_temp_free.py evaluation register-review-config \
  --config-file review-execution-config.json
```

## 2. 试评对象与合成 pair 要求

- **单条**：任选一个 sealed run 的一个 finalized idea（当前 slot 1 若只作只读诊断演示，必须披露暴露，其响应不得再充当 prompt 优化后的未见测试证据；用于调整 prompt 的材料一律标 development-only）。
- **合成 pair**：同一 case 的两个 sealed idea。合成 pair 的材料须包含**材料内部可证伪的明显缺陷**——「预期错误」来自给定事实的矛盾，不来自另一位 AI 的喜好；该 pair 的预期结果记录在执行前的工作日志，不写进任何模型可见内容（程序也会 fail closed 拦截身份泄漏）。

## 3. 六次调用序列

```bash
# 单条 ×2（两位评审独立上下文；同一份 review-request.txt 分别发送）
python ai_scientist/perform_ideation_temp_free.py evaluation export-review-package \
  --run-id <run_id> --idea-index <n>
# → 把 ai/review-request.txt 原样发给 primary 模型，保存回复
python ai_scientist/perform_ideation_temp_free.py evaluation import-review-response \
  --run-id <run_id> --idea-index <n> --evaluator-slot primary \
  --response-file <primary-output.txt> --provider <p1> --model-id <m1> \
  --responded-at <ts> --supplied-by Robert --imported-by <operator>
python ai_scientist/perform_ideation_temp_free.py evaluation validate-review \
  --run-id <run_id> --idea-index <n> --evaluator-slot primary
# → second 重复同样三步（--evaluator-slot second, m2），不得让第二位看到第一位答案
python ai_scientist/perform_ideation_temp_free.py evaluation aggregate-review \
  --run-id <run_id> --idea-index <n>

# 合成 pair ×4
python ai_scientist/perform_ideation_temp_free.py evaluation export-pair-package \
  --run-id-a <runA> --idea-index-a 0 --run-id-b <runB> --idea-index-b 0
# → pair-request-ab.txt 发给两个模型（各一次）；pair-request-ba.txt 同理
#   共四次发送，四个上下文互不知晓彼此
python ai_scientist/perform_ideation_temp_free.py evaluation import-pair-response \
  --pair-id <pair_id> --evaluator-slot primary --direction ab \
  --response-file <out.txt> --provider <p1> --model-id <m1> \
  --responded-at <ts> --supplied-by Robert --imported-by <operator>
python ai_scientist/perform_ideation_temp_free.py evaluation validate-pair-review \
  --pair-id <pair_id> --evaluator-slot primary --direction ab
# → 其余三个 (slot, direction) 组合重复；四次全部 validated 后：
python ai_scientist/perform_ideation_temp_free.py evaluation reduce-pair-review \
  --pair-id <pair_id>
```

失败处理：任何 `exit 1`（canonical JSON 错误码在 stderr）先读错误码；`INVALID_FORMAT` 类失败保留原始响应，可修复格式后作为**新的物理调用**重发并记录；引用核验失败（`CITATION_QUOTE_NOT_FOUND` 等）不得改材料迁就响应。

## 4. 真实报告必填字段

报告写入 `docs/research/`（中文），逐项引用程序产物中的数值，不手工美化：

| 字段 | 来源 |
|---|---|
| 引用有效数/总数 | 单条：两位 slot 各自记录 `ai/<slot>/vNNNN.json` 的 `citation_verification.refs_quote_verified / refs_total`（求和汇总）；pair：四条 `<slot>/<direction>/vNNNN.json` 同字段求和。共识记录与还原记录只携带 `refs_total` 合计，`refs_quote_verified` 以 slot/方向记录为准（语义支持恒标 `not_performed`） |
| 预设缺陷检出数/总数 | 合成 pair 的预期缺陷 vs 共识/还原 verdict |
| 已知误报数 | 预期无缺陷处出现的负面判定 |
| 弃权数 | 共识记录 `abstained` 维度数 + pair `incomparable` 判断数 |
| 模型分歧 | `conflict` 维度与 `evaluator_conflict` 还原原因 |
| 换位结果 | ab/ba 显示侧 verdict 与还原后 content 值；`position_flip` 出现即如实记录 |
| 物理调用次数 | 基础 6 + 每次修复调用的记录（时间戳、tokens、费用） |
| 延迟 | 每次调用的响应耗时（来自 provider 返回或操作者计时） |
| 费用 | 逐次与合计（CNY），与执行配置的费用边界对照 |

**禁止表述**：没有专家 gold 时不得报告「科研准确率」；没有人工计时时不得估计「造节省比例」；不得用通用基准分数（如 skill 示例中的 "80% accuracy"）替代本任务的验收。

## 5. 完成条件与失败处置

六次 smoke 的完成条件（规格第 6 节）：

1. 真实响应被解析与回链（记录、卡、还原报告全部落盘且哈希可核）；
2. 已知明显缺陷未被一致漏过；
3. 故意缺失的证据未被冒充存在（弃权/missing_information 行为正常）；
4. 换位不制造稳定假 winner（还原端 position_flip 正确拦截）。

任一失败 → 保留失败记录，回到对应 prompt 或材料修正后重试；prompt 修订即新版本（模板 SHA-256 重新 pin，旧响应不可与新版本合并）。smoke 只证明流程可用与最低检错行为，不证明双模型优于单模型，也不证明跨领域效果。
