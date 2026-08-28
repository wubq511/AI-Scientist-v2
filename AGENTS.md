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

Target Python 3.11, four-space indentation, and Black. Use `snake_case` for modules/functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep external services behind small boundaries; make provenance and validation explicit.

## Reproducibility, Commits & Pull Requests

For each model run, log the commit SHA, dataset hashes, target/reference counts, command, model/provider identifier, parameters, timestamps, output paths, validation results, failures, and output hashes where practical. Preserve raw logs; never expose secrets.

Create small, coherent commits that reveal the sequence. History uses imperative subjects and `add:`/`fix:` prefixes; prefer `feat: add target-reference index` or `test: prove cross-target isolation`. Each commit must be validated. Pull requests explain the problem, approved decisions, evidence, commands, failures/risks, linked issue when applicable, and confirm no downstream stages were entered.
