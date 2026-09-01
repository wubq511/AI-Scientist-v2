# Local-ranking evaluator profile calibration protocol v1.0

Protocol date: 2026-09-01（Asia/Shanghai）
Status: **Approved and frozen before qualification-008 output**

本协议回答一个问题：`opencode-go/deepseek-v4-flash` / `high` 在冻结的 24-item 匿名 top-3
`Retrieval Result` 比较任务上，qualification-007 的 `22/24` 是偶然波动，还是该 profile 的持续运行特征。
它不选择 BM25/E5、不打开 private mapping，也不把 calibration judgment 计入正式 evaluator panel。

Robert 已批准固定三组重复实验，并在知道 OpenCode Go retention 仍未确认的情况下，授权再次发送本文件绑定的
两份 exact spent prompts。qualification-007 继续保持 FAIL，只作先导证据，不进入本协议的三组分母。

## 1. Frozen Flash/high profile and inputs

- Source commit before this protocol: `de44dec8e304688f261e6f841a762bfee2615547`；
- Profile: provider `opencode-go`、wire model `deepseek-v4-flash`、effort `high`；
- Transport: direct non-streaming Chat Completions、`response_format=json_object`、`max_tokens=32768`；
- Setwise preparation:
  `artifacts/local-ranking-prototype/setwise-v1.6-qualification/attempts/spent-dev-holdout-001-opencode-go`；
- Orientation 1 bundle SHA-256:
  `10b57768cdd367e91f445ffe0a9aa61f563c3b63c42f4efd4af555eb55cf391b`；
- Orientation 2 bundle SHA-256:
  `aee43f68db7406d511766d5a38b4529659c7ac49211f8e2aff428e37704ab1c9`；
- Orientation 1 request: 269578 bytes，SHA-256
  `9c085636616fd1d90a0769ea54d2ef37d4b50be1219bd3798f3f0e61bd908765`；
- Orientation 2 request: 269578 bytes，SHA-256
  `2c47348451dc09d78807c026171ad4ea000fba69618e7dee9a86f856e968f243`；
- Aggregator source SHA-256:
  `55daae8839f975430b876f98aac391480c91b73c656be2f0efac83588965078a`。

三组 replicate 必须使用上述同一对 bundles、requests、item order、side assignment、rubric、schema 和
validator。唯一允许变化的是 provider 对六个 fresh calls 的响应。六个 provider response ID 必须互异。

## 2. Attempts and controlled concurrency

根 attempt ID 固定为 `qualification-008-flash-high`，包含：

- `replicate-1`：orientation 1/2；
- `replicate-2`：orientation 1/2；
- `replicate-3`：orientation 1/2。

每个 replicate 内两个 orientations 并行，最大并发固定为 2；三个 replicates 依次执行。这样减少成对调用的
等待时间，同时不让六个大请求同时竞争 provider capacity。每次调用写入互斥、write-once execution/result
目录。每个 replicate 最长等待 12 分钟，不高频轮询。

不得在同一 attempt 内 retry、repair、补字段、只重发不稳定 item 或替换某一 orientation。HTTP 429、5xx、
network timeout 等不能归因于 evaluator semantic stability 的基础设施错误，使整个 qualification-008 标记为
`incomplete` 并停止；它既不让 profile PASS，也不把 profile 判为 semantic FAIL。JSON/schema/coverage/
evidence validator failure属于 profile 的运行可靠性失败，但仍保留其余预登记调用，供固定三组诊断使用。

## 3. Frozen aggregate gates

每一路必须首先满足 exact request/profile receipt、HTTP 200 normal stop、24/24 closed-schema judgments、
bundle/evaluator binding、visible evidence references 和本地 semantic validator。三组都满足后才计算镜像稳定性。

Profile 只有同时满足以下全部条件才 PASS：

1. 每组 mirror stable 至少 `22/24`；
2. 三组中至少两组达到原始 `23/24` gate；
3. 三组合计至少 `69/72`；
4. 六个 fresh calls 的 provider response ID 全部不同。

例：`22 + 24 + 24 = 70` PASS；`22 + 23 + 23 = 68` FAIL；`21 + 24 + 24 = 69`
也 FAIL。必须完成三组后按全部预登记结果判断，不能挑最好的一组，也不能继续追加第四组直到过线。

## 4. Sequential profile ladder

若 Flash/high PASS，停止 profile ladder，并以该 profile 与 Kimi K3 运行一个全新的双模型 panel qualification；
本 calibration 的六个 outputs 不得复用为 panel votes。

若 Flash/high FAIL，依次验证：

1. `deepseek-v4-flash` / `max`；
2. `deepseek-v4-pro` / `high`；
3. `deepseek-v4-pro` / `max`。

每个新 profile 必须先通过独立 synthetic transport probe，再生成绑定正确 evaluator identity 的新 bundles/
requests，并按同样的三组 aggregate gates 运行。第一个 PASS 的 profile 停止 ladder。若 Pro/max 仍 FAIL，
停止且不得降低 gate；后续只能在新批准协议下重构 evaluator task 或更换模型族。

## 5. Interpretation boundary

三组调用只能作为当前 provider/profile/冻结任务的 operational reproducibility 证据。Provider 没有暴露 seed，
也不能证明重复调用是统计独立样本，因此本协议不计算置信区间或显著性。并行完成不等于独立性证明；response
IDs、timestamps、usage、raw hashes 和全部失败只是让该限制可审计。

无论 PASS/FAIL，都不得打开 private mapping、运行 candidate reducer、计算 BM25/E5 winner，或进入任何
Downstream Experiment。
