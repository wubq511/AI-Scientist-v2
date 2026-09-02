from __future__ import annotations

import json

import pytest

from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.opencode_go_chat import prepare_synthetic
from prototypes.local_ranking.opencode_go_stream import (
    _extract_stream_response,
    _extract_stream_tool_response,
    _validate_preparation,
    prepare,
)


def _event(value: object) -> bytes:
    payload = (
        "[DONE]" if value == "[DONE]" else json.dumps(value, separators=(",", ":"))
    )
    return f"data: {payload}\n\n".encode()


def _chunk(
    *,
    content: str | None = None,
    finish_reason: str | None = None,
    response_id: str = "chatcmpl-stream-test",
    model: str = "deepseek-v4-flash",
    role: str | None = None,
) -> dict:
    delta = {}
    if content is not None:
        delta["content"] = content
    if role is not None:
        delta["role"] = role
    return {
        "choices": [
            {
                "delta": delta,
                "finish_reason": finish_reason,
                "index": 0,
            }
        ],
        "created": 1,
        "id": response_id,
        "model": model,
        "object": "chat.completion.chunk",
    }


def _successful_stream(*, model: str = "deepseek-v4-flash") -> bytes:
    terminal = _chunk(content="", finish_reason="stop", model=model)
    terminal["usage"] = {
        "completion_tokens": 19,
        "prompt_tokens": 10,
        "total_tokens": 29,
    }
    usage_enrichment = {
        "choices": [],
        "created": 1,
        "id": "chatcmpl-stream-test",
        "model": model,
        "object": "chat.completion.chunk",
        "usage": {
            "completion_tokens": 20,
            "prompt_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 0},
            "total_tokens": 30,
        },
    }
    return b"".join(
        (
            b": keepalive\n\n",
            _event(_chunk(content='{"value":', role="assistant", model=model)),
            _event(_chunk(content="true}", model=model)),
            _event(terminal),
            _event(usage_enrichment),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )


def test_extract_stream_requires_terminal_done_and_rebuilds_json() -> None:
    draft, usage, identity, chunks, diagnostics = _extract_stream_response(
        _successful_stream()
    )

    assert draft == {"value": True}
    assert usage == {
        "cached_tokens": 0,
        "completion_tokens": 20,
        "prompt_tokens": 10,
        "total_tokens": 30,
    }
    assert identity == {
        "cost": "0",
        "created_first": 1,
        "created_last": 1,
        "finish_reason": "stop",
        "model": "deepseek-v4-flash",
        "provider_response_id": "chatcmpl-stream-test",
    }
    assert len(chunks) == 5
    assert diagnostics == {
        "content_bytes": 14,
        "data_event_count": 6,
        "done_received": True,
        "keepalive_count": 1,
        "post_done_cost_received": True,
    }


def test_extract_stream_binds_requested_pro_model() -> None:
    _, _, identity, _, _ = _extract_stream_response(
        _successful_stream(model="deepseek-v4-pro"),
        expected_model="deepseek-v4-pro",
    )

    assert identity["model"] == "deepseek-v4-pro"


@pytest.mark.parametrize(
    ("raw_stream", "expected_code"),
    [
        (_successful_stream().split(_event("[DONE]"))[0], "STREAM_INCOMPLETE"),
        (
            _successful_stream().replace(
                b'"finish_reason":"stop"', b'"finish_reason":"other"'
            ),
            "PROVIDER_RESPONSE_FAILED",
        ),
        (
            _successful_stream().replace(
                b'"model":"deepseek-v4-flash"', b'"model":"wrong-model"', 1
            ),
            "PROVIDER_IDENTITY_MISMATCH",
        ),
        (
            _successful_stream().replace(b'"created":1', b'"created":2', 1),
            "PROVIDER_IDENTITY_MISMATCH",
        ),
        (
            _successful_stream() + _event({"choices": [], "cost": "1"}),
            "INVALID_SSE",
        ),
    ],
)
def test_extract_stream_rejects_incomplete_or_wrong_terminal_state(
    raw_stream: bytes, expected_code: str
) -> None:
    with pytest.raises(HarnessError) as raised:
        _extract_stream_response(raw_stream)

    assert raised.value.code == expected_code


def test_extract_stream_rejects_cumulative_usage_regression() -> None:
    raw_stream = (
        _successful_stream()
        .replace(b'"completion_tokens":20', b'"completion_tokens":18', 1)
        .replace(b'"total_tokens":30', b'"total_tokens":28', 1)
    )

    with pytest.raises(HarnessError) as raised:
        _extract_stream_response(raw_stream)

    assert raised.value.code == "INVALID_PROVIDER_RESPONSE"


def test_extract_stream_classifies_billing_before_done_as_incomplete() -> None:
    raw_stream = _successful_stream().replace(_event("[DONE]"), b"")

    with pytest.raises(HarnessError) as raised:
        _extract_stream_response(raw_stream)

    assert raised.value.code == "STREAM_INCOMPLETE"


def test_prepare_stream_request_changes_only_transport_shape(tmp_path) -> None:
    base_protocol = tmp_path / "base.md"
    evaluator_protocol = tmp_path / "evaluator.md"
    base_protocol.write_text("synthetic base protocol\n")
    evaluator_protocol.write_text("synthetic evaluator protocol\n")
    synthetic_root = tmp_path / "synthetic"
    prepare_synthetic(
        base_protocol_path=base_protocol,
        evaluator_protocol_path=evaluator_protocol,
        output_root=synthetic_root,
    )

    output_root = tmp_path / "stream"
    manifest = prepare(
        bundle_path=synthetic_root / "input/bundle.json",
        prompt_path=synthetic_root / "input/prompt.txt",
        output_root=output_root,
    )

    non_stream = json.loads((synthetic_root / "request/request.json").read_text())
    stream = json.loads((output_root / "request.json").read_text())
    assert non_stream | {"stream": True} == stream
    assert manifest["transport"] == (
        "opencode-go-chat-completions-json-object-sse-candidate"
    )


def test_prepare_stream_request_binds_flash_max_profile(tmp_path) -> None:
    base_protocol = tmp_path / "base.md"
    evaluator_protocol = tmp_path / "evaluator.md"
    base_protocol.write_text("synthetic base protocol\n")
    evaluator_protocol.write_text("synthetic evaluator protocol\n")
    synthetic_root = tmp_path / "synthetic"
    prepare_synthetic(
        base_protocol_path=base_protocol,
        evaluator_protocol_path=evaluator_protocol,
        output_root=synthetic_root,
    )
    bundle_path = synthetic_root / "input/bundle.json"
    old_bundle_bytes = bundle_path.read_bytes()
    bundle = json.loads(old_bundle_bytes)
    bundle["evaluator"]["reasoning_effort"] = "max"
    bundle_without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    bundle["bundle_sha256"] = sha256_bytes(canonical_json_bytes(bundle_without_hash))
    new_bundle_bytes = canonical_json_bytes(bundle)
    bundle_path.write_bytes(new_bundle_bytes)
    prompt_path = synthetic_root / "input/prompt.txt"
    prompt_path.write_bytes(
        prompt_path.read_bytes().replace(old_bundle_bytes, new_bundle_bytes)
    )

    output_root = tmp_path / "stream"
    manifest = prepare(
        bundle_path=bundle_path,
        prompt_path=prompt_path,
        output_root=output_root,
    )
    request = json.loads((output_root / "request.json").read_text())
    validated = _validate_preparation(preparation_root=output_root)

    assert request["reasoning_effort"] == "max"
    assert manifest["bundle_sha256"] == sha256_bytes(new_bundle_bytes)
    assert manifest["reasoning_effort"] == "max"
    assert manifest["schema_version"].endswith("v1.1")
    assert validated[2]["reasoning_effort"] == "max"

    manifest["reasoning_effort"] = "high"
    (output_root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(HarnessError) as raised:
        _validate_preparation(preparation_root=output_root)
    assert raised.value.code == "INVALID_ARTIFACT"


def test_prepare_stream_request_rejects_unapproved_effort(tmp_path) -> None:
    base_protocol = tmp_path / "base.md"
    evaluator_protocol = tmp_path / "evaluator.md"
    base_protocol.write_text("synthetic base protocol\n")
    evaluator_protocol.write_text("synthetic evaluator protocol\n")
    synthetic_root = tmp_path / "synthetic"
    prepare_synthetic(
        base_protocol_path=base_protocol,
        evaluator_protocol_path=evaluator_protocol,
        output_root=synthetic_root,
    )
    bundle_path = synthetic_root / "input/bundle.json"
    bundle = json.loads(bundle_path.read_bytes())
    bundle["evaluator"]["reasoning_effort"] = "low"
    bundle_without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    bundle["bundle_sha256"] = sha256_bytes(canonical_json_bytes(bundle_without_hash))
    bundle_path.write_bytes(canonical_json_bytes(bundle))

    with pytest.raises(HarnessError) as raised:
        prepare(
            bundle_path=bundle_path,
            prompt_path=synthetic_root / "input/prompt.txt",
            output_root=tmp_path / "stream",
        )

    assert raised.value.code == "INVALID_ARTIFACT"


def test_prepare_stream_request_binds_pro_high_profile(tmp_path) -> None:
    base_protocol = tmp_path / "base.md"
    evaluator_protocol = tmp_path / "evaluator.md"
    base_protocol.write_text("synthetic base protocol\n")
    evaluator_protocol.write_text("synthetic evaluator protocol\n")
    synthetic_root = tmp_path / "synthetic"
    prepare_synthetic(
        base_protocol_path=base_protocol,
        evaluator_protocol_path=evaluator_protocol,
        output_root=synthetic_root,
    )
    bundle_path = synthetic_root / "input/bundle.json"
    old_bundle_bytes = bundle_path.read_bytes()
    bundle = json.loads(old_bundle_bytes)
    bundle["evaluator"]["model_alias"] = "opencode-go/deepseek-v4-pro"
    bundle_without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    bundle["bundle_sha256"] = sha256_bytes(canonical_json_bytes(bundle_without_hash))
    new_bundle_bytes = canonical_json_bytes(bundle)
    bundle_path.write_bytes(new_bundle_bytes)
    prompt_path = synthetic_root / "input/prompt.txt"
    prompt_path.write_bytes(
        prompt_path.read_bytes().replace(old_bundle_bytes, new_bundle_bytes)
    )

    output_root = tmp_path / "stream"
    manifest = prepare(
        bundle_path=bundle_path,
        prompt_path=prompt_path,
        output_root=output_root,
    )
    request = json.loads((output_root / "request.json").read_text())
    validated = _validate_preparation(preparation_root=output_root)

    assert request["model"] == "deepseek-v4-pro"
    assert request["reasoning_effort"] == "high"
    assert manifest["model"] == "deepseek-v4-pro"
    assert validated[2]["model"] == "deepseek-v4-pro"


def _tool_chunk(
    *,
    delta: dict,
    finish_reason: str | None = None,
    response_id: str = "chatcmpl-tool-test",
    model: str = "deepseek-v4-pro",
) -> dict:
    return {
        "choices": [
            {
                "delta": delta,
                "finish_reason": finish_reason,
                "index": 0,
            }
        ],
        "created": 1,
        "id": response_id,
        "model": model,
        "object": "chat.completion.chunk",
    }


def _tool_stream(
    *,
    arguments: str = '{"value":true}',
    tool_name: str = "submit_judgment",
    tool_call_id: str = "call-tool-001",
    finish_reason: str = "tool_calls",
    content: str | None = None,
    reasoning: str | None = None,
) -> bytes:
    midpoint = len(arguments) // 2
    first_delta: dict = {
        "role": "assistant",
        "tool_calls": [
            {
                "function": {
                    "arguments": arguments[:midpoint],
                    "name": tool_name[:7],
                },
                "id": tool_call_id,
                "index": 0,
                "type": "function",
            }
        ],
    }
    if content is not None:
        first_delta["content"] = content
    if reasoning is not None:
        first_delta["reasoning_content"] = reasoning
    second_delta = {
        "tool_calls": [
            {
                "function": {
                    "arguments": arguments[midpoint:],
                    "name": tool_name[7:],
                },
                "index": 0,
            }
        ]
    }
    terminal = _tool_chunk(delta={}, finish_reason=finish_reason)
    terminal["usage"] = {
        "completion_tokens": 5,
        "prompt_tokens": 10,
        "total_tokens": 15,
    }
    return b"".join(
        (
            _event(_tool_chunk(delta=first_delta)),
            _event(_tool_chunk(delta=second_delta)),
            _event(terminal),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )


def _extract_tool(raw_stream: bytes):
    return _extract_stream_tool_response(
        raw_stream,
        expected_model="deepseek-v4-pro",
        tool_name="submit_judgment",
    )


def test_extract_tool_stream_joins_fragmented_call_and_isolates_content() -> None:
    arguments, usage, identity, chunks, diagnostics = _extract_tool(
        _tool_stream(content="noise", reasoning="private reasoning")
    )

    assert arguments == {"value": True}
    assert usage == {"completion_tokens": 5, "prompt_tokens": 10, "total_tokens": 15}
    assert identity == {
        "cost": "0",
        "created_first": 1,
        "created_last": 1,
        "finish_reason": "tool_calls",
        "model": "deepseek-v4-pro",
        "provider_response_id": "chatcmpl-tool-test",
        "tool_call_id": "call-tool-001",
    }
    assert len(chunks) == 4
    assert diagnostics == {
        "arguments_bytes": 14,
        "content_bytes": 5,
        "data_event_count": 5,
        "done_received": True,
        "keepalive_count": 0,
        "post_done_cost_received": True,
        "reasoning_bytes": 17,
    }


def test_extract_tool_stream_accepts_stop_finish_reason() -> None:
    arguments, _, identity, _, _ = _extract_tool(_tool_stream(finish_reason="stop"))

    assert arguments == {"value": True}
    assert identity["finish_reason"] == "stop"


@pytest.mark.parametrize(
    ("raw_stream", "expected_code"),
    [
        (_tool_stream(tool_name="submit_judgm3nt"), "INVALID_TOOL_CALL"),
        (_tool_stream(arguments='{"value":'), "INVALID_TOOL_CALL"),
        (_tool_stream(arguments="[1]"), "INVALID_TOOL_CALL"),
        (_tool_stream(arguments=""), "INVALID_TOOL_CALL"),
        (_tool_stream(finish_reason="length"), "PROVIDER_RESPONSE_FAILED"),
        (_tool_stream().split(_event("[DONE]"))[0], "STREAM_INCOMPLETE"),
        (
            _tool_stream().replace(b'"index":0', b'"index":1', 1),
            "INVALID_TOOL_CALL",
        ),
    ],
)
def test_extract_tool_stream_fails_closed(
    raw_stream: bytes, expected_code: str
) -> None:
    with pytest.raises(HarnessError) as raised:
        _extract_tool(raw_stream)

    assert raised.value.code == expected_code


def test_extract_tool_stream_rejects_conflicting_tool_call_id() -> None:
    first = _tool_chunk(
        delta={
            "role": "assistant",
            "tool_calls": [
                {
                    "function": {"arguments": '{"value":', "name": "submit_"},
                    "id": "call-tool-001",
                    "index": 0,
                    "type": "function",
                }
            ],
        }
    )
    second = _tool_chunk(
        delta={
            "tool_calls": [
                {
                    "function": {"arguments": "true}", "name": "judgment"},
                    "id": "call-other",
                    "index": 0,
                }
            ]
        }
    )
    terminal = _tool_chunk(delta={}, finish_reason="tool_calls")
    terminal["usage"] = {
        "completion_tokens": 5,
        "prompt_tokens": 10,
        "total_tokens": 15,
    }
    raw_stream = b"".join(
        (
            _event(first),
            _event(second),
            _event(terminal),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )

    with pytest.raises(HarnessError) as raised:
        _extract_tool(raw_stream)

    assert raised.value.code == "INVALID_TOOL_CALL"


def test_extract_tool_stream_requires_a_tool_call() -> None:
    content_only = _chunk(
        content='{"value":true}', model="deepseek-v4-pro", role="assistant"
    )
    terminal = _chunk(content="", finish_reason="stop", model="deepseek-v4-pro")
    terminal["usage"] = {
        "completion_tokens": 5,
        "prompt_tokens": 10,
        "total_tokens": 15,
    }
    raw_stream = b"".join(
        (
            _event(content_only),
            _event(terminal),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )

    with pytest.raises(HarnessError) as raised:
        _extract_tool(raw_stream)

    assert raised.value.code == "INVALID_TOOL_CALL"


def test_extract_tool_stream_rejects_refusal_and_terminal_continuation() -> None:
    refusal = _tool_chunk(delta={"refusal": "cannot answer"})
    second = _tool_chunk(
        delta={
            "tool_calls": [
                {
                    "function": {"arguments": "true}", "name": "judgment"},
                    "index": 0,
                }
            ]
        }
    )
    terminal = _tool_chunk(delta={}, finish_reason="tool_calls")
    terminal["usage"] = {
        "completion_tokens": 5,
        "prompt_tokens": 10,
        "total_tokens": 15,
    }
    refusal_stream = b"".join(
        (
            _event(refusal),
            _event(second),
            _event(terminal),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )
    with pytest.raises(HarnessError) as raised:
        _extract_tool(refusal_stream)
    assert raised.value.code == "PROVIDER_RESPONSE_FAILED"

    terminal_extra = _tool_chunk(
        delta={"tool_calls": [{"function": {"arguments": "{}"}, "index": 0}]},
    )
    continued = _tool_stream().replace(
        _event("[DONE]"), _event(terminal_extra) + _event("[DONE]"), 1
    )
    with pytest.raises(HarnessError) as raised:
        _extract_tool(continued)
    assert raised.value.code == "INVALID_PROVIDER_RESPONSE"


def test_extract_tool_stream_rejects_non_string_reasoning() -> None:
    bad_reasoning = _tool_chunk(delta={"role": "assistant", "reasoning_content": 5})
    terminal = _tool_chunk(delta={}, finish_reason="tool_calls")
    terminal["usage"] = {
        "completion_tokens": 5,
        "prompt_tokens": 10,
        "total_tokens": 15,
    }
    raw_stream = b"".join(
        (
            _event(bad_reasoning),
            _event(terminal),
            _event("[DONE]"),
            _event({"choices": [], "cost": "0"}),
        )
    )

    with pytest.raises(HarnessError) as raised:
        _extract_tool(raw_stream)

    assert raised.value.code == "INVALID_PROVIDER_RESPONSE"
