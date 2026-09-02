from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from prototypes.local_ranking.atomic_judge import (
    SUBMIT_JUDGMENT_SCHEMA,
    SUBMIT_JUDGMENT_TOOL,
    SUBMIT_JUDGMENT_TOOL_CHOICE,
)
from prototypes.local_ranking.atomic_opencode_go import (
    ATOMIC_MAX_TOKENS,
    _legacy_request,
    _smoke_probe_arguments,
    _validate_preparation,
    execute_call,
    prepare_smoke,
    run_smoke,
    validate_smoke_call,
)
from prototypes.local_ranking.atomic_profile import snapshot_usage
from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError


def _event(value: object) -> bytes:
    payload = (
        "[DONE]" if value == "[DONE]" else json.dumps(value, separators=(",", ":"))
    )
    return f"data: {payload}\n\n".encode()


def _stream(
    *, response_id: str, arguments: dict, finish_reason: str = "tool_calls"
) -> bytes:
    model = "deepseek-v4-pro"
    base = {
        "created": 1,
        "id": response_id,
        "model": model,
        "object": "chat.completion.chunk",
    }
    first = {
        **base,
        "choices": [
            {
                "delta": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "arguments": json.dumps(
                                    arguments, separators=(",", ":")
                                ),
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
    terminal = {
        **base,
        "choices": [
            {
                "delta": {},
                "finish_reason": finish_reason,
                "index": 0,
            }
        ],
        "usage": {
            "completion_tokens": 12,
            "prompt_tokens": 30,
            "total_tokens": 42,
        },
    }
    return b"".join(
        (
            _event(first),
            _event(terminal),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )


def test_smoke_preparation_freezes_profile_token_ceiling_and_concurrency(
    tmp_path: Path,
) -> None:
    manifest = prepare_smoke(output_root=tmp_path / "input")

    assert manifest["call_count"] == 4
    assert manifest["max_concurrency"] == 4
    assert manifest["max_tokens"] == ATOMIC_MAX_TOKENS == 16_384
    assert manifest["evaluator"]["model_alias"] == "opencode-go/deepseek-v4-pro"
    assert manifest["schema_version"] == (
        "local-ranking-atomic-opencode-go-preparation-v3.1"
    )
    assert manifest["response_submission"] == "forced_submit_judgment_tool"
    for call in manifest["calls"]:
        request = json.loads((tmp_path / "input" / call["request_path"]).read_bytes())
        assert request == {
            "max_tokens": 16_384,
            "messages": [
                {
                    "content": (tmp_path / "input" / call["prompt_path"]).read_text(),
                    "role": "user",
                }
            ],
            "model": "deepseek-v4-pro",
            "reasoning_effort": "high",
            "stream": True,
            "tool_choice": SUBMIT_JUDGMENT_TOOL_CHOICE,
            "tools": [SUBMIT_JUDGMENT_TOOL],
        }
        assert request["tools"][0]["function"]["parameters"] == SUBMIT_JUDGMENT_SCHEMA
        assert "response_format" not in request


def test_execute_call_writes_bound_receipt(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    manifest = prepare_smoke(output_root=preparation_root)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-pro"
        assert body["tool_choice"] == SUBMIT_JUDGMENT_TOOL_CHOICE
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(
                response_id="response-001",
                arguments=_smoke_probe_arguments("smoke-001"),
            ),
        )

    receipt = execute_call(
        preparation_root=preparation_root,
        call_sequence=1,
        output_root=tmp_path / "output",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert receipt["call_binding"] == {
        "atomic_manifest_sha256": None,
        "call_id": "smoke-001",
        "kind": "smoke",
        "orientation": None,
        "prompt_sha256": manifest["calls"][0]["prompt_sha256"],
        "replicate_id": None,
        "sequence": 1,
    }
    assert receipt["identity"]["provider_response_id"] == "response-001"
    assert receipt["identity"]["finish_reason"] == "tool_calls"
    assert receipt["identity"]["tool_call_id"] == "call-response-001"
    assert receipt["tool"] == {
        "name": "submit_judgment",
        "schema_sha256": sha256_bytes(canonical_json_bytes(SUBMIT_JUDGMENT_TOOL)),
    }
    assert receipt["transport_qualification"] == {
        "forced_tool_call_accepted": True,
        "reasoning_effort_requested": "high",
        "reasoning_execution_proven": False,
        "stream_completed": True,
        "streaming_requested": True,
    }

    validated = validate_smoke_call(
        preparation_root=preparation_root,
        call_sequence=1,
        execution_root=tmp_path / "output",
    )
    assert validated["status"] == "pass"


def test_run_smoke_executes_four_calls_concurrently(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root, max_concurrency=4)
    lock = threading.Lock()
    active = 0
    maximum_active = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        prompt = json.loads(request.content)["messages"][0]["content"]
        call_id = next(
            f"smoke-{index:03d}"
            for index in range(1, 5)
            if f"smoke-{index:03d}" in prompt
        )
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(
                response_id=f"response-{call_id}",
                arguments=_smoke_probe_arguments(call_id),
            ),
        )

    result = run_smoke(
        preparation_root=preparation_root,
        output_root=tmp_path / "output",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert result["status"] == "pass"
    assert len(result["calls"]) == 4
    assert maximum_active >= 2


def test_preparation_fails_closed_after_request_tampering(tmp_path: Path) -> None:
    root = tmp_path / "input"
    manifest = prepare_smoke(output_root=root)
    request_path = root / manifest["calls"][0]["request_path"]
    request = json.loads(request_path.read_bytes())
    request["max_tokens"] = 1
    request_path.write_bytes(canonical_json_bytes(request))

    with pytest.raises(HarnessError) as raised:
        _validate_preparation(root)

    assert raised.value.code == "HASH_MISMATCH"


def test_failed_physical_call_writes_replayable_execution_result(
    tmp_path: Path,
) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"temporarily unavailable")

    output_root = tmp_path / "output"
    with pytest.raises(HarnessError) as raised:
        execute_call(
            preparation_root=preparation_root,
            call_sequence=1,
            output_root=output_root,
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    result = json.loads((output_root / "execution-result.json").read_bytes())
    assert raised.value.code == "OPENCODE_GO_STREAM_HTTP_FAILED"
    assert result["status"] == "fail"
    assert result["receipt_sha256"] is None
    assert result["error"]["code"] == raised.value.code
    assert "http-status.txt" in result["files"]


def test_usage_snapshot_records_quota_without_credential(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/usage"):
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(
                200,
                json={
                    "usage": {
                        period: {
                            "percent": 12,
                            "resetsAt": "2026-09-02T00:00:00Z",
                            "status": "ok",
                        }
                        for period in ("rolling", "weekly", "monthly")
                    }
                },
            )
        return httpx.Response(
            200,
            json={"data": [{"id": "deepseek-v4-pro"}]},
        )

    output_path = tmp_path / "usage.json"
    snapshot = snapshot_usage(
        output_path=output_path,
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert snapshot["status"] == "pass"
    assert snapshot["model_present"] is True
    assert "test-key" not in output_path.read_text()


def test_execute_call_fails_closed_on_wrong_tool_name(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)

    def handler(_: httpx.Request) -> httpx.Response:
        stream = _stream(
            response_id="response-001",
            arguments=_smoke_probe_arguments("smoke-001"),
        ).replace(b"submit_judgment", b"other_function")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=stream,
        )

    output_root = tmp_path / "output"
    with pytest.raises(HarnessError) as raised:
        execute_call(
            preparation_root=preparation_root,
            call_sequence=1,
            output_root=output_root,
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    assert raised.value.code == "INVALID_TOOL_CALL"
    result = json.loads((output_root / "execution-result.json").read_bytes())
    assert result["status"] == "fail"
    assert result["error"]["code"] == "INVALID_TOOL_CALL"
    assert not (output_root / "response.json").exists()
    stream_error = json.loads(
        (output_root / "stream-validation-error.json").read_bytes()
    )
    assert stream_error["code"] == "INVALID_TOOL_CALL"


def test_validate_smoke_call_rejects_drifted_probe_response(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)

    def handler(_: httpx.Request) -> httpx.Response:
        arguments = _smoke_probe_arguments("smoke-001")
        arguments["winner"] = "left"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(response_id="response-001", arguments=arguments),
        )

    output_root = tmp_path / "output"
    execute_call(
        preparation_root=preparation_root,
        call_sequence=1,
        output_root=output_root,
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(HarnessError) as raised:
        validate_smoke_call(
            preparation_root=preparation_root,
            call_sequence=1,
            execution_root=output_root,
        )

    assert raised.value.code == "INVALID_SMOKE_RESPONSE"


def test_repeated_prepare_is_byte_identical(tmp_path: Path) -> None:
    first = prepare_smoke(output_root=tmp_path / "first")
    second = prepare_smoke(output_root=tmp_path / "second")

    assert first == second
    for call in first["calls"]:
        for key in ("prompt_path", "request_path"):
            assert (tmp_path / "first" / call[key]).read_bytes() == (
                tmp_path / "second" / call[key]
            ).read_bytes()


def _relabeled_smoke_preparation(root: Path, schema_version: str) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if schema_version == "local-ranking-atomic-opencode-go-preparation-v2.1":
        for call in manifest["calls"]:
            prompt = (root / call["prompt_path"]).read_text()
            request_bytes = canonical_json_bytes(
                _legacy_request(
                    prompt=prompt,
                    reasoning_effort=manifest["evaluator"]["reasoning_effort"],
                )
            )
            (root / call["request_path"]).write_bytes(request_bytes)
            call["request_sha256"] = sha256_bytes(request_bytes)
    elif schema_version != "local-ranking-atomic-opencode-go-preparation-v3.0":
        raise AssertionError(f"unsupported test relabel target {schema_version}")
    del manifest["response_submission"]
    manifest["schema_version"] = schema_version
    manifest_path.write_bytes(canonical_json_bytes(manifest))


@pytest.mark.parametrize(
    "schema_version",
    [
        "local-ranking-atomic-opencode-go-preparation-v2.1",
        "local-ranking-atomic-opencode-go-preparation-v3.0",
    ],
)
def test_legacy_and_canary_preparations_validate_but_cannot_execute(
    tmp_path: Path, schema_version: str
) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)
    _relabeled_smoke_preparation(preparation_root, schema_version)

    manifest, _, calls = _validate_preparation(preparation_root)

    assert manifest["schema_version"] == schema_version
    assert set(calls) == {1, 2, 3, 4}

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("diagnostic-only preparation must never be sent")

    with pytest.raises(HarnessError) as raised:
        execute_call(
            preparation_root=preparation_root,
            call_sequence=1,
            output_root=tmp_path / "output",
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    assert raised.value.code == "INVALID_PREPARATION"
    assert not (tmp_path / "output").exists()


def test_validate_smoke_call_rejects_response_only_evidence(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)
    execution_root = tmp_path / "output"
    execution_root.mkdir()
    (execution_root / "response.json").write_bytes(
        canonical_json_bytes(_smoke_probe_arguments("smoke-001"))
    )

    with pytest.raises(HarnessError) as raised:
        validate_smoke_call(
            preparation_root=preparation_root,
            call_sequence=1,
            execution_root=execution_root,
        )

    assert raised.value.code == "INCOMPLETE_SMOKE_EVIDENCE"


def test_validate_smoke_call_rejects_forged_receipt(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(
                response_id="response-001",
                arguments=_smoke_probe_arguments("smoke-001"),
            ),
        )

    output_root = tmp_path / "output"
    execute_call(
        preparation_root=preparation_root,
        call_sequence=1,
        output_root=output_root,
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    receipt_path = output_root / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["identity"]["provider_response_id"] = "chatcmpl-forged"
    receipt_path.write_bytes(canonical_json_bytes(receipt))

    with pytest.raises(HarnessError) as raised:
        validate_smoke_call(
            preparation_root=preparation_root,
            call_sequence=1,
            execution_root=output_root,
        )

    assert raised.value.code == "HASH_MISMATCH"


def test_execute_call_writes_failed_result_for_escaped_lone_surrogate(
    tmp_path: Path,
) -> None:
    preparation_root = tmp_path / "input"
    prepare_smoke(output_root=preparation_root)
    arguments = _smoke_probe_arguments("smoke-001")
    arguments["rationale"] = "transport probe \ud800 truncated"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(response_id="response-001", arguments=arguments),
        )

    output_root = tmp_path / "output"
    with pytest.raises(HarnessError) as raised:
        execute_call(
            preparation_root=preparation_root,
            call_sequence=1,
            output_root=output_root,
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )

    assert raised.value.code == "INVALID_TOOL_CALL"
    result = json.loads((output_root / "execution-result.json").read_bytes())
    assert result["status"] == "fail"
    assert result["error"]["code"] == "INVALID_TOOL_CALL"
    assert result["receipt_sha256"] is None
    assert not (output_root / "response.json").exists()
    assert not (output_root / "receipt.json").exists()
    assert (output_root / "stream-body.sse").is_file()
    stream_error = json.loads(
        (output_root / "stream-validation-error.json").read_bytes()
    )
    assert stream_error["code"] == "INVALID_TOOL_CALL"
    assert {
        "http-status.txt",
        "stream-body.sse",
        "stream-validation-error.json",
    } <= set(result["files"])
