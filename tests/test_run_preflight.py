"""Nine-step fail-closed new-run preflight tests (ticket 04).

Covers VM-CONTRACT-024-02: the new-run CLI runs the approved preflight
sequence in order; each step fails closed with retained request/preflight
evidence and no admission.json; non-interactive stdin (anything other than
an exact `yes`) rejects before admission. The whole slice performs no model
calls.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCRIPT = REPO_ROOT / "ai_scientist" / "perform_ideation_temp_free.py"
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"

CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"
CORPUS_CASE = "case-0123456789abcdef0123456789abcdef"


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
    # Preflight verifies a clean worktree; give the workspace a real git repo.
    # Run roots are private evidence and must be gitignored like production.
    (workspace / ".gitignore").write_text(
        "artifacts/ideation-runs/\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.invalid"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Fixture"],
        cwd=workspace,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture workspace"],
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
    """Build, validate, and approve the fixture corpus; return path + hash."""
    build = _prepare_cli(
        workspace,
        "corpus",
        "build",
        "--case-id",
        CORPUS_CASE,
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
        "rationale": "Fixture bundle approved for admission tests.",
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
    import hashlib

    corpus_sha = hashlib.sha256((workspace / corpus_rel).read_bytes()).hexdigest()
    return corpus_rel, corpus_sha


def _run_new_run(
    workspace: Path,
    *,
    stdin: str | None = "yes\n",
    env_extra: dict[str, str] | None = None,
    **overrides: str,
) -> subprocess.CompletedProcess[str]:
    """Run the new-run CLI with the approval prompt driven over a real pty."""
    # Preflight verifies a clean worktree; the fixture approvals must be
    # committed before the run request is evaluated.
    _commit_all(workspace)
    environment = os.environ.copy()
    environment["DEEPSEEK_API_KEY"] = "fixture-present"
    environment["COLUMNS"] = "80"
    if env_extra:
        environment.update(env_extra)
    arguments = [
        sys.executable,
        str(ENTRY_SCRIPT),
        "new-run",
        "--case-id",
        overrides.get("case_id", CASE_ID),
        "--max-num-generations",
        overrides.get("max_num_generations", "1"),
        "--num-reflections",
        overrides.get("num_reflections", "2"),
        "--prompt-profile",
        overrides.get("prompt_profile", "ml-baseline-v1"),
    ]
    for flag, key in (
        ("--workshop", "workshop"),
        ("--workshop-sha256", "workshop_sha256"),
        ("--corpus", "corpus"),
        ("--corpus-sha256", "corpus_sha256"),
    ):
        if key in overrides:
            arguments.extend([flag, overrides[key]])
    master, slave = os.openpty()
    process = subprocess.Popen(
        arguments,
        cwd=workspace,
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    os.close(slave)
    # Always write at least one newline so a blocking input() in the child
    # can never deadlock the suite; an empty line is simply not `yes`. The
    # master stays open until the child exits: closing it early would
    # discard the unread pty buffer and turn answers into EOF.
    os.write(master, ((stdin or "") + "\n").encode("utf-8"))
    stdout_text, stderr_text = process.communicate()
    os.close(master)
    return subprocess.CompletedProcess(
        args=arguments,
        returncode=process.returncode,
        stdout=stdout_text,
        stderr=stderr_text,
    )


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
    checks = {
        "abstract_is_neutral_problem_scope": True,
        "allows_multiple_method_families": True,
        "keywords_are_established_terms": True,
        "no_answer_leakage": True,
        "no_identity_leakage": True,
        "target_relevant": True,
        "title_is_identity_free_problem_area": True,
        "tldr_is_open_question_or_tension": True,
        "written_in_english": True,
    }
    import hashlib

    decision = {
        "attempt_manifest_sha256": hashlib.sha256(
            (workspace / attempt_rel).read_bytes()
        ).hexdigest(),
        "candidate_sha256": hashlib.sha256(
            (workspace / attempt["candidate"]["path"]).read_bytes()
        ).hexdigest(),
        "case_id": CASE_ID,
        "checks": checks,
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


def test_new_run_admits_after_all_nine_steps_and_writes_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    from ai_scientist.perform_ideation_temp_free import _run_new_run as cli_run_new_run

    args = argparse.Namespace(
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
    result = cli_run_new_run(args, workspace_root=workspace, execute=False)
    assert result == 0

    runs_root = workspace / "artifacts/ideation-runs"
    run_dirs = [child for child in runs_root.iterdir() if child.is_dir()]
    assert len(run_dirs) == 1
    run_root = run_dirs[0]
    assert (run_root / "admission.json").is_file()
    assert (run_root / "request.json").is_file()
    events = sorted((run_root / "events").glob("*.json"))
    # Step 1 (request schema) precedes the run; step 2 is recorded by the
    # write-once request.json itself; step 9 (admission write) is recorded
    # by the terminal `admitted` event. The remaining six steps each emit
    # one preflight event, plus `preflight_started`: 8 events in total.
    assert len(events) == 8
    admission = json.loads((run_root / "admission.json").read_text(encoding="utf-8"))
    assert admission["case_id"] == CASE_ID
    assert admission["workshop"]["sha256"] == workshop_sha
    assert admission["corpus"]["sha256"] == corpus_sha
    assert admission["cost"]["currency"] == "CNY"

    # No adapter, retriever, or paid work: admission is terminal for this slice.
    assert "deepseek" in json.dumps(admission).lower()


def test_new_run_rejects_bad_case_id_before_any_run_is_created(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    # A full valid argument set with only the case_id malformed: the closed
    # request schema (step 1) must reject before any run root exists.
    result = _run_new_run(
        workspace,
        case_id="not-a-case-id",
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
    )
    assert result.returncode != 0
    assert "INVALID_SCHEMA" in result.stderr
    assert not (workspace / "artifacts/ideation-runs").exists()


def test_new_run_rejects_malformed_sha_and_nonpositive_budgets_before_any_run(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    result = _run_new_run(
        workspace,
        workshop=workshop_rel,
        workshop_sha256="nothex",
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
    )
    assert result.returncode != 0
    assert "INVALID_SCHEMA" in result.stderr
    assert not (workspace / "artifacts/ideation-runs").exists()

    result = _run_new_run(
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations="0",
        workspace=workspace,
    )
    assert result.returncode != 0
    assert "INVALID_SCHEMA" in result.stderr
    assert not (workspace / "artifacts/ideation-runs").exists()


def test_new_run_rejects_dirty_worktree_before_admission(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    _commit_all(workspace)
    # Dirty the worktree after the approvals are committed; run the raw CLI
    # (the _run_new_run helper would commit the dirt away first).
    (workspace / "data/raw/filtered_references.csv").write_bytes(
        (workspace / "data/raw/filtered_references.csv").read_bytes() + b"\n"
    )
    environment = os.environ.copy()
    environment["DEEPSEEK_API_KEY"] = "fixture-present"
    environment["COLUMNS"] = "80"
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRY_SCRIPT),
            "new-run",
            "--case-id",
            CASE_ID,
            "--workshop",
            workshop_rel,
            "--workshop-sha256",
            workshop_sha,
            "--corpus",
            corpus_rel,
            "--corpus-sha256",
            corpus_sha,
            "--max-num-generations",
            "1",
            "--num-reflections",
            "2",
            "--prompt-profile",
            "ml-baseline-v1",
        ],
        cwd=workspace,
        input="yes\n",
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    assert result.returncode != 0
    assert "DIRTY_WORKTREE" in result.stderr
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()


def test_new_run_rejects_workshop_hash_mismatch_with_retained_evidence(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, _workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    result = _run_new_run(
        workspace,
        workshop=workshop_rel,
        workshop_sha256="0" * 64,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
    )
    assert result.returncode != 0
    runs_root = workspace / "artifacts/ideation-runs"
    run_dirs = [child for child in runs_root.iterdir() if child.is_dir()]
    assert len(run_dirs) == 1
    run_root = run_dirs[0]
    assert not (run_root / "admission.json").exists()
    assert (run_root / "request.json").is_file()
    events = sorted((run_root / "events").glob("*.json"))
    assert events, "preflight rejection evidence must be retained"
    last_event = json.loads(events[-1].read_text(encoding="utf-8"))
    assert last_event["event_type"] == "preflight_rejected"
    assert last_event["payload"]["error_code"] == "HASH_MISMATCH"


def test_new_run_rejects_corpus_hash_mismatch_with_retained_evidence(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, _corpus_sha = _approved_corpus(workspace)

    result = _run_new_run(
        workspace,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256="0" * 64,
    )
    assert result.returncode != 0
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()
    assert (run_root / "request.json").is_file()
    assert sorted((run_root / "events").glob("*.json"))


def test_new_run_rejects_unapproved_workshop(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    (workspace / "drafts").mkdir(exist_ok=True)
    (workspace / "drafts/unapproved.md").write_text(
        "# Title: Anything\n\n## Keywords\none\n\n## TL;DR\nQuestion?\n\n"
        "## Abstract\nNeutral scope.\n",
        encoding="utf-8",
    )
    import hashlib

    sha = hashlib.sha256((workspace / "drafts/unapproved.md").read_bytes()).hexdigest()

    result = _run_new_run(
        workspace,
        workshop="drafts/unapproved.md",
        workshop_sha256=sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
    )
    assert result.returncode != 0
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()


def test_new_run_rejects_unapproved_corpus(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    build = _prepare_cli(
        workspace,
        "corpus",
        "build",
        "--case-id",
        CORPUS_CASE,
        "--target-paper-id",
        TARGET_ID,
        "--build-id",
        "build-002",
    )
    assert build.returncode == 0, build.stderr
    bundle_rel = json.loads(build.stdout)["bundle_path"]
    import hashlib

    sha = hashlib.sha256(
        (workspace / bundle_rel / "corpus.json").read_bytes()
    ).hexdigest()

    result = _run_new_run(
        workspace,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=f"{bundle_rel}/corpus.json",
        corpus_sha256=sha,
    )
    assert result.returncode != 0
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()


def test_new_run_requires_case_consistency_between_workshop_and_corpus(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    # Approve the primary-case corpus first so a decision template exists.
    _approved_corpus(workspace)
    # Build a corpus for a different case under the same target.
    other_case = "case-ffffffffffffffffffffffffffffffff"
    build = _prepare_cli(
        workspace,
        "corpus",
        "build",
        "--case-id",
        other_case,
        "--target-paper-id",
        TARGET_ID,
        "--build-id",
        "build-003",
    )
    assert build.returncode == 0, build.stderr
    bundle_rel = json.loads(build.stdout)["bundle_path"]
    decision = json.loads(
        (workspace / "reviews/corpus-approval-decision.json").read_text(
            encoding="utf-8"
        )
    )
    decision_path = workspace / "reviews/corpus-approval-decision-2.json"
    manifest = json.loads(
        (workspace / bundle_rel / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    decision["case_id"] = other_case
    decision["bundle_content_sha256"] = manifest["bundle_content_sha256"]
    decision["corpus_sha256"] = manifest["inventory"]["corpus.json"]
    decision["validation_report_sha256"] = manifest["inventory"][
        "validation-report.json"
    ]
    decision["versions"] = manifest["versions"]
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

    sha = hashlib.sha256(
        (workspace / bundle_rel / "corpus.json").read_bytes()
    ).hexdigest()

    result = _run_new_run(
        workspace,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=f"{bundle_rel}/corpus.json",
        corpus_sha256=sha,
    )
    assert result.returncode != 0
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()


def test_new_run_fails_closed_without_credential_presence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    result = _run_new_run(
        workspace,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        env_extra={"DEEPSEEK_API_KEY": ""},
    )
    assert result.returncode != 0
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()


def test_new_run_rejects_anything_but_exact_yes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    for stdin in ["no\n", "YES\n", "", "yes extra\n"]:
        result = _run_new_run(
            workspace,
            stdin=stdin,
            workshop=workshop_rel,
            workshop_sha256=workshop_sha,
            corpus=corpus_rel,
            corpus_sha256=corpus_sha,
        )
        assert result.returncode != 0, f"stdin={stdin!r} must be rejected"
        run_root = next(
            child
            for child in (workspace / "artifacts/ideation-runs").iterdir()
            if child.is_dir()
        )
        assert not (run_root / "admission.json").exists()


def test_new_run_fails_closed_in_a_non_interactive_environment(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    # stdin closed: approval prompt cannot be answered -> fail closed.
    environment = os.environ.copy()
    environment["DEEPSEEK_API_KEY"] = "fixture-present"
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRY_SCRIPT),
            "new-run",
            "--case-id",
            CASE_ID,
            "--max-num-generations",
            "1",
            "--num-reflections",
            "2",
            "--workshop",
            workshop_rel,
            "--workshop-sha256",
            workshop_sha,
            "--corpus",
            corpus_rel,
            "--corpus-sha256",
            corpus_sha,
            "--prompt-profile",
            "ml-baseline-v1",
        ],
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode != 0
    run_root = next(
        child
        for child in (workspace / "artifacts/ideation-runs").iterdir()
        if child.is_dir()
    )
    assert not (run_root / "admission.json").exists()


def test_new_run_rejects_unknown_flags(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(ENTRY_SCRIPT),
            "new-run",
            "--case-id",
            CASE_ID,
            "--model",
            "gpt-4o",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_new_run_rejects_path_escape_inputs_before_any_run(tmp_path: Path) -> None:
    """CLI input paths must cross the guarded workspace path boundary."""
    workspace = _workspace(tmp_path)
    workshop_rel, workshop_sha = _approved_workshop_paths(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)

    for bad_path, flag, sha_flag, sha in (
        ("../outside.md", "--workshop", "--workshop-sha256", workshop_sha),
        ("/etc/hosts", "--corpus", "--corpus-sha256", corpus_sha),
    ):
        arguments = {
            "workshop": workshop_rel,
            "workshop_sha256": workshop_sha,
            "corpus": corpus_rel,
            "corpus_sha256": corpus_sha,
        }
        key = flag.removeprefix("--").replace("-", "_")
        arguments[key] = bad_path
        arguments[sha_flag.removeprefix("--").replace("-", "_")] = sha
        result = _run_new_run(workspace, **arguments)
        assert result.returncode != 0, f"{bad_path} must be rejected"
        assert "PATH_ESCAPE" in result.stderr or "INVALID_PATH" in result.stderr

    run_dirs = [
        child
        for child in (workspace / "artifacts/ideation-runs").glob("*")
        if child.is_dir()
    ]
    for run_root in run_dirs:
        assert not (run_root / "admission.json").exists()
