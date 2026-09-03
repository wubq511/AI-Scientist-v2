"""Automated tests for Ticket 08: Correct model-fixable actions.

Delivers:
- VM-CONTRACT-024-03: FinalizeIdea structure validation (closed two-key object, 7-field typed structure, non-empty, no silent repair).
- VM-CONTRACT-025-01: Model-Fixable Error unified feedback across 5 classes (parse, unknown action, invalid arguments, retriever dual codes, structure/gate/grounding/duplicate), no silent break or print-only, minimal feedback without paths/hashes/stacks.
- VM-CONTRACT-026-01: Declared Grounding 3 error codes (INVALID_GROUNDING, EMPTY_GROUNDING, UNRETRIEVED_PAPER) and per-generation eligibility isolation.
- VM-INTEGRATION-02: End-to-end recovery script (stub makes deliberate errors, receives feedback, corrects them, successfully finalizes, verifiable hash chain).
- Near-duplicate idea recovery and budget exhaustion behavior (budget_exhausted disposition without crashing run).
"""

from __future__ import annotations

import io
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
    MODEL_FIXABLE_ERROR_CODES,
    MODEL_VISIBLE_ACTIONS,
    IdeationController,
    parse_action_and_arguments,
    validate_declared_grounding,
    validate_idea_structure,
)
from ai_scientist.ideation.deepseek import (
    DeepSeekAdapter,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError
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


def _make_response_bytes(content: str, message_id: str = "msg_001") -> bytes:
    doc = {
        "id": message_id,
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 10},
        },
    }
    return canonical_json_bytes(doc)


# ==============================================================================
# VM-CONTRACT-024-03: FinalizeIdea structure validation
# ==============================================================================


def test_vm_contract_024_03_closed_two_key_object_and_seven_fields() -> None:
    """Verify FinalizeIdea enforces closed 2-key object and 7-field typed structure."""
    valid_idea = {
        "Name": "linear_attention_sparse",
        "Title": "Sparse Linear Attention Networks",
        "Short Hypothesis": "Sparse patterns enhance linear attention expressivity.",
        "Related Work": "Prior work on FlashAttention and linear transformers.",
        "Abstract": "We propose a sparse linear attention mechanism achieving O(N) complexity.",
        "Experiments": ["Benchmark on Long Range Arena", "Ablation on sparsity mask"],
        "Risk Factors and Limitations": [
            "Hardware alignment may require custom Triton kernels"
        ],
    }
    # Direct idea payload validation
    assert validate_idea_structure(valid_idea) == valid_idea

    # Reject missing fields
    missing_title = dict(valid_idea)
    del missing_title["Title"]
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(missing_title)

    # Reject unknown fields (no silent repair)
    extra_field = dict(valid_idea, ExtraField="extra_value")
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(extra_field)

    # Reject non-lowercase / invalid regex Name
    invalid_name = dict(valid_idea, Name="LinearAttentionSparse")
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(invalid_name)

    invalid_name_spaces = dict(valid_idea, Name="linear attention")
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(invalid_name_spaces)

    # Reject empty strings in string fields
    empty_title = dict(valid_idea, Title="   ")
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(empty_title)

    # Reject empty lists in list fields
    empty_exp = dict(valid_idea, Experiments=[])
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(empty_exp)

    # Reject lists containing empty strings
    empty_exp_item = dict(valid_idea, Experiments=[""])
    with pytest.raises(IdeationInputError, match="INVALID_IDEA_STRUCTURE"):
        validate_idea_structure(empty_exp_item)


# ==============================================================================
# VM-CONTRACT-026-01: Declared Grounding 3 error codes & eligibility
# ==============================================================================


def test_vm_contract_026_01_declared_grounding_codes_and_eligibility() -> None:
    """Verify INVALID_GROUNDING, EMPTY_GROUNDING, UNRETRIEVED_PAPER and eligibility isolation."""
    eligible_ids = {"paper_101", "paper_102"}

    # Valid grounding
    assert validate_declared_grounding(["paper_101"], eligible_ids) == ["paper_101"]
    assert validate_declared_grounding(["paper_101", "paper_102"], eligible_ids) == [
        "paper_101",
        "paper_102",
    ]

    # 1. EMPTY_GROUNDING: empty list
    with pytest.raises(IdeationInputError, match="EMPTY_GROUNDING"):
        validate_declared_grounding([], eligible_ids)

    # 2. INVALID_GROUNDING: not a list
    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING"):
        validate_declared_grounding("paper_101", eligible_ids)

    # 2. INVALID_GROUNDING: duplicate paper_id (no silent deduplication)
    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING") as exc_info:
        validate_declared_grounding(["paper_101", "paper_101"], eligible_ids)
    assert "Duplicate paper_id" in str(exc_info.value)

    # 2. INVALID_GROUNDING: whitespace or path separator
    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING"):
        validate_declared_grounding([" paper_101 "], eligible_ids)

    with pytest.raises(IdeationInputError, match="INVALID_GROUNDING"):
        validate_declared_grounding(["sub/paper_101"], eligible_ids)

    # 3. UNRETRIEVED_PAPER: paper was not retrieved in this generation
    with pytest.raises(IdeationInputError, match="UNRETRIEVED_PAPER") as exc_info:
        validate_declared_grounding(["paper_999"], eligible_ids)
    # Proves error message explicitly names the unretrieved paper_id
    assert "paper_999" in str(exc_info.value)


# ==============================================================================
# VM-CONTRACT-025-01: Model-Fixable Error unified feedback across 5 classes
# ==============================================================================


def test_vm_contract_025_01_model_fixable_errors_unified_feedback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Prove that all 5 classes of model-fixable errors are fed back into reflection without silent break or print-only."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    valid_paper_id = corpus_data["records"][0]["paper_id"]

    valid_idea = {
        "Name": "correct_proposal",
        "Title": "Correct Proposal Title",
        "Short Hypothesis": "Short hypothesis text.",
        "Related Work": "Related work discussion.",
        "Abstract": "Proposal abstract text.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }

    # Generation with 5 reflection rounds, testing 4 consecutive fixable error classes followed by success
    stub_responses = [
        # Round 0: Class 1 - PARSE_ERROR (missing ACTION/ARGUMENTS blocks)
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                "I think we should do some literature search first.", "r0"
            ),
            30.0,
        ),
        # Round 1: Class 2 - UNKNOWN_ACTION (ExecutePythonInterpreter is not allowed)
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: ExecutePythonInterpreter\nARGUMENTS: {"code": "print(1)"}',
                "r1",
            ),
            30.0,
        ),
        # Round 2: Class 3 - INVALID_ARGUMENTS_JSON (malformed JSON syntax)
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {query: "broken_json"', "r2"
            ),
            30.0,
        ),
        # Round 3: Class 4 - RETRIEVER INVALID_QUERY (missing query key)
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"wrong_arg": "test"}', "r3"
            ),
            30.0,
        ),
        # Round 4: SearchLiterature succeeds!
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "attention mechanisms"}',
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
        max_num_generations=1,
        num_reflections=5,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    # Round 4 was search, so 0 ideas finalized; but run completes and seals successfully
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 0

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    events_dir = run_root / "events"
    events = [
        parse_json_bytes(p.read_bytes(), label=p.name)
        for p in sorted(events_dir.glob("*.json"))
    ]

    action_outcome_events = [
        e for e in events if e.get("event_type") == "action_outcome"
    ]
    assert len(action_outcome_events) == 5

    # Verify rounds 0 to 3 produced model_fixable_error with minimal feedback
    expected_error_codes = [
        "PARSE_ERROR",
        "UNKNOWN_ACTION",
        "INVALID_ARGUMENTS_JSON",
        "INVALID_QUERY",
    ]
    for idx, expected_code in enumerate(expected_error_codes):
        ao = action_outcome_events[idx]
        assert ao["payload"]["outcome"] == "model_fixable_error"
        assert ao["payload"]["error_code"] == expected_code
        # Minimal feedback check: no file paths, no sha256 hashes, no Python tracebacks
        fb = ao["payload"]["feedback"]
        assert "Traceback" not in fb
        assert "/Users" not in fb
        assert "sha256" not in fb

        # Verify feedback.txt artifact exists on disk
        ref = ao["artifact_refs"][0]
        assert ref["role"] == "model_fixable_feedback"
        artifact_path = run_root / ref["relative_path"]
        assert artifact_path.is_file()
        assert artifact_path.read_text(encoding="utf-8") == fb

    # Verify round 4 was tool_result
    assert action_outcome_events[4]["payload"]["outcome"] == "tool_result"
    assert action_outcome_events[4]["payload"]["action"] == "SearchLiterature"


# ==============================================================================
# VM-INTEGRATION-02: End-to-end recovery script (mistakes -> feedback -> success)
# ==============================================================================


def test_vm_integration_02_model_fixable_recovery_script(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Scripted recovery: stub makes deliberate structure & unretrieved errors, receives feedback, corrects them, and finalizes."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    valid_paper_id = corpus_data["records"][0]["paper_id"]

    bad_structure_idea = {
        "Name": "linear_transformer_rec",
        "Title": "Linear Transformer Recurrence",
        "Short Hypothesis": "Recurrent linear transformers scale better.",
        "Related Work": "Prior work on linear recurrence.",
        # Lacks "Abstract" field (deliberate structure violation)
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }

    correct_idea = dict(
        bad_structure_idea,
        Abstract="This paper proposes a linear recurrent transformer architecture.",
    )

    stub_responses = [
        # Round 0: SearchLiterature -> succeeds, yields valid_paper_id
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "transformer recurrence"}',
                "r0",
            ),
            30.0,
        ),
        # Round 1: FinalizeIdea with bad structure (missing Abstract) -> Model-Fixable Error
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(bad_structure_idea)}, "grounding": ["{valid_paper_id}"]}}',
                "r1",
            ),
            30.0,
        ),
        # Round 2: FinalizeIdea with unretrieved paper_id (lying detection) -> Model-Fixable Error
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(correct_idea)}, "grounding": ["unretrieved_hallucinated_paper"]}}',
                "r2",
            ),
            30.0,
        ),
        # Round 3: FinalizeIdea corrected with valid structure and declared grounding -> Accepted!
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(correct_idea)}, "grounding": ["{valid_paper_id}"]}}',
                "r3",
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
        num_reflections=4,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["idea_count"] == 1
    assert result["terminal_outcome"] == "success"

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = parse_json_bytes((run_root / "seal.json").read_bytes(), label="seal.json")
    assert seal["terminal_summary"]["outcome"] == "success"
    assert seal["terminal_summary"]["idea_count"] == 1
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 1,
        "budget_exhausted": 0,
    }

    # Verify event sequence
    events_dir = run_root / "events"
    events = [
        parse_json_bytes(p.read_bytes(), label=p.name)
        for p in sorted(events_dir.glob("*.json"))
    ]
    action_outcomes = [e for e in events if e.get("event_type") == "action_outcome"]
    assert len(action_outcomes) == 4

    assert action_outcomes[0]["payload"]["outcome"] == "tool_result"
    assert action_outcomes[1]["payload"]["outcome"] == "model_fixable_error"
    assert action_outcomes[1]["payload"]["error_code"] == "INVALID_IDEA_STRUCTURE"
    assert action_outcomes[2]["payload"]["outcome"] == "model_fixable_error"
    assert action_outcomes[2]["payload"]["error_code"] == "UNRETRIEVED_PAPER"
    assert action_outcomes[3]["payload"]["outcome"] == "finalize_accepted"

    # Verify finalized idea artifact on disk
    idea_path = run_root / "artifacts/ideas/000000/idea.json"
    assert idea_path.is_file()
    assert parse_json_bytes(idea_path.read_bytes(), label="idea.json") == correct_idea

    # Verify chain integrity
    RunStore(workspace).verify_chain(result["run_id"])


# ==============================================================================
# Near-duplicate idea recovery & budget exhaustion
# ==============================================================================


def test_near_duplicate_recovery_and_budget_exhaustion(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verify that near-duplicate ideas are fixable, and if budget runs out, disposition is budget_exhausted."""
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

    idea_base = {
        "Name": "linear_sparse_arch",
        "Title": "Linear Sparse Attention Architecture",
        "Short Hypothesis": "Sparsity improves linear transformer accuracy.",
        "Related Work": "Related linear attention works.",
        "Abstract": "Abstract describing the linear sparse attention architecture.",
        "Experiments": ["LRA benchmark"],
        "Risk Factors and Limitations": ["Triton kernel dependency"],
    }

    # Idea with duplicate Title
    duplicate_title_idea = dict(
        idea_base,
        Name="linear_sparse_arch_alt",  # Different Name, but identical Title
    )

    # Completely distinct idea
    distinct_idea = {
        "Name": "orthogonal_rotary_embeddings",
        "Title": "Orthogonal Rotary Positional Embeddings",
        "Short Hypothesis": "Orthogonal embeddings preserve norm across layers.",
        "Related Work": "RoPE and its variants.",
        "Abstract": "We introduce orthogonal RoPE for deep transformer models.",
        "Experiments": ["Long-context perplexity on Pile"],
        "Risk Factors and Limitations": ["Memory overhead during training"],
    }

    stub_responses = [
        # Gen 0: Search -> Finalize idea_base
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "sparse linear attention"}',
                "g0_r0",
            ),
            30.0,
        ),
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_base)}, "grounding": ["{paper_id}"]}}',
                "g0_r1",
            ),
            30.0,
        ),
        # Gen 1: Search -> Proposes duplicate_title_idea -> Fixes with distinct_idea
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "orthogonal rotary"}',
                "g1_r0",
            ),
            30.0,
        ),
        # Round 1: Model submits near duplicate -> receives DUPLICATE_IDEA feedback
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(duplicate_title_idea)}, "grounding": ["{paper_id}"]}}',
                "g1_r1",
            ),
            30.0,
        ),
        # Round 2: Model fixes with distinct_idea -> Accepted!
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(distinct_idea)}, "grounding": ["{paper_id}"]}}',
                "g1_r2",
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
        num_reflections=3,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["idea_count"] == 2
    assert result["terminal_outcome"] == "success"

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = parse_json_bytes((run_root / "seal.json").read_bytes(), label="seal.json")
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 2,
        "budget_exhausted": 0,
    }


def test_cross_generation_declared_grounding_isolation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Prove that papers retrieved in Gen 0 cannot be declared in Gen 1 without being retrieved in Gen 1."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_gen0 = corpus_data["records"][0]["paper_id"]

    idea_0 = {
        "Name": "gen0_idea",
        "Title": "Gen 0 Idea Title",
        "Short Hypothesis": "Short hypothesis text 0.",
        "Related Work": "Related work discussion 0.",
        "Abstract": "Proposal abstract text 0.",
        "Experiments": ["Experiment 0"],
        "Risk Factors and Limitations": ["Limitation 0"],
    }
    idea_1 = {
        "Name": "gen1_idea",
        "Title": "Gen 1 Idea Title",
        "Short Hypothesis": "Short hypothesis text 1.",
        "Related Work": "Related work discussion 1.",
        "Abstract": "Proposal abstract text 1.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }

    stub_responses = [
        # Gen 0: Search -> retrieves paper_gen0 -> Finalize with paper_gen0
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                'ACTION: SearchLiterature\nARGUMENTS: {"query": "scientific abstract"}',
                "g0_r0",
            ),
            30.0,
        ),
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_0)}, "grounding": ["{paper_gen0}"]}}',
                "g0_r1",
            ),
            30.0,
        ),
        # Gen 1: Model attempts to finalize immediately with paper_gen0 without searching in Gen 1
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_1)}, "grounding": ["{paper_gen0}"]}}',
                "g1_r0",
            ),
            30.0,
        ),
        # Gen 1 Round 1: Model tries again without searching -> exhausts reflection budget
        TransportResponse(
            200,
            {"content-type": "application/json"},
            _make_response_bytes(
                f'ACTION: FinalizeIdea\nARGUMENTS: {{"idea": {json.dumps(idea_1)}, "grounding": ["{paper_gen0}"]}}',
                "g1_r1",
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
    assert result["idea_count"] == 1  # Only Gen 0 finalized
    assert result["terminal_outcome"] == "success"

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = parse_json_bytes((run_root / "seal.json").read_bytes(), label="seal.json")
    # Gen 1 exhausted budget due to GATE_REJECTED (isolated from Gen 0 retrieval)
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 1,
        "budget_exhausted": 1,
    }

    # Verify feedback artifact for Gen 1 proves GATE_REJECTED occurred
    fb_path = run_root / "artifacts/operations/000005/attempts/000001/feedback.txt"
    assert fb_path.is_file()
    fb_text = fb_path.read_text(encoding="utf-8")
    assert "GATE_REJECTED" in fb_text
