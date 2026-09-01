from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.atomic_calibration import aggregate
from prototypes.local_ranking.atomic_judge import (
    ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION,
    ATOMIC_ORIENTATION_TRACE_SCHEMA_VERSION,
    prepare_atomic,
    resolve_orientation,
)
from prototypes.local_ranking.atomic_judge import (
    record_attempt as _record_attempt,
)
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


def record_attempt(**kwargs):
    manifest_path = kwargs["manifest_path"]
    response_path = kwargs["response_path"]
    output_root = kwargs["output_root"]
    manifest = json.loads(manifest_path.read_bytes())
    call = manifest["calls"][kwargs["call_sequence"] - 1]
    response_bytes = response_path.read_bytes()
    response_id = "test-" + sha256_bytes(str(output_root).encode())[:24]
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
        "identity": {
            "cost": "0",
            "created_first": 1,
            "created_last": 1,
            "finish_reason": "stop",
            "model": "deepseek-v4-pro",
            "provider_response_id": response_id,
        },
        "preparation_manifest_sha256": "a" * 64,
        "provider": "opencode-go",
        "request_sha256": "b" * 64,
        "schema_version": ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "status": "pass",
        "transport_qualification": {
            "json_object_accepted": True,
            "reasoning_effort_requested": manifest["evaluator"]["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        },
        "usage": None,
    }
    receipt_path = _write(
        output_root.parent / f"{output_root.name}-receipt.json", receipt
    )
    return _record_attempt(execution_receipt_path=receipt_path, **kwargs)


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


def test_two_invalid_attempts_exhaust_one_logical_call(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared"
    manifest = prepare_atomic(
        bundle_path=_source_bundle(tmp_path / "source.json"),
        replicate_id="r1",
        output_root=prepared,
    )
    manifest_path = prepared / "private" / "manifest.json"
    attempt_paths = []
    for call in manifest["calls"]:
        numbers = (1, 2) if call["sequence"] == 1 else (1,)
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
