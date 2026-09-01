from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .atomic_judge import (
    ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION,
    EXPECTED_ITEM_COUNT,
)
from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail

ATOMIC_CALIBRATION_SCHEMA_VERSION = "local-ranking-atomic-calibration-v2.0"
EXPECTED_REPLICATE_COUNT = 3
MIN_REPLICATE_STABILITY = 22
MIN_POOLED_STABILITY = 69
VALID_WINNERS = {"left", "right", "tie", "both_bad"}


def _read_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_ARTIFACT", f"{label} is unreadable JSON", error=str(exc))
    if not isinstance(value, dict):
        fail("INVALID_ARTIFACT", f"{label} must be an object")
    if canonical_json_bytes(value) != data:
        fail("NON_CANONICAL_INPUT", f"{label} must use canonical JSON bytes")
    return value, data


def _normalize_mirrored_winner(winner: str) -> str:
    return {"left": "right", "right": "left"}.get(winner, winner)


def _winner_index(
    trace: dict[str, Any], *, replicate_id: str, orientation: int
) -> tuple[dict[str, str], set[str]]:
    expected_keys = {
        "attempt_summary",
        "evaluator",
        "invalid_attempts_by_error",
        "judgments",
        "orientation",
        "replicate_id",
        "schema_version",
        "selected_attempts",
        "source_bundle_file_sha256",
        "source_bundle_self_sha256",
        "status",
    }
    if (
        set(trace) != expected_keys
        or trace.get("schema_version") != ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION
        or trace.get("status") != "pass"
        or trace.get("orientation") != orientation
        or trace.get("replicate_id") != replicate_id
        or not isinstance(trace.get("evaluator"), dict)
    ):
        fail(
            "INVALID_ATOMIC_TRACE",
            "Atomic trace identity or closed schema is invalid",
            replicate_id=replicate_id,
            orientation=orientation,
        )
    attempt_summary = trace.get("attempt_summary")
    if not isinstance(attempt_summary, dict) or set(attempt_summary) != {
        "first_attempt_valid_count",
        "invalid_attempt_count",
        "retried_call_count",
        "total_physical_attempts",
    }:
        fail("INVALID_ATOMIC_TRACE", "Atomic attempt summary is invalid")
    first_valid = attempt_summary.get("first_attempt_valid_count")
    retried = attempt_summary.get("retried_call_count")
    invalid = attempt_summary.get("invalid_attempt_count")
    physical = attempt_summary.get("total_physical_attempts")
    if (
        any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (first_valid, retried, invalid, physical)
        )
        or first_valid + retried != EXPECTED_ITEM_COUNT
        or invalid != retried
        or physical != EXPECTED_ITEM_COUNT + retried
    ):
        fail("INVALID_ATOMIC_TRACE", "Atomic attempt counts are inconsistent")
    selected = trace.get("selected_attempts")
    if not isinstance(selected, list) or len(selected) != EXPECTED_ITEM_COUNT:
        fail("INVALID_ATOMIC_TRACE", "Atomic selected-attempt coverage is invalid")
    selected_call_ids: set[str] = set()
    provider_response_ids: set[str] = set()
    selected_second_attempts = 0
    for selection in selected:
        if not isinstance(selection, dict) or set(selection) != {
            "attempt_sha256s",
            "call_id",
            "provider_response_ids",
            "selected_attempt_number",
        }:
            fail("INVALID_ATOMIC_TRACE", "Selected attempt binding is invalid")
        call_id = selection.get("call_id")
        selected_number = selection.get("selected_attempt_number")
        hashes = selection.get("attempt_sha256s")
        response_ids = selection.get("provider_response_ids")
        if (
            not isinstance(call_id, str)
            or call_id in selected_call_ids
            or isinstance(selected_number, bool)
            or selected_number not in {1, 2}
            or not isinstance(hashes, list)
            or len(hashes) != selected_number
            or any(not isinstance(value, str) or len(value) != 64 for value in hashes)
            or not isinstance(response_ids, list)
            or not 1 <= len(response_ids) <= selected_number
            or any(not isinstance(value, str) or not value for value in response_ids)
            or len(set(response_ids)) != len(response_ids)
            or any(value in provider_response_ids for value in response_ids)
        ):
            fail("INVALID_ATOMIC_TRACE", "Selected attempt identity is invalid")
        selected_call_ids.add(call_id)
        provider_response_ids.update(response_ids)
        selected_second_attempts += selected_number == 2
    if (
        selected_call_ids
        != {f"call-{index:03d}" for index in range(1, EXPECTED_ITEM_COUNT + 1)}
        or selected_second_attempts != retried
    ):
        fail("INVALID_ATOMIC_TRACE", "Selected attempts do not match retry counts")
    judgments = trace.get("judgments")
    if not isinstance(judgments, list) or len(judgments) != EXPECTED_ITEM_COUNT:
        fail("INVALID_ATOMIC_TRACE", "Atomic trace must contain exactly 24 judgments")
    winners: dict[str, str] = {}
    for judgment in judgments:
        if not isinstance(judgment, dict):
            fail("INVALID_ATOMIC_TRACE", "Atomic judgment must be an object")
        item_id = judgment.get("item_id")
        winner = judgment.get("winner")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in winners
            or winner not in VALID_WINNERS
        ):
            fail("INVALID_ATOMIC_TRACE", "Atomic judgment identity is invalid")
        winners[item_id] = winner
    for key in ("source_bundle_file_sha256", "source_bundle_self_sha256"):
        value = trace.get(key)
        if not isinstance(value, str) or len(value) != 64:
            fail("INVALID_ATOMIC_TRACE", f"{key} is invalid")
    return winners, provider_response_ids


def evaluate_progress(stable_counts: list[int]) -> dict[str, Any]:
    if len(stable_counts) > EXPECTED_REPLICATE_COUNT or any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > EXPECTED_ITEM_COUNT
        for value in stable_counts
    ):
        fail("INVALID_CALIBRATION_PROGRESS", "Stable counts are invalid")
    completed = len(stable_counts)
    remaining = EXPECTED_REPLICATE_COUNT - completed
    maximum_pooled = sum(stable_counts) + remaining * EXPECTED_ITEM_COUNT
    if any(value < MIN_REPLICATE_STABILITY for value in stable_counts):
        decision = "stop_per_replicate_impossible"
    elif maximum_pooled < MIN_POOLED_STABILITY:
        decision = "stop_pooled_impossible"
    elif completed < EXPECTED_REPLICATE_COUNT:
        decision = "continue"
    else:
        decision = "profile_qualified"
    return {
        "completed_replicates": completed,
        "decision": decision,
        "maximum_possible_pooled_stability": maximum_pooled,
        "pooled_stable_count": sum(stable_counts),
        "remaining_replicates": remaining,
    }


def aggregate(
    *, replicates: list[dict[str, Path | str]], output_path: Path
) -> dict[str, Any]:
    if len(replicates) != EXPECTED_REPLICATE_COUNT:
        fail(
            "INVALID_ATOMIC_CALIBRATION_INPUT",
            "Atomic calibration requires exactly three mirror replicates",
        )
    seen_replicate_ids: set[str] = set()
    evaluator: dict[str, Any] | None = None
    source_hashes: dict[int, set[tuple[str, str]]] = {1: set(), 2: set()}
    pair_results = []
    file_hashes: dict[str, str] = {}
    total_first_valid = 0
    total_invalid_attempts = 0
    total_physical_attempts = 0
    total_retried_calls = 0
    invalid_codes: Counter[str] = Counter()
    all_provider_response_ids: set[str] = set()
    for raw_replicate in replicates:
        replicate_id = raw_replicate.get("replicate_id")
        if (
            not isinstance(replicate_id, str)
            or not replicate_id
            or replicate_id in seen_replicate_ids
        ):
            fail("INVALID_ATOMIC_CALIBRATION_INPUT", "Replicate identity is invalid")
        seen_replicate_ids.add(replicate_id)
        winners_by_orientation: dict[int, dict[str, str]] = {}
        distributions: dict[int, Counter[str]] = {}
        for orientation in (1, 2):
            trace_path = raw_replicate.get(f"orientation_{orientation}_trace")
            if not isinstance(trace_path, Path):
                fail(
                    "INVALID_ATOMIC_CALIBRATION_INPUT",
                    "Replicate trace paths are incomplete",
                )
            trace, trace_bytes = _read_object(
                trace_path,
                label=f"{replicate_id} orientation {orientation} atomic trace",
            )
            winners, response_ids = _winner_index(
                trace, replicate_id=replicate_id, orientation=orientation
            )
            if response_ids & all_provider_response_ids:
                fail(
                    "DUPLICATE_PROVIDER_RESPONSE",
                    "Atomic traces reuse a provider response",
                )
            all_provider_response_ids.update(response_ids)
            if evaluator is None:
                evaluator = trace["evaluator"]
            elif trace["evaluator"] != evaluator:
                fail(
                    "PROFILE_MISMATCH",
                    "Atomic traces use different evaluator profiles",
                )
            source_hashes[orientation].add(
                (
                    trace["source_bundle_file_sha256"],
                    trace["source_bundle_self_sha256"],
                )
            )
            summary = trace["attempt_summary"]
            total_first_valid += summary["first_attempt_valid_count"]
            total_invalid_attempts += summary["invalid_attempt_count"]
            total_physical_attempts += summary["total_physical_attempts"]
            total_retried_calls += summary["retried_call_count"]
            errors = trace["invalid_attempts_by_error"]
            if not isinstance(errors, dict) or any(
                not isinstance(key, str)
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                for key, value in errors.items()
            ):
                fail("INVALID_ATOMIC_TRACE", "Invalid-attempt diagnostics are invalid")
            if sum(errors.values()) != summary["invalid_attempt_count"]:
                fail(
                    "INVALID_ATOMIC_TRACE",
                    "Invalid-attempt diagnostics do not match attempt counts",
                )
            invalid_codes.update(errors)
            winners_by_orientation[orientation] = winners
            distributions[orientation] = Counter(winners.values())
            file_hashes[f"{replicate_id}/orientation-{orientation}/trace.json"] = (
                sha256_bytes(trace_bytes)
            )
        if set(winners_by_orientation[1]) != set(winners_by_orientation[2]):
            fail(
                "ITEM_IDENTITY_MISMATCH",
                "Mirrored atomic traces cover different items",
                replicate_id=replicate_id,
            )
        unstable_items = sorted(
            item_id
            for item_id, winner in winners_by_orientation[1].items()
            if winner != _normalize_mirrored_winner(winners_by_orientation[2][item_id])
        )
        stable_count = EXPECTED_ITEM_COUNT - len(unstable_items)
        stable_directional_count = sum(
            1
            for item_id, winner in winners_by_orientation[1].items()
            if winner in {"left", "right"} and item_id not in unstable_items
        )
        pair_results.append(
            {
                "meets_minimum": stable_count >= MIN_REPLICATE_STABILITY,
                "orientation_1_distribution": dict(sorted(distributions[1].items())),
                "orientation_2_distribution": dict(sorted(distributions[2].items())),
                "replicate_id": replicate_id,
                "stable_count": stable_count,
                "stable_directional_count": stable_directional_count,
                "total_count": EXPECTED_ITEM_COUNT,
                "unstable_item_ids": unstable_items,
            }
        )
    if any(len(values) != 1 for values in source_hashes.values()):
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "Replicates do not use one frozen source bundle per orientation",
        )
    pooled_stable = sum(pair["stable_count"] for pair in pair_results)
    gates = {
        "all_replicates_directional": all(
            pair["stable_directional_count"] > 0 for pair in pair_results
        ),
        "all_replicates_stable_at_or_above_22": all(
            pair["meets_minimum"] for pair in pair_results
        ),
        "pooled_stable_at_or_above_69_of_72": (pooled_stable >= MIN_POOLED_STABILITY),
    }
    passed = all(gates.values())
    result = {
        "attempt_diagnostics": {
            "first_attempt_valid_count": total_first_valid,
            "invalid_attempt_count": total_invalid_attempts,
            "invalid_attempts_by_error": dict(sorted(invalid_codes.items())),
            "retried_call_count": total_retried_calls,
            "total_logical_calls": EXPECTED_ITEM_COUNT * 2 * EXPECTED_REPLICATE_COUNT,
            "total_physical_attempts": total_physical_attempts,
        },
        "decision": "profile_qualified" if passed else "escalate_profile",
        "evaluator": evaluator,
        "files": dict(sorted(file_hashes.items())),
        "gates": gates,
        "pair_results": pair_results,
        "pooled_stable_count": pooled_stable,
        "pooled_total_count": EXPECTED_ITEM_COUNT * EXPECTED_REPLICATE_COUNT,
        "schema_version": ATOMIC_CALIBRATION_SCHEMA_VERSION,
        "source_bundle_hashes_by_orientation": {
            str(orientation): {
                "file_sha256": next(iter(values))[0],
                "self_sha256": next(iter(values))[1],
            }
            for orientation, values in source_hashes.items()
        },
        "status": "pass" if passed else "fail",
    }
    write_once(output_path, canonical_json_bytes(result))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate three atomic local-ranking mirror replicates"
    )
    parser.add_argument(
        "--replicate",
        action="append",
        nargs=3,
        metavar=("ID", "O1_TRACE", "O2_TRACE"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    replicates = [
        {
            "orientation_1_trace": Path(o1_trace),
            "orientation_2_trace": Path(o2_trace),
            "replicate_id": replicate_id,
        }
        for replicate_id, o1_trace, o2_trace in args.replicate
    ]
    try:
        result = aggregate(replicates=replicates, output_path=args.output)
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "ATOMIC_CALIBRATION_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
