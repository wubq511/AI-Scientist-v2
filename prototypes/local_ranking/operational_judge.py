from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, write_json_once, write_once
from .errors import HarnessError, fail
from .schema import RankingInput, parse_ranking_input

BUNDLE_SCHEMA_VERSION = "local-ranking-setwise-judge-bundle-v1.1"
DRAFT_SCHEMA_VERSION = "local-ranking-setwise-judge-draft-v1.1"
TRACE_SCHEMA_VERSION = "local-ranking-setwise-judge-trace-v1.1"
MAPPING_SCHEMA_VERSION = "local-ranking-setwise-mapping-v1.1"
PREPARATION_SCHEMA_VERSION = "local-ranking-setwise-preparation-v1.1"
FORMALIZATION_SCHEMA_VERSION = "prototype-formal-input-v1.0"
OPERATIONAL_SELECTION_VERSION = "local-ranking-operational-case-selection-v1.0.1"
SPENT_QUALIFICATION_MANIFEST_VERSION = "local-ranking-spent-qualification-input-v1.0"
SPENT_QUALIFICATION_SELECTION_VERSION = (
    "local-ranking-spent-qualification-case-selection-v1.0"
)
FROZEN_BASELINE_CANDIDATE_ID = "bm25-k16-b05-tw1-cap3"
FROZEN_CHALLENGER_CANDIDATE_ID = "e5-small-v2-tw1-cap3"
WINNERS = {"left", "right", "tie", "both_bad"}
SCORE_FIELDS = {
    "coverage_diversity",
    "direct_support",
    "query_usefulness",
    "specificity",
}
EVALUATORS = {
    "judge-kimi": {
        "harness": "kimi-code-cli",
        "model_alias": "kimi-code/k3",
        "provider": "managed:kimi-code",
        "reasoning_effort": "high",
    },
    "judge-deepseek": {
        "harness": "kimi-code-cli",
        "model_alias": "opencode-go/deepseek-v4-flash",
        "provider": "opencode-go",
        "reasoning_effort": "high",
    },
}
FORBIDDEN_PUBLIC_TEXT = ("bm25", "e5-small", "qrels", "old winner")


def _expect_keys(value: dict[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        fail(
            "INVALID_SCHEMA",
            f"{label} has an invalid closed schema",
            missing=sorted(expected - set(value)),
            unknown=sorted(set(value) - expected),
        )


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


def _read_draft(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_JUDGE_DRAFT", "Judge draft is unreadable JSON", error=str(exc))
    if not isinstance(value, dict):
        fail("INVALID_JUDGE_DRAFT", "Judge draft must be an object")
    return value, data


def _read_payload_records(path: Path) -> tuple[dict[str, dict[str, Any]], bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", "Candidate payload file is unreadable", error=str(exc))
    records: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(data.splitlines(keepends=True), start=1):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail(
                "INVALID_PAYLOAD",
                "Candidate payload line is invalid JSON",
                line=index,
                error=str(exc),
            )
        if not isinstance(value, dict) or canonical_json_bytes(value) != line:
            fail(
                "NON_CANONICAL_INPUT",
                "Candidate payload line is not canonical",
                line=index,
            )
        _expect_keys(
            value,
            {"case_id", "payload", "payload_sha256", "query_id"},
            label=f"payload line {index}",
        )
        query_id = value.get("query_id")
        if not isinstance(query_id, str) or query_id in records:
            fail("INVALID_PAYLOAD", "Candidate query identity is invalid", line=index)
        payload = value.get("payload")
        if not isinstance(payload, dict):
            fail(
                "INVALID_PAYLOAD",
                "Candidate payload must be an object",
                query_id=query_id,
            )
        if sha256_bytes(canonical_json_bytes(payload)) != value.get("payload_sha256"):
            fail("HASH_MISMATCH", "Candidate payload hash changed", query_id=query_id)
        records[query_id] = value
    if not records:
        fail("INVALID_PAYLOAD", "Candidate payload file is empty")
    return records, data


def _input_indexes(
    ranking_input: RankingInput,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cases: dict[str, Any] = {}
    queries: dict[str, Any] = {}
    for case in ranking_input.cases:
        paper_index = {paper.paper_id: paper for paper in case.papers}
        cases[case.case_id] = {"case": case, "papers": paper_index}
        for query in case.queries:
            queries[query.query_id] = {"case": case, "query": query}
    return cases, queries


def _validate_payload_set(
    records: dict[str, dict[str, Any]], ranking_input: RankingInput
) -> dict[str, dict[str, Any]]:
    cases, queries = _input_indexes(ranking_input)
    if set(records) != set(queries):
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "Candidate payload query set differs from formal input",
            missing=sorted(set(queries) - set(records)),
            unknown=sorted(set(records) - set(queries)),
        )
    rendered: dict[str, dict[str, Any]] = {}
    for query_id, record in records.items():
        query_entry = queries[query_id]
        case = query_entry["case"]
        if record.get("case_id") != case.case_id:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Payload case/query mapping changed",
                query_id=query_id,
            )
        payload = record["payload"]
        _expect_keys(payload, {"papers"}, label=f"{query_id}.payload")
        raw_papers = payload.get("papers")
        if not isinstance(raw_papers, list) or len(raw_papers) != 3:
            fail(
                "OUTPUT_BUDGET_VIOLATION",
                "Setwise evaluator requires exact top-3",
                query_id=query_id,
            )
        seen_papers: set[str] = set()
        papers: list[dict[str, Any]] = []
        source_papers = cases[case.case_id]["papers"]
        for raw_paper in raw_papers:
            if not isinstance(raw_paper, dict):
                fail(
                    "INVALID_PAYLOAD",
                    "Payload paper must be an object",
                    query_id=query_id,
                )
            _expect_keys(
                raw_paper, {"paper_id", "segments", "title"}, label=f"{query_id}.paper"
            )
            paper_id = raw_paper.get("paper_id")
            if (
                not isinstance(paper_id, str)
                or paper_id in seen_papers
                or paper_id not in source_papers
            ):
                fail(
                    "CORPUS_BOUNDARY_VIOLATION",
                    "Payload paper identity is invalid",
                    query_id=query_id,
                )
            seen_papers.add(paper_id)
            source_paper = source_papers[paper_id]
            if raw_paper.get("title") != source_paper.title:
                fail(
                    "CORPUS_DRIFT",
                    "Payload title differs from formal input",
                    paper_id=paper_id,
                )
            raw_segments = raw_paper.get("segments")
            if not isinstance(raw_segments, list) or len(raw_segments) != 1:
                fail(
                    "OUTPUT_BUDGET_VIOLATION",
                    "Each top-3 paper needs one segment",
                    paper_id=paper_id,
                )
            raw_segment = raw_segments[0]
            if not isinstance(raw_segment, dict):
                fail(
                    "INVALID_PAYLOAD",
                    "Payload segment must be an object",
                    paper_id=paper_id,
                )
            _expect_keys(
                raw_segment, {"content_type", "text"}, label=f"{paper_id}.segment"
            )
            matches = [
                segment
                for segment in source_paper.segments
                if segment.content_type == raw_segment.get("content_type")
                and segment.text == raw_segment.get("text")
            ]
            if len(matches) != 1:
                fail(
                    "CORPUS_DRIFT",
                    "Payload segment does not map uniquely to formal input",
                    paper_id=paper_id,
                )
            segment = matches[0]
            papers.append(
                {
                    "paper_id": paper_id,
                    "segments": [
                        {
                            "content_type": segment.content_type,
                            "segment_id": segment.segment_id,
                            "source_start": segment.source_start,
                            "text": segment.text,
                        }
                    ],
                    "title": source_paper.title,
                }
            )
        rendered[query_id] = {"papers": papers}
    return rendered


def _validate_summary(
    summary: dict[str, Any],
    *,
    candidate_ids: tuple[str, str],
    payload_sets: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    if summary.get("status") != "success":
        fail("CANDIDATE_GATE_FAILED", "Comparison summary is not successful")
    raw_results = summary.get("candidate_results")
    if not isinstance(raw_results, list):
        fail("INVALID_ARTIFACT", "Comparison summary has no candidate results")
    by_id = {
        item.get("candidate_id"): item
        for item in raw_results
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
    }
    if any(candidate_id not in by_id for candidate_id in candidate_ids):
        fail("INPUT_IDENTITY_MISMATCH", "Comparison summary lacks a frozen finalist")
    result: dict[str, dict[str, Any]] = {}
    for candidate_id, payloads in zip(candidate_ids, payload_sets, strict=True):
        candidate = by_id[candidate_id]
        resources = candidate.get("resources")
        if (
            candidate.get("status") != "success"
            or not isinstance(resources, dict)
            or resources.get("gate_status") != "pass"
            or resources.get("gate_failures") != []
        ):
            fail(
                "CANDIDATE_GATE_FAILED",
                "Frozen finalist failed a retrieval/resource gate",
                candidate_id=candidate_id,
            )
        expected_hashes = {
            query_id: item["payload_sha256"] for query_id, item in payloads.items()
        }
        if candidate.get("payload_hashes") != expected_hashes:
            fail(
                "HASH_MISMATCH",
                "Comparison summary payload hashes differ",
                candidate_id=candidate_id,
            )
        result[candidate_id] = {
            "gate_status": "pass",
            "resource_gate_failures": [],
        }
    return result


def _selection_strata(
    selection: dict[str, Any], ranking_input: RankingInput
) -> dict[str, str]:
    raw_cases = selection.get("cases")
    if not isinstance(raw_cases, list):
        fail("INVALID_SELECTION", "Selection manifest contains no cases")
    by_case = {
        item.get("case_id"): item
        for item in raw_cases
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    input_case_ids = {case.case_id for case in ranking_input.cases}
    if ranking_input.split == "operational":
        if selection.get("selection_version") != OPERATIONAL_SELECTION_VERSION:
            fail(
                "INVALID_SELECTION",
                "Formal operational input requires the frozen fresh selection version",
            )
        if set(by_case) != input_case_ids:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Operational selection and formal input case sets differ",
            )
    elif ranking_input.split == "spent_qualification":
        if selection.get("selection_version") != SPENT_QUALIFICATION_SELECTION_VERSION:
            fail(
                "INVALID_SELECTION",
                "Spent qualification input requires its derived selection version",
            )
        if set(by_case) != input_case_ids:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Spent qualification selection and input case sets differ",
            )
    elif ranking_input.split not in {"development", "holdout"}:
        fail(
            "INVALID_SPLIT",
            "Only operational evidence or spent development/holdout diagnostics are allowed",
        )
    strata: dict[str, str] = {}
    for case in ranking_input.cases:
        item = by_case.get(case.case_id)
        if item is None or item.get("stratum") not in {"small", "medium", "large"}:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Selection lacks case stratum",
                case_id=case.case_id,
            )
        strata[case.case_id] = item["stratum"]
    if ranking_input.split in {"operational", "spent_qualification"}:
        counts = {
            stratum: sum(value == stratum for value in strata.values())
            for stratum in ("small", "medium", "large")
        }
        if counts != {"small": 4, "medium": 4, "large": 4}:
            fail(
                "INVALID_SELECTION",
                "Evaluation selection must contain four cases per stratum",
                counts=counts,
            )
    return strata


def _bundle_item(
    *,
    query_id: str,
    query_entry: dict[str, Any],
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    query = query_entry["query"]
    case = query_entry["case"]
    return {
        "case_id": case.case_id,
        "item_id": query_id,
        "left": left,
        "query": {"kind": query.kind, "text": query.text},
        "right": right,
    }


def _draft_contract() -> dict[str, Any]:
    return {
        "attestation": {
            "bundle_only": True,
            "fresh_session": True,
            "no_external_sources": True,
            "tool_access": "disabled",
        },
        "judgment": {
            "catastrophic_omission_side": ["left", "right", "neither"],
            "evidence_ref_count": [1, 4],
            "evidence_support_scalar_count": [20, 500],
            "score_fields": sorted(SCORE_FIELDS),
            "score_values": [0, 1, 2],
            "winner": sorted(WINNERS),
        },
        "schema_version": DRAFT_SCHEMA_VERSION,
    }


def _prompt_text(bundle: dict[str, Any]) -> str:
    bundle_json = canonical_json_bytes(bundle).decode("utf-8")
    return (
        "You are a blind setwise evidence evaluator. No tools are available. "
        "Use only the embedded bundle; do not rely on external facts or prior conversations.\n\n"
        "For every item, compare the complete left and right top-3 evidence sets for the query. "
        "Judge direct support, usefulness for AI ideation, coverage/diversity, specificity, and "
        "catastrophic omissions. Do not reward length, fluency, or familiarity by themselves.\n\n"
        "Return exactly one JSON object and no Markdown. Copy bundle_sha256 and evaluator exactly. "
        "The root keys must be attestation, bundle_sha256, evaluator, judgments, schema_version. "
        "Each judgment must have exactly: item_id, winner, left_scores, right_scores, "
        "catastrophic_omission_side, evidence_refs, rationale. Each score object must contain "
        "coverage_diversity, direct_support, query_usefulness, specificity with integer 0, 1, or 2. "
        "evidence_refs must contain 1-4 objects with exactly side, paper_id, segment_id, support. "
        "Each support must contain 20-500 Unicode scalars and explain why that visible segment "
        "supports the score; it is not a source quote. A left/right winner needs a reference from "
        "the winning side; tie/both_bad needs at least one reference from each side. Rationale must "
        "be concise and use only visible evidence.\n\n"
        f"EMBEDDED_BUNDLE_JSON\n{bundle_json}\n"
    )


def _agent_file() -> bytes:
    return (
        "---\n"
        "name: local-ranking-tool-less-judge\n"
        "description: Evaluate one embedded local-ranking bundle without tools.\n"
        "tools: []\n"
        "subagents: []\n"
        "---\n\n"
        "Return only the requested JSON. You have no authority to read files, use tools, browse, "
        "delegate, or resume another session.\n"
    ).encode("utf-8")


def prepare(
    *,
    input_path: Path,
    formal_manifest_path: Path,
    selection_path: Path,
    protocol_path: Path,
    evaluator_protocol_path: Path,
    comparison_summary_path: Path,
    baseline_candidate_id: str,
    baseline_payload_path: Path,
    challenger_candidate_id: str,
    challenger_payload_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    expected_candidates = (
        FROZEN_BASELINE_CANDIDATE_ID,
        FROZEN_CHALLENGER_CANDIDATE_ID,
    )
    if (baseline_candidate_id, challenger_candidate_id) != expected_candidates:
        fail(
            "CANDIDATE_IDENTITY_MISMATCH",
            "v1.4 permits only the frozen BM25 baseline and E5 challenger",
            expected=list(expected_candidates),
            actual=[baseline_candidate_id, challenger_candidate_id],
        )
    input_value, input_bytes = _read_canonical_object(input_path, label="formal input")
    ranking_input = parse_ranking_input(input_value)
    formal_manifest, formal_manifest_bytes = _read_canonical_object(
        formal_manifest_path, label="formal input manifest"
    )
    selection, selection_bytes = _read_canonical_object(
        selection_path, label="selection manifest"
    )
    summary, summary_bytes = _read_canonical_object(
        comparison_summary_path, label="comparison summary"
    )
    try:
        protocol_bytes = protocol_path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", "v1.4 protocol is unreadable", error=str(exc))
    protocol_sha256 = sha256_bytes(protocol_bytes)
    try:
        evaluator_protocol_bytes = evaluator_protocol_path.read_bytes()
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT", "v1.5 evaluator protocol is unreadable", error=str(exc)
        )
    evaluator_protocol_sha256 = sha256_bytes(evaluator_protocol_bytes)
    baseline_records, baseline_bytes = _read_payload_records(baseline_payload_path)
    challenger_records, challenger_bytes = _read_payload_records(
        challenger_payload_path
    )
    formal_files = formal_manifest.get("files")
    if ranking_input.split == "spent_qualification":
        _expect_keys(
            formal_manifest,
            {"evidence_mode", "files", "schema_version", "source_bindings", "status"},
            label="spent qualification manifest",
        )
        expected_files = {
            "baseline-payloads.jsonl": sha256_bytes(baseline_bytes),
            "challenger-payloads.jsonl": sha256_bytes(challenger_bytes),
            "comparison-summary.json": sha256_bytes(summary_bytes),
            "input.json": sha256_bytes(input_bytes),
            "selection.json": sha256_bytes(selection_bytes),
        }
        if (
            formal_manifest.get("schema_version")
            != SPENT_QUALIFICATION_MANIFEST_VERSION
            or formal_manifest.get("status") != "spent_qualification_input_ready"
            or formal_manifest.get("evidence_mode") != "spent_diagnostic_only"
            or formal_files != expected_files
            or not isinstance(formal_manifest.get("source_bindings"), dict)
        ):
            fail(
                "INVALID_ARTIFACT",
                "Spent qualification manifest is incompatible with exact derived inputs",
            )
    else:
        if formal_manifest.get("schema_version") != FORMALIZATION_SCHEMA_VERSION:
            fail("UNSUPPORTED_SCHEMA", "Formal input manifest version is unsupported")
        expected_input_key = f"{ranking_input.split}/input.json"
        if not isinstance(formal_files, dict) or formal_files.get(
            expected_input_key
        ) != sha256_bytes(input_bytes):
            fail("HASH_MISMATCH", "Formal input manifest does not bind the exact input")
        expected_status = (
            "formal_operational_input_ready"
            if ranking_input.split == "operational"
            else "formal_inputs_ready_qrels_pending"
        )
        if formal_manifest.get("status") != expected_status:
            fail("INVALID_ARTIFACT", "Formal input manifest status is incompatible")
        formal_source = formal_manifest.get("source_binding")
        if not isinstance(formal_source, dict):
            fail("INVALID_ARTIFACT", "Formal input provenance binding is missing")
        if ranking_input.split == "operational" and (
            formal_source.get("selection_manifest_sha256")
            != sha256_bytes(selection_bytes)
            or formal_source.get("protocol_sha256") != protocol_sha256
        ):
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Operational input, selection, and v1.4 protocol are not hash-bound",
            )
    baseline_rendered = _validate_payload_set(baseline_records, ranking_input)
    challenger_rendered = _validate_payload_set(challenger_records, ranking_input)
    gate_evidence = _validate_summary(
        summary,
        candidate_ids=(baseline_candidate_id, challenger_candidate_id),
        payload_sets=(baseline_records, challenger_records),
    )
    case_strata = _selection_strata(selection, ranking_input)
    _, query_index = _input_indexes(ranking_input)
    query_ids = sorted(query_index)
    baseline_left: set[str] = set()
    for stratum in ("small", "medium", "large"):
        for query_kind in ("broad", "focused"):
            block = [
                query_id
                for query_id in query_ids
                if case_strata[query_index[query_id]["case"].case_id] == stratum
                and query_index[query_id]["query"].kind == query_kind
            ]
            if len(block) % 2 != 0 or not block:
                fail(
                    "INVALID_SELECTION",
                    "Each stratum/query-kind block must support balanced side assignment",
                    query_kind=query_kind,
                    stratum=stratum,
                    count=len(block),
                )
            side_order = sorted(
                block,
                key=lambda query_id: sha256_bytes(
                    (
                        f"{protocol_sha256}|{evaluator_protocol_sha256}|balanced-side|"
                        f"{stratum}|{query_kind}|{query_id}"
                    ).encode()
                ),
            )
            baseline_left.update(side_order[: len(side_order) // 2])
    assignments = []
    for query_id in query_ids:
        orientation_1 = (
            {"left": "baseline", "right": "challenger"}
            if query_id in baseline_left
            else {"left": "challenger", "right": "baseline"}
        )
        assignments.append(
            {
                "case_id": query_index[query_id]["case"].case_id,
                "orientation_1": orientation_1,
                "orientation_2": {
                    "left": orientation_1["right"],
                    "right": orientation_1["left"],
                },
                "query_id": query_id,
                "query_kind": query_index[query_id]["query"].kind,
                "stratum": case_strata[query_index[query_id]["case"].case_id],
            }
        )
    mapping = {
        "assignments": assignments,
        "candidates": {
            "baseline": {
                "candidate_id": baseline_candidate_id,
                "gate_evidence": gate_evidence[baseline_candidate_id],
                "payloads_sha256": sha256_bytes(baseline_bytes),
            },
            "challenger": {
                "candidate_id": challenger_candidate_id,
                "gate_evidence": gate_evidence[challenger_candidate_id],
                "payloads_sha256": sha256_bytes(challenger_bytes),
            },
        },
        "evidence_mode": (
            "formal_fresh"
            if ranking_input.split == "operational"
            else "spent_diagnostic_only"
        ),
        "evaluator_protocol_sha256": evaluator_protocol_sha256,
        "formal_manifest_sha256": sha256_bytes(formal_manifest_bytes),
        "input_sha256": sha256_bytes(input_bytes),
        "protocol_sha256": protocol_sha256,
        "schema_version": MAPPING_SCHEMA_VERSION,
        "selection_sha256": sha256_bytes(selection_bytes),
        "split": ranking_input.split,
        "summary_sha256": sha256_bytes(summary_bytes),
    }
    mapping_bytes = canonical_json_bytes(mapping)
    mapping_sha256 = sha256_bytes(mapping_bytes)
    files: dict[str, bytes] = {
        "private/mapping.json": mapping_bytes,
        "tool-less-agent.md": _agent_file(),
    }
    bundle_records: list[dict[str, Any]] = []
    assignment_by_query = {item["query_id"]: item for item in assignments}
    for evaluator_id, evaluator in EVALUATORS.items():
        item_order = sorted(
            query_ids,
            key=lambda query_id: sha256_bytes(
                (
                    f"{protocol_sha256}|{evaluator_protocol_sha256}|{evaluator_id}|"
                    f"item-order|{query_id}"
                ).encode()
            ),
        )
        for orientation in (1, 2):
            items = []
            for query_id in item_order:
                sides = assignment_by_query[query_id][f"orientation_{orientation}"]
                payload_by_role = {
                    "baseline": baseline_rendered[query_id],
                    "challenger": challenger_rendered[query_id],
                }
                items.append(
                    _bundle_item(
                        query_id=query_id,
                        query_entry=query_index[query_id],
                        left=payload_by_role[sides["left"]],
                        right=payload_by_role[sides["right"]],
                    )
                )
            bundle_without_hash = {
                "bundle_id": f"{evaluator_id}-orientation-{orientation}",
                "draft_contract": _draft_contract(),
                "evaluator": evaluator,
                "evaluator_protocol_sha256": evaluator_protocol_sha256,
                "items": items,
                "orientation": orientation,
                "protocol_sha256": protocol_sha256,
                "schema_version": BUNDLE_SCHEMA_VERSION,
                "source_binding": {
                    "evaluator_protocol_sha256": evaluator_protocol_sha256,
                    "formal_input_sha256": sha256_bytes(input_bytes),
                    "mapping_commitment_sha256": mapping_sha256,
                    "payload_set_sha256": sorted(
                        [sha256_bytes(baseline_bytes), sha256_bytes(challenger_bytes)]
                    ),
                },
            }
            bundle_sha256 = sha256_bytes(canonical_json_bytes(bundle_without_hash))
            bundle = {**bundle_without_hash, "bundle_sha256": bundle_sha256}
            bundle_bytes = canonical_json_bytes(bundle)
            lowered = bundle_bytes.lower()
            if any(text.encode() in lowered for text in FORBIDDEN_PUBLIC_TEXT):
                fail("BLINDING_FAILURE", "Public judge bundle exposes forbidden text")
            prefix = f"public/{evaluator_id}/orientation-{orientation}"
            prompt = _prompt_text(bundle).encode("utf-8")
            files[f"{prefix}/bundle.json"] = bundle_bytes
            files[f"{prefix}/prompt.txt"] = prompt
            bundle_records.append(
                {
                    "bundle_path": f"{prefix}/bundle.json",
                    "bundle_sha256": sha256_bytes(bundle_bytes),
                    "evaluator_id": evaluator_id,
                    "orientation": orientation,
                    "prompt_bytes": len(prompt),
                    "prompt_path": f"{prefix}/prompt.txt",
                    "prompt_sha256": sha256_bytes(prompt),
                }
            )
    manifest = {
        "bundles": bundle_records,
        "evidence_mode": mapping["evidence_mode"],
        "evaluator_protocol_sha256": evaluator_protocol_sha256,
        "file_hashes": {
            name: sha256_bytes(data) for name, data in sorted(files.items())
        },
        "mapping_sha256": mapping_sha256,
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "status": "ready_for_tool_less_evaluators",
    }
    files["manifest.json"] = canonical_json_bytes(manifest)
    for name, data in files.items():
        write_once(output_root / name, data)
    return manifest


def _score_object(value: Any, *, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        fail("INVALID_JUDGE_DRAFT", f"{label} must be an object")
    _expect_keys(value, SCORE_FIELDS, label=label)
    for key, score in value.items():
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or score not in {0, 1, 2}
        ):
            fail("INVALID_JUDGE_DRAFT", f"{label}.{key} must be 0, 1, or 2")
    return dict(sorted(value.items()))


def _validate_draft(
    bundle: dict[str, Any], draft: dict[str, Any]
) -> list[dict[str, Any]]:
    _expect_keys(
        draft,
        {"attestation", "bundle_sha256", "evaluator", "judgments", "schema_version"},
        label="judge draft",
    )
    if draft.get("schema_version") != DRAFT_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Judge draft schema version is unsupported")
    if draft.get("bundle_sha256") != bundle.get("bundle_sha256"):
        fail("HASH_MISMATCH", "Judge draft does not bind the exact bundle")
    if draft.get("evaluator") != bundle.get("evaluator"):
        fail("PROVENANCE_MISMATCH", "Judge evaluator profile differs from bundle")
    expected_attestation = _draft_contract()["attestation"]
    if draft.get("attestation") != expected_attestation:
        fail(
            "ISOLATION_ATTESTATION_FAILED", "Judge tool-less attestation is incomplete"
        )
    raw_judgments = draft.get("judgments")
    items = bundle.get("items")
    if not isinstance(raw_judgments, list) or not isinstance(items, list):
        fail("INVALID_JUDGE_DRAFT", "Judge items/judgments must be arrays")
    item_by_id = {item.get("item_id"): item for item in items if isinstance(item, dict)}
    if len(item_by_id) != len(items):
        fail("INVALID_JUDGE_BUNDLE", "Judge bundle item identities are invalid")
    parsed: dict[str, dict[str, Any]] = {}
    for raw in raw_judgments:
        if not isinstance(raw, dict):
            fail("INVALID_JUDGE_DRAFT", "Judgment must be an object")
        _expect_keys(
            raw,
            {
                "catastrophic_omission_side",
                "evidence_refs",
                "item_id",
                "left_scores",
                "rationale",
                "right_scores",
                "winner",
            },
            label="judgment",
        )
        item_id = raw.get("item_id")
        if (
            not isinstance(item_id, str)
            or item_id not in item_by_id
            or item_id in parsed
        ):
            fail(
                "INVALID_JUDGE_DRAFT",
                "Judgment item identity is invalid",
                item_id=item_id,
            )
        winner = raw.get("winner")
        if winner not in WINNERS:
            fail("INVALID_JUDGE_DRAFT", "Judgment winner is invalid", item_id=item_id)
        catastrophic = raw.get("catastrophic_omission_side")
        if catastrophic not in {"left", "right", "neither"}:
            fail(
                "INVALID_JUDGE_DRAFT",
                "Catastrophic omission side is invalid",
                item_id=item_id,
            )
        rationale = raw.get("rationale")
        if not isinstance(rationale, str) or not 1 <= len(rationale) <= 800:
            fail(
                "INVALID_JUDGE_DRAFT",
                "Judgment rationale length is invalid",
                item_id=item_id,
            )
        if any(text in rationale.casefold() for text in FORBIDDEN_PUBLIC_TEXT):
            fail(
                "BLINDING_FAILURE",
                "Judge rationale exposes forbidden candidate text",
                item_id=item_id,
            )
        evidence_items = raw.get("evidence_refs")
        if not isinstance(evidence_items, list) or not 1 <= len(evidence_items) <= 4:
            fail(
                "INVALID_JUDGE_DRAFT",
                "Judgment needs 1-4 evidence references",
                item_id=item_id,
            )
        visible: set[tuple[str, str, str]] = set()
        for side in ("left", "right"):
            for paper in item_by_id[item_id][side]["papers"]:
                for segment in paper["segments"]:
                    visible.add((side, paper["paper_id"], segment["segment_id"]))
        parsed_refs: list[dict[str, str]] = []
        evidence_sides: set[str] = set()
        seen_refs: set[tuple[str, str, str]] = set()
        for evidence_item in evidence_items:
            if not isinstance(evidence_item, dict):
                fail(
                    "INVALID_JUDGE_DRAFT",
                    "Evidence reference must be an object",
                    item_id=item_id,
                )
            _expect_keys(
                evidence_item,
                {"paper_id", "segment_id", "side", "support"},
                label="evidence reference",
            )
            side = evidence_item.get("side")
            paper_id = evidence_item.get("paper_id")
            segment_id = evidence_item.get("segment_id")
            support = evidence_item.get("support")
            key = (side, paper_id, segment_id)
            if (
                side not in {"left", "right"}
                or not isinstance(paper_id, str)
                or not isinstance(segment_id, str)
                or not isinstance(support, str)
                or support != support.strip()
                or not 20 <= len(support) <= 500
                or any(text in support.casefold() for text in FORBIDDEN_PUBLIC_TEXT)
                or key not in visible
                or key in seen_refs
            ):
                fail(
                    "INVALID_EVIDENCE_REFERENCE",
                    "Evidence reference is not unique visible evidence",
                    item_id=item_id,
                )
            seen_refs.add(key)
            evidence_sides.add(side)
            parsed_refs.append(dict(sorted(evidence_item.items())))
        required_sides = {winner} if winner in {"left", "right"} else {"left", "right"}
        if not required_sides.issubset(evidence_sides):
            fail(
                "INVALID_JUDGE_DRAFT",
                "Evidence references do not cover required sides",
                item_id=item_id,
            )
        parsed[item_id] = {
            "catastrophic_omission_side": catastrophic,
            "evidence_refs": parsed_refs,
            "item_id": item_id,
            "left_scores": _score_object(
                raw.get("left_scores"), label=f"{item_id}.left_scores"
            ),
            "rationale": rationale,
            "right_scores": _score_object(
                raw.get("right_scores"), label=f"{item_id}.right_scores"
            ),
            "winner": winner,
        }
    if set(parsed) != set(item_by_id):
        fail(
            "INCOMPLETE_JUDGE_DRAFT",
            "Judge draft does not cover the exact bundle",
            missing=sorted(set(item_by_id) - set(parsed)),
            unknown=sorted(set(parsed) - set(item_by_id)),
        )
    return [parsed[item["item_id"]] for item in items]


def finalize(
    *, bundle_path: Path, draft_path: Path, output_root: Path
) -> dict[str, Any]:
    bundle, bundle_bytes = _read_canonical_object(bundle_path, label="judge bundle")
    if bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Judge bundle schema version is unsupported")
    expected_bundle_hash = bundle.get("bundle_sha256")
    without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    if expected_bundle_hash != sha256_bytes(canonical_json_bytes(without_hash)):
        fail("HASH_MISMATCH", "Judge bundle self-hash is invalid")
    draft, draft_bytes = _read_draft(draft_path)
    judgments = _validate_draft(bundle, draft)
    trace = {
        "bundle_sha256": sha256_bytes(bundle_bytes),
        "draft_sha256": sha256_bytes(draft_bytes),
        "evaluator": bundle["evaluator"],
        "judgments": judgments,
        "orientation": bundle["orientation"],
        "schema_version": TRACE_SCHEMA_VERSION,
        "status": "pass",
    }
    trace_bytes = canonical_json_bytes(trace)
    result = {
        "bundle_sha256": sha256_bytes(bundle_bytes),
        "draft_sha256": sha256_bytes(draft_bytes),
        "judgment_count": len(judgments),
        "schema_version": TRACE_SCHEMA_VERSION,
        "status": "pass",
        "trace_sha256": sha256_bytes(trace_bytes),
    }
    write_once(output_root / "draft.json", draft_bytes)
    write_once(output_root / "trace.json", trace_bytes)
    write_json_once(output_root / "result.json", result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and validate blind setwise judges"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--input", type=Path, required=True)
    prepare_parser.add_argument("--formal-manifest", type=Path, required=True)
    prepare_parser.add_argument("--selection", type=Path, required=True)
    prepare_parser.add_argument("--protocol", type=Path, required=True)
    prepare_parser.add_argument("--evaluator-protocol", type=Path, required=True)
    prepare_parser.add_argument("--comparison-summary", type=Path, required=True)
    prepare_parser.add_argument("--baseline-candidate-id", required=True)
    prepare_parser.add_argument("--baseline-payloads", type=Path, required=True)
    prepare_parser.add_argument("--challenger-candidate-id", required=True)
    prepare_parser.add_argument("--challenger-payloads", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("--bundle", type=Path, required=True)
    finalize_parser.add_argument("--draft", type=Path, required=True)
    finalize_parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(
                input_path=args.input,
                formal_manifest_path=args.formal_manifest,
                selection_path=args.selection,
                protocol_path=args.protocol,
                evaluator_protocol_path=args.evaluator_protocol,
                comparison_summary_path=args.comparison_summary,
                baseline_candidate_id=args.baseline_candidate_id,
                baseline_payload_path=args.baseline_payloads,
                challenger_candidate_id=args.challenger_candidate_id,
                challenger_payload_path=args.challenger_payloads,
                output_root=args.output_root,
            )
        else:
            result = finalize(
                bundle_path=args.bundle,
                draft_path=args.draft,
                output_root=args.output_root,
            )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {
                "code": "OPERATIONAL_JUDGE_FAILED",
                "message": str(exc),
            }
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
