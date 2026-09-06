"""Tests for Canary v1.1 selection, matrix ordering, blinding, and spend ledger."""

from __future__ import annotations

import json
from pathlib import Path

from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from prototypes.canary_matrix.matrix import (
    build_canary_matrix,
    build_initial_spend_ledger,
)
from prototypes.canary_matrix.selection import (
    BASE_CLUSTER_QUOTAS,
    EXPECTED_SPENT_COUNT,
    SELECTION_VERSION,
    build_selection_manifest,
    generate_sanitized_summary_table,
    load_spent_target_ids,
    select_canary_v11_cases,
)


def test_spent_target_ids_count_and_exclusion() -> None:
    workspace_root = Path.cwd()
    spent = load_spent_target_ids(workspace_root)
    assert len(spent) == EXPECTED_SPENT_COUNT


def test_canary_v11_case_selection_properties() -> None:
    workspace_root = Path.cwd()
    selected = select_canary_v11_cases(workspace_root)

    assert len(selected) == 12

    # Verify all targets and case_ids are distinct
    target_ids = [c.target_id for c in selected]
    case_ids = [c.case_id for c in selected]
    assert len(set(target_ids)) == 12
    assert len(set(case_ids)) == 12

    # Verify freshness (0 overlap with spent)
    spent = load_spent_target_ids(workspace_root)
    assert len(set(target_ids) & spent) == 0

    # Verify cluster distribution
    cluster_counts: dict[str, int] = {}
    for c in selected:
        cluster_counts[c.cluster] = cluster_counts.get(c.cluster, 0) + 1

    assert len(cluster_counts) == 8
    assert cluster_counts["Health & Medicine"] == 3  # 2 base + 1 edge slot
    assert cluster_counts["Genetics & Molecular Biology"] == 2
    assert cluster_counts["Neuroscience & Cognitive Sciences"] == 2
    for other_cl in (
        "Environmental Sciences",
        "Materials Science",
        "Public Health & Policy",
        "Social & Behavioral Sciences",
        "Technology & Engineering",
    ):
        assert cluster_counts[other_cl] == 1

    # Verify roles
    base_slots = [c for c in selected if c.role == "base_slot"]
    edge_slots = [c for c in selected if c.role == "constraint_driven_edge_slot"]
    assert len(base_slots) == 11
    assert len(edge_slots) == 1
    assert edge_slots[0].slot_index == 12

    # Verify edge requirements
    assert any(c.ref_count == 3 for c in selected)
    assert any(c.ref_count == 7 for c in selected)
    assert any(c.ref_count == 32 for c in selected)
    assert any(c.strategy == 2 for c in selected)

    unavail_cases = [c for c in selected if c.has_unavail_abstract]
    assert len(unavail_cases) == 1
    assert unavail_cases[0].slot_index == 12
    assert unavail_cases[0].role == "constraint_driven_edge_slot"

    # Verify table generation
    table = generate_sanitized_summary_table(selected)
    assert "| 01 |" in table
    assert "| 12 |" in table
    assert "unavailable_reference_abstract" in table


def test_canary_matrix_order_and_blinding_balance() -> None:
    workspace_root = Path.cwd()
    selected = select_canary_v11_cases(workspace_root)
    manifest = build_selection_manifest(workspace_root, selected)
    manifest_sha256 = sha256_bytes(canonical_json_bytes(manifest))

    runs, blind_pairs = build_canary_matrix(selected, manifest_sha256)

    assert len(runs) == 24
    assert len(blind_pairs) == 12

    # Check 6 high-first, 6 max-first
    high_first = [p for p in range(12) if runs[p * 2].reasoning_effort == "high"]
    max_first = [p for p in range(12) if runs[p * 2].reasoning_effort == "max"]
    assert len(high_first) == 6
    assert len(max_first) == 6

    # Check blinding balance: 6 where A=high, 6 where A=max
    a_high = [bp for bp in blind_pairs if bp.arm_a_effort == "high"]
    a_max = [bp for bp in blind_pairs if bp.arm_a_effort == "max"]
    assert len(a_high) == 6
    assert len(a_max) == 6

    # Check commands are credential-free
    for r in runs:
        assert "DEEPSEEK_API_KEY" not in r.credential_free_command
        assert "api_key" not in r.credential_free_command
        assert "new-run" in r.credential_free_command
        assert r.case_id in r.credential_free_command
        assert f"--reasoning-effort {r.reasoning_effort}" in r.credential_free_command
        assert "--max-tokens 32768" in r.credential_free_command


def test_initial_spend_ledger_properties() -> None:
    manifest_sha = "a" * 64
    ledger = build_initial_spend_ledger(manifest_sha)
    assert ledger["status"] == "initialized"
    assert ledger["current_actual_spend_cny"] == "0.00"
    assert ledger["current_remaining_budget_cny"] == "30.00"
    assert ledger["planned_runs_count"] == 24
    assert ledger["completed_runs_count"] == 0
    assert ledger["budget_rules"]["per_run_worst_case_admission_bound_cny"] == "7.08"


def test_selection_is_deterministic() -> None:
    workspace_root = Path.cwd()
    run1 = select_canary_v11_cases(workspace_root)
    run2 = select_canary_v11_cases(workspace_root)

    manifest1 = build_selection_manifest(workspace_root, run1)
    manifest2 = build_selection_manifest(workspace_root, run2)

    bytes1 = canonical_json_bytes(manifest1)
    bytes2 = canonical_json_bytes(manifest2)
    assert bytes1 == bytes2


def test_materialize_comparison_artifacts(tmp_path: Path) -> None:
    from prototypes.canary_matrix.matrix import materialize_comparison_artifacts

    workspace_root = Path.cwd()
    selected = select_canary_v11_cases(workspace_root)
    manifest = build_selection_manifest(workspace_root, selected)
    manifest_sha = sha256_bytes(canonical_json_bytes(manifest))

    hashes = materialize_comparison_artifacts(
        workspace_root, selected, manifest_sha, tmp_path
    )

    assert set(hashes.keys()) == {
        "run-matrix.json",
        "blind-mapping.json",
        "spend-ledger.json",
        "commands.txt",
    }
    for filename, sha in hashes.items():
        assert len(sha) == 64
        assert (tmp_path / filename).is_file()

    matrix = json.loads((tmp_path / "run-matrix.json").read_text())
    assert matrix["planned_runs_count"] == 24
    assert matrix["pairs_count"] == 12
    assert matrix["high_first_pairs_count"] == 6
    assert matrix["max_first_pairs_count"] == 6

    blinding = json.loads((tmp_path / "blind-mapping.json").read_text())
    assert blinding["pairs_count"] == 12
    assert blinding["arm_a_is_high_count"] == 6
    assert blinding["arm_a_is_max_count"] == 6

    ledger = json.loads((tmp_path / "spend-ledger.json").read_text())
    assert ledger["current_actual_spend_cny"] == "0.00"
    assert ledger["current_remaining_budget_cny"] == "30.00"

    lines = (tmp_path / "commands.txt").read_text().strip().split("\n")
    assert len(lines) == 24
    for line in lines:
        assert line.startswith(
            "python ai_scientist/perform_ideation_temp_free.py new-run"
        )
        assert "DEEPSEEK_API_KEY" not in line
