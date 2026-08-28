# Minimal Ideation Runtime Audit

Audit for the Wayfinder ticket `Audit the minimal ideation runtime`: which imports, packages, commands, and platform assumptions are actually required to run preprocessing, ideation, and validation without installing or importing downstream dependencies.

Method: static import-graph trace from the ideation entry point, cross-checked against `requirements.txt`, then an empirical import test in an isolated `uv` venv (Python 3.11.15) containing only the five candidate packages. The venv was deleted after verification.

## Answer

The current ideation path (`ai_scientist/perform_ideation_temp_free.py`) needs only the Python 3.11 standard library plus five third-party packages — `anthropic`, `backoff`, `openai`, `requests`, `tiktoken` — on a CPU-only machine. No downstream module (`treesearch/`, write-up, plotting, review, `vlm.py`, `ideas/*.py`) is imported transitively. However, `requirements.txt` does not describe this minimal set: it omits `requests`, forces dozens of downstream-only packages, and pins nothing.

## Verified minimal runtime

Entry command (from repo root; the script prepends the repo root to `sys.path` itself):

```bash
python ai_scientist/perform_ideation_temp_free.py \
  --model <one of AVAILABLE_LLMS> \
  --workshop-file <topic.md> \
  --max-num-generations N --num-reflections M
```

Import graph from the entry point:

- `perform_ideation_temp_free.py` → stdlib only + `ai_scientist.llm`, `ai_scientist.tools.semantic_scholar`, `ai_scientist.tools.base_tool`
- `ai_scientist/llm.py` → `anthropic`, `backoff`, `openai` (all three at module top level, so both vendor SDKs are mandatory even for a DeepSeek-only runtime) + `ai_scientist.utils.token_tracker`
- `ai_scientist/utils/token_tracker.py` → `tiktoken` (imported but never used; the tracker trusts API `usage` fields, and `get_response_from_llm` — the function ideation actually calls — is not even decorated)
- `ai_scientist/tools/semantic_scholar.py` → `requests`, `backoff`
- `ai_scientist/tools/base_tool.py` → stdlib only
- All `__init__.py` files are empty; nothing else is pulled in.

Empirical verification (2026-08-29): in a fresh Python 3.11.15 venv with exactly `anthropic openai backoff requests tiktoken` installed and `torch`, `numpy`, `transformers`, `datasets`, `rich`, `omegaconf`, `igraph`, `pymupdf`, `pandas`, `matplotlib` confirmed absent, `import ai_scientist.perform_ideation_temp_free` succeeds and `--help` runs. The only import-time side effect is the `SemanticScholarSearchTool` instantiation warning about a missing `S2_API_KEY` (no network at import).

## Downstream-only modules and their packages

Nothing below is reachable from the ideation entry point:

- `launch_scientist_bfts.py` → `torch` (not in `requirements.txt` at all; conda-installed per README), plus the whole tree below.
- `ai_scientist/treesearch/` → `rich`, `dataclasses-json`, `python-igraph`, `humanize`, `funcy`, `jsonschema`, `omegaconf`, `coolname`, `shutup`, `black`, `genson`, `tqdm` (lazy), `numpy`, plus undeclared `pandas` (`utils/data_preview.py`) and `PyYAML` (`bfts_utils.py`).
- `perform_writeup.py` / `perform_icbinb_writeup.py` / `perform_plotting.py` / `perform_llm_review.py` / `perform_vlm_review.py` / `vlm.py` → `pypdf`, `pymupdf` (itself undeclared; arrives via `pymupdf4llm`), `pymupdf4llm`, `numpy`, `PIL` (undeclared), and `subprocess` calls to LaTeX/poppler/chktex system tools.
- `ai_scientist/ideas/*.py` (example experiment payloads) → `torch`, `torchvision`, `transformers`, `datasets`, `huggingface_hub`, `PIL`, `numpy`.

## `requirements.txt` gaps (facts, not decisions)

- Missing but imported: `requests` (on the ideation path — the only missing package that blocks ideation in a minimal install), `pandas`, `PyYAML`, `Pillow`, `pymupdf` (all downstream).
- Declared but never imported by repo code: `wandb`, `boto3`, `botocore` (Bedrock support comes from the `anthropic[bedrock]` extra per README), `matplotlib`, `seaborn` (these two exist for LLM-generated downstream experiment code, not for repo modules).
- `black` is dual-use: a dev check (`python -m black --check ai_scientist`) and a downstream runtime import (`treesearch/utils/response.py`).
- No version is pinned anywhere; `torch` is absent by design (conda-only, GPU-oriented).

## Platform assumptions found on the ideation path

- **Python**: README and `AGENTS.md` prescribe 3.11; the ambient default interpreter on this machine is 3.14.6 and there is no `.python-version`/`pyproject.toml` marker, so the version contract exists only in docs.
- **CPU/OS**: the ideation path is pure Python; no CUDA, `subprocess`, `signal`, or `multiprocessing` (those live in treesearch and write-up). OS-agnostic.
- **Network at run time**: the LLM API endpoint and the Semantic Scholar API. This conflicts with the already-decided frozen-corpus boundary (`Freeze literature before ideation`): the `SearchSemanticScholar` tool on the entry path must be replaced by the Scoped Literature Retriever (`Define the scoped retriever contract`).
- **Environment variables**: provider keys selected by `--model` (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` implicitly via default client constructors, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `HUGGINGFACE_API_KEY`, `OLLAMA_API_KEY`, AWS vars for Bedrock), plus optional `S2_API_KEY`.
- **Working directory**: must run from the repo root as a script; the default `--workshop-file ideas/i_cant_believe_its_not_better.md` is relative.
- **State**: the output JSON is written next to the workshop file (`<workshop>.json`) and "resume" reloads that same file — there is no run identity or Run Isolation today (feeds `Define run identity and evidence layout` and `Define the safe ideation entry`).

## Facts later tickets depend on

- `DeepSeek-V4-Pro-0813` is absent from `AVAILABLE_LLMS` (47 entries, verified). The only existing DeepSeek route is `deepseek-coder-v2-0724` via an OpenAI-compatible client at `https://api.deepseek.com` with `DEEPSEEK_API_KEY`. Feeds `Choose the DeepSeek provider and version contract` and `Define the DeepSeek adapter contract`.
- `llm.py`'s top-level `anthropic`/`openai` imports force both SDKs into any minimal environment until the adapter contract reshapes this.
- The unused `tiktoken` import in `token_tracker.py` is a hard import-time requirement of the ideation path despite providing no functionality there.
- **Preprocessing**: no code exists for the interview dataset (`data/raw/` is ignored); there is nothing to audit beyond the dataset checks already logged.
- **Validation**: no idea-validation code exists. Current repo-level checks are `python -m compileall ai_scientist` and `python -m black --check ai_scientist`; `pytest` is planned but not yet a dependency (`tests/test_*.py` per `AGENTS.md`).

## Newly specifiable question

The audit makes one decision sharply statable that no open ticket covers: the dependency contract for the minimal runtime (what is declared, where, pinned or not, and how the undeclared/unused/downstream-only packages are handled). Captured as the new ticket `Define the minimal runtime dependency contract`.
