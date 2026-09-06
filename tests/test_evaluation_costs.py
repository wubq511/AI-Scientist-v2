"""Evaluation AI-review cost ledger tests (ticket 03).

Offline, deterministic pytest coverage of the separate, hash-linked,
append-only AI review cost ledger: write-once initialization, append-only
recording with recomputed totals and fail-closed entry validation, closed
re-validation on load with tampering detection, the read-only merged
generation + evaluation cost report, and concurrent-modification drift
protection. No network and no fixtures beyond tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.evaluation_costs import (
    EVALUATION_COST_LEDGER_NAME,
    EVALUATION_COST_LEDGER_SCHEMA_VERSION,
    initialize_evaluation_cost_ledger,
    load_evaluation_cost_ledger,
    merged_cost_report,
    record_evaluation_cost,
    save_evaluation_cost_ledger,
)

LEDGER_RELPATH = Path("artifacts/evaluations") / EVALUATION_COST_LEDGER_NAME

VALID_ENTRY = {
    "call_kind": "single_review",
    "run_id": "run-00000001",
    "pair_id": None,
    "idea_index": 0,
    "provider": "deepseek",
    "model_id": "deepseek-v4-pro",
    "physical_call_count": 1,
    "cost_cny": "0.10",
    "responded_at": "2026-09-05T01:00:00.000000Z",
    "recorded_at": "2026-09-05T01:05:00.000000Z",
    "recorded_by": "Robert",
    "note": "primary single review",
}


def _record(ledger: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    entry = dict(VALID_ENTRY)
    entry.update(overrides)
    return record_evaluation_cost(ledger, **entry)


def _fake_generation_ledger() -> dict[str, Any]:
    return {
        "canary_hard_cap_cny": "30.00",
        "comparison_actual_spend_cny": "2.00",
        "forfeited_spend_cny": "0.00",
        "historical_spend_cny": "0.14",
        "plan_gate_reapproval_threshold_cny": "5.00",
        "schema_version": "comparison-spend-ledger-v1.3.0",
        "status": "ingesting",
        "total_stage_spend_cny": "2.14",
    }


def test_init_is_write_once_and_duplicate_fails(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    document = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    assert document["schema_version"] == EVALUATION_COST_LEDGER_SCHEMA_VERSION
    assert document["created_by"] == "Robert"
    assert document["entries"] == []
    assert document["total_cost_cny"] == "0.00"
    assert document["last_entry_sha256"] is None
    assert document["status"] == "open"

    ledger_path = workspace / LEDGER_RELPATH
    assert ledger_path.is_file()
    assert ledger_path.stat().st_mode & 0o777 == 0o600

    with pytest.raises(IdeationInputError) as exc:
        initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    assert exc.value.code == "ARTIFACT_EXISTS"


def test_load_missing_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(IdeationInputError) as exc:
        load_evaluation_cost_ledger(workspace)
    assert exc.value.code == "EVALUATION_COST_LEDGER_MISSING"


def test_record_appends_and_total_recomputes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")

    ledger = _record(ledger, cost_cny="0.10")
    assert ledger["total_cost_cny"] == "0.10"
    assert ledger["entries"][0]["entry_seq"] == 1
    expected_hash = sha256_bytes(canonical_json_bytes(ledger["entries"][0]))
    assert ledger["last_entry_sha256"] == expected_hash
    save_evaluation_cost_ledger(workspace, ledger)

    ledger = _record(
        load_evaluation_cost_ledger(workspace),
        call_kind="pair_review",
        run_id=None,
        pair_id="pair-1",
        cost_cny="0.20",
    )
    assert ledger["total_cost_cny"] == "0.30"
    assert ledger["entries"][1]["entry_seq"] == 2
    assert ledger["entries"][1]["run_id"] is None
    expected_hash = sha256_bytes(canonical_json_bytes(ledger["entries"][1]))
    assert ledger["last_entry_sha256"] == expected_hash
    save_evaluation_cost_ledger(workspace, ledger)

    ledger = _record(
        load_evaluation_cost_ledger(workspace),
        call_kind="repair",
        run_id=None,
        pair_id="pair-1",
        idea_index=None,
        cost_cny="0.05",
    )
    assert ledger["total_cost_cny"] == "0.35"
    save_evaluation_cost_ledger(workspace, ledger)
    reloaded = load_evaluation_cost_ledger(workspace)
    assert reloaded["total_cost_cny"] == "0.35"
    assert len(reloaded["entries"]) == 3
    assert [entry["entry_seq"] for entry in reloaded["entries"]] == [1, 2, 3]
    assert reloaded["status"] == "open"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"call_kind": "not_a_kind"}, "INVALID_SCHEMA"),
        ({"provider": ""}, "INVALID_SCHEMA"),
        ({"model_id": ""}, "INVALID_SCHEMA"),
        ({"recorded_by": ""}, "INVALID_SCHEMA"),
        ({"cost_cny": "0.1"}, "INVALID_MONEY"),
        ({"cost_cny": "abc"}, "INVALID_MONEY"),
        ({"cost_cny": "-1.00"}, "INVALID_MONEY"),
        ({"cost_cny": "0.001"}, "INVALID_MONEY"),
        ({"physical_call_count": 0}, "INVALID_SCHEMA"),
        ({"physical_call_count": True}, "INVALID_SCHEMA"),
        ({"responded_at": "not-a-timestamp"}, "INVALID_SCHEMA"),
        ({"recorded_at": "2026-09-05 01:00:00"}, "INVALID_SCHEMA"),
        ({"idea_index": -1}, "INVALID_SCHEMA"),
        ({"note": ""}, "INVALID_SCHEMA"),
        ({"run_id": "run-x", "call_kind": "pair_review"}, "INVALID_SCHEMA"),
    ],
)
def test_record_rejects_invalid_entries(
    tmp_path: Path, overrides: dict[str, Any], expected_code: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    with pytest.raises(IdeationInputError) as exc:
        _record(ledger, **overrides)
    assert exc.value.code == expected_code


def test_record_rejects_closed_ledger(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    closed = dict(ledger)
    closed["status"] = "closed"
    with pytest.raises(IdeationInputError) as exc:
        _record(closed)
    assert exc.value.code == "EVALUATION_COST_LEDGER_CLOSED"


def test_load_detects_tampering(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    ledger = _record(ledger, cost_cny="0.10")
    save_evaluation_cost_ledger(workspace, ledger)
    ledger = _record(
        load_evaluation_cost_ledger(workspace),
        call_kind="pair_review",
        run_id=None,
        pair_id="pair-1",
        cost_cny="0.20",
    )
    save_evaluation_cost_ledger(workspace, ledger)

    ledger_path = workspace / LEDGER_RELPATH
    on_disk = json.loads(ledger_path.read_text(encoding="utf-8"))

    # Cost tampering: the stored total no longer recomputes from the entries.
    tampered = json.loads(json.dumps(on_disk))
    tampered["entries"][0]["cost_cny"] = "0.99"
    ledger_path.write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(IdeationInputError) as exc:
        load_evaluation_cost_ledger(workspace)
    assert exc.value.code == "EVALUATION_COST_LEDGER_ARITHMETIC"

    # Hash-chain tampering: a non-monetary field change breaks the last hash.
    tampered = json.loads(json.dumps(on_disk))
    tampered["entries"][1]["model_id"] = "tampered-model"
    ledger_path.write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(IdeationInputError) as exc2:
        load_evaluation_cost_ledger(workspace)
    assert exc2.value.code == "EVALUATION_COST_LEDGER_CHAIN_DRIFT"

    # Closed-shape tampering: an unknown top-level key is rejected.
    tampered = json.loads(json.dumps(on_disk))
    tampered["evil"] = True
    ledger_path.write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(IdeationInputError) as exc3:
        load_evaluation_cost_ledger(workspace)
    assert exc3.value.code == "INVALID_SCHEMA"


def test_merged_cost_report_shape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    ledger = _record(ledger, call_kind="single_review", cost_cny="0.10")
    ledger = _record(
        ledger,
        call_kind="pair_review",
        run_id=None,
        pair_id="pair-1",
        cost_cny="0.20",
    )
    ledger = _record(
        ledger,
        call_kind="repair",
        run_id=None,
        pair_id="pair-1",
        cost_cny="0.05",
    )

    generation = _fake_generation_ledger()
    generation_before = json.loads(json.dumps(generation))
    evaluation_before = json.loads(json.dumps(ledger))

    report = merged_cost_report(generation, ledger)

    assert report["schema_version"] == "evaluation-cost-merged-report-v1.0.0"
    assert report["generation"] == {
        "canary_hard_cap_cny": "30.00",
        "comparison_actual_spend_cny": "2.00",
        "forfeited_spend_cny": "0.00",
        "historical_spend_cny": "0.14",
        "plan_gate_reapproval_threshold_cny": "5.00",
        "total_stage_spend_cny": "2.14",
    }
    assert report["evaluation"] == {
        "total_cost_cny": "0.35",
        "entries_count": 3,
        "by_call_kind": {
            "pair_review": "0.20",
            "repair": "0.05",
            "single_review": "0.10",
        },
        "by_provider_model": {
            "deepseek/deepseek-v4-pro": "0.35",
        },
    }
    assert report["merged_stage_spend_cny"] == "2.49"
    assert (
        "NOT covered by the generation Plan Gate approval"
        in report["unauthorized_spend_disclosure"]
    )
    assert report["notes"] == [
        "The merged view is read-only and never rewrites generation history.",
        "AI review costs never silently extend the generation budget.",
    ]
    # Read-only: neither input is mutated.
    assert generation == generation_before
    assert ledger == evaluation_before


def test_merged_report_rejects_invalid_generation_money(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    generation = _fake_generation_ledger()
    generation["total_stage_spend_cny"] = "two-point-one-four"
    with pytest.raises(IdeationInputError) as exc:
        merged_cost_report(generation, ledger)
    assert exc.value.code == "INVALID_MONEY"


def test_save_fails_on_concurrent_modification(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = initialize_evaluation_cost_ledger(workspace, created_by="Robert")
    ledger = _record(ledger, cost_cny="0.10")
    save_evaluation_cost_ledger(workspace, ledger)

    # A concurrent writer appends and persists another entry.
    concurrent = _record(
        ledger,
        call_kind="pair_review",
        run_id=None,
        pair_id="pair-1",
        cost_cny="0.20",
    )
    save_evaluation_cost_ledger(workspace, concurrent)

    # The stale snapshot can no longer be persisted: drift fails closed.
    with pytest.raises(IdeationInputError) as exc:
        save_evaluation_cost_ledger(workspace, ledger)
    assert exc.value.code == "EVALUATION_COST_LEDGER_DRIFT"
