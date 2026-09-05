"""Batch pre-authorization: write-once approval for named frozen slots.

Robert's one explicit decision covers named matrix slots instead of typing
`yes` per run. The document is write-once inside the comparison package,
the admission verifies its covering entry (slot identity + recomputed
worst-case ceiling) before paid work, the approval provenance lands in the
Run Admission verbatim, and every miss (missing file, schema drift,
unknown slot, ceiling drift) fails closed rather than silently falling
back to the interactive prompt. Runs outside the batch keep the
interactive `yes` path.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

from ai_scientist.ideation.canonical import canonical_json_bytes
from ai_scientist.ideation.comparison_preauthorization import (
    PREAUTHORIZATION_ENV_VAR,
    PREAUTHORIZATION_NAME,
    build_preauthorization_document,
    covering_preauthorization,
    write_preauthorization,
)
from ai_scientist.ideation.errors import IdeationInputError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"
MATRIX_SHA = "a" * 64


# ==========================================================================
# Unit tests: document build, write-once, covering resolution (fail closed)
# ==========================================================================


def _document(**overrides: Any) -> dict[str, Any]:
    slot = {
        "run_index": 3,
        "case_id": CASE_ID,
        "prompt_profile_id": "ml-baseline-v1",
        "worst_case_bound_cny": "7.08",
    }
    kwargs: dict[str, Any] = {
        "matrix_sha256": MATRIX_SHA,
        "slots": [slot, dict(slot, run_index=4)],
        "approved_by": "Robert",
        "approved_at": "2026-09-05T15:30:00.000000Z",
        "note": "Remaining six matrix slots of 002-cross-domain-ideation-prompt",
    }
    kwargs.update(overrides)
    return build_preauthorization_document(
        matrix_sha256=kwargs.pop("matrix_sha256"),
        slots=kwargs.pop("slots"),
        approved_by=kwargs.pop("approved_by"),
        approved_at=kwargs.pop("approved_at"),
        note=kwargs.pop("note", None),
    )


def test_build_rejects_empty_slots_and_duplicate_indexes() -> None:
    with pytest.raises(IdeationInputError):
        build_preauthorization_document(
            matrix_sha256=MATRIX_SHA,
            slots=[],
            approved_by="Robert",
            approved_at="2026-09-05T15:30:00.000000Z",
        )
    slot = {
        "run_index": 3,
        "case_id": CASE_ID,
        "prompt_profile_id": "ml-baseline-v1",
        "worst_case_bound_cny": "7.08",
    }
    with pytest.raises(IdeationInputError):
        build_preauthorization_document(
            matrix_sha256=MATRIX_SHA,
            slots=[slot, dict(slot)],
            approved_by="Robert",
            approved_at="2026-09-05T15:30:00.000000Z",
        )


def _stub_package(tmp_path: Path) -> Path:
    """A minimal comparison package whose run matrix pins the write-once."""
    package = tmp_path / "package"
    package.mkdir()
    (package / "run-matrix.json").write_bytes(
        canonical_json_bytes({"schema_version": "comparison-run-matrix-v1.0.0"})
    )
    return package


def test_write_once_and_second_write_fails_closed(tmp_path: Path) -> None:
    package = _stub_package(tmp_path)
    document = _document()
    _first_path, digest = write_preauthorization(package, document)
    assert len(digest) == 64
    with pytest.raises(IdeationInputError) as exc:
        write_preauthorization(package, document)
    assert exc.value.code == "ARTIFACT_EXISTS"


def test_covering_slot_returns_provenance(tmp_path: Path, monkeypatch: Any) -> None:
    package = _stub_package(tmp_path)
    path, _digest = write_preauthorization(package, _document())
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    record = covering_preauthorization(
        case_id=CASE_ID,
        prompt_profile_id="ml-baseline-v1",
        worst_case_bound_cny="7.08",
    )
    assert record is not None
    assert record["approved_by"] == "Robert"
    assert record["confirmed_with"] == "batch_preauthorization"
    assert record["total_upper_bound_cny"] == "7.08"
    assert len(record["document_sha256"]) == 64


def test_unset_env_keeps_interactive_path(monkeypatch: Any) -> None:
    monkeypatch.delenv(PREAUTHORIZATION_ENV_VAR, raising=False)
    assert (
        covering_preauthorization(
            case_id=CASE_ID,
            prompt_profile_id="ml-baseline-v1",
            worst_case_bound_cny="7.08",
        )
        is None
    )


def test_missing_file_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(tmp_path / "missing.json"))
    with pytest.raises(IdeationInputError) as exc:
        covering_preauthorization(
            case_id=CASE_ID,
            prompt_profile_id="ml-baseline-v1",
            worst_case_bound_cny="7.08",
        )
    assert exc.value.code == "PREAUTHORIZATION_UNREADABLE"


def test_uncovered_slot_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    package = _stub_package(tmp_path)
    path, _digest = write_preauthorization(package, _document())
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    with pytest.raises(IdeationInputError) as exc:
        covering_preauthorization(
            case_id="case-8c6ddd334df3bf058720ac8f14ce3db6",
            prompt_profile_id="ml-baseline-v1",
            worst_case_bound_cny="7.08",
        )
    assert exc.value.code == "PREAUTHORIZATION_SLOT_NOT_COVERED"


def test_ceiling_drift_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    package = _stub_package(tmp_path)
    path, _digest = write_preauthorization(package, _document())
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    with pytest.raises(IdeationInputError) as exc:
        covering_preauthorization(
            case_id=CASE_ID,
            prompt_profile_id="ml-baseline-v1",
            worst_case_bound_cny="7.09",
        )
    assert exc.value.code == "PREAUTHORIZATION_CEILING_DRIFT"


def test_prompt_profile_mismatch_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    package = _stub_package(tmp_path)
    path, _digest = write_preauthorization(package, _document())
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    with pytest.raises(IdeationInputError) as exc:
        covering_preauthorization(
            case_id=CASE_ID,
            prompt_profile_id="cross-domain-v1",
            worst_case_bound_cny="7.08",
        )
    assert exc.value.code == "PREAUTHORIZATION_SLOT_NOT_COVERED"


def test_schema_drift_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    package = _stub_package(tmp_path)
    path, _digest = write_preauthorization(package, _document())
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["approved_at"]
    path.write_bytes(canonical_json_bytes(payload))
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    with pytest.raises(IdeationInputError) as exc:
        covering_preauthorization(
            case_id=CASE_ID,
            prompt_profile_id="ml-baseline-v1",
            worst_case_bound_cny="7.08",
        )
    assert exc.value.code == "INVALID_SCHEMA"


# ==========================================================================
# Integration: a covered slot admits without interactive input; a slot
# outside the batch keeps the interactive path.
# ==========================================================================


def _workspace(tmp_path: Path) -> Path:
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
        ["git", "config", "user.email", "fixture@example.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture workspace"], cwd=workspace, check=True
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
    """Build, validate, and approve the fixture corpus; return path + hash."""
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
        "rationale": "Fixture bundle approved for preauthorization tests.",
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
    import hashlib

    corpus_rel = f"{bundle_rel}/corpus.json"
    corpus_sha = hashlib.sha256((workspace / corpus_rel).read_bytes()).hexdigest()
    return corpus_rel, corpus_sha


def _approved_workshop_paths(workspace: Path) -> tuple[str, str]:
    """Approve the fixture Workshop through the real prepare/validate/approve CLI."""
    prepare = _prepare_cli(
        workspace,
        "workshop",
        "prepare",
        "--case-id",
        CASE_ID,
        "--target-paper-id",
        TARGET_ID,
        "--preparation-id",
        "preparation-001",
    )
    assert prepare.returncode == 0, prepare.stderr
    preparation_rel = json.loads(prepare.stdout)["preparation_manifest"]
    preparation = json.loads((workspace / preparation_rel).read_text(encoding="utf-8"))
    derivation = {
        "actor": "fixture-author",
        "authoring_source_sha256": preparation["authoring_source"]["sha256"],
        "completed_at": "2026-09-03T01:02:03.000000Z",
        "mechanism": "manual",
        "mechanism_version": "fixture-manual-v1",
        "schema_version": "workshop-derivation-v1.0",
        "source_fields": ["title", "abstract"],
    }
    derivation_path = workspace / "reviews/derivation.json"
    derivation_path.parent.mkdir(parents=True, exist_ok=True)
    derivation_path.write_bytes(
        (json.dumps(derivation, sort_keys=True, separators=(",", ":")) + "\n").encode()
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
        preparation_rel,
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
    import hashlib

    decision = {
        "attempt_manifest_sha256": hashlib.sha256(
            (workspace / attempt_rel).read_bytes()
        ).hexdigest(),
        "candidate_sha256": hashlib.sha256(
            (workspace / attempt["candidate"]["path"]).read_bytes()
        ).hexdigest(),
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
        "reviewer": "fixture-reviewer",
        "schema_version": "workshop-semantic-decision-v1.1",
    }
    decision_path = workspace / "reviews/semantic-decision.json"
    decision_path.write_bytes(
        (json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    approve = _prepare_cli(
        workspace,
        "workshop",
        "approve",
        "--attempt-manifest",
        attempt_rel,
        "--semantic-decision",
        decision_path.relative_to(workspace).as_posix(),
    )
    assert approve.returncode == 0, approve.stderr
    payload = json.loads(approve.stdout)
    import hashlib

    workshop_sha = hashlib.sha256(
        (workspace / payload["workshop"]).read_bytes()
    ).hexdigest()
    return payload["workshop"], workshop_sha


def _commit_all(workspace: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "fixture approvals"],
        cwd=workspace,
        check=True,
    )


def _admission_estimate(workspace: Path) -> str:
    """The recomputed worst-case bound admission step 8 will demand."""
    from ai_scientist.ideation.admission import (
        DEFAULT_MAX_TOKENS,
        MAX_ATTEMPTS_PER_OPERATION,
        WORST_CASE_INPUT_TOKENS_PER_ROUND,
    )
    from ai_scientist.ideation.pricing import load_price_table, worst_case_bound

    estimate = worst_case_bound(
        load_price_table(workspace),
        input_tokens=1 * 2 * WORST_CASE_INPUT_TOKENS_PER_ROUND,
        output_tokens=1 * 2 * DEFAULT_MAX_TOKENS,
        attempts=MAX_ATTEMPTS_PER_OPERATION,
    )
    return str(estimate.total_cny)


def _cli_args(
    workshop_rel: str,
    workshop_sha: str,
    corpus_rel: str,
    corpus_sha: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
        prompt_profile="ml-baseline-v1",
        entry="new-run",
    )


def test_admission_records_batch_preauthorization_without_interactive_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    package = workspace / (
        "artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt"
    )
    package.mkdir(parents=True, exist_ok=True)
    (package / "run-matrix.json").write_bytes(
        canonical_json_bytes({"schema_version": "comparison-run-matrix-v1.0.0"})
    )
    bound = _admission_estimate(workspace)
    path, _digest = write_preauthorization(
        package,
        build_preauthorization_document(
            matrix_sha256=MATRIX_SHA,
            slots=[
                {
                    "run_index": 1,
                    "case_id": CASE_ID,
                    "prompt_profile_id": "ml-baseline-v1",
                    "worst_case_bound_cny": bound,
                }
            ],
            approved_by="Robert",
            approved_at="2026-09-05T15:30:00.000000Z",
        ),
    )
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    # stdin is NOT a tty and holds no `yes`: only the preauthorization can
    # carry this admission.
    monkeypatch.setattr("sys.stdin", io.StringIO("no\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    from ai_scientist.perform_ideation_temp_free import _run_new_run as cli_run_new_run

    assert (
        cli_run_new_run(
            _cli_args(workshop_rel, workshop_sha, corpus_rel, corpus_sha),
            workspace_root=workspace,
            execute=False,
        )
        == 0
    )

    runs_root = workspace / "artifacts/ideation-runs"
    run_root = next(child for child in runs_root.iterdir() if child.is_dir())
    admission = json.loads((run_root / "admission.json").read_text(encoding="utf-8"))
    approval = admission["cost"]["approval"]
    assert approval["confirmed_with"] == "batch_preauthorization"
    assert approval["approved_by"] == "Robert"
    assert approval["total_upper_bound_cny"] == bound
    assert len(approval["preauthorization_document_sha256"]) == 64


def test_admission_outside_covered_slots_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set variable plus an uncovered slot rejects: no silent re-prompting.

    The env var is an operator statement ("this document governs this
    batch"); if the run then falls outside the covered slots, that is an
    operator mistake that must stop the run, never silently fall back to
    the interactive prompt. Only an UNSET variable keeps the interactive
    path in charge.
    """
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    package = workspace / (
        "artifacts/ideation-inputs/comparisons/002-cross-domain-ideation-prompt"
    )
    package.mkdir(parents=True, exist_ok=True)
    (package / "run-matrix.json").write_bytes(
        canonical_json_bytes({"schema_version": "comparison-run-matrix-v1.0.0"})
    )
    bound = _admission_estimate(workspace)
    path, _digest = write_preauthorization(
        package,
        build_preauthorization_document(
            matrix_sha256=MATRIX_SHA,
            slots=[
                {
                    "run_index": 3,
                    # A different case than the request below: the run is
                    # outside the covered slots.
                    "case_id": "case-8c6ddd334df3bf058720ac8f14ce3db6",
                    "prompt_profile_id": "ml-baseline-v1",
                    "worst_case_bound_cny": bound,
                }
            ],
            approved_by="Robert",
            approved_at="2026-09-05T15:30:00.000000Z",
        ),
    )
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setenv(PREAUTHORIZATION_ENV_VAR, str(path))
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    from ai_scientist.perform_ideation_temp_free import _run_new_run as cli_run_new_run

    exit_code = cli_run_new_run(
        _cli_args(workshop_rel, workshop_sha, corpus_rel, corpus_sha),
        workspace_root=workspace,
        execute=False,
    )
    assert exit_code == 2

    # The rejection is a preflight rejection: no admission was written and
    # the minted run root stays unsealed and resumable.
    runs_root = workspace / "artifacts/ideation-runs"
    run_root = next(child for child in runs_root.iterdir() if child.is_dir())
    assert not (run_root / "admission.json").exists()


def test_admission_with_unreadable_env_fails_closed_not_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A set-but-broken preauthorization must not silently fall back to yes."""
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setenv(
        PREAUTHORIZATION_ENV_VAR, str(workspace / PREAUTHORIZATION_NAME)
    )  # missing file
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    from ai_scientist.perform_ideation_temp_free import _run_new_run as cli_run_new_run

    exit_code = cli_run_new_run(
        _cli_args(workshop_rel, workshop_sha, corpus_rel, corpus_sha),
        workspace_root=workspace,
        execute=False,
    )
    assert exit_code == 2
