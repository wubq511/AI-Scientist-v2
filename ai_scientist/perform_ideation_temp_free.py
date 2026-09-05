import argparse
import os.path as osp
from pathlib import Path
import sys
from typing import Any

sys.path.append(osp.join(osp.dirname(__file__), ".."))
# Module-level imports stay standard-library only. The ideation-only import
# closure is pinned by tests/test_ideation_import_contract.py; legacy provider
# and literature-search modules stay in retained code outside this entry
# (ticket 13 contracted the legacy subcommand out of this file). Since ticket
# 01 the new-run entry also carries the closed --prompt-profile id; free
# prompt text, paths, and unregistered ids fail closed in Run Admission.


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate AI scientist proposals - template free"
    )
    subparsers = parser.add_subparsers(dest="entry")

    # Safe ideation entry: request, nine-step preflight, cost approval, and
    # Run Admission. No model, ranker, device, output-root, or resume control.
    new_run = subparsers.add_parser(
        "new-run", help="Admit one Ideation Run without any paid work."
    )
    new_run.add_argument("--case-id", required=True)
    new_run.add_argument("--workshop", required=True)
    new_run.add_argument("--workshop-sha256", required=True)
    new_run.add_argument("--corpus", required=True)
    new_run.add_argument("--corpus-sha256", required=True)
    new_run.add_argument("--max-num-generations", type=int, required=True)
    new_run.add_argument("--num-reflections", type=int, required=True)
    new_run.add_argument(
        "--prompt-profile",
        required=True,
        metavar="PROFILE_ID",
        help="Closed, versioned Prompt Profile id: ml-baseline-v1 or cross-domain-v1.",
    )

    # Resume entry: continue one suspended Ideation Run; exact run_id only
    # (ticket 10). No other control surface is accepted.
    resume = subparsers.add_parser(
        "resume", help="Resume one suspended Ideation Run by its exact run_id."
    )
    resume.add_argument("--run-id", required=True)

    # Validate entry: verify a sealed Evidence Chain; exact run_id only (ticket 11).
    validate = subparsers.add_parser(
        "validate", help="Validate one sealed Evidence Chain by its exact run_id."
    )
    validate.add_argument("--run-id", required=True)

    # Export entry: export sanitized evidence; exact run_id only (ticket 11).
    export = subparsers.add_parser(
        "export", help="Export sanitized evidence for one sealed Ideation Run."
    )
    export.add_argument("--run-id", required=True)

    # Evaluation entries: post-seal qualitative Evaluation Artifacts (ticket 12).
    evaluation = subparsers.add_parser(
        "evaluation",
        help="Post-seal qualitative evaluation of finalized ideas (private).",
    )
    evaluation_actions = evaluation.add_subparsers(
        dest="evaluation_action", required=True
    )
    ev_assemble = evaluation_actions.add_parser(
        "assemble",
        help="Assemble the private Evaluation Brief and draft skeleton.",
    )
    ev_assemble.add_argument("--run-id", required=True)
    ev_assemble.add_argument("--idea-index", type=int, required=True)
    ev_assemble.add_argument("--assembled-by", required=True)
    ev_validate = evaluation_actions.add_parser(
        "validate",
        help="Validate an authored draft into an immutable Evaluation Artifact.",
    )
    ev_validate.add_argument("--run-id", required=True)
    ev_validate.add_argument("--idea-index", type=int, required=True)
    ev_validate.add_argument("--validated-by", required=True)
    evaluation_actions.add_parser(
        "list-coverage",
        help="Read-only evaluation coverage over the seal inventory.",
    )
    ev_export_review = evaluation_actions.add_parser(
        "export-review-package",
        help="Export the anonymous AI review package and ready-to-send request.",
    )
    ev_export_review.add_argument("--run-id", required=True)
    ev_export_review.add_argument("--idea-index", type=int, required=True)
    ev_import_review = evaluation_actions.add_parser(
        "import-review-response",
        help="Import one operator-supplied AI review response (write-once).",
    )
    ev_import_review.add_argument("--run-id", required=True)
    ev_import_review.add_argument("--idea-index", type=int, required=True)
    ev_import_review.add_argument("--response-file", required=True)
    ev_import_review.add_argument("--provider", required=True)
    ev_import_review.add_argument("--model-id", required=True)
    ev_import_review.add_argument("--responded-at", required=True)
    ev_import_review.add_argument("--supplied-by", required=True)
    ev_import_review.add_argument("--imported-by", required=True)
    ev_import_review.add_argument(
        "--evaluator-slot",
        default="primary",
        choices=["primary", "second"],
        help="Which evaluator slot this response belongs to (isolated contexts).",
    )
    ev_validate_review = evaluation_actions.add_parser(
        "validate-review",
        help="Validate the latest imported response into an immutable AI review record and evidence card.",
    )
    ev_validate_review.add_argument("--run-id", required=True)
    ev_validate_review.add_argument("--idea-index", type=int, required=True)
    ev_validate_review.add_argument(
        "--evaluator-slot",
        default="primary",
        choices=["primary", "second"],
    )
    ev_register_config = evaluation_actions.add_parser(
        "register-review-config",
        help="Register the write-once review execution config (two distinct-family evaluators).",
    )
    ev_register_config.add_argument("--config-file", required=True)
    ev_aggregate_review = evaluation_actions.add_parser(
        "aggregate-review",
        help="Merge both evaluator slots' validated records into a dual-review consensus record and card.",
    )
    ev_aggregate_review.add_argument("--run-id", required=True)
    ev_aggregate_review.add_argument("--idea-index", type=int, required=True)
    ev_export_pair = evaluation_actions.add_parser(
        "export-pair-package",
        help="Export the anonymous two-arm pair package and both direction requests.",
    )
    ev_export_pair.add_argument("--run-id-a", required=True)
    ev_export_pair.add_argument("--idea-index-a", type=int, required=True)
    ev_export_pair.add_argument("--run-id-b", required=True)
    ev_export_pair.add_argument("--idea-index-b", type=int, required=True)
    ev_import_pair = evaluation_actions.add_parser(
        "import-pair-response",
        help="Import one operator-supplied pair review response (write-once, per slot/direction).",
    )
    ev_import_pair.add_argument("--pair-id", required=True)
    ev_import_pair.add_argument(
        "--evaluator-slot", required=True, choices=["primary", "second"]
    )
    ev_import_pair.add_argument("--direction", required=True, choices=["ab", "ba"])
    ev_import_pair.add_argument("--response-file", required=True)
    ev_import_pair.add_argument("--provider", required=True)
    ev_import_pair.add_argument("--model-id", required=True)
    ev_import_pair.add_argument("--responded-at", required=True)
    ev_import_pair.add_argument("--supplied-by", required=True)
    ev_import_pair.add_argument("--imported-by", required=True)
    ev_validate_pair = evaluation_actions.add_parser(
        "validate-pair-review",
        help="Validate one slot/direction pair response into an immutable pair review record.",
    )
    ev_validate_pair.add_argument("--pair-id", required=True)
    ev_validate_pair.add_argument(
        "--evaluator-slot", required=True, choices=["primary", "second"]
    )
    ev_validate_pair.add_argument("--direction", required=True, choices=["ab", "ba"])
    ev_reduce_pair = evaluation_actions.add_parser(
        "reduce-pair-review",
        help="Restore anonymous content across the four pair reviews into a stable result or incomparable.",
    )
    ev_reduce_pair.add_argument("--pair-id", required=True)
    return parser


def run_new_run(
    workspace_root: Path,
    request: Any,
    *,
    command: list[str] | None = None,
    stream: Any = None,
    adapter: Any = None,
    retriever: Any = None,
    store: Any = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Admit and optionally execute an Ideation Run with injected components."""
    from ai_scientist.ideation.admission import admit_new_run

    admission_result = admit_new_run(
        workspace_root,
        request,
        stream=stream,
        command=command,
    )
    if not execute:
        return admission_result

    from ai_scientist.ideation.controller import IdeationController

    progress_stream = stream
    if progress_stream is None and sys.stderr.isatty():
        progress_stream = sys.stderr

    controller = IdeationController(
        workspace_root,
        admission_result["run_id"],
        store=store,
        adapter=adapter,
        retriever=retriever,
        progress_stream=progress_stream,
    )
    return controller.run()


def _suspended_payload(run_id: str | None, code: str, message: str) -> dict[str, Any]:
    """Uniform suspend report: the run stays unsealed and resumable."""
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "status": "suspended",
    }
    if run_id is not None:
        payload["run_id"] = run_id
    return payload


def _run_new_run(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
    stream: Any = None,
    adapter: Any = None,
    retriever: Any = None,
    store: Any = None,
    execute: bool | None = None,
) -> int:
    from ai_scientist.ideation.admission import NewRunRequest, admit_new_run
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.deepseek import ModelRoundError
    from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted

    root = workspace_root or Path.cwd()
    request = NewRunRequest(
        case_id=args.case_id,
        workshop=args.workshop,
        workshop_sha256=args.workshop_sha256,
        corpus=args.corpus,
        corpus_sha256=args.corpus_sha256,
        max_num_generations=args.max_num_generations,
        num_reflections=args.num_reflections,
        prompt_profile_id=args.prompt_profile,
    )
    # Production CLI executes by default after admission (ticket 01);
    # tests and library callers may still pass execute=False.
    if execute is None:
        execute = True

    command = [
        "python",
        "ai_scientist/perform_ideation_temp_free.py",
        "new-run",
        "--case-id",
        args.case_id,
        "--workshop",
        args.workshop,
        "--workshop-sha256",
        args.workshop_sha256,
        "--corpus",
        args.corpus,
        "--corpus-sha256",
        args.corpus_sha256,
        "--max-num-generations",
        str(args.max_num_generations),
        "--num-reflections",
        str(args.num_reflections),
        "--prompt-profile",
        args.prompt_profile,
    ]

    # Admission phase: failures are preflight rejections (exit 2).
    try:
        admission_result = admit_new_run(
            root,
            request,
            stream=stream,
            command=command,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "preflight_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 2
    except KeyboardInterrupt as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(
                    getattr(exc, "run_id", None),
                    "KEYBOARD_INTERRUPT",
                    "Interrupted during admission",
                )
            )
        )
        return 3

    if not execute:
        sys.stdout.buffer.write(canonical_json_bytes(admission_result))
        return 0

    # Execution phase: suspend-class failures leave the run unsealed and
    # resumable (exit 3); terminal outcomes seal and return normally.
    run_id = admission_result["run_id"]
    try:
        from ai_scientist.ideation.controller import IdeationController

        progress_stream = stream
        if progress_stream is None and sys.stderr.isatty():
            progress_stream = sys.stderr

        controller = IdeationController(
            root,
            run_id,
            store=store,
            adapter=adapter,
            retriever=retriever,
            progress_stream=progress_stream,
        )
        result = controller.run()
    except IdeationInputError as exc:
        if exc.code != "STORAGE_WRITE_FAILED":
            raise
        sys.stdout.buffer.write(
            canonical_json_bytes(_suspended_payload(run_id, exc.code, exc.message))
        )
        return 3
    except ModelRoundError as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(_suspended_payload(run_id, exc.code, str(exc)))
        )
        return 3
    except RunInterrupted as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(run_id, "RUN_INTERRUPTED", str(exc))
            )
        )
        return 3
    except KeyboardInterrupt:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(
                    run_id, "KEYBOARD_INTERRUPT", "Interrupted during execution"
                )
            )
        )
        return 3
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_resume(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
    stream: Any = None,
    adapter: Any = None,
    retriever: Any = None,
    store: Any = None,
) -> int:
    """Resume a suspended run: exit 0 sealed, 2 resume_rejected, 3 suspended."""
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.deepseek import ModelRoundError
    from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted
    from ai_scientist.ideation.resume import resume_run

    root = workspace_root or Path.cwd()
    try:
        result = resume_run(
            root,
            args.run_id,
            stream=stream,
            adapter=adapter,
            retriever=retriever,
            store=store,
        )
    except IdeationInputError as exc:
        if exc.code == "STORAGE_WRITE_FAILED":
            sys.stdout.buffer.write(
                canonical_json_bytes(
                    _suspended_payload(args.run_id, exc.code, exc.message)
                )
            )
            return 3
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "resume_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 2
    except ModelRoundError as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(_suspended_payload(args.run_id, exc.code, str(exc)))
        )
        return 3
    except RunInterrupted as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(args.run_id, "RUN_INTERRUPTED", str(exc))
            )
        )
        return 3
    except KeyboardInterrupt:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(
                    args.run_id, "KEYBOARD_INTERRUPT", "Interrupted during resume"
                )
            )
        )
        return 3
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_validate(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Validate a sealed run: exit 0 valid, 1 corrupt/error."""
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evidence import validate_evidence_chain

    root = workspace_root or Path.cwd()
    try:
        result = validate_evidence_chain(root, args.run_id, check_sealed=True)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "corrupt" if exc.code == "RUN_CORRUPT" else "error",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_export(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Export sanitized evidence: exit 0 exported, 1 corrupt/rejected."""
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evidence import export_sanitized_evidence

    root = workspace_root or Path.cwd()
    try:
        result = export_sanitized_evidence(root, args.run_id)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "export_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_assemble(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Assemble the Evaluation Brief and draft skeleton: exit 0 assembled, 1 rejected."""
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evaluation import assemble_evaluation_brief

    root = workspace_root or Path.cwd()
    try:
        result = assemble_evaluation_brief(
            root,
            args.run_id,
            args.idea_index,
            assembled_by=args.assembled_by,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "assemble_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_validate(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Validate an authored draft: exit 0 validated, 1 rejected (draft kept)."""
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evaluation import validate_evaluation_artifact

    root = workspace_root or Path.cwd()
    try:
        result = validate_evaluation_artifact(
            root,
            args.run_id,
            args.idea_index,
            validated_by=args.validated_by,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "validation_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_export_review_package(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Export the AI review package: exit 0 exported, 1 rejected."""
    from ai_scientist.ideation.ai_review import export_review_package
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = export_review_package(root, args.run_id, args.idea_index)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "export_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_import_review_response(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Import a review response: exit 0 imported, 1 rejected/invalid format.

    An unparseable response is still retained on disk; the failure report
    names the stored file so the raw input stays auditable.
    """
    from ai_scientist.ideation.ai_review import import_review_response
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = import_review_response(
            root,
            args.run_id,
            args.idea_index,
            response_path=Path(args.response_file),
            evaluator_slot=args.evaluator_slot,
            provider=args.provider,
            model_id=args.model_id,
            responded_at=args.responded_at,
            supplied_by=args.supplied_by,
            imported_by=args.imported_by,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "import_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0 if result["parse_status"] == "ok" else 1


def _run_evaluation_validate_review(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Validate the latest imported response: exit 0 validated, 1 rejected."""
    from ai_scientist.ideation.ai_review import validate_ai_review
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = validate_ai_review(
            root, args.run_id, args.idea_index, evaluator_slot=args.evaluator_slot
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "review_validation_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_register_review_config(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Register the write-once review execution config: exit 0 registered, 1 rejected."""
    from ai_scientist.ideation.ai_review import register_review_config
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = register_review_config(root, Path(args.config_file))
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "config_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_aggregate_review(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Merge both evaluator slots into a consensus record: exit 0 aggregated, 1 rejected."""
    from ai_scientist.ideation.ai_review import aggregate_review
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = aggregate_review(root, args.run_id, args.idea_index)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "aggregation_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_export_pair_package(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Export the anonymous pair package: exit 0 exported, 1 rejected."""
    from ai_scientist.ideation.ai_pair_review import export_pair_package
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = export_pair_package(
            root,
            args.run_id_a,
            args.idea_index_a,
            args.run_id_b,
            args.idea_index_b,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "export_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_import_pair_response(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Import one pair response: exit 0 imported, 1 rejected/invalid format.

    An unparseable response is still retained on disk under its slot and
    direction; the failure report names the stored file.
    """
    from ai_scientist.ideation.ai_pair_review import import_pair_response
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = import_pair_response(
            root,
            args.pair_id,
            args.evaluator_slot,
            args.direction,
            response_path=Path(args.response_file),
            provider=args.provider,
            model_id=args.model_id,
            responded_at=args.responded_at,
            supplied_by=args.supplied_by,
            imported_by=args.imported_by,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "pair_id": args.pair_id,
            "status": "import_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0 if result["parse_status"] == "ok" else 1


def _run_evaluation_validate_pair_review(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Validate one slot/direction pair response: exit 0 validated, 1 rejected."""
    from ai_scientist.ideation.ai_pair_review import validate_pair_review
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = validate_pair_review(
            root, args.pair_id, args.evaluator_slot, args.direction
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "pair_id": args.pair_id,
            "status": "pair_validation_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_reduce_pair_review(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Reduce the four pair reviews into a stable result: exit 0 reduced, 1 rejected."""
    from ai_scientist.ideation.ai_pair_review import reduce_pair_review
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError

    root = workspace_root or Path.cwd()
    try:
        result = reduce_pair_review(root, args.pair_id)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "pair_id": args.pair_id,
            "status": "reduction_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_evaluation_list_coverage(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Read-only evaluation coverage over the seal inventory: exit 0 reported."""
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evaluation import list_evaluation_coverage

    root = workspace_root or Path.cwd()
    try:
        result = list_evaluation_coverage(root)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "error",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    _parser = _build_parser()
    _args = _parser.parse_args()
    if _args.entry == "new-run":
        raise SystemExit(_run_new_run(_args))
    if _args.entry == "resume":
        raise SystemExit(_run_resume(_args))
    if _args.entry == "validate":
        raise SystemExit(_run_validate(_args))
    if _args.entry == "export":
        raise SystemExit(_run_export(_args))
    if _args.entry == "evaluation":
        if _args.evaluation_action == "assemble":
            raise SystemExit(_run_evaluation_assemble(_args))
        if _args.evaluation_action == "validate":
            raise SystemExit(_run_evaluation_validate(_args))
        if _args.evaluation_action == "list-coverage":
            raise SystemExit(_run_evaluation_list_coverage(_args))
        if _args.evaluation_action == "export-review-package":
            raise SystemExit(_run_evaluation_export_review_package(_args))
        if _args.evaluation_action == "import-review-response":
            raise SystemExit(_run_evaluation_import_review_response(_args))
        if _args.evaluation_action == "validate-review":
            raise SystemExit(_run_evaluation_validate_review(_args))
        if _args.evaluation_action == "register-review-config":
            raise SystemExit(_run_evaluation_register_review_config(_args))
        if _args.evaluation_action == "aggregate-review":
            raise SystemExit(_run_evaluation_aggregate_review(_args))
        if _args.evaluation_action == "export-pair-package":
            raise SystemExit(_run_evaluation_export_pair_package(_args))
        if _args.evaluation_action == "import-pair-response":
            raise SystemExit(_run_evaluation_import_pair_response(_args))
        if _args.evaluation_action == "validate-pair-review":
            raise SystemExit(_run_evaluation_validate_pair_review(_args))
        if _args.evaluation_action == "reduce-pair-review":
            raise SystemExit(_run_evaluation_reduce_pair_review(_args))
    # No subcommand: print the same help text and exit like --help.
    _parser.print_help()
    raise SystemExit(0)
