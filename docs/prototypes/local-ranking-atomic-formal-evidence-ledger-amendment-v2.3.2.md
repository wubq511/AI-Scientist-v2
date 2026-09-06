# Atomic formal evidence ledger 补充合同 v2.3.2

日期：2026-09-02（Asia/Shanghai）

状态：**evidence-ledger repair authorized；live calls remain unauthorized**

基线：`739ea57cc89297a092c75a30675c2d78c5ea9ee2`

上游合同：

- [Atomic tool-output contract v2.3](local-ranking-atomic-tool-output-contract-v2.3.md)
- [Atomic tool-output formal-readiness review v2.3](local-ranking-atomic-tool-output-formal-readiness-review-v2.3.md)
- [Atomic tool-output formal-readiness 补修合同 v2.3.1](local-ranking-atomic-tool-output-formal-readiness-amendment-v2.3.1.md)

## 1. 结论

`562942f` 完整实现了 v2.3.1 的四项明示要求，spec review 为 PASS；但独立 standards review 和随后对正式
`record_attempt` 的 focused audit 证明，当前代码仍允许把传输证据删减或把 metadata 改成无意义内容，再重算
receipt/result 内部 hashes 后通过验证。该缺口同时存在于 smoke 和 future formal attempt ledger，不能按一个局部小修
处理。Fresh `pro-max-calibration-003-tool-output` 继续禁止；下一步只做本合同的 evidence-ledger closure。

这不是新增模型准入门槛。它不改变 rubric、packet、model、effort、token ceiling、retry、semantic gates、concurrency、
latency、cost 或 vote acceptance；只确保系统声称“某个 request 产生了某个 result”时，留存证据足以重放该声明。

## 2. First-principles boundary

实验需要防住的是 incomplete、inconsistent、误配和常规 artifact tampering，而不是靠同一目录内的自报 hash 抵御能同时
重写全部文件和验证代码的攻击者。最终跨设备 bundle 仍由外部 immutable hash/seal 负责。因此本合同只要求：

1. 每个正式 attempt 绑定真正通过验证并被发送的 frozen input；
2. 成功 response 可以从 raw SSE 唯一重建，并与全部 derived evidence 一致；
3. 失败也保留足以区分 transport、HTTP/content-type 和 stream extraction failure 的最小证据；
4. replay 对复制后的 bytes 执行与 record-time 相同强度的检查。

不引入签名系统、外部 timestamp authority、网络证明、性能阈值、人工审批或额外 model call。这些都不能直接修复当前
错误边界，属于不必要门槛。

## 3. Confirmed blockers

### E1 — smoke metadata 只做 hash，不做语义验证

把真实 `smoke-001` 的 `http-status.txt` 改成 `503`、headers 改成非法 JSON、开始/结束时间改成无效或倒序值，再同步
更新 receipt/result hashes，当前 `validate-smoke-call` 仍 PASS。Hash 只能证明“当前 bytes 与自报一致”，不能证明 bytes
表达了成功的 SSE 调用。

### E2 — formal success 接受自洽子集

把真实 canary `call-021` 的 receipt `files` 缩成只有 `response.json`，execution-result 缩成
`response.json + receipt.json`，删除 SSE、chunks、headers、status 和 timestamps 并重算 hashes，当前
`record_attempt` 仍返回 `valid`。因此 smoke 已有的 exact-set/raw-replay 规则没有进入正式 ledger。

### E3 — formal failure 接受任意非空文件集

`record_failed_attempt` 当前只要求 result 声明任意一个存在文件；它不证明 request 是否真正开始、HTTP 状态是什么、
是否收到 SSE，或 result error 是否与 raw failure evidence 一致。失败 attempt 会参与 retry/exhaustion 账本，因此同样必须
可审计，但不能强行要求成功 response/receipt。

### E4 — transport preparation 与 request hashes 没有外部绑定

正式 recorder 只检查 `preparation_manifest_sha256` 和 `request_sha256` 是 64 字符且 receipt/result 相互一致，没有把它们
与 runner 实际使用的 current transport manifest/request/prompt bytes 比较。Synthetic helper 用任意 `a*64` / `b*64`
也能产生 current-family valid attempt，说明目前 ledger 证明不了“记录的就是发送的 request”。

### E5 — replay 复用了同一弱规则

`_validate_attempt` 重验复制后的 receipt/result，但仍接受 E2/E3/E4 的缩减或未绑定证据。只在 record-time 增强检查不够；
否则写入后损坏的 ledger 仍可能在 resume/resolve 时被接受。

## 4. Frozen minimal repair

### 4.1 One shared current-tool evidence policy

成功/失败 evidence file sets、metadata parsing、raw SSE replay、usage/cost 和 error/evidence consistency 必须由一个共享验证
边界定义，并同时被 `validate-smoke-call`、`record_attempt`、`record_failed_attempt` 和 `_validate_attempt` 使用。
不得继续让 smoke constants、writer allowlist 与 formal validator 各自维护可漂移的集合。内部函数放置可以调整，但不能
复制四套近似规则。

### 4.2 Successful tool execution

Tool receipt `files` 必须恰好为七个文件：

- `chunks.jsonl`
- `finished-at.txt`
- `http-status.txt`
- `response-headers.json`
- `response.json`
- `started-at.txt`
- `stream-body.sse`

Successful execution-result `files` 必须恰好为上述集合再加 `receipt.json`。除既有 closed-schema、identity、binding、
usage/cost checks 外，还必须验证：

- `http-status.txt` exact 为 `200\n`，并与 result/receipt `http_status` 一致；
- `response-headers.json` 是 canonical JSON object，只含 writer allowlist 中的小写 header names 和 string values，且
  `content-type` 包含 `text/event-stream`；
- `started-at.txt` / `finished-at.txt` 各为一个以 `Z` 结尾、带单个换行的可解析 UTC timestamp，且 start 不晚于 finish；
- 从 `stream-body.sse` 用冻结 tool extractor 重建 canonical `response.json`、canonical `chunks.jsonl`、identity、
  diagnostics 和 usage，并 exact compare；
- 独立 `raw-response.bin` / `execution-receipt.json` 与 `execution-evidence/response.json` /
  `execution-evidence/receipt.json` 继续由同一 hashes 绑定。

这些规则同时适用于真实 v2.4 canary success replay 和 current v2.5 formal success；它们不得改变既有 canary bytes。

### 4.3 Failed current-tool execution

失败 execution-result 不得接受任意子集。共同 base set 必须恰好为：

- `started-at.txt`
- `finished-at.txt`
- `http-status.txt`
- `response-headers.json`
- `stream-body.sse`

在 base set 上只允许以下一种附加状态：

- transport exception：只再加 `transport-error.json`；连接建立前失败时 status 可为 exact `unavailable\n`，读取中断时可保留
  已取得的 numeric status、safe headers 与 partial raw SSE；`transport-error.json` 的 error type 必须与 result error exact
  对应，不能把 partial transport failure 误报成成功或 HTTP failure；
- HTTP non-200 或 200-but-non-SSE：不增加文件；HTTP error 的 status/details 一致，或 non-SSE error 在 status 200 且
  content-type 不含 `text/event-stream` 时成立；
- SSE/tool extractor failure：只再加 `stream-validation-error.json`；status 200、content-type 为 SSE，error 文件与 result
  error exact equal，重新运行 frozen extractor必须产生同一 typed failure。

失败 evidence 仍验证 canonical safe headers 与 ordered UTC timestamps。它不要求 receipt、response、chunks、provider ID、
usage 或 cost，因为这些值在失败边界可能尚未产生；也不要求 raw SSE 非空。任何 receipt/response/chunks 混入 failed set、
error 与 evidence 不一致、缺 base file 或多余 allowlisted file均 fail closed。

### 4.4 Bind and preserve the actual prepared input

Current atomic v2.5 的 `record_attempt` 与 `record_failed_attempt` 必须获得本次调用实际使用的 `preparation_root`；在写 ledger
前完整验证 current transport v3.1 preparation，并证明：

- transport `atomic_manifest_sha256` 等于当前 atomic manifest bytes；
- active transport call 的 sequence/call ID/orientation/replicate 与 atomic call一致；
- transport prompt bytes 与 atomic prompt bytes一致，且 hashes 与双方 manifests一致；
- request 是 frozen forced-tool request，request bytes hash 与 transport call、receipt/result一致；
- receipt/result 的 preparation hash 等于实际 transport manifest bytes。

每个 current attempt ledger 固定保存且只保存该次重放所需的三个 input evidence files：transport manifest、active prompt、
active request。建议路径为 `input-evidence/manifest.json`、`input-evidence/prompt.txt`、
`input-evidence/request.json`；不得为每个 attempt 复制全部 24 calls。Replay 必须从这三个复制后的文件重新验证同一 binding，
不能回退依赖易变的源目录。Record-time 对源 preparation 做 24-call 完整验证；replay 对已由 manifest hash 绑定的完整
manifest closed schema 和 active call entry 做验证，只要求 active prompt/request 在该 attempt 的 input-evidence 中存在，
不得因未复制其他 23 calls 而要求它们的文件也在 attempt 目录内。

CLI、runner new-call path、partial-execution recovery path 和 resume path 都必须遵守该参数/binding；缺 current
`preparation_root` 或缺 input evidence 时在任何新 request/重试前 fail closed。

### 4.5 Version families

Current atomic v2.5 新写 attempt 升为 `local-ranking-atomic-attempt-v2.6`，用该版本表达强 input/execution ledger。版本配对为：

- legacy atomic v2.2/v2.3：继续只读既有 legacy attempts/receipts/results；
- canary atomic v2.4：继续只读 attempt v2.5 + tool receipt v3.0 + result v2.1，执行证据按 §4.2 强重放，但不追溯要求
  历史 ledger 新增 input-evidence；
- current atomic v2.5：只写/接受 attempt v2.6 + tool receipt v3.0 + result v2.1 + §4.4 input-evidence。

Orientation trace/result、run/round/profile schema 不因这次外部 ledger closure 升版。Tool schema、prompt、HTTP request、
receipt/result writer bytes 和 transport preparation schema 不变，因此已通过 canary 不重跑。

## 5. Scope

允许 Kimi 修改：

- `prototypes/local_ranking/atomic_judge.py`
- `prototypes/local_ranking/atomic_opencode_go.py`
- `prototypes/local_ranking/atomic_runner.py`
- `tests/test_local_ranking_atomic_judge.py`
- `tests/test_local_ranking_atomic_opencode_go.py`
- `prototypes/local_ranking/README.md`
- `docs/wayfinder/ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md`

本合同文件与 Codex session log 由 Codex 在实现前冻结，不属于 Kimi implementation diff。不得修改 `AGENTS.md`、
`atomic_profile.py`、rubric/prompt/tool schema、frozen artifacts 或 dependency locks；不得清理无关 Ruff baseline；不得读取
credential、连接 Windows 或发送任何 model/API request。

若为实现单一共享验证边界确有必要新增一个内部 Python module 及对应 test file，Kimi 必须先在回报中证明现有依赖方向
无法无循环地承载该边界；否则保持上述文件范围。该例外不授权任何新功能或 dependency。

## 6. Required proofs

1. 先以当前 `739ea57` 代码证明 E1–E4 negatives 会错误 PASS，再修到 fail closed；保留 red/green 证据。
2. Smoke negative：invalid/noncanonical headers、status 非 200、invalid/倒序 timestamps，即使同步重算内部 hashes 也失败；
   真实 `smoke-001` 仍 PASS。
3. Formal success negatives：删任一七文件、缩减 receipt/result maps、raw SSE 与 response/chunks/receipt 不一致、metadata
   无效，均在写 ledger 前失败且不产生 partial ledger。
4. Formal failure negatives覆盖 transport、HTTP、non-SSE、extractor 四类；缺 base file、错附加文件、错误 metadata、
   error/evidence mismatch、额外 response/receipt/chunks 均失败；每类真实 writer-shaped positive 均通过。
5. Input binding negatives：伪造 preparation/request hashes、错 transport root、错 call、prompt/request 修改、缺
   input-evidence 及复制后修改均失败；runner recovery/resume 不会因此重发已完成的 physical call。
6. Current preparation repeated prepare 的 prompt/request/tool schema hashes 不变；proof 5 的 canary tool schema、prompt、
   request hashes 仍分别为 `fa2cea71b0c41b87ef7743010656cd819d871ab2e8a95fcff2f8518cd11a859c`、
   `4d8b409ebd6a3b24aed74e6ec230cd8b83950858de6a068b7e4f63a5501134ef`、
   `7445fd80b52c1b4da594f46fe28d0811f22efb35be8edf188a2d823499588cb4`。
7. 真实 canary `call-021` attempt replay SHA-256 继续为
   `5d620f2807f584071d444dc842811f2ea266f43e1811c44d926814e73ff75252`；真实 v2.2 r1/o1 的 25 attempts 继续可读。
8. Python 3.13 reference 与当前 Mac compatibility interpreter 的 full pytest 全绿；Black、compileall、
   `git diff --check` 与 touched Python files 的 Ruff 全绿；full Ruff 只能保留已披露的 7 个 untouched baseline。

实现形成一个 clean commit：`fix: close atomic formal evidence ledger`。随后只提交实现 session log，停止并交回 Codex。
修复通过后仍不得自行 prepare/run formal 003；Codex 必须独立复核并冻结 Windows execution bundle、profile hash、调用前
usage、执行顺序与 r1 budget 后，才能使用 Robert 之后给出的单独 live-call 授权。
