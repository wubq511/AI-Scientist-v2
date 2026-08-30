from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.blind_review import render_blind_review_html
from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.formal_input import (
    _build_blind_packet,
    _build_formal_artifacts,
    _validate_query_manifest,
    approve_queries,
)
from prototypes.local_ranking.normalization import normalize_query


def _write_json(path: Path, value: object) -> bytes:
    data = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _query_manifest(packet_hash: str, protocol_hash: str) -> dict[str, object]:
    cases = []
    for split_prefix, split in (("dev", "development"), ("hol", "holdout")):
        for number in range(1, 7):
            case_id = f"lr-{split_prefix}-{number:02d}"
            queries = []
            for kind, text in (
                ("broad", f"How should evidence be found for case {case_id}?"),
                ("focused", f"Which mechanism best addresses case {case_id}?"),
            ):
                normalized = normalize_query(text)
                queries.append(
                    {
                        "authoring_basis": "Workshop-only basis.",
                        "kind": kind,
                        "normalized_text": normalized.normalized,
                        "normalized_tokens": list(normalized.tokens),
                        "query_id": f"{case_id}-{kind}",
                        "scalar_count": len(text),
                        "text": text,
                        "text_sha256": sha256_bytes(text.encode()),
                    }
                )
            cases.append(
                {
                    "case_id": case_id,
                    "queries": queries,
                    "split": split,
                    "workshop": {
                        "path": f"query-author-packet/workshops/{case_id}.md",
                        "sha256": "a" * 64,
                    },
                }
            )
    return {
        "author": {"identity": "codex"},
        "case_count": 12,
        "cases": cases,
        "created_at": "2026-08-30T00:00:00+08:00",
        "manifest_id": "query-draft-test",
        "query_count": 24,
        "query_rules": {"language": "en"},
        "schema_version": "prototype-query-manifest-v1.0",
        "source_binding": {
            "approval_id": "input-approval-test",
            "protocol_path": "docs/prototypes/protocol.md",
            "protocol_sha256": protocol_hash,
            "protocol_version": "approved v1.1",
            "query_author_packet_manifest_sha256": packet_hash,
        },
        "status": "draft_pending_robert_approval",
        "validation": {"passed": True},
        "visibility_boundary": {"read": ["packet"]},
    }


def _packet_manifest() -> dict[str, object]:
    return {
        "case_count": 12,
        "workshops": [
            {
                "case_id": f"lr-{split}-{number:02d}",
                "path": f"workshops/lr-{split}-{number:02d}.md",
                "sha256": "a" * 64,
            }
            for split in ("dev", "hol")
            for number in range(1, 7)
        ],
    }


def _approved_corpora(tmp_path: Path) -> tuple[dict[str, object], Path]:
    corpora_root = tmp_path / "corpora"
    entries = []
    long_abstract = "A" * 300 + ". " + "B" * 300 + "."
    for split_prefix in ("dev", "hol"):
        for number in range(1, 7):
            case_id = f"lr-{split_prefix}-{number:02d}"
            records = []
            for paper_number in range(3):
                split_digit = "1" if split_prefix == "hol" else "0"
                paper_id = f"{split_digit}{number:02d}{paper_number:02d}".ljust(40, "a")
                text = (
                    long_abstract
                    if case_id == "lr-dev-01" and paper_number == 0
                    else f"Evidence abstract for {case_id} paper {paper_number}."
                )
                records.append(
                    {
                        "content_items": [
                            {
                                "status": "validated",
                                "text": text,
                                "type": "publisher_abstract",
                            }
                        ],
                        "paper_id": paper_id,
                        "title": f"Paper {paper_number} for {case_id}",
                    }
                )
            corpus = {"case_id": case_id, "records": records}
            corpus_bytes = _write_json(corpora_root / case_id / "corpus.json", corpus)
            entries.append(
                {
                    "case_id": case_id,
                    "corpus_sha256": sha256_bytes(corpus_bytes),
                    "record_count": 3,
                }
            )
    return {"case_count": 12, "corpora": entries}, corpora_root


def test_query_approval_binds_exact_isolated_manifest(tmp_path: Path) -> None:
    packet_bytes = _write_json(tmp_path / "packet.json", _packet_manifest())
    protocol_bytes = b"approved protocol\n"
    (tmp_path / "protocol.md").write_bytes(protocol_bytes)
    query_manifest = _query_manifest(
        sha256_bytes(packet_bytes), sha256_bytes(protocol_bytes)
    )
    query_path = tmp_path / "queries.json"
    _write_json(query_path, query_manifest)

    approval = approve_queries(
        query_manifest_path=query_path,
        packet_manifest_path=tmp_path / "packet.json",
        protocol_path=tmp_path / "protocol.md",
        output_path=tmp_path / "approval.json",
        approved_on="2026-08-30",
        decision_actor="Codex controller",
        delegated_by="Robert",
        delegation_text="Decide whether to approve.",
    )

    assert approval["approval_status"] == "approved_as_is"
    assert approval["decision"]["query_count"] == 24
    with pytest.raises(HarnessError, match="ARTIFACT_EXISTS"):
        approve_queries(
            query_manifest_path=query_path,
            packet_manifest_path=tmp_path / "packet.json",
            protocol_path=tmp_path / "protocol.md",
            output_path=tmp_path / "approval.json",
            approved_on="2026-08-30",
            decision_actor="Codex controller",
            delegated_by="Robert",
            delegation_text="Decide whether to approve.",
        )


def test_query_manifest_rejects_changed_frozen_text() -> None:
    manifest = _query_manifest("a" * 64, "b" * 64)
    manifest["cases"][0]["queries"][0]["text"] += " changed"

    with pytest.raises(HarnessError, match="scalar count changed"):
        _validate_query_manifest(
            manifest,
            packet_manifest=_packet_manifest(),
            packet_manifest_sha256="a" * 64,
            protocol_sha256="b" * 64,
        )


def test_formal_materialization_is_source_complete_and_shared(tmp_path: Path) -> None:
    manifest = _query_manifest("a" * 64, "b" * 64)
    query_cases = _validate_query_manifest(
        manifest,
        packet_manifest=_packet_manifest(),
        packet_manifest_sha256="a" * 64,
        protocol_sha256="b" * 64,
    )
    approved, corpora_root = _approved_corpora(tmp_path)

    outputs, audit = _build_formal_artifacts(
        approved_corpora=approved,
        corpora_root=corpora_root,
        query_cases=query_cases,
        query_token_length=lambda text: len(text),
        passage_token_length=lambda text: len(text),
    )

    assert len(outputs["development"]["cases"]) == 6
    assert len(outputs["holdout"]["cases"]) == 6
    assert audit["paper_count"] == 36
    assert audit["segment_count"] == 37
    assert audit["segments_per_paper_histogram"] == {"1": 35, "2": 1}
    assert audit["maximum_segment_input_tokens"] <= 512
    first_paper = outputs["development"]["cases"][0]["papers"][0]
    assert "".join(segment["text"] for segment in first_paper["segments"]) == (
        "A" * 300 + ". " + "B" * 300 + "."
    )


def test_blind_packet_and_html_omit_comparison_results(tmp_path: Path) -> None:
    manifest = _query_manifest("a" * 64, "b" * 64)
    query_cases = _validate_query_manifest(
        manifest,
        packet_manifest=_packet_manifest(),
        packet_manifest_sha256="a" * 64,
        protocol_sha256="b" * 64,
    )
    approved, corpora_root = _approved_corpora(tmp_path)
    outputs, _ = _build_formal_artifacts(
        approved_corpora=approved,
        corpora_root=corpora_root,
        query_cases=query_cases,
        query_token_length=lambda text: len(text),
        passage_token_length=lambda text: len(text),
    )
    input_bytes = canonical_json_bytes(outputs["development"])
    packet = _build_blind_packet(
        outputs["development"], input_sha256=sha256_bytes(input_bytes)
    )
    serialized = json.dumps(packet)
    html = render_blind_review_html(packet).decode()

    assert packet["paper_judgment_count"] == 36
    assert all(
        term not in serialized
        for term in ('"candidate_id"', '"score"', '"rank_position"')
    )
    assert "http://" not in html
    assert "https://" not in html
    assert "localStorage" in html
    assert "local-ranking-qrels-v1" in html
