"""Versioned CNY price table and deterministic preflight cost estimates.

Covers VM-UNIT-06: versioned price table lookups by attempt-start period,
conservative worst-case bounds, and fail-closed behavior for a missing or
hash-mismatched table.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from ai_scientist.ideation import pricing
from ai_scientist.ideation.errors import IdeationInputError

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "case-0123456789abcdef0123456789abcdef"


def test_repo_price_table_is_loadable_and_hash_pinned() -> None:
    table = pricing.load_price_table(REPO_ROOT)
    assert table.document["model_id"] == "deepseek-v4-pro"
    assert table.sha256 == pricing.expected_price_table_sha256()


def test_estimate_uses_peak_rates_all_miss_and_two_attempts() -> None:
    table = pricing.load_price_table(REPO_ROOT)
    # 1M tokens input, 100k tokens output, 2 attempts -> worst case bound.
    estimate = pricing.worst_case_bound(
        table,
        input_tokens=1_000_000,
        output_tokens=100_000,
        attempts=2,
    )
    # peak cache-miss 9.0 CNY/1M and output 27.0 CNY/1M per attempt:
    # (1_000_000/1M * 9.0 + 100_000/1M * 27.0) * 2 = 23.4 CNY
    assert estimate.total_cny == Decimal("23.40")
    assert estimate.cache_miss_cost_cny == Decimal("18.00")
    assert estimate.output_cost_cny == Decimal("5.40")
    assert estimate.cache_hit_cost_cny == Decimal("0.00")


def test_attempt_period_classification_follows_the_table_windows() -> None:
    table = pricing.load_price_table(REPO_ROOT)
    # Wednesday 2026-09-02: peak windows are 01:00-04:00 and 06:00-10:00 UTC.
    assert table.period_for("2026-09-02T02:30:00.000000Z") == "peak"
    assert table.period_for("2026-09-02T04:30:00.000000Z") == "off_peak"
    assert table.period_for("2026-09-02T06:00:00.000000Z") == "peak"
    assert table.period_for("2026-09-02T10:00:00.000000Z") == "off_peak"
    assert table.period_for("2026-09-02T23:59:59.999999Z") == "off_peak"
    # Sunday is always off-peak.
    assert table.period_for("2026-09-06T02:30:00.000000Z") == "off_peak"


def test_attempt_cost_uses_attempt_start_period() -> None:
    table = pricing.load_price_table(REPO_ROOT)
    # A peak-start attempt billed with peak rates even if it ends off-peak.
    cost = pricing.attempt_cost(
        table,
        attempt_started_at="2026-09-02T02:00:00.000000Z",
        cache_hit_tokens=100_000,
        cache_miss_tokens=400_000,
        output_tokens=50_000,
    )
    # peak cache-hit 0.30, cache-miss 9.0, output 27.0 CNY/1M tokens:
    # (0.1 * 0.30 + 0.4 * 9.0 + 0.05 * 27.0) = 4.98 CNY
    assert cost.total_cny == Decimal("4.98")


def test_costs_round_up_to_the_nearest_fen() -> None:
    table = pricing.load_price_table(REPO_ROOT)
    cost = pricing.attempt_cost(
        table,
        attempt_started_at="2026-09-02T02:00:00.000000Z",
        cache_hit_tokens=1,
        cache_miss_tokens=1,
        output_tokens=1,
    )
    assert cost.total_cny == Decimal("0.01")


def test_missing_price_table_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(IdeationInputError, match="MISSING_PRICE_TABLE"):
        pricing.load_price_table(tmp_path)


def test_hash_mismatched_price_table_fails_closed(tmp_path: Path) -> None:
    source = REPO_ROOT / pricing.PRICE_TABLE_RELPATH
    target = tmp_path / pricing.PRICE_TABLE_RELPATH
    target.parent.mkdir(parents=True)
    tampered = source.read_bytes().replace(b"9.0", b"9.1")
    target.write_bytes(tampered)
    with pytest.raises(IdeationInputError, match="PRICE_TABLE_HASH_MISMATCH"):
        pricing.load_price_table(tmp_path)
