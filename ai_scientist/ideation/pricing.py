"""Versioned CNY pricing for DeepSeek cost accounting (ticket 04).

The price table is a tracked, version-managed file registered once with
Robert's approval; preflight pins its SHA-256 into the Run Admission. All
amounts are exact decimals computed from token counts and the table rates,
rounded up to the nearest fen (0.01 CNY). A missing or hash-mismatched
table fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
import re
from typing import Any

from .canonical import parse_json_bytes, sha256_bytes
from .errors import fail

PRICE_TABLE_RELPATH = Path(
    "ai_scientist/ideation/policies/deepseek-cny-price-table-v1.json"
)
# Registered with Robert's approval on 2026-09-03; official repricing
# requires a new table version and a fresh approval.
PRICE_TABLE_SHA256 = "f02bab04f210a7cab755ae0ccb027920570cc17ad3d146cec38167ac3a8c77fd"

TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
WINDOW_PATTERN = re.compile(r"([01]\d|2[0-3]):([0-5]\d)\Z")
DAY_PATTERN = re.compile(r"mon|tue|wed|thu|fri|sat|sun\Z")
REQUIRED_TABLE_KEYS = frozenset(
    {
        "currency",
        "model_id",
        "peak_windows_utc",
        "rates_per_million_tokens",
        "registered_at",
        "schema_version",
        "source_url",
    }
)
RATE_KEYS = frozenset({"cache_hit", "cache_miss", "output"})
MONEY_PATTERN = re.compile(r"\d+(?:\.\d+)?\Z")
PEAK_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri"})
FEN = Decimal("0.01")


def expected_price_table_sha256() -> str:
    return PRICE_TABLE_SHA256


def _round_up_to_fen(amount: Decimal) -> Decimal:
    return amount.quantize(FEN, rounding=ROUND_CEILING)


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    cache_hit_cost_cny: Decimal
    cache_miss_cost_cny: Decimal
    output_cost_cny: Decimal
    total_cny: Decimal


def _validate_money(value: object, *, label: str) -> Decimal:
    if not isinstance(value, str) or not MONEY_PATTERN.fullmatch(value):
        fail("PRICE_TABLE_INVALID", f"{label} must be a decimal CNY rate string")
    return Decimal(value)


def _validate_rates(value: object, *, label: str) -> dict[str, Decimal]:
    if not isinstance(value, dict) or set(value) != RATE_KEYS:
        fail("PRICE_TABLE_INVALID", f"{label} must hold exactly {sorted(RATE_KEYS)}")
    return {
        key: _validate_money(value[key], label=f"{label}.{key}")
        for key in sorted(RATE_KEYS)
    }


def _validate_peak_windows(value: object) -> None:
    if not isinstance(value, list) or not value:
        fail("PRICE_TABLE_INVALID", "peak_windows_utc must be a non-empty array")
    for index, window in enumerate(value):
        label = f"peak_windows_utc[{index}]"
        if not isinstance(window, dict) or set(window) != {"days", "end", "start"}:
            fail("PRICE_TABLE_INVALID", f"{label} must hold days, start, and end")
        if not isinstance(window["days"], list) or not window["days"]:
            fail("PRICE_TABLE_INVALID", f"{label}.days must be a non-empty array")
        for day in window["days"]:
            if not isinstance(day, str) or not DAY_PATTERN.fullmatch(day):
                fail("PRICE_TABLE_INVALID", f"{label}.days has an invalid weekday")
        start = window["start"] if isinstance(window["start"], str) else ""
        end = window["end"] if isinstance(window["end"], str) else ""
        start_match = WINDOW_PATTERN.fullmatch(start)
        end_match = WINDOW_PATTERN.fullmatch(end)
        if start_match is None or end_match is None:
            fail("PRICE_TABLE_INVALID", f"{label} has an invalid HH:MM window")
        start_minutes = int(start_match.group(1)) * 60 + int(start_match.group(2))
        end_minutes = int(end_match.group(1)) * 60 + int(end_match.group(2))
        if start_minutes >= end_minutes:
            fail("PRICE_TABLE_INVALID", f"{label} does not span a positive range")


def _validate_table(document: dict[str, Any]) -> None:
    unknown = sorted(set(document) - REQUIRED_TABLE_KEYS)
    missing = sorted(REQUIRED_TABLE_KEYS - set(document))
    if unknown or missing:
        fail(
            "PRICE_TABLE_INVALID",
            "CNY price table has an invalid closed schema",
            unknown=unknown,
            missing=missing,
        )
    for key in ("currency", "model_id", "registered_at", "schema_version"):
        if not isinstance(document[key], str) or not document[key]:
            fail("PRICE_TABLE_INVALID", f"price table {key} must be a non-empty string")
    if document["currency"] != "CNY":
        fail("PRICE_TABLE_INVALID", "price table currency must be CNY")
    if not isinstance(document["source_url"], str) or not document["source_url"]:
        fail("PRICE_TABLE_INVALID", "price table source_url must be non-empty")
    if not isinstance(document["registered_at"], str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}\Z", document["registered_at"]
    ):
        fail("PRICE_TABLE_INVALID", "registered_at must be an ISO date")
    rates_root = document["rates_per_million_tokens"]
    if not isinstance(rates_root, dict) or set(rates_root) != {"peak", "off_peak"}:
        fail(
            "PRICE_TABLE_INVALID",
            "rates_per_million_tokens must hold peak and off_peak",
        )
    for period in ("peak", "off_peak"):
        _validate_rates(rates_root[period], label=f"rates.{period}")
    _validate_peak_windows(document["peak_windows_utc"])


@dataclass(frozen=True, slots=True)
class PriceTable:
    document: dict[str, Any]
    sha256: str

    def period_for(self, started_at: str) -> str:
        """Classify an attempt-start timestamp as `peak` or `off_peak`."""
        if not isinstance(started_at, str) or not TIMESTAMP_PATTERN.fullmatch(
            started_at
        ):
            fail("INVALID_TIMESTAMP", "attempt start must be a canonical UTC timestamp")
        parsed = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=UTC
        )
        weekday = parsed.strftime("%a").lower()
        if weekday not in PEAK_DAYS:
            return "off_peak"
        minutes = parsed.hour * 60 + parsed.minute
        for window in self.document["peak_windows_utc"]:
            if weekday not in window["days"]:
                continue
            start_hour, start_minute = (
                int(part) for part in window["start"].split(":")
            )
            end_hour, end_minute = (int(part) for part in window["end"].split(":"))
            if start_hour * 60 + start_minute <= minutes < end_hour * 60 + end_minute:
                return "peak"
        return "off_peak"

    def rates(self, period: str) -> dict[str, Decimal]:
        raw = self.document["rates_per_million_tokens"][period]
        return {key: Decimal(value) for key, value in raw.items()}


def load_price_table(workspace_root: Path) -> PriceTable:
    """Load and hash-pin the registered CNY price table, or fail closed."""
    path = workspace_root / PRICE_TABLE_RELPATH
    if not path.is_file():
        fail("MISSING_PRICE_TABLE", f"CNY price table is missing: {path}")
    data = path.read_bytes()
    actual = sha256_bytes(data)
    if actual != PRICE_TABLE_SHA256:
        fail(
            "PRICE_TABLE_HASH_MISMATCH",
            "CNY price table does not match its registered SHA-256",
            expected=PRICE_TABLE_SHA256,
            actual=actual,
        )
    value = parse_json_bytes(data, label="price table")
    if not isinstance(value, dict):
        fail("PRICE_TABLE_INVALID", "CNY price table must be a JSON object")
    _validate_table(value)
    return PriceTable(document=value, sha256=actual)


def _charge(tokens: int, rate: Decimal) -> Decimal:
    return Decimal(tokens) / Decimal(1_000_000) * rate


def worst_case_bound(
    table: PriceTable,
    *,
    input_tokens: int,
    output_tokens: int,
    attempts: int,
) -> CostBreakdown:
    """Conservative upper bound: peak rates, all cache miss, declared budgets.

    The declared `input_tokens` is the worst-case input (all charged at the
    peak cache-miss rate); `output_tokens` is the explicit output budget;
    `attempts` is the declared attempt ceiling (<= 2 per the adapter
    contract).
    """
    if not isinstance(input_tokens, int) or input_tokens < 0:
        fail("INVALID_BUDGET", "input_tokens must be a non-negative integer")
    if not isinstance(output_tokens, int) or output_tokens < 0:
        fail("INVALID_BUDGET", "output_tokens must be a non-negative integer")
    if not isinstance(attempts, int) or attempts < 1 or attempts > 2:
        fail("INVALID_BUDGET", "Attempt ceiling must be 1 or 2")
    rates = table.rates("peak")
    cache_miss_cost = _charge(input_tokens, rates["cache_miss"]) * attempts
    output_cost = _charge(output_tokens, rates["output"]) * attempts
    total = _round_up_to_fen(cache_miss_cost + output_cost)
    return CostBreakdown(
        cache_hit_cost_cny=Decimal("0.00"),
        cache_miss_cost_cny=_round_up_to_fen(cache_miss_cost),
        output_cost_cny=_round_up_to_fen(output_cost),
        total_cny=total,
    )


def attempt_cost(
    table: PriceTable,
    *,
    attempt_started_at: str,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    output_tokens: int,
) -> CostBreakdown:
    """Actual cost for one attempt, settled by its start-time period."""
    for name, value in (
        ("cache_hit_tokens", cache_hit_tokens),
        ("cache_miss_tokens", cache_miss_tokens),
        ("output_tokens", output_tokens),
    ):
        if not isinstance(value, int) or value < 0:
            fail("INVALID_USAGE", f"{name} must be a non-negative integer")
    period = table.period_for(attempt_started_at)
    rates = table.rates(period)
    cache_hit_cost = _charge(cache_hit_tokens, rates["cache_hit"])
    cache_miss_cost = _charge(cache_miss_tokens, rates["cache_miss"])
    output_cost = _charge(output_tokens, rates["output"])
    total = _round_up_to_fen(cache_hit_cost + cache_miss_cost + output_cost)
    return CostBreakdown(
        cache_hit_cost_cny=_round_up_to_fen(cache_hit_cost),
        cache_miss_cost_cny=_round_up_to_fen(cache_miss_cost),
        output_cost_cny=_round_up_to_fen(output_cost),
        total_cny=total,
    )
