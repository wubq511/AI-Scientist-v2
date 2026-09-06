from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail
from .operational_judge import TRACE_SCHEMA_VERSION

CALIBRATION_SCHEMA_VERSION = "local-ranking-evaluator-profile-calibration-v1.0"
OPENCODE_RECEIPT_SCHEMA_VERSION = "local-ranking-opencode-go-chat-receipt-v1.0"
OPENCODE_STREAM_RECEIPT_SCHEMA_VERSION = (
    "local-ranking-opencode-go-chat-stream-receipt-v1.0"
)
EXPECTED_ITEM_COUNT = 24
EXPECTED_REPLICATE_COUNT = 3
MIN_PAIR_STABILITY = 22
ORIGINAL_PAIR_GATE = 23
MIN_PAIRS_AT_ORIGINAL_GATE = 2
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


def _expected_evaluator(*, model: str, reasoning_effort: str) -> dict[str, str]:
    return {
        "harness": "opencode-go-chat-completions",
        "model_alias": f"opencode-go/{model}",
        "provider": "opencode-go",
        "reasoning_effort": reasoning_effort,
    }


def _winner_index(trace: dict[str, Any], *, orientation: int) -> dict[str, str]:
    if (
        set(trace)
        != {
            "bundle_sha256",
            "draft_sha256",
            "evaluator",
            "judgments",
            "orientation",
            "schema_version",
            "status",
        }
        or trace.get("schema_version") != TRACE_SCHEMA_VERSION
        or trace.get("status") != "pass"
        or trace.get("orientation") != orientation
    ):
        fail(
            "INVALID_TRACE",
            "Evaluator trace is not a passing expected orientation",
            orientation=orientation,
        )
    judgments = trace.get("judgments")
    if not isinstance(judgments, list) or len(judgments) != EXPECTED_ITEM_COUNT:
        fail(
            "INVALID_TRACE",
            "Evaluator trace does not contain exactly 24 judgments",
            orientation=orientation,
        )
    winners: dict[str, str] = {}
    for judgment in judgments:
        if not isinstance(judgment, dict):
            fail("INVALID_TRACE", "Evaluator judgment must be an object")
        item_id = judgment.get("item_id")
        winner = judgment.get("winner")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in winners
            or winner not in VALID_WINNERS
        ):
            fail("INVALID_TRACE", "Evaluator judgment identity or winner is invalid")
        winners[item_id] = winner
    return winners


def _validate_result_receipt(
    result: dict[str, Any], *, trace: dict[str, Any], trace_bytes: bytes
) -> None:
    if set(result) != {
        "bundle_sha256",
        "draft_sha256",
        "judgment_count",
        "schema_version",
        "status",
        "trace_sha256",
    } or (
        result.get("bundle_sha256") != trace.get("bundle_sha256")
        or result.get("draft_sha256") != trace.get("draft_sha256")
        or result.get("judgment_count") != EXPECTED_ITEM_COUNT
        or result.get("schema_version") != TRACE_SCHEMA_VERSION
        or result.get("status") != "pass"
        or result.get("trace_sha256") != sha256_bytes(trace_bytes)
    ):
        fail(
            "INVALID_JUDGE_RESULT",
            "Judge result receipt does not bind the validated trace",
        )


def _normalize_mirrored_winner(winner: str) -> str:
    return {"left": "right", "right": "left"}.get(winner, winner)


def _validate_receipt(
    receipt: dict[str, Any], *, model: str, reasoning_effort: str
) -> tuple[str, str, str]:
    identity = receipt.get("identity")
    qualification = receipt.get("transport_qualification")
    schema_version = receipt.get("schema_version")
    is_stream = schema_version == OPENCODE_STREAM_RECEIPT_SCHEMA_VERSION
    if (
        schema_version
        not in {
            OPENCODE_RECEIPT_SCHEMA_VERSION,
            OPENCODE_STREAM_RECEIPT_SCHEMA_VERSION,
        }
        or receipt.get("status") != "pass"
        or receipt.get("provider") != "opencode-go"
        or receipt.get("http_status") != 200
        or not isinstance(identity, dict)
        or identity.get("model") != model
        or not isinstance(qualification, dict)
        or qualification.get("reasoning_effort_requested") != reasoning_effort
        or qualification.get("json_object_accepted") is not True
        or (
            is_stream
            and (
                qualification.get("streaming_requested") is not True
                or qualification.get("stream_completed") is not True
                or identity.get("finish_reason") != "stop"
            )
        )
    ):
        fail("INVALID_RECEIPT", "OpenCode Go execution receipt is incompatible")
    response_id = identity.get("provider_response_id")
    request_sha256 = receipt.get("request_sha256")
    if (
        not isinstance(response_id, str)
        or not response_id
        or not isinstance(request_sha256, str)
        or len(request_sha256) != 64
    ):
        fail("INVALID_RECEIPT", "OpenCode Go receipt identity is incomplete")
    return response_id, request_sha256, "sse" if is_stream else "non_streaming"


def aggregate(
    *,
    model: str,
    reasoning_effort: str,
    replicates: list[dict[str, Path | str]],
    output_path: Path,
) -> dict[str, Any]:
    if len(replicates) != EXPECTED_REPLICATE_COUNT:
        fail(
            "INVALID_CALIBRATION_INPUT",
            "Profile calibration requires exactly three fresh mirror replicates",
        )
    expected_evaluator = _expected_evaluator(
        model=model, reasoning_effort=reasoning_effort
    )
    seen_replicate_ids: set[str] = set()
    seen_response_ids: set[str] = set()
    bundle_hashes: dict[int, set[str]] = {1: set(), 2: set()}
    request_hashes: dict[int, set[str]] = {1: set(), 2: set()}
    transport_modes: set[str] = set()
    pair_results: list[dict[str, Any]] = []
    input_files: dict[str, str] = {}

    for raw_replicate in replicates:
        replicate_id = raw_replicate.get("replicate_id")
        if (
            not isinstance(replicate_id, str)
            or not replicate_id
            or replicate_id in seen_replicate_ids
        ):
            fail("INVALID_CALIBRATION_INPUT", "Replicate identity is invalid")
        seen_replicate_ids.add(replicate_id)
        winner_indexes: dict[int, dict[str, str]] = {}
        distributions: dict[int, Counter[str]] = {}
        for orientation in (1, 2):
            trace_key = f"orientation_{orientation}_trace"
            receipt_key = f"orientation_{orientation}_receipt"
            trace_path = raw_replicate.get(trace_key)
            receipt_path = raw_replicate.get(receipt_key)
            if not isinstance(trace_path, Path) or not isinstance(receipt_path, Path):
                fail("INVALID_CALIBRATION_INPUT", "Replicate paths are incomplete")
            trace, trace_bytes = _read_object(
                trace_path, label=f"{replicate_id} orientation {orientation} trace"
            )
            result, result_bytes = _read_object(
                trace_path.parent / "result.json",
                label=f"{replicate_id} orientation {orientation} result",
            )
            receipt, receipt_bytes = _read_object(
                receipt_path,
                label=f"{replicate_id} orientation {orientation} receipt",
            )
            if trace.get("evaluator") != expected_evaluator:
                fail(
                    "PROFILE_MISMATCH",
                    "Evaluator trace does not match the calibrated profile",
                    replicate_id=replicate_id,
                    orientation=orientation,
                )
            _validate_result_receipt(result, trace=trace, trace_bytes=trace_bytes)
            response_id, request_hash, transport_mode = _validate_receipt(
                receipt, model=model, reasoning_effort=reasoning_effort
            )
            transport_modes.add(transport_mode)
            if response_id in seen_response_ids:
                fail(
                    "DUPLICATE_PROVIDER_RESPONSE",
                    "Fresh calibration calls reused a provider response identity",
                )
            seen_response_ids.add(response_id)
            request_hashes[orientation].add(request_hash)
            bundle_hash = trace.get("bundle_sha256")
            if not isinstance(bundle_hash, str) or len(bundle_hash) != 64:
                fail("INVALID_TRACE", "Trace bundle hash is invalid")
            bundle_hashes[orientation].add(bundle_hash)
            winner_indexes[orientation] = _winner_index(trace, orientation=orientation)
            distributions[orientation] = Counter(winner_indexes[orientation].values())
            input_files[f"{replicate_id}/orientation-{orientation}/trace.json"] = (
                sha256_bytes(trace_bytes)
            )
            input_files[f"{replicate_id}/orientation-{orientation}/result.json"] = (
                sha256_bytes(result_bytes)
            )
            input_files[f"{replicate_id}/orientation-{orientation}/receipt.json"] = (
                sha256_bytes(receipt_bytes)
            )

        if set(winner_indexes[1]) != set(winner_indexes[2]):
            fail(
                "ITEM_IDENTITY_MISMATCH",
                "Mirrored traces do not cover the same item identities",
                replicate_id=replicate_id,
            )
        unstable_items = sorted(
            item_id
            for item_id, winner in winner_indexes[1].items()
            if winner != _normalize_mirrored_winner(winner_indexes[2][item_id])
        )
        stable_count = EXPECTED_ITEM_COUNT - len(unstable_items)
        pair_results.append(
            {
                "at_original_gate": stable_count >= ORIGINAL_PAIR_GATE,
                "meets_minimum": stable_count >= MIN_PAIR_STABILITY,
                "orientation_1_distribution": dict(sorted(distributions[1].items())),
                "orientation_2_distribution": dict(sorted(distributions[2].items())),
                "replicate_id": replicate_id,
                "stable_count": stable_count,
                "total_count": EXPECTED_ITEM_COUNT,
                "unstable_item_ids": unstable_items,
            }
        )

    if any(len(values) != 1 for values in bundle_hashes.values()):
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "Replicates do not use one frozen bundle per orientation",
        )
    if any(len(values) != 1 for values in request_hashes.values()):
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "Replicates do not use one frozen request per orientation",
        )
    if len(transport_modes) != 1:
        fail(
            "TRANSPORT_MISMATCH",
            "All profile calibration calls must use one frozen transport",
        )
    pooled_stable = sum(pair["stable_count"] for pair in pair_results)
    pairs_at_original_gate = sum(1 for pair in pair_results if pair["at_original_gate"])
    gates = {
        "all_pairs_at_or_above_22": all(pair["meets_minimum"] for pair in pair_results),
        "at_least_two_pairs_at_or_above_23": (
            pairs_at_original_gate >= MIN_PAIRS_AT_ORIGINAL_GATE
        ),
        "pooled_at_or_above_69_of_72": pooled_stable >= MIN_POOLED_STABILITY,
        "six_unique_provider_responses": len(seen_response_ids)
        == EXPECTED_REPLICATE_COUNT * 2,
    }
    passed = all(gates.values())
    result = {
        "bundle_sha256_by_orientation": {
            str(orientation): next(iter(values))
            for orientation, values in bundle_hashes.items()
        },
        "decision": "profile_qualified" if passed else "escalate_profile",
        "files": dict(sorted(input_files.items())),
        "gates": gates,
        "model": model,
        "pair_results": pair_results,
        "pairs_at_original_gate": pairs_at_original_gate,
        "pooled_stable_count": pooled_stable,
        "pooled_total_count": EXPECTED_ITEM_COUNT * EXPECTED_REPLICATE_COUNT,
        "provider": "opencode-go",
        "reasoning_effort": reasoning_effort,
        "request_sha256_by_orientation": {
            str(orientation): next(iter(values))
            for orientation, values in request_hashes.items()
        },
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "status": "pass" if passed else "fail",
        "transport": next(iter(transport_modes)),
    }
    write_once(output_path, canonical_json_bytes(result))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate three frozen local-ranking evaluator mirror replicates"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument(
        "--replicate",
        action="append",
        nargs=5,
        metavar=("ID", "O1_TRACE", "O2_TRACE", "O1_RECEIPT", "O2_RECEIPT"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    replicates = [
        {
            "orientation_1_receipt": Path(o1_receipt),
            "orientation_1_trace": Path(o1_trace),
            "orientation_2_receipt": Path(o2_receipt),
            "orientation_2_trace": Path(o2_trace),
            "replicate_id": replicate_id,
        }
        for replicate_id, o1_trace, o2_trace, o1_receipt, o2_receipt in args.replicate
    ]
    try:
        result = aggregate(
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            replicates=replicates,
            output_path=args.output,
        )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "PROFILE_CALIBRATION_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
