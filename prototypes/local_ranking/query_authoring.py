from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .canonical import sha256_bytes, write_json_once
from .errors import HarnessError, fail
from .formal_input import (
    OPERATIONAL_EXPECTED_CASE_IDS,
    QUERY_MANIFEST_SCHEMA_VERSION,
)
from .normalization import normalize_query

DRAFT_SCHEMA_VERSION = "local-ranking-operational-query-draft-v1.0"
PROMPT_MANIFEST_SCHEMA_VERSION = "local-ranking-operational-query-author-prompt-v1.0"
MIN_QUERY_SCALARS = 20
MAX_QUERY_SCALARS = 220
KIMI_TEXT_RENDERER_PREFIX = "\u2022 "
FORBIDDEN_QUERY_TERMS = ("bm25", "e5", "ranking", "target paper")


def _expect_keys(value: dict[str, Any], *, expected: set[str], label: str) -> None:
    if set(value) != expected:
        fail(
            "INVALID_QUERY_DRAFT",
            f"{label} has an invalid closed schema",
            missing=sorted(expected - set(value)),
            unknown=sorted(set(value) - expected),
        )


def _read_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_ARTIFACT", f"{label} is not readable JSON", error=str(exc))
    if not isinstance(value, dict):
        fail("INVALID_ARTIFACT", f"{label} must be an object")
    return value, data


def _parse_raw_response(data: bytes) -> tuple[dict[str, Any], bool]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(
            "INVALID_QUERY_DRAFT",
            "Raw query-author response is not UTF-8",
            offset=exc.start,
        )
    renderer_prefix_removed = text.startswith(KIMI_TEXT_RENDERER_PREFIX)
    if renderer_prefix_removed:
        text = text[len(KIMI_TEXT_RENDERER_PREFIX) :]
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_QUERY_DRAFT",
            "Raw query-author response is not one JSON object",
            line=exc.lineno,
            column=exc.colno,
        )
    if not isinstance(value, dict):
        fail("INVALID_QUERY_DRAFT", "Raw query-author response must be an object")
    return value, renderer_prefix_removed


def _validate_prompt_binding(
    *,
    prompt_manifest: dict[str, Any],
    prompt_bytes: bytes,
    packet_bytes: bytes,
    protocol_bytes: bytes,
) -> None:
    _expect_keys(
        prompt_manifest,
        expected={
            "case_count",
            "prompt_bytes",
            "prompt_sha256",
            "protocol_sha256",
            "query_author_packet_manifest_sha256",
            "schema_version",
            "status",
        },
        label="query-author prompt manifest",
    )
    expected = {
        "case_count": 12,
        "prompt_bytes": len(prompt_bytes),
        "prompt_sha256": sha256_bytes(prompt_bytes),
        "protocol_sha256": sha256_bytes(protocol_bytes),
        "query_author_packet_manifest_sha256": sha256_bytes(packet_bytes),
        "schema_version": PROMPT_MANIFEST_SCHEMA_VERSION,
        "status": "ready_for_fresh_isolated_author",
    }
    if prompt_manifest != expected:
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "Query-author prompt manifest does not bind the exact inputs",
        )


def _validate_source_binding(
    *,
    packet_manifest: dict[str, Any],
    packet_sha256: str,
    input_approval: dict[str, Any],
    protocol_sha256: str,
) -> dict[str, str]:
    workshops = packet_manifest.get("workshops")
    if not isinstance(workshops, list) or len(workshops) != 12:
        fail("INVALID_QUERY_DRAFT", "Query-author packet must contain 12 Workshops")
    packet_case_ids = tuple(
        item.get("case_id") if isinstance(item, dict) else None for item in workshops
    )
    if packet_case_ids != OPERATIONAL_EXPECTED_CASE_IDS:
        fail(
            "NON_CANONICAL_INPUT",
            "Query-author packet must use the frozen operational case order",
        )

    if input_approval.get("approval_status") != "approved":
        fail("APPROVAL_REQUIRED", "Operational input is not approved")
    approval_id = input_approval.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        fail("INVALID_ARTIFACT", "Input approval_id is missing")
    artifacts = input_approval.get("artifacts")
    protocol = input_approval.get("protocol")
    if not isinstance(artifacts, dict) or not isinstance(protocol, dict):
        fail("INVALID_ARTIFACT", "Input approval bindings are missing")
    if artifacts.get("query-author-packet/manifest.json") != packet_sha256:
        fail("INPUT_IDENTITY_MISMATCH", "Approved query-author packet changed")
    if protocol.get("sha256") != protocol_sha256:
        fail("INPUT_IDENTITY_MISMATCH", "Approved protocol changed")
    protocol_path = protocol.get("path")
    protocol_version = protocol.get("version")
    if not isinstance(protocol_path, str) or not isinstance(protocol_version, str):
        fail("INVALID_ARTIFACT", "Approved protocol identity is incomplete")
    return {
        "approval_id": approval_id,
        "protocol_path": protocol_path,
        "protocol_sha256": protocol_sha256,
        "protocol_version": protocol_version,
        "query_author_packet_manifest_sha256": packet_sha256,
    }


def _validate_draft(
    draft: dict[str, Any], *, packet_manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    _expect_keys(
        draft,
        expected={"cases", "schema_version"},
        label="query draft",
    )
    if draft.get("schema_version") != DRAFT_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Unsupported query draft schema")
    cases = draft.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        fail("INVALID_QUERY_DRAFT", "Query draft must contain 12 cases")
    workshops = packet_manifest["workshops"]
    frozen_cases: list[dict[str, Any]] = []
    normalized_texts: set[str] = set()

    for position, (case, workshop) in enumerate(zip(cases, workshops, strict=True)):
        if not isinstance(case, dict):
            fail("INVALID_QUERY_DRAFT", "Query case must be an object")
        _expect_keys(case, expected={"case_id", "queries"}, label="query case")
        expected_case_id = OPERATIONAL_EXPECTED_CASE_IDS[position]
        case_id = case.get("case_id")
        if case_id != expected_case_id or workshop.get("case_id") != case_id:
            fail(
                "NON_CANONICAL_INPUT",
                "Query cases must match the frozen operational order",
                position=position,
            )
        queries = case.get("queries")
        if not isinstance(queries, list) or len(queries) != 2:
            fail(
                "INVALID_QUERY_DRAFT",
                "Each case must contain exactly two queries",
                case_id=case_id,
            )
        frozen_queries: list[dict[str, Any]] = []
        for query_position, query in enumerate(queries):
            if not isinstance(query, dict):
                fail("INVALID_QUERY_DRAFT", "Query must be an object")
            _expect_keys(
                query,
                expected={"authoring_basis", "kind", "text"},
                label="query",
            )
            expected_kind = "broad" if query_position == 0 else "focused"
            if query.get("kind") != expected_kind:
                fail(
                    "NON_CANONICAL_INPUT",
                    "Query kinds must be broad then focused",
                    case_id=case_id,
                )
            text = query.get("text")
            if (
                not isinstance(text, str)
                or text != text.strip()
                or not text.isascii()
                or "\n" in text
                or "\r" in text
            ):
                fail(
                    "INVALID_QUERY_DRAFT",
                    "Query text must be trimmed, ASCII, and single-line",
                    case_id=case_id,
                    kind=expected_kind,
                )
            if not MIN_QUERY_SCALARS <= len(text) <= MAX_QUERY_SCALARS:
                fail(
                    "INVALID_QUERY_DRAFT",
                    "Query text violates the frozen scalar limits",
                    case_id=case_id,
                    kind=expected_kind,
                    actual=len(text),
                )
            lowered = text.casefold()
            forbidden = next(
                (term for term in FORBIDDEN_QUERY_TERMS if term in lowered), None
            )
            if forbidden is not None or case_id in lowered:
                fail(
                    "INVALID_QUERY_DRAFT",
                    "Query text contains forbidden evaluation identity",
                    case_id=case_id,
                    kind=expected_kind,
                    forbidden=forbidden or case_id,
                )
            basis = query.get("authoring_basis")
            if (
                not isinstance(basis, str)
                or not basis
                or basis != basis.strip()
                or not basis.isascii()
                or "\n" in basis
                or "\r" in basis
            ):
                fail(
                    "INVALID_QUERY_DRAFT",
                    "authoring_basis must be non-empty, trimmed ASCII on one line",
                    case_id=case_id,
                    kind=expected_kind,
                )
            normalized = normalize_query(text)
            if normalized.normalized in normalized_texts:
                fail(
                    "INVALID_QUERY_DRAFT",
                    "Query texts must be unique after normalization",
                    case_id=case_id,
                    kind=expected_kind,
                )
            normalized_texts.add(normalized.normalized)
            query_id = f"{case_id}-{expected_kind}"
            frozen_queries.append(
                {
                    "authoring_basis": basis,
                    "kind": expected_kind,
                    "normalized_text": normalized.normalized,
                    "normalized_tokens": list(normalized.tokens),
                    "query_id": query_id,
                    "scalar_count": len(text),
                    "text": text,
                    "text_sha256": sha256_bytes(text.encode("utf-8")),
                }
            )
        frozen_cases.append(
            {
                "case_id": case_id,
                "queries": frozen_queries,
                "split": "operational",
                "workshop": {
                    "path": f"query-author-packet/{workshop['path']}",
                    "sha256": workshop["sha256"],
                },
            }
        )
    return frozen_cases


def finalize_query_draft(
    *,
    raw_response_path: Path,
    raw_stderr_path: Path,
    prompt_path: Path,
    prompt_manifest_path: Path,
    agent_file_path: Path,
    packet_manifest_path: Path,
    input_approval_path: Path,
    protocol_path: Path,
    output_path: Path,
    manifest_id: str,
    execution_id: str,
    created_at: str,
    cli_version: str,
    model_alias: str,
    model_name: str,
    provider: str,
    reasoning_mode: str,
) -> dict[str, Any]:
    raw_response_bytes = raw_response_path.read_bytes()
    raw_stderr_bytes = raw_stderr_path.read_bytes()
    prompt_bytes = prompt_path.read_bytes()
    agent_bytes = agent_file_path.read_bytes()
    protocol_bytes = protocol_path.read_bytes()
    prompt_manifest, _ = _read_object(
        prompt_manifest_path, label="query-author prompt manifest"
    )
    packet_manifest, packet_bytes = _read_object(
        packet_manifest_path, label="query-author packet manifest"
    )
    input_approval, _ = _read_object(
        input_approval_path, label="input approval manifest"
    )
    _validate_prompt_binding(
        prompt_manifest=prompt_manifest,
        prompt_bytes=prompt_bytes,
        packet_bytes=packet_bytes,
        protocol_bytes=protocol_bytes,
    )
    source_binding = _validate_source_binding(
        packet_manifest=packet_manifest,
        packet_sha256=sha256_bytes(packet_bytes),
        input_approval=input_approval,
        protocol_sha256=sha256_bytes(protocol_bytes),
    )
    draft, renderer_prefix_removed = _parse_raw_response(raw_response_bytes)
    cases = _validate_draft(draft, packet_manifest=packet_manifest)
    if not all(
        isinstance(value, str) and value
        for value in (
            manifest_id,
            execution_id,
            created_at,
            cli_version,
            model_alias,
            model_name,
            provider,
            reasoning_mode,
        )
    ):
        fail("INVALID_INVOCATION", "Query-author execution identity is incomplete")

    manifest = {
        "author": {
            "agent_file_sha256": sha256_bytes(agent_bytes),
            "cli": {"name": "kimi-code", "version": cli_version},
            "execution_id": execution_id,
            "identity": "fresh-isolated-kimi-query-author",
            "isolation": {
                "fresh_session": True,
                "skills_directory": "empty",
                "subagents": [],
                "tools": [],
            },
            "model": {
                "alias": model_alias,
                "display_name": model_name,
                "provider": provider,
                "reasoning_mode": reasoning_mode,
            },
            "prompt_sha256": sha256_bytes(prompt_bytes),
            "raw_response_sha256": sha256_bytes(raw_response_bytes),
            "raw_stderr_sha256": sha256_bytes(raw_stderr_bytes),
            "renderer_prefix_removed": renderer_prefix_removed,
        },
        "case_count": len(cases),
        "cases": cases,
        "created_at": created_at,
        "manifest_id": manifest_id,
        "query_count": sum(len(case["queries"]) for case in cases),
        "query_rules": {
            "case_query_kinds": ["broad", "focused"],
            "language": "English ASCII",
            "scalar_limits": {
                "maximum": MAX_QUERY_SCALARS,
                "minimum": MIN_QUERY_SCALARS,
            },
            "selection_policy": "Workshop-only neutral retrieval intent",
        },
        "schema_version": QUERY_MANIFEST_SCHEMA_VERSION,
        "source_binding": source_binding,
        "status": "draft_pending_controller_approval",
        "validation": {
            "case_count": len(cases),
            "duplicate_normalized_query_count": 0,
            "machine_checks_passed": True,
            "query_count": sum(len(case["queries"]) for case in cases),
            "semantic_controller_review_required": True,
        },
        "visibility_boundary": {
            "forbidden": [
                "Target Paper identity or text",
                "reference corpus or titles",
                "ranker identity or output",
                "qrels or prior evaluation results",
                "repository, shell, network, tools, skills, or subagents",
            ],
            "read": ["embedded Approved Workshop text in the bound prompt"],
        },
    }
    write_json_once(output_path, manifest)
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze an isolated query-author draft"
    )
    parser.add_argument("--raw-response", type=Path, required=True)
    parser.add_argument("--raw-stderr", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--prompt-manifest", type=Path, required=True)
    parser.add_argument("--agent-file", type=Path, required=True)
    parser.add_argument("--packet-manifest", type=Path, required=True)
    parser.add_argument("--input-approval", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-id", required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--cli-version", required=True)
    parser.add_argument("--model-alias", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--reasoning-mode", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        manifest = finalize_query_draft(
            raw_response_path=args.raw_response,
            raw_stderr_path=args.raw_stderr,
            prompt_path=args.prompt,
            prompt_manifest_path=args.prompt_manifest,
            agent_file_path=args.agent_file,
            packet_manifest_path=args.packet_manifest,
            input_approval_path=args.input_approval,
            protocol_path=args.protocol,
            output_path=args.output,
            manifest_id=args.manifest_id,
            execution_id=args.execution_id,
            created_at=args.created_at,
            cli_version=args.cli_version,
            model_alias=args.model_alias,
            model_name=args.model_name,
            provider=args.provider,
            reasoning_mode=args.reasoning_mode,
        )
    except HarnessError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "case_count": manifest["case_count"],
                "output": str(args.output),
                "query_count": manifest["query_count"],
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
