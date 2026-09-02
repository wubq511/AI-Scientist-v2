# Repository Guidelines

## Project Structure & Scope

`ai_scientist/` contains the Python package. Ideation starts in `perform_ideation_temp_free.py`; model adapters live in `llm.py`, and literature tools in `tools/`. `data/raw/` is the ignored interview dataset. `.agents/skills/` defines workflows; `work-logs/` is shared memory across agents and sessions. Treat `docs/task/` as private, ignored background.

The interview scope ends at workshop/topic preparation, target-scoped reference retrieval, idea generation, and validation. Never invoke `launch_scientist_bfts.py` or enter BFTS, experiments, plotting, write-up, or review workflows.

## Human-in-the-Loop Workflow

Before modifying code or starting a run, tell Robert the intended behavior, files, rationale, validation, and risks. Architecture, dataset semantics, model/API, retrieval, evaluation, and scope require his explicit approval before implementation.

Never lock a material technical approach from intuition alone. Define hypotheses, viable alternatives, comparison metrics, and failure cases; run the smallest fair comparative validation; then show Robert the evidence before selection. Optimize for observed effectiveness first. Among options meeting the evidence threshold, choose the simplest, lightest design. Record rejected alternatives, failures, and lessons. This validation stays inside ideation scope and is not a Downstream Experiment.

For every result, record why it is trustworthy. Before resuming, read relevant work logs. After a material change, decision, failure, or validation, use `record-session-progress`; use `daily-work-summary` at day end.

## Development & Validation Commands

This repository has no build step or automated test suite.

```bash
python -m pip install -r requirements.txt
python ai_scientist/perform_ideation_temp_free.py --help
python -m compileall ai_scientist
python -m black --check ai_scientist
```

Add deterministic `tests/test_*.py`; run `python -m pytest -q` after adding `pytest` as a development dependency. Fail closed on isolation, schema, metadata, and model errors. Never bypass failed checks.

## Coding Style & Naming

Target Python 3.13 as the reference minor, four-space indentation, and Black. Record the exact patch and per-platform dependency lock for evidence runs; treat 3.12/3.14 as compatibility candidates and 3.11 results as historical evidence unless a later approved contract changes this policy. Use `snake_case` for modules/functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep external services behind small boundaries; make provenance and validation explicit. Write Robert-facing documents (research reports, tracker bodies, work logs) in Chinese; code, identifiers, paths, commands, and commit messages stay English.

The ideation-only runtime must retain a portable CPU FP32 reference path. Optional inference acceleration may be added only after a scoped comparison proves a material end-to-end benefit, no observable payload drift or operator fallback, and acceptable dependency cost; no accelerator is required. Exclude accelerator-dependent runtime assumptions, GPU training, and downstream-only stacks. The root `README.md` retains upstream full-pipeline CUDA/Python 3.11 instructions and is not the runtime contract for this fork.

## Local-Ranking Execution Topology

Use Windows as the bulk evidence executor for local-ranking candidate matrices, local-scorer calibration, repeated replay, and formal local-scorer holdout evaluation. Copy immutable code/input/model bundles once, verify hashes, run from the Windows-local workspace, and return only evidence artifacts. Do not move these local-compute workloads to Mac merely because Windows is temporarily unavailable.

Use Mac as the controller for editing, protocol and input preparation, SSH orchestration, evidence review, ordinary single-run ranking, and authenticated calls to remote-provider judges/evaluators. Remote inference does not use Windows compute: keep API credentials on Mac, then send only immutable credential-free outputs to Windows for offline replay or verification. Follow the `windows-executor` skill for Windows connection, transfer, unpacking, offline verification, and cleanup. The frozen scorer must remain runnable on Mac and produce the same canonical payload as Windows; raw float equality and performance parity are not required. Run Mac cross-platform checks only when the scorer, model, dependency lock, or output semantics change—not for every bulk evidence run.

## Reproducibility, Commits & Pull Requests

For each model run, log the commit SHA, dataset hashes, target/reference counts, command, model/provider identifier, parameters, timestamps, output paths, validation results, failures, and output hashes where practical. Preserve raw logs; never expose secrets.

Create small, coherent commits that reveal the sequence. History uses imperative subjects and `add:`/`fix:` prefixes; prefer `feat: add target-reference index` or `test: prove cross-target isolation`. Each commit must be validated. Pull requests explain the problem, approved decisions, evidence, commands, failures/risks, linked issue when applicable, and confirm no downstream stages were entered.
