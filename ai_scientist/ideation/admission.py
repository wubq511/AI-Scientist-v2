"""Nine-step fail-closed new-run preflight and Run Admission (ticket 04).

The preflight sequence is fixed by the safe-entry contract: request schema,
run creation, clean worktree, Approved Workshop, Approved Corpus, bound
retriever, credential presence, explicit cost approval, then the write-once
Run Admission. No model request may precede admission; any step failure
marks the run preflight-rejected with retained request and event evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, TextIO

from . import profiles as prompt_profiles
from . import pricing
from .canonical import parse_json_bytes, sha256_bytes, workspace_relative_path
from .contract import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL_ID,
    DEFAULT_REASONING_EFFORT,
    MAX_ATTEMPTS_PER_OPERATION,
    _now,
)
from .errors import IdeationInputError, fail
from .profiles import resolve_profile as _resolve_request_profile
from .retrieval import bind_corpus
from .run_store import (
    RUN_ADMISSION_SCHEMA_VERSION,
    RUN_REQUEST_SCHEMA_VERSION,
    RunHandle,
    RunStore,
)
from .schema import case_id as parse_case_id
from .schema import positive_integer, sha256 as parse_sha256

# Canary-open parameters (tickets 035/036) exposed as pinned defaults; the
# admission records them so a Run Specification stays immutable.
DEFAULT_MAX_TOKENS = 32768
# Declared worst-case input tokens per model round. The workshop file,
# prompts, and history sizes are bounded artifacts; this constant is the
# pinned policy value recorded in the admission document.
WORST_CASE_INPUT_TOKENS_PER_ROUND = 32_768

WORKSHOP_MANIFEST_NAME = "workshop-manifest.json"
CORPUS_MANIFEST_NAME = "bundle-manifest.json"
CORPUS_VALIDATION_REPORT_NAME = "validation-report.json"


@dataclass(frozen=True, slots=True)
class NewRunRequest:
    case_id: str
    workshop: str
    workshop_sha256: str
    corpus: str
    corpus_sha256: str
    max_num_generations: int
    num_reflections: int
    prompt_profile_id: str = prompt_profiles.DEFAULT_PROMPT_PROFILE_ID

    def validate(self) -> None:
        """Step 1: closed request schema (a failure is a run-external error)."""
        parse_case_id(self.case_id)
        parse_sha256(self.workshop_sha256, label="workshop_sha256")
        parse_sha256(self.corpus_sha256, label="corpus_sha256")
        positive_integer(self.max_num_generations, label="max_num_generations")
        positive_integer(self.num_reflections, label="num_reflections")
        # Closed Prompt Profile resolution: only registered ids are accepted;
        # free text, paths, fragments and unknown ids fail closed here.
        _resolve_request_profile(self.prompt_profile_id)
        for path_field, label in [(self.workshop, "workshop"), (self.corpus, "corpus")]:
            if not isinstance(path_field, str) or not path_field:
                fail("INVALID_PATH", f"{label} path must be a non-empty string")
            if (
                path_field.startswith("artifacts/ideation-runs/")
                or path_field.startswith("evidence/ideation-runs/")
                or "/ideation-runs/" in path_field
            ):
                fail(
                    "CROSS_RUN_INPUT_FORBIDDEN",
                    f"Prior run evidence cannot be used as {label} runtime input: {path_field}",
                )

    def prompt_profile_field(self) -> dict[str, Any]:
        """Return the closed profile pin field for the request/admission docs."""
        profile = _resolve_request_profile(self.prompt_profile_id)
        return {
            "bundle_sha256": prompt_profiles.profile_bundle_sha256(profile),
            "contract_version": profile.contract_version,
            "profile_id": profile.profile_id,
            "registry_sha256": prompt_profiles.profile_registry_sha256(),
        }

    def document(self, run_id: str, command: list[str]) -> dict[str, Any]:
        return {
            "schema_version": RUN_REQUEST_SCHEMA_VERSION,
            "run_id": run_id,
            "requested_at": _now(),
            "case_id": self.case_id,
            "command": list(command),
            "prompt_profile": self.prompt_profile_field(),
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


def _read_pinned_input(
    workspace_root: Path, relpath: str, expected_sha256: str, *, label: str
) -> tuple[Path, bytes]:
    """Resolve a pinned input through the guarded path boundary and hash it."""
    if (
        relpath.startswith("artifacts/ideation-runs/")
        or relpath.startswith("evidence/ideation-runs/")
        or "/ideation-runs/" in relpath
    ):
        fail(
            "CROSS_RUN_INPUT_FORBIDDEN",
            f"Prior run evidence cannot be used as {label} runtime input: {relpath}",
        )
    path = workspace_relative_path(workspace_root, relpath, label=f"{label}_path")
    if not path.is_file():
        fail(f"MISSING_{label.upper()}", f"The pinned {label} is missing")
    data = path.read_bytes()
    if sha256_bytes(data) != expected_sha256:
        fail(
            "HASH_MISMATCH",
            f"{label.capitalize()} bytes do not match the requested SHA-256",
            expected=expected_sha256,
        )
    return path, data


def _mapping_field(value: object, *, label: str) -> dict[str, Any]:
    """Return a JSON object field or fail closed with a typed error."""
    if not isinstance(value, dict):
        fail("INVALID_SCHEMA", f"{label} must be a JSON object")
    return value


def _load_approved_workshop(
    workspace_root: Path, request: NewRunRequest
) -> dict[str, Any]:
    """Verify the pinned Workshop: exact hash, approval status, case binding."""
    workshop_path, workshop_bytes = _read_pinned_input(
        workspace_root,
        request.workshop,
        request.workshop_sha256,
        label="workshop",
    )
    manifest_path = workshop_path.parent / WORKSHOP_MANIFEST_NAME
    if not manifest_path.is_file():
        fail("WORKSHOP_NOT_APPROVED", "The pinned Workshop has no approval manifest")
    manifest_value = parse_json_bytes(
        manifest_path.read_bytes(), label="workshop manifest"
    )
    manifest = _mapping_field(manifest_value, label="workshop manifest")
    if manifest.get("approval_status") != "approved":
        fail("WORKSHOP_NOT_APPROVED", "The pinned Workshop is not approved")
    if manifest.get("case_id") != request.case_id:
        fail("IDENTITY_MISMATCH", "The Workshop belongs to another case")
    workshop_ref = _mapping_field(
        manifest.get("workshop"), label="workshop manifest.workshop"
    )
    if workshop_ref.get("sha256") != request.workshop_sha256:
        fail("HASH_MISMATCH", "Workshop manifest does not bind the pinned bytes")
    rules = _mapping_field(manifest.get("rules"), label="workshop manifest.rules")
    return {
        "path": request.workshop,
        "sha256": request.workshop_sha256,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "contract_version": manifest.get("contract_version"),
        "validator_version": rules.get("validator_version"),
        "schema_version": manifest.get("schema_version"),
    }


def _load_approved_corpus(
    workspace_root: Path, request: NewRunRequest
) -> dict[str, Any]:
    """Verify the pinned corpus bundle per the frozen-corpus contract."""
    corpus_path, corpus_bytes = _read_pinned_input(
        workspace_root,
        request.corpus,
        request.corpus_sha256,
        label="corpus",
    )
    bundle_root = corpus_path.parent
    manifest_path = bundle_root / CORPUS_MANIFEST_NAME
    if not manifest_path.is_file():
        fail("CORPUS_NOT_APPROVED", "The pinned corpus bundle has no manifest")
    manifest_value = parse_json_bytes(
        manifest_path.read_bytes(), label="corpus manifest"
    )
    manifest = _mapping_field(manifest_value, label="corpus manifest")
    if manifest.get("approval_status") != "approved":
        fail("CORPUS_NOT_APPROVED", "The pinned corpus bundle is not approved")
    if manifest.get("case_id") != request.case_id:
        fail("IDENTITY_MISMATCH", "The corpus bundle belongs to another case")
    inventory = _mapping_field(
        manifest.get("inventory"), label="corpus manifest.inventory"
    )
    if inventory.get("corpus.json") != request.corpus_sha256:
        fail("HASH_MISMATCH", "Corpus manifest does not bind the pinned bytes")
    if bundle_root.name != request.case_id:
        fail("IDENTITY_MISMATCH", "The corpus bundle is not case-named")
    # The validation report must exist and match the same bundle inventory.
    report_path = bundle_root / CORPUS_VALIDATION_REPORT_NAME
    if not report_path.is_file():
        fail("CORPUS_NOT_APPROVED", "The corpus bundle lacks its validation report")
    report_sha = sha256_bytes(report_path.read_bytes())
    if inventory.get(CORPUS_VALIDATION_REPORT_NAME) != report_sha:
        fail("HASH_MISMATCH", "The validation report does not match the bundle")
    report_value = parse_json_bytes(
        report_path.read_bytes(), label="corpus validation report"
    )
    report = _mapping_field(report_value, label="corpus validation report")
    if report.get("corpus_sha256") != request.corpus_sha256:
        fail("HASH_MISMATCH", "The validation report does not bind the corpus")
    if report.get("status") != "pass" or report.get("error_count") != 0:
        fail("CORPUS_NOT_APPROVED", "The corpus validation report is not a pass")
    corpus_value = parse_json_bytes(corpus_bytes, label="corpus")
    corpus = _mapping_field(corpus_value, label="corpus")
    records = corpus.get("records")
    if not isinstance(records, list):
        fail("CORPUS_INVALID", "The pinned corpus has no records")
    versions = _mapping_field(
        manifest.get("versions"), label="corpus manifest.versions"
    )
    if corpus.get("schema_version") != versions.get("schema"):
        fail("VERSION_MISMATCH", "The corpus schema version is inconsistent")
    return {
        "path": request.corpus,
        "sha256": request.corpus_sha256,
        "case_id": manifest.get("case_id"),
        "record_count": len(records),
        "versions": versions,
        "bundle_content_sha256": manifest.get("bundle_content_sha256"),
        "validation_report_sha256": report_sha,
    }


def _check_credential_presence() -> None:
    import os

    if not os.environ.get("DEEPSEEK_API_KEY"):
        fail("MISSING_CREDENTIAL", "DEEPSEEK_API_KEY is not set in the environment")


def _request_cost_approval(
    stream: TextIO, estimate: pricing.CostBreakdown
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
    import sys

    if not sys.stdin.isatty():
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
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Run the nine-step preflight; return the admission result.

    Any failure raises a typed IdeationInputError after recording the
    preflight rejection evidence; no model request can occur here.
    """
    import sys

    stream = stream if stream is not None else sys.stdout
    # Step 1: closed request schema; a failure stays a run-external error.
    request.validate()
    workspace = workspace_root.resolve(strict=True)
    store = RunStore(workspace)

    # Step 2: mint the run and write the canonical request.
    run = store.create_run()
    request_document = request.document(run.run_id, command or [])
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
        return _run_preflight_steps(store, run, request, request_sha, workspace, stream)
    except IdeationInputError as exc:
        preflight_rejected(store, run.run_id, exc.code, exc.message)
        raise
    except KeyboardInterrupt as exc:
        # The minted run stays unsealed and resumable (ticket 10): carry its
        # run_id on the interruption so the CLI suspension report can name it.
        exc.run_id = run.run_id  # type: ignore[attr-defined]
        raise


def _run_preflight_steps(
    store: RunStore,
    run: RunHandle,
    request: NewRunRequest,
    request_sha: str,
    workspace: Path,
    stream: TextIO,
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
        run_id=run.run_id,
        store=store,
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

    # Step 8: conservative cost bound and explicit approval. The default is
    # Robert's interactive per-run `yes`. Robert's write-once batch
    # preauthorization (comparison_preauthorization, pointed at by
    # COMPARISON_PREAUTHORIZATION) covers named frozen matrix slots instead;
    # a set-but-unreadable/non-covering variable fails closed rather than
    # silently falling back to prompting, and every approval record carries
    # its provenance verbatim.
    price_table = pricing.load_price_table(workspace)
    model_rounds = request.max_num_generations * request.num_reflections
    worst_case_input_tokens = model_rounds * WORST_CASE_INPUT_TOKENS_PER_ROUND
    worst_case_output_tokens = model_rounds * DEFAULT_MAX_TOKENS
    estimate = pricing.worst_case_bound(
        price_table,
        input_tokens=worst_case_input_tokens,
        output_tokens=worst_case_output_tokens,
        attempts=MAX_ATTEMPTS_PER_OPERATION,
    )
    from .comparison_preauthorization import (
        covering_preauthorization,
        preauthorization_admission_field,
    )

    authorization = covering_preauthorization(
        case_id=request.case_id,
        prompt_profile_id=request.prompt_profile_id,
        worst_case_bound_cny=str(estimate.total_cny),
    )
    if authorization is not None:
        approval = preauthorization_admission_field(authorization)
    else:
        approval = _request_cost_approval(stream, estimate)
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
        "schema_version": RUN_ADMISSION_SCHEMA_VERSION,
        "run_id": run.run_id,
        "admitted_at": _now(),
        "case_id": request.case_id,
        "request_sha256": request_sha,
        "code": {"commit": commit_sha},
        "prompt_profile": request.prompt_profile_field(),
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
                "input_tokens": worst_case_input_tokens,
                "output_tokens": worst_case_output_tokens,
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
    if stream is not None and getattr(stream, "isatty", lambda: False)():
        stream.write(
            f"\n  ✓ 费用已批准，Run 准入成功 (Run ID: {run.run_id}，Prompt Profile: {request.prompt_profile_id})，正在启动推理与检索控制循环...\n\n"
        )
        stream.flush()
    return {
        "prompt_profile": request.prompt_profile_id,
        "status": "admitted",
        "run_id": run.run_id,
        "admission_sha256": admission_sha,
        "worst_case_cny": str(estimate.total_cny),
    }


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
