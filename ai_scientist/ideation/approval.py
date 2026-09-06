from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import (
    canonical_json_bytes,
    read_json,
    relative_posix,
    sha256_bytes,
    workspace_relative_path,
    write_tree_once,
)
from .contract import (
    SOURCE_ALLOWLIST,
    WORKSHOP_CONTRACT_VERSION,
    WORKSHOP_MANIFEST_SCHEMA_VERSION,
    WORKSHOP_RESOLUTION_SCHEMA_VERSION,
    WORKSHOP_VALIDATOR_VERSION,
    _artifact_ref,
    _now,
)
from .errors import fail
from .preparation import _frozen_preparation_binding
from .validation import (
    _approved_resolution_exists,
    _load_attempt,
    _parse_semantic_decision,
)


def _attempt_history(
    workspace: Path,
    case_root: Path,
    *,
    current_attempt_id: str,
    current_decision: dict[str, Any],
    frozen_preparation: dict[str, Any],
) -> list[dict[str, Any]]:
    attempts_root = case_root / "attempts"
    history: list[dict[str, Any]] = []
    for attempt_root in sorted(attempts_root.iterdir(), key=lambda path: path.name):
        if attempt_root.name.startswith("."):
            continue
        if not attempt_root.is_dir() or attempt_root.is_symlink():
            fail("INVALID_ARTIFACT", "Workshop attempt inventory is invalid")
        manifest_path = attempt_root / "attempt-manifest.json"
        loaded = _load_attempt(workspace, manifest_path)
        attempt = loaded.attempt
        manifest_bytes = loaded.manifest_bytes
        derivation = loaded.derivation
        if attempt["case_id"] != case_root.name:
            fail("IDENTITY_MISMATCH", "Attempt inventory crosses case boundaries")
        if _frozen_preparation_binding(
            loaded.preparation
        ) != _frozen_preparation_binding(frozen_preparation):
            fail(
                "FROZEN_SOURCE_MISMATCH",
                "Workshop attempts do not share one frozen source binding",
            )
        report = loaded.report
        semantic_status = "not_run"
        semantic_review: dict[str, Any] | None = None
        resolution_path = attempt_root / "resolution/semantic-decision.json"
        if attempt["attempt_id"] == current_attempt_id:
            semantic_status = current_decision["decision"]
            semantic_review = {
                "decision_sha256": sha256_bytes(canonical_json_bytes(current_decision)),
                "rationale": current_decision["rationale"],
                "reviewed_at": current_decision["reviewed_at"],
                "reviewer": current_decision["reviewer"],
            }
        elif resolution_path.is_file():
            previous_decision, previous_decision_bytes = read_json(
                resolution_path, label="semantic decision"
            )
            parsed_decision = _parse_semantic_decision(previous_decision)
            if (
                parsed_decision["attempt_manifest_sha256"]
                != sha256_bytes(manifest_bytes)
                or parsed_decision["candidate_sha256"] != attempt["candidate"]["sha256"]
                or parsed_decision["case_id"] != attempt["case_id"]
            ):
                fail("HASH_MISMATCH", "Prior semantic decision binding is invalid")
            if parsed_decision["reviewer"] == derivation["actor"]:
                fail(
                    "REVIEW_NOT_INDEPENDENT",
                    "Prior Workshop reviewer was not independent",
                )
            if parsed_decision["reviewed_at"] <= derivation["completed_at"]:
                fail("INVALID_REVIEW", "Prior semantic review predates derivation")
            semantic_status = parsed_decision["decision"]
            semantic_review = {
                "decision_sha256": sha256_bytes(previous_decision_bytes),
                "rationale": parsed_decision["rationale"],
                "reviewed_at": parsed_decision["reviewed_at"],
                "reviewer": parsed_decision["reviewer"],
            }
        elif (attempt_root / "resolution").exists():
            fail("MISSING_ARTIFACT", "Prior Workshop resolution is incomplete")
        elif report["deterministic_status"] == "pass":
            semantic_status = "pending_independent_review"
        history.append(
            {
                "attempt_id": attempt["attempt_id"],
                "attempt_manifest_sha256": sha256_bytes(manifest_bytes),
                "candidate": attempt["candidate"],
                "created_at": attempt["created_at"],
                "derivation": {
                    **derivation,
                    "record_sha256": attempt["derivation_record"]["sha256"],
                },
                "semantic_review": semantic_review,
                "semantic_status": semantic_status,
                "validation": {
                    "deterministic_status": report["deterministic_status"],
                    "failures": report["failures"],
                    "normalization_version": report["normalization_version"],
                    "policy_sha256": report["policy_sha256"],
                    "policy_version": report["policy_version"],
                    "report_sha256": attempt["validation_report"]["sha256"],
                    "validator_version": report["validator_version"],
                },
            }
        )
    return history


def approve_workshop(
    workspace_root: Path,
    *,
    attempt_manifest: str,
    semantic_decision: str,
) -> dict[str, Any]:
    workspace = workspace_root.resolve(strict=True)
    attempt_manifest_path = workspace_relative_path(
        workspace, attempt_manifest, label="attempt_manifest"
    )
    resolution_root = attempt_manifest_path.parent / "resolution"
    if resolution_root.exists():
        fail("ARTIFACT_EXISTS", "Workshop attempt is already resolved")
    loaded = _load_attempt(workspace, attempt_manifest_path)
    attempt = loaded.attempt
    attempt_bytes = loaded.manifest_bytes
    derivation = loaded.derivation
    candidate_bytes = loaded.candidate_bytes
    preparation = loaded.preparation
    policy = loaded.policy
    if attempt["status"] != "pending_independent_review":
        fail(
            "APPROVAL_FORBIDDEN",
            "Deterministically rejected Workshop cannot be approved",
        )
    decision_path = workspace_relative_path(
        workspace, semantic_decision, label="semantic_decision"
    )
    decision_value, _ = read_json(decision_path, label="semantic decision")
    decision = _parse_semantic_decision(decision_value)
    if decision["case_id"] != attempt["case_id"]:
        fail("IDENTITY_MISMATCH", "Semantic decision case differs")
    if decision["attempt_manifest_sha256"] != sha256_bytes(attempt_bytes):
        fail("HASH_MISMATCH", "Semantic decision binds a different attempt")
    if decision["candidate_sha256"] != attempt["candidate"]["sha256"]:
        fail("HASH_MISMATCH", "Semantic decision binds a different candidate")
    if decision["reviewer"] == derivation["actor"]:
        fail(
            "REVIEW_NOT_INDEPENDENT",
            "Workshop reviewer must differ from the derivation actor",
        )
    if decision["reviewed_at"] <= derivation["completed_at"]:
        fail("INVALID_REVIEW", "Semantic review must follow derivation")

    canonical_decision_bytes = canonical_json_bytes(decision)
    decision_target_path = resolution_root / "semantic-decision.json"
    if decision["decision"] == "rejected":
        resolution_manifest = {
            "attempt_id": attempt["attempt_id"],
            "case_id": attempt["case_id"],
            "resolved_at": _now(),
            "schema_version": WORKSHOP_RESOLUTION_SCHEMA_VERSION,
            "semantic_decision": _artifact_ref(
                decision_target_path, workspace, canonical_decision_bytes
            ),
            "status": "rejected_semantic",
            "workshop": None,
            "workshop_manifest": None,
        }
        write_tree_once(
            resolution_root,
            {
                "semantic-decision.json": canonical_decision_bytes,
                "resolution-manifest.json": canonical_json_bytes(resolution_manifest),
            },
        )
        return {
            "case_id": attempt["case_id"],
            "resolution": relative_posix(
                resolution_root / "resolution-manifest.json", workspace
            ),
            "status": "rejected_semantic",
        }

    case_root = attempt_manifest_path.parent.parent.parent
    if _approved_resolution_exists(case_root):
        fail("WORKSHOP_ALREADY_APPROVED", "This case already has an Approved Workshop")
    approved_workshop_path = resolution_root / f"{attempt['case_id']}.md"
    workshop_manifest_path = resolution_root / "workshop-manifest.json"
    history = _attempt_history(
        workspace,
        case_root,
        current_attempt_id=attempt["attempt_id"],
        current_decision=decision,
        frozen_preparation=preparation,
    )
    report = loaded.report
    workshop_manifest = {
        "approval_status": "approved",
        "approved_at": _now(),
        "attempts": history,
        "case_id": attempt["case_id"],
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "derivation": derivation,
        "independent_review": {
            "decision_sha256": sha256_bytes(canonical_decision_bytes),
            "rationale": decision["rationale"],
            "reviewed_at": decision["reviewed_at"],
            "reviewer": decision["reviewer"],
        },
        "rules": {
            "normalization_version": policy.normalization_version,
            "policy_sha256": policy.sha256,
            "policy_version": policy.version,
            "validator_version": WORKSHOP_VALIDATOR_VERSION,
        },
        "schema_version": WORKSHOP_MANIFEST_SCHEMA_VERSION,
        "source_allowlist": SOURCE_ALLOWLIST,
        "source_provenance": preparation["sources"],
        "target_identity": preparation["target_identity"],
        "validation": {
            "deterministic_status": report["deterministic_status"],
            "failure_rule_ids": [],
            "lengths": report["lengths"],
            "semantic_status": decision["decision"],
            "validation_report_sha256": attempt["validation_report"]["sha256"],
        },
        "workshop": _artifact_ref(approved_workshop_path, workspace, candidate_bytes),
    }
    workshop_manifest_bytes = canonical_json_bytes(workshop_manifest)
    resolution_manifest = {
        "attempt_id": attempt["attempt_id"],
        "case_id": attempt["case_id"],
        "resolved_at": _now(),
        "schema_version": WORKSHOP_RESOLUTION_SCHEMA_VERSION,
        "semantic_decision": _artifact_ref(
            decision_target_path, workspace, canonical_decision_bytes
        ),
        "status": "approved",
        "workshop": _artifact_ref(approved_workshop_path, workspace, candidate_bytes),
        "workshop_manifest": _artifact_ref(
            workshop_manifest_path, workspace, workshop_manifest_bytes
        ),
    }
    write_tree_once(
        resolution_root,
        {
            "semantic-decision.json": canonical_decision_bytes,
            f"{attempt['case_id']}.md": candidate_bytes,
            "workshop-manifest.json": workshop_manifest_bytes,
            "resolution-manifest.json": canonical_json_bytes(resolution_manifest),
        },
    )
    return {
        "case_id": attempt["case_id"],
        "status": "approved",
        "workshop": relative_posix(approved_workshop_path, workspace),
        "workshop_manifest": relative_posix(workshop_manifest_path, workspace),
        "workshop_manifest_sha256": sha256_bytes(workshop_manifest_bytes),
        "workshop_sha256": sha256_bytes(candidate_bytes),
    }
