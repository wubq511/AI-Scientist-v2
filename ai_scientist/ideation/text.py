from __future__ import annotations

import re
import unicodedata

from .errors import fail

NORMALIZATION_VERSION = "ideation-text-normalization-v1.0"
TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*(?:\+{1,2}|#)?", re.UNICODE)
APOSTROPHES = {"\u2018", "\u2019", "\u02bc"}


def _validate_scalar_string(value: str, *, label: str) -> None:
    for index, character in enumerate(value):
        if 0xD800 <= ord(character) <= 0xDFFF:
            fail(
                "INVALID_UNICODE",
                f"{label} contains an unpaired surrogate",
                index=index,
            )


def normalize_text(value: object, *, label: str = "text") -> str:
    if not isinstance(value, str):
        fail("INVALID_TEXT", f"{label} must be a string")
    _validate_scalar_string(value, label=label)
    normalized = unicodedata.normalize("NFC", value).casefold()
    translated: list[str] = []
    for character in normalized:
        if unicodedata.category(character) == "Pd":
            translated.append("-")
        elif character in APOSTROPHES:
            translated.append("'")
        else:
            translated.append(character)
    return " ".join("".join(translated).split())


def tokenize_text(value: object, *, label: str = "text") -> tuple[str, ...]:
    normalized = normalize_text(value, label=label)
    return tuple(match.group(0) for match in TOKEN_PATTERN.finditer(normalized))
