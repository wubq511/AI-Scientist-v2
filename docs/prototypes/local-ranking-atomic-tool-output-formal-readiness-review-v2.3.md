# Atomic tool-output v2.3 独立复核与 formal-readiness 修复合同

日期：2026-09-02（Asia/Shanghai）

状态：**Canary accepted；implementation not formal-ready；repair authorized，live calls not authorized**

复核对象：`fa2409ff1d955cb546aec27f08de7ae62412e130` 与
`pro-max-tool-output-canary-001`

## 1. 结论

Forced `submit_judgment` transport 的最小假设已通过：synthetic probe 有完整 tool-call receipt，历史上连续四次
free-content JSON 失败的 spent `call-021` 在 tool transport 下 first-valid。该 canary 继续只属于
`spent_transport_only`，不产生 semantic vote，但无需因下面的 metadata/validator 修复而重跑。

`fa2409f` 不能直接用于 fresh `pro-max-calibration-003-tool-output`。独立复核发现五个 formal evidence blocker，
另有一个已知 runner/profile 缺口和一次流程偏差。下一步只修 formal readiness；不得发送新的 model call。

## 2. 独立确认的 canary 证据

- 实现 commit 恰好修改 v2.3 §10 的 8 个文件；完整 pytest 为 `156 passed`，Black、compileall 与
  `git diff --check` 通过。
- `canary-summary.json` SHA-256 为
  `900b49b59c72f3da4282e2cf7d58affb7df0678421a9f042cf868db4a6b26749`；记录 2 个 physical calls，usage
  rolling/weekly/monthly 从 `0/32/40%` 变为 `0/33/40%`。
- Synthetic receipt/response SHA-256 分别为
  `03b69356dccb81e972723accbc33876b0be396bdc1cb1d85df76ab36f0b8d081` /
  `a4b1b80643f7477475b38963a66f6540b4cddaf9b8ae3ba29037894f33c238f2`；provider response ID 为
  `chatcmpl-RUZWeimRG6eAfScBjtMpvaGP`。
- Stress receipt/response/execution-result/attempt SHA-256 分别为
  `4226858331160cdce971e0433c5dd0b45994199ea0c4edade61ce68196e0fa82` /
  `d08396930840b08432e4abe2ac17ec6f9e6c702cf26b3dae35e6b5be3fdcedec` /
  `72d95a24ffd0da765024418b23dd5ad412e5d59073c90574e46812f093709480` /
  `5d620f2807f584071d444dc842811f2ea266f43e1811c44d926814e73ff75252`；provider response ID 为
  `chatcmpl-RNCl4vbqyB1DXrXHWRMJKXe0`。
- Codex 从 raw SSE 重新提取 tool arguments，得到与 canonical `response.json` byte-identical 的对象；重新运行
  `record_attempt` 得到 `valid`。Receipt 中全部文件 hashes 与磁盘 bytes 一致，safe headers 和 evidence root
  未发现 credential。
- `SUBMIT_JUDGMENT_SCHEMA` 与 v2.3 合同 JSON 相等；request 只有一个 forced tool、没有 `response_format`，且
  message content 与 prompt bytes 相等。新旧 `call-021` 的 source/packet 相同，只有已批准的 prompt/transport
  改变。

这些事实直接证明 canary 要回答的两个问题：provider 接受 forced tool transport；原先失败的 stress item 可以通过
该 transport 交付完整 judgment。下面的修复不改变成功 request bytes，因此不会推翻这个结论。

## 3. Formal blockers

### F1 — manifests 缺少已冻结的 instrument identity

v2.3 §9 要求 primary/fallback manifests 显式携带 `response_submission` enum，但 atomic v2.4 与 transport v3.0
manifests 都没有该字段。下游只能从 request shape 猜测 transport，违反 single-source provenance。

### F2 — 真实 legacy evidence 不能读取

`_load_call_packet` 对所有 manifest versions 都用新的 tool prompt 重建 bytes。真实
`pro-max-calibration-002` atomic preparation v2.2 的第一个 packet 因而报 `HASH_MISMATCH`。现有 legacy test 只是
把新 manifest 改成旧 version，仍使用新 prompt，未测试历史 bytes。

### F3 — 新旧 transport family 可以非法混装

当前 `record_attempt` 会接受 atomic preparation v2.4 + legacy receipt v2.0 / execution v2.0，并写出 valid
attempt v2.5。版本 allowlist 没有按 measurement instrument 配对，无法阻止 free-content JSON evidence 冒充 tool
evidence。

### F4 — 单 call smoke validator 没验证 transport evidence

`validate-smoke-call` 只读取 `response.json`。仅复制一份正确 response、完全不提供 receipt、execution result、raw
SSE 或 tool identity 也会得到 PASS。当前 canary 的完整 receipt 已被 Codex 独立复核，所以本次 PASS 仍成立；未来
validator 必须自身 fail closed。

### F5 — JSON escaped lone surrogate 会丢失失败证据

合法 UTF-8 SSE 可以用 JSON escape 携带 lone surrogate。当前路径在 canonical UTF-8 encode 时抛出未捕获的
`UnicodeEncodeError`，并且不写 `execution-result.json`。这不是答案质量问题，但会破坏 every physical call 的
可重放 ledger。

### F6 — Formal runner/profile 仍写旧 schema

`atomic_runner.py` 仍写 orientation-run/round v2.1，`atomic_profile.py` 仍写 profile-manifest v2.1；它们尚未实现
v2.3 §9 已冻结的 v2.2 versions，也没有绑定 tool canary 或 response-submission identity。

### Process deviation — Ruff 前置条件未满足

合同要求 Ruff 全绿，但 live canary 前 full command 仍有 11 个 pre-existing findings。它们没有改变 canary raw
request/response 的真实性，因此不否定 canary；但“pre-existing”不是原合同允许的例外。后续采用有保护作用的差分
门槛：本次涉及的 Atomic files 必须 Ruff zero-error；未触及文件保留的 7 个 baseline findings完整披露，但不再作为
formal blocker。这样既防止新增 lint debt，也不为清理无关代码扩大实验 scope。

## 4. Frozen repair design

### 4.1 Current writers 与显式枚举

只冻结一个当前 primary enum：

```text
response_submission = "forced_submit_judgment_tool"
```

Fallback 仍未实现；其 enum 值只能在 fallback 获批时另立合同，不能预埋可执行分支。

Current writers 更新为：

- atomic preparation：`local-ranking-atomic-preparation-v2.5`；
- transport preparation：`local-ranking-atomic-opencode-go-preparation-v3.1`；
- orientation run / execution round：v2.3 已冻结的 `v2.2`；
- profile manifest：v2.3 已冻结的 `v2.2`；
- attempt v2.5、orientation trace v2.5 / result v2.3、receipt v3.0、execution result v2.1 保持不变，因为其
  shape 与 successful tool receipt 已经正确，不为 metadata field 做无意义版本膨胀。

Atomic v2.5、transport v3.1 与 profile v2.2 manifests 都必须 closed-schema 包含 exact
`response_submission`。Fresh profile 只接受这组 current manifests，且所有 orientations 必须相等。

### 4.2 Legacy/canary read 与 current execute 分离

- Atomic v2.2/v2.3 使用冻结的 legacy JSON prompt 重建；只接受 legacy attempt v2.3/v2.4、receipt v2.0、execution
  v2.0。
- Atomic v2.4 是本次 spent tool canary family，使用 tool prompt；只接受 attempt v2.5、receipt v3.0、execution
  v2.1。
- Atomic v2.5 是 current tool family，使用相同 tool prompt；只接受 attempt v2.5、receipt v3.0、execution v2.1。
- Transport preparation v2.1 可做 legacy diagnostic validation；v3.0 可做 canary diagnostic validation；只有
  current v3.1 可被 `execute-call` / runner 发送。
- Legacy/canary evidence 可以 read/replay/diagnose，但不能 resume live execution、进入 fresh profile、或被 current
  writer 静默改写。

Version pairing 必须由 validator 读取显式 schema/enum 后决定，禁止根据是否存在 `tool`、`response_format` 或
`tool_call_id` 猜测。

### 4.3 Strong smoke validation

`validate-smoke-call` 必须验证 current preparation call、execution-result、receipt、raw/derived file hashes、request
hash、tool name/schema/call ID、provider/model/finish reason、usage/cost、canonical response 和 exact synthetic
arguments。Response-only directory 必须 fail。Current canary 的完整 raw evidence必须通过这个增强 validator。

### 4.4 Unicode failure evidence

Tool arguments、content 或 reasoning 解码后若含不可 canonical UTF-8 的值，返回 typed machine-invalid error，并写
完整 failed `execution-result.json` 与 raw stream evidence；不得抛出无 ledger 的 Python exception，不得修复或替换
字符。

### 4.5 Formal profile binding

Profile manifest v2.2 用 `transport_canary_summary_sha256` 绑定本合同 §2 的 exact
`900b49b59c72f3da4282e2cf7d58affb7df0678421a9f042cf868db4a6b26749`，并记录
`canary_implementation_commit=fa2409ff1d955cb546aec27f08de7ae62412e130`。`prepare_profile` 必须读取并
closed-schema 验证该 summary：`evidence_class=spent_transport_only`、physical calls `1..5`、provider/model/effort/
max tokens exact、synthetic validator pass、stress semantic validator pass、stop condition 为 first-valid canary PASS，
且 summary bytes 的 SHA-256 与输入一致。

Formal source commit 是 repair 后的新 clean commit；它不必等于 canary implementation commit，但 profile 必须同时
记录两者。只有当 tool schema、prompt 或 HTTP request bytes 改变时，旧 canary 才失去 transport qualification；纯
manifest metadata、legacy validators、runner/profile 和 invalid-edge 修复不触发重跑。

## 5. Implementation scope

这次修复涉及 11 个文件，超过 8 个是因为 formal scheduler/profile 原本被明确留到下一阶段，不是功能扩张：

- `prototypes/local_ranking/atomic_judge.py`
- `prototypes/local_ranking/atomic_opencode_go.py`
- `prototypes/local_ranking/opencode_go_stream.py`
- `prototypes/local_ranking/atomic_runner.py`
- `prototypes/local_ranking/atomic_profile.py`
- `tests/test_local_ranking_atomic_judge.py`
- `tests/test_local_ranking_atomic_opencode_go.py`
- `tests/test_local_ranking_opencode_go_stream.py`
- `tests/test_local_ranking_atomic_calibration.py`
- `prototypes/local_ranking/README.md`
- ticket 021

不增加 dependency，不修改 v2.3 tool schema/prompt/rubric/packet/model/effort/max tokens/retry/gates，不清理其他模块的
Ruff baseline，不修改既有 canary/legacy artifacts，不发送 model call。

## 6. Required proofs

实现 commit 前必须全部满足：

1. 真实 historical v2.2 manifest + prompt/attempt replay PASS；当前 canary v2.4 raw evidence replay PASS；
2. new manifest + legacy receipt/result、legacy manifest + tool receipt/result、response-only smoke directory 全部
   fail closed；
3. escaped lone surrogate 得到 typed invalid 与 complete failed execution result；
4. atomic v2.5 / transport v3.1 repeated prepare byte-identical，且都有 exact `response_submission`；
5. old canary `call-021` tool schema、prompt 和 HTTP request hashes 仍分别为
   `fa2cea71b0c41b87ef7743010656cd819d871ab2e8a95fcff2f8518cd11a859c`、
   `4d8b409ebd6a3b24aed74e6ec230cd8b83950858de6a068b7e4f63a5501134ef`、
   `7445fd80b52c1b4da594f46fe28d0811f22efb35be8edf188a2d823499588cb4`；
6. profile v2.2 绑定并验证 exact canary summary，拒绝错误 hash、FAIL/incomplete summary、legacy/canary manifests 和
   mixed response submission；
7. runner v2.2 保持 max concurrency 4、invalid-only attempts 1–4、first-valid stop、resume partial-call fail-closed 与
   orientation early-stop 语义；
8. Python 3.13 reference 和当前 Mac compatibility interpreter 的 full pytest 全绿；Black、compileall、
   `git diff --check` 全绿；上述 9 个 Python implementation/test files 的 Ruff 为 zero-error；full Ruff 只能留下未触及
   files 的 7 个已披露 baseline findings，且不得新增。

完成后形成一个 clean commit，message 为 `fix: harden atomic tool formal readiness`，然后停止并交回 Codex。不得
prepare fresh profile、连接 Windows executor、读取 credential 或发出任何 model request。

## 7. 下一决策边界

Codex 复核 repair commit 后，才报告 fresh 003 的 frozen profile hash、Windows execution bundle、调用前 usage、
execution order 与预算。Formal calibration 最多 144 logical / 576 physical calls，实际先跑 r1 两个 orientations；
r1 semantic gate 不通过就停止，不发送 r2/r3。该 live-call 授权必须由 Robert 单独批准，不能由本修复合同推导。
