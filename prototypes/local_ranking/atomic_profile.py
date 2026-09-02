from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

from .atomic_judge import (
    APPROVED_ATOMIC_MODEL_ALIAS,
    EXPECTED_ITEM_COUNT,
    MAX_PHYSICAL_ATTEMPTS,
    _load_manifest,
)
from .atomic_opencode_go import (
    ATOMIC_MAX_TOKENS,
    MAX_CONCURRENCY,
    RETRY_POLICY,
    _validate_preparation,
)
from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail
from .opencode_go_chat import _api_key, _utc_now

USAGE_SNAPSHOT_SCHEMA_VERSION = "local-ranking-opencode-go-usage-snapshot-v2.0"
PROFILE_MANIFEST_SCHEMA_VERSION = "local-ranking-atomic-profile-manifest-v2.1"
USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
MODELS_URL = "https://opencode.ai/zen/go/v1/models"
EXPECTED_REPLICATES = 3


def _read_canonical_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_ARTIFACT", f"{label} is unreadable JSON", error=str(exc))
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        fail("NON_CANONICAL_INPUT", f"{label} must be one canonical JSON object")
    return value, data


def snapshot_usage(
    *,
    output_path: Path,
    api_key_env: str = "OPENCODE_GO_API_KEY",
    kimi_config_path: Path | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    key = api_key or _api_key(env_name=api_key_env, kimi_config_path=kimi_config_path)
    with httpx.Client(timeout=30.0, transport=transport) as client:
        usage_response = client.get(
            USAGE_URL, headers={"Authorization": f"Bearer {key}"}
        )
        models_response = client.get(MODELS_URL)
    try:
        usage_body = usage_response.json()
        models_body = models_response.json()
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "Usage or model list is not JSON",
            error=str(exc),
        )
    model_id = APPROVED_ATOMIC_MODEL_ALIAS.rsplit("/", 1)[-1]
    model_present = (
        isinstance(models_body, dict)
        and isinstance(models_body.get("data"), list)
        and any(
            isinstance(item, dict) and item.get("id") == model_id
            for item in models_body["data"]
        )
    )
    usage = usage_body.get("usage") if isinstance(usage_body, dict) else None
    if (
        usage_response.status_code != 200
        or models_response.status_code != 200
        or not isinstance(usage, dict)
        or not model_present
    ):
        fail(
            "PROVIDER_PREFLIGHT_FAILED",
            "OpenCode Go usage or model availability preflight failed",
            usage_http_status=usage_response.status_code,
            models_http_status=models_response.status_code,
            model_present=model_present,
        )
    snapshot = {
        "captured_at": _utc_now(),
        "model_id": model_id,
        "model_present": True,
        "models_http_status": models_response.status_code,
        "models_url": MODELS_URL,
        "schema_version": USAGE_SNAPSHOT_SCHEMA_VERSION,
        "status": "pass",
        "usage": usage,
        "usage_http_status": usage_response.status_code,
        "usage_url": USAGE_URL,
    }
    write_once(output_path, canonical_json_bytes(snapshot))
    return snapshot


def _validate_usage_snapshot(path: Path) -> tuple[dict[str, Any], bytes]:
    snapshot, snapshot_bytes = _read_canonical_object(
        path, label="OpenCode Go usage snapshot"
    )
    if (
        set(snapshot)
        != {
            "captured_at",
            "model_id",
            "model_present",
            "models_http_status",
            "models_url",
            "schema_version",
            "status",
            "usage",
            "usage_http_status",
            "usage_url",
        }
        or snapshot.get("schema_version") != USAGE_SNAPSHOT_SCHEMA_VERSION
        or snapshot.get("status") != "pass"
        or snapshot.get("model_id") != APPROVED_ATOMIC_MODEL_ALIAS.rsplit("/", 1)[-1]
        or snapshot.get("model_present") is not True
        or snapshot.get("models_http_status") != 200
        or snapshot.get("usage_http_status") != 200
        or snapshot.get("models_url") != MODELS_URL
        or snapshot.get("usage_url") != USAGE_URL
        or not isinstance(snapshot.get("usage"), dict)
    ):
        fail("INVALID_USAGE_SNAPSHOT", "OpenCode Go usage snapshot is incompatible")
    periods = snapshot["usage"]
    for period in ("rolling", "weekly", "monthly"):
        value = periods.get(period)
        if (
            not isinstance(value, dict)
            or value.get("status") != "ok"
            or isinstance(value.get("percent"), bool)
            or not isinstance(value.get("percent"), int)
            or not 0 <= value["percent"] <= 100
            or not isinstance(value.get("resetsAt"), str)
            or not value["resetsAt"]
        ):
            fail(
                "QUOTA_NOT_READY",
                "OpenCode Go quota period is not ready for the frozen profile",
                period=period,
            )
    return snapshot, snapshot_bytes


def prepare_profile(
    *,
    replicates: list[dict[str, Path | str]],
    source_commit: str,
    reasoning_effort: str,
    usage_snapshot_path: Path,
    smoke_result_sha256: str,
    output_path: Path,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        fail("INVALID_SOURCE_COMMIT", "Profile source commit must be a full SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", smoke_result_sha256):
        fail("INVALID_SMOKE_BINDING", "Smoke result SHA-256 is invalid")
    if reasoning_effort not in {"high", "max"}:
        fail("PROFILE_MISMATCH", "Profile reasoning effort must be high or max")
    if len(replicates) != EXPECTED_REPLICATES:
        fail("INVALID_PROFILE_INPUT", "Profile requires exactly three replicates")
    usage_snapshot, usage_snapshot_bytes = _validate_usage_snapshot(usage_snapshot_path)
    evaluator: dict[str, Any] | None = None
    seen_replicates: set[str] = set()
    source_hashes: dict[int, set[tuple[str, str]]] = {1: set(), 2: set()}
    frozen_replicates = []
    for raw_replicate in replicates:
        replicate_id = raw_replicate.get("replicate_id")
        if (
            not isinstance(replicate_id, str)
            or not replicate_id
            or replicate_id in seen_replicates
        ):
            fail("INVALID_PROFILE_INPUT", "Profile replicate identity is invalid")
        seen_replicates.add(replicate_id)
        orientations = []
        for orientation in (1, 2):
            atomic_path = raw_replicate.get(f"orientation_{orientation}_atomic")
            preparation_root = raw_replicate.get(
                f"orientation_{orientation}_preparation"
            )
            if not isinstance(atomic_path, Path) or not isinstance(
                preparation_root, Path
            ):
                fail(
                    "INVALID_PROFILE_INPUT", "Profile orientation paths are incomplete"
                )
            atomic_manifest, _, atomic_calls = _load_manifest(atomic_path)
            preparation, preparation_bytes, prepared_calls = _validate_preparation(
                preparation_root
            )
            atomic_bytes = atomic_path.read_bytes()
            if (
                atomic_manifest["replicate_id"] != replicate_id
                or atomic_manifest["orientation"] != orientation
                or preparation["kind"] != "atomic"
                or preparation["atomic_manifest_sha256"] != sha256_bytes(atomic_bytes)
                or preparation["evaluator"] != atomic_manifest["evaluator"]
                or preparation["max_concurrency"] != MAX_CONCURRENCY
                or preparation["max_tokens"] != ATOMIC_MAX_TOKENS
                or preparation["retry_policy"] != RETRY_POLICY
                or set(prepared_calls) != set(atomic_calls)
            ):
                fail(
                    "PROFILE_BINDING_MISMATCH",
                    "Profile orientation preparation does not match its atomic manifest",
                    replicate_id=replicate_id,
                    orientation=orientation,
                )
            if evaluator is None:
                evaluator = atomic_manifest["evaluator"]
            elif atomic_manifest["evaluator"] != evaluator:
                fail("PROFILE_MISMATCH", "Profile evaluator identities differ")
            source_hashes[orientation].add(
                (
                    atomic_manifest["source_bundle_file_sha256"],
                    atomic_manifest["source_bundle_self_sha256"],
                )
            )
            orientations.append(
                {
                    "atomic_manifest_path": atomic_path.as_posix(),
                    "atomic_manifest_sha256": sha256_bytes(atomic_bytes),
                    "orientation": orientation,
                    "preparation_manifest_path": (
                        preparation_root / "manifest.json"
                    ).as_posix(),
                    "preparation_manifest_sha256": sha256_bytes(preparation_bytes),
                }
            )
        frozen_replicates.append(
            {"orientations": orientations, "replicate_id": replicate_id}
        )
    if evaluator is None or (
        evaluator.get("model_alias") != APPROVED_ATOMIC_MODEL_ALIAS
        or evaluator.get("reasoning_effort") != reasoning_effort
    ):
        fail(
            "PROFILE_MISMATCH",
            "Atomic profile evaluator does not match the requested effort",
        )
    if any(len(values) != 1 for values in source_hashes.values()):
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "Replicates do not reuse one frozen source per orientation",
        )
    manifest = {
        "budget": {
            "logical_calls": EXPECTED_ITEM_COUNT * 2 * EXPECTED_REPLICATES,
            "max_concurrency": MAX_CONCURRENCY,
            "max_physical_calls": (
                EXPECTED_ITEM_COUNT * 2 * EXPECTED_REPLICATES * MAX_PHYSICAL_ATTEMPTS
            ),
            "max_tokens_per_call": ATOMIC_MAX_TOKENS,
        },
        "early_stop": {
            "logical_call_exhausted": "stop_incomplete",
            "per_replicate_stable_below_22": "stop_profile_failed",
            "pooled_69_impossible": "stop_profile_failed",
            "stable_directional_count_zero": "stop_profile_failed",
        },
        "evaluator": evaluator,
        "replicates": frozen_replicates,
        "retry_policy": RETRY_POLICY,
        "schema_version": PROFILE_MANIFEST_SCHEMA_VERSION,
        "smoke_result_sha256": smoke_result_sha256,
        "source_bundle_hashes_by_orientation": {
            str(orientation): {
                "file_sha256": next(iter(values))[0],
                "self_sha256": next(iter(values))[1],
            }
            for orientation, values in source_hashes.items()
        },
        "source_commit": source_commit,
        "status": f"ready_for_pro_{reasoning_effort}_calibration",
        "usage_snapshot": usage_snapshot,
        "usage_snapshot_sha256": sha256_bytes(usage_snapshot_bytes),
    }
    write_once(output_path, canonical_json_bytes(manifest))
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze an atomic DeepSeek profile execution manifest"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    usage = subparsers.add_parser("snapshot-usage")
    usage.add_argument("--output", type=Path, required=True)
    usage.add_argument("--api-key-env", default="OPENCODE_GO_API_KEY")
    usage.add_argument("--kimi-config", type=Path)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-commit", required=True)
    prepare.add_argument("--reasoning-effort", choices=("high", "max"), required=True)
    prepare.add_argument("--usage-snapshot", type=Path, required=True)
    prepare.add_argument("--smoke-result-sha256", required=True)
    prepare.add_argument(
        "--replicate",
        action="append",
        nargs=5,
        metavar=("ID", "O1_ATOMIC", "O1_PREP", "O2_ATOMIC", "O2_PREP"),
        required=True,
    )
    prepare.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot-usage":
            result = snapshot_usage(
                output_path=args.output,
                api_key_env=args.api_key_env,
                kimi_config_path=args.kimi_config,
            )
        else:
            replicates = [
                {
                    "orientation_1_atomic": Path(o1_atomic),
                    "orientation_1_preparation": Path(o1_preparation),
                    "orientation_2_atomic": Path(o2_atomic),
                    "orientation_2_preparation": Path(o2_preparation),
                    "replicate_id": replicate_id,
                }
                for replicate_id, o1_atomic, o1_preparation, o2_atomic, o2_preparation in args.replicate
            ]
            result = prepare_profile(
                replicates=replicates,
                source_commit=args.source_commit,
                reasoning_effort=args.reasoning_effort,
                usage_snapshot_path=args.usage_snapshot,
                smoke_result_sha256=args.smoke_result_sha256,
                output_path=args.output,
            )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "ATOMIC_PROFILE_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    displayed = {
        key: result[key] for key in ("schema_version", "status") if key in result
    }
    if "budget" in result:
        displayed["budget"] = result["budget"]
    print(json.dumps({"result": displayed, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
