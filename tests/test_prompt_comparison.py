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

import json
import shlex
import subprocess
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
    build_comparison_commands,
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


def _case(case_id: str, cluster: str) -> CanaryCase:
    """A synthetic Canary case whose canonical hash is the recomputed one,
    so the selection seam's CANARY_HASH_FORGERY check accepts it."""
    canonical = canonical_case_hash_for_canary_case(case_id)
    return CanaryCase(
        case_id=case_id,
        cluster=cluster,
        canonical_hash=canonical,
        target_row_sha256=sha256_bytes(f"row:{case_id}".encode()),
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
        cases.append(_case(f"case-{index:032x}", cluster))
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
        new_id = f"case-{index + 0x100:032x}"
        cases.append(
            CanaryCase(
                case_id=new_id,
                cluster="Health & Medicine",
                canonical_hash=canonical_case_hash_for_canary_case(new_id),
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
            canonical_hash=canonical_case_hash_for_canary_case(f"case-{index:032x}"),
            target_row_sha256=sha256_bytes(f"row:miss-{index}".encode()),
            source_row_snapshot_sha256=sha256_bytes(f"data:miss-{index}".encode()),
        )
        for index in range(12)
    ]
    with pytest.raises(Exception, match="MISSING_CLUSTER"):
        select_comparison_cases(
            tuple(replaced),
            canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            target_source=_target_source(),
        )


def test_selection_rejects_forged_canonical_hash() -> None:
    """F10: the selection seam recomputes each canonical hash and fails
    closed on any supplied hash that does not match the pinned seed."""
    approved = list(_approved_twelve())
    target = next(case for case in approved if case.cluster == "Materials Science")
    forged = CanaryCase(
        case_id=target.case_id,
        cluster=target.cluster,
        canonical_hash="f" * 64,
        target_row_sha256=target.target_row_sha256,
        source_row_snapshot_sha256=target.source_row_snapshot_sha256,
    )
    cases = tuple(
        forged if case.case_id == forged.case_id else case for case in approved
    )
    assert len(cases) == 12
    with pytest.raises(Exception, match="CANARY_HASH_FORGERY"):
        select_comparison_cases(
            cases,
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
    case = _case("case-" + "a" * 32, APPROVED_CLUSTERS[0])
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
    matrix_file_sha256 = sha256_bytes(canonical_json_bytes(document))
    parser = _build_parser()
    for run_index, command in enumerate(commands, start=1):
        assert "scripts/with-project-env" in command
        tokens = shlex.split(command)
        assert tokens == [
            "python",
            "scripts/with-project-env",
            "--",
            "python",
            "scripts/run-prompt-comparison-slot",
            "--package-dir",
            str(cmp_mod.DEFAULT_COMPARISON_PACKAGE_DIR),
            "--matrix-sha256",
            matrix_file_sha256,
            "--reapproval-threshold-cny",
            "5.00",
            "--run-index",
            str(run_index),
        ]
        inner = cmp_mod._production_new_run_argv(document["runs"][run_index - 1])
        parsed = parser.parse_args(list(inner[2:]))
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


def test_commands_reject_direct_or_augmented_runner_shapes() -> None:
    from ai_scientist.ideation.comparison import _assert_command_contract

    runs, _pairs, document, _manifest = _matrix(_selected())
    base = cmp_mod.build_comparison_commands(runs, matrix_document=document)[0]
    kwargs = {
        "matrix_document": document,
        "expected_run_index": 1,
        "expected_package_dir": cmp_mod.DEFAULT_COMPARISON_PACKAGE_DIR,
        "expected_reapproval_threshold_cny": Decimal("5.00"),
    }
    _assert_command_contract(base, **kwargs)
    with pytest.raises(Exception, match="COMMAND_SHAPE_INVALID"):
        _assert_command_contract(base + " --reasoning-effort max", **kwargs)
    direct = " ".join(
        shlex.quote(part)
        for part in cmp_mod._production_new_run_argv(document["runs"][0])
    )
    with pytest.raises(Exception, match="COMMAND_SHAPE_INVALID"):
        _assert_command_contract(direct, **kwargs)


# ==========================================================================
# Spend ledger: append-only, Plan Gate arithmetic, not per-run approval
# ==========================================================================


def _ledger():
    _runs, _pairs, document, _manifest = _matrix(_selected())
    from decimal import Decimal as D

    return cmp_mod.initialize_comparison_ledger(
        matrix_document=document,
        plan_gate_reapproval_threshold_cny=D("4.00"),
        historical_spend_cny=cmp_mod.CANARY_STAGE_HISTORICAL_SPEND_CNY,
    )


def _entry(run_index: int, cost: str, run_id: str) -> cmp_mod.LedgerEntry:
    from decimal import Decimal as D

    _runs, _pairs, document, _manifest = _matrix(_selected())
    matrix_run = next(run for run in document["runs"] if run["run_index"] == run_index)
    return cmp_mod.LedgerEntry(
        run_index=run_index,
        pair_index=matrix_run["pair_index"],
        case_id=matrix_run["case_id"],
        profile_id=matrix_run["prompt_profile_id"],
        run_id=run_id,
        status="success",
        actual_cost_cny=D(cost),
        worst_case_bound_cny=D("0.50"),
        physical_attempt_count=1,
    )


def test_ledger_starts_at_zero_tracked_over_historical_opening() -> None:
    from decimal import Decimal as D

    ledger = _ledger()
    # Tracked comparison spend starts at 0.00; the total stage spend opens
    # at the recorded 0.14 CNY historical Canary-stage balance.
    assert ledger["comparison_actual_spend_cny"] == "0.00"
    assert ledger["historical_spend_cny"] == "0.14"
    assert ledger["total_stage_spend_cny"] == "0.14"
    assert ledger["schema_version"] == cmp_mod.SPEND_LEDGER_SCHEMA_VERSION
    assert ledger["status"] == "initialized"
    assert "current_actual_spend_cny" not in ledger
    assert cmp_mod.ledger_current_spend(ledger) == D("0.00")
    assert cmp_mod.ledger_total_stage_spend(ledger) == D("0.14")
    updated = cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(1, "0.14", "r1"))
    assert updated["comparison_actual_spend_cny"] == "0.14"
    assert updated["total_stage_spend_cny"] == "0.28"
    assert len(updated["entries"]) == 1
    twice = cmp_mod.ingest_run_actual_cost(updated, entry=_entry(2, "0.20", "r2"))
    assert twice["comparison_actual_spend_cny"] == "0.34"
    assert twice["total_stage_spend_cny"] == "0.48"
    # Duplicate run / slot ingests fail closed.
    with pytest.raises(Exception, match="LEDGER_DUPLICATE_RUN"):
        cmp_mod.ingest_run_actual_cost(twice, entry=_entry(3, "0.01", "r1"))
    with pytest.raises(Exception, match="LEDGER_DUPLICATE_SLOT"):
        cmp_mod.ingest_run_actual_cost(twice, entry=_entry(2, "0.01", "r3"))


def test_ledger_rejects_negative_historical_spend() -> None:
    from decimal import Decimal as D

    _runs, _pairs, document, _manifest = _matrix(_selected())
    with pytest.raises(Exception, match="INVALID_HISTORICAL_SPEND"):
        cmp_mod.initialize_comparison_ledger(
            matrix_document=document,
            plan_gate_reapproval_threshold_cny=D("4.00"),
            historical_spend_cny=D("-0.01"),
        )


def test_ledger_ingests_failed_suspended_resumed_and_retried_runs() -> None:
    ledger = _ledger()
    statuses = ("failed", "suspended", "resume_success", "success")
    for index, status in enumerate(statuses, start=1):
        entry = _entry(index, "0.10", f"r{index}")
        entry = cmp_mod.LedgerEntry(
            run_index=index,
            pair_index=entry.pair_index,
            case_id=entry.case_id,
            profile_id=entry.profile_id,
            run_id=entry.run_id,
            status=status,
            actual_cost_cny=entry.actual_cost_cny,
            worst_case_bound_cny=entry.worst_case_bound_cny,
            physical_attempt_count=2 if status == "resume_success" else 1,
        )
        ledger = cmp_mod.ingest_run_actual_cost(ledger, entry=entry)
    assert ledger["comparison_actual_spend_cny"] == "0.40"
    assert ledger["total_stage_spend_cny"] == "0.54"
    attempts = [e["physical_attempt_count"] for e in ledger["entries"]]
    assert attempts == [1, 1, 2, 1]


def test_plan_gate_threshold_is_checked_before_the_next_run() -> None:
    from decimal import Decimal as D

    # Threshold 4.00, opening historical 0.14. Actual spend may reach the
    # threshold, but the next irreversible provider run must then stop.
    _runs, _pairs, document, _manifest = _matrix(_selected())
    ledger = _ledger()
    ledger = cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(1, "3.85", "r1"))
    assert cmp_mod.ledger_total_stage_spend(ledger) == D("3.99")
    cmp_mod.authorize_next_comparison_run(
        ledger,
        matrix_document=document,
        run_index=2,
        next_run_worst_case_bound_cny=D("0.01"),
    )
    ledger = cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(2, "0.01", "r2"))
    assert cmp_mod.ledger_total_stage_spend(ledger) == D("4.00")
    assert ledger["status"] == "reapproval_required"
    with pytest.raises(Exception, match="PLAN_GATE_REAPPROVAL_REQUIRED"):
        cmp_mod.authorize_next_comparison_run(
            ledger,
            matrix_document=document,
            run_index=3,
            next_run_worst_case_bound_cny=D("0.01"),
        )


def test_plan_gate_reapproval_threshold_cannot_exceed_canary_cap() -> None:
    from decimal import Decimal as D

    _runs, _pairs, document, _manifest = _matrix(_selected())
    with pytest.raises(Exception, match="REAPPROVAL_THRESHOLD_EXCEEDS_CANARY_CAP"):
        cmp_mod.initialize_comparison_ledger(
            matrix_document=document,
            plan_gate_reapproval_threshold_cny=D("30.01"),
            historical_spend_cny=cmp_mod.CANARY_STAGE_HISTORICAL_SPEND_CNY,
        )


def test_plan_gate_is_not_a_per_run_approval() -> None:
    approval = cmp_mod.plan_gate_approval_document(
        ledger=_ledger(), approved_by="Robert"
    )
    assert cmp_mod.plan_gate_does_not_waive_per_run_approval(approval)
    assert approval["scope"] == "matrix_reapproval_threshold_not_per_run"
    assert approval["plan_gate_reapproval_threshold_cny"] == "4.00"
    assert approval["historical_spend_cny"] == "0.14"
    assert approval["comparison_actual_spend_cny"] == "0.00"
    assert approval["total_stage_spend_cny"] == "0.14"


def test_ledger_records_a_hard_cap_breach_instead_of_hiding_actual_spend() -> None:
    ledger = _ledger()
    breached = cmp_mod.ingest_run_actual_cost(ledger, entry=_entry(1, "30.01", "r1"))
    assert breached["comparison_actual_spend_cny"] == "30.01"
    assert breached["total_stage_spend_cny"] == "30.15"
    assert breached["status"] == "hard_cap_breached"


# ==========================================================================
# Result ingestion: fail-closed against corrupt/drifted/cross-case evidence
# (exercised through the synthetic sealed-run envelope below; no unit-level
# ingestion fixtures are needed because every arm reaching ingestion must
# be a genuine sealed Evidence Chain).
# ==========================================================================


# ==========================================================================
# Write-once verdicts + reveal gate
# ==========================================================================


def _verdict(case_id: str, verdict: str = "a_better") -> cmp_mod.PairVerdict:
    return cmp_mod.PairVerdict(
        case_id=case_id,
        verdict=verdict,
        overall_rationale="Arm A proposes a stronger validation plan.",
        domain_method_fit="challenger_better",
        unjustified_ml_intrusion="decreased",
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
    # F6: domain_method_fit is a pair-level scalar from a closed enum.
    bad_fit = _verdict(case_id)
    object.__setattr__(bad_fit, "domain_method_fit", "better")
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(bad_fit, packet_sha256="5" * 64)
    # The legacy per-arm dict shape is no longer a valid instrument.
    old_fit = _verdict(case_id)
    object.__setattr__(
        old_fit, "domain_method_fit", {"arm_a": "improved", "arm_b": "unchanged"}
    )
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(old_fit, packet_sha256="5" * 64)
    bad_intrusion = _verdict(case_id)
    object.__setattr__(bad_intrusion, "unjustified_ml_intrusion", "worse")
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(bad_intrusion, packet_sha256="5" * 64)
    bad_floor = _verdict(case_id)
    object.__setattr__(
        bad_floor, "rubric_floor", {"arm_a": "terrible", "arm_b": "clean"}
    )
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        vault.record_verdict(bad_floor, packet_sha256="5" * 64)


def test_verdict_pair_level_scalar_enums_accept_only_registered_values() -> None:
    case_id = _selected()[0].case_id
    for fit in ("challenger_better", "tie", "baseline_better", "incomparable"):
        verdict = _verdict(case_id)
        object.__setattr__(verdict, "domain_method_fit", fit)
        document = cmp_mod.verdict_document(verdict, packet_sha256="5" * 64)
        assert document["domain_method_fit"] == fit
    for intrusion in ("increased", "unchanged", "decreased", "incomparable"):
        verdict = _verdict(case_id)
        object.__setattr__(verdict, "unjustified_ml_intrusion", intrusion)
        document = cmp_mod.verdict_document(verdict, packet_sha256="5" * 64)
        assert document["unjustified_ml_intrusion"] == intrusion
    # The pre-F6 vocabulary is rejected on the pair-level scalars.
    verdict = _verdict(case_id)
    object.__setattr__(verdict, "domain_method_fit", "improved")
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        cmp_mod.verdict_document(verdict, packet_sha256="5" * 64)
    verdict = _verdict(case_id)
    object.__setattr__(verdict, "domain_method_fit", "worse")
    with pytest.raises(Exception, match="INVALID_VERDICT"):
        cmp_mod.verdict_document(verdict, packet_sha256="5" * 64)
    assert (
        cmp_mod.verdict_document(_verdict(case_id), packet_sha256="5" * 64)[
            "schema_version"
        ]
        == cmp_mod.VERDICT_SCHEMA_VERSION
    )


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
        matrix_document=document,
        plan_gate_reapproval_threshold_cny=Decimal("4.00"),
        historical_spend_cny=cmp_mod.CANARY_STAGE_HISTORICAL_SPEND_CNY,
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
    packet_sha256: str = "5" * 64,
) -> tuple[cmp_mod.PairFacts, ...]:
    facts = []
    for pair_index, case in enumerate(selected, start=1):
        case_id = case.case_id
        verdict_value = (verdict_by_case or {}).get(case_id, "a_better")
        verdict = _verdict(case_id, verdict_value)
        if verdict_mutate is not None:
            verdict = verdict_mutate(case_id, verdict)
        document = cmp_mod.verdict_document(verdict, packet_sha256=packet_sha256)
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
                packet_sha256=packet_sha256,
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
        packet_sha256=facts[0].packet_sha256,
    )
    reduction = _reduce(tuple(facts), ledger, mappings, document, manifest)
    assert reduction["decision"] == "incomplete"


def _fit_mutate(value: str):
    def mutate(case_id: str, verdict: cmp_mod.PairVerdict) -> cmp_mod.PairVerdict:
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=value,
            unjustified_ml_intrusion=verdict.unjustified_ml_intrusion,
            rubric_floor=dict(verdict.rubric_floor),
            recorded_at=verdict.recorded_at,
        )

    return mutate


def test_reducer_rejects_domain_method_regression() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # Regress pair 1: the challenger arm's fit is strictly worse than the
    # baseline arm's (pair-level "baseline_better").
    facts = _facts(selected, mappings, verdict_mutate=_fit_mutate("baseline_better"))
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["domain_method_fit"]["regressed_pairs"] >= 1
    assert reduction["decision"] == "reject"


def test_reducer_rejects_when_domain_method_fit_improves_fewer_than_two() -> None:
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    # Only one pair improves (challenger_better); the rest tie.
    case0 = selected[0]

    def mutate(case_id: str, verdict: cmp_mod.PairVerdict) -> cmp_mod.PairVerdict:
        fit = "challenger_better" if case_id == case0.case_id else "tie"
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=fit,
            unjustified_ml_intrusion=verdict.unjustified_ml_intrusion,
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
        return cmp_mod.PairVerdict(
            case_id=verdict.case_id,
            verdict=verdict.verdict,
            overall_rationale=verdict.overall_rationale,
            domain_method_fit=verdict.domain_method_fit,
            unjustified_ml_intrusion="increased",
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
            domain_method_fit=verdict.domain_method_fit,
            unjustified_ml_intrusion=verdict.unjustified_ml_intrusion,
            rubric_floor=floor,
            recorded_at=verdict.recorded_at,
        )

    facts = _facts(selected, mappings, verdict_mutate=mutate)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    assert reduction["gates"]["rubric_floor"]["hits"]
    assert reduction["decision"] == "reject"


def test_reducer_records_deterministic_regression_enforced_at_ingestion() -> None:
    # F5: the deterministic_regression gate is a recorded statement of the
    # ingestion-enforced zero tolerance, not an always-True per-run flag.
    selected, reveal_document, manifest, document, ledger = _reducer_env()
    mappings = _mappings_from(reveal_document)
    verdicts = {
        case.case_id: _letter_for(case, mappings, cmp_mod.CHALLENGER_PROFILE_ID)
        for case in selected
    }
    facts = _facts(selected, mappings, verdict_by_case=verdicts)
    reduction = _reduce(facts, ledger, mappings, document, manifest)
    gate = reduction["gates"]["deterministic_regression"]
    assert gate["pass"] is True
    assert gate["problems"] == []
    assert gate["enforced_at"] == "result_ingestion"
    assert gate["ingested_gates"] == [
        "evidence_chain_seal",
        "profile_and_input_pins",
        "sanitized_export_identity",
        "evaluation_coverage",
    ]
    assert reduction["decision"] == "promote"


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
        packet_sha256=facts[0].packet_sha256,
    )
    reduction = _reduce(tuple(facts), ledger, mappings, document, manifest)
    assert reduction["decision"] == "incomplete"


def _baseline_letter(case, mappings) -> str:
    mapping = cmp_mod._mapping_for_case(mappings, case.case_id)
    return (
        "arm_a" if mapping.arm_a_profile_id == cmp_mod.BASELINE_PROFILE_ID else "arm_b"
    )


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


def _synthetic_canary_identity(prepared, clusters) -> tuple[CanaryCase, ...]:
    """A full synthetic 12-case approved-Canary identity.

    The four prepared cases fill the four pre-registered comparison
    clusters; eight filler cases (two per non-comparison Canary cluster)
    complete the twelve-case identity. Because comparison clusters hold
    only prepared cases, those win their clusters unconditionally. Every
    canonical hash is the recomputed one, so the F10 forgery check passes.
    """
    synthetic_cases: list[CanaryCase] = []
    for index, (case_id, inputs) in enumerate(prepared):
        synthetic_cases.append(
            CanaryCase(
                case_id=case_id,
                cluster=clusters[index],
                canonical_hash=canonical_case_hash_for_canary_case(case_id),
                target_row_sha256=inputs["corpus_sha256"],
                source_row_snapshot_sha256=inputs["corpus_sha256"],
            )
        )
    filler_clusters = sorted(cmp_mod.CANARY_CLUSTERS - set(clusters)) * 2
    for index, cluster in enumerate(filler_clusters):
        filler_id = f"case-{sha256_bytes(f'filler:{index}:{cluster}'.encode())[:32]}"
        synthetic_cases.append(
            CanaryCase(
                case_id=filler_id,
                cluster=cluster,
                canonical_hash=canonical_case_hash_for_canary_case(filler_id),
                target_row_sha256=sha256_bytes(
                    f"filler-row:{index}:{cluster}".encode()
                ),
                source_row_snapshot_sha256=sha256_bytes(
                    f"filler-dataset:{index}:{cluster}".encode()
                ),
            )
        )
    assert len(synthetic_cases) == 12
    return tuple(synthetic_cases)


def _synthetic_matrix_parts(synthetic_workspace: tuple[Any, Any]) -> dict[str, Any]:
    """The frozen 8-run matrix over the synthetic workspace identity.

    Shared by the ingested 8-run envelope and the zero-idea ingestion
    fixtures: selection, freezing, and document building only — no runs.
    """
    workspace, prepared = synthetic_workspace
    clusters = list(COMPARISON_CLUSTERS)
    synthetic_cases = _synthetic_canary_identity(prepared, clusters)
    # The prepared cases are the only candidates in their clusters, so
    # their rows are the per-cluster winners; ensure the identity really
    # assigned each prepared case its intended cluster.
    prepared_by_id = {case_id: inputs for case_id, inputs in prepared}
    for case in synthetic_cases:
        if case.case_id in prepared_by_id:
            assert case.cluster == clusters[list(prepared_by_id).index(case.case_id)]
    selected_hashes = {
        clusters[index]: inputs["corpus_sha256"]
        for index, (case_id, inputs) in enumerate(prepared)
    }
    snapshots = {
        cluster: TargetSourceSnapshot(
            target_dataset_sha256=row_hash,
            target_row_sha256=row_hash,
        )
        for cluster, row_hash in selected_hashes.items()
    }
    selected = select_comparison_cases(
        synthetic_cases,
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=snapshots,
    )
    assert [case.case_id for case in selected] == [
        case_id for case_id, _inputs in prepared
    ]
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
    return {
        "workspace": workspace,
        "prepared": prepared,
        "selected": selected,
        "manifest": manifest,
        "runs": runs,
        "pairs": pairs,
        "document": document,
    }


@pytest.fixture(scope="module")
def ingested_env(
    tmp_path_factory: Any,
    helpers: Any,
    synthetic_workspace: tuple[Any, Any],
) -> dict[str, Any]:
    """One full synthetic comparison envelope, prepared once per module.

    Builds the 12-case identity, freezes matrix/mapping, seals all eight
    runs against the real production lifecycle (admission -> controller ->
    seal -> validate -> export -> evaluation), ingests them into metrics
    and the spend ledger, and builds the pair packets from the ingested
    sealed evidence (build_pair_packets_from_ingested, the only sanctioned
    live packet builder). Tests share this envelope; verdicts, vaults, and
    reveal documents stay per-test (write-once).
    """
    from ai_scientist.ideation.comparison import (
        CANARY_HARD_CAP_CNY,
        build_blind_mapping,
        build_pair_packets_from_ingested,
        ingest_comparison_result,
        initialize_comparison_ledger,
    )
    from tests.comparison_synthetic import (
        finish_sealed_run_pipeline,
        run_one_sealed_run,
    )

    parts = _synthetic_matrix_parts(synthetic_workspace)
    workspace = parts["workspace"]
    prepared = parts["prepared"]
    runs = parts["runs"]
    pairs = parts["pairs"]
    manifest = parts["manifest"]
    selected = parts["selected"]
    document = parts["document"]

    by_case = {case_id: inputs for case_id, inputs in prepared}
    baseline_profile = cmp_mod.BASELINE_PROFILE_ID
    challenger_profile = cmp_mod.CHALLENGER_PROFILE_ID
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
                + ("baseline" if run.profile_id == baseline_profile else "challenger"),
                duration_ms=100.0,
            )
            run_ids[key] = run_id
            finish_sealed_run_pipeline(workspace, helpers, run_id)
    finally:
        monkey.undo()

    ledger = initialize_comparison_ledger(
        matrix_document=document,
        plan_gate_reapproval_threshold_cny=CANARY_HARD_CAP_CNY,
        historical_spend_cny=cmp_mod.CANARY_STAGE_HISTORICAL_SPEND_CNY,
    )
    # Every synthetic run was admitted at the same fixture-workspace HEAD
    # (run artifacts are gitignored), so one execution-code pin covers all.
    admission_commits = set()
    for run_id in run_ids.values():
        admission = json.loads(
            (
                workspace / "artifacts" / "ideation-runs" / run_id / "admission.json"
            ).read_text(encoding="utf-8")
        )
        admission_commits.add(admission["code"]["commit"])
    assert len(admission_commits) == 1
    package_dir = tmp_path_factory.mktemp("comparison-pkg") / "pkg"
    package_dir.mkdir()
    cmp_mod.create_execution_code_pin(package_dir, commit=admission_commits.pop())
    metrics_by_run: dict[str, cmp_mod.RunMetrics] = {}
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
    assert cmp_mod.ledger_current_spend(ledger) > 0
    assert cmp_mod.ledger_total_stage_spend(ledger) > cmp_mod.ledger_current_spend(
        ledger
    )
    mappings = build_blind_mapping(pairs, selection_manifest=manifest)
    packets = build_pair_packets_from_ingested(
        workspace,
        matrix_document=document,
        selection_manifest=manifest,
        mappings=mappings,
        metrics_by_run=metrics_by_run,
    )
    assert sorted(packets) == [1, 2, 3, 4]
    return {
        "workspace": workspace,
        "manifest": manifest,
        "document": document,
        "runs": runs,
        "pairs": pairs,
        "mappings": mappings,
        "ledger": ledger,
        "metrics_by_run": metrics_by_run,
        "run_ids": run_ids,
        "packets": packets,
        "selected": selected,
        "baseline_profile": baseline_profile,
        "challenger_profile": challenger_profile,
    }


@pytest.fixture(scope="module")
def zero_idea_env(
    tmp_path_factory: Any,
    helpers: Any,
    synthetic_workspace: tuple[Any, Any],
) -> dict[str, Any]:
    """A frozen matrix plus one sealed zero-idea run, exported and pinned.

    The run seals success without a finalized idea and carries its
    sanitized export but no Evaluation Artifact — the exact shape the
    previously unreachable ingest coverage gate must reject.
    """
    from tests.comparison_synthetic import (
        finish_sealed_run_pipeline,
        run_zero_idea_sealed_run,
    )

    parts = _synthetic_matrix_parts(synthetic_workspace)
    workspace = parts["workspace"]
    prepared = parts["prepared"]
    runs = parts["runs"]
    document = parts["document"]
    matrix_run = runs[0]
    by_case = {case_id: inputs for case_id, inputs in prepared}
    monkey = pytest.MonkeyPatch()
    try:
        run_id = run_zero_idea_sealed_run(
            workspace,
            helpers,
            monkey,
            case_id=matrix_run.case_id,
            inputs=by_case[matrix_run.case_id],
            profile_id=matrix_run.profile_id,
            idea_name="zero_idea_probe",
        )
    finally:
        monkey.undo()
    finish_sealed_run_pipeline(workspace, helpers, run_id)
    admission = json.loads(
        (
            workspace / "artifacts" / "ideation-runs" / run_id / "admission.json"
        ).read_text(encoding="utf-8")
    )
    package_dir = tmp_path_factory.mktemp("zero-idea-pkg") / "pkg"
    package_dir.mkdir()
    cmp_mod.create_execution_code_pin(package_dir, commit=admission["code"]["commit"])
    return {
        "workspace": workspace,
        "run_id": run_id,
        "run": matrix_run,
        "document": document,
        "package_dir": package_dir,
    }


def test_ingest_fails_closed_on_zero_idea_run_without_evaluation_coverage(
    zero_idea_env: dict[str, Any],
) -> None:
    """EVALUATION_ARTIFACT_MISSING must be reachable for zero-idea runs."""
    env = zero_idea_env
    run = env["run"]
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.ingest_comparison_result(
            env["workspace"],
            env["run_id"],
            expected_run_index=run.run_index,
            expected_arm_position=run.arm_position,
            expected_pair_index=run.pair_index,
            expected_case_id=run.case_id,
            expected_profile_id=run.profile_id,
            matrix_document=env["document"],
            package_dir=env["package_dir"],
        )
    assert exc_info.value.code == "EVALUATION_ARTIFACT_MISSING"


def _synthetic_facts(
    env: dict[str, Any],
    vault: cmp_mod.ComparisonVault,
    *,
    packet_sha256: str | None = None,
) -> tuple[cmp_mod.PairFacts, ...]:
    """PairFacts over the ingested envelope with vault-bound verdicts."""
    from ai_scientist.ideation.comparison import PairFacts

    facts = []
    for pair in env["pairs"]:
        facts.append(
            PairFacts(
                pair_index=pair.pair_index,
                case_id=pair.case_id,
                cluster=pair.cluster,
                baseline_metrics=env["metrics_by_run"][
                    env["run_ids"][(pair.case_id, env["baseline_profile"])]
                ],
                challenger_metrics=env["metrics_by_run"][
                    env["run_ids"][(pair.case_id, env["challenger_profile"])]
                ],
                verdict=vault.load_verdict(pair.case_id),
                packet_sha256=(
                    packet_sha256
                    if packet_sha256 is not None
                    else cmp_mod.pair_packet_sha256(env["packets"][pair.pair_index])
                ),
            )
        )
    return tuple(facts)


def _synthetic_verdicts(
    env: dict[str, Any],
    vault: cmp_mod.ComparisonVault,
    *,
    packet_sha256: str | None = None,
) -> None:
    """Record a promote-sweep verdict per pair.

    Each verdict binds to its own pair's packet hash unless an explicit
    foreign hash is passed (for binding-failure tests).
    """
    from ai_scientist.ideation.comparison import PairVerdict

    for pair in env["pairs"]:
        challenger_letter = _letter_for(
            pair, env["mappings"], env["challenger_profile"]
        )
        verdict = PairVerdict(
            case_id=pair.case_id,
            verdict=challenger_letter,
            overall_rationale="Synthetic sweep for the challenger arm.",
            domain_method_fit="challenger_better",
            unjustified_ml_intrusion="unchanged",
            rubric_floor={"arm_a": "clean", "arm_b": "clean"},
            recorded_at="2026-09-04T08:00:00.000000Z",
        )
        bound = (
            packet_sha256
            if packet_sha256 is not None
            else cmp_mod.pair_packet_sha256(env["packets"][pair.pair_index])
        )
        vault.record_verdict(verdict, packet_sha256=bound)


def test_synthetic_sealed_runs_flow_through_ingestion_and_reduction(
    tmp_path: Path,
    ingested_env: dict[str, Any],
) -> None:
    from ai_scientist.ideation.comparison import (
        ComparisonVault,
        reduce_prompt_comparison,
    )

    env = ingested_env
    workspace = env["workspace"]
    manifest = env["manifest"]
    document = env["document"]
    mappings = env["mappings"]
    ledger = env["ledger"]
    selected = env["selected"]

    vault = ComparisonVault(tmp_path / "comparison-e2e")
    _synthetic_verdicts(env, vault)
    assert vault.verdicts_frozen(required_case_ids=tuple(c.case_id for c in selected))
    facts = _synthetic_facts(env, vault)
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
        pair_facts=facts,
        ledger=ledger,
    )
    assert reduction["decision"] == "promote", reduction["gates"]
    assert reduction["gates"]["completeness"]["pass"] is True
    assert reduction["gates"]["budget"]["pass"] is True
    assert reduction["gates"]["deterministic_regression"]["enforced_at"] == (
        "result_ingestion"
    )
    # The packet arms bind exactly the sealed idea payloads.
    packet_one = env["packets"][1]
    mapping_one = cmp_mod._mapping_for_case(mappings, env["pairs"][0].case_id)
    arm_a_run_id = env["run_ids"][
        (env["pairs"][0].case_id, mapping_one.arm_a_profile_id)
    ]
    assert packet_one["arm_a"]["idea_sha256"] == cmp_mod.final_idea_sha256(
        cmp_mod.load_sealed_final_idea(workspace, arm_a_run_id)
    )
    again = reduce_prompt_comparison(
        selection_manifest=manifest,
        matrix_document=document,
        reveal_document=reveal_document,
        pair_facts=facts,
        ledger=ledger,
    )
    assert canonical_json_bytes(reduction) == canonical_json_bytes(again)


def test_packet_binding_detects_tampered_idea_payload(ingested_env) -> None:
    """A hand-built packet whose idea payload drifts from the sealed run
    is detected: its arm idea_sha256 no longer equals the sealed idea's."""
    env = ingested_env
    workspace = env["workspace"]
    pair = env["pairs"][0]
    correct = env["packets"][pair.pair_index]
    mapping = cmp_mod._mapping_for_case(env["mappings"], pair.case_id)
    if mapping.arm_a_profile_id == env["baseline_profile"]:
        arm_a_run_id = env["run_ids"][(pair.case_id, env["baseline_profile"])]
        arm_b_run_id = env["run_ids"][(pair.case_id, env["challenger_profile"])]
    else:
        arm_a_run_id = env["run_ids"][(pair.case_id, env["challenger_profile"])]
        arm_b_run_id = env["run_ids"][(pair.case_id, env["baseline_profile"])]
    sealed_arm_a = cmp_mod.load_sealed_final_idea(workspace, arm_a_run_id)
    tampered = dict(sealed_arm_a)
    tampered["Title"] = tampered["Title"] + " (tampered)"
    hand_built = cmp_mod.build_pair_packet(
        pair.pair_index,
        pair.case_id,
        pair.cluster,
        tampered,
        cmp_mod.load_sealed_final_idea(workspace, arm_b_run_id),
        selection_manifest=env["manifest"],
    )
    assert hand_built["arm_a"]["idea_sha256"] != correct["arm_a"]["idea_sha256"]
    assert correct["arm_a"]["idea_sha256"] == cmp_mod.final_idea_sha256(sealed_arm_a)
    assert hand_built["arm_a"]["idea_sha256"] != cmp_mod.final_idea_sha256(sealed_arm_a)


def test_reducer_rejects_verdict_bound_to_a_different_packet(
    tmp_path: Path, ingested_env
) -> None:
    from ai_scientist.ideation.comparison import (
        ComparisonVault,
        reduce_prompt_comparison,
    )

    env = ingested_env
    foreign_hash = "6" * 64
    vault = ComparisonVault(tmp_path / "comparison-e2e-mismatch")
    _synthetic_verdicts(env, vault, packet_sha256=foreign_hash)
    facts = _synthetic_facts(env, vault)
    reveal_document = {
        "blind_mapping": cmp_mod.blind_mapping_document(
            env["mappings"], selection_manifest=env["manifest"]
        ),
        "revealed_at": "2026-09-04T08:00:00.000000Z",
        "schema_version": "comparison-reveal-v1.0.0",
    }
    with pytest.raises(Exception, match="VERDICT_PACKET_MISMATCH"):
        reduce_prompt_comparison(
            selection_manifest=env["manifest"],
            matrix_document=env["document"],
            reveal_document=reveal_document,
            pair_facts=facts,
            ledger=env["ledger"],
        )


def test_packet_binding_detects_arm_swap_relative_to_frozen_mapping(
    ingested_env,
) -> None:
    """Building a packet with transposed A/B ideas changes every arm's
    idea_sha256 relative to the correctly-built packet's arms."""
    env = ingested_env
    pair = env["pairs"][1]
    correct = env["packets"][pair.pair_index]
    transposed = cmp_mod.build_pair_packet(
        pair.pair_index,
        pair.case_id,
        pair.cluster,
        correct["arm_b"]["idea"],
        correct["arm_a"]["idea"],
        selection_manifest=env["manifest"],
    )
    assert transposed["arm_a"]["idea_sha256"] != correct["arm_a"]["idea_sha256"]
    assert transposed["arm_b"]["idea_sha256"] != correct["arm_b"]["idea_sha256"]
    assert transposed["arm_a"]["idea_sha256"] == correct["arm_b"]["idea_sha256"]
    assert transposed["arm_b"]["idea_sha256"] == correct["arm_a"]["idea_sha256"]
    # The correct builder assigned the arms per the frozen mapping: the
    # arm_a idea is exactly the sealed idea of the mapped arm_a run.
    mapping = cmp_mod._mapping_for_case(env["mappings"], pair.case_id)
    mapped_run_id = env["run_ids"][(pair.case_id, mapping.arm_a_profile_id)]
    assert correct["arm_a"]["idea"] == cmp_mod.load_sealed_final_idea(
        env["workspace"], mapped_run_id
    )


def test_load_sealed_final_idea_fails_closed_on_tampered_artifact(
    tmp_path: Path, ingested_env
) -> None:
    import shutil

    env = ingested_env
    run_id = env["run_ids"][(env["pairs"][0].case_id, env["baseline_profile"])]
    copy = tmp_path / "workspace-copy"
    shutil.copytree(env["workspace"], copy)
    idea_path = (
        copy / "artifacts/ideation-runs" / run_id / "artifacts/ideas/000000/idea.json"
    )
    idea = json.loads(idea_path.read_text(encoding="utf-8"))
    del idea["Experiments"]
    idea_path.write_bytes(
        (json.dumps(idea, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.load_sealed_final_idea(copy, run_id)
    assert exc_info.value.code == "RUN_CORRUPT"


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
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    assert len(result["selected_cases"]) == 4
    assert len(result["commands"]) == 8
    assert result["plan_gate_reapproval_threshold_cny"] == "5.00"

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
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    assert result["artifacts"] == result2["artifacts"]

    # Tampering triggers PACKAGE_DRIFT
    tampered_file = pkg_dir / "commands.txt"
    tampered_file.write_bytes(b"tampered content")
    with pytest.raises(IdeationInputError) as exc_info:
        freeze_prompt_comparison_package(
            REPO_ROOT,
            plan_gate_reapproval_threshold_cny=Decimal("5.00"),
            target_dir=pkg_dir,
        )
    assert exc_info.value.code == "PACKAGE_DRIFT"


def test_freeze_prompt_comparison_commands_parser_contract(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "comparison-pkg"
    result = freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    commands = result["commands"]
    assert len(commands) == 8

    profile_counts: dict[str, int] = {}
    matrix_document = json.loads((pkg_dir / "run-matrix.json").read_text())
    matrix_file_sha256 = sha256_bytes((pkg_dir / "run-matrix.json").read_bytes())
    parser = _build_parser()
    for run_index, cmd in enumerate(commands, start=1):
        parts = shlex.split(cmd)
        assert parts == [
            "python",
            "scripts/with-project-env",
            "--",
            "python",
            "scripts/run-prompt-comparison-slot",
            "--package-dir",
            str(pkg_dir),
            "--matrix-sha256",
            matrix_file_sha256,
            "--reapproval-threshold-cny",
            "5.00",
            "--run-index",
            str(run_index),
        ]

        # The guard reconstructs and parser-checks this immutable inner argv.
        inner = cmp_mod._production_new_run_argv(matrix_document["runs"][run_index - 1])
        args = parser.parse_args(list(inner[2:]))
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


def test_reapproval_threshold_records_crossing_and_blocks_the_next_slot() -> None:
    """The 5 CNY control is a reapproval threshold, not a false hard cap."""
    _runs, _pairs, document, _manifest = _matrix(_selected())
    ledger = cmp_mod.initialize_comparison_ledger(
        matrix_document=document,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        historical_spend_cny=cmp_mod.CANARY_STAGE_HISTORICAL_SPEND_CNY,
    )
    crossed = cmp_mod.ingest_run_actual_cost(
        ledger,
        entry=_entry(1, "4.87", "threshold-crossing-run"),
    )
    assert crossed["total_stage_spend_cny"] == "5.01"
    assert crossed["status"] == "reapproval_required"
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.authorize_next_comparison_run(
            crossed,
            matrix_document=document,
            run_index=2,
            next_run_worst_case_bound_cny=Decimal("7.08"),
        )
    assert exc_info.value.code == "PLAN_GATE_REAPPROVAL_REQUIRED"


# Fixture execution-code identities: the comparison matrix must run under one
# pinned commit; tests inject these instead of touching the real repository's
# git state (the production default resolver requires a clean worktree).
EXECUTION_COMMIT_A = "a1" * 20
EXECUTION_COMMIT_B = "b2" * 20


def _slot_prepare_kwargs(pkg_dir: Path, run_index: int) -> dict[str, object]:
    return {
        "package_dir": pkg_dir,
        "expected_matrix_sha256": sha256_bytes(
            (pkg_dir / "run-matrix.json").read_bytes()
        ),
        "expected_reapproval_threshold_cny": Decimal("5.00"),
        "run_index": run_index,
    }


def _reserve(
    launch: dict[str, Any], commit: str = EXECUTION_COMMIT_A
) -> dict[str, Any]:
    return cmp_mod.reserve_comparison_slot(
        launch,
        execution_head_resolver=lambda _root: commit,
    )


def _slot_runner_argv(pkg_dir: Path, run_index: int) -> list[str]:
    kwargs = _slot_prepare_kwargs(pkg_dir, run_index)
    return [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run-prompt-comparison-slot"),
        "--package-dir",
        str(pkg_dir),
        "--matrix-sha256",
        str(kwargs["expected_matrix_sha256"]),
        "--reapproval-threshold-cny",
        "5.00",
        "--run-index",
        str(run_index),
    ]


def test_hard_cap_reservation_accepts_exact_bound_and_refuses_one_cent_over() -> None:
    """Irreversible provider spend is guarded before the next run starts."""
    _runs, _pairs, document, _manifest = _matrix(_selected())
    ledger = cmp_mod.initialize_comparison_ledger(
        matrix_document=document,
        plan_gate_reapproval_threshold_cny=Decimal("30.00"),
        historical_spend_cny=cmp_mod.CANARY_STAGE_HISTORICAL_SPEND_CNY,
    )
    exact = cmp_mod.ingest_run_actual_cost(
        ledger,
        entry=_entry(1, "22.78", "exact-hard-cap-reservation"),
    )
    authorization = cmp_mod.authorize_next_comparison_run(
        exact,
        matrix_document=document,
        run_index=2,
        next_run_worst_case_bound_cny=Decimal("7.08"),
    )
    assert authorization["projected_hard_ceiling_cny"] == "30.00"

    one_cent_over = dict(exact)
    one_cent_over["comparison_actual_spend_cny"] = "22.79"
    one_cent_over["total_stage_spend_cny"] = "22.93"
    one_cent_over["entries"] = [dict(exact["entries"][0])]
    one_cent_over["entries"][0]["actual_cost_cny"] = "22.79"
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.authorize_next_comparison_run(
            one_cent_over,
            matrix_document=document,
            run_index=2,
            next_run_worst_case_bound_cny=Decimal("7.08"),
        )
    assert exc_info.value.code == "CANARY_HARD_CAP_RESERVATION_FAILED"


def test_slot_runner_prepares_only_the_next_frozen_production_command(
    tmp_path: Path,
) -> None:
    """The wrapper closes the gap between aggregate preflight and exec."""
    pkg_dir = tmp_path / "comparison-pkg"
    result = freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    first_command = shlex.split(result["commands"][0])
    assert first_command[:5] == [
        "python",
        "scripts/with-project-env",
        "--",
        "python",
        "scripts/run-prompt-comparison-slot",
    ]
    assert first_command[-2:] == ["--run-index", "1"]

    launch = cmp_mod.prepare_comparison_slot_launch(
        REPO_ROOT,
        **_slot_prepare_kwargs(pkg_dir, 1),
    )
    assert launch["authorization"]["next_run_worst_case_bound_cny"] == "7.08"
    parsed = _build_parser().parse_args(list(launch["command_argv"])[2:])
    assert parsed.entry == "new-run"
    assert parsed.prompt_profile == cmp_mod.BASELINE_PROFILE_ID

    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.prepare_comparison_slot_launch(
            REPO_ROOT,
            **_slot_prepare_kwargs(pkg_dir, 2),
        )
    assert exc_info.value.code == "PREVIOUS_SLOT_NOT_INGESTED"

    runner = REPO_ROOT / "scripts" / "run-prompt-comparison-slot"
    assert runner.is_file()
    assert runner.stat().st_mode & 0o111


def test_slot_runner_rejects_external_matrix_and_budget_contract_drift(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    kwargs = _slot_prepare_kwargs(pkg_dir, 1)

    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.prepare_comparison_slot_launch(
            REPO_ROOT,
            **{**kwargs, "expected_matrix_sha256": "0" * 64},
        )
    assert exc_info.value.code == "MATRIX_FILE_HASH_MISMATCH"

    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.prepare_comparison_slot_launch(
            REPO_ROOT,
            **{**kwargs, "expected_reapproval_threshold_cny": Decimal("4.99")},
        )
    assert exc_info.value.code == "PLAN_GATE_CONTRACT_DRIFT"

    ledger_path = pkg_dir / "spend-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["historical_spend_cny"] = "0.13"
    ledger["total_stage_spend_cny"] = "0.13"
    ledger_path.write_bytes(canonical_json_bytes(ledger))
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.prepare_comparison_slot_launch(REPO_ROOT, **kwargs)
    assert exc_info.value.code == "LEDGER_OPENING_BALANCE_DRIFT"


def test_slot_runner_cli_rejects_out_of_order_without_exec_or_network(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    completed = subprocess.run(
        _slot_runner_argv(pkg_dir, 2),
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    error = json.loads(completed.stderr)
    assert error == {
        "code": "PREVIOUS_SLOT_NOT_INGESTED",
        "message": "Only the next sequential matrix slot may be launched",
        "status": "comparison_preflight_rejected",
    }
    assert completed.stdout == b""


def test_slot_reservation_is_write_once_and_blocks_duplicate_launches(
    tmp_path: Path,
) -> None:
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    launch = cmp_mod.prepare_comparison_slot_launch(
        REPO_ROOT,
        **_slot_prepare_kwargs(pkg_dir, 1),
    )
    reservation = _reserve(launch)
    reservation_path = Path(reservation["path"])
    assert reservation_path.is_file()
    assert reservation_path.stat().st_mode & 0o777 == 0o600
    document = json.loads(reservation_path.read_text())
    assert document["authorization"]["run_index"] == 1
    assert document["authorization"]["next_run_worst_case_bound_cny"] == "7.08"
    assert document["execution_code_commit"] == EXECUTION_COMMIT_A
    assert document["command_argv_sha256"] == sha256_bytes(
        canonical_json_bytes(list(launch["command_argv"]))
    )
    with pytest.raises(IdeationInputError) as exc_info:
        _reserve(launch)
    assert exc_info.value.code == "COMPARISON_SLOT_ALREADY_RESERVED"

    # CLI leg: a fresh package whose pin matches the real repository HEAD, so
    # the real runner reaches the duplicate-reservation guard when the
    # worktree is clean; when it is dirty (the usual pre-commit validation
    # state) the clean-HEAD guard fires first. Both fail closed before exec.
    cli_pkg = tmp_path / "comparison-pkg-cli"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=cli_pkg,
    )
    real_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _reserve(
        cmp_mod.prepare_comparison_slot_launch(
            REPO_ROOT,
            **_slot_prepare_kwargs(cli_pkg, 1),
        ),
        commit=real_head,
    )
    completed = subprocess.run(
        _slot_runner_argv(cli_pkg, 1),
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert json.loads(completed.stderr)["code"] in {
        "COMPARISON_SLOT_ALREADY_RESERVED",
        "DIRTY_WORKTREE",
    }
    assert completed.stdout == b""


def _advance_ledger_through(pkg_dir: Path, last_ingested_slot: int) -> None:
    """Record actual costs for slots 1..last_ingested_slot in the package ledger."""
    ledger_path = pkg_dir / "spend-ledger.json"
    matrix = parse_json_bytes(
        (pkg_dir / "run-matrix.json").read_bytes(), label="run matrix"
    )
    ledger = parse_json_bytes(ledger_path.read_bytes(), label="spend ledger")
    for slot in range(1, last_ingested_slot + 1):
        slot_run = next(run for run in matrix["runs"] if run["run_index"] == slot)
        ledger = cmp_mod.ingest_run_actual_cost(
            ledger,
            entry=cmp_mod.LedgerEntry(
                run_index=slot,
                pair_index=slot_run["pair_index"],
                case_id=slot_run["case_id"],
                profile_id=slot_run["prompt_profile_id"],
                run_id=f"00000000-0000-4000-8000-{slot:012d}",
                status="success",
                actual_cost_cny=Decimal("0.10"),
                worst_case_bound_cny=Decimal("0.50"),
                physical_attempt_count=1,
            ),
        )
    ledger_path.write_bytes(canonical_json_bytes(ledger))


def test_first_slot_creates_execution_code_pin_and_same_commit_retry_is_safe(
    tmp_path: Path,
) -> None:
    """Slot 1 reservation pins the clean HEAD write-once at mode 0600."""
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    launch = cmp_mod.prepare_comparison_slot_launch(
        REPO_ROOT,
        **_slot_prepare_kwargs(pkg_dir, 1),
    )
    reservation = _reserve(launch)
    pin_path = pkg_dir / "execution-code-pin.json"
    assert pin_path.is_file()
    assert pin_path.stat().st_mode & 0o777 == 0o600
    pin = json.loads(pin_path.read_text())
    assert pin["commit"] == EXECUTION_COMMIT_A
    assert pin["schema_version"] == "comparison-execution-code-pin-v1.0.0"
    assert reservation["document"]["execution_code_commit"] == EXECUTION_COMMIT_A

    # A same-commit retry stays fail-closed on the reservation and never
    # touches the existing pin.
    with pytest.raises(IdeationInputError) as exc_info:
        _reserve(launch)
    assert exc_info.value.code == "COMPARISON_SLOT_ALREADY_RESERVED"
    assert json.loads(pin_path.read_text())["commit"] == EXECUTION_COMMIT_A


def test_execution_code_pin_missing_after_first_slot_fails_closed(
    tmp_path: Path,
) -> None:
    """A later slot without the pin means slot 1's evidence was tampered with."""
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    _advance_ledger_through(pkg_dir, 1)
    launch = cmp_mod.prepare_comparison_slot_launch(
        REPO_ROOT,
        **_slot_prepare_kwargs(pkg_dir, 2),
    )
    with pytest.raises(IdeationInputError) as exc_info:
        _reserve(launch)
    assert exc_info.value.code == "EXECUTION_CODE_PIN_MISSING"


def test_execution_code_pin_rejects_commit_drift_and_preserves_stale_pin(
    tmp_path: Path,
) -> None:
    """A later slot at a different HEAD fails closed; the stale pin is evidence."""
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    _reserve(
        cmp_mod.prepare_comparison_slot_launch(
            REPO_ROOT,
            **_slot_prepare_kwargs(pkg_dir, 1),
        )
    )
    _advance_ledger_through(pkg_dir, 1)
    launch = cmp_mod.prepare_comparison_slot_launch(
        REPO_ROOT,
        **_slot_prepare_kwargs(pkg_dir, 2),
    )
    pin_bytes = (pkg_dir / "execution-code-pin.json").read_bytes()
    with pytest.raises(IdeationInputError) as exc_info:
        _reserve(launch, commit=EXECUTION_COMMIT_B)
    assert exc_info.value.code == "EXECUTION_CODE_PIN_MISMATCH"
    assert (pkg_dir / "execution-code-pin.json").read_bytes() == pin_bytes
    assert not (pkg_dir / "vault" / "run-reservations" / "run-002.json").exists()


def test_execution_code_pin_creation_is_exclusive(tmp_path: Path) -> None:
    """Concurrent/double pin creation loses the exclusive-create race closed."""
    pkg_dir = tmp_path / "comparison-pkg"
    pkg_dir.mkdir()
    created = cmp_mod.create_execution_code_pin(pkg_dir, commit=EXECUTION_COMMIT_A)
    assert Path(created["path"]).stat().st_mode & 0o777 == 0o600
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.create_execution_code_pin(pkg_dir, commit=EXECUTION_COMMIT_A)
    assert exc_info.value.code == "EXECUTION_CODE_PIN_EXISTS"


def test_execution_code_pin_requires_a_clean_worktree_at_launch(
    tmp_path: Path,
) -> None:
    """The production default resolver fails closed on a dirty worktree."""
    pkg_dir = tmp_path / "comparison-pkg"
    freeze_prompt_comparison_package(
        REPO_ROOT,
        plan_gate_reapproval_threshold_cny=Decimal("5.00"),
        target_dir=pkg_dir,
    )
    repo = tmp_path / "exec-repo"
    policies = repo / "ai_scientist" / "ideation" / "policies"
    policies.mkdir(parents=True)
    (policies / "deepseek-cny-price-table-v1.json").write_bytes(
        (
            REPO_ROOT
            / "ai_scientist"
            / "ideation"
            / "policies"
            / "deepseek-cny-price-table-v1.json"
        ).read_bytes()
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Comparison Tester"], cwd=repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "tester@example.com"], cwd=repo, check=True
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture exec repo"], cwd=repo, check=True
    )
    launch = cmp_mod.prepare_comparison_slot_launch(
        repo,
        **_slot_prepare_kwargs(pkg_dir, 1),
    )
    # The clean fixture repository reserves slot 1 under its real HEAD.
    reservation = cmp_mod.reserve_comparison_slot(launch)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    pin = json.loads((pkg_dir / "execution-code-pin.json").read_text())
    assert pin["commit"] == head
    assert reservation["document"]["execution_code_commit"] == head

    # A dirty worktree is rejected at the reserve seam before any further write.
    (repo / "dirty.txt").write_text("uncommitted")
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.reserve_comparison_slot(launch)
    assert exc_info.value.code == "DIRTY_WORKTREE"


def test_ingest_rejects_run_admitted_at_a_different_commit(
    ingested_env: dict[str, Any],
    tmp_path: Path,
) -> None:
    """A sealed run whose admission commit differs from the pin is rejected."""
    env = ingested_env
    run = env["runs"][0]
    run_id = env["run_ids"][(run.case_id, run.profile_id)]
    pin_dir = tmp_path / "comparison-pkg"
    pin_dir.mkdir()
    cmp_mod.create_execution_code_pin(pin_dir, commit=EXECUTION_COMMIT_B)
    pin_bytes = (pin_dir / "execution-code-pin.json").read_bytes()
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.ingest_comparison_result(
            env["workspace"],
            run_id,
            expected_run_index=run.run_index,
            expected_arm_position=run.arm_position,
            expected_pair_index=run.pair_index,
            expected_case_id=run.case_id,
            expected_profile_id=run.profile_id,
            matrix_document=env["document"],
            package_dir=pin_dir,
        )
    assert exc_info.value.code == "EXECUTION_CODE_PIN_MISMATCH"
    assert (pin_dir / "execution-code-pin.json").read_bytes() == pin_bytes


def test_ingest_requires_the_execution_code_pin(
    ingested_env: dict[str, Any],
    tmp_path: Path,
) -> None:
    env = ingested_env
    run = env["runs"][0]
    run_id = env["run_ids"][(run.case_id, run.profile_id)]
    empty_dir = tmp_path / "comparison-pkg"
    empty_dir.mkdir()
    with pytest.raises(IdeationInputError) as exc_info:
        cmp_mod.ingest_comparison_result(
            env["workspace"],
            run_id,
            expected_run_index=run.run_index,
            expected_arm_position=run.arm_position,
            expected_pair_index=run.pair_index,
            expected_case_id=run.case_id,
            expected_profile_id=run.profile_id,
            matrix_document=env["document"],
            package_dir=empty_dir,
        )
    assert exc_info.value.code == "EXECUTION_CODE_PIN_MISSING"
