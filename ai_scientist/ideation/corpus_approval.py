from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_json_bytes,
    relative_posix,
    sha256_bytes,
)
from .contract import _now
from .corpus_validation import validate_corpus_bundle
from .errors import fail


def approve_corpus_bundle(
    workspace_root: Path,
    *,
    bundle_path: str | Path,
    approval_decision: str | Path,
) -> dict[str, Any]:
    bundle_dir = workspace_root / bundle_path
    if not bundle_dir.is_dir():
        fail("MISSING_BUNDLE", f"Corpus bundle directory does not exist: {bundle_dir}")

    manifest_path = bundle_dir / "bundle-manifest.json"
    if not manifest_path.is_file():
        fail("MISSING_MANIFEST", f"Manifest file missing: {manifest_path}")

    # 1. Run deterministic validation first
    val_report = validate_corpus_bundle(workspace_root, bundle_path=bundle_path)
    if val_report.get("status") != "pass" or val_report.get("error_count", 0) > 0:
        fail(
            "VALIDATION_FAILED",
            "Corpus bundle failed deterministic validation; cannot approve",
            errors=val_report.get("errors", []),
        )

    # 2. Load decision
    decision_file = workspace_root / approval_decision
    if not decision_file.is_file():
        fail("MISSING_DECISION", f"Approval decision file missing: {decision_file}")

    try:
        decision = json.loads(decision_file.read_bytes().decode("utf-8"))
    except Exception as exc:
        fail("INVALID_DECISION", "Approval decision is not valid JSON", error=str(exc))

    if decision.get("decision") != "approved":
        fail(
            "REJECTED_DECISION",
            f"Approval decision is not 'approved': {decision.get('decision')}",
        )

    approver = decision.get("approver", "").strip()
    if not approver:
        fail("INVALID_DECISION", "Decision missing non-empty 'approver'")

    # Load existing manifest
    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    if decision.get("case_id") != manifest.get("case_id"):
        fail(
            "CASE_MISMATCH",
            f"Decision case_id '{decision.get('case_id')}' does not match manifest '{manifest.get('case_id')}'",
        )

    # Verify versions match
    if decision.get("versions") != manifest.get("versions"):
        fail(
            "VERSION_MISMATCH",
            "Decision versions do not match manifest versions",
            decision_versions=decision.get("versions"),
            manifest_versions=manifest.get("versions"),
        )

    # Verify human review gates
    human_review = decision.get("human_review", {})
    if (
        human_review.get("exceptional_content_review") != "approved"
        or human_review.get("ordinary_abstract_sampling") != "approved"
        or human_review.get("policy_versions") != "approved"
    ):
        fail(
            "UNAPPROVED_HUMAN_REVIEW",
            "Not all human review gates are approved in decision",
            human_review=human_review,
        )

    # 3. Update manifest
    manifest["approval_status"] = "approved"
    manifest["approved_by"] = approver
    manifest["approved_at"] = _now()
    manifest["human_review"] = {
        "exceptional_content_count": manifest.get("human_review", {}).get(
            "exceptional_content_count", 0
        ),
        "ordinary_abstract_sampling_status": "approved",
        "policy_versions_approval_status": "approved",
    }

    # Record approval in evidence
    evidence_dir = bundle_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    approval_record = {
        "approval_decision": decision,
        "approved_at": manifest["approved_at"],
        "approved_by": approver,
        "case_id": manifest["case_id"],
        "validation_report_sha256": val_report.get("corpus_sha256"),
    }
    record_bytes = canonical_json_bytes(approval_record)
    record_path = evidence_dir / "approval-record.json"
    record_path.write_bytes(record_bytes)
    record_sha = sha256_bytes(record_bytes)

    # Update manifest inventory and bundle_content_sha256
    manifest["inventory"]["evidence/approval-record.json"] = record_sha
    manifest["bundle_content_sha256"] = sha256_bytes(
        canonical_json_bytes(manifest["inventory"])
    )

    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)

    return {
        "approved_at": manifest["approved_at"],
        "approved_by": approver,
        "bundle_path": relative_posix(bundle_dir, workspace_root),
        "case_id": manifest["case_id"],
        "status": "approved",
    }
