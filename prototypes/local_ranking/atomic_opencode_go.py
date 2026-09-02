from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from .atomic_judge import (
    APPROVED_ATOMIC_EFFORTS,
    APPROVED_ATOMIC_MODEL_ALIAS,
    ATOMIC_EXECUTION_RECEIPT_SCHEMA_VERSION,
    ATOMIC_MAX_TOKENS,
    ATOMIC_PREPARATION_SCHEMA_VERSION,
    ATOMIC_RESPONSE_SUBMISSION,
    CANARY_PREPARATION_SCHEMA_VERSIONS,
    OPENCODE_GO_ENDPOINT,
    PREPARATION_SCHEMA_VERSION,
    RETRY_POLICY,
    SMOKE_CALL_COUNT,
    SUBMIT_JUDGMENT_TOOL,
    SUBMIT_JUDGMENT_TOOL_NAME,
    _call_binding,
    _load_call_packet,
    _load_manifest,
    _read_canonical_object,
    _request,
    _validate_preparation,
    _validate_tool_success_evidence,
    _validated_concurrency,
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

EXECUTION_RESULT_SCHEMA_VERSION = "local-ranking-atomic-opencode-go-execution-v2.1"
SMOKE_RESULT_SCHEMA_VERSION = "local-ranking-atomic-opencode-go-smoke-v2.0"
MAX_CONCURRENCY = 4


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
    expected_model = evaluator["model_alias"].rsplit("/", 1)[-1]
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
    _validate_tool_success_evidence(
        evidence_root=execution_root,
        receipt=receipt,
        result=result,
        expected_model=expected_model,
        code="INVALID_SMOKE_EVIDENCE",
    )
    if (
        receipt["files"]["response.json"] != sha256_bytes(response_bytes)
        or result["files"]["receipt.json"] != sha256_bytes(receipt_bytes)
        or result["files"]["response.json"] != sha256_bytes(response_bytes)
    ):
        fail("HASH_MISMATCH", "Smoke evidence does not bind this response")
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
