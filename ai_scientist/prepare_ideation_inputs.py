from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from ai_scientist.ideation.canonical import canonical_json_bytes
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.corpus import (
    approve_corpus,
    build_corpus,
    validate_all_corpora,
    validate_corpus,
)
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

    corpus = inputs.add_parser(
        "corpus", help="Prepare, validate, and approve Target Reference Corpora."
    )
    corpus_actions = corpus.add_subparsers(dest="action", required=True)

    build_c = corpus_actions.add_parser(
        "build", help="Build a canonical Target Reference Corpus bundle."
    )
    build_c.add_argument("--case-id", required=True)
    build_c.add_argument("--target-paper-id", required=True)
    build_c.add_argument("--build-id", required=True)
    build_c.add_argument("--source-root", default="data/raw")
    build_c.add_argument("--artifact-root", default="artifacts/ideation-inputs")
    build_c.add_argument("--authority-path", default=None)
    build_c.add_argument("--built-by", default="codex")

    validate_c = corpus_actions.add_parser(
        "validate", help="Deterministically validate a corpus bundle."
    )
    validate_c.add_argument("--bundle-path", required=True)

    approve_c = corpus_actions.add_parser(
        "approve", help="Apply Robert's approval to a corpus bundle."
    )
    approve_c.add_argument("--bundle-path", required=True)
    approve_c.add_argument("--approval-decision", required=True)

    validate_all = corpus_actions.add_parser(
        "validate-all",
        help="Validate all targets deterministically without model calls.",
    )
    validate_all.add_argument("--source-root", default="data/raw")
    validate_all.add_argument("--authority-path", default=None)

    return parser


def _execute(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(arguments.workspace_root)
    if arguments.input_kind == "workshop":
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

    if arguments.input_kind == "corpus":
        if arguments.action == "build":
            return build_corpus(
                workspace,
                case_id=arguments.case_id,
                target_paper_id=arguments.target_paper_id,
                build_id=arguments.build_id,
                source_root=arguments.source_root,
                artifact_root=arguments.artifact_root,
                authority_path=arguments.authority_path,
                built_by=arguments.built_by,
            )
        if arguments.action == "validate":
            return validate_corpus(
                workspace,
                bundle_path=arguments.bundle_path,
            )
        if arguments.action == "approve":
            return approve_corpus(
                workspace,
                bundle_path=arguments.bundle_path,
                approval_decision=arguments.approval_decision,
            )
        if arguments.action == "validate-all":
            return validate_all_corpora(
                workspace,
                source_root=arguments.source_root,
                authority_path=arguments.authority_path,
            )
        raise AssertionError("argparse admitted an unsupported Corpus action")

    raise AssertionError("argparse admitted an unsupported input kind")


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
