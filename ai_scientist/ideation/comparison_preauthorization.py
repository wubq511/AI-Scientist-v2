"""Robert's batch pre-authorization for frozen comparison slots.

The interactive per-run `yes` remains the default production approval path.
Robert may instead grant, in one explicit decision, a write-once batch
pre-authorization covering named matrix slots: a document in the comparison
package that binds the matrix bytes, the exact (case_id, prompt_profile_id)
slot identities, a per-run worst-case CNY ceiling, the approver, and the
decision timestamp. The admission boundary verifies the covering entry for
its own slot before any paid work and records the authorization provenance
verbatim into the Run Admission; every non-covered slot keeps requiring the
interactive `yes`. Nothing here waives reservation, Plan Gate, hard-cap, or
ledger arithmetic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .errors import fail
from .schema import closed_object, nonempty_string

COMPARISON_PREAUTHORIZATION_SCHEMA_VERSION = "comparison-preauthorization-v1.0.0"
PREAUTHORIZATION_ENV_VAR = "COMPARISON_PREAUTHORIZATION"
PREAUTHORIZATION_NAME = "run-preauthorization.json"


def build_preauthorization_document(
    *,
    matrix_sha256: str,
    slots: list[dict[str, Any]],
    approved_by: str,
    approved_at: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Derive the document Robert's approval decision is recorded into.

    `slots` carries one entry per covered matrix slot: `run_index`,
    `case_id`, `prompt_profile_id`, and `worst_case_bound_cny`. The doc is
    a pure record; registration happens against the live package bytes.
    """
    if len(matrix_sha256) != 64:
        fail("INVALID_INPUT", "The preauthorization lacks the matrix sha256")
    if not slots:
        fail("INVALID_INPUT", "A preauthorization must cover at least one slot")
    covered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for slot in slots:
        record = closed_object(
            slot,
            label="preauthorization slot",
            keys={"run_index", "case_id", "prompt_profile_id", "worst_case_bound_cny"},
        )
        run_index = record["run_index"]
        if (
            not isinstance(run_index, int)
            or isinstance(run_index, bool)
            or run_index < 1
        ):
            fail("INVALID_INPUT", "A preauthorization slot needs a positive run index")
        if run_index in seen:
            fail(
                "INVALID_INPUT",
                "A preauthorization covers a slot twice",
                run_index=run_index,
            )
        seen.add(run_index)
        nonempty_string(record["case_id"], label="preauthorization case_id")
        nonempty_string(record["prompt_profile_id"], label="preauthorization profile")
        covered.append(dict(record))
    covered.sort(key=lambda item: item["run_index"])
    document: dict[str, Any] = {
        "approved_at": approved_at,
        "approved_by": approved_by,
        "matrix_sha256": matrix_sha256,
        "schema_version": COMPARISON_PREAUTHORIZATION_SCHEMA_VERSION,
        "slots": covered,
    }
    if note is not None:
        nonempty_string(note, label="preauthorization note")
        document["note"] = note
    return document


def write_preauthorization(
    package_dir: Path,
    document: dict[str, Any],
) -> tuple[Path, str]:
    """Write-once the preauthorization inside the comparison package."""
    from .comparison import _write_bytes_once

    package = package_dir.resolve(strict=True)
    if not (package / "run-matrix.json").is_file():
        fail("COMPARISON_PACKAGE_INCOMPLETE", "The package lacks its run matrix")
    path = package / PREAUTHORIZATION_NAME
    digest = _write_bytes_once(
        path,
        canonical_json_bytes(document),
        label="run preauthorization",
        exists_code="ARTIFACT_EXISTS",
    )
    return path, digest


def covering_preauthorization(
    *,
    case_id: str,
    prompt_profile_id: str,
    worst_case_bound_cny: str,
) -> dict[str, Any] | None:
    """The covering slot's authorization record, or None when unset.

    The environment variable names the write-once document; a missing
    variable means the interactive `yes` path stays in charge. A variable
    pointing at a missing or malformed document fails closed — an operator
    mistake must stop the run, never silently fall back to prompting.
    """
    raw = os.environ.get(PREAUTHORIZATION_ENV_VAR)
    if raw is None or raw == "":
        return None
    path = Path(raw)
    if path.is_symlink() or not path.is_file():
        fail(
            "PREAUTHORIZATION_UNREADABLE",
            "The preauthorization environment variable points at a missing file",
            path=str(path),
        )
    value = parse_json_bytes(path.read_bytes(), label="run preauthorization")
    required_keys = {
        "approved_at",
        "approved_by",
        "matrix_sha256",
        "schema_version",
        "slots",
    }
    if not isinstance(value, dict) or sorted(value) not in (
        sorted(required_keys),
        sorted(required_keys | {"note"}),
    ):
        fail(
            "INVALID_SCHEMA",
            "The preauthorization document has an invalid closed schema",
        )
    document = value
    if document["schema_version"] != COMPARISON_PREAUTHORIZATION_SCHEMA_VERSION:
        fail(
            "UNSUPPORTED_SCHEMA",
            "Unsupported preauthorization schema_version",
            schema_version=document["schema_version"],
        )
    # The matrix binding is an audit field of the document (the frozen
    # commands carry the matrix hash themselves); the runtime check matches
    # the slot identity, which a single-variable matrix makes unique.
    for slot in document["slots"]:
        record = closed_object(
            slot,
            label="preauthorization slot",
            keys={"run_index", "case_id", "prompt_profile_id", "worst_case_bound_cny"},
        )
        if (
            record["case_id"] == case_id
            and record["prompt_profile_id"] == prompt_profile_id
        ):
            if record["worst_case_bound_cny"] != worst_case_bound_cny:
                fail(
                    "PREAUTHORIZATION_CEILING_DRIFT",
                    "The preauthorization's worst-case ceiling disagrees with "
                    "the admission's recomputed bound",
                    authorized=record["worst_case_bound_cny"],
                    recomputed=worst_case_bound_cny,
                )
            return {
                "approved_at": document["approved_at"],
                "approved_by": document["approved_by"],
                "confirmed_with": "batch_preauthorization",
                "document_sha256": sha256_bytes(path.read_bytes()),
                "note": document.get("note"),
                "total_upper_bound_cny": worst_case_bound_cny,
            }
    fail(
        "PREAUTHORIZATION_SLOT_NOT_COVERED",
        "The preauthorization does not cover this matrix slot",
        case_id=case_id,
        prompt_profile_id=prompt_profile_id,
    )


def preauthorization_admission_field(authorization: dict[str, Any]) -> dict[str, Any]:
    """The admission's `cost.approval` record for a batch-authorized run."""
    return {
        "approved_at": authorization["approved_at"],
        "approved_by": authorization["approved_by"],
        "confirmed_with": "batch_preauthorization",
        "preauthorization_document_sha256": authorization["document_sha256"],
        "note": authorization["note"],
        "total_upper_bound_cny": authorization["total_upper_bound_cny"],
    }


__all__ = [
    "PREAUTHORIZATION_ENV_VAR",
    "PREAUTHORIZATION_NAME",
    "COMPARISON_PREAUTHORIZATION_SCHEMA_VERSION",
    "build_preauthorization_document",
    "covering_preauthorization",
    "preauthorization_admission_field",
    "write_preauthorization",
]
