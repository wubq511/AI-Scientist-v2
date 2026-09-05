"""Evaluation protocol manifest (ticket 03, comparison integration).

The manifest is the versioned amendment that lets the governed comparison
consume AI Evaluation Artifacts under the revised evaluation protocol: it
binds the review execution config (evaluators, prompt versions), the
material-package schema versions, the aggregation rules identity, and the
post-first-output disclosure into one write-once registration. The
pre-registered criteria of Proposal 002 (3-0 wins, domain-method fit,
quality floor, cost and regression thresholds) stay untouched: this manifest
only changes WHO may author the post-seal judgment, never what the gates
measure.

Fail-closed rules:

- One authoritative manifest per workspace, write-once (``ARTIFACT_EXISTS``);
  the amendment path archives old bytes, never deletes them.
- Registration requires the review execution config and re-verifies that
  every pinned prompt/schema version matches the code constants (drift is a
  contract violation, not a config choice).
- Every consumption point (comparison ingestion, pair-result derivation,
  reduction) re-loads the manifest and checks each AI record's embedded
  ``review_config_sha256`` against the manifest binding: cross-protocol
  merges fail closed (``EVALUATION_PROTOCOL_MISMATCH``).
- The manifest carries a required disclosure: this evaluation-protocol
  amendment was made after the first comparison output existed and must
  never be presented as a pre-registered human blind review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ai_review import _config_sha256, _load_review_config
from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import (
    EVALUATION_AI_PAIR_REDUCTION_SCHEMA_VERSION,
    EVALUATION_AI_PAIR_REVIEW_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_PAIR_REVIEW_RESPONSE_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_CONSENSUS_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION,
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION,
    EVALUATION_AI_REVIEW_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_RESPONSE_SCHEMA_VERSION,
    EVALUATION_AUTHORING_CONTRACT_VERSION,
    EVALUATION_PAIR_MATERIALS_SCHEMA_VERSION,
    EVALUATION_PAIR_PACKAGE_SCHEMA_VERSION,
    EVALUATION_REVIEW_MATERIALS_SCHEMA_VERSION,
    EVALUATION_REVIEW_PACKAGE_SCHEMA_VERSION,
    EVALUATION_REVIEW_RESPONSE_IMPORT_SCHEMA_VERSION,
    EVALUATION_ROOT_RELPATH,
    EVALUATION_RUBRIC_SCHEMA_VERSION,
    _now,
)
from .errors import fail
from .evaluation import _write_bytes_once
from .run_store import _fsync_directory
from .schema import closed_object, nonempty_string

PROTOCOL_MANIFEST_SCHEMA_VERSION = "evaluation-protocol-manifest-v1.0.0"
PROTOCOL_MANIFEST_NAME = "evaluation-protocol-manifest.json"
PROTOCOL_ID = "ai-review-evaluation-protocol-v1"
AGGREGATION_RULES_ID = "ai-review-aggregation-v1"
EVALUATION_PROTOCOL_REVISION_STATEMENT = (
    "post-first-output evaluation-protocol revision: the scoring role moves "
    "from Robert-only human artifacts to identified-author AI review records; "
    "pre-registered criteria are unchanged. Not a pre-registered human blind "
    "review and not independent scientific verification."
)

# The exact schema-version bundle the manifest pins: every schema the AI
# evaluation path produces must match these values at registration, so a
# manifest registered by different evaluation code cannot silently widen the
# consumed contract.
_MANIFEST_SCHEMA_PIN_KEYS = {
    "ai_pair_reduction_record",
    "ai_pair_review_record",
    "ai_pair_review_response",
    "ai_review_consensus_record",
    "ai_review_record",
    "ai_review_response",
    "pair_materials",
    "pair_package",
    "review_import_record",
    "review_materials",
    "review_package",
}

_PROTOCOL_PINNED_SCHEMAS = {
    "ai_pair_reduction_record": EVALUATION_AI_PAIR_REDUCTION_SCHEMA_VERSION,
    "ai_pair_review_record": EVALUATION_AI_PAIR_REVIEW_RECORD_SCHEMA_VERSION,
    "ai_pair_review_response": EVALUATION_AI_PAIR_REVIEW_RESPONSE_SCHEMA_VERSION,
    "ai_review_consensus_record": EVALUATION_AI_REVIEW_CONSENSUS_RECORD_SCHEMA_VERSION,
    "ai_review_record": EVALUATION_AI_REVIEW_RECORD_SCHEMA_VERSION,
    "ai_review_response": EVALUATION_AI_REVIEW_RESPONSE_SCHEMA_VERSION,
    "pair_materials": EVALUATION_PAIR_MATERIALS_SCHEMA_VERSION,
    "pair_package": EVALUATION_PAIR_PACKAGE_SCHEMA_VERSION,
    "review_import_record": EVALUATION_REVIEW_RESPONSE_IMPORT_SCHEMA_VERSION,
    "review_materials": EVALUATION_REVIEW_MATERIALS_SCHEMA_VERSION,
    "review_package": EVALUATION_REVIEW_PACKAGE_SCHEMA_VERSION,
}

_MANIFEST_KEYS = {
    "abstention_policy",
    "aggregation_rules_id",
    "authoring_contract_version",
    "evaluator_binding_sha256",
    "material_schema_versions",
    "prompt_versions",
    "protocol_id",
    "registered_at",
    "registered_by",
    "revision_disclosure",
    "rubric_schema_version",
    "schema_version",
}


def _pinned_schema_bundle() -> dict[str, str]:
    return dict(sorted(_PROTOCOL_PINNED_SCHEMAS.items()))


def register_evaluation_protocol(
    workspace_root: Path,
    manifest_path: Path,
    *,
    registered_by: str,
) -> dict[str, Any]:
    """Validate and register the write-once evaluation protocol manifest.

    Registration re-derives every pinned version from the running code and
    the registered review execution config, so a manifest cannot be committed
    against drifting templates or an absent/foreign evaluator binding.
    A second registration archives the old bytes (amendment path), never
    deletes them.
    """
    registered_by = nonempty_string(registered_by, label="registered_by")
    workspace = workspace_root.resolve(strict=True)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        fail("INVALID_INPUT", f"Manifest file is missing: {manifest_path}")
    value = parse_json_bytes(manifest_path.read_bytes(), label="protocol manifest")
    manifest = _check_manifest_document(value, at_registration=True)
    root = workspace / EVALUATION_ROOT_RELPATH
    if root.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The evaluations root is a symlink")
    try:
        root.mkdir(parents=True, exist_ok=True)
        _fsync_directory(root)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create evaluations root: {detail}")
    target = root / PROTOCOL_MANIFEST_NAME
    archived: dict[str, str] | None = None
    if target.is_file():
        archive_name = (
            "evaluation-protocol-manifest-archived-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        archive_path = root / archive_name
        target.rename(archive_path)
        _fsync_directory(root)
        archived = {
            "file": EVALUATION_ROOT_RELPATH.joinpath(archive_name).as_posix(),
            "sha256": sha256_bytes(archive_path.read_bytes()),
        }
    document = dict(manifest)
    document["registered_at"] = _now()
    document["registered_by"] = registered_by
    document_bytes = canonical_json_bytes(document)
    _write_bytes_once(target, document_bytes, label=PROTOCOL_MANIFEST_NAME)
    result = {
        "manifest": EVALUATION_ROOT_RELPATH.joinpath(PROTOCOL_MANIFEST_NAME).as_posix(),
        "manifest_sha256": sha256_bytes(document_bytes),
        "protocol_id": document["protocol_id"],
        "status": "registered",
    }
    if archived is not None:
        result["archived_manifest"] = archived
    return result


def _check_manifest_document(value: object, *, at_registration: bool) -> dict[str, Any]:
    """Closed validation of the manifest; registration pins derive from code."""
    manifest = closed_object(
        value, label="evaluation protocol manifest", keys=_MANIFEST_KEYS
    )
    if manifest["schema_version"] != PROTOCOL_MANIFEST_SCHEMA_VERSION:
        fail(
            "UNSUPPORTED_SCHEMA",
            "Unsupported evaluation protocol manifest schema_version: "
            f"{manifest['schema_version']}",
        )
    if manifest["protocol_id"] != PROTOCOL_ID:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The manifest binds an unknown evaluation protocol id",
            expected=PROTOCOL_ID,
            actual=manifest["protocol_id"],
        )
    if manifest["authoring_contract_version"] != EVALUATION_AUTHORING_CONTRACT_VERSION:
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            "The manifest binds another authoring contract version",
        )
    if manifest["aggregation_rules_id"] != AGGREGATION_RULES_ID:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The manifest binds an unknown aggregation-rules identity",
            expected=AGGREGATION_RULES_ID,
            actual=manifest["aggregation_rules_id"],
        )
    if manifest["rubric_schema_version"] != EVALUATION_RUBRIC_SCHEMA_VERSION:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The manifest binds another rubric schema version",
        )
    if manifest["revision_disclosure"] != EVALUATION_PROTOCOL_REVISION_STATEMENT:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The manifest must carry the exact post-first-output revision "
            "disclosure; a different wording is not the approved amendment",
        )
    abstention = manifest["abstention_policy"]
    if not isinstance(abstention, dict) or set(abstention) != {
        "coverage_states",
        "unresolved_blocks_quality_pass",
    }:
        fail(
            "INVALID_SCHEMA",
            "The manifest abstention_policy must fix the coverage vocabulary "
            "and the unresolved-blocks-quality-pass rule",
        )
    coverage_states = manifest["abstention_policy"]["coverage_states"]
    if set(coverage_states or []) != {
        "missing",
        "invalid",
        "complete_resolved",
        "complete_unresolved",
    }:
        fail(
            "INVALID_SCHEMA",
            "The manifest must fix the four-state coverage vocabulary",
        )
    if manifest["abstention_policy"]["unresolved_blocks_quality_pass"] is not True:
        fail(
            "INVALID_SCHEMA",
            "The manifest must keep complete_unresolved from producing a "
            "quality pass",
        )
    prompt_versions = closed_object(
        manifest["prompt_versions"],
        label="manifest.prompt_versions",
        keys={"pair", "single"},
    )
    if at_registration:
        if (
            prompt_versions["single"] != EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION
            or prompt_versions["pair"] != EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION
        ):
            fail(
                "REVIEW_CONTRACT_MISMATCH",
                "The manifest pins unapproved prompt versions",
            )
        schemas = closed_object(
            manifest["material_schema_versions"],
            label="manifest.material_schema_versions",
            keys=_MANIFEST_SCHEMA_PIN_KEYS,
        )
        expected = _pinned_schema_bundle()
        if schemas != expected:
            drifted = sorted(
                key for key in expected if schemas.get(key) != expected[key]
            )
            fail(
                "EVALUATION_PROTOCOL_MISMATCH",
                "The manifest pins material schema versions that differ from "
                "the running evaluation code",
                drifted=drifted,
            )
    return manifest


def load_evaluation_protocol(workspace_root: Path) -> dict[str, Any]:
    """Load the registered manifest and re-verify its binding hash.

    The evaluator binding hash must equal the review execution config's
    current hash: the manifest cannot stay loadable after the config is
    superseded — that would let records from two protocols merge.
    """
    workspace = workspace_root.resolve(strict=True)
    path = workspace / EVALUATION_ROOT_RELPATH / PROTOCOL_MANIFEST_NAME
    if path.is_symlink() or not path.is_file():
        fail(
            "EVALUATION_PROTOCOL_NOT_FOUND",
            "No registered evaluation protocol manifest; run evaluation "
            "register-evaluation-protocol first",
        )
    value = parse_json_bytes(path.read_bytes(), label="evaluation protocol manifest")
    manifest = _check_manifest_document(value, at_registration=False)
    binding_sha = _config_sha256(workspace)
    if manifest["evaluator_binding_sha256"] != binding_sha:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The manifest's evaluator binding differs from the registered "
            "review execution config",
            expected=manifest["evaluator_binding_sha256"],
            actual=binding_sha,
        )
    return manifest


def build_evaluation_protocol_manifest(workspace_root: Path) -> dict[str, Any]:
    """Derive a manifest skeleton over the workspace's registered config.

    Everything pinned is taken from the running code and the registered
    review execution config; callers only file it. This makes the intended
    manifest a deterministic artifact instead of hand-copied constants.
    """
    workspace = workspace_root.resolve(strict=True)
    config = _load_review_config(workspace)
    if (
        config["prompt_versions"]["single"]
        != EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION
        or config["prompt_versions"]["pair"] != EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION
    ):
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            "The registered review execution config pins prompt versions the "
            "running code does not approve",
        )
    return {
        "abstention_policy": {
            "coverage_states": [
                "complete_resolved",
                "complete_unresolved",
                "invalid",
                "missing",
            ],
            "unresolved_blocks_quality_pass": True,
        },
        "aggregation_rules_id": AGGREGATION_RULES_ID,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "evaluator_binding_sha256": _config_sha256(workspace),
        "material_schema_versions": _pinned_schema_bundle(),
        "prompt_versions": {
            "pair": EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION,
            "single": EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION,
        },
        "protocol_id": PROTOCOL_ID,
        "registered_at": None,
        "registered_by": None,
        "revision_disclosure": EVALUATION_PROTOCOL_REVISION_STATEMENT,
        "rubric_schema_version": EVALUATION_RUBRIC_SCHEMA_VERSION,
        "schema_version": PROTOCOL_MANIFEST_SCHEMA_VERSION,
    }
