from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from . import NORMALIZATION_VERSION
from .errors import fail

TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*(?:\+{1,2}|#)?", re.UNICODE)
APOSTROPHES = {"\u2018", "\u2019", "\u02bc"}
MAX_QUERY_SCALARS = 256


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    version: str = NORMALIZATION_VERSION


def _validate_scalar_string(value: str, *, label: str) -> None:
    for index, char in enumerate(value):
        if 0xD800 <= ord(char) <= 0xDFFF:
            fail(
                "INVALID_UNICODE",
                f"{label} contains an unpaired surrogate",
                index=index,
            )


def normalize_text(value: str, *, label: str = "text") -> str:
    if not isinstance(value, str):
        fail("INVALID_TEXT", f"{label} must be a string")
    _validate_scalar_string(value, label=label)
    normalized = unicodedata.normalize("NFC", value).casefold()
    translated: list[str] = []
    for char in normalized:
        if unicodedata.category(char) == "Pd":
            translated.append("-")
        elif char in APOSTROPHES:
            translated.append("'")
        else:
            translated.append(char)
    return " ".join("".join(translated).split())


def tokenize_normalized(value: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in TOKEN_PATTERN.finditer(value))


def tokenize_text(value: str, *, label: str = "text") -> tuple[str, ...]:
    return tokenize_normalized(normalize_text(value, label=label))


def normalize_query(value: str) -> NormalizedQuery:
    if not isinstance(value, str):
        fail("INVALID_QUERY", "query must be a string")
    _validate_scalar_string(value, label="query")
    trimmed = value.strip()
    if not trimmed:
        fail("INVALID_QUERY", "query must be non-empty after trimming")
    if len(trimmed) > MAX_QUERY_SCALARS:
        fail(
            "QUERY_TOO_LONG",
            "query exceeds the lexical_normalization_v1 scalar limit",
            maximum=MAX_QUERY_SCALARS,
            actual=len(trimmed),
        )
    normalized = normalize_text(trimmed, label="query")
    tokens = tokenize_normalized(normalized)
    if not tokens:
        fail("INVALID_QUERY", "query contains no searchable tokens after normalization")
    return NormalizedQuery(raw=value, normalized=normalized, tokens=tokens)
