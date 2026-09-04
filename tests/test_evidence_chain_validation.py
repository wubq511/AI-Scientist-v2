"""Evidence Chain validation, sanitized export, and cross-run isolation tests.

Delivers:
- VM-CONTRACT-023-02: corrupt run detection checklist, non-repairability,
  and fail-closed behavior across resume/export/replay.
- VM-CONTRACT-023-03: sanitized release gate with positive allowlist,
  linkage, and idempotent byte-identical export.
- VM-LEAKAGE-03: forbidden key, path, credential, and target identifier scans.
- VM-ISOLATION-01: cross-run guards (cross-run read/write, prior run evidence
  refused as input, exclusive-create conflict, wrong run_id resume, latest/glob refused).
- VM-ISOLATION-02: path and symlink attack set (absolute, .., backslash, symlinks).
- VM-ISOLATION-03: candidate/attempt isolation (write-once immutable attempt,
  no overwrite on rerun, offline replay verification).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

from ai_scientist.ideation.admission import NewRunRequest
from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.deepseek import (
    DEEPSEEK_MODEL_ID,
    DeepSeekAdapter,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.evidence import (
    EVIDENCE_ROOT_RELPATH,
    _load_target_identities,
    _scan_for_forbidden_paths,
    _scan_for_target_leaks,
    export_sanitized_evidence,
    replay_recorded_run,
    validate_evidence_chain,
)
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.resume import resume_run
from ai_scientist.ideation.run_store import RunStore, _validate_run_id
from ai_scientist.perform_ideation_temp_free import run_new_run

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"


@pytest.fixture(autouse=True)
def _mock_interactive_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    import io

    approval_input = io.StringIO("yes\n" * 100)
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _make_response_bytes(content: str, response_id: str) -> bytes:
    payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {
                    "content": content,
                    "role": "assistant",
                },
            }
        ],
        "created": 1725321600,
        "id": response_id,
        "model": DEEPSEEK_MODEL_ID,
        "object": "chat.completion",
        "usage": {
            "completion_tokens": 120,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 200,
            "prompt_tokens": 200,
            "total_tokens": 320,
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _setup_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    raw_root = workspace / "data/raw"
    policy_root = workspace / "ai_scientist/ideation/policies"
    raw_root.mkdir(parents=True)
    policy_root.mkdir(parents=True)
    shutil.copyfile(
        FIXTURE_CORPUS / "target_papers.csv", raw_root / "target_papers.csv"
    )
    shutil.copyfile(
        FIXTURE_CORPUS / "filtered_references.csv",
        raw_root / "filtered_references.csv",
    )
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/reference-authority-v1.json",
        policy_root / "reference-authority-v1.json",
    )
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/workshop-leakage-v1.json",
        policy_root / "workshop-leakage-v1.json",
    )
    shutil.copyfile(
        REPO_ROOT / "ai_scientist/ideation/policies/deepseek-cny-price-table-v1.json",
        policy_root / "deepseek-cny-price-table-v1.json",
    )
    (workspace / ".gitignore").write_text(
        "artifacts/ideation-runs/\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Integration Tester"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: setup integration workspace"],
        cwd=workspace,
        check=True,
    )
    return workspace


def _prepare_cli(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_scientist.prepare_ideation_inputs",
            "--workspace-root",
            str(workspace),
            *arguments,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _approved_corpus(workspace: Path) -> tuple[str, str]:
    build = _prepare_cli(
        workspace,
        "corpus",
        "build",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--build-id",
        BUILD_ID,
    )
    assert build.returncode == 0, build.stderr
    bundle_rel = json.loads(build.stdout)["bundle_path"]
    manifest = json.loads(
        (workspace / bundle_rel / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    decision = {
        "approver": "Robert",
        "bundle_content_sha256": manifest["bundle_content_sha256"],
        "case_id": manifest["case_id"],
        "corpus_sha256": manifest["inventory"]["corpus.json"],
        "decision": "approved",
        "human_review": {
            "exceptional_content_review": "approved",
            "ordinary_abstract_sampling": "approved",
            "policy_versions": "approved",
        },
        "rationale": "Fixture bundle approved for integration tests.",
        "reviewed_at": "2026-09-03T12:00:00.000000Z",
        "schema_version": "corpus-approval-decision-v1.0",
        "validation_report_sha256": manifest["inventory"]["validation-report.json"],
        "versions": manifest["versions"],
    }
    decision_path = workspace / "reviews/corpus-approval-decision.json"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_bytes(
        (json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    approve = _prepare_cli(
        workspace,
        "corpus",
        "approve",
        "--bundle-path",
        bundle_rel,
        "--approval-decision",
        decision_path.relative_to(workspace).as_posix(),
    )
    assert approve.returncode == 0, approve.stderr
    corpus_rel = f"{bundle_rel}/corpus.json"
    corpus_sha = sha256_bytes((workspace / corpus_rel).read_bytes())
    return corpus_rel, corpus_sha


def _approved_workshop(workspace: Path) -> tuple[str, str]:
    prep = _prepare_cli(
        workspace,
        "workshop",
        "prepare",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--preparation-id",
        "prep-001",
    )
    assert prep.returncode == 0, prep.stderr
    prep_rel = json.loads(prep.stdout)["preparation_manifest"]
    prep_manifest = json.loads((workspace / prep_rel).read_text(encoding="utf-8"))

    (workspace / "reviews").mkdir(exist_ok=True)
    derivation = {
        "actor": "integration-tester",
        "authoring_source_sha256": prep_manifest["authoring_source"]["sha256"],
        "completed_at": "2026-09-03T02:00:00.000000Z",
        "mechanism": "manual",
        "mechanism_version": "human-v1",
        "schema_version": "workshop-derivation-v1.0",
        "source_fields": ["title", "abstract"],
    }
    (workspace / "reviews/derivation.json").write_bytes(
        canonical_json_bytes(derivation)
    )

    candidate = (
        "# Title: Migraine care questions\n\n"
        "## Keywords\nchronic migraine, clinical forecasting\n\n"
        "## TL;DR\nWhich research directions remain open?\n\n"
        "## Abstract\nSymptom variability complicates timely migraine care; "
        "several forecasting and cueing method families remain unexplored.\n"
    )
    (workspace / "drafts").mkdir(exist_ok=True)
    (workspace / "drafts/workshop.md").write_text(candidate, encoding="utf-8")

    validate = _prepare_cli(
        workspace,
        "workshop",
        "validate",
        "--preparation-manifest",
        prep_rel,
        "--attempt-id",
        "attempt-001",
        "--candidate",
        "drafts/workshop.md",
        "--derivation-record",
        "reviews/derivation.json",
    )
    assert validate.returncode == 0, validate.stderr
    attempt_rel = json.loads(validate.stdout)["attempt_manifest"]
    attempt = json.loads((workspace / attempt_rel).read_text(encoding="utf-8"))

    decision = {
        "attempt_manifest_sha256": sha256_bytes((workspace / attempt_rel).read_bytes()),
        "candidate_sha256": sha256_bytes(
            (workspace / attempt["candidate"]["path"]).read_bytes()
        ),
        "case_id": CASE_ID,
        "checks": {
            "abstract_is_neutral_problem_scope": True,
            "allows_multiple_method_families": True,
            "keywords_are_established_terms": True,
            "no_answer_leakage": True,
            "no_identity_leakage": True,
            "target_relevant": True,
            "title_is_identity_free_problem_area": True,
            "tldr_is_open_question_or_tension": True,
            "written_in_english": True,
        },
        "decision": "approved",
        "rationale": "The problem remains open with several method families.",
        "reviewed_at": "2026-09-03T02:03:04.000000Z",
        "reviewer": "integration-reviewer",
        "schema_version": "workshop-semantic-decision-v1.1",
    }
    decision_rel = "reviews/semantic-decision.json"
    (workspace / decision_rel).write_bytes(canonical_json_bytes(decision))

    approve = _prepare_cli(
        workspace,
        "workshop",
        "approve",
        "--attempt-manifest",
        attempt_rel,
        "--semantic-decision",
        decision_rel,
    )
    assert approve.returncode == 0, approve.stderr
    payload = json.loads(approve.stdout)
    workshop_rel = payload["workshop"]
    workshop_sha = sha256_bytes((workspace / workshop_rel).read_bytes())
    return workshop_rel, workshop_sha


def _create_sealed_run(workspace: Path) -> dict[str, Any]:
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: commit approved inputs"],
        cwd=workspace,
        check=True,
    )

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    first_record = corpus_data["records"][0]
    expected_paper_id = first_record["paper_id"]

    round_0_content = (
        "ACTION: SearchLiterature\n"
        'ARGUMENTS: {"query": "clinical forecasting migraine"}'
    )
    idea_payload = {
        "Name": "adaptive_temporal_cueing",
        "Title": "Adaptive Temporal Cueing for Migraine Forecasting",
        "Short Hypothesis": "Continuous passive symptom tracking with adaptive temporal cueing significantly improves early warning accuracy for migraine attacks.",
        "Related Work": "Existing forecasting approaches rely exclusively on static clinical records. Our proposal introduces adaptive temporal cueing based on passive sensing streams.",
        "Abstract": "Migraine forecasting remains a major challenge due to symptom variability. We propose an adaptive temporal cueing framework that learns individualized warning windows from passive telemetry. Systematic clinical evaluation demonstrates enhanced prediction sensitivity while minimizing false alarms.",
        "Experiments": [
            "Benchmark adaptive cueing against static baseline predictors on multi-center clinical cohorts.",
            "Ablation study on temporal cueing window lengths and passive sensor feature subsets.",
        ],
        "Risk Factors and Limitations": [
            "Sensitivity to intermittent missing sensor telemetry.",
            "Potential variation in patient symptom reporting consistency.",
        ],
    }
    round_1_content = (
        f"ACTION: FinalizeIdea\n"
        f"ARGUMENTS: {{\n"
        f'  "idea": {json.dumps(idea_payload)},\n'
        f'  "grounding": ["{expected_paper_id}"]\n'
        f"}}"
    )

    stub_responses = [
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(round_0_content, "chatcmpl-round-0"),
            duration_ms=45.0,
        ),
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(round_1_content, "chatcmpl-round-1"),
            duration_ms=55.0,
        ),
    ]

    transport = StubTransport(stub_responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(
        price_table=price_table,
        transport=transport,
    )
    result = run_new_run(
        workspace,
        request,
        adapter=adapter,
        execute=True,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    return result


# ==============================================================================
# VM-CONTRACT-023-02: Corrupt Run Detection & Non-Repairability
# ==============================================================================


def test_validate_evidence_chain_golden_pass(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: A valid sealed run passes all validation checks."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    report = validate_evidence_chain(workspace, run_id, check_sealed=True)
    assert report["status"] == "valid"
    assert report["run_id"] == run_id
    assert report["is_sealed"] is True
    assert report["terminal_outcome"] == "success"
    assert report["event_count"] >= 5
    assert report["artifact_count"] >= 3


def test_validate_missing_request_json_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Missing request.json is corrupt and cannot resume or export."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    req_path = workspace / "artifacts/ideation-runs" / run_id / "request.json"
    req_path.unlink()

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"

    # Must refuse export
    with pytest.raises(IdeationInputError) as export_exc:
        export_sanitized_evidence(workspace, run_id)
    assert export_exc.value.code == "RUN_CORRUPT"

    # Must refuse replay
    with pytest.raises(IdeationInputError) as replay_exc:
        replay_recorded_run(workspace, run_id)
    assert replay_exc.value.code == "RUN_CORRUPT"


def test_validate_missing_admission_json_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Missing admission.json on sealed run is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    adm_path = workspace / "artifacts/ideation-runs" / run_id / "admission.json"
    adm_path.unlink()

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


def test_validate_broken_event_chain_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Event sequence gap or broken hash chain is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    # Delete an intermediate event
    ev2 = workspace / "artifacts/ideation-runs" / run_id / "events/00000002.json"
    ev2.unlink()

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


def test_validate_tampered_event_hash_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Tampered event payload or hash is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    ev1 = workspace / "artifacts/ideation-runs" / run_id / "events/00000001.json"
    data = json.loads(ev1.read_text(encoding="utf-8"))
    data["event_hash"] = "0" * 64
    ev1.write_bytes(canonical_json_bytes(data))

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


def test_validate_tampered_artifact_bytes_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Modified artifact bytes or length mismatch is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    # Find an artifact and modify it
    art_path = next(
        (workspace / "artifacts/ideation-runs" / run_id / "artifacts").rglob("*.json")
    )
    art_path.write_bytes(b'{"tampered":true}\n')

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


def test_validate_orphan_uninventoried_artifact_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Extra orphan artifact in artifacts/ is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    orphan = workspace / "artifacts/ideation-runs" / run_id / "artifacts/orphan.json"
    orphan.write_bytes(b'{"orphan":1}\n')

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


def test_validate_staging_uncleaned_in_sealed_run_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Lingering staging residue in a sealed run is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    staging = workspace / "artifacts/ideation-runs" / run_id / "staging"
    staging.mkdir(exist_ok=True)
    (staging / "leftover.tmp").write_bytes(b"temp")

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


def test_validate_symlink_in_run_root_fails_closed(tmp_path: Path) -> None:
    """VM-CONTRACT-023-02: Any symlink inside run root is corrupt."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    symlink = workspace / "artifacts/ideation-runs" / run_id / "artifacts/link.json"
    target = workspace / "artifacts/ideation-runs" / run_id / "request.json"
    symlink.symlink_to(target)

    with pytest.raises(IdeationInputError) as exc:
        validate_evidence_chain(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"


# ==============================================================================
# VM-CONTRACT-023-03 & VM-LEAKAGE-03: Sanitized Release Gate & Exporter
# ==============================================================================


def test_export_sanitized_evidence_golden_pass(tmp_path: Path) -> None:
    """VM-CONTRACT-023-03: Positive allowlist export creates valid manifest and events."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    export_result = export_sanitized_evidence(workspace, run_id)
    assert export_result["status"] == "exported"
    assert export_result["run_id"] == run_id

    dest_dir = workspace / EVIDENCE_ROOT_RELPATH / run_id
    assert dest_dir.is_dir()

    manifest_file = dest_dir / "manifest.json"
    events_file = dest_dir / "events.json"
    assert manifest_file.is_file()
    assert events_file.is_file()

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    events = json.loads(events_file.read_text(encoding="utf-8"))

    # Schema & linkage checks
    assert manifest["schema_version"] == "sanitized-manifest-v1.0.0"
    assert manifest["run_id"] == run_id
    assert manifest["case_id"] == CASE_ID
    assert manifest["terminal_outcome"] == "success"
    assert manifest["events_sha256"] == sha256_bytes(events_file.read_bytes())
    assert len(manifest["artifact_inventory"]) >= 3

    # Events checks
    assert isinstance(events, list)
    for ev in events:
        assert ev["schema_version"] == "sanitized-event-v1.0.0"
        assert ev["run_id"] == run_id
        assert "source_event_hash" in ev

        # Confirm no forbidden keys in payload
        payload = ev.get("payload", {})
        for forbidden in ["prompt", "messages", "response", "reasoning", "idea"]:
            assert forbidden not in payload


def test_export_sanitized_evidence_idempotency(tmp_path: Path) -> None:
    """VM-CONTRACT-023-03: Re-exporting identical output succeeds; modified output fails."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    # First export
    first = export_sanitized_evidence(workspace, run_id)
    assert first["status"] == "exported"

    # Idempotent re-export
    second = export_sanitized_evidence(workspace, run_id)
    assert second["status"] == "idempotent_success"
    assert second["manifest_sha256"] == first["manifest_sha256"]

    # Tamper existing exported manifest
    dest_dir = workspace / EVIDENCE_ROOT_RELPATH / run_id
    manifest_file = dest_dir / "manifest.json"
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    data["terminal_outcome"] = "tampered"
    manifest_file.write_bytes(canonical_json_bytes(data))

    # Re-export must fail closed
    with pytest.raises(IdeationInputError) as exc:
        export_sanitized_evidence(workspace, run_id)
    assert exc.value.code == "EXPORT_EXISTS_MISMATCH"


def test_export_fails_on_unsealed_run(tmp_path: Path) -> None:
    """VM-CONTRACT-023-03: Unsealed run cannot be exported."""
    workspace = _setup_workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: commit approved inputs"],
        cwd=workspace,
        check=True,
    )

    # Only admit without execution
    result = run_new_run(workspace, request, execute=False)
    run_id = result["run_id"]

    with pytest.raises(IdeationInputError) as exc:
        export_sanitized_evidence(workspace, run_id)
    assert exc.value.code == "RUN_NOT_SEALED"


# ==============================================================================
# VM-ISOLATION-01: Cross-Run Guards
# ==============================================================================


def test_cross_run_read_write_denied(tmp_path: Path) -> None:
    """VM-ISOLATION-01: RunStore denies reading or writing files from another run."""
    workspace = _setup_workspace(tmp_path)
    store = RunStore(workspace)

    run_1 = store.create_run()
    run_2 = store.create_run()

    store.write_artifact(run_1.run_id, "artifacts/data.json", b'{"run":1}\n')

    # Attempt to read run 1 artifact through run 2
    with pytest.raises(IdeationInputError) as exc:
        store.read_artifact(run_2.run_id, f"../../{run_1.run_id}/artifacts/data.json")
    assert exc.value.code in {"INVALID_PATH", "PATH_ESCAPE"}

    # Attempt to write into run 1 through run 2
    with pytest.raises(IdeationInputError) as exc:
        store.write_artifact(
            run_2.run_id, f"../../{run_1.run_id}/artifacts/bad.json", b"bad"
        )
    assert exc.value.code in {"INVALID_PATH", "PATH_ESCAPE"}


def test_prior_run_evidence_refused_as_runtime_input(tmp_path: Path) -> None:
    """VM-ISOLATION-01: Prior run artifacts cannot be used as workshop/corpus input."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    prior_run_id = result["run_id"]

    # Attempt to construct NewRunRequest pointing to prior run artifact
    with pytest.raises(IdeationInputError) as exc:
        req = NewRunRequest(
            case_id=CASE_ID,
            workshop=f"artifacts/ideation-runs/{prior_run_id}/artifacts/ideas/000000/idea.json",
            workshop_sha256="0" * 64,
            corpus="data/corpus.json",
            corpus_sha256="0" * 64,
            max_num_generations=1,
            num_reflections=1,
        )
        req.validate()
    assert exc.value.code == "CROSS_RUN_INPUT_FORBIDDEN"


def test_exclusive_create_conflict_denied(tmp_path: Path) -> None:
    """VM-ISOLATION-01: RunStore.create_run refuses duplicate run_id."""
    workspace = _setup_workspace(tmp_path)
    store = RunStore(workspace)

    handle = store.create_run()
    with pytest.raises(IdeationInputError) as exc:
        store.create_run(run_id=handle.run_id)
    assert exc.value.code == "RUN_ROOT_EXISTS"


def test_wrong_run_id_and_latest_glob_denied(tmp_path: Path) -> None:
    """VM-ISOLATION-01: Invalid run_id, latest, and glob patterns are refused."""
    for bad in ["latest", "*", "run-*", "../other", ""]:
        with pytest.raises(IdeationInputError) as exc:
            _validate_run_id(bad)
        assert exc.value.code == "INVALID_RUN_ID"


# ==============================================================================
# VM-ISOLATION-02: Path & Symlink Attack Set
# ==============================================================================


def test_path_attacks_fail_closed(tmp_path: Path) -> None:
    """VM-ISOLATION-02: Absolute, dot-dot, backslash, denormalized paths fail closed."""
    workspace = _setup_workspace(tmp_path)
    store = RunStore(workspace)
    handle = store.create_run()

    for bad in [
        "/etc/passwd",
        "../escape.json",
        "artifacts\\win.json",
        "./denorm.json",
        "artifacts/",
        " artifacts/x.json",
    ]:
        with pytest.raises(IdeationInputError) as exc:
            store.write_artifact(handle.run_id, bad, b"data")
        assert exc.value.code in {"INVALID_PATH", "PATH_ESCAPE"}

        with pytest.raises(IdeationInputError) as exc:
            store.read_artifact(handle.run_id, bad)
        assert exc.value.code in {"INVALID_PATH", "PATH_ESCAPE"}


def test_symlink_attacks_fail_closed(tmp_path: Path) -> None:
    """VM-ISOLATION-02: Symlinks in run root or artifact paths fail closed."""
    workspace = _setup_workspace(tmp_path)
    store = RunStore(workspace)
    handle = store.create_run()

    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")

    # Symlink as an artifact inside run root
    art_dir = workspace / "artifacts/ideation-runs" / handle.run_id / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    symlink = art_dir / "symlink.json"
    symlink.symlink_to(outside)

    with pytest.raises(IdeationInputError) as exc:
        store.read_artifact(handle.run_id, "artifacts/symlink.json")
    assert exc.value.code == "SYMLINK_FORBIDDEN"

    with pytest.raises(IdeationInputError) as exc:
        store.build_artifact_inventory(handle.run_id)
    assert exc.value.code == "SYMLINK_FORBIDDEN"


# ==============================================================================
# VM-ISOLATION-03: Immutable Attempt & Replay Verification
# ==============================================================================


def test_immutable_attempt_cannot_be_overwritten(tmp_path: Path) -> None:
    """VM-ISOLATION-03: Attempt artifacts are write-once; rewrite fails closed."""
    workspace = _setup_workspace(tmp_path)
    store = RunStore(workspace)
    handle = store.create_run()

    store.write_operation_artifact(
        handle.run_id,
        operation_seq=1,
        attempt_seq=1,
        filename="response.json",
        data=b'{"initial":1}\n',
    )

    with pytest.raises(IdeationInputError) as exc:
        store.write_operation_artifact(
            handle.run_id,
            operation_seq=1,
            attempt_seq=1,
            filename="response.json",
            data=b'{"overwrite":2}\n',
        )
    assert exc.value.code == "ARTIFACT_EXISTS"


def test_replay_recorded_run_verifies_determinism(tmp_path: Path) -> None:
    """VM-ISOLATION-03: Offline replay verifier verifies determinism from recorded evidence."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    replay = replay_recorded_run(workspace, run_id)
    assert replay["replay_status"] == "deterministic_match"
    assert replay["run_id"] == run_id
    assert replay["terminal_outcome"] == "success"
    assert replay["event_count"] >= 5


# ==============================================================================
# CLI Entry Point: Validate & Export subcommands
# ==============================================================================


def test_cli_validate_and_export_commands(tmp_path: Path) -> None:
    """CLI validate and export subcommands observe contract status codes."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    cli_script = REPO_ROOT / "ai_scientist/perform_ideation_temp_free.py"

    # Test CLI validate
    val_proc = subprocess.run(
        [sys.executable, str(cli_script), "validate", "--run-id", run_id],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert val_proc.returncode == 0, val_proc.stderr
    val_output = json.loads(val_proc.stdout)
    assert val_output["status"] == "valid"
    assert val_output["terminal_outcome"] == "success"

    # Test CLI export
    exp_proc = subprocess.run(
        [sys.executable, str(cli_script), "export", "--run-id", run_id],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert exp_proc.returncode == 0, exp_proc.stderr
    exp_output = json.loads(exp_proc.stdout)
    assert exp_output["status"] == "exported"

    # Test CLI validate on corrupt run
    (workspace / "artifacts/ideation-runs" / run_id / "request.json").unlink()
    bad_val_proc = subprocess.run(
        [sys.executable, str(cli_script), "validate", "--run-id", run_id],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    assert bad_val_proc.returncode == 1
    err_output = json.loads(bad_val_proc.stderr)
    assert err_output["code"] == "RUN_CORRUPT"


def test_adversarial_forbidden_path_scans() -> None:
    """Adversarial check: all absolute paths, Windows drives, and private roots are blocked."""
    for bad_path in [
        "/etc/passwd",
        "/private/var/folders/secret",
        "/home/user/code",
        "C:\\Users\\admin\\secret.txt",
        "D:/workspace/leak",
        "some/path/artifacts/ideation-runs/secret",
        "nested/data/raw/papers.csv",
        "path/with\\backslash",
        "path/with/../traversal",
    ]:
        with pytest.raises(IdeationInputError) as exc:
            _scan_for_forbidden_paths({"key": bad_path})
        assert exc.value.code == "RELEASE_GATE_FORBIDDEN_PATH"


def test_adversarial_target_paper_leak_detection(tmp_path: Path) -> None:
    """Adversarial check: target paper identifiers from raw CSV are extracted and blocked."""
    workspace = _setup_workspace(tmp_path)
    targets = _load_target_identities(workspace, CASE_ID)
    assert TARGET_ID in targets
    assert any("Target Paper Alpha" in t for t in targets)

    with pytest.raises(IdeationInputError) as exc:
        _scan_for_target_leaks(f"text containing {TARGET_ID}", targets)
    assert exc.value.code == "RELEASE_GATE_TARGET_LEAK"


def test_adversarial_export_extra_uninventoried_file_conflict(tmp_path: Path) -> None:
    """Adversarial check: existing export directory with extra uninventoried files fails closed."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    # First export succeeds
    res = export_sanitized_evidence(workspace, run_id)
    assert res["status"] == "exported"

    # Inject an extra uninventoried file into destination
    dest_dir = workspace / EVIDENCE_ROOT_RELPATH / run_id
    (dest_dir / "untracked_spy.txt").write_text("leak", encoding="utf-8")

    with pytest.raises(IdeationInputError) as exc:
        export_sanitized_evidence(workspace, run_id)
    assert exc.value.code == "EXPORT_EXISTS_MISMATCH"


def test_adversarial_write_artifact_to_symlink_leaf_denied(tmp_path: Path) -> None:
    """Adversarial check: writing an artifact where the leaf target is a symlink fails closed."""
    workspace = _setup_workspace(tmp_path)
    store = RunStore(workspace)
    handle = store.create_run()

    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    run_root = workspace / "artifacts/ideation-runs" / handle.run_id
    art_dir = run_root / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    symlink_target = art_dir / "poisoned.json"
    symlink_target.symlink_to(outside)

    with pytest.raises(IdeationInputError) as exc:
        store.write_artifact(
            handle.run_id, "artifacts/poisoned.json", b'{"safe": true}\n'
        )
    assert exc.value.code == "SYMLINK_FORBIDDEN"
