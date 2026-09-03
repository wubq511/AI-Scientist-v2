"""Versioned CNY pricing for DeepSeek preflight cost bounds (ticket 04).

The price table is a tracked, version-managed file registered once with
Robert's approval; preflight pins its SHA-256 into the Run Admission. All
amounts are exact decimals computed from token counts and the table rates,
rounded up to the nearest fen (0.01 CNY). A missing or hash-mismatched
table fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

from .canonical import parse_json_bytes, sha256_bytes
from .errors import fail

PRICE_TABLE_RELPATH = Path(
    "ai_scientist/ideation/policies/deepseek-cny-price-table-v1.json"
)
# Registered with Robert's approval on 2026-09-03; official repricing
# requires a new table version and a fresh approval.
PRICE_TABLE_SHA256 = "f02bab04f210a7cab755ae0ccb027920570cc17ad3d146cec38167ac3a8c77fd"

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


@dataclass(frozen=True, slots=True)
class PriceTable:
    document: dict[str, Any]
    sha256: str

    def period_for(self, started_at: str) -> str:
        """Classify an attempt-start timestamp as `peak` or `off_peak`."""
        parsed = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=UTC
        )
        weekday = parsed.strftime("%a").lower()
        if weekday not in PEAK_DAYS:
            return "off_peak"
        minutes = parsed.hour * 60 + parsed.minute
        for window in self.document["peak_windows_utc"]:
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

    The declared `input_tokens` is the per-attempt worst-case input (all
    charged at the peak cache-miss rate); `output_tokens` is the explicit
    per-attempt output budget; `attempts` is the declared attempt ceiling
    (<= 2 per the adapter contract).
    """
    if input_tokens < 0 or output_tokens < 0:
        fail("INVALID_BUDGET", "Token budgets must be non-negative integers")
    if attempts < 1 or attempts > 2:
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
