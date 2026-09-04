"""DeepSeek-only adapter and model round execution (tickets 06, 022, 025, 031).

Enforces approved non-streaming Chat Completions boundary for DeepSeek direct
(deepseek-v4-pro), closed request parameter allowlist, provider-success and
usage invariant verification, closed 16-code failure taxonomy with table-lookup
disposition, bounded retry (<=2 attempts, transient only), centralized secret
redaction, Provider Attempt recording, and CNY cost accounting via versioned
price table.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re
import time
from typing import Any, Callable, Protocol, Sequence

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL_ID,
    DEFAULT_REASONING_EFFORT,
    MAX_ATTEMPTS_PER_OPERATION,
    _now,
)
from .errors import fail
from .pricing import CostBreakdown, PriceTable, attempt_cost
from .run_store import RunStore

DEEPSEEK_ADAPTER_SCHEMA_VERSION = "deepseek-adapter-v1.0.0"

ALLOWED_REASONING_EFFORTS = frozenset({"low", "high", "max"})

ALLOWED_OUTPUT_MODES = frozenset({"text", "json_object"})
DEFAULT_OUTPUT_MODE = "text"

ALLOWED_ROLES = frozenset({"system", "user", "assistant"})

CONNECT_TIMEOUT_SECONDS = 10.0
WALL_CLOCK_DEADLINE_SECONDS = 3600.0  # 60 minutes per attempt
MAX_RETRY_AFTER_SECONDS = 60.0

# Closed 16-code Failure Taxonomy (Ticket 022)
FAILURE_TAXONOMY: frozenset[str] = frozenset(
    {
        "configuration",
        "authentication",
        "insufficient_balance",
        "rate_limited",
        "provider_transient",
        "timeout_ambiguous",
        "transport_ambiguous",
        "model_mismatch",
        "truncated",
        "content_filtered",
        "resource_exhausted",
        "empty_content",
        "invalid_json",
        "unexpected_tool_call",
        "malformed_response",
        "unknown_provider_failure",
    }
)

# Closed 2-value Disposition Table (Ticket 025)
SUSPEND_FAILURES: frozenset[str] = frozenset(
    {
        "authentication",
        "insufficient_balance",
        "rate_limited",
        "provider_transient",
        "resource_exhausted",
        "timeout_ambiguous",
        "transport_ambiguous",
    }
)

TERMINAL_FAILURES: frozenset[str] = frozenset(
    {
        "configuration",
        "model_mismatch",
        "truncated",
        "content_filtered",
        "empty_content",
        "invalid_json",
        "unexpected_tool_call",
        "malformed_response",
        "unknown_provider_failure",
    }
)

# Only these three transient failure codes may be retried once inside the adapter (Ticket 022)
RETRYABLE_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "rate_limited",
        "provider_transient",
        "resource_exhausted",
    }
)

SECRET_PATTERNS = [
    re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE),
    re.compile(
        r"(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk|dsk)-[A-Za-z0-9_\-]{16,}\b", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Scrub credentials and tokens from any text or error message."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def disposition_for_failure(code: str) -> str:
    """Lookup disposition ('suspend' | 'terminal') for a failure taxonomy code.

    Strict lookup table per Ticket 025; unknown codes fail closed.
    """
    if code in SUSPEND_FAILURES:
        return "suspend"
    if code in TERMINAL_FAILURES:
        return "terminal"
    fail("INVALID_FAILURE_CODE", f"Unknown failure taxonomy code: {code}")


@dataclass(frozen=True, slots=True)
class DeepSeekMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class DeepSeekRequest:
    messages: tuple[DeepSeekMessage, ...]
    reasoning_effort: str
    max_tokens: int
    output_mode: str
    user_id: str

    def to_canonical_dict(self) -> dict[str, Any]:
        """Produce the canonical allowlisted request payload for provider transport."""
        payload: dict[str, Any] = {
            "max_tokens": self.max_tokens,
            "messages": [{"content": m.content, "role": m.role} for m in self.messages],
            "model": DEEPSEEK_MODEL_ID,
            "reasoning_effort": self.reasoning_effort,
            "stream": False,
            "thinking": {"type": "enabled"},
            "user_id": self.user_id,
        }
        if self.output_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int
    prompt_cache_hit_tokens: int
    prompt_cache_miss_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    total_tokens: int

    def to_dict(self) -> dict[str, int]:
        return {
            "completion_tokens": self.completion_tokens,
            "prompt_cache_hit_tokens": self.prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": self.prompt_cache_miss_tokens,
            "prompt_tokens": self.prompt_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    duration_ms: float

    def __post_init__(self) -> None:
        if isinstance(self.headers, dict):
            normalized = {str(k).lower(): str(v) for k, v in self.headers.items()}
            object.__setattr__(self, "headers", normalized)


class Transport(Protocol):
    def send(self, request_payload: dict[str, Any]) -> TransportResponse:
        """Send the canonical request payload to the provider transport."""
        ...


@dataclass(frozen=True, slots=True)
class ModelRoundResult:
    visible_content: str
    reasoning_content: str | None
    tool_calls: tuple[dict[str, Any], ...]
    requested_model: str
    response_model: str
    response_id: str
    system_fingerprint: str | None
    finish_reason: str
    usage: TokenUsage
    cost: CostBreakdown
    attempt_seq: int
    total_attempts: int
    duration_ms: float
    raw_response: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelRoundFailure:
    error_code: str
    disposition: str
    message: str
    http_status: int | None
    attempt_seq: int
    total_attempts: int
    retry_disposition: str
    duration_ms: float
    cost: CostBreakdown | None
    raw_error: dict[str, Any] | str | None


class ModelRoundError(RuntimeError):
    """Raised when a model round fails to produce a valid typed result."""

    def __init__(self, failure: ModelRoundFailure) -> None:
        super().__init__(
            f"{failure.error_code} ({failure.disposition}): {failure.message}"
        )
        self.failure = failure
        self.code = failure.error_code
        self.disposition = failure.disposition


def validate_request(
    *,
    messages: Sequence[dict[str, Any] | DeepSeekMessage],
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    max_tokens: int,
    output_mode: str = DEFAULT_OUTPUT_MODE,
    user_id: str,
    **extra_kwargs: Any,
) -> DeepSeekRequest:
    """Validate request arguments against the strict DeepSeek adapter allowlist.

    Caller overrides of provider-controlled fields, extra/unknown parameters,
    temperature/top_p/penalties/seed/extra_body, or invalid enum values fail closed.
    """
    if extra_kwargs:
        disallowed = sorted(str(k) for k in extra_kwargs.keys())
        raise ModelRoundError(
            ModelRoundFailure(
                error_code="configuration",
                disposition="terminal",
                message=f"Disallowed or unknown request parameters: {disallowed}",
                http_status=None,
                attempt_seq=1,
                total_attempts=1,
                retry_disposition="none",
                duration_ms=0.0,
                cost=None,
                raw_error={"disallowed_parameters": disallowed},
            )
        )

    if not isinstance(messages, (list, tuple)) or not messages:
        raise ModelRoundError(
            ModelRoundFailure(
                error_code="configuration",
                disposition="terminal",
                message="messages must be a non-empty sequence",
                http_status=None,
                attempt_seq=1,
                total_attempts=1,
                retry_disposition="none",
                duration_ms=0.0,
                cost=None,
                raw_error=None,
            )
        )

    validated_messages: list[DeepSeekMessage] = []
    for idx, msg in enumerate(messages):
        if isinstance(msg, DeepSeekMessage):
            role, content = msg.role, msg.content
        elif isinstance(msg, dict):
            allowed_msg_keys = {"role", "content"}
            if set(msg.keys()) != allowed_msg_keys:
                raise ModelRoundError(
                    ModelRoundFailure(
                        error_code="configuration",
                        disposition="terminal",
                        message=f"message[{idx}] has invalid keys: {sorted(msg.keys())}",
                        http_status=None,
                        attempt_seq=1,
                        total_attempts=1,
                        retry_disposition="none",
                        duration_ms=0.0,
                        cost=None,
                        raw_error=None,
                    )
                )
            role, content = msg["role"], msg["content"]
        else:
            raise ModelRoundError(
                ModelRoundFailure(
                    error_code="configuration",
                    disposition="terminal",
                    message=f"message[{idx}] must be a dict or DeepSeekMessage",
                    http_status=None,
                    attempt_seq=1,
                    total_attempts=1,
                    retry_disposition="none",
                    duration_ms=0.0,
                    cost=None,
                    raw_error=None,
                )
            )

        if role not in ALLOWED_ROLES:
            raise ModelRoundError(
                ModelRoundFailure(
                    error_code="configuration",
                    disposition="terminal",
                    message=f"message[{idx}] role '{role}' not in approved roles: {sorted(ALLOWED_ROLES)}",
                    http_status=None,
                    attempt_seq=1,
                    total_attempts=1,
                    retry_disposition="none",
                    duration_ms=0.0,
                    cost=None,
                    raw_error=None,
                )
            )
        if not isinstance(content, str) or not content.strip():
            raise ModelRoundError(
                ModelRoundFailure(
                    error_code="configuration",
                    disposition="terminal",
                    message=f"message[{idx}] content must be a non-empty, non-whitespace string",
                    http_status=None,
                    attempt_seq=1,
                    total_attempts=1,
                    retry_disposition="none",
                    duration_ms=0.0,
                    cost=None,
                    raw_error=None,
                )
            )

        # Disallow null bytes and unpaired surrogates in content
        for ch in content:
            code_pt = ord(ch)
            if code_pt == 0 or (0xD800 <= code_pt <= 0xDFFF):
                raise ModelRoundError(
                    ModelRoundFailure(
                        error_code="configuration",
                        disposition="terminal",
                        message=f"message[{idx}] content contains invalid characters (null byte or surrogate pair)",
                        http_status=None,
                        attempt_seq=1,
                        total_attempts=1,
                        retry_disposition="none",
                        duration_ms=0.0,
                        cost=None,
                        raw_error=None,
                    )
                )

        if role == "system" and idx != 0:
            raise ModelRoundError(
                ModelRoundFailure(
                    error_code="configuration",
                    disposition="terminal",
                    message=f"message[{idx}] system role is only allowed at messages[0]",
                    http_status=None,
                    attempt_seq=1,
                    total_attempts=1,
                    retry_disposition="none",
                    duration_ms=0.0,
                    cost=None,
                    raw_error=None,
                )
            )

        validated_messages.append(DeepSeekMessage(role=role, content=content))

    if reasoning_effort not in ALLOWED_REASONING_EFFORTS:
        raise ModelRoundError(
            ModelRoundFailure(
                error_code="configuration",
                disposition="terminal",
                message=f"reasoning_effort '{reasoning_effort}' not in {sorted(ALLOWED_REASONING_EFFORTS)}",
                http_status=None,
                attempt_seq=1,
                total_attempts=1,
                retry_disposition="none",
                duration_ms=0.0,
                cost=None,
                raw_error=None,
            )
        )

    if (
        not isinstance(max_tokens, int)
        or isinstance(max_tokens, bool)
        or max_tokens <= 0
    ):
        raise ModelRoundError(
            ModelRoundFailure(
                error_code="configuration",
                disposition="terminal",
                message=f"max_tokens must be a positive integer, got {max_tokens}",
                http_status=None,
                attempt_seq=1,
                total_attempts=1,
                retry_disposition="none",
                duration_ms=0.0,
                cost=None,
                raw_error=None,
            )
        )

    if output_mode not in ALLOWED_OUTPUT_MODES:
        raise ModelRoundError(
            ModelRoundFailure(
                error_code="configuration",
                disposition="terminal",
                message=f"output_mode '{output_mode}' not in {sorted(ALLOWED_OUTPUT_MODES)}",
                http_status=None,
                attempt_seq=1,
                total_attempts=1,
                retry_disposition="none",
                duration_ms=0.0,
                cost=None,
                raw_error=None,
            )
        )

    if not isinstance(user_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_\-\.]{1,128}\Z", user_id.strip()
    ):
        raise ModelRoundError(
            ModelRoundFailure(
                error_code="configuration",
                disposition="terminal",
                message="user_id must be a non-empty opaque ASCII identifier (1-128 chars: letters, digits, _, -, .)",
                http_status=None,
                attempt_seq=1,
                total_attempts=1,
                retry_disposition="none",
                duration_ms=0.0,
                cost=None,
                raw_error=None,
            )
        )

    return DeepSeekRequest(
        messages=tuple(validated_messages),
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        output_mode=output_mode,
        user_id=user_id.strip(),
    )


def validate_provider_response(
    status_code: int,
    headers: dict[str, str],
    body_bytes: bytes,
    *,
    output_mode: str,
    attempt_seq: int = 1,
    duration_ms: float = 0.0,
    in_call_attempt_seq: int | None = None,
) -> tuple[
    str,
    str | None,
    tuple[dict[str, Any], ...],
    str,
    str | None,
    str,
    TokenUsage,
    dict[str, Any],
]:
    """Validate HTTP response and raw provider body against provider-success contract.

    Returns:
      (visible_content, reasoning_content, tool_calls, response_id, system_fingerprint, finish_reason, usage, parsed_body)
    Raises ModelRoundError with typed ModelRoundFailure on any contract violation.

    `attempt_seq` is the physical attempt coordinate recorded in evidence;
    `in_call_attempt_seq` is the position within this call's bounded retry
    budget (the two differ only on resume re-execution, ticket 10).
    """
    in_call_position = (
        in_call_attempt_seq if in_call_attempt_seq is not None else attempt_seq
    )

    def _fail(
        code: str, message: str, raw_err: Any = None, http_st: int | None = status_code
    ) -> None:
        raise ModelRoundError(
            ModelRoundFailure(
                error_code=code,
                disposition=disposition_for_failure(code),
                message=redact_secrets(message),
                http_status=http_st,
                attempt_seq=attempt_seq,
                total_attempts=attempt_seq,
                retry_disposition=(
                    "retry_candidate"
                    if code in RETRYABLE_FAILURE_CODES
                    and in_call_position < MAX_ATTEMPTS_PER_OPERATION
                    else "none"
                ),
                duration_ms=duration_ms,
                cost=None,
                raw_error=raw_err,
            )
        )

    # 1. HTTP Status mapping for non-200
    if status_code != 200:
        raw_error_text = redact_secrets(body_bytes.decode("utf-8", errors="replace"))
        if status_code in (400, 422):
            _fail(
                "configuration",
                f"Provider returned HTTP {status_code}: {raw_error_text}",
            )
        elif status_code == 401:
            _fail("authentication", f"Provider returned HTTP 401: {raw_error_text}")
        elif status_code == 402:
            _fail(
                "insufficient_balance", f"Provider returned HTTP 402: {raw_error_text}"
            )
        elif status_code == 429:
            _fail("rate_limited", f"Provider returned HTTP 429: {raw_error_text}")
        elif status_code in (500, 502, 503, 504):
            _fail(
                "provider_transient",
                f"Provider returned HTTP {status_code}: {raw_error_text}",
            )
        else:
            _fail(
                "unknown_provider_failure",
                f"Provider returned HTTP {status_code}: {raw_error_text}",
            )

    # 2. Parse JSON body
    try:
        data = parse_json_bytes(body_bytes, label="provider response")
    except Exception as exc:
        _fail("malformed_response", f"Failed to parse provider response JSON: {exc}")

    if not isinstance(data, dict):
        _fail("malformed_response", "Provider response root must be a JSON object")

    # 3. Required top-level fields
    for required_key in ("id", "model", "choices", "usage"):
        if required_key not in data:
            _fail(
                "malformed_response",
                f"Provider response missing required field: '{required_key}'",
            )

    response_id = data["id"]
    if not isinstance(response_id, str) or not response_id:
        _fail("malformed_response", "Response 'id' must be a non-empty string")

    response_model = data["model"]
    if not isinstance(response_model, str):
        _fail("malformed_response", "Response 'model' must be a string")

    # 4. Model exact match
    if response_model != DEEPSEEK_MODEL_ID:
        _fail(
            "model_mismatch",
            f"Response model '{response_model}' does not match requested '{DEEPSEEK_MODEL_ID}'",
            raw_err={
                "expected_model": DEEPSEEK_MODEL_ID,
                "response_model": response_model,
            },
        )

    system_fingerprint = data.get("system_fingerprint")
    if system_fingerprint is not None and not isinstance(system_fingerprint, str):
        _fail("malformed_response", "system_fingerprint must be a string or null")

    # 5. Choices validation
    choices = data["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        _fail(
            "malformed_response",
            f"Response 'choices' must contain exactly 1 element, got {len(choices) if isinstance(choices, list) else type(choices)}",
            raw_err=data,
        )

    choice0 = choices[0]
    if not isinstance(choice0, dict):
        _fail(
            "malformed_response", "Response choice[0] must be an object", raw_err=data
        )

    if choice0.get("index") != 0:
        _fail(
            "malformed_response",
            f"choice[0].index must be 0, got {choice0.get('index')}",
            raw_err=data,
        )

    finish_reason = choice0.get("finish_reason")
    if not isinstance(finish_reason, str):
        _fail("malformed_response", "finish_reason must be a string", raw_err=data)

    # 6. Finish reason checks
    if finish_reason == "length":
        _fail(
            "truncated",
            "Provider response truncated due to length (max_tokens reached)",
            raw_err=data,
        )
    elif finish_reason == "content_filter":
        _fail(
            "content_filtered",
            "Provider response omitted due to content filter",
            raw_err=data,
        )
    elif finish_reason == "insufficient_system_resource":
        _fail(
            "resource_exhausted",
            "Provider returned finish_reason=insufficient_system_resource",
            raw_err=data,
        )
    elif finish_reason == "tool_calls":
        _fail(
            "unexpected_tool_call",
            "Unexpected finish_reason=tool_calls; native tools are disabled in v1",
            raw_err=data,
        )
    elif finish_reason != "stop":
        _fail(
            "malformed_response",
            f"Unexpected finish_reason: '{finish_reason}'",
            raw_err=data,
        )

    message = choice0.get("message")
    if not isinstance(message, dict):
        _fail("malformed_response", "choice[0].message must be an object", raw_err=data)

    # 7. Content and tool_calls
    content = message.get("content")
    if content is None or not isinstance(content, str) or not content.strip():
        _fail(
            "empty_content",
            "Provider response choice[0].message.content is empty or whitespace",
            raw_err=data,
        )

    tool_calls = message.get("tool_calls")
    if tool_calls is not None:
        if not isinstance(tool_calls, list):
            _fail(
                "malformed_response",
                "tool_calls must be a list if present",
                raw_err=data,
            )
        if tool_calls:
            _fail(
                "unexpected_tool_call",
                "Provider returned unexpected tool_calls in message",
                raw_err=data,
            )

    reasoning_content = message.get("reasoning_content")
    if reasoning_content is not None and not isinstance(reasoning_content, str):
        _fail("malformed_response", "reasoning_content must be a string or null")

    # 8. Output mode validation
    if output_mode == "json_object":
        try:
            json_val = parse_json_bytes(
                content.encode("utf-8"), label="content json_object"
            )
        except Exception as exc:
            _fail(
                "invalid_json", f"Content in json_object mode is not valid JSON: {exc}"
            )
        if not isinstance(json_val, dict):
            _fail(
                "invalid_json",
                "Content in json_object mode must be a top-level JSON object",
            )

    # 9. Usage and invariants
    raw_usage = data["usage"]
    if not isinstance(raw_usage, dict):
        _fail("malformed_response", "usage must be an object")

    required_usage_keys = (
        "completion_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_tokens",
        "total_tokens",
    )
    for ukey in required_usage_keys:
        if ukey not in raw_usage:
            _fail("malformed_response", f"usage missing required key: '{ukey}'")
        val = raw_usage[ukey]
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            _fail("malformed_response", f"usage.{ukey} must be a non-negative integer")

    prompt_tokens = raw_usage["prompt_tokens"]
    prompt_cache_hit = raw_usage["prompt_cache_hit_tokens"]
    prompt_cache_miss = raw_usage["prompt_cache_miss_tokens"]
    completion_tokens = raw_usage["completion_tokens"]
    total_tokens = raw_usage["total_tokens"]

    # Reasoning tokens can appear in completion_tokens_details or at top-level
    reasoning_tokens = 0
    if "completion_tokens_details" in raw_usage:
        details = raw_usage["completion_tokens_details"]
        if isinstance(details, dict) and "reasoning_tokens" in details:
            rt_val = details["reasoning_tokens"]
            if not isinstance(rt_val, int) or isinstance(rt_val, bool) or rt_val < 0:
                _fail(
                    "malformed_response",
                    "completion_tokens_details.reasoning_tokens must be a non-negative int",
                )
            reasoning_tokens = rt_val
    elif "reasoning_tokens" in raw_usage:
        rt_val = raw_usage["reasoning_tokens"]
        if not isinstance(rt_val, int) or isinstance(rt_val, bool) or rt_val < 0:
            _fail(
                "malformed_response",
                "usage.reasoning_tokens must be a non-negative int",
            )
        reasoning_tokens = rt_val

    # Invariants check
    if prompt_tokens != (prompt_cache_hit + prompt_cache_miss):
        _fail(
            "malformed_response",
            f"Usage invariant violated: prompt ({prompt_tokens}) != cache_hit ({prompt_cache_hit}) + cache_miss ({prompt_cache_miss})",
        )

    if total_tokens != (prompt_tokens + completion_tokens):
        _fail(
            "malformed_response",
            f"Usage invariant violated: total ({total_tokens}) != prompt ({prompt_tokens}) + completion ({completion_tokens})",
        )

    if not (0 <= reasoning_tokens <= completion_tokens):
        _fail(
            "malformed_response",
            f"Usage invariant violated: reasoning ({reasoning_tokens}) not in [0, completion ({completion_tokens})]",
        )

    usage = TokenUsage(
        completion_tokens=completion_tokens,
        prompt_cache_hit_tokens=prompt_cache_hit,
        prompt_cache_miss_tokens=prompt_cache_miss,
        prompt_tokens=prompt_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )

    return (
        content,
        reasoning_content,
        tuple(),
        response_id,
        system_fingerprint,
        finish_reason,
        usage,
        data,
    )


def parse_stored_response_content(body_bytes: bytes) -> str:
    """Re-validate a committed provider response artifact; return visible content.

    Used by resume replay (ticket 10): the bytes were validated when
    committed, so re-validation either passes deterministically or fails
    closed as evidence corruption.
    """
    visible_content, *_rest = validate_provider_response(
        200,
        {"content-type": "application/json"},
        body_bytes,
        output_mode="text",
        attempt_seq=1,
        duration_ms=0.0,
    )
    return visible_content


class StubTransport:
    """Deterministic, scriptable transport for offline testing and fault injection."""

    def __init__(
        self,
        responses: Sequence[
            TransportResponse | Exception | Callable[..., TransportResponse]
        ],
    ) -> None:
        self._queue: list[
            TransportResponse | Exception | Callable[..., TransportResponse]
        ] = list(responses)
        self.sent_requests: list[dict[str, Any]] = []

    def send(self, request_payload: dict[str, Any]) -> TransportResponse:
        self.sent_requests.append(request_payload)
        if not self._queue:
            fail(
                "TRANSPORT_EXHAUSTED",
                "StubTransport received more requests than configured responses",
            )
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request_payload)
        return item


class RecordedTransport:
    """Deterministic replay transport loaded from canonical recorded response."""

    def __init__(
        self, response_bytes: bytes, status_code: int = 200, duration_ms: float = 120.0
    ) -> None:
        self.response_bytes = response_bytes
        self.status_code = status_code
        self.duration_ms = duration_ms
        self.sent_requests: list[dict[str, Any]] = []

    def send(self, request_payload: dict[str, Any]) -> TransportResponse:
        self.sent_requests.append(request_payload)
        return TransportResponse(
            body=self.response_bytes,
            duration_ms=self.duration_ms,
            headers={"content-type": "application/json"},
            status_code=self.status_code,
        )


def create_deepseek_client_options(api_key: str | None = None) -> dict[str, Any]:
    """Return explicit client configuration options ensuring SDK implicit retries are off."""
    return {
        "api_key": api_key or "[REDACTED]",
        "base_url": DEEPSEEK_BASE_URL,
        "max_retries": 0,  # Strict contract: SDK implicit retries disabled
        "timeout": WALL_CLOCK_DEADLINE_SECONDS,
    }


class DeepSeekAdapter:
    """DeepSeek-only non-streaming adapter governing provider transport and evidence."""

    def __init__(
        self,
        transport: Transport,
        *,
        store: RunStore | None = None,
        run_id: str | None = None,
        price_table: PriceTable | None = None,
    ) -> None:
        self.transport = transport
        self.store = store
        self.run_id = run_id
        self.price_table = price_table

    def execute_round(
        self,
        request: DeepSeekRequest | dict[str, Any],
        op_seq: int,
        *,
        pipeline_position: dict[str, Any] | None = None,
        writer_epoch: int = 1,
        initial_attempt_seq: int = 1,
    ) -> ModelRoundResult:
        """Execute a model round with bounded retry, Provider Attempts, and evidence chain persistence.

        `initial_attempt_seq` is 1 for a fresh operation; a resume re-executes
        an in-flight operation under the same `op_seq` with the next physical
        attempt coordinate (contract 025: attempt 3+ only ever comes from a
        resume). Each call keeps its own <=2 attempt budget (ticket 022).
        """
        # Audit Release Gate: Ensure execution has admitted run audit context
        if self.store is None or self.run_id is None:
            fail(
                "AUDIT_RELEASE_GATE_FAILED",
                "Cannot execute model round without admitted RunStore and run_id audit context",
            )

        if not isinstance(op_seq, int) or isinstance(op_seq, bool) or op_seq < 1:
            fail(
                "INVALID_COORDINATE",
                f"op_seq must be a positive integer, got {op_seq}",
            )

        if (
            not isinstance(initial_attempt_seq, int)
            or isinstance(initial_attempt_seq, bool)
            or initial_attempt_seq < 1
        ):
            fail(
                "INVALID_COORDINATE",
                f"initial_attempt_seq must be a positive integer, got {initial_attempt_seq}",
            )

        if (
            not isinstance(writer_epoch, int)
            or isinstance(writer_epoch, bool)
            or writer_epoch < 1
        ):
            fail(
                "INVALID_EPOCH",
                f"writer_epoch must be a positive integer, got {writer_epoch}",
            )

        if pipeline_position is not None:
            if not isinstance(pipeline_position, dict):
                fail("INVALID_COORDINATE", "pipeline_position must be a dict")
            for k in ("generation_index", "reflection_index"):
                if k in pipeline_position:
                    val = pipeline_position[k]
                    if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                        fail(
                            "INVALID_COORDINATE",
                            f"pipeline_position.{k} must be a non-negative integer",
                        )

        # 1. Validate request
        if isinstance(request, DeepSeekRequest):
            validated_req = request
        elif isinstance(request, dict):
            validated_req = validate_request(**request)
        else:
            raise ModelRoundError(
                ModelRoundFailure(
                    attempt_seq=1,
                    cost=None,
                    disposition="terminal",
                    duration_ms=0.0,
                    error_code="configuration",
                    http_status=None,
                    message=f"Request must be DeepSeekRequest or dict, got {type(request)}",
                    raw_error=None,
                    retry_disposition="none",
                    total_attempts=1,
                )
            )

        canonical_req_dict = validated_req.to_canonical_dict()
        req_bytes = canonical_json_bytes(canonical_req_dict)

        pipe_pos = pipeline_position or {
            "generation_index": 0,
            "idea_index": None,
            "reflection_index": 0,
        }

        attempts_executed = 0
        last_failure: ModelRoundFailure | None = None

        for attempt_offset in range(MAX_ATTEMPTS_PER_OPERATION):
            attempt_seq = initial_attempt_seq + attempt_offset
            attempts_executed += 1
            attempt_started_at = _now()
            t0 = time.perf_counter()

            # Optional persistence of request.json
            req_ref: dict[str, Any] | None = None
            if self.store is not None and self.run_id is not None:
                rel_path, byte_len, sha = self.store.write_operation_artifact(
                    self.run_id,
                    op_seq,
                    attempt_seq,
                    "request.json",
                    req_bytes,
                    label="provider request",
                )
                req_ref = {
                    "byte_length": byte_len,
                    "media_type": "application/json",
                    "relative_path": rel_path,
                    "role": "provider_request",
                    "sha256": sha,
                }

            # Execute transport call
            transport_resp: TransportResponse | None = None
            transport_failure: ModelRoundFailure | None = None
            try:
                transport_resp = self.transport.send(canonical_req_dict)
            except TimeoutError as exc:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
                transport_failure = ModelRoundFailure(
                    attempt_seq=attempt_seq,
                    cost=None,
                    disposition="suspend",
                    duration_ms=elapsed_ms,
                    error_code="timeout_ambiguous",
                    http_status=None,
                    message=f"Transport call timed out: {exc}",
                    raw_error=str(exc),
                    retry_disposition="none",  # timeout_ambiguous must not be retried!
                    total_attempts=attempt_seq,
                )
            except (ConnectionError, OSError) as exc:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
                transport_failure = ModelRoundFailure(
                    attempt_seq=attempt_seq,
                    cost=None,
                    disposition="suspend",
                    duration_ms=elapsed_ms,
                    error_code="transport_ambiguous",
                    http_status=None,
                    message=f"Transport connection failed: {exc}",
                    raw_error=str(exc),
                    retry_disposition="none",  # transport_ambiguous must not be retried!
                    total_attempts=attempt_seq,
                )
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)
                transport_failure = ModelRoundFailure(
                    attempt_seq=attempt_seq,
                    cost=None,
                    disposition="terminal",
                    duration_ms=elapsed_ms,
                    error_code="unknown_provider_failure",
                    http_status=None,
                    message=f"Unexpected transport exception: {exc}",
                    raw_error=str(exc),
                    retry_disposition="none",
                    total_attempts=attempt_seq,
                )

            # If transport exception occurred:
            if transport_failure is not None:
                last_failure = transport_failure
                self._record_attempt_failure(
                    failure=transport_failure,
                    op_seq=op_seq,
                    attempt_seq=attempt_seq,
                    pipeline_position=pipe_pos,
                    req_ref=req_ref,
                    writer_epoch=writer_epoch,
                )
                # Ambiguous/unknown failures never retry
                self._record_operation_failed(
                    failure=transport_failure,
                    op_seq=op_seq,
                    attempt_seq=attempt_seq,
                    pipeline_position=pipe_pos,
                    writer_epoch=writer_epoch,
                )
                raise ModelRoundError(transport_failure)

            assert transport_resp is not None
            elapsed_ms = transport_resp.duration_ms or round(
                (time.perf_counter() - t0) * 1000, 3
            )

            # Validate response
            try:
                (
                    visible_content,
                    reasoning_content,
                    tool_calls,
                    response_id,
                    system_fingerprint,
                    finish_reason,
                    usage,
                    parsed_body,
                ) = validate_provider_response(
                    transport_resp.status_code,
                    transport_resp.headers,
                    transport_resp.body,
                    attempt_seq=attempt_seq,
                    duration_ms=elapsed_ms,
                    output_mode=validated_req.output_mode,
                    in_call_attempt_seq=attempts_executed,
                )
            except ModelRoundError as mre:
                last_failure = mre.failure
                # Calculate cost if usage was parsed
                cost = None
                if (
                    self.price_table is not None
                    and isinstance(last_failure.raw_error, dict)
                    and "usage" in last_failure.raw_error
                ):
                    raw_u = last_failure.raw_error["usage"]
                    if (
                        isinstance(raw_u, dict)
                        and "prompt_tokens" in raw_u
                        and "completion_tokens" in raw_u
                    ):
                        try:
                            parsed_u = TokenUsage(
                                completion_tokens=int(
                                    raw_u.get("completion_tokens", 0)
                                ),
                                prompt_cache_hit_tokens=int(
                                    raw_u.get("prompt_cache_hit_tokens", 0)
                                ),
                                prompt_cache_miss_tokens=int(
                                    raw_u.get("prompt_cache_miss_tokens", 0)
                                ),
                                prompt_tokens=int(raw_u.get("prompt_tokens", 0)),
                                reasoning_tokens=int(raw_u.get("reasoning_tokens", 0)),
                                total_tokens=int(raw_u.get("total_tokens", 0)),
                            )
                            cost = self._compute_cost(attempt_started_at, parsed_u)
                        except Exception:
                            cost = None

                # Check Retry-After header for 429
                retry_disposition = last_failure.retry_disposition
                if last_failure.error_code == "rate_limited":
                    retry_after_str = transport_resp.headers.get("retry-after", "")
                    try:
                        if (
                            retry_after_str
                            and float(retry_after_str) > MAX_RETRY_AFTER_SECONDS
                        ):
                            retry_disposition = "retry_after_exceeded"
                    except ValueError:
                        pass

                # Update failure record with actual retry disposition
                last_failure = ModelRoundFailure(
                    attempt_seq=attempt_seq,
                    cost=cost,
                    disposition=last_failure.disposition,
                    duration_ms=elapsed_ms,
                    error_code=last_failure.error_code,
                    http_status=last_failure.http_status,
                    message=last_failure.message,
                    raw_error=last_failure.raw_error
                    or redact_secrets(
                        transport_resp.body.decode("utf-8", errors="replace")
                    ),
                    retry_disposition=retry_disposition,
                    total_attempts=attempt_seq,
                )

                # Persist attempt failure artifact and event
                self._record_attempt_failure(
                    failure=last_failure,
                    op_seq=op_seq,
                    attempt_seq=attempt_seq,
                    pipeline_position=pipe_pos,
                    req_ref=req_ref,
                    writer_epoch=writer_epoch,
                )

                # Decide whether to retry within this call's budget (022)
                if (
                    attempts_executed < MAX_ATTEMPTS_PER_OPERATION
                    and last_failure.error_code in RETRYABLE_FAILURE_CODES
                    and retry_disposition != "retry_after_exceeded"
                ):
                    # Proceed to attempt 2
                    continue
                else:
                    # Final attempt failed
                    self._record_operation_failed(
                        failure=last_failure,
                        op_seq=op_seq,
                        attempt_seq=attempt_seq,
                        pipeline_position=pipe_pos,
                        writer_epoch=writer_epoch,
                    )
                    raise ModelRoundError(last_failure)

            # Success path!
            cost = self._compute_cost(attempt_started_at, usage)
            result = ModelRoundResult(
                attempt_seq=attempt_seq,
                cost=cost,
                duration_ms=elapsed_ms,
                finish_reason=finish_reason,
                raw_response=parsed_body,
                reasoning_content=reasoning_content,
                requested_model=DEEPSEEK_MODEL_ID,
                response_id=response_id,
                response_model=DEEPSEEK_MODEL_ID,
                system_fingerprint=system_fingerprint,
                tool_calls=tool_calls,
                total_attempts=attempts_executed,
                usage=usage,
                visible_content=visible_content,
            )

            self._record_attempt_and_operation_success(
                op_seq=op_seq,
                attempt_seq=attempt_seq,
                pipeline_position=pipe_pos,
                raw_body_bytes=transport_resp.body,
                req_ref=req_ref,
                result=result,
                writer_epoch=writer_epoch,
            )
            return result

        assert last_failure is not None
        raise ModelRoundError(last_failure)

    def _compute_cost(self, started_at: str, usage: TokenUsage) -> CostBreakdown:
        if self.price_table is None:
            # Zero breakdown fallback if price table not configured
            return CostBreakdown(
                cache_hit_cost_cny=Decimal("0.00"),
                cache_miss_cost_cny=Decimal("0.00"),
                output_cost_cny=Decimal("0.00"),
                total_cny=Decimal("0.00"),
            )
        return attempt_cost(
            self.price_table,
            attempt_started_at=started_at,
            cache_hit_tokens=usage.prompt_cache_hit_tokens,
            cache_miss_tokens=usage.prompt_cache_miss_tokens,
            output_tokens=usage.completion_tokens,
        )

    def _record_attempt_failure(
        self,
        *,
        op_seq: int,
        attempt_seq: int,
        req_ref: dict[str, Any] | None,
        failure: ModelRoundFailure,
        pipeline_position: dict[str, Any],
        writer_epoch: int,
    ) -> None:
        if self.store is None or self.run_id is None:
            return
        fail_dict: dict[str, Any] = {
            "disposition": failure.disposition,
            "duration_ms": f"{failure.duration_ms:.3f}",
            "error_code": failure.error_code,
            "http_status": failure.http_status,
            "message": failure.message,
            "retry_disposition": failure.retry_disposition,
        }
        if failure.cost is not None:
            fail_dict["cost"] = {
                "cache_hit_cost_cny": str(failure.cost.cache_hit_cost_cny),
                "cache_miss_cost_cny": str(failure.cost.cache_miss_cost_cny),
                "output_cost_cny": str(failure.cost.output_cost_cny),
                "total_cny": str(failure.cost.total_cny),
            }
        fail_bytes = canonical_json_bytes(fail_dict)
        f_rel, f_len, f_sha = self.store.write_operation_artifact(
            self.run_id,
            op_seq,
            attempt_seq,
            "failure.json",
            fail_bytes,
            label="provider failure",
        )
        artifact_refs = []
        if req_ref:
            artifact_refs.append(req_ref)
        artifact_refs.append(
            {
                "byte_length": f_len,
                "media_type": "application/json",
                "relative_path": f_rel,
                "role": "provider_failure",
                "sha256": f_sha,
            }
        )
        attempt_payload: dict[str, Any] = {
            "disposition": failure.disposition,
            "duration_ms": f"{failure.duration_ms:.3f}",
            "error_code": failure.error_code,
            "outcome": "failed",
            "retry_disposition": failure.retry_disposition,
        }
        if failure.cost is not None:
            attempt_payload["cost_cny"] = str(failure.cost.total_cny)
        self.store.append_event(
            self.run_id,
            {
                "artifact_refs": artifact_refs,
                "event_type": "provider_attempt.finished",
                "operation": {
                    "attempt_seq": attempt_seq,
                    "operation_kind": "model_inference",
                    "operation_seq": op_seq,
                },
                "payload": attempt_payload,
                "pipeline_position": pipeline_position,
                "writer_epoch": writer_epoch,
            },
        )

    def _record_operation_failed(
        self,
        *,
        op_seq: int,
        attempt_seq: int,
        failure: ModelRoundFailure,
        pipeline_position: dict[str, Any],
        writer_epoch: int,
    ) -> None:
        if self.store is None or self.run_id is None:
            return
        self.store.append_event(
            self.run_id,
            {
                "event_type": "operation.failed",
                "operation": {
                    "attempt_seq": attempt_seq,
                    "operation_kind": "model_inference",
                    "operation_seq": op_seq,
                },
                "payload": {
                    "disposition": failure.disposition,
                    "error_code": failure.error_code,
                    "status": "failed",
                    "total_attempts": attempt_seq,
                },
                "pipeline_position": pipeline_position,
                "writer_epoch": writer_epoch,
            },
        )
        self.store.verify_chain(self.run_id)

    def _record_attempt_and_operation_success(
        self,
        *,
        op_seq: int,
        attempt_seq: int,
        req_ref: dict[str, Any] | None,
        result: ModelRoundResult,
        raw_body_bytes: bytes,
        pipeline_position: dict[str, Any],
        writer_epoch: int,
    ) -> None:
        if self.store is None or self.run_id is None:
            return

        resp_rel, resp_len, resp_sha = self.store.write_operation_artifact(
            self.run_id,
            op_seq,
            attempt_seq,
            "response.json",
            raw_body_bytes,
            label="provider response",
        )
        attempt_refs = []
        if req_ref:
            attempt_refs.append(req_ref)
        resp_ref = {
            "byte_length": resp_len,
            "media_type": "application/json",
            "relative_path": resp_rel,
            "role": "provider_response",
            "sha256": resp_sha,
        }
        attempt_refs.append(resp_ref)

        # 1. provider_attempt.finished event
        self.store.append_event(
            self.run_id,
            {
                "artifact_refs": attempt_refs,
                "event_type": "provider_attempt.finished",
                "operation": {
                    "attempt_seq": attempt_seq,
                    "operation_kind": "model_inference",
                    "operation_seq": op_seq,
                },
                "payload": {
                    "cost_cny": str(result.cost.total_cny),
                    "duration_ms": f"{result.duration_ms:.3f}",
                    "finish_reason": result.finish_reason,
                    "model": result.response_model,
                    "outcome": "success",
                    "response_id": result.response_id,
                    "usage": result.usage.to_dict(),
                },
                "pipeline_position": pipeline_position,
                "writer_epoch": writer_epoch,
            },
        )

        # 2. operation.finished event
        self.store.append_event(
            self.run_id,
            {
                "artifact_refs": [resp_ref],
                "event_type": "operation.finished",
                "operation": {
                    "attempt_seq": attempt_seq,
                    "operation_kind": "model_inference",
                    "operation_seq": op_seq,
                },
                "payload": {
                    "cost_cny": str(result.cost.total_cny),
                    "model": result.response_model,
                    "response_id": result.response_id,
                    "status": "success",
                    "total_attempts": result.total_attempts,
                },
                "pipeline_position": pipeline_position,
                "writer_epoch": writer_epoch,
            },
        )
        self.store.verify_chain(self.run_id)
