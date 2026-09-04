import argparse
import os.path as osp
from pathlib import Path
import sys
from typing import Any

sys.path.append(osp.join(osp.dirname(__file__), ".."))
# Module-level imports stay standard-library only. The ideation-only import
# closure is pinned by tests/test_ideation_import_contract.py; legacy provider
# and literature-search modules stay in retained code outside this entry
# (ticket 13 contracted the legacy subcommand out of this file).


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
    # No subcommand: print the same help text and exit like --help.
    _parser.print_help()
    raise SystemExit(0)
