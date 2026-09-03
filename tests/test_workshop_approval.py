from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.schema import closed_object
from ai_scientist.ideation.text import normalize_text, tokenize_text

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workshop"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    raw_root = workspace / "data/raw"
    draft_root = workspace / "drafts"
    policy_root = workspace / "ai_scientist/ideation/policies"
    raw_root.mkdir(parents=True)
    draft_root.mkdir(parents=True)
    policy_root.mkdir(parents=True)
    shutil.copyfile(FIXTURE_ROOT / "target_papers.csv", raw_root / "target_papers.csv")
    shutil.copyfile(
        FIXTURE_ROOT / "filtered_references.csv",
        raw_root / "filtered_references.csv",
    )
    shutil.copyfile(FIXTURE_ROOT / "valid.md", draft_root / "valid.md")
    shutil.copyfile(FIXTURE_ROOT / "leaked.md", draft_root / "leaked.md")
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/workshop-leakage-v1.json",
        policy_root / "workshop-leakage-v1.json",
    )
    return workspace


def _run(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_scientist.prepare_ideation_inputs",
            "--workspace-root",
            str(workspace),
            "workshop",
            *arguments,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _prepare(workspace: Path, preparation_id: str = "preparation-001") -> Path:
    result = _run(
        workspace,
        "prepare",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--preparation-id",
        preparation_id,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "prepared"
    preparation = workspace / payload["preparation_manifest"]
    assert preparation.is_file()
    return preparation


def _derivation_record(workspace: Path, preparation: Path) -> Path:
    preparation_value = json.loads(preparation.read_text(encoding="utf-8"))
    path = workspace / "reviews/derivation.json"
    _write_json(
        path,
        {
            "actor": "fixture-author",
            "authoring_source_sha256": preparation_value["authoring_source"]["sha256"],
            "completed_at": "2026-09-03T01:02:03.000000Z",
            "mechanism": "manual",
            "mechanism_version": "fixture-manual-v1",
            "schema_version": "workshop-derivation-v1.0",
            "source_fields": ["title", "abstract"],
        },
    )
    return path


def _validate(
    workspace: Path,
    preparation: Path,
    *,
    attempt_id: str,
    candidate: str,
) -> subprocess.CompletedProcess[str]:
    return _run(
        workspace,
        "validate",
        "--preparation-manifest",
        preparation.relative_to(workspace).as_posix(),
        "--attempt-id",
        attempt_id,
        "--candidate",
        candidate,
        "--derivation-record",
        "reviews/derivation.json",
    )


def _semantic_decision(
    workspace: Path,
    attempt_manifest: Path,
    *,
    approved: bool,
    reviewer: str = "fixture-reviewer",
) -> Path:
    attempt = json.loads(attempt_manifest.read_text(encoding="utf-8"))
    candidate_path = workspace / attempt["candidate"]["path"]
    path = workspace / "reviews/semantic-decision.json"
    checks = {
        "allows_multiple_method_families": approved,
        "no_answer_leakage": approved,
        "no_identity_leakage": approved,
        "target_relevant": True,
    }
    _write_json(
        path,
        {
            "attempt_manifest_sha256": _sha256(attempt_manifest.read_bytes()),
            "candidate_sha256": _sha256(candidate_path.read_bytes()),
            "case_id": CASE_ID,
            "checks": checks,
            "decision": "approved" if approved else "rejected",
            "rationale": (
                "The problem remains open and several method families are plausible."
                if approved
                else "The candidate narrows the problem to the held-out answer."
            ),
            "reviewed_at": "2026-09-03T02:03:04.000000Z",
            "reviewer": reviewer,
            "schema_version": "workshop-semantic-decision-v1.0",
        },
    )
    return path


def test_text_normalization_has_stable_tokens_and_rejects_invalid_values() -> None:
    assert normalize_text("  Café—CAFE\u0301  ") == "café-café"
    assert tokenize_text("risk risk C++ and O’Neill") == (
        "risk",
        "risk",
        "c++",
        "and",
        "o'neill",
    )

    with pytest.raises(IdeationInputError, match="INVALID_TEXT"):
        normalize_text(7)  # type: ignore[arg-type]
    with pytest.raises(IdeationInputError, match="INVALID_UNICODE"):
        normalize_text("bad\ud800")


def test_closed_schema_rejects_unknown_fields_and_types() -> None:
    assert closed_object({"name": "value"}, label="fixture", keys={"name"}) == {
        "name": "value"
    }

    with pytest.raises(IdeationInputError, match="INVALID_SCHEMA"):
        closed_object({"name": "value", "extra": True}, label="fixture", keys={"name"})
    with pytest.raises(IdeationInputError, match="INVALID_SCHEMA"):
        closed_object(["not", "an", "object"], label="fixture", keys={"name"})


def test_workshop_cli_approves_only_a_hash_bound_two_gate_candidate(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    preparation = _prepare(workspace)
    preparation_value = json.loads(preparation.read_text(encoding="utf-8"))
    authoring = json.loads(
        (workspace / preparation_value["authoring_source"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    assert set(authoring) == {
        "case_id",
        "raw_abstract",
        "schema_version",
        "source_fields",
        "title",
    }
    assert authoring["source_fields"] == ["title", "abstract"]
    assert "abstract_summary" not in json.dumps(authoring)
    assert TARGET_ID not in json.dumps(authoring)

    _derivation_record(workspace, preparation)
    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/valid.md",
    )
    assert validation.returncode == 0, validation.stderr
    validation_payload = json.loads(validation.stdout)
    attempt_manifest = workspace / validation_payload["attempt_manifest"]
    report = json.loads(
        (attempt_manifest.parent / "validation-report.json").read_text(encoding="utf-8")
    )
    assert report["deterministic_status"] == "pass"
    assert report["semantic_status"] == "pending_independent_review"

    decision = _semantic_decision(workspace, attempt_manifest, approved=True)
    approval = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        attempt_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        decision.relative_to(workspace).as_posix(),
    )
    assert approval.returncode == 0, approval.stderr
    approval_payload = json.loads(approval.stdout)
    assert approval_payload["status"] == "approved"
    workshop_path = workspace / approval_payload["workshop"]
    manifest_path = workspace / approval_payload["workshop_manifest"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert workshop_path.name == f"{CASE_ID}.md"
    assert workshop_path.read_bytes() == (workspace / "drafts/valid.md").read_bytes()
    assert manifest["approval_status"] == "approved"
    assert manifest["workshop"]["sha256"] == _sha256(workshop_path.read_bytes())
    assert manifest["target_identity"]["paper_id"] == TARGET_ID
    assert "raw_abstract" not in manifest
    assert "abstract_summary" not in manifest

    repeated = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        attempt_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        decision.relative_to(workspace).as_posix(),
    )
    assert repeated.returncode == 1
    assert "ARTIFACT_EXISTS" in repeated.stderr


def test_workshop_cli_retains_deterministic_rejection_without_approval(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)
    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/leaked.md",
    )
    assert validation.returncode == 2, validation.stderr
    payload = json.loads(validation.stdout)
    attempt_manifest = workspace / payload["attempt_manifest"]
    report = json.loads(
        (attempt_manifest.parent / "validation-report.json").read_text(encoding="utf-8")
    )
    assert report["semantic_status"] == "not_run"
    rule_ids = {failure["rule_id"] for failure in report["failures"]}
    assert {
        "WORKSHOP-IDENTITY-DOI",
        "WORKSHOP-IDENTITY-TITLE",
        "WORKSHOP-IDENTITY-URL",
        "WORKSHOP-LEAKAGE-NGRAM",
    } <= rule_ids
    assert not (attempt_manifest.parent / "resolution").exists()
    assert not list(attempt_manifest.parents[2].glob("**/workshop-manifest.json"))


@pytest.mark.parametrize(
    "private_text,expected_rule",
    [
        (
            "PulseMap combines wearable sensing and symptom diaries to improve "
            "individualized early-warning accuracy.",
            "WORKSHOP-LEAKAGE-EXACT",
        ),
        (
            "PULSEMAP COMBINES WEARABLE SENSING AND SYMPTOM DIARIES TO IMPROVE "
            "INDIVIDUALIZED EARLY—WARNING ACCURACY.",
            "WORKSHOP-LEAKAGE-NORMALIZED",
        ),
    ],
)
def test_workshop_cli_rejects_exact_and_normalized_private_sources(
    tmp_path: Path,
    private_text: str,
    expected_rule: str,
) -> None:
    workspace = _workspace(tmp_path)
    candidate = (
        "# Title: Migraine care questions\n\n"
        "## Keywords\nchronic migraine, clinical forecasting\n\n"
        "## TL;DR\nWhich research directions remain open?\n\n"
        f"## Abstract\n{private_text}\n"
    )
    (workspace / "drafts/private-source.md").write_text(
        candidate, encoding="utf-8", newline=""
    )
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)

    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/private-source.md",
    )

    assert validation.returncode == 2, validation.stderr
    attempt_manifest = workspace / json.loads(validation.stdout)["attempt_manifest"]
    report = json.loads(
        (attempt_manifest.parent / "validation-report.json").read_text(encoding="utf-8")
    )
    assert expected_rule in {failure["rule_id"] for failure in report["failures"]}
    assert private_text not in json.dumps(report)


def test_workshop_cli_retains_semantic_rejection_and_rejects_self_review(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)
    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/valid.md",
    )
    assert validation.returncode == 0, validation.stderr
    attempt_manifest = workspace / json.loads(validation.stdout)["attempt_manifest"]

    self_review = _semantic_decision(
        workspace,
        attempt_manifest,
        approved=True,
        reviewer="fixture-author",
    )
    rejected = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        attempt_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        self_review.relative_to(workspace).as_posix(),
    )
    assert rejected.returncode == 1
    assert "REVIEW_NOT_INDEPENDENT" in rejected.stderr
    assert not (attempt_manifest.parent / "resolution").exists()

    decision = _semantic_decision(workspace, attempt_manifest, approved=False)
    semantic_rejection = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        attempt_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        decision.relative_to(workspace).as_posix(),
    )
    assert semantic_rejection.returncode == 2, semantic_rejection.stderr
    resolution = attempt_manifest.parent / "resolution"
    assert (resolution / "semantic-decision.json").is_file()
    assert not (resolution / f"{CASE_ID}.md").exists()
    assert not (resolution / "workshop-manifest.json").exists()


def test_workshop_approval_rejects_a_tampered_semantic_review_packet(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)
    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/valid.md",
    )
    assert validation.returncode == 0, validation.stderr
    payload = json.loads(validation.stdout)
    attempt_manifest = workspace / payload["attempt_manifest"]
    semantic_packet = workspace / payload["semantic_review_packet"]
    semantic_packet.write_bytes(semantic_packet.read_bytes() + b" ")
    decision = _semantic_decision(workspace, attempt_manifest, approved=True)

    approval = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        attempt_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        decision.relative_to(workspace).as_posix(),
    )

    assert approval.returncode == 1
    assert "HASH_MISMATCH" in approval.stderr
    assert not (attempt_manifest.parent / "resolution").exists()


def test_approved_manifest_retains_all_prior_rejected_attempts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)
    rejected = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/leaked.md",
    )
    assert rejected.returncode == 2, rejected.stderr
    semantically_rejected = _validate(
        workspace,
        preparation,
        attempt_id="attempt-002",
        candidate="drafts/valid.md",
    )
    assert semantically_rejected.returncode == 0, semantically_rejected.stderr
    rejected_manifest = (
        workspace / json.loads(semantically_rejected.stdout)["attempt_manifest"]
    )
    rejected_decision = _semantic_decision(workspace, rejected_manifest, approved=False)
    rejection = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        rejected_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        rejected_decision.relative_to(workspace).as_posix(),
    )
    assert rejection.returncode == 2, rejection.stderr

    accepted = _validate(
        workspace,
        preparation,
        attempt_id="attempt-003",
        candidate="drafts/valid.md",
    )
    assert accepted.returncode == 0, accepted.stderr
    attempt_manifest = workspace / json.loads(accepted.stdout)["attempt_manifest"]
    decision = _semantic_decision(workspace, attempt_manifest, approved=True)

    approval = _run(
        workspace,
        "approve",
        "--attempt-manifest",
        attempt_manifest.relative_to(workspace).as_posix(),
        "--semantic-decision",
        decision.relative_to(workspace).as_posix(),
    )

    assert approval.returncode == 0, approval.stderr
    manifest = json.loads(
        (workspace / json.loads(approval.stdout)["workshop_manifest"]).read_text(
            encoding="utf-8"
        )
    )
    assert [item["attempt_id"] for item in manifest["attempts"]] == [
        "attempt-001",
        "attempt-002",
        "attempt-003",
    ]
    assert manifest["attempts"][0]["deterministic_status"] == "fail"
    assert manifest["attempts"][0]["semantic_status"] == "not_run"
    assert manifest["attempts"][1]["semantic_status"] == "rejected"
    assert manifest["attempts"][2]["semantic_status"] == "approved"


def test_workshop_validation_fails_closed_when_the_source_snapshot_drifts(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)
    target_path = workspace / "data/raw/target_papers.csv"
    target_path.write_bytes(target_path.read_bytes() + b"\n")

    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/valid.md",
    )

    assert validation.returncode == 1
    assert "SOURCE_DRIFT" in validation.stderr
    assert not list((preparation.parent.parent.parent / "attempts").glob("attempt-001"))


@pytest.mark.parametrize(
    "candidate_bytes,expected_rule",
    [
        (
            b"# Title: Valid label\r\n\r\n## Keywords\r\none\r\n\r\n"
            b"## TL;DR\r\nQuestion?\r\n\r\n## Abstract\r\nNeutral scope.\r\n",
            "WORKSHOP-CANONICAL-LF",
        ),
        (
            b"# Title: Valid label\n\n## Keywords\none\n\n## TL;DR\nQuestion?\n\n"
            b"## Abstract\nNeutral scope.\n\n## Method\nForbidden.\n",
            "WORKSHOP-SCHEMA",
        ),
    ],
)
def test_workshop_cli_rejects_noncanonical_or_extra_content(
    tmp_path: Path,
    candidate_bytes: bytes,
    expected_rule: str,
) -> None:
    workspace = _workspace(tmp_path)
    (workspace / "drafts/invalid.md").write_bytes(candidate_bytes)
    preparation = _prepare(workspace)
    _derivation_record(workspace, preparation)
    validation = _validate(
        workspace,
        preparation,
        attempt_id="attempt-001",
        candidate="drafts/invalid.md",
    )
    assert validation.returncode == 2, validation.stderr
    attempt_manifest = workspace / json.loads(validation.stdout)["attempt_manifest"]
    report = json.loads(
        (attempt_manifest.parent / "validation-report.json").read_text(encoding="utf-8")
    )
    assert expected_rule in {failure["rule_id"] for failure in report["failures"]}
