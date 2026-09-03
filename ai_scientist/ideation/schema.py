from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .errors import fail

CASE_ID_PATTERN = re.compile(r"case-[0-9a-f]{32}\Z")
STAGE_ID_PATTERN = re.compile(r"(?=.{1,64}\Z)[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
TIMESTAMP_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")


def closed_object(value: object, *, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("INVALID_SCHEMA", f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        fail("INVALID_SCHEMA", f"{label} keys must be strings")
    unknown = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    if unknown or missing:
        fail(
            "INVALID_SCHEMA",
            f"{label} has an invalid closed schema",
            unknown=unknown,
            missing=missing,
        )
    return value


def nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        fail("INVALID_SCHEMA", f"{label} must be a non-empty string")
    return value


def boolean(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        fail("INVALID_SCHEMA", f"{label} must be boolean")
    return value


def positive_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        fail("INVALID_SCHEMA", f"{label} must be a positive integer")
    return value


def string_list(value: object, *, label: str, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        fail("INVALID_SCHEMA", f"{label} must be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(nonempty_string(item, label=f"{label}[{index}]"))
    return result


def case_id(value: object, *, label: str = "case_id") -> str:
    parsed = nonempty_string(value, label=label)
    if not CASE_ID_PATTERN.fullmatch(parsed):
        fail(
            "INVALID_SCHEMA",
            f"{label} must be an opaque case identifier",
        )
    return parsed


def stage_id(value: object, *, label: str) -> str:
    parsed = nonempty_string(value, label=label)
    if not STAGE_ID_PATTERN.fullmatch(parsed):
        fail("INVALID_SCHEMA", f"{label} must be a canonical stage identifier")
    return parsed


def sha256(value: object, *, label: str) -> str:
    parsed = nonempty_string(value, label=label)
    if not SHA256_PATTERN.fullmatch(parsed):
        fail("INVALID_SCHEMA", f"{label} must be a lowercase SHA-256 digest")
    return parsed


def timestamp(value: object, *, label: str) -> str:
    parsed = nonempty_string(value, label=label)
    if not TIMESTAMP_PATTERN.fullmatch(parsed):
        fail("INVALID_SCHEMA", f"{label} must be a canonical UTC timestamp")
    try:
        datetime_value = datetime.strptime(parsed, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        fail("INVALID_SCHEMA", f"{label} must be a real UTC timestamp")
    if datetime_value.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != parsed:
        fail("INVALID_SCHEMA", f"{label} must be a canonical UTC timestamp")
    return parsed
