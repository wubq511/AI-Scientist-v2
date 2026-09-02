from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from .canonical import canonical_json_bytes, sha256_bytes, write_once
from .errors import HarnessError, fail
from .opencode_go_chat import (
    API_URL,
    MAX_TOKENS,
    MODEL_ID,
    SAFE_RESPONSE_HEADERS,
    _api_key,
    _read_canonical_object,
    _read_utf8,
    _usage,
    _utc_now,
)
from .operational_judge import BUNDLE_SCHEMA_VERSION, EVALUATORS

LEGACY_PREPARATION_SCHEMA_VERSION = "local-ranking-opencode-go-stream-preparation-v1.0"
PREPARATION_SCHEMA_VERSION = "local-ranking-opencode-go-stream-preparation-v1.1"
RECEIPT_SCHEMA_VERSION = "local-ranking-opencode-go-chat-stream-receipt-v1.0"
ALLOWED_DEEPSEEK_PROFILES = {
    ("opencode-go/deepseek-v4-flash", "high"): "deepseek-v4-flash",
    ("opencode-go/deepseek-v4-flash", "max"): "deepseek-v4-flash",
    ("opencode-go/deepseek-v4-pro", "high"): "deepseek-v4-pro",
    ("opencode-go/deepseek-v4-pro", "max"): "deepseek-v4-pro",
}
ALLOWED_WIRE_PROFILES = {
    (model, effort)
    for (model_alias, effort), model in ALLOWED_DEEPSEEK_PROFILES.items()
}


def _deepseek_profile(bundle: dict[str, Any]) -> tuple[str, str]:
    evaluator = bundle.get("evaluator")
    expected = EVALUATORS["judge-deepseek"]
    if not isinstance(evaluator, dict) or set(evaluator) != set(expected):
        fail("INVALID_ARTIFACT", "Judge bundle evaluator is invalid")
    model_alias = evaluator.get("model_alias")
    reasoning_effort = evaluator.get("reasoning_effort")
    if (
        evaluator.get("harness") != expected["harness"]
        or evaluator.get("provider") != expected["provider"]
        or (model_alias, reasoning_effort) not in ALLOWED_DEEPSEEK_PROFILES
    ):
        fail(
            "INVALID_ARTIFACT",
            "Judge bundle is not an approved OpenCode Go DeepSeek profile",
        )
    return ALLOWED_DEEPSEEK_PROFILES[(model_alias, reasoning_effort)], reasoning_effort


def prepare(
    *, bundle_path: Path, prompt_path: Path, output_root: Path
) -> dict[str, Any]:
    bundle, bundle_bytes = _read_canonical_object(bundle_path, label="judge bundle")
    prompt, prompt_bytes = _read_utf8(prompt_path, label="judge prompt")
    if bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        fail(
            "INVALID_ARTIFACT",
            "Judge bundle is not the frozen OpenCode Go DeepSeek schema",
        )
    model, reasoning_effort = _deepseek_profile(bundle)
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
        "model": model,
        "reasoning_effort": reasoning_effort,
        "response_format": {"type": "json_object"},
        "stream": True,
    }
    request_bytes = canonical_json_bytes(request)
    manifest = {
        "bundle_sha256": sha256_bytes(bundle_bytes),
        "endpoint": API_URL,
        "files": {
            "prompt.txt": sha256_bytes(prompt_bytes),
            "request.json": sha256_bytes(request_bytes),
        },
        "model": model,
        "provider": "opencode-go",
        "reasoning_effort": reasoning_effort,
        "schema_version": PREPARATION_SCHEMA_VERSION,
        "status": "ready_for_synthetic_or_spent_stream_qualification",
        "transport": "opencode-go-chat-completions-json-object-sse-candidate",
    }
    write_once(output_root / "prompt.txt", prompt_bytes)
    write_once(output_root / "request.json", request_bytes)
    write_once(output_root / "manifest.json", canonical_json_bytes(manifest))
    return manifest


def _sse_data_events(raw_stream: bytes) -> tuple[list[str], int]:
    try:
        text = raw_stream.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_SSE", "OpenCode Go stream is not UTF-8", offset=exc.start)
    events: list[str] = []
    data_lines: list[str] = []
    keepalive_count = 0

    def dispatch() -> None:
        if data_lines:
            events.append("\n".join(data_lines))
            data_lines.clear()

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line == "":
            dispatch()
        elif line.startswith(":"):
            keepalive_count += 1
        elif line == "data" or line.startswith("data:"):
            value = line[5:] if line.startswith("data:") else ""
            data_lines.append(value[1:] if value.startswith(" ") else value)
        else:
            fail("INVALID_SSE", "OpenCode Go stream contains a non-data SSE field")
    dispatch()
    if not events:
        fail("STREAM_INCOMPLETE", "OpenCode Go stream contains no data events")
    return events, keepalive_count


def _validated_cost(value: Any) -> str | None:
    if value is None:
        return None
    try:
        parsed = Decimal(value) if isinstance(value, str) else Decimal("NaN")
    except InvalidOperation:
        parsed = Decimal("NaN")
    if not parsed.is_finite() or parsed < 0:
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go stream cost is invalid")
    return value


def _merge_usage(
    current: dict[str, int] | None, incoming: dict[str, int]
) -> dict[str, int]:
    if current is None:
        return incoming
    if (
        current["prompt_tokens"] != incoming["prompt_tokens"]
        or incoming["completion_tokens"] < current["completion_tokens"]
        or incoming["total_tokens"] < current["total_tokens"]
    ):
        fail("INVALID_PROVIDER_RESPONSE", "Cumulative stream usage regressed")
    merged = dict(incoming)
    core_keys = {"completion_tokens", "prompt_tokens", "total_tokens"}
    for key, value in current.items():
        if key in core_keys:
            continue
        if key in incoming and incoming[key] != value:
            fail(
                "INVALID_PROVIDER_RESPONSE",
                "Stream usage detail changed between chunks",
            )
        merged.setdefault(key, value)
    return merged


def _extract_stream_response(
    raw_stream: bytes,
    *,
    expected_model: str = MODEL_ID,
) -> tuple[
    dict[str, Any],
    dict[str, int] | None,
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
]:
    events, keepalive_count = _sse_data_events(raw_stream)
    chunks: list[dict[str, Any]] = []
    content_parts: list[str] = []
    response_id: str | None = None
    created_first: int | None = None
    created_last: int | None = None
    usage: dict[str, int] | None = None
    cost: str | None = None
    terminal_count = 0
    done_received = False
    post_done_cost_received = False

    for event_index, event in enumerate(events):
        if event == "[DONE]":
            if done_received:
                fail("INVALID_SSE", "[DONE] must be a unique SSE data event")
            done_received = True
            continue
        try:
            chunk = json.loads(event)
        except json.JSONDecodeError as exc:
            fail(
                "INVALID_SSE",
                "OpenCode Go SSE data is not JSON",
                event_index=event_index,
                line=exc.lineno,
                column=exc.colno,
            )
        if (
            not done_received
            and isinstance(chunk, dict)
            and set(chunk) == {"choices", "cost"}
            and chunk.get("choices") == []
        ):
            fail(
                "STREAM_INCOMPLETE",
                "OpenCode Go billing sidecar arrived before [DONE]",
            )
        if done_received:
            if (
                event_index != len(events) - 1
                or post_done_cost_received
                or not isinstance(chunk, dict)
                or set(chunk) != {"choices", "cost"}
                or chunk.get("choices") != []
            ):
                fail(
                    "INVALID_SSE",
                    "Only one final billing sidecar may follow [DONE]",
                )
            cost = _validated_cost(chunk.get("cost"))
            post_done_cost_received = True
            chunks.append(chunk)
            continue
        if (
            not isinstance(chunk, dict)
            or chunk.get("object") != "chat.completion.chunk"
        ):
            fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go stream chunk is invalid")
        chunks.append(chunk)
        choices = chunk.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            fail("INVALID_PROVIDER_RESPONSE", "Stream chunk choices are invalid")
        chunk_id = chunk.get("id")
        chunk_model = chunk.get("model")
        chunk_created = chunk.get("created")
        if choices:
            if (
                not isinstance(chunk_id, str)
                or not chunk_id
                or chunk_model != expected_model
                or isinstance(chunk_created, bool)
                or not isinstance(chunk_created, int)
                or chunk_created < 0
            ):
                fail(
                    "PROVIDER_IDENTITY_MISMATCH",
                    "Content stream chunk identity is invalid",
                )
            if response_id is None:
                response_id = chunk_id
                created_first = chunk_created
                created_last = chunk_created
            elif (
                response_id != chunk_id
                or created_last is None
                or chunk_created < created_last
            ):
                fail(
                    "PROVIDER_IDENTITY_MISMATCH",
                    "Stream chunk response identity changed",
                )
            else:
                created_last = chunk_created
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("index") != 0:
                fail("INVALID_PROVIDER_RESPONSE", "Stream choice is invalid")
            finish_reason = choice.get("finish_reason")
            if finish_reason not in {None, "stop"}:
                fail(
                    "PROVIDER_RESPONSE_FAILED",
                    "OpenCode Go stream did not finish normally",
                    finish_reason=finish_reason,
                )
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                fail("INVALID_PROVIDER_RESPONSE", "Stream delta is invalid")
            if delta.get("role") not in {None, "assistant"}:
                fail("INVALID_PROVIDER_RESPONSE", "Stream delta role is invalid")
            if delta.get("refusal") not in {None, ""} or delta.get(
                "tool_calls"
            ) not in (
                None,
                [],
            ):
                fail("PROVIDER_RESPONSE_FAILED", "Stream returned refusal or tools")
            content = delta.get("content")
            if content is not None and not isinstance(content, str):
                fail("INVALID_PROVIDER_RESPONSE", "Stream content delta is invalid")
            reasoning_content = delta.get("reasoning_content")
            if reasoning_content is not None and not isinstance(reasoning_content, str):
                fail("INVALID_PROVIDER_RESPONSE", "Stream reasoning delta is invalid")
            if terminal_count and content:
                fail(
                    "INVALID_PROVIDER_RESPONSE",
                    "Content continued after terminal chunk",
                )
            if content:
                content_parts.append(content)
            if finish_reason == "stop":
                terminal_count += 1
        elif chunk.get("usage") is None and chunk.get("cost") is None:
            fail(
                "INVALID_PROVIDER_RESPONSE",
                "Empty-choice stream chunk has no usage or cost evidence",
            )
        if chunk.get("usage") is not None:
            parsed_usage = _usage(chunk)
            usage = _merge_usage(usage, parsed_usage)
        if chunk.get("cost") is not None:
            parsed_cost = _validated_cost(chunk.get("cost"))
            if cost is not None and cost != parsed_cost:
                fail("INVALID_PROVIDER_RESPONSE", "Stream cost changed between chunks")
            cost = parsed_cost

    if not done_received or terminal_count != 1:
        fail(
            "STREAM_INCOMPLETE",
            "OpenCode Go stream lacks one normal terminal chunk and [DONE]",
            done_received=done_received,
            terminal_count=terminal_count,
        )
    if response_id is None or created_first is None or created_last is None:
        fail("PROVIDER_IDENTITY_MISMATCH", "OpenCode Go stream has no identity")
    content_text = "".join(content_parts)
    if not content_text:
        fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go stream content is empty")
    try:
        draft = json.loads(content_text)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_PROVIDER_RESPONSE",
            "OpenCode Go stream content is not JSON",
            line=exc.lineno,
            column=exc.colno,
        )
    if not isinstance(draft, dict):
        fail("INVALID_PROVIDER_RESPONSE", "Stream output JSON must be an object")
    identity = {
        "cost": cost,
        "created_first": created_first,
        "created_last": created_last,
        "finish_reason": "stop",
        "model": expected_model,
        "provider_response_id": response_id,
    }
    diagnostics = {
        "content_bytes": len(content_text.encode("utf-8")),
        "data_event_count": len(events),
        "done_received": done_received,
        "keepalive_count": keepalive_count,
        "post_done_cost_received": post_done_cost_received,
    }
    return draft, usage, identity, chunks, diagnostics


def _extract_stream_tool_response(
    raw_stream: bytes,
    *,
    expected_model: str,
    tool_name: str,
) -> tuple[
    dict[str, Any],
    dict[str, int] | None,
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
]:
    events, keepalive_count = _sse_data_events(raw_stream)
    chunks: list[dict[str, Any]] = []
    content_parts: list[str] = []
    reasoning_bytes = 0
    response_id: str | None = None
    created_first: int | None = None
    created_last: int | None = None
    usage: dict[str, int] | None = None
    cost: str | None = None
    terminal_count = 0
    terminal_reason: str | None = None
    done_received = False
    post_done_cost_received = False
    tool_call_seen = False
    tool_call_id: str | None = None
    tool_name_parts: list[str] = []
    argument_parts: list[str] = []

    for event_index, event in enumerate(events):
        if event == "[DONE]":
            if done_received:
                fail("INVALID_SSE", "[DONE] must be a unique SSE data event")
            done_received = True
            continue
        try:
            chunk = json.loads(event)
        except json.JSONDecodeError as exc:
            fail(
                "INVALID_SSE",
                "OpenCode Go SSE data is not JSON",
                event_index=event_index,
                line=exc.lineno,
                column=exc.colno,
            )
        if (
            not done_received
            and isinstance(chunk, dict)
            and set(chunk) == {"choices", "cost"}
            and chunk.get("choices") == []
        ):
            fail(
                "STREAM_INCOMPLETE",
                "OpenCode Go billing sidecar arrived before [DONE]",
            )
        if done_received:
            if (
                event_index != len(events) - 1
                or post_done_cost_received
                or not isinstance(chunk, dict)
                or set(chunk) != {"choices", "cost"}
                or chunk.get("choices") != []
            ):
                fail(
                    "INVALID_SSE",
                    "Only one final billing sidecar may follow [DONE]",
                )
            cost = _validated_cost(chunk.get("cost"))
            post_done_cost_received = True
            chunks.append(chunk)
            continue
        if (
            not isinstance(chunk, dict)
            or chunk.get("object") != "chat.completion.chunk"
        ):
            fail("INVALID_PROVIDER_RESPONSE", "OpenCode Go stream chunk is invalid")
        chunks.append(chunk)
        choices = chunk.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            fail("INVALID_PROVIDER_RESPONSE", "Stream chunk choices are invalid")
        chunk_id = chunk.get("id")
        chunk_model = chunk.get("model")
        chunk_created = chunk.get("created")
        if choices:
            if (
                not isinstance(chunk_id, str)
                or not chunk_id
                or chunk_model != expected_model
                or isinstance(chunk_created, bool)
                or not isinstance(chunk_created, int)
                or chunk_created < 0
            ):
                fail(
                    "PROVIDER_IDENTITY_MISMATCH",
                    "Content stream chunk identity is invalid",
                )
            if response_id is None:
                response_id = chunk_id
                created_first = chunk_created
                created_last = chunk_created
            elif (
                response_id != chunk_id
                or created_last is None
                or chunk_created < created_last
            ):
                fail(
                    "PROVIDER_IDENTITY_MISMATCH",
                    "Stream chunk response identity changed",
                )
            else:
                created_last = chunk_created
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("index") != 0:
                fail("INVALID_PROVIDER_RESPONSE", "Stream choice is invalid")
            finish_reason = choice.get("finish_reason")
            if finish_reason not in {None, "stop", "tool_calls"}:
                fail(
                    "PROVIDER_RESPONSE_FAILED",
                    "OpenCode Go tool stream did not finish normally",
                    finish_reason=finish_reason,
                )
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                fail("INVALID_PROVIDER_RESPONSE", "Stream delta is invalid")
            if delta.get("role") not in {None, "assistant"}:
                fail("INVALID_PROVIDER_RESPONSE", "Stream delta role is invalid")
            if delta.get("refusal") not in {None, ""}:
                fail("PROVIDER_RESPONSE_FAILED", "Stream returned a refusal")
            content = delta.get("content")
            if content is not None and not isinstance(content, str):
                fail("INVALID_PROVIDER_RESPONSE", "Stream content delta is invalid")
            reasoning_content = delta.get("reasoning_content")
            if reasoning_content is not None and not isinstance(reasoning_content, str):
                fail("INVALID_PROVIDER_RESPONSE", "Stream reasoning delta is invalid")
            raw_tool_calls = delta.get("tool_calls")
            if raw_tool_calls is not None:
                if not isinstance(raw_tool_calls, list):
                    fail("INVALID_TOOL_CALL", "Stream tool-call delta is invalid")
                for entry in raw_tool_calls:
                    if not isinstance(entry, dict):
                        fail("INVALID_TOOL_CALL", "Stream tool-call entry is invalid")
                    index = entry.get("index")
                    if (
                        isinstance(index, bool)
                        or not isinstance(index, int)
                        or index != 0
                    ):
                        fail(
                            "INVALID_TOOL_CALL",
                            "Only one index-0 tool call is accepted",
                        )
                    tool_call_seen = True
                    entry_id = entry.get("id")
                    if entry_id is not None:
                        if not isinstance(entry_id, str):
                            fail("INVALID_TOOL_CALL", "Tool-call ID is invalid")
                        if entry_id:
                            if tool_call_id is not None and tool_call_id != entry_id:
                                fail(
                                    "INVALID_TOOL_CALL",
                                    "Tool-call ID changed between fragments",
                                )
                            tool_call_id = entry_id
                    entry_type = entry.get("type")
                    if entry_type is not None and entry_type != "function":
                        fail("INVALID_TOOL_CALL", "Tool-call type is invalid")
                    function = entry.get("function")
                    if function is not None:
                        if not isinstance(function, dict):
                            fail("INVALID_TOOL_CALL", "Tool-call function is invalid")
                        name_part = function.get("name")
                        if name_part is not None:
                            if not isinstance(name_part, str):
                                fail("INVALID_TOOL_CALL", "Tool-call name is invalid")
                            tool_name_parts.append(name_part)
                        arguments_part = function.get("arguments")
                        if arguments_part is not None:
                            if not isinstance(arguments_part, str):
                                fail(
                                    "INVALID_TOOL_CALL",
                                    "Tool-call arguments fragment is invalid",
                                )
                            argument_parts.append(arguments_part)
            if terminal_count and (content or reasoning_content or raw_tool_calls):
                fail(
                    "INVALID_PROVIDER_RESPONSE",
                    "Stream output continued after the terminal chunk",
                )
            if content:
                content_parts.append(content)
            if reasoning_content:
                reasoning_bytes += len(reasoning_content.encode("utf-8"))
            if finish_reason in {"stop", "tool_calls"}:
                terminal_count += 1
                terminal_reason = finish_reason
        elif chunk.get("usage") is None and chunk.get("cost") is None:
            fail(
                "INVALID_PROVIDER_RESPONSE",
                "Empty-choice stream chunk has no usage or cost evidence",
            )
        if chunk.get("usage") is not None:
            parsed_usage = _usage(chunk)
            usage = _merge_usage(usage, parsed_usage)
        if chunk.get("cost") is not None:
            parsed_cost = _validated_cost(chunk.get("cost"))
            if cost is not None and cost != parsed_cost:
                fail("INVALID_PROVIDER_RESPONSE", "Stream cost changed between chunks")
            cost = parsed_cost

    if not done_received or terminal_count != 1:
        fail(
            "STREAM_INCOMPLETE",
            "OpenCode Go stream lacks one normal terminal chunk and [DONE]",
            done_received=done_received,
            terminal_count=terminal_count,
        )
    if response_id is None or created_first is None or created_last is None:
        fail("PROVIDER_IDENTITY_MISMATCH", "OpenCode Go stream has no identity")
    if not tool_call_seen or tool_call_id is None:
        fail("INVALID_TOOL_CALL", "OpenCode Go stream returned no tool call")
    joined_name = "".join(tool_name_parts)
    if joined_name != tool_name:
        fail(
            "INVALID_TOOL_CALL",
            "OpenCode Go stream returned a wrong tool call",
            expected=tool_name,
            actual=joined_name,
        )
    arguments_text = "".join(argument_parts)
    if not arguments_text:
        fail("INVALID_TOOL_CALL", "Tool call arguments are missing")
    try:
        arguments = json.loads(arguments_text)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_TOOL_CALL",
            "Tool call arguments are not valid JSON",
            line=exc.lineno,
            column=exc.colno,
        )
    if not isinstance(arguments, dict):
        fail("INVALID_TOOL_CALL", "Tool call arguments must be one JSON object")
    content_text = "".join(content_parts)
    identity = {
        "cost": cost,
        "created_first": created_first,
        "created_last": created_last,
        "finish_reason": terminal_reason,
        "model": expected_model,
        "provider_response_id": response_id,
        "tool_call_id": tool_call_id,
    }
    diagnostics = {
        "arguments_bytes": len(arguments_text.encode("utf-8")),
        "content_bytes": len(content_text.encode("utf-8")),
        "data_event_count": len(events),
        "done_received": done_received,
        "keepalive_count": keepalive_count,
        "post_done_cost_received": post_done_cost_received,
        "reasoning_bytes": reasoning_bytes,
    }
    return arguments, usage, identity, chunks, diagnostics


def _validate_preparation(
    *, preparation_root: Path
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, str, bytes]:
    manifest, manifest_bytes = _read_canonical_object(
        preparation_root / "manifest.json", label="stream preparation manifest"
    )
    request, request_bytes = _read_canonical_object(
        preparation_root / "request.json", label="stream request"
    )
    prompt, prompt_bytes = _read_utf8(
        preparation_root / "prompt.txt", label="stream prompt"
    )
    schema_version = manifest.get("schema_version")
    request_model = request.get("model")
    request_effort = request.get("reasoning_effort")
    legacy_high_profile = (
        schema_version == LEGACY_PREPARATION_SCHEMA_VERSION
        and "reasoning_effort" not in manifest
        and request_model == MODEL_ID
        and request_effort == "high"
    )
    profile_aware_manifest = (
        schema_version == PREPARATION_SCHEMA_VERSION
        and manifest.get("model") == request_model
        and manifest.get("reasoning_effort") == request_effort
        and (request_model, request_effort) in ALLOWED_WIRE_PROFILES
    )
    if (
        not (legacy_high_profile or profile_aware_manifest)
        or manifest.get("status") != "ready_for_synthetic_or_spent_stream_qualification"
        or manifest.get("endpoint") != API_URL
        or manifest.get("model") != request_model
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
        or (request_model, request_effort) not in ALLOWED_WIRE_PROFILES
        or request.get("max_tokens") != MAX_TOKENS
        or request.get("response_format") != {"type": "json_object"}
        or request.get("stream") is not True
    ):
        fail("INVALID_ARTIFACT", "OpenCode Go stream preparation is incompatible")
    return manifest, manifest_bytes, request, request_bytes, prompt, prompt_bytes


def execute(
    *,
    preparation_root: Path,
    output_root: Path,
    api_key_env: str,
    kimi_config_path: Path | None,
) -> dict[str, Any]:
    manifest, manifest_bytes, request, request_bytes, _, _ = _validate_preparation(
        preparation_root=preparation_root
    )
    key = _api_key(env_name=api_key_env, kimi_config_path=kimi_config_path)
    started_at = _utc_now()
    started_bytes = (started_at + "\n").encode()
    write_once(output_root / "started-at.txt", started_bytes)
    raw_parts: list[bytes] = []
    status_code: int | None = None
    safe_headers: dict[str, str] = {}
    transport_error: str | None = None
    try:
        with httpx.Client(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
            with client.stream(
                "POST",
                API_URL,
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
                for part in response.iter_bytes():
                    raw_parts.append(part)
    except httpx.HTTPError as exc:
        transport_error = type(exc).__name__

    finished_at = _utc_now()
    finished_bytes = (finished_at + "\n").encode()
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
        fail(
            "OPENCODE_GO_STREAM_TRANSPORT_FAILED",
            "OpenCode Go stream request failed",
            error=transport_error,
        )
    if status_code != 200:
        fail(
            "OPENCODE_GO_STREAM_HTTP_FAILED",
            "OpenCode Go stream returned a non-success HTTP status",
            status_code=status_code,
        )
    if "text/event-stream" not in safe_headers.get("content-type", ""):
        fail(
            "INVALID_SSE",
            "OpenCode Go stream response is not text/event-stream",
        )
    try:
        draft, usage, identity, chunks, diagnostics = _extract_stream_response(
            raw_stream,
            expected_model=request["model"],
        )
    except HarnessError as exc:
        write_once(
            output_root / "stream-validation-error.json",
            canonical_json_bytes(exc.as_dict()),
        )
        raise
    draft_bytes = canonical_json_bytes(draft)
    chunk_bytes = b"".join(canonical_json_bytes(chunk) for chunk in chunks)
    write_once(output_root / "chunks.jsonl", chunk_bytes)
    write_once(output_root / "response.json", draft_bytes)
    files = {
        "chunks.jsonl": chunk_bytes,
        "finished-at.txt": finished_bytes,
        "http-status.txt": status_bytes,
        "response-headers.json": header_bytes,
        "response.json": draft_bytes,
        "started-at.txt": started_bytes,
        "stream-body.sse": raw_stream,
    }
    receipt = {
        "diagnostics": diagnostics,
        "endpoint": API_URL,
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "http_status": status_code,
        "identity": identity,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "provider": "opencode-go",
        "request_sha256": sha256_bytes(request_bytes),
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "pass",
        "transport_qualification": {
            "json_object_accepted": True,
            "reasoning_effort_requested": request["reasoning_effort"],
            "reasoning_execution_proven": False,
            "stream_completed": True,
            "streaming_requested": True,
        },
        "usage": usage,
    }
    write_once(output_root / "receipt.json", canonical_json_bytes(receipt))
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or run OpenCode Go streaming Chat judges"
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
            else {"code": "OPENCODE_GO_STREAM_FAILED", "message": str(exc)}
        )
        print(json.dumps({"error": error, "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
