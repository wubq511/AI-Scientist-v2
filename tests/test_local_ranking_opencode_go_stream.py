from __future__ import annotations

import json

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.opencode_go_chat import prepare_synthetic
from prototypes.local_ranking.opencode_go_stream import (
    _extract_stream_response,
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


def _successful_stream() -> bytes:
    usage = {
        "choices": [],
        "cost": "0",
        "created": 1,
        "id": "chatcmpl-stream-test",
        "model": "deepseek-v4-flash",
        "object": "chat.completion.chunk",
        "usage": {
            "completion_tokens": 20,
            "prompt_tokens": 10,
            "total_tokens": 30,
        },
    }
    return b"".join(
        (
            b": keepalive\n\n",
            _event(_chunk(content='{"value":', role="assistant")),
            _event(_chunk(content="true}")),
            _event(_chunk(finish_reason="stop")),
            _event(usage),
            _event("[DONE]"),
        )
    )


def test_extract_stream_requires_terminal_done_and_rebuilds_json() -> None:
    draft, usage, identity, chunks, diagnostics = _extract_stream_response(
        _successful_stream()
    )

    assert draft == {"value": True}
    assert usage == {
        "completion_tokens": 20,
        "prompt_tokens": 10,
        "total_tokens": 30,
    }
    assert identity == {
        "cost": "0",
        "created": 1,
        "finish_reason": "stop",
        "model": "deepseek-v4-flash",
        "provider_response_id": "chatcmpl-stream-test",
    }
    assert len(chunks) == 4
    assert diagnostics == {
        "content_bytes": 14,
        "data_event_count": 5,
        "done_received": True,
        "keepalive_count": 1,
    }


@pytest.mark.parametrize(
    ("raw_stream", "expected_code"),
    [
        (_successful_stream().replace(_event("[DONE]"), b""), "STREAM_INCOMPLETE"),
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
    ],
)
def test_extract_stream_rejects_incomplete_or_wrong_terminal_state(
    raw_stream: bytes, expected_code: str
) -> None:
    with pytest.raises(HarnessError) as raised:
        _extract_stream_response(raw_stream)

    assert raised.value.code == expected_code


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
