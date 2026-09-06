from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import INPUT_SCHEMA_VERSION
from .blind_review import render_blind_review_html
from .canonical import canonical_json_bytes, sha256_bytes, write_json_once, write_once
from .errors import HarnessError, fail
from .length_policy_probe import (
    MAX_INPUT_TOKENS,
    MODEL_ID,
    MODEL_REVISION,
    PASSAGE_PREFIX,
    TOKENIZER_JSON_SHA256,
    TOKENIZERS_VERSION,
    segment_source_text,
)
from .normalization import normalize_query
from .schema import SAFE_ID_PATTERN, parse_ranking_input

QUERY_PREFIX = "query: "
QUERY_MANIFEST_SCHEMA_VERSION = "prototype-query-manifest-v1.0"
QUERY_APPROVAL_SCHEMA_VERSION = "prototype-query-approval-v1.0"
FORMALIZATION_SCHEMA_VERSION = "prototype-formal-input-v1.0"
BLIND_PACKET_SCHEMA_VERSION = "prototype-blind-qrels-packet-v1.0"
LEGACY_EXPECTED_CASE_IDS = tuple(
    f"lr-{split}-{number:02d}" for split in ("dev", "hol") for number in range(1, 7)
)
OPERATIONAL_EXPECTED_CASE_IDS = tuple(f"lr-op-{number:02d}" for number in range(1, 13))


def _case_split(case_id: str) -> str:
    if case_id.startswith("lr-dev-"):
        return "development"
    if case_id.startswith("lr-hol-"):
        return "holdout"
    if case_id.startswith("lr-op-"):
        return "operational"
    fail(
        "INVALID_QUERY_MANIFEST", "Query case_id has no approved split", case_id=case_id
    )


def _expect_keys(value: dict[str, Any], *, expected: set[str], label: str) -> None:
    if set(value) != expected:
        fail(
            "INVALID_QUERY_MANIFEST",
            f"{label} has an invalid closed schema",
            missing=sorted(expected - set(value)),
            unknown=sorted(set(value) - expected),
        )


def _read_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
        value = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(
            "INVALID_ARTIFACT",
            f"{label} is not readable canonical JSON",
            error=str(exc),
        )
    if not isinstance(value, dict):
        fail("INVALID_ARTIFACT", f"{label} must be an object")
    if canonical_json_bytes(value) != data:
        fail("NON_CANONICAL_INPUT", f"{label} must use canonical JSON bytes")
    return value, data


def _safe_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_PATTERN.fullmatch(value):
        fail("INVALID_QUERY_MANIFEST", f"{label} is not a safe identifier")
    return value


def _validate_query_manifest(
    manifest: dict[str, Any],
    *,
    packet_manifest: dict[str, Any],
    packet_manifest_sha256: str,
    protocol_sha256: str,
) -> dict[str, dict[str, Any]]:
    _expect_keys(
        manifest,
        expected={
            "author",
            "case_count",
            "cases",
            "created_at",
            "manifest_id",
            "query_count",
            "query_rules",
            "schema_version",
            "source_binding",
            "status",
            "validation",
            "visibility_boundary",
        },
        label="query manifest",
    )
    if manifest.get("schema_version") != QUERY_MANIFEST_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Unsupported query manifest schema")
    if manifest.get("case_count") != 12 or manifest.get("query_count") != 24:
        fail(
            "INVALID_QUERY_MANIFEST",
            "Query manifest must contain 12 cases / 24 queries",
        )
    source = manifest.get("source_binding")
    if not isinstance(source, dict):
        fail("INVALID_QUERY_MANIFEST", "Query source binding is missing")
    _expect_keys(
        source,
        expected={
            "approval_id",
            "protocol_path",
            "protocol_sha256",
            "protocol_version",
            "query_author_packet_manifest_sha256",
        },
        label="query source binding",
    )
    if source.get("query_author_packet_manifest_sha256") != packet_manifest_sha256:
        fail("INPUT_IDENTITY_MISMATCH", "Query packet manifest hash changed")
    if source.get("protocol_sha256") != protocol_sha256:
        fail("INPUT_IDENTITY_MISMATCH", "Query protocol hash changed")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        fail("INVALID_QUERY_MANIFEST", "Query cases are incomplete")
    packet_workshops = packet_manifest.get("workshops")
    if not isinstance(packet_workshops, list) or len(packet_workshops) != 12:
        fail("INVALID_QUERY_MANIFEST", "Query packet workshops are incomplete")
    packet_by_case = {
        workshop.get("case_id"): workshop
        for workshop in packet_workshops
        if isinstance(workshop, dict)
    }
    expected_case_ids = frozenset(packet_by_case)
    if expected_case_ids not in {
        frozenset(LEGACY_EXPECTED_CASE_IDS),
        frozenset(OPERATIONAL_EXPECTED_CASE_IDS),
    }:
        fail("INVALID_QUERY_MANIFEST", "Query packet case set is invalid")

    result: dict[str, dict[str, Any]] = {}
    all_query_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            fail("INVALID_QUERY_MANIFEST", "Query case must be an object")
        _expect_keys(
            case,
            expected={"case_id", "queries", "split", "workshop"},
            label="query case",
        )
        case_id = _safe_id(case.get("case_id"), label="case_id")
        if case_id in result:
            fail("INVALID_QUERY_MANIFEST", "Duplicate query case", case_id=case_id)
        if case_id not in expected_case_ids:
            fail("INVALID_QUERY_MANIFEST", "Query case_id is outside the frozen set")
        expected_split = _case_split(case_id)
        if case.get("split") != expected_split:
            fail(
                "INVALID_QUERY_MANIFEST",
                "Query split disagrees with case_id",
                case_id=case_id,
            )
        queries = case.get("queries")
        if not isinstance(queries, list) or len(queries) != 2:
            fail(
                "INVALID_QUERY_MANIFEST",
                "Each case needs exactly two queries",
                case_id=case_id,
            )
        workshop = case.get("workshop")
        if not isinstance(workshop, dict):
            fail("INVALID_QUERY_MANIFEST", "Query workshop binding is missing")
        _expect_keys(
            workshop,
            expected={"path", "sha256"},
            label="query workshop binding",
        )
        packet_workshop = packet_by_case[case_id]
        if workshop != {
            "path": f"query-author-packet/{packet_workshop.get('path')}",
            "sha256": packet_workshop.get("sha256"),
        }:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Query workshop binding changed",
                case_id=case_id,
            )
        parsed_queries: list[dict[str, str]] = []
        for index, query in enumerate(queries):
            if not isinstance(query, dict):
                fail(
                    "INVALID_QUERY_MANIFEST", "Query must be an object", case_id=case_id
                )
            _expect_keys(
                query,
                expected={
                    "authoring_basis",
                    "kind",
                    "normalized_text",
                    "normalized_tokens",
                    "query_id",
                    "scalar_count",
                    "text",
                    "text_sha256",
                },
                label="query",
            )
            kind = query.get("kind")
            if kind != ("broad" if index == 0 else "focused"):
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Query kinds must be broad then focused",
                    case_id=case_id,
                )
            query_id = _safe_id(query.get("query_id"), label="query_id")
            if query_id != f"{case_id}-{kind}" or query_id in all_query_ids:
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Query id is inconsistent or duplicated",
                    query_id=query_id,
                )
            text = query.get("text")
            if not isinstance(text, str) or text != text.strip() or not text.isascii():
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Query text must be trimmed ASCII",
                    query_id=query_id,
                )
            if query.get("scalar_count") != len(text):
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Query scalar count changed",
                    query_id=query_id,
                )
            if query.get("text_sha256") != sha256_bytes(text.encode("utf-8")):
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Query text hash changed",
                    query_id=query_id,
                )
            if (
                not isinstance(query.get("authoring_basis"), str)
                or not query["authoring_basis"]
            ):
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Query authoring basis is missing",
                    query_id=query_id,
                )
            normalized = normalize_query(text)
            if query.get("normalized_text") != normalized.normalized or query.get(
                "normalized_tokens"
            ) != list(normalized.tokens):
                fail(
                    "INVALID_QUERY_MANIFEST",
                    "Frozen query normalization changed",
                    query_id=query_id,
                )
            all_query_ids.add(query_id)
            parsed_queries.append({"query_id": query_id, "kind": kind, "text": text})
        result[case_id] = {"split": expected_split, "queries": parsed_queries}
    expected_order = (
        OPERATIONAL_EXPECTED_CASE_IDS
        if expected_case_ids == frozenset(OPERATIONAL_EXPECTED_CASE_IDS)
        else LEGACY_EXPECTED_CASE_IDS
    )
    if tuple(result) != expected_order:
        fail("NON_CANONICAL_INPUT", "Query cases must match the frozen order")
    return result


def approve_queries(
    *,
    query_manifest_path: Path,
    packet_manifest_path: Path,
    protocol_path: Path,
    output_path: Path,
    approved_on: str,
    decision_actor: str,
    delegated_by: str,
    delegation_text: str,
) -> dict[str, Any]:
    query_manifest, query_bytes = _read_json(
        query_manifest_path, label="query manifest"
    )
    packet_manifest, packet_bytes = _read_json(
        packet_manifest_path, label="query packet manifest"
    )
    protocol_bytes = protocol_path.read_bytes()
    parsed = _validate_query_manifest(
        query_manifest,
        packet_manifest=packet_manifest,
        packet_manifest_sha256=sha256_bytes(packet_bytes),
        protocol_sha256=sha256_bytes(protocol_bytes),
    )
    approval = {
        "approval_id": "query-approval-001",
        "approval_status": "approved_as_is",
        "approved_on": approved_on,
        "authority": {
            "decision_actor": decision_actor,
            "delegated_by": delegated_by,
            "delegation_text": delegation_text,
        },
        "decision": {
            "case_count": len(parsed),
            "query_count": sum(len(case["queries"]) for case in parsed.values()),
            "rewrite_count": 0,
            "rationale": (
                "The immutable isolated-author manifest satisfies the approved query shape, "
                "identity, normalization, provenance, and visibility-boundary checks. The "
                "controller approved it without rewriting any query bytes."
            ),
        },
        "schema_version": QUERY_APPROVAL_SCHEMA_VERSION,
        "source_binding": {
            "protocol_sha256": sha256_bytes(protocol_bytes),
            "query_author_packet_manifest_sha256": sha256_bytes(packet_bytes),
            "query_manifest_sha256": sha256_bytes(query_bytes),
        },
    }
    write_json_once(output_path, approval)
    return approval


def _validate_query_approval(
    approval: dict[str, Any],
    *,
    query_manifest_sha256: str,
    packet_manifest_sha256: str,
    protocol_sha256: str,
) -> None:
    if approval.get("schema_version") != QUERY_APPROVAL_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Unsupported query approval schema")
    if approval.get("approval_status") != "approved_as_is":
        fail("APPROVAL_REQUIRED", "Queries are not approved as-is")
    binding = approval.get("source_binding")
    expected = {
        "protocol_sha256": protocol_sha256,
        "query_author_packet_manifest_sha256": packet_manifest_sha256,
        "query_manifest_sha256": query_manifest_sha256,
    }
    if binding != expected:
        fail("INPUT_IDENTITY_MISMATCH", "Query approval does not bind exact inputs")


def _load_token_lengths(
    tokenizer_json: Path,
) -> tuple[Callable[[str], int], Callable[[str], int]]:
    try:
        import tokenizers
        from tokenizers import Tokenizer
    except ImportError as exc:
        fail(
            "MISSING_DEPENDENCY",
            "Pinned tokenizers package is required",
            error=str(exc),
        )
    tokenizer_bytes = tokenizer_json.read_bytes()
    if sha256_bytes(tokenizer_bytes) != TOKENIZER_JSON_SHA256:
        fail(
            "TOKENIZER_HASH_MISMATCH", "Tokenizer bytes differ from pinned E5 revision"
        )
    if tokenizers.__version__ != TOKENIZERS_VERSION:
        fail(
            "DEPENDENCY_VERSION_MISMATCH",
            "tokenizers version differs from the frozen policy",
            expected=TOKENIZERS_VERSION,
            actual=tokenizers.__version__,
        )
    tokenizer = Tokenizer.from_file(str(tokenizer_json))
    return (
        lambda text: len(tokenizer.encode(QUERY_PREFIX + text).ids),
        lambda text: len(tokenizer.encode(PASSAGE_PREFIX + text).ids),
    )


def _blind_order(split: str, query_id: str, paper_id: str) -> str:
    value = f"blind-qrels-v1|{split}|{query_id}|{paper_id}".encode()
    return hashlib.sha256(value).hexdigest()


def _build_formal_artifacts(
    *,
    approved_corpora: dict[str, Any],
    corpora_root: Path,
    query_cases: dict[str, dict[str, Any]],
    query_token_length: Callable[[str], int],
    passage_token_length: Callable[[str], int],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    entries = approved_corpora.get("corpora")
    if approved_corpora.get("case_count") != 12 or not isinstance(entries, list):
        fail("INVALID_APPROVAL", "Approved corpora must contain 12 cases")
    query_splits = {item.get("split") for item in query_cases.values()}
    if query_splits not in (
        {"development", "holdout"},
        {"operational"},
    ):
        fail(
            "INVALID_QUERY_MANIFEST",
            "Query cases do not form an approved formal split set",
            splits=sorted(str(item) for item in query_splits),
        )
    outputs = {
        split: {
            "schema_version": INPUT_SCHEMA_VERSION,
            "split": split,
            "cases": [],
        }
        for split in sorted(query_splits)
    }
    query_lengths: list[dict[str, Any]] = []
    title_lengths: list[int] = []
    segment_lengths: list[int] = []
    segment_records: list[dict[str, Any]] = []
    histogram: Counter[int] = Counter()

    for entry in entries:
        if not isinstance(entry, dict):
            fail("INVALID_APPROVAL", "Approved corpus entry must be an object")
        case_id = _safe_id(entry.get("case_id"), label="approved case_id")
        query_case = query_cases.get(case_id)
        if query_case is None:
            fail(
                "INPUT_IDENTITY_MISMATCH",
                "Approved case has no frozen queries",
                case_id=case_id,
            )
        corpus_path = corpora_root / case_id / "corpus.json"
        corpus, corpus_bytes = _read_json(corpus_path, label=f"{case_id} corpus")
        if sha256_bytes(corpus_bytes) != entry.get("corpus_sha256"):
            fail("CORPUS_DRIFT", "Approved corpus hash changed", case_id=case_id)
        if corpus.get("case_id") != case_id:
            fail("INPUT_IDENTITY_MISMATCH", "Corpus case_id changed", case_id=case_id)
        records = corpus.get("records")
        if not isinstance(records, list) or len(records) != entry.get("record_count"):
            fail(
                "INVALID_CORPUS",
                "Approved corpus record count changed",
                case_id=case_id,
            )
        frozen_queries: list[dict[str, str]] = []
        for query in query_case["queries"]:
            length = query_token_length(query["text"])
            if length > MAX_INPUT_TOKENS:
                fail(
                    "QUERY_TOO_LONG",
                    "Frozen query exceeds E5 input boundary",
                    query_id=query["query_id"],
                )
            query_lengths.append(
                {"query_id": query["query_id"], "input_tokens": length}
            )
            frozen_queries.append(dict(query))

        papers: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                fail(
                    "INVALID_CORPUS", "Corpus record must be an object", case_id=case_id
                )
            paper_id = _safe_id(record.get("paper_id"), label="paper_id")
            title = record.get("title")
            if not isinstance(title, str) or not title:
                fail("INVALID_CORPUS", "Paper title is missing", paper_id=paper_id)
            title_length = passage_token_length(title)
            if title_length > MAX_INPUT_TOKENS:
                fail(
                    "TITLE_TOO_LONG",
                    "Paper title exceeds E5 input boundary",
                    paper_id=paper_id,
                )
            title_lengths.append(title_length)
            content_items = record.get("content_items")
            if not isinstance(content_items, list) or len(content_items) != 1:
                fail(
                    "INVALID_CORPUS",
                    "v1.1 requires one content item",
                    paper_id=paper_id,
                )
            item = content_items[0]
            if (
                not isinstance(item, dict)
                or item.get("type") != "publisher_abstract"
                or item.get("status") != "validated"
                or not isinstance(item.get("text"), str)
                or not item["text"]
            ):
                fail(
                    "INVALID_CORPUS",
                    "Content must be a validated publisher abstract",
                    paper_id=paper_id,
                )
            source_text = item["text"]
            spans = segment_source_text(source_text, passage_token_length)
            if "".join(text for _, _, text in spans) != source_text:
                fail(
                    "NON_REVERSIBLE_SEGMENTATION",
                    "Formal segments do not reconstruct source",
                )
            histogram[len(spans)] += 1
            segments: list[dict[str, Any]] = []
            private_segments: list[dict[str, Any]] = []
            for index, (start, end, text) in enumerate(spans, start=1):
                length = passage_token_length(text)
                if length > MAX_INPUT_TOKENS:
                    fail("SEGMENT_TOO_LONG", "Formal segment exceeds E5 input boundary")
                segment_id = f"{paper_id}-s{index:02d}"
                segment_lengths.append(length)
                segments.append(
                    {
                        "content_item_order": 0,
                        "content_type": "publisher_abstract",
                        "segment_id": segment_id,
                        "source_start": start,
                        "text": text,
                    }
                )
                private_segments.append(
                    {
                        "input_tokens": length,
                        "segment_id": segment_id,
                        "source_end": end,
                        "source_start": start,
                        "text_sha256": sha256_bytes(text.encode()),
                    }
                )
            papers.append({"paper_id": paper_id, "segments": segments, "title": title})
            segment_records.append(
                {
                    "case_id": case_id,
                    "paper_id": paper_id,
                    "segments": private_segments,
                    "source_sha256": sha256_bytes(source_text.encode()),
                }
            )
        papers.sort(key=lambda paper: paper["paper_id"])
        formal_case = {
            "case_id": case_id,
            "corpus_sha256": entry["corpus_sha256"],
            "papers": papers,
            "queries": frozen_queries,
        }
        outputs[query_case["split"]]["cases"].append(formal_case)

    if set(query_cases) != {
        case["case_id"] for split in outputs.values() for case in split["cases"]
    }:
        fail("INPUT_IDENTITY_MISMATCH", "Query and corpus case sets differ")
    for split in outputs.values():
        split["cases"].sort(key=lambda case: case["case_id"])
        parse_ranking_input(split)
    audit = {
        "paper_count": sum(histogram.values()),
        "query_count": len(query_lengths),
        "query_inputs": query_lengths,
        "maximum_query_input_tokens": max(
            item["input_tokens"] for item in query_lengths
        ),
        "maximum_title_input_tokens": max(title_lengths),
        "maximum_segment_input_tokens": max(segment_lengths),
        "segment_count": len(segment_lengths),
        "segments_per_paper_histogram": {
            str(key): value for key, value in sorted(histogram.items())
        },
        "segmentation_sha256": sha256_bytes(canonical_json_bytes(segment_records)),
        "private_segment_records": segment_records,
    }
    return outputs, audit


def _build_blind_packet(
    ranking_input: dict[str, Any], *, input_sha256: str
) -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    judgment_count = 0
    for case in ranking_input["cases"]:
        for query in case["queries"]:
            papers = [
                {
                    "paper_id": paper["paper_id"],
                    "title": paper["title"],
                    "segments": paper["segments"],
                }
                for paper in case["papers"]
            ]
            papers.sort(
                key=lambda paper: _blind_order(
                    ranking_input["split"], query["query_id"], paper["paper_id"]
                )
            )
            judgment_count += len(papers)
            queries.append({"case_id": case["case_id"], **query, "papers": papers})
    return {
        "input_sha256": input_sha256,
        "paper_judgment_count": judgment_count,
        "queries": queries,
        "query_count": len(queries),
        "schema_version": BLIND_PACKET_SCHEMA_VERSION,
        "split": ranking_input["split"],
        "visibility": {
            "includes": [
                "query",
                "eligible paper title",
                "eligible retrieval segments",
            ],
            "omits": [
                "candidate identity",
                "scores",
                "rank position",
                "Target Paper",
                "previous result",
            ],
        },
    }


def materialize(
    *,
    approval_root: Path,
    corpora_root: Path,
    query_manifest_path: Path,
    query_approval_path: Path,
    protocol_path: Path,
    tokenizer_json: Path,
    output_root: Path,
) -> dict[str, Any]:
    approval_manifest, approval_manifest_bytes = _read_json(
        approval_root / "approval-manifest.json", label="input approval"
    )
    approved_corpora, approved_corpora_bytes = _read_json(
        approval_root / "approved-corpora.json", label="approved corpora"
    )
    approval_artifacts = approval_manifest.get("artifacts")
    if not isinstance(approval_artifacts, dict):
        fail("INVALID_APPROVAL", "Input approval artifact bindings are missing")
    expected_corpora_hash = approval_artifacts.get("approved-corpora.json")
    if sha256_bytes(approved_corpora_bytes) != expected_corpora_hash:
        fail("INPUT_IDENTITY_MISMATCH", "Input approval does not bind approved corpora")
    packet_path = approval_root / "query-author-packet/manifest.json"
    packet_manifest, packet_bytes = _read_json(
        packet_path, label="query packet manifest"
    )
    query_manifest, query_bytes = _read_json(
        query_manifest_path, label="query manifest"
    )
    query_approval, query_approval_bytes = _read_json(
        query_approval_path, label="query approval"
    )
    protocol_bytes = protocol_path.read_bytes()
    protocol_hash = sha256_bytes(protocol_bytes)
    packet_hash = sha256_bytes(packet_bytes)
    query_hash = sha256_bytes(query_bytes)
    if approval_manifest.get("approval_status") != "approved":
        fail("APPROVAL_REQUIRED", "Input approval manifest is not approved")
    approval_protocol = approval_manifest.get("protocol")
    if (
        not isinstance(approval_protocol, dict)
        or approval_protocol.get("sha256") != protocol_hash
    ):
        fail("INPUT_IDENTITY_MISMATCH", "Input approval does not bind the protocol")
    if approval_artifacts.get("query-author-packet/manifest.json") != packet_hash:
        fail("INPUT_IDENTITY_MISMATCH", "Input approval does not bind the query packet")
    approval_preparation = approval_manifest.get("preparation")
    if not isinstance(approval_preparation, dict) or not isinstance(
        approval_preparation.get("selection_manifest_sha256"), str
    ):
        fail("INVALID_APPROVAL", "Input approval selection binding is missing")
    query_cases = _validate_query_manifest(
        query_manifest,
        packet_manifest=packet_manifest,
        packet_manifest_sha256=packet_hash,
        protocol_sha256=protocol_hash,
    )
    _validate_query_approval(
        query_approval,
        query_manifest_sha256=query_hash,
        packet_manifest_sha256=packet_hash,
        protocol_sha256=protocol_hash,
    )
    query_token_length, passage_token_length = _load_token_lengths(tokenizer_json)
    inputs, audit = _build_formal_artifacts(
        approved_corpora=approved_corpora,
        corpora_root=corpora_root,
        query_cases=query_cases,
        query_token_length=query_token_length,
        passage_token_length=passage_token_length,
    )
    files: dict[str, bytes] = {}
    for split, value in inputs.items():
        input_bytes = canonical_json_bytes(value)
        files[f"{split}/input.json"] = input_bytes
        if split != "operational":
            packet = _build_blind_packet(value, input_sha256=sha256_bytes(input_bytes))
            files[f"{split}/blind-review-packet.json"] = canonical_json_bytes(packet)
            files[f"{split}/blind-review.html"] = render_blind_review_html(packet)
    files["audit.json"] = canonical_json_bytes(
        {
            **audit,
            "model": {
                "id": MODEL_ID,
                "maximum_input_tokens": MAX_INPUT_TOKENS,
                "passage_prefix": PASSAGE_PREFIX,
                "query_prefix": QUERY_PREFIX,
                "revision": MODEL_REVISION,
                "tokenizer_json_sha256": TOKENIZER_JSON_SHA256,
                "tokenizers_version": TOKENIZERS_VERSION,
            },
            "schema_version": FORMALIZATION_SCHEMA_VERSION,
        }
    )
    manifest = {
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "schema_version": FORMALIZATION_SCHEMA_VERSION,
        "source_binding": {
            "approved_corpora_sha256": sha256_bytes(approved_corpora_bytes),
            "input_approval_manifest_sha256": sha256_bytes(approval_manifest_bytes),
            "protocol_sha256": protocol_hash,
            "query_approval_sha256": sha256_bytes(query_approval_bytes),
            "query_author_packet_manifest_sha256": packet_hash,
            "query_manifest_sha256": query_hash,
            "selection_manifest_sha256": approval_preparation[
                "selection_manifest_sha256"
            ],
            "tokenizer_json_sha256": TOKENIZER_JSON_SHA256,
        },
        "status": (
            "formal_operational_input_ready"
            if set(inputs) == {"operational"}
            else "formal_inputs_ready_qrels_pending"
        ),
    }
    files["manifest.json"] = canonical_json_bytes(manifest)
    for name, data in sorted(
        files.items(), key=lambda item: item[0] == "manifest.json"
    ):
        write_once(output_root / name, data)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Approve queries and materialize formal ranking inputs"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    approve = subparsers.add_parser("approve-queries")
    approve.add_argument("--query-manifest", type=Path, required=True)
    approve.add_argument("--packet-manifest", type=Path, required=True)
    approve.add_argument("--protocol", type=Path, required=True)
    approve.add_argument("--output", type=Path, required=True)
    approve.add_argument("--approved-on", required=True)
    approve.add_argument("--decision-actor", required=True)
    approve.add_argument("--delegated-by", required=True)
    approve.add_argument("--delegation-text", required=True)
    make = subparsers.add_parser("materialize")
    make.add_argument("--approval-root", type=Path, required=True)
    make.add_argument("--corpora-root", type=Path, required=True)
    make.add_argument("--query-manifest", type=Path, required=True)
    make.add_argument("--query-approval", type=Path, required=True)
    make.add_argument("--protocol", type=Path, required=True)
    make.add_argument("--tokenizer-json", type=Path, required=True)
    make.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "approve-queries":
            result = approve_queries(
                query_manifest_path=args.query_manifest,
                packet_manifest_path=args.packet_manifest,
                protocol_path=args.protocol,
                output_path=args.output,
                approved_on=args.approved_on,
                decision_actor=args.decision_actor,
                delegated_by=args.delegated_by,
                delegation_text=args.delegation_text,
            )
        else:
            result = materialize(
                approval_root=args.approval_root,
                corpora_root=args.corpora_root,
                query_manifest_path=args.query_manifest,
                query_approval_path=args.query_approval,
                protocol_path=args.protocol,
                tokenizer_json=args.tokenizer_json,
                output_root=args.output_root,
            )
    except (HarnessError, FileNotFoundError, OSError, ValueError) as exc:
        if isinstance(exc, HarnessError):
            print(json.dumps(exc.to_dict(), sort_keys=True))
        else:
            print(json.dumps({"code": "FORMALIZATION_FAILED", "message": str(exc)}))
        return 2
    print(json.dumps({"status": "success", "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
