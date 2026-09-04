# Legacy 路径合同化与 Handoff Readiness 验证证据

日期：2026-09-04

Implementation ticket：[Contract the legacy path and prove handoff readiness](../wayfinder/ideation-implementation/tickets/13-contract-the-legacy-path-and-prove-handoff-readiness.md)

验证矩阵：`VM-CONTRACT-024-01`（终验）、`VM-ENV-01`、`VM-ENV-02`、`VM-ENV-03`、`VM-ENV-04`；Validation Matrix 全部已实现行随全量 pytest 重跑。

## 结论

expand-contract 的 contract 阶段完成：新 ideation entry（`perform_ideation_temp_free.py`）的传递 import closure 收紧为纯标准库——global Semantic Scholar、旧 model/output controls（`legacy` 子命令及其 `--model`/输出路径参数）、implicit sibling idea archive（`generate_temp_free_idea` 的 `.md`→`.json` 兄弟文件机制）与 legacy import-time side effects（`llm.py` 链上的 `token_tracker` 模块级实例）全部从入口闭包移除。三类 dependency contract 与最终闭包一致：`requirements.txt` 空（零 runtime 包），四个 legacy 包移入 `requirements-upstream.txt` 继续服务保留代码。Python 3.13.7 clean 环境 628 项 pytest 全绿、preflight CLI 测试在 clean venv 内通过、裸 venv（零第三方包）CLI smoke 通过。本票未执行真实模型 run、未产生费用、未替 035/036 选参数、未进入 downstream。

## 固定实现边界

- 基线 commit：`cd25f36bf9ee464ac99f33769a42fed63e921394`（`add: map ideation implementation tickets`，implementation-map publication baseline）。
- 本票实现 commits：`c359b42 feat: contract the legacy path out of the ideation entry`、`391eac5 fix: close two-axis handoff review findings`。
- runtime 行为改动：删除入口的 `legacy` 子命令与全部 legacy 机器（`_tool_catalog`/`_build_system_prompt`/generation/reflection prompt 常量/`generate_temp_free_idea`，共 −358 行）；新路径（new-run/resume/validate/export/evaluation）行为零变化，由全量回归与逐字节 CLI baseline 证明。
- 保留代码不动：`llm.py`、`tools/`、下游 `perform_*`、`treesearch/` 继续服务 retained 路径；upstream `README.md` 正文未动（不在 diff 中）。

## 依赖合同（最终态）

| 类别 | 包 | 说明 |
|---|---|---|
| runtime（`requirements.txt`） | 无 | 新路径闭包纯标准库；合同有意为空 |
| development（`requirements-dev.txt`） | `black==26.5.1`、`httpx==0.28.1`、`pytest==9.1.1` | 不变 |
| retained upstream/downstream（`requirements-upstream.txt`） | 25 个 exact pins | 新增 `anthropic==1.3.0`、`backoff==2.2.1`、`openai==3.7.0`（`llm.py` legacy providers）与 `requests==2.34.2`（`tools/semantic_scholar.py`，transitional 标注随之迁移）；`tiktoken` 在 ticket 01 已删，本票确认全仓库零引用 |

声明文件 SHA-256：

- `requirements.txt`：`224bc587b44b33e6d7a7635b03f8b157bea627167edba73e05272c246685bb10`
- `requirements-dev.txt`：`68528a63263d3edc209368d0c63f3512c9ade0e568b82c6350361911c9653391`（不变）
- `requirements-upstream.txt`：`ceede1a2b01503606a5a16544b5cbf72eda22b3579d0e065cec53697e76c22da`

## VM-CONTRACT-024-01（终验）

内部模块精确 allowlist 收紧为 17 项（`ai_scientist` + `perform_ideation_temp_free` + `ideation` 包及 14 个子模块），`llm`/`tools`/`tools.base_tool`/`tools.semantic_scholar`/`utils.token_tracker` 移出；第三方 top-level allowlist 为空集。守卫继续 fail-closed：新增内部模块、第三方 top-level、无法解析模块、`__import__`/`importlib.import_module` 动态入口都会打红单一 closure snapshot assertion。TDD 红灯实证：先在旧代码上把清单改到目标态，两契约测试如预期失败，代码收缩后转绿。

CLI baseline：`--help` exit `0`、stderr 0 字节、stdout SHA-256 `838a69a4598b2711b3e52cd090c944a20b6862938814196bb41c3042d3d4a87f`（子命令面收缩为 `new-run/resume/validate/export/evaluation` 后的新基准）。

## VM-ENV-01（阻断，通过）

环境：CPython 3.13.7、macOS 26.6.2 arm64、uv 0.12.4、binary distributions only。临时 venv 路径与 host-specific 目录未写入证据。

可复现命令（`<venv>` 为新的临时目录）：

```bash
uv venv --python 3.13 <venv>
uv pip install --python <venv>/bin/python --only-binary :all: \
  -r requirements.txt -r requirements-dev.txt
<venv>/bin/python -m pytest -q
COLUMNS=80 <venv>/bin/python ai_scientist/perform_ideation_temp_free.py --help
<venv>/bin/python -m compileall -q ai_scientist
```

结果（终态代码，commit `391eac5`）：

- exact environment lock：[legacy-contract-macos-arm64-py313.lock.txt](legacy-contract-macos-arm64-py313.lock.txt)，18 行（纯 dev 传递闭包：black/httpx/pytest 及其依赖，零 runtime 包），SHA-256 `582eb60960ce2eb92a9cadc364214fdf6e9fe0e1036ddbef7536e249c916fd1f`。
- 全量 pytest：`628 passed`（含 `test_run_preflight.py` 经真实 pty 驱动 new-run CLI 的 preflight 级 smoke，在 clean venv 内通过）。
- CLI：exit `0`；stdout SHA-256 与基准一致；stderr 为空。
- compileall：exit `0`。
- runtime-only 复验：另一个零安装的裸 venv（`uv pip freeze` 0 行）运行同一 CLI，stdout hash 与 stderr 结果逐字节一致——stdlib-only 运行面的最强证据。

## VM-ENV-02（兼容性候选，记录不扩大承诺）

| 解释器 | 结果 | 备注 |
|---|---|---|
| CPython 3.12.13（clean venv） | 627 passed / 1 failed | 唯一失败为 `test_ideation_cli_help_matches_compatible_baseline`：3.12 argparse 在 `COLUMNS=80` 下把 usage 行折成两行，stdout bytes 与 3.13 基准不同；功能行为无差异，基准 hash 按合同 pin 在 3.13 reference |
| CPython 3.14.6（clean venv） | 628 passed | CLI stdout hash 与基准逐字节一致 |
| CPython 3.14.6（ambient 开发环境） | 628 passed | 日常开发面 |

## VM-ENV-03 / VM-ENV-04

- VM-ENV-03：入口闭包与依赖合同不含 `torch`、dense model 或任何 accelerator 包；全部验证在 Mac CPU 环境完成，accelerator 缺席不影响任何行。
- VM-ENV-04：主开发平台 macOS arm64 全量通过（上表与 VM-ENV-01）；平台锁见 VM-ENV-01 的 lock 文件。本机无第二个操作系统平台，其余平台候选无新增记录。

## Validation Matrix 全量已实现行重跑

全量 628 项 pytest 即全部已实现矩阵行的载体（unit/contract/integration/replay/leakage/isolation/fault-injection/qualitative 各层均在 `tests/` 内），在 3.13 clean venv 与 ambient 3.14.6 各跑一遍，均 628 passed、零失败、零绕过。

## 失败与修复记录

- **入口在 Python ≤3.13 下无法 import（本票发现并修复的真实缺陷）**：`run_new_run` 等 7 处签名注解引用 `Path`，但 `Path` 只在 `__main__` 块引入；3.12/3.13 eager 注解求值直接 `NameError`（3.12 打桩实测复现），ambient 3.14 的 PEP 649 惰性注解掩盖了它。修复为顶层 `from pathlib import Path`，并删除六个函数内 `Path as _Path` 别名；3.13.7 与 3.12.13 实测 import 通过。
- **操作中误删 `_run_resume` 的 ideation import**：编辑事故，当场发现、当场修回，全量回归证实无残留。
- **双轴 handoff review（`cd25f36...c359b42`，64 commits/98 files）发现并已修复**：
  - `DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL_ID`/`DEFAULT_REASONING_EFFORT`/`MAX_ATTEMPTS_PER_OPERATION` 在 `admission.py` 与 `deepseek.py` 双定义、可静默漂移 → 单源化到 `contract.py`（两模块经 import 复用，测试 import 路径不变）；
  - `IDEATION_EXECUTE` 环境变量是未在任何合同/文档登记的隐藏付费执行开关（024 只准七个 CLI 参数）→ 移除，执行只经注入 adapter 的受测缝，真实 provider transport 接线留作 Canary 阶段显式决策；
  - `controller.py` 模块 docstring 未覆盖 ticket 10 resume 职责 → 补记；
  - CLI baseline 测试残留 `S2_API_KEY` 注入（Semantic Scholar 已出闭包）→ 移除；
  - AGENTS.md 入口描述补齐 `validate`/`export`/`evaluation` 子命令。
  - 非阻断判断项（corpus/workshop 模块命名惯例、跨模块 `_private` 引用、provenance 默认值 `"codex"` 等）按最小改动纪律记录不处理，留待 Robert 决策。

## Trust boundary

依赖安装阶段访问 package index（binary-only）；所有 pytest 与 CLI smoke 均为 zero-model、zero-cost、zero-network（stub/pty 驱动），未调用 DeepSeek、Semantic Scholar 或任何 provider。环境 lock 与本文档不含 credential、绝对路径、host identity、prompt、response、Target Paper 或 idea 内容。仓库未配置 formal type checker；验证执行 compileall、pytest、import-contract 与 Black，不虚构 typecheck 结果。

## Hash 索引

| 项 | SHA-256 / 值 |
|---|---|
| implementation-map 基线 commit | `cd25f36bf9ee464ac99f33769a42fed63e921394` |
| 本票实现 commit | `c359b42da1a877e08fd41a68e02b9a21dc047714` |
| review 修复 commit | `391eac557e26dbd8b7e5c8651a206829e79505d5` |
| `requirements.txt` | `224bc587b44b33e6d7a7635b03f8b157bea627167edba73e05272c246685bb10` |
| `requirements-dev.txt` | `68528a63263d3edc209368d0c63f3512c9ade0e568b82c6350361911c9653391` |
| `requirements-upstream.txt` | `ceede1a2b01503606a5a16544b5cbf72eda22b3579d0e065cec53697e76c22da` |
| py313 环境 lock | `582eb60960ce2eb92a9cadc364214fdf6e9fe0e1036ddbef7536e249c916fd1f` |
| CLI `--help` stdout 基准 | `838a69a4598b2711b3e52cd090c944a20b6862938814196bb41c3042d3d4a87f` |
