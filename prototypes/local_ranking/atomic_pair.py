from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .atomic_calibration import (
    EXPECTED_ITEM_COUNT,
    MIN_REPLICATE_STABILITY,
    _normalize_mirrored_winner,
    _read_object,
    _winner_index,
)
from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail

PAIR_RESULT_SCHEMA_VERSION = "local-ranking-atomic-pair-result-v2.0"


def evaluate_pair(
    *,
    replicate_id: str,
    orientation_1_trace: Path,
    orientation_2_trace: Path,
    output_path: Path,
) -> dict[str, Any]:
    if not isinstance(replicate_id, str) or not replicate_id:
        fail("INVALID_REPLICATE_ID", "Pair replicate ID is invalid")
    traces = {}
    trace_bytes = {}
    winners = {}
    response_ids: set[str] = set()
    evaluator: dict[str, Any] | None = None
    for orientation, path in (
        (1, orientation_1_trace),
        (2, orientation_2_trace),
    ):
        trace, data = _read_object(
            path, label=f"{replicate_id} orientation {orientation} atomic trace"
        )
        indexed, orientation_response_ids = _winner_index(
            trace, replicate_id=replicate_id, orientation=orientation
        )
        if response_ids & orientation_response_ids:
            fail(
                "DUPLICATE_PROVIDER_RESPONSE",
                "Mirror orientations reuse a provider response",
            )
        response_ids.update(orientation_response_ids)
        if evaluator is None:
            evaluator = trace["evaluator"]
        elif trace["evaluator"] != evaluator:
            fail("PROFILE_MISMATCH", "Mirror orientations use different evaluators")
        traces[orientation] = trace
        trace_bytes[orientation] = data
        winners[orientation] = indexed
    if set(winners[1]) != set(winners[2]):
        fail("ITEM_IDENTITY_MISMATCH", "Mirror orientations cover different items")
    unstable_items = sorted(
        item_id
        for item_id, winner in winners[1].items()
        if winner != _normalize_mirrored_winner(winners[2][item_id])
    )
    stable_count = EXPECTED_ITEM_COUNT - len(unstable_items)
    stable_directional_count = sum(
        1
        for item_id, winner in winners[1].items()
        if item_id not in unstable_items and winner in {"left", "right"}
    )
    result = {
        "decision": (
            "continue_profile"
            if stable_count >= MIN_REPLICATE_STABILITY and stable_directional_count > 0
            else "stop_profile_failed"
        ),
        "evaluator": evaluator,
        "meets_minimum": stable_count >= MIN_REPLICATE_STABILITY,
        "orientation_1_distribution": dict(
            sorted(Counter(winners[1].values()).items())
        ),
        "orientation_2_distribution": dict(
            sorted(Counter(winners[2].values()).items())
        ),
        "replicate_id": replicate_id,
        "schema_version": PAIR_RESULT_SCHEMA_VERSION,
        "stable_count": stable_count,
        "stable_directional_count": stable_directional_count,
        "status": "pass",
        "trace_sha256s": {
            str(orientation): sha256_bytes(trace_bytes[orientation])
            for orientation in (1, 2)
        },
        "unstable_item_ids": unstable_items,
    }
    write_once(output_path, canonical_json_bytes(result))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate one atomic mirrored replicate for early stop"
    )
    parser.add_argument("--replicate-id", required=True)
    parser.add_argument("--orientation-1-trace", type=Path, required=True)
    parser.add_argument("--orientation-2-trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = evaluate_pair(
            replicate_id=args.replicate_id,
            orientation_1_trace=args.orientation_1_trace,
            orientation_2_trace=args.orientation_2_trace,
            output_path=args.output,
        )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "ATOMIC_PAIR_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
