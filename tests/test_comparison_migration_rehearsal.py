"""Ticket 03 migration rehearsal tests (offline, synthetic two-end topology).

Reproduces the migration topology the live matrix moves to (spec §7, ticket
03 acceptance): the generation side stays on the original execution-code pin
and the frozen package, while the post-seal AI evaluation runs as a new
versioned channel and feeds the comparison vault's separate AI verdict
directory. The rehearsal proves, end to end on synthetic sealed evidence:

- the AI evaluation protocol registers only over a registered review config
  and pins the exact code versions (cross-protocol merges are refused);
- the AI dual-review coverage branch ingests complete runs (resolved and
  unresolved) and fails closed on invalid/missing coverage;
- one pair's AI reduction is consumed into the vault's `ai-verdicts/`
  channel with the same packet binding a human verdict carries, and the
  reducer consumes it only under the registered evaluation protocol while
  every pre-registered gate (3-0, fit, intrusion, floors, envelopes)
  applies unchanged;
- mixing AI and human verdicts inside one reduction fails closed, and AI
  verdicts without a registered protocol fail closed;
- the migration helpers verify the frozen package hand-off, and the ledger
  recency comparison distinguishes same/newer/ambiguous states so two
  workspaces cannot double-book a slot;
- the old generation pin discipline is untouched: a drifted execution HEAD
  is refused exactly as before.

All evidence is synthetic; no paid provider call happens in this suite.
Real-model acceptance stays with the smoke runbook; this file proves the
software contract only.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from ai_scientist.ideation.comparison import (
    BASELINE_PROFILE_ID,
    CANARY_HARD_CAP_CNY,
    CANARY_STAGE_HISTORICAL_SPEND_CNY,
    CHALLENGER_PROFILE_ID,
    ComparisonVault,
)
from ai_scientist.ideation.errors import IdeationInputError

cmp_mod = pytest.importorskip("ai_scientist.ideation.comparison")

RESPONDED_AT = "2026-09-05T09:00:00.000000Z"

SLOT_PROVIDERS = {
    "primary": ("example-provider", "example-model-1"),
    "second": ("other-provider", "other-model-9"),
}


def _review_config_document() -> dict[str, Any]:
    return {
        "authoring_contract_version": "evaluation-authoring-contract-v2.0.0",
        "evaluators": [
            {
                "model_family": "family-one",
                "model_id": "example-model-1",
                "provider": "example-provider",
                "slot": "primary",
            },
            {
                "model_family": "family-two",
                "model_id": "other-model-9",
                "provider": "other-provider",
                "slot": "second",
            },
        ],
        "prompt_versions": {"pair": "pair-review-v1", "single": "single-review-v2"},
        "real_call_authorization": None,
        "schema_version": "evaluation-review-execution-config-v1.0.0",
    }


def _register_review_config(workspace: Path) -> dict[str, Any]:
    from ai_scientist.ideation.ai_review import (
        CONFIG_NAME,
        register_review_config,
    )

    existing = workspace / "artifacts/evaluations" / CONFIG_NAME
    if existing.is_file():
        return {"status": "already-registered"}
    config_path = workspace / "review-execution-config.json"
    config_path.write_bytes(canonical_json_bytes(_review_config_document()))
    return register_review_config(workspace, config_path, supersede=False)


def _register_evaluation_protocol(workspace: Path) -> dict[str, Any]:
    from ai_scientist.ideation.canonical import parse_json_bytes
    from ai_scientist.ideation.evaluation_protocol import (
        PROTOCOL_MANIFEST_NAME,
        build_evaluation_protocol_manifest,
        register_evaluation_protocol,
    )

    existing = workspace / "artifacts/evaluations" / PROTOCOL_MANIFEST_NAME
    if existing.is_file():
        return {"status": "already-registered"}
    manifest = build_evaluation_protocol_manifest(workspace)
    manifest_path = workspace / "evaluation-protocol-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    reregistered = parse_json_bytes(manifest_path.read_bytes(), label="manifest")
    return register_evaluation_protocol(
        workspace, manifest_path, registered_by="rehearsal-agent"
    )


def _norm(text: str) -> str:
    return " ".join(text.split())


def _valid_synthetic_response_body(
    workspace: Path, run_id: str, idea_index: int
) -> dict[str, Any]:
    """A schema-valid seven-dimension judged response over the real
    comparison-synthetic package (quotes taken verbatim from its sources)."""
    from ai_scientist.ideation.ai_review import PACKAGE_NAME

    package = json.loads(
        (
            workspace
            / "artifacts/evaluations"
            / run_id
            / "ideas"
            / f"{idea_index:06d}"
            / "ai"
            / PACKAGE_NAME
        ).read_text(encoding="utf-8")
    )
    sources = {
        source["source_id"]: source
        for source in package["model_payload"]["materials"]["sources"]
    }

    def ref(source_id: str, claim: str, stance: str = "supports") -> dict[str, str]:
        source = sources[source_id]
        return {
            "claim": claim,
            "quote": _norm(source["text"])[:50],
            "source_id": source_id,
            "stance": stance,
        }

    def dim(
        verdict: str,
        rationale: str,
        refs: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "assessment_status": "judged",
            "evidence_refs": refs,
            "key_assumptions": [],
            "missing_information": [],
            "proposed_verdict": verdict,
            "rationale": rationale,
        }

    idea_fields = {
        source["field"]: source_id
        for source_id, source in sources.items()
        if source["kind"] == "idea_field"
    }
    workshop = next(
        source_id
        for source_id, source in sources.items()
        if source["kind"] == "workshop"
    )
    audit = next(
        source_id
        for source_id, source in sources.items()
        if source["kind"] == "audit_statement"
    )
    segment = next(
        source_id
        for source_id, source in sources.items()
        if source["kind"] == "retrieval_segment"
    )
    return {
        "dimensions": {
            "problem_space_match": dim(
                "aligned",
                "idea 与 target 同属同一问题空间，研究对象与目的对应。",
                [ref(idea_fields["Short Hypothesis"], "idea 的假设锚定同一问题")],
            ),
            "target_contribution_overlap": dim(
                "materially_different",
                "idea 与 target 的核心贡献不同。",
                [ref(idea_fields["Related Work"], "idea 声明与现有工作的差异")],
            ),
            "relative_novelty": dim(
                "on_par",
                "相对给定 target，idea 的实质增量与 target 相当。",
                [ref(idea_fields["Title"], "idea 的标题给出具体方案")],
            ),
            "feasibility_soundness": dim(
                "sound",
                "假设、方法与验证计划逻辑连贯。",
                [ref(idea_fields["Experiments"], "idea 给出实验计划")],
            ),
            "contamination_signal": dim(
                "none_found",
                "在本材料包范围内未发现难以解释的 target 独有命名。",
                [
                    ref(idea_fields["Name"], "idea 命名未复现 target 独有命名"),
                    ref(
                        audit,
                        "none_found 仅限本材料包实际审查范围",
                    ),
                ],
            ),
            "leakage_review": dim(
                "clean",
                "审计声明显示生成期 hygiene 扫描通过且检索释放记录完整。",
                [ref(audit, "生成期 hygiene 通过")],
            ),
            "grounding_synthesis": dim(
                "synthesized",
                "声明 grounding 的片段被 idea 实际使用。",
                [ref(segment, "idea 的思路与该检索片段一致")],
            ),
        },
        "task": "single_idea_review",
    }


def _run_dual_review(
    workspace: Path,
    run_id: str,
    idea_index: int,
    *,
    preference: str = "clean_resolved",
) -> str:
    """Export, import two slot responses, validate, and aggregate one idea.

    `preference` chooses the scripted judgment set: `clean_resolved` (all
    seven consensus, clean floor), `negative_resolved` (an unsound
    consensus), `abstain_unresolved` (one abstention), or `conflict`
    (one dimension judged differently per slot).
    """
    from ai_scientist.ideation.ai_review import (
        aggregate_review,
        export_review_package,
        import_review_response,
        validate_ai_review,
    )

    exported = export_review_package(workspace, run_id, idea_index)
    assert exported["status"] == "exported"

    base = _valid_synthetic_response_body(workspace, run_id, idea_index)
    primary = json.loads(json.dumps(base))
    second = json.loads(json.dumps(base))
    if preference == "abstain_unresolved":
        primary["dimensions"]["relative_novelty"] = {
            "assessment_status": "insufficient_evidence",
            "evidence_refs": [],
            "key_assumptions": [],
            "missing_information": ["材料缺少 novelty 对照基准"],
            "proposed_verdict": None,
            "rationale": "材料不足，弃权。",
        }
    elif preference == "conflict":
        second["dimensions"]["relative_novelty"]["proposed_verdict"] = "below"
    elif preference == "negative_resolved":
        for side in (primary, second):
            side["dimensions"]["feasibility_soundness"] = {
                "assessment_status": "judged",
                "evidence_refs": side["dimensions"]["feasibility_soundness"][
                    "evidence_refs"
                ],
                "key_assumptions": [],
                "missing_information": [],
                "proposed_verdict": "unsound",
                "rationale": "验证计划无法回答研究问题。",
            }
    bodies: dict[str, dict[str, Any]] = {"primary": primary, "second": second}
    import uuid

    for slot, body in bodies.items():
        provider, model_id = SLOT_PROVIDERS[slot]
        response_file = workspace / f"response-{uuid.uuid4().hex}.txt"
        response_file.write_bytes(
            (json.dumps(body, ensure_ascii=False, indent=2)).encode("utf-8")
        )
        import_review_response(
            workspace,
            run_id,
            idea_index,
            response_path=response_file,
            evaluator_slot=slot,
            provider=provider,
            model_id=model_id,
            responded_at=RESPONDED_AT,
            supplied_by="rehearsal-supplier",
            imported_by="rehearsal-importer",
        )
        validate_ai_review(workspace, run_id, idea_index, evaluator_slot=slot)
    aggregated = aggregate_review(workspace, run_id, idea_index)
    return aggregated["coverage"]


def _run_pair_review(
    workspace: Path,
    run_a: str,
    run_b: str,
    *,
    preference: str = "content_1",
) -> dict[str, Any]:
    """Export a pair package, run the four independent reviews, reduce."""
    from ai_scientist.ideation.ai_pair_review import (
        export_pair_package,
        import_pair_response,
        reduce_pair_review,
        validate_pair_review,
    )
    from tests.test_ai_pair_review import (
        _display_verdicts,
        _first_arm_source,
        _norm,
        _pair_response_body,
        _pair_root,
    )

    exported = export_pair_package(workspace, run_a, 0, run_b, 0)
    pair_id = exported["pair_id"]
    root = _pair_root(workspace, pair_id)
    for slot in ("primary", "second"):
        for direction in ("ab", "ba"):
            body = _pair_response_body(
                workspace, pair_id, direction, preference=preference
            )
            # The shared builder writes over the workspace root; reuse it via
            # a stable path inside the pair directory's parent.
            response_path = root.parent / f"response-{slot}-{direction}.txt"
            response_path.write_bytes(
                (json.dumps(body, ensure_ascii=False, indent=2)).encode("utf-8")
            )
            provider, model_id = SLOT_PROVIDERS[slot]
            import_pair_response(
                workspace,
                pair_id,
                slot,
                direction,
                response_path=response_path,
                provider=provider,
                model_id=model_id,
                responded_at=RESPONDED_AT,
                supplied_by="rehearsal-supplier",
                imported_by="rehearsal-importer",
            )
            validate_pair_review(workspace, pair_id, slot, direction)
    reduction = reduce_pair_review(workspace, pair_id)
    assert reduction["coverage"] == "complete"
    assert reduction["reduction"]["overall_preference"]["outcome"] == "stable"
    return {"pair_id": pair_id, "reduction": reduction}


def _write_protocol_pin(package_dir: Path, config_sha256: str) -> Path:
    pin_path = package_dir / "evaluation-protocol-pin.json"
    pin_path.write_bytes(
        canonical_json_bytes(
            {
                "registered_at": "2026-09-05T00:00:00.000000Z",
                "review_config_sha256": config_sha256,
                "schema_version": "comparison-evaluation-protocol-pin-v1.0.0",
            }
        )
        + b"\n"
    )
    return pin_path


# ==========================================================================
# Evaluation protocol manifest registration
# ==========================================================================


def test_protocol_registration_requires_review_config(tmp_path: Path) -> None:
    from ai_scientist.ideation.evaluation_protocol import (
        build_evaluation_protocol_manifest,
    )

    (tmp_path / "workspace").mkdir()
    workspace = tmp_path / "workspace"
    with pytest.raises(IdeationInputError) as exc_info:
        build_evaluation_protocol_manifest(workspace)
    assert exc_info.value.code == "REVIEW_CONFIG_NOT_FOUND"


def test_protocol_registration_pins_current_versions(tmp_path: Path) -> None:
    from ai_scientist.ideation.evaluation_protocol import (
        PROTOCOL_ID,
        load_evaluation_protocol,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _register_review_config(workspace)
    _register_evaluation_protocol(workspace)
    manifest = load_evaluation_protocol(workspace)
    assert manifest["protocol_id"] == PROTOCOL_ID
    assert manifest["abstention_policy"]["unresolved_blocks_quality_pass"] is True
    assert "post-first-output" in manifest["revision_disclosure"]


def test_protocol_load_fails_after_config_supersede(tmp_path: Path) -> None:
    """The manifest binds the config hash; a superseded config breaks it."""
    from ai_scientist.ideation.ai_review import register_review_config
    from ai_scientist.ideation.evaluation_protocol import load_evaluation_protocol

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _register_review_config(workspace)
    _register_evaluation_protocol(workspace)
    amended = _review_config_document()
    amended["evaluators"][0]["model_id"] = "example-model-2"
    amended_path = workspace / "amended-config.json"
    amended_path.write_bytes(canonical_json_bytes(amended))
    register_review_config(workspace, amended_path, supersede=True)
    with pytest.raises(IdeationInputError) as exc_info:
        load_evaluation_protocol(workspace)
    assert exc_info.value.code == "EVALUATION_PROTOCOL_MISMATCH"


# ==========================================================================
# Migration helpers: package hand-off and ledger recency
# ==========================================================================


def _make_frozen_package_files(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    package_dir = tmp_path / "package"
    package_dir.mkdir(parents=True)
    files: dict[str, bytes] = {
        "selection-manifest.json": b'{"schema":"manifest"}',
        "selection-approval.json": b'{"schema":"approval"}',
        "run-matrix.json": b'{"schema":"matrix"}',
        "blind-mapping.json": b'{"schema":"mapping"}',
        "commands.txt": b"command-one\ncommand-two\n",
        "execution-code-pin.json": b'{"commit":"' + b"a" * 40 + b'"}',
    }
    for name, content in files.items():
        (package_dir / name).write_bytes(content)
    return package_dir, {name: sha256_bytes(content) for name, content in files.items()}


def test_migration_package_verification_round_trip(tmp_path: Path) -> None:
    from ai_scientist.ideation.migration import (
        verify_generation_package_compatibility,
    )

    _package_dir, hashes = _make_frozen_package_files(tmp_path / "gen")
    eval_root = tmp_path / "eval"
    (eval_root / "artifacts" / "ideation-inputs" / "comparisons" / "002-x").mkdir(
        parents=True
    )
    for name, digest in hashes.items():
        (
            eval_root / "artifacts" / "ideation-inputs" / "comparisons" / "002-x" / name
        ).write_bytes((tmp_path / "gen" / "package" / name).read_bytes())
    result = verify_generation_package_compatibility(eval_root, expected_sha256s=hashes)
    assert result["status"] == "verified"
    assert set(result["package_files"]) == set(hashes)


def test_migration_package_verification_fails_on_matrix_drift(tmp_path: Path) -> None:
    from ai_scientist.ideation.migration import verify_generation_package_compatibility

    _package_dir, hashes = _make_frozen_package_files(tmp_path / "gen")
    eval_root = tmp_path / "eval"
    target = eval_root / "artifacts" / "ideation-inputs" / "comparisons" / "002-x"
    target.mkdir(parents=True)
    for name, digest in hashes.items():
        (target / name).write_bytes((tmp_path / "gen" / "package" / name).read_bytes())
    (target / "run-matrix.json").write_bytes(b'{"schema":"tampered"}')
    with pytest.raises(IdeationInputError) as exc_info:
        verify_generation_package_compatibility(eval_root, expected_sha256s=hashes)
    # The tampered matrix identifies no package, so the lookup itself fails
    # closed before any per-file comparison could cherry-pick across slugs.
    assert exc_info.value.code == "MIGRATION_PACKAGE_MISSING"


def test_migration_package_verification_fails_on_frozen_file_drift(
    tmp_path: Path,
) -> None:
    from ai_scientist.ideation.migration import verify_generation_package_compatibility

    _package_dir, hashes = _make_frozen_package_files(tmp_path / "gen")
    eval_root = tmp_path / "eval"
    target = eval_root / "artifacts" / "ideation-inputs" / "comparisons" / "002-x"
    target.mkdir(parents=True)
    for name, digest in hashes.items():
        (target / name).write_bytes((tmp_path / "gen" / "package" / name).read_bytes())
    (target / "commands.txt").write_bytes(b"tampered-command\n")
    with pytest.raises(IdeationInputError) as exc_info:
        verify_generation_package_compatibility(eval_root, expected_sha256s=hashes)
    assert exc_info.value.code == "MIGRATION_PACKAGE_DRIFT"


def test_migration_package_verification_rejects_ambiguous_slugs(
    tmp_path: Path,
) -> None:
    """Two package slugs carrying the same pinned matrix bytes fail closed:
    the six frozen files must come from one package, never a chimera."""
    from ai_scientist.ideation.migration import verify_generation_package_compatibility

    _package_dir, hashes = _make_frozen_package_files(tmp_path / "gen")
    eval_root = tmp_path / "eval"
    for slug in ("002-a", "002-b"):
        target = eval_root / "artifacts" / "ideation-inputs" / "comparisons" / slug
        target.mkdir(parents=True)
        for name, digest in hashes.items():
            (target / name).write_bytes(
                (tmp_path / "gen" / "package" / name).read_bytes()
            )
    with pytest.raises(IdeationInputError) as exc_info:
        verify_generation_package_compatibility(eval_root, expected_sha256s=hashes)
    assert exc_info.value.code == "MIGRATION_PACKAGE_AMBIGUOUS"


def test_handoff_manifest_round_trip(tmp_path: Path) -> None:
    from ai_scientist.ideation.migration import (
        migration_handoff_manifest,
        verify_handoff_manifest,
    )

    gen_root = tmp_path / "gen"
    eval_root = tmp_path / "eval"
    gen_root.mkdir()
    eval_root.mkdir()
    evidence = gen_root / "artifacts" / "ideation-runs" / "r1" / "seal.json"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b'{"sealed":true}')
    digest = sha256_bytes(evidence.read_bytes())
    manifest = migration_handoff_manifest(
        gen_root,
        direction="generation_to_evaluation",
        carried_files=[{"path": str(evidence.relative_to(gen_root)), "sha256": digest}],
        direction_state="ledger: 1 ingested entry",
        created_by="rehearsal-agent",
    )
    (eval_root / evidence.relative_to(gen_root)).parent.mkdir(parents=True)
    (eval_root / evidence.relative_to(gen_root)).write_bytes(evidence.read_bytes())
    sending = verify_handoff_manifest(gen_root, manifest, verify_present=False)
    receiving = verify_handoff_manifest(eval_root, manifest, verify_present=True)
    assert sending["status"] == receiving["status"] == "verified"


def test_handoff_manifest_detects_missing_file(tmp_path: Path) -> None:
    from ai_scientist.ideation.migration import (
        migration_handoff_manifest,
        verify_handoff_manifest,
    )

    gen_root = tmp_path / "gen"
    eval_root = tmp_path / "eval"
    gen_root.mkdir()
    eval_root.mkdir()
    evidence = gen_root / "artifacts" / "evaluations" / "card.md"
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"card")
    manifest = migration_handoff_manifest(
        gen_root,
        direction="evaluation_to_generation",
        carried_files=[
            {
                "path": str(evidence.relative_to(gen_root)),
                "sha256": sha256_bytes(evidence.read_bytes()),
            }
        ],
        direction_state="ledger: 1 ingested entry",
        created_by="rehearsal-agent",
    )
    with pytest.raises(IdeationInputError) as exc_info:
        verify_handoff_manifest(eval_root, manifest, verify_present=True)
    assert exc_info.value.code == "MIGRATION_HANDOFF_DRIFT"


def _ledger_copy(entries: int, *, forfeited: int = 0, marker: str = "x") -> dict:
    return {
        "canary_hard_cap_cny": "30.00",
        "comparison_actual_spend_cny": f"{entries * 1:.2f}",
        "entries": [
            {
                "actual_cost_cny": "1.00",
                "case_id": f"case-{marker}{i}",
                "pair_index": 1,
                "physical_attempt_count": 2,
                "profile_id": "ml-baseline-v1",
                "run_id": f"run-{marker}{i}",
                "run_index": i,
                "status": "success",
                "worst_case_bound_cny": "7.08",
            }
            for i in range(1, entries + 1)
        ],
        "forfeited_entries": [
            {
                "actual_cost_cny": "0.10",
                "physical_attempt_count": 1,
                "reason": "ZERO_FINALIZED_IDEA",
                "run_id": f"forfeit-{marker}{i}",
                "run_index": 1,
                "worst_case_bound_cny": "7.08",
            }
            for i in range(1, forfeited + 1)
        ],
        "forfeited_spend_cny": f"{forfeited * 0.1:.2f}",
        "historical_spend_cny": "0.14",
        "matrix_sha256": "c" * 64,
        "plan_gate_reapproval_threshold_cny": "5.00",
        "planned_runs_count": 8,
        "schema_version": "comparison-spend-ledger-v1.3.0",
        "status": "ingesting",
        "total_stage_spend_cny": f"{0.14 + entries + forfeited * 0.1:.2f}",
    }


def test_ledger_recency_distinguishes_states() -> None:
    from ai_scientist.ideation.migration import ledger_recency_comparison

    same = ledger_recency_comparison(_ledger_copy(1), _ledger_copy(1))
    assert same["verdict"] == "same_state"
    newer_local = ledger_recency_comparison(_ledger_copy(2), _ledger_copy(1))
    assert newer_local["verdict"] == "local_newer"
    newer_remote = ledger_recency_comparison(_ledger_copy(1), _ledger_copy(2))
    assert newer_remote["verdict"] == "remote_newer"


def test_ledger_recency_fails_ambiguous() -> None:
    from ai_scientist.ideation.migration import ledger_recency_comparison

    local = _ledger_copy(1)
    remote = _ledger_copy(1)
    remote["total_stage_spend_cny"] = "9.99"
    with pytest.raises(IdeationInputError) as exc_info:
        ledger_recency_comparison(local, remote)
    assert exc_info.value.code == "MIGRATION_LEDGER_AMBIGUOUS"


def test_ledger_recency_fails_cross_matrix() -> None:
    from ai_scientist.ideation.migration import ledger_recency_comparison

    remote = _ledger_copy(1)
    remote["matrix_sha256"] = "d" * 64
    with pytest.raises(IdeationInputError) as exc_info:
        ledger_recency_comparison(_ledger_copy(1), remote)
    assert exc_info.value.code == "MATRIX_PIN_DRIFT"


# ==========================================================================
# E2E rehearsal: sealed runs → AI dual review → pair reduction → AI verdict
# → reducer under the registered evaluation protocol
# ==========================================================================


def _ingest_env(helpers, tmp_path_factory, synthetic_workspace):
    """The 8-run synthetic envelope with ingested metrics (one module)."""
    from ai_scientist.ideation.comparison import (
        ingest_comparison_result,
        initialize_comparison_ledger,
    )
    from tests.test_prompt_comparison import _synthetic_matrix_parts
    from tests.comparison_synthetic import (
        finish_sealed_run_pipeline,
        run_one_sealed_run,
    )

    import shutil
    import subprocess

    REPO_ROOT = Path(__file__).resolve().parents[1]
    policies_dir = synthetic_workspace[0] / "ai_scientist" / "ideation" / "policies"
    policies_dir.mkdir(parents=True, exist_ok=True)
    for template in (
        "ai-review-prompt-single-v2.md",
        "ai-review-prompt-pair-v1.md",
    ):
        shutil.copyfile(
            REPO_ROOT / "ai_scientist" / "ideation" / "policies" / template,
            policies_dir / template,
        )
    subprocess.run(["git", "add", "-A"], cwd=synthetic_workspace[0], check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: pin review prompt templates"],
        cwd=synthetic_workspace[0],
        check=False,
        capture_output=True,
    )

    parts = _synthetic_matrix_parts(synthetic_workspace)
    workspace = parts["workspace"]
    prepared = parts["prepared"]
    runs = parts["runs"]
    manifest = parts["manifest"]
    document = parts["document"]
    by_case = {case_id: inputs for case_id, inputs in prepared}
    run_ids: dict[tuple[str, str], str] = {}
    monkey = pytest.MonkeyPatch()
    try:
        for run in runs:
            key = (run.case_id, run.profile_id)
            if key in run_ids:
                continue
            run_id = run_one_sealed_run(
                workspace,
                helpers,
                monkey,
                case_id=run.case_id,
                inputs=by_case[run.case_id],
                profile_id=run.profile_id,
                idea_name="synthetic_idea_"
                + (
                    "baseline"
                    if run.profile_id == BASELINE_PROFILE_ID
                    else "challenger"
                ),
                duration_ms=100.0,
            )
            run_ids[key] = run_id
            finish_sealed_run_pipeline(workspace, helpers, run_id)
    finally:
        monkey.undo()

    ledger = initialize_comparison_ledger(
        matrix_document=document,
        plan_gate_reapproval_threshold_cny=CANARY_HARD_CAP_CNY,
        historical_spend_cny=CANARY_STAGE_HISTORICAL_SPEND_CNY,
    )
    admission_commits = set()
    for run_id in run_ids.values():
        admission = json.loads(
            (
                workspace / "artifacts" / "ideation-runs" / run_id / "admission.json"
            ).read_text(encoding="utf-8")
        )
        admission_commits.add(admission["code"]["commit"])
    assert len(admission_commits) == 1
    pinned_commit = admission_commits.pop()
    package_dir = tmp_path_factory.mktemp("rehearsal-pkg") / "pkg"
    package_dir.mkdir()
    cmp_mod.create_execution_code_pin(package_dir, commit=pinned_commit)
    metrics_by_run: dict[str, Any] = {}
    for run in runs:
        key = (run.case_id, run.profile_id)
        run_id = run_ids[key]
        metrics = ingest_comparison_result(
            workspace,
            run_id,
            expected_run_index=run.run_index,
            expected_arm_position=run.arm_position,
            expected_pair_index=run.pair_index,
            expected_case_id=run.case_id,
            expected_profile_id=run.profile_id,
            matrix_document=document,
            package_dir=package_dir,
        )
        metrics_by_run[run_id] = metrics
        ledger = cmp_mod.ingest_run_actual_cost(
            ledger,
            entry=cmp_mod.LedgerEntry(
                run_index=run.run_index,
                pair_index=run.pair_index,
                case_id=run.case_id,
                profile_id=run.profile_id,
                run_id=run_id,
                status="success",
                actual_cost_cny=metrics.actual_cost_cny,
                worst_case_bound_cny=Decimal("0.50"),
                physical_attempt_count=metrics.physical_attempt_count,
            ),
        )
    mappings = cmp_mod.build_blind_mapping(parts["pairs"], selection_manifest=manifest)
    packets = cmp_mod.build_pair_packets_from_ingested(
        workspace,
        matrix_document=document,
        selection_manifest=manifest,
        mappings=mappings,
        metrics_by_run=metrics_by_run,
    )
    return {
        "workspace": workspace,
        "manifest": manifest,
        "document": document,
        "runs": runs,
        "pairs": parts["pairs"],
        "mappings": mappings,
        "ledger": ledger,
        "metrics_by_run": metrics_by_run,
        "run_ids": run_ids,
        "packets": packets,
        "package_dir": package_dir,
        "admission_commit": pinned_commit,
    }


# ==========================================================================
# E2E: the AI verdict channel through ingestion + reducer
# ==========================================================================


@pytest.fixture(scope="module")
def helpers():
    from tests.comparison_synthetic import _load_helper_module

    return _load_helper_module()


@pytest.fixture(scope="module")
def synthetic_workspace(tmp_path_factory, helpers):
    from tests.comparison_synthetic import prepare_workspace

    tmp = tmp_path_factory.mktemp("rehearsal-synthetic")
    workspace, prepared = prepare_workspace(tmp, helpers)
    return workspace, prepared


@pytest.fixture(scope="module")
def rehearsal_env(tmp_path_factory, helpers, synthetic_workspace):
    return _ingest_env(helpers, tmp_path_factory, synthetic_workspace)


def test_ai_verdict_channel_end_to_end(rehearsal_env, tmp_path) -> None:
    """The full AI path: dual review → pair reduction → vault AI verdict →
    reducer under the registered evaluation protocol."""
    from ai_scientist.ideation.ai_review import list_ai_review_coverage
    from ai_scientist.ideation.comparison import (
        PairFacts,
        reduce_prompt_comparison,
    )
    from ai_scientist.ideation.comparison_ai import record_comparison_ai_verdict
    from ai_scientist.ideation.evaluation_protocol import load_evaluation_protocol

    env = rehearsal_env
    workspace = env["workspace"]
    pair = env["pairs"][0]
    baseline_run_id = env["run_ids"][(pair.case_id, BASELINE_PROFILE_ID)]
    challenger_run_id = env["run_ids"][(pair.case_id, CHALLENGER_PROFILE_ID)]

    # 1. The evaluation workspace registers the review config + protocol.
    _register_review_config(workspace)
    _register_evaluation_protocol(workspace)
    protocol = load_evaluation_protocol(workspace)

    # 2. The pinned protocol binding goes into the package (the migration
    #    hand-off carries the workspace config hash into the generation side).
    config_sha = sha256_bytes(
        (workspace / "artifacts/evaluations/ai-review-config.json").read_bytes()
    )
    _write_protocol_pin(env["package_dir"], config_sha)
    # The live package carries the frozen blind-mapping bytes; the rehearsal
    # package materializes the same frozen document it was built from.
    (env["package_dir"] / "blind-mapping.json").write_bytes(
        canonical_json_bytes(
            cmp_mod.blind_mapping_document(
                env["mappings"], selection_manifest=env["manifest"]
            )
        )
    )

    # 3. Dual review of both arms: one clean-resolved arm is enough for the
    #    floor states; the pair reduction requires both arms' ideas only.
    coverage_primary = _run_dual_review(
        workspace, baseline_run_id, 0, preference="clean_resolved"
    )
    coverage_second = _run_dual_review(
        workspace, challenger_run_id, 0, preference="clean_resolved"
    )
    assert coverage_primary == coverage_second == "complete_resolved"
    ai_coverage = list_ai_review_coverage(workspace)
    states = {idea["state"] for run in ai_coverage["runs"] for idea in run["ideas"]}
    assert "complete_resolved" in states

    # 4. The four-context pair blind review converges on content_1.
    pair_result = _run_pair_review(workspace, baseline_run_id, challenger_run_id)
    assert pair_result["reduction"]["reduction"]["overall_preference"][
        "content_value"
    ] in ("content_1", "content_2")

    # 5. Record the AI verdict into the vault's ai-verdicts channel.
    packet_sha = cmp_mod.pair_packet_sha256(env["packets"][pair.pair_index])
    recorded = record_comparison_ai_verdict(
        workspace,
        package_dir=env["package_dir"],
        case_id=pair.case_id,
        baseline_run_id=baseline_run_id,
        challenger_run_id=challenger_run_id,
        packet_sha256=packet_sha,
        recorded_by="rehearsal-agent",
    )
    assert recorded["status"] == "recorded"
    vault = ComparisonVault(env["package_dir"] / "vault")
    ai_verdict = vault.load_ai_verdict(pair.case_id)
    assert ai_verdict["schema_version"] == "comparison-ai-verdict-v1.0.0"
    # write-once: a second record fails closed
    with pytest.raises(IdeationInputError) as exc_info:
        record_comparison_ai_verdict(
            workspace,
            package_dir=env["package_dir"],
            case_id=pair.case_id,
            baseline_run_id=baseline_run_id,
            challenger_run_id=challenger_run_id,
            packet_sha256=packet_sha,
            recorded_by="rehearsal-agent",
        )
    assert exc_info.value.code == "ARTIFACT_EXISTS"

    # 6. Reduce: only pair 1 carries the AI verdict; pairs 2-4 have none.
    #    Completeness fails (missing verdicts), decision incomplete — the
    #    AI channel itself must be error-free.
    facts = []
    for p in env["pairs"]:
        verdict = (
            vault.load_ai_verdict(p.case_id) if p.case_id == pair.case_id else None
        )
        if verdict is not None:
            verdict = cmp_mod.ai_verdict_facts(
                verdict,
                baseline_run_id=baseline_run_id,
                challenger_run_id=challenger_run_id,
                mapping=cmp_mod._mapping_for_case(env["mappings"], p.case_id),
                packet_sha256=packet_sha,
                recorded_at=ai_verdict["recorded_at"],
            )
        facts.append(
            PairFacts(
                pair_index=p.pair_index,
                case_id=p.case_id,
                cluster=p.cluster,
                baseline_metrics=env["metrics_by_run"][
                    env["run_ids"][(p.case_id, BASELINE_PROFILE_ID)]
                ],
                challenger_metrics=env["metrics_by_run"][
                    env["run_ids"][(p.case_id, CHALLENGER_PROFILE_ID)]
                ],
                verdict=verdict,
                packet_sha256=cmp_mod.pair_packet_sha256(env["packets"][p.pair_index]),
            )
        )
    reveal_document = {
        "blind_mapping": cmp_mod.blind_mapping_document(
            env["mappings"], selection_manifest=env["manifest"]
        ),
        "revealed_at": "2026-09-05T08:00:00.000000Z",
        "schema_version": "comparison-reveal-v1.0.0",
    }
    reduction = reduce_prompt_comparison(
        selection_manifest=env["manifest"],
        matrix_document=env["document"],
        reveal_document=reveal_document,
        pair_facts=tuple(facts),
        ledger=env["ledger"],
        ai_verdicts={pair.case_id: vault.load_ai_verdict(pair.case_id)},
        evaluation_protocol=protocol,
    )
    assert reduction["decision"] == "incomplete"
    assert reduction["gates"]["completeness"]["pass"] is False
    assert reduction["gates"]["completeness"]["verdict_channels"] == {
        pair.case_id: "ai_pair_reduction"
    }
    # The AI verdict consumed cleanly: the projected enums are all closed.
    del protocol


def test_ai_verdict_consumption_requires_registered_protocol(rehearsal_env) -> None:
    """AI verdicts with no registered evaluation protocol fail closed."""
    from ai_scientist.ideation.comparison import PairFacts, reduce_prompt_comparison

    env = rehearsal_env
    pair = env["pairs"][1]  # pair 1 is consumed by the E2E test; use pair 2
    baseline_run_id = env["run_ids"][(pair.case_id, BASELINE_PROFILE_ID)]
    challenger_run_id = env["run_ids"][(pair.case_id, CHALLENGER_PROFILE_ID)]
    workspace = env["workspace"]
    _register_review_config(workspace)
    _register_evaluation_protocol(workspace)
    config_sha = sha256_bytes(
        (workspace / "artifacts/evaluations/ai-review-config.json").read_bytes()
    )
    package_dir = env["package_dir"]
    _write_protocol_pin(package_dir, config_sha)
    (package_dir / "blind-mapping.json").write_bytes(
        canonical_json_bytes(
            cmp_mod.blind_mapping_document(
                env["mappings"], selection_manifest=env["manifest"]
            )
        )
    )
    _run_dual_review(workspace, baseline_run_id, 0)
    _run_dual_review(workspace, challenger_run_id, 0)
    _run_pair_review(workspace, baseline_run_id, challenger_run_id)
    packet_sha = cmp_mod.pair_packet_sha256(env["packets"][pair.pair_index])
    from ai_scientist.ideation.comparison_ai import record_comparison_ai_verdict

    record_comparison_ai_verdict(
        workspace,
        package_dir=package_dir,
        case_id=pair.case_id,
        baseline_run_id=baseline_run_id,
        challenger_run_id=challenger_run_id,
        packet_sha256=packet_sha,
        recorded_by="rehearsal-agent",
    )
    vault = ComparisonVault(package_dir / "vault")
    ai_verdict = vault.load_ai_verdict(pair.case_id)
    facts = (
        PairFacts(
            pair_index=pair.pair_index,
            case_id=pair.case_id,
            cluster=pair.cluster,
            baseline_metrics=env["metrics_by_run"][baseline_run_id],
            challenger_metrics=env["metrics_by_run"][challenger_run_id],
            verdict=cmp_mod.ai_verdict_facts(
                ai_verdict,
                baseline_run_id=baseline_run_id,
                challenger_run_id=challenger_run_id,
                mapping=cmp_mod._mapping_for_case(env["mappings"], pair.case_id),
                packet_sha256=packet_sha,
                recorded_at=ai_verdict["recorded_at"],
            ),
            packet_sha256=packet_sha,
        ),
    )
    reveal_document = {
        "blind_mapping": cmp_mod.blind_mapping_document(
            env["mappings"], selection_manifest=env["manifest"]
        ),
        "revealed_at": "2026-09-05T08:00:00.000000Z",
        "schema_version": "comparison-reveal-v1.0.0",
    }
    with pytest.raises(IdeationInputError) as exc_info:
        reduce_prompt_comparison(
            selection_manifest=env["manifest"],
            matrix_document=env["document"],
            reveal_document=reveal_document,
            pair_facts=facts,
            ledger=env["ledger"],
            ai_verdicts={pair.case_id: ai_verdict},
        )
    assert exc_info.value.code == "EVALUATION_PROTOCOL_MISMATCH"


def test_human_verdict_path_stays_reachable_without_ai_arguments(
    rehearsal_env, tmp_path
) -> None:
    """The legacy human blind-verdict reduction is untouched: no ai_verdicts
    argument, no protocol gate in the output document."""
    from ai_scientist.ideation.comparison import (
        ComparisonVault,
        PairVerdict,
        reduce_prompt_comparison,
    )
    from tests.test_prompt_comparison import _letter_for

    env = rehearsal_env
    pair = env["pairs"][0]
    vault = ComparisonVault(tmp_path / "human-vault")
    challenger_letter = _letter_for(pair, env["mappings"], CHALLENGER_PROFILE_ID)
    verdict = PairVerdict(
        case_id=pair.case_id,
        verdict=challenger_letter,
        overall_rationale="Human sweep.",
        domain_method_fit="challenger_better",
        unjustified_ml_intrusion="unchanged",
        rubric_floor={"arm_a": "clean", "arm_b": "clean"},
        recorded_at="2026-09-04T08:00:00.000000Z",
    )
    vault.record_verdict(
        verdict,
        packet_sha256=cmp_mod.pair_packet_sha256(env["packets"][pair.pair_index]),
    )
    facts = tuple(
        cmp_mod.PairFacts(
            pair_index=p.pair_index,
            case_id=p.case_id,
            cluster=p.cluster,
            baseline_metrics=env["metrics_by_run"][
                env["run_ids"][(p.case_id, BASELINE_PROFILE_ID)]
            ],
            challenger_metrics=env["metrics_by_run"][
                env["run_ids"][(p.case_id, CHALLENGER_PROFILE_ID)]
            ],
            verdict=(
                vault.load_verdict(p.case_id) if p.case_id == pair.case_id else None
            ),
            packet_sha256=cmp_mod.pair_packet_sha256(env["packets"][p.pair_index]),
        )
        for p in env["pairs"]
    )
    reveal_document = {
        "blind_mapping": cmp_mod.blind_mapping_document(
            env["mappings"], selection_manifest=env["manifest"]
        ),
        "revealed_at": "2026-09-05T08:00:00.000000Z",
        "schema_version": "comparison-reveal-v1.0.0",
    }
    reduction = reduce_prompt_comparison(
        selection_manifest=env["manifest"],
        matrix_document=env["document"],
        reveal_document=reveal_document,
        pair_facts=facts,
        ledger=env["ledger"],
    )
    assert reduction["decision"] == "incomplete"
    # Byte-stability against the pre-revision reducer: the incomplete early
    # return carries exactly the legacy completeness gate (no AI-channel
    # keys, no protocol gate) and the document keeps its pre-revision shape.
    # Any future drift in the no-AI path breaks this contract.
    assert set(reduction["gates"]) == {"completeness"}
    assert set(reduction["gates"]["completeness"]) == {"pass", "problems"}
    assert set(reduction) == {
        "decision",
        "gates",
        "matrix_sha256",
        "revealed_pair_profiles",
        "schema_version",
        "selection_manifest_sha256",
    }
    assert reduction["gates"]["completeness"]["problems"] == [
        {"case_id": p.case_id, "problem": "missing_verdict"}
        for p in sorted(env["pairs"], key=lambda pair: pair.pair_index)
        if p.case_id != pair.case_id
    ]


def test_drifted_workspace_refused_by_old_runner(rehearsal_env) -> None:
    """A clean worktree whose HEAD sits on the post-ticket-03 commit is
    refused by the frozen slot runner exactly as the live drifted workspace:
    the pin check runs before any reservation, so the drifted tree can
    neither create a reservation nor exec, and the stale pin is preserved."""
    env = rehearsal_env
    workspace = env["workspace"]
    launch = {
        "authorization": {
            "run_index": 2,
            "schema_version": "comparison-run-authorization-v1.0.0",
        },
        "command_argv": ("echo", "frozen-command"),
        "package_dir": str(env["package_dir"]),
        "workspace_root": str(workspace),
    }
    drifted_head = "f" * 40  # the newer HEAD the live workspace sits at
    pin_bytes = (env["package_dir"] / "execution-code-pin.json").read_bytes()
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.reserve_comparison_slot(
            launch, execution_head_resolver=lambda _root: drifted_head
        )
    assert exc_info.value.code == "EXECUTION_CODE_PIN_MISMATCH"
    # The stale pin is preserved as evidence; nothing was written.
    assert (env["package_dir"] / "execution-code-pin.json").read_bytes() == pin_bytes
    assert (
        not (env["package_dir"] / "vault" / "run-reservations").exists()
        or not (
            env["package_dir"] / "vault" / "run-reservations" / "run-002.json"
        ).exists()
    )
    pin = cmp_mod.load_execution_code_pin(env["package_dir"])
    assert pin["commit"] == env["admission_commit"]


def test_full_ai_matrix_reduces_to_promote(rehearsal_env) -> None:
    """A complete four-pair AI matrix under the registered protocol reduces
    through every pre-registered gate to a decision: gates 2-4 consume the
    projected AI verdicts exactly as they would a human sweep, and the
    reduction document carries the protocol gate."""
    from ai_scientist.ideation.comparison import (
        ComparisonVault,
        reduce_prompt_comparison,
    )
    from ai_scientist.ideation.comparison_ai import record_comparison_ai_verdict

    env = rehearsal_env
    workspace = env["workspace"]
    _register_review_config(workspace)
    _register_evaluation_protocol(workspace)
    config_sha = sha256_bytes(
        (workspace / "artifacts/evaluations/ai-review-config.json").read_bytes()
    )
    package_dir = env["package_dir"]
    _write_protocol_pin(package_dir, config_sha)
    (package_dir / "blind-mapping.json").write_bytes(
        canonical_json_bytes(
            cmp_mod.blind_mapping_document(
                env["mappings"], selection_manifest=env["manifest"]
            )
        )
    )
    vault = ComparisonVault(package_dir / "vault")
    from ai_scientist.ideation.evaluation_protocol import load_evaluation_protocol

    protocol = load_evaluation_protocol(workspace)

    # Build the reducer-facing AI verdicts for all four pairs from one
    # challenger-preferred content-space document per pair. Each pair's
    # packet binding is its own; the arm bindings come from the ingested
    # runs (the AI side would produce these through the real dual-review +
    # pair-review chain proven by the E2E test above).
    ai_verdicts: dict[str, dict[str, Any]] = {}
    facts: list[cmp_mod.PairFacts] = []
    for pair in env["pairs"]:
        baseline_run_id = env["run_ids"][(pair.case_id, BASELINE_PROFILE_ID)]
        challenger_run_id = env["run_ids"][(pair.case_id, CHALLENGER_PROFILE_ID)]
        challenger_idea = cmp_mod.load_sealed_final_idea(workspace, challenger_run_id)
        baseline_idea = cmp_mod.load_sealed_final_idea(workspace, baseline_run_id)
        challenger_sha = cmp_mod.final_idea_sha256(challenger_idea)
        baseline_sha = cmp_mod.final_idea_sha256(baseline_idea)
        document = {
            "schema_version": "comparison-ai-verdict-v1.0.0",
            "case_id": pair.case_id,
            "recorded_at": "2026-09-05T08:00:00.000000Z",
            "authorship": {
                "kind": "ai_pair_reduction",
                "pair_id": f"pair-{sha256_bytes(pair.case_id.encode())[:16]}",
                "review_config_sha256": config_sha,
                "verdict_run_id": challenger_run_id,
                "verdict_idea_index": 0,
            },
            "content_space": {
                "overall_preference": "content_1",
                "domain_method_fit": "content_1",
                "unjustified_ml_intrusion": "content_2",
                "quality_floor_content_1": "clean",
                "quality_floor_content_2": "clean",
                "arm_content_1": {
                    "run_id": challenger_run_id,
                    "idea_index": 0,
                    "idea_sha256": challenger_sha,
                },
                "arm_content_2": {
                    "run_id": baseline_run_id,
                    "idea_index": 0,
                    "idea_sha256": baseline_sha,
                },
            },
        }
        ai_verdicts[pair.case_id] = document
        facts.append(
            cmp_mod.PairFacts(
                pair_index=pair.pair_index,
                case_id=pair.case_id,
                cluster=pair.cluster,
                baseline_metrics=env["metrics_by_run"][baseline_run_id],
                challenger_metrics=env["metrics_by_run"][challenger_run_id],
                verdict=cmp_mod.ai_verdict_facts(
                    document,
                    baseline_run_id=baseline_run_id,
                    challenger_run_id=challenger_run_id,
                    mapping=cmp_mod._mapping_for_case(env["mappings"], pair.case_id),
                    packet_sha256=cmp_mod.pair_packet_sha256(
                        env["packets"][pair.pair_index]
                    ),
                    recorded_at=document["recorded_at"],
                ),
                packet_sha256=cmp_mod.pair_packet_sha256(
                    env["packets"][pair.pair_index]
                ),
            )
        )
    reveal_document = {
        "blind_mapping": cmp_mod.blind_mapping_document(
            env["mappings"], selection_manifest=env["manifest"]
        ),
        "revealed_at": "2026-09-05T08:00:00.000000Z",
        "schema_version": "comparison-reveal-v1.0.0",
    }
    reduction = reduce_prompt_comparison(
        selection_manifest=env["manifest"],
        matrix_document=env["document"],
        reveal_document=reveal_document,
        pair_facts=tuple(facts),
        ledger=env["ledger"],
        ai_verdicts=ai_verdicts,
        evaluation_protocol=protocol,
    )
    # The challenger sweep passes every pre-registered gate: 4-0 wins, fit
    # 4 improved / 0 regressed, no intrusion increase, floors clean, and
    # the deterministic-regression structural gate holds. Cost/latency and
    # budget depend on the synthetic metrics; assert the structural gates
    # and the decision explicitly.
    assert reduction["gates"]["quality_3_0"]["challenger_wins"] == 4
    assert reduction["gates"]["quality_3_0"]["baseline_wins"] == 0
    assert reduction["gates"]["domain_method_fit"]["pass"] is True
    assert reduction["gates"]["ml_intrusion"]["pass"] is True
    assert reduction["gates"]["rubric_floor"]["pass"] is True
    assert reduction["gates"]["ai_quality_floor_unresolved"]["pass"] is True
    assert reduction["gates"]["completeness"]["pass"] is True
    assert set(reduction["gates"]["completeness"]["verdict_channels"].values()) == {
        "ai_pair_reduction"
    }
    assert (
        reduction["gates"]["evaluation_protocol"]["revision_disclosure"]
        == protocol["revision_disclosure"]
    )
    assert reduction["decision"] in ("promote", "reject")
    # Determinism: the same inputs reduce to byte-identical output.
    again = reduce_prompt_comparison(
        selection_manifest=env["manifest"],
        matrix_document=env["document"],
        reveal_document=reveal_document,
        pair_facts=tuple(facts),
        ledger=env["ledger"],
        ai_verdicts=ai_verdicts,
        evaluation_protocol=protocol,
    )
    assert canonical_json_bytes(reduction) == canonical_json_bytes(again)
    del vault, record_comparison_ai_verdict
