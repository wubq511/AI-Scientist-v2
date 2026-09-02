from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from .atomic_judge import (
    ATOMIC_PREPARATION_SCHEMA_VERSION,
    ATOMIC_RESPONSE_SUBMISSION,
    MAX_PHYSICAL_ATTEMPTS,
    _load_manifest,
    _validate_attempt,
    record_attempt,
    record_failed_attempt,
    resolve_orientation,
)
from .atomic_opencode_go import (
    PREPARATION_SCHEMA_VERSION,
    _validate_preparation,
    execute_call,
)
from .canonical import (
    canonical_json_bytes,
    sha256_bytes,
    write_identical_or_once,
)
from .errors import HarnessError, fail
from .opencode_go_chat import _api_key

ORIENTATION_RUN_SCHEMA_VERSION = "local-ranking-atomic-orientation-run-v2.2"
ROUND_SCHEMA_VERSION = "local-ranking-atomic-execution-round-v2.2"


def _load_existing_attempt(
    *,
    attempt_path: Path,
    manifest: dict[str, Any],
    artifact_root: Path,
    calls_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    attempt, _ = _validate_attempt(
        attempt_path=attempt_path,
        manifest=manifest,
        artifact_root=artifact_root,
        calls_by_id=calls_by_id,
    )
    return attempt


def _attempt_paths(
    output_root: Path, *, call_id: str, attempt_number: int
) -> tuple[Path, Path]:
    execution_root = output_root / "executions" / call_id / f"attempt-{attempt_number}"
    ledger_root = output_root / "attempts" / call_id / f"attempt-{attempt_number}"
    return execution_root, ledger_root


def _preflight_resume(
    *,
    output_root: Path,
    manifest: dict[str, Any],
    artifact_root: Path,
    calls: dict[int, dict[str, Any]],
) -> dict[tuple[int, int], dict[str, Any]]:
    calls_by_id = {call["call_id"]: call for call in calls.values()}
    existing = {}
    for sequence, call in calls.items():
        for attempt_number in range(1, MAX_PHYSICAL_ATTEMPTS + 1):
            execution_root, ledger_root = _attempt_paths(
                output_root,
                call_id=call["call_id"],
                attempt_number=attempt_number,
            )
            attempt_path = ledger_root / "attempt.json"
            if attempt_path.is_file():
                existing[(sequence, attempt_number)] = _load_existing_attempt(
                    attempt_path=attempt_path,
                    manifest=manifest,
                    artifact_root=artifact_root,
                    calls_by_id=calls_by_id,
                )
            elif (
                execution_root / "execution-result.json"
            ).is_file() and not ledger_root.exists():
                result_path = execution_root / "execution-result.json"
                try:
                    execution_result = json.loads(result_path.read_bytes())
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    fail(
                        "AMBIGUOUS_PARTIAL_ATTEMPT",
                        "Completed execution evidence is unreadable and cannot be recovered safely",
                        call_id=call["call_id"],
                        attempt_number=attempt_number,
                        error=str(exc),
                    )
                if execution_result.get("status") == "pass":
                    existing[(sequence, attempt_number)] = record_attempt(
                        manifest_path=artifact_root / "private" / "manifest.json",
                        call_sequence=sequence,
                        attempt_number=attempt_number,
                        response_path=execution_root / "response.json",
                        execution_receipt_path=execution_root / "receipt.json",
                        execution_result_path=result_path,
                        output_root=ledger_root,
                    )
                elif execution_result.get("status") == "fail":
                    existing[(sequence, attempt_number)] = record_failed_attempt(
                        manifest_path=artifact_root / "private" / "manifest.json",
                        call_sequence=sequence,
                        attempt_number=attempt_number,
                        execution_result_path=result_path,
                        output_root=ledger_root,
                    )
                else:
                    fail(
                        "AMBIGUOUS_PARTIAL_ATTEMPT",
                        "Execution result status cannot be recovered safely",
                        call_id=call["call_id"],
                        attempt_number=attempt_number,
                    )
            elif execution_root.exists() or ledger_root.exists():
                fail(
                    "AMBIGUOUS_PARTIAL_ATTEMPT",
                    "A physical call may have started without a complete ledger; do not resend it automatically",
                    call_id=call["call_id"],
                    attempt_number=attempt_number,
                )
        attempt_numbers = sorted(
            attempt_number
            for existing_sequence, attempt_number in existing
            if existing_sequence == sequence
        )
        if attempt_numbers != list(range(1, len(attempt_numbers) + 1)):
            fail(
                "INVALID_ATTEMPT_SEQUENCE",
                "Physical attempts must be consecutive from attempt 1",
                call_id=call["call_id"],
            )
        if any(
            existing[(sequence, attempt_number)]["status"] == "valid"
            for attempt_number in attempt_numbers[:-1]
        ):
            fail(
                "RETRY_AFTER_VALID",
                "A valid response must not have a later physical attempt",
                call_id=call["call_id"],
            )
    return existing


def _checkpoint_round(
    *, output_root: Path, attempt_number: int, attempts: dict[int, dict[str, Any]]
) -> None:
    checkpoint = {
        "attempt_number": attempt_number,
        "calls": [
            {
                "attempt_sha256": sha256_bytes(
                    (
                        output_root
                        / "attempts"
                        / attempt["call_id"]
                        / f"attempt-{attempt_number}"
                        / "attempt.json"
                    ).read_bytes()
                ),
                "call_id": attempt["call_id"],
                "error_code": (
                    attempt["validation"]["error"]["code"]
                    if attempt["status"] == "invalid"
                    else None
                ),
                "provider_response_id": attempt["provider_response_id"],
                "status": attempt["status"],
            }
            for _, attempt in sorted(attempts.items())
        ],
        "schema_version": ROUND_SCHEMA_VERSION,
        "status": "complete",
    }
    write_identical_or_once(
        output_root / f"round-{attempt_number}.json",
        canonical_json_bytes(checkpoint),
    )


def _resume_completed_run(
    *,
    output_root: Path,
    manifest: dict[str, Any],
    atomic_manifest_bytes: bytes,
    preparation_bytes: bytes,
) -> dict[str, Any] | None:
    result_path = output_root / "run-result.json"
    if not result_path.is_file():
        return None
    try:
        result_bytes = result_path.read_bytes()
        result = json.loads(result_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(
            "INVALID_RUN_RESULT", "Orientation run result is unreadable", error=str(exc)
        )
    expected_keys = {
        "atomic_manifest_sha256",
        "exhausted_call_ids",
        "orientation",
        "preparation_manifest_sha256",
        "replicate_id",
        "schema_version",
        "status",
        "trace_sha256",
    }
    if (
        not isinstance(result, dict)
        or canonical_json_bytes(result) != result_bytes
        or set(result) != expected_keys
        or result.get("schema_version") != ORIENTATION_RUN_SCHEMA_VERSION
        or result.get("atomic_manifest_sha256") != sha256_bytes(atomic_manifest_bytes)
        or result.get("preparation_manifest_sha256") != sha256_bytes(preparation_bytes)
        or result.get("orientation") != manifest["orientation"]
        or result.get("replicate_id") != manifest["replicate_id"]
        or result.get("status") not in {"pass", "incomplete"}
    ):
        fail("INVALID_RUN_RESULT", "Orientation run result identity is invalid")
    if result["status"] == "incomplete":
        fail(
            "ORIENTATION_INCOMPLETE",
            "The recorded orientation exhausted at least one logical call",
            exhausted_call_ids=result["exhausted_call_ids"],
        )
    trace_path = output_root / "resolved" / "trace.json"
    try:
        trace_bytes = trace_path.read_bytes()
        trace = json.loads(trace_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(
            "INVALID_RUN_RESULT",
            "Resolved orientation trace is unreadable",
            error=str(exc),
        )
    if canonical_json_bytes(trace) != trace_bytes or sha256_bytes(
        trace_bytes
    ) != result.get("trace_sha256"):
        fail("HASH_MISMATCH", "Resolved orientation trace changed")
    return {"run_result": result, "trace": trace}


def run_orientation(
    *,
    atomic_manifest_path: Path,
    preparation_root: Path,
    output_root: Path,
    api_key_env: str = "OPENCODE_GO_API_KEY",
    kimi_config_path: Path | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    manifest, artifact_root, calls = _load_manifest(atomic_manifest_path)
    preparation, preparation_bytes, prepared_calls = _validate_preparation(
        preparation_root
    )
    atomic_manifest_bytes = atomic_manifest_path.read_bytes()
    if (
        manifest["schema_version"] != ATOMIC_PREPARATION_SCHEMA_VERSION
        or manifest.get("response_submission") != ATOMIC_RESPONSE_SUBMISSION
    ):
        fail(
            "INVALID_ATOMIC_MANIFEST",
            "Orientation runner requires the current atomic preparation",
        )
    if (
        preparation["schema_version"] != PREPARATION_SCHEMA_VERSION
        or preparation.get("response_submission") != ATOMIC_RESPONSE_SUBMISSION
    ):
        fail(
            "INVALID_PREPARATION",
            "Orientation runner requires the current atomic transport preparation",
        )
    if (
        preparation["kind"] != "atomic"
        or preparation["atomic_manifest_sha256"] != sha256_bytes(atomic_manifest_bytes)
        or preparation["evaluator"] != manifest["evaluator"]
        or set(prepared_calls) != set(calls)
        or any(
            prepared_calls[sequence]["call_id"] != calls[sequence]["call_id"]
            or prepared_calls[sequence]["orientation"] != manifest["orientation"]
            or prepared_calls[sequence]["replicate_id"] != manifest["replicate_id"]
            or prepared_calls[sequence]["prompt_sha256"]
            != calls[sequence]["prompt_sha256"]
            for sequence in calls
        )
    ):
        fail(
            "PREPARATION_IDENTITY_MISMATCH",
            "Transport preparation does not bind the atomic orientation",
        )
    existing = _preflight_resume(
        output_root=output_root,
        manifest=manifest,
        artifact_root=artifact_root,
        calls=calls,
    )
    completed = _resume_completed_run(
        output_root=output_root,
        manifest=manifest,
        atomic_manifest_bytes=atomic_manifest_bytes,
        preparation_bytes=preparation_bytes,
    )
    if completed is not None:
        return completed
    key = api_key or _api_key(env_name=api_key_env, kimi_config_path=kimi_config_path)

    def run_physical(sequence: int, attempt_number: int) -> dict[str, Any]:
        if (sequence, attempt_number) in existing:
            return existing[(sequence, attempt_number)]
        call = calls[sequence]
        execution_root, ledger_root = _attempt_paths(
            output_root,
            call_id=call["call_id"],
            attempt_number=attempt_number,
        )
        try:
            execute_call(
                preparation_root=preparation_root,
                call_sequence=sequence,
                output_root=execution_root,
                api_key=key,
                transport=transport,
            )
        except HarnessError:
            result_path = execution_root / "execution-result.json"
            if not result_path.is_file():
                raise
            return record_failed_attempt(
                manifest_path=atomic_manifest_path,
                call_sequence=sequence,
                attempt_number=attempt_number,
                execution_result_path=result_path,
                output_root=ledger_root,
            )
        return record_attempt(
            manifest_path=atomic_manifest_path,
            call_sequence=sequence,
            attempt_number=attempt_number,
            response_path=execution_root / "response.json",
            execution_receipt_path=execution_root / "receipt.json",
            execution_result_path=execution_root / "execution-result.json",
            output_root=ledger_root,
        )

    first_attempts: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=preparation["max_concurrency"]) as executor:
        futures = {
            executor.submit(run_physical, sequence, 1): sequence
            for sequence in sorted(calls)
        }
        for future in as_completed(futures):
            first_attempts[futures[future]] = future.result()
    _checkpoint_round(
        output_root=output_root, attempt_number=1, attempts=first_attempts
    )

    attempts_by_number = {1: first_attempts}
    latest_attempts = first_attempts
    for attempt_number in range(2, MAX_PHYSICAL_ATTEMPTS + 1):
        retry_sequences = [
            sequence
            for sequence, attempt in sorted(latest_attempts.items())
            if attempt["status"] == "invalid"
        ]
        if not retry_sequences:
            break
        current_attempts: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=preparation["max_concurrency"]) as executor:
            futures = {
                executor.submit(run_physical, sequence, attempt_number): sequence
                for sequence in retry_sequences
            }
            for future in as_completed(futures):
                current_attempts[futures[future]] = future.result()
        _checkpoint_round(
            output_root=output_root,
            attempt_number=attempt_number,
            attempts=current_attempts,
        )
        attempts_by_number[attempt_number] = current_attempts
        latest_attempts = current_attempts

    exhausted = [
        sequence
        for sequence, attempt in sorted(latest_attempts.items())
        if attempt["status"] == "invalid"
    ]
    attempt_paths = []
    for sequence, call in sorted(calls.items()):
        attempt_paths.append(
            output_root / "attempts" / call["call_id"] / "attempt-1" / "attempt.json"
        )
        for attempt_number in range(2, MAX_PHYSICAL_ATTEMPTS + 1):
            if sequence in attempts_by_number.get(attempt_number, {}):
                attempt_paths.append(
                    output_root
                    / "attempts"
                    / call["call_id"]
                    / f"attempt-{attempt_number}"
                    / "attempt.json"
                )
    if exhausted:
        run_result = {
            "atomic_manifest_sha256": sha256_bytes(atomic_manifest_bytes),
            "exhausted_call_ids": [
                calls[sequence]["call_id"] for sequence in exhausted
            ],
            "orientation": manifest["orientation"],
            "preparation_manifest_sha256": sha256_bytes(preparation_bytes),
            "replicate_id": manifest["replicate_id"],
            "schema_version": ORIENTATION_RUN_SCHEMA_VERSION,
            "status": "incomplete",
            "trace_sha256": None,
        }
        write_identical_or_once(
            output_root / "run-result.json", canonical_json_bytes(run_result)
        )
        fail(
            "ORIENTATION_INCOMPLETE",
            (
                "At least one logical call remained invalid after "
                f"{MAX_PHYSICAL_ATTEMPTS} physical attempts"
            ),
            exhausted_call_ids=run_result["exhausted_call_ids"],
        )
    trace = resolve_orientation(
        manifest_path=atomic_manifest_path,
        attempt_paths=attempt_paths,
        output_root=output_root / "resolved",
    )
    trace_bytes = (output_root / "resolved" / "trace.json").read_bytes()
    run_result = {
        "atomic_manifest_sha256": sha256_bytes(atomic_manifest_bytes),
        "exhausted_call_ids": [],
        "orientation": manifest["orientation"],
        "preparation_manifest_sha256": sha256_bytes(preparation_bytes),
        "replicate_id": manifest["replicate_id"],
        "schema_version": ORIENTATION_RUN_SCHEMA_VERSION,
        "status": "pass",
        "trace_sha256": sha256_bytes(trace_bytes),
    }
    write_identical_or_once(
        output_root / "run-result.json", canonical_json_bytes(run_result)
    )
    return {"run_result": run_result, "trace": trace}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one atomic local-ranking orientation with bounded retry"
    )
    parser.add_argument("--atomic-manifest", type=Path, required=True)
    parser.add_argument("--preparation-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--api-key-env", default="OPENCODE_GO_API_KEY")
    parser.add_argument("--kimi-config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_orientation(
            atomic_manifest_path=args.atomic_manifest,
            preparation_root=args.preparation_root,
            output_root=args.output_root,
            api_key_env=args.api_key_env,
            kimi_config_path=args.kimi_config,
        )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "ATOMIC_ORIENTATION_RUN_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {"result": result["run_result"], "status": "success"}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
