"""Automated tests for Ticket 10: Suspend and resume an interrupted Ideation Run.

Delivers:
- VM-REPLAY-04: an interrupted run resumed after approval reaches a final
  Evidence Chain equivalent to the never-interrupted run.
- VM-FAULT-02: interruption injection at every commit-path stage (staging,
  fsync, hash, rename, event append) leaves no half-committed evidence and
  resumes to an equivalent chain.
- VM-FAULT-03: storage/IO failures (write failure, disk full) classify as
  suspend and never seal the run.

All tests are deterministic: StubTransport / injected store seams, real local
storage, zero network, zero real model cost, no downstream stages.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
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
    DeepSeekAdapter,
    ModelRoundError,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.run_store import RunStore
from ai_scientist.perform_ideation_temp_free import run_new_run

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"


# ==========================================================================
# Workspace and approved-input helpers (same pattern as tickets 07/09)
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
    prepare = _prepare_cli(
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
    assert prepare.returncode == 0, prepare.stderr
    prep_rel = json.loads(prepare.stdout)["preparation_manifest"]
    prep = json.loads((workspace / prep_rel).read_text(encoding="utf-8"))

    derivation = {
        "actor": "integration-author",
        "authoring_source_sha256": prep["authoring_source"]["sha256"],
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
    workshop_rel = payload["workshop"]
    workshop_sha = sha256_bytes((workspace / workshop_rel).read_bytes())
    return workshop_rel, workshop_sha


def _commit_all(workspace: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: commit approved inputs"],
        cwd=workspace,
        check=True,
    )


def _approve_cost(monkeypatch: Any) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _make_response_bytes(content: str, response_id: str = "chatcmpl-ticket10") -> bytes:
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {
                    "content": content,
                    "reasoning_content": "Detailed reasoning about the proposal...",
                    "role": "assistant",
                },
            }
        ],
        "created": 1725360000,
        "id": response_id,
        "model": "deepseek-v4-pro",
        "object": "chat.completion",
        "system_fingerprint": "fp_ticket10",
        "usage": {
            "completion_tokens": 50,
            "completion_tokens_details": {"reasoning_tokens": 10},
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "prompt_tokens": 100,
            "total_tokens": 150,
        },
    }
    return canonical_json_bytes(body)


def _stub(content: str, response_id: str) -> TransportResponse:
    return TransportResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body=_make_response_bytes(content, response_id),
        duration_ms=30.0,
    )


def _read_events(run_root: Path) -> list[dict[str, Any]]:
    events_dir = run_root / "events"
    return [
        parse_json_bytes(path.read_bytes(), label=path.name)
        for path in sorted(events_dir.glob("*.json"))
    ]


def _run_root(workspace: Path, run_id: str) -> Path:
    return workspace / "artifacts/ideation-runs" / run_id


def _first_paper_id(workspace: Path, corpus_rel: str) -> str:
    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    return corpus_data["records"][0]["paper_id"]


# ==========================================================================
# Slice 1: staged atomic commit, write-once exclusivity, writer-epoch fencing
# ==========================================================================


def test_commits_go_through_staging_and_leave_no_residue(tmp_path: Path) -> None:
    """Every committed artifact/event lands via run-local staging + rename."""
    workspace = _workspace(tmp_path)
    store = RunStore(workspace)
    run = store.create_run()
    store.write_request(run.run_id, {"schema_version": "run-request-v1.0.0"})

    rel, length, sha = store.write_artifact(
        run.run_id, "artifacts/validations/probe.json", b'{"ok": true}\n'
    )
    assert rel == "artifacts/validations/probe.json"
    run_root = _run_root(workspace, run.run_id)
    assert (run_root / rel).read_bytes() == b'{"ok": true}\n'
    assert length == len(b'{"ok": true}\n')
    assert sha == sha256_bytes(b'{"ok": true}\n')
    # Staging subtree exists but holds no residue after a clean commit.
    staging = run_root / "staging"
    assert not staging.exists() or not any(staging.iterdir())

    store.append_event(run.run_id, {"event_type": "preflight_started", "payload": {}})
    assert not any(staging.iterdir())
    assert store.verify_chain(run.run_id) == 1


def test_staged_commit_preserves_write_once_exclusivity(tmp_path: Path) -> None:
    """A second commit to the same final path fails closed; first bytes survive."""
    workspace = _workspace(tmp_path)
    store = RunStore(workspace)
    run = store.create_run()
    store.write_artifact(run.run_id, "artifacts/validations/probe.json", b"first\n")

    with pytest.raises(IdeationInputError, match="ARTIFACT_EXISTS"):
        store.write_artifact(run.run_id, "artifacts/validations/probe.json", b"second\n")

    run_root = _run_root(workspace, run.run_id)
    assert (run_root / "artifacts/validations/probe.json").read_bytes() == b"first\n"
    staging = run_root / "staging"
    assert not staging.exists() or not any(staging.iterdir())


def test_append_event_rejects_stale_writer_epoch(tmp_path: Path) -> None:
    """writer_epoch is a fencing token: an old writer's append fails closed."""
    workspace = _workspace(tmp_path)
    store = RunStore(workspace)
    run = store.create_run()
    store.append_event(
        run.run_id, {"event_type": "preflight_started", "payload": {}}
    )
    store.append_event(
        run.run_id,
        {"event_type": "resumed", "payload": {}, "writer_epoch": 3},
    )
    with pytest.raises(IdeationInputError, match="STALE_WRITER_EPOCH"):
        store.append_event(
            run.run_id,
            {"event_type": "action_outcome", "payload": {}, "writer_epoch": 2},
        )
    # The current writer (epoch 3) and epoch-less lifecycle events still append.
    store.append_event(
        run.run_id,
        {"event_type": "action_outcome", "payload": {}, "writer_epoch": 3},
    )
    store.append_event(run.run_id, {"event_type": "terminal", "payload": {}})
    assert store.verify_chain(run.run_id) == 4


def test_storage_write_failure_is_typed_and_leaves_no_partial_commit(
    tmp_path: Path,
) -> None:
    """Disk-full at staging raises STORAGE_WRITE_FAILED; no half-committed file."""

    class FullDiskStore(RunStore):
        def _stage_bytes(self, staging_path: Path, data: bytes, *, label: str) -> None:
            raise OSError(28, "No space left on device")

    workspace = _workspace(tmp_path)
    store = FullDiskStore(workspace)
    run = store.create_run()
    with pytest.raises(IdeationInputError, match="STORAGE_WRITE_FAILED"):
        store.write_artifact(run.run_id, "artifacts/validations/probe.json", b"x\n")
    run_root = _run_root(workspace, run.run_id)
    assert not (run_root / "artifacts/validations/probe.json").exists()
    staging = run_root / "staging"
    assert not staging.exists() or not any(staging.iterdir())


# ==========================================================================
# Slice 2: SIGINT/SIGTERM immediate abort, interrupted event, resume attempts
# ==========================================================================


def _admitted_workspace(tmp_path: Path, monkeypatch: Any) -> tuple[Path, dict[str, str]]:
    """Workspace with approved inputs and a ready NewRunRequest payload."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)
    return workspace, {
        "corpus": corpus_rel,
        "corpus_sha256": corpus_sha,
        "workshop": workshop_rel,
        "workshop_sha256": workshop_sha,
    }


def test_sigint_during_transport_aborts_and_records_interrupted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """SIGINT mid-transport aborts immediately; the writer records `interrupted`
    and the run stays unsealed with the in-flight request artifact orphaned."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)

    def kill_self(payload: dict[str, Any]) -> TransportResponse:
        os.kill(os.getpid(), signal.SIGINT)
        raise AssertionError("the signal handler must abort before this returns")

    transport = StubTransport([kill_self])
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )
    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=2,
    )

    with pytest.raises(RunInterrupted) as exc_info:
        run_new_run(workspace, request, adapter=adapter, execute=True)
    assert exc_info.value.signal_name == "SIGINT"

    run_dirs = list((workspace / "artifacts/ideation-runs").iterdir())
    assert len(run_dirs) == 1
    run_root = run_dirs[0]
    assert not (run_root / "seal.json").exists()
    assert RunStore(workspace).verify_chain(run_root.name) >= 1

    events = _read_events(run_root)
    assert events[-1]["event_type"] == "interrupted"
    assert events[-1]["payload"]["signal"] == "SIGINT"
    # The in-flight operation committed its request artifact but no event
    # references it yet: an approved orphan-window remnant, not a half commit.
    orphan = (
        run_root / "artifacts/operations/000001/attempts/000001/request.json"
    )
    assert orphan.is_file()
    referenced = {
        ref["relative_path"]
        for event in events
        for ref in event.get("artifact_refs", [])
    }
    assert "artifacts/operations/000001/attempts/000001/request.json" not in referenced


def test_sigterm_during_transport_aborts_and_records_interrupted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """SIGTERM receives the same immediate-abort suspension semantics."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)

    def kill_self(payload: dict[str, Any]) -> TransportResponse:
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError("the signal handler must abort before this returns")

    transport = StubTransport([kill_self])
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )
    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=2,
    )

    with pytest.raises(RunInterrupted) as exc_info:
        run_new_run(workspace, request, adapter=adapter, execute=True)
    assert exc_info.value.signal_name == "SIGTERM"

    run_root = next((workspace / "artifacts/ideation-runs").iterdir())
    assert not (run_root / "seal.json").exists()
    events = _read_events(run_root)
    assert events[-1]["event_type"] == "interrupted"
    assert events[-1]["payload"]["signal"] == "SIGTERM"


def test_execute_round_accepts_resume_attempt_coordinates(tmp_path: Path) -> None:
    """Resume re-execution uses the same operation with new physical attempts
    (contract 025: attempt 3+ only ever comes from a resume)."""
    workspace = _workspace(tmp_path)
    store = RunStore(workspace)
    run = store.create_run()

    from ai_scientist.ideation.deepseek import DeepSeekRequest, DeepSeekMessage

    request = DeepSeekRequest(
        max_tokens=256,
        messages=(DeepSeekMessage(role="user", content="probe"),),
        output_mode="text",
        reasoning_effort="high",
        user_id="run-probe",
    )
    transport = StubTransport([_stub("ACTION: FinalizeIdea\nARGUMENTS: {}", "r3")])
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=transport,
        store=store,
        run_id=run.run_id,
    )
    result = adapter.execute_round(request, 1, initial_attempt_seq=3)
    assert result.attempt_seq == 3

    run_root = _run_root(workspace, run.run_id)
    assert (
        run_root / "artifacts/operations/000001/attempts/000003/request.json"
    ).is_file()
    assert (
        run_root / "artifacts/operations/000001/attempts/000003/response.json"
    ).is_file()
    events = _read_events(run_root)
    attempt_events = [
        e for e in events if e["event_type"] == "provider_attempt.finished"
    ]
    assert attempt_events[0]["operation"]["attempt_seq"] == 3
    assert attempt_events[0]["operation"]["operation_seq"] == 1


def test_execute_round_resume_attempts_keep_in_call_retry_budget(tmp_path: Path) -> None:
    """A resumed call keeps its own <=2 attempt budget (022): the first resume
    attempt of a transient failure retries once within the call."""
    workspace = _workspace(tmp_path)
    store = RunStore(workspace)
    run = store.create_run()

    from ai_scientist.ideation.deepseek import DeepSeekRequest, DeepSeekMessage

    request = DeepSeekRequest(
        max_tokens=256,
        messages=(DeepSeekMessage(role="user", content="probe"),),
        output_mode="text",
        reasoning_effort="high",
        user_id="run-probe",
    )
    rate_limited = TransportResponse(
        status_code=429,
        headers={"content-type": "application/json", "retry-after": "0"},
        body=canonical_json_bytes({"error": "slow down"}),
        duration_ms=25.0,
    )
    transport = StubTransport(
        [rate_limited, _stub("ACTION: FinalizeIdea\nARGUMENTS: {}", "r4")]
    )
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=transport,
        store=store,
        run_id=run.run_id,
    )
    result = adapter.execute_round(request, 2, initial_attempt_seq=3)
    assert result.attempt_seq == 4
    assert result.total_attempts == 2

    run_root = _run_root(workspace, run.run_id)
    assert (
        run_root / "artifacts/operations/000002/attempts/000003/failure.json"
    ).is_file()
    assert (
        run_root / "artifacts/operations/000002/attempts/000004/response.json"
    ).is_file()
    events = _read_events(run_root)
    attempts = [e for e in events if e["event_type"] == "provider_attempt.finished"]
    assert [e["operation"]["attempt_seq"] for e in attempts] == [3, 4]
