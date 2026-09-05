# 真实迁移执行手册（ticket 03 — comparison 接入 AI 评估）

日期：2026-09-05。状态：**未执行**（离线编码验收已完成，真实迁移需 Robert 批准评估协议修订后按本手册执行）。合同行为见 [ai-review-authoring-contract-v2.md](ai-review-authoring-contract-v2.md)「Comparison 接入（ticket 03）」一节；规格见 [ai-assisted-ideation-evaluation-spec.md](ai-assisted-ideation-evaluation-spec.md) 第 7 节；迁移 rehearsal 证据见 `tests/test_comparison_migration_rehearsal.py`（13 项）与 `tests/test_evaluation_costs.py`（23 项）。

本手册是**可执行操作手册**：所有命令、哈希、目录都是当前真实状态；每一步都有机器检查，任何检查不过都 fail closed 并停在原地（见「失败保留」）。

## 1. 前置条件（全部成立才能开始）

1. **Robert 显式批准评估协议修订**：`evaluation register-evaluation-protocol` 注册 `evaluation-protocol-manifest.json`（首条输出后的评估协议修订，含固定 `revision_disclosure`）并批准修订版 Promotion Gate 对 AI 记录的消费。**当前未批准**；本手册与任何离线验收都不构成该批准。
2. **真实 smoke 按 [ai-review-smoke-runbook.md](ai-review-smoke-runbook.md) 通过并出证据报告**：已满足——2026-09-05 六次基础调用 + 修复/重跑共 14 次物理调用全部完成，runbook 四个完成条件 4/4（预设缺陷 4/4 检出、引用 31/31 + 37/37 逐字通过、position_flip/evaluator_conflict 为 0），证据报告 [ai-review-real-smoke-evidence.md](../research/ai-review-real-smoke-evidence.md)。注意：slot 1 材料因此被暴露（development/diagnostic），见第 4 节。
3. **provider 配置可用且已注册**：当前 pin = `artifacts/evaluations/ai-review-config.json`（`evaluation-review-execution-config-v1.0.0`）：primary=deepseek/`deepseek-v4-pro`、second=moonshot/`k3-256k`（Kimi Code 订阅端点），两 slot 异 model family、异 exact model id；config SHA-256 当前为 `807886563f9770de29084bf719d46795dc709252471c6cc606080520f5d6ce30`（supersede 留档 `ai-review-config-archived-20260905T114121Z.json`）。config 变更会使已注册 manifest 加载失败（`EVALUATION_PROTOCOL_MISMATCH`），因此迁移期间**不得再 supersede config**。
4. **每个 run 费用单独确认**：生成端沿用 production admission 的逐 run 交互式批准（`yes`），与 Plan Gate、reservation 互不替代；每个真实评审调用同样逐次记录并确认。
5. **评审费用预算单独列出**：AI 评审费用记入独立台账 `artifacts/evaluations/evaluation-cost-ledger.json`（`evaluation-cost-ledger-v1.0.0`，`evaluation init-evaluation-cost-ledger` / `record-evaluation-cost`），**不占用**生成端 30.00 CNY 硬上限口径——这是独立的新预算列项，其**上限必须由 Robert 单独批准**（当前未批准）。smoke 期间已发生的 DeepSeek 1.6224 CNY 与 Kimi 订阅零边际费用属于 smoke 授权范畴，不入迁移评审预算。

## 2. 迁移拓扑

| 侧 | 位置 | 要求 |
|---|---|---|
| 生成 workspace | 原 execution-code pin `d733ffed3bdb913598b8db46330cbbbc0af24610` 的 **clean worktree** | 当前 HEAD（写作时 `871a813f…`）已超过 pin，主工作区 dirty/漂移被旧 runner fail closed（`DIRTY_WORKTREE`/`EXECUTION_CODE_PIN_MISMATCH`）；剩余生成只能在这个 worktree 内执行 |
| 评估 workspace | **当前工作区**（含 ticket 03 全部代码、已注册的 `artifacts/evaluations/ai-review-config.json` 与全部评估端工具） | 全部 post-seal AI 评估、ingestion、reduction 只在这里执行；不要求 HEAD 等于 pin |

建立生成 worktree（一次性）：

```bash
git worktree add /Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2-pin \
  d733ffed3bdb913598b8db46330cbbbc0af24610
```

`artifacts/` 是 gitignored 私有目录，worktree 不会自动带有：把冻结比较包（及该 slot 引用的 corpora/workshop 等私有输入）从评估 workspace 复制进 worktree，**保持原相对布局** `artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/`，然后用机器检查核验（见下）。

冻结比较包的六个冻结文件在两个工作区各持一份字节相同的副本（`FROZEN_PACKAGE_FILES`；`spend-ledger.json` **不在**冻结清单——它是串行推进的权威账本，由 recency comparison 覆盖）：

| 文件 | 当前 SHA-256 |
|---|---|
| `selection-manifest.json` | `b09488322ce934e1aca1ce3020791240a23c6f55a68eee2dc66a14c3076bc83f` |
| `selection-approval.json` | `9944dc5e4d00fc6aaec1f541ccc6bb7481bca8a36e3634a3a6e63bcf49e893ba` |
| `run-matrix.json` | `c8a9217ffcf60718cc132ef04688bdf0bd3bd23758f0e54373993e1237d78ef4` |
| `blind-mapping.json` | `a605f3755b7bfeeb6497f6e27a9bc1e3f6f36822155497f1c9f19d85388f0a9e` |
| `commands.txt` | `3851ca37ed6fdc9fe2c634238d865693db4f3663859f9d1c6bcedc2b62664af6` |
| `execution-code-pin.json` | 运行期产物，**用 vault 内现值核验**——写作时 `841f8bbe77a136c3230e240033fcd895a4c0b8de96ce5cdaadd48a69d0527556`（commit `d733ffed…`，pinned_at 2026-09-05T02:59:09Z） |

核验命令（两个 workspace 都要跑，缺文件 `MIGRATION_PACKAGE_MISSING`、字节漂移 `MIGRATION_PACKAGE_DRIFT`）：

```bash
python ai_scientist/perform_ideation_temp_free.py evaluation verify-migration-package \
  --expected-sha256 selection-manifest.json=b09488322ce934e1aca1ce3020791240a23c6f55a68eee2dc66a14c3076bc83f \
  --expected-sha256 selection-approval.json=9944dc5e4d00fc6aaec1f541ccc6bb7481bca8a36e3634a3a6e63bcf49e893ba \
  --expected-sha256 run-matrix.json=c8a9217ffcf60718cc132ef04688bdf0bd3bd23758f0e54373993e1237d78ef4 \
  --expected-sha256 blind-mapping.json=a605f3755b7bfeeb6497f6e27a9bc1e3f6f36822155497f1c9f19d85388f0a9e \
  --expected-sha256 commands.txt=3851ca37ed6fdc9fe2c634238d865693db4f3663859f9d1c6bcedc2b62664af6 \
  --expected-sha256 execution-code-pin.json=<vault 内 current 值>
```

评估协议 pin（`evaluation-protocol-pin.json`，位于比较包目录）：`record-comparison-ai-verdict` 要求它存在且其 `review_config_sha256` 等于当前工作区 `ai-review-config.json` 的 SHA-256。一次性生成（在评估 workspace 执行；生成 worktree 的 runner 不读它）：

```bash
python3 - <<'EOF'
import hashlib, json, pathlib
sha = hashlib.sha256(
    pathlib.Path("artifacts/evaluations/ai-review-config.json").read_bytes()
).hexdigest()
pin = {
    "schema_version": "comparison-evaluation-protocol-pin-v1.0.0",
    "review_config_sha256": sha,
    "registered_at": "2026-09-05T00:00:00.000000Z",
}
out = pathlib.Path(
    "artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/"
    "evaluation-protocol-pin.json"
)
out.write_text(json.dumps(pin, sort_keys=True, separators=(",", ":")) + "\n")
print("review_config_sha256 =", sha)
EOF
```

## 3. 串行纪律（一个权威 ledger）

权威 spend ledger（`comparison-spend-ledger-v1.3.0`，当前总额 0.24 CNY = historical 0.14 + forfeited 0.10，status `ingesting`）与 vault（reservation/quarantine/verdicts/ai-verdicts）在任何时刻只允许**一侧推进**；每轮 slot 的完整顺序：

1. **生成前同步**：把评估 workspace 的最新 package 状态（含 spend-ledger、reservations、quarantine、vault）复制进生成 worktree，然后做台账新旧判定——比较两侧 `spend-ledger.json` 文档（相同 `matrix_sha256`，`comparison-spend-ledger-v1.3.0` 形状）：

   ```bash
   python3 - <<'EOF'
   import json
   from ai_scientist.ideation.migration import ledger_recency_comparison
   local = json.load(open(
       "artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/spend-ledger.json"))
   remote = json.load(open(
       "<worktree>/artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt/spend-ledger.json"))
   print(ledger_recency_comparison(local, remote))
   EOF
   ```

   判定必须为 `same_state` 才允许新 slot；`local_newer`/`remote_newer` = 把较新一份复制到另一侧后重判；`MIGRATION_LEDGER_AMBIGUOUS`（同进度、字节不同）= **绝不能猜**，把两份与 reservation/quarantine 记录并列交给 Robert 裁决。

2. **生成**：在 worktree 内执行冻结命令（`commands.txt` 中该 slot 的命令，经 credential wrapper 进入 `scripts/run-prompt-comparison-slot`，携带 frozen matrix SHA-256 与 5.00 CNY threshold 外部 pin），每个 run 在 production admission 中逐 run 交互式批准；reservation/`execution-code-pin` 校验全部原样生效（缺 pin `EXECUTION_CODE_PIN_MISSING`、commit 漂移 `EXECUTION_CODE_PIN_MISMATCH`、重复 `EXECUTION_CODE_PIN_EXISTS`）。

3. **归还证据**：生成侧用 `migration_handoff_manifest`（`direction=generation_to_evaluation`）记录本轮新增证据（sealed run 证据、更新后的 spend-ledger 等，路径 + SHA-256 + 交接时的账本状态），把清单与文件复制回评估 workspace 后由接收侧 `verify_handoff_manifest`（`verify_present=True`）逐字节核验（缺失/漂移 `MIGRATION_HANDOFF_DRIFT`）。复制前发送侧先以 `verify_present=False` 自证本侧副本。

4. **评估**（全部在评估 workspace）：对每对 (baseline, challenger)：

   ```bash
   # 双评审：每个 run 的每个 finalized idea（两 slot 独立上下文）
   python ai_scientist/perform_ideation_temp_free.py evaluation export-review-package \
     --run-id <run_id> --idea-index <n>
   # → 把 ai/review-request.txt 分别发给 primary/second，保存回复
   python ai_scientist/perform_ideation_temp_free.py evaluation import-review-response \
     --run-id <run_id> --idea-index <n> --evaluator-slot primary --response-file <f> \
     --provider deepseek --model-id deepseek-v4-pro --responded-at <ts> \
     --supplied-by Robert --imported-by <operator>   # second 同理（--evaluator-slot second, moonshot/k3-256k）
   python ai_scientist/perform_ideation_temp_free.py evaluation validate-review \
     --run-id <run_id> --idea-index <n> --evaluator-slot primary   # second 同理
   python ai_scientist/perform_ideation_temp_free.py evaluation aggregate-review \
     --run-id <run_id> --idea-index <n>

   # 成对盲评：同一 case 的两臂
   python ai_scientist/perform_ideation_temp_free.py evaluation export-pair-package \
     --run-id-a <baseline> --idea-index-a <i> --run-id-b <challenger> --idea-index-b <j>
   # → pair-request-ab.txt / pair-request-ba.txt 各发两个模型，共四次
   python ai_scientist/perform_ideation_temp_free.py evaluation import-pair-response \
     --pair-id <pair_id> --evaluator-slot primary --direction ab --response-file <f> \
     --provider deepseek --model-id deepseek-v4-pro --responded-at <ts> \
     --supplied-by Robert --imported-by <operator>   # 其余三个 (slot, direction) 同理
   python ai_scientist/perform_ideation_temp_free.py evaluation validate-pair-review \
     --pair-id <pair_id> --evaluator-slot primary --direction ab   # 其余同理
   python ai_scientist/perform_ideation_temp_free.py evaluation reduce-pair-review \
     --pair-id <pair_id>
   ```

   ingestion（`ingest_comparison_result`）与减缩（`reduce_prompt_comparison`）沿用既有 comparison CLI；AI 判定消费经 vault `ai-verdicts/` 通道——把 pair 还原结果写入 package vault（write-once，每 case 一条）：

   ```bash
   python ai_scientist/perform_ideation_temp_free.py evaluation record-comparison-ai-verdict \
     --package-dir artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt \
     --case-id <case_id> --baseline-run-id <baseline> --challenger-run-id <challenger> \
     --pair-index <n> --packet-sha256 <sha> --recorded-by <operator>
   ```

   `--packet-sha256` 取该 pair 在 ingestion 时构建的 pair packet 摘要（与 reduce 消费的 `PairFacts.packet_sha256` 一致；记录不符则 `VERDICT_PACKET_MISMATCH` fail closed）。该命令要求：已注册评估协议 manifest + package 内 `evaluation-protocol-pin.json` 的 `review_config_sha256` 等于当前 config 哈希 + 恰好一条 complete + stable 的 pair 还原记录绑定两臂（`AI_PAIR_REDUCTION_NOT_FOUND`/`_AMBIGUOUS`/`AI_PAIR_NOT_COMPLETE`/`AI_PAIR_NOT_STABLE` 一律不可 ingest）。

5. **费用记账**：每次真实评审调用后 `record-evaluation-cost` 写入评审台账（`call_kind` ∈ `single_review`/`pair_review`/`repair`，含 `physical_call_count`）；每 slot 结束后 `evaluation-cost-report --package-dir <p>` 给 Robert 合并只读口径（生成账本金额逐字带入 + 评审台账 + 未授权支出披露）。

6. 下一 slot 从第 1 步重复。**绝不双端并行推进同一 slot**。中断恢复 = 回到第 1 步用 `ledger_recency_comparison` + reservation/quarantine 记录核对哪份状态最新，逐项补齐后再继续；裁决不清时等 Robert。

## 4. 首条 slot 1 的处置

替换 run `1143a894-1230-4ee1-b41a-f801cc50c027`（材料科学 case）已 sealed、含 1 个 finalized idea（idea 0）：

- 该 idea 0 的匿名评审材料包**已被真实 smoke 用作单条评审对象且结果被开发者观察**（证据报告「暴露披露」节），按规范降级为 **development/diagnostic**——其响应此后不得充当 prompt 优化后的未见测试证据；正式评估应使用未暴露的 run。原 slot 1 零产出 run `966d0fdc-…` 已 quarantine（forfeited 0.10 CNY 入账，vault `quarantine/run-001.json`），替换 run 的 reservation 为 `run-001-seq-2.json`（projected ceiling 7.32 ≤ 30.00 ✓）。
- 该 idea 的 v1 人工 draft 已存在（`ideas/000000/brief.md` + `draft.json`）但**未 validate**；两条合法路径二选一（**须 Robert 决定**）：
  - **（a）按修订协议改走 AI 双评审**：按第 3 节第 4 步执行；暴露状态如实记录，其 AI 判定只能以 development/diagnostic 证据的身份进入 vault `ai-verdicts/`（若 Robert 决定它参与本轮矩阵判分，须在裁决中同时批准暴露材料的处理方式）。
  - **（b）由 Robert 继续人工 validate**（v1 通道仍可用）：v1 人工 Evaluation Artifact 通道语义不变，该 pair 的判定走 `verdicts/` 人工通道；同一矩阵其余 7 条结果仍必须全部走 AI 通道（不混用）。
- 两条路径都被程序强制互斥：一个 case 的 AI 判定与人工判定不可同存（`EVALUATION_CHANNEL_CONFLICT`），一次 reduction 内 AI 与人工 verdict 混用 fail closed。

## 5. 失败保留

任何机检失败（`PROTOCOL`/`COVERAGE`/`PIN`/`LEDGER`/`MIGRATION_*` 等错误码）→ **停在原地、保留现场**（错误输出、两侧文件、ledger 状态全部不动），报告错误码与上下文；**禁止**修改冻结命令、关闭检查或改写记录来「通过」。AI 评审与成对还原均为 write-once：有效结果绝不因 verdict 不理想而重跑；格式无效的响应保留原始字节，修复只能作为新的物理调用与成本记录。

## 6. 恢复 / 回退

- 迁移 rehearsal 已通过（`tests/test_comparison_migration_rehearsal.py` 13 项：协议注册/拒场景、迁移包往返 + 漂移、handoff 往返 + 缺失、recency 四状态、AI 判定通道 E2E、协议必需拒绝、人工通道 byte-stability；`tests/test_evaluation_costs.py` 23 项；全量 879 passed）。
- 真实迁移第一步失败的回退动作 = **不动任何冻结文件**（六项冻结哈希、`run-matrix.json`、`commands.txt` 字节保持），报告失败代码；需要代码修复时只能在评估侧推进，生成侧 pin 保持不变，修复后从第 1 步重新同步重试。

## 7. 明确不做

- 不自动 supersede execution-code pin（更换 pinned commit 需 Robert 显式批准新 Design Epoch）。
- 不重跑已 seal 的 run（包括已 quarantine 的 `966d0fdc`）。
- 不把 smoke 的 development 集（slot 1 暴露材料与合成 pair runs）当作未见测试证据。
- 不部署、不推送、不自动晋升；Promotion Gate 宣判仍由 Robert 在全部判据 reduction 后做出。