from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from .atomic_judge import (
    APPROVED_ATOMIC_EFFORTS,
    APPROVED_ATOMIC_MODEL_ALIAS,
    ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION,
    ATOMIC_PREPARATION_SCHEMA_VERSION,
    ATOMIC_RESPONSE_SUBMISSION,
    MAX_PHYSICAL_ATTEMPTS,
    OPENCODE_GO_ENDPOINT,
    SUBMIT_JUDGMENT_TOOL,
    SUBMIT_JUDGMENT_TOOL_CHOICE,
    SUBMIT_JUDGMENT_TOOL_NAME,
    _load_call_packet,
    _load_manifest,
)
from .canonical import (
    canonical_json_bytes,
    resolve_repo_relative,
    sha256_bytes,
    write_once,
)
from .errors import HarnessError, fail
from .opencode_go_chat import SAFE_RESPONSE_HEADERS, _api_key, _utc_now
from .opencode_go_stream import _extract_stream_tool_response

PREPARATION_SCHEMA_VERSION = "local-ranking-atomic-opencode-go-preparation-v3.1"
CANARY_PREPARATION_SCHEMA_VERSIONS = {
    "local-ranking-atomic-opencode-go-preparation-v3.0"
}
LEGACY_PREPARATION_SCHEMA_VERSIONS = {
    "local-ranking-atomic-opencode-go-preparation-v2.1"
}
EXECUTION_RESULT_SCHEMA_VERSION = "local-ranking-atomic-opencode-go-execution-v2.1"
SMOKE_RESULT_SCHEMA_VERSION = "local-ranking-atomic-opencode-go-smoke-v2.0"
SMOKE_RECEIPT_EVIDENCE_FILES = frozenset(
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
SMOKE_RESULT_EVIDENCE_FILES = SMOKE_RECEIPT_EVIDENCE_FILES | {"receipt.json"}
ATOMIC_MAX_TOKENS = 16_384
MAX_CONCURRENCY = 4
SMOKE_CALL_COUNT = 4
RETRY_POLICY = {
    "error_feedback": False,
    "max_physical_attempts": MAX_PHYSICAL_ATTEMPTS,
    "retry_after_valid": False,
    "same_prompt": True,
    "trigger": "deterministic_invalid_only",
}


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


def _write_preparation(
    *,
    output_root: Path,
    kind: str,
    evaluator: dict[str, Any],
    atomic_manifest_sha256: str | None,
    raw_calls: list[dict[str, Any]],
    max_concurrency: int,
) -> dict[str, Any]:
    concurrency = _validated_concurrency(max_concurrency)
    calls = []
    files: dict[str, bytes] = {}
    for raw_call in raw_calls:
        sequence = raw_call["sequence"]
        call_id = raw_call["call_id"]
        prefix = f"calls/{call_id}"
        prompt_path = f"{prefix}/prompt.txt"
        request_path = f"{prefix}/request.json"
        prompt_bytes = raw_call["prompt_bytes"]
        request_bytes = canonical_json_bytes(
            _request(
                prompt=prompt_bytes.decode("utf-8"),
                reasoning_effort=evaluator["reasoning_effort"],
            )
        )
        files[prompt_path] = prompt_bytes
        files[request_path] = request_bytes
        calls.append(
            {
                "call_id": call_id,
                "orientation": raw_call["orientation"],
                "prompt_path": prompt_path,
                "prompt_sha256": sha256_bytes(prompt_bytes),
                "replicate_id": raw_call["replicate_id"],
                "request_path": request_path,
                "request_sha256": sha256_bytes(request_bytes),
                "sequence": sequence,
            }
        )
    manifest = {
        "atomic_manifest_sha256": atomic_manifest_sha256,
        "call_count": len(calls),
        "calls": calls,
        "endpoint": OPENCODE_GO_ENDPOINT,
        "evaluator": evaluator,
        "kind": kind,
        "max_concurrency": concurrency,
        "max_tokens": ATOMIC_MAX_TOKENS,
        "response_submission": ATOMIC_RESPONSE_SUBMISSION,
        "retry_policy": RETRY_POLICY,
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "status": "ready_for_execution",
    }
    for relative_path, data in files.items():
        write_once(output_root / relative_path, data)
    write_once(output_root / "manifest.json", canonical_json_bytes(manifest))
    return manifest


def prepare_atomic_transport(
    *, atomic_manifest_path: Path, output_root: Path, max_concurrency: int = 4
) -> dict[str, Any]:
    manifest, artifact_root, calls = _load_manifest(atomic_manifest_path)
    if manifest["schema_version"] != ATOMIC_PREPARATION_SCHEMA_VERSION:
        fail(
            "INVALID_ATOMIC_MANIFEST",
            "Transport preparation requires the current atomic manifest",
        )
    manifest_bytes = atomic_manifest_path.read_bytes()
    raw_calls = []
    for sequence in sorted(calls):
        call = calls[sequence]
        _load_call_packet(
            artifact_root=artifact_root,
            call=call,
            preparation_schema_version=manifest["schema_version"],
        )
        prompt_path = resolve_repo_relative(
            artifact_root, call["prompt_path"], label="atomic prompt path"
        )
        prompt_bytes = prompt_path.read_bytes()
        raw_calls.append(
            {
                "call_id": call["call_id"],
                "orientation": manifest["orientation"],
                "prompt_bytes": prompt_bytes,
                "replicate_id": manifest["replicate_id"],
                "sequence": sequence,
            }
        )
    return _write_preparation(
        output_root=output_root,
        kind="atomic",
        evaluator=manifest["evaluator"],
        atomic_manifest_sha256=sha256_bytes(manifest_bytes),
        raw_calls=raw_calls,
        max_concurrency=max_concurrency,
    )


def _smoke_probe_arguments(call_id: str) -> dict[str, Any]:
    scores = {
        "coverage_diversity": 1,
        "direct_support": 1,
        "query_usefulness": 1,
        "specificity": 1,
    }
    return {
        "catastrophic_omission_side": "neither",
        "evidence_handles": ["L1", "R1"],
        "left_scores": scores,
        "rationale": (
            f"Transport-only synthetic probe {call_id}; no evidence was judged."
        ),
        "right_scores": dict(scores),
        "winner": "tie",
    }


def _smoke_prompt(call_id: str) -> bytes:
    probe = _smoke_probe_arguments(call_id)
    return (
        "This is a transport-only tool-call probe. No external or retrieval tools are "
        "available; the only available tool is submit_judgment, which submits one blind "
        "evidence-set judgment. Call submit_judgment exactly once with these exact "
        'argument values: winner "tie", catastrophic_omission_side "neither", '
        'evidence_handles ["L1", "R1"], every left_scores and right_scores field set '
        f'to integer 1, and rationale "{probe["rationale"]}". Do not add any other text.'
    ).encode()


def prepare_smoke(
    *,
    output_root: Path,
    reasoning_effort: str = "high",
    max_concurrency: int = 4,
) -> dict[str, Any]:
    if reasoning_effort not in APPROVED_ATOMIC_EFFORTS:
        fail("INVALID_EVALUATOR", "Smoke reasoning effort must be high or max")
    evaluator = {
        "harness": "opencode-go-chat-completions",
        "model_alias": APPROVED_ATOMIC_MODEL_ALIAS,
        "provider": "opencode-go",
        "reasoning_effort": reasoning_effort,
    }
    raw_calls = [
        {
            "call_id": f"smoke-{sequence:03d}",
            "orientation": None,
            "prompt_bytes": _smoke_prompt(f"smoke-{sequence:03d}"),
            "replicate_id": None,
            "sequence": sequence,
        }
        for sequence in range(1, SMOKE_CALL_COUNT + 1)
    ]
    return _write_preparation(
        output_root=output_root,
        kind="smoke",
        evaluator=evaluator,
        atomic_manifest_sha256=None,
        raw_calls=raw_calls,
        max_concurrency=max_concurrency,
    )


def _read_canonical_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_ARTIFACT", f"{label} is unreadable JSON", error=str(exc))
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        fail("NON_CANONICAL_INPUT", f"{label} must be one canonical JSON object")
    return value, data


def _validate_preparation(
    preparation_root: Path,
) -> tuple[dict[str, Any], bytes, dict[int, dict[str, Any]]]:
    manifest, manifest_bytes = _read_canonical_object(
        preparation_root / "manifest.json", label="atomic transport manifest"
    )
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
    request_builder = _request
    if schema_version == PREPARATION_SCHEMA_VERSION:
        expected_keys = {*base_keys, "response_submission"}
    elif schema_version in CANARY_PREPARATION_SCHEMA_VERSIONS:
        expected_keys = base_keys
    elif schema_version in LEGACY_PREPARATION_SCHEMA_VERSIONS:
        expected_keys = base_keys
        request_builder = _legacy_request
    else:
        fail(
            "INVALID_PREPARATION",
            "Atomic transport preparation schema is unsupported",
        )
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
        fail("INVALID_PREPARATION", "Atomic transport manifest is incompatible")
    _validated_concurrency(manifest.get("max_concurrency"))
    atomic_sha = manifest.get("atomic_manifest_sha256")
    if (
        kind == "atomic" and (not isinstance(atomic_sha, str) or len(atomic_sha) != 64)
    ) or (kind == "smoke" and atomic_sha is not None):
        fail("INVALID_PREPARATION", "Atomic manifest binding is invalid")
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
            fail("INVALID_PREPARATION", "Prepared call schema is invalid")
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
            fail("INVALID_PREPARATION", "Prepared call identity is invalid")
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
            prompt=prompt_bytes.decode("utf-8"),
            reasoning_effort=evaluator["reasoning_effort"],
        )
        if (
            sha256_bytes(prompt_bytes) != call.get("prompt_sha256")
            or sha256_bytes(request_bytes) != call.get("request_sha256")
            or request != expected_request
        ):
            fail("HASH_MISMATCH", "Prepared prompt or request changed")
        by_sequence[sequence] = call
    return manifest, manifest_bytes, by_sequence


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


def _execution_files(output_root: Path) -> dict[str, str]:
    allowed = {
        "chunks.jsonl",
        "finished-at.txt",
        "http-status.txt",
        "receipt.json",
        "response-headers.json",
        "response.json",
        "started-at.txt",
        "stream-body.sse",
        "stream-validation-error.json",
        "transport-error.json",
    }
    result = {}
    for name in sorted(allowed):
        path = output_root / name
        if path.is_file():
            result[name] = sha256_bytes(path.read_bytes())
    return result


def _write_execution_result(
    *,
    output_root: Path,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    call: dict[str, Any],
    request_bytes: bytes,
    status: str,
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    receipt_path = output_root / "receipt.json"
    receipt_sha256 = (
        sha256_bytes(receipt_path.read_bytes()) if receipt_path.is_file() else None
    )
    result = {
        "call_binding": _call_binding(manifest=manifest, call=call),
        "error": error,
        "files": _execution_files(output_root),
        "preparation_manifest_sha256": sha256_bytes(manifest_bytes),
        "receipt_sha256": receipt_sha256,
        "request_sha256": sha256_bytes(request_bytes),
        "schema_version": EXECUTION_RESULT_SCHEMA_VERSION,
        "status": status,
    }
    write_once(output_root / "execution-result.json", canonical_json_bytes(result))
    return result


def _fail_execution(
    *,
    output_root: Path,
    manifest: dict[str, Any],
    manifest_bytes: bytes,
    call: dict[str, Any],
    request_bytes: bytes,
    error: HarnessError,
) -> None:
    _write_execution_result(
        output_root=output_root,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        call=call,
        request_bytes=request_bytes,
        status="fail",
        error=error.as_dict(),
    )
    raise error


def _require_current_preparation(manifest: dict[str, Any], *, command: str) -> None:
    if manifest["schema_version"] != PREPARATION_SCHEMA_VERSION:
        fail(
            "INVALID_PREPARATION",
            f"{command} may send only the current atomic transport preparation",
        )


def execute_call(
    *,
    preparation_root: Path,
    call_sequence: int,
    output_root: Path,
    api_key_env: str = "OPENCODE_GO_API_KEY",
    kimi_config_path: Path | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    manifest, manifest_bytes, calls = _validate_preparation(preparation_root)
    _require_current_preparation(manifest, command="execute-call")
    call = calls.get(call_sequence)
    if call is None:
        fail("UNKNOWN_LOGICAL_CALL", "Prepared call sequence does not exist")
    request_path = resolve_repo_relative(
        preparation_root, call["request_path"], label="prepared request path"
    )
    request_bytes = request_path.read_bytes()
    key = api_key or _api_key(env_name=api_key_env, kimi_config_path=kimi_config_path)
    started_bytes = (_utc_now() + "\n").encode()
    write_once(output_root / "started-at.txt", started_bytes)
    raw_parts: list[bytes] = []
    status_code: int | None = None
    safe_headers: dict[str, str] = {}
    transport_error: str | None = None
    try:
        with httpx.Client(
            timeout=httpx.Timeout(900.0, connect=30.0), transport=transport
        ) as client, client.stream(
            "POST",
            OPENCODE_GO_ENDPOINT,
            content=request_bytes,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        ) as response:
            status_code = response.status_code
            safe_headers = {
                name.lower(): value
                for name, value in response.headers.items()
                if name.lower() in SAFE_RESPONSE_HEADERS
            }
            raw_parts.extend(response.iter_bytes())
    except httpx.HTTPError as exc:
        transport_error = type(exc).__name__
    finished_bytes = (_utc_now() + "\n").encode()
    raw_stream = b"".join(raw_parts)
    status_bytes = (
        f"{status_code}\n".encode() if status_code is not None else b"unavailable\n"
    )
    header_bytes = canonical_json_bytes(safe_headers)
    write_once(output_root / "finished-at.txt", finished_bytes)
    write_once(output_root / "http-status.txt", status_bytes)
    write_once(output_root / "response-headers.json", header_bytes)
    write_once(output_root / "stream-body.sse", raw_stream)
    if transport_error is not None:
        write_once(
            output_root / "transport-error.json",
            canonical_json_bytes({"error_type": transport_error}),
        )
        _fail_execution(
            output_root=output_root,
            manifest=manifest,
            manifest_bytes=manifest_bytes,
            call=call,
            request_bytes=request_bytes,
            error=HarnessError(
                "OPENCODE_GO_STREAM_TRANSPORT_FAILED",
                "Atomic OpenCode Go request failed",
                {"error": transport_error},
            ),
        )
    if status_code != 200:
        _fail_execution(
            output_root=output_root,
            manifest=manifest,
            manifest_bytes=manifest_bytes,
            call=call,
            request_bytes=request_bytes,
            error=HarnessError(
                "OPENCODE_GO_STREAM_HTTP_FAILED",
                "Atomic OpenCode Go request returned a non-success status",
                {"status_code": status_code},
            ),
        )
    if "text/event-stream" not in safe_headers.get("content-type", ""):
        _fail_execution(
            output_root=output_root,
            manifest=manifest,
            manifest_bytes=manifest_bytes,
            call=call,
            request_bytes=request_bytes,
            error=HarnessError(
                "INVALID_SSE", "Atomic response is not text/event-stream"
            ),
        )
    request = json.loads(request_bytes)
    try:
        draft, usage, identity, chunks, diagnostics = _extract_stream_tool_response(
            raw_stream,
            expected_model=request["model"],
            tool_name=SUBMIT_JUDGMENT_TOOL_NAME,
        )
    except HarnessError as exc:
        write_once(
            output_root / "stream-validation-error.json",
            canonical_json_bytes(exc.as_dict()),
        )
        _fail_execution(
            output_root=output_root,
            manifest=manifest,
            manifest_bytes=manifest_bytes,
            call=call,
            request_bytes=request_bytes,
            error=exc,
        )
    response_bytes = canonical_json_bytes(draft)
    chunks_bytes = b"".join(canonical_json_bytes(chunk) for chunk in chunks)
    write_once(output_root / "chunks.jsonl", chunks_bytes)
    write_once(output_root / "response.json", response_bytes)
    files = {
        "chunks.jsonl": chunks_bytes,
        "finished-at.txt": finished_bytes,
        "http-status.txt": status_bytes,
        "response-headers.json": header_bytes,
        "response.json": response_bytes,
        "started-at.txt": started_bytes,
        "stream-body.sse": raw_stream,
    }
    receipt = {
        "call_binding": _call_binding(manifest=manifest, call=call),
        "diagnostics": diagnostics,
        "endpoint": OPENCODE_GO_ENDPOINT,
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "http_status": status_code,
        "identity": identity,
        "preparation_manifest_sha256": sha256_bytes(manifest_bytes),
        "provider": "opencode-go",
        "request_sha256": sha256_bytes(request_bytes),
        "schema_version": ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "status": "pass",
        "tool": {
            "name": SUBMIT_JUDGMENT_TOOL_NAME,
            "schema_sha256": sha256_bytes(canonical_json_bytes(SUBMIT_JUDGMENT_TOOL)),
        },
        "transport_qualification": {
            "forced_tool_call_accepted": True,
            "reasoning_effort_requested": request["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        },
        "usage": usage,
    }
    write_once(output_root / "receipt.json", canonical_json_bytes(receipt))
    _write_execution_result(
        output_root=output_root,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        call=call,
        request_bytes=request_bytes,
        status="pass",
        error=None,
    )
    return receipt


def _validated_smoke_usage(value: Any) -> None:
    if not isinstance(value, dict) or not {
        "completion_tokens",
        "prompt_tokens",
        "total_tokens",
    }.issubset(value):
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt usage is incomplete")
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
            fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt usage is invalid")
    if value["total_tokens"] != value["prompt_tokens"] + value["completion_tokens"]:
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt token usage is inconsistent")


def _smoke_evidence_files(*, execution_root: Path, files: Any, label: str) -> None:
    if (
        not isinstance(files, dict)
        or not files
        or any(
            not isinstance(name, str)
            or not name
            or Path(name).name != name
            or not isinstance(digest, str)
            or len(digest) != 64
            for name, digest in files.items()
        )
    ):
        fail("INVALID_SMOKE_EVIDENCE", f"{label} file hashes are invalid")
    for name, digest in files.items():
        try:
            data = (execution_root / name).read_bytes()
        except OSError as exc:
            fail(
                "MISSING_ARTIFACT",
                f"{label} evidence is missing",
                file=name,
                error=str(exc),
            )
        if sha256_bytes(data) != digest:
            fail("HASH_MISMATCH", f"{label} evidence changed", file=name)


def validate_smoke_call(
    *, preparation_root: Path, call_sequence: int, execution_root: Path
) -> dict[str, Any]:
    manifest, manifest_bytes, calls = _validate_preparation(preparation_root)
    if manifest["kind"] != "smoke":
        fail("INVALID_PREPARATION", "validate-smoke-call requires a smoke preparation")
    if manifest["schema_version"] not in (
        {PREPARATION_SCHEMA_VERSION} | CANARY_PREPARATION_SCHEMA_VERSIONS
    ):
        fail(
            "INVALID_PREPARATION",
            "validate-smoke-call requires a current or canary smoke preparation",
        )
    call = calls.get(call_sequence)
    if call is None:
        fail("UNKNOWN_LOGICAL_CALL", "Prepared call sequence does not exist")
    response_path = execution_root / "response.json"
    receipt_path = execution_root / "receipt.json"
    result_path = execution_root / "execution-result.json"
    if not (
        response_path.is_file() and receipt_path.is_file() and result_path.is_file()
    ):
        fail(
            "INCOMPLETE_SMOKE_EVIDENCE",
            "Smoke validation requires response, receipt, and execution result",
        )
    response, response_bytes = _read_canonical_object(
        response_path, label="smoke response"
    )
    receipt, receipt_bytes = _read_canonical_object(
        receipt_path, label="smoke execution receipt"
    )
    result, _ = _read_canonical_object(result_path, label="smoke execution result")
    evaluator = manifest["evaluator"]
    expected_binding = _call_binding(manifest=manifest, call=call)
    if (
        set(receipt)
        != {
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
        or receipt.get("schema_version") != ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION
        or receipt.get("status") != "pass"
        or receipt.get("provider") != "opencode-go"
        or receipt.get("endpoint") != OPENCODE_GO_ENDPOINT
        or receipt.get("http_status") != 200
        or receipt.get("call_binding") != expected_binding
        or receipt.get("preparation_manifest_sha256") != sha256_bytes(manifest_bytes)
        or receipt.get("request_sha256") != call["request_sha256"]
        or receipt.get("tool")
        != {
            "name": SUBMIT_JUDGMENT_TOOL_NAME,
            "schema_sha256": sha256_bytes(canonical_json_bytes(SUBMIT_JUDGMENT_TOOL)),
        }
        or receipt.get("transport_qualification")
        != {
            "forced_tool_call_accepted": True,
            "reasoning_effort_requested": evaluator["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        }
    ):
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt does not bind this call")
    identity = receipt["identity"]
    if not isinstance(identity, dict) or set(identity) != {
        "cost",
        "created_first",
        "created_last",
        "finish_reason",
        "model",
        "provider_response_id",
        "tool_call_id",
    }:
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt provider identity is invalid")
    created_first = identity.get("created_first")
    created_last = identity.get("created_last")
    if (
        identity.get("finish_reason") not in {"stop", "tool_calls"}
        or identity.get("model") != evaluator["model_alias"].rsplit("/", 1)[-1]
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
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt provider identity is invalid")
    cost = identity.get("cost")
    try:
        parsed_cost = Decimal(cost) if isinstance(cost, str) else Decimal("NaN")
    except InvalidOperation:
        parsed_cost = Decimal("NaN")
    if not parsed_cost.is_finite() or parsed_cost < 0:
        fail(
            "INVALID_SMOKE_EVIDENCE",
            "Smoke receipt cost must be a finite non-negative decimal string",
        )
    usage = receipt.get("usage")
    if usage is None:
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt usage is missing")
    _validated_smoke_usage(usage)
    diagnostics = receipt["diagnostics"]
    if (
        not isinstance(diagnostics, dict)
        or set(diagnostics)
        != {
            "arguments_bytes",
            "content_bytes",
            "data_event_count",
            "done_received",
            "keepalive_count",
            "post_done_cost_received",
            "reasoning_bytes",
        }
        or diagnostics.get("done_received") is not True
        or not isinstance(diagnostics.get("post_done_cost_received"), bool)
        or any(
            isinstance(diagnostics[key], bool)
            or not isinstance(diagnostics[key], int)
            or diagnostics[key] < 0
            for key in (
                "arguments_bytes",
                "content_bytes",
                "data_event_count",
                "keepalive_count",
                "reasoning_bytes",
            )
        )
    ):
        fail("INVALID_SMOKE_EVIDENCE", "Smoke receipt diagnostics are invalid")
    _smoke_evidence_files(
        execution_root=execution_root, files=receipt.get("files"), label="Smoke receipt"
    )
    if set(receipt["files"]) != SMOKE_RECEIPT_EVIDENCE_FILES:
        fail(
            "INVALID_SMOKE_EVIDENCE",
            "Smoke receipt must declare the exact raw and derived evidence set",
        )
    if receipt["files"].get("response.json") != sha256_bytes(response_bytes):
        fail("HASH_MISMATCH", "Smoke receipt does not bind this response")
    if (
        set(result)
        != {
            "call_binding",
            "error",
            "files",
            "preparation_manifest_sha256",
            "receipt_sha256",
            "request_sha256",
            "schema_version",
            "status",
        }
        or result.get("schema_version") != EXECUTION_RESULT_SCHEMA_VERSION
        or result.get("status") != "pass"
        or result.get("error") is not None
        or result.get("call_binding") != expected_binding
        or result.get("preparation_manifest_sha256") != sha256_bytes(manifest_bytes)
        or result.get("request_sha256") != call["request_sha256"]
    ):
        fail("INVALID_SMOKE_EVIDENCE", "Smoke execution result does not bind this call")
    if result.get("receipt_sha256") != sha256_bytes(receipt_bytes):
        fail("HASH_MISMATCH", "Smoke execution result and receipt do not match")
    _smoke_evidence_files(
        execution_root=execution_root,
        files=result.get("files"),
        label="Smoke execution result",
    )
    if set(result["files"]) != SMOKE_RESULT_EVIDENCE_FILES:
        fail(
            "INVALID_SMOKE_EVIDENCE",
            "Smoke execution result must declare the exact evidence set",
        )
    if result["files"].get("receipt.json") != sha256_bytes(receipt_bytes) or result[
        "files"
    ].get("response.json") != sha256_bytes(response_bytes):
        fail("HASH_MISMATCH", "Smoke execution result does not bind this evidence")
    request_path = resolve_repo_relative(
        preparation_root, call["request_path"], label="prepared request path"
    )
    request = json.loads(request_path.read_bytes())
    try:
        (
            rebuilt_response,
            rebuilt_usage,
            rebuilt_identity,
            rebuilt_chunks,
            rebuilt_diagnostics,
        ) = _extract_stream_tool_response(
            (execution_root / "stream-body.sse").read_bytes(),
            expected_model=request["model"],
            tool_name=SUBMIT_JUDGMENT_TOOL_NAME,
        )
    except HarnessError as exc:
        fail(
            "INVALID_SMOKE_EVIDENCE",
            "Smoke raw stream does not replay as a valid tool response",
            error=exc.as_dict(),
        )
    if canonical_json_bytes(rebuilt_response) != response_bytes:
        fail("HASH_MISMATCH", "Smoke response does not match the raw stream")
    chunks_bytes = b"".join(canonical_json_bytes(chunk) for chunk in rebuilt_chunks)
    if chunks_bytes != (execution_root / "chunks.jsonl").read_bytes():
        fail("HASH_MISMATCH", "Smoke chunks do not match the raw stream")
    if (
        rebuilt_identity != receipt["identity"]
        or rebuilt_diagnostics != receipt["diagnostics"]
        or rebuilt_usage != usage
    ):
        fail("HASH_MISMATCH", "Smoke receipt does not match the raw stream")
    if response != _smoke_probe_arguments(call["call_id"]):
        fail("INVALID_SMOKE_RESPONSE", "Transport smoke response schema is invalid")
    return {
        "call_id": call["call_id"],
        "response_sha256": sha256_bytes(response_bytes),
        "status": "pass",
    }


def run_smoke(
    *,
    preparation_root: Path,
    output_root: Path,
    api_key_env: str = "OPENCODE_GO_API_KEY",
    kimi_config_path: Path | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    manifest, _, calls = _validate_preparation(preparation_root)
    if manifest["kind"] != "smoke":
        fail("INVALID_PREPARATION", "run-smoke requires a smoke preparation")
    _require_current_preparation(manifest, command="run-smoke")
    key = api_key or _api_key(env_name=api_key_env, kimi_config_path=kimi_config_path)

    def run_one(sequence: int) -> dict[str, Any]:
        call = calls[sequence]
        call_root = output_root / "calls" / call["call_id"]
        try:
            receipt = execute_call(
                preparation_root=preparation_root,
                call_sequence=sequence,
                output_root=call_root,
                api_key=key,
                transport=transport,
            )
            validate_smoke_call(
                preparation_root=preparation_root,
                call_sequence=sequence,
                execution_root=call_root,
            )
            return {
                "call_id": call["call_id"],
                "error": None,
                "provider_response_id": receipt["identity"]["provider_response_id"],
                "receipt_sha256": sha256_bytes(
                    (call_root / "receipt.json").read_bytes()
                ),
                "status": "pass",
            }
        except (HarnessError, OSError, ValueError) as exc:
            error = (
                exc.as_dict()
                if isinstance(exc, HarnessError)
                else {"code": "SMOKE_CALL_FAILED", "message": str(exc)}
            )
            return {
                "call_id": call["call_id"],
                "error": error,
                "provider_response_id": None,
                "receipt_sha256": None,
                "status": "fail",
            }

    results = []
    with ThreadPoolExecutor(max_workers=manifest["max_concurrency"]) as executor:
        futures = {
            executor.submit(run_one, sequence): sequence for sequence in sorted(calls)
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda result: result["call_id"])
    response_ids = [
        result["provider_response_id"]
        for result in results
        if result["provider_response_id"] is not None
    ]
    passed = all(result["status"] == "pass" for result in results) and len(
        set(response_ids)
    ) == len(results)
    smoke_result = {
        "call_count": len(results),
        "calls": results,
        "max_concurrency": manifest["max_concurrency"],
        "schema_version": SMOKE_RESULT_SCHEMA_VERSION,
        "status": "pass" if passed else "fail",
    }
    write_once(output_root / "result.json", canonical_json_bytes(smoke_result))
    if not passed:
        fail("SMOKE_FAILED", "Atomic OpenCode Go concurrency smoke failed")
    return smoke_result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and execute atomic OpenCode Go calls"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    atomic = subparsers.add_parser("prepare-atomic")
    atomic.add_argument("--atomic-manifest", type=Path, required=True)
    atomic.add_argument("--output-root", type=Path, required=True)
    atomic.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY)
    smoke = subparsers.add_parser("prepare-smoke")
    smoke.add_argument("--output-root", type=Path, required=True)
    smoke.add_argument(
        "--reasoning-effort", choices=sorted(APPROVED_ATOMIC_EFFORTS), default="high"
    )
    smoke.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY)
    execute = subparsers.add_parser("execute-call")
    execute.add_argument("--preparation-root", type=Path, required=True)
    execute.add_argument("--call-sequence", type=int, required=True)
    execute.add_argument("--output-root", type=Path, required=True)
    execute.add_argument("--api-key-env", default="OPENCODE_GO_API_KEY")
    execute.add_argument("--kimi-config", type=Path)
    run = subparsers.add_parser("run-smoke")
    run.add_argument("--preparation-root", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--api-key-env", default="OPENCODE_GO_API_KEY")
    run.add_argument("--kimi-config", type=Path)
    validate = subparsers.add_parser("validate-smoke-call")
    validate.add_argument("--preparation-root", type=Path, required=True)
    validate.add_argument("--call-sequence", type=int, required=True)
    validate.add_argument("--execution-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare-atomic":
            result = prepare_atomic_transport(
                atomic_manifest_path=args.atomic_manifest,
                output_root=args.output_root,
                max_concurrency=args.max_concurrency,
            )
        elif args.command == "prepare-smoke":
            result = prepare_smoke(
                output_root=args.output_root,
                reasoning_effort=args.reasoning_effort,
                max_concurrency=args.max_concurrency,
            )
        elif args.command == "execute-call":
            result = execute_call(
                preparation_root=args.preparation_root,
                call_sequence=args.call_sequence,
                output_root=args.output_root,
                api_key_env=args.api_key_env,
                kimi_config_path=args.kimi_config,
            )
        elif args.command == "validate-smoke-call":
            result = validate_smoke_call(
                preparation_root=args.preparation_root,
                call_sequence=args.call_sequence,
                execution_root=args.execution_root,
            )
        else:
            result = run_smoke(
                preparation_root=args.preparation_root,
                output_root=args.output_root,
                api_key_env=args.api_key_env,
                kimi_config_path=args.kimi_config,
            )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "ATOMIC_OPENCODE_GO_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    displayed_result = result
    if args.command in {"prepare-atomic", "prepare-smoke"}:
        displayed_result = {
            key: result[key]
            for key in (
                "call_count",
                "kind",
                "max_concurrency",
                "max_tokens",
                "schema_version",
                "status",
            )
        }
    print(json.dumps({"result": displayed_result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
