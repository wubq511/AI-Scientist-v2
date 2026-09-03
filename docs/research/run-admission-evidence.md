# Ideation Run admission boundary 验证证据

日期：2026-09-03

Implementation ticket：[Admit an Ideation Run without paid work](../wayfinder/ideation-implementation/tickets/04-admit-an-ideation-run-without-paid-work.md)

验证矩阵：`VM-UNIT-02`、`VM-UNIT-03`、`VM-UNIT-06`、`VM-CONTRACT-023-01`、`VM-CONTRACT-024-02`

## 结论

new-run 安全入口已落地：请求 schema 校验、exclusive-create run root、canonical `request.json`/`admission.json`、连续 hash chain 的 preflight 事件、九步 fail-closed 准入序列、versioned CNY 价格表、保守费用上界与显式 `yes` 批准全部按合同实现。任何一步失败都留下带 `preflight_rejected` 终结事件的证据，不产生 `admission.json`；整个 slice 零模型调用、零网络请求、零费用，未进入 BFTS 或其他 downstream 阶段。

## 固定实现边界

- 开工固定点：`add45bd4403a6b15ab13cee058231483e8010f58`（`fix: backfill closure commit SHA in session log`）。
- 实现 commits：`cbaa99b add: implement Ideation Run admission without paid work`、`631e209 fix: harden admission preflight per two-axis review`、`6783c46 fix: close re-review findings in admission boundary`、`7d4884e fix: reject denormalized relative paths; prove canonical negatives`（验收自查补缺）。
- CLI 面：`python ai_scientist/perform_ideation_temp_free.py new-run --help`；运行说明见 `AGENTS.md`。
- 模块职责：`run_store.py` 负责 run root、write-once 文档与 event hash chain；`pricing.py` 负责 versioned 价格表、上界与逐 attempt 计价；`retrieval.py` 只构造绑定获批 corpus 的 retriever（检索执行归 05 票）；`admission.py` 负责九步序列与 Run Admission。

## CLI 面（024 合同）

new-run 只接受七个参数：`--case-id`、`--workshop`、`--workshop-sha256`、`--corpus`、`--corpus-sha256`、`--max-num-generations`、`--num-reflections`。模型身份（`deepseek-v4-pro`、`https://api.deepseek.com`）锁进代码并写入 admission；无 model、ranker、device、output-root 或隐式 resume 控制。无子命令时打印 help（exit 0）；legacy 基线路径保留为显式 `legacy` 子命令（expand-contract，13 票收除）。

入口 import 副作用已消除：工具实例与 prompt 构造收进惰性工厂，`--help` stderr 为 0 字节（此前含 SemanticScholar API key warning）。`--help` stdout 基准 hash 因子命令化从 `362c88d2…` 更新为 `1175cbe4…`（`COLUMNS=80`、`S2_API_KEY=baseline-smoke`）。

## 九步 preflight（VM-CONTRACT-024-02）

1. 封闭 request schema（`case-[0-9a-f]{32}`、lowercase 64-hex、正整数）——失败是 run 外 entry error，不创建任何 run root。
2. 铸 `run_id`（canonical lowercase UUIDv4）、exclusive-create `artifacts/ideation-runs/<run_id>/`、写 canonical `request.json`（含完整 command evidence）。
3. `git status --porcelain` 验 clean worktree，`git rev-parse HEAD` 记录 commit。
4. Approved Workshop：路径经 `workspace_relative_path` 守卫、exact hash、manifest `approval_status=approved`、`case_id` 一致、manifest 绑定 pinned bytes。
5. Approved Corpus：hash、manifest approval/case、inventory 绑定、bundle 目录 case-named、validation report 存在且 inventory hash 匹配、report 绑定 `corpus_sha256` 且 `status=pass`/`error_count=0`、corpus `schema_version` 与 manifest versions 一致。
6. 构造绑定唯一获批 corpus 的 retriever，记录 policy 版本；无模型调用。
7. `DEEPSEEK_API_KEY` 存在性检查（不读值、不记录）。
8. 高峰费率、全 cache miss、声明 token 预算、≤2 attempts 计算上界，打印明细，stdin 必须 `isatty()` 且输入恰为 `yes`；其余一切（含非交互）fail closed。
9. 写 `admission.json` pin 全部输入（workshop/corpus/commit/价格表 hash/model/budgets/approval 事实），此后才有付费调用路径。

任一步失败：事件链以 `preflight_rejected` 收束并留存 request/事件证据，无 admission，无 fallback。

## 定价（VM-UNIT-06）

`ai_scientist/ideation/policies/deepseek-cny-price-table-v1.json`（SHA-256 `f02bab04f210a7cab755ae0ccb027920570cc17ad3d146cec38167ac3a8c77fd`，代码硬绑定同一 digest，缺失/漂移 fail closed）登记 2026-08-29 官方人民币价：高峰 cache hit 0.30 元、cache miss 9.0 元、output 27.0 元/百万 tokens，空闲减半（0.15/4.5/13.5）；高峰窗口为工作日 01:00–04:00 与 06:00–10:00 UTC；source URL 与登记日期入表。计价用 `Decimal`，金额向上取整到分；attempt 按开始时刻所在时段结算；上界恒按高峰、全 miss、≤2 attempts。

## TDD 与验证结果

主要 RED 证据：`test_run_admission.py` 首次运行因模块不存在 collection fail；`test_run_pricing.py` 同；`test_run_preflight.py` 首次 9 failed（`new-run` 子命令不存在）；price table hash pin 曾以占位值跑出 `PRICE_TABLE_HASH_MISMATCH` 后以真实 digest 转绿；`attempt_cost` 期望值先按错误手算 5.13 红灯，复算为 4.98 后转绿；pty harness 先暴露 close-master 丢弃缓冲使 `yes` 变 EOF 的缺陷，改为写后保持 master 打开转绿。

最终可复现命令（`<venv>` 为 Python 3.13.7 clean venv；依赖未变，环境继续引用 [ideation foundation lock](ideation-foundation-macos-arm64-py313.lock.txt)，SHA-256 `8b43ebd5480a02a1613a44f65a6bd27ba94e8aa24b9e9eb8fa48cc82d75e26f0`）：

```bash
<venv>/bin/python -m pytest -q \
  tests/test_run_admission.py tests/test_run_pricing.py tests/test_run_preflight.py
<venv>/bin/python -m pytest -q
<venv>/bin/python -m compileall -q ai_scientist
<venv>/bin/python -m black --check ai_scientist/ideation \
  ai_scientist/perform_ideation_temp_free.py tests/test_run_admission.py \
  tests/test_run_pricing.py tests/test_run_preflight.py \
  tests/test_ideation_import_contract.py tests/test_ideation_cli_baseline.py
S2_API_KEY=baseline-smoke COLUMNS=80 \
  <venv>/bin/python ai_scientist/perform_ideation_temp_free.py --help
```

结果：

- 新增测试 30 项（store 9 + pricing 7 + preflight 14）全部通过；定向命令 `30 passed in 25.40s`。
- 全量 pytest：`328 passed in 44.86s`（开工前基线 298 passed，全部保持通过）。
- compileall：exit `0`。
- Black：触及范围 24 files 全部 unchanged；repo-wide 既有 14 个 retained legacy/downstream 格式债务不变，未以 exclude 掩盖。
- `--help`：exit `0`、stderr 0 bytes、stdout SHA-256 `1175cbe491d2e8736bda75a68101f74818e56d85184249588d40a1085cdd9977`。
- import closure allowlist 显式扩至 14 个内部模块（新增 `ideation.admission/canonical/contract/errors/pricing/retrieval/run_store/schema`），第三方 top-level 仍为 `anthropic/backoff/openai/requests` 四包，无新增依赖。
- `requirements.txt` / `requirements-dev.txt` 未修改，SHA-256 保持 `3b031a68…` / `68528a63…`。
- `.gitignore` 新增 `artifacts/ideation-runs/`（023 私有 root）。

## Code review

固定点 `add45bd` 的首轮双轴 review：Standards 8 项（最高信号：不可能的 adjacency 守卫、双生 schema 常量、`_now` 三重复制、死 helper）；Spec 10 项（最实质：step-1 仅有 argparse 层、corpus 验证偏浅、`--non-interactive` 超合同、路径绕过守卫）。修复 commit `631e209` 处理全部可执行项：schema 校验前移、corpus/report/versions 全验、路径走 `workspace_relative_path`、删除超合同 flag 与死代码、统一常量、复用 `contract._now`。

对修复后 HEAD 的双轴复核：Spec 轴 0 findings（六个修复全部核实、九步顺序与价格合同不变）；Standards 轴余 2 项——manifest 非 dict 值会以 `AttributeError` 逃逸 typed failure 路径（真实失败面）、`_now` 在 `run_store` 仍存一份。修复 commit `6783c46` 引入 `_mapping_field` 使全部 manifest 字段 fail closed、删除 `run_store._now` 与死 `_read_request_hash`、`_run_preflight_steps` 签名改用 `RunHandle`。复核遗留的 judgement calls（loader 返回 string-keyed dict、`attempt_cost` 仅测试触达）记录如下：前者是 023 事件 payload 的序列化边界所需，后者是 VM-UNIT-06 的合同测试对象（022 定义、本票交付的 unit 行），不构成投机泛型。

## 验收自查与补缺（2026-09-03 晚间追加）

验收复核发现两处机检缺口并已在 `7d4884e` 补齐：

- `VM-UNIT-02` 负向条款（duplicate keys、NaN/Infinity、float 值、非 NFC、unpaired surrogate、非法 UTF-8）此前无直接测试；新增 4 项测试实证 `canonical_json_bytes`/`parse_json_bytes` 全部 fail closed，并固化 canonical rendering 形状（sorted/compact/LF/末尾单 newline）。
- `VM-CONTRACT-023-01` 路径负向中，`./x` 与 `x/` 因 pathlib `parts` 丢弃前导 `./`、尾部 `/` 而绕过检查——这是实现缺陷。`workspace_relative_path` 现在在解析前拒绝非归一化形状（`./`、尾部 `/`、外侧空白），以 stash 修复前后做了 RED→GREEN 实证；backslash/absolute/`..`/symlink 负向集一并入测。

补缺后全量 `333 passed in 43.84s`、Black 触及范围合规、compileall exit 0。

## Trust boundary

所有验证 offline、zero-model、zero-cost、zero-network；未访问 provider、Semantic Scholar 或任何远端服务。`DEEPSEEK_API_KEY` 在测试中仅验证存在性，fixture 用占位值，真实 credential 从未进入源码、日志、commit 或本证据。价格表、canonical bytes 与 fixture 均不含 Target Paper identity、真实 prompt、response 或 credential。真实获批 Workshop/corpus 的私有路径只存在于 gitignored `artifacts/ideation-inputs/`；run root 为 gitignored `artifacts/ideation-runs/`。本票不选择 Canary 参数（`reasoning_effort`/`max_tokens` 以 pinned 默认值入 admission，胜者归 035/036）。