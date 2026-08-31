from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

import httpx

from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail
from .operational_judge import (
    BUNDLE_SCHEMA_VERSION,
    DRAFT_SCHEMA_VERSION,
    EVALUATORS,
    SCORE_FIELDS,
    _prompt_text,
    _read_canonical_object,
)

API_URL = "https://api.deepseek.com/responses"
MODEL_ID = "deepseek-v4-flash"
MAX_OUTPUT_TOKENS = 131_072
REQUEST_SCHEMA_VERSION = "local-ranking-deepseek-responses-request-v1.0"
PREPARATION_SCHEMA_VERSION = "local-ranking-deepseek-responses-preparation-v1.0"
RECEIPT_SCHEMA_VERSION = "local-ranking-deepseek-responses-receipt-v1.0"
SAFE_RESPONSE_HEADERS = {"cf-ray", "date", "request-id", "server", "x-request-id"}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _score_schema() -> dict[str, Any]:
    return {
        "additionalProperties": False,
        "properties": {
            field: {"maximum": 2, "minimum": 0, "type": "integer"}
            for field in sorted(SCORE_FIELDS)
        },
        "required": sorted(SCORE_FIELDS),
        "type": "object",
    }


def draft_json_schema(bundle: dict[str, Any]) -> dict[str, Any]:
    items = bundle.get("items")
    evaluator = bundle.get("evaluator")
    if not isinstance(items, list) or not items or not isinstance(evaluator, dict):
        fail("INVALID_JUDGE_BUNDLE", "DeepSeek bundle has no items or evaluator")
    raw_item_ids = [item.get("item_id") for item in items if isinstance(item, dict)]
    if len(raw_item_ids) != len(items) or any(
        not isinstance(item, str) for item in raw_item_ids
    ):
        fail("INVALID_JUDGE_BUNDLE", "DeepSeek bundle item identities are invalid")
    item_ids = sorted(raw_item_ids)
    evaluator_properties = {
        key: {"enum": [value], "type": "string"}
        for key, value in sorted(evaluator.items())
    }
    evidence_schema = {
        "additionalProperties": False,
        "properties": {
            "paper_id": {"minLength": 1, "type": "string"},
            "segment_id": {"minLength": 1, "type": "string"},
            "side": {"enum": ["left", "right"], "type": "string"},
            "support": {"maxLength": 500, "minLength": 20, "type": "string"},
        },
        "required": ["paper_id", "segment_id", "side", "support"],
        "type": "object",
    }
    judgment_schema = {
        "additionalProperties": False,
        "properties": {
            "catastrophic_omission_side": {
                "enum": ["left", "right", "neither"],
                "type": "string",
            },
            "evidence_refs": {
                "items": evidence_schema,
                "maxItems": 4,
                "minItems": 1,
                "type": "array",
            },
            "item_id": {"enum": item_ids, "type": "string"},
            "left_scores": _score_schema(),
            "rationale": {"maxLength": 800, "minLength": 1, "type": "string"},
            "right_scores": _score_schema(),
            "winner": {
                "enum": ["both_bad", "left", "right", "tie"],
                "type": "string",
            },
        },
        "required": [
            "catastrophic_omission_side",
            "evidence_refs",
            "item_id",
            "left_scores",
            "rationale",
            "right_scores",
            "winner",
        ],
        "type": "object",
    }
    return {
        "additionalProperties": False,
        "properties": {
            "attestation": {
                "additionalProperties": False,
                "properties": {
                    "bundle_only": {"enum": [True], "type": "boolean"},
                    "fresh_session": {"enum": [True], "type": "boolean"},
                    "no_external_sources": {"enum": [True], "type": "boolean"},
                    "tool_access": {"enum": ["disabled"], "type": "string"},
                },
                "required": [
                    "bundle_only",
                    "fresh_session",
                    "no_external_sources",
                    "tool_access",
                ],
                "type": "object",
            },
            "bundle_sha256": {
                "enum": [bundle.get("bundle_sha256")],
                "type": "string",
            },
            "evaluator": {
                "additionalProperties": False,
                "properties": evaluator_properties,
                "required": sorted(evaluator_properties),
                "type": "object",
            },
            "judgments": {
                "items": judgment_schema,
                "maxItems": len(item_ids),
                "minItems": len(item_ids),
                "type": "array",
            },
            "schema_version": {
                "enum": [DRAFT_SCHEMA_VERSION],
                "type": "string",
            },
        },
        "required": [
            "attestation",
            "bundle_sha256",
            "evaluator",
            "judgments",
            "schema_version",
        ],
        "type": "object",
    }


def prepare(
    *, bundle_path: Path, prompt_path: Path, output_root: Path
) -> dict[str, Any]:
    bundle, bundle_bytes = _read_canonical_object(bundle_path, label="DeepSeek bundle")
    if bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "DeepSeek bundle schema is unsupported")
    if bundle.get("evaluator") != EVALUATORS["judge-deepseek"]:
        fail("PROVENANCE_MISMATCH", "DeepSeek bundle uses the wrong transport profile")
    try:
        prompt_bytes = prompt_path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", "DeepSeek prompt is unreadable", error=str(exc))
    if prompt_bytes != _prompt_text(bundle).encode("utf-8"):
        fail("HASH_MISMATCH", "DeepSeek prompt does not match its exact bundle")

    schema = draft_json_schema(bundle)
    schema_bytes = canonical_json_bytes(schema)
    request = {
        "input": [
            {
                "content": [
                    {
                        "text": prompt_bytes.decode("utf-8"),
                        "type": "input_text",
                    }
                ],
                "role": "user",
            }
        ],
        "instructions": (
            "Follow the embedded blind evaluator contract exactly. Use only the supplied "
            "bundle and return the structured response."
        ),
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "model": MODEL_ID,
        "reasoning": {"effort": "high"},
        "stream": False,
        "text": {
            "format": {
                "name": "local_ranking_judgments_v1",
                "schema": schema,
                "type": "json_schema",
            }
        },
    }
    request_bytes = canonical_json_bytes(request)
    files = {
        "bundle.json": bundle_bytes,
        "prompt.txt": prompt_bytes,
        "request.json": request_bytes,
        "response-schema.json": schema_bytes,
    }
    manifest = {
        "endpoint": API_URL,
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "model": MODEL_ID,
        "reasoning_effort": "high",
        "request_schema_version": REQUEST_SCHEMA_VERSION,
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "status": "ready_for_authorized_call",
        "transport": "deepseek-official-responses-json-schema",
    }
    for name, data in files.items():
        write_once(output_root / name, data)
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
        value = config["providers"]["deepseek"]["api_key"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        fail("MISSING_CREDENTIAL", "DeepSeek credential is unavailable", error=str(exc))
    if not isinstance(value, str) or not value:
        fail("MISSING_CREDENTIAL", "DeepSeek credential is empty")
    return value


def _extract_output_text(response: Any) -> tuple[dict[str, Any], dict[str, int]]:
    if not isinstance(response, dict) or response.get("object") != "response":
        fail("INVALID_PROVIDER_RESPONSE", "DeepSeek response object is invalid")
    if (
        response.get("status") != "completed"
        or response.get("error") is not None
        or response.get("incomplete_details") is not None
        or response.get("model") != MODEL_ID
    ):
        fail(
            "PROVIDER_RESPONSE_FAILED",
            "DeepSeek response is not a completed target-model response",
        )
    output = response.get("output")
    if not isinstance(output, list):
        fail("INVALID_PROVIDER_RESPONSE", "DeepSeek response output is missing")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") not in {
            "reasoning",
            "message",
        }:
            fail(
                "INVALID_PROVIDER_RESPONSE",
                "DeepSeek response contains a forbidden output item",
            )
        if item.get("status") != "completed":
            fail("PROVIDER_RESPONSE_FAILED", "DeepSeek output item is incomplete")
        if item["type"] == "reasoning":
            continue
        if item.get("role") != "assistant" or not isinstance(item.get("content"), list):
            fail("INVALID_PROVIDER_RESPONSE", "DeepSeek assistant message is invalid")
        for content in item["content"]:
            if not isinstance(content, dict) or content.get("type") != "output_text":
                fail(
                    "INVALID_PROVIDER_RESPONSE",
                    "DeepSeek message contains non-text output",
                )
            text = content.get("text")
            if not isinstance(text, str) or not text:
                fail("INVALID_PROVIDER_RESPONSE", "DeepSeek output text is empty")
            texts.append(text)
    if len(texts) != 1:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "DeepSeek response must contain exactly one output text",
        )
    try:
        draft = json.loads(texts[0])
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "DeepSeek output text is not JSON",
            error=str(exc),
        )
    if not isinstance(draft, dict):
        fail("INVALID_PROVIDER_RESPONSE", "DeepSeek output JSON must be an object")
    usage = response.get("usage")
    if not isinstance(usage, dict):
        fail("INVALID_PROVIDER_RESPONSE", "DeepSeek response usage is missing")
    values: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            fail("INVALID_PROVIDER_RESPONSE", f"DeepSeek usage.{key} is invalid")
        values[key] = value
    details = usage.get("input_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, dict) else None
    if (
        isinstance(cached, bool)
        or not isinstance(cached, int)
        or not 0 <= cached <= values["input_tokens"]
    ):
        fail("INVALID_PROVIDER_RESPONSE", "DeepSeek cached token usage is invalid")
    if values["total_tokens"] != values["input_tokens"] + values["output_tokens"]:
        fail("INVALID_PROVIDER_RESPONSE", "DeepSeek total token usage is inconsistent")
    values["cached_tokens"] = cached
    return draft, values


def execute(
    *,
    preparation_root: Path,
    output_root: Path,
    api_key_env: str,
    kimi_config_path: Path | None,
) -> dict[str, Any]:
    manifest, manifest_bytes = _read_canonical_object(
        preparation_root / "manifest.json", label="DeepSeek preparation manifest"
    )
    request, request_bytes = _read_canonical_object(
        preparation_root / "request.json", label="DeepSeek request"
    )
    if (
        manifest.get("schema_version") != PREPARATION_SCHEMA_VERSION
        or manifest.get("status") != "ready_for_authorized_call"
        or manifest.get("files", {}).get("request.json") != sha256_bytes(request_bytes)
        or request.get("model") != MODEL_ID
        or request.get("max_output_tokens") != MAX_OUTPUT_TOKENS
    ):
        fail("INVALID_ARTIFACT", "DeepSeek preparation is incompatible")
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
        write_once(output_root / "finished-at.txt", (_utc_now() + "\n").encode())
        write_once(
            output_root / "transport-error.json",
            canonical_json_bytes({"error_type": type(exc).__name__}),
        )
        fail(
            "DEEPSEEK_TRANSPORT_FAILED",
            "DeepSeek request failed",
            error=type(exc).__name__,
        )
    finished_at = _utc_now()
    raw_body = response.content
    safe_headers = {
        key.lower(): value
        for key, value in response.headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }
    write_once(output_root / "finished-at.txt", (finished_at + "\n").encode())
    write_once(output_root / "raw-response.json", raw_body)
    write_once(
        output_root / "response-headers.json", canonical_json_bytes(safe_headers)
    )
    write_once(output_root / "http-status.txt", f"{response.status_code}\n".encode())
    try:
        provider_response = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "DeepSeek HTTP body is not JSON",
            error=str(exc),
        )
    if response.status_code != 200:
        fail(
            "DEEPSEEK_HTTP_FAILED",
            "DeepSeek returned a non-success HTTP status",
            status_code=response.status_code,
        )
    draft, usage = _extract_output_text(provider_response)
    draft_bytes = canonical_json_bytes(draft)
    write_once(output_root / "response.json", draft_bytes)
    files = {
        "finished-at.txt": (finished_at + "\n").encode(),
        "http-status.txt": f"{response.status_code}\n".encode(),
        "raw-response.json": raw_body,
        "response-headers.json": canonical_json_bytes(safe_headers),
        "response.json": draft_bytes,
        "started-at.txt": (started_at + "\n").encode(),
    }
    receipt = {
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "http_status": response.status_code,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "model": provider_response.get("model"),
        "provider_response_id": provider_response.get("id"),
        "request_sha256": sha256_bytes(request_bytes),
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "pass",
        "usage": usage,
    }
    write_once(output_root / "receipt.json", canonical_json_bytes(receipt))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or run DeepSeek Responses judges"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--bundle", type=Path, required=True)
    prepare_parser.add_argument("--prompt", type=Path, required=True)
    prepare_parser.add_argument("--output-root", type=Path, required=True)
    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--preparation-root", type=Path, required=True)
    execute_parser.add_argument("--output-root", type=Path, required=True)
    execute_parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
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
            else {"code": "DEEPSEEK_RESPONSES_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
