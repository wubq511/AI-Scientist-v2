from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import unicodedata

from .errors import IdeationInputError, fail


def _canonical_value(value: object, *, label: str) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        fail("NON_CANONICAL_JSON", f"{label} contains a floating-point value")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            fail("NON_CANONICAL_JSON", f"{label} contains a non-NFC string")
        for index, character in enumerate(value):
            if 0xD800 <= ord(character) <= 0xDFFF:
                fail(
                    "NON_CANONICAL_JSON",
                    f"{label} contains an unpaired surrogate",
                    index=index,
                )
        return value
    if isinstance(value, list):
        return [
            _canonical_value(item, label=f"{label}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                fail("NON_CANONICAL_JSON", f"{label} contains a non-string key")
            canonical_key = _canonical_value(key, label=f"{label}.key")
            assert isinstance(canonical_key, str)
            result[canonical_key] = _canonical_value(
                item, label=f"{label}.{canonical_key}"
            )
        return result
    fail(
        "NON_CANONICAL_JSON",
        f"{label} contains an unsupported value",
        value_type=type(value).__name__,
    )


def canonical_json_bytes(value: object) -> bytes:
    canonical = _canonical_value(value, label="document")
    try:
        text = json.dumps(
            canonical,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        fail("NON_CANONICAL_JSON", "Document cannot be serialized", error=str(exc))
    return (text + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("INVALID_JSON", "JSON object contains a duplicate key", key=key)
        result[key] = value
    return result


def parse_json_bytes(data: bytes, *, label: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", f"{label} is not valid UTF-8", offset=exc.start)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda constant: fail(
                "INVALID_JSON", f"{label} contains {constant}"
            ),
        )
    except IdeationInputError:
        raise
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_JSON",
            f"{label} is not valid JSON",
            line=exc.lineno,
            column=exc.colno,
        )
    _canonical_value(value, label=label)
    return value


def read_json(path: Path, *, label: str) -> tuple[object, bytes]:
    if not path.is_file():
        fail("MISSING_ARTIFACT", f"{label} is missing")
    data = path.read_bytes()
    return parse_json_bytes(data, label=label), data


def read_exact(path: Path, expected_sha256: str, *, label: str) -> bytes:
    if not path.is_file():
        fail("MISSING_ARTIFACT", f"{label} is missing")
    data = path.read_bytes()
    actual = sha256_bytes(data)
    if actual != expected_sha256:
        fail(
            "HASH_MISMATCH",
            f"{label} does not match its approved SHA-256",
            expected=expected_sha256,
            actual=actual,
        )
    return data


def workspace_relative_path(workspace_root: Path, value: object, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        fail("INVALID_PATH", f"{label} must be a non-empty relative POSIX path")
    if "\\" in value:
        fail("INVALID_PATH", f"{label} must use POSIX separators")
    if value != value.strip() or value.startswith("./") or value.endswith("/"):
        fail("INVALID_PATH", f"{label} must be normalized and workspace-relative")
    relative = Path(value)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        fail("INVALID_PATH", f"{label} must be normalized and workspace-relative")
    workspace = workspace_root.resolve(strict=True)
    resolved = (workspace / relative).resolve()
    if not resolved.is_relative_to(workspace):
        fail("PATH_ESCAPE", f"{label} escapes the workspace")
    current = workspace
    for part in relative.parts:
        current /= part
        if current.exists() and current.is_symlink():
            fail("SYMLINK_FORBIDDEN", f"{label} traverses a symlink")
    return resolved


def relative_posix(path: Path, workspace_root: Path) -> str:
    try:
        return (
            path.resolve().relative_to(workspace_root.resolve(strict=True)).as_posix()
        )
    except ValueError:
        fail("PATH_ESCAPE", "Artifact path escapes the workspace")


def write_tree_once(target: Path, files: dict[str, bytes]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        fail("ARTIFACT_EXISTS", "Immutable artifact already exists")
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent)
    )
    try:
        for relative_name, data in files.items():
            relative = Path(relative_name)
            if relative.is_absolute() or any(
                part in {"", ".", ".."} for part in relative.parts
            ):
                fail("INVALID_PATH", "Generated artifact path is invalid")
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            descriptor = os.open(path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        if target.exists():
            fail("ARTIFACT_EXISTS", "Immutable artifact already exists")
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
