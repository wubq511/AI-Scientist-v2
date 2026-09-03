from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from ai_scientist.ideation.canonical import canonical_json_bytes
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.workshop import (
    approve_workshop,
    prepare_workshop,
    validate_workshop,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and approve private ideation inputs without model calls."
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root containing source data and private artifacts.",
    )
    inputs = parser.add_subparsers(dest="input_kind", required=True)
    workshop = inputs.add_parser("workshop", help="Prepare one Workshop File.")
    actions = workshop.add_subparsers(dest="action", required=True)

    prepare = actions.add_parser(
        "prepare", help="Create the allowlisted Workshop authoring source."
    )
    prepare.add_argument("--case-id", required=True)
    prepare.add_argument("--target-paper-id", required=True)
    prepare.add_argument("--preparation-id", required=True)
    prepare.add_argument("--source-root", default="data/raw")
    prepare.add_argument("--artifact-root", default="artifacts/ideation-inputs")
    prepare.add_argument("--prepared-by", default="codex")

    validate = actions.add_parser(
        "validate", help="Record and deterministically validate one candidate."
    )
    validate.add_argument("--preparation-manifest", required=True)
    validate.add_argument("--attempt-id", required=True)
    validate.add_argument("--candidate", required=True)
    validate.add_argument("--derivation-record", required=True)

    approve = actions.add_parser(
        "approve", help="Apply an independent semantic review decision."
    )
    approve.add_argument("--attempt-manifest", required=True)
    approve.add_argument("--semantic-decision", required=True)
    return parser


def _execute(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(arguments.workspace_root)
    if arguments.input_kind != "workshop":
        raise AssertionError("argparse admitted an unsupported input kind")
    if arguments.action == "prepare":
        return prepare_workshop(
            workspace,
            case_id=arguments.case_id,
            target_paper_id=arguments.target_paper_id,
            preparation_id=arguments.preparation_id,
            source_root=arguments.source_root,
            artifact_root=arguments.artifact_root,
            prepared_by=arguments.prepared_by,
        )
    if arguments.action == "validate":
        return validate_workshop(
            workspace,
            preparation_manifest=arguments.preparation_manifest,
            attempt_id=arguments.attempt_id,
            candidate=arguments.candidate,
            derivation_record=arguments.derivation_record,
        )
    if arguments.action == "approve":
        return approve_workshop(
            workspace,
            attempt_manifest=arguments.attempt_manifest,
            semantic_decision=arguments.semantic_decision,
        )
    raise AssertionError("argparse admitted an unsupported Workshop action")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = _execute(arguments)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "error",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    if result.get("status") in {"rejected_deterministic", "rejected_semantic"}:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
