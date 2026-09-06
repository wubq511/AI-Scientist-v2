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
import uuid

import pytest

from ai_scientist.ideation.admission import NewRunRequest
from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.controller import IdeationController
from ai_scientist.ideation.deepseek import (
    DeepSeekAdapter,
    ModelRoundError,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted, fail
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.resume import resume_run
from ai_scientist.ideation.run_store import RunStore
from ai_scientist.perform_ideation_temp_free import (
    _run_new_run,
    _run_resume,
    run_new_run,
)

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
        store.write_artifact(
            run.run_id, "artifacts/validations/probe.json", b"second\n"
        )

    run_root = _run_root(workspace, run.run_id)
    assert (run_root / "artifacts/validations/probe.json").read_bytes() == b"first\n"
    staging = run_root / "staging"
    assert not staging.exists() or not any(staging.iterdir())


def test_append_event_rejects_stale_writer_epoch(tmp_path: Path) -> None:
    """writer_epoch is a fencing token: an old writer's append fails closed."""
    workspace = _workspace(tmp_path)
    store = RunStore(workspace)
    run = store.create_run()
    store.append_event(run.run_id, {"event_type": "preflight_started", "payload": {}})
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


def _admitted_workspace(
    tmp_path: Path, monkeypatch: Any
) -> tuple[Path, dict[str, str]]:
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
    orphan = run_root / "artifacts/operations/000001/attempts/000001/request.json"
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


def test_execute_round_resume_attempts_keep_in_call_retry_budget(
    tmp_path: Path,
) -> None:
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


# ==========================================================================
# Slice 4/5 shared helpers: scripted runs, crash injection, equivalence maps
# ==========================================================================

_SEARCH_CONTENT = (
    'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}'
)
_SEARCH_RESPONSE_ID = "chatcmpl-t10-search"
_FINALIZE_RESPONSE_ID = "chatcmpl-t10-finalize"
_IDEA_NAME = "adaptive_temporal_cueing"


def _idea_payload(name: str) -> dict[str, Any]:
    return {
        "Name": name,
        "Title": "Adaptive Temporal Cueing for Migraine Forecasting",
        "Short Hypothesis": "Continuous passive symptom tracking with adaptive temporal cueing improves early warning accuracy for migraine attacks.",
        "Related Work": "Existing forecasting approaches rely on static clinical records; this proposal introduces adaptive temporal cueing from passive sensing streams.",
        "Abstract": "Migraine forecasting remains challenging due to symptom variability. We propose an adaptive temporal cueing framework that learns individualized warning windows from passive telemetry.",
        "Experiments": [
            "Benchmark adaptive cueing against static baseline predictors on multi-center clinical cohorts.",
            "Ablation study on temporal cueing window lengths and passive sensor feature subsets.",
        ],
        "Risk Factors and Limitations": [
            "Sensitivity to intermittent missing sensor telemetry.",
            "Variation in patient symptom reporting consistency.",
        ],
    }


def _search_stub() -> TransportResponse:
    return _stub(_SEARCH_CONTENT, _SEARCH_RESPONSE_ID)


def _finalize_stub(workspace: Path, corpus_rel: str) -> TransportResponse:
    paper_id = _first_paper_id(workspace, corpus_rel)
    content = (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(_idea_payload(_IDEA_NAME))}, '
        f'"grounding": ["{paper_id}"]}}'
    )
    return _stub(content, _FINALIZE_RESPONSE_ID)


def _success_stubs(workspace: Path, corpus_rel: str) -> list[TransportResponse]:
    return [_search_stub(), _finalize_stub(workspace, corpus_rel)]


def _new_request(inputs: dict[str, str]) -> NewRunRequest:
    return NewRunRequest(
        case_id=CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=2,
    )


def _admit(workspace: Path, inputs: dict[str, str], monkeypatch: Any) -> str:
    _approve_cost(monkeypatch)
    result = run_new_run(workspace, _new_request(inputs), execute=False)
    assert result["status"] == "admitted"
    return result["run_id"]


def _execute(
    workspace: Path,
    run_id: str,
    transport: StubTransport,
    store: RunStore | None = None,
) -> dict[str, Any]:
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )
    return IdeationController(workspace, run_id, store=store, adapter=adapter).run()


def _resume(
    workspace: Path,
    run_id: str,
    transport: StubTransport,
    monkeypatch: Any,
    store: RunStore | None = None,
) -> dict[str, Any]:
    _approve_cost(monkeypatch)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )
    return resume_run(workspace, run_id, adapter=adapter, store=store)


def _run_baseline_success(
    workspace: Path, inputs: dict[str, str], monkeypatch: Any
) -> tuple[str, StubTransport]:
    """Run A: the never-interrupted reference run sealed `success`."""
    run_id = _admit(workspace, inputs, monkeypatch)
    transport = StubTransport(_success_stubs(workspace, inputs["corpus"]))
    result = _execute(workspace, run_id, transport)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    return run_id, transport


def _bad_request_response() -> TransportResponse:
    return TransportResponse(
        status_code=400,
        headers={"content-type": "application/json"},
        body=canonical_json_bytes({"error": "bad request"}),
        duration_ms=20.0,
    )


def _run_baseline_failed(
    workspace: Path, inputs: dict[str, str], monkeypatch: Any
) -> str:
    """Run A-fail: the never-interrupted reference run sealed `failed`."""
    run_id = _admit(workspace, inputs, monkeypatch)
    result = _execute(workspace, run_id, StubTransport([_bad_request_response()]))
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "configuration"
    return run_id


def _kill_sigint(payload: dict[str, Any]) -> TransportResponse:
    os.kill(os.getpid(), signal.SIGINT)
    raise AssertionError("the signal handler must abort before this returns")


_TRACE_DROP_TYPES = frozenset({"interrupted", "resumed", "orphans_quarantined"})
_TRACE_DROP_PAYLOAD_KEYS = frozenset({"cost_cny", "duration_ms", "total_attempts"})


def _semantic_trace(run_root: Path) -> list[dict[str, Any]]:
    """Lifecycle-free, timing-free event projection for A/B equivalence.

    A resumed run legitimately carries `interrupted`/`resumed`/
    `orphans_quarantined` lifecycle records, failed attempts, and its own
    writer epoch / chain coordinates; every remaining event must equal the
    never-interrupted reference run.
    """
    trace: list[dict[str, Any]] = []
    for event in _read_events(run_root):
        event_type = event["event_type"]
        if event_type in _TRACE_DROP_TYPES:
            continue
        payload = event.get("payload", {})
        if (
            event_type == "provider_attempt.finished"
            and payload.get("outcome") != "success"
        ):
            continue
        if event_type == "operation.failed" and payload.get("disposition") == "suspend":
            continue
        entry: dict[str, Any] = {"event_type": event_type}
        operation = event.get("operation")
        if operation is not None:
            entry["operation"] = {
                "operation_kind": operation.get("operation_kind"),
                "operation_seq": operation.get("operation_seq"),
            }
        if "pipeline_position" in event:
            entry["pipeline_position"] = event["pipeline_position"]
        entry["payload"] = {
            key: value
            for key, value in payload.items()
            if key not in _TRACE_DROP_PAYLOAD_KEYS
        }
        refs = event.get("artifact_refs")
        if refs is not None:
            entry["artifact_refs"] = sorted(
                (ref["role"], ref["media_type"]) for ref in refs
            )
        trace.append(entry)
    return trace


_BYTE_MAP_NAMES = frozenset(
    {"response.json", "payload.json", "idea.json", "grounding.json"}
)


def _artifact_byte_map(run_root: Path) -> dict[str, str]:
    """Attempt-coordinate-normalized content map of deterministic artifacts.

    request.json embeds the run-bound user_id; audit.json/sidecar.json embed
    timestamps and run identity — none of them are comparable across runs.
    """
    artifacts_root = run_root / "artifacts"
    result: dict[str, str] = {}
    for path in sorted(artifacts_root.rglob("*")):
        if not path.is_file() or path.name not in _BYTE_MAP_NAMES:
            continue
        rel = path.relative_to(run_root).as_posix()
        rel = re.sub(r"attempts/\d{6}", "attempts/X", rel)
        result[rel] = sha256_bytes(path.read_bytes())
    return result


def _sent_requests(transport: StubTransport) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in request.items() if key != "user_id"}
        for request in transport.sent_requests
    ]


def _assert_single_resume_epoch2(run_root: Path, events: list[dict[str, Any]]) -> None:
    resumed = [event for event in events if event["event_type"] == "resumed"]
    assert len(resumed) == 1
    assert resumed[0]["writer_epoch"] == 2
    approval_rel = "artifacts/validations/resume-approval-000002.json"
    assert (run_root / approval_rel).is_file()
    assert any(
        ref["relative_path"] == approval_rel
        for ref in resumed[0].get("artifact_refs", [])
    )


# --------------------------------------------------------------------------
# VM-FAULT-02: interruption injection at commit-path stages
# --------------------------------------------------------------------------


class _CrashStore(RunStore):
    """Aborts with RunInterrupted at the first matching commit, exactly once."""

    def __init__(
        self,
        workspace: Path,
        *,
        artifact_name: str | None = None,
        event_match: Any | None = None,
    ) -> None:
        super().__init__(workspace)
        self._artifact_name = artifact_name
        self._event_match = event_match
        self.crashed = False

    def _crash_once(self) -> None:
        self.crashed = True
        raise RunInterrupted("SIGKILL")

    def _rename_staged(self, staging_path: Path, target: Path, *, label: str) -> None:
        if not self.crashed and self._artifact_name is not None:
            if self._artifact_name == "seal.json":
                matched = target.name == "seal.json"
            else:
                # The operation-artifact guard keeps the run-root request.json
                # from matching the "request.json" artifact name.
                matched = (
                    target.name == self._artifact_name
                    and "artifacts/operations/" in target.as_posix()
                )
            if matched:
                self._crash_once()
        return super()._rename_staged(staging_path, target, label=label)

    def append_event(
        self,
        run_id: str,
        event: dict[str, Any],
        *,
        prev_event_hash: str | None = None,
    ) -> Any:
        if (
            not self.crashed
            and self._event_match is not None
            and self._event_match(event)
        ):
            self._crash_once()
        return super().append_event(run_id, event, prev_event_hash=prev_event_hash)


def _match_provider_attempt(event: dict[str, Any]) -> bool:
    return event.get("event_type") == "provider_attempt.finished"


def _match_model_op_finished(event: dict[str, Any]) -> bool:
    return (
        event.get("event_type") == "operation.finished"
        and (event.get("operation") or {}).get("operation_kind") == "model_inference"
    )


def _match_tool_result(event: dict[str, Any]) -> bool:
    return (
        event.get("event_type") == "action_outcome"
        and (event.get("payload") or {}).get("outcome") == "tool_result"
    )


def _match_finalize_accepted(event: dict[str, Any]) -> bool:
    return (
        event.get("event_type") == "action_outcome"
        and (event.get("payload") or {}).get("outcome") == "finalize_accepted"
    )


def _match_generation_finished(event: dict[str, Any]) -> bool:
    return event.get("event_type") == "generation.finished"


def _match_terminal(event: dict[str, Any]) -> bool:
    return event.get("event_type") == "terminal"


@pytest.mark.parametrize(
    "crash_kwargs, stub_start, expected_remaining",
    [
        pytest.param(
            {"artifact_name": "request.json"}, 0, 2, id="commit-request-artifact"
        ),
        pytest.param(
            {"artifact_name": "response.json"}, 0, 2, id="commit-response-artifact"
        ),
        pytest.param(
            {"event_match": _match_provider_attempt}, 0, 2, id="commit-attempt-event"
        ),
        pytest.param(
            {"event_match": _match_model_op_finished},
            1,
            1,
            id="commit-model-op-finished-event",
        ),
        pytest.param(
            {"event_match": _match_tool_result}, 1, 1, id="commit-tool-result-event"
        ),
        pytest.param(
            {"event_match": _match_finalize_accepted},
            2,
            0,
            id="commit-finalize-accepted-event",
        ),
        pytest.param(
            {"event_match": _match_generation_finished},
            2,
            0,
            id="commit-generation-finished-event",
        ),
    ],
)
def test_vm_fault_02_commit_point_interruption_resumes_to_equivalent_chain(
    tmp_path: Path,
    monkeypatch: Any,
    crash_kwargs: dict[str, Any],
    stub_start: int,
    expected_remaining: int,
) -> None:
    """SIGKILL-style interruption at a commit point leaves no half-committed
    evidence; the approved resume seals a chain equivalent to the
    never-interrupted reference run (VM-FAULT-02)."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    crash_store = _CrashStore(workspace, **crash_kwargs)
    with pytest.raises(RunInterrupted):
        _execute(
            workspace,
            run_b,
            StubTransport(_success_stubs(workspace, inputs["corpus"])),
            store=crash_store,
        )
    assert crash_store.crashed
    run_root_b = _run_root(workspace, run_b)
    assert not (run_root_b / "seal.json").exists()

    resume_stubs = _success_stubs(workspace, inputs["corpus"])[stub_start:]
    result = _resume(workspace, run_b, StubTransport(resume_stubs), monkeypatch)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)

    events_b = _read_events(run_root_b)
    _assert_single_resume_epoch2(run_root_b, events_b)
    # The fresh cost approval re-estimates the remaining work only: a round
    # whose model response is already committed replays for free.
    approval = parse_json_bytes(
        (run_root_b / "artifacts/validations/resume-approval-000002.json").read_bytes(),
        label="resume approval",
    )
    assert approval["remaining_model_rounds"] == expected_remaining
    assert RunStore(workspace).verify_chain(run_b) == len(events_b)


@pytest.mark.parametrize(
    "crash_kwargs",
    [
        pytest.param({"event_match": _match_terminal}, id="commit-terminal-event"),
        pytest.param({"artifact_name": "seal.json"}, id="commit-seal-artifact"),
    ],
)
def test_vm_fault_02_interrupted_terminal_failure_seals_identically_on_resume(
    tmp_path: Path, monkeypatch: Any, crash_kwargs: dict[str, Any]
) -> None:
    """A run interrupted while sealing its terminal `failed` outcome is
    sealed by the resume with the identical failure evidence (VM-FAULT-02)."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a = _run_baseline_failed(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    crash_store = _CrashStore(workspace, **crash_kwargs)
    with pytest.raises(RunInterrupted):
        _execute(
            workspace,
            run_b,
            StubTransport([_bad_request_response()]),
            store=crash_store,
        )
    assert crash_store.crashed
    run_root_b = _run_root(workspace, run_b)
    assert not (run_root_b / "seal.json").exists()

    result = _resume(workspace, run_b, StubTransport([]), monkeypatch)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "configuration"

    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)

    events_b = _read_events(run_root_b)
    _assert_single_resume_epoch2(run_root_b, events_b)
    assert RunStore(workspace).verify_chain(run_b) == len(events_b)


# --------------------------------------------------------------------------
# VM-REPLAY-04: SIGINT mid-call; resume replays byte-identical requests
# --------------------------------------------------------------------------


def test_vm_replay_04_sigint_mid_call_resume_reaches_equivalent_chain(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """SIGINT during the round-1 transport call suspends the run; the approved
    resume rebuilds the message history from the chain, re-issues the
    byte-identical round-1 request, and seals a chain equivalent to the
    never-interrupted reference run (VM-REPLAY-04)."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    transport_b_pre = StubTransport([_search_stub(), _kill_sigint])
    with pytest.raises(RunInterrupted) as exc_info:
        _execute(workspace, run_b, transport_b_pre)
    assert exc_info.value.signal_name == "SIGINT"
    run_root_b = _run_root(workspace, run_b)
    assert not (run_root_b / "seal.json").exists()
    events_pre = _read_events(run_root_b)
    assert events_pre[-1]["event_type"] == "interrupted"
    assert events_pre[-1]["writer_epoch"] == 1
    # The in-flight round-1 request committed but no event references it yet.
    orphan_rel = "artifacts/operations/000003/attempts/000001/request.json"
    assert (run_root_b / orphan_rel).is_file()

    transport_b_resume = StubTransport([_finalize_stub(workspace, inputs["corpus"])])
    result = _resume(workspace, run_b, transport_b_resume, monkeypatch)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 1

    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)

    # The interrupted round-1 request was re-issued byte-identically: the
    # rebuilt message history reproduces the exact reference request.
    sent_a = _sent_requests(transport_a)
    assert len(sent_a) == 2
    sent_b = _sent_requests(transport_b_pre) + _sent_requests(transport_b_resume)
    assert sent_b == [sent_a[0], sent_a[1], sent_a[1]]

    # The orphaned request bytes were quarantined under the new writer epoch.
    quarantined = sorted((run_root_b / "quarantine").rglob("request.json"))
    assert len(quarantined) == 1
    events_b = _read_events(run_root_b)
    quarantine_events = [
        event for event in events_b if event["event_type"] == "orphans_quarantined"
    ]
    assert len(quarantine_events) == 1
    assert quarantine_events[0]["writer_epoch"] == 2
    record = quarantine_events[0]["payload"]["orphans"][0]
    assert record["relative_path"] == orphan_rel
    assert sha256_bytes(quarantined[0].read_bytes()) == record["sha256"]
    _assert_single_resume_epoch2(run_root_b, events_b)
    assert RunStore(workspace).verify_chain(run_b) == len(events_b)


def test_repeated_suspend_resume_cycles_keep_equivalent_chain(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Two consecutive suspensions (initial run + first resume) still resume
    to the reference chain under writer epoch 3."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(RunInterrupted):
        _execute(workspace, run_b, StubTransport([_search_stub(), _kill_sigint]))
    with pytest.raises(RunInterrupted):
        _resume(workspace, run_b, StubTransport([_kill_sigint]), monkeypatch)
    result = _resume(
        workspace,
        run_b,
        StubTransport([_finalize_stub(workspace, inputs["corpus"])]),
        monkeypatch,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    run_root_b = _run_root(workspace, run_b)
    events = _read_events(run_root_b)
    interrupted = [event for event in events if event["event_type"] == "interrupted"]
    resumed = [event for event in events if event["event_type"] == "resumed"]
    assert [event["writer_epoch"] for event in interrupted] == [1, 2]
    assert [event["writer_epoch"] for event in resumed] == [2, 3]
    assert {event["writer_epoch"] for event in events if "writer_epoch" in event} == {
        1,
        2,
        3,
    }
    assert (run_root_b / "artifacts/validations/resume-approval-000002.json").is_file()
    assert (run_root_b / "artifacts/validations/resume-approval-000003.json").is_file()

    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)
    assert RunStore(workspace).verify_chain(run_b) == len(events)


# --------------------------------------------------------------------------
# VM-FAULT-03: storage/IO failures classify as suspend, never seal
# --------------------------------------------------------------------------


class _FullDiskOnceStore(RunStore):
    """First provider-response staging write hits ENOSPC (VM-FAULT-03)."""

    def __init__(self, workspace: Path) -> None:
        super().__init__(workspace)
        self.failed = False

    def _stage_bytes(self, staging_path: Path, data: bytes, *, label: str) -> None:
        if not self.failed and label == "provider response":
            self.failed = True
            raise OSError(28, "No space left on device")
        return super()._stage_bytes(staging_path, data, label=label)


class _EventIOFailStore(RunStore):
    """First tool_result action_outcome append hits an I/O failure."""

    def __init__(self, workspace: Path) -> None:
        super().__init__(workspace)
        self.failed = False

    def append_event(
        self,
        run_id: str,
        event: dict[str, Any],
        *,
        prev_event_hash: str | None = None,
    ) -> Any:
        if (
            not self.failed
            and event.get("event_type") == "action_outcome"
            and (event.get("payload") or {}).get("outcome") == "tool_result"
        ):
            self.failed = True
            fail("STORAGE_WRITE_FAILED", "simulated I/O failure on event append")
        return super().append_event(run_id, event, prev_event_hash=prev_event_hash)


def test_vm_fault_03_disk_full_mid_commit_suspends_then_resumes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """ENOSPC during the response staging write raises STORAGE_WRITE_FAILED,
    leaves the run unsealed, and resumes to the reference chain."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(IdeationInputError, match="STORAGE_WRITE_FAILED"):
        _execute(
            workspace,
            run_b,
            StubTransport(_success_stubs(workspace, inputs["corpus"])),
            store=_FullDiskOnceStore(workspace),
        )
    run_root_b = _run_root(workspace, run_b)
    assert not (run_root_b / "seal.json").exists()
    assert not any(
        event["event_type"] == "interrupted" for event in _read_events(run_root_b)
    )

    result = _resume(
        workspace,
        run_b,
        StubTransport(_success_stubs(workspace, inputs["corpus"])),
        monkeypatch,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)
    events_b = _read_events(run_root_b)
    _assert_single_resume_epoch2(run_root_b, events_b)
    assert RunStore(workspace).verify_chain(run_b) == len(events_b)


def test_vm_fault_03_event_append_io_failure_suspends_then_resumes(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """An I/O failure on the action_outcome append suspends the run; the
    resume completes the cut commit from the chain and seals equivalently."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(IdeationInputError, match="STORAGE_WRITE_FAILED"):
        _execute(
            workspace,
            run_b,
            StubTransport(_success_stubs(workspace, inputs["corpus"])),
            store=_EventIOFailStore(workspace),
        )
    run_root_b = _run_root(workspace, run_b)
    assert not (run_root_b / "seal.json").exists()
    assert not any(
        event["event_type"] == "action_outcome" for event in _read_events(run_root_b)
    )

    result = _resume(
        workspace,
        run_b,
        StubTransport([_finalize_stub(workspace, inputs["corpus"])]),
        monkeypatch,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)
    events_b = _read_events(run_root_b)
    _assert_single_resume_epoch2(run_root_b, events_b)
    assert RunStore(workspace).verify_chain(run_b) == len(events_b)


# --------------------------------------------------------------------------
# Slice 4: resume gates and approval
# --------------------------------------------------------------------------


def test_resume_rejects_malformed_run_id(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(IdeationInputError, match="INVALID_RUN_ID"):
        resume_run(workspace, "not-a-run-id")


def test_resume_rejects_unknown_run_id(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(IdeationInputError, match="RUN_NOT_FOUND"):
        resume_run(workspace, str(uuid.uuid4()))


def test_resume_rejects_sealed_run(tmp_path: Path, monkeypatch: Any) -> None:
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)
    with pytest.raises(IdeationInputError, match="RUN_ALREADY_SEALED"):
        resume_run(workspace, run_a)


def test_resume_rejects_preflight_rejected_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256="0" * 64,
        max_num_generations=1,
        num_reflections=2,
    )
    with pytest.raises(IdeationInputError):
        run_new_run(workspace, request, execute=False)
    run_id = next((workspace / "artifacts/ideation-runs").iterdir()).name
    events = _read_events(_run_root(workspace, run_id))
    assert events[-1]["event_type"] == "preflight_rejected"
    with pytest.raises(IdeationInputError, match="RUN_PREFLIGHT_REJECTED"):
        resume_run(workspace, run_id)


def test_resume_rejects_tampered_event_chain(tmp_path: Path, monkeypatch: Any) -> None:
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_id = _admit(workspace, inputs, monkeypatch)
    first_event_path = _run_root(workspace, run_id) / "events/00000001.json"
    tampered = parse_json_bytes(first_event_path.read_bytes(), label="event 00000001")
    tampered["payload"]["steps"] = 8
    first_event_path.write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(IdeationInputError, match="RUN_CORRUPT"):
        resume_run(workspace, run_id)


def test_resume_rejects_missing_referenced_artifact(
    tmp_path: Path, monkeypatch: Any
) -> None:
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(RunInterrupted):
        _execute(workspace, run_b, StubTransport([_search_stub(), _kill_sigint]))
    referenced = (
        _run_root(workspace, run_b)
        / "artifacts/operations/000001/attempts/000001/response.json"
    )
    assert referenced.is_file()
    referenced.unlink()
    with pytest.raises(IdeationInputError, match="RUN_CORRUPT"):
        resume_run(workspace, run_b)


def test_resume_requires_interactive_approval(tmp_path: Path, monkeypatch: Any) -> None:
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(RunInterrupted):
        _execute(workspace, run_b, StubTransport([_search_stub(), _kill_sigint]))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=StubTransport([_finalize_stub(workspace, inputs["corpus"])]),
    )
    with pytest.raises(IdeationInputError, match="APPROVAL_UNAVAILABLE"):
        resume_run(workspace, run_b, adapter=adapter, stream=io.StringIO())
    # The rejected attempt leaves the run unsealed and resumable.
    assert not (_run_root(workspace, run_b) / "seal.json").exists()


def test_resume_approval_rejection_is_repeatable(
    tmp_path: Path, monkeypatch: Any
) -> None:
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)
    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(RunInterrupted):
        _execute(workspace, run_b, StubTransport([_search_stub(), _kill_sigint]))

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    monkeypatch.setattr("sys.stdin", io.StringIO("no\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=StubTransport([_finalize_stub(workspace, inputs["corpus"])]),
    )
    with pytest.raises(IdeationInputError, match="APPROVAL_REJECTED"):
        resume_run(workspace, run_b, adapter=adapter, stream=io.StringIO())
    assert not (_run_root(workspace, run_b) / "seal.json").exists()

    # A later approval resumes the same run to the reference chain.
    result = _resume(
        workspace,
        run_b,
        StubTransport([_finalize_stub(workspace, inputs["corpus"])]),
        monkeypatch,
    )
    assert result["terminal_outcome"] == "success"
    run_root_a = _run_root(workspace, run_a)
    run_root_b = _run_root(workspace, run_b)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)


def test_suspend_class_provider_failure_resumes_at_next_attempt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Exhausted in-call retries on a suspend-class provider failure leave the
    run unsealed; the resume re-executes at the next physical attempt."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    run_b = _admit(workspace, inputs, monkeypatch)
    rate_limited = TransportResponse(
        status_code=429,
        headers={"content-type": "application/json", "retry-after": "0"},
        body=canonical_json_bytes({"error": "slow down"}),
        duration_ms=25.0,
    )
    with pytest.raises(ModelRoundError):
        _execute(workspace, run_b, StubTransport([rate_limited, rate_limited]))
    run_root_b = _run_root(workspace, run_b)
    assert not (run_root_b / "seal.json").exists()
    pre_events = _read_events(run_root_b)
    suspend_failures = [
        event for event in pre_events if event["event_type"] == "operation.failed"
    ]
    assert len(suspend_failures) == 1
    assert suspend_failures[0]["payload"]["disposition"] == "suspend"
    assert suspend_failures[0]["payload"]["error_code"] == "rate_limited"

    result = _resume(
        workspace,
        run_b,
        StubTransport(_success_stubs(workspace, inputs["corpus"])),
        monkeypatch,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    events = _read_events(run_root_b)
    attempt_seqs = [
        event["operation"]["attempt_seq"]
        for event in events
        if event["event_type"] == "provider_attempt.finished"
    ]
    # Round 0: attempts 1-2 rate-limited, attempt 3 succeeds; round 1: op 3.
    assert attempt_seqs == [1, 2, 3, 1]
    run_root_a = _run_root(workspace, run_a)
    assert _semantic_trace(run_root_b) == _semantic_trace(run_root_a)
    assert _artifact_byte_map(run_root_b) == _artifact_byte_map(run_root_a)
    _assert_single_resume_epoch2(run_root_b, events)
    assert RunStore(workspace).verify_chain(run_b) == len(events)


def test_resume_after_preflight_interruption_reruns_preflight(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A run interrupted before its Run Admission re-runs the idempotent
    preflight on resume: no writer epoch bump, no `resumed` event, no resume
    approval artifact — the cost approval lives inside the admission."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    _approve_cost(monkeypatch)

    import ai_scientist.ideation.admission as admission_module

    original_loader = admission_module._load_approved_corpus
    calls = {"count": 0}

    def flaky_loader(workspace_root: Path, request: NewRunRequest) -> dict[str, Any]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise KeyboardInterrupt
        return original_loader(workspace_root, request)

    monkeypatch.setattr(admission_module, "_load_approved_corpus", flaky_loader)

    with pytest.raises(KeyboardInterrupt):
        run_new_run(workspace, _new_request(inputs), execute=False)
    run_id = next((workspace / "artifacts/ideation-runs").iterdir()).name
    assert not (_run_root(workspace, run_id) / "admission.json").exists()

    result = _resume(
        workspace,
        run_id,
        StubTransport(_success_stubs(workspace, inputs["corpus"])),
        monkeypatch,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    run_root = _run_root(workspace, run_id)
    events = _read_events(run_root)
    assert not any(event["event_type"] == "resumed" for event in events)
    assert not any(event["event_type"] == "interrupted" for event in events)
    assert not any(event["event_type"] == "orphans_quarantined" for event in events)
    validations_dir = run_root / "artifacts/validations"
    approvals = (
        list(validations_dir.glob("resume-approval-*.json"))
        if validations_dir.is_dir()
        else []
    )
    assert approvals == []
    assert RunStore(workspace).verify_chain(run_id) == len(events)


def test_cli_resume_exit_codes(tmp_path: Path, monkeypatch: Any) -> None:
    """`resume` CLI seam: exit 0 sealed, exit 2 resume_rejected, exit 3 suspended."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)

    # Exit 0: the suspended run resumes to its seal.
    run_b = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(RunInterrupted):
        _execute(workspace, run_b, StubTransport([_search_stub(), _kill_sigint]))
    _approve_cost(monkeypatch)
    ok_adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=StubTransport([_finalize_stub(workspace, inputs["corpus"])]),
    )
    args_b = argparse.Namespace(run_id=run_b)
    assert (
        _run_resume(
            args_b, workspace_root=workspace, stream=io.StringIO(), adapter=ok_adapter
        )
        == 0
    )

    # Exit 2: resuming a sealed run is rejected deterministically.
    assert _run_resume(args_b, workspace_root=workspace, stream=io.StringIO()) == 2

    # Exit 3: a suspend-class failure during resume leaves the run unsealed.
    run_c = _admit(workspace, inputs, monkeypatch)
    with pytest.raises(RunInterrupted):
        _execute(workspace, run_c, StubTransport([_search_stub(), _kill_sigint]))
    _approve_cost(monkeypatch)
    failing_adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=StubTransport(
            [ConnectionError("boom"), ConnectionError("boom again")]
        ),
    )
    args_c = argparse.Namespace(run_id=run_c)
    assert (
        _run_resume(
            args_c,
            workspace_root=workspace,
            stream=io.StringIO(),
            adapter=failing_adapter,
        )
        == 3
    )
    assert not (_run_root(workspace, run_c) / "seal.json").exists()


def test_resume_completes_admitted_event_cut_after_admission_commit(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Crash in the approved window between the write-once admission commit
    and the `admitted` event append: resume completes the event epoch-less,
    then executes the run to the reference chain."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    run_a, _transport_a = _run_baseline_success(workspace, inputs, monkeypatch)

    class AdmissionCrashStore(_CrashStore):
        def __init__(self, ws: Path) -> None:
            super().__init__(
                ws, event_match=lambda event: event.get("event_type") == "admitted"
            )

    import ai_scientist.ideation.admission as admission_module

    monkeypatch.setattr(admission_module, "RunStore", AdmissionCrashStore)
    _approve_cost(monkeypatch)
    with pytest.raises(RunInterrupted):
        run_new_run(workspace, _new_request(inputs), execute=False)
    run_id = [
        path.name
        for path in (workspace / "artifacts/ideation-runs").iterdir()
        if path.name != run_a
    ][0]
    run_root = _run_root(workspace, run_id)
    assert (run_root / "admission.json").is_file()
    assert not any(
        event["event_type"] == "admitted" for event in _read_events(run_root)
    )

    result = _resume(
        workspace,
        run_id,
        StubTransport(_success_stubs(workspace, inputs["corpus"])),
        monkeypatch,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"

    events = _read_events(run_root)
    admitted = [event for event in events if event["event_type"] == "admitted"]
    assert len(admitted) == 1
    # The completion replays exactly what the original preflight would have
    # written: epoch-less, pinned to the committed admission hash.
    assert "writer_epoch" not in admitted[0]
    assert _semantic_trace(run_root) == _semantic_trace(_run_root(workspace, run_a))
    assert _artifact_byte_map(run_root) == _artifact_byte_map(
        _run_root(workspace, run_a)
    )
    _assert_single_resume_epoch2(run_root, events)
    assert RunStore(workspace).verify_chain(run_id) == len(events)


def test_cli_new_run_admission_interrupt_reports_run_id(
    tmp_path: Path, monkeypatch: Any, capsysbinary: Any
) -> None:
    """A pre-admission interruption still names the minted run_id in the
    suspension report so the operator can resume by exact run_id."""
    workspace, inputs = _admitted_workspace(tmp_path, monkeypatch)
    _approve_cost(monkeypatch)

    import ai_scientist.ideation.admission as admission_module

    def interrupting_loader(workspace_root: Path, request: NewRunRequest) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(admission_module, "_load_approved_corpus", interrupting_loader)

    args = argparse.Namespace(
        case_id=CASE_ID,
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        prompt_profile="cross-domain-v1",
        entry="new-run",
        max_num_generations=1,
        num_reflections=2,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
    )
    assert _run_new_run(args, workspace_root=workspace, execute=False) == 3
    payload = json.loads(capsysbinary.readouterr().out)
    assert payload["status"] == "suspended"
    assert payload["code"] == "KEYBOARD_INTERRUPT"
    run_id = next((workspace / "artifacts/ideation-runs").iterdir()).name
    assert payload["run_id"] == run_id
