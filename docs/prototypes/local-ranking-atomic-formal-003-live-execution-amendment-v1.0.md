# Local-ranking atomic formal 003 live execution amendment v1.0

日期：2026-09-03（Asia/Shanghai）
状态：**Robert 已批准本 amendment 与 r1 live execution；r2/r3 未授权**

本文件补充而不改写
[formal 003 preparation contract v1.0](local-ranking-atomic-formal-003-preparation-contract-v1.0.md)。Preparation contract
SHA-256 继续固定为 `a08d761279fb70a56b653b79c8f1055f9cb56d15be88c48954cf5c8cc9f6252c`；本 amendment 只覆盖其
live authenticated caller 拓扑，不改变已经完成的 prepare-only 身份或证据。

## 1. 冻结边界

- runtime source commit：`8ea6443e5a4424fe3068a48a8b3d40c5ddfa56aa`；
- prepared controller commit：`326f928349255b5c51ee638285db61a15613977c`；
- profile manifest SHA-256：`6be3471c0f774f7d88ebfb06cbf322a5dcba1910d5f3b73e87c515248d30762b`；
- execution bundle SHA-256：`d7acd549d4e17e628da67ec788d5dda5212715d7b0d45644db98f3b593e86795`；
- bundle ledger SHA-256：`c008f9dfec8ab6671d05a1b3a6d9b794e0bf6a734ebbcc34d08d4d2fe7939ffb`；
- freeze summary SHA-256：`22283185a831348d68b47565723fddc176e7c828e451357b80a5edb42a9b3d60`；
- evaluator：`opencode-go/deepseek-v4-pro`，`reasoning_effort=max`；
- submission：单一 forced `submit_judgment` tool；
- `max_tokens=16384`，`max_concurrency=4`，每 logical call 最多 4 次 deterministic-invalid retry。

两份 source bundles、144 个 prepared requests、prompt、tool schema、rubric、model、effort、retry、semantic gates、canary 与
historical evidence 均保持冻结。无需重新 prepare、重新 canary 或修改 profile；r1 只使用已冻结六路中的 `r1/o1` 和
`r1/o2`。

## 2. Live 拓扑与 credential boundary

Mac 是 authenticated request executor。它必须从上述 archive 的 fresh extraction 导入 frozen runtime 与 input，在 bundle
外的新 output root 执行 request；API key 只由 Mac 本地 environment 或 Kimi config 提供，不写入 command、artifact、日志、
archive 或 Windows。

Windows 是 credential-free offline verifier。它只接收 Mac 生成的 immutable output archive，核对 archive SHA、短路径解包，
再用已验证的 frozen bundle/runtime 离线 replay。Windows 不读取、复制、持久化或转发 API key，也不访问 provider endpoint。

这一变化不改变实验变量。远端 provider 承担模型推理，caller OS 只负责发送 exact request bytes、解析 SSE 和写 evidence；因此
Mac/Windows caller 性能不是指标，也不要求重复两平台 live calls。

## 3. Fresh preflight

任何 live request 前依次完成：

1. 当前 tracked contract/rules commit 已冻结，runtime `.py` 与 `8ea6443` 的 diff 为空；
2. formal output root、live usage snapshots、pair result 与 live summary 均不存在；若存在无法解释的 partial state，停止；
3. 在 fresh Mac extraction 重算 archive SHA，运行 bundle ledger/verifier，确认五步 PASS；
4. 用 Mac 本地 credential 运行一次 `atomic_profile snapshot-usage`，写到
   `controller/live-r1-usage-before.json`；它只允许 authenticated `GET /usage` 与公开 model-list GET；
5. snapshot 必须通过现有 schema、HTTP status、三 period `status=ok` 和 model-present 校验。百分比只记录，不设额外 quota、
   token、cost 或 latency threshold。

如果 preflight 未全部通过，零 live request 并停止。Preparation 时的 `usage-before.json` 与 profile hash 不修改；fresh snapshot
作为 live controller evidence 单独保存。

## 4. 唯一授权的执行顺序

输出位置固定为：

- `output/r1/orientation-1/`；
- `output/r1/orientation-2/`；
- `output/r1/pair-result.json`；
- `controller/live-r1-usage-before.json`、`live-r1-usage-after.json`、`live-r1-execution-summary.json`；
- `controller/live-r1-output.tar.gz` 与 `windows-live-r1-verifier-output.json`。

顺序与停止条件：

1. 只通过 frozen `atomic_runner` 执行 `r1/o1`：24 logical，最多 96 physical，concurrency 4；
2. valid 后禁止重发；只有 deterministic validator 判定 invalid 才能用 exact same request retry；
3. 任一 logical 四次仍 invalid、出现 ambiguous partial attempt、identity/hash/evidence failure 或 runner 无法安全恢复时，
   `r1/o1=incomplete` 并立即停止，不发 o2；
4. 仅当 o1 完整并通过本地 offline resume/replay，才执行 `r1/o2`：同样 24 logical、最多 96 physical；
5. o2 incomplete 时停止；两路都完整时只运行 `atomic_pair` 生成 r1 mirror result；
6. `stable_count < 22/24` 或 `stable_directional_count = 0` 时 `stop_profile_failed`；否则只得到
   `continue_profile`，不等于 profile 已 qualified，也不授权 r2/r3；
7. 在最后一次 live request 后尽力获取一次 read-only `live-r1-usage-after.json`。该 diagnostic GET 失败必须披露，但不得据此
   重发任何 model request 或篡改已完成 semantic evidence；
8. r1 完成、失败或中止后均停止并交回 Codex。不得运行 r2、r3、fallback、winner-driven retry 或新的 canary。

本次 live 上限是 `48 logical / 192 physical`；profile 中 `144 / 576` 只是六路结构上限，不是本次授权。

## 5. Evidence 与 Windows offline replay

Mac 保留 runner 生成的完整 executions、attempt ledgers、round checkpoints、resolved traces 与 run results。不得只保留 response
或汇总。所有 provider response IDs 在 r1 两路内必须唯一；usage、cost、timestamps、raw SSE、derived response、receipt、
execution-result、input evidence 与 attempt hashes 继续按 current-family validator fail closed。

Mac 将 r1 output、live usage snapshots、pair result（若产生）和 controller summary 打成一个 credential-free archive，记录
SHA-256、字节数与文件数。通过 `windows-executor` skill 复制到 Windows 的新目录，先核对 archive SHA，再用短路径解包。
Windows 使用 frozen bundle 的 Python 3.13.7 UTF-8 runtime：

- 对每个已运行 orientation 重新进入 `atomic_runner`，必须在读取 credential 或发请求前从完整 run-result/trace 返回同一结果；
- 若 orientation 为 incomplete，必须离线重验 existing attempts 后返回同一 typed failure；
- 若 pair result 存在，在 fresh scratch 重新运行 `atomic_pair` 并要求 bytes identical；
- 保存 verifier stdout/result 与 SHA，回传 Mac；不清理正式 evidence，只清理 scratch。

Windows replay 若失败，禁止重发模型调用；保留 Mac raw evidence、Windows failure evidence并交回 Codex 判断。

## 6. Kimi 执行权限与交回条件

Kimi 只可执行本 amendment 的 preflight、r1/o1、条件式 r1/o2、r1 pair reduction、usage diagnostics、credential-free archive 与
Windows offline replay。Live calls 必须由 frozen runner 发出，不能改成 Kimi 对话、手工 provider call 或其他 harness。

任何 runtime、prompt、request、tool schema、rubric、retry、gate、profile 或 frozen input 修改都必须停止；不得就地修复后继续
同一 formal attempt。允许新增 controller evidence、ticket/session record，以及只记录结果的最小 clean commit。

交回 Codex 时必须报告：

- amendment commit/SHA、archive/profile/preflight hashes；
- o1/o2 logical 与 physical counts、valid/invalid/exhausted counts、全部 provider response ID uniqueness verdict；
- 每路 run-result/trace SHA、pair result 与 SHA（若产生）；
- usage-before/after 与 hashes、receipt 汇总 usage/cost；
- output archive SHA/size/file count、Windows verifier result/SHA；
- 所有 failure/deviation、exact artifact paths、tracked tree 状态。

到此停止。Codex 独立复核 r1 后，才决定是否向 Robert申请 r2/r3；本授权本身不包含后续调用。
