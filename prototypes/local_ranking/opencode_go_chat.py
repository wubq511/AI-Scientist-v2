from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail
from .operational_judge import BUNDLE_SCHEMA_VERSION, EVALUATORS

API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL_ID = "deepseek-v4-flash"
MAX_TOKENS = 32768
PREPARATION_SCHEMA_VERSION = "local-ranking-opencode-go-chat-preparation-v1.0"
RECEIPT_SCHEMA_VERSION = "local-ranking-opencode-go-chat-receipt-v1.0"
SAFE_RESPONSE_HEADERS = {"cache-control", "content-type", "retry-after"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_canonical_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_ARTIFACT", f"{label} is unreadable JSON", error=str(exc))
    if not isinstance(value, dict):
        fail("INVALID_ARTIFACT", f"{label} must be an object")
    if canonical_json_bytes(value) != data:
        fail("NON_CANONICAL_INPUT", f"{label} must use canonical JSON bytes")
    return value, data


def _read_utf8(path: Path, *, label: str) -> tuple[str, bytes]:
    try:
        data = path.read_bytes()
        value = data.decode("utf-8")
    except OSError as exc:
        fail("MISSING_ARTIFACT", f"{label} is unreadable", error=str(exc))
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", f"{label} is not UTF-8", offset=exc.start)
    if not value:
        fail("INVALID_ARTIFACT", f"{label} is empty")
    return value, data


def prepare(
    *, bundle_path: Path, prompt_path: Path, output_root: Path
) -> dict[str, Any]:
    bundle, bundle_bytes = _read_canonical_object(bundle_path, label="judge bundle")
    prompt, prompt_bytes = _read_utf8(prompt_path, label="judge prompt")
    expected_evaluator = EVALUATORS["judge-deepseek"]
    if (
        bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION
        or bundle.get("evaluator") != expected_evaluator
    ):
        fail(
            "INVALID_ARTIFACT",
            "Judge bundle is not the frozen OpenCode Go DeepSeek profile",
        )
    expected_bundle_hash = bundle.get("bundle_sha256")
    without_hash = {
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    }
    if expected_bundle_hash != sha256_bytes(canonical_json_bytes(without_hash)):
        fail("HASH_MISMATCH", "Judge bundle self-hash is invalid")
    embedded_bundle = canonical_json_bytes(bundle).decode("utf-8")
    if prompt.count(embedded_bundle) != 1:
        fail(
            "PROMPT_BINDING_FAILED",
            "Judge prompt must embed the exact canonical bundle once",
        )

    request = {
        "max_tokens": MAX_TOKENS,
        "messages": [{"content": prompt, "role": "user"}],
        "model": MODEL_ID,
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    request_bytes = canonical_json_bytes(request)
    manifest = {
        "bundle_sha256": sha256_bytes(bundle_bytes),
        "endpoint": API_URL,
        "files": {
            "prompt.txt": sha256_bytes(prompt_bytes),
            "request.json": sha256_bytes(request_bytes),
        },
        "model": MODEL_ID,
        "provider": "opencode-go",
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "status": "ready_for_spent_or_synthetic_qualification",
        "transport": "opencode-go-chat-completions-json-object-candidate",
    }
    write_once(output_root / "prompt.txt", prompt_bytes)
    write_once(output_root / "request.json", request_bytes)
    write_once(output_root / "manifest.json", canonical_json_bytes(manifest))
    return manifest


def _api_key(*, env_name: str, kimi_config_path: Path | None) -> str:
    value = os.environ.get(env_name)
    if value:
        return value
    if kimi_config_path is None:
        fail("MISSING_CREDENTIAL", f"{env_name} is unset")
    try:
        config = tomllib.loads(kimi_config_path.read_text(encoding="utf-8"))
        value = config["providers"]["opencode-go"]["api_key"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        fail(
            "MISSING_CREDENTIAL",
            "OpenCode Go credential is unavailable",
            error=type(exc).__name__,
        )
    if not isinstance(value, str) or not value:
        fail("MISSING_CREDENTIAL", "OpenCode Go credential is empty")
    return value


def _usage(response: dict[str, Any]) -> dict[str, int]:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go response usage is missing")
    values: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            fail(
                "INVALID_PROVIDER_RESPONSE",
                f"OpenCode Go usage.{key} is invalid",
            )
        values[key] = value
    if values["total_tokens"] != values["prompt_tokens"] + values["completion_tokens"]:
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go token usage is inconsistent")
    for detail_key, total_key, output_key in (
        ("prompt_tokens_details", "prompt_tokens", "cached_tokens"),
        ("completion_tokens_details", "completion_tokens", "reasoning_tokens"),
    ):
        details = usage.get(detail_key)
        if details is None:
            continue
        if not isinstance(details, dict):
            fail(
                "INVALID_PROVIDER_RESPONSE",
                f"OpenCode Go usage.{detail_key} is invalid",
            )
        detail_value = details.get(output_key)
        if detail_value is None:
            continue
        if (
            isinstance(detail_value, bool)
            or not isinstance(detail_value, int)
            or not 0 <= detail_value <= values[total_key]
        ):
            fail(
                "INVALID_PROVIDER_RESPONSE",
                f"OpenCode Go usage.{detail_key}.{output_key} is invalid",
            )
        values[output_key] = detail_value
    return values


def _extract_chat_response(
    response: Any,
) -> tuple[dict[str, Any], dict[str, int], dict[str, Any]]:
    if not isinstance(response, dict) or response.get("object") != "chat.completion":
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go response object is invalid")
    if response.get("model") != MODEL_ID:
        fail("PROVIDER_IDENTITY_MISMATCH", "OpenCode Go returned another model")
    response_id = response.get("id")
    created = response.get("created")
    if (
        not isinstance(response_id, str)
        or not response_id
        or isinstance(created, bool)
        or not isinstance(created, int)
        or created < 0
    ):
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go response identity is invalid")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "OpenCode Go response must contain exactly one choice",
        )
    choice = choices[0]
    if (
        not isinstance(choice, dict)
        or choice.get("index") != 0
        or choice.get("finish_reason") != "stop"
    ):
        fail("PROVIDER_RESPONSE_FAILED", "OpenCode Go choice did not finish normally")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go assistant message is invalid")
    if message.get("refusal") not in {None, ""} or message.get("tool_calls") not in (
        None,
        [],
    ):
        fail("PROVIDER_RESPONSE_FAILED", "OpenCode Go returned refusal or tool calls")
    content = message.get("content")
    if not isinstance(content, str) or not content:
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go response content is empty")
    try:
        draft = json.loads(content)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "OpenCode Go response content is not JSON",
            line=exc.lineno,
            column=exc.colno,
        )
    if not isinstance(draft, dict):
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go output JSON must be an object")
    usage = _usage(response)
    cost = response.get("cost")
    if cost is not None:
        try:
            parsed_cost = Decimal(cost) if isinstance(cost, str) else Decimal("NaN")
            if not parsed_cost.is_finite() or parsed_cost < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go response cost is invalid")
    identity = {
        "cost": cost,
        "created": created,
        "model": response["model"],
        "provider_response_id": response_id,
    }
    return draft, usage, identity


def execute(
    *,
    preparation_root: Path,
    output_root: Path,
    api_key_env: str,
    kimi_config_path: Path | None,
) -> dict[str, Any]:
    manifest, manifest_bytes = _read_canonical_object(
        preparation_root / "manifest.json", label="OpenCode Go preparation manifest"
    )
    request, request_bytes = _read_canonical_object(
        preparation_root / "request.json", label="OpenCode Go request"
    )
    prompt, prompt_bytes = _read_utf8(
        preparation_root / "prompt.txt", label="OpenCode Go prompt"
    )
    if (
        manifest.get("schema_version") != PREPARATION_SCHEMA_VERSION
        or manifest.get("status") != "ready_for_spent_or_synthetic_qualification"
        or manifest.get("endpoint") != API_URL
        or manifest.get("model") != MODEL_ID
        or manifest.get("files", {}).get("request.json") != sha256_bytes(request_bytes)
        or manifest.get("files", {}).get("prompt.txt") != sha256_bytes(prompt_bytes)
        or set(request)
        != {
            "max_tokens",
            "messages",
            "model",
            "reasoning_effort",
            "response_format",
            "stream",
        }
        or request.get("messages") != [{"content": prompt, "role": "user"}]
        or request.get("model") != MODEL_ID
        or request.get("max_tokens") != MAX_TOKENS
        or request.get("reasoning_effort") != "high"
        or request.get("response_format") != {"type": "json_object"}
        or request.get("stream") is not False
    ):
        fail("INVALID_ARTIFACT", "OpenCode Go preparation is incompatible")
    key = _api_key(env_name=api_key_env, kimi_config_path=kimi_config_path)
    started_at = _utc_now()
    write_once(output_root / "started-at.txt", (started_at + "\n").encode())
    try:
        with httpx.Client(timeout=httpx.Timeout(660.0, connect=30.0)) as client:
            response = client.post(
                API_URL,
                content=request_bytes,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        finished_at = _utc_now()
        write_once(output_root / "finished-at.txt", (finished_at + "\n").encode())
        write_once(
            output_root / "transport-error.json",
            canonical_json_bytes({"error_type": type(exc).__name__}),
        )
        fail(
            "OPENCODE_GO_TRANSPORT_FAILED",
            "OpenCode Go request failed",
            error=type(exc).__name__,
        )
    finished_at = _utc_now()
    raw_body = response.content
    safe_headers = {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }
    status_bytes = f"{response.status_code}\n".encode()
    header_bytes = canonical_json_bytes(safe_headers)
    finished_bytes = (finished_at + "\n").encode()
    write_once(output_root / "finished-at.txt", finished_bytes)
    write_once(output_root / "http-status.txt", status_bytes)
    write_once(output_root / "raw-response.json", raw_body)
    write_once(output_root / "response-headers.json", header_bytes)
    try:
        provider_response = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "OpenCode Go HTTP body is not JSON",
            error=type(exc).__name__,
        )
    if response.status_code != 200:
        fail(
            "OPENCODE_GO_HTTP_FAILED",
            "OpenCode Go returned a non-success HTTP status",
            status_code=response.status_code,
        )
    draft, usage, identity = _extract_chat_response(provider_response)
    draft_bytes = canonical_json_bytes(draft)
    write_once(output_root / "response.json", draft_bytes)
    files = {
        "finished-at.txt": finished_bytes,
        "http-status.txt": status_bytes,
        "raw-response.json": raw_body,
        "response-headers.json": header_bytes,
        "response.json": draft_bytes,
        "started-at.txt": (started_at + "\n").encode(),
    }
    receipt = {
        "endpoint": API_URL,
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "http_status": response.status_code,
        "identity": identity,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "provider": "opencode-go",
        "request_sha256": sha256_bytes(request_bytes),
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "pass",
        "transport_qualification": {
            "json_object_accepted": True,
            "reasoning_effort_requested": "high",
            "reasoning_execution_proven": False,
        },
        "usage": usage,
    }
    write_once(output_root / "receipt.json", canonical_json_bytes(receipt))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or run OpenCode Go Chat Completions judges"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--bundle", type=Path, required=True)
    prepare_parser.add_argument("--prompt", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--preparation-root", type=Path, required=True)
    execute_parser.add_argument("--output-root", type=Path, required=True)
    execute_parser.add_argument("--api-key-env", default="OPENCODE_GO_API_KEY")
    execute_parser.add_argument("--kimi-config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(
                bundle_path=args.bundle,
                prompt_path=args.prompt,
                output_root=args.output_root,
            )
        else:
            result = execute(
                preparation_root=args.preparation_root,
                output_root=args.output_root,
                api_key_env=args.api_key_env,
                kimi_config_path=args.kimi_config,
            )
    except (HarnessError, OSError, ValueError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, HarnessError)
            else {"code": "OPENCODE_GO_CHAT_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
