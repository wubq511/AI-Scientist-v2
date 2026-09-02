---
title: Choose and calibrate local literature ranking
type: prototype
status: open
assignee: Robert
blocked_by:
  - 018-define-the-workshop-file-contract.md
  - 020-define-the-scoped-retriever-contract.md
---

## Evidence

- [小规模冻结文献语料的本地排序技术路线调研](../../../research/local-literature-ranking-alternatives.md)
- [Local literature ranking：runtime 与最小 dense model 调研](../../../research/local-ranking-runtime-and-dense-model.md)
- [本地文献排序最小公平比较协议（approved v1.1）](../../../prototypes/local-literature-ranking-comparison-protocol.md)
- [AI qrels 调研与本项目决策](../../../prototypes/local-ranking-ai-qrels-research.md)
- [本地文献排序最小公平比较协议 v1.2（approved overlay）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.2.md)
- [本地文献排序比较协议 v1.2.1（actual judge provenance correction）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.2.1.md)
- [AI qrels development evidence 与 holdout receipts](../../../prototypes/local-ranking-ai-qrels-development-evidence.md)
- [Development Stage A 结果](../../../prototypes/local-literature-ranking-comparison-result.md)
- [Windows CPU thread-count 执行补充 v1.3](../../../prototypes/local-literature-ranking-comparison-protocol-v1.3.md)
- [Local ranking 是否需要论文全文](../../../prototypes/local-ranking-full-text-decision.md)
- [Local ranking 正式输入就绪检查](../../../prototypes/local-ranking-input-readiness.md)
- [Local ranking 正式输入准备证据](../../../prototypes/local-ranking-input-preparation.md)
- [E5 512-token 边界与摘要长度政策研究](../../../prototypes/e5-length-policy-research.md)
- [Local ranking 长度政策最小比较](../../../prototypes/local-ranking-length-policy-comparison.md)
- [Local ranking 正式输入与盲评表](../../../prototypes/local-ranking-formal-input-and-blind-qrels.md)
- [Local ranking Windows dense smoke](../../../prototypes/local-ranking-windows-dense-smoke.md)
- [Formal holdout inconclusive 后的补救设计研究](../../../prototypes/local-ranking-inconclusive-next-step-research.md)
- [v1.4 fresh direct-payload evaluation 对抗性审查](../../../research/local-ranking-v1.4-adversarial-protocol-review.md)
- [本地文献排序比较协议 v1.4（approved operational overlay）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.4.md)
- [本地文献排序比较协议 v1.5（segment-reference evaluator overlay）](../../../prototypes/local-literature-ranking-comparison-protocol-v1.5.md)
- [DeepSeek V4 Flash 裁判适配研究](../../../research/deepseek-v4-flash-judge-fit.md)
- [Local-ranking evaluator qualification protocol v1.0](../../../prototypes/local-ranking-evaluator-qualification-protocol-v1.0.md)
- [Local-ranking evaluator qualification protocol v1.0.1（quote contract correction）](../../../prototypes/local-ranking-evaluator-qualification-protocol-v1.0.1.md)
- [Local-ranking evaluator qualification protocol v1.1（segment-reference schema）](../../../prototypes/local-ranking-evaluator-qualification-protocol-v1.1.md)
- [Local-ranking atomic evaluator contract v2.0（approved adversarial redesign）](../../../prototypes/local-ranking-atomic-evaluator-contract-v2.0.md)
- [Local-ranking atomic transport smoke protocol v2.0](../../../prototypes/local-ranking-atomic-transport-smoke-v2.0.md)
- [Local-ranking atomic transport smoke result v2.0](../../../prototypes/local-ranking-atomic-transport-smoke-result-v2.0.md)
- [Local-ranking atomic Pro/high calibration protocol v2.0](../../../prototypes/local-ranking-atomic-pro-high-calibration-protocol-v2.0.md)
- [Local-ranking atomic Pro/high calibration result v2.0](../../../prototypes/local-ranking-atomic-pro-high-calibration-result-v2.0.md)
- [Local-ranking atomic Pro/max calibration protocol v2.0](../../../prototypes/local-ranking-atomic-pro-max-calibration-protocol-v2.0.md)
- [Local-ranking atomic rationale contract correction v2.1](../../../prototypes/local-ranking-atomic-rationale-contract-v2.1.md)
- [Local-ranking atomic Pro/max calibration protocol v2.1](../../../prototypes/local-ranking-atomic-pro-max-calibration-protocol-v2.1.md)
- [Local-ranking atomic bounded-retry contract correction v2.2](../../../prototypes/local-ranking-atomic-bounded-retry-contract-v2.2.md)
- [Local-ranking atomic Pro/max mechanical continuation protocol v2.2](../../../prototypes/local-ranking-atomic-pro-max-continuation-protocol-v2.2.md)
- [Local-ranking atomic Pro/max mechanical continuation result v2.2](../../../prototypes/local-ranking-atomic-pro-max-continuation-result-v2.2.md)
- [Local-ranking atomic tool-output contract v2.3](../../../prototypes/local-ranking-atomic-tool-output-contract-v2.3.md)
- [Local-ranking atomic formal-readiness review v2.3](../../../prototypes/local-ranking-atomic-tool-output-formal-readiness-review-v2.3.md)
- [Local-ranking atomic formal-readiness 补修合同 v2.3.1](../../../prototypes/local-ranking-atomic-tool-output-formal-readiness-amendment-v2.3.1.md)
- [Local-ranking atomic formal evidence ledger 补充合同 v2.3.2](../../../prototypes/local-ranking-atomic-formal-evidence-ledger-amendment-v2.3.2.md)

## Question

Which minimal ranking approach returns useful evidence from 3–36 allowed references, and how will a cheap prototype compare relevance, determinism, dependencies, latency, and failure cases before Robert chooses it?

## Current state

Robert 已批准 comparison protocol、v1.2 AI-qrels overlay 与在任何 ranking 前完成的 v1.2.1 actual-judge provenance correction。v1.1 的 Python 3.13.7 + mandatory CPU FP32 reference path、pinned `intfloat/e5-small-v2` dense challenger、12 cases / 24 queries、题名 + `publisher_abstract` relevance scope、固定 normalization/resource/promotion/output-budget rules 继续生效；overlays 只覆盖 qrels authority、stability、holdout sealing 与真实执行模型绑定，不原地修改 hash-bound v1.1/v1.2。

Throwaway harness 已实现：strict allowlist-only schemas、input/qrels/model/environment-lock hash verification、lexical/RRF scoring、deterministic payload、candidate-isolated worker、typed failure capture、immutable attempt evidence 与 one-command replay 均已落地。Windows SSH 已恢复，持久工作根目录为 `D:\AI-Scientist-v2-workspace`。Development Stage A 已从 clean `2c1b332` 完成：三套 qrels 共 39/39 arms success、跨 qrels payload identity 完全一致、全部 resource gates pass。Cold-start measurement 已与 corpus-build 分离，旧的重复计时 evidence 不用于淘汰 dense。

正式输入盘点最初发现 approved case bundles 为 0；随后完成了独立、不可变的 input preparation 与 approval chain，没有把 raw rows 直接重命名成 Approved Workshop/Corpus。

Windows/macOS Python 3.13 locks 已用 `uv 0.12.4`、binary-only resolution 和 distribution hashes 生成；Windows fresh venv 已按 Windows lock 安装。Pinned E5 六文件 manifest 与 weight hash 校验通过，两次 Windows CPU FP32 diagnostic attempts 均成功，跨 attempt canonical payload hashes 完全一致；E5 worst observed cold p95 8.786 s、warm p95 29.641 ms、build 0.193 s、peak RSS 422,768,640 bytes、model 134,410,262 bytes、environment 836,643,909 bytes，均通过 v1.0 complexity gates。

本 smoke 只证明 frozen runtime 可行，不是 ranker relevance 证据。Evidence-hardening commit `d065002` 已在 Windows fresh attempt 验证：frozen lock、environment/model bytes 与 direct/conservative resource verdict 均写入 raw evidence，三条 candidates 全部 `pass`；Python socket probe 返回 typed `NETWORK_ACCESS_DENIED`，attempt-03 payload hashes 与前两个 attempts 完全一致。

Input preparation 已形成 12-case proposal、12 个 zero-error corpus bundles 与 12 份 deterministic-validation-passed Workshop drafts，并由第二 attempt 对 52 个 selection/corpus artifacts 完成 byte-identical replay。Robert 随后授权 Codex 从第一性原理研究并决定 input/full-text policy；逐案语义审计、全部 reference-title inspection、结构化 abstract audit 与一手资料调研支持批准全部 12 cases。`input-approval-001` 已用 immutable sidecars 绑定 selection、Workshop、corpus、validator 与 v1.1 protocol hashes，approved cases 现为 12。

v1.1 正式 relevance comparison 明确采用题名 + `publisher_abstract`，不混入覆盖不均的全文；结论只支持 abstract-level local paper ranking。Pinned E5 exact tokenizer preflight 已完成：11/168 篇（5 cases）完整 `passage: ` inputs 超过 512，最大 1101；统一前截断会丢 8,458 source characters。已批准 512 仅作为 E5 单 segment hard boundary，并冻结只分割这 11 篇、所有 arms 共用、sentence-aware、zero-overlap、full-coverage、可精确回链的 segmentation。

隔离 query-author session 已只基于 Approved Workshop packet 冻结 24 条 queries；controller 在 Robert 的 delegated authority 下原样批准、未改写 query bytes。Formal adapter 随后物化 168 papers / 180 shared segments，max query/title/segment exact inputs 为 44/53/512 tokens；两个 hardened fresh-process attempts byte-identical，并生成了中文规则、本地离线的 development/holdout blind packets。

人工 qrels blocker 已由 v1.2/v1.2.1 正式替换。实际 judge-A 是 Kimi Code `kimi-k3`，judge-B 是 Kimi Code `deepseek-v4-flash`；两者 development/holdout 均完成 fail-closed validation。原 bundles 错误声明 Codex model，现已冻结 actual-model bundles，并以只改 provenance、不改 qrels/judgment semantics 的 sidecar 重新绑定 development。A/B 共用 holdout raw-draft 路径导致 DeepSeek draft 被 Kimi 覆盖，但 DeepSeek canonical qrels/trace/result 仍完整且 hashes 匹配；v1.2.1 允许从 validated trace 重建并强制披露该 provenance degradation。

Development A/B 在 grade、segment 或 exact-span 上共有 73 个 disputed items；不含 prior labels/rationales 的 blind packet 已由 judge-C=`gpt-5.6-sol`/`xhigh` 全部裁决。Development consensus 完整覆盖 176 items；holdout A/B/C/consensus 也已通过 validator，但标签继续 sealed。A/B exact paper-grade agreement 为 71.59%，linear-weighted kappa 0.6561，`1↔2` boundary disagreement 3.98%，grade gap≥2 为 1.14%；diagnostics 不冒充真实性门槛。

Stage A sensitivity gate 已通过：三套 qrels 都选择 E5 为 best single scorer、BM25 为 best lexical；Stage B 冻结 BM25 `k1=1.6,b=0.5`，并因双方都有对方遗漏的 grade≥2 papers 而保留 RRF ablation。Windows 1/4/8/16-thread probe 的 12-query payload 完全一致；16-thread 将 corpus build total 缩短 7.75x，后续 formal evidence 按 approved v1.3 使用 16 threads，1-thread CPU FP32 path 继续保留。Stage B1 title ablation 18/18 arms success：BM25 与 E5 均冻结 `title_weight=1`；E5 的 exact primary optimum 在 judge-A 有轻微差异，但 finalist direction、Recall 与 catastrophic-miss 改善不变并已完整披露。Stage B2 phrase ablation 6/6 arms success，off/on 的 12/12 payloads 与全部 relevance metrics 完全相同，因此冻结 `phrase_bonus=false`。Stage B3 12/12 arms success；RRF-k10/60 均被 E5 在三套 qrels 的 nDCG/Recall 上支配，故拒绝。Stage B4 12/12 arms success；两 finalists 的 cap3/cap5 EvidenceHit 与 ranking metrics 相同，按 payload bytes tie-break 均冻结 `paper_cap=3`。两个 development finalists 的全部参数已冻结：BM25 baseline 与 E5 best single scorer。Windows scoring-only 10-run 与 macOS stable 3-run gate 均已通过；两平台的 observable payload byte-identical，全部 resource gates pass。Formal holdout 随后从 clean `d44e8b2` 一次性运行：三套 comparison 与 6/6 candidate gates 全部成功，但 judge-A 选择 BM25、judge-B 名义选择 E5、consensus 的 E5 优势只有 `0.008299`。这违反 v1.2 的 same-direction gate，因此 result=`inconclusive`；不得多数票、重跑、调参或生成以 same-direction 为前提的 Robert utility card。

后续对抗性审查确认：已批准 experiment matrix 完整执行，但旧 pointwise synthetic qrels 与旧 holdout 均不能回答 top-3 evidence-set 对 AI ideation 的直接效用，也不能再提供无偏 winner vote。v1.4 operational overlay 已获 Robert 授权并冻结为 fresh direct-payload evaluation：从未使用 eligible candidates 机械选择新的 12 cases（small/medium/large 各 4），重新走 Workshop/corpus/query approval chain；primary 只比较冻结 BM25/E5 top-3，不加入不等预算的 union/full-corpus arm。两个不同 model families 各做两次镜像、fresh、tool-less orientation；统计单位是 12 cases，采用 exact case-level sign-flip，并由 E5 承担非对称 promotion burden。未过门槛只支持保留 BM25 的 parsimony default，不支持宣称 BM25 科学胜出或两者等价。

v1.4 harness 已实现 fresh sampler、operational formal-input path、formal input/selection/protocol/candidate payload hash binding、四路匿名镜像 bundle、`tools: []` judge contract、byte-exact quote validator、position/cross-model unresolved reducer、exact `2^12` randomization、case-cluster bootstrap 与 frozen promotion gates。69 个仓库测试通过；旧 holdout 的真实 BM25/E5 payload 已完成全链机械 dry-run，并被 reducer 强制标为 `spent_diagnostic_only`。下一阶段是在本 commit 后抽取 fresh batch 并完成新的 approval/query/formal-input chain，再交给 Windows 批量生成候选 payload。任何 Kimi/DeepSeek 正式 evaluator 调用仍需先报告 exact prompt size/context feasibility、调用上界与费用并取得单独批准。本 ticket 保持 open；在 fresh formal result 前不能写 Resolution、更新 map 或实现 production ranker。

随后 full-size evaluator ladder 证明 monolithic 24-item response contract 本身不可靠：已观察到漏题、复制错误
profile identity 与跨 item evidence 污染。这些失败不能区分文献判断能力和长 JSON bookkeeping 能力。Robert 已
批准 v2 原子化重构及其对抗性审查：一个 logical call 只判断一个 item，模型只输出 winner/scores/omission/
短 evidence handles/rationale；controller 持有全部 identity 与 provenance。每个 logical call 最多两次
physical attempts，只对机器可判定 invalid 使用 exact-prompt retry，first valid 自动入账，禁止按 winner 或
mirror 结果重跑。

v2 删除了首轮 valid-rate、synthetic winner、分块 side flip、重复 evidence support，以及被其他门槛数学蕴含的
“至少两组 23/24”等无独立保护作用的准入项。保留的 semantic gates 仅为每组至少 `22/24` mirror stable、
pooled 至少 `69/72`，以及每组至少一个稳定 directional judgment。原子 packet/validator/attempt ledger/
orientation resolver/calibration aggregator 已实现；16 项 targeted tests 在 Python 3.13/3.14 均通过。Historical
spent Pro/max 两个 bundles 的 prepare-only dry run 生成 48/48 单题 prompts，public roots 不含 controller
IDs，同输入重建 byte-identical；单 prompt 8,996–14,503 bytes，总 input bytes 比旧 prompts 增加 4.72%，该成本
已披露但不作为无科学含义的阻塞门槛。

Atomic OpenCode Go adapter 已实现：source/effective evaluator 分开记录，request 固定 DeepSeek Pro、JSON-object
SSE 与 `max_tokens=16384`，receipt 逐 call 绑定 manifest/prompt/request/response/provider identity，resolver 与
aggregator 禁止复用 provider response ID。4-call concurrency smoke scheduler 及 fail-closed probe validator 已
加入；targeted tests 21/21 PASS，并已用 historical Pro/max bundle 做 24-call Pro/high prepare-only integration。

冻结的 4-call transport-only Pro/high smoke 已一次 PASS：4/4 HTTP/SSE/closed JSON/receipts 有效，provider
response IDs 唯一，整批 wall 2.911s、总计 793 tokens、receipt cost 合计 `0`。因此 semantic scheduler 的并发
上限冻结为 4；probe 不产生 semantic votes。下一步冻结六个 orientation manifests、144 logical-call budget、
invalid retry state machine 与 early-stop receipts，再按 Pro/high → Pro/max 运行 spent calibration；首个合格
DeepSeek profile 再与 Kimi K3 使用全新 atomic calls 做 panel qualification。Calibration votes 不得复用为
candidate votes，ticket 继续保持 open。

Pro/high 已按 frozen manifest 执行 r1 后触发数学早停：两 orientations 均 24/24 first-valid、零 retry，但 mirror
stable 只有 `20/24`，低于 `22/24`；stable directional 为 14，因此不是全 tie 退化。r2/r3 的 96 calls 未发出。
48 physical calls 共 340,058 tokens，receipt cost 合计 `0`，但 OpenCode Go usage 从 rolling/weekly/monthly
`0/18/33%` 上升到 `16/25/36%`。这使 FAIL 能归因于当前 Pro/high atomic semantic stability，而非长输出抄写或
transport 完整性。下一步按已批准 ladder 冻结全新 Pro/max profile；不得复用 Pro/high votes 或修改 gates。

首个 Pro/max run `pro-max-calibration-001` 在 `r1/o1` 完成 26 个 transport-success calls 后停止为 incomplete：
`call-008` first attempt 的 rationale 为 826 字符、retry 524 字符后 valid；`call-011` 两次分别为 879/982
字符，除此之外 closed schema、visible handles 与 enums 均完整。26 个 calls 合计 169,211 tokens、provider IDs
全唯一、receipt cost 合计 `0`。因此失败来自 Atomic v2.0 任意的 800 字符 gate，不是 Pro/max semantic FAIL。

从第一性原理审查后，Atomic v2.1 删除 rationale 的独立上限：审计需要 non-empty/grounded/blinded，而资源边界
已经由 `max_tokens=16384` 直接控制。旧 run 永久标记为 `spent_incomplete_contract_v2.0`，不事后追认任何 vote；
Pro/high 结果不受影响。下一步必须从新源码 commit 冻结 `pro-max-calibration-002`，六个 orientations 全用 fresh
provider responses，并沿用原有 mirror、retry、budget 与 early-stop gates。

`pro-max-calibration-002` 已从修正 commit `d87e311` 冻结：profile manifest SHA-256 为
`61dc61072b0358de75d1a01fb2a3151ffad73ea9ba88369aa050ce0122b61c5f`，六个 atomic/transport bindings 见
v2.1 protocol。调用前 rolling/weekly/monthly usage 为 `0/28/38%`，均为 `ok`。现在按预注册顺序执行
fresh r1/o1 → r1/o2，再由 pair gate 决定是否允许 r2。

`pro-max-calibration-002` 的 fresh r1/o1 最终仍为 incomplete，但不构成 semantic FAIL：23/24 first attempts
valid；`call-021` 两次都是完整 200/SSE，却在分别消耗 14,197/11,991 tokens 后只输出 schema-empty 的
`{": 0}{": 0}` / `{":":","}`。25 calls 合计 183,518 tokens，response IDs 全唯一，receipt cost 合计 `0`。

对抗性审查后，一次性把 invalid-only physical-attempt ceiling 从 2 修正为 4：exact request、no-error-feedback、
first-valid 和 valid 后禁重试全部不变；attempt 4 仍 invalid 就永久停止，不再上调。缺题、解析 private reasoning、
自动猜测修复、静默覆盖旧 run-result 以及新增 first-valid-rate gate 均被拒绝。进一步复核确认无需重跑其余 23
题：`call-021` attempts 1/2 在新旧规则下都仍是 invalid，而其余都是不受 ceiling 变化影响的 first-valid；且
orientation 2 尚未执行，amendment 不可能由 mirror PASS/FAIL 驱动。下一步保留原 v2.1 incomplete evidence，
以 hash-bound v2.2 continuation 只发 `call-021` attempt 3，必要时 attempt 4，再将旧、新 attempts 一起重验为
combined orientation trace。

Mechanical continuation 已在调用前冻结：修正 commit `510f6c2`，amended profile SHA-256
`e69acf34a7214c3f763780a6d67b90bbd99f116fa3977d3aed3cb9a4128b8b7f`，新旧 `call-021` request SHA-256
均为 `0916cfca6f3fca8a00c48c9b728af82e9395a98187cf673d511bc0b204998cdb`。调用前 usage 为
`9/32/40%`。当前只授权 attempt 3，invalid 才允许 attempt 4；其他 23 题不得重发。

Continuation 已按 scope 完成：只新增 `call-021` attempts 3/4，其他 23 题未重发；两次均为 200/SSE pass，
分别消耗 15,615/8,083 tokens，但仍只生成损坏 JSON，validator 均为 `INVALID_SCHEMA`。原 run 加 continuation
共 27 calls / 207,216 tokens / 27 unique response IDs，usage 从 `9/32/40%` 到 `10/32/40%`。四次上限已耗尽，
未发 attempt 5，未运行 o2/r2/r3；Pro/max 在当前 JSON-object transport 下仍为 operational incomplete。

继续相同 request 已无合理信息增益。若要继续 DeepSeek，下一步必须作为新合同先做一个 spent `call-021`
canary：去掉 provider `response_format=json_object`，但保持同一 packet/rubric/model/max/本地六字段 validator，
只测试 prompt-enforced JSON 是否能避免 finalization 退化；失败则停止 DeepSeek Pro/max，转向其他模型族。该
fallback 尚未获本 result 授权，不能伪装成第 5 次普通 retry。

Robert 随后批准 v2.3 tool-output redesign。Pro/max reasoning/max tokens/rubric/packet/retry/gates 保持不变；primary
删除 `response_format=json_object`，强制唯一 `submit_judgment` function call，由 tool arguments 承载六字段，
controller 保留但不解析 reasoning/content，并沿用本地 closed-schema/handle validator。实现完成后先做 1-call
synthetic 与 spent `call-021` 最多 4-call canary；两者均不产生 vote。Robert 于 2026-09-02 进一步明确授权 primary
implementation 的 Kimi Code/Kimi K3 agent：在实现、完整验证、clean commit、prepare-only hash verification 与
调用前 usage snapshot 全部完成后，可不经中间 checkpoint，按 synthetic → spent `call-021` 的顺序直接执行最多
5 个 live physical calls；synthetic invalid、stress exhausted 或 canary PASS 时都必须立即停止并交回 Codex 复核。

Primary canary 通过后必须从 clean commit fresh 运行 `pro-max-calibration-003-tool-output`，不得用新 `call-021`
拼接旧 23 votes。若 tool canary 机器失败，唯一 fallback 是带两份左右镜像完整 examples 的 JSON-object 合同；
fallback 再失败就停止该 provider/model evaluator profile，不继续 prompt-only grammar、修复 malformed JSON、解析
reasoning 或提高 retry ceiling。当前授权只覆盖 primary implementation 与上述 disposable 最多 5-call canary；不授权
Kimi Code 自行运行 fresh calibration、fallback、额外 retry 或任何其他模型调用。

v2.3 primary 实现已由 Kimi Code/Kimi K3 完成（commit `fix: submit atomic judgments via tool calls`）：atomic
prompt 改为声明无 external/retrieval tools 且要求恰好一次 `submit_judgment` 调用；request 删除
`response_format`，冻结唯一 forced function tool 与 contract §4 的 closed schema；tool-mode SSE extractor 按
index 拼接 fragmented tool-call ID/name/arguments，只接受 index-0 `submit_judgment`，arguments 不做任何修复直接
解析为一个 JSON object，`finish_reason` 只允许 `tool_calls`/`stop`，content/reasoning 仅保留为 raw evidence，
不供应或覆盖 judgment fields；canonical `response.json` 只由 tool arguments 生成，receipt v3.0 绑定 tool
schema、tool-call ID、request、raw/derived evidence、usage 与 cost。新 writers 只写 v2.3 合同版本（atomic
preparation v2.4、attempt v2.5、orientation trace v2.5 / result v2.3、transport preparation v3.0、receipt v3.0 /
execution v2.1）；legacy v2.2-era preparation/attempt/receipt/execution evidence 仍可被 resolver 重验。
`atomic_runner.py` 与 profile/aggregator 代码不变，retry/resume/early-stop 语义不退化。实现 commit、完整验证与
prepare-only hash 冻结完成后，按 v2.3 第 6 节直接执行 synthetic → spent `call-021` 最多 5-call canary，全部输出
`spent_transport_only`；无论 PASS/FAIL 都在 fresh calibration 前停止并交回 Codex 复核。

Kimi implementation commit 为 `fa2409f`。Canary 实际只发 2 calls：synthetic `smoke-001` valid，spent
`call-021` attempt 1 也 valid，随后 first-valid stop；usage 从 `0/32/40%` 到 `0/33/40%`，summary SHA-256 为
`900b49b59c72f3da4282e2cf7d58affb7df0678421a9f042cf868db4a6b26749`。Codex 已从 raw SSE 独立重提取
arguments、重跑 `record_attempt` 并逐文件核验 receipt hashes，因此接受 tool canary PASS，不复用其 judgment，
也不因后续 metadata/validator 修复而重复调用。

Formal-readiness 独立复核同时发现：new manifests 漏写 `response_submission`；真实 v2.2 prompt replay 因统一使用
新 prompt 而失败；new manifest 可接受 legacy receipt/result；`validate-smoke-call` 在只有 response 时也会 PASS；
lone surrogate 会抛出无 execution-result 的 `UnicodeEncodeError`；runner/profile 仍写旧 versions。另有一次已披露
流程偏差：合同要求 Ruff 全绿，但 canary 前仍有 11 个 pre-existing findings。Canary raw evidence不受这些问题影响，
但 `fa2409f` 不具备 formal readiness。

下一步按 `local-ranking-atomic-tool-output-formal-readiness-review-v2.3.md` 做无 live-call repair：current atomic /
transport manifests 升 v2.5/v3.1 并显式写 `forced_submit_judgment_tool`，补真实 legacy/canary read-only validation、
版本配对、完整 smoke evidence validation、typed Unicode failure、runner/round/profile v2.2 与 exact canary-summary
binding。修复不得改变已通过 canary 的 tool schema/prompt/request bytes；修复后由 Codex 复核并单独申请 fresh 003
调用授权。Ticket 继续 open。

Formal-readiness repair 已由 Kimi Code/Kimi K3 完成（commit `fix: harden atomic tool formal readiness`），全程无 live
call、未动 frozen artifacts、未碰 credential。Current atomic/transport preparation 升 v2.5/v3.1 并显式声明
`response_submission: forced_submit_judgment_tool`；legacy JSON-response 族（atomic v2.2/v2.3、transport v2.1、
receipt v2.0/execution v2.0、attempt v2.3/v2.4）与 v2.3 canary 族（atomic v2.4、transport v3.0）保留只读
diagnostic validation，`execute-call`/`run-smoke` 只发 current preparations；`record-attempt` 强制
response/receipt/result/attempt 与 manifest 同族，跨族 fail closed。`validate-smoke-call` 重写为完整 evidence
链验证（response-only 以 `INCOMPLETE_SMOKE_EVIDENCE` 拒绝；receipt/result closed-schema、逐文件 hash 对盘校验、
精确 probe arguments 比对）。tool-mode SSE extractor 对 lone surrogate 等不可 UTF-8 编码片段 fail closed 为 typed
`INVALID_PROVIDER_RESPONSE`/`INVALID_TOOL_CALL` 并保留 raw SSE 与完整 failed execution-result。runner 升 v2.2；
profile manifest 升 v2.2，`prepare` 新增 `--canary-summary`，强制绑定 frozen canary summary SHA-256
（`900b49b59c72f3da4282e2cf7d58affb7df0678421a9f042cf868db4a6b26749`）与 canary implementation commit `fa2409f`，
六个 orientations 必须是 current-family manifests。已通过 canary 的 tool schema/prompt/request bytes 未变（proof 5
三个 hash 原样保留）。验证：Python 3.13.7 locked venv 与 ambient 3.14.6 各 187 tests passed；targeted Ruff（9 个改动
文件）zero-error，full Ruff 恰剩 7 个 pre-existing baseline（canary 前披露的 11 个中本任务修掉 4 个
`opencode_go_stream` findings）；Black/compileall/diff-check 绿。真实 v2.2 replay：pro-max-calibration-002 r1/o1 的 25
个真实 attempt 全部通过重验，resolve 正确停在 RETRY_REQUIRED/call-021 语义边界；canary replay：真实 `call-021`
attempt-1 重放 attempt SHA-256 `5d620f2807f584071d444dc842811f2ea266f43e1811c44d926814e73ff75252` 精确一致，真实
smoke-001 通过增强 validator；proof 6 用真实 canary-summary 与默认冻结 hash 通过 prepare-profile。Ticket 继续 open；
fresh `pro-max-calibration-003-tool-output` 仍需 Robert 单独授权。

Codex 对 `c4bbb2e` 的独立 post-repair review 没有直接采信自报结果：双解释器 187 tests、targeted Ruff、真实 v2.2
25-attempt replay、真实 canary `call-021` replay 与 frozen hashes 均复验通过；但新增 adversarial probes 发现 formal
readiness 仍有四处缺口。`run_orientation` 没有强制 atomic manifest 为 current v2.5，spent v2.4 可被重新包装后进入
执行；smoke validator 接受只含 response/receipt/result 的自洽子集，也接受 `usage=null` / `cost=null`，且没有从 raw
SSE 重建 arguments/chunks/identity；`prepare_profile` 的 Python API 允许 caller 覆盖 frozen canary hash。因此
`c4bbb2e` 尚未批准进入 fresh 003。下一步只执行
`local-ranking-atomic-tool-output-formal-readiness-amendment-v2.3.1.md` 的无 live-call 最小补修；不改变任何模型质量门、
tool/prompt/request bytes 或版本，不连接 Windows、不读取 credential、不发送 model call。

v2.3.1 补修已由 Kimi Code/Kimi K3 完成（commit `fix: close atomic formal readiness bypasses`），全程无 live call、未动
frozen artifacts。`run_orientation` 在读取 credential、创建输出或提交 request 之前强制双 current-family 门（atomic
v2.5 + transport v3.1 且两者 `response_submission=forced_submit_judgment_tool`），spent v2.4/legacy v2.2 重包装与
canary v3.0 transport 均在任何 HTTP 与输出前被拒；legacy/canary 的只读 diagnostic 入口不变。`validate-smoke-call`
升级为强证据验证：receipt `files` 必须恰好是七个 raw/derived 文件、result `files` 必须恰好再加 `receipt.json`，
缩减 file map 以 `INVALID_SMOKE_EVIDENCE` 拒绝；成功 smoke 的 `usage` 必须为合法非空 object、`identity.cost` 必须为
有限非负 decimal string（只查账本完整性，不设数值门槛）；并从 `stream-body.sse` 用冻结的 tool-stream extractor 重建
arguments/chunks/identity/diagnostics/usage，与留存证据逐字节/逐字段比对，不一致以 `HASH_MISMATCH` 拒绝。
`prepare_profile` 删除 `expected_canary_summary_sha256` 参数，production path 只比较模块内冻结常量；测试改用
monkeypatch 构造 synthetic fixture。验证：Python 3.13.7 locked venv 与 ambient 3.14.6 各 196 tests passed（新增 9 个
负例全部先红后绿）；targeted Ruff（5 个改动 .py 文件）zero-error，full Ruff 恰剩 7 个 pre-existing baseline；
Black/compileall/diff-check 绿。真实 replay：canary smoke-001 通过增强 validator，`call-021` attempt-1 replay SHA-256
`5d620f2807f584071d444dc842811f2ea266f43e1811c44d926814e73ff75252` 精确一致，v2.2 r1/o1 25 个真实 attempt 全部可读；
proof 5 三个 hash 原样保留。Ticket 继续 open；fresh `pro-max-calibration-003-tool-output` 仍需 Codex 先冻结
profile/Windows bundle/usage snapshot/执行顺序/r1 budget，再向 Robert 单独申请授权。

Codex 对 `562942f` 的 spec review 为 PASS，且独立复验了双解释器 196 tests、真实 canary/legacy replay 与 frozen hashes；
但 standards review 后的 focused formal-ledger probes 发现，smoke metadata 只做 hash 不做语义校验，正式
`record_attempt` / `record_failed_attempt` 仍可接受删减后的自洽 evidence 子集，且 receipt/result 中的 transport
preparation/request hashes 没有绑定 runner 实际发送的 bytes。真实 `call-021` 被删到只有 response/receipt 后重算 hashes，
当前 recorder 仍返回 `valid`，所以这不是 smoke-only 小修。下一步冻结执行
`local-ranking-atomic-formal-evidence-ledger-amendment-v2.3.2.md`：只统一 current-tool evidence policy、绑定并保存每个
attempt 的实际 manifest/prompt/request、按失败类型保留最小 raw evidence，并让 record/replay 同强度 fail closed；不新增
任何模型质量、性能或人工准入门槛，不改变 frozen tool/prompt/request bytes，不重跑 canary，不发送 live call。
