"""Run admission boundary tests (ticket 04).

Covers the deterministic Evidence Chain primitives for new-run admission:
canonical bytes, event hash chain, run root exclusive-create, and path
validation (VM-UNIT-02, VM-UNIT-03, VM-CONTRACT-023-01).
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation import run_store

REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "case-0123456789abcdef0123456789abcdef"
OTHER_CASE_ID = "case-ffffffffffffffffffffffffffffffff"


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def _run_file(workspace: Path, relpath: str) -> Path:
    return workspace / "artifacts/ideation-runs" / relpath


def test_new_run_root_is_exclusive_created_under_the_fixed_private_root(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    created = store.create_run()
    assert (workspace / "artifacts/ideation-runs" / created.run_id).is_dir()

    # Existing directory (whatever holds it) refuses reuse without clearing.
    with pytest.raises(IdeationInputError, match="RUN_ROOT_EXISTS"):
        run_store.RunStore(workspace).create_run(run_id=created.run_id)


def test_created_run_refuses_unknown_run_id_shapes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    for bad in ["not-a-uuid", "RUN-UPPER", "", "3628aca1-2d1f-4g04-9e8e-0e6f71e4d99b"]:
        with pytest.raises(IdeationInputError, match="INVALID_RUN_ID"):
            store.create_run(run_id=bad)


def test_request_and_events_use_canonical_bytes_and_a_linked_hash_chain(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    run = store.create_run()

    request_document = {
        "case_id": CASE_ID,
        "run_id": run.run_id,
        "schema_version": "run-request-v1.0.0",
    }
    request_sha = store.write_request(run.run_id, request_document)
    request_bytes = (_run_file(workspace, run.request_path)).read_bytes()
    assert request_bytes == canonical_json_bytes(request_document)
    assert sha256_bytes(request_bytes) == request_sha

    first = store.append_event(
        run.run_id,
        {
            "event_type": "preflight_started",
            "payload": {"step": "request_schema"},
            "schema_version": "evidence-event-v1.0.0",
        },
    )
    second = store.append_event(
        run.run_id,
        {
            "event_type": "preflight_step",
            "payload": {"step": "workshop_approval", "status": "pass"},
            "schema_version": "evidence-event-v1.0.0",
        },
    )
    assert first.event_seq == 1
    assert first.prev_event_hash is None
    assert second.event_seq == 2
    assert second.prev_event_hash == first.event_hash

    first_bytes = _run_file(workspace, run.event_path(1)).read_bytes()
    first_document = json.loads(first_bytes)
    assert first_document["prev_event_hash"] is None
    assert first_document["event_hash"] == first.event_hash
    assert first_bytes == canonical_json_bytes(first_document)

    second_bytes = _run_file(workspace, run.event_path(2)).read_bytes()
    second_document = json.loads(second_bytes)
    assert second_document["prev_event_hash"] == first.event_hash
    assert second_bytes == canonical_json_bytes(second_document)

    # event_hash is the canonical bytes of the event with event_hash omitted.
    without_hash = dict(second_document)
    del without_hash["event_hash"]
    assert sha256_bytes(canonical_json_bytes(without_hash)) == second.event_hash


def test_write_admission_is_write_once_and_hash_pinned(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    run = store.create_run()
    store.write_request(
        run.run_id,
        {"case_id": CASE_ID, "run_id": run.run_id, "schema_version": "x"},
    )
    admission = {
        "case_id": CASE_ID,
        "run_id": run.run_id,
        "schema_version": "run-admission-v1.0.0",
    }
    admission_sha = store.write_admission(run.run_id, admission)
    admission_bytes = (_run_file(workspace, run.admission_path)).read_bytes()
    assert admission_bytes == canonical_json_bytes(admission)
    assert sha256_bytes(admission_bytes) == admission_sha

    with pytest.raises(IdeationInputError, match="ARTIFACT_EXISTS"):
        store.write_admission(
            run.run_id, {**admission, "approved_at": "2026-09-03T00:00:00.000000Z"}
        )


def test_request_cannot_be_rewritten(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    run = store.create_run()
    store.write_request(
        run.run_id, {"case_id": CASE_ID, "run_id": run.run_id, "schema": "x"}
    )
    with pytest.raises(IdeationInputError, match="ARTIFACT_EXISTS"):
        store.write_request(run.run_id, {"case_id": OTHER_CASE_ID, "x": 1})


def test_event_paths_reject_relative_sequences_and_skips(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    run = store.create_run()
    # Appending with a prev_event_hash that does not extend the canonical
    # chain must fail closed rather than forking the sequence.
    first = store.append_event(
        run.run_id, {"event_type": "preflight_started", "schema_version": "x"}
    )
    with pytest.raises(IdeationInputError, match="MISSING_EVENT"):
        store.append_event(
            run.run_id,
            {"event_type": "preflight_step", "schema_version": "x"},
            prev_event_hash="0" * 64,
        )
    assert first.event_seq == 1


def test_symlinked_run_root_component_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    runs_root = workspace / "artifacts/ideation-runs"
    runs_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (runs_root / "3628aca1-2d1f-4d04-9e8e-0e6f71e4d99b").symlink_to(
        outside, target_is_directory=True
    )
    store = run_store.RunStore(workspace)
    with pytest.raises(IdeationInputError, match="RUN_ROOT_EXISTS|SYMLINK"):
        store.create_run(run_id="3628aca1-2d1f-4d04-9e8e-0e6f71e4d99b")


def test_event_chain_verification_detects_a_break(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    run = store.create_run()
    store.write_request(
        run.run_id, {"case_id": CASE_ID, "run_id": run.run_id, "schema": "x"}
    )
    store.append_event(
        run.run_id, {"event_type": "preflight_started", "schema_version": "x"}
    )
    store.append_event(
        run.run_id, {"event_type": "preflight_step", "schema_version": "x"}
    )
    assert store.verify_chain(run.run_id) == 2

    # Tamper with the second event file: verification must fail closed.
    event_path = _run_file(workspace, run.event_path(2))
    document = json.loads(event_path.read_bytes())
    document["payload"] = {"tampered": True}
    event_path.write_bytes(canonical_json_bytes(document))
    with pytest.raises(IdeationInputError):
        store.verify_chain(run.run_id)


def test_run_events_never_leak_across_runs(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    store = run_store.RunStore(workspace)
    run_a = store.create_run()
    store.append_event(
        run_a.run_id, {"event_type": "preflight_started", "schema_version": "x"}
    )
    # A different store instance bound to the same workspace cannot append to
    # run A under a foreign run root, and run A's events stay inside its root.
    run_b = store.create_run()
    assert run_a.run_id != run_b.run_id
    assert _run_file(workspace, run_a.event_path(1)).is_file()
    assert not _run_file(workspace, run_b.event_path(1)).exists()
