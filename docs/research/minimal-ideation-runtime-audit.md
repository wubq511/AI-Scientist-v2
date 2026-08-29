# 最小 Ideation Runtime 审计

> Policy note（2026-08-30）：本文记录的 Python 3.11.15/CPU-only 环境是一次历史兼容性 test cell，用来证明现有 import path 不需要 downstream/GPU stack；它不构成当前 reference minor 或永久 accelerator ban。当前治理 policy 是 Python 3.13 reference minor + mandatory CPU FP32 reference path + evidence-gated optional inference acceleration，详见 [local ranking runtime 调研](local-ranking-runtime-and-dense-model.md)。

对应 Wayfinder ticket `Audit the minimal ideation runtime`：在不安装、不导入 downstream 依赖的前提下，实际运行 preprocessing、ideation 和 validation 需要哪些 import、包、命令和平台假设。

方法：从 ideation 入口静态追踪完整 import 图，与 `requirements.txt` 交叉核对，再用隔离的 uv venv（Python 3.11.15，只装 5 个候选包）做实证导入验证。验证后 venv 已删除。

## 结论

当前 ideation 路径（`ai_scientist/perform_ideation_temp_free.py`）已在 CPU-only Python 3.11 test cell 中证明只需要标准库加五个第三方包——`anthropic`、`backoff`、`openai`、`requests`、`tiktoken`。任何 downstream 模块（`treesearch/`、write-up、plotting、review、`vlm.py`、`ideas/*.py`）都不会被传递导入。但 `requirements.txt` 并不描述这个最小集合：它漏掉了 `requests`，强制装了几十个 downstream-only 的包，且没有任何版本锁定。

## 已验证的最小 runtime

入口命令（从仓库根目录运行；脚本自己会先把仓库根目录加入 `sys.path`）：

```bash
python ai_scientist/perform_ideation_temp_free.py \
  --model <AVAILABLE_LLMS 之一> \
  --workshop-file <topic.md> \
  --max-num-generations N --num-reflections M
```

从入口出发的 import 图：

- `perform_ideation_temp_free.py` → 仅标准库 + `ai_scientist.llm`、`ai_scientist.tools.semantic_scholar`、`ai_scientist.tools.base_tool`
- `ai_scientist/llm.py` → 顶层 import `anthropic`、`backoff`、`openai`（三个都在模块顶层，所以即使只用 DeepSeek，两家厂商 SDK 也都是必装）+ `ai_scientist.utils.token_tracker`
- `ai_scientist/utils/token_tracker.py` → `tiktoken`（import 了但从未使用；tracker 信任 API 返回的 `usage` 字段，而 ideation 实际调用的 `get_response_from_llm` 甚至没有挂这个装饰器）
- `ai_scientist/tools/semantic_scholar.py` → `requests`、`backoff`
- `ai_scientist/tools/base_tool.py` → 仅标准库
- 所有 `__init__.py` 均为空文件，没有其他传递导入。

实证验证（2026-08-29）：在全新的 Python 3.11.15 venv 中只安装 `anthropic openai backoff requests tiktoken`，并确认 `torch`、`numpy`、`transformers`、`datasets`、`rich`、`omegaconf`、`igraph`、`pymupdf`、`pandas`、`matplotlib` 全部缺失，此时 `import ai_scientist.perform_ideation_temp_free` 成功，`--help` 正常运行。唯一的 import 时副作用是 `SemanticScholarSearchTool` 实例化时对缺失 `S2_API_KEY` 的 warning（import 阶段无网络请求）。

## downstream-only 模块及其依赖

以下模块从 ideation 入口均不可达：

- `launch_scientist_bfts.py` → `torch`（根本不在 `requirements.txt` 里，按 README 用 conda 安装），外加下面整棵树。
- `ai_scientist/treesearch/` → `rich`、`dataclasses-json`、`python-igraph`、`humanize`、`funcy`、`jsonschema`、`omegaconf`、`coolname`、`shutup`、`black`、`genson`、`tqdm`（惰性 import）、`numpy`，外加未声明的 `pandas`（`utils/data_preview.py`）和 `PyYAML`（`bfts_utils.py`）。
- `perform_writeup.py` / `perform_icbinb_writeup.py` / `perform_plotting.py` / `perform_llm_review.py` / `perform_vlm_review.py` / `vlm.py` → `pypdf`、`pymupdf`（本身未声明，随 `pymupdf4llm` 传入）、`pymupdf4llm`、`numpy`、`PIL`（未声明），以及通过 `subprocess` 调用 LaTeX/poppler/chktex 系统工具。
- `ai_scientist/ideas/*.py`（示例 experiment 代码）→ `torch`、`torchvision`、`transformers`、`datasets`、`huggingface_hub`、`PIL`、`numpy`。

## `requirements.txt` 的偏差（事实记录，非决策）

- 被 import 但未声明：`requests`（在 ideation 路径上——这是 minimal 安装下唯一会直接卡死 ideation 的缺失包）、`pandas`、`PyYAML`、`Pillow`、`pymupdf`（均为 downstream）。
- 已声明但仓库代码从未 import：`wandb`、`boto3`、`botocore`（Bedrock 支持按 README 走 `anthropic[bedrock]` extra）、`matplotlib`、`seaborn`（这两个是给 LLM 生成的 downstream experiment 代码用的，不是仓库模块）。
- `black` 有双重身份：开发检查工具（`python -m black --check ai_scientist`）兼 downstream 运行时 import（`treesearch/utils/response.py`）。
- 全部依赖无版本锁定；`torch` 有意缺席（conda-only，面向 GPU）。

## ideation 路径上的平台假设

- **Python（审计时事实）**：当时 README 和 `AGENTS.md` 约定 3.11；本机 ambient 默认解释器是 3.14.6，且仓库没有 `.python-version`/`pyproject.toml` 标记。`AGENTS.md` 已于 2026-08-30 将新 reference minor 改为 3.13；本条保留原始审计语境。
- **CPU/OS**：ideation 路径是纯 Python；不涉及 CUDA、`subprocess`、`signal`、`multiprocessing`（那些都在 treesearch 和 write-up 里）。与 OS 无关。
- **运行时网络**：LLM API endpoint 和 Semantic Scholar API。这与已决策的 frozen-corpus 边界（`Freeze literature before ideation`）冲突：入口路径上的 `SearchSemanticScholar` 工具必须替换为 Scoped Literature Retriever（见 `Define the scoped retriever contract`）。
- **环境变量**：按 `--model` 选择 provider key（`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` 由默认 client 构造器隐式读取，另有 `DEEPSEEK_API_KEY`、`GEMINI_API_KEY`、`OPENROUTER_API_KEY`、`HUGGINGFACE_API_KEY`、`OLLAMA_API_KEY`、Bedrock 的 AWS 变量），外加可选的 `S2_API_KEY`。
- **工作目录**：必须从仓库根目录以脚本方式运行；默认 `--workshop-file ideas/i_cant_believe_its_not_better.md` 是相对路径。
- **状态**：输出 JSON 写在 workshop 文件旁边（`<workshop>.json`），"resume" 就是重读同一个文件——目前不存在 run identity 和 Run Isolation（输入给 `Define run identity and evidence layout` 与 `Define the safe ideation entry`）。

## 后续 tickets 依赖的事实

- `DeepSeek-V4-Pro-0813` 不在 `AVAILABLE_LLMS` 中（共 47 个，已验证）。现有的唯一 DeepSeek 通道是 `deepseek-coder-v2-0724`，走 OpenAI 兼容 client 指向 `https://api.deepseek.com`，用 `DEEPSEEK_API_KEY`。输入给 `Choose the DeepSeek provider and version contract` 和 `Define the DeepSeek adapter contract`。
- `llm.py` 顶层的 `anthropic`/`openai` import 在 adapter contract 重塑之前，会强制把两家 SDK 都塞进任何 minimal 环境。
- `token_tracker.py` 里未使用的 `tiktoken` import 是 ideation 路径的硬性 import 时依赖，尽管它在那里不提供任何功能。
- **Preprocessing**：面试数据集（`data/raw/`，已 ignore）尚无任何预处理代码；除已记录的数据集检查外没有可审计的对象。
- **Validation**：尚无任何 idea 校验代码。当前仓库级检查是 `python -m compileall ai_scientist` 和 `python -m black --check ai_scientist`；`pytest` 在计划中但尚未成为依赖（`AGENTS.md` 约定的 `tests/test_*.py`）。

## 新浮现的可精确陈述的问题

审计使一个此前没有 open ticket 覆盖的决策变得可以精确陈述：minimal runtime 的依赖契约（声明什么、声明在哪、是否锁定版本、undeclared/unused/downstream-only 的包如何处理）。已建成新 ticket `Define the minimal runtime dependency contract`。
