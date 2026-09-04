"""Comprehensive offline tests for DeepSeek HttpTransport and execution readiness (Ticket 01).

Zero real network calls, zero model spend, 100% MockTransport.
Covers:
- Outgoing POST method, fixed DeepSeek endpoint, canonical JSON body
- Headers: Authorization: Bearer <key>, Content-Type, Accept
- Secret isolation: key redacted from errors, events, and artifacts
- Network isolation: follow_redirects=False, trust_env=False, verify=True
- Keep-alive whitespace acceptance and raw body preservation
- 60-minute wall-clock deadline enforcement -> timeout_ambiguous
- Connection error / disconnect -> transport_ambiguous
- Bounded retry taxonomy (429/500/503 retried once; 400/401/402/422 non-retryable)
- End-to-end CLI seam: _run_new_run and _run_resume with HttpTransport(MockTransport)
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

import httpx
import pytest

from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from ai_scientist.ideation.deepseek import (
    CONNECT_TIMEOUT_SECONDS,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL_ID,
    WALL_CLOCK_DEADLINE_SECONDS,
    DeepSeekAdapter,
    DeepSeekMessage,
    DeepSeekRequest,
    HttpTransport,
    ModelRoundError,
    TransportResponse,
    redact_secrets,
    validate_provider_response,
)
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.run_store import RunStore
from ai_scientist.perform_ideation_temp_free import _run_new_run, _run_resume

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"


def _make_golden_response_dict(
    *,
    content: str,
    response_id: str = "chatcmpl-mock-12345",
    prompt_tokens: int = 100,
    prompt_cache_hit_tokens: int = 60,
    prompt_cache_miss_tokens: int = 40,
    completion_tokens: int = 50,
    reasoning_tokens: int = 20,
) -> dict[str, Any]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {
                    "content": content,
                    "reasoning_content": "Thinking steps here...",
                    "role": "assistant",
                },
            }
        ],
        "created": 1725400000,
        "id": response_id,
        "model": DEEPSEEK_MODEL_ID,
        "object": "chat.completion",
        "system_fingerprint": "fp_deepseek_v4",
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


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    raw_root = workspace / "data/raw"
    policy_root = workspace / "ai_scientist/ideation/policies"
    raw_root.mkdir(parents=True)
    policy_root.mkdir(parents=True)
    shutil.copyfile(
        FIXTURE_CORPUS / "target_papers.csv", raw_root / "target_papers.csv"
    )
    shutil.copyfile(
        FIXTURE_CORPUS / "filtered_references.csv",
        raw_root / "filtered_references.csv",
    )
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/reference-authority-v1.json",
        policy_root / "reference-authority-v1.json",
    )
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/workshop-leakage-v1.json",
        policy_root / "workshop-leakage-v1.json",
    )
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/deepseek-cny-price-table-v1.json",
        policy_root / "deepseek-cny-price-table-v1.json",
    )
    (workspace / ".gitignore").write_text(
        "artifacts/ideation-runs/\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Integration Tester"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: setup integration workspace"],
        cwd=workspace,
        check=True,
    )
    return workspace


def _prepare_cli(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_scientist.prepare_ideation_inputs",
            "--workspace-root",
            str(workspace),
            *arguments,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _approved_corpus(workspace: Path) -> tuple[str, str]:
    build = _prepare_cli(
        workspace,
        "corpus",
        "build",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--build-id",
        BUILD_ID,
    )
    assert build.returncode == 0, build.stderr
    bundle_rel = json.loads(build.stdout)["bundle_path"]
    manifest = json.loads(
        (workspace / bundle_rel / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    decision = {
        "approver": "Robert",
        "bundle_content_sha256": manifest["bundle_content_sha256"],
        "case_id": manifest["case_id"],
        "corpus_sha256": manifest["inventory"]["corpus.json"],
        "decision": "approved",
        "human_review": {
            "exceptional_content_review": "approved",
            "ordinary_abstract_sampling": "approved",
            "policy_versions": "approved",
        },
        "rationale": "Fixture bundle approved for integration tests.",
        "reviewed_at": "2026-09-03T12:00:00.000000Z",
        "schema_version": "corpus-approval-decision-v1.0",
        "validation_report_sha256": manifest["inventory"]["validation-report.json"],
        "versions": manifest["versions"],
    }
    decision_path = workspace / "reviews/corpus-approval-decision.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_bytes(
        (json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    approve = _prepare_cli(
        workspace,
        "corpus",
        "approve",
        "--bundle-path",
        bundle_rel,
        "--approval-decision",
        decision_path.relative_to(workspace).as_posix(),
    )
    assert approve.returncode == 0, approve.stderr
    corpus_rel = f"{bundle_rel}/corpus.json"
    corpus_sha = sha256_bytes((workspace / corpus_rel).read_bytes())
    return corpus_rel, corpus_sha


def _approved_workshop_paths(workspace: Path) -> tuple[str, str]:
    """Approve the fixture Workshop through the real prepare/validate/approve CLI."""
    prepare = _prepare_cli(
        workspace,
        "workshop",
        "prepare",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--preparation-id",
        "preparation-001",
    )
    assert prepare.returncode == 0, prepare.stderr
    preparation_rel = json.loads(prepare.stdout)["preparation_manifest"]
    preparation = json.loads((workspace / preparation_rel).read_text(encoding="utf-8"))
    derivation = {
        "actor": "fixture-author",
        "authoring_source_sha256": preparation["authoring_source"]["sha256"],
        "completed_at": "2026-09-03T01:02:03.000000Z",
        "mechanism": "manual",
        "mechanism_version": "fixture-manual-v1",
        "schema_version": "workshop-derivation-v1.0",
        "source_fields": ["title", "abstract"],
    }
    derivation_path = workspace / "reviews/derivation.json"
    derivation_path.parent.mkdir(parents=True, exist_ok=True)
    derivation_path.write_bytes(
        (json.dumps(derivation, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    candidate = (
        "# Title: Migraine care questions\n\n"
        "## Keywords\nchronic migraine, clinical forecasting\n\n"
        "## TL;DR\nWhich research directions remain open?\n\n"
        "## Abstract\nSymptom variability complicates timely migraine care; "
        "several forecasting and cueing method families remain unexplored.\n"
    )
    (workspace / "drafts").mkdir(exist_ok=True)
    (workspace / "drafts/workshop.md").write_text(candidate, encoding="utf-8")
    validate = _prepare_cli(
        workspace,
        "workshop",
        "validate",
        "--preparation-manifest",
        preparation_rel,
        "--attempt-id",
        "attempt-001",
        "--candidate",
        "drafts/workshop.md",
        "--derivation-record",
        "reviews/derivation.json",
    )
    assert validate.returncode == 0, validate.stderr
    attempt_rel = json.loads(validate.stdout)["attempt_manifest"]
    attempt = json.loads((workspace / attempt_rel).read_text(encoding="utf-8"))
    checks = {
        "abstract_is_neutral_problem_scope": True,
        "allows_multiple_method_families": True,
        "keywords_are_established_terms": True,
        "no_answer_leakage": True,
        "no_identity_leakage": True,
        "target_relevant": True,
        "title_is_identity_free_problem_area": True,
        "tldr_is_open_question_or_tension": True,
        "written_in_english": True,
    }
    decision = {
        "attempt_manifest_sha256": sha256_bytes((workspace / attempt_rel).read_bytes()),
        "candidate_sha256": sha256_bytes(
            (workspace / attempt["candidate"]["path"]).read_bytes()
        ),
        "case_id": CASE_ID,
        "checks": checks,
        "decision": "approved",
        "rationale": "The problem remains open with several method families.",
        "reviewed_at": "2026-09-03T02:03:04.000000Z",
        "reviewer": "fixture-reviewer",
        "schema_version": "workshop-semantic-decision-v1.1",
    }
    decision_path = workspace / "reviews/semantic-decision.json"
    decision_path.write_bytes(
        (json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    approve = _prepare_cli(
        workspace,
        "workshop",
        "approve",
        "--attempt-manifest",
        attempt_rel,
        "--semantic-decision",
        decision_path.relative_to(workspace).as_posix(),
    )
    assert approve.returncode == 0, approve.stderr
    payload = json.loads(approve.stdout)
    workshop_sha = sha256_bytes((workspace / payload["workshop"]).read_bytes())
    return payload["workshop"], workshop_sha


def _commit_all(workspace: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "fixture commit"],
        cwd=workspace,
        check=True,
    )


# -----------------------------------------------------------------------------
# Unit Tests for HttpTransport Contract
# -----------------------------------------------------------------------------


def test_http_transport_outgoing_request_canonical_shape_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test POST method, target URL, Bearer auth, Content-Type, Accept, and canonical JSON body."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret-key-99999")

    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        resp_payload = _make_golden_response_dict(
            content='ACTION: SearchLiterature\nARGUMENTS: {"query": "deep learning"}'
        )
        return httpx.Response(200, json=resp_payload)

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    payload = {
        "model": DEEPSEEK_MODEL_ID,
        "messages": [{"role": "user", "content": "Hello DeepSeek"}],
        "stream": False,
    }

    resp = transport.send(payload)

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.method == "POST"
    assert str(req.url) == f"{DEEPSEEK_BASE_URL}/chat/completions"
    assert req.headers["Authorization"] == "Bearer test-secret-key-99999"
    assert req.headers["Content-Type"] == "application/json"
    assert req.headers["Accept"] == "application/json"
    assert req.content == canonical_json_bytes(payload)

    assert resp.status_code == 200
    assert resp.duration_ms >= 0.0
    parsed = json.loads(resp.body.decode("utf-8"))
    assert parsed["choices"][0]["message"]["content"].startswith(
        "ACTION: SearchLiterature"
    )


def test_http_transport_missing_api_key_raises_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing or whitespace-only API key must fail closed before sending request."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    transport = HttpTransport()
    with pytest.raises(
        ConnectionError, match="DEEPSEEK_API_KEY is not set in environment"
    ):
        transport.send({"model": DEEPSEEK_MODEL_ID})

    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
    with pytest.raises(
        ConnectionError, match="DEEPSEEK_API_KEY is not set in environment"
    ):
        transport.send({"model": DEEPSEEK_MODEL_ID})


def test_http_transport_secret_isolation_in_redaction_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Credentials must never leak into error messages, exceptions, or stored request artifacts."""
    secret = "sk-deepseek-super-secret-token-abcdef123456"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)

    # 1. Text redaction cleans direct occurrences and patterns
    msg = f"Failed with header Authorization: Bearer {secret} and token {secret}"
    redacted = redact_secrets(msg)
    assert secret not in redacted
    assert "[REDACTED_SECRET]" in redacted

    # 2. Injected adapter storing request.json never writes auth headers or keys
    store = RunStore(tmp_path)
    run = store.create_run()

    def handler(request: httpx.Request) -> httpx.Response:
        # Provider returns 401 with raw error body containing key
        return httpx.Response(
            401,
            json={
                "error": {
                    "message": f"Invalid key {secret}",
                    "type": "authentication_error",
                }
            },
        )

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(
        transport=transport,
        store=store,
        run_id=run.run_id,
        price_table=load_price_table(REPO_ROOT),
    )

    req = _make_sample_request()
    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    # Failure message and raw_error must not contain secret
    err_str = str(exc_info.value)
    assert secret not in err_str
    assert "[REDACTED_SECRET]" in err_str

    # request.json written to run store must not contain secret
    req_artifact = store.read_artifact(
        run.run_id, "artifacts/operations/000001/attempts/000001/request.json"
    )
    assert secret.encode("utf-8") not in req_artifact
    req_json = json.loads(req_artifact.decode("utf-8"))
    assert "Authorization" not in req_json
    assert "headers" not in req_json


def test_http_transport_redirect_rejected_not_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """follow_redirects=False: HTTP 301/302 redirects are not followed."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            301,
            headers={"Location": "https://attacker.com/steal"},
            text="Moved Permanently",
        )

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    resp = transport.send({"model": DEEPSEEK_MODEL_ID})

    assert call_count == 1  # Only 1 call made, redirect target was NOT requested
    assert resp.status_code == 301


def test_http_transport_ignores_ambient_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trust_env=False: ambient HTTP_PROXY and HTTPS_PROXY are ignored."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("HTTP_PROXY", "http://evil-proxy:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://evil-proxy:8080")
    monkeypatch.setenv("ALL_PROXY", "socks5://evil-proxy:1080")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_make_golden_response_dict(content="ok"))

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    resp = transport.send({"model": DEEPSEEK_MODEL_ID})
    assert resp.status_code == 200


def test_http_transport_keep_alive_whitespace_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leading keep-alive whitespace/newlines before JSON body are preserved and parsed."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    golden_payload = _make_golden_response_dict(
        content='ACTION: SearchLiterature\nARGUMENTS: {"query": "keep alive test"}'
    )
    raw_body = b"\r\n\r\n\n  " + canonical_json_bytes(golden_payload)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=raw_body, headers={"content-type": "application/json"}
        )

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    resp = transport.send({"model": DEEPSEEK_MODEL_ID})

    assert resp.body == raw_body
    # validate_provider_response must accept whitespace-prefixed JSON
    visible_content, *_rest = validate_provider_response(
        resp.status_code,
        resp.headers,
        resp.body,
        output_mode="text",
    )
    assert visible_content.startswith("ACTION: SearchLiterature")


def test_http_transport_wall_clock_deadline_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monotonic wall clock exceeding 3600s raises TimeoutError -> timeout_ambiguous."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        def body_stream():
            yield b'{"id": "test",'
            yield b'"choices": []}'

        return httpx.Response(200, content=body_stream())

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))

    # Mock time.monotonic to advance beyond WALL_CLOCK_DEADLINE_SECONDS
    clock_values = [
        0.0,
        0.1,
        WALL_CLOCK_DEADLINE_SECONDS + 5.0,
        WALL_CLOCK_DEADLINE_SECONDS + 10.0,
    ]
    monkeypatch.setattr(
        time, "monotonic", lambda: clock_values.pop(0) if clock_values else 4000.0
    )

    with pytest.raises(TimeoutError, match="exceeded wall-clock deadline"):
        transport.send({"model": DEEPSEEK_MODEL_ID})


def test_http_transport_connect_timeout_maps_to_timeout_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Connect timeout raises TimeoutError which adapter maps to timeout_ambiguous."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out after 10s")

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    store = RunStore(tmp_path)
    run = store.create_run()
    adapter = DeepSeekAdapter(
        transport=transport,
        store=store,
        run_id=run.run_id,
        price_table=load_price_table(REPO_ROOT),
    )

    req = _make_sample_request()
    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    failure = exc_info.value.failure
    assert failure.error_code == "timeout_ambiguous"
    assert failure.disposition == "suspend"
    assert failure.retry_disposition == "none"


def test_http_transport_network_disconnect_maps_to_transport_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Network error/disconnect raises ConnectionError which adapter maps to transport_ambiguous."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.NetworkError("Connection reset by peer")

    transport = HttpTransport(_http_transport=httpx.MockTransport(handler))
    store = RunStore(tmp_path)
    run = store.create_run()
    adapter = DeepSeekAdapter(
        transport=transport,
        store=store,
        run_id=run.run_id,
        price_table=load_price_table(REPO_ROOT),
    )

    req = _make_sample_request()
    with pytest.raises(ModelRoundError) as exc_info:
        adapter.execute_round(req, op_seq=1)

    failure = exc_info.value.failure
    assert failure.error_code == "transport_ambiguous"
    assert failure.disposition == "suspend"
    assert failure.retry_disposition == "none"


def test_adapter_retry_taxonomy_with_mock_http_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """429/500/503 retried at most once; 400/401/402 fail without retry."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    store = RunStore(tmp_path)
    price_table = load_price_table(REPO_ROOT)
    req = _make_sample_request()

    # 1. 429 rate limit retried once then succeeds
    run_429 = store.create_run()
    attempts_429: list[int] = []

    def handler_429(request: httpx.Request) -> httpx.Response:
        attempts_429.append(len(attempts_429) + 1)
        if len(attempts_429) == 1:
            return httpx.Response(
                429, headers={"Retry-After": "1"}, text="Rate limited"
            )
        return httpx.Response(
            200,
            json=_make_golden_response_dict(
                content='ACTION: SearchLiterature\nARGUMENTS: {"query": "retry test"}'
            ),
        )

    monkeypatch.setattr(time, "sleep", lambda _s: None)

    adapter_429 = DeepSeekAdapter(
        transport=HttpTransport(_http_transport=httpx.MockTransport(handler_429)),
        store=store,
        run_id=run_429.run_id,
        price_table=price_table,
    )
    result = adapter_429.execute_round(req, op_seq=1)
    assert len(attempts_429) == 2
    assert result.attempt_seq == 2

    # 2. 401 authentication fails immediately with suspend, NO retry
    run_401 = store.create_run()
    attempts_401: list[int] = []

    def handler_401(request: httpx.Request) -> httpx.Response:
        attempts_401.append(len(attempts_401) + 1)
        return httpx.Response(401, text="Unauthorized key")

    adapter_401 = DeepSeekAdapter(
        transport=HttpTransport(_http_transport=httpx.MockTransport(handler_401)),
        store=store,
        run_id=run_401.run_id,
        price_table=price_table,
    )
    with pytest.raises(ModelRoundError) as exc_401:
        adapter_401.execute_round(req, op_seq=1)
    assert len(attempts_401) == 1
    assert exc_401.value.failure.error_code == "authentication"
    assert exc_401.value.failure.disposition == "suspend"

    # 3. 400 configuration fails immediately with terminal, NO retry
    run_400 = store.create_run()
    attempts_400: list[int] = []

    def handler_400(request: httpx.Request) -> httpx.Response:
        attempts_400.append(len(attempts_400) + 1)
        return httpx.Response(400, text="Bad Request")

    adapter_400 = DeepSeekAdapter(
        transport=HttpTransport(_http_transport=httpx.MockTransport(handler_400)),
        store=store,
        run_id=run_400.run_id,
        price_table=price_table,
    )
    with pytest.raises(ModelRoundError) as exc_400:
        adapter_400.execute_round(req, op_seq=1)
    assert len(attempts_400) == 1
    assert exc_400.value.failure.error_code == "configuration"
    assert exc_400.value.failure.disposition == "terminal"


# -----------------------------------------------------------------------------
# End-to-End CLI Seam Tests via MockTransport
# -----------------------------------------------------------------------------


def test_cli_seam_new_run_with_mock_http_transport_seals_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full execution through _run_new_run with HttpTransport(MockTransport) seals success."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    idea_payload = {
        "Name": "http_transport_mock_idea",
        "Title": "Live Transport Verification with MockTransport",
        "Short Hypothesis": "HttpTransport seamlessly executes through MockTransport to a sealed success.",
        "Related Work": "Prior work used StubTransport; this validates production HttpTransport stack.",
        "Abstract": "We evaluate end-to-end ideation execution via HttpTransport with zero real network.",
        "Experiments": ["Run new-run with mock transport and verify seal."],
        "Risk Factors and Limitations": [
            "Requires interactive approval in production."
        ],
    }

    mock_responses = [
        _make_golden_response_dict(
            content='ACTION: SearchLiterature\nARGUMENTS: {"query": "temporal forecasting"}',
            response_id="chatcmpl-mock-0",
        ),
        _make_golden_response_dict(
            content=f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_payload)}, "grounding": ["{paper_id}"]}}',
            response_id="chatcmpl-mock-1",
        ),
    ]

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{DEEPSEEK_BASE_URL}/chat/completions"
        assert request.headers["Authorization"] == "Bearer fixture-present"
        assert (
            mock_responses
        ), "Handler received more requests than configured responses"
        resp_data = mock_responses.pop(0)
        return httpx.Response(200, json=resp_data)

    transport = HttpTransport(_http_transport=httpx.MockTransport(mock_handler))
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)

    args = argparse.Namespace(
        case_id=CASE_ID,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        entry="new-run",
        max_num_generations=1,
        num_reflections=2,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
    )

    exit_code = _run_new_run(
        args,
        workspace_root=workspace,
        adapter=adapter,
        execute=True,
    )
    assert exit_code == 0

    # Verify run sealed as success
    runs_root = workspace / "artifacts/ideation-runs"
    run_dirs = [d for d in runs_root.iterdir() if d.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    seal_file = run_dir / "seal.json"
    assert seal_file.is_file()
    seal_data = json.loads(seal_file.read_text(encoding="utf-8"))
    assert seal_data["terminal_outcome"] == "success"

    # Verify requests recorded in evidence
    req_file = run_dir / "artifacts/operations/000001/attempts/000001/request.json"
    assert req_file.is_file()
    req_json = json.loads(req_file.read_text(encoding="utf-8"))
    assert req_json["model"] == DEEPSEEK_MODEL_ID
    # Secret must never appear in request artifact
    assert "Authorization" not in req_json
    assert "fixture-present" not in req_file.read_text(encoding="utf-8")


def test_cli_seam_resume_with_mock_http_transport_completes_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suspended run resumed via _run_resume with HttpTransport(MockTransport) seals success."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    idea_payload = {
        "Name": "http_resume_mock_idea",
        "Title": "Live Transport Verification with Resume",
        "Short Hypothesis": "Resumed run successfully seals through mock HttpTransport.",
        "Related Work": "Prior tests validated resume; this tests live HttpTransport seam.",
        "Abstract": "We evaluate resume execution via HttpTransport with zero real network.",
        "Experiments": ["Resume suspended run with mock transport and verify seal."],
        "Risk Factors and Limitations": [
            "Requires interactive approval in production."
        ],
    }

    # Step 1: Start a run that gets suspended due to transport connection error
    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Simulated network outage during first run")

    failing_transport = HttpTransport(
        _http_transport=httpx.MockTransport(failing_handler)
    )
    price_table = load_price_table(workspace)
    failing_adapter = DeepSeekAdapter(
        price_table=price_table, transport=failing_transport
    )

    args_new = argparse.Namespace(
        case_id=CASE_ID,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        entry="new-run",
        max_num_generations=1,
        num_reflections=2,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
    )

    exit_code = _run_new_run(
        args_new,
        workspace_root=workspace,
        adapter=failing_adapter,
        execute=True,
    )
    assert exit_code == 3  # Suspended

    runs_root = workspace / "artifacts/ideation-runs"
    run_dirs = [d for d in runs_root.iterdir() if d.is_dir()]
    assert len(run_dirs) == 1
    run_id = run_dirs[0].name

    # Step 2: Resume the suspended run with working MockTransport
    resume_responses = [
        _make_golden_response_dict(
            content='ACTION: SearchLiterature\nARGUMENTS: {"query": "temporal forecasting"}',
            response_id="chatcmpl-resume-0",
        ),
        _make_golden_response_dict(
            content=f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_payload)}, "grounding": ["{paper_id}"]}}',
            response_id="chatcmpl-resume-1",
        ),
    ]

    def resume_handler(request: httpx.Request) -> httpx.Response:
        assert (
            resume_responses
        ), "Handler received more requests than configured responses"
        return httpx.Response(200, json=resume_responses.pop(0))

    working_transport = HttpTransport(
        _http_transport=httpx.MockTransport(resume_handler)
    )
    working_adapter = DeepSeekAdapter(
        price_table=price_table, transport=working_transport
    )

    # Resume requires interactive confirmation 'yes'
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    args_resume = argparse.Namespace(
        entry="resume",
        run_id=run_id,
    )

    resume_exit_code = _run_resume(
        args_resume,
        workspace_root=workspace,
        adapter=working_adapter,
    )
    assert resume_exit_code == 0

    seal_file = runs_root / run_id / "seal.json"
    assert seal_file.is_file()
    seal_data = json.loads(seal_file.read_text(encoding="utf-8"))
    assert seal_data["terminal_outcome"] == "success"
