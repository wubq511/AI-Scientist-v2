from __future__ import annotations

import inspect
import json
import threading
from pathlib import Path

import httpx
import pytest

from prototypes.local_ranking import atomic_profile
from prototypes.local_ranking.atomic_calibration import aggregate
from prototypes.local_ranking.atomic_judge import (
    ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION,
    ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION,
    ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION,
    ATOMIC_PREPARATION_SCHEMA_VERSION,
    ATOMIC_RESPONSE_SUBMISSION,
    SUBMIT_JUDGMENT_TOOL,
    _legacy_prompt_text,
    prepare_atomic,
    record_failed_attempt,
    resolve_orientation,
)
from prototypes.local_ranking.atomic_judge import (
    record_attempt as _record_attempt,
)
from prototypes.local_ranking.atomic_opencode_go import prepare_atomic_transport
from prototypes.local_ranking.atomic_profile import (
    TRANSPORT_CANARY_SUMMARY_SHA256,
    USAGE_SNAPSHOT_SCHEMA_VERSION,
    prepare_profile,
)
from prototypes.local_ranking.atomic_runner import run_orientation
from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.operational_judge import BUNDLE_SCHEMA_VERSION

SCORE_FIELDS = (
    "coverage_diversity",
    "direct_support",
    "query_usefulness",
    "specificity",
)


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    return path


def _source_bundle(path: Path, *, orientation: int = 1) -> Path:
    items = []
    for item_index in range(24):
        sides = {}
        for side in ("left", "right"):
            papers = []
            for paper_index in range(1, 4):
                identity = f"{side}-{item_index:02d}-{paper_index}"
                papers.append(
                    {
                        "paper_id": f"paper-{identity}",
                        "segments": [
                            {
                                "content_type": "publisher_abstract",
                                "segment_id": f"segment-{identity}",
                                "source_start": 0,
                                "text": (
                                    f"Visible {side} evidence {paper_index} for item {item_index} "
                                    "describes a concrete mechanism and research implication."
                                ),
                            }
                        ],
                        "title": f"Visible {side} paper {paper_index}",
                    }
                )
            sides[side] = {"papers": papers}
        items.append(
            {
                "case_id": f"case-{item_index // 2:02d}",
                "item_id": f"item-{item_index:02d}",
                "left": sides["left"],
                "query": {
                    "kind": "broad" if item_index % 2 == 0 else "focused",
                    "text": f"Which evidence best addresses query {item_index}?",
                },
                "right": sides["right"],
            }
        )
    without_hash = {
        "bundle_id": f"judge-deepseek-orientation-{orientation}",
        "draft_contract": {},
        "evaluator": {
            "harness": "opencode-go-chat-completions",
            "model_alias": "opencode-go/deepseek-v4-pro",
            "provider": "opencode-go",
            "reasoning_effort": "high",
        },
        "evaluator_protocol_sha256": "e" * 64,
        "items": items,
        "orientation": orientation,
        "protocol_sha256": "p" * 64,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source_binding": {},
    }
    return _write(
        path,
        {
            **without_hash,
            "bundle_sha256": sha256_bytes(canonical_json_bytes(without_hash)),
        },
    )


def _valid_response(*, winner: str = "left") -> dict:
    handles = ["L1"] if winner == "left" else ["R1"]
    if winner in {"tie", "both_bad"}:
        handles = ["L1", "R1"]
    return {
        "catastrophic_omission_side": "neither",
        "evidence_handles": handles,
        "left_scores": {field: 2 for field in SCORE_FIELDS},
        "rationale": "The cited evidence gives the more directly useful visible support.",
        "right_scores": {field: 1 for field in SCORE_FIELDS},
        "winner": winner,
    }


def _sse_event(value: object) -> bytes:
    payload = (
        "[DONE]" if value == "[DONE]" else json.dumps(value, separators=(",", ":"))
    )
    return f"data: {payload}\n\n".encode()


def _semantic_stream(*, response_id: str, response: dict) -> bytes:
    model = "deepseek-v4-pro"
    base = {
        "created": 1,
        "id": response_id,
        "model": model,
        "object": "chat.completion.chunk",
    }
    arguments = json.dumps(response, separators=(",", ":"))
    return b"".join(
        (
            _sse_event(
                {
                    **base,
                    "choices": [
                        {
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "function": {
                                            "arguments": arguments,
                                            "name": "submit_judgment",
                                        },
                                        "id": f"call-{response_id}",
                                        "index": 0,
                                        "type": "function",
                                    }
                                ],
                            },
                            "finish_reason": None,
                            "index": 0,
                        }
                    ],
                }
            ),
            _sse_event(
                {
                    **base,
                    "choices": [
                        {
                            "delta": {},
                            "finish_reason": "tool_calls",
                            "index": 0,
                        }
                    ],
                    "usage": {
                        "completion_tokens": 50,
                        "prompt_tokens": 100,
                        "total_tokens": 150,
                    },
                }
            ),
            _sse_event("[DONE]"),
            _sse_event({"choices": [], "cost": "0"}),
        )
    )


def record_attempt(
    receipt_family: str = "tool", result_family: str | None = None, **kwargs
):
    if result_family is None:
        result_family = receipt_family
    manifest_path = kwargs["manifest_path"]
    response_path = kwargs["response_path"]
    output_root = kwargs["output_root"]
    manifest = json.loads(manifest_path.read_bytes())
    call = manifest["calls"][kwargs["call_sequence"] - 1]
    response_bytes = response_path.read_bytes()
    response_id = "test-" + sha256_bytes(str(output_root).encode())[:24]
    if receipt_family == "legacy":
        identity = {
            "cost": "0",
            "created_first": 1,
            "created_last": 1,
            "finish_reason": "stop",
            "model": "deepseek-v4-pro",
            "provider_response_id": response_id,
        }
        qualification = {
            "json_object_accepted": True,
            "reasoning_effort_requested": manifest["evaluator"]["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        }
        receipt_schema_version = "local-ranking-atomic-opencode-go-receipt-v2.0"
    else:
        identity = {
            "cost": "0",
            "created_first": 1,
            "created_last": 1,
            "finish_reason": "tool_calls",
            "model": "deepseek-v4-pro",
            "provider_response_id": response_id,
            "tool_call_id": f"tool-{response_id}",
        }
        qualification = {
            "forced_tool_call_accepted": True,
            "reasoning_effort_requested": manifest["evaluator"]["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        }
        receipt_schema_version = ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION
    result_schema_version = (
        "local-ranking-atomic-opencode-go-execution-v2.0"
        if result_family == "legacy"
        else ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION
    )
    receipt = {
        "call_binding": {
            "atomic_manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "call_id": call["call_id"],
            "kind": "atomic",
            "orientation": manifest["orientation"],
            "prompt_sha256": call["prompt_sha256"],
            "replicate_id": manifest["replicate_id"],
            "sequence": call["sequence"],
        },
        "diagnostics": {},
        "endpoint": "https://opencode.ai/zen/go/v1/chat/completions",
        "files": {"response.json": sha256_bytes(response_bytes)},
        "http_status": 200,
        "identity": identity,
        "preparation_manifest_sha256": "a" * 64,
        "provider": "opencode-go",
        "request_sha256": "b" * 64,
        "schema_version": receipt_schema_version,
        "status": "pass",
        "transport_qualification": qualification,
        "usage": None,
    }
    if receipt_family == "tool":
        receipt["tool"] = {
            "name": "submit_judgment",
            "schema_sha256": sha256_bytes(canonical_json_bytes(SUBMIT_JUDGMENT_TOOL)),
        }
    execution_root = output_root.parent / f"{output_root.name}-execution-source"
    receipt_path = _write(execution_root / "receipt.json", receipt)
    (execution_root / "response.json").write_bytes(response_bytes)
    execution_result = {
        "call_binding": receipt["call_binding"],
        "error": None,
        "files": {
            "receipt.json": sha256_bytes(receipt_path.read_bytes()),
            "response.json": sha256_bytes(response_bytes),
        },
        "preparation_manifest_sha256": "a" * 64,
        "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
        "request_sha256": "b" * 64,
        "schema_version": result_schema_version,
        "status": "pass",
    }
    execution_result_path = _write(
        execution_root / "execution-result.json", execution_result
    )
    return _record_attempt(
        execution_receipt_path=receipt_path,
        execution_result_path=execution_result_path,
        **kwargs,
    )


def _failed_attempt(
    *,
    manifest_path: Path,
    call_sequence: int,
    attempt_number: int,
    output_root: Path,
) -> dict:
    manifest = json.loads(manifest_path.read_bytes())
    call = manifest["calls"][call_sequence - 1]
    execution_root = output_root.parent / f"{output_root.name}-execution-source"
    status_path = execution_root / "http-status.txt"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_bytes(b"503\n")
    result = {
        "call_binding": {
            "atomic_manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "call_id": call["call_id"],
            "kind": "atomic",
            "orientation": manifest["orientation"],
            "prompt_sha256": call["prompt_sha256"],
            "replicate_id": manifest["replicate_id"],
            "sequence": call["sequence"],
        },
        "error": {
            "code": "OPENCODE_GO_STREAM_HTTP_FAILED",
            "details": {"status_code": 503},
            "message": "Synthetic provider failure",
        },
        "files": {"http-status.txt": sha256_bytes(b"503\n")},
        "preparation_manifest_sha256": "a" * 64,
        "receipt_sha256": None,
        "request_sha256": "b" * 64,
        "schema_version": ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION,
        "status": "fail",
    }
    result_path = _write(execution_root / "execution-result.json", result)
    return record_failed_attempt(
        manifest_path=manifest_path,
        call_sequence=call_sequence,
        attempt_number=attempt_number,
        execution_result_path=result_path,
        output_root=output_root,
    )


def test_prepare_atomic_removes_controller_owned_id_copying(tmp_path: Path) -> None:
    source = _source_bundle(tmp_path / "source.json")
    output = tmp_path / "prepared"

    manifest = prepare_atomic(
        bundle_path=source,
        replicate_id="r1",
        output_root=output,
    )

    assert manifest["call_count"] == 24
    assert manifest["status"] == "ready_for_atomic_execution"
    first = manifest["calls"][0]
    packet = (output / first["packet_path"]).read_text()
    prompt = (output / first["prompt_path"]).read_text()
    assert first["item_id"] not in packet
    assert first["item_id"] not in prompt
    assert "paper-left-" not in packet
    assert "segment-left-" not in packet
    assert '"handle":"L1"' in packet
    assert "bundle_sha256" not in prompt
    assert "item_id" not in prompt


def test_prepare_atomic_records_source_and_effective_evaluator(tmp_path: Path) -> None:
    source = _source_bundle(tmp_path / "source.json")
    bundle = json.loads(source.read_bytes())
    bundle["evaluator"]["reasoning_effort"] = "max"
    without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    bundle["bundle_sha256"] = sha256_bytes(canonical_json_bytes(without_hash))
    source.write_bytes(canonical_json_bytes(bundle))

    manifest = prepare_atomic(
        bundle_path=source,
        replicate_id="r1",
        output_root=tmp_path / "prepared",
        reasoning_effort="high",
    )

    assert manifest["source_evaluator"]["reasoning_effort"] == "max"
    assert manifest["evaluator"]["reasoning_effort"] == "high"


def test_first_valid_attempt_is_selected_and_handles_expand_privately(
    tmp_path: Path,
) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    attempt_paths = []
    for call in manifest["calls"]:
        call_number = call["sequence"]
        if call_number == 1:
            invalid = _write(tmp_path / "draft-invalid.json", {"winner": "left"})
            first = record_attempt(
                manifest_path=manifest_path,
                call_sequence=call_number,
                attempt_number=1,
                response_path=invalid,
                output_root=tmp_path / "attempts" / "call-001" / "attempt-1",
            )
            assert first["status"] == "invalid"
            attempt_paths.append(
                tmp_path / "attempts" / "call-001" / "attempt-1" / "attempt.json"
            )
            attempt_number = 2
        else:
            attempt_number = 1
        response = _write(
            tmp_path / f"draft-{call_number:03d}-{attempt_number}.json",
            _valid_response(),
        )
        attempt_root = (
            tmp_path
            / "attempts"
            / f"call-{call_number:03d}"
            / f"attempt-{attempt_number}"
        )
        outcome = record_attempt(
            manifest_path=manifest_path,
            call_sequence=call_number,
            attempt_number=attempt_number,
            response_path=response,
            output_root=attempt_root,
        )
        assert outcome["status"] == "valid"
        attempt_paths.append(attempt_root / "attempt.json")

    trace = resolve_orientation(
        manifest_path=manifest_path,
        attempt_paths=attempt_paths,
        output_root=tmp_path / "resolved",
    )

    assert trace["schema_version"] == ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION
    assert trace["status"] == "pass"
    assert trace["attempt_summary"] == {
        "first_attempt_valid_count": 23,
        "invalid_attempt_count": 1,
        "retried_call_count": 1,
        "total_physical_attempts": 25,
    }
    first_judgment = trace["judgments"][0]
    assert first_judgment["item_id"] == "item-00"
    assert first_judgment["evidence_refs"] == [
        {
            "handle": "L1",
            "paper_id": "paper-left-00-1",
            "segment_id": "segment-left-00-1",
            "side": "left",
        }
    ]


def test_resolver_forbids_retry_after_a_valid_response(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    attempt_paths = []
    for call in manifest["calls"]:
        for attempt_number in ((1, 2) if call["sequence"] == 1 else (1,)):
            response = _write(
                tmp_path / f"draft-{call['sequence']}-{attempt_number}.json",
                _valid_response(),
            )
            root = (
                tmp_path
                / "attempts"
                / f"call-{call['sequence']:03d}"
                / f"attempt-{attempt_number}"
            )
            record_attempt(
                manifest_path=manifest_path,
                call_sequence=call["sequence"],
                attempt_number=attempt_number,
                response_path=response,
                output_root=root,
            )
            attempt_paths.append(root / "attempt.json")

    with pytest.raises(HarnessError) as raised:
        resolve_orientation(
            manifest_path=manifest_path,
            attempt_paths=attempt_paths,
            output_root=tmp_path / "resolved",
        )

    assert raised.value.code == "RETRY_AFTER_VALID"


def _relabeled_atomic_manifest(
    prepared: Path, manifest_path: Path, schema_version: str
) -> dict:
    manifest = json.loads(manifest_path.read_bytes())
    if schema_version in (
        "local-ranking-atomic-preparation-v2.2",
        "local-ranking-atomic-preparation-v2.3",
    ):
        # Rebuild every prompt with the frozen legacy JSON prompt so the
        # manifest binds genuine legacy bytes instead of relabelled new ones.
        del manifest["response_submission"]
        for call in manifest["calls"]:
            packet = json.loads((prepared / call["packet_path"]).read_bytes())
            prompt_bytes = _legacy_prompt_text(packet).encode("utf-8")
            (prepared / call["prompt_path"]).write_bytes(prompt_bytes)
            call["prompt_bytes"] = len(prompt_bytes)
            call["prompt_sha256"] = sha256_bytes(prompt_bytes)
    elif schema_version == "local-ranking-atomic-preparation-v2.4":
        # The spent canary family shares the current tool prompt bytes.
        del manifest["response_submission"]
    else:
        raise AssertionError(f"unsupported test relabel target {schema_version}")
    manifest["schema_version"] = schema_version
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    return manifest


def test_retry_correction_accepts_legacy_manifest_and_attempts(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    _relabeled_atomic_manifest(
        prepared, manifest_path, "local-ranking-atomic-preparation-v2.2"
    )
    attempt_paths = []
    for call in manifest["calls"]:
        response = _write(
            tmp_path / "responses" / f"{call['call_id']}.json",
            _valid_response(),
        )
        attempt_root = tmp_path / "attempts" / call["call_id"] / "attempt-1"
        outcome = record_attempt(
            receipt_family="legacy",
            manifest_path=manifest_path,
            call_sequence=call["sequence"],
            attempt_number=1,
            response_path=response,
            output_root=attempt_root,
        )
        assert outcome["schema_version"] == "local-ranking-atomic-attempt-v2.4"
        attempt_path = attempt_root / "attempt.json"
        if call["sequence"] == 1:
            legacy_attempt = json.loads(attempt_path.read_bytes())
            legacy_attempt["schema_version"] = "local-ranking-atomic-attempt-v2.3"
            attempt_path.write_bytes(canonical_json_bytes(legacy_attempt))
        attempt_paths.append(attempt_path)

    trace = resolve_orientation(
        manifest_path=manifest_path,
        attempt_paths=attempt_paths,
        output_root=tmp_path / "resolved",
    )

    assert trace["status"] == "pass"
    assert trace["attempt_summary"]["total_physical_attempts"] == 24
    attempt = json.loads(attempt_paths[0].read_bytes())
    assert attempt["schema_version"] == "local-ranking-atomic-attempt-v2.3"
    legacy_receipt = json.loads(
        (attempt_paths[0].parent / "execution-receipt.json").read_bytes()
    )
    assert legacy_receipt["schema_version"] == (
        "local-ranking-atomic-opencode-go-receipt-v2.0"
    )
    assert legacy_receipt["identity"]["finish_reason"] == "stop"


def test_spent_canary_family_accepts_tool_prompt_without_submission_enum(
    tmp_path: Path,
) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    _relabeled_atomic_manifest(
        prepared, manifest_path, "local-ranking-atomic-preparation-v2.4"
    )
    response = _write(tmp_path / "response.json", _valid_response())

    outcome = record_attempt(
        manifest_path=manifest_path,
        call_sequence=1,
        attempt_number=1,
        response_path=response,
        output_root=tmp_path / "attempt",
    )

    assert outcome["status"] == "valid"
    assert outcome["schema_version"] == "local-ranking-atomic-attempt-v2.5"


@pytest.mark.parametrize(
    ("manifest_version", "receipt_family", "result_family", "expected_code"),
    [
        ("v2.5", "legacy", "legacy", "INVALID_EXECUTION_RECEIPT"),
        ("v2.5", "tool", "legacy", "INVALID_EXECUTION_RESULT"),
        ("v2.2", "tool", "tool", "INVALID_EXECUTION_RECEIPT"),
        ("v2.2", "legacy", "tool", "INVALID_EXECUTION_RESULT"),
        ("v2.4", "legacy", "legacy", "INVALID_EXECUTION_RECEIPT"),
    ],
)
def test_record_attempt_pairs_manifest_and_evidence_transport_families(
    tmp_path: Path,
    manifest_version: str,
    receipt_family: str,
    result_family: str,
    expected_code: str,
) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    if manifest_version != "v2.5":
        _relabeled_atomic_manifest(
            prepared,
            manifest_path,
            f"local-ranking-atomic-preparation-{manifest_version}",
        )
    response = _write(tmp_path / "response.json", _valid_response())

    with pytest.raises(HarnessError) as raised:
        record_attempt(
            receipt_family=receipt_family,
            result_family=result_family,
            manifest_path=manifest_path,
            call_sequence=1,
            attempt_number=1,
            response_path=response,
            output_root=tmp_path / "attempt",
        )

    assert raised.value.code == expected_code


def test_resolve_orientation_rejects_attempt_from_the_wrong_family(
    tmp_path: Path,
) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    _relabeled_atomic_manifest(
        prepared, manifest_path, "local-ranking-atomic-preparation-v2.2"
    )
    attempt_paths = []
    for call in manifest["calls"]:
        response = _write(
            tmp_path / "responses" / f"{call['call_id']}.json",
            _valid_response(),
        )
        attempt_root = tmp_path / "attempts" / call["call_id"] / "attempt-1"
        record_attempt(
            receipt_family="legacy",
            manifest_path=manifest_path,
            call_sequence=call["sequence"],
            attempt_number=1,
            response_path=response,
            output_root=attempt_root,
        )
        attempt_path = attempt_root / "attempt.json"
        if call["sequence"] == 1:
            misplaced = json.loads(attempt_path.read_bytes())
            misplaced["schema_version"] = "local-ranking-atomic-attempt-v2.5"
            attempt_path.write_bytes(canonical_json_bytes(misplaced))
        attempt_paths.append(attempt_path)

    with pytest.raises(HarnessError) as raised:
        resolve_orientation(
            manifest_path=manifest_path,
            attempt_paths=attempt_paths,
            output_root=tmp_path / "resolved",
        )

    assert raised.value.code == "ATTEMPT_IDENTITY_MISMATCH"


def test_new_writers_emit_only_tool_transport_schema_versions(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    response = _write(tmp_path / "response.json", _valid_response())

    outcome = record_attempt(
        manifest_path=manifest_path,
        call_sequence=1,
        attempt_number=1,
        response_path=response,
        output_root=tmp_path / "attempt",
    )

    assert manifest["schema_version"] == "local-ranking-atomic-preparation-v2.5"
    assert manifest["schema_version"] == ATOMIC_PREPARATION_SCHEMA_VERSION
    assert manifest["response_submission"] == "forced_submit_judgment_tool"
    assert manifest["response_submission"] == ATOMIC_RESPONSE_SUBMISSION
    assert outcome["schema_version"] == "local-ranking-atomic-attempt-v2.5"
    receipt = json.loads((tmp_path / "attempt" / "execution-receipt.json").read_bytes())
    assert receipt["schema_version"] == ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION
    assert receipt["identity"]["finish_reason"] == "tool_calls"
    assert receipt["identity"]["tool_call_id"]
    assert receipt["tool"] == {
        "name": "submit_judgment",
        "schema_sha256": sha256_bytes(canonical_json_bytes(SUBMIT_JUDGMENT_TOOL)),
    }
    result = json.loads((tmp_path / "attempt" / "execution-result.json").read_bytes())
    assert result["schema_version"] == ATOMIC_EXECUTION_RESULT_SCHEMA_VERSION


def test_record_attempt_rejects_receipt_outside_tool_finish_allowlist(
    tmp_path: Path,
) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    response = _write(tmp_path / "response.json", _valid_response())
    attempt_root = tmp_path / "attempt"

    record_attempt(
        manifest_path=manifest_path,
        call_sequence=1,
        attempt_number=1,
        response_path=response,
        output_root=attempt_root,
    )
    receipt_path = (
        attempt_root.parent / f"{attempt_root.name}-execution-source" / ("receipt.json")
    )
    receipt = json.loads(receipt_path.read_bytes())
    receipt["identity"]["finish_reason"] = "length"
    receipt_path.write_bytes(canonical_json_bytes(receipt))

    with pytest.raises(HarnessError) as raised_after_drift:
        _record_attempt(
            manifest_path=manifest_path,
            call_sequence=1,
            attempt_number=1,
            response_path=response,
            execution_receipt_path=receipt_path,
            execution_result_path=receipt_path.parent / "execution-result.json",
            output_root=tmp_path / "attempt-drifted",
        )

    assert raised_after_drift.value.code == "INVALID_EXECUTION_RECEIPT"


def test_record_attempt_rejects_receipt_with_wrong_tool_schema(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    response = _write(tmp_path / "response.json", _valid_response())
    attempt_root = tmp_path / "attempt"

    record_attempt(
        manifest_path=manifest_path,
        call_sequence=1,
        attempt_number=1,
        response_path=response,
        output_root=attempt_root,
    )
    receipt_path = (
        attempt_root.parent / f"{attempt_root.name}-execution-source" / ("receipt.json")
    )
    receipt = json.loads(receipt_path.read_bytes())
    receipt["tool"]["schema_sha256"] = "0" * 64
    receipt_path.write_bytes(canonical_json_bytes(receipt))

    with pytest.raises(HarnessError) as raised:
        _record_attempt(
            manifest_path=manifest_path,
            call_sequence=1,
            attempt_number=1,
            response_path=response,
            execution_receipt_path=receipt_path,
            execution_result_path=receipt_path.parent / "execution-result.json",
            output_root=tmp_path / "attempt-drifted",
        )

    assert raised.value.code == "INVALID_EXECUTION_RECEIPT"


def test_four_invalid_attempts_exhaust_one_logical_call(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    attempt_paths = []
    for call in manifest["calls"]:
        numbers = range(1, 5) if call["sequence"] == 1 else (1,)
        for attempt_number in numbers:
            response_value = (
                {"winner": "left"} if call["sequence"] == 1 else _valid_response()
            )
            response = _write(
                tmp_path / f"draft-{call['sequence']}-{attempt_number}.json",
                response_value,
            )
            root = (
                tmp_path
                / "attempts"
                / f"call-{call['sequence']:03d}"
                / f"attempt-{attempt_number}"
            )
            record_attempt(
                manifest_path=manifest_path,
                call_sequence=call["sequence"],
                attempt_number=attempt_number,
                response_path=response,
                output_root=root,
            )
            attempt_paths.append(root / "attempt.json")

    with pytest.raises(HarnessError) as raised:
        resolve_orientation(
            manifest_path=manifest_path,
            attempt_paths=attempt_paths,
            output_root=tmp_path / "resolved",
        )

    assert raised.value.code == "LOGICAL_CALL_EXHAUSTED"


def test_transport_failure_counts_as_first_physical_attempt(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    attempt_paths = []
    failed_root = tmp_path / "attempts" / "call-001" / "attempt-1"
    failed = _failed_attempt(
        manifest_path=manifest_path,
        call_sequence=1,
        attempt_number=1,
        output_root=failed_root,
    )
    assert failed["status"] == "invalid"
    assert failed["provider_response_id"] is None
    attempt_paths.append(failed_root / "attempt.json")
    for call in manifest["calls"]:
        attempt_number = 2 if call["sequence"] == 1 else 1
        response = _write(
            tmp_path / f"response-{call['sequence']:03d}.json", _valid_response()
        )
        attempt_root = (
            tmp_path / "attempts" / call["call_id"] / f"attempt-{attempt_number}"
        )
        record_attempt(
            manifest_path=manifest_path,
            call_sequence=call["sequence"],
            attempt_number=attempt_number,
            response_path=response,
            output_root=attempt_root,
        )
        attempt_paths.append(attempt_root / "attempt.json")

    trace = resolve_orientation(
        manifest_path=manifest_path,
        attempt_paths=attempt_paths,
        output_root=tmp_path / "resolved",
    )

    assert trace["attempt_summary"]["retried_call_count"] == 1
    assert len(trace["selected_attempts"][0]["provider_response_ids"]) == 1


def test_orientation_runner_retries_only_invalid_response(tmp_path: Path) -> None:
    atomic_root = tmp_path / "atomic"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=atomic_root,
    )
    manifest_path = atomic_root / "private" / "manifest.json"
    preparation_root = tmp_path / "transport"
    prepare_atomic_transport(
        atomic_manifest_path=manifest_path,
        output_root=preparation_root,
        max_concurrency=4,
    )
    lock = threading.Lock()
    request_count = 0
    first_item_seen = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count, first_item_seen
        prompt = json.loads(request.content)["messages"][0]["content"]
        with lock:
            request_count += 1
            response_id = f"runner-response-{request_count:03d}"
            is_first_item = "query 0?" in prompt
            if is_first_item:
                first_item_seen += 1
                invalid = first_item_seen == 1
            else:
                invalid = False
        response = {"winner": "left"} if invalid else _valid_response()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_semantic_stream(response_id=response_id, response=response),
        )

    result = run_orientation(
        atomic_manifest_path=manifest_path,
        preparation_root=preparation_root,
        output_root=tmp_path / "run",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert result["run_result"]["status"] == "pass"
    assert result["run_result"]["schema_version"] == (
        "local-ranking-atomic-orientation-run-v2.2"
    )
    assert request_count == 25
    assert result["trace"]["attempt_summary"] == {
        "first_attempt_valid_count": 23,
        "invalid_attempt_count": 1,
        "retried_call_count": 1,
        "total_physical_attempts": 25,
    }
    assert manifest["call_count"] == 24

    replay = run_orientation(
        atomic_manifest_path=manifest_path,
        preparation_root=preparation_root,
        output_root=tmp_path / "run",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    assert replay == result
    assert request_count == 25


def test_orientation_runner_accepts_first_valid_on_fourth_attempt(
    tmp_path: Path,
) -> None:
    atomic_root = tmp_path / "atomic"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=atomic_root,
    )
    manifest_path = atomic_root / "private" / "manifest.json"
    preparation_root = tmp_path / "transport"
    prepare_atomic_transport(
        atomic_manifest_path=manifest_path,
        output_root=preparation_root,
        max_concurrency=4,
    )
    lock = threading.Lock()
    request_count = 0
    first_item_seen = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count, first_item_seen
        prompt = json.loads(request.content)["messages"][0]["content"]
        with lock:
            request_count += 1
            response_id = f"fourth-attempt-response-{request_count:03d}"
            is_first_item = "query 0?" in prompt
            if is_first_item:
                first_item_seen += 1
                invalid = first_item_seen < 4
            else:
                invalid = False
        response = {"winner": "left"} if invalid else _valid_response()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_semantic_stream(response_id=response_id, response=response),
        )

    result = run_orientation(
        atomic_manifest_path=manifest_path,
        preparation_root=preparation_root,
        output_root=tmp_path / "run-fourth",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert result["run_result"]["status"] == "pass"
    assert request_count == 27
    assert result["trace"]["attempt_summary"] == {
        "first_attempt_valid_count": 23,
        "invalid_attempt_count": 3,
        "retried_call_count": 1,
        "total_physical_attempts": 27,
    }
    assert result["trace"]["selected_attempts"][0]["selected_attempt_number"] == 4


def test_orientation_runner_stops_after_four_invalid_attempts(tmp_path: Path) -> None:
    atomic_root = tmp_path / "atomic"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=atomic_root,
    )
    manifest_path = atomic_root / "private" / "manifest.json"
    preparation_root = tmp_path / "transport"
    prepare_atomic_transport(
        atomic_manifest_path=manifest_path,
        output_root=preparation_root,
        max_concurrency=4,
    )
    lock = threading.Lock()
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        prompt = json.loads(request.content)["messages"][0]["content"]
        with lock:
            request_count += 1
            response_id = f"exhausted-response-{request_count:03d}"
        response = {"winner": "left"} if "query 0?" in prompt else _valid_response()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_semantic_stream(response_id=response_id, response=response),
        )

    run_root = tmp_path / "run-exhausted"
    with pytest.raises(HarnessError) as raised:
        run_orientation(
            atomic_manifest_path=manifest_path,
            preparation_root=preparation_root,
            output_root=run_root,
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    assert raised.value.code == "ORIENTATION_INCOMPLETE"
    assert request_count == 27
    assert json.loads((run_root / "run-result.json").read_bytes())["status"] == (
        "incomplete"
    )
    assert len(list((run_root / "attempts" / "call-001").glob("*/attempt.json"))) == 4


def test_orientation_runner_fails_closed_on_ambiguous_partial_attempt(
    tmp_path: Path,
) -> None:
    atomic_root = tmp_path / "atomic"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=atomic_root,
    )
    manifest_path = atomic_root / "private" / "manifest.json"
    preparation_root = tmp_path / "transport"
    prepare_atomic_transport(
        atomic_manifest_path=manifest_path,
        output_root=preparation_root,
        max_concurrency=4,
    )
    run_root = tmp_path / "run-interrupted"
    partial = run_root / "executions" / "call-001" / "attempt-1"
    partial.mkdir(parents=True)
    (partial / "started-at.txt").write_bytes(b"2026-09-02T00:00:00Z\n")

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be sent while a partial attempt exists")

    with pytest.raises(HarnessError) as raised:
        run_orientation(
            atomic_manifest_path=manifest_path,
            preparation_root=preparation_root,
            output_root=run_root,
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    assert raised.value.code == "AMBIGUOUS_PARTIAL_ATTEMPT"


@pytest.mark.parametrize(
    ("side", "schema_version", "expected_code"),
    [
        (
            "atomic",
            "local-ranking-atomic-preparation-v2.2",
            "INVALID_ATOMIC_MANIFEST",
        ),
        (
            "atomic",
            "local-ranking-atomic-preparation-v2.4",
            "INVALID_ATOMIC_MANIFEST",
        ),
        (
            "transport",
            "local-ranking-atomic-opencode-go-preparation-v3.0",
            "INVALID_PREPARATION",
        ),
    ],
)
def test_orientation_runner_requires_current_preparation_families(
    tmp_path: Path, side: str, schema_version: str, expected_code: str
) -> None:
    atomic_root = tmp_path / "atomic"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=atomic_root,
    )
    manifest_path = atomic_root / "private" / "manifest.json"
    preparation_root = tmp_path / "transport"
    prepare_atomic_transport(
        atomic_manifest_path=manifest_path,
        output_root=preparation_root,
        max_concurrency=4,
    )
    transport_path = preparation_root / "manifest.json"
    transport = json.loads(transport_path.read_bytes())
    if side == "atomic":
        _relabeled_atomic_manifest(atomic_root, manifest_path, schema_version)
        transport["atomic_manifest_sha256"] = sha256_bytes(manifest_path.read_bytes())
    else:
        del transport["response_submission"]
        transport["schema_version"] = schema_version
    transport_path.write_bytes(canonical_json_bytes(transport))

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError(
            "runner must reject non-current families before any request"
        )

    run_root = tmp_path / "run"
    with pytest.raises(HarnessError) as raised:
        run_orientation(
            atomic_manifest_path=manifest_path,
            preparation_root=preparation_root,
            output_root=run_root,
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    assert raised.value.code == expected_code
    assert not run_root.exists()


CANARY_IMPLEMENTATION_COMMIT = "fa2409ff1d955cb546aec27f08de7ae62412e130"


def _canary_summary(path: Path, **overrides: object) -> Path:
    summary: dict[str, object] = {
        "authorization": "atomic tool-output contract v2.3 section 6 (Robert, 2026-09-02)",
        "evidence_class": "spent_transport_only",
        "implementation_commit": CANARY_IMPLEMENTATION_COMMIT,
        "max_tokens": 16_384,
        "notes": "Synthetic closed-schema canary summary for profile binding tests.",
        "physical_call_count": 2,
        "prepare_only_inputs": {
            "atomic_manifest_sha256": "a" * 64,
            "transport_manifest_sha256": "b" * 64,
        },
        "provider_model": "opencode-go/deepseek-v4-pro",
        "reasoning_effort": "max",
        "stress_canary": {
            "attempt_1": {
                "attempt_sha256": "c" * 64,
                "cost": "0",
                "execution_result_sha256": "d" * 64,
                "finish_reason": "tool_calls",
                "provider_response_id": "chatcmpl-stress",
                "receipt_sha256": "e" * 64,
                "response_sha256": "f" * 64,
                "semantic_validator": {"error": None, "status": "pass"},
                "status": "valid",
                "tool_call_id": "chatcmpl-tool-stress",
                "usage": {
                    "cached_tokens": 0,
                    "completion_tokens": 100,
                    "prompt_tokens": 200,
                    "reasoning_tokens": 50,
                    "total_tokens": 300,
                },
            },
            "attempts_sent": 1,
            "call_id": "call-021",
            "stop_condition": "first-valid stop (canary PASS)",
        },
        "synthetic_probe": {
            "call_id": "smoke-001",
            "cost": "0",
            "finish_reason": "tool_calls",
            "provider_response_id": "chatcmpl-probe",
            "receipt_sha256": "1" * 64,
            "response_sha256": "2" * 64,
            "tool_call_id": "chatcmpl-tool-probe",
            "usage": {
                "cached_tokens": 0,
                "completion_tokens": 10,
                "prompt_tokens": 20,
                "reasoning_tokens": 5,
                "total_tokens": 30,
            },
            "validator": "validate-smoke-call: pass",
        },
        "usage_percent_after": {"monthly": 40, "rolling": 0, "weekly": 33},
        "usage_percent_before": {"monthly": 40, "rolling": 0, "weekly": 32},
        "usage_snapshot_after_sha256": "3" * 64,
        "usage_snapshot_before_sha256": "4" * 64,
    }
    summary.update(overrides)
    return _write(path, summary)


def _profile_replicates(tmp_path: Path) -> list[dict[str, Path | str]]:
    replicates = []
    for replicate_index in range(1, 4):
        replicate_id = f"r{replicate_index}"
        entry: dict[str, Path | str] = {"replicate_id": replicate_id}
        for orientation in (1, 2):
            atomic_root = tmp_path / replicate_id / f"o{orientation}" / "atomic"
            prepare_atomic(
                bundle_path=_source_bundle(
                    tmp_path / f"source-o{orientation}.json", orientation=orientation
                ),
                replicate_id=replicate_id,
                output_root=atomic_root,
                reasoning_effort="max",
            )
            atomic_path = atomic_root / "private" / "manifest.json"
            preparation_root = tmp_path / replicate_id / f"o{orientation}" / "transport"
            prepare_atomic_transport(
                atomic_manifest_path=atomic_path,
                output_root=preparation_root,
                max_concurrency=4,
            )
            entry[f"orientation_{orientation}_atomic"] = atomic_path
            entry[f"orientation_{orientation}_preparation"] = preparation_root
        replicates.append(entry)
    return replicates


def _usage_snapshot(path: Path) -> Path:
    return _write(
        path,
        {
            "captured_at": "2026-09-01T00:00:00Z",
            "model_id": "deepseek-v4-pro",
            "model_present": True,
            "models_http_status": 200,
            "models_url": "https://opencode.ai/zen/go/v1/models",
            "schema_version": USAGE_SNAPSHOT_SCHEMA_VERSION,
            "status": "pass",
            "usage": {
                period: {
                    "percent": 10,
                    "resetsAt": "2026-09-02T00:00:00Z",
                    "status": "ok",
                }
                for period in ("rolling", "weekly", "monthly")
            },
            "usage_http_status": 200,
            "usage_url": "https://opencode.ai/zen/go/v1/usage",
        },
    )


def test_profile_manifest_binds_six_orientations_and_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replicates = _profile_replicates(tmp_path)
    usage_snapshot = _usage_snapshot(tmp_path / "usage.json")
    canary_summary = _canary_summary(tmp_path / "canary-summary.json")
    canary_summary_sha256 = sha256_bytes(canary_summary.read_bytes())
    monkeypatch.setattr(
        atomic_profile, "TRANSPORT_CANARY_SUMMARY_SHA256", canary_summary_sha256
    )

    profile = prepare_profile(
        replicates=replicates,
        source_commit="a" * 40,
        reasoning_effort="max",
        usage_snapshot_path=usage_snapshot,
        smoke_result_sha256="b" * 64,
        canary_summary_path=canary_summary,
        output_path=tmp_path / "profile.json",
    )

    assert profile["budget"] == {
        "logical_calls": 144,
        "max_concurrency": 4,
        "max_physical_calls": 576,
        "max_tokens_per_call": 16_384,
    }
    assert len(profile["replicates"]) == 3
    assert all(len(item["orientations"]) == 2 for item in profile["replicates"])
    assert profile["status"] == "ready_for_pro_max_calibration"
    assert profile["schema_version"] == "local-ranking-atomic-profile-manifest-v2.2"
    assert profile["response_submission"] == "forced_submit_judgment_tool"
    assert profile["transport_canary_summary_sha256"] == canary_summary_sha256
    assert profile["canary_implementation_commit"] == CANARY_IMPLEMENTATION_COMMIT


def test_profile_requires_the_frozen_canary_summary_hash(tmp_path: Path) -> None:
    canary_summary = _canary_summary(tmp_path / "canary-summary.json")

    with pytest.raises(HarnessError) as raised:
        prepare_profile(
            replicates=_profile_replicates(tmp_path),
            source_commit="a" * 40,
            reasoning_effort="max",
            usage_snapshot_path=_usage_snapshot(tmp_path / "usage.json"),
            smoke_result_sha256="b" * 64,
            canary_summary_path=canary_summary,
            output_path=tmp_path / "profile.json",
        )

    assert raised.value.code == "CANARY_SUMMARY_MISMATCH"
    assert TRANSPORT_CANARY_SUMMARY_SHA256 == (
        "900b49b59c72f3da4282e2cf7d58affb7df0678421a9f042cf868db4a6b26749"
    )


def test_prepare_profile_has_no_canary_hash_override_parameter() -> None:
    assert "expected_canary_summary_sha256" not in (
        inspect.signature(prepare_profile).parameters
    )


@pytest.mark.parametrize(
    "override",
    [
        {"evidence_class": "semantic_vote"},
        {"physical_call_count": 0},
        {"physical_call_count": 6},
        {"provider_model": "opencode-go/deepseek-v4-flash"},
        {"reasoning_effort": "high"},
        {"max_tokens": 8192},
        {"implementation_commit": "0" * 40},
        {"synthetic_probe": {"validator": "validate-smoke-call: fail"}},
        {"stress_canary": {"stop_condition": "exhausted after four attempts"}},
        {
            "stress_canary": {
                "attempt_1": {"semantic_validator": {"error": {}, "status": "fail"}},
                "stop_condition": "first-valid stop (canary PASS)",
            }
        },
    ],
)
def test_profile_rejects_incomplete_or_failed_canary_summary(
    tmp_path: Path, override: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary_summary = _canary_summary(tmp_path / "canary-summary.json", **override)
    monkeypatch.setattr(
        atomic_profile,
        "TRANSPORT_CANARY_SUMMARY_SHA256",
        sha256_bytes(canary_summary.read_bytes()),
    )

    with pytest.raises(HarnessError) as raised:
        prepare_profile(
            replicates=_profile_replicates(tmp_path),
            source_commit="a" * 40,
            reasoning_effort="max",
            usage_snapshot_path=_usage_snapshot(tmp_path / "usage.json"),
            smoke_result_sha256="b" * 64,
            canary_summary_path=canary_summary,
            output_path=tmp_path / "profile.json",
        )

    assert raised.value.code == "INVALID_CANARY_SUMMARY"


@pytest.mark.parametrize(
    ("atomic_version", "transport_version"),
    [
        ("local-ranking-atomic-preparation-v2.4", None),
        (None, "local-ranking-atomic-opencode-go-preparation-v3.0"),
    ],
)
def test_profile_requires_current_orientation_manifests(
    tmp_path: Path,
    atomic_version: str | None,
    transport_version: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replicates = _profile_replicates(tmp_path)
    first = replicates[0]
    atomic_path = first["orientation_1_atomic"]
    assert isinstance(atomic_path, Path)
    if atomic_version is not None:
        _relabeled_atomic_manifest(
            atomic_path.parent.parent, atomic_path, atomic_version
        )
    if transport_version is not None:
        preparation_root = first["orientation_1_preparation"]
        assert isinstance(preparation_root, Path)
        transport_path = preparation_root / "manifest.json"
        transport = json.loads(transport_path.read_bytes())
        del transport["response_submission"]
        transport["schema_version"] = transport_version
        transport_path.write_bytes(canonical_json_bytes(transport))
    canary_summary = _canary_summary(tmp_path / "canary-summary.json")
    monkeypatch.setattr(
        atomic_profile,
        "TRANSPORT_CANARY_SUMMARY_SHA256",
        sha256_bytes(canary_summary.read_bytes()),
    )

    with pytest.raises(HarnessError) as raised:
        prepare_profile(
            replicates=replicates,
            source_commit="a" * 40,
            reasoning_effort="max",
            usage_snapshot_path=_usage_snapshot(tmp_path / "usage.json"),
            smoke_result_sha256="b" * 64,
            canary_summary_path=canary_summary,
            output_path=tmp_path / "profile.json",
        )

    assert raised.value.code == "PROFILE_BINDING_MISMATCH"


@pytest.mark.parametrize(
    ("tamper", "expected_code"),
    [
        ("atomic", "INVALID_ATOMIC_MANIFEST"),
        ("transport", "INVALID_PREPARATION"),
    ],
)
def test_profile_rejects_divergent_response_submission(
    tmp_path: Path, tamper: str, expected_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    replicates = _profile_replicates(tmp_path)
    first = replicates[0]
    if tamper == "atomic":
        manifest_path = first["orientation_1_atomic"]
    else:
        preparation_root = first["orientation_1_preparation"]
        assert isinstance(preparation_root, Path)
        manifest_path = preparation_root / "manifest.json"
    assert isinstance(manifest_path, Path)
    manifest = json.loads(manifest_path.read_bytes())
    manifest["response_submission"] = "free_content_json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    canary_summary = _canary_summary(tmp_path / "canary-summary.json")
    monkeypatch.setattr(
        atomic_profile,
        "TRANSPORT_CANARY_SUMMARY_SHA256",
        sha256_bytes(canary_summary.read_bytes()),
    )

    with pytest.raises(HarnessError) as raised:
        prepare_profile(
            replicates=replicates,
            source_commit="a" * 40,
            reasoning_effort="max",
            usage_snapshot_path=_usage_snapshot(tmp_path / "usage.json"),
            smoke_result_sha256="b" * 64,
            canary_summary_path=canary_summary,
            output_path=tmp_path / "profile.json",
        )

    assert raised.value.code == expected_code


def test_unknown_handle_is_machine_detectable_invalid(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    response = _valid_response()
    response["evidence_handles"] = ["L9"]

    outcome = record_attempt(
        manifest_path=prepared / "private" / "manifest.json",
        call_sequence=1,
        attempt_number=1,
        response_path=_write(tmp_path / "response.json", response),
        output_root=tmp_path / "attempt",
    )

    assert outcome["status"] == "invalid"
    assert outcome["validation"]["error"]["code"] == "INVALID_EVIDENCE_HANDLE"


def test_rationale_has_no_redundant_semantic_length_ceiling(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    response = _valid_response()
    response["rationale"] = "Grounded visible evidence. " * 100

    outcome = record_attempt(
        manifest_path=prepared / "private" / "manifest.json",
        call_sequence=1,
        attempt_number=1,
        response_path=_write(tmp_path / "response.json", response),
        output_root=tmp_path / "attempt",
    )

    assert len(response["rationale"]) > 800
    assert outcome["status"] == "valid"


def test_empty_rationale_remains_machine_detectable_invalid(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    response = _valid_response()
    response["rationale"] = ""

    outcome = record_attempt(
        manifest_path=prepared / "private" / "manifest.json",
        call_sequence=1,
        attempt_number=1,
        response_path=_write(tmp_path / "response.json", response),
        output_root=tmp_path / "attempt",
    )

    assert outcome["status"] == "invalid"
    assert outcome["validation"]["error"]["code"] == "INVALID_ATOMIC_RESPONSE"


def test_resolved_atomic_traces_feed_calibration_end_to_end(tmp_path: Path) -> None:
    replicates = []
    for replicate_number in range(1, 4):
        replicate_id = f"r{replicate_number}"
        replicate: dict[str, Path | str] = {"replicate_id": replicate_id}
        for orientation in (1, 2):
            root = tmp_path / replicate_id / f"orientation-{orientation}"
            prepared = root / "prepared"
            manifest = prepare_atomic(
                bundle_path=_source_bundle(
                    root / "source.json", orientation=orientation
                ),
                replicate_id=replicate_id,
                output_root=prepared,
            )
            manifest_path = prepared / "private" / "manifest.json"
            attempts = []
            for call in manifest["calls"]:
                response = _write(
                    root / "responses" / f"{call['call_id']}.json",
                    _valid_response(winner="left" if orientation == 1 else "right"),
                )
                attempt_root = root / "attempts" / call["call_id"]
                record_attempt(
                    manifest_path=manifest_path,
                    call_sequence=call["sequence"],
                    attempt_number=1,
                    response_path=response,
                    output_root=attempt_root,
                )
                attempts.append(attempt_root / "attempt.json")
            resolved = root / "resolved"
            resolve_orientation(
                manifest_path=manifest_path,
                attempt_paths=attempts,
                output_root=resolved,
            )
            replicate[f"orientation_{orientation}_trace"] = resolved / "trace.json"
        replicates.append(replicate)

    result = aggregate(
        replicates=replicates,
        output_path=tmp_path / "calibration.json",
    )

    assert result["status"] == "pass"
    assert result["pooled_stable_count"] == 72
    assert result["attempt_diagnostics"]["total_physical_attempts"] == 144


def test_prepare_atomic_prompt_requires_exactly_one_tool_call(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )

    first = manifest["calls"][0]
    prompt = (prepared / first["prompt_path"]).read_text()
    assert manifest["schema_version"] == "local-ranking-atomic-preparation-v2.5"
    assert manifest["response_submission"] == "forced_submit_judgment_tool"
    assert "No external or retrieval tools are available" in prompt
    assert "submit_judgment" in prompt
    assert "Call submit_judgment exactly once" in prompt
    assert "No tools are available" not in prompt
    assert "Return exactly one JSON object" not in prompt
    assert "response_format" not in prompt


def test_repeated_atomic_prepare_is_byte_identical(tmp_path: Path) -> None:
    source = _source_bundle(tmp_path / "source.json")
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = prepare_atomic(
        bundle_path=source, replicate_id="r1", output_root=first_root
    )
    second = prepare_atomic(
        bundle_path=source, replicate_id="r1", output_root=second_root
    )

    assert first == second
    first_files = sorted(
        path.relative_to(first_root) for path in first_root.rglob("*") if path.is_file()
    )
    second_files = sorted(
        path.relative_to(second_root)
        for path in second_root.rglob("*")
        if path.is_file()
    )
    assert first_files == second_files
    for relative in first_files:
        assert (first_root / relative).read_bytes() == (
            second_root / relative
        ).read_bytes()

    first_transport = tmp_path / "first-transport"
    second_transport = tmp_path / "second-transport"
    prepare_atomic_transport(
        atomic_manifest_path=first_root / "private" / "manifest.json",
        output_root=first_transport,
    )
    prepare_atomic_transport(
        atomic_manifest_path=second_root / "private" / "manifest.json",
        output_root=second_transport,
    )
    transport_files = sorted(
        path.relative_to(first_transport)
        for path in first_transport.rglob("*")
        if path.is_file()
    )
    assert transport_files == sorted(
        path.relative_to(second_transport)
        for path in second_transport.rglob("*")
        if path.is_file()
    )
    for relative in transport_files:
        assert (first_transport / relative).read_bytes() == (
            second_transport / relative
        ).read_bytes()
