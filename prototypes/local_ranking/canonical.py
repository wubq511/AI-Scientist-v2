from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .errors import fail


def canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        fail(
            "NON_CANONICAL_JSON",
            "Value cannot be serialized canonically",
            error=str(exc),
        )
    return (text + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_exact_bytes(path: Path, expected_sha256: str, *, label: str) -> bytes:
    if not path.is_file():
        fail("MISSING_ARTIFACT", f"{label} is not a regular file", path=str(path))
    data = path.read_bytes()
    actual = sha256_bytes(data)
    if actual != expected_sha256:
        fail(
            "HASH_MISMATCH",
            f"{label} SHA-256 does not match the frozen protocol",
            expected=expected_sha256,
            actual=actual,
        )
    return data


def parse_json_bytes(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", f"{label} is not valid UTF-8", offset=exc.start)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_JSON",
            f"{label} is not valid JSON",
            line=exc.lineno,
            column=exc.colno,
        )


def resolve_repo_relative(base: Path, value: str, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        fail("INVALID_PATH", f"{label} must be a non-empty relative POSIX path")
    if "\\" in value:
        fail("INVALID_PATH", f"{label} must use POSIX separators")
    raw = Path(value)
    if raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
        fail(
            "INVALID_PATH",
            f"{label} must be normalized and repository-relative",
            path=value,
        )
    resolved_base = base.resolve()
    resolved = (resolved_base / raw).resolve()
    if not resolved.is_relative_to(resolved_base):
        fail("PATH_ESCAPE", f"{label} escapes the repository root", path=value)
    current = resolved_base
    for part in raw.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            fail("SYMLINK_FORBIDDEN", f"{label} traverses a symlink", path=value)
    return resolved


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        fail(
            "ARTIFACT_EXISTS",
            "Immutable prototype artifact already exists",
            path=str(path),
        )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:  # noqa: BLE001
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


def write_json_once(path: Path, value: Any) -> None:
    write_once(path, canonical_json_bytes(value))


def write_identical_or_once(path: Path, data: bytes) -> None:
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            fail(
                "ARTIFACT_CONFLICT",
                "Existing immutable artifact differs",
                path=str(path),
            )
        return
    write_once(path, data)


def write_json_identical_or_once(path: Path, value: Any) -> None:
    write_identical_or_once(path, canonical_json_bytes(value))
