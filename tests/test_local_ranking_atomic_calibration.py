from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.atomic_calibration import aggregate, evaluate_progress
from prototypes.local_ranking.atomic_judge import (
    ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION,
)
from prototypes.local_ranking.canonical import canonical_json_bytes


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    return path


def _trace(
    *, replicate_id: str, orientation: int, unstable: int = 0, all_tie: bool = False
) -> dict:
    judgments = []
    for index in range(24):
        if all_tie:
            winner = "tie"
        elif orientation == 1:
            winner = "left"
        else:
            winner = "left" if index < unstable else "right"
        judgments.append({"item_id": f"item-{index:02d}", "winner": winner})
    return {
        "attempt_summary": {
            "first_attempt_valid_count": 24,
            "invalid_attempt_count": 0,
            "retried_call_count": 0,
            "total_physical_attempts": 24,
        },
        "evaluator": {
            "harness": "opencode-go-chat-completions",
            "model_alias": "opencode-go/deepseek-v4-pro",
            "provider": "opencode-go",
            "reasoning_effort": "high",
        },
        "invalid_attempts_by_error": {},
        "judgments": judgments,
        "orientation": orientation,
        "replicate_id": replicate_id,
        "schema_version": ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION,
        "selected_attempts": [
            {
                "attempt_sha256s": [f"{index:064x}"],
                "call_id": f"call-{index + 1:03d}",
                "selected_attempt_number": 1,
            }
            for index in range(24)
        ],
        "source_bundle_file_sha256": str(orientation) * 64,
        "source_bundle_self_sha256": chr(96 + orientation) * 64,
        "status": "pass",
    }


def _replicates(
    tmp_path: Path,
    unstable_counts: tuple[int, int, int],
    *,
    all_tie_replicate: int | None = None,
) -> list[dict[str, Path | str]]:
    result = []
    for index, unstable in enumerate(unstable_counts, start=1):
        replicate_id = f"r{index}"
        result.append(
            {
                "orientation_1_trace": _write(
                    tmp_path / replicate_id / "o1.json",
                    _trace(
                        replicate_id=replicate_id,
                        orientation=1,
                        all_tie=index == all_tie_replicate,
                    ),
                ),
                "orientation_2_trace": _write(
                    tmp_path / replicate_id / "o2.json",
                    _trace(
                        replicate_id=replicate_id,
                        orientation=2,
                        unstable=unstable,
                        all_tie=index == all_tie_replicate,
                    ),
                ),
                "replicate_id": replicate_id,
            }
        )
    return result


def test_atomic_profile_passes_22_24_24_without_redundant_gate(
    tmp_path: Path,
) -> None:
    result = aggregate(
        replicates=_replicates(tmp_path, (2, 0, 0)),
        output_path=tmp_path / "result.json",
    )

    assert result["status"] == "pass"
    assert result["pooled_stable_count"] == 70
    assert set(result["gates"]) == {
        "all_replicates_directional",
        "all_replicates_stable_at_or_above_22",
        "pooled_stable_at_or_above_69_of_72",
    }
    assert all(result["gates"].values())


@pytest.mark.parametrize("unstable_counts", [(2, 1, 1), (3, 0, 0)])
def test_atomic_profile_fails_only_direct_stability_gates(
    tmp_path: Path, unstable_counts: tuple[int, int, int]
) -> None:
    result = aggregate(
        replicates=_replicates(tmp_path, unstable_counts),
        output_path=tmp_path / "result.json",
    )

    assert result["status"] == "fail"


def test_atomic_profile_rejects_all_tie_degeneracy(tmp_path: Path) -> None:
    result = aggregate(
        replicates=_replicates(tmp_path, (0, 0, 0), all_tie_replicate=2),
        output_path=tmp_path / "result.json",
    )

    assert result["status"] == "fail"
    assert result["gates"]["all_replicates_directional"] is False


def test_first_attempt_validity_is_reported_but_not_an_admission_gate(
    tmp_path: Path,
) -> None:
    replicates = _replicates(tmp_path, (0, 0, 0))
    trace_path = replicates[0]["orientation_1_trace"]
    assert isinstance(trace_path, Path)
    trace = json.loads(trace_path.read_text())
    trace["attempt_summary"] = {
        "first_attempt_valid_count": 23,
        "invalid_attempt_count": 1,
        "retried_call_count": 1,
        "total_physical_attempts": 25,
    }
    trace["invalid_attempts_by_error"] = {"INVALID_ATOMIC_RESPONSE": 1}
    trace["selected_attempts"][0] = {
        "attempt_sha256s": ["a" * 64, "b" * 64],
        "call_id": "call-001",
        "selected_attempt_number": 2,
    }
    _write(trace_path, trace)

    result = aggregate(
        replicates=replicates,
        output_path=tmp_path / "result.json",
    )

    assert result["status"] == "pass"
    assert result["attempt_diagnostics"]["retried_call_count"] == 1
    assert result["attempt_diagnostics"]["first_attempt_valid_count"] == 143


@pytest.mark.parametrize(
    ("stable_counts", "decision"),
    [
        ((22,), "continue"),
        ((21,), "stop_per_replicate_impossible"),
        ((22, 22), "stop_pooled_impossible"),
        ((22, 24), "continue"),
        ((22, 24, 24), "profile_qualified"),
    ],
)
def test_progress_stops_only_when_frozen_gates_are_impossible(
    stable_counts: tuple[int, ...], decision: str
) -> None:
    assert evaluate_progress(list(stable_counts))["decision"] == decision
