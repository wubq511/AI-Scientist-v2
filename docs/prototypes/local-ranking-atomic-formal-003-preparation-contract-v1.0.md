# Local-ranking atomic formal 003 preparation contract v1.0

日期：2026-09-02（Asia/Shanghai）
状态：**Robert 已批准 prepare-only；live model calls 未授权**

执行代码基线：`8ea6443e5a4424fe3068a48a8b3d40c5ddfa56aa`
正式 attempt：`pro-max-calibration-003-tool-output`

上游冻结边界：

- [Atomic evaluator contract v2.0](local-ranking-atomic-evaluator-contract-v2.0.md)
- [Atomic tool-output contract v2.3](local-ranking-atomic-tool-output-contract-v2.3.md)
- [Formal-readiness review v2.3](local-ranking-atomic-tool-output-formal-readiness-review-v2.3.md)
- [Formal-readiness supplement v2.3.1](local-ranking-atomic-tool-output-formal-readiness-amendment-v2.3.1.md)
- [Formal evidence-ledger supplement v2.3.2](local-ranking-atomic-formal-evidence-ledger-amendment-v2.3.2.md)

## 1. 本阶段回答什么

本阶段只把 formal 003 的输入与执行环境变成一个可复核、可跨设备传输、尚未产生新 vote 的冻结对象。结束时必须能回答：

1. 六个 orientations 是否全部由同一已验收代码、同一两份 source bundles、同一 Pro/max instrument 生成；
2. profile 是否绑定 exact manifests、canary、transport smoke、调用前 quota 与最坏预算；
3. Windows 收到的是否就是 Mac 冻结的 execution bundle；
4. 后续若只授权 r1，runner 最多能发多少次、在什么条件下必须停止。

本阶段不回答 Pro/max 是否是合格裁判，不读取 winner，不运行 semantic aggregate，不产生 candidate vote，也不因 prepare-only
结果修改 rubric、prompt、tool schema、model、effort、token ceiling、retry 或 promotion gates。

## 2. 冻结身份

### 2.1 Source bundles

只允许使用以下两份已经 spent、但仍是 evaluator calibration 合法输入的 exact bundles：

| orientation | path | file SHA-256 | self SHA-256 |
| --- | --- | --- | --- |
| 1 | `artifacts/local-ranking-prototype/evaluator-profile-calibration-v1/preparations/pro-max-sse-v1/orientation-1/input/bundle.json` | `9e98b1f9c9e4ffe5c57c3c81219a03c50717a0729bd3447e82c4ca174d898e5c` | `4e8d2db1983dfab5055624a12790bb9ac77d56a3424c62af6d9434e92900f7f2` |
| 2 | `artifacts/local-ranking-prototype/evaluator-profile-calibration-v1/preparations/pro-max-sse-v1/orientation-2/input/bundle.json` | `b8ccd49bca0e1cb6c6c23d07229f0d875195504ef297fc3f8d02ecb10504aa10` | `800e994595c74be2d6fa5b71adfc673acc126ec1939560f8636064ee2adbf4f3` |

`r1`、`r2`、`r3` 对同一 orientation 复用 source bytes，但必须生成各自的 atomic identity，并在 live 阶段取得 fresh、全局唯一
provider response IDs。历史 Pro/max judgments、continuation 与 canary response 均不得进入新 traces。

### 2.2 Instrument prerequisites

- evaluator：`opencode-go/deepseek-v4-pro`，`reasoning_effort=max`；
- response submission：`forced_submit_judgment_tool`；
- atomic / transport manifests：current `v2.5` / `v3.1`；
- attempt ledger：current `v2.6`；
- `max_tokens=16384`，`max_concurrency=4`，每 logical call 最多 4 次 exact-request attempts；
- canary summary：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-tool-output-canary-001/canary-summary.json`，
  SHA-256 `900b49b59c72f3da4282e2cf7d58affb7df0678421a9f042cf868db4a6b26749`；
- concurrency smoke result：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/transport-smoke-001/output/result.json`，
  SHA-256 `b57460388033dd6ced38f7f45bb7b175bea6e55d74137ae83faa44fb71c44d9e`。

Canary 只证明 forced-tool transport，旧 4-call smoke 只证明 concurrency 4；两者职责不同，所以 profile 同时保留两项绑定。

## 3. Prepare-only 输出

Fresh root 必须事先不存在：

`artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-003-tool-output/`

在该 root 下生成：

- `input/r{1,2,3}/orientation-{1,2}/atomic/`：六份 current atomic preparations；
- `input/r{1,2,3}/orientation-{1,2}/transport/`：六份 current transport preparations；
- `input/usage-before.json`：authenticated read-only quota/model snapshot；
- `input/profile-manifest.json`：current profile v2.2；
- `input/frozen-prerequisites/`：上述两份 source bundle、canary summary 与 concurrency smoke result 的 byte-identical copy；
- `controller/freeze-summary.json`：在 archive 外记录执行代码 SHA、全部关键 hashes、文件数量/大小、生成命令、平台、Python
  版本、验证结果、Windows bundle SHA 与远端验证结果；不得记录 secret、SSH identity、host/IP 或用户绝对路径。

所有传给 `atomic_profile prepare` 的路径必须从 repository root 表示为相对 POSIX path，使 profile 在 Windows checkout 下仍可解析。
同一 source、replicate、orientation 在临时目录重复 prepare 必须 byte-identical；临时重放不得写入 formal root。

`snapshot-usage` 是本阶段唯一允许的 provider request：只可调用 authenticated `GET /usage` 与公开 model-list endpoint，不发送
messages/tools/prompt。Snapshot 三个 period 都必须为 `status=ok`，但 percent 数值只用于向 Robert 报告，不新增自定义 quota、
token 或 cost admission threshold。若 preflight 不满足现有 validator，prepare 阶段停止，不生成“ready”结论。

## 4. Mac / Windows 拓扑

Mac 是 controller：从 clean code baseline 生成 inputs、取得 read-only usage snapshot、构建 archive、经 SSH 编排并审阅回传证据。
Windows 是 formal evidence executor：只从传入的 immutable bundle 运行 current runner；不得把 Windows 暂时不可用当作改在 Mac
执行 formal calls 的理由。

Prepare-only 阶段必须：

1. 从代码基线构建不含 `.git`、credential、Kimi config、`.env`、历史 outputs 的 source tree；
2. 加入 formal 003 `input/` 与一个 canonical file ledger，ledger 对除自身外的每个 bundle file 记录 relative path、size、SHA-256；
3. 生成单一 archive 并在 Mac 记录 SHA-256；
4. 只复制一次到 `D:\AI-Scientist-v2-workspace` 下的新目录，不覆盖旧 checkout 或旧 evidence；
5. Windows 先核对 archive SHA，再解包并逐文件核对 ledger；
6. 用 Windows Python 3.13.7、UTF-8 mode 离线重验六份 atomic/transport preparations 与 profile；不得读取 credential、不得调用
   model endpoint；
7. 把 Windows verifier 输出及其 SHA 回传到 archive 外的 `controller/freeze-summary.json`，避免让 archive hash 自我引用；
   repository 不保存 hostname、IP、SSH 用户或密钥路径。

本阶段不要求 Mac/Windows 性能比较，也不在 Mac 重跑未来 Windows live outputs。API latency 主要由远端 provider 决定；Windows
在这里的价值是遵守 formal evidence 执行拓扑和保持后续运行与回传边界一致，不声称它能加速模型推理。

## 5. Profile 与预算

Profile 冻结完整三组：`144 logical / 576 physical` 是结构上限，不等于当前调用授权。

下一次若 Robert 单独批准 live execution，首批只允许 r1 mirror pair：

1. `r1/o1`：24 logical，最多 96 physical；任一 call 四次仍 invalid，orientation=`incomplete`，立即停止，不发 `r1/o2`；
2. `r1/o2`：仅在 `r1/o1` 完整后执行，24 logical，最多 96 physical；
3. r1 合计上限：`48 logical / 192 physical`，concurrency 最大 4；
4. 两路都完整后才计算 mirror pair；stable `<22/24` 或 stable directional count=`0` 时 profile semantic FAIL；
5. r1 PASS 也不自动授权 r2/r3。Codex 先复核 ledger、provider response ID uniqueness、usage/cost 与 pair result，再决定下一批授权。

不设置 first-attempt-valid、retry rate、latency、token、cost、tie rate 或 winner direction 门槛。Retry 只能由机器可判定 invalid 触发；
valid 后禁止重发；人工不能因为答案方向不理想而追加调用。

## 6. Kimi prepare-only 权限与停止条件

本阶段任务量为中等，具体准备与跨设备验证交给 Kimi Code/Kimi K3。允许：

- 读取本合同、上游 contracts、current Python modules/tests 与指定 frozen artifacts；
- 运行离线 prepare/validate/replay、full tests 与静态检查；
- 调用 read-only usage/model-list preflight；
- 使用既有 SSH 连接，把无 secret execution bundle 复制到 Windows 并离线验证；
- 写 fresh ignored artifacts、更新 ticket/README/session log，并形成必要的最小提交。

禁止：

- 调用 chat/completions、responses 或任何产生模型输出的 endpoint；
- 在 Windows 持久化或通过命令行/日志打印 API key；
- 运行 `atomic_runner` 的真实 transport，创建 formal output vote，或读取历史 private answer 来改变输入；
- 修改 tool schema、prompt、rubric、model、effort、token ceiling、retry、gates、版本族或 frozen canary/legacy artifacts；
- 自动进入 r1、r2、r3 或 fallback。

若现有代码不能完成本合同，Kimi 只可直接修复不改变实验 instrument 的小缺陷，并以 TDD、clean commit 和 exact diff 回报；中量
及以上改动、任何 request bytes 变化、credential 设计变更或重新 canary 必须停止交回 Codex。

Prepare-only PASS 后 Kimi 必须回报并停止：implementation/source SHA、六组 manifest hashes、profile hash、usage snapshot 值与 hash、
execution archive hash/size/file count、Windows verifier 结果、测试/静态检查、所有 deviations 和 exact paths。只有 Codex 独立复核并
向 Robert 展示这些值后，Robert 的新明确批准才能授权 r1 live calls。
