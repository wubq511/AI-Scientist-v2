# 可测试 Ideation 地基验证证据

日期：2026-09-03  
Implementation ticket：[Establish the testable ideation foundation](../wayfinder/ideation-implementation/tickets/01-establish-the-testable-ideation-foundation.md)  
验证矩阵：`VM-CONTRACT-024-01`、`VM-ENV-01`

## 结论

Python 3.13.7 / macOS arm64 的全新环境能够只安装精确声明的 runtime 与 development 依赖，运行全部 258 项 pytest，并在不安装 `tiktoken`、retained upstream/downstream 包或 accelerator stack 的情况下执行 ideation CLI baseline smoke。修改前后 `--help` 的 exit code、stdout bytes 与 stderr bytes 一致；本票未调用模型、未产生模型费用、未进入 downstream。

## 固定实现边界

- 基线 commit：`cd25f36bf9ee464ac99f33769a42fed63e921394`（`add: map ideation implementation tickets`）。
- 实现 commits：`9c29ec0 add: establish testable ideation foundation`、`a6c6679 fix: remove dependency file whitespace`。
- runtime 行为改动：无；唯一 runtime 源码变化是删除 `ai_scientist/utils/token_tracker.py` 未使用的 `tiktoken` import，并由 Black 格式化同文件两处既有长条件。
- public behavior seam：`python ai_scientist/perform_ideation_temp_free.py --help`。
- import contract seam：从 `ai_scientist.perform_ideation_temp_free` 开始、只递归仓库内 `ai_scientist.*` 源码的静态传递 import closure。第三方 distribution 的自身传递依赖由环境 lock 记录，不冒充项目源码的 top-level allowlist。

## 依赖合同

当前日期从 package index 解析出的 stable direct versions 先经过 Python 3.13 resolver，再以 binary-only clean install、全量 pytest 与 CLI hash 为接受标准。历史 runtime 审计只记录了五个包名，没有留下可复用的精确版本 lock；继续使用 unpinned 声明会使同一验证命令随时间漂移。

| 类别 | 精确 direct pin | 当前使用方/理由 |
|---|---|---|
| runtime | `anthropic==1.3.0` | `ai_scientist/llm.py` 顶层 import；后续 adapter 收缩前仍在入口 closure |
| runtime | `backoff==2.2.1` | `ai_scientist/llm.py` 与 `ai_scientist/tools/semantic_scholar.py` |
| runtime | `openai==3.7.0` | `ai_scientist/llm.py` 顶层 import；后续 adapter 收缩前仍在入口 closure |
| runtime | `requests==2.34.2` | `semantic_scholar.py` transitional 使用方；该 legacy tool 被替换时一起删除 |
| development | `black==26.5.1` | 格式验证；不进入 runtime-only 环境 |
| development | `httpx==0.28.1` | 既有 local-ranking prototype 测试与 zero-network transport stubs |
| development | `pytest==9.1.1` | 自动化验证入口 |
| retained upstream/downstream | 见 `requirements-upstream.txt` 的 21 个 exact pins | 保留代码与上游工作流，不是 fork runtime 合同 |

声明文件 SHA-256：

- `requirements.txt`：`3b031a68c7bd8c4f498b8182183b10b866a2aac46fd8c77bda85a3200b0637ac`
- `requirements-dev.txt`：`68528a63263d3edc209368d0c63f3512c9ade0e568b82c6350361911c9653391`
- `requirements-upstream.txt`：`955863573c9474233f7f8a54a5ad9a77338eee439e8551017284524716cb7219`

## VM-CONTRACT-024-01

内部模块精确 allowlist：

```text
ai_scientist
ai_scientist.llm
ai_scientist.perform_ideation_temp_free
ai_scientist.tools
ai_scientist.tools.base_tool
ai_scientist.tools.semantic_scholar
ai_scientist.utils.token_tracker
```

第三方 top-level 精确 allowlist：

```text
anthropic
backoff
openai
requests
```

守卫会扫描每个可达内部模块及其 package initializer；新增内部模块、第三方 top-level、无法解析的内部模块、`__import__` 或 `importlib.import_module` 动态入口都会使单一 closure snapshot assertion 失败。TDD 红灯实证为删除代码前实际集合多出 `tiktoken`；删除唯一未使用 import 后转绿。

## VM-ENV-01

环境：CPython 3.13.7、macOS 26.6.2 arm64、uv 0.12.4、binary distributions only。临时 venv 路径与 host-specific 目录未写入证据。

可复现命令（`<venv>` 为新的临时目录）：

```bash
uv venv --python 3.13 <venv>
uv pip install --python <venv>/bin/python --only-binary :all: \
  -r requirements.txt -r requirements-dev.txt
<venv>/bin/python -m pytest -q
S2_API_KEY=baseline-smoke COLUMNS=80 \
  <venv>/bin/python ai_scientist/perform_ideation_temp_free.py --help
<venv>/bin/python -m compileall -q ai_scientist
```

结果：

- exact environment lock：[ideation-foundation-macos-arm64-py313.lock.txt](ideation-foundation-macos-arm64-py313.lock.txt)，34 行，SHA-256 `8b43ebd5480a02a1613a44f65a6bd27ba94e8aa24b9e9eb8fa48cc82d75e26f0`；与 clean venv 的 `uv pip freeze` byte-for-byte 一致。
- 全量 pytest：`258 passed in 11.53s`。
- CLI：exit `0`；stdout SHA-256 `362c88d203c7b1e8aaa0e18098310b778acfd58aa76af0f3f7ff5c63689f1bf1`；stderr 为空。修改前 Python 3.13.7 baseline 的三项值完全相同。
- compileall：exit `0`。retained `perform_icbinb_writeup.py` 报 2 条既有 invalid escape `SyntaxWarning`，不在 ideation import closure，也未被隐藏。
- runtime-only 复验：另一个 clean venv 只安装 `requirements.txt`，共 21 个 direct/transitive distributions；`black`、`httpx`、`pytest`、`tiktoken` 均不存在，CLI 仍得到相同 hash 与空 stderr。
- CPU reference：上述依赖与入口 closure 不含 `torch`、dense model 或 accelerator 包；smoke 在 Mac CPU 环境完成。

## 失败与修复记录

- ambient Python 3.14.6 在安装合同依赖前执行 CLI，因旧 `tiktoken` import 返回 `ModuleNotFoundError`；这不是合规环境结果，但直接暴露了 [Define the minimal runtime dependency contract](../wayfinder/ideation-pipeline/tickets/034-define-the-minimal-runtime-dependency-contract.md) 记录的伪依赖。
- 最初无参数运行 pytest 会递归收集 ignored `artifacts/` 内的 evidence repo copy，产生 10 个同名模块 import mismatch；新增 `pytest.ini` 的 `testpaths = tests` 后，同一无参数命令稳定收集 canonical tests，258 项全绿。
- `uv pip compile ... -o /dev/null` 已完成依赖解析，但 uv 尝试在 `/dev` 原子创建临时文件时返回 `Operation not permitted`；正式证据改用真正 clean venv 的 binary-only install 与 freeze，不把该诊断命令记为 pass。
- repo-wide `black --check ai_scientist` 在本票前已有 15 个格式失败；格式化本票触及的 `token_tracker.py` 后仍有 14 个 retained legacy/downstream 文件不合规。本票新增/触及的 4 个 Python 文件均通过 Black。本票没有用 exclude 掩盖失败，也没有把无关 downstream 格式债务扩成大面积 diff。

## Trust boundary

依赖下载阶段访问 package index；所有 pytest 与 CLI smoke 均为 zero-model、zero-cost，且未调用 Semantic Scholar 或任何 provider。环境 lock 不含 credential、绝对路径、host identity、prompt、response、Target Paper 或 idea 内容。当前仓库没有配置 formal type checker；本票执行 compileall、pytest、import-contract 与 Black，不虚构 typecheck 结果。

## Code review

固定点 `cd25f36` 的首次双轴 review 结果：Standards 轴 3 项、Spec 轴 1 项；最严重问题均为 exact environment lock、命令、pass/fail 与 commit evidence 尚未进入已提交 diff。其余问题为 session commit 占位未回填及 work log ticket 引用未链接；没有 scope creep、实现语义错误或 baseline code smell。本报告、相邻 lock、ticket evidence 链接与 session log 回填共同处理这些发现；修复后复核结果随最终 session evidence 记录。
