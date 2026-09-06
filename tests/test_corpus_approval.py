from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    read_json,
    sha256_bytes,
)
from ai_scientist.ideation.errors import IdeationInputError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/corpus"
POLICY_PATH = REPO_ROOT / "ai_scientist/ideation/policies/reference-authority-v1.json"

CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
ALT_TARGET_ID = "c" * 40


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return canonical_json_bytes(value)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    raw_root = workspace / "data/raw"
    policy_root = workspace / "ai_scientist/ideation/policies"
    raw_root.mkdir(parents=True)
    policy_root.mkdir(parents=True)
    shutil.copyfile(FIXTURE_ROOT / "target_papers.csv", raw_root / "target_papers.csv")
    shutil.copyfile(
        FIXTURE_ROOT / "filtered_references.csv",
        raw_root / "filtered_references.csv",
    )
    shutil.copyfile(POLICY_PATH, policy_root / "reference-authority-v1.json")
    return workspace


def _run(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_scientist.prepare_ideation_inputs",
            "--workspace-root",
            str(workspace),
            "corpus",
            *arguments,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _build(
    workspace: Path,
    case_id: str = CASE_ID,
    target_paper_id: str = TARGET_ID,
    build_id: str = "build-001",
) -> Path:
    result = _run(
        workspace,
        "build",
        "--case-id",
        case_id,
        "--target-paper-id",
        target_paper_id,
        "--build-id",
        build_id,
    )
    assert result.returncode == 0, f"build failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "pending_robert_approval"
    bundle_path = workspace / payload["bundle_path"]
    assert bundle_path.is_dir()
    return bundle_path


def _approval_decision(
    workspace: Path,
    bundle_path: Path,
    *,
    approved: bool = True,
    approver: str = "Robert",
) -> Path:
    manifest_path = bundle_path / "bundle-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    corpus_path = bundle_path / "corpus.json"
    corpus_sha256 = _sha256(corpus_path.read_bytes())
    report_path = bundle_path / "validation-report.json"
    report_sha256 = _sha256(report_path.read_bytes())

    decision_path = workspace / "reviews/corpus-approval-decision.json"
    decision = {
        "approver": approver,
        "bundle_content_sha256": manifest["bundle_content_sha256"],
        "case_id": manifest["case_id"],
        "corpus_sha256": corpus_sha256,
        "decision": "approved" if approved else "rejected",
        "human_review": {
            "exceptional_content_review": "approved" if approved else "rejected",
            "ordinary_abstract_sampling": "approved" if approved else "rejected",
            "policy_versions": "approved" if approved else "rejected",
        },
        "rationale": (
            "All references verified against exact authority evidence."
            if approved
            else "Authority evidence rejected."
        ),
        "reviewed_at": "2026-09-03T12:00:00.000000Z",
        "schema_version": "corpus-approval-decision-v1.0",
        "validation_report_sha256": report_sha256,
        "versions": manifest["versions"],
    }
    _write_json(decision_path, decision)
    return decision_path


def test_corpus_build_produces_canonical_bundle_and_manifest(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    bundle_path = _build(workspace)

    corpus_path = bundle_path / "corpus.json"
    manifest_path = bundle_path / "bundle-manifest.json"
    report_path = bundle_path / "validation-report.json"
    source_rows_path = bundle_path / "evidence/source-rows.jsonl"

    assert corpus_path.is_file()
    assert manifest_path.is_file()
    assert report_path.is_file()
    assert source_rows_path.is_file()

    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert corpus["case_id"] == CASE_ID
    assert "schema_version" in corpus
    assert "normalization_version" in corpus
    assert "enrichment_policy_version" in corpus
    assert "records" in corpus

    # 5 references for TARGET_ID in fixture
    assert len(corpus["records"]) == 5

    # Records sorted by canonical paper_id
    paper_ids = [r["paper_id"] for r in corpus["records"]]
    assert paper_ids == sorted(paper_ids)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["approval_status"] == "pending_robert_approval"
    assert manifest["case_id"] == CASE_ID
    assert manifest["inventory"]["corpus.json"] == _sha256(corpus_path.read_bytes())


def test_corpus_validator_positive_golden_and_no_mutation(tmp_path: Path) -> None:
    """VM-CONTRACT-019-02: corpus validator positive golden bundle passes and is not mutated."""
    from ai_scientist.ideation.corpus import validate_corpus

    workspace = _workspace(tmp_path)
    bundle_path = _build(workspace)

    corpus_path = bundle_path / "corpus.json"
    before_bytes = corpus_path.read_bytes()
    manifest_before = (bundle_path / "bundle-manifest.json").read_bytes()

    result = validate_corpus(
        workspace,
        bundle_path=bundle_path.relative_to(workspace),
    )

    assert result["status"] == "pass"
    assert result["error_count"] == 0
    # 2 warnings expected: 1 missing venue, 1 un-published abstract for frailty commentary
    assert result["warning_count"] >= 1

    after_bytes = corpus_path.read_bytes()
    manifest_after = (bundle_path / "bundle-manifest.json").read_bytes()
    assert before_bytes == after_bytes, "corpus.json was mutated by validator!"
    assert manifest_before == manifest_after, "bundle-manifest.json was mutated!"


def test_corpus_rebuild_replay_determinism(tmp_path: Path) -> None:
    """VM-REPLAY-02: corpus同输入重建 → 相同 bundle SHA-256 与 byte-identical corpus.json."""
    workspace1 = _workspace(tmp_path / "run1")
    workspace2 = _workspace(tmp_path / "run2")

    bundle1 = _build(workspace1, build_id="build-001")
    bundle2 = _build(workspace2, build_id="build-001")

    corpus1_bytes = (bundle1 / "corpus.json").read_bytes()
    corpus2_bytes = (bundle2 / "corpus.json").read_bytes()
    assert corpus1_bytes == corpus2_bytes

    manifest1 = json.loads(
        (bundle1 / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    manifest2 = json.loads(
        (bundle2 / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest1["bundle_content_sha256"] == manifest2["bundle_content_sha256"]


def test_corpus_quarantine_leakage(tmp_path: Path) -> None:
    """VM-LEAKAGE-04: quarantine 校验: contexts/intents/targetPaperId 等不进入 corpus model-eligible 区."""
    workspace = _workspace(tmp_path)
    bundle_path = _build(workspace)

    corpus_text = (bundle_path / "corpus.json").read_text(encoding="utf-8")
    forbidden_keys = [
        "targetPaperId",
        "contexts",
        "intents",
        "isInfluential",
        "citationCount",
        "abstract_summary",
        "query",
        "score",
        "rank",
    ]
    for key in forbidden_keys:
        assert (
            f'"{key}"' not in corpus_text
        ), f"Quarantined key {key} leaked into corpus.json!"

    # But evidence/source-rows.jsonl must preserve them for audit
    source_rows_text = (bundle_path / "evidence/source-rows.jsonl").read_text(
        encoding="utf-8"
    )
    assert "targetPaperId" in source_rows_text
    assert "contexts" in source_rows_text
    assert "intents" in source_rows_text


def test_corpus_validator_negative_fail_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-019-01: corpus validator 负向: error 级清单逐条 fail-closed."""
    from ai_scientist.ideation.corpus import validate_corpus

    workspace = _workspace(tmp_path)
    bundle_path = _build(workspace)
    corpus_path = bundle_path / "corpus.json"
    manifest_path = bundle_path / "bundle-manifest.json"

    original_corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. CORPUS-SCHEMA-001: extra forbidden key
    bad_corpus = dict(original_corpus)
    bad_corpus["unexpected_field"] = "bad"
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-SCHEMA-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 2. Non-canonical bytes (CRLF)
    corpus_path.write_bytes(
        canonical_json_bytes(original_corpus).replace(b"\n", b"\r\n")
    )
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-SCHEMA-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 3. CORPUS-MAPPING-001: case_id mismatch
    bad_corpus = dict(original_corpus)
    bad_corpus["case_id"] = "case-" + "f" * 32
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-MAPPING-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 4. CORPUS-MEMBERSHIP-001: missing reference paper
    bad_corpus = dict(original_corpus)
    bad_corpus["records"] = original_corpus["records"][:-1]
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-MEMBERSHIP-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 5. CORPUS-MEMBERSHIP-001: duplicate reference paperId
    bad_corpus = dict(original_corpus)
    bad_corpus["records"] = original_corpus["records"] + [original_corpus["records"][0]]
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-MEMBERSHIP-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 6. CORPUS-IDENTITY-001: invalid paper_id (not 40 hex)
    bad_corpus = dict(original_corpus)
    bad_records = [dict(r) for r in original_corpus["records"]]
    bad_records[0]["paper_id"] = "not-40-hex"
    bad_corpus["records"] = bad_records
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-IDENTITY-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 7. CORPUS-CONTENT-001: empty title
    bad_corpus = dict(original_corpus)
    bad_records = [dict(r) for r in original_corpus["records"]]
    bad_records[0]["title"] = "   "
    bad_corpus["records"] = bad_records
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-CONTENT-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 8. CORPUS-CONTENT-001: status validated but text empty
    bad_corpus = dict(original_corpus)
    bad_records = [dict(r) for r in original_corpus["records"]]
    bad_items = [dict(it) for it in bad_records[0]["content_items"]]
    bad_items[0]["text"] = ""
    bad_records[0]["content_items"] = bad_items
    bad_corpus["records"] = bad_records
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-CONTENT-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 9. CORPUS-KNOWN-BAD-001: raw "falls," enters text
    bad_corpus = dict(original_corpus)
    bad_records = [dict(r) for r in original_corpus["records"]]
    bad_items = [dict(it) for it in bad_records[0]["content_items"]]
    bad_items[0]["text"] = "falls,"
    bad_records[0]["content_items"] = bad_items
    bad_corpus["records"] = bad_records
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-KNOWN-BAD-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 10. CORPUS-QUARANTINE-001: quarantined key in corpus.json
    bad_corpus = dict(original_corpus)
    bad_corpus["contexts"] = ["leaked context"]
    corpus_path.write_bytes(canonical_json_bytes(bad_corpus))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-QUARANTINE-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )

    # 11. CORPUS-HASH-001: inventory hash mismatch
    corpus_path.write_bytes(canonical_json_bytes(original_corpus))
    bad_manifest = dict(original_manifest)
    bad_manifest["inventory"]["corpus.json"] = "0" * 64
    manifest_path.write_bytes(canonical_json_bytes(bad_manifest))
    res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert res["status"] == "fail"
    assert any(
        "CORPUS-HASH-001" in r["rule_id"] and r["status"] == "fail"
        for r in res["rules"]
    )


def test_corpus_approval_lifecycle_and_isolation(tmp_path: Path) -> None:
    """Test the complete build -> validate -> approve flow, and verify approval enforcement."""
    from ai_scientist.ideation.corpus import approve_corpus, validate_corpus

    workspace = _workspace(tmp_path)
    bundle_path = _build(workspace)

    # Validate first
    val_res = validate_corpus(workspace, bundle_path=bundle_path.relative_to(workspace))
    assert val_res["status"] == "pass"

    decision_path = _approval_decision(workspace, bundle_path, approved=True)

    # Approve
    app_res = approve_corpus(
        workspace,
        bundle_path=bundle_path.relative_to(workspace),
        approval_decision=decision_path.relative_to(workspace),
    )
    assert app_res["status"] == "approved"
    assert app_res["approved_by"] == "Robert"

    # Verify manifest updated to approved
    manifest = json.loads(
        (bundle_path / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["approval_status"] == "approved"
    assert manifest["approved_by"] == "Robert"

    # Cannot approve with rejected decision
    rejected_decision_path = _approval_decision(workspace, bundle_path, approved=False)
    with pytest.raises(IdeationInputError, match="REJECTED_DECISION"):
        approve_corpus(
            workspace,
            bundle_path=bundle_path.relative_to(workspace),
            approval_decision=rejected_decision_path.relative_to(workspace),
        )


def test_corpus_build_cannot_overwrite_existing(tmp_path: Path) -> None:
    """Immutable build attempt: cannot overwrite existing corpus bundle."""
    workspace = _workspace(tmp_path)
    _build(workspace, build_id="build-001")

    # Building again with same build_id should fail
    result = _run(
        workspace,
        "build",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--build-id",
        "build-001",
    )
    assert result.returncode != 0
    assert "EXISTS" in result.stderr or "ALREADY_EXISTS" in result.stderr


def test_validate_all_targets_offline(tmp_path: Path) -> None:
    """Test deterministic preprocessing validation for all targets in workspace data."""
    from ai_scientist.ideation.corpus import validate_all_corpora

    workspace = _workspace(tmp_path)

    # Run on fixture data (contains 2 targets)
    result = validate_all_corpora(workspace)
    assert result["total_targets"] == 2
    assert result["passed_targets"] == 2
    assert result["failed_targets"] == 0
    assert result["status"] == "pass"


def test_corpus_cli_end_to_end(tmp_path: Path) -> None:
    """Test end-to-end CLI build, validate, approve commands."""
    workspace = _workspace(tmp_path)

    # 1. CLI build
    res_build = _run(
        workspace,
        "build",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--build-id",
        "build-001",
    )
    assert res_build.returncode == 0
    payload_build = json.loads(res_build.stdout)
    assert payload_build["status"] == "pending_robert_approval"
    bundle_rel = payload_build["bundle_path"]

    # 2. CLI validate
    res_val = _run(
        workspace,
        "validate",
        "--bundle-path",
        bundle_rel,
    )
    assert res_val.returncode == 0
    payload_val = json.loads(res_val.stdout)
    assert payload_val["status"] == "pass"

    # 3. CLI approve
    bundle_path = workspace / bundle_rel
    dec_path = _approval_decision(workspace, bundle_path, approved=True)
    res_app = _run(
        workspace,
        "approve",
        "--bundle-path",
        bundle_rel,
        "--approval-decision",
        dec_path.relative_to(workspace).as_posix(),
    )
    assert res_app.returncode == 0
    payload_app = json.loads(res_app.stdout)
    assert payload_app["status"] == "approved"


def test_validate_all_237_targets_offline_on_repo_raw_data() -> None:
    """Test deterministic preprocessing validation for all 237 real targets in data/raw."""
    from ai_scientist.ideation.corpus import validate_all_corpora

    result = validate_all_corpora(REPO_ROOT)
    assert result["total_targets"] == 237
    assert result["passed_targets"] == 237
    assert result["failed_targets"] == 0
    assert result["status"] == "pass"
