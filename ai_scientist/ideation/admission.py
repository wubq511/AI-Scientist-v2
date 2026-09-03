"""Nine-step fail-closed new-run preflight and Run Admission (ticket 04).

The preflight sequence is fixed by the safe-entry contract: request schema,
run creation, clean worktree, Approved Workshop, Approved Corpus, bound
retriever, credential presence, explicit cost approval, then the write-once
Run Admission. No model request may precede admission; any step failure
marks the run preflight-rejected with retained request and event evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import subprocess
from typing import Any, TextIO

from . import pricing
from .canonical import parse_json_bytes, sha256_bytes
from .errors import IdeationInputError, fail
from .retrieval import bind_corpus
from .run_store import (
    RUN_REQUEST_SCHEMA_VERSION,
    RunStore,
)

RUN_ADMISSION_SCHEMA = "run-admission-v1.0.0"
DEEPSEEK_MODEL_ID = "deepseek-v4-pro"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# Canary-open parameters (tickets 035/036) exposed as pinned defaults; the
# admission records them so a Run Specification stays immutable.
DEFAULT_REASONING_EFFORT = "high"
DEFAULT_MAX_TOKENS = 32768
MAX_ATTEMPTS_PER_OPERATION = 2


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True, slots=True)
class NewRunRequest:
    case_id: str
    workshop: str
    workshop_sha256: str
    corpus: str
    corpus_sha256: str
    max_num_generations: int
    num_reflections: int

    def document(self, run_id: str) -> dict[str, Any]:
        return {
            "schema_version": RUN_REQUEST_SCHEMA_VERSION,
            "run_id": run_id,
            "requested_at": _now(),
            "case_id": self.case_id,
            "workshop": {"path": self.workshop, "sha256": self.workshop_sha256},
            "corpus": {"path": self.corpus, "sha256": self.corpus_sha256},
            "max_num_generations": self.max_num_generations,
            "num_reflections": self.num_reflections,
        }


def _append_step(
    store: RunStore,
    run_id: str,
    step: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    store.append_event(
        run_id,
        {
            "event_type": "preflight_step",
            "payload": {
                "step": step,
                "status": status,
                **(detail or {}),
            },
        },
    )


def _require_clean_worktree(workspace_root: Path) -> str:
    """Verify a clean git worktree and return the exact commit SHA."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail("GIT_UNAVAILABLE", "Cannot verify the worktree", error=str(exc))
    if status.stdout.strip():
        fail("DIRTY_WORKTREE", "The worktree has uncommitted changes")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        fail("GIT_UNAVAILABLE", "Cannot resolve HEAD", error=str(exc))
    return commit.stdout.strip()


def _load_approved_workshop(
    workspace_root: Path, request: NewRunRequest
) -> dict[str, Any]:
    """Verify the pinned Workshop: exact hash, approval status, case binding."""
    workshop_path = workspace_root / request.workshop
    if not workshop_path.is_file():
        fail("MISSING_WORKSHOP", "The pinned Workshop File is missing")
    workshop_bytes = workshop_path.read_bytes()
    if sha256_bytes(workshop_bytes) != request.workshop_sha256:
        fail(
            "HASH_MISMATCH",
            "Workshop bytes do not match the requested SHA-256",
            expected=request.workshop_sha256,
        )
    resolution_root = workshop_path.parent
    manifest_path = resolution_root / "workshop-manifest.json"
    if not manifest_path.is_file():
        fail("WORKSHOP_NOT_APPROVED", "The pinned Workshop has no approval manifest")
    manifest_bytes = manifest_path.read_bytes()
    manifest_value = parse_json_bytes(manifest_bytes, label="workshop manifest")
    manifest = manifest_value if isinstance(manifest_value, dict) else {}
    if manifest.get("approval_status") != "approved":
        fail("WORKSHOP_NOT_APPROVED", "The pinned Workshop is not approved")
    if manifest.get("case_id") != request.case_id:
        fail("IDENTITY_MISMATCH", "The Workshop belongs to another case")
    workshop_ref = manifest.get("workshop") or {}
    if workshop_ref.get("sha256") != request.workshop_sha256:
        fail("HASH_MISMATCH", "Workshop manifest does not bind the pinned bytes")
    if manifest_path.parent != workshop_path.parent:
        fail("WORKSHOP_NOT_APPROVED", "Workshop manifest is not adjacent")
    return {
        "path": request.workshop,
        "sha256": request.workshop_sha256,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "contract_version": manifest.get("contract_version"),
        "validator_version": manifest.get("rules", {}).get("validator_version"),
        "schema_version": manifest.get("schema_version"),
    }


def _load_approved_corpus(
    workspace_root: Path, request: NewRunRequest
) -> dict[str, Any]:
    """Verify the pinned corpus bundle per the frozen-corpus contract."""
    corpus_path = workspace_root / request.corpus
    if not corpus_path.is_file():
        fail("MISSING_CORPUS", "The pinned corpus file is missing")
    corpus_bytes = corpus_path.read_bytes()
    if sha256_bytes(corpus_bytes) != request.corpus_sha256:
        fail(
            "HASH_MISMATCH",
            "Corpus bytes do not match the requested SHA-256",
            expected=request.corpus_sha256,
        )
    bundle_root = corpus_path.parent
    manifest_path = bundle_root / "bundle-manifest.json"
    if not manifest_path.is_file():
        fail("CORPUS_NOT_APPROVED", "The pinned corpus bundle has no manifest")
    manifest_value = parse_json_bytes(
        manifest_path.read_bytes(), label="corpus manifest"
    )
    manifest = manifest_value if isinstance(manifest_value, dict) else {}
    if manifest.get("approval_status") != "approved":
        fail("CORPUS_NOT_APPROVED", "The pinned corpus bundle is not approved")
    if manifest.get("case_id") != request.case_id:
        fail("IDENTITY_MISMATCH", "The corpus bundle belongs to another case")
    inventory = manifest.get("inventory") or {}
    if inventory.get("corpus.json") != request.corpus_sha256:
        fail("HASH_MISMATCH", "Corpus manifest does not bind the pinned bytes")
    corpus_value = parse_json_bytes(corpus_bytes, label="corpus")
    corpus = corpus_value if isinstance(corpus_value, dict) else {}
    records = corpus.get("records")
    if not isinstance(records, list):
        fail("CORPUS_INVALID", "The pinned corpus has no records")
    return {
        "path": request.corpus,
        "sha256": request.corpus_sha256,
        "case_id": manifest.get("case_id"),
        "record_count": len(records),
        "versions": manifest.get("versions"),
        "bundle_content_sha256": manifest.get("bundle_content_sha256"),
    }


def _check_credential_presence() -> None:
    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        fail("MISSING_CREDENTIAL", "DEEPSEEK_API_KEY is not set in the environment")


def _request_cost_approval(
    stream: TextIO, estimate: pricing.CostBreakdown, *, interactive: bool
) -> dict[str, Any]:
    """Show the worst-case CNY bound and require an exact `yes` confirmation."""
    print(
        f"Planned paid work under model {DEEPSEEK_MODEL_ID} at {DEEPSEEK_BASE_URL}.",
        file=stream,
    )
    print(
        "Worst-case bound (peak rates, all cache miss, declared budgets, "
        f"<= {MAX_ATTEMPTS_PER_OPERATION} attempts per operation):",
        file=stream,
    )
    print(
        f"  input  (cache miss): {estimate.cache_miss_cost_cny} CNY",
        file=stream,
    )
    print(f"  output             : {estimate.output_cost_cny} CNY", file=stream)
    print(f"  total upper bound  : {estimate.total_cny} CNY", file=stream)
    print("Approve this run's paid work? Type `yes` to confirm:", file=stream)
    if not interactive:
        fail("APPROVAL_UNAVAILABLE", "Cost approval requires an interactive session")
    try:
        answer = input()
    except EOFError:
        fail("APPROVAL_REJECTED", "Cost approval was not confirmed")
    if answer != "yes":
        fail("APPROVAL_REJECTED", "Cost approval was not confirmed")
    return {
        "approved_at": _now(),
        "confirmed_with": "yes",
        "total_upper_bound_cny": str(estimate.total_cny),
    }


def admit_new_run(
    workspace_root: Path,
    request: NewRunRequest,
    *,
    stream: TextIO | None = None,
    interactive: bool = True,
) -> dict[str, Any]:
    """Run the nine-step preflight; return the admission result.

    Any failure raises a typed IdeationInputError after recording the
    preflight rejection evidence; no model request can occur here.
    """
    import sys

    stream = stream if stream is not None else sys.stdout
    workspace = workspace_root.resolve(strict=True)
    store = RunStore(workspace)

    run = store.create_run()
    request_document = request.document(run.run_id)
    request_sha = store.write_request(run.run_id, request_document)
    store.append_event(
        run.run_id,
        {
            "event_type": "preflight_started",
            "payload": {"steps": 9},
            "request_sha256": request_sha,
        },
    )

    try:
        return _run_preflight_steps(
            store, run, request, request_sha, workspace, stream, interactive
        )
    except IdeationInputError as exc:
        preflight_rejected(store, run.run_id, exc.code, exc.message)
        raise


def _run_preflight_steps(
    store: RunStore,
    run: Any,
    request: NewRunRequest,
    request_sha: str,
    workspace: Path,
    stream: TextIO,
    interactive: bool,
) -> dict[str, Any]:
    # Step 3: clean worktree and exact commit.
    commit_sha = _require_clean_worktree(workspace)
    _append_step(store, run.run_id, "clean_worktree", "pass", {"commit": commit_sha})

    # Step 4: Approved Workshop.
    workshop = _load_approved_workshop(workspace, request)
    _append_step(store, run.run_id, "workshop_approval", "pass", workshop)

    # Step 5: Approved Corpus.
    corpus = _load_approved_corpus(workspace, request)
    _append_step(store, run.run_id, "corpus_approval", "pass", corpus)

    # Step 6: bind the retriever to the one approved corpus (no model call).
    bound = bind_corpus(
        workspace,
        corpus_relpath=corpus["path"],
        corpus_sha256=corpus["sha256"],
        case_id=corpus["case_id"],
        record_count=corpus["record_count"],
    )
    _append_step(
        store,
        run.run_id,
        "retriever_binding",
        "pass",
        {"policy_version": bound.policy_version},
    )

    # Step 7: credential presence (value never read or recorded).
    _check_credential_presence()
    _append_step(store, run.run_id, "credential_presence", "pass")

    # Step 8: conservative cost bound and explicit approval.
    price_table = pricing.load_price_table(workspace)
    estimate = pricing.worst_case_bound(
        price_table,
        input_tokens=request.max_num_generations
        * request.num_reflections
        * _WORST_CASE_INPUT_TOKENS_PER_ROUND,
        output_tokens=request.max_num_generations
        * request.num_reflections
        * DEFAULT_MAX_TOKENS,
        attempts=MAX_ATTEMPTS_PER_OPERATION,
    )
    approval = _request_cost_approval(stream, estimate, interactive=interactive)
    _append_step(
        store,
        run.run_id,
        "cost_approval",
        "pass",
        {
            "total_upper_bound_cny": str(estimate.total_cny),
            "price_table_sha256": price_table.sha256,
        },
    )

    # Step 9: write the Run Admission; paid work may only follow this.
    admission_document = {
        "schema_version": RUN_ADMISSION_SCHEMA,
        "run_id": run.run_id,
        "admitted_at": _now(),
        "case_id": request.case_id,
        "request_sha256": request_sha,
        "code": {"commit": commit_sha},
        "workshop": workshop,
        "corpus": corpus,
        "retriever": {"policy_version": bound.policy_version},
        "model": {
            "provider": "deepseek",
            "base_url": DEEPSEEK_BASE_URL,
            "model_id": DEEPSEEK_MODEL_ID,
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "max_attempts_per_operation": MAX_ATTEMPTS_PER_OPERATION,
        },
        "price_table": {
            "sha256": price_table.sha256,
            "version": price_table.document["schema_version"],
        },
        "cost": {
            "currency": "CNY",
            "worst_case": {
                "input_tokens": request.max_num_generations
                * request.num_reflections
                * _WORST_CASE_INPUT_TOKENS_PER_ROUND,
                "output_tokens": request.max_num_generations
                * request.num_reflections
                * DEFAULT_MAX_TOKENS,
                "attempts": MAX_ATTEMPTS_PER_OPERATION,
                "total_cny": str(estimate.total_cny),
            },
            "approval": approval,
        },
        "budgets": {
            "max_num_generations": request.max_num_generations,
            "num_reflections": request.num_reflections,
        },
    }
    admission_sha = store.write_admission(run.run_id, admission_document)
    store.append_event(
        run.run_id,
        {
            "event_type": "admitted",
            "payload": {},
            "admission_sha256": admission_sha,
        },
    )
    return {
        "status": "admitted",
        "run_id": run.run_id,
        "admission_sha256": admission_sha,
        "worst_case_cny": str(estimate.total_cny),
    }


# Declared worst-case input per model round. The workshop file, prompts and
# history sizes are bounded artifacts; this constant is the pinned policy
# value recorded in the admission document.
_WORST_CASE_INPUT_TOKENS_PER_ROUND = 32_768


def preflight_rejected(
    store: RunStore,
    run_id: str,
    error_code: str,
    message: str,
) -> None:
    """Record a preflight rejection event for auditability."""
    store.append_event(
        run_id,
        {
            "event_type": "preflight_rejected",
            "payload": {"error_code": error_code, "message": message},
        },
    )
