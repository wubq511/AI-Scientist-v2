"""Synthetic sealed-run fixtures for the comparison boundary tests.

Builds one synthetic workspace with two fixture targets (the two targets in
tests/fixtures/corpus), prepares Approved Workshop + Approved Corpus for two
case ids, and runs the real production lifecycle (admission -> controller ->
seal -> validate -> export -> evaluation) for the requested (case, profile)
grid, so `ingest_comparison_result` is exercised against genuine sealed
Evidence Chains rather than hand-built documents.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from ai_scientist.ideation.deepseek import TransportResponse

REPO_ROOT = Path(__file__).resolve().parents[1]

TARGET_A = "a" * 40  # 5 references in the fixture corpus
TARGET_B = "c" * 40  # 1 reference in the fixture corpus


def _load_helper_module():
    path = REPO_ROOT / "tests" / "test_suspend_resume.py"
    spec = importlib.util.spec_from_file_location(
        "_comparison_suspend_resume_helpers", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _response_bytes(content: str, response_id: str) -> bytes:
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
        "system_fingerprint": "fp_comparison_synthetic",
        "usage": {
            "completion_tokens": 50,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "prompt_tokens": 100,
            "total_tokens": 150,
        },
    }
    return canonical_json_bytes(body)


def _stub(
    content: str, response_id: str, duration_ms: float = 30.0
) -> TransportResponse:
    return TransportResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body=_response_bytes(content, response_id),
        duration_ms=duration_ms,
    )


SEARCH_CONTENT = (
    'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}'
)
SEARCH_RESPONSE_ID = "chatcmpl-comparison-search"
FINALIZE_RESPONSE_ID = "chatcmpl-comparison-finalize"


def idea_payload(name: str) -> dict[str, Any]:
    return {
        "Name": name,
        "Title": f"Synthetic {name} proposal",
        "Short Hypothesis": "Synthetic hypothesis for the governed comparison.",
        "Related Work": "Existing fixtures rely on static seeds; this differs.",
        "Abstract": "A synthetic research idea for offline reduction testing.",
        "Experiments": [
            "Run the fixture retrieval once and report the collected evidence."
        ],
        "Risk Factors and Limitations": [
            "Synthetic fixture limitations are recorded in the verdict.",
        ],
    }


def finalize_content(name: str, paper_id: str) -> str:
    return (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(idea_payload(name))}, '
        f'"grounding": ["{paper_id}"]}}'
    )


def ungrounded_finalize_content(name: str) -> str:
    """FinalizeIdea declaring a paper that was never retrieved (lying shape)."""
    return (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(idea_payload(name))}, '
        '"grounding": ["unretrieved_hallucinated_paper"]}}'
    )


class SequencedTransport:
    """Stub transport serving scripted responses (duration-controlled)."""

    def __init__(self, responses: list[TransportResponse]) -> None:
        self._responses = list(responses)
        self.sent_requests: list[dict[str, str]] = []

    def send(self, request: dict[str, str]) -> TransportResponse:
        self.sent_requests.append(request)
        return self._responses.pop(0)


def prepare_workspace(tmp_path: Path, helpers) -> tuple[Path, list[tuple[str, str]]]:
    """Workspace with four prepared, approved cases (two per fixture target)."""
    workspace = tmp_path / "workspace"
    raw_root = workspace / "data/raw"
    policy_root = workspace / "ai_scientist/ideation/policies"
    raw_root.mkdir(parents=True)
    policy_root.mkdir(parents=True)
    fixtures = REPO_ROOT / "tests" / "fixtures" / "corpus"
    raw_root.joinpath("target_papers.csv").write_bytes(
        fixtures.joinpath("target_papers.csv").read_bytes()
    )
    raw_root.joinpath("filtered_references.csv").write_bytes(
        fixtures.joinpath("filtered_references.csv").read_bytes()
    )
    for policy in (
        "reference-authority-v1.json",
        "workshop-leakage-v1.json",
        "deepseek-cny-price-table-v1.json",
        "idea-quality-rubric-v1.json",
    ):
        policy_root.joinpath(policy).write_bytes(
            (REPO_ROOT / "ai_scientist/ideation/policies" / policy).read_bytes()
        )
    (workspace / ".gitignore").write_text(
        "artifacts/ideation-runs/\n"
        "artifacts/evaluations/\n"
        "evidence/ideation-runs/\n",
        encoding="utf-8",
    )

    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Comparison Tester"],
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
        ["git", "commit", "-q", "-m", "chore: setup comparison workspace"],
        cwd=workspace,
        check=True,
    )

    prepared: list[tuple[str, dict[str, str]]] = []
    for case_slot, (target_id, case_suffix) in enumerate(
        (
            (TARGET_A, TARGET_A[:32]),
            (TARGET_B, TARGET_B[:32]),
            (TARGET_A, sha256_bytes(f"{TARGET_A}:second".encode())[:32]),
            (TARGET_B, sha256_bytes(f"{TARGET_B}:second".encode())[:32]),
        )
    ):
        index = case_slot
        case_id = f"case-{case_suffix}"
        build = helpers._prepare_cli(
            workspace,
            "corpus",
            "build",
            "--case-id",
            case_id,
            "--target-paper-id",
            target_id,
            "--build-id",
            f"build-{index:03d}",
        )
        assert build.returncode == 0, build.stderr
        bundle_rel = json.loads(build.stdout)["bundle_path"]
        manifest = json.loads(
            (workspace / bundle_rel / "bundle-manifest.json").read_text(
                encoding="utf-8"
            )
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
            "rationale": "Fixture bundle approved for comparison tests.",
            "reviewed_at": "2026-09-04T12:00:00.000000Z",
            "schema_version": "corpus-approval-decision-v1.0",
            "validation_report_sha256": manifest["inventory"]["validation-report.json"],
            "versions": manifest["versions"],
        }
        decision_path = workspace / f"reviews/corpus-approval-decision-{index:03d}.json"
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        decision_path.write_bytes(
            (
                json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        )
        approve = helpers._prepare_cli(
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

        prep = helpers._prepare_cli(
            workspace,
            "workshop",
            "prepare",
            "--case-id",
            case_id,
            "--target-paper-id",
            target_id,
            "--preparation-id",
            f"prep-{index:03d}",
        )
        assert prep.returncode == 0, prep.stderr
        prep_rel = json.loads(prep.stdout)["preparation_manifest"]
        prep_data = json.loads((workspace / prep_rel).read_text(encoding="utf-8"))

        derivation = {
            "actor": "comparison-author",
            "authoring_source_sha256": prep_data["authoring_source"]["sha256"],
            "completed_at": "2026-09-04T01:02:03.000000Z",
            "mechanism": "manual",
            "mechanism_version": "fixture-manual-v1",
            "schema_version": "workshop-derivation-v1.0",
            "source_fields": ["title", "abstract"],
        }
        derivation_path = workspace / f"reviews/derivation-{index:03d}.json"
        derivation_path.write_bytes(
            (
                json.dumps(derivation, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        )

        candidate = (
            f"# Title: Research questions in {index:02d} open area\n\n"
            "## Keywords\nfixture keywords, open research directions\n\n"
            "## TL;DR\nWhich research directions remain open?\n\n"
            "## Abstract\nFixture problem with several method families still "
            "unexplored; the question remains open for structured inquiry.\n"
        )
        drafts = workspace / "drafts"
        drafts.mkdir(exist_ok=True)
        draft_path = drafts / f"workshop-{index:03d}.md"
        draft_path.write_text(candidate, encoding="utf-8")

        validate = helpers._prepare_cli(
            workspace,
            "workshop",
            "validate",
            "--preparation-manifest",
            prep_rel,
            "--attempt-id",
            f"attempt-{index:03d}",
            "--candidate",
            draft_path.relative_to(workspace).as_posix(),
            "--derivation-record",
            derivation_path.relative_to(workspace).as_posix(),
        )
        assert validate.returncode == 0, validate.stderr
        attempt_rel = json.loads(validate.stdout)["attempt_manifest"]
        attempt = json.loads((workspace / attempt_rel).read_text(encoding="utf-8"))

        decision_ws = {
            "attempt_manifest_sha256": sha256_bytes(
                (workspace / attempt_rel).read_bytes()
            ),
            "candidate_sha256": sha256_bytes(draft_path.read_bytes()),
            "case_id": case_id,
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
            "reviewed_at": "2026-09-04T02:03:04.000000Z",
            "reviewer": "comparison-reviewer",
            "schema_version": "workshop-semantic-decision-v1.1",
        }
        decision_path_ws = workspace / f"reviews/semantic-decision-{index:03d}.json"
        decision_path_ws.write_bytes(
            (
                json.dumps(decision_ws, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        )
        approve_ws = helpers._prepare_cli(
            workspace,
            "workshop",
            "approve",
            "--attempt-manifest",
            attempt_rel,
            "--semantic-decision",
            decision_path_ws.relative_to(workspace).as_posix(),
        )
        assert approve_ws.returncode == 0, approve_ws.stderr
        payload = json.loads(approve_ws.stdout)
        workshop_rel = payload["workshop"]
        workshop_sha = sha256_bytes((workspace / workshop_rel).read_bytes())
        prepared.append(
            (
                case_id,
                {
                    "corpus": corpus_rel,
                    "corpus_sha256": corpus_sha,
                    "workshop": workshop_rel,
                    "workshop_sha256": workshop_sha,
                },
            )
        )

    helpers._commit_all(workspace)
    return workspace, prepared


def run_one_sealed_run(
    workspace: Path,
    helpers,
    monkeypatch,
    *,
    case_id: str,
    inputs: dict[str, str],
    profile_id: str,
    idea_name: str,
    duration_ms: float = 30.0,
) -> str:
    """Admit -> execute -> seal one synthetic run with the pinned profile."""
    from ai_scientist.ideation.controller import IdeationController
    from ai_scientist.ideation.deepseek import DeepSeekAdapter, StubTransport
    from ai_scientist.ideation.pricing import load_price_table

    corpus_data = json.loads((workspace / inputs["corpus"]).read_text(encoding="utf-8"))
    paper_id = corpus_data["records"][0]["paper_id"]
    responses = [
        _stub(
            SEARCH_CONTENT,
            SEARCH_RESPONSE_ID,
            duration_ms=duration_ms,
        ),
        _stub(
            finalize_content(idea_name, paper_id),
            FINALIZE_RESPONSE_ID,
            duration_ms=duration_ms,
        ),
    ]
    helpers._approve_cost(monkeypatch)
    from ai_scientist.ideation.admission import NewRunRequest

    request = NewRunRequest(
        case_id=case_id,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=3,
        prompt_profile_id=profile_id,
    )
    result = helpers.run_new_run(workspace, request, execute=False)
    assert result["status"] == "admitted", result
    run_id = result["run_id"]
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=StubTransport(responses)
    )
    sealed = IdeationController(workspace, run_id, adapter=adapter).run()
    assert sealed["status"] == "sealed", sealed
    assert sealed["terminal_outcome"] == "success", sealed
    return run_id


def run_zero_idea_sealed_run(
    workspace: Path,
    helpers,
    monkeypatch,
    *,
    case_id: str,
    inputs: dict[str, str],
    profile_id: str,
    idea_name: str,
    duration_ms: float = 30.0,
) -> str:
    """Admit -> execute -> seal one synthetic run that finalizes nothing.

    The response script stays stable under the final-round convergence
    contract: the last round's fixable violation receives the corrective
    re-ask (an extra scripted response) and still refuses to finalize, so
    the run seals success with zero finalized ideas on both contract sides.
    """
    from ai_scientist.ideation.controller import IdeationController
    from ai_scientist.ideation.deepseek import DeepSeekAdapter, StubTransport
    from ai_scientist.ideation.pricing import load_price_table

    responses = [
        _stub(SEARCH_CONTENT, "chatcmpl-zero-search-0", duration_ms=duration_ms),
        _stub(SEARCH_CONTENT, "chatcmpl-zero-search-1", duration_ms=duration_ms),
        _stub(
            ungrounded_finalize_content(idea_name),
            "chatcmpl-zero-lie-0",
            duration_ms=duration_ms,
        ),
        _stub(
            ungrounded_finalize_content(idea_name),
            "chatcmpl-zero-lie-1",
            duration_ms=duration_ms,
        ),
    ]
    helpers._approve_cost(monkeypatch)
    from ai_scientist.ideation.admission import NewRunRequest

    request = NewRunRequest(
        case_id=case_id,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=3,
        prompt_profile_id=profile_id,
    )
    result = helpers.run_new_run(workspace, request, execute=False)
    assert result["status"] == "admitted", result
    run_id = result["run_id"]
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=StubTransport(responses)
    )
    sealed = IdeationController(workspace, run_id, adapter=adapter).run()
    assert sealed["status"] == "sealed", sealed
    assert sealed["terminal_outcome"] == "success", sealed
    assert sealed["idea_count"] == 0, sealed
    return run_id


def finish_sealed_run_pipeline(workspace: Path, helpers, run_id: str) -> None:
    """Validate + export + evaluation artifact for one sealed run."""
    import io

    from ai_scientist.ideation.evidence import export_sanitized_evidence
    from ai_scientist.ideation.evaluation import (
        assemble_evaluation_brief,
        validate_evaluation_artifact,
    )
    from ai_scientist.ideation.evidence import validate_evidence_chain

    assert (
        validate_evidence_chain(workspace, run_id, check_sealed=True)["status"]
        == "valid"
    )
    export = export_sanitized_evidence(workspace, run_id)
    assert export["status"] in ("exported", "idempotent_success")

    seal = json.loads(
        (workspace / "artifacts/ideation-runs" / run_id / "seal.json").read_text(
            encoding="utf-8"
        )
    )
    idea_count = seal["terminal_summary"]["idea_count"]
    for idea_index in range(idea_count):
        assemble = assemble_evaluation_brief(
            workspace, run_id, idea_index, assembled_by="comparison-agent"
        )
        assert assemble["status"] == "assembled"
        idea_dir = (
            workspace / "artifacts/evaluations" / run_id / "ideas" / f"{idea_index:06d}"
        )
        draft_path = idea_dir / "draft.json"
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        verdicts = {
            "problem_space_match": ("aligned", "The idea matches the problem space."),
            "target_contribution_overlap": (
                "materially_different",
                "Distinct from the target.",
            ),
            "relative_novelty": ("on_par", "Comparable novelty to the target."),
            "feasibility_soundness": ("sound", "Feasible validation plan."),
            "contamination_signal": ("none_found", "No contamination observed."),
            "leakage_review": ("clean", "No leakage detected."),
            "grounding_synthesis": ("synthesized", "Grounding is synthesized."),
        }
        for criterion_id, (verdict, rationale) in verdicts.items():
            draft["judgments"][criterion_id]["verdict"] = verdict
            draft["judgments"][criterion_id]["rationale"] = rationale
        draft["audit"]["authored_by"] = "comparison-author"
        draft["audit"]["authored_at"] = "2026-09-04T03:04:05.000000Z"
        draft_path.write_bytes(
            (json.dumps(draft, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        validated = validate_evaluation_artifact(
            workspace, run_id, idea_index, validated_by="comparison-agent"
        )
        assert validated["status"] == "validated", validated
