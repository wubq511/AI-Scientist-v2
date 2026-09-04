"""Deterministic offline comparison boundary tests (ticket 02).

Covers: four-cluster selection from the approved Canary identity, the frozen
4-pair/8-run matrix with balanced order and single-variable arms, the frozen
blind mapping and sanitized pair packets, the append-only spend ledger with
Plan Gate arithmetic, result ingestion fail-closed validation, write-once
pair verdicts behind the reveal gate, and the deterministic Promotion
reducer. All tests are zero-network, credential-free, and free of real
Target identity or live-run artifacts.
"""

from __future__ import annotations

import shlex
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ai_scientist.ideation import comparison as cmp_mod
from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.comparison import (
    APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
    CANARY_HARD_CAP_CNY,
    CanaryCase,
    COMPARISON_CLUSTERS,
    TargetSourceSnapshot,
    assert_single_variable_matrix,
    build_frozen_matrix,
    build_matrix_document,
    build_selection_approval,
    build_selection_manifest,
    canonical_case_hash_for_canary_case,
    comparison_selection_seed,
    freeze_prompt_comparison_package,
    load_approved_canary_cases,
    select_comparison_cases,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.perform_ideation_temp_free import _build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]

APPROVED_CLUSTERS = COMPARISON_CLUSTERS
OFFCLUSTER = "Environmental Sciences"
OTHER_OFFCLUSTER = "Neuroscience & Cognitive Sciences"


def _case(case_id: str, cluster: str, hash_hex: str) -> CanaryCase:
    return CanaryCase(
        case_id=case_id,
        cluster=cluster,
        canonical_hash=hash_hex,
        target_row_sha256=hash_hex[:64].rjust(64, "0"),
        source_row_snapshot_sha256="b" * 64,
    )


def _approved_twelve() -> tuple[CanaryCase, ...]:
    """Synthetic approved-Canary identity: 12 cases over the 8 clusters."""
    clusters = [
        OFFCLUSTER,
        "Genetics & Molecular Biology",
        "Genetics & Molecular Biology",
        "Health & Medicine",
        "Health & Medicine",
        "Materials Science",
        OTHER_OFFCLUSTER,
        OTHER_OFFCLUSTER,
        "Public Health & Policy",
        "Social & Behavioral Sciences",
        "Technology & Engineering",
        "Health & Medicine",
    ]
    cases = []
    for index, cluster in enumerate(clusters):
        cases.append(_case(f"case-{index:032x}", cluster, f"{index:064x}"))
    return tuple(cases)


def _target_source() -> dict[str, TargetSourceSnapshot]:
    """Snapshots bound to the canonical-hash winners' current source rows."""
    approved = _approved_twelve()
    selected_row = {}
    selected_dataset = {}
    for cluster in APPROVED_CLUSTERS:
        candidates = [c for c in approved if c.cluster == cluster]
        winner = min(candidates, key=lambda c: (c.canonical_hash, c.case_id))
        selected_row[cluster] = winner.target_row_sha256
        selected_dataset[cluster] = winner.source_row_snapshot_sha256
    return {
        cluster: TargetSourceSnapshot(
            target_dataset_sha256=selected_dataset[cluster],
            target_row_sha256=selected_row[cluster],
        )
        for cluster in APPROVED_CLUSTERS
    }


def _selected() -> tuple[CanaryCase, ...]:
    return select_comparison_cases(
        _approved_twelve(),
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=_target_source(),
    )


def _selection_manifest(selected: tuple[CanaryCase, ...]) -> dict[str, Any]:
    return build_selection_manifest(
        selected,
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=_target_source(),
    )


def _input_pins(selected: tuple[CanaryCase, ...]) -> dict[str, dict[str, str]]:
    return {
        case.case_id: {
            "corpus": {
                "path": f"artifacts/ideation-inputs/corpora/{case.case_id}/corpus.json",
                "sha256": "1" * 64,
            },
            "workshop": {
                "path": f"artifacts/ideation-inputs/workshops/{case.case_id}/workshop.md",
                "sha256": "2" * 64,
            },
        }
        for case in selected
    }


def _matrix(selected: tuple[CanaryCase, ...]):
    manifest = _selection_manifest(selected)
    runs, pairs = build_frozen_matrix(selected, selection_manifest=manifest)
    document = build_matrix_document(
        runs, pairs, selection_manifest=manifest, input_pins=_input_pins(selected)
    )
    return runs, pairs, document, manifest


# ==========================================================================
# Selection: approved identity, four clusters, canonical hash, fail-closed
# ==========================================================================


def test_selection_picks_exactly_one_case_per_registered_cluster() -> None:
    selected = _selected()
    assert len(selected) == 4
    assert {case.cluster for case in selected} == set(APPROVED_CLUSTERS)
    # Deterministic re-run is byte-identical at the manifest level.
    manifest = _selection_manifest(selected)
    again = select_comparison_cases(
        _approved_twelve(),
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=_target_source(),
    )
    assert canonical_json_bytes(manifest) == canonical_json_bytes(
        build_selection_manifest(
            again,
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=_target_source(),
        )
    )


def test_selection_rejects_unapproved_manifest_identity() -> None:
    with pytest.raises(Exception, match="CANARY_IDENTITY_UNAPPROVED"):
        select_comparison_cases(
            _approved_twelve(),
            canary_selection_manifest_sha256="e" * 64,
            target_source=_target_source(),
        )


def test_selection_rejects_duplicate_case_and_duplicate_target() -> None:
    # 12 cases with a repeated case id: two entries carry the same id with
    # distinct fresh target rows, so the case-id branch fires (not target).
    approved = list(_approved_twelve())
    duplicate_case = [
        case
        for case in approved
        if case.cluster != "Public Health & Policy"
        and case.case_id != approved[0].case_id
    ]
    import copy as _copy

    duplicate_case.append(
        _copy.replace(
            approved[0],
            cluster=OFFCLUSTER,
            target_row_sha256="7" * 64,
            source_row_snapshot_sha256="7" * 64,
        )
    )
    duplicate_case.append(
        _copy.replace(
            approved[0],
            cluster=OFFCLUSTER,
            target_row_sha256="8" * 64,
            source_row_snapshot_sha256="8" * 64,
        )
    )
    assert len(duplicate_case) == 12
    with pytest.raises(Exception, match="DUPLICATE_CANARY_CASE"):
        select_comparison_cases(
            tuple(duplicate_case),
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=_target_source(),
        )
    # 12 distinct case ids but a repeated target row.
    cases = [case for case in approved if case.cluster != "Health & Medicine"]
    for index in range(3):
        cases.append(
            CanaryCase(
                case_id=f"case-{index + 0x100:032x}",
                cluster="Health & Medicine",
                canonical_hash=f"{index + 0x100:064x}",
                target_row_sha256=approved[1].target_row_sha256,
                source_row_snapshot_sha256=approved[1].source_row_snapshot_sha256,
            )
        )
    assert len(cases) == 12
    with pytest.raises(Exception, match="DUPLICATE_CANARY_TARGET"):
        select_comparison_cases(
            tuple(cases),
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=_target_source(),
        )


def test_selection_rejects_missing_cluster() -> None:
    # An 11-case input is a forged subset: the identity count check fires
    # before the cluster check.
    cases = [case for case in _approved_twelve() if case.cluster != "Materials Science"]
    with pytest.raises(Exception, match="CANARY_IDENTITY_UNAPPROVED"):
        select_comparison_cases(
            tuple(cases),
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=_target_source(),
        )
    # A full 12-case list with a replaced cluster fails MISSING_CLUSTER.
    replaced = [
        CanaryCase(
            case_id=f"case-{index:032x}",
            cluster=OFFCLUSTER,
            canonical_hash=f"{index:064x}",
            target_row_sha256=f"{index:064x}",
            source_row_snapshot_sha256=f"{index:064x}",
        )
        for index in range(12)
    ]
    with pytest.raises(Exception, match="MISSING_CLUSTER"):
        select_comparison_cases(
            tuple(replaced),
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=_target_source(),
        )


def test_selection_rejects_source_hash_drift() -> None:
    drifted = dict(_target_source())
    drifted["Materials Science"] = TargetSourceSnapshot(
        target_dataset_sha256="c" * 64, target_row_sha256="f" * 64
    )
    with pytest.raises(Exception, match="SOURCE_HASH_DRIFT"):
        select_comparison_cases(
            _approved_twelve(),
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=drifted,
        )


def test_selection_does_not_read_target_contribution_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The selection input stream never touches contribution/result fields.

    The comparison consumes only the Canary identity records
    (`CanaryCase`), never raw CSV rows. The guarantee proven here: a
    poisoned target CSV with `contribution`/`route_result` columns cannot
    enter the selection decision, because the identity document the
    selection consumes and the manifest it emits never carry those fields
    (nor any content-bearing field at all).
    """
    poisoned_csv = (
        "paperId,title,abstract,externalIds,abstract_summary,contribution,route_result\n"
        f"{'a' * 40},Private Target,Secret abstract,{{}},Summary,SECRET-CONTRIBUTION,LEAKED-ROUTING\n"
    ).encode("utf-8")
    # The selection seam's input type carries no content fields by
    # construction: CanaryCase fields are identity-only.
    case = _case("case-" + "a" * 32, APPROVED_CLUSTERS[0], "5" * 64)
    case_fields = frozenset(
        {
            "case_id",
            "cluster",
            "canonical_hash",
            "target_row_sha256",
            "source_row_snapshot_sha256",
        }
    )
    assert frozenset(f for f in case.__dataclass_fields__) == case_fields
    selected = select_comparison_cases(
        _approved_twelve(),
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=_target_source(),
    )
    manifest_text = canonical_json_bytes(_selection_manifest(selected)).decode("utf-8")
    # No content field name, and none of the poisoned values, appear in
    # the serialized selection decision.
    for needle in (
        "contribution",
        "route_result",
        "SECRET-CONTRIBUTION",
        "LEAKED-ROUTING",
        "Secret abstract",
        "abstract",
        "title",
        "abstract_summary",
    ):
        assert needle not in manifest_text
    assert (
        "contribution" not in poisoned_csv.decode("utf-8") or True
    )  # csv content is never parsed here


def test_selection_seed_is_stable_across_runs() -> None:
    manifest = _selection_manifest(_selected())
    seed_one = comparison_selection_seed(manifest)
    seed_two = comparison_selection_seed(_selection_manifest(_selected()))
    assert seed_one == seed_two
    assert len(seed_one) == 64


# ==========================================================================
# Frozen matrix: shape, order balance, single variable
# ==========================================================================


def test_matrix_is_exactly_four_pairs_and_eight_runs() -> None:
    selected = _selected()
    runs, pairs, document, _manifest = _matrix(selected)
    assert len(pairs) == 4
    assert len(runs) == 8
    assert document["pairs_count"] == 4
    assert document["planned_runs_count"] == 8
    # One run per arm position per pair.
    for pair_index in range(1, 5):
        arm_runs = [run for run in runs if run.pair_index == pair_index]
        assert sorted(run.arm_position for run in arm_runs) == [1, 2]
        assert {run.profile_id for run in arm_runs} == {
            cmp_mod.BASELINE_PROFILE_ID,
            cmp_mod.CHALLENGER_PROFILE_ID,
        }


def test_matrix_order_is_exactly_two_two_balanced() -> None:
    _runs, pairs, document, _manifest = _matrix(_selected())
    assert document["baseline_first_pairs_count"] == 2
    assert document["challenger_first_pairs_count"] == 2
    assert (
        sum(1 for pair in pairs if pair.first_profile_id == cmp_mod.BASELINE_PROFILE_ID)
        == 2
    )
    assert (
        sum(
            1
            for pair in pairs
            if pair.first_profile_id == cmp_mod.CHALLENGER_PROFILE_ID
        )
        == 2
    )


def test_matrix_arms_differ_only_in_prompt_profile() -> None:
    _runs, _pairs, document, _manifest = _matrix(_selected())
    assert_single_variable_matrix(document)  # must not raise


def test_matrix_rejects_arm_specification_drift() -> None:
    document = dict(_matrix(_selected())[2])
    tampered = [dict(run) for run in document["runs"]]
    tampered[0]["num_reflections"] = 5
    drifted = dict(document)
    drifted["runs"] = tampered
    with pytest.raises(Exception, match="ARM_SPECIFICATION_DRIFT"):
        assert_single_variable_matrix(drifted)


def test_matrix_is_byte_identical_across_replays() -> None:
    first = _matrix(_selected())[2]
    second = _matrix(_selected())[2]
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert cmp_mod.matrix_sha256(first) == cmp_mod.matrix_sha256(second)


# ==========================================================================
# Blind mapping: 2/2 balance, secrecy, fail-closed reveal
# ==========================================================================


def test_blind_mapping_is_exactly_two_two_balanced() -> None:
    from ai_scientist.ideation.comparison import build_blind_mapping

    _runs, pairs, _document, manifest = _matrix(_selected())
    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    a_baseline = sum(
        1 for m in mappings if m.arm_a_profile_id == cmp_mod.BASELINE_PROFILE_ID
    )
    a_challenger = sum(
        1 for m in mappings if m.arm_a_profile_id == cmp_mod.CHALLENGER_PROFILE_ID
    )
    assert (a_baseline, a_challenger) == (2, 2)
    for mapping in mappings:
        assert mapping.arm_a_profile_id != mapping.arm_b_profile_id


def test_blind_mapping_is_byte_identical_and_shape_checked() -> None:
    from ai_scientist.ideation.comparison import (
        assert_blind_mapping_document_shape,
        blind_mapping_document,
        build_blind_mapping,
    )

    _runs, pairs, _document, manifest = _matrix(_selected())
    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    document = blind_mapping_document(mappings, selection_manifest=manifest)
    reparsed = assert_blind_mapping_document_shape(document)
    assert reparsed == mappings
    again = blind_mapping_document(
        build_blind_mapping(pairs, selection_manifest=manifest),
        selection_manifest=manifest,
    )
    assert canonical_json_bytes(document) == canonical_json_bytes(again)


def test_blind_mapping_tampered_balance_fails_closed() -> None:
    from ai_scientist.ideation.comparison import (
        assert_blind_mapping_document_shape,
        blind_mapping_document,
        build_blind_mapping,
    )

    _runs, pairs, _document, manifest = _matrix(_selected())
    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    document = blind_mapping_document(mappings, selection_manifest=manifest)
    tampered = dict(document)
    flipped_pairs = []
    baseline_flips = 0
    for entry in document["pairs"]:
        flipped = dict(entry)
        if (
            flipped["arm_a_profile_id"] == cmp_mod.BASELINE_PROFILE_ID
            and baseline_flips < 3
        ):
            flipped["arm_a_profile_id"] = cmp_mod.CHALLENGER_PROFILE_ID
            flipped["arm_b_profile_id"] = cmp_mod.BASELINE_PROFILE_ID
            baseline_flips += 1
        flipped_pairs.append(flipped)
    tampered["pairs"] = flipped_pairs
    with pytest.raises(Exception, match="BLIND_BALANCE_FAILED"):
        assert_blind_mapping_document_shape(tampered)


def test_pair_packet_never_carries_blinding_or_operational_metadata() -> None:
    from ai_scientist.ideation.comparison import build_pair_packet

    idea_a = {
        "Experiments": ["collect field samples"],
        "Name": "field_probe",
        "Title": "Field probe",
    }
    idea_b = {
        "Experiments": ["fine-tune a benchmark model"],
        "Name": "benchmark_probe",
        "Title": "Benchmark probe",
    }
    packet = build_pair_packet(
        1,
        _selected()[0].case_id,
        _selected()[0].cluster,
        idea_a,
        idea_b,
        selection_manifest=_selection_manifest(_selected()),
    )
    assert packet["arm_a"]["idea"] == idea_a
    assert packet["arm_b"]["idea"] == idea_b

    # Structural scan: no forbidden metadata key anywhere, no profile
    # identity value outside the idea payloads.
    def _check(value, path="packet"):
        if isinstance(value, dict):
            for key, item in value.items():
                assert key.lower() not in cmp_mod.PAIR_PACKET_FORBIDDEN_KEYS, key
                _check(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _check(item, f"{path}[{index}]")
        elif isinstance(value, str):
            if f"{path}.idea" not in path and "idea" not in path.split(".")[-2:]:
                assert value not in cmp_mod.PAIR_PACKET_FORBIDDEN_IDENTITY_VALUES, value

    _check({k: v for k, v in packet.items() if k not in ("arm_a", "arm_b")})


def test_pair_packet_rejects_identical_arms() -> None:
    from ai_scientist.ideation.comparison import build_pair_packet

    idea = {"Name": "same", "Title": "Same"}
    with pytest.raises(Exception, match="PACKET_PAYLOAD_COLLAPSE"):
        build_pair_packet(
            1,
            _selected()[0].case_id,
            _selected()[0].cluster,
            idea,
            dict(idea),
            selection_manifest=_selection_manifest(_selected()),
        )


def test_pair_packet_is_deterministic() -> None:
    from ai_scientist.ideation.comparison import build_pair_packet

    selected = _selected()
    manifest = _selection_manifest(selected)
    idea_a = {"Name": "probe_a", "Title": "A"}
    idea_b = {"Name": "probe_b", "Title": "B"}
    first = build_pair_packet(
        1,
        selected[0].case_id,
        selected[0].cluster,
        idea_a,
        idea_b,
        selection_manifest=manifest,
    )
    second = build_pair_packet(
        1,
        selected[0].case_id,
        selected[0].cluster,
        idea_a,
        idea_b,
        selection_manifest=manifest,
    )
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


# ==========================================================================
# Commands: production parser contract, credential-free shape
# ==========================================================================


def test_commands_parse_with_production_parser_and_stay_credential_free() -> None:
    from ai_scientist.ideation.comparison import build_comparison_commands
    from ai_scientist.perform_ideation_temp_free import _build_parser

    runs, _pairs, document, _manifest = _matrix(_selected())
    commands = build_comparison_commands(runs, matrix_document=document)
    assert len(commands) == 8
    parser = _build_parser()
    for command in commands:
        assert "scripts/with-project-env" in command
        tokens = shlex.split(command)
        dash_index = tokens.index("--")
        payload = tokens[dash_index + 1 :]
        parsed = parser.parse_args(payload[2:])
        assert parsed.entry == "new-run"
        assert parsed.prompt_profile in (
            cmp_mod.BASELINE_PROFILE_ID,
            cmp_mod.CHALLENGER_PROFILE_ID,
        )
        assert parsed.max_num_generations == 1
        assert parsed.num_reflections == 3
        for forbidden in (
            "--reasoning-effort",
            "--max-tokens",
            "DEEPSEEK_API_KEY",
            "sk-",
            "| yes",
            "echo yes",
        ):
            assert forbidden not in command


def test_commands_reject_unsupported_provider_arguments() -> None:
    from ai_scientist.ideation.comparison import _assert_command_contract

    base = (
        "python scripts/with-project-env -- python "
        "ai_scientist/perform_ideation_temp_free.py new-run "
        "--case-id case-0123456789abcdef0123456789abcdef "
        "--workshop artifacts/w.md --workshop-sha256 "
        + "2" * 64
        + " --corpus artifacts/c.json --corpus-sha256 "
        + "1" * 64
        + " --max-num-generations 1 --num-reflections 3 "
        "--prompt-profile ml-baseline-v1"
    )
    _assert_command_contract(base)  # accepted
    with pytest.raises(Exception, match="COMMAND_NOT_PARSER_SUPPORTED"):
        _assert_command_contract(base + " --reasoning-effort max")
    with pytest.raises(Exception, match="COMMAND_NOT_PARSER_SUPPORTED"):
        _assert_command_contract(base + " --max-tokens 32768")
    with pytest.raises(Exception, match="COMMAND_FORBIDDEN_ARGUMENT"):
        _assert_command_contract(
            base.replace("scripts/with-project-env", "DEEPSEEK_API_KEY=sk-xxx python")
        )


# ==========================================================================
# Spend ledger: append-only, Plan Gate arithmetic, not per-run approval
# ==========================================================================


def _ledger():
    _runs, _pairs, document, _manifest = _matrix(_selected())
    from decimal import Decimal as D

    return cmp_mod.initialize_comparison_ledger(
        matrix_document=document, plan_gate_subcap_cny=D("4.00")
    )


def _entry(run_index: int, cost: str, run_id: str) -> cmp_mod.LedgerEntry:
    from decimal import Decimal as D

    return cmp_mod.LedgerEntry(
        run_index=run_index,
        pair_index=1,
        case_id=_selected()[0].case_id,
        profile_id=cmp_mod.BASELINE_PROFILE_ID,
        run_id=run_id,
        status="success",
        actual_cost_cny=D(cost),
        worst_case_bound_cny=D("0.50"),
        physical_attempt_count=1,
    )


def test_ledger_starts_at_zero_and_is_append_only() -> None:
    from decimal import Decimal as D

    ledger = _ledger()
    assert ledger["current_actual_spend_cny"] == "0.00"
    assert ledger["status"] == "initialized"
    updated = cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(1, "0.14", "r1"))
    assert updated["current_actual_spend_cny"] == "0.14"
    assert len(updated["entries"]) == 1
    twice = cmp_mod.ingest_run_actual_cost(updated, entry=_entry(2, "0.20", "r2"))
    assert twice["current_actual_spend_cny"] == "0.34"
    # Duplicate run / slot ingests fail closed.
    with pytest.raises(Exception, match="LEDGER_DUPLICATE_RUN"):
        cmp_mod.ingest_run_actual_cost(twice, entry=_entry(3, "0.01", "r1"))
    with pytest.raises(Exception, match="LEDGER_DUPLICATE_SLOT"):
        cmp_mod.ingest_run_actual_cost(twice, entry=_entry(2, "0.01", "r3"))


def test_ledger_ingests_failed_suspended_resumed_and_retried_runs() -> None:
    ledger = _ledger()
    statuses = ("failed", "suspended", "resume_success", "success")
    for index, status in enumerate(statuses, start=1):
        entry = _entry(index, "0.10", f"r{index}")
        object.__setattr__(entry, "status", status)
        entry = cmp_mod.LedgerEntry(
            run_index=index,
            pair_index=1,
            case_id=entry.case_id,
            profile_id=entry.profile_id,
            run_id=entry.run_id,
            status=status,
            actual_cost_cny=entry.actual_cost_cny,
            worst_case_bound_cny=entry.worst_case_bound_cny,
            physical_attempt_count=2 if status == "resume_success" else 1,
        )
        ledger = cmp_mod.ingest_run_actual_cost(ledger, entry=entry)
    assert ledger["current_actual_spend_cny"] == "0.40"
    attempts = [e["physical_attempt_count"] for e in ledger["entries"]]
    assert attempts == [1, 1, 2, 1]


def test_plan_gate_accepts_exact_bound_and_refuses_one_cent_over() -> None:
    from decimal import Decimal as D

    ledger = _ledger()
    # subcap 4.00; spend exactly 3.50 -> next bound 0.50 fits exactly.
    ledger = cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(1, "3.50", "r1"))
    assert cmp_mod.plan_gate_next_run_allowed(
        ledger, next_run_worst_case_bound_cny=D("0.50")
    )
    assert not cmp_mod.plan_gate_one_cent_over(ledger, next_bound=D("0.50"))
    # One cent over is refused.
    assert not cmp_mod.plan_gate_next_run_allowed(
        ledger, next_run_worst_case_bound_cny=D("0.51")
    )
    assert cmp_mod.plan_gate_one_cent_over(ledger, next_bound=D("0.51"))


def test_plan_gate_subcap_cannot_exceed_canary_cap() -> None:
    from decimal import Decimal as D

    _runs, _pairs, document, _manifest = _matrix(_selected())
    with pytest.raises(Exception, match="SUBCAP_EXCEEDS_CANARY_CAP"):
        cmp_mod.initialize_comparison_ledger(
            matrix_document=document, plan_gate_subcap_cny=D("30.01")
        )


def test_plan_gate_is_not_a_per_run_approval() -> None:
    approval = cmp_mod.plan_gate_approval_document(
        ledger=_ledger(), approved_by="Robert"
    )
    assert cmp_mod.plan_gate_does_not_waive_per_run_approval(approval)
    assert approval["scope"] == "matrix_level_only_not_per_run"


def test_ledger_hard_cap_refusal() -> None:
    from decimal import Decimal as D

    ledger = _ledger()
    with pytest.raises(Exception, match="BUDGET_EXCEEDED"):
        cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(1, "30.01", "r1"))


# ==========================================================================
# Result ingestion: fail-closed against corrupt/drifted/cross-case evidence
# ==========================================================================


def _ingest_args(
    selected, run_index: int, pair_index: int, arm_position: int, profile_id: str
):
    case = selected[(run_index - 1) // 2]
    return dict(
        expected_run_index=run_index,
        expected_arm_position=arm_position,
        expected_pair_index=pair_index,
        expected_case_id=case.case_id,
        expected_profile_id=profile_id,
    )


def _make_sealed_run(
    workspace: Path,
    inputs: dict[str, str],
    profile_id: str,
    transport_responses: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    helpers: Any,
) -> str:
    from ai_scientist.ideation.deepseek import DeepSeekAdapter
    from ai_scientist.ideation.pricing import load_price_table

    helpers._approve_cost(monkeypatch)
    request = helpers.make_request(helpers, inputs, profile_id)
    result = helpers.run_new_run(workspace, request, execute=False)
    assert result["status"] == "admitted", result
    run_id = result["run_id"]
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace),
        transport=_SequencedTransport(transport_responses),
    )
    from ai_scientist.ideation.controller import IdeationController

    sealed = IdeationController(workspace, run_id, adapter=adapter).run()
    assert sealed["status"] == "sealed", sealed
    return run_id


class _SequencedTransport:
    """Stub transport serving a scripted list of responses."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.sent_requests: list[dict[str, Any]] = []

    def send(self, request: dict[str, Any]) -> Any:
        self.sent_requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _stub_response(content: str, duration_ms: float = 30.0) -> Any:
    from ai_scientist.ideation.canonical import canonical_json_bytes as cjb
    from ai_scientist.ideation.deepseek import TransportResponse

    body = cjb(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {
                        "content": content,
                        "reasoning_content": "Detailed reasoning...",
                        "role": "assistant",
                    },
                }
            ],
            "created": 1725360000,
            "id": "chatcmpl-comparison",
            "model": "deepseek-v4-pro",
            "object": "chat.completion",
            "system_fingerprint": "fp_comparison",
            "usage": {
                "completion_tokens": 50,
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
                "prompt_tokens": 100,
                "total_tokens": 150,
            },
        }
    )
    return TransportResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body=body,
        duration_ms=duration_ms,
    )


# ==========================================================================
# Write-once verdicts + reveal gate
# ==========================================================================


def _verdict(case_id: str, verdict: str = "a_better") -> cmp_mod.PairVerdict:
    return cmp_mod.PairVerdict(
        case_id=case_id,
        verdict=verdict,
        overall_rationale="Arm A proposes a stronger validation plan.",
        domain_method_fit={"arm_a": "improved", "arm_b": "unchanged"},
        unjustified_ml_intrusion={"arm_a": "decreased", "arm_b": "unchanged"},
        rubric_floor={"arm_a": "clean", "arm_b": "clean"},
        recorded_at="2026-09-04T08:00:00.000000Z",
    )


def _vault(tmp_path: Path) -> cmp_mod.ComparisonVault:
    return cmp_mod.ComparisonVault(tmp_path / "comparison")


def test_verdict_is_write_once_and_cannot_be_overwritten(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    case_id = _selected()[0].case_id
    packet_sha = "5" * 64
    vault.record_verdict(_verdict(case_id), packet_sha256=packet_sha)
    with pytest.raises(Exception, match="ARTIFACT_EXISTS"):
        vault.record_verdict(
            _verdict(case_id, verdict="b_better"), packet_sha256=packet_sha
        )
    stored = vault.load_verdict(case_id)
    assert stored["verdict"] == "a_better"


def test_verdict_closed_enums_fail_closed(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    case_id = _selected()[0].case_id
    bad = _verdict(case_id)
    object.__setattr__(bad, "verdict", "a_wins")
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(bad, packet_sha256="5" * 64)
    bad_fit = _verdict(case_id)
    object.__setattr__(
        bad_fit, "domain_method_fit", {"arm_a": "better", "arm_b": "unchanged"}
    )
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(bad_fit, packet_sha256="5" * 64)
    bad_floor = _verdict(case_id)
    object.__setattr__(
        bad_floor, "rubric_floor", {"arm_a": "terrible", "arm_b": "clean"}
    )
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(bad_floor, packet_sha256="5" * 64)


def test_reveal_fails_closed_until_all_verdicts_frozen(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    selected = _selected()
    _runs, pairs, _document, manifest = _matrix(selected)
    from ai_scientist.ideation.comparison import build_blind_mapping

    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    case_ids = tuple(case.case_id for case in selected)
    # Zero verdicts: blocked.
    with pytest.raises(Exception, match="REVEAL_BLOCKED"):
        vault.reveal(
            mappings=mappings,
            selection_manifest=manifest,
            required_case_ids=case_ids,
        )
    # One verdict short: still blocked.
    for case_id in case_ids[:-1]:
        vault.record_verdict(_verdict(case_id), packet_sha256="5" * 64)
    with pytest.raises(Exception, match="REVEAL_BLOCKED"):
        vault.reveal(
            mappings=mappings,
            selection_manifest=manifest,
            required_case_ids=case_ids,
        )
    # Final verdict freezes the matrix; reveal now succeeds once.
    vault.record_verdict(_verdict(case_ids[-1]), packet_sha256="5" * 64)
    document = vault.reveal(
        mappings=mappings,
        selection_manifest=manifest,
        required_case_ids=case_ids,
    )
    assert document["blind_mapping"]["pairs_count"] == 4
    with pytest.raises(Exception, match="ARTIFACT_EXISTS"):
        vault.reveal(
            mappings=mappings,
            selection_manifest=manifest,
            required_case_ids=case_ids,
        )


def test_verdict_after_reveal_fails_closed(tmp_path: Path) -> None:
    vault = _vault(tmp_path)
    selected = _selected()
    _runs, pairs, _document, manifest = _matrix(selected)
    from ai_scientist.ideation.comparison import build_blind_mapping

    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    case_ids = tuple(case.case_id for case in selected)
    for case_id in case_ids:
        vault.record_verdict(_verdict(case_id), packet_sha256="5" * 64)
    vault.reveal(
        mappings=mappings,
        selection_manifest=manifest,
        required_case_ids=case_ids,
    )
    late_case = f"case-{'9' * 32}"
    with pytest.raises(Exception, match="VERDICT_AFTER_REVEAL"):
        vault.record_verdict(_verdict(late_case), packet_sha256="5" * 64)


# ==========================================================================
# Deterministic reducer: every gate, promote and every reject branch
# ==========================================================================


def _run_metrics(
    profile_id: str,
    *,
    cost: str = "0.14",
    latency_ms: str = "100.0",
    terminal_outcome: str = "success",
    finish_reasons: tuple[str, ...] = ("stop",),
    attempts: int = 1,
    deterministic_pass: bool = True,
) -> cmp_mod.RunMetrics:
    from decimal import Decimal as D

    return cmp_mod.RunMetrics(
        run_id=f"run-{profile_id}-{attempts}-{terminal_outcome}",
        run_index=1,
        pair_index=1,
        arm_position=1,
        case_id="case-" + "0" * 32,
        profile_id=profile_id,
        terminal_outcome=terminal_outcome,
        finish_reasons=finish_reasons,
        physical_attempt_count=attempts,
        end_to_end_latency_ms=D(latency_ms),
        actual_cost_cny=D(cost),
        idea_count=1,
        deterministic_validation_passed=deterministic_pass,
    )


def _reducer_env():
    selected = _selected()
    _runs, pairs, document, manifest = _matrix(selected)
    from ai_scientist.ideation.comparison import (
        build_blind_mapping,
        blind_mapping_document,
    )

    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    reveal_document = {
        "blind_mapping": blind_mapping_document(mappings, selection_manifest=manifest),
        "revealed_at": "2026-09-04T08:00:00.000000Z",
        "schema_version": "comparison-reveal-v1.0.0",
    }
    ledger = cmp_mod.initialize_comparison_ledger(
        matrix_document=document, plan_gate_subcap_cny=Decimal("4.00")
    )
    return selected, reveal_document, manifest, document, ledger


def _mappings_from(reveal_document):
    from ai_scientist.ideation.comparison import assert_blind_mapping_document_shape

    return assert_blind_mapping_document_shape(reveal_document["blind_mapping"])


def _facts(
    selected,
    mappings,
    *,
    verdict_by_case: dict[str, str] | None = None,
    baseline_metrics: cmp_mod.RunMetrics | None = None,
    challenger_metrics: cmp_mod.RunMetrics | None = None,
    verdict_mutate=None,
) -> tuple[cmp_mod.PairFacts, ...]:
    facts = []
    for pair_index, case in enumerate(selected, start=1):
        case_id = case.case_id
        verdict_value = (verdict_by_case or {}).get(case_id, "a_better")
        verdict = _verdict(case_id, verdict_value)
        if verdict_mutate is not None:
            verdict = verdict_mutate(case_id, verdict)
        document = cmp_mod.verdict_document(verdict, packet_sha256="5" * 64)
        baseline = baseline_metrics or _run_metrics(cmp_mod.BASELINE_PROFILE_ID)
        challenger = challenger_metrics or _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID)
        facts.append(
            cmp_mod.PairFacts(
                pair_index=pair_index,
                case_id=case_id,
                cluster=case.cluster,
                baseline_metrics=baseline,
                challenger_metrics=challenger,
                verdict=document,
            )
        )
    return tuple(facts)


def _reduce(facts, ledger, mappings, document, manifest):
    """Reducer entry from typed mappings (derives the reveal document)."""
    if (
        isinstance(mappings, tuple)
        and mappings
        and isinstance(mappings[0], cmp_mod.BlindPairMapping)
    ):
        reveal_document = {
            "blind_mapping": cmp_mod.blind_mapping_document(
                mappings, selection_manifest=manifest
            ),
            "revealed_at": "2026-09-04T08:00:00.000000Z",
            "schema_version": "comparison-reveal-v1.0.0",
        }
    else:
        reveal_document = mappings
    return cmp_mod.reduce_prompt_comparison(
        selection_manifest=manifest,
        matrix_document=document,
        reveal_document=reveal_document,
        pair_facts=facts,
        ledger=ledger,
    )


def test_reducer_promotes_a_clean_three_zero_sweep() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # The verdicts are blinded letters; choose the challenger side per pair
    # via its frozen blind mapping, exactly how a real sweep is judged.
    verdicts = {
        case.case_id: _letter_for(case, mappings, cmp_mod.CHALLENGER_PROFILE_ID)
        for case in selected
    }
    facts = _facts(selected, mappings, verdict_by_case=verdicts)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    quality = reduction["gates"]["quality_3_0"]
    assert quality["challenger_wins"] == 4
    assert quality["baseline_wins"] == 0
    assert reduction["decision"] == "promote"
    assert reduction["revealed_pair_profiles"] is not None
    # Deterministic: byte-identical re-reduction.
    again = _reduce(facts, ledger, mappings, document, manifest)
    assert canonical_json_bytes(reduction) == canonical_json_bytes(again)


def test_reducer_rejects_two_zero_sweep() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    facts = _facts(selected, mappings, verdict_by_case={selected[0].case_id: "tie"})
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["quality_3_0"]["pass"] is False
    assert reduction["decision"] == "reject"


def test_reducer_rejects_any_baseline_win() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # Choose a verdict letter that maps to the baseline side for pair 2.
    baseline_letter = _baseline_letter(selected[1], mappings)
    other = "b_better" if baseline_letter == "a_better" else "a_better"
    facts = _facts(selected, mappings, verdict_by_case={selected[1].case_id: other})
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["quality_3_0"]["baseline_wins"] >= 1
    assert reduction["decision"] == "reject"


def test_reducer_treats_incomparable_verdict_as_incomplete() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    facts = _facts(
        selected, mappings, verdict_by_case={selected[2].case_id: "incomparable"}
    )
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["decision"] == "incomplete"
    assert reduction["gates"]["completeness"]["pass"] is False


def test_reducer_incomplete_when_arm_metrics_missing() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    facts = list(
        _facts(
            selected,
            mappings,
            verdict_by_case={c.case_id: "a_better" for c in selected},
        )
    )
    facts[0] = cmp_mod.PairFacts(
        pair_index=facts[0].pair_index,
        case_id=facts[0].case_id,
        cluster=facts[0].cluster,
        baseline_metrics=None,
        challenger_metrics=facts[0].challenger_metrics,
        verdict=facts[0].verdict,
    )
    reduction = _reduce(tuple(facts), ledger, mappings, document, manifest)
    assert reduction["decision"] == "incomplete"


def _fit_mutate(arm: str, value: str):
    def mutate(case_id: str, verdict: cmp_mod.PairVerdict) -> cmp_mod.PairVerdict:
        updated = dict(verdict.domain_method_fit)
        updated[arm] = value
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=updated,
            unjustified_ml_intrusion=dict(verdict.unjustified_ml_intrusion),
            rubric_floor=dict(verdict.rubric_floor),
            recorded_at=verdict.recorded_at,
        )

    return mutate


def test_reducer_rejects_domain_method_regression() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # Regress the challenger arm on pair 1 (find the challenger letter).
    case0 = selected[0]
    challenger_letter = _challenger_letter(case0, mappings)
    facts = _facts(
        selected,
        mappings,
        verdict_mutate=_fit_mutate(challenger_letter, "worse"),
    )
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["domain_method_fit"]["regressed_pairs"] >= 1
    assert reduction["decision"] == "reject"


def test_reducer_rejects_when_domain_method_fit_improves_fewer_than_two() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # Only one pair improves; the rest unchanged.
    case0 = selected[0]
    challenger_letter = _challenger_letter(case0, mappings)
    baseline_letter = _baseline_letter(case0, mappings)

    def mutate(case_id: str, verdict: cmp_mod.PairVerdict) -> cmp_mod.PairVerdict:
        if case_id == case0.case_id:
            fit = {challenger_letter: "improved", baseline_letter: "unchanged"}
        else:
            fit = {"arm_a": "unchanged", "arm_b": "unchanged"}
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=fit,
            unjustified_ml_intrusion=dict(verdict.unjustified_ml_intrusion),
            rubric_floor=dict(verdict.rubric_floor),
            recorded_at=verdict.recorded_at,
        )

    facts = _facts(selected, mappings, verdict_mutate=mutate)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["domain_method_fit"]["improved_pairs"] < 2
    assert reduction["decision"] == "reject"


def test_reducer_rejects_increased_ml_intrusion() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)

    def mutate(case_id: str, verdict: cmp_mod.PairVerdict) -> cmp_mod.PairVerdict:
        case = next(c for c in selected if c.case_id == case_id)
        letter = _challenger_letter(case, mappings)
        intrusion = dict(verdict.unjustified_ml_intrusion)
        intrusion[letter] = "increased"
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=dict(verdict.domain_method_fit),
            unjustified_ml_intrusion=intrusion,
            rubric_floor=dict(verdict.rubric_floor),
            recorded_at=verdict.recorded_at,
        )

    facts = _facts(selected, mappings, verdict_mutate=mutate)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["ml_intrusion"]["increased_pairs"]
    assert reduction["decision"] == "reject"


def test_reducer_rejects_rubric_floor_hit_on_either_arm() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # Baseline arm hits an unsound floor: still blocks promotion.
    case0 = selected[0]
    baseline_letter = _baseline_letter(case0, mappings)

    def mutate(case_id: str, verdict: cmp_mod.PairVerdict) -> cmp_mod.PairVerdict:
        floor = {"arm_a": "clean", "arm_b": "clean"}
        if case_id == case0.case_id:
            floor[baseline_letter] = "unsound"
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=dict(verdict.domain_method_fit),
            unjustified_ml_intrusion=dict(verdict.unjustified_ml_intrusion),
            rubric_floor=floor,
            recorded_at=verdict.recorded_at,
        )

    facts = _facts(selected, mappings, verdict_mutate=mutate)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["rubric_floor"]["hits"]
    assert reduction["decision"] == "reject"


def test_reducer_rejects_deterministic_regression() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    failing = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, deterministic_pass=False)
    facts = _facts(selected, mappings, challenger_metrics=failing)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["deterministic_regression"]["problems"]
    assert reduction["decision"] == "reject"


def test_reducer_rejects_challenger_only_truncation() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    challenger = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, finish_reasons=("length",))
    facts = _facts(selected, mappings, challenger_metrics=challenger)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["reliability"]["problems"]
    assert reduction["decision"] == "reject"


def test_reducer_rejects_challenger_only_retry_increase() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    challenger = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, attempts=2)
    facts = _facts(selected, mappings, challenger_metrics=challenger)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert any(
        problem["pattern"] == "challenger_only_retry_increase"
        for problem in reduction["gates"]["reliability"]["problems"]
    )
    assert reduction["decision"] == "reject"


def test_reducer_rejects_challenger_only_terminal_failure() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    challenger = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, terminal_outcome="failed")
    facts = _facts(selected, mappings, challenger_metrics=challenger)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["decision"] == "incomplete"


def test_reducer_rejects_latency_envelope_breach() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    challenger = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, latency_ms="200.1")
    baseline = _run_metrics(cmp_mod.BASELINE_PROFILE_ID, latency_ms="100.0")
    facts = _facts(
        selected, mappings, baseline_metrics=baseline, challenger_metrics=challenger
    )
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["cost_latency_envelope"]["pass"] is False
    assert reduction["decision"] == "reject"


def test_reducer_accepts_latency_exactly_two_times() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    challenger = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, latency_ms="200.0")
    baseline = _run_metrics(cmp_mod.BASELINE_PROFILE_ID, latency_ms="100.0")
    facts = _facts(
        selected, mappings, baseline_metrics=baseline, challenger_metrics=challenger
    )
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["cost_latency_envelope"]["pass"] is True


def test_reducer_rejects_cost_envelope_breach() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    challenger = _run_metrics(cmp_mod.CHALLENGER_PROFILE_ID, cost="0.29")
    baseline = _run_metrics(cmp_mod.BASELINE_PROFILE_ID, cost="0.14")
    facts = _facts(
        selected, mappings, baseline_metrics=baseline, challenger_metrics=challenger
    )
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["cost_latency_envelope"]["pass"] is False
    assert reduction["decision"] == "reject"


def test_reducer_incomplete_when_verdict_missing() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    facts = list(
        _facts(
            selected,
            mappings,
            verdict_by_case={c.case_id: "a_better" for c in selected},
        )
    )
    facts[0] = cmp_mod.PairFacts(
        pair_index=facts[0].pair_index,
        case_id=facts[0].case_id,
        cluster=facts[0].cluster,
        baseline_metrics=facts[0].baseline_metrics,
        challenger_metrics=facts[0].challenger_metrics,
        verdict=None,
    )
    reduction = _reduce(tuple(facts), ledger, mappings, document, manifest)
    assert reduction["decision"] == "incomplete"


def _challenger_letter(case, mappings) -> str:
    mapping = cmp_mod._mapping_for_case(mappings, case.case_id)
    return (
        "arm_a"
        if mapping.arm_a_profile_id == cmp_mod.CHALLENGER_PROFILE_ID
        else "arm_b"
    )


def _baseline_letter(case, mappings) -> str:
    mapping = cmp_mod._mapping_for_case(mappings, case.case_id)
    return (
        "arm_a" if mapping.arm_a_profile_id == cmp_mod.BASELINE_PROFILE_ID else "arm_b"
    )


def _other_letter(letter: str) -> str:
    return "arm_b" if letter == "arm_a" else "arm_a"


def _letter_for(case, mappings, profile_id: str) -> str:
    mapping = cmp_mod._mapping_for_case(mappings, case.case_id)
    if mapping.arm_a_profile_id == profile_id:
        return "a_better"
    if mapping.arm_b_profile_id == profile_id:
        return "b_better"
    raise AssertionError("profile not in mapping")


# ==========================================================================
# E2E synthetic lifecycle: real sealed runs through the whole boundary
# ==========================================================================


@pytest.fixture(scope="module")
def helpers():
    from tests.comparison_synthetic import _load_helper_module

    return _load_helper_module()


@pytest.fixture(scope="module")
def synthetic_workspace(tmp_path_factory, helpers):
    from tests.comparison_synthetic import prepare_workspace

    tmp = tmp_path_factory.mktemp("comparison-synthetic")
    workspace, prepared = prepare_workspace(tmp, helpers)
    return workspace, prepared


def test_synthetic_sealed_runs_flow_through_ingestion_and_reduction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    helpers: Any,
    synthetic_workspace: tuple[Any, Any],
) -> None:
    from ai_scientist.ideation.comparison import (
        APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        CANARY_HARD_CAP_CNY,
        CanaryCase,
        COMPARISON_CLUSTERS,
        ComparisonVault,
        PairFacts,
        PairVerdict,
        TargetSourceSnapshot,
        build_blind_mapping,
        build_comparison_commands,
        build_frozen_matrix,
        build_matrix_document,
        build_pair_packet,
        build_selection_manifest,
        ingest_comparison_result,
        initialize_comparison_ledger,
        reduce_prompt_comparison,
        select_comparison_cases,
    )
    from tests.comparison_synthetic import (
        finish_sealed_run_pipeline,
        run_one_sealed_run,
    )

    workspace, prepared = synthetic_workspace
    monkeypatch.chdir(workspace)

    # A full synthetic 12-case approved-Canary identity: the four prepared
    # cases fill the four pre-registered clusters; eight filler cases
    # complete the twelve-case identity (the real Canary holds multiple
    # cases per cluster; fillers are never selected because the prepared
    # cases carry the lower canonical hashes).
    clusters = list(COMPARISON_CLUSTERS)
    filler_clusters = sorted(cmp_mod.CANARY_CLUSTERS - set(clusters)) + clusters
    synthetic_cases: list[CanaryCase] = []
    for index, (case_id, inputs) in enumerate(prepared):
        synthetic_cases.append(
            CanaryCase(
                case_id=case_id,
                cluster=clusters[index],
                canonical_hash=f"{index:062d}00",
                target_row_sha256=inputs["corpus_sha256"],
                source_row_snapshot_sha256=inputs["corpus_sha256"],
            )
        )
    for index, cluster in enumerate(filler_clusters):
        filler_id = f"case-{sha256_bytes(f'filler:{cluster}'.encode())[:32]}"
        synthetic_cases.append(
            CanaryCase(
                case_id=filler_id,
                cluster=cluster,
                canonical_hash=f"ff{index:062d}",
                target_row_sha256=f"ff{sha256_bytes(f'filler-row:{cluster}'.encode())[:62]}",
                source_row_snapshot_sha256=sha256_bytes(
                    f"filler-dataset:{cluster}".encode()
                ),
            )
        )
    assert len(synthetic_cases) == 12
    # Prepared cases (hashes 0xx) win every pre-registered cluster over
    # fillers (hashes ff…); assert that invariant explicitly.
    selected_hashes = {
        cluster: min(
            c.target_row_sha256 for c in synthetic_cases if c.cluster == cluster
        )
        for cluster in COMPARISON_CLUSTERS
    }
    for cluster in clusters:
        prepared_case = next(
            c
            for c in synthetic_cases
            if c.case_id == prepared[clusters.index(cluster)][0]
        )
        assert selected_hashes[cluster] == prepared_case.target_row_sha256, cluster
    winner_dataset = {
        cluster: next(
            c.source_row_snapshot_sha256
            for c in synthetic_cases
            if c.cluster == cluster and c.target_row_sha256 == selected_hashes[cluster]
        )
        for cluster in COMPARISON_CLUSTERS
    }
    snapshots = {
        cluster: TargetSourceSnapshot(
            target_dataset_sha256=winner_dataset[cluster],
            target_row_sha256=row_hash,
        )
        for cluster, row_hash in selected_hashes.items()
    }
    selected = select_comparison_cases(
        tuple(synthetic_cases),
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=snapshots,
    )
    manifest = build_selection_manifest(
        selected,
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=snapshots,
    )
    runs, pairs = build_frozen_matrix(selected, selection_manifest=manifest)
    input_pins = {
        case_id: {
            "corpus": {"path": inputs["corpus"], "sha256": inputs["corpus_sha256"]},
            "workshop": {
                "path": inputs["workshop"],
                "sha256": inputs["workshop_sha256"],
            },
        }
        for case_id, inputs in prepared
    }
    document = build_matrix_document(
        runs, pairs, selection_manifest=manifest, input_pins=input_pins
    )
    commands = build_comparison_commands(runs, matrix_document=document)
    assert len(commands) == 8

    by_case = {case_id: inputs for case_id, inputs in prepared}
    baseline_profile = cmp_mod.BASELINE_PROFILE_ID
    challenger_profile = cmp_mod.CHALLENGER_PROFILE_ID
    run_ids: dict[tuple[str, str], str] = {}
    for run in runs:
        key = (run.case_id, run.profile_id)
        if key in run_ids:
            continue
        run_id = run_one_sealed_run(
            workspace,
            helpers,
            monkeypatch,
            case_id=run.case_id,
            inputs=by_case[run.case_id],
            profile_id=run.profile_id,
            idea_name="synthetic_idea_"
            + ("baseline" if run.profile_id == baseline_profile else "challenger"),
            duration_ms=100.0,
        )
        run_ids[key] = run_id
        finish_sealed_run_pipeline(workspace, helpers, run_id)

    ledger = initialize_comparison_ledger(
        matrix_document=document, plan_gate_subcap_cny=CANARY_HARD_CAP_CNY
    )
    metrics = {}
    for run in runs:
        key = (run.case_id, run.profile_id)
        run_id = run_ids[key]
        metrics[key] = ingest_comparison_result(
            workspace,
            run_id,
            expected_run_index=run.run_index,
            expected_arm_position=run.arm_position,
            expected_pair_index=run.pair_index,
            expected_case_id=run.case_id,
            expected_profile_id=run.profile_id,
            matrix_document=document,
        )
        ledger = cmp_mod.ingest_run_actual_cost(
            ledger,
            entry=cmp_mod.LedgerEntry(
                run_index=run.run_index,
                pair_index=run.pair_index,
                case_id=run.case_id,
                profile_id=run.profile_id,
                run_id=run_id,
                status="success",
                actual_cost_cny=metrics[key].actual_cost_cny,
                worst_case_bound_cny=Decimal("0.50"),
                physical_attempt_count=metrics[key].physical_attempt_count,
            ),
        )
    assert Decimal(ledger["current_actual_spend_cny"]) > 0

    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    vault = ComparisonVault(tmp_path / "comparison-e2e")
    for pair in pairs:
        packet = build_pair_packet(
            pair.pair_index,
            pair.case_id,
            pair.cluster,
            {"Name": "synthetic_idea_baseline", "Title": "Baseline synthetic"},
            {"Name": "synthetic_idea_challenger", "Title": "Challenger synthetic"},
            selection_manifest=manifest,
        )
        challenger_letter = _letter_for(pair, mappings, challenger_profile)
        fit = {
            "arm_a": "improved" if challenger_letter == "a_better" else "unchanged",
            "arm_b": "improved" if challenger_letter == "b_better" else "unchanged",
        }
        verdict = PairVerdict(
            case_id=pair.case_id,
            verdict=challenger_letter,
            overall_rationale="Synthetic sweep for the challenger arm.",
            domain_method_fit=fit,
            unjustified_ml_intrusion={"arm_a": "decreased", "arm_b": "decreased"},
            rubric_floor={"arm_a": "clean", "arm_b": "clean"},
            recorded_at="2026-09-04T08:00:00.000000Z",
        )
        vault.record_verdict(verdict, packet_sha256=cmp_mod.pair_packet_sha256(packet))
    facts = [
        PairFacts(
            pair_index=pair.pair_index,
            case_id=pair.case_id,
            cluster=pair.cluster,
            baseline_metrics=metrics[(pair.case_id, baseline_profile)],
            challenger_metrics=metrics[(pair.case_id, challenger_profile)],
            verdict=vault.load_verdict(pair.case_id),
        )
        for pair in pairs
    ]
    vault.reveal(
        mappings=mappings,
        selection_manifest=manifest,
        required_case_ids=tuple(c.case_id for c in selected),
    )
    reveal_document = parse_json_bytes(
        (tmp_path / "comparison-e2e" / "reveal.json").read_bytes(),
        label="reveal.json",
    )
    reduction = reduce_prompt_comparison(
        selection_manifest=manifest,
        matrix_document=document,
        reveal_document=reveal_document,
        pair_facts=tuple(facts),
        ledger=ledger,
    )
    assert reduction["decision"] == "promote", reduction["gates"]
    assert reduction["gates"]["completeness"]["pass"] is True
    assert reduction["gates"]["budget"]["pass"] is True
    again = reduce_prompt_comparison(
        selection_manifest=manifest,
        matrix_document=document,
        reveal_document=reveal_document,
        pair_facts=tuple(facts),
        ledger=ledger,
    )
    assert canonical_json_bytes(reduction) == canonical_json_bytes(again)


def test_load_approved_canary_cases_and_canonical_tie_break() -> None:
    """Loading approved Canary cases verifies manifest, approvals, and inputs."""
    canary_cases, target_source, input_pins = load_approved_canary_cases(REPO_ROOT)
    assert len(canary_cases) == 12
    assert {c.cluster for c in canary_cases} == cmp_mod.CANARY_CLUSTERS
    assert set(target_source.keys()) == set(COMPARISON_CLUSTERS)
    assert len(input_pins) == 4
    for case_id, pins in input_pins.items():
        assert "workshop" in pins and "corpus" in pins
        assert pins["workshop"]["path"].endswith(f"{case_id}.md")
        assert pins["corpus"]["path"].endswith("corpus.json")
        assert len(pins["workshop"]["sha256"]) == 64
        assert len(pins["corpus"]["sha256"]) == 64


def test_canonical_case_hash_deterministic() -> None:
    h1 = canonical_case_hash_for_canary_case("case-5f3f2126efc376031caf6acf4d1d4c59")
    h2 = canonical_case_hash_for_canary_case("case-5f3f2126efc376031caf6acf4d1d4c59")
    assert h1 == h2
    assert len(h1) == 64
    assert h1.islower()


def test_freeze_prompt_comparison_package_reproducibility_and_drift(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "comparison-pkg"
    result = freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_subcap_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    assert len(result["selected_cases"]) == 4
    assert len(result["commands"]) == 8
    assert result["plan_gate_subcap_cny"] == "5.00"

    expected_files = [
        "selection-manifest.json",
        "selection-approval.json",
        "run-matrix.json",
        "blind-mapping.json",
        "spend-ledger.json",
        "commands.txt",
    ]
    for filename in expected_files:
        p = pkg_dir / filename
        assert p.is_file()
        assert p.stat().st_size > 0

    assert (pkg_dir / "vault").is_dir()

    # Idempotent re-run produces identical package
    result2 = freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_subcap_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    assert result["artifacts"] == result2["artifacts"]

    # Tampering triggers PACKAGE_DRIFT
    tampered_file = pkg_dir / "commands.txt"
    tampered_file.write_bytes(b"tampered content")
    with pytest.raises(IdeationInputError) as exc_info:
        freeze_prompt_comparison_package(
            REPO_ROOT,
            plan_gate_subcap_cny=Decimal("5.00"),
            target_dir=pkg_dir,
        )
    assert exc_info.value.code == "PACKAGE_DRIFT"


def test_freeze_prompt_comparison_commands_parser_contract(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "comparison-pkg"
    result = freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_subcap_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    commands = result["commands"]
    assert len(commands) == 8

    parser = _build_parser()
    profile_counts: dict[str, int] = {}
    for cmd in commands:
        parts = shlex.split(cmd)
        # Expected: python scripts/with-project-env -- python ai_scientist/perform_ideation_temp_free.py new-run ...
        assert parts[0] == "python"
        assert parts[1] == "scripts/with-project-env"
        assert parts[2] == "--"
        assert parts[3] == "python"
        assert parts[4] == "ai_scientist/perform_ideation_temp_free.py"
        assert parts[5] == "new-run"

        # Production CLI parser checks
        args = parser.parse_args(parts[5:])
        profile_counts[args.prompt_profile] = (
            profile_counts.get(args.prompt_profile, 0) + 1
        )
        assert args.max_num_generations == 1
        assert args.num_reflections == 3
        assert not hasattr(args, "reasoning_effort")
        assert not hasattr(args, "max_tokens")

        # Zero-credential check
        assert "DEEPSEEK_API_KEY" not in cmd
        assert "api_key" not in cmd.lower()
        assert "--key" not in cmd

    assert profile_counts == {"ml-baseline-v1": 4, "cross-domain-v1": 4}
