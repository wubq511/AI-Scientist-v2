from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from prototypes.local_ranking.atomic_opencode_go import (
    ATOMIC_MAX_TOKENS,
    _validate_preparation,
    execute_call,
    prepare_smoke,
    run_smoke,
)
from prototypes.local_ranking.canonical import canonical_json_bytes
from prototypes.local_ranking.errors import HarnessError


def _event(value: object) -> bytes:
    payload = (
        "[DONE]" if value == "[DONE]" else json.dumps(value, separators=(",", ":"))
    )
    return f"data: {payload}\n\n".encode()


def _stream(*, response_id: str, content: dict) -> bytes:
    model = "deepseek-v4-pro"
    content_text = json.dumps(content, separators=(",", ":"))
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
                "delta": {"content": content_text, "role": "assistant"},
                "finish_reason": None,
                "index": 0,
            }
        ],
    }
    terminal = {
        **base,
        "choices": [
            {
                "delta": {"content": ""},
                "finish_reason": "stop",
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
    for call in manifest["calls"]:
        request = json.loads((tmp_path / "input" / call["request_path"]).read_bytes())
        assert request["max_tokens"] == 16_384
        assert request["reasoning_effort"] == "high"
        assert request["stream"] is True
        assert request["response_format"] == {"type": "json_object"}


def test_execute_call_writes_bound_receipt(tmp_path: Path) -> None:
    preparation_root = tmp_path / "input"
    manifest = prepare_smoke(output_root=preparation_root)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-pro"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_stream(
                response_id="response-001",
                content={"probe_id": "smoke-001", "status": "ok"},
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
    assert receipt["transport_qualification"]["reasoning_execution_proven"] is False


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
                content={"probe_id": call_id, "status": "ok"},
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
