"""Resume a suspended Ideation Run from its canonical evidence chain (ticket 10).

The resume entry point takes only the exact run_id: it re-verifies the full
evidence chain and every artifact reference, re-checks the admission pins
(workshop, corpus, price table, code commit, credential presence), clears
staging residue, quarantines approved-window orphan artifacts under a new
writer epoch, rebuilds the control state from events/artifacts (never a
projection), re-estimates the remaining cost bound, requires a fresh
write-once cost approval, and continues the run to a terminal seal.

A run interrupted during preflight re-runs the idempotent preflight instead:
no writer epoch bump, no `resumed` event, no resume approval artifact (the
cost approval lives inside the Run Admission itself).

Deterministic failures never resume: sealed runs, preflight-rejected runs,
and corrupt evidence are rejected, while a committed-but-unsealed terminal
failure is sealed during the resume (ticket 025: Run Suspension is not a
Terminal Outcome).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re
import sys
from typing import Any, TextIO

from . import pricing
from .admission import (
    DEFAULT_MAX_TOKENS,
    MAX_ATTEMPTS_PER_OPERATION,
    WORST_CASE_INPUT_TOKENS_PER_ROUND,
    NewRunRequest,
    _check_credential_presence,
    _load_approved_corpus,
    _load_approved_workshop,
    _require_clean_worktree,
    _run_preflight_steps,
    preflight_rejected,
)
from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import _now
from .controller import IdeationController, rebuild_resume_plan
from .errors import IdeationInputError, fail
from .run_store import RunHandle, RunStore, _validate_run_id

RESUME_APPROVAL_SCHEMA_VERSION = "resume-cost-approval-v1.0.0"

_OPERATION_ARTIFACT_PATTERN = re.compile(
    r"^artifacts/operations/(\d{6})/attempts/(\d{6})/([^/]+)$"
)

# Event types legal in a run that never reached admission.
_PRE_ADMISSION_EVENT_TYPES = {"preflight_started", "preflight_step", "interrupted"}


def _request_from_document(document: dict[str, Any], run_id: str) -> NewRunRequest:
    """Rebuild the NewRunRequest from the canonical request.json document."""
    if document.get("run_id") != run_id:
        fail("RUN_CORRUPT", "request.json belongs to another run")
    workshop = document.get("workshop") or {}
    corpus = document.get("corpus") or {}
    request = NewRunRequest(
        case_id=document.get("case_id"),
        workshop=workshop.get("path"),
        workshop_sha256=workshop.get("sha256"),
        corpus=corpus.get("path"),
        corpus_sha256=corpus.get("sha256"),
        max_num_generations=document.get("max_num_generations"),
        num_reflections=document.get("num_reflections"),
    )
    request.validate()
    return request


def _verify_artifact_refs(
    store: RunStore, run_id: str, events: list[dict[str, Any]]
) -> None:
    """Verify existence, SHA-256, and byte length of every referenced artifact."""
    for event in events:
        for ref in event.get("artifact_refs", []):
            relative_path = ref.get("relative_path")
            if not isinstance(relative_path, str):
                fail("RUN_CORRUPT", "Artifact reference lacks its relative_path")
            if not store.artifact_exists(run_id, relative_path):
                fail(
                    "RUN_CORRUPT",
                    f"Referenced artifact is missing: {relative_path}",
                )
            data = store.read_artifact(run_id, relative_path)
            if sha256_bytes(data) != ref.get("sha256") or len(data) != ref.get(
                "byte_length"
            ):
                fail(
                    "RUN_CORRUPT",
                    f"Referenced artifact fails hash/length verification: {relative_path}",
                )


def _resume_interrupted_preflight(
    store: RunStore,
    workspace: Path,
    run_id: str,
    events: list[dict[str, Any]],
    *,
    stream: TextIO,
    adapter: Any,
    retriever: Any,
) -> dict[str, Any]:
    """Re-run the idempotent preflight for a run interrupted before admission.

    Preflight steps are read-only checks plus write-once commits, so re-running
    them is exact. No epoch is bumped and no resume approval artifact is
    written: the cost approval is part of the Run Admission itself.
    """
    for event in events:
        if event.get("event_type") not in _PRE_ADMISSION_EVENT_TYPES:
            fail("RUN_CORRUPT", "Execution evidence exists without an admission")
    request_bytes = store.read_artifact(run_id, "request.json")
    request_sha = sha256_bytes(request_bytes)
    request = _request_from_document(
        parse_json_bytes(request_bytes, label="request.json"), run_id
    )
    if events:
        first = events[0]
        if (
            first.get("event_type") != "preflight_started"
            or first.get("request_sha256") != request_sha
        ):
            fail(
                "RUN_CORRUPT",
                "The chain does not start with the pinned preflight_started event",
            )
    else:
        store.append_event(
            run_id,
            {
                "event_type": "preflight_started",
                "payload": {"steps": 9},
                "request_sha256": request_sha,
            },
        )
    try:
        _run_preflight_steps(
            store, RunHandle(run_id), request, request_sha, workspace, stream
        )
    except IdeationInputError as exc:
        preflight_rejected(store, run_id, exc.code, exc.message)
        raise
    controller = IdeationController(
        workspace,
        run_id,
        store=store,
        adapter=adapter,
        retriever=retriever,
    )
    return controller.run()


def resume_run(
    workspace_root: Path,
    run_id: str,
    *,
    stream: TextIO | None = None,
    adapter: Any = None,
    retriever: Any = None,
    store: RunStore | None = None,
) -> dict[str, Any]:
    """Verify, approve, and continue a suspended Ideation Run to its seal."""
    stream = stream if stream is not None else sys.stdout
    workspace = workspace_root.resolve(strict=True)
    store = store or RunStore(workspace)

    # -- Gates: identity, existence, seal, chain, references ----------------
    _validate_run_id(run_id)
    if not store.run_root_exists(run_id):
        fail("RUN_NOT_FOUND", f"No Ideation Run exists with run_id: {run_id}")
    if store.artifact_exists(run_id, "seal.json"):
        fail("RUN_ALREADY_SEALED", f"Ideation Run is already sealed: {run_id}")
    if not store.artifact_exists(run_id, "request.json"):
        fail("RUN_CORRUPT", "The run root lacks its canonical request.json")

    events = store.read_events(run_id)
    if events:
        try:
            store.verify_chain(run_id)
        except IdeationInputError as exc:
            fail("RUN_CORRUPT", f"Evidence chain verification failed: {exc}")
    _verify_artifact_refs(store, run_id, events)

    if any(event.get("event_type") == "preflight_rejected" for event in events):
        fail(
            "RUN_PREFLIGHT_REJECTED",
            "A preflight-rejected run is deterministic and never resumed",
        )

    # -- Admission consistency ----------------------------------------------
    admission_exists = store.artifact_exists(run_id, "admission.json")
    admitted_events = [
        event for event in events if event.get("event_type") == "admitted"
    ]
    if not admission_exists and not admitted_events:
        return _resume_interrupted_preflight(
            store,
            workspace,
            run_id,
            events,
            stream=stream,
            adapter=adapter,
            retriever=retriever,
        )
    if not admission_exists:
        fail("RUN_CORRUPT", "An admitted event exists without admission.json")
    if len(admitted_events) > 1:
        fail("RUN_CORRUPT", "The chain carries multiple admitted events")

    admission_bytes = store.read_artifact(run_id, "admission.json")
    admission = parse_json_bytes(admission_bytes, label="admission.json")
    admission_sha = sha256_bytes(admission_bytes)
    if not admitted_events:
        # Approved crash window between the write-once admission commit and
        # the admitted event append: complete it epoch-less, exactly as the
        # original preflight would have written it.
        store.append_event(
            run_id,
            {
                "event_type": "admitted",
                "payload": {},
                "admission_sha256": admission_sha,
            },
        )
        events = store.read_events(run_id)
    elif admitted_events[0].get("admission_sha256") != admission_sha:
        fail(
            "ADMISSION_TAMPERED",
            "admission.json content does not match admission hash pinned in event chain",
        )

    # -- Admission pins re-verification --------------------------------------
    request_bytes = store.read_artifact(run_id, "request.json")
    if sha256_bytes(request_bytes) != admission["request_sha256"]:
        fail(
            "ADMISSION_TAMPERED",
            "request.json content does not match the admission pin",
        )
    request = _request_from_document(
        parse_json_bytes(request_bytes, label="request.json"), run_id
    )
    workshop = _load_approved_workshop(workspace, request)
    if workshop != admission["workshop"]:
        fail(
            "ADMISSION_TAMPERED",
            "The approved workshop no longer matches the admission pin",
        )
    corpus = _load_approved_corpus(workspace, request)
    if corpus != admission["corpus"]:
        fail(
            "ADMISSION_TAMPERED",
            "The approved corpus no longer matches the admission pin",
        )
    price_table = pricing.load_price_table(workspace)
    if price_table.sha256 != admission["price_table"]["sha256"]:
        fail(
            "ADMISSION_TAMPERED",
            "The CNY price table no longer matches the admission pin",
        )
    commit = _require_clean_worktree(workspace)
    if commit != admission["code"]["commit"]:
        fail(
            "ADMISSION_TAMPERED",
            "The HEAD commit no longer matches the admission pin",
        )
    _check_credential_presence()

    workshop_path = workspace / workshop["path"]
    workshop_text = workshop_path.read_bytes().decode("utf-8")

    # -- New writer epoch, staging cleanup, orphan quarantine ----------------
    prior_epoch = max(
        (
            event["writer_epoch"]
            for event in events
            if isinstance(event.get("writer_epoch"), int)
        ),
        default=1,
    )
    new_epoch = prior_epoch + 1

    store.clear_staging(run_id)

    referenced = {
        ref["relative_path"]
        for event in events
        for ref in event.get("artifact_refs", [])
    }
    orphans = sorted(set(store.list_committed_artifact_paths(run_id)) - referenced)
    quarantine_records: list[dict[str, Any]] = []
    orphan_triples: list[tuple[int, int, str]] = []
    for relative_path in orphans:
        record = store.quarantine_artifact(
            run_id, relative_path, incident=f"epoch-{new_epoch:06d}"
        )
        quarantine_records.append(record)
        match = _OPERATION_ARTIFACT_PATTERN.match(relative_path)
        if match:
            orphan_triples.append(
                (int(match.group(1)), int(match.group(2)), match.group(3))
            )
    if quarantine_records:
        store.append_event(
            run_id,
            {
                "event_type": "orphans_quarantined",
                "payload": {"orphans": quarantine_records},
                "writer_epoch": new_epoch,
            },
        )

    plan = rebuild_resume_plan(
        store,
        run_id,
        admission,
        writer_epoch=new_epoch,
        workshop_description=workshop_text,
        orphan_operation_artifacts=orphan_triples,
    )

    # -- Cost accounting and fresh write-once approval -----------------------
    spent = Decimal(0)
    for event in events:
        if event.get("event_type") != "provider_attempt.finished":
            continue
        cost = event.get("payload", {}).get("cost_cny")
        if cost is not None:
            spent += Decimal(cost)

    total_rounds = (
        admission["budgets"]["max_num_generations"]
        * admission["budgets"]["num_reflections"]
    )
    remaining_rounds = plan.remaining_model_rounds
    estimate = pricing.worst_case_bound(
        price_table,
        input_tokens=remaining_rounds * WORST_CASE_INPUT_TOKENS_PER_ROUND,
        output_tokens=remaining_rounds * DEFAULT_MAX_TOKENS,
        attempts=MAX_ATTEMPTS_PER_OPERATION,
    )
    projected = spent + estimate.total_cny
    original_bound = Decimal(admission["cost"]["worst_case"]["total_cny"])

    print(
        f"Resume Ideation Run {run_id} under writer epoch {new_epoch}.",
        file=stream,
    )
    print(f"  original total upper bound : {original_bound} CNY", file=stream)
    print(f"  already spent (committed)  : {spent} CNY", file=stream)
    print(
        f"  remaining upper bound      : {estimate.total_cny} CNY "
        f"({remaining_rounds} model rounds)",
        file=stream,
    )
    print(f"  projected total            : {projected} CNY", file=stream)
    print("Approve resuming this run's paid work? Type `yes` to confirm:", file=stream)
    if not sys.stdin.isatty():
        fail(
            "APPROVAL_UNAVAILABLE",
            "Resume cost approval requires an interactive session",
        )
    try:
        answer = input()
    except EOFError:
        fail("APPROVAL_REJECTED", "Resume cost approval was not confirmed")
    if answer != "yes":
        fail("APPROVAL_REJECTED", "Resume cost approval was not confirmed")

    approval_document = {
        "schema_version": RESUME_APPROVAL_SCHEMA_VERSION,
        "run_id": run_id,
        "writer_epoch": new_epoch,
        "approved_at": _now(),
        "confirmed_with": "yes",
        "original_total_upper_bound_cny": str(original_bound),
        "spent_cny": str(spent),
        "remaining_upper_bound_cny": str(estimate.total_cny),
        "projected_total_cny": str(projected),
        "completed_model_rounds": total_rounds - remaining_rounds,
        "remaining_model_rounds": remaining_rounds,
    }
    approval_rel, approval_len, approval_sha = store.write_artifact(
        run_id,
        f"artifacts/validations/resume-approval-{new_epoch:06d}.json",
        canonical_json_bytes(approval_document),
        label="resume cost approval",
    )
    store.append_event(
        run_id,
        {
            "event_type": "resumed",
            "payload": {
                "prior_writer_epoch": prior_epoch,
                "writer_epoch": new_epoch,
                "spent_cny": str(spent),
                "remaining_upper_bound_cny": str(estimate.total_cny),
                "projected_total_cny": str(projected),
            },
            "artifact_refs": [
                {
                    "byte_length": approval_len,
                    "media_type": "application/json",
                    "relative_path": approval_rel,
                    "role": "resume_cost_approval",
                    "sha256": approval_sha,
                }
            ],
            "writer_epoch": new_epoch,
        },
    )

    progress_stream = stream
    if progress_stream is None and sys.stderr.isatty():
        progress_stream = sys.stderr

    controller = IdeationController(
        workspace,
        run_id,
        store=store,
        adapter=adapter,
        retriever=retriever,
        writer_epoch=new_epoch,
        resume_plan=plan,
        progress_stream=progress_stream,
    )
    return controller.run()
