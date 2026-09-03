"""Integration test for sealing one grounded Ideation Run (Ticket 07).

Delivers VM-INTEGRATION-01:
- Happy path: preflight -> retrieval -> FinalizeIdea -> seal
- Asserts event sequence is valid and contiguous
- Asserts hash chain is continuous from event 1 to final event
- Asserts Terminal Outcome = success
- Asserts seal.json references final event hash and complete artifact inventory
- Zero network calls and zero real model cost via deterministic StubTransport
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
from ai_scientist.ideation.controller import (
    ACTION_OUTCOME_SCHEMA_VERSION,
    IDEA_SIDECAR_SCHEMA_VERSION,
    RUN_SEAL_SCHEMA_VERSION,
    IdeationController,
)
from ai_scientist.ideation.deepseek import (
    DEEPSEEK_MODEL_ID,
    DeepSeekAdapter,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.run_store import RunStore
from ai_scientist.perform_ideation_temp_free import run_new_run

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"


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


def _make_response_bytes(
    content: str, response_id: str = "chatcmpl-test-happy"
) -> bytes:
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
        "model": DEEPSEEK_MODEL_ID,
        "object": "chat.completion",
        "system_fingerprint": "fp_integration",
        "usage": {
            "completion_tokens": 120,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "prompt_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 80},
            "total_tokens": 220,
        },
    }
    return canonical_json_bytes(body)


def test_vm_integration_01_happy_path_seals_ideation_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """VM-INTEGRATION-01: happy path preflight -> retrieval -> FinalizeIdea -> seal."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    # Set up environment for credential check
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")

    # Mock interactive cost approval with "yes"
    import io

    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )

    # Inspect corpus records to get an actual eligible paper_id from filtered references
    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    first_record = corpus_data["records"][0]
    expected_paper_id = first_record["paper_id"]

    # Round 0: model performs SearchLiterature
    round_0_content = (
        "ACTION: SearchLiterature\n"
        'ARGUMENTS: {"query": "clinical forecasting migraine"}'
    )
    # Round 1: model finalizes idea declaring the retrieved paper
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
    store = RunStore(workspace)

    # We provide an adapter builder or pre-constructed adapter
    # Since run_id is minted during admission, we construct the adapter with stub transport
    # Note: DeepSeekAdapter dynamically adopts the admitted run_id and store from admission
    adapter = DeepSeekAdapter(
        price_table=price_table,
        transport=transport,
    )

    result = run_new_run(
        workspace,
        request,
        adapter=adapter,
        store=store,
        execute=True,
    )

    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 1
    run_id = result["run_id"]

    run_root = workspace / "artifacts/ideation-runs" / run_id
    assert run_root.is_dir()

    # Verify seal.json
    seal_path = run_root / "seal.json"
    assert seal_path.is_file()
    seal_bytes = seal_path.read_bytes()
    seal = parse_json_bytes(seal_bytes, label="seal.json")

    assert seal["schema_version"] == RUN_SEAL_SCHEMA_VERSION
    assert seal["run_id"] == run_id
    assert seal["terminal_outcome"] == "success"
    assert seal["terminal_summary"]["outcome"] == "success"
    assert seal["terminal_summary"]["idea_count"] == 1
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 1,
        "budget_exhausted": 0,
    }

    # Verify inventory in seal.json
    inventory = seal["artifact_inventory"]
    assert len(inventory) > 0

    # Ensure inventory is strictly sorted by relative_path
    rel_paths = [item["relative_path"] for item in inventory]
    assert rel_paths == sorted(rel_paths)

    # Every item in inventory must exist and match sha256 + length
    for item in inventory:
        artifact_path = run_root / item["relative_path"]
        assert artifact_path.is_file(), f"Missing artifact {item['relative_path']}"
        data = artifact_path.read_bytes()
        assert len(data) == item["byte_length"]
        assert sha256_bytes(data) == item["sha256"]

    # Verify finalized idea artifacts exist
    idea_json_path = run_root / "artifacts/ideas/000000/idea.json"
    grounding_json_path = run_root / "artifacts/ideas/000000/grounding.json"
    sidecar_json_path = run_root / "artifacts/ideas/000000/sidecar.json"

    assert idea_json_path.is_file()
    assert grounding_json_path.is_file()
    assert sidecar_json_path.is_file()

    idea_data = parse_json_bytes(idea_json_path.read_bytes(), label="idea.json")
    assert idea_data == idea_payload

    grounding_data = parse_json_bytes(
        grounding_json_path.read_bytes(), label="grounding.json"
    )
    assert grounding_data == [expected_paper_id]

    sidecar_data = parse_json_bytes(
        sidecar_json_path.read_bytes(), label="sidecar.json"
    )
    assert sidecar_data["schema_version"] == IDEA_SIDECAR_SCHEMA_VERSION
    assert sidecar_data["run_id"] == run_id
    assert sidecar_data["idea_index"] == 0
    assert sidecar_data["generation_index"] == 0
    assert sidecar_data["declared_grounding"] == [expected_paper_id]
    assert sidecar_data["idea_sha256"] == sha256_bytes(idea_json_path.read_bytes())
    assert sidecar_data["grounding_sha256"] == sha256_bytes(
        grounding_json_path.read_bytes()
    )

    # Verify complete contiguous event chain
    events_dir = run_root / "events"
    event_files = sorted(events_dir.glob("*.json"))
    assert len(event_files) >= 15

    # Check the exact final event matches seal.json
    final_event_file = event_files[-1]
    final_event = parse_json_bytes(final_event_file.read_bytes(), label="final event")
    assert final_event["event_type"] == "terminal"
    assert seal["final_event"]["event_seq"] == final_event["event_seq"]
    assert seal["final_event"]["event_hash"] == final_event["event_hash"]

    # Full chain verification
    verified_count = store.verify_chain(run_id)
    assert verified_count == len(event_files)

    # Verify event types and sequence
    event_types = [
        parse_json_bytes(f.read_bytes(), label=f.name)["event_type"]
        for f in event_files
    ]
    assert event_types[0] == "preflight_started"
    assert event_types[7] == "admitted"
    assert "generation.started" in event_types
    assert "provider_attempt.finished" in event_types
    assert "action_outcome" in event_types
    assert "generation.finished" in event_types
    assert event_types[-1] == "terminal"


def test_cli_seam_executes_and_seals_run(tmp_path: Path, monkeypatch: Any) -> None:
    """Prove the CLI entry point _run_new_run seamlessly drives the controller when execute=True."""
    import argparse
    import io
    from ai_scientist.perform_ideation_temp_free import _run_new_run

    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    idea_payload = {
        "Name": "cli_cueing_idea",
        "Title": "CLI Driven Proposal for Temporal Forecasting",
        "Short Hypothesis": "Automated verification through the CLI seam functions identically to the programmatic controller.",
        "Related Work": "Prior tests validated preflight in isolation; this proves integrated CLI execution.",
        "Abstract": "We evaluate the unified CLI seam driving the ideation loop.",
        "Experiments": [
            "Execute new-run CLI with injected adapter and verify seal emission."
        ],
        "Risk Factors and Limitations": [
            "Requires interactive approval in production."
        ],
    }
    stub_responses = [
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
                "chatcmpl-cli-0",
            ),
            duration_ms=40.0,
        ),
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_payload)}, "grounding": ["{paper_id}"]}}',
                "chatcmpl-cli-1",
            ),
            duration_ms=50.0,
        ),
    ]

    transport = StubTransport(stub_responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)

    args = argparse.Namespace(
        case_id=CASE_ID,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        entry="new-run",
        max_num_generations=1,
        num_reflections=2,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
    )

    exit_code = _run_new_run(
        args,
        workspace_root=workspace,
        adapter=adapter,
        execute=True,
    )
    assert exit_code == 0

    runs_root = workspace / "artifacts/ideation-runs"
    run_dirs = [d for d in runs_root.iterdir() if d.is_dir()]
    assert len(run_dirs) == 1
    run_root = run_dirs[0]

    assert (run_root / "seal.json").is_file()
    seal = json.loads((run_root / "seal.json").read_text(encoding="utf-8"))
    assert seal["terminal_outcome"] == "success"
    assert seal["terminal_summary"]["idea_count"] == 1


def test_multi_generation_happy_path_seals_multiple_ideas(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verify happy path across multiple generations with archive propagation."""
    import io

    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    idea_1 = {
        "Name": "proposal_one",
        "Title": "First Generated Proposal",
        "Short Hypothesis": "Hypothesis 1 on migraine forecasting.",
        "Related Work": "Related work for proposal 1.",
        "Abstract": "Abstract for proposal 1.",
        "Experiments": ["Experiment 1A", "Experiment 1B"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }
    idea_2 = {
        "Name": "proposal_two",
        "Title": "Second Generated Proposal",
        "Short Hypothesis": "Hypothesis 2 exploring complementary telemetry.",
        "Related Work": "Related work for proposal 2.",
        "Abstract": "Abstract for proposal 2.",
        "Experiments": ["Experiment 2A"],
        "Risk Factors and Limitations": ["Limitation 2"],
    }

    stub_responses = [
        # Gen 0, Round 0: Search
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
                "gen0-round0",
            ),
            40.0,
        ),
        # Gen 0, Round 1: Finalize idea 1
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_1)}, "grounding": ["{paper_id}"]}}',
                "gen0-round1",
            ),
            45.0,
        ),
        # Gen 1, Round 0: Search
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
                "gen1-round0",
            ),
            40.0,
        ),
        # Gen 1, Round 1: Finalize idea 2
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_2)}, "grounding": ["{paper_id}"]}}',
                "gen1-round1",
            ),
            50.0,
        ),
    ]

    transport = StubTransport(stub_responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=2,
        num_reflections=2,
    )

    result = run_new_run(
        workspace,
        request,
        adapter=adapter,
        execute=True,
    )

    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 2

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    assert (run_root / "artifacts/ideas/000000/idea.json").is_file()
    assert (run_root / "artifacts/ideas/000001/idea.json").is_file()

    seal = json.loads((run_root / "seal.json").read_text(encoding="utf-8"))
    assert seal["terminal_summary"]["idea_count"] == 2
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 2,
        "budget_exhausted": 0,
    }

    # Verify that in Gen 1, prompt sent to model contained proposal_one in prev_ideas_string
    gen1_request = transport.sent_requests[2]
    user_message = gen1_request["messages"][-1]["content"]
    assert "proposal_one" in user_message


def test_validate_idea_structure_enforces_seven_fields() -> None:
    from ai_scientist.ideation.controller import validate_idea_structure
    from ai_scientist.ideation.errors import IdeationInputError

    valid = {
        "Name": "test_idea",
        "Title": "Test Idea Title",
        "Short Hypothesis": "Short hypothesis text.",
        "Related Work": "Related work discussion.",
        "Abstract": "Proposal abstract text.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }
    assert validate_idea_structure(valid) == valid

    # Missing field
    missing = dict(valid)
    del missing["Abstract"]
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(missing)

    # Extra unknown field
    extra = dict(valid)
    extra["UnknownField"] = "value"
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(extra)

    # Empty string
    empty_str = dict(valid, Title="   ")
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(empty_str)

    # Empty list
    empty_list = dict(valid, Experiments=[])
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(empty_list)


def test_validate_declared_grounding_enforces_paper_eligibility() -> None:
    from ai_scientist.ideation.controller import validate_declared_grounding
    from ai_scientist.ideation.errors import IdeationInputError

    eligible = {"paper_A", "paper_B"}
    assert validate_declared_grounding(["paper_A"], eligible) == ["paper_A"]
    assert validate_declared_grounding(["paper_A", "paper_B"], eligible) == [
        "paper_A",
        "paper_B",
    ]

    # Empty grounding
    with pytest.raises(IdeationInputError, match="EMPTY_GROUNDING"):
        validate_declared_grounding([], eligible)

    # Duplicate paper_id
    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING"):
        validate_declared_grounding(["paper_A", "paper_A"], eligible)

    # Unretrieved paper_id (lying detection)
    with pytest.raises(IdeationInputError, match="UNRETRIEVED_PAPER"):
        validate_declared_grounding(["paper_C"], eligible)


def test_system_prompt_adheres_to_tool_and_grounding_fence() -> None:
    from ai_scientist.ideation.controller import build_system_prompt

    prompt = build_system_prompt()
    assert "SearchLiterature" in prompt
    assert "FinalizeIdea" in prompt
    assert "SearchSemanticScholar" not in prompt
    assert "grounding" in prompt
    assert "paper_id_1" in prompt


# =========================================================================
# First-Principles Adversarial Attack Tests
# =========================================================================


def test_adversarial_tampered_admission_json_is_rejected(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Detect and fail closed if admission.json on disk was tampered with after admission."""
    import io
    from ai_scientist.ideation.admission import admit_new_run
    from ai_scientist.ideation.controller import IdeationController
    from ai_scientist.ideation.errors import IdeationInputError

    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )
    result = admit_new_run(workspace, request)
    run_id = result["run_id"]

    # Tamper with admission.json on disk (e.g. inject extra reflections)
    admission_path = workspace / f"artifacts/ideation-runs/{run_id}/admission.json"
    data = json.loads(admission_path.read_text(encoding="utf-8"))
    data["budgets"]["num_reflections"] = 99
    admission_path.write_bytes(
        (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )

    with pytest.raises(IdeationInputError, match="ADMISSION_TAMPERED"):
        IdeationController(workspace, run_id)


def test_adversarial_tampered_workshop_is_rejected(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Detect and fail closed if pinned workshop content on disk was tampered with."""
    import io
    from ai_scientist.ideation.admission import admit_new_run
    from ai_scientist.ideation.controller import IdeationController
    from ai_scientist.ideation.errors import IdeationInputError

    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )
    result = admit_new_run(workspace, request)
    run_id = result["run_id"]

    # Tamper with workshop file on disk
    (workspace / workshop_rel).write_text(
        "Tampered workshop content!", encoding="utf-8"
    )

    with pytest.raises(IdeationInputError, match="HASH_MISMATCH"):
        IdeationController(workspace, run_id)


def test_adversarial_unallowed_idea_artifact_filename_is_rejected(
    tmp_path: Path,
) -> None:
    """Reject attempt to write idea artifacts outside the canonical set."""
    from ai_scientist.ideation.errors import IdeationInputError

    store = RunStore(tmp_path)
    run_id = "00000000-0000-4000-8000-000000000000"
    (tmp_path / "artifacts/ideation-runs" / run_id).mkdir(parents=True)

    with pytest.raises(IdeationInputError, match="INVALID_PATH"):
        store.write_idea_artifact(run_id, 0, "../escape.json", b"{}")

    with pytest.raises(IdeationInputError, match="INVALID_PATH"):
        store.write_idea_artifact(run_id, 0, "malicious.sh", b"echo pwned")

    with pytest.raises(IdeationInputError, match="INVALID_PATH"):
        store.write_idea_artifact(run_id, 0, "arbitrary.json", b"{}")


def test_adversarial_invalid_idea_index_is_rejected(tmp_path: Path) -> None:
    """Reject invalid idea_index coordinates (negative, bool, or out-of-range)."""
    from ai_scientist.ideation.errors import IdeationInputError

    store = RunStore(tmp_path)
    run_id = "00000000-0000-4000-8000-000000000000"
    (tmp_path / "artifacts/ideation-runs" / run_id).mkdir(parents=True)

    with pytest.raises(IdeationInputError, match="INVALID_COORDINATE"):
        store.write_idea_artifact(run_id, True, "idea.json", b"{}")  # type: ignore[arg-type]

    with pytest.raises(IdeationInputError, match="INVALID_COORDINATE"):
        store.write_idea_artifact(run_id, -1, "idea.json", b"{}")

    with pytest.raises(IdeationInputError, match="INVALID_COORDINATE"):
        store.write_idea_artifact(run_id, 1000000, "idea.json", b"{}")


def test_adversarial_duplicate_idea_name_in_run_is_rejected(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Reject attempt to finalize two ideas with the exact same name in the same run."""
    import io
    from ai_scientist.ideation.errors import IdeationInputError

    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    same_idea = {
        "Name": "duplicate_name_proposal",
        "Title": "Original Proposal Title",
        "Short Hypothesis": "Short hypothesis text here.",
        "Related Work": "Related work discussion.",
        "Abstract": "Abstract of the proposal.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }

    stub_responses = [
        # Gen 0: Search -> Finalize
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "q1"}', "r1"
            ),
            30.0,
        ),
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(same_idea)}, "grounding": ["{paper_id}"]}}',
                "r2",
            ),
            30.0,
        ),
        # Gen 1: Search -> Finalize with duplicate name
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "q2"}', "r3"
            ),
            30.0,
        ),
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(same_idea)}, "grounding": ["{paper_id}"]}}',
                "r4",
            ),
            30.0,
        ),
    ]

    transport = StubTransport(stub_responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=2,
        num_reflections=2,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["idea_count"] == 1
    assert result["terminal_outcome"] == "success"

    seal_bytes = (
        workspace / "artifacts/ideation-runs" / result["run_id"] / "seal.json"
    ).read_bytes()
    seal = parse_json_bytes(seal_bytes, label="seal.json")
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 1,
        "budget_exhausted": 1,
    }
    assert seal["terminal_summary"]["idea_count"] == 1

    # Verify model-fixable error feedback artifact exists for duplicate attempt (op 7)
    fb_path = (
        workspace
        / "artifacts/ideation-runs"
        / result["run_id"]
        / "artifacts/operations/000007/attempts/000001/feedback.txt"
    )
    assert fb_path.is_file()
    assert "DUPLICATE_IDEA_NAME" in fb_path.read_text(encoding="utf-8")


def test_adversarial_finalize_without_prior_retrieval_is_rejected(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Prove that finalizing an idea without prior SearchLiterature in the run fails on the retrieval backstop.

    Since ticket 09 the run-level backstop seals an explicit terminal `failed`
    outcome instead of raising out of the controller.
    """
    import io
    from ai_scientist.ideation.run_store import RUN_SEAL_SCHEMA_VERSION as _SEAL_SCHEMA

    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    idea = {
        "Name": "gate_test_proposal",
        "Title": "Proposal Seeking Direct Finalization",
        "Short Hypothesis": "Hypothesis statement.",
        "Related Work": "Related work statement.",
        "Abstract": "Proposal abstract.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }

    stub_responses = [
        # Round 0: Model tries to finalize idea without any prior SearchLiterature
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea)}, "grounding": ["some_paper"]}}',
                "r1",
            ),
            30.0,
        ),
        # Round 1: Model tries again without searching -> exhausts reflection budget
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea)}, "grounding": ["some_paper"]}}',
                "r2",
            ),
            30.0,
        ),
    ]

    transport = StubTransport(stub_responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "RETRIEVAL_BACKSTOP_FAILED"

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal_bytes = (run_root / "seal.json").read_bytes()
    seal = parse_json_bytes(seal_bytes, label="seal.json")
    assert seal["schema_version"] == _SEAL_SCHEMA
    assert seal["terminal_outcome"] == "failed"
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 0,
        "budget_exhausted": 1,
    }


def test_adversarial_idea_structure_rejects_surrogates_and_null_bytes() -> None:
    """Ensure idea validation rejects null bytes and surrogate characters."""
    from ai_scientist.ideation.controller import validate_idea_structure
    from ai_scientist.ideation.errors import IdeationInputError

    valid = {
        "Name": "hygiene_check",
        "Title": "Title",
        "Short Hypothesis": "Hypothesis",
        "Related Work": "Related work",
        "Abstract": "Abstract",
        "Experiments": ["Exp 1"],
        "Risk Factors and Limitations": ["Lim 1"],
    }

    # Null byte in Title
    with pytest.raises(IdeationInputError, match="PAYLOAD_CORRUPT"):
        validate_idea_structure(dict(valid, Title="Bad\x00Title"))

    # Surrogate in Abstract
    with pytest.raises(IdeationInputError, match="PAYLOAD_CORRUPT"):
        validate_idea_structure(dict(valid, Abstract="Bad\ud800Abstract"))

    # Name with uppercase or space
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(dict(valid, Name="Upper Name"))


def test_adversarial_declared_grounding_rejects_whitespace_and_path_separators() -> (
    None
):
    """Ensure declared grounding rejects path traversal and unstripped paper IDs."""
    from ai_scientist.ideation.controller import validate_declared_grounding
    from ai_scientist.ideation.errors import IdeationInputError

    eligible = {"paper_ok"}

    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING"):
        validate_declared_grounding(["  paper_ok  "], eligible)

    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING"):
        validate_declared_grounding(["../../escape"], eligible)


def test_adversarial_seal_rejects_invalid_schema_or_missing_fields(
    tmp_path: Path,
) -> None:
    """Ensure write_seal fails closed if seal document is invalid or missing fields."""
    from ai_scientist.ideation.errors import IdeationInputError

    store = RunStore(tmp_path)
    run_id = "00000000-0000-4000-8000-000000000000"
    (tmp_path / "artifacts/ideation-runs" / run_id).mkdir(parents=True)

    with pytest.raises(IdeationInputError, match="INVALID_SEAL"):
        store.write_seal(run_id, {"schema_version": "wrong-schema"})

    with pytest.raises(IdeationInputError, match="INVALID_SEAL"):
        store.write_seal(
            run_id,
            {
                "schema_version": RUN_SEAL_SCHEMA_VERSION,
                "run_id": "different-run-id",
            },
        )

    with pytest.raises(IdeationInputError, match="INVALID_SEAL"):
        store.write_seal(
            run_id,
            {
                "schema_version": RUN_SEAL_SCHEMA_VERSION,
                "run_id": run_id,
                # Missing terminal_outcome, request_sha256, etc.
            },
        )
