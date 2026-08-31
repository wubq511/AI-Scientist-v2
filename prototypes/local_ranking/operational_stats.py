from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, write_json_once
from .errors import HarnessError, fail
from .operational_judge import (
    EVALUATORS,
    MAPPING_SCHEMA_VERSION,
    PREPARATION_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
)

REPORT_SCHEMA_VERSION = "local-ranking-setwise-statistics-v1.0"
BOOTSTRAP_REPETITIONS = 10_000
PROMOTION_MIN_RESOLVED = 18
PROMOTION_MIN_STRATUM_RESOLVED = 5
PROMOTION_MIN_DELTA = 1 / 3
PROMOTION_MAX_P = 0.05
MATERIAL_REVERSE = -0.25


def _read_canonical_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def exact_case_sign_flip(case_values: list[float]) -> dict[str, float | int]:
    if not case_values:
        fail("INVALID_STATISTICS", "Case-level statistic requires observations")
    observed = _mean(case_values)
    one_sided = 0
    two_sided = 0
    total = 0
    tolerance = 1e-12
    for signs in itertools.product((-1.0, 1.0), repeat=len(case_values)):
        permuted = _mean(
            [sign * value for sign, value in zip(signs, case_values, strict=True)]
        )
        total += 1
        if permuted + tolerance >= observed:
            one_sided += 1
        if abs(permuted) + tolerance >= abs(observed):
            two_sided += 1
    return {
        "enumeration_count": total,
        "observed_delta": observed,
        "one_sided_p": one_sided / total,
        "two_sided_p": two_sided / total,
    }


def _bootstrap_indices(seed: str, repetition: int, slot: int, count: int) -> int:
    digest = sha256_bytes(f"{seed}|bootstrap|{repetition}|{slot}".encode())
    return int(digest[:16], 16) % count


def cluster_bootstrap_ci(
    case_values: list[float], *, seed: str, repetitions: int = BOOTSTRAP_REPETITIONS
) -> dict[str, Any]:
    if not case_values or repetitions < 1:
        fail("INVALID_STATISTICS", "Bootstrap configuration is invalid")
    samples: list[float] = []
    for repetition in range(repetitions):
        selected = [
            case_values[_bootstrap_indices(seed, repetition, slot, len(case_values))]
            for slot in range(len(case_values))
        ]
        samples.append(_mean(selected))
    samples.sort()
    low_index = math.floor(0.025 * (repetitions - 1))
    high_index = math.ceil(0.975 * (repetitions - 1))
    return {
        "confidence": 0.95,
        "lower": samples[low_index],
        "method": "fixed-seed case-cluster percentile bootstrap",
        "repetitions": repetitions,
        "upper": samples[high_index],
    }


def _trace_index(
    trace: dict[str, Any],
    *,
    evaluator_id: str,
    orientation: int,
    expected_bundle_sha256: str,
) -> dict[str, dict[str, Any]]:
    expected_root_keys = {
        "bundle_sha256",
        "draft_sha256",
        "evaluator",
        "judgments",
        "orientation",
        "schema_version",
        "status",
    }
    if set(trace) != expected_root_keys:
        fail("INVALID_JUDGE_TRACE", "Judge trace root schema is not closed")
    if (
        trace.get("schema_version") != TRACE_SCHEMA_VERSION
        or trace.get("status") != "pass"
    ):
        fail("INVALID_JUDGE_TRACE", "Judge trace did not pass validation")
    if trace.get("evaluator") != EVALUATORS[evaluator_id]:
        fail("PROVENANCE_MISMATCH", "Judge trace evaluator profile changed")
    if trace.get("orientation") != orientation:
        fail("PROVENANCE_MISMATCH", "Judge trace orientation changed")
    if trace.get("bundle_sha256") != expected_bundle_sha256:
        fail("HASH_MISMATCH", "Judge trace does not bind preparation bundle")
    judgments = trace.get("judgments")
    if not isinstance(judgments, list):
        fail("INVALID_JUDGE_TRACE", "Judge trace judgments are missing")
    result = {
        item.get("item_id"): item
        for item in judgments
        if isinstance(item, dict) and isinstance(item.get("item_id"), str)
    }
    if len(result) != len(judgments):
        fail("INVALID_JUDGE_TRACE", "Judge trace item identities are duplicated")
    return result


def _validate_result_receipt(
    result: dict[str, Any],
    *,
    trace: dict[str, Any],
    trace_bytes: bytes,
    expected_bundle_sha256: str,
) -> None:
    expected_keys = {
        "bundle_sha256",
        "draft_sha256",
        "judgment_count",
        "schema_version",
        "status",
        "trace_sha256",
    }
    if set(result) != expected_keys:
        fail("INVALID_JUDGE_RESULT", "Judge result receipt schema is not closed")
    if (
        result.get("schema_version") != TRACE_SCHEMA_VERSION
        or result.get("status") != "pass"
        or result.get("bundle_sha256") != expected_bundle_sha256
        or result.get("draft_sha256") != trace.get("draft_sha256")
        or result.get("judgment_count") != len(trace.get("judgments", []))
        or result.get("trace_sha256") != sha256_bytes(trace_bytes)
    ):
        fail(
            "INVALID_JUDGE_RESULT",
            "Judge result receipt does not bind the validated trace",
        )


def _mapped_judgment(
    judgment: dict[str, Any], *, sides: dict[str, str]
) -> dict[str, Any]:
    winner = judgment["winner"]
    mapped_winner = sides[winner] if winner in {"left", "right"} else winner
    score_by_role = {
        sides["left"]: judgment["left_scores"],
        sides["right"]: judgment["right_scores"],
    }
    catastrophic = judgment["catastrophic_omission_side"]
    mapped_catastrophic = (
        sides[catastrophic] if catastrophic in {"left", "right"} else "neither"
    )
    return {
        "catastrophic_omission_role": mapped_catastrophic,
        "scores_by_role": score_by_role,
        "winner_role": mapped_winner,
    }


def _model_stability(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    winner_stable = first["winner_role"] == second["winner_role"]
    return {
        "orientation_1": first,
        "orientation_2": second,
        "score_profile_stable": first["scores_by_role"] == second["scores_by_role"],
        "winner_stable": winner_stable,
        "stable_winner_role": first["winner_role"] if winner_stable else None,
    }


def _group_delta(rows: list[dict[str, Any]], *, field: str, value: str) -> float:
    scores = [row["score"] for row in rows if row[field] == value]
    return _mean(scores)


def aggregate(
    *,
    mapping_path: Path,
    preparation_manifest_path: Path,
    trace_paths: dict[tuple[str, int], Path],
    output_path: Path,
) -> dict[str, Any]:
    mapping, mapping_bytes = _read_canonical_object(
        mapping_path, label="sealed mapping"
    )
    manifest, manifest_bytes = _read_canonical_object(
        preparation_manifest_path, label="judge preparation manifest"
    )
    if mapping.get("schema_version") != MAPPING_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Setwise mapping version is unsupported")
    if manifest.get("schema_version") != PREPARATION_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Judge preparation manifest version is unsupported")
    if manifest.get("mapping_sha256") != sha256_bytes(mapping_bytes):
        fail("HASH_MISMATCH", "Preparation manifest does not bind the mapping")
    bundle_records = manifest.get("bundles")
    if not isinstance(bundle_records, list) or len(bundle_records) != 4:
        fail("INVALID_ARTIFACT", "Preparation manifest must bind four judge bundles")
    bundle_sha_by_key = {
        (item.get("evaluator_id"), item.get("orientation")): item.get("bundle_sha256")
        for item in bundle_records
        if isinstance(item, dict)
    }
    expected_keys = {
        (evaluator_id, orientation)
        for evaluator_id in EVALUATORS
        for orientation in (1, 2)
    }
    if set(bundle_sha_by_key) != expected_keys or set(trace_paths) != expected_keys:
        fail(
            "INCOMPLETE_JUDGE_EVIDENCE",
            "Four exact evaluator orientations are required",
        )
    traces: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}
    trace_hashes: dict[str, str] = {}
    for key in sorted(expected_keys):
        trace, trace_bytes = _read_canonical_object(
            trace_paths[key], label=f"{key[0]} orientation {key[1]} trace"
        )
        result, _ = _read_canonical_object(
            trace_paths[key].parent / "result.json",
            label=f"{key[0]} orientation {key[1]} result receipt",
        )
        traces[key] = _trace_index(
            trace,
            evaluator_id=key[0],
            orientation=key[1],
            expected_bundle_sha256=bundle_sha_by_key[key],
        )
        _validate_result_receipt(
            result,
            trace=trace,
            trace_bytes=trace_bytes,
            expected_bundle_sha256=bundle_sha_by_key[key],
        )
        trace_hashes[f"{key[0]}-orientation-{key[1]}"] = sha256_bytes(trace_bytes)

    assignments = mapping.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        fail("INVALID_ARTIFACT", "Mapping has no assignments")
    query_ids = {item.get("query_id") for item in assignments if isinstance(item, dict)}
    if len(query_ids) != len(assignments) or any(
        set(index) != query_ids for index in traces.values()
    ):
        fail("INCOMPLETE_JUDGE_EVIDENCE", "Judge traces do not cover the exact mapping")

    rows: list[dict[str, Any]] = []
    for assignment in assignments:
        query_id = assignment["query_id"]
        model_results: dict[str, Any] = {}
        for evaluator_id in EVALUATORS:
            first = _mapped_judgment(
                traces[(evaluator_id, 1)][query_id],
                sides=assignment["orientation_1"],
            )
            second = _mapped_judgment(
                traces[(evaluator_id, 2)][query_id],
                sides=assignment["orientation_2"],
            )
            model_results[evaluator_id] = _model_stability(first, second)
        stable_winners = [
            model_results[evaluator_id]["stable_winner_role"]
            for evaluator_id in EVALUATORS
            if model_results[evaluator_id]["winner_stable"]
        ]
        if len(stable_winners) != len(EVALUATORS):
            category = "position_unstable"
            winner_role = None
        elif len(set(stable_winners)) != 1:
            category = "cross_model_unresolved"
            winner_role = None
        else:
            winner_role = stable_winners[0]
            category = {
                "baseline": "baseline_win",
                "challenger": "challenger_win",
                "tie": "tie",
                "both_bad": "both_bad",
            }[winner_role]
        catastrophic_challenger = len(stable_winners) == len(EVALUATORS) and all(
            model_results[evaluator_id][orientation]["catastrophic_omission_role"]
            == "challenger"
            for evaluator_id in EVALUATORS
            for orientation in ("orientation_1", "orientation_2")
        )
        rows.append(
            {
                "case_id": assignment["case_id"],
                "catastrophic_challenger": catastrophic_challenger,
                "category": category,
                "model_results": model_results,
                "query_id": query_id,
                "query_kind": assignment["query_kind"],
                "resolved": winner_role is not None,
                "score": (
                    1
                    if winner_role == "challenger"
                    else -1 if winner_role == "baseline" else 0
                ),
                "stratum": assignment["stratum"],
            }
        )

    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(row["case_id"], []).append(row)
    if any(len(case_rows) != 2 for case_rows in by_case.values()):
        fail(
            "INVALID_STATISTICS",
            "Each case must contain exactly two query observations",
        )
    case_values = [
        _mean([row["score"] for row in by_case[case_id]]) for case_id in sorted(by_case)
    ]
    exact = exact_case_sign_flip(case_values)
    mapping_sha256 = sha256_bytes(mapping_bytes)
    bootstrap = cluster_bootstrap_ci(case_values, seed=mapping_sha256)
    category_counts = {
        category: sum(row["category"] == category for row in rows)
        for category in (
            "baseline_win",
            "challenger_win",
            "tie",
            "both_bad",
            "position_unstable",
            "cross_model_unresolved",
        )
    }
    resolved_count = sum(row["resolved"] for row in rows)
    stratum_resolved = {
        stratum: sum(row["resolved"] and row["stratum"] == stratum for row in rows)
        for stratum in ("small", "medium", "large")
    }
    group_deltas = {
        "query_kind": {
            kind: _group_delta(rows, field="query_kind", value=kind)
            for kind in ("broad", "focused")
        },
        "stratum": {
            stratum: _group_delta(rows, field="stratum", value=stratum)
            for stratum in ("small", "medium", "large")
        },
    }
    material_reverse_groups = [
        f"{group}:{name}"
        for group, values in group_deltas.items()
        for name, delta in values.items()
        if delta <= MATERIAL_REVERSE
    ]
    catastrophic_total = sum(row["catastrophic_challenger"] for row in rows)
    catastrophic_by_stratum = {
        stratum: sum(
            row["catastrophic_challenger"] and row["stratum"] == stratum for row in rows
        )
        for stratum in ("small", "medium", "large")
    }
    systematic_catastrophic = catastrophic_total >= 3 or any(
        count >= 2 for count in catastrophic_by_stratum.values()
    )
    formal_shape = (
        mapping.get("evidence_mode") == "formal_fresh"
        and mapping.get("split") == "operational"
        and len(by_case) == 12
        and len(rows) == 24
        and all(
            sum(row["stratum"] == stratum for row in rows) == 8
            for stratum in ("small", "medium", "large")
        )
        and all(
            sum(row["query_kind"] == kind for row in rows) == 12
            for kind in ("broad", "focused")
        )
    )
    candidates = mapping.get("candidates")
    candidate_gates_pass = (
        isinstance(candidates, dict)
        and set(candidates) == {"baseline", "challenger"}
        and all(
            isinstance(item, dict)
            and item.get("gate_evidence")
            == {"gate_status": "pass", "resource_gate_failures": []}
            for item in candidates.values()
        )
    )
    promotion_gates = {
        "candidate_gates_pass": candidate_gates_pass,
        "delta_at_least_one_third": exact["observed_delta"] >= PROMOTION_MIN_DELTA,
        "formal_shape": formal_shape,
        "no_material_group_reverse": not material_reverse_groups,
        "no_systematic_challenger_catastrophic_omission": not systematic_catastrophic,
        "one_sided_p_at_most_0_05": exact["one_sided_p"] <= PROMOTION_MAX_P,
        "resolved_at_least_18": resolved_count >= PROMOTION_MIN_RESOLVED,
        "strata_resolved_at_least_5": all(
            count >= PROMOTION_MIN_STRATUM_RESOLVED
            for count in stratum_resolved.values()
        ),
    }
    challenger_promoted = all(promotion_gates.values())
    decision = (
        "diagnostic_only"
        if not formal_shape
        else (
            "promote_challenger" if challenger_promoted else "retain_baseline_parsimony"
        )
    )
    report = {
        "bootstrap_ci": bootstrap,
        "candidate_identity": candidates,
        "case_count": len(by_case),
        "case_values": [
            {"case_id": case_id, "d_i": value}
            for case_id, value in zip(sorted(by_case), case_values, strict=True)
        ],
        "category_counts": category_counts,
        "challenger_promoted": challenger_promoted,
        "decision": decision,
        "effect": exact,
        "evidence_mode": mapping.get("evidence_mode"),
        "group_deltas": group_deltas,
        "judge_rows": rows,
        "mapping_sha256": mapping_sha256,
        "material_reverse_groups": material_reverse_groups,
        "preparation_manifest_sha256": sha256_bytes(manifest_bytes),
        "promotion_gates": promotion_gates,
        "query_count": len(rows),
        "resolved_count": resolved_count,
        "schema_version": REPORT_SCHEMA_VERSION,
        "stratum_resolved": stratum_resolved,
        "systematic_challenger_catastrophic_omission": {
            "by_stratum": catastrophic_by_stratum,
            "status": systematic_catastrophic,
            "total": catastrophic_total,
        },
        "trace_hashes": trace_hashes,
    }
    write_json_once(output_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate frozen setwise judge traces"
    )
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--preparation-manifest", type=Path, required=True)
    parser.add_argument("--kimi-orientation-1", type=Path, required=True)
    parser.add_argument("--kimi-orientation-2", type=Path, required=True)
    parser.add_argument("--deepseek-orientation-1", type=Path, required=True)
    parser.add_argument("--deepseek-orientation-2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    trace_paths = {
        ("judge-kimi", 1): args.kimi_orientation_1,
        ("judge-kimi", 2): args.kimi_orientation_2,
        ("judge-deepseek", 1): args.deepseek_orientation_1,
        ("judge-deepseek", 2): args.deepseek_orientation_2,
    }
    try:
        result = aggregate(
            mapping_path=args.mapping,
            preparation_manifest_path=args.preparation_manifest,
            trace_paths=trace_paths,
            output_path=args.output,
        )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {
                "code": "OPERATIONAL_STATISTICS_FAILED",
                "message": str(exc),
            }
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
