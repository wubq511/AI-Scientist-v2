"""Tests for DeepSeek-only adapter and model round execution (Ticket 06).

Covers validation matrix rows:
- VM-UNIT-07: failure taxonomy lookup table (16 closed codes, suspend/terminal binary classification)
- VM-CONTRACT-022-01: adapter parameter allowlist and SDK implicit retries disabled
- VM-CONTRACT-022-02: provider-success criteria, required fields, and usage invariants
- VM-CONTRACT-022-03: closed 16-code failure taxonomy triggered via stub transport, bounded retries (<=2 attempts)
- VM-REPLAY-01: recorded provider responses replay produces identical canonical artifacts and hashes
- VM-FAULT-01: transport fault injection across all 16 codes and disposition consistency
"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import pytest
from typing import Any

from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.deepseek import (
    ALLOWED_OUTPUT_MODES,
    ALLOWED_REASONING_EFFORTS,
    ALLOWED_ROLES,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL_ID,
    FAILURE_TAXONOMY,
    MAX_ATTEMPTS_PER_OPERATION,
    RETRYABLE_FAILURE_CODES,
    SUSPEND_FAILURES,
    TERMINAL_FAILURES,
    DeepSeekAdapter,
    DeepSeekMessage,
    DeepSeekRequest,
    ModelRoundError,
    ModelRoundFailure,
    ModelRoundResult,
    RecordedTransport,
    StubTransport,
    TokenUsage,
    TransportResponse,
    create_deepseek_client_options,
    disposition_for_failure,
    redact_secrets,
    validate_provider_response,
    validate_request,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.run_store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_golden_response_dict(
    *,
    model: str = DEEPSEEK_MODEL_ID,
    finish_reason: str = "stop",
    content: str = 'ACTION: SearchLiterature\nARGUMENTS: {"query": "attention mechanism"}',
    reasoning_content: str | None = "Thinking about attention mechanisms...",
    tool_calls: list[Any] | None = None,
    prompt_tokens: int = 100,
    prompt_cache_hit_tokens: int = 60,
    prompt_cache_miss_tokens: int = 40,
    completion_tokens: int = 50,
    reasoning_tokens: int = 20,
    response_id: str = "chatcmpl-test-12345",
    system_fingerprint: str = "fp_deepseek_v4",
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "finish_reason": finish_reason,
                "index": 0,
                "message": {
                    "content": content,
                    "reasoning_content": reasoning_content,
                    "role": "assistant",
                    **({"tool_calls": tool_calls} if tool_calls is not None else {}),
                },
            }
        ],
        "created": 1725350400,
        "id": response_id,
        "model": model,
        "object": "chat.completion",
        "system_fingerprint": system_fingerprint,
        "usage": {
            "completion_tokens": completion_tokens,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "prompt_tokens": prompt_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _make_sample_request() -> DeepSeekRequest:
    return DeepSeekRequest(
        messages=(
            DeepSeekMessage(role="system", content="You are an AI researcher."),
            DeepSeekMessage(role="user", content="Propose a research idea."),
        ),
        reasoning_effort="high",
        max_tokens=32768,
        output_mode="text",
        user_id="user-run-test-01",
    )


# ==============================================================================
# VM-UNIT-07: Failure Taxonomy Lookup Table
# ==============================================================================


def test_failure_taxonomy_lookup_table_completeness_and_classification() -> None:
    """VM-UNIT-07: verify closed 16-code taxonomy and strict 2-value disposition."""
    assert len(FAILURE_TAXONOMY) == 16
    assert len(SUSPEND_FAILURES) == 7
    assert len(TERMINAL_FAILURES) == 9
    assert SUSPEND_FAILURES | TERMINAL_FAILURES == FAILURE_TAXONOMY
    assert SUSPEND_FAILURES.isdisjoint(TERMINAL_FAILURES)

    for code in SUSPEND_FAILURES:
        assert disposition_for_failure(code) == "suspend"

    for code in TERMINAL_FAILURES:
        assert disposition_for_failure(code) == "terminal"

    # Unknown code must fail closed
    with pytest.raises(IdeationInputError) as exc_info:
        disposition_for_failure("not_a_valid_failure_code")
    assert exc_info.value.code == "INVALID_FAILURE_CODE"


def test_failure_taxonomy_retryable_subset() -> None:
    """VM-UNIT-07: verify only 3 approved transient failure codes are retryable."""
    assert RETRYABLE_FAILURE_CODES == frozenset(
        {"rate_limited", "provider_transient", "resource_exhausted"}
    )
    # Ambiguous transport/timeout errors must NOT be retryable in adapter
    assert "timeout_ambiguous" not in RETRYABLE_FAILURE_CODES
    assert "transport_ambiguous" not in RETRYABLE_FAILURE_CODES


# ==============================================================================
# VM-CONTRACT-022-01: Adapter Request Allowlist & SDK Options
# ==============================================================================


def test_adapter_allowlist_accepts_valid_request() -> None:
    """VM-CONTRACT-022-01: valid approved parameters pass and construct canonical payload."""
    req = validate_request(
        messages=[
            {"role": "system", "content": "You are a scientist."},
            {"role": "user", "content": "Explore new ideas."},
        ],
        reasoning_effort="high",
        max_tokens=16384,
        output_mode="text",
        user_id="run-42-opaque",
    )
    payload = req.to_canonical_dict()
    assert payload["model"] == DEEPSEEK_MODEL_ID
    assert payload["stream"] is False
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert payload["max_tokens"] == 16384
    assert payload["user_id"] == "run-42-opaque"
    assert "response_format" not in payload


def test_adapter_allowlist_json_object_mode() -> None:
    """VM-CONTRACT-022-01: json_object output_mode attaches response_format."""
    req = validate_request(
        messages=[{"role": "user", "content": "Return json"}],
        max_tokens=4096,
        output_mode="json_object",
        user_id="run-42-opaque",
    )
    payload = req.to_canonical_dict()
    assert payload["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    "bad_kwargs,expected_msg",
    [
        ({"temperature": 0.7}, "Disallowed or unknown request parameters"),
        ({"top_p": 0.9}, "Disallowed or unknown request parameters"),
        ({"presence_penalty": 0.5}, "Disallowed or unknown request parameters"),
        ({"frequency_penalty": 0.5}, "Disallowed or unknown request parameters"),
        ({"seed": 42}, "Disallowed or unknown request parameters"),
        ({"extra_body": {"foo": "bar"}}, "Disallowed or unknown request parameters"),
        ({"stream": True}, "Disallowed or unknown request parameters"),
        ({"tools": [{"name": "fake"}]}, "Disallowed or unknown request parameters"),
        ({"unknown_arg": 123}, "Disallowed or unknown request parameters"),
    ],
)
def test_adapter_allowlist_rejects_disallowed_parameters(
    bad_kwargs: dict[str, Any], expected_msg: str
) -> None:
    """VM-CONTRACT-022-01: temperature, top_p, penalties, seed, extra_body, tools fail closed."""
    with pytest.raises(ModelRoundError) as exc_info:
        validate_request(
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1000,
            user_id="uid",
            **bad_kwargs,
        )
    assert exc_info.value.code == "configuration"
    assert exc_info.value.disposition == "terminal"
    assert expected_msg in exc_info.value.failure.message


@pytest.mark.parametrize(
    "kwargs,expected_code",
    [
        ({"messages": []}, "configuration"),
        ({"messages": [{"role": "developer", "content": "hi"}]}, "configuration"),
        ({"messages": [{"role": "user", "content": ""}]}, "configuration"),
        ({"messages": [{"role": "user"}]}, "configuration"),
        ({"reasoning_effort": "extreme"}, "configuration"),
        ({"max_tokens": 0}, "configuration"),
        ({"max_tokens": -100}, "configuration"),
        ({"max_tokens": "32768"}, "configuration"),
        ({"output_mode": "xml"}, "configuration"),
        ({"user_id": ""}, "configuration"),
    ],
)
def test_adapter_allowlist_rejects_invalid_field_values(
    kwargs: dict[str, Any], expected_code: str
) -> None:
    """VM-CONTRACT-022-01: invalid enum values, non-positive max_tokens, invalid messages fail closed."""
    base: dict[str, Any] = {
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 1000,
        "user_id": "uid",
    }
    base.update(kwargs)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_request(**base)
    assert exc_info.value.code == expected_code
    assert exc_info.value.disposition == "terminal"


def test_sdk_implicit_retries_disabled_in_client_options() -> None:
    """VM-CONTRACT-022-01: SDK client options must explicitly set max_retries=0."""
    opts = create_deepseek_client_options("sk-test-secret-key-12345678")
    assert opts["base_url"] == DEEPSEEK_BASE_URL
    assert opts["max_retries"] == 0
    assert opts["timeout"] == 3600.0


# ==============================================================================
# VM-CONTRACT-022-02: Provider Success Determination & Invariants
# ==============================================================================


def test_provider_success_happy_path() -> None:
    """VM-CONTRACT-022-02: valid response passes all provider-success gates."""
    doc = _make_golden_response_dict()
    body_bytes = canonical_json_bytes(doc)
    (
        content,
        reasoning,
        tools,
        resp_id,
        fingerprint,
        finish_reason,
        usage,
        parsed_body,
    ) = validate_provider_response(
        200,
        {"content-type": "application/json"},
        body_bytes,
        output_mode="text",
    )
    assert content == doc["choices"][0]["message"]["content"]
    assert reasoning == doc["choices"][0]["message"]["reasoning_content"]
    assert resp_id == "chatcmpl-test-12345"
    assert finish_reason == "stop"
    assert usage.prompt_tokens == 100
    assert usage.prompt_cache_hit_tokens == 60
    assert usage.prompt_cache_miss_tokens == 40
    assert usage.completion_tokens == 50
    assert usage.reasoning_tokens == 20
    assert usage.total_tokens == 150


def test_provider_success_json_object_mode_valid() -> None:
    """VM-CONTRACT-022-02: json_object output_mode accepts valid JSON object."""
    doc = _make_golden_response_dict(
        content=json.dumps({"idea": {"Title": "A Great Idea", "Name": "great_idea"}})
    )
    body_bytes = canonical_json_bytes(doc)
    content, _, _, _, _, _, _, _ = validate_provider_response(
        200,
        {"content-type": "application/json"},
        body_bytes,
        output_mode="json_object",
    )
    assert "great_idea" in content


@pytest.mark.parametrize(
    "json_content",
    [
        "not a json",
        "[1, 2, 3]",  # valid JSON but array, not top-level object
        '"a string"',
        "12345",
        "true",
    ],
)
def test_provider_success_json_object_mode_invalid(json_content: str) -> None:
    """VM-CONTRACT-022-02: json_object output_mode rejects malformed or non-object content."""
    doc = _make_golden_response_dict(content=json_content)
    body_bytes = canonical_json_bytes(doc)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_provider_response(
            200,
            {"content-type": "application/json"},
            body_bytes,
            output_mode="json_object",
        )
    assert exc_info.value.code == "invalid_json"
    assert exc_info.value.disposition == "terminal"


def test_provider_success_rejects_model_mismatch() -> None:
    """VM-CONTRACT-022-02: response model must strictly match deepseek-v4-pro."""
    doc = _make_golden_response_dict(model="deepseek-chat")
    body_bytes = canonical_json_bytes(doc)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_provider_response(
            200,
            {"content-type": "application/json"},
            body_bytes,
            output_mode="text",
        )
    assert exc_info.value.code == "model_mismatch"
    assert exc_info.value.disposition == "terminal"


@pytest.mark.parametrize(
    "finish_reason,expected_code,expected_disp",
    [
        ("length", "truncated", "terminal"),
        ("content_filter", "content_filtered", "terminal"),
        ("insufficient_system_resource", "resource_exhausted", "suspend"),
        ("tool_calls", "unexpected_tool_call", "terminal"),
        ("weird_stop_reason", "malformed_response", "terminal"),
    ],
)
def test_provider_success_finish_reason_dispositions(
    finish_reason: str, expected_code: str, expected_disp: str
) -> None:
    """VM-CONTRACT-022-02: non-stop finish reasons trigger corresponding closed failure codes."""
    doc = _make_golden_response_dict(finish_reason=finish_reason)
    body_bytes = canonical_json_bytes(doc)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_provider_response(
            200,
            {"content-type": "application/json"},
            body_bytes,
            output_mode="text",
        )
    assert exc_info.value.code == expected_code
    assert exc_info.value.disposition == expected_disp


@pytest.mark.parametrize("empty_val", ["", "   ", "\n\t  \n"])
def test_provider_success_rejects_empty_content(empty_val: str) -> None:
    """VM-CONTRACT-022-02: empty or whitespace content is rejected as empty_content."""
    doc = _make_golden_response_dict(content=empty_val)
    body_bytes = canonical_json_bytes(doc)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_provider_response(
            200,
            {"content-type": "application/json"},
            body_bytes,
            output_mode="text",
        )
    assert exc_info.value.code == "empty_content"
    assert exc_info.value.disposition == "terminal"


def test_provider_success_rejects_unexpected_tool_calls() -> None:
    """VM-CONTRACT-022-02: tool_calls in message rejected as unexpected_tool_call."""
    doc = _make_golden_response_dict(tool_calls=[{"id": "call_1", "type": "function"}])
    body_bytes = canonical_json_bytes(doc)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_provider_response(
            200,
            {"content-type": "application/json"},
            body_bytes,
            output_mode="text",
        )
    assert exc_info.value.code == "unexpected_tool_call"
    assert exc_info.value.disposition == "terminal"


@pytest.mark.parametrize(
    "bad_usage,reason",
    [
        # prompt != cache_hit + cache_miss
        (
            {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 50,
                "prompt_cache_miss_tokens": 40,
                "completion_tokens": 10,
                "total_tokens": 110,
            },
            "prompt sum mismatch",
        ),
        # total != prompt + completion
        (
            {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 60,
                "prompt_cache_miss_tokens": 40,
                "completion_tokens": 50,
                "total_tokens": 200,
            },
            "total sum mismatch",
        ),
        # reasoning > completion
        (
            {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 60,
                "prompt_cache_miss_tokens": 40,
                "completion_tokens": 50,
                "total_tokens": 150,
                "completion_tokens_details": {"reasoning_tokens": 60},
            },
            "reasoning > completion",
        ),
        # negative token
        (
            {
                "prompt_tokens": -1,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": -1,
            },
            "negative tokens",
        ),
        # missing field
        (
            {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 60,
                "prompt_cache_miss_tokens": 40,
                "completion_tokens": 50,
            },
            "missing total_tokens",
        ),
    ],
)
def test_provider_success_usage_invariants_fail_closed(
    bad_usage: dict[str, Any], reason: str
) -> None:
    """VM-CONTRACT-022-02: usage invariant violations are rejected as malformed_response."""
    doc = _make_golden_response_dict()
    doc["usage"] = bad_usage
    body_bytes = canonical_json_bytes(doc)
    with pytest.raises(ModelRoundError) as exc_info:
        validate_provider_response(
            200,
            {"content-type": "application/json"},
            body_bytes,
            output_mode="text",
        )
    assert exc_info.value.code == "malformed_response"
    assert exc_info.value.disposition == "terminal"


# ==============================================================================
# VM-CONTRACT-022-03: Stub Triggering & Retry Bounds (<=2 attempts)
# ==============================================================================


def test_retry_transient_rate_limited_succeeds_on_second_attempt(
    tmp_path: Path,
) -> None:
    """VM-CONTRACT-022-03: rate_limited retries once and succeeds on attempt 2."""
    store = RunStore(tmp_path)
    run = store.create_run()
    price_table = load_price_table(REPO_ROOT)

    golden_body = canonical_json_bytes(_make_golden_response_dict())
    stub = StubTransport(
        [
            TransportResponse(
                status_code=429,
                headers={"retry-after": "2"},
                body=b'{"error": {"message": "Rate limit exceeded"}}',
                duration_ms=50.0,
            ),
            TransportResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=golden_body,
                duration_ms=120.0,
            ),
        ]
    )

    adapter = DeepSeekAdapter(
        stub, store=store, run_id=run.run_id, price_table=price_table
    )
    req = _make_sample_request()
    result = adapter.execute_round(req, op_seq=1)

    assert result.attempt_seq == 2
    assert result.total_attempts == 2
    assert len(stub.sent_requests) == 2
    assert result.finish_reason == "stop"

    # Verify artifacts on disk for both attempts
    assert (
        tmp_path
        / f"artifacts/ideation-runs/{run.run_id}/artifacts/operations/000001/attempts/000001/request.json"
    ).is_file()
    assert (
        tmp_path
        / f"artifacts/ideation-runs/{run.run_id}/artifacts/operations/000001/attempts/000001/failure.json"
    ).is_file()
    assert (
        tmp_path
        / f"artifacts/ideation-runs/{run.run_id}/artifacts/operations/000001/attempts/000002/request.json"
    ).is_file()
    assert (
        tmp_path
        / f"artifacts/ideation-runs/{run.run_id}/artifacts/operations/000001/attempts/000002/response.json"
    ).is_file()

    # Verify event chain
    count = store.verify_chain(run.run_id)
    assert count == 3  # attempt 1 finished, attempt 2 finished, operation finished


def test_retry_transient_fails_after_two_attempts(tmp_path: Path) -> None:
    """VM-CONTRACT-022-03: transient failure retried once, fails closed after attempt 2."""
    store = RunStore(tmp_path)
    run = store.create_run()

    stub = StubTransport(
        [
            TransportResponse(
                status_code=500,
                headers={},
                body=b'{"error": "Internal server error"}',
                duration_ms=30.0,
            ),
            TransportResponse(
                status_code=503,
                headers={},
                body=b'{"error": "Service unavailable"}',
                duration_ms=40.0,
            ),
        ]
    )

    adapter = DeepSeekAdapter(stub, store=store, run_id=run.run_id)
    req = _make_sample_request()

    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    assert exc_info.value.code == "provider_transient"
    assert exc_info.value.disposition == "suspend"
    assert exc_info.value.failure.attempt_seq == 2
    assert len(stub.sent_requests) == 2
    store.verify_chain(run.run_id)


def test_timeout_ambiguous_does_not_retry(tmp_path: Path) -> None:
    """VM-CONTRACT-022-03: timeout_ambiguous must not be retried automatically."""
    store = RunStore(tmp_path)
    run = store.create_run()

    stub = StubTransport([TimeoutError("Wall-clock deadline exceeded")])
    adapter = DeepSeekAdapter(stub, store=store, run_id=run.run_id)
    req = _make_sample_request()

    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    assert exc_info.value.code == "timeout_ambiguous"
    assert exc_info.value.disposition == "suspend"
    assert exc_info.value.failure.attempt_seq == 1
    assert len(stub.sent_requests) == 1  # Strictly 1 attempt!
    store.verify_chain(run.run_id)


def test_transport_ambiguous_does_not_retry(tmp_path: Path) -> None:
    """VM-CONTRACT-022-03: transport_ambiguous (connection drop) must not be retried."""
    store = RunStore(tmp_path)
    run = store.create_run()

    stub = StubTransport([ConnectionResetError("Connection reset by peer")])
    adapter = DeepSeekAdapter(stub, store=store, run_id=run.run_id)
    req = _make_sample_request()

    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    assert exc_info.value.code == "transport_ambiguous"
    assert exc_info.value.disposition == "suspend"
    assert exc_info.value.failure.attempt_seq == 1
    assert len(stub.sent_requests) == 1  # Strictly 1 attempt!
    store.verify_chain(run.run_id)


def test_rate_limited_retry_after_exceeded_does_not_wait_inside_adapter(
    tmp_path: Path,
) -> None:
    """VM-CONTRACT-022-03: rate_limited with Retry-After > 60s returns immediately without adapter wait."""
    store = RunStore(tmp_path)
    run = store.create_run()

    stub = StubTransport(
        [
            TransportResponse(
                status_code=429,
                headers={"retry-after": "120"},
                body=b'{"error": "Too many requests"}',
                duration_ms=25.0,
            )
        ]
    )

    adapter = DeepSeekAdapter(stub, store=store, run_id=run.run_id)
    req = _make_sample_request()

    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    assert exc_info.value.code == "rate_limited"
    assert exc_info.value.disposition == "suspend"
    assert exc_info.value.failure.retry_disposition == "retry_after_exceeded"
    assert len(stub.sent_requests) == 1


# ==============================================================================
# VM-REPLAY-01: Deterministic Replay of Recorded Responses
# ==============================================================================


def test_recorded_response_replay_canonical_artifacts(tmp_path: Path) -> None:
    """VM-REPLAY-01: recorded provider response replay yields identical canonical artifacts and hashes."""
    recorded_body = canonical_json_bytes(_make_golden_response_dict())
    price_table = load_price_table(REPO_ROOT)

    # Run A
    root_a = tmp_path / "run_a"
    root_a.mkdir()
    store_a = RunStore(root_a)
    run_a = store_a.create_run()
    transport_a = RecordedTransport(recorded_body)
    adapter_a = DeepSeekAdapter(
        transport_a, store=store_a, run_id=run_a.run_id, price_table=price_table
    )
    req_a = _make_sample_request()
    result_a = adapter_a.execute_round(req_a, op_seq=1)

    # Run B
    root_b = tmp_path / "run_b"
    root_b.mkdir()
    store_b = RunStore(root_b)
    run_b = store_b.create_run()
    transport_b = RecordedTransport(recorded_body)
    adapter_b = DeepSeekAdapter(
        transport_b, store=store_b, run_id=run_b.run_id, price_table=price_table
    )
    req_b = _make_sample_request()
    result_b = adapter_b.execute_round(req_b, op_seq=1)

    # Verify results match
    assert result_a.visible_content == result_b.visible_content
    assert result_a.response_id == result_b.response_id
    assert result_a.usage == result_b.usage
    assert result_a.cost.total_cny == result_b.cost.total_cny

    # Verify request.json bytes and SHA-256 are identical across runs
    req_path_a = (
        root_a
        / f"artifacts/ideation-runs/{run_a.run_id}/artifacts/operations/000001/attempts/000001/request.json"
    )
    req_path_b = (
        root_b
        / f"artifacts/ideation-runs/{run_b.run_id}/artifacts/operations/000001/attempts/000001/request.json"
    )
    assert req_path_a.read_bytes() == req_path_b.read_bytes()
    assert sha256_bytes(req_path_a.read_bytes()) == sha256_bytes(
        req_path_b.read_bytes()
    )

    # Verify response.json bytes and SHA-256 are identical across runs
    resp_path_a = (
        root_a
        / f"artifacts/ideation-runs/{run_a.run_id}/artifacts/operations/000001/attempts/000001/response.json"
    )
    resp_path_b = (
        root_b
        / f"artifacts/ideation-runs/{run_b.run_id}/artifacts/operations/000001/attempts/000001/response.json"
    )
    assert resp_path_a.read_bytes() == resp_path_b.read_bytes()
    assert sha256_bytes(resp_path_a.read_bytes()) == sha256_bytes(
        resp_path_b.read_bytes()
    )


# ==============================================================================
# VM-FAULT-01: Transport Fault Injection Across All 16 Codes
# ==============================================================================


@pytest.mark.parametrize(
    "code,resp_factory,expected_disp,expected_retry",
    [
        (
            "configuration",
            lambda: TransportResponse(400, {}, b'{"error": "Invalid param"}', 10.0),
            "terminal",
            "none",
        ),
        (
            "authentication",
            lambda: TransportResponse(401, {}, b'{"error": "Unauthorized"}', 10.0),
            "suspend",
            "none",
        ),
        (
            "insufficient_balance",
            lambda: TransportResponse(
                402, {}, b'{"error": "Insufficient balance"}', 10.0
            ),
            "suspend",
            "none",
        ),
        (
            "rate_limited",
            lambda: TransportResponse(429, {}, b'{"error": "Rate limited"}', 10.0),
            "suspend",
            "retry_candidate",
        ),
        (
            "provider_transient",
            lambda: TransportResponse(500, {}, b'{"error": "Internal error"}', 10.0),
            "suspend",
            "retry_candidate",
        ),
        (
            "timeout_ambiguous",
            lambda: TimeoutError("Read timed out"),
            "suspend",
            "none",
        ),
        (
            "transport_ambiguous",
            lambda: ConnectionResetError("Connection lost"),
            "suspend",
            "none",
        ),
        (
            "model_mismatch",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(_make_golden_response_dict(model="deepseek-v3")),
                10.0,
            ),
            "terminal",
            "none",
        ),
        (
            "truncated",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(
                    _make_golden_response_dict(finish_reason="length")
                ),
                10.0,
            ),
            "terminal",
            "none",
        ),
        (
            "content_filtered",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(
                    _make_golden_response_dict(finish_reason="content_filter")
                ),
                10.0,
            ),
            "terminal",
            "none",
        ),
        (
            "resource_exhausted",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(
                    _make_golden_response_dict(
                        finish_reason="insufficient_system_resource"
                    )
                ),
                10.0,
            ),
            "suspend",
            "retry_candidate",
        ),
        (
            "empty_content",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(_make_golden_response_dict(content="")),
                10.0,
            ),
            "terminal",
            "none",
        ),
        (
            "invalid_json",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(
                    _make_golden_response_dict(content="not valid json")
                ),
                10.0,
            ),
            "terminal",
            "none",
        ),
        (
            "unexpected_tool_call",
            lambda: TransportResponse(
                200,
                {},
                canonical_json_bytes(
                    _make_golden_response_dict(finish_reason="tool_calls")
                ),
                10.0,
            ),
            "terminal",
            "none",
        ),
        (
            "malformed_response",
            lambda: TransportResponse(
                200, {}, b'{"id": "test", "corrupt": true}', 10.0
            ),
            "terminal",
            "none",
        ),
        (
            "unknown_provider_failure",
            lambda: TransportResponse(510, {}, b'{"error": "Not extended"}', 10.0),
            "terminal",
            "none",
        ),
    ],
)
def test_fault_injection_all_16_codes(
    tmp_path: Path,
    code: str,
    resp_factory: Any,
    expected_disp: str,
    expected_retry: str,
) -> None:
    """VM-FAULT-01: 16 failure taxonomy codes injected; verify retry and suspend/terminal dispositions."""
    item = resp_factory()
    # If retry candidate, provide a second response so the test tests retry path without exhaustion
    responses = [item, item] if expected_retry == "retry_candidate" else [item]

    store = RunStore(tmp_path)
    run = store.create_run()
    stub = StubTransport(responses)
    adapter = DeepSeekAdapter(stub, store=store, run_id=run.run_id)

    # For invalid_json test, set output_mode to json_object
    req = DeepSeekRequest(
        messages=(DeepSeekMessage(role="user", content="hello"),),
        reasoning_effort="high",
        max_tokens=4096,
        output_mode="json_object" if code == "invalid_json" else "text",
        user_id="user-test",
    )

    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    failure = exc_info.value.failure
    assert failure.error_code == code
    assert failure.disposition == expected_disp
    assert failure.disposition == disposition_for_failure(code)

    if expected_retry == "retry_candidate":
        assert failure.total_attempts == 2
    else:
        assert failure.total_attempts == 1

    # Verify event chain persists properly
    store.verify_chain(run.run_id)


# ==============================================================================
# Security & Privacy: Centralized Redaction Tests
# ==============================================================================


def test_centralized_secret_redaction() -> None:
    """Verify secrets are redacted from error messages, logs, and artifacts."""
    sample_text = (
        "Authorization failed: Bearer sk-antigravity-secret-key-123456789\n"
        "Configured api_key: 'dsk-9876543210abcdefghij'"
    )
    redacted = redact_secrets(sample_text)
    assert "sk-antigravity-secret-key-123456789" not in redacted
    assert "dsk-9876543210abcdefghij" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_credential_never_in_persisted_request_artifact(tmp_path: Path) -> None:
    """Verify request.json artifact contains only allowlisted semantic payload, zero credentials."""
    store = RunStore(tmp_path)
    run = store.create_run()
    golden_body = canonical_json_bytes(_make_golden_response_dict())
    stub = StubTransport([TransportResponse(200, {}, golden_body, 10.0)])
    adapter = DeepSeekAdapter(stub, store=store, run_id=run.run_id)

    req = _make_sample_request()
    adapter.execute_round(req, op_seq=1)

    req_artifact = (
        tmp_path
        / f"artifacts/ideation-runs/{run.run_id}/artifacts/operations/000001/attempts/000001/request.json"
    )
    doc = parse_json_bytes(req_artifact.read_bytes(), label="req")
    assert "api_key" not in doc
    assert "Authorization" not in doc
    assert "credential" not in doc
    assert doc["model"] == DEEPSEEK_MODEL_ID
