from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_json_bytes,
    resolve_repo_relative,
    sha256_bytes,
    write_json_once,
    write_once,
)
from .errors import HarnessError, fail
from .operational_judge import (
    BUNDLE_SCHEMA_VERSION,
    FORBIDDEN_PUBLIC_TEXT,
    SCORE_FIELDS,
    WINNERS,
)

ATOMIC_PACKET_SCHEMA_VERSION = "local-ranking-atomic-judge-packet-v2.0"
ATOMIC_PREPARATION_SCHEMA_VERSION = "local-ranking-atomic-preparation-v2.4"
LEGACY_ATOMIC_PREPARATION_SCHEMA_VERSIONS = {
    "local-ranking-atomic-preparation-v2.2",
    "local-ranking-atomic-preparation-v2.3",
}
ATOMIC_ATTEMPT_SCHEMA_VERSION = "local-ranking-atomic-attempt-v2.5"
LEGACY_ATOMIC_ATTEMPT_SCHEMA_VERSIONS = {
    "local-ranking-atomic-attempt-v2.3",
    "local-ranking-atomic-attempt-v2.4",
}
ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION = "local-ranking-atomic-orientation-trace-v2.5"
ATOMIC_ORIENTATION_RESULT_SCHEMA_VERSION = (
    "local-ranking-atomic-orientation-result-v2.3"
)
EXPECTED_ITEM_COUNT = 24
MAX_PHYSICAL_ATTEMPTS = 4
ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION = (
    "local-ranking-atomic-opencode-go-receipt-v3.0"
)
LEGACY_ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSIONS = {
    "local-ranking-atomic-opencode-go-receipt-v2.0"
}
ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION = (
    "local-ranking-atomic-opencode-go-execution-v2.1"
)
LEGACY_ATOMIC_EXECUTION_RESULT_SCHEMA_VERSIONS = {
    "local-ranking-atomic-opencode-go-execution-v2.0"
}
OPENCODE_GO_ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
APPROVED_ATOMIC_MODEL_ALIAS = "opencode-go/deepseek-v4-pro"
APPROVED_ATOMIC_EFFORTS = {"high", "max"}
SUBMIT_JUDGMENT_TOOL_NAME = "submit_judgment"
_SCORE_SCHEMA_FIELDS = (
    "coverage_diversity",
    "direct_support",
    "query_usefulness",
    "specificity",
)
SUBMIT_JUDGMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "catastrophic_omission_side": {
            "type": "string",
            "enum": ["left", "right", "neither"],
        },
        "evidence_handles": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["L1", "L2", "L3", "R1", "R2", "R3"],
            },
        },
        "left_scores": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                field: {"type": "integer", "enum": [0, 1, 2]}
                for field in _SCORE_SCHEMA_FIELDS
            },
            "required": list(_SCORE_SCHEMA_FIELDS),
        },
        "rationale": {"type": "string"},
        "right_scores": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                field: {"type": "integer", "enum": [0, 1, 2]}
                for field in _SCORE_SCHEMA_FIELDS
            },
            "required": list(_SCORE_SCHEMA_FIELDS),
        },
        "winner": {
            "type": "string",
            "enum": ["left", "right", "tie", "both_bad"],
        },
    },
    "required": [
        "catastrophic_omission_side",
        "evidence_handles",
        "left_scores",
        "rationale",
        "right_scores",
        "winner",
    ],
}
SUBMIT_JUDGMENT_TOOL = {
    "type": "function",
    "function": {
        "name": SUBMIT_JUDGMENT_TOOL_NAME,
        "description": "Submit the final blind evidence-set judgment for this single item.",
        "parameters": SUBMIT_JUDGMENT_SCHEMA,
    },
}
SUBMIT_JUDGMENT_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": SUBMIT_JUDGMENT_TOOL_NAME},
}
RESPONSE_KEYS = {
    "catastrophic_omission_side",
    "evidence_handles",
    "left_scores",
    "rationale",
    "right_scores",
    "winner",
}


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


def _validate_source_bundle(bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Atomic preparation requires a v1.2 source bundle")
    without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    if bundle.get("bundle_sha256") != sha256_bytes(canonical_json_bytes(without_hash)):
        fail("HASH_MISMATCH", "Source bundle self-hash is invalid")
    if bundle.get("orientation") not in {1, 2}:
        fail("INVALID_SOURCE_BUNDLE", "Source bundle orientation is invalid")
    if not isinstance(bundle.get("evaluator"), dict):
        fail("INVALID_SOURCE_BUNDLE", "Source bundle evaluator is missing")
    items = bundle.get("items")
    if not isinstance(items, list) or len(items) != EXPECTED_ITEM_COUNT:
        fail(
            "INVALID_SOURCE_BUNDLE",
            "Atomic preparation requires exactly 24 source items",
        )
    item_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            fail("INVALID_SOURCE_BUNDLE", "Source bundle item must be an object")
        _expect_keys(
            item,
            {"case_id", "item_id", "left", "query", "right"},
            label="source bundle item",
        )
        item_id = item.get("item_id")
        case_id = item.get("case_id")
        if (
            not isinstance(item_id, str)
            or not item_id
            or item_id in item_ids
            or not isinstance(case_id, str)
            or not case_id
        ):
            fail("INVALID_SOURCE_BUNDLE", "Source item identity is invalid")
        item_ids.add(item_id)


def _public_side(
    raw_side: Any, *, side: str
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    if not isinstance(raw_side, dict):
        fail("INVALID_SOURCE_BUNDLE", f"Source {side} side must be an object")
    _expect_keys(raw_side, {"papers"}, label=f"source {side} side")
    papers = raw_side.get("papers")
    if not isinstance(papers, list) or len(papers) != 3:
        fail("INVALID_SOURCE_BUNDLE", f"Source {side} side must contain top-3")
    public_evidence = []
    handle_map: dict[str, dict[str, str]] = {}
    prefix = "L" if side == "left" else "R"
    for index, paper in enumerate(papers, start=1):
        if not isinstance(paper, dict):
            fail("INVALID_SOURCE_BUNDLE", "Source paper must be an object")
        _expect_keys(
            paper,
            {"paper_id", "segments", "title"},
            label="source paper",
        )
        segments = paper.get("segments")
        if not isinstance(segments, list) or len(segments) != 1:
            fail(
                "INVALID_SOURCE_BUNDLE",
                "Atomic handle contract requires one segment per paper",
            )
        segment = segments[0]
        if not isinstance(segment, dict):
            fail("INVALID_SOURCE_BUNDLE", "Source segment must be an object")
        _expect_keys(
            segment,
            {"content_type", "segment_id", "source_start", "text"},
            label="source segment",
        )
        handle = f"{prefix}{index}"
        paper_id = paper.get("paper_id")
        segment_id = segment.get("segment_id")
        if (
            not isinstance(paper_id, str)
            or not paper_id
            or not isinstance(segment_id, str)
            or not segment_id
            or not isinstance(paper.get("title"), str)
            or not isinstance(segment.get("content_type"), str)
            or not isinstance(segment.get("text"), str)
        ):
            fail("INVALID_SOURCE_BUNDLE", "Source evidence fields are invalid")
        public_evidence.append(
            {
                "content_type": segment["content_type"],
                "handle": handle,
                "text": segment["text"],
                "title": paper["title"],
            }
        )
        handle_map[handle] = {
            "paper_id": paper_id,
            "segment_id": segment_id,
            "side": side,
        }
    return {"evidence": public_evidence}, handle_map


def _public_packet(
    item: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    query = item.get("query")
    if not isinstance(query, dict):
        fail("INVALID_SOURCE_BUNDLE", "Source query must be an object")
    _expect_keys(query, {"kind", "text"}, label="source query")
    if not isinstance(query.get("kind"), str) or not isinstance(query.get("text"), str):
        fail("INVALID_SOURCE_BUNDLE", "Source query fields are invalid")
    left, left_map = _public_side(item.get("left"), side="left")
    right, right_map = _public_side(item.get("right"), side="right")
    packet = {
        "item": {"left": left, "query": query, "right": right},
        "response_contract": {
            "catastrophic_omission_side": ["left", "right", "neither"],
            "evidence_handle_count": [1, 4],
            "score_fields": sorted(SCORE_FIELDS),
            "score_values": [0, 1, 2],
            "winner": sorted(WINNERS),
        },
        "schema_version": ATOMIC_PACKET_SCHEMA_VERSION,
    }
    return packet, {**left_map, **right_map}


def _prompt_text(packet: dict[str, Any]) -> str:
    packet_json = canonical_json_bytes(packet).decode("utf-8")
    return (
        "You are a blind setwise evidence evaluator. No external or retrieval tools "
        "are available; the only available tool is submit_judgment, which you must use "
        "to submit the final judgment for this single item. Use only the embedded "
        "single-item packet; do not use external facts or prior conversations.\n\n"
        "Compare the complete left and right top-3 evidence sets for the query. Judge direct "
        "support, usefulness for AI ideation, coverage/diversity, specificity, and catastrophic "
        "omissions. Do not reward length, fluency, or familiarity by themselves.\n\n"
        "Call submit_judgment exactly once. Its arguments must contain exactly "
        "catastrophic_omission_side, evidence_handles, left_scores, rationale, right_scores, "
        "winner. Each score object must contain coverage_diversity, direct_support, "
        "query_usefulness, specificity with integer 0, 1, or 2. winner must be left, right, "
        "tie, or both_bad. catastrophic_omission_side must be left, right, or neither. "
        "evidence_handles must contain 1-4 unique visible handles. A left/right winner needs "
        "at least one handle from the winning side; tie/both_bad needs at least one from each "
        "side. rationale must be a non-empty string and use only visible evidence. "
        "Do not name or infer retrieval methods, ground-truth labels, or prior results.\n\n"
        f"EMBEDDED_ATOMIC_PACKET_JSON\n{packet_json}"
    )


def _effective_evaluator(
    source_evaluator: Any, *, reasoning_effort: str | None
) -> dict[str, str]:
    expected_keys = {"harness", "model_alias", "provider", "reasoning_effort"}
    if not isinstance(source_evaluator, dict) or set(source_evaluator) != expected_keys:
        fail("INVALID_EVALUATOR", "Source evaluator has an invalid closed schema")
    if (
        source_evaluator.get("harness") != "opencode-go-chat-completions"
        or source_evaluator.get("provider") != "opencode-go"
        or source_evaluator.get("model_alias") != APPROVED_ATOMIC_MODEL_ALIAS
        or source_evaluator.get("reasoning_effort") not in APPROVED_ATOMIC_EFFORTS
    ):
        fail(
            "INVALID_EVALUATOR",
            "Atomic calibration requires the approved OpenCode Go DeepSeek Pro profile",
        )
    effective_effort = (
        source_evaluator["reasoning_effort"]
        if reasoning_effort is None
        else reasoning_effort
    )
    if effective_effort not in APPROVED_ATOMIC_EFFORTS:
        fail("INVALID_EVALUATOR", "Atomic reasoning effort must be high or max")
    return {**source_evaluator, "reasoning_effort": effective_effort}


def prepare_atomic(
    *,
    bundle_path: Path,
    replicate_id: str,
    output_root: Path,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(replicate_id, str)
        or not replicate_id
        or replicate_id != replicate_id.strip()
    ):
        fail("INVALID_REPLICATE_ID", "Replicate ID must be a non-empty trimmed string")
    bundle, bundle_bytes = _read_canonical_object(bundle_path, label="source bundle")
    _validate_source_bundle(bundle)
    evaluator = _effective_evaluator(
        bundle["evaluator"], reasoning_effort=reasoning_effort
    )
    files: dict[str, bytes] = {}
    calls = []
    for sequence, item in enumerate(bundle["items"], start=1):
        packet, handle_map = _public_packet(item)
        packet_bytes = canonical_json_bytes(packet)
        lowered = packet_bytes.lower()
        if any(text.encode() in lowered for text in FORBIDDEN_PUBLIC_TEXT):
            fail("BLINDING_FAILURE", "Atomic packet exposes forbidden candidate text")
        prompt_bytes = _prompt_text(packet).encode("utf-8")
        prefix = f"public/call-{sequence:03d}"
        packet_path = f"{prefix}/packet.json"
        prompt_path = f"{prefix}/prompt.txt"
        files[packet_path] = packet_bytes
        files[prompt_path] = prompt_bytes
        calls.append(
            {
                "call_id": f"call-{sequence:03d}",
                "case_id": item["case_id"],
                "evidence_handle_map": handle_map,
                "item_id": item["item_id"],
                "packet_bytes": len(packet_bytes),
                "packet_path": packet_path,
                "packet_sha256": sha256_bytes(packet_bytes),
                "prompt_bytes": len(prompt_bytes),
                "prompt_path": prompt_path,
                "prompt_sha256": sha256_bytes(prompt_bytes),
                "sequence": sequence,
            }
        )
    manifest = {
        "call_count": len(calls),
        "calls": calls,
        "evaluator": evaluator,
        "orientation": bundle["orientation"],
        "replicate_id": replicate_id,
        "schema_version": ATOMIC_PREPARATION_SCHEMA_VERSION,
        "source_evaluator": bundle["evaluator"],
        "source_bundle_file_sha256": sha256_bytes(bundle_bytes),
        "source_bundle_self_sha256": bundle["bundle_sha256"],
        "status": "ready_for_atomic_execution",
    }
    files["private/manifest.json"] = canonical_json_bytes(manifest)
    for relative_path, data in files.items():
        write_once(output_root / relative_path, data)
    return manifest


def _load_manifest(
    manifest_path: Path,
) -> tuple[dict[str, Any], Path, dict[int, dict[str, Any]]]:
    manifest, _ = _read_canonical_object(manifest_path, label="atomic manifest")
    _expect_keys(
        manifest,
        {
            "call_count",
            "calls",
            "evaluator",
            "orientation",
            "replicate_id",
            "schema_version",
            "source_bundle_file_sha256",
            "source_bundle_self_sha256",
            "source_evaluator",
            "status",
        },
        label="atomic manifest",
    )
    calls = manifest.get("calls")
    if (
        manifest.get("schema_version")
        not in {
            ATOMIC_PREPARATION_SCHEMA_VERSION,
            *LEGACY_ATOMIC_PREPARATION_SCHEMA_VERSIONS,
        }
        or manifest.get("status") != "ready_for_atomic_execution"
        or manifest.get("call_count") != EXPECTED_ITEM_COUNT
        or not isinstance(calls, list)
        or len(calls) != EXPECTED_ITEM_COUNT
    ):
        fail("INVALID_ATOMIC_MANIFEST", "Atomic manifest is incomplete")
    evaluator = manifest.get("evaluator")
    effective = _effective_evaluator(
        manifest.get("source_evaluator"),
        reasoning_effort=(
            evaluator.get("reasoning_effort") if isinstance(evaluator, dict) else None
        ),
    )
    if evaluator != effective:
        fail("INVALID_ATOMIC_MANIFEST", "Atomic effective evaluator is invalid")
    by_sequence: dict[int, dict[str, Any]] = {}
    seen_call_ids: set[str] = set()
    seen_item_ids: set[str] = set()
    for call in calls:
        if not isinstance(call, dict):
            fail("INVALID_ATOMIC_MANIFEST", "Atomic call must be an object")
        _expect_keys(
            call,
            {
                "call_id",
                "case_id",
                "evidence_handle_map",
                "item_id",
                "packet_bytes",
                "packet_path",
                "packet_sha256",
                "prompt_bytes",
                "prompt_path",
                "prompt_sha256",
                "sequence",
            },
            label="atomic call",
        )
        sequence = call.get("sequence")
        call_id = call.get("call_id")
        item_id = call.get("item_id")
        handle_map = call.get("evidence_handle_map")
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence not in range(1, EXPECTED_ITEM_COUNT + 1)
            or sequence in by_sequence
            or call_id != f"call-{sequence:03d}"
            or call_id in seen_call_ids
            or not isinstance(item_id, str)
            or not item_id
            or item_id in seen_item_ids
        ):
            fail("INVALID_ATOMIC_MANIFEST", "Atomic call identity is invalid")
        expected_handles = {
            f"{prefix}{index}" for prefix in ("L", "R") for index in range(1, 4)
        }
        if not isinstance(handle_map, dict) or set(handle_map) != expected_handles:
            fail("INVALID_ATOMIC_MANIFEST", "Atomic evidence handle map is invalid")
        for handle, binding in handle_map.items():
            expected_side = "left" if handle.startswith("L") else "right"
            if (
                not isinstance(binding, dict)
                or set(binding) != {"paper_id", "segment_id", "side"}
                or binding.get("side") != expected_side
                or not isinstance(binding.get("paper_id"), str)
                or not binding.get("paper_id")
                or not isinstance(binding.get("segment_id"), str)
                or not binding.get("segment_id")
            ):
                fail(
                    "INVALID_ATOMIC_MANIFEST",
                    "Atomic evidence handle binding is invalid",
                )
        for path_key in ("packet_path", "prompt_path"):
            if not isinstance(call.get(path_key), str) or not call.get(path_key):
                fail("INVALID_ATOMIC_MANIFEST", "Atomic call path is invalid")
        for size_key in ("packet_bytes", "prompt_bytes"):
            size = call.get(size_key)
            if isinstance(size, bool) or not isinstance(size, int) or size < 1:
                fail("INVALID_ATOMIC_MANIFEST", "Atomic call byte size is invalid")
        for hash_key in ("packet_sha256", "prompt_sha256"):
            digest = call.get(hash_key)
            if not isinstance(digest, str) or len(digest) != 64:
                fail("INVALID_ATOMIC_MANIFEST", "Atomic call hash is invalid")
        by_sequence[sequence] = call
        seen_call_ids.add(call_id)
        seen_item_ids.add(item_id)
    if set(by_sequence) != set(range(1, EXPECTED_ITEM_COUNT + 1)):
        fail("INVALID_ATOMIC_MANIFEST", "Atomic call sequence is incomplete")
    artifact_root = manifest_path.resolve().parent.parent
    return manifest, artifact_root, by_sequence


def _load_call_packet(
    *, artifact_root: Path, call: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    packet_path = resolve_repo_relative(
        artifact_root, call["packet_path"], label="atomic packet path"
    )
    packet, packet_bytes = _read_canonical_object(packet_path, label="atomic packet")
    prompt_path = resolve_repo_relative(
        artifact_root, call["prompt_path"], label="atomic prompt path"
    )
    try:
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", "Atomic prompt is unreadable", error=str(exc))
    if (
        packet.get("schema_version") != ATOMIC_PACKET_SCHEMA_VERSION
        or len(packet_bytes) != call.get("packet_bytes")
        or sha256_bytes(packet_bytes) != call.get("packet_sha256")
        or len(prompt_bytes) != call.get("prompt_bytes")
        or sha256_bytes(prompt_bytes) != call.get("prompt_sha256")
        or prompt_bytes != _prompt_text(packet).encode("utf-8")
    ):
        fail("HASH_MISMATCH", "Atomic packet or prompt differs from manifest")
    return packet, packet_bytes


def _score_object(value: Any, *, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        fail("INVALID_ATOMIC_RESPONSE", f"{label} must be an object")
    _expect_keys(value, SCORE_FIELDS, label=label)
    for key, score in value.items():
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or score not in {0, 1, 2}
        ):
            fail("INVALID_ATOMIC_RESPONSE", f"{label}.{key} must be 0, 1, or 2")
    return dict(sorted(value.items()))


def _validate_response(
    *,
    handle_map: dict[str, dict[str, str]],
    response: Any,
) -> dict[str, Any]:
    if not isinstance(response, dict):
        fail("INVALID_ATOMIC_RESPONSE", "Atomic response must be one JSON object")
    _expect_keys(response, RESPONSE_KEYS, label="atomic response")
    winner = response.get("winner")
    if winner not in WINNERS:
        fail("INVALID_ATOMIC_RESPONSE", "Atomic winner is invalid")
    catastrophic = response.get("catastrophic_omission_side")
    if catastrophic not in {"left", "right", "neither"}:
        fail("INVALID_ATOMIC_RESPONSE", "Catastrophic omission side is invalid")
    rationale = response.get("rationale")
    if not isinstance(rationale, str) or not rationale:
        fail("INVALID_ATOMIC_RESPONSE", "Atomic rationale must be a non-empty string")
    if any(text in rationale.casefold() for text in FORBIDDEN_PUBLIC_TEXT):
        fail("BLINDING_FAILURE", "Atomic rationale exposes forbidden candidate text")
    handles = response.get("evidence_handles")
    if not isinstance(handles, list) or not 1 <= len(handles) <= 4:
        fail("INVALID_EVIDENCE_HANDLE", "Atomic response needs 1-4 evidence handles")
    if any(not isinstance(handle, str) for handle in handles) or len(
        set(handles)
    ) != len(handles):
        fail("INVALID_EVIDENCE_HANDLE", "Evidence handles must be unique strings")
    if any(handle not in handle_map for handle in handles):
        fail("INVALID_EVIDENCE_HANDLE", "Evidence handle is not visible in this packet")
    evidence_sides = {handle_map[handle]["side"] for handle in handles}
    required_sides = {winner} if winner in {"left", "right"} else {"left", "right"}
    if not required_sides.issubset(evidence_sides):
        fail(
            "INVALID_EVIDENCE_HANDLE",
            "Evidence handles do not cover the required side or sides",
        )
    return {
        "catastrophic_omission_side": catastrophic,
        "evidence_handles": handles,
        "evidence_refs": [
            {"handle": handle, **handle_map[handle]} for handle in handles
        ],
        "left_scores": _score_object(response.get("left_scores"), label="left_scores"),
        "rationale": rationale,
        "right_scores": _score_object(
            response.get("right_scores"), label="right_scores"
        ),
        "winner": winner,
    }


def _assess_response(
    *, response_bytes: bytes, handle_map: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        response = json.loads(response_bytes)
        judgment = _validate_response(handle_map=handle_map, response=response)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        error = HarnessError(
            "INVALID_ATOMIC_RESPONSE",
            "Atomic response is not valid UTF-8 JSON",
            {"error": str(exc)},
        )
        return None, {"error": error.as_dict(), "status": "fail"}
    except HarnessError as exc:
        return None, {"error": exc.as_dict(), "status": "fail"}
    return judgment, {"error": None, "status": "pass"}


def _validate_execution_receipt(
    *,
    receipt_path: Path,
    response_bytes: bytes,
    manifest: dict[str, Any],
    manifest_file_sha256: str,
    call: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    receipt, receipt_bytes = _read_canonical_object(
        receipt_path, label="atomic execution receipt"
    )
    evaluator = manifest["evaluator"]
    schema_version = receipt.get("schema_version")
    if schema_version == ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION:
        expected_receipt_keys = {
            "call_binding",
            "diagnostics",
            "endpoint",
            "files",
            "http_status",
            "identity",
            "preparation_manifest_sha256",
            "provider",
            "request_sha256",
            "schema_version",
            "status",
            "tool",
            "transport_qualification",
            "usage",
        }
        expected_identity_keys = {
            "cost",
            "created_first",
            "created_last",
            "finish_reason",
            "model",
            "provider_response_id",
            "tool_call_id",
        }
        expected_qualification = {
            "forced_tool_call_accepted": True,
            "reasoning_effort_requested": evaluator["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        }
        allowed_finish_reasons = {"stop", "tool_calls"}
        expected_tool = {
            "name": SUBMIT_JUDGMENT_TOOL_NAME,
            "schema_sha256": sha256_bytes(canonical_json_bytes(SUBMIT_JUDGMENT_TOOL)),
        }
    elif schema_version in LEGACY_ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSIONS:
        expected_receipt_keys = {
            "call_binding",
            "diagnostics",
            "endpoint",
            "files",
            "http_status",
            "identity",
            "preparation_manifest_sha256",
            "provider",
            "request_sha256",
            "schema_version",
            "status",
            "transport_qualification",
            "usage",
        }
        expected_identity_keys = {
            "cost",
            "created_first",
            "created_last",
            "finish_reason",
            "model",
            "provider_response_id",
        }
        expected_qualification = {
            "json_object_accepted": True,
            "reasoning_effort_requested": evaluator["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        }
        allowed_finish_reasons = {"stop"}
        expected_tool = None
    else:
        fail(
            "INVALID_EXECUTION_RECEIPT",
            "Atomic execution receipt schema is unsupported",
        )
    _expect_keys(
        receipt,
        expected_receipt_keys,
        label="atomic execution receipt",
    )
    binding = receipt.get("call_binding")
    if not isinstance(binding, dict):
        fail("INVALID_EXECUTION_RECEIPT", "Atomic call binding is missing")
    _expect_keys(
        binding,
        {
            "atomic_manifest_sha256",
            "call_id",
            "kind",
            "orientation",
            "prompt_sha256",
            "replicate_id",
            "sequence",
        },
        label="atomic receipt call binding",
    )
    identity = receipt.get("identity")
    if not isinstance(identity, dict):
        fail("INVALID_EXECUTION_RECEIPT", "Provider identity is missing")
    _expect_keys(
        identity,
        expected_identity_keys,
        label="atomic receipt provider identity",
    )
    qualification = receipt.get("transport_qualification")
    if not isinstance(qualification, dict):
        fail("INVALID_EXECUTION_RECEIPT", "Transport qualification is missing")
    _expect_keys(
        qualification,
        set(expected_qualification),
        label="atomic receipt transport qualification",
    )
    files = receipt.get("files")
    response_sha256 = sha256_bytes(response_bytes)
    provider_response_id = identity.get("provider_response_id")
    tool_call_id = identity.get("tool_call_id")
    request_sha256 = receipt.get("request_sha256")
    preparation_sha256 = receipt.get("preparation_manifest_sha256")
    if (
        receipt.get("status") != "pass"
        or receipt.get("provider") != "opencode-go"
        or receipt.get("endpoint") != OPENCODE_GO_ENDPOINT
        or receipt.get("http_status") != 200
        or not isinstance(files, dict)
        or files.get("response.json") != response_sha256
        or any(
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or len(digest) != 64
            for name, digest in files.items()
        )
        or not isinstance(preparation_sha256, str)
        or len(preparation_sha256) != 64
        or not isinstance(request_sha256, str)
        or len(request_sha256) != 64
        or binding
        != {
            "atomic_manifest_sha256": manifest_file_sha256,
            "call_id": call["call_id"],
            "kind": "atomic",
            "orientation": manifest["orientation"],
            "prompt_sha256": call["prompt_sha256"],
            "replicate_id": manifest["replicate_id"],
            "sequence": call["sequence"],
        }
        or identity.get("finish_reason") not in allowed_finish_reasons
        or identity.get("model") != evaluator["model_alias"].rsplit("/", 1)[-1]
        or not isinstance(provider_response_id, str)
        or not provider_response_id
        or qualification != expected_qualification
        or (expected_tool is not None and receipt.get("tool") != expected_tool)
        or (
            expected_tool is not None
            and (not isinstance(tool_call_id, str) or not tool_call_id)
        )
    ):
        fail(
            "INVALID_EXECUTION_RECEIPT",
            "Execution receipt does not bind this atomic response",
        )
    return receipt, receipt_bytes


def _validate_execution_result(
    *,
    result_path: Path,
    manifest: dict[str, Any],
    manifest_file_sha256: str,
    call: dict[str, Any],
    expected_status: str,
    evidence_root: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    result, result_bytes = _read_canonical_object(
        result_path, label="atomic execution result"
    )
    _expect_keys(
        result,
        {
            "call_binding",
            "error",
            "files",
            "preparation_manifest_sha256",
            "receipt_sha256",
            "request_sha256",
            "schema_version",
            "status",
        },
        label="atomic execution result",
    )
    expected_binding = {
        "atomic_manifest_sha256": manifest_file_sha256,
        "call_id": call["call_id"],
        "kind": "atomic",
        "orientation": manifest["orientation"],
        "prompt_sha256": call["prompt_sha256"],
        "replicate_id": manifest["replicate_id"],
        "sequence": call["sequence"],
    }
    files = result.get("files")
    request_sha256 = result.get("request_sha256")
    preparation_sha256 = result.get("preparation_manifest_sha256")
    if (
        result.get("schema_version")
        not in {
            ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION,
            *LEGACY_ATOMIC_EXECUTION_RESULT_SCHEMA_VERSIONS,
        }
        or result.get("status") != expected_status
        or result.get("call_binding") != expected_binding
        or not isinstance(files, dict)
        or not files
        or any(
            not isinstance(name, str)
            or not name
            or Path(name).name != name
            or not isinstance(digest, str)
            or len(digest) != 64
            for name, digest in files.items()
        )
        or not isinstance(request_sha256, str)
        or len(request_sha256) != 64
        or not isinstance(preparation_sha256, str)
        or len(preparation_sha256) != 64
    ):
        fail(
            "INVALID_EXECUTION_RESULT",
            "Execution result does not bind this atomic call",
        )
    resolved_evidence_root = (
        result_path.parent if evidence_root is None else evidence_root
    )
    for name, digest in files.items():
        evidence_path = resolved_evidence_root / name
        try:
            evidence_bytes = evidence_path.read_bytes()
        except OSError as exc:
            fail(
                "MISSING_ARTIFACT",
                "Execution result evidence is missing",
                file=name,
                error=str(exc),
            )
        if sha256_bytes(evidence_bytes) != digest:
            fail("HASH_MISMATCH", "Execution result evidence changed", file=name)
    error = result.get("error")
    receipt_sha256 = result.get("receipt_sha256")
    if expected_status == "pass":
        if (
            error is not None
            or not isinstance(receipt_sha256, str)
            or len(receipt_sha256) != 64
            or files.get("receipt.json") != receipt_sha256
            or "response.json" not in files
        ):
            fail("INVALID_EXECUTION_RESULT", "Successful execution result is invalid")
    elif (
        not isinstance(error, dict)
        or not isinstance(error.get("code"), str)
        or not error.get("code")
        or not isinstance(error.get("message"), str)
        or not error.get("message")
        or receipt_sha256 is not None
        or "receipt.json" in files
        or "response.json" in files
    ):
        fail("INVALID_EXECUTION_RESULT", "Failed execution result is invalid")
    return result, result_bytes


def _copy_execution_evidence(
    *, result: dict[str, Any], source_root: Path, output_root: Path
) -> None:
    for name in sorted(result["files"]):
        try:
            data = (source_root / name).read_bytes()
        except OSError as exc:
            fail(
                "MISSING_ARTIFACT",
                "Execution evidence disappeared before recording",
                file=name,
                error=str(exc),
            )
        write_once(output_root / "execution-evidence" / name, data)


def record_attempt(
    *,
    manifest_path: Path,
    call_sequence: int,
    attempt_number: int,
    response_path: Path,
    execution_receipt_path: Path,
    execution_result_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    if (
        isinstance(attempt_number, bool)
        or not isinstance(attempt_number, int)
        or attempt_number not in range(1, MAX_PHYSICAL_ATTEMPTS + 1)
    ):
        fail(
            "ATTEMPT_LIMIT_EXCEEDED",
            f"Physical attempt number must be 1-{MAX_PHYSICAL_ATTEMPTS}",
        )
    manifest, artifact_root, calls = _load_manifest(manifest_path)
    manifest_file_sha256 = sha256_bytes(manifest_path.read_bytes())
    call = calls.get(call_sequence)
    if call is None:
        fail("UNKNOWN_LOGICAL_CALL", "Logical call sequence is not in the manifest")
    _load_call_packet(artifact_root=artifact_root, call=call)
    try:
        response_bytes = response_path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", "Atomic raw response is unreadable", error=str(exc))
    judgment, validation = _assess_response(
        response_bytes=response_bytes,
        handle_map=call["evidence_handle_map"],
    )
    receipt, receipt_bytes = _validate_execution_receipt(
        receipt_path=execution_receipt_path,
        response_bytes=response_bytes,
        manifest=manifest,
        manifest_file_sha256=manifest_file_sha256,
        call=call,
    )
    execution_result, execution_result_bytes = _validate_execution_result(
        result_path=execution_result_path,
        manifest=manifest,
        manifest_file_sha256=manifest_file_sha256,
        call=call,
        expected_status="pass",
    )
    if (
        execution_result["receipt_sha256"] != sha256_bytes(receipt_bytes)
        or execution_result["request_sha256"] != receipt["request_sha256"]
        or execution_result["files"].get("response.json")
        != sha256_bytes(response_bytes)
    ):
        fail("HASH_MISMATCH", "Execution result and receipt do not match")
    outcome = {
        "attempt_number": attempt_number,
        "call_id": call["call_id"],
        "case_id": call["case_id"],
        "evaluator": manifest["evaluator"],
        "execution_receipt_sha256": sha256_bytes(receipt_bytes),
        "execution_result_sha256": sha256_bytes(execution_result_bytes),
        "execution_status": "pass",
        "item_id": call["item_id"],
        "judgment": judgment,
        "orientation": manifest["orientation"],
        "packet_sha256": call["packet_sha256"],
        "prompt_sha256": call["prompt_sha256"],
        "provider_response_id": receipt["identity"]["provider_response_id"],
        "raw_response_sha256": sha256_bytes(response_bytes),
        "replicate_id": manifest["replicate_id"],
        "request_sha256": receipt["request_sha256"],
        "schema_version": ATOMIC_ATTEMPT_SCHEMA_VERSION,
        "status": "valid" if judgment is not None else "invalid",
        "validation": validation,
    }
    write_once(output_root / "raw-response.bin", response_bytes)
    write_once(output_root / "execution-receipt.json", receipt_bytes)
    write_once(output_root / "execution-result.json", execution_result_bytes)
    _copy_execution_evidence(
        result=execution_result,
        source_root=execution_result_path.parent,
        output_root=output_root,
    )
    write_json_once(output_root / "attempt.json", outcome)
    return outcome


def record_failed_attempt(
    *,
    manifest_path: Path,
    call_sequence: int,
    attempt_number: int,
    execution_result_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    if (
        isinstance(attempt_number, bool)
        or not isinstance(attempt_number, int)
        or attempt_number not in range(1, MAX_PHYSICAL_ATTEMPTS + 1)
    ):
        fail(
            "ATTEMPT_LIMIT_EXCEEDED",
            f"Physical attempt number must be 1-{MAX_PHYSICAL_ATTEMPTS}",
        )
    manifest, artifact_root, calls = _load_manifest(manifest_path)
    manifest_file_sha256 = sha256_bytes(manifest_path.read_bytes())
    call = calls.get(call_sequence)
    if call is None:
        fail("UNKNOWN_LOGICAL_CALL", "Logical call sequence is not in the manifest")
    _load_call_packet(artifact_root=artifact_root, call=call)
    execution_result, execution_result_bytes = _validate_execution_result(
        result_path=execution_result_path,
        manifest=manifest,
        manifest_file_sha256=manifest_file_sha256,
        call=call,
        expected_status="fail",
    )
    validation = {"error": execution_result["error"], "status": "fail"}
    outcome = {
        "attempt_number": attempt_number,
        "call_id": call["call_id"],
        "case_id": call["case_id"],
        "evaluator": manifest["evaluator"],
        "execution_receipt_sha256": None,
        "execution_result_sha256": sha256_bytes(execution_result_bytes),
        "execution_status": "fail",
        "item_id": call["item_id"],
        "judgment": None,
        "orientation": manifest["orientation"],
        "packet_sha256": call["packet_sha256"],
        "prompt_sha256": call["prompt_sha256"],
        "provider_response_id": None,
        "raw_response_sha256": None,
        "replicate_id": manifest["replicate_id"],
        "request_sha256": execution_result["request_sha256"],
        "schema_version": ATOMIC_ATTEMPT_SCHEMA_VERSION,
        "status": "invalid",
        "validation": validation,
    }
    write_once(output_root / "execution-result.json", execution_result_bytes)
    _copy_execution_evidence(
        result=execution_result,
        source_root=execution_result_path.parent,
        output_root=output_root,
    )
    write_json_once(output_root / "attempt.json", outcome)
    return outcome


def _validate_attempt(
    *,
    attempt_path: Path,
    manifest: dict[str, Any],
    artifact_root: Path,
    calls_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], bytes]:
    attempt, attempt_bytes = _read_canonical_object(
        attempt_path, label="atomic attempt"
    )
    _expect_keys(
        attempt,
        {
            "attempt_number",
            "call_id",
            "case_id",
            "evaluator",
            "execution_receipt_sha256",
            "execution_result_sha256",
            "execution_status",
            "item_id",
            "judgment",
            "orientation",
            "packet_sha256",
            "prompt_sha256",
            "provider_response_id",
            "raw_response_sha256",
            "replicate_id",
            "request_sha256",
            "schema_version",
            "status",
            "validation",
        },
        label="atomic attempt",
    )
    call = calls_by_id.get(attempt.get("call_id"))
    attempt_number = attempt.get("attempt_number")
    if (
        attempt.get("schema_version")
        not in {
            ATOMIC_ATTEMPT_SCHEMA_VERSION,
            *LEGACY_ATOMIC_ATTEMPT_SCHEMA_VERSIONS,
        }
        or call is None
        or isinstance(attempt_number, bool)
        or not isinstance(attempt_number, int)
        or attempt_number not in range(1, MAX_PHYSICAL_ATTEMPTS + 1)
        or attempt.get("case_id") != call["case_id"]
        or attempt.get("item_id") != call["item_id"]
        or attempt.get("evaluator") != manifest["evaluator"]
        or attempt.get("orientation") != manifest["orientation"]
        or attempt.get("replicate_id") != manifest["replicate_id"]
        or attempt.get("packet_sha256") != call["packet_sha256"]
        or attempt.get("prompt_sha256") != call["prompt_sha256"]
    ):
        fail("ATTEMPT_IDENTITY_MISMATCH", "Atomic attempt identity is invalid")
    _load_call_packet(artifact_root=artifact_root, call=call)
    execution_status = attempt.get("execution_status")
    if execution_status not in {"pass", "fail"}:
        fail("ATTEMPT_IDENTITY_MISMATCH", "Atomic execution status is invalid")
    result_path = attempt_path.parent / "execution-result.json"
    execution_result, execution_result_bytes = _validate_execution_result(
        result_path=result_path,
        manifest=manifest,
        manifest_file_sha256=sha256_bytes(canonical_json_bytes(manifest)),
        call=call,
        expected_status=execution_status,
        evidence_root=attempt_path.parent / "execution-evidence",
    )
    if sha256_bytes(execution_result_bytes) != attempt.get(
        "execution_result_sha256"
    ) or execution_result["request_sha256"] != attempt.get("request_sha256"):
        fail("HASH_MISMATCH", "Atomic execution result binding changed")
    if execution_status == "pass":
        raw_path = attempt_path.parent / "raw-response.bin"
        receipt_path = attempt_path.parent / "execution-receipt.json"
        try:
            raw_bytes = raw_path.read_bytes()
        except OSError as exc:
            fail("MISSING_ARTIFACT", "Atomic raw response is missing", error=str(exc))
        if sha256_bytes(raw_bytes) != attempt.get("raw_response_sha256"):
            fail("HASH_MISMATCH", "Atomic raw response hash changed")
        receipt, receipt_bytes = _validate_execution_receipt(
            receipt_path=receipt_path,
            response_bytes=raw_bytes,
            manifest=manifest,
            manifest_file_sha256=sha256_bytes(canonical_json_bytes(manifest)),
            call=call,
        )
        if (
            sha256_bytes(receipt_bytes) != attempt.get("execution_receipt_sha256")
            or receipt["identity"]["provider_response_id"]
            != attempt.get("provider_response_id")
            or receipt["request_sha256"] != attempt.get("request_sha256")
            or execution_result["receipt_sha256"] != sha256_bytes(receipt_bytes)
        ):
            fail("HASH_MISMATCH", "Atomic execution receipt binding changed")
        judgment, validation = _assess_response(
            response_bytes=raw_bytes,
            handle_map=call["evidence_handle_map"],
        )
        expected_status = "valid" if judgment is not None else "invalid"
    else:
        if any(
            attempt.get(key) is not None
            for key in (
                "execution_receipt_sha256",
                "provider_response_id",
                "raw_response_sha256",
            )
        ):
            fail(
                "ATTEMPT_VALIDATION_MISMATCH",
                "Failed execution attempt contains response identity",
            )
        judgment = None
        validation = {"error": execution_result["error"], "status": "fail"}
        expected_status = "invalid"
    if (
        attempt.get("status") != expected_status
        or attempt.get("judgment") != judgment
        or attempt.get("validation") != validation
    ):
        fail("ATTEMPT_VALIDATION_MISMATCH", "Atomic attempt cannot be reproduced")
    return attempt, attempt_bytes


def resolve_orientation(
    *, manifest_path: Path, attempt_paths: list[Path], output_root: Path
) -> dict[str, Any]:
    manifest, artifact_root, calls = _load_manifest(manifest_path)
    calls_by_id = {call["call_id"]: call for call in calls.values()}
    grouped: dict[str, list[tuple[dict[str, Any], bytes]]] = {
        call_id: [] for call_id in calls_by_id
    }
    for attempt_path in attempt_paths:
        attempt, attempt_bytes = _validate_attempt(
            attempt_path=attempt_path,
            manifest=manifest,
            artifact_root=artifact_root,
            calls_by_id=calls_by_id,
        )
        grouped[attempt["call_id"]].append((attempt, attempt_bytes))
    judgments = []
    selected_attempts = []
    first_valid_count = 0
    invalid_count = 0
    retried_count = 0
    total_attempts = 0
    invalid_codes: Counter[str] = Counter()
    provider_response_ids: set[str] = set()
    for sequence in range(1, EXPECTED_ITEM_COUNT + 1):
        call = calls[sequence]
        entries = sorted(
            grouped[call["call_id"]], key=lambda entry: entry[0]["attempt_number"]
        )
        numbers = [entry[0]["attempt_number"] for entry in entries]
        if not entries:
            fail("MISSING_LOGICAL_CALL", "Orientation lacks a logical call result")
        if numbers != list(range(1, len(numbers) + 1)) or len(numbers) > (
            MAX_PHYSICAL_ATTEMPTS
        ):
            fail(
                "INVALID_ATTEMPT_SEQUENCE", "Atomic attempts must be consecutive from 1"
            )
        valid_indexes = [
            index
            for index, entry in enumerate(entries)
            if entry[0]["status"] == "valid"
        ]
        if valid_indexes:
            valid_index = valid_indexes[0]
            if valid_index != len(entries) - 1 or len(valid_indexes) != 1:
                fail(
                    "RETRY_AFTER_VALID",
                    "The first valid response must be accepted without retry",
                    call_id=call["call_id"],
                )
            selected = entries[valid_index]
            if valid_index == 0:
                first_valid_count += 1
        else:
            if len(entries) < MAX_PHYSICAL_ATTEMPTS:
                fail(
                    "RETRY_REQUIRED",
                    "Invalid response needs another exact-prompt retry",
                    call_id=call["call_id"],
                )
            fail(
                "LOGICAL_CALL_EXHAUSTED",
                (
                    "Logical call remained invalid after "
                    f"{MAX_PHYSICAL_ATTEMPTS} physical attempts"
                ),
                call_id=call["call_id"],
            )
        if len(entries) > 1:
            retried_count += 1
        invalid_entries = [
            entry for entry in entries if entry[0]["status"] == "invalid"
        ]
        invalid_count += len(invalid_entries)
        for invalid_entry, _ in invalid_entries:
            invalid_codes[invalid_entry["validation"]["error"]["code"]] += 1
        total_attempts += len(entries)
        entry_response_ids = [
            entry[0]["provider_response_id"]
            for entry in entries
            if entry[0]["provider_response_id"] is not None
        ]
        if any(
            response_id in provider_response_ids for response_id in entry_response_ids
        ):
            fail(
                "DUPLICATE_PROVIDER_RESPONSE",
                "Each physical atomic attempt needs a unique provider response ID",
            )
        provider_response_ids.update(entry_response_ids)
        selected_attempt, _ = selected
        judgments.append(
            {
                "case_id": call["case_id"],
                "item_id": call["item_id"],
                **selected_attempt["judgment"],
            }
        )
        selected_attempts.append(
            {
                "attempt_sha256s": [
                    sha256_bytes(attempt_bytes) for _, attempt_bytes in entries
                ],
                "call_id": call["call_id"],
                "provider_response_ids": entry_response_ids,
                "selected_attempt_number": selected_attempt["attempt_number"],
            }
        )
    trace = {
        "attempt_summary": {
            "first_attempt_valid_count": first_valid_count,
            "invalid_attempt_count": invalid_count,
            "retried_call_count": retried_count,
            "total_physical_attempts": total_attempts,
        },
        "evaluator": manifest["evaluator"],
        "invalid_attempts_by_error": dict(sorted(invalid_codes.items())),
        "judgments": judgments,
        "orientation": manifest["orientation"],
        "replicate_id": manifest["replicate_id"],
        "schema_version": ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION,
        "selected_attempts": selected_attempts,
        "source_bundle_file_sha256": manifest["source_bundle_file_sha256"],
        "source_bundle_self_sha256": manifest["source_bundle_self_sha256"],
        "status": "pass",
    }
    trace_bytes = canonical_json_bytes(trace)
    result = {
        "judgment_count": len(judgments),
        "schema_version": ATOMIC_ORIENTATION_RESULT_SCHEMA_VERSION,
        "status": "pass",
        "trace_sha256": sha256_bytes(trace_bytes),
    }
    write_once(output_root / "trace.json", trace_bytes)
    write_json_once(output_root / "result.json", result)
    return trace


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and validate atomic local-ranking judge calls"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--bundle", type=Path, required=True)
    prepare_parser.add_argument("--replicate-id", required=True)
    prepare_parser.add_argument(
        "--reasoning-effort", choices=sorted(APPROVED_ATOMIC_EFFORTS)
    )
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    attempt_parser = subparsers.add_parser("record-attempt")
    attempt_parser.add_argument("--manifest", type=Path, required=True)
    attempt_parser.add_argument("--call-sequence", type=int, required=True)
    attempt_parser.add_argument("--attempt-number", type=int, required=True)
    attempt_parser.add_argument("--response", type=Path, required=True)
    attempt_parser.add_argument("--execution-receipt", type=Path, required=True)
    attempt_parser.add_argument("--execution-result", type=Path, required=True)
    attempt_parser.add_argument("--output-root", type=Path, required=True)
    failed_parser = subparsers.add_parser("record-failed-attempt")
    failed_parser.add_argument("--manifest", type=Path, required=True)
    failed_parser.add_argument("--call-sequence", type=int, required=True)
    failed_parser.add_argument("--attempt-number", type=int, required=True)
    failed_parser.add_argument("--execution-result", type=Path, required=True)
    failed_parser.add_argument("--output-root", type=Path, required=True)
    resolve_parser = subparsers.add_parser("resolve-orientation")
    resolve_parser.add_argument("--manifest", type=Path, required=True)
    resolve_parser.add_argument("--attempt", action="append", type=Path, required=True)
    resolve_parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_atomic(
                bundle_path=args.bundle,
                replicate_id=args.replicate_id,
                output_root=args.output_root,
                reasoning_effort=args.reasoning_effort,
            )
            displayed_result = {
                key: result[key]
                for key in (
                    "call_count",
                    "orientation",
                    "replicate_id",
                    "schema_version",
                    "source_bundle_file_sha256",
                    "source_bundle_self_sha256",
                    "status",
                )
            }
        elif args.command == "record-attempt":
            result = record_attempt(
                manifest_path=args.manifest,
                call_sequence=args.call_sequence,
                attempt_number=args.attempt_number,
                response_path=args.response,
                execution_receipt_path=args.execution_receipt,
                execution_result_path=args.execution_result,
                output_root=args.output_root,
            )
            displayed_result = {
                key: result[key]
                for key in (
                    "attempt_number",
                    "call_id",
                    "raw_response_sha256",
                    "schema_version",
                    "status",
                    "validation",
                )
            }
        elif args.command == "record-failed-attempt":
            result = record_failed_attempt(
                manifest_path=args.manifest,
                call_sequence=args.call_sequence,
                attempt_number=args.attempt_number,
                execution_result_path=args.execution_result,
                output_root=args.output_root,
            )
            displayed_result = {
                key: result[key]
                for key in (
                    "attempt_number",
                    "call_id",
                    "execution_result_sha256",
                    "schema_version",
                    "status",
                    "validation",
                )
            }
        else:
            result = resolve_orientation(
                manifest_path=args.manifest,
                attempt_paths=args.attempt,
                output_root=args.output_root,
            )
            displayed_result = {
                "attempt_summary": result["attempt_summary"],
                "orientation": result["orientation"],
                "replicate_id": result["replicate_id"],
                "schema_version": result["schema_version"],
                "status": result["status"],
            }
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "ATOMIC_JUDGE_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": displayed_result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
