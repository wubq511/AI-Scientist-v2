"""Canary 24-run matrix, ordering, blinding, and spend ledger for Ticket 035.

Implements:
- 12 case-paired units, 24 serial Ideation Runs.
- Balanced execution order: exactly 6 high-first and 6 max-first pairs.
- Balanced blind A/B mapping: exactly 6 pairs where A=high, B=max, and 6 where A=max, B=high.
- Spend ledger initialization: hard cap 30.00 CNY, admission bound 7.08 CNY, actual spend 0.00 CNY.
- Credential-free runnable CLI commands.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .selection import SelectedCanaryCase


@dataclass(frozen=True)
class PlannedRun:
    run_index: int  # 1 to 24
    pair_index: int  # 1 to 12
    arm_position: int  # 1 or 2 within the pair
    case_id: str
    cluster: str
    reasoning_effort: str  # "high" or "max"
    max_tokens: int  # 32768
    num_reflections: int  # 3
    max_num_generations: int  # 1
    workshop_path: str
    workshop_sha256: str
    corpus_path: str
    corpus_sha256: str
    credential_free_command: str


@dataclass(frozen=True)
class BlindPairMapping:
    pair_index: int
    case_id: str
    cluster: str
    arm_a_effort: str  # "high" or "max"
    arm_b_effort: str  # "max" or "high"
    arm_a_run_index: int
    arm_b_run_index: int


def build_canary_matrix(
    selected_cases: tuple[SelectedCanaryCase, ...],
    selection_manifest_sha256: str,
    workspace_root: Path | None = None,
) -> tuple[tuple[PlannedRun, ...], tuple[BlindPairMapping, ...]]:
    if len(selected_cases) != 12:
        raise ValueError(f"Expected 12 cases, got {len(selected_cases)}")

    root = workspace_root or Path.cwd()

    # 1. Balanced execution order (6 high-first, 6 max-first)
    order_hashes: list[tuple[str, str]] = []
    for c in selected_cases:
        h = hashlib.sha256(
            f"{selection_manifest_sha256}|arm_order|{c.case_id}".encode()
        ).hexdigest()
        order_hashes.append((h, c.case_id))
    order_hashes.sort()

    high_first_cases = {case_id for _, case_id in order_hashes[:6]}

    runs: list[PlannedRun] = []
    pair_mappings: list[BlindPairMapping] = []

    # 2. Balanced blinding mapping (6 where A=high, 6 where A=max)
    blind_hashes: list[tuple[str, str]] = []
    for c in selected_cases:
        h = hashlib.sha256(
            f"{selection_manifest_sha256}|blind_mapping|{c.case_id}".encode()
        ).hexdigest()
        blind_hashes.append((h, c.case_id))
    blind_hashes.sort()

    a_is_high_cases = {case_id for _, case_id in blind_hashes[:6]}

    run_counter = 1
    for pair_idx, c in enumerate(selected_cases, start=1):
        c_id = c.case_id
        is_high_first = c_id in high_first_cases

        efforts = ("high", "max") if is_high_first else ("max", "high")

        run_idx_1 = run_counter
        run_idx_2 = run_counter + 1
        run_counter += 2

        workshop_rel = f"artifacts/ideation-inputs/workshops/{c_id}/attempts/attempt-001/resolution/{c_id}.md"
        corpus_rel = f"artifacts/ideation-inputs/corpora/{c_id}/corpus.json"

        # Lookup real hashes if the files exist
        w_file = root / workshop_rel
        c_file = root / corpus_rel
        w_sha = (
            hashlib.sha256(w_file.read_bytes()).hexdigest() if w_file.is_file() else ""
        )
        c_sha = (
            hashlib.sha256(c_file.read_bytes()).hexdigest() if c_file.is_file() else ""
        )

        # Run 1 in pair
        cmd1 = (
            f"python ai_scientist/perform_ideation_temp_free.py new-run "
            f"--case-id {c_id} --reasoning-effort {efforts[0]} --max-tokens 32768 "
            f"--workshop {workshop_rel} "
            f"{f'--workshop-sha256 {w_sha} ' if w_sha else ''}"
            f"--corpus {corpus_rel}"
            f"{f' --corpus-sha256 {c_sha}' if c_sha else ''} "
            f"--max-num-generations 1 --num-reflections 3"
        ).strip()
        runs.append(
            PlannedRun(
                run_index=run_idx_1,
                pair_index=pair_idx,
                arm_position=1,
                case_id=c_id,
                cluster=c.cluster,
                reasoning_effort=efforts[0],
                max_tokens=32768,
                num_reflections=3,
                max_num_generations=1,
                workshop_path=workshop_rel,
                workshop_sha256=w_sha,
                corpus_path=corpus_rel,
                corpus_sha256=c_sha,
                credential_free_command=cmd1,
            )
        )

        # Run 2 in pair
        cmd2 = (
            f"python ai_scientist/perform_ideation_temp_free.py new-run "
            f"--case-id {c_id} --reasoning-effort {efforts[1]} --max-tokens 32768 "
            f"--workshop {workshop_rel} "
            f"{f'--workshop-sha256 {w_sha} ' if w_sha else ''}"
            f"--corpus {corpus_rel}"
            f"{f' --corpus-sha256 {c_sha}' if c_sha else ''} "
            f"--max-num-generations 1 --num-reflections 3"
        ).strip()
        runs.append(
            PlannedRun(
                run_index=run_idx_2,
                pair_index=pair_idx,
                arm_position=2,
                case_id=c_id,
                cluster=c.cluster,
                reasoning_effort=efforts[1],
                max_tokens=32768,
                num_reflections=3,
                max_num_generations=1,
                workshop_path=workshop_rel,
                workshop_sha256=w_sha,
                corpus_path=corpus_rel,
                corpus_sha256=c_sha,
                credential_free_command=cmd2,
            )
        )

        # Blind mapping
        a_is_high = c_id in a_is_high_cases
        arm_a = "high" if a_is_high else "max"
        arm_b = "max" if a_is_high else "high"
        arm_a_run = run_idx_1 if efforts[0] == arm_a else run_idx_2
        arm_b_run = run_idx_2 if efforts[0] == arm_a else run_idx_1

        pair_mappings.append(
            BlindPairMapping(
                pair_index=pair_idx,
                case_id=c_id,
                cluster=c.cluster,
                arm_a_effort=arm_a,
                arm_b_effort=arm_b,
                arm_a_run_index=arm_a_run,
                arm_b_run_index=arm_b_run,
            )
        )

    return tuple(runs), tuple(pair_mappings)


def build_initial_spend_ledger(
    selection_manifest_sha256: str,
) -> dict[str, Any]:
    return {
        "budget_rules": {
            "aggregate_canary_hard_cap_cny": "30.00",
            "operating_forecast_cny": "3.36–6.72",
            "per_run_worst_case_admission_bound_cny": "7.08",
            "rule": "cumulative_actual_spend + next_run_worst_case_bound <= 30.00 CNY",
        },
        "completed_runs_count": 0,
        "current_actual_spend_cny": "0.00",
        "current_remaining_budget_cny": "30.00",
        "planned_runs_count": 24,
        "runs": [],
        "schema_version": "canary-spend-ledger-v1.0",
        "selection_manifest_sha256": selection_manifest_sha256,
        "status": "initialized",
    }


def materialize_comparison_artifacts(
    workspace_root: Path,
    selected_cases: tuple[SelectedCanaryCase, ...],
    selection_manifest_sha256: str,
    output_dir: Path,
) -> dict[str, str]:
    """Freeze and write the 24-run matrix, blind mapping, spend ledger, and commands."""
    import json
    from ai_scientist.ideation.canonical import canonical_json_bytes

    output_dir.mkdir(parents=True, exist_ok=True)
    runs, blind_pairs = build_canary_matrix(
        selected_cases, selection_manifest_sha256, workspace_root=workspace_root
    )

    # 1. run-matrix.json
    matrix_doc = {
        "schema_version": "canary-run-matrix-v1.0",
        "selection_manifest_sha256": selection_manifest_sha256,
        "planned_runs_count": len(runs),
        "pairs_count": len(blind_pairs),
        "high_first_pairs_count": sum(
            1 for p in range(len(blind_pairs)) if runs[p * 2].reasoning_effort == "high"
        ),
        "max_first_pairs_count": sum(
            1 for p in range(len(blind_pairs)) if runs[p * 2].reasoning_effort == "max"
        ),
        "runs": [
            {
                "run_index": r.run_index,
                "pair_index": r.pair_index,
                "arm_position": r.arm_position,
                "case_id": r.case_id,
                "cluster": r.cluster,
                "reasoning_effort": r.reasoning_effort,
                "max_tokens": r.max_tokens,
                "num_reflections": r.num_reflections,
                "max_num_generations": r.max_num_generations,
                "workshop": {
                    "path": r.workshop_path,
                    "sha256": r.workshop_sha256,
                },
                "corpus": {
                    "path": r.corpus_path,
                    "sha256": r.corpus_sha256,
                },
                "credential_free_command": r.credential_free_command,
            }
            for r in runs
        ],
    }
    matrix_bytes = canonical_json_bytes(matrix_doc)
    (output_dir / "run-matrix.json").write_bytes(matrix_bytes)

    # 2. blind-mapping.json
    blind_doc = {
        "schema_version": "canary-blind-mapping-v1.0",
        "selection_manifest_sha256": selection_manifest_sha256,
        "pairs_count": len(blind_pairs),
        "arm_a_is_high_count": sum(
            1 for bp in blind_pairs if bp.arm_a_effort == "high"
        ),
        "arm_a_is_max_count": sum(1 for bp in blind_pairs if bp.arm_a_effort == "max"),
        "pairs": [
            {
                "pair_index": bp.pair_index,
                "case_id": bp.case_id,
                "cluster": bp.cluster,
                "arm_a": {
                    "reasoning_effort": bp.arm_a_effort,
                    "planned_run_index": bp.arm_a_run_index,
                },
                "arm_b": {
                    "reasoning_effort": bp.arm_b_effort,
                    "planned_run_index": bp.arm_b_run_index,
                },
            }
            for bp in blind_pairs
        ],
    }
    blind_bytes = canonical_json_bytes(blind_doc)
    (output_dir / "blind-mapping.json").write_bytes(blind_bytes)

    # 3. spend-ledger.json
    ledger_doc = build_initial_spend_ledger(selection_manifest_sha256)
    ledger_bytes = canonical_json_bytes(ledger_doc)
    (output_dir / "spend-ledger.json").write_bytes(ledger_bytes)

    # 4. commands.txt
    commands_text = "\n".join(r.credential_free_command for r in runs) + "\n"
    (output_dir / "commands.txt").write_text(commands_text, encoding="utf-8")

    return {
        "run-matrix.json": hashlib.sha256(matrix_bytes).hexdigest(),
        "blind-mapping.json": hashlib.sha256(blind_bytes).hexdigest(),
        "spend-ledger.json": hashlib.sha256(ledger_bytes).hexdigest(),
        "commands.txt": hashlib.sha256(commands_text.encode("utf-8")).hexdigest(),
    }
