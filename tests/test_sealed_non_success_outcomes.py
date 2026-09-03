"""Automated tests for Ticket 09: Seal explicit non-success outcomes.

Delivers:
- VM-CONTRACT-025-02: finalization gate fixed priority (hygiene -> structure ->
  grounding -> duplicate), one highest-priority result per round, and terminal
  conditions never masked or repaired through model-fixable feedback.
- VM-CONTRACT-026-02: payload hygiene scan hits are terminal; near-duplicate
  ideas stay model-fixable.
- VM-LEAKAGE-02: deterministic Idea Leakage payload hygiene scan with a
  versioned pattern list derived from tickets 023/024 identifier formats.
- VM-INTEGRATION-03: terminal scripts (hygiene hit -> failed; run-level
  no-nonempty-retrieval backstop -> failed) seal with a complete inventory.
- VM-FAULT-04: adversarial/defective model behavior reaches the approved end
  state through the real CLI/controller seam.

All tests are deterministic: StubTransport / injected components, zero network,
zero real model cost, no downstream stages.
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

from ai_scientist.ideation.admission import NewRunRequest
from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.controller import (
    ACTION_OUTCOME_SCHEMA_VERSION,
    PAYLOAD_HYGIENE_PATTERNS_VERSION,
    scan_payload_hygiene,
)
from ai_scientist.ideation.deepseek import (
    DeepSeekAdapter,
    ModelRoundError,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.run_store import RUN_SEAL_SCHEMA_VERSION, RunStore
from ai_scientist.perform_ideation_temp_free import _run_new_run, run_new_run

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


def _approve_cost(monkeypatch: Any) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    approval_input = io.StringIO("yes\n")
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


def _make_response_bytes(content: str, response_id: str = "chatcmpl-ticket09") -> bytes:
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
        "system_fingerprint": "fp_ticket09",
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


def _finalize_arguments(idea: dict[str, Any], grounding: list[str]) -> str:
    return json.dumps({"grounding": grounding, "idea": idea}, sort_keys=True)


def _read_events(run_root: Path) -> list[dict[str, Any]]:
    events_dir = run_root / "events"
    return [
        parse_json_bytes(path.read_bytes(), label=path.name)
        for path in sorted(events_dir.glob("*.json"))
    ]


def _load_seal(run_root: Path) -> dict[str, Any]:
    return parse_json_bytes((run_root / "seal.json").read_bytes(), label="seal.json")


def _assert_failed_seal_inventory(workspace: Path, result: dict[str, Any]) -> None:
    """The failed seal must reference a complete, verifiable artifact inventory."""
    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = _load_seal(run_root)
    assert seal["schema_version"] == RUN_SEAL_SCHEMA_VERSION
    assert seal["terminal_outcome"] == "failed"
    assert seal["terminal_summary"]["outcome"] == "failed"
    assert seal["final_event"]["event_seq"] > 0

    inventory = seal["artifact_inventory"]
    assert len(inventory) > 0
    rel_paths = [item["relative_path"] for item in inventory]
    assert rel_paths == sorted(rel_paths)
    for item in inventory:
        artifact_path = run_root / item["relative_path"]
        assert artifact_path.is_file(), f"Missing artifact {item['relative_path']}"
        data = artifact_path.read_bytes()
        assert len(data) == item["byte_length"]
        assert sha256_bytes(data) == item["sha256"]

    events = _read_events(run_root)
    assert events[-1]["event_type"] == "terminal"
    assert events[-1]["payload"]["outcome"] == "failed"
    assert seal["final_event"]["event_hash"] == events[-1]["event_hash"]
    assert RunStore(workspace).verify_chain(result["run_id"]) == len(events)


def _make_idea(name: str, title: str) -> dict[str, Any]:
    return {
        "Name": name,
        "Title": title,
        "Short Hypothesis": f"Hypothesis for {name}.",
        "Related Work": f"Related work for {name}.",
        "Abstract": f"Abstract for {name}.",
        "Experiments": [f"Experiment for {name}"],
        "Risk Factors and Limitations": [f"Limitation for {name}"],
    }


# ==========================================================================
# VM-CONTRACT-026-02 / VM-LEAKAGE-02: payload hygiene scan
# ==========================================================================


def test_payload_hygiene_scan_detects_private_identifier_patterns() -> None:
    """Hygiene scan hits case_id, sha256 hex, UUIDv4, run-root and internal paths."""
    assert isinstance(PAYLOAD_HYGIENE_PATTERNS_VERSION, str)
    assert PAYLOAD_HYGIENE_PATTERNS_VERSION.startswith("payload-hygiene-patterns-")

    # case_id form (ticket 024 schema)
    hits = scan_payload_hygiene(f"Grounded in case {CASE_ID} results.")
    assert hits and hits[0]["pattern_id"] == "case_id_format"

    # SHA-256 hex form (ticket 023 canonical hashes)
    hits = scan_payload_hygiene("verify with " + "0b" * 32 + " later")
    assert hits and hits[0]["pattern_id"] == "sha256_hex"

    # run_id UUIDv4 form (ticket 023 identity model)
    hits = scan_payload_hygiene(
        "run 00000000-0000-4000-8000-000000000000 stored the corpus"
    )
    assert hits and hits[0]["pattern_id"] == "uuidv4_format"

    # run root path form (ticket 023 fixed trust roots)
    hits = scan_payload_hygiene("see artifacts/ideation-runs/<run_id>/admission.json")
    assert hits and hits[0]["pattern_id"] == "run_root_path"

    # internal evidence subtrees (run root paths, dataset input, operation artifacts)
    for snippet, expected in (
        ("copies data/raw/target_papers.csv", "internal_evidence_path"),
        (
            "writes artifacts/operations/000001/attempts/000001/audit.json",
            "internal_evidence_path",
        ),
        ("reads projections/resume-state.json after resume", "internal_evidence_path"),
    ):
        hits = scan_payload_hygiene(snippet)
        assert hits and hits[0]["pattern_id"] == expected, snippet

    # internal lifecycle artifact filenames
    hits = scan_payload_hygiene("the admission.json pins the corpus")
    assert hits and hits[0]["pattern_id"] == "internal_artifact_filename"

    # Ordinary scientific text is clean.
    clean = (
        "The BM25 ranking uses k1=1.6 and b=0.5. Prior forecasting work relies on "
        "static clinical records; our proposal introduces adaptive cueing based on "
        "passive sensing streams evaluated on multi-center cohorts."
    )
    assert scan_payload_hygiene(clean) == []


def test_payload_hygiene_scan_treats_retrieved_paper_ids_as_model_visible() -> None:
    """paper_id values are model-visible (ticket 020) and must never be hygiene hits."""
    paper_id = "1" * 40
    text = (
        "This proposal builds on the retrieved evidence. "
        f"Reference evidence includes paper entry {paper_id}."
    )
    assert scan_payload_hygiene(text) == []

    # Non-canonical uppercase hex is not a canonical internal identifier form.
    assert scan_payload_hygiene("A" * 64) == []


# ==========================================================================
# VM-INTEGRATION-03 / VM-LEAKAGE-02: hygiene hit seals terminal failed
# ==========================================================================


def test_vm_integration_03_hygiene_hit_seals_failed_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A hygiene pattern hit immediately seals the run terminal failed."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    leaking_idea = _make_idea(
        "boundary_probe_idea",
        f"Temporal Cueing Probe {CASE_ID}",  # case_id leaked into the payload
    )

    stub_responses = [
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "r0",
        ),
        _stub(
            f"ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(leaking_idea, [paper_id])}",
            "r1",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

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
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "PAYLOAD_HYGIENE_VIOLATION"
    assert result["idea_count"] == 0

    # Exactly two model rounds: the hygiene hit is never fed back to the model.
    assert len(transport.sent_requests) == 2

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    events = _read_events(run_root)
    action_outcomes = [e for e in events if e["event_type"] == "action_outcome"]
    assert [e["payload"]["outcome"] for e in action_outcomes] == [
        "tool_result",
        "hygiene_hit",
    ]
    hygiene_event = action_outcomes[-1]
    assert hygiene_event["payload"]["error_code"] == "PAYLOAD_HYGIENE_VIOLATION"
    assert hygiene_event["payload"]["action"] == "FinalizeIdea"
    assert hygiene_event["payload"]["schema_version"] == ACTION_OUTCOME_SCHEMA_VERSION
    # No fixable feedback text exists for this round.
    assert "feedback" not in hygiene_event["payload"]

    # The private violation report records the pattern hit for audit.
    report_refs = [
        ref
        for ref in hygiene_event["artifact_refs"]
        if ref["role"] == "hygiene_violation_report"
    ]
    assert len(report_refs) == 1
    report = parse_json_bytes(
        (run_root / report_refs[0]["relative_path"]).read_bytes(),
        label="hygiene-violation.json",
    )
    assert report["hit_count"] >= 1
    assert report["hits"][0]["pattern_id"] == "case_id_format"

    # No idea artifacts were committed for the leaking submission.
    assert not (run_root / "artifacts/ideas").exists()

    seal = _load_seal(run_root)
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 0,
        "budget_exhausted": 0,
    }
    assert seal["terminal_summary"]["idea_count"] == 0
    _assert_failed_seal_inventory(workspace, result)


def test_vm_contract_025_02_hygiene_hit_not_masked_by_fixable_errors(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A hygiene hit outranks structure/grounding feedback and is never repairable."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    # Submission violates hygiene (case_id), structure (missing Abstract) and
    # grounding (unretrieved paper) simultaneously.
    corrupt_idea = {
        "Name": "masked_violation_probe",
        "Title": f"Masked Violation Probe {CASE_ID}",
        "Short Hypothesis": "Hypothesis text.",
        "Related Work": "Related work text.",
        "Experiments": ["Experiment 1"],
        "Risk Factors and Limitations": ["Limitation 1"],
    }

    stub_responses = [
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(corrupt_idea, ["unretrieved_paper_xyz"])}',
            "r1",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

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
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "PAYLOAD_HYGIENE_VIOLATION"
    assert len(transport.sent_requests) == 2

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    events = _read_events(run_root)
    action_outcomes = [e for e in events if e["event_type"] == "action_outcome"]
    # The terminal hygiene result is the ONLY result for that round: no
    # model-fixable feedback may mask or replace it.
    assert [e["payload"]["outcome"] for e in action_outcomes] == [
        "tool_result",
        "hygiene_hit",
    ]
    assert not any(
        e["payload"]["outcome"] == "model_fixable_error" for e in action_outcomes
    )
    _assert_failed_seal_inventory(workspace, result)


def test_vm_contract_025_02_gate_priority_structure_grounding_duplicate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Gate reports exactly one highest-priority result per round in fixed order."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    idea_a = _make_idea("gate_order_first", "Gate Order First Proposal")
    duplicate_name_idea = _make_idea("gate_order_first", "Gate Order Second Proposal")
    distinct_idea = _make_idea("gate_order_final", "Gate Order Final Proposal")

    # Structure-violating variant of duplicate_name_idea (missing Abstract).
    no_abstract = {k: v for k, v in duplicate_name_idea.items() if k != "Abstract"}

    stub_responses = [
        # Gen 0: search then finalize idea_a
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "g0r0",
        ),
        _stub(
            f"ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(idea_a, [paper_id])}",
            "g0r1",
        ),
        # Gen 1 round 0: search
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g1r0",
        ),
        # Gen 1 round 1: bad structure + unretrieved grounding -> structure wins
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(no_abstract, ["unretrieved_paper_xyz"])}',
            "g1r1",
        ),
        # Gen 1 round 2: valid structure + unretrieved grounding + duplicate name
        # -> grounding beats duplicate
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(duplicate_name_idea, ["unretrieved_paper_xyz"])}',
            "g1r2",
        ),
        # Gen 1 round 3: valid grounding + duplicate name -> duplicate reported
        _stub(
            f"ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(duplicate_name_idea, [paper_id])}",
            "g1r3",
        ),
        # Gen 1 round 4: distinct idea accepted
        _stub(
            f"ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(distinct_idea, [paper_id])}",
            "g1r4",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=2,
        num_reflections=5,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 2

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    events = _read_events(run_root)
    action_outcomes = [e for e in events if e["event_type"] == "action_outcome"]
    codes = [
        (
            e["payload"].get("error_code")
            if e["payload"]["outcome"] == "model_fixable_error"
            else e["payload"]["outcome"]
        )
        for e in action_outcomes
    ]
    assert codes == [
        "tool_result",
        "finalize_accepted",
        "tool_result",
        "INVALID_IDEA_STRUCTURE",
        "UNRETRIEVED_PAPER",
        "DUPLICATE_IDEA_NAME",
        "finalize_accepted",
    ]
    # Exactly one result per round; the masked-priority pair never appears in
    # the same round.
    assert len(action_outcomes) == 7


# ==========================================================================
# VM-INTEGRATION-03: run-level retrieval backstop seals failed
# ==========================================================================


def test_vm_integration_03_retrieval_backstop_seals_failed_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A run with zero non-empty Retrieval Results seals terminal failed."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    never_grounded = _make_idea("backstop_probe_idea", "Backstop Probe Proposal")

    stub_responses = [
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(never_grounded, ["some_paper"])}',
            "r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(never_grounded, ["some_paper"])}',
            "r1",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
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

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "RETRIEVAL_BACKSTOP_FAILED"
    assert result["idea_count"] == 0

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = _load_seal(run_root)
    # The legal budget_exhausted generation is preserved inside the failed seal.
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 0,
        "budget_exhausted": 1,
    }
    assert seal["terminal_summary"]["idea_count"] == 0
    _assert_failed_seal_inventory(workspace, result)
    # No idea artifacts exist for the run.
    assert not (run_root / "artifacts/ideas").exists()


def test_cli_seam_backstop_failure_seals_failed(
    tmp_path: Path, monkeypatch: Any, capfd: Any
) -> None:
    """The real CLI entry seals the failed run and reports it as structured JSON."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    never_grounded = _make_idea("cli_backstop_probe", "CLI Backstop Probe Proposal")
    stub_responses = [
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(never_grounded, ["some_paper"])}',
            "c0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(never_grounded, ["some_paper"])}',
            "c1",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

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
        args, workspace_root=workspace, adapter=adapter, execute=True
    )
    assert exit_code == 0

    captured = capfd.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["status"] == "sealed"
    assert payload["terminal_outcome"] == "failed"
    assert payload["reason_code"] == "RETRIEVAL_BACKSTOP_FAILED"

    run_root = workspace / "artifacts/ideation-runs" / payload["run_id"]
    assert (run_root / "seal.json").is_file()
    assert _load_seal(run_root)["terminal_outcome"] == "failed"


# ==========================================================================
# Deterministic adapter / retriever / evidence failures seal failed
# ==========================================================================


def test_terminal_adapter_failure_seals_failed_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A deterministic provider failure (HTTP 400 -> configuration) seals failed."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    bad_request_response = TransportResponse(
        status_code=400,
        headers={"content-type": "application/json"},
        body=canonical_json_bytes({"error": "Bad request shape"}),
        duration_ms=25.0,
    )
    transport = StubTransport([bad_request_response])
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
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

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "configuration"

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    events = _read_events(run_root)
    operation_failed = [e for e in events if e["event_type"] == "operation.failed"]
    assert len(operation_failed) == 1
    assert operation_failed[0]["payload"]["disposition"] == "terminal"
    assert operation_failed[0]["payload"]["error_code"] == "configuration"
    _assert_failed_seal_inventory(workspace, result)


def test_suspend_adapter_failure_does_not_seal(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Environment-class provider failures propagate without a seal (ticket 10)."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    unauthorized_response = TransportResponse(
        status_code=401,
        headers={"content-type": "application/json"},
        body=canonical_json_bytes({"error": "Authentication Fails: bad key"}),
        duration_ms=25.0,
    )
    transport = StubTransport([unauthorized_response])
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
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

    with pytest.raises(ModelRoundError) as exc_info:
        run_new_run(workspace, request, adapter=adapter, execute=True)
    assert exc_info.value.disposition == "suspend"

    run_dirs = list((workspace / "artifacts/ideation-runs").iterdir())
    assert len(run_dirs) == 1
    run_root = run_dirs[0]
    assert not (run_root / "seal.json").exists()
    events = _read_events(run_root)
    assert events[-1]["event_type"] != "terminal"
    suspended = [e for e in events if e["event_type"] == "operation.failed"]
    assert suspended and suspended[-1]["payload"]["disposition"] == "suspend"


def test_retriever_boundary_failure_seals_failed_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A deterministic retriever/evidence boundary failure seals failed, no fallback."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    class TamperedCorpusRetriever:
        """Injected retriever seam simulating a corpus hash boundary failure."""

        policy_version = "scoped-retrieval-policy-v1"

        def search(self, arguments: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            raise IdeationInputError(
                "HASH_MISMATCH", "Corpus bytes do not match bound SHA-256"
            )

    stub_responses = [
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "r0",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=3,
    )

    result = run_new_run(
        workspace,
        request,
        adapter=adapter,
        retriever=TamperedCorpusRetriever(),
        execute=True,
    )
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "HASH_MISMATCH"
    # No retry with different inputs and no model-fixable masking.
    assert len(transport.sent_requests) == 1
    _assert_failed_seal_inventory(workspace, result)


def test_payload_corrupt_idea_seals_failed_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A null byte in a submitted idea is a deterministic terminal failure."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]

    corrupt_idea = _make_idea("corrupt_payload_probe", "Corrupt Payload Proposal")
    corrupt_idea["Abstract"] = "Boundary probe\x00embedded"

    stub_responses = [
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "r0",
        ),
        _stub(
            f"ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(corrupt_idea, [paper_id])}",
            "r1",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=3,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["terminal_outcome"] == "failed"
    assert result["reason_code"] == "PAYLOAD_CORRUPT"
    _assert_failed_seal_inventory(workspace, result)


# ==========================================================================
# VM-FAULT-04: adversarial model behavior reaches approved endpoints
# ==========================================================================


def test_vm_fault_04_fixable_adversarial_scripts_reach_budget_exhausted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Malformed action + grounding lie never fixed: budget_exhausted, run seals success."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    unfixable_model = _make_idea("adversarial_probe", "Adversarial Probe Proposal")

    stub_responses = [
        # Round 0: legitimate retrieval (satisfies the run-level backstop)
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "r0",
        ),
        # Round 1: malformed/unknown action -> model-fixable feedback
        _stub('ACTION: RunShellCommand\nARGUMENTS: {"cmd": "rm -rf /"}', "r1"),
        # Round 2: grounding lie (paper never retrieved) -> UNRETRIEVED_PAPER
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(unfixable_model, ["hallucinated_paper_id"])}',
            "r2",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=3,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 0

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = _load_seal(run_root)
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 0,
        "budget_exhausted": 1,
    }
    assert seal["terminal_outcome"] == "success"

    events = _read_events(run_root)
    action_outcomes = [e for e in events if e["event_type"] == "action_outcome"]
    assert [e["payload"]["outcome"] for e in action_outcomes] == [
        "tool_result",
        "model_fixable_error",
        "model_fixable_error",
    ]
    assert action_outcomes[1]["payload"]["error_code"] == "UNKNOWN_ACTION"
    assert action_outcomes[2]["payload"]["error_code"] == "UNRETRIEVED_PAPER"
    assert RunStore(workspace).verify_chain(result["run_id"]) == len(events)


def test_vm_fault_04_budget_exhausted_then_run_succeeds_after_prior_retrieval(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The backstop only fails a run that never obtained a non-empty result."""
    workspace = _workspace(tmp_path)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    _commit_all(workspace)
    _approve_cost(monkeypatch)

    stub_responses = [
        # Gen 0: legitimate retrieval (run-level backstop satisfied)
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}',
            "g0r0",
        ),
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g0r1",
        ),
        # Generations 1-5: model burns every budget on an unfixable grounding lie.
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g1r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(_make_idea("lie_probe", "Lie Probe Proposal"), ["hallucinated_paper_id"])}',
            "g1r1",
        ),
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g2r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(_make_idea("lie_probe_two", "Lie Probe Two Proposal"), ["hallucinated_paper_id"])}',
            "g2r1",
        ),
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g3r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(_make_idea("lie_probe_three", "Lie Probe Three Proposal"), ["hallucinated_paper_id"])}',
            "g3r1",
        ),
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g4r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(_make_idea("lie_probe_four", "Lie Probe Four Proposal"), ["hallucinated_paper_id"])}',
            "g4r1",
        ),
        _stub(
            'ACTION: SearchLiterature\nARGUMENTS: {"query": "migraine telemetry"}',
            "g5r0",
        ),
        _stub(
            f'ACTION: FinalizeIdea\nARGUMENTS: {_finalize_arguments(_make_idea("lie_probe_five", "Lie Probe Five Proposal"), ["hallucinated_paper_id"])}',
            "g5r1",
        ),
    ]
    transport = StubTransport(stub_responses)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=6,
        num_reflections=2,
    )

    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 0

    run_root = workspace / "artifacts/ideation-runs" / result["run_id"]
    seal = _load_seal(run_root)
    assert seal["terminal_summary"]["disposition_counts"] == {
        "finalized": 0,
        "budget_exhausted": 6,
    }
    assert RunStore(workspace).verify_chain(result["run_id"]) == len(
        _read_events(run_root)
    )
