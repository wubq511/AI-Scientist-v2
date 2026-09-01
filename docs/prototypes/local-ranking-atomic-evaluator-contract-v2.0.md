# Local-ranking atomic evaluator contract v2.0

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and implemented locally; live model calls require the frozen smoke manifest described below**

## 1. 决策

把现有“一次调用返回 24 个 judgments”的裁判任务改为 **一个 logical call 只判断一个 item**。

模型只负责六个语义字段：

1. `winner`；
2. `left_scores`；
3. `right_scores`；
4. `catastrophic_omission_side`；
5. `evidence_handles`；
6. `rationale`。

`bundle_sha256`、provider/model/effort、replicate、orientation、item identity、paper/segment identity、请求与
响应 hashes 全部由 controller 记录。模型只看到 `L1-L3`、`R1-R3` 这类当前 item 内的短 evidence handles，
不再抄写长 ID 或跨 24 个 item 维护完整性。

本版本先实现本地 packet builder、closed-schema validator、有界 attempt ledger、orientation resolver 与三组
mirror calibration aggregator。它不修改历史 v1.x artifacts，不追认过去失败的输出，也不在本次实现阶段发起
外部模型调用。

## 2. 第一性原理：实验真正要测什么

目标变量是：**同一组可见文献证据交换左右位置后，裁判的候选方向是否稳定**。

下列能力不是目标变量：

- 抄写 bundle hash、model alias、item ID、paper ID 或 segment ID；
- 在一个长 JSON 中记住 24 个 item 并全部输出；
- 生成每条 evidence reference 的重复解释文字；
- 在长任务中避免把上一题身份带到下一题。

旧 contract 把这些 bookkeeping 能力和语义判断绑在一起。`20/24`、错误 evaluator identity、引用当前题目中
不存在的 evidence，既可能来自语义失败，也可能只是长输出中的复制和状态污染。因此旧结果能够证明旧
**整体 contract 不可靠**，却不能单独证明模型不能完成单 item 文献比较。

新的最直接设计是消除无关能力，而不是靠无限重试等待模型偶然抄对。

## 3. 对抗性审查

### 3.1 主要攻击面与防线

| 攻击或失败方式 | 对结论的危害 | v2 防线 | 是否硬门槛 |
| --- | --- | --- | --- |
| 模型漏掉部分 items | 选择性缺失改变分母 | 一个 logical call 天然只含一个 item；orientation 必须解析出固定 24 个 calls | 是 |
| 抄错 item/model/hash | 产生假 provenance 或错配 | 这些字段不进入 model-owned output，由 controller 从冻结 manifest 写入 | 是 |
| 引用另一题 evidence | 用无关证据伪装 grounding | 每个 prompt 只有当前 item；handles 只在当前 packet 内有效 | 是 |
| 左右位置偏差 | 候选方向随呈现顺序变化 | 每个 replicate 使用 exact mirrored orientations | 是 |
| 失败后按答案选择性重试 | 通过 cherry-picking 改变 winner 分布 | 只对机器可判定 invalid retry；完全相同 prompt；不回传错误；首个 valid 自动入账 | 是 |
| 无限重试直到过线 | 隐藏运行可靠性并放大选择偏差 | 每个 logical call 最多 2 个 physical attempts，全部保留 | 是 |
| valid 但“不喜欢”的答案被重跑 | 直接污染语义证据 | valid 后禁止第二次调用；不得因 winner、mirror 或分数触发 retry | 是 |
| 一个 replicate 很差被 pooled 掩盖 | 平均值隐藏单轮不稳定 | 每组 mirror stable 至少 `22/24` | 是 |
| 多组都略差但累计看似可接受 | profile 持续位置敏感 | 三组合计至少 `69/72` | 是 |
| 全部输出 tie/both_bad 获得 24/24 稳定 | 无方向输出冒充稳定裁判 | 报告每组 directional count；若整组无任何 left/right，判 semantic degeneracy | 是，只有零方向这一条 |
| 某候选真实明显更好导致 mapped winner 偏斜 | 把内容信号误判为 side bias | 不对 mapped candidate balance 设门槛；只用 mirror stability 检测显示位置偏差 | 否 |
| scores 与 winner 看似不一致 | 未定义权重时 controller 擅自替模型改判 | 不新增 score-sum consistency gate；保留原始字段供审计 | 否 |
| 并发导致 provider/transport 不稳定 | 产生缺失或截断 | live run 前做 transport-only smoke；并发是执行参数，不是语义能力门槛 | transport 门槛，不是模型门槛 |
| controller 篡改模型答案 | 结论不可审计 | raw response write-once；trace 只扩展 handles 和 provenance，不改语义字段 | 是 |

### 3.2 刻意删除或降级的旧门槛

以下规则不再阻碍 profile qualification：

1. **首轮 valid 比例门槛删除。** First-attempt validity、retry count 和错误类型完整报告，但 bounded retry 是
   正式运行时 contract 的一部分，因此首轮失败不是独立的语义否决条件。
2. **synthetic winner 门槛删除。** Synthetic 只验证 transport、JSON mode、receipt 和 concurrency；checksum
   题的答案不能证明文献判断能力。
3. **“至少两组达到 23/24”删除。** 该条件被“每组至少 22/24、pooled 至少 69/72、每组上限
   24”数学蕴含：若最多一组达到 23，最大只能是 `24 + 22 + 22 = 68`。保留它没有新增保护。
4. **r1 必须 23/24 的早停删除。** `22 + 24 + 24 = 70` 本来可以 PASS，不能因为 r1 为 22 提前阻止。
5. **每个 stratum × query-kind 必须出现 side flip 删除。** 小区块可能因真实内容形成同向 winner；mirror
   pair 已直接测量位置偏差，额外分块规则会把内容差异误当失败。
6. **输出 `support` 字段删除。** 它与 rationale 重复，且是长输出复制错误来源。Controller 仍能用 handle
   回链 exact visible segment。
7. **总 prompt bytes/token 比例门槛删除。** 只报告实际 request/response tokens、费用和延迟；不因一个没有
   科学含义的资源比例阻止实验。
8. **micro-batch 4 不作为首选。** 它比 24-item 简单，但仍保留漏项与跨题污染。Atomic 通过后，micro-batch
   只能作为成本优化的新实验，不能反向替换证据。

### 3.3 仍然保留的最小硬门槛

每个 logical call：

- frozen public packet 与 prompt hashes 正确；
- response 是 exact closed schema，enum/type/length 正确；
- `evidence_handles` 为 1–4 个当前 packet 内的唯一 handles；
- left/right winner 至少引用 winning side；tie/both_bad 至少各引用一侧；
- controller input/provenance mismatch 立即 hard fail，不通过模型 retry 掩盖；
- 最多两次 physical attempts，采用 first valid；两次仍 invalid 时该 logical call 失败。

每个 profile：

- 固定三组 replicates，每组两个 mirrored orientations，每个 orientation 恰好 24 个 resolved calls；
- 每组 stable 至少 `22/24`；
- pooled stable 至少 `69/72`；
- 每组至少出现一个稳定的 left/right direction，排除全 tie/both_bad 的退化输出；
- 不追加第四组，不挑最好的一组，不复用旧 calibration votes。

Directional gate 刻意只设为 `>0`，不预设 18/24 等高阈值：dry run 中 7/24 items 的左右 top-3 在忽略
顺序与 handles 后本来就是相同 evidence set，tie 有合理空间；只有整组没有任何稳定方向时，该 profile 才无法
承担后续 candidate comparison 的基本职责。

这里 `22/24` 与 `69/72` 直接约束要研究的位置稳定性。它们仍是工程阈值而非统计真实性证明；provider 未
暴露 seed，因此三组重复只能证明当前 provider/profile/contract 的 operational reproducibility。

## 4. Atomic contract

### 4.1 Model-visible packet

每个 packet 只含一个 query，以及左右各三条 handle-labeled evidence。模型看不到 controller 的 item ID、
candidate identity 或 long evidence identity。

```json
{
  "item": {
    "left": {"evidence": [{"content_type": "...", "handle": "L1", "text": "...", "title": "..."}]},
    "query": {"kind": "...", "text": "..."},
    "right": {"evidence": [{"content_type": "...", "handle": "R1", "text": "...", "title": "..."}]}
  },
  "response_contract": {
    "catastrophic_omission_side": ["left", "right", "neither"],
    "evidence_handle_count": [1, 4],
    "score_fields": ["coverage_diversity", "direct_support", "query_usefulness", "specificity"],
    "score_values": [0, 1, 2],
    "winner": ["both_bad", "left", "right", "tie"]
  },
  "schema_version": "local-ranking-atomic-judge-packet-v2.0"
}
```

Model-owned response exact root keys：

```json
{
  "catastrophic_omission_side": "neither",
  "evidence_handles": ["L1"],
  "left_scores": {
    "coverage_diversity": 2,
    "direct_support": 2,
    "query_usefulness": 2,
    "specificity": 2
  },
  "rationale": "...",
  "right_scores": {
    "coverage_diversity": 1,
    "direct_support": 1,
    "query_usefulness": 1,
    "specificity": 1
  },
  "winner": "left"
}
```

### 4.2 Controller-private bindings

Private manifest 保存：

- source bundle file/self hashes；
- evaluator provider/model/effort；
- replicate 与 orientation；
- call sequence 到原始 `case_id` / `item_id` 的映射；
- `L1-L3` / `R1-R3` 到 exact side/paper/segment IDs 的映射；
- public packet/prompt path、bytes 与 SHA-256。

Final trace 保存 raw response、execution receipt、request SHA-256、唯一 provider response ID 和 controller
展开的 evidence refs。扩展只做确定性 handle lookup；不得修改 winner、scores、catastrophic omission 或
rationale。Attempt 若没有与 exact atomic manifest、call、prompt、request、response、model/effort 绑定的 canonical
receipt，或者六条 traces 复用了 provider response ID，均 fail closed。

## 5. Retry 与执行预算

一次 profile 包含：

- `24 items × 2 orientations × 3 replicates = 144 logical calls`；
- 每个 logical call 最多 2 次 physical attempts；
- 最坏上限 `288 physical calls`，不是目标调用量；首轮 valid 时不会产生第二次。

允许 retry 的原因仅限机器可判定的 transport failure、截断/非 JSON、closed-schema/type/enum/length 失败、
unknown/重复/side-coverage 不合法的 handles。Retry 必须使用相同 prompt bytes、model、effort、max tokens 与
execution profile，不提供 validator 错误，不要求“改正上一版”。

不允许 retry 的原因包括 winner、分数、rationale 观点、mirror mismatch、与另一模型不一致。Controller
provenance/hash mismatch 是 harness hard fail，修复后必须创建新 attempt，不能算该 model call 的第二次。

`max_tokens` 冻结为 `16,384`。历史 Pro/max 多个 24-item receipts 的 completion 分别为 24,174、27,359、
29,452 等量级，平均约 1,100 tokens/item；因此 16,384 给单 item 约 14 倍历史均值余量，同时把旧 32,768
异常生成上界减半。它只是防截断和失控的 ceiling，不是要求模型用满的预算，也不是 semantic gate。在发起
semantic calibration 前只用 transport smoke 确认 provider 接受该 ceiling；profile 内不得临时改变。

## 6. 并发、早停与 profile ladder

### 6.1 并发

先运行 4 个互不相关的 transport-only atomic smoke calls：

- concurrency 4 成功则 semantic batch 的 scheduler 上限为 4；
- provider/transport 不能稳定承载时依次降为 2、1；
- synthetic 结果不进入 semantic gates；
- scheduler 上限与每次实际并发写入 receipts，不把并发失败解释成模型语义失败。

### 6.2 只在结论已不可能改变时早停

- 任一 replicate 完成后 stable `<22/24`：profile 已无法满足 per-replicate gate，停止；
- 前两组完成后，`current pooled + 24 < 69`：即使第三组全稳定也不能 PASS，停止；
- 任一 logical call 两次仍 invalid：当前 profile run 不完整，停止；
- r1 为 `22/24` 时必须继续，因为仍可能达到 pooled gate；
- 不依据当前 winner direction 或“看起来不利”早停。

### 6.3 模型顺序

1. 先运行 `opencode-go/deepseek-v4-pro` / `high`；
2. 若 semantic gates FAIL，再用全新 outputs 运行 `opencode-go/deepseek-v4-pro` / `max`；
3. 不继续 Flash ladder；
4. 首个 PASS 的 DeepSeek profile 与 Kimi K3 使用同一 atomic contract 运行全新 panel qualification；
5. calibration calls 不复用为 panel votes。

是否需要更换模型族只在 Pro/high 与 Pro/max 都未通过 atomic contract 后决定。不能通过增加 replicates 或重跑
valid calls 直到过线。

## 7. 实施和验证顺序

1. 新增 versioned atomic packet/validator/attempt ledger，不改 v1.2 validator；
2. 用 synthetic fixtures 做 closed schema、handle mapping、first-valid、attempt ceiling 与 write-once tests；
3. 新增 atomic orientation resolver 和三组 mirror aggregator，测试 `22+24+24` PASS、`22+23+23` FAIL、
   `21+24+24` FAIL，并证明冗余 23 gate 已删除；
4. 对 historical spent Pro/max bundles 做 **prepare-only dry run**，验证 48 个 prompts 均为单 item、无 controller
   IDs、hash 可重建；不把 dry run 当模型 evidence；
5. 冻结 live execution manifest、`max_tokens=16384`、concurrency 1-4 和 provider receipt adapter；
6. 先运行 4-call transport-only smoke。只有 transport/SSE/JSON/receipt/唯一 response ID 是 smoke gate；probe
   的语义内容不进入 calibration；
7. smoke PASS 后按 Pro/high → Pro/max 发起 fresh semantic calibration。

Mac 继续作为 API controller、protocol/input preparation、evidence review 与 fallback；该阶段没有本地模型计算，
不需要为了形式把 API calls 转到 Windows。Windows 仍负责本地 ranking 的 bulk compute，不改变仓库已记录的职责
分工。

## 8. 脆弱假设、失败含义与回滚

最脆弱的假设是：删除 bookkeeping 后，DeepSeek Pro 的 winner 能在镜像下稳定。如果 atomic Pro/high 与
Pro/max 仍达不到 gates，失败就更能归因于 rubric 含糊、证据确实接近或模型判断不稳定，而不是长 JSON 抄写。

外部依赖失效时，保留 receipts/raw responses，在 attempt ceiling 内结束；不篡改 artifacts，不把 incomplete
写成 semantic FAIL。Provider 行为漂移时需要新的 versioned execution manifest。

回滚边界简单：v2 使用新模块与 schema；历史 v1.x protocols、bundles、失败 artifacts 和结果保持不变。删除
新模块或回退对应 commit 即可，不会改变已有 ranking evidence。

## 9. 技术依据

- LLM judge 会受到答案位置影响，因此 mirror/pairwise order swap 是直接相关的防线：
  [Large Language Models are not Fair Evaluators](https://arxiv.org/abs/2406.07791)。
- MT-Bench 的 LLM-as-a-judge 工作也把 position bias、verbosity 等作为已知限制，而不是把格式正确等同于判断
  正确：[Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685)。
- Constrained/structured generation 提高 schema compliance，但不能替代 semantic validation：
  [JSONSchemaBench](https://arxiv.org/abs/2501.10868)。
- 生产结构化输出工具采用 bounded retry，但 retry 必须作为显式运行策略被记录：
  [Instructor retrying documentation](https://github.com/567-labs/instructor/blob/main/docs/concepts/retrying.md)。

## 10. Prepare-only implementation evidence

2026-09-01 使用 historical spent Pro/max orientation bundles 做了不调用模型的 dry run：

- source bundle file SHA-256：orientation 1
  `9e98b1f9c9e4ffe5c57c3c81219a03c50717a0729bd3447e82c4ca174d898e5c`，orientation 2
  `b8ccd49bca0e1cb6c6c23d07229f0d875195504ef297fc3f8d02ecb10504aa10`；
- 两个 orientations 均生成 24 个 atomic prompts，共 48 个；
- 单 prompt 为 8,996–14,503 bytes，mean 11,571.4 bytes；旧 monolithic prompt 每个 265,186
  bytes，单请求 model-visible context 缩小至少 94.5%；
- 48 个 prompt 合计 555,426 bytes，相比旧两个 prompts 合计 530,372 bytes 增加 4.72%。因此 atomic
  解决的是单请求状态污染与输出完整性，不声称降低总 input tokens；
- public roots 全量搜索不到 `item_id`、`case_id`、`paper_id`、`segment_id`、`bundle_sha256` 或
  `deepseek-v4-pro`；
- 对 orientation 1 用相同 source 与 replicate ID 重新 prepare，`diff -qr` byte-identical；
- 初版本地 atomic targeted tests 16/16 PASS，覆盖 first-valid、retry-after-valid、attempt exhaustion、private
  handle expansion、冗余 gate 删除、degeneracy、数学早停与 144-call end-to-end aggregation；Python 3.13
  与 3.14 均通过；
- 当前源码的 Python 3.14 `tests/` 全量 119/119 PASS；changed Python files 的 Black 26.5.1、Ruff
  0.16.5、compileall 与 `git diff --check` 均通过。全仓 Black/Ruff 仍有上游既存失败，未为本 prototype
  修改无关文件。

## 11. Atomic transport implementation evidence

2026-09-01 新增独立的 `atomic_opencode_go` adapter，不修改历史 v1.x transport：

- source evaluator 与 effective evaluator 分开记录；只允许同一 OpenCode Go DeepSeek Pro profile 在
  `high/max` 间显式选择，能够从 spent Pro/max bundle 诚实派生 Pro/high request；
- 每个 call 的 prompt/request 独立 canonical + write-once，request 固定 `deepseek-v4-pro`、JSON object、SSE、
  `max_tokens=16384`；
- receipt 绑定 atomic manifest、call/replicate/orientation、prompt/request/response hashes、model/effort、
  provider response ID、usage、safe headers 与 raw SSE；
- resolver 禁止 physical attempts 复用 provider response ID，calibration aggregator 再对六条 traces 做全局
  uniqueness 检查；
- 4-call smoke 使用真实并发 scheduler，但只检查 HTTP/SSE/JSON/receipt、exact probe schema 和 response ID
  uniqueness，不把 synthetic answer 当模型判断能力；
- targeted tests 更新为 21/21 PASS；prepare-only integration 从 historical Pro/max orientation 1 成功生成
  24 个 effective Pro/high atomic requests，source/effective evaluator 同时保留，concurrency 4 与 token ceiling
  16,384 均可重建。

实时 smoke 的 commit、preparation hashes、quota snapshot、receipts、latency/usage/cost 和 PASS/FAIL 另写入冻结的
transport smoke protocol/result，不能由本地 mock PASS 代替。

实时 `transport-smoke-001` 随后按冻结 protocol 一次 PASS：4/4 receipts 有效且 response IDs 唯一，整批
wall 2.911 秒、total 793 tokens、receipt cost 合计 `0`，因此 semantic scheduler max concurrency 冻结为 4。
完整 evidence 见 [atomic transport smoke result v2.0](local-ranking-atomic-transport-smoke-result-v2.0.md)。

总 input 增长不设为失败门槛：4.72% 是重复短 instruction 的明确成本，但它换取每次只处理一个独立判断，并
允许 scheduler 并发。若 live token/cost 证明该成本不可接受，再以 atomic 结果为 reference 对 micro-batch 做独立
比较；不能在取得证据前因为总 bytes 略增而退回已知不可靠的 24-item response。
