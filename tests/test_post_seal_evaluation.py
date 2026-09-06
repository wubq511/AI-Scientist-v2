"""Post-seal qualitative Evaluation Artifact tests (ticket 12).

Delivers:
- VM-QUAL-01: every finalized idea of a sealed run can be linked to a
  schema-valid Evaluation Artifact; coverage is machine-accountable
  (linkage exists + schema valid). Robert's verdict content itself is
  never machine-scored.
- Contract 037: deterministic assemble (private Evaluation Brief +
  pre-filled linkage skeleton), fail-closed validate (closed schema,
  hash linkage, seven approved enums, non-empty rationales, authoring
  audit, linear supersedes), immutable write-once versions, read-only
  coverage over the seal inventory.
"""

from __future__ import annotations

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
    sha256_bytes,
)
from ai_scientist.ideation.deepseek import (
    DEEPSEEK_MODEL_ID,
    DeepSeekAdapter,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.evaluation import (
    RunContext,
    _collect_retrieval_excerpts,
    assemble_evaluation_brief,
    list_evaluation_coverage,
    validate_evaluation_artifact,
)
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.perform_ideation_temp_free import run_new_run

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_CORPUS = REPO_ROOT / "tests/fixtures/corpus"
CASE_ID = "case-0123456789abcdef0123456789abcdef"
TARGET_ID = "a" * 40
BUILD_ID = "build-001"

VALID_VERDICTS = {
    "problem_space_match": "aligned",
    "target_contribution_overlap": "partial_overlap",
    "relative_novelty": "on_par",
    "feasibility_soundness": "sound",
    "contamination_signal": "none_found",
    "leakage_review": "clean",
    "grounding_synthesis": "synthesized",
}

EVALUATIONS_ROOT = Path("artifacts/evaluations")


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
    for policy_name in (
        "reference-authority-v1.json",
        "workshop-leakage-v1.json",
        "deepseek-cny-price-table-v1.json",
        "idea-quality-rubric-v1.json",
    ):
        shutil.copyfile(
            REPO_ROOT / "ai_scientist/ideation/policies" / policy_name,
            policy_root / policy_name,
        )
    (workspace / ".gitignore").write_text(
        "artifacts/ideation-runs/\nartifacts/evaluations/\n", encoding="utf-8"
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


def _idea_payload(name: str = "adaptive_temporal_cueing") -> dict[str, Any]:
    return {
        "Name": name,
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


def _run_responses(
    workspace: Path, corpus_rel: str
) -> tuple[str, list[TransportResponse]]:
    corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    expected_paper_id = corpus_data["records"][0]["paper_id"]
    round_0_content = (
        "ACTION: SearchLiterature\n"
        'ARGUMENTS: {"query": "clinical forecasting migraine"}'
    )
    round_1_content = (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(_idea_payload())}, '
        f'"grounding": ["{expected_paper_id}"]}}'
    )
    responses = [
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
    return expected_paper_id, responses


def _create_sealed_run(workspace: Path) -> dict[str, Any]:
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    _, responses = _run_responses(workspace, corpus_rel)

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
    transport = StubTransport(responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)
    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    return result


def _create_failed_run_with_idea(workspace: Path) -> dict[str, Any]:
    """Two generations: generation 0 finalizes an idea, generation 1 hits the
    payload hygiene gate and seals the run terminal `failed`."""
    workshop_rel, workshop_sha = _approved_workshop(workspace)
    corpus_rel, corpus_sha = _approved_corpus(workspace)
    _, responses = _run_responses(workspace, corpus_rel)

    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: commit approved inputs"],
        cwd=workspace,
        check=True,
    )

    hygiene_hit_content = (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(_idea_payload("hygiene_hit_idea"))}, '
        f'"grounding": ["{CASE_ID}"]}}'
    )
    responses = responses + [
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(hygiene_hit_content, "chatcmpl-round-2"),
            duration_ms=60.0,
        )
    ]

    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=2,
        num_reflections=2,
    )
    transport = StubTransport(responses)
    price_table = load_price_table(workspace)
    adapter = DeepSeekAdapter(price_table=price_table, transport=transport)
    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "failed"
    return result


def _idea_dir(workspace: Path, run_id: str, idea_index: int = 0) -> Path:
    return workspace / EVALUATIONS_ROOT / run_id / "ideas" / f"{idea_index:06d}"


def _assemble(workspace: Path, run_id: str, idea_index: int = 0) -> dict[str, Any]:
    return assemble_evaluation_brief(
        workspace, run_id, idea_index, assembled_by="integration-tester"
    )


def _author_draft(
    workspace: Path,
    run_id: str,
    idea_index: int = 0,
    *,
    mutate: Any = None,
) -> dict[str, Any]:
    draft_path = _idea_dir(workspace, run_id, idea_index) / "draft.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    for criterion, verdict in VALID_VERDICTS.items():
        draft["judgments"][criterion]["verdict"] = verdict
        draft["judgments"][criterion]["rationale"] = f"Rationale for {criterion}."
    draft["audit"]["authored_by"] = "Robert"
    draft["audit"]["authored_at"] = "2026-09-04T01:00:00.000000Z"
    if mutate is not None:
        mutate(draft)
    draft_path.write_bytes(canonical_json_bytes(draft))
    return draft


def _validate(workspace: Path, run_id: str, idea_index: int = 0) -> dict[str, Any]:
    return validate_evaluation_artifact(
        workspace, run_id, idea_index, validated_by="Robert"
    )


# ==============================================================================
# Assemble: Evaluation Brief + linkage skeleton
# ==============================================================================


def test_assemble_golden_creates_brief_and_draft(tmp_path: Path) -> None:
    """Contract 037: assemble produces a rebuildable brief and a pre-filled draft."""
    workspace = _setup_workspace(tmp_path)
    result = _create_sealed_run(workspace)
    run_id = result["run_id"]

    assembled = _assemble(workspace, run_id)
    assert assembled["status"] == "assembled"
    assert assembled["run_id"] == run_id
    assert assembled["case_id"] == CASE_ID
    assert assembled["idea_index"] == 0
    assert assembled["terminal_outcome"] == "success"
    assert assembled["supersedes"] is None
    assert assembled["draft_status"] == "created"

    idea_dir = _idea_dir(workspace, run_id)
    brief_path = idea_dir / "brief.md"
    draft_path = idea_dir / "draft.json"
    assert brief_path.is_file()
    assert draft_path.is_file()
    assert assembled["brief_sha256"] == sha256_bytes(brief_path.read_bytes())

    brief = brief_path.read_text(encoding="utf-8")
    # Idea payload, declared grounding, retrieval excerpts, target comparator.
    assert "Adaptive Temporal Cueing for Migraine Forecasting" in brief
    assert "Continuous passive symptom tracking" in brief
    assert "Target abstract summary for alpha" in brief
    assert "Alpha abstract for testing purposes." in brief
    assert "Target Paper Alpha" in brief
    assert "10.1000/alpha" in brief
    # The declared paper's retrieval segment excerpt must appear verbatim.
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    run_root = workspace / "artifacts/ideation-runs" / run_id
    seal = json.loads((run_root / "seal.json").read_text(encoding="utf-8"))
    inventory = {item["relative_path"]: item for item in seal["artifact_inventory"]}
    idea_rel = "artifacts/ideas/000000/idea.json"
    grounding_rel = "artifacts/ideas/000000/grounding.json"
    assert idea_rel in inventory and grounding_rel in inventory
    grounding_ids = json.loads((run_root / grounding_rel).read_text(encoding="utf-8"))
    assert grounding_ids, "fixture run must declare grounding"
    for paper_id in grounding_ids:
        assert paper_id in brief
    # The exact segment texts released to the model must appear verbatim.
    payloads = sorted((run_root / "artifacts/operations").rglob("payload.json"))
    assert payloads
    for payload_path in payloads:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        for paper in payload["papers"]:
            if paper["paper_id"] in grounding_ids:
                for segment in paper["segments"]:
                    assert segment["text"] in brief

    # Draft skeleton: linkage pre-filled, judgments/authored fields null.
    assert draft["schema_version"] == "evaluation-artifact-v1.0.0"
    assert draft["rubric_version"] == "idea-quality-rubric-v1.0.0"
    assert draft["run_id"] == run_id
    assert draft["case_id"] == CASE_ID
    assert draft["seal_sha256"] == sha256_bytes((run_root / "seal.json").read_bytes())
    assert draft["idea"] == {
        "idea_index": 0,
        "relative_path": idea_rel,
        "sha256": inventory[idea_rel]["sha256"],
    }
    assert draft["target_paper"]["title"] == "Target Paper Alpha"
    assert draft["target_paper"]["doi"] == "10.1000/alpha"
    assert draft["target_paper"]["dataset_path"] == "data/raw/target_papers.csv"
    assert draft["supersedes"] is None
    assert set(draft["judgments"]) == set(VALID_VERDICTS)
    for judgment in draft["judgments"].values():
        assert judgment == {"verdict": None, "rationale": None}
    assert draft["audit"]["assembled_by"] == "integration-tester"
    assert draft["audit"]["brief_sha256"] == assembled["brief_sha256"]
    assert draft["audit"]["authored_by"] is None
    assert draft["audit"]["authored_at"] is None
    assert "validated_by" not in draft["audit"]


def test_assemble_is_deterministic_and_preserves_existing_draft(
    tmp_path: Path,
) -> None:
    """Contract 037: brief.md may be regenerated byte-identically; an in-progress
    draft is never clobbered by re-assembly."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    first = _assemble(workspace, run_id)
    idea_dir = _idea_dir(workspace, run_id)
    brief_bytes = (idea_dir / "brief.md").read_bytes()

    # Robert starts filling the draft.
    _author_draft(workspace, run_id)

    second = _assemble(workspace, run_id)
    assert second["draft_status"] == "existing_kept"
    assert (idea_dir / "brief.md").read_bytes() == brief_bytes
    assert second["brief_sha256"] == first["brief_sha256"]
    # The filled draft survived re-assembly.
    draft = json.loads((idea_dir / "draft.json").read_text(encoding="utf-8"))
    assert draft["audit"]["authored_by"] == "Robert"
    assert draft["judgments"]["problem_space_match"]["verdict"] == "aligned"


def test_assemble_requires_sealed_noncorrupt_run(tmp_path: Path) -> None:
    """Contract 023/037: corrupt or unsealed runs cannot enter evaluation."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    # Tamper the event chain -> corrupt.
    event_path = workspace / "artifacts/ideation-runs" / run_id / "events/00000001.json"
    data = json.loads(event_path.read_text(encoding="utf-8"))
    data["event_hash"] = "0" * 64
    event_path.write_bytes(canonical_json_bytes(data))

    with pytest.raises(IdeationInputError) as exc:
        _assemble(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"

    # Admitted but unsealed run.
    workspace2 = _setup_workspace(tmp_path / "second")
    workshop_rel, workshop_sha = _approved_workshop(workspace2)
    corpus_rel, corpus_sha = _approved_corpus(workspace2)
    subprocess.run(["git", "add", "-A"], cwd=workspace2, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: commit approved inputs"],
        cwd=workspace2,
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
    admitted = run_new_run(workspace2, request, execute=False)
    with pytest.raises(IdeationInputError) as exc2:
        _assemble(workspace2, admitted["run_id"])
    assert exc2.value.code == "RUN_NOT_SEALED"


def test_assemble_rejects_unknown_idea_index(tmp_path: Path) -> None:
    """Only finalized ideas from the seal inventory can be evaluated."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    with pytest.raises(IdeationInputError) as exc:
        _assemble(workspace, run_id, idea_index=1)
    assert exc.value.code == "EVALUATION_IDEA_NOT_FOUND"

    with pytest.raises(IdeationInputError) as exc2:
        _assemble(workspace, run_id, idea_index=-1)
    assert exc2.value.code == "INVALID_COORDINATE"


def test_assemble_failed_run_with_committed_idea(tmp_path: Path) -> None:
    """Contract 037: ideas committed in a terminal `failed` run are evaluable."""
    workspace = _setup_workspace(tmp_path)
    result = _create_failed_run_with_idea(workspace)
    run_id = result["run_id"]

    assembled = _assemble(workspace, run_id)
    assert assembled["status"] == "assembled"
    assert assembled["terminal_outcome"] == "failed"
    assert _idea_dir(workspace, run_id) / "brief.md"
    brief = (_idea_dir(workspace, run_id) / "brief.md").read_text(encoding="utf-8")
    assert "Adaptive Temporal Cueing for Migraine Forecasting" in brief


def test_assemble_detects_target_source_drift(tmp_path: Path) -> None:
    """The target comparator must match the Workshop Manifest's pinned source."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    csv_path = workspace / "data/raw/target_papers.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b"\n")

    with pytest.raises(IdeationInputError) as exc:
        _assemble(workspace, run_id)
    assert exc.value.code in {"HASH_MISMATCH", "SOURCE_DRIFT"}


def test_assemble_rejects_tampered_rubric_policy(tmp_path: Path) -> None:
    """The idea quality rubric is a pinned, versioned policy file."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    policy_path = (
        workspace / "ai_scientist/ideation/policies/idea-quality-rubric-v1.json"
    )
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["version"] = "idea-quality-rubric-v9.9.9"
    policy_path.write_bytes(canonical_json_bytes(policy))

    with pytest.raises(IdeationInputError) as exc:
        _assemble(workspace, run_id)
    assert exc.value.code == "POLICY_DRIFT"


# ==============================================================================
# Retrieval excerpt collection: fail closed on malformed linkage shapes
# ==============================================================================


class _StubStore:
    """Minimal RunStore seam for _collect_retrieval_excerpts shape guards."""

    def __init__(
        self, events: list[dict[str, Any]], payloads: dict[str, bytes]
    ) -> None:
        self._events = events
        self._payloads = payloads

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._events

    def read_artifact(
        self, run_id: str, relative_path: str, sha256: str, label: str = ""
    ) -> bytes:
        return self._payloads[relative_path]


_MODEL_PAYLOAD_REF = [
    {"relative_path": "p.json", "role": "model_payload", "sha256": "f" * 64}
]


def _retrieval_event(artifact_refs: Any) -> dict[str, Any]:
    return {
        "artifact_refs": artifact_refs,
        "event_type": "operation.finished",
        "operation": {
            "attempt_seq": 1,
            "operation_kind": "literature_retrieval",
            "operation_seq": 7,
        },
    }


def _collect(
    events: list[dict[str, Any]], payloads: dict[str, bytes] | None = None
) -> dict[str, Any]:
    context = RunContext(
        store=_StubStore(events, payloads or {}),
        seal_document={},
        seal_sha256="0" * 64,
        terminal_outcome="success",
        case_id=CASE_ID,
        workshop={"path": "workshop.md", "sha256": "0" * 64},
    )
    return _collect_retrieval_excerpts(
        context, "run-stub", {"retrieval_operation_seqs": [7]}, ["paper-x"]
    )


@pytest.mark.parametrize(
    ("artifact_refs", "expected_code"),
    [
        (None, "RUN_CORRUPT"),
        ("artifacts/retrieval/payload.json", "RUN_CORRUPT"),
        ([{"role": "model_payload", "sha256": "f" * 64}], "RUN_CORRUPT"),
        (
            [{"relative_path": "p.json", "role": "model_payload", "sha256": 42}],
            "RUN_CORRUPT",
        ),
        ([{"role": "audit"}], "EVALUATION_LINKAGE_INCONSISTENT"),
    ],
)
def test_excerpt_collection_rejects_malformed_refs(
    artifact_refs: Any, expected_code: str
) -> None:
    """Malformed artifact_refs fail closed with a structured error code."""
    with pytest.raises(IdeationInputError) as exc:
        _collect([_retrieval_event(artifact_refs)])
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    "payload",
    [
        {"papers": None},
        {"papers": ["not-an-object"]},
        {"papers": [{"paper_id": "paper-x", "segments": [], "title": 7}]},
        {"papers": [{"paper_id": "paper-x", "segments": None, "title": "T"}]},
        {"papers": [{"paper_id": "paper-x", "segments": ["bad"], "title": "T"}]},
        {
            "papers": [
                {
                    "paper_id": "paper-x",
                    "segments": [{"content_type": "abstract", "text": 9}],
                    "title": "T",
                }
            ]
        },
    ],
)
def test_excerpt_collection_rejects_malformed_payloads(payload: Any) -> None:
    """Malformed payload shapes fail closed; no KeyError/TypeError tracebacks."""
    events = [_retrieval_event(_MODEL_PAYLOAD_REF)]
    payloads = {"p.json": canonical_json_bytes(payload)}
    with pytest.raises(IdeationInputError) as exc:
        _collect(events, payloads)
    assert exc.value.code == "RUN_CORRUPT"


@pytest.mark.parametrize(
    "payload",
    [
        {"papers": [{"paper_id": ["unhashable"], "segments": [], "title": "T"}]},
        {"papers": [{"paper_id": 42, "segments": [], "title": "T"}]},
    ],
)
def test_excerpt_collection_skips_unmatchable_papers(payload: Any) -> None:
    """Non-string paper_ids cannot match declared grounding; the uncovered
    grounding paper then fails closed as a linkage inconsistency."""
    events = [_retrieval_event(_MODEL_PAYLOAD_REF)]
    payloads = {"p.json": canonical_json_bytes(payload)}
    with pytest.raises(IdeationInputError) as exc:
        _collect(events, payloads)
    assert exc.value.code == "EVALUATION_LINKAGE_INCONSISTENT"


def test_excerpt_collection_ignores_malformed_operation_fields() -> None:
    """Events without a usable operation object or seq cannot match the
    sidecar's wanted retrieval operations; the gap fails closed."""
    events = [
        {"event_type": "operation.finished", "operation": "corrupt"},
        {
            "event_type": "operation.finished",
            "operation": {
                "operation_kind": "literature_retrieval",
                "operation_seq": [7],
            },
        },
    ]
    with pytest.raises(IdeationInputError) as exc:
        _collect(events)
    assert exc.value.code == "EVALUATION_LINKAGE_INCONSISTENT"


def test_excerpt_collection_happy_path() -> None:
    """Matched grounding papers yield exactly the released segments."""
    payload = {
        "papers": [
            {
                "paper_id": "paper-x",
                "segments": [{"content_type": "abstract", "text": "segment text"}],
                "title": "Paper X",
            },
            {"paper_id": "paper-y", "segments": [], "title": "Paper Y"},
        ]
    }
    excerpts = _collect(
        [_retrieval_event(_MODEL_PAYLOAD_REF)],
        {"p.json": canonical_json_bytes(payload)},
    )
    assert excerpts == {
        "paper-x": [
            {
                "operation_seq": 7,
                "segments": [{"content_type": "abstract", "text": "segment text"}],
                "title": "Paper X",
            }
        ]
    }


# ==============================================================================
# Validate: draft -> immutable Evaluation Artifact
# ==============================================================================


def test_validate_golden_writes_immutable_artifact(tmp_path: Path) -> None:
    """Contract 037: a fully authored draft validates into v0001.json."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    draft_before = (_idea_dir(workspace, run_id) / "draft.json").read_bytes()
    _author_draft(workspace, run_id)
    draft_authored = (_idea_dir(workspace, run_id) / "draft.json").read_bytes()

    result = _validate(workspace, run_id)
    assert result["status"] == "validated"
    assert result["version"] == "v0001.json"
    assert result["run_id"] == run_id
    assert result["supersedes"] is None

    artifact_path = _idea_dir(workspace, run_id) / "v0001.json"
    assert artifact_path.is_file()
    assert result["artifact_sha256"] == sha256_bytes(artifact_path.read_bytes())
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["schema_version"] == "evaluation-artifact-v1.0.0"
    assert artifact["rubric_version"] == "idea-quality-rubric-v1.0.0"
    for criterion, verdict in VALID_VERDICTS.items():
        assert artifact["judgments"][criterion]["verdict"] == verdict
        assert artifact["judgments"][criterion]["rationale"]
    audit = artifact["audit"]
    assert audit["assembled_by"] == "integration-tester"
    assert audit["authored_by"] == "Robert"
    assert audit["authored_at"] == "2026-09-04T01:00:00.000000Z"
    assert audit["validated_by"] == "Robert"
    assert audit["validation_result"] == "passed"
    assert isinstance(audit["validated_at"], str) and audit["validated_at"]

    # The draft is a working file and stays exactly as authored.
    assert (_idea_dir(workspace, run_id) / "draft.json").read_bytes() == draft_authored
    assert draft_before != draft_authored


def test_validate_without_draft_fails_closed(tmp_path: Path) -> None:
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    with pytest.raises(IdeationInputError) as exc:
        _validate(workspace, run_id)
    assert exc.value.code == "EVALUATION_DRAFT_NOT_FOUND"


def test_validate_requires_valid_sealed_run(tmp_path: Path) -> None:
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    _author_draft(workspace, run_id)

    # Corrupt the run after authoring.
    (workspace / "artifacts/ideation-runs" / run_id / "request.json").unlink()
    with pytest.raises(IdeationInputError) as exc:
        _validate(workspace, run_id)
    assert exc.value.code == "RUN_CORRUPT"
    assert not (_idea_dir(workspace, run_id) / "v0001.json").exists()


@pytest.mark.parametrize(
    "mutate, expected_code",
    [
        (lambda d: d.update({"overall_score": 5}), "INVALID_SCHEMA"),
        (lambda d: d["judgments"].pop("relative_novelty"), "INVALID_SCHEMA"),
        (
            lambda d: d["judgments"]["relative_novelty"].update(
                {"verdict": "brilliant"}
            ),
            "INVALID_SCHEMA",
        ),
        (
            lambda d: d["judgments"]["relative_novelty"].update({"rationale": ""}),
            "INVALID_SCHEMA",
        ),
        (
            lambda d: d["judgments"]["relative_novelty"].update({"rationale": "   "}),
            "INVALID_SCHEMA",
        ),
        (
            lambda d: d["judgments"]["leakage_review"].update({"verdict": None}),
            "INVALID_SCHEMA",
        ),
        (lambda d: d.update({"seal_sha256": "0" * 64}), "HASH_MISMATCH"),
        (
            lambda d: d["idea"].update({"sha256": "0" * 64}),
            "HASH_MISMATCH",
        ),
        (
            lambda d: d["idea"].update(
                {"relative_path": "artifacts/ideas/000001/idea.json"}
            ),
            "HASH_MISMATCH",
        ),
        (lambda d: d.update({"case_id": "case-" + "f" * 32}), "IDENTITY_MISMATCH"),
        (
            lambda d: d.update({"run_id": "0" * 8 + "-0000-4000-8000-000000000000"}),
            "IDENTITY_MISMATCH",
        ),
        (
            lambda d: d["target_paper"].update({"title": "Another Title"}),
            "IDENTITY_MISMATCH",
        ),
        (
            lambda d: d["target_paper"].update({"doi": "10.1000/elsewhere"}),
            "IDENTITY_MISMATCH",
        ),
        (
            lambda d: d["target_paper"].update({"row_sha256": "0" * 64}),
            "HASH_MISMATCH",
        ),
        (
            lambda d: d.update({"rubric_version": "idea-quality-rubric-v0.0.0"}),
            "RUBRIC_VERSION_NOT_APPROVED",
        ),
        (
            lambda d: d.update({"schema_version": "evaluation-artifact-v9.9.9"}),
            "UNSUPPORTED_SCHEMA",
        ),
        (lambda d: d["audit"].update({"authored_by": None}), "INVALID_SCHEMA"),
        (
            lambda d: d["audit"].update({"authored_at": "not-a-timestamp"}),
            "INVALID_SCHEMA",
        ),
        (lambda d: d["audit"].pop("assembled_by"), "INVALID_SCHEMA"),
        (
            lambda d: d["audit"].update({"validated_by": "self-appointed"}),
            "INVALID_SCHEMA",
        ),
        (
            lambda d: d.update({"supersedes": "v0001.json"}),
            "EVALUATION_SUPERSEDES_INVALID",
        ),
        (
            lambda d: d.update({"supersedes": "../v0001.json"}),
            "EVALUATION_SUPERSEDES_INVALID",
        ),
    ],
)
def test_validate_rejects_invalid_drafts(
    tmp_path: Path, mutate: Any, expected_code: str
) -> None:
    """Contract 037.8: every deterministic validation rule fails closed and a
    failed draft never becomes an artifact."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    _author_draft(workspace, run_id, mutate=mutate)
    draft_before = (_idea_dir(workspace, run_id) / "draft.json").read_bytes()

    with pytest.raises(IdeationInputError) as exc:
        _validate(workspace, run_id)
    assert exc.value.code == expected_code

    idea_dir = _idea_dir(workspace, run_id)
    assert not (idea_dir / "v0001.json").exists()
    # The draft survives validation failure untouched.
    assert (idea_dir / "draft.json").read_bytes() == draft_before


def test_validate_rejects_stale_brief(tmp_path: Path) -> None:
    """The recorded brief_sha256 must match the brief on disk at validate time."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    _author_draft(workspace, run_id)

    brief_path = _idea_dir(workspace, run_id) / "brief.md"
    brief_path.write_text("hand-edited brief\n", encoding="utf-8")

    with pytest.raises(IdeationInputError) as exc:
        _validate(workspace, run_id)
    assert exc.value.code == "HASH_MISMATCH"
    assert not (_idea_dir(workspace, run_id) / "v0001.json").exists()


def test_supersedes_chain_is_linear(tmp_path: Path) -> None:
    """Contract 037.7: only the latest unsuperseded version can be superseded."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    _author_draft(workspace, run_id)

    first = _validate(workspace, run_id)
    assert first["version"] == "v0001.json"

    # Author a correction that supersedes v0001.
    _author_draft(
        workspace,
        run_id,
        mutate=lambda d: d.update({"supersedes": "v0001.json"}),
    )
    second = _validate(workspace, run_id)
    assert second["version"] == "v0002.json"
    assert second["supersedes"] == "v0001.json"
    artifact2 = json.loads(
        (_idea_dir(workspace, run_id) / "v0002.json").read_text(encoding="utf-8")
    )
    assert artifact2["supersedes"] == "v0001.json"

    # v0001 is already superseded; superseding it again must fail.
    _author_draft(
        workspace,
        run_id,
        mutate=lambda d: d.update({"supersedes": "v0001.json"}),
    )
    with pytest.raises(IdeationInputError) as exc:
        _validate(workspace, run_id)
    assert exc.value.code == "EVALUATION_SUPERSEDES_INVALID"

    # Superseding nothing when versions exist must fail.
    _author_draft(workspace, run_id)
    with pytest.raises(IdeationInputError) as exc2:
        _validate(workspace, run_id)
    assert exc2.value.code == "EVALUATION_SUPERSEDES_INVALID"

    # Superseding the not-yet-existing head must fail.
    _author_draft(
        workspace,
        run_id,
        mutate=lambda d: d.update({"supersedes": "v0003.json"}),
    )
    with pytest.raises(IdeationInputError) as exc3:
        _validate(workspace, run_id)
    assert exc3.value.code == "EVALUATION_SUPERSEDES_INVALID"

    # Both finalized versions remain byte-identical (write-once).
    assert (
        sha256_bytes((_idea_dir(workspace, run_id) / "v0001.json").read_bytes())
        == first["artifact_sha256"]
    )
    assert not (_idea_dir(workspace, run_id) / "v0003.json").exists()


# ==============================================================================
# Coverage: read-only accounting over the seal inventory (VM-QUAL-01)
# ==============================================================================


def test_coverage_states_missing_draft_only_covered(tmp_path: Path) -> None:
    """VM-QUAL-01: coverage follows missing -> draft_only -> covered."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    report = list_evaluation_coverage(workspace)
    assert report["status"] == "ok"
    assert report["summary"] == {
        "covered": 0,
        "corrupt_runs": 0,
        "draft_only": 0,
        "missing": 1,
        "sealed_runs": 1,
        "unevaluable_runs": 0,
    }
    run_entry = report["runs"][0]
    assert run_entry["run_id"] == run_id
    assert run_entry["status"] == "evaluable"
    assert run_entry["terminal_outcome"] == "success"
    assert run_entry["ideas"] == [
        {
            "draft_present": False,
            "head_error": None,
            "head_sha256": None,
            "head_version": None,
            "idea_index": 0,
            "state": "missing",
        }
    ]

    _assemble(workspace, run_id)
    report = list_evaluation_coverage(workspace)
    assert report["summary"]["draft_only"] == 1
    idea_entry = report["runs"][0]["ideas"][0]
    assert idea_entry["state"] == "draft_only"
    assert idea_entry["draft_present"] is True

    _author_draft(workspace, run_id)
    validated = _validate(workspace, run_id)
    report = list_evaluation_coverage(workspace)
    assert report["summary"]["covered"] == 1
    idea_entry = report["runs"][0]["ideas"][0]
    assert idea_entry["state"] == "covered"
    assert idea_entry["head_version"] == "v0001.json"
    assert idea_entry["head_sha256"] == validated["artifact_sha256"]
    assert idea_entry["head_error"] is None


def test_coverage_includes_failed_run_ideas(tmp_path: Path) -> None:
    """Contract 037.5: ideas committed in a terminal failed run count too."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_failed_run_with_idea(workspace)["run_id"]

    report = list_evaluation_coverage(workspace)
    run_entry = report["runs"][0]
    assert run_entry["terminal_outcome"] == "failed"
    assert run_entry["ideas"][0]["state"] == "missing"
    assert report["summary"]["missing"] == 1


def test_coverage_skips_unsealed_runs(tmp_path: Path) -> None:
    """Coverage accounts only over the seal inventory."""
    workspace = _setup_workspace(tmp_path)
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
    run_new_run(workspace, request, execute=False)

    report = list_evaluation_coverage(workspace)
    assert report["runs"] == []
    assert report["summary"]["sealed_runs"] == 0


def test_coverage_marks_corrupt_run(tmp_path: Path) -> None:
    """A corrupt run is barred from evaluation and reported as corrupt."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)

    (workspace / "artifacts/ideation-runs" / run_id / "events/00000002.json").unlink()

    report = list_evaluation_coverage(workspace)
    run_entry = report["runs"][0]
    assert run_entry["status"] == "corrupt"
    assert run_entry["ideas"] == []
    assert report["summary"]["corrupt_runs"] == 1


def test_coverage_marks_unevaluable_run(tmp_path: Path) -> None:
    """A sealed run whose case-level comparator inputs vanished is reported as
    unevaluable (its own Evidence Chain is intact), not corrupt."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)

    # Remove the Approved Workshop manifest referenced by the run request.
    run_root = workspace / "artifacts/ideation-runs" / run_id
    request = json.loads((run_root / "request.json").read_text(encoding="utf-8"))
    workshop_path = workspace / request["workshop"]["path"]
    (workshop_path.parent / "workshop-manifest.json").unlink()

    report = list_evaluation_coverage(workspace)
    run_entry = report["runs"][0]
    assert run_entry["status"] == "unevaluable"
    assert run_entry["error_code"] == "WORKSHOP_NOT_APPROVED"
    assert run_entry["ideas"] == []
    assert report["summary"]["corrupt_runs"] == 0
    assert report["summary"]["unevaluable_runs"] == 1
    # The run itself is still a valid sealed Evidence Chain.
    from ai_scientist.ideation.evidence import validate_evidence_chain

    assert validate_evidence_chain(workspace, run_id)["status"] == "valid"


def test_coverage_invalid_head_is_not_covered(tmp_path: Path) -> None:
    """VM-QUAL-01: covered requires a schema-valid head artifact."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    _author_draft(workspace, run_id)
    _validate(workspace, run_id)

    # Tamper the finalized artifact: unknown field breaks the closed schema.
    artifact_path = _idea_dir(workspace, run_id) / "v0001.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["overall_score"] = 5
    artifact_path.write_bytes(canonical_json_bytes(artifact))

    report = list_evaluation_coverage(workspace)
    idea_entry = report["runs"][0]["ideas"][0]
    assert idea_entry["state"] == "draft_only"
    assert idea_entry["head_version"] == "v0001.json"
    assert idea_entry["head_error"] is not None
    assert idea_entry["head_error"]["code"] == "INVALID_SCHEMA"
    assert report["summary"]["covered"] == 0


def test_coverage_is_read_only(tmp_path: Path) -> None:
    """Coverage never rewrites run evidence or evaluation artifacts."""

    def _tree_hashes(root: Path) -> dict[str, str]:
        if not root.is_dir():
            return {}
        return {
            path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    _assemble(workspace, run_id)
    _author_draft(workspace, run_id)
    _validate(workspace, run_id)

    before = _tree_hashes(workspace / "artifacts")
    list_evaluation_coverage(workspace)
    after = _tree_hashes(workspace / "artifacts")
    assert before == after


# ==============================================================================
# CLI seam
# ==============================================================================


def _evaluation_cli(
    workspace: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    cli_script = REPO_ROOT / "ai_scientist/perform_ideation_temp_free.py"
    return subprocess.run(
        [sys.executable, str(cli_script), "evaluation", *arguments],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_evaluation_assemble_validate_coverage(tmp_path: Path) -> None:
    """The evaluation CLI seam exposes assemble, validate, and list-coverage."""
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]

    assemble = _evaluation_cli(
        workspace,
        "assemble",
        "--run-id",
        run_id,
        "--idea-index",
        "0",
        "--assembled-by",
        "integration-tester",
    )
    assert assemble.returncode == 0, assemble.stderr
    assert json.loads(assemble.stdout)["status"] == "assembled"

    # Unfilled draft fails validation with a structured error on stderr.
    rejected = _evaluation_cli(
        workspace,
        "validate",
        "--run-id",
        run_id,
        "--idea-index",
        "0",
        "--validated-by",
        "Robert",
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stderr)["code"] == "INVALID_SCHEMA"

    _author_draft(workspace, run_id)
    validated = _evaluation_cli(
        workspace,
        "validate",
        "--run-id",
        run_id,
        "--idea-index",
        "0",
        "--validated-by",
        "Robert",
    )
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["version"] == "v0001.json"

    coverage = _evaluation_cli(workspace, "list-coverage")
    assert coverage.returncode == 0, coverage.stderr
    report = json.loads(coverage.stdout)
    assert report["summary"]["covered"] == 1


def test_cli_evaluation_rejects_corrupt_run(tmp_path: Path) -> None:
    workspace = _setup_workspace(tmp_path)
    run_id = _create_sealed_run(workspace)["run_id"]
    (workspace / "artifacts/ideation-runs" / run_id / "admission.json").unlink()

    assemble = _evaluation_cli(
        workspace,
        "assemble",
        "--run-id",
        run_id,
        "--idea-index",
        "0",
        "--assembled-by",
        "integration-tester",
    )
    assert assemble.returncode == 1
    assert json.loads(assemble.stderr)["code"] == "RUN_CORRUPT"


# ==============================================================================
# Repository hygiene
# ==============================================================================


def test_gitignore_covers_evaluation_root() -> None:
    """Contract 037.2: artifacts/evaluations/ is gitignored like ideation-runs."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in gitignore.splitlines()}
    assert "artifacts/evaluations/" in lines
