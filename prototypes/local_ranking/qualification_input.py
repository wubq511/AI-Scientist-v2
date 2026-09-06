from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import INPUT_SCHEMA_VERSION
from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail
from .operational_judge import (
    FROZEN_BASELINE_CANDIDATE_ID,
    FROZEN_CHALLENGER_CANDIDATE_ID,
    _read_canonical_object,
    _read_payload_records,
    _validate_payload_set,
    _validate_summary,
)
from .schema import RankingInput, parse_ranking_input

MANIFEST_SCHEMA_VERSION = "local-ranking-spent-qualification-input-v1.0"
SELECTION_SCHEMA_VERSION = "local-ranking-spent-qualification-case-selection-v1.0"
SUMMARY_SCHEMA_VERSION = "local-ranking-spent-qualification-comparison-v1.0"
OUTPUT_FILES = {
    "baseline_payloads": "baseline-payloads.jsonl",
    "challenger_payloads": "challenger-payloads.jsonl",
    "comparison_summary": "comparison-summary.json",
    "input": "input.json",
    "selection": "selection.json",
}


def _source_input(
    path: Path, *, split: str
) -> tuple[dict[str, Any], bytes, RankingInput]:
    value, data = _read_canonical_object(path, label=f"{split} input")
    parsed = parse_ranking_input(value)
    if parsed.split != split:
        fail(
            "INVALID_SPLIT",
            "Qualification source input has the wrong split",
            expected=split,
            actual=parsed.split,
        )
    if len(parsed.cases) != 6 or len(parsed.queries) != 12:
        fail(
            "INVALID_QUALIFICATION_SCALE",
            "Each spent source must contain six cases and twelve queries",
            split=split,
            case_count=len(parsed.cases),
            query_count=len(parsed.queries),
        )
    return value, data, parsed


def _selection_cases(
    selection: dict[str, Any], sources: tuple[RankingInput, RankingInput]
) -> list[dict[str, Any]]:
    raw_cases = selection.get("cases")
    if not isinstance(raw_cases, list):
        fail("INVALID_SELECTION", "Source selection contains no cases")
    by_case: dict[str, dict[str, Any]] = {}
    for item in raw_cases:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            fail("INVALID_SELECTION", "Source selection case is invalid")
        case_id = item["case_id"]
        if case_id in by_case:
            fail(
                "INVALID_SELECTION",
                "Source selection case is duplicated",
                case_id=case_id,
            )
        by_case[case_id] = item

    selected: list[dict[str, Any]] = []
    all_case_ids: set[str] = set()
    for source in sources:
        expected_split = source.split
        split_strata: list[str] = []
        for case in source.cases:
            if case.case_id in all_case_ids:
                fail(
                    "INPUT_IDENTITY_MISMATCH",
                    "Spent source case is duplicated across splits",
                    case_id=case.case_id,
                )
            all_case_ids.add(case.case_id)
            item = by_case.get(case.case_id)
            if item is None or item.get("split") != expected_split:
                fail(
                    "INPUT_IDENTITY_MISMATCH",
                    "Selection does not preserve source split identity",
                    case_id=case.case_id,
                )
            stratum = item.get("stratum")
            if stratum not in {"small", "medium", "large"}:
                fail(
                    "INVALID_SELECTION",
                    "Selection case has an invalid stratum",
                    case_id=case.case_id,
                )
            split_strata.append(stratum)
            selected.append(item)
        counts = {
            stratum: split_strata.count(stratum)
            for stratum in ("small", "medium", "large")
        }
        if counts != {"small": 2, "medium": 2, "large": 2}:
            fail(
                "INVALID_SELECTION",
                "Each spent source must contain two cases per stratum",
                split=expected_split,
                counts=counts,
            )
    return sorted(selected, key=lambda item: item["case_id"])


def _combined_payload_bytes(
    source_paths: tuple[Path, Path],
    source_inputs: tuple[RankingInput, RankingInput],
    source_summaries: tuple[dict[str, Any], dict[str, Any]],
    *,
    candidate_id: str,
) -> tuple[bytes, dict[str, str], tuple[bytes, bytes]]:
    combined_records: dict[str, dict[str, Any]] = {}
    source_bytes: list[bytes] = []
    for path, ranking_input, summary in zip(
        source_paths, source_inputs, source_summaries, strict=True
    ):
        records, data = _read_payload_records(path)
        _validate_payload_set(records, ranking_input)
        _validate_summary(
            summary,
            candidate_ids=(candidate_id, candidate_id),
            payload_sets=(records, records),
        )
        overlap = set(combined_records).intersection(records)
        if overlap:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Payload query is duplicated across spent sources",
                query_ids=sorted(overlap),
            )
        combined_records.update(records)
        source_bytes.append(data)
    combined = b"".join(
        canonical_json_bytes(combined_records[query_id])
        for query_id in sorted(combined_records)
    )
    hashes = {
        query_id: combined_records[query_id]["payload_sha256"]
        for query_id in sorted(combined_records)
    }
    return combined, hashes, (source_bytes[0], source_bytes[1])


def prepare(
    *,
    development_input_path: Path,
    holdout_input_path: Path,
    selection_path: Path,
    development_summary_path: Path,
    holdout_summary_path: Path,
    development_baseline_payload_path: Path,
    holdout_baseline_payload_path: Path,
    development_challenger_payload_path: Path,
    holdout_challenger_payload_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    development_value, development_bytes, development_input = _source_input(
        development_input_path, split="development"
    )
    holdout_value, holdout_bytes, holdout_input = _source_input(
        holdout_input_path, split="holdout"
    )
    selection, selection_bytes = _read_canonical_object(
        selection_path, label="source selection"
    )
    development_summary, development_summary_bytes = _read_canonical_object(
        development_summary_path, label="development comparison summary"
    )
    holdout_summary, holdout_summary_bytes = _read_canonical_object(
        holdout_summary_path, label="holdout comparison summary"
    )
    source_inputs = (development_input, holdout_input)
    source_summaries = (development_summary, holdout_summary)

    baseline_bytes, baseline_hashes, baseline_source_bytes = _combined_payload_bytes(
        (development_baseline_payload_path, holdout_baseline_payload_path),
        source_inputs,
        source_summaries,
        candidate_id=FROZEN_BASELINE_CANDIDATE_ID,
    )
    challenger_bytes, challenger_hashes, challenger_source_bytes = (
        _combined_payload_bytes(
            (development_challenger_payload_path, holdout_challenger_payload_path),
            source_inputs,
            source_summaries,
            candidate_id=FROZEN_CHALLENGER_CANDIDATE_ID,
        )
    )

    cases = sorted(
        [*development_value["cases"], *holdout_value["cases"]],
        key=lambda item: item["case_id"],
    )
    combined_input = {
        "cases": cases,
        "schema_version": INPUT_SCHEMA_VERSION,
        "split": "spent_qualification",
    }
    parsed_combined = parse_ranking_input(combined_input)
    if len(parsed_combined.cases) != 12 or len(parsed_combined.queries) != 24:
        fail(
            "INVALID_QUALIFICATION_SCALE",
            "Combined spent qualification input must contain 12 cases and 24 queries",
        )
    combined_input_bytes = canonical_json_bytes(combined_input)

    selected_cases = _selection_cases(selection, source_inputs)
    combined_selection = {
        "cases": selected_cases,
        "selection_version": SELECTION_SCHEMA_VERSION,
        "source_selection_sha256": sha256_bytes(selection_bytes),
    }
    combined_selection_bytes = canonical_json_bytes(combined_selection)
    combined_summary = {
        "candidate_results": [
            {
                "candidate_id": candidate_id,
                "payload_hashes": payload_hashes,
                "resources": {"gate_failures": [], "gate_status": "pass"},
                "status": "success",
            }
            for candidate_id, payload_hashes in (
                (FROZEN_BASELINE_CANDIDATE_ID, baseline_hashes),
                (FROZEN_CHALLENGER_CANDIDATE_ID, challenger_hashes),
            )
        ],
        "evidence_mode": "spent_diagnostic_only",
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "source_summary_sha256": {
            "development": sha256_bytes(development_summary_bytes),
            "holdout": sha256_bytes(holdout_summary_bytes),
        },
        "status": "success",
    }
    combined_summary_bytes = canonical_json_bytes(combined_summary)
    files = {
        OUTPUT_FILES["baseline_payloads"]: baseline_bytes,
        OUTPUT_FILES["challenger_payloads"]: challenger_bytes,
        OUTPUT_FILES["comparison_summary"]: combined_summary_bytes,
        OUTPUT_FILES["input"]: combined_input_bytes,
        OUTPUT_FILES["selection"]: combined_selection_bytes,
    }
    manifest = {
        "evidence_mode": "spent_diagnostic_only",
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_bindings": {
            "development_baseline_payloads_sha256": sha256_bytes(
                baseline_source_bytes[0]
            ),
            "development_challenger_payloads_sha256": sha256_bytes(
                challenger_source_bytes[0]
            ),
            "development_input_sha256": sha256_bytes(development_bytes),
            "development_summary_sha256": sha256_bytes(development_summary_bytes),
            "holdout_baseline_payloads_sha256": sha256_bytes(baseline_source_bytes[1]),
            "holdout_challenger_payloads_sha256": sha256_bytes(
                challenger_source_bytes[1]
            ),
            "holdout_input_sha256": sha256_bytes(holdout_bytes),
            "holdout_summary_sha256": sha256_bytes(holdout_summary_bytes),
            "source_selection_sha256": sha256_bytes(selection_bytes),
        },
        "status": "spent_qualification_input_ready",
    }
    for name, data in files.items():
        write_once(output_root / name, data)
    write_once(output_root / "manifest.json", canonical_json_bytes(manifest))
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine spent development and holdout evidence for judge qualification"
    )
    parser.add_argument("--development-input", type=Path, required=True)
    parser.add_argument("--holdout-input", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--development-summary", type=Path, required=True)
    parser.add_argument("--holdout-summary", type=Path, required=True)
    parser.add_argument("--development-baseline-payloads", type=Path, required=True)
    parser.add_argument("--holdout-baseline-payloads", type=Path, required=True)
    parser.add_argument("--development-challenger-payloads", type=Path, required=True)
    parser.add_argument("--holdout-challenger-payloads", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = prepare(
            development_input_path=args.development_input,
            holdout_input_path=args.holdout_input,
            selection_path=args.selection,
            development_summary_path=args.development_summary,
            holdout_summary_path=args.holdout_summary,
            development_baseline_payload_path=args.development_baseline_payloads,
            holdout_baseline_payload_path=args.holdout_baseline_payloads,
            development_challenger_payload_path=args.development_challenger_payloads,
            holdout_challenger_payload_path=args.holdout_challenger_payloads,
            output_root=args.output_root,
        )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "QUALIFICATION_INPUT_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
