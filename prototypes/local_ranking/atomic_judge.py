from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
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
from .opencode_go_chat import SAFE_RESPONSE_HEADERS
from .opencode_go_stream import _extract_stream_tool_response
from .operational_judge import (
    BUNDLE_SCHEMA_VERSION,
    FORBIDDEN_PUBLIC_TEXT,
    SCORE_FIELDS,
    WINNERS,
)

ATOMIC_PACKET_SCHEMA_VERSION = "local-ranking-atomic-judge-packet-v2.0"
ATOMIC_PREPARATION_SCHEMA_VERSION = "local-ranking-atomic-preparation-v2.5"
CANARY_ATOMIC_PREPARATION_SCHEMA_VERSIONS = {"local-ranking-atomic-preparation-v2.4"}
LEGACY_ATOMIC_PREPARATION_SCHEMA_VERSIONS = {
    "local-ranking-atomic-preparation-v2.2",
    "local-ranking-atomic-preparation-v2.3",
}
ATOMIC_RESPONSE_SUBMISSION = "forced_submit_judgment_tool"
ATOMIC_ATTEMPT_SCHEMA_VERSION = "local-ranking-atomic-attempt-v2.6"
CANARY_ATOMIC_ATTEMPT_SCHEMA_VERSIONS = {"local-ranking-atomic-attempt-v2.5"}
CANARY_ATOMIC_ATTEMPT_WRITE_SCHEMA_VERSION = "local-ranking-atomic-attempt-v2.5"
LEGACY_ATOMIC_ATTEMPT_SCHEMA_VERSIONS = {
    "local-ranking-atomic-attempt-v2.3",
    "local-ranking-atomic-attempt-v2.4",
}
LEGACY_ATOMIC_ATTEMPT_WRITE_SCHEMA_VERSION = "local-ranking-atomic-attempt-v2.4"
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
PREPARATION_SCHEMA_VERSION = "local-ranking-atomic-opencode-go-preparation-v3.1"
CANARY_PREPARATION_SCHEMA_VERSIONS = {
    "local-ranking-atomic-opencode-go-preparation-v3.0"
}
LEGACY_PREPARATION_SCHEMA_VERSIONS = {
    "local-ranking-atomic-opencode-go-preparation-v2.1"
}
TOOL_RECEIPT_EVIDENCE_FILES = frozenset(
    {
        "chunks.jsonl",
        "finished-at.txt",
        "http-status.txt",
        "response-headers.json",
        "response.json",
        "started-at.txt",
        "stream-body.sse",
    }
)
TOOL_RESULT_EVIDENCE_FILES = TOOL_RECEIPT_EVIDENCE_FILES | {"receipt.json"}
FAILED_RESULT_BASE_EVIDENCE_FILES = frozenset(
    {
        "finished-at.txt",
        "http-status.txt",
        "response-headers.json",
        "started-at.txt",
        "stream-body.sse",
    }
)
TRANSPORT_ERROR_EVIDENCE_FILE = "transport-error.json"
STREAM_ERROR_EVIDENCE_FILE = "stream-validation-error.json"
ATOMIC_MAX_TOKENS = 16_384
SMOKE_CALL_COUNT = 4
RETRY_POLICY = {
    "error_feedback": False,
    "max_physical_attempts": MAX_PHYSICAL_ATTEMPTS,
    "retry_after_valid": False,
    "same_prompt": True,
    "trigger": "deterministic_invalid_only",
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


def _legacy_prompt_text(packet: dict[str, Any]) -> str:
    packet_json = canonical_json_bytes(packet).decode("utf-8")
    return (
        "You are a blind setwise evidence evaluator. No tools are available. "
        "Use only the embedded single-item packet; do not use external facts or prior conversations.\n\n"
        "Compare the complete left and right top-3 evidence sets for the query. Judge direct "
        "support, usefulness for AI ideation, coverage/diversity, specificity, and catastrophic "
        "omissions. Do not reward length, fluency, or familiarity by themselves.\n\n"
        "Return exactly one JSON object and no Markdown. Root keys must be exactly "
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


def _uses_tool_transport(preparation_schema_version: Any) -> bool:
    if preparation_schema_version in LEGACY_ATOMIC_PREPARATION_SCHEMA_VERSIONS:
        return False
    if preparation_schema_version in (
        {ATOMIC_PREPARATION_SCHEMA_VERSION} | CANARY_ATOMIC_PREPARATION_SCHEMA_VERSIONS
    ):
        return True
    fail("INVALID_ATOMIC_MANIFEST", "Atomic preparation schema is unsupported")


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
        "response_submission": ATOMIC_RESPONSE_SUBMISSION,
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
    schema_version = manifest.get("schema_version")
    expected_keys = {
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
    }
    if schema_version == ATOMIC_PREPARATION_SCHEMA_VERSION:
        expected_keys = {*expected_keys, "response_submission"}
    elif schema_version not in (
        LEGACY_ATOMIC_PREPARATION_SCHEMA_VERSIONS
        | CANARY_ATOMIC_PREPARATION_SCHEMA_VERSIONS
    ):
        fail("INVALID_ATOMIC_MANIFEST", "Atomic manifest schema is unsupported")
    _expect_keys(
        manifest,
        expected_keys,
        label="atomic manifest",
    )
    if (
        schema_version == ATOMIC_PREPARATION_SCHEMA_VERSION
        and manifest.get("response_submission") != ATOMIC_RESPONSE_SUBMISSION
    ):
        fail("INVALID_ATOMIC_MANIFEST", "Atomic response submission is invalid")
    calls = manifest.get("calls")
    if (
        manifest.get("status") != "ready_for_atomic_execution"
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
    *, artifact_root: Path, call: dict[str, Any], preparation_schema_version: str
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
    prompt_text = (
        _prompt_text
        if _uses_tool_transport(preparation_schema_version)
        else _legacy_prompt_text
    )
    if (
        packet.get("schema_version") != ATOMIC_PACKET_SCHEMA_VERSION
        or len(packet_bytes) != call.get("packet_bytes")
        or sha256_bytes(packet_bytes) != call.get("packet_sha256")
        or len(prompt_bytes) != call.get("prompt_bytes")
        or sha256_bytes(prompt_bytes) != call.get("prompt_sha256")
        or prompt_bytes != prompt_text(packet).encode("utf-8")
    ):
        fail("HASH_MISMATCH", "Atomic packet or prompt differs from manifest")
    return packet, packet_bytes


def _request(*, prompt: str, reasoning_effort: str) -> dict[str, Any]:
    return {
        "max_tokens": ATOMIC_MAX_TOKENS,
        "messages": [{"content": prompt, "role": "user"}],
        "model": APPROVED_ATOMIC_MODEL_ALIAS.rsplit("/", 1)[-1],
        "reasoning_effort": reasoning_effort,
        "stream": True,
        "tool_choice": SUBMIT_JUDGMENT_TOOL_CHOICE,
        "tools": [SUBMIT_JUDGMENT_TOOL],
    }


def _legacy_request(*, prompt: str, reasoning_effort: str) -> dict[str, Any]:
    return {
        "max_tokens": ATOMIC_MAX_TOKENS,
        "messages": [{"content": prompt, "role": "user"}],
        "model": APPROVED_ATOMIC_MODEL_ALIAS.rsplit("/", 1)[-1],
        "reasoning_effort": reasoning_effort,
        "response_format": {"type": "json_object"},
        "stream": True,
    }


def _validated_concurrency(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4:
        fail("INVALID_CONCURRENCY", "Atomic concurrency must be between 1 and 4")
    return value


def _transport_request_builder(schema_version: Any) -> Any:
    if (
        schema_version
        in {PREPARATION_SCHEMA_VERSION} | CANARY_PREPARATION_SCHEMA_VERSIONS
    ):
        return _request
    if schema_version in LEGACY_PREPARATION_SCHEMA_VERSIONS:
        return _legacy_request
    fail(
        "INVALID_PREPARATION",
        "Atomic transport preparation schema is unsupported",
    )


def _decode_utf8(data: bytes, *, code: str, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(code, f"{label} is not UTF-8", offset=exc.start)


def _validate_transport_manifest_shape(
    manifest: dict[str, Any], *, code: str
) -> dict[int, dict[str, Any]]:
    base_keys = {
        "atomic_manifest_sha256",
        "call_count",
        "calls",
        "endpoint",
        "evaluator",
        "kind",
        "max_concurrency",
        "max_tokens",
        "retry_policy",
        "schema_version",
        "status",
    }
    schema_version = manifest.get("schema_version")
    if schema_version == PREPARATION_SCHEMA_VERSION:
        expected_keys = {*base_keys, "response_submission"}
    elif schema_version in (
        CANARY_PREPARATION_SCHEMA_VERSIONS | LEGACY_PREPARATION_SCHEMA_VERSIONS
    ):
        expected_keys = base_keys
    else:
        fail(code, "Atomic transport preparation schema is unsupported")
    evaluator = manifest.get("evaluator")
    kind = manifest.get("kind")
    calls = manifest.get("calls")
    expected_count = 24 if kind == "atomic" else SMOKE_CALL_COUNT
    if (
        set(manifest) != expected_keys
        or (
            schema_version == PREPARATION_SCHEMA_VERSION
            and manifest.get("response_submission") != ATOMIC_RESPONSE_SUBMISSION
        )
        or manifest.get("status") != "ready_for_execution"
        or manifest.get("endpoint") != OPENCODE_GO_ENDPOINT
        or manifest.get("max_tokens") != ATOMIC_MAX_TOKENS
        or manifest.get("retry_policy") != RETRY_POLICY
        or kind not in {"atomic", "smoke"}
        or not isinstance(evaluator, dict)
        or set(evaluator) != {"harness", "model_alias", "provider", "reasoning_effort"}
        or evaluator.get("harness") != "opencode-go-chat-completions"
        or evaluator.get("model_alias") != APPROVED_ATOMIC_MODEL_ALIAS
        or evaluator.get("provider") != "opencode-go"
        or evaluator.get("reasoning_effort") not in APPROVED_ATOMIC_EFFORTS
        or not isinstance(calls, list)
        or manifest.get("call_count") != expected_count
        or len(calls) != expected_count
    ):
        fail(code, "Atomic transport manifest is incompatible")
    _validated_concurrency(manifest.get("max_concurrency"))
    atomic_sha = manifest.get("atomic_manifest_sha256")
    if (
        kind == "atomic" and (not isinstance(atomic_sha, str) or len(atomic_sha) != 64)
    ) or (kind == "smoke" and atomic_sha is not None):
        fail(code, "Atomic manifest binding is invalid")
    by_sequence: dict[int, dict[str, Any]] = {}
    for call in calls:
        if not isinstance(call, dict) or set(call) != {
            "call_id",
            "orientation",
            "prompt_path",
            "prompt_sha256",
            "replicate_id",
            "request_path",
            "request_sha256",
            "sequence",
        }:
            fail(code, "Prepared call schema is invalid")
        sequence = call.get("sequence")
        expected_id = (
            f"call-{sequence:03d}"
            if kind == "atomic" and isinstance(sequence, int)
            else f"smoke-{sequence:03d}" if isinstance(sequence, int) else None
        )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence not in range(1, expected_count + 1)
            or sequence in by_sequence
            or call.get("call_id") != expected_id
            or (kind == "atomic")
            != (
                call.get("orientation") in {1, 2}
                and isinstance(call.get("replicate_id"), str)
                and bool(call.get("replicate_id"))
            )
        ):
            fail(code, "Prepared call identity is invalid")
        by_sequence[sequence] = call
    return by_sequence


def _validate_transport_call_files(
    *,
    preparation_root: Path,
    call: dict[str, Any],
    request_builder: Any,
    reasoning_effort: str,
) -> None:
    prompt_path = resolve_repo_relative(
        preparation_root, call["prompt_path"], label="prepared prompt path"
    )
    request_path = resolve_repo_relative(
        preparation_root, call["request_path"], label="prepared request path"
    )
    try:
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", "Prepared prompt is missing", error=str(exc))
    request, request_bytes = _read_canonical_object(
        request_path, label="prepared request"
    )
    expected_request = request_builder(
        prompt=_decode_utf8(prompt_bytes, code="INVALID_UTF8", label="Prepared prompt"),
        reasoning_effort=reasoning_effort,
    )
    if (
        sha256_bytes(prompt_bytes) != call.get("prompt_sha256")
        or sha256_bytes(request_bytes) != call.get("request_sha256")
        or request != expected_request
    ):
        fail("HASH_MISMATCH", "Prepared prompt or request changed")


def _validate_preparation(
    preparation_root: Path,
) -> tuple[dict[str, Any], bytes, dict[int, dict[str, Any]]]:
    manifest, manifest_bytes = _read_canonical_object(
        preparation_root / "manifest.json", label="atomic transport manifest"
    )
    calls = _validate_transport_manifest_shape(manifest, code="INVALID_PREPARATION")
    request_builder = _transport_request_builder(manifest["schema_version"])
    for call in calls.values():
        _validate_transport_call_files(
            preparation_root=preparation_root,
            call=call,
            request_builder=request_builder,
            reasoning_effort=manifest["evaluator"]["reasoning_effort"],
        )
    return manifest, manifest_bytes, calls


def _call_binding(*, manifest: dict[str, Any], call: dict[str, Any]) -> dict[str, Any]:
    return {
        "atomic_manifest_sha256": manifest["atomic_manifest_sha256"],
        "call_id": call["call_id"],
        "kind": manifest["kind"],
        "orientation": call["orientation"],
        "prompt_sha256": call["prompt_sha256"],
        "replicate_id": call["replicate_id"],
        "sequence": call["sequence"],
    }


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


def _validated_evidence_file_shape(files: Any, *, code: str, label: str) -> None:
    if not isinstance(files, dict) or any(
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or not isinstance(digest, str)
        or len(digest) != 64
        for name, digest in files.items()
    ):
        fail(code, f"{label} file hashes are invalid")


def _validated_evidence_file_map(
    files: Any, expected: frozenset[str], *, code: str, label: str
) -> dict[str, str]:
    _validated_evidence_file_shape(files, code=code, label=label)
    if set(files) != set(expected):
        fail(
            code,
            f"{label} must declare exactly the frozen evidence set",
            missing=sorted(set(expected) - set(files)),
            unexpected=sorted(set(files) - set(expected)),
        )
    return files


def _verify_evidence_files(
    evidence_root: Path, files: dict[str, str], *, label: str
) -> None:
    for name, digest in files.items():
        try:
            data = (evidence_root / name).read_bytes()
        except OSError as exc:
            fail(
                "MISSING_ARTIFACT",
                f"{label} evidence is missing",
                file=name,
                error=str(exc),
            )
        if sha256_bytes(data) != digest:
            fail("HASH_MISMATCH", f"{label} evidence changed", file=name)


def _read_evidence_line(evidence_root: Path, name: str, *, code: str) -> str:
    try:
        text = (evidence_root / name).read_bytes().decode("utf-8")
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT", f"Execution evidence {name} is missing", error=str(exc)
        )
    except UnicodeDecodeError as exc:
        fail(code, f"Execution evidence {name} is not UTF-8", error=str(exc))
    if not text.endswith("\n") or "\n" in text[:-1] or not text[:-1]:
        fail(code, f"Execution evidence {name} must be exactly one line")
    return text[:-1]


def _validated_execution_status(evidence_root: Path, *, code: str) -> str:
    status = _read_evidence_line(evidence_root, "http-status.txt", code=code)
    if status != "unavailable":
        try:
            value = int(status)
        except ValueError:
            fail(
                code,
                "Execution HTTP status is neither unavailable nor numeric",
            )
        if not 100 <= value <= 599:
            fail(code, "Execution HTTP status is not a valid status code")
    return status


def _validated_execution_headers(
    evidence_root: Path, *, expect_sse: bool | None, code: str
) -> dict[str, str]:
    try:
        data = (evidence_root / "response-headers.json").read_bytes()
        headers = json.loads(data)
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT",
            "Execution response headers are missing",
            error=str(exc),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(code, "Execution response headers are unreadable", error=str(exc))
    if (
        not isinstance(headers, dict)
        or canonical_json_bytes(headers) != data
        or any(
            not isinstance(name, str)
            or name not in SAFE_RESPONSE_HEADERS
            or not isinstance(value, str)
            for name, value in headers.items()
        )
    ):
        fail(code, "Execution response headers are not the canonical safe subset")
    content_type = headers.get("content-type", "")
    if expect_sse is True and "text/event-stream" not in content_type:
        fail(code, "Execution response is not text/event-stream")
    if expect_sse is False and "text/event-stream" in content_type:
        fail(code, "Execution response is unexpectedly text/event-stream")
    return headers


def _validated_execution_timestamps(evidence_root: Path, *, code: str) -> None:
    timestamps = []
    for name in ("started-at.txt", "finished-at.txt"):
        value = _read_evidence_line(evidence_root, name, code=code)
        if not value.endswith("Z"):
            fail(code, f"Execution evidence {name} must be a UTC Zulu timestamp")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            fail(
                code,
                f"Execution evidence {name} is not a valid timestamp",
                error=str(exc),
            )
        if parsed.tzinfo is None:
            fail(code, f"Execution evidence {name} must be timezone-aware")
        timestamps.append(parsed)
    if timestamps[0] > timestamps[1]:
        fail(code, "Execution started after it finished")


def _validated_tool_usage(value: Any, *, code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not {
        "completion_tokens",
        "prompt_tokens",
        "total_tokens",
    }.issubset(value):
        fail(code, "Tool execution usage is incomplete")
    for key, token_count in value.items():
        if (
            key
            not in {
                "cached_tokens",
                "completion_tokens",
                "prompt_tokens",
                "reasoning_tokens",
                "total_tokens",
            }
            or isinstance(token_count, bool)
            or not isinstance(token_count, int)
            or token_count < 0
        ):
            fail(code, "Tool execution usage is invalid")
    if value["total_tokens"] != value["prompt_tokens"] + value["completion_tokens"]:
        fail(code, "Tool execution token usage is inconsistent")
    return value


def _validated_tool_cost(value: Any, *, code: str) -> None:
    try:
        parsed = Decimal(value) if isinstance(value, str) else Decimal("NaN")
    except InvalidOperation:
        parsed = Decimal("NaN")
    if not parsed.is_finite() or parsed < 0:
        fail(
            code,
            "Tool execution cost must be a finite non-negative decimal string",
        )


def _validated_tool_identity(
    identity: Any, *, expected_model: str, code: str
) -> dict[str, Any]:
    if not isinstance(identity, dict) or set(identity) != {
        "cost",
        "created_first",
        "created_last",
        "finish_reason",
        "model",
        "provider_response_id",
        "tool_call_id",
    }:
        fail(code, "Tool execution provider identity is invalid")
    created_first = identity.get("created_first")
    created_last = identity.get("created_last")
    if (
        identity.get("finish_reason") not in {"stop", "tool_calls"}
        or identity.get("model") != expected_model
        or not isinstance(identity.get("provider_response_id"), str)
        or not identity["provider_response_id"]
        or not isinstance(identity.get("tool_call_id"), str)
        or not identity["tool_call_id"]
        or isinstance(created_first, bool)
        or not isinstance(created_first, int)
        or created_first < 0
        or isinstance(created_last, bool)
        or not isinstance(created_last, int)
        or created_last < created_first
    ):
        fail(code, "Tool execution provider identity is invalid")
    _validated_tool_cost(identity.get("cost"), code=code)
    return identity


def _validated_tool_diagnostics(value: Any, *, code: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "arguments_bytes",
            "content_bytes",
            "data_event_count",
            "done_received",
            "keepalive_count",
            "post_done_cost_received",
            "reasoning_bytes",
        }
        or value.get("done_received") is not True
        or not isinstance(value.get("post_done_cost_received"), bool)
        or any(
            isinstance(value[key], bool)
            or not isinstance(value[key], int)
            or value[key] < 0
            for key in (
                "arguments_bytes",
                "content_bytes",
                "data_event_count",
                "keepalive_count",
                "reasoning_bytes",
            )
        )
    ):
        fail(code, "Tool execution diagnostics are invalid")
    return value


def _replay_tool_stream(
    evidence_root: Path, *, expected_model: str, code: str
) -> tuple[bytes, bytes, dict[str, Any], dict[str, Any], Any]:
    try:
        raw_stream = (evidence_root / "stream-body.sse").read_bytes()
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT",
            "Raw SSE stream evidence is missing",
            error=str(exc),
        )
    try:
        draft, usage, identity, chunks, diagnostics = _extract_stream_tool_response(
            raw_stream,
            expected_model=expected_model,
            tool_name=SUBMIT_JUDGMENT_TOOL_NAME,
        )
    except HarnessError as exc:
        fail(
            code,
            "Raw SSE stream does not replay as a valid tool response",
            error=exc.as_dict(),
        )
    response_bytes = canonical_json_bytes(draft)
    chunks_bytes = b"".join(canonical_json_bytes(chunk) for chunk in chunks)
    return response_bytes, chunks_bytes, identity, diagnostics, usage


def _validate_tool_success_evidence(
    *,
    evidence_root: Path,
    receipt: dict[str, Any],
    result: dict[str, Any],
    expected_model: str,
    code: str,
) -> None:
    _validated_evidence_file_map(
        receipt.get("files"),
        TOOL_RECEIPT_EVIDENCE_FILES,
        code=code,
        label="Tool execution receipt",
    )
    _verify_evidence_files(
        evidence_root, receipt["files"], label="Tool execution receipt"
    )
    _validated_evidence_file_map(
        result.get("files"),
        TOOL_RESULT_EVIDENCE_FILES,
        code=code,
        label="Tool execution result",
    )
    _verify_evidence_files(
        evidence_root, result["files"], label="Tool execution result"
    )
    if (
        _validated_execution_status(evidence_root, code=code) != "200"
        or receipt.get("http_status") != 200
    ):
        fail(code, "Successful execution requires HTTP 200 evidence")
    _validated_execution_headers(evidence_root, expect_sse=True, code=code)
    _validated_execution_timestamps(evidence_root, code=code)
    _validated_tool_identity(
        receipt.get("identity"), expected_model=expected_model, code=code
    )
    _validated_tool_usage(receipt.get("usage"), code=code)
    _validated_tool_diagnostics(receipt.get("diagnostics"), code=code)
    (
        replayed_response,
        replayed_chunks,
        replayed_identity,
        replayed_diagnostics,
        replayed_usage,
    ) = _replay_tool_stream(evidence_root, expected_model=expected_model, code=code)
    try:
        recorded_response = (evidence_root / "response.json").read_bytes()
        recorded_chunks = (evidence_root / "chunks.jsonl").read_bytes()
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT",
            "Derived execution evidence is missing",
            error=str(exc),
        )
    if recorded_response != replayed_response:
        fail("HASH_MISMATCH", "Execution response does not match the raw stream")
    if recorded_chunks != replayed_chunks:
        fail("HASH_MISMATCH", "Execution chunks do not match the raw stream")
    if (
        replayed_identity != receipt["identity"]
        or replayed_diagnostics != receipt["diagnostics"]
        or replayed_usage != receipt["usage"]
    ):
        fail("HASH_MISMATCH", "Execution receipt does not match the raw stream")


def _read_error_evidence_file(
    evidence_root: Path, name: str, *, code: str
) -> dict[str, Any]:
    try:
        data = (evidence_root / name).read_bytes()
        payload = json.loads(data)
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT", f"Execution evidence {name} is missing", error=str(exc)
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(code, f"Execution evidence {name} is unreadable", error=str(exc))
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        fail(code, f"Execution evidence {name} is not a canonical JSON object")
    return payload


def _validate_tool_failure_evidence(
    *,
    evidence_root: Path,
    result: dict[str, Any],
    expected_model: str,
    code: str,
) -> None:
    files = result.get("files")
    _validated_evidence_file_shape(files, code=code, label="Failed execution result")
    names = set(files)
    unknown = names - (
        FAILED_RESULT_BASE_EVIDENCE_FILES
        | {TRANSPORT_ERROR_EVIDENCE_FILE, STREAM_ERROR_EVIDENCE_FILE}
    )
    if unknown:
        fail(
            code,
            "Failed execution evidence declares forbidden files",
            unexpected=sorted(unknown),
        )
    if not FAILED_RESULT_BASE_EVIDENCE_FILES.issubset(names):
        fail(
            code,
            "Failed execution evidence lacks the frozen base set",
            missing=sorted(FAILED_RESULT_BASE_EVIDENCE_FILES - names),
        )
    extra = names - FAILED_RESULT_BASE_EVIDENCE_FILES
    error = result["error"]
    status = _validated_execution_status(evidence_root, code=code)
    if extra == {TRANSPORT_ERROR_EVIDENCE_FILE}:
        details = error.get("details")
        if (
            error.get("code") != "OPENCODE_GO_STREAM_TRANSPORT_FAILED"
            or not isinstance(details, dict)
            or set(details) != {"error"}
            or not isinstance(details["error"], str)
            or not details["error"]
        ):
            fail(code, "Transport failure error does not match its evidence file")
        payload = _read_error_evidence_file(
            evidence_root, TRANSPORT_ERROR_EVIDENCE_FILE, code=code
        )
        if payload != {"error_type": details["error"]}:
            fail(code, "Transport error evidence does not match the result error")
        _validated_execution_headers(evidence_root, expect_sse=None, code=code)
    elif extra == {STREAM_ERROR_EVIDENCE_FILE}:
        if status != "200":
            fail(code, "Stream validation failure requires HTTP 200 evidence")
        _validated_execution_headers(evidence_root, expect_sse=True, code=code)
        payload = _read_error_evidence_file(
            evidence_root, STREAM_ERROR_EVIDENCE_FILE, code=code
        )
        if payload != error:
            fail(code, "Stream validation error evidence must equal the result error")
        try:
            _extract_stream_tool_response(
                (evidence_root / "stream-body.sse").read_bytes(),
                expected_model=expected_model,
                tool_name=SUBMIT_JUDGMENT_TOOL_NAME,
            )
        except HarnessError as exc:
            if exc.as_dict() != error:
                fail(code, "Raw stream does not reproduce the recorded failure")
        else:
            fail(code, "Raw stream replays successfully despite the recorded failure")
    elif not extra:
        if status == "200":
            if error.get("code") != "INVALID_SSE":
                fail(code, "HTTP 200 failure evidence requires the non-SSE error")
            _validated_execution_headers(evidence_root, expect_sse=False, code=code)
        elif status == "unavailable":
            fail(code, "Unavailable status requires transport error evidence")
        else:
            if error.get("code") != "OPENCODE_GO_STREAM_HTTP_FAILED" or error.get(
                "details"
            ) != {"status_code": int(status)}:
                fail(code, "HTTP failure evidence does not match the result error")
            _validated_execution_headers(evidence_root, expect_sse=None, code=code)
    else:
        fail(code, "Failed execution evidence has an invalid additional file set")
    _validated_execution_timestamps(evidence_root, code=code)


def _bind_current_preparation(
    *,
    preparation_root: Path,
    manifest: dict[str, Any],
    manifest_file_sha256: str,
    artifact_root: Path,
    call: dict[str, Any],
    request_sha256s: set[str],
    preparation_sha256s: set[str],
) -> tuple[bytes, bytes, bytes]:
    preparation, preparation_bytes, prepared_calls = _validate_preparation(
        preparation_root
    )
    if (
        preparation["schema_version"] != PREPARATION_SCHEMA_VERSION
        or preparation.get("response_submission") != ATOMIC_RESPONSE_SUBMISSION
        or preparation["kind"] != "atomic"
    ):
        fail(
            "INVALID_PREPARATION",
            "Atomic ledger recording requires the current transport preparation",
        )
    prepared_call = prepared_calls.get(call["sequence"])
    if (
        preparation["atomic_manifest_sha256"] != manifest_file_sha256
        or preparation["evaluator"] != manifest["evaluator"]
        or prepared_call is None
        or prepared_call["call_id"] != call["call_id"]
        or prepared_call["orientation"] != manifest["orientation"]
        or prepared_call["replicate_id"] != manifest["replicate_id"]
        or prepared_call["prompt_sha256"] != call["prompt_sha256"]
    ):
        fail(
            "INVALID_PREPARATION",
            "Transport preparation does not bind this atomic call",
        )
    atomic_prompt_path = resolve_repo_relative(
        artifact_root, call["prompt_path"], label="atomic prompt path"
    )
    transport_prompt_path = resolve_repo_relative(
        preparation_root, prepared_call["prompt_path"], label="prepared prompt path"
    )
    request_path = resolve_repo_relative(
        preparation_root, prepared_call["request_path"], label="prepared request path"
    )
    try:
        atomic_prompt_bytes = atomic_prompt_path.read_bytes()
        transport_prompt_bytes = transport_prompt_path.read_bytes()
        request_bytes = request_path.read_bytes()
    except OSError as exc:
        fail(
            "MISSING_ARTIFACT", "Prepared input evidence is unreadable", error=str(exc)
        )
    if transport_prompt_bytes != atomic_prompt_bytes:
        fail(
            "INVALID_PREPARATION",
            "Transport prompt differs from the atomic prompt",
        )
    if (
        request_sha256s != {prepared_call["request_sha256"]}
        or sha256_bytes(request_bytes) != prepared_call["request_sha256"]
    ):
        fail(
            "INVALID_PREPARATION",
            "Execution evidence does not bind the prepared request",
        )
    if preparation_sha256s != {sha256_bytes(preparation_bytes)}:
        fail(
            "INVALID_PREPARATION",
            "Execution evidence does not bind the transport preparation",
        )
    return preparation_bytes, transport_prompt_bytes, request_bytes


def _write_input_evidence(
    *,
    output_root: Path,
    preparation_bytes: bytes,
    prompt_bytes: bytes,
    request_bytes: bytes,
) -> None:
    write_once(output_root / "input-evidence" / "manifest.json", preparation_bytes)
    write_once(output_root / "input-evidence" / "prompt.txt", prompt_bytes)
    write_once(output_root / "input-evidence" / "request.json", request_bytes)


def _validate_attempt_input_evidence(
    *,
    attempt_dir: Path,
    attempt: dict[str, Any],
    manifest: dict[str, Any],
    manifest_file_sha256: str,
    call: dict[str, Any],
) -> None:
    code = "INVALID_INPUT_EVIDENCE"
    evidence_root = attempt_dir / "input-evidence"
    expected_files = {"manifest.json", "prompt.txt", "request.json"}
    actual_files = (
        {path.name for path in evidence_root.iterdir() if path.is_file()}
        if evidence_root.is_dir()
        else set()
    )
    if actual_files != expected_files:
        fail(
            code,
            "Attempt input evidence must contain exactly the three frozen files",
        )
    try:
        manifest_bytes = (evidence_root / "manifest.json").read_bytes()
        copied = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(code, "Attempt input evidence manifest is unreadable", error=str(exc))
    if (
        not isinstance(copied, dict)
        or canonical_json_bytes(copied) != manifest_bytes
        or sha256_bytes(manifest_bytes) != attempt.get("preparation_manifest_sha256")
    ):
        fail(code, "Attempt input evidence manifest does not match the attempt")
    prepared_calls = _validate_transport_manifest_shape(copied, code=code)
    if (
        copied["schema_version"] != PREPARATION_SCHEMA_VERSION
        or copied.get("response_submission") != ATOMIC_RESPONSE_SUBMISSION
        or copied["kind"] != "atomic"
        or copied["atomic_manifest_sha256"] != manifest_file_sha256
        or copied["evaluator"] != manifest["evaluator"]
    ):
        fail(
            code,
            "Attempt input evidence does not bind the current atomic preparation",
        )
    prepared_call = prepared_calls.get(call["sequence"])
    if (
        prepared_call is None
        or prepared_call["call_id"] != call["call_id"]
        or prepared_call["orientation"] != manifest["orientation"]
        or prepared_call["replicate_id"] != manifest["replicate_id"]
        or prepared_call["prompt_sha256"] != call["prompt_sha256"]
    ):
        fail(code, "Attempt input evidence does not bind the atomic call")
    try:
        prompt_bytes = (evidence_root / "prompt.txt").read_bytes()
        request_bytes = (evidence_root / "request.json").read_bytes()
        request = json.loads(request_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(
            code,
            "Attempt input evidence prompt or request is unreadable",
            error=str(exc),
        )
    expected_request = _request(
        prompt=_decode_utf8(prompt_bytes, code=code, label="Attempt input prompt"),
        reasoning_effort=copied["evaluator"]["reasoning_effort"],
    )
    if (
        not isinstance(request, dict)
        or canonical_json_bytes(request) != request_bytes
        or sha256_bytes(prompt_bytes) != prepared_call["prompt_sha256"]
        or sha256_bytes(request_bytes) != prepared_call["request_sha256"]
        or sha256_bytes(request_bytes) != attempt.get("request_sha256")
        or request != expected_request
    ):
        fail(code, "Attempt input evidence prompt or request changed")


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
    if _uses_tool_transport(manifest.get("schema_version")):
        if schema_version != ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION:
            fail(
                "INVALID_EXECUTION_RECEIPT",
                "Tool-transport atomic evidence requires the forced-tool receipt",
            )
    elif schema_version not in LEGACY_ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSIONS:
        fail(
            "INVALID_EXECUTION_RECEIPT",
            "Legacy atomic evidence requires the free-content receipt",
        )
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
    allowed_result_versions = (
        {ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION}
        if _uses_tool_transport(manifest.get("schema_version"))
        else LEGACY_ATOMIC_EXECUTION_RESULT_SCHEMA_VERSIONS
    )
    if (
        result.get("schema_version") not in allowed_result_versions
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
    preparation_root: Path | None = None,
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
    _load_call_packet(
        artifact_root=artifact_root,
        call=call,
        preparation_schema_version=manifest["schema_version"],
    )
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
    tool_transport = _uses_tool_transport(manifest["schema_version"])
    is_current = manifest["schema_version"] == ATOMIC_PREPARATION_SCHEMA_VERSION
    if tool_transport:
        _validate_tool_success_evidence(
            evidence_root=execution_result_path.parent,
            receipt=receipt,
            result=execution_result,
            expected_model=manifest["evaluator"]["model_alias"].rsplit("/", 1)[-1],
            code="INVALID_EXECUTION_RESULT",
        )
    if is_current:
        if preparation_root is None:
            fail(
                "INVALID_PREPARATION",
                "Current atomic attempts require the actual transport preparation",
            )
    elif preparation_root is not None:
        fail(
            "INVALID_PREPARATION",
            "Spent atomic families must not bind a new transport preparation",
        )
    input_evidence: tuple[bytes, bytes, bytes] | None = None
    if is_current:
        input_evidence = _bind_current_preparation(
            preparation_root=preparation_root,
            manifest=manifest,
            manifest_file_sha256=manifest_file_sha256,
            artifact_root=artifact_root,
            call=call,
            request_sha256s={
                receipt["request_sha256"],
                execution_result["request_sha256"],
            },
            preparation_sha256s={
                receipt["preparation_manifest_sha256"],
                execution_result["preparation_manifest_sha256"],
            },
        )
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
        "schema_version": (
            ATOMIC_ATTEMPT_SCHEMA_VERSION
            if is_current
            else (
                CANARY_ATOMIC_ATTEMPT_WRITE_SCHEMA_VERSION
                if tool_transport
                else LEGACY_ATOMIC_ATTEMPT_WRITE_SCHEMA_VERSION
            )
        ),
        "status": "valid" if judgment is not None else "invalid",
        "validation": validation,
    }
    if input_evidence is not None:
        outcome["preparation_manifest_sha256"] = sha256_bytes(input_evidence[0])
    write_once(output_root / "raw-response.bin", response_bytes)
    write_once(output_root / "execution-receipt.json", receipt_bytes)
    write_once(output_root / "execution-result.json", execution_result_bytes)
    _copy_execution_evidence(
        result=execution_result,
        source_root=execution_result_path.parent,
        output_root=output_root,
    )
    if input_evidence is not None:
        _write_input_evidence(
            output_root=output_root,
            preparation_bytes=input_evidence[0],
            prompt_bytes=input_evidence[1],
            request_bytes=input_evidence[2],
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
    preparation_root: Path | None = None,
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
    _load_call_packet(
        artifact_root=artifact_root,
        call=call,
        preparation_schema_version=manifest["schema_version"],
    )
    execution_result, execution_result_bytes = _validate_execution_result(
        result_path=execution_result_path,
        manifest=manifest,
        manifest_file_sha256=manifest_file_sha256,
        call=call,
        expected_status="fail",
    )
    tool_transport = _uses_tool_transport(manifest["schema_version"])
    is_current = manifest["schema_version"] == ATOMIC_PREPARATION_SCHEMA_VERSION
    if tool_transport:
        _validate_tool_failure_evidence(
            evidence_root=execution_result_path.parent,
            result=execution_result,
            expected_model=manifest["evaluator"]["model_alias"].rsplit("/", 1)[-1],
            code="INVALID_EXECUTION_RESULT",
        )
    if is_current:
        if preparation_root is None:
            fail(
                "INVALID_PREPARATION",
                "Current atomic attempts require the actual transport preparation",
            )
    elif preparation_root is not None:
        fail(
            "INVALID_PREPARATION",
            "Spent atomic families must not bind a new transport preparation",
        )
    input_evidence: tuple[bytes, bytes, bytes] | None = None
    if is_current:
        input_evidence = _bind_current_preparation(
            preparation_root=preparation_root,
            manifest=manifest,
            manifest_file_sha256=manifest_file_sha256,
            artifact_root=artifact_root,
            call=call,
            request_sha256s={execution_result["request_sha256"]},
            preparation_sha256s={execution_result["preparation_manifest_sha256"]},
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
        "schema_version": (
            ATOMIC_ATTEMPT_SCHEMA_VERSION
            if is_current
            else (
                CANARY_ATOMIC_ATTEMPT_WRITE_SCHEMA_VERSION
                if tool_transport
                else LEGACY_ATOMIC_ATTEMPT_WRITE_SCHEMA_VERSION
            )
        ),
        "status": "invalid",
        "validation": validation,
    }
    if input_evidence is not None:
        outcome["preparation_manifest_sha256"] = sha256_bytes(input_evidence[0])
    write_once(output_root / "execution-result.json", execution_result_bytes)
    _copy_execution_evidence(
        result=execution_result,
        source_root=execution_result_path.parent,
        output_root=output_root,
    )
    if input_evidence is not None:
        _write_input_evidence(
            output_root=output_root,
            preparation_bytes=input_evidence[0],
            prompt_bytes=input_evidence[1],
            request_bytes=input_evidence[2],
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
    manifest_schema = manifest.get("schema_version")
    if manifest_schema == ATOMIC_PREPARATION_SCHEMA_VERSION:
        allowed_attempt_versions = {ATOMIC_ATTEMPT_SCHEMA_VERSION}
    elif manifest_schema in CANARY_ATOMIC_PREPARATION_SCHEMA_VERSIONS:
        allowed_attempt_versions = CANARY_ATOMIC_ATTEMPT_SCHEMA_VERSIONS
    elif manifest_schema in LEGACY_ATOMIC_PREPARATION_SCHEMA_VERSIONS:
        allowed_attempt_versions = LEGACY_ATOMIC_ATTEMPT_SCHEMA_VERSIONS
    else:
        fail("INVALID_ATOMIC_MANIFEST", "Atomic preparation schema is unsupported")
    attempt_version = attempt.get("schema_version")
    if attempt_version not in allowed_attempt_versions:
        fail(
            "ATTEMPT_IDENTITY_MISMATCH",
            "Atomic attempt schema does not match the preparation family",
        )
    expected_attempt_keys = {
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
    }
    if attempt_version == ATOMIC_ATTEMPT_SCHEMA_VERSION:
        expected_attempt_keys = {
            *expected_attempt_keys,
            "preparation_manifest_sha256",
        }
    _expect_keys(
        attempt,
        expected_attempt_keys,
        label="atomic attempt",
    )
    call = calls_by_id.get(attempt.get("call_id"))
    attempt_number = attempt.get("attempt_number")
    preparation_sha256 = attempt.get("preparation_manifest_sha256")
    if (
        call is None
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
        or (
            attempt_version == ATOMIC_ATTEMPT_SCHEMA_VERSION
            and (
                not isinstance(preparation_sha256, str) or len(preparation_sha256) != 64
            )
        )
    ):
        fail("ATTEMPT_IDENTITY_MISMATCH", "Atomic attempt identity is invalid")
    _load_call_packet(
        artifact_root=artifact_root,
        call=call,
        preparation_schema_version=manifest["schema_version"],
    )
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
        if _uses_tool_transport(manifest_schema):
            _validate_tool_success_evidence(
                evidence_root=attempt_path.parent / "execution-evidence",
                receipt=receipt,
                result=execution_result,
                expected_model=manifest["evaluator"]["model_alias"].rsplit("/", 1)[-1],
                code="INVALID_EXECUTION_RESULT",
            )
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
        if _uses_tool_transport(manifest_schema):
            _validate_tool_failure_evidence(
                evidence_root=attempt_path.parent / "execution-evidence",
                result=execution_result,
                expected_model=manifest["evaluator"]["model_alias"].rsplit("/", 1)[-1],
                code="INVALID_EXECUTION_RESULT",
            )
        judgment = None
        validation = {"error": execution_result["error"], "status": "fail"}
        expected_status = "invalid"
    if attempt_version == ATOMIC_ATTEMPT_SCHEMA_VERSION:
        if attempt.get("preparation_manifest_sha256") != execution_result[
            "preparation_manifest_sha256"
        ] or (
            execution_status == "pass"
            and attempt.get("preparation_manifest_sha256")
            != receipt["preparation_manifest_sha256"]
        ):
            fail(
                "INVALID_INPUT_EVIDENCE",
                "Atomic attempt does not bind the recorded transport preparation",
            )
        _validate_attempt_input_evidence(
            attempt_dir=attempt_path.parent,
            attempt=attempt,
            manifest=manifest,
            manifest_file_sha256=sha256_bytes(canonical_json_bytes(manifest)),
            call=call,
        )
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
    attempt_parser.add_argument("--preparation-root", type=Path)
    attempt_parser.add_argument("--output-root", type=Path, required=True)
    failed_parser = subparsers.add_parser("record-failed-attempt")
    failed_parser.add_argument("--manifest", type=Path, required=True)
    failed_parser.add_argument("--call-sequence", type=int, required=True)
    failed_parser.add_argument("--attempt-number", type=int, required=True)
    failed_parser.add_argument("--execution-result", type=Path, required=True)
    failed_parser.add_argument("--preparation-root", type=Path)
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
                preparation_root=args.preparation_root,
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
                preparation_root=args.preparation_root,
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
