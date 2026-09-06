from __future__ import annotations

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.normalization import normalize_query


def test_lexical_normalization_v1_golden_tokens() -> None:
    query = normalize_query("  COVID–19 C++ C# O’Reilly Straße e\u0301 2026 🤖  ")

    assert query.normalized == "covid-19 c++ c# o'reilly strasse é 2026 🤖"
    assert query.tokens == (
        "covid-19",
        "c++",
        "c#",
        "o'reilly",
        "strasse",
        "é",
        "2026",
    )


def test_normalization_preserves_repeated_terms() -> None:
    assert normalize_query("Alpha alpha beta").tokens == ("alpha", "alpha", "beta")


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("   ", "INVALID_QUERY"),
        ("🤖", "INVALID_QUERY"),
        ("x" * 257, "QUERY_TOO_LONG"),
        ("bad\ud800value", "INVALID_UNICODE"),
    ],
)
def test_query_validation_fails_closed(value: str, code: str) -> None:
    with pytest.raises(HarnessError) as raised:
        normalize_query(value)

    assert raised.value.code == code


def test_non_string_query_is_rejected() -> None:
    with pytest.raises(HarnessError, match="INVALID_QUERY"):
        normalize_query(123)  # type: ignore[arg-type]
