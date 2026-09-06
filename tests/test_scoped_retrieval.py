"""Comprehensive verification and adversarial tests for Scoped Literature Retriever (ticket 05).

Delivers:
- VM-UNIT-05: deterministic BM25 ranking, stable tie-break, output budget,
  allowlist payload, and payload SHA-256.
- VM-CONTRACT-020-01: retriever input boundary is strictly {"query": non-empty},
  fails closed on unknown fields, type errors, trimmed empty, length > 256.
- VM-CONTRACT-020-02: scope binding is immutable; corpus tampering, missing file,
  or identity mismatch fails closed immediately.
- VM-CONTRACT-020-03: candidate eligibility enforces validated publisher_abstract
  only; ineligible records excluded; all-ineligible corpus fails closed.
- VM-CONTRACT-020-04: audit release gate mandates on-disk persistence and hash
  verification of audit event and payload before releasing; closed error vocabulary.
- VM-REPLAY-03: repeated retrieval on identical corpus and normalized query
  yields byte-identical canonical payloads and identical SHA-256 hashes.
- Adversarial hardening: segment ID qualification across papers, duplicate record
  detection, zero-token content rejection, non-string argument key safety, and
  mandatory audit release gate enforcement.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.retrieval import (
    BoundCorpus,
    EligiblePaper,
    EligibleSegment,
    PAPER_CAP,
    SEGMENTS_PER_PAPER,
    TOTAL_SEGMENT_CAP,
    bind_corpus,
    bm25_score,
    build_collection,
    load_eligible_candidates,
    normalize_query,
    rank_corpus,
)
from ai_scientist.ideation.run_store import RunStore

CASE_ID = "case-0123456789abcdef0123456789abcdef"


def _sample_corpus_dict(case_id: str = CASE_ID) -> dict:
    """Construct a clean, schema-valid corpus dictionary for testing."""
    abstract_1 = (
        "Preventive treatment for episodic and chronic migraine includes "
        "beta blockers, topiramate, and monoclonal antibodies targeting CGRP."
    )
    abstract_2 = (
        "Clinical trials evaluated CGRP receptor antagonists for acute migraine "
        "therapy and prevention, showing significant reduction in headache days."
    )
    abstract_3 = (
        "Neuroimaging studies reveal cortical spreading depression and trigeminal "
        "cervical complex activation during migraine attacks."
    )
    abstract_4 = (
        "Cluster headache management requires high-flow oxygen and sumatriptan, "
        "differing substantially from typical migraine pathways."
    )
    return {
        "case_id": case_id,
        "schema_version": "prototype-frozen-corpus-v1",
        "records": [
            {
                "paper_id": "paper-01-cgrp",
                "title": "CGRP Pathways in Migraine Prevention",
                "content_items": [
                    {
                        "content_id": "abs-01",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract_1,
                        "sha256": sha256_bytes(abstract_1.encode("utf-8")),
                    }
                ],
            },
            {
                "paper_id": "paper-02-trials",
                "title": "Randomized Trials of Migraine Prophylaxis",
                "content_items": [
                    {
                        "content_id": "abs-02",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract_2,
                        "sha256": sha256_bytes(abstract_2.encode("utf-8")),
                    }
                ],
            },
            {
                "paper_id": "paper-03-imaging",
                "title": "Neuroimaging Mechanisms in Headache Disorders",
                "content_items": [
                    {
                        "content_id": "abs-03",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract_3,
                        "sha256": sha256_bytes(abstract_3.encode("utf-8")),
                    }
                ],
            },
            {
                "paper_id": "paper-04-cluster",
                "title": "Cluster Headache Differential Diagnosis",
                "content_items": [
                    {
                        "content_id": "abs-04",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract_4,
                        "sha256": sha256_bytes(abstract_4.encode("utf-8")),
                    }
                ],
            },
        ],
    }


def _setup_workspace_corpus(
    workspace_root: Path,
    corpus_dict: dict | None = None,
    case_id: str = CASE_ID,
) -> tuple[str, str, int]:
    """Write corpus to workspace and return (relpath, sha256, record_count)."""
    data = corpus_dict or _sample_corpus_dict(case_id)
    raw_bytes = canonical_json_bytes(data)
    corpus_rel = f"corpus/{case_id}/corpus.json"
    target = workspace_root / corpus_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw_bytes)
    return corpus_rel, sha256_bytes(raw_bytes), len(data["records"])


def _setup_retriever(
    workspace_root: Path,
    corpus_dict: dict | None = None,
    case_id: str = CASE_ID,
) -> tuple[Any, str, RunStore]:
    """Setup a fully-audited retriever bound to an admitted run."""
    rel, sha, count = _setup_workspace_corpus(workspace_root, corpus_dict, case_id)
    store = RunStore(workspace_root)
    run = store.create_run()
    retriever = bind_corpus(
        workspace_root,
        corpus_relpath=rel,
        corpus_sha256=sha,
        case_id=case_id,
        record_count=count,
        run_id=run.run_id,
        store=store,
    )
    return retriever, run.run_id, store


# =========================================================================
# VM-UNIT-05: Ranking and Payload Construction Unit Tests
# =========================================================================


def test_bm25_positive_idf_and_length_normalization() -> None:
    """Positive-IDF BM25 must produce non-negative scores and reward term matches."""
    docs = {
        "d1": "migraine treatment with beta blockers",
        "d2": "cluster headache treatment protocols",
        "d3": "neuroimaging studies of brain disorders",
    }
    stats = build_collection(docs, label="test.docs")
    query = ("migraine", "treatment")
    score_d1 = bm25_score(query, stats.documents["d1"], stats)
    score_d2 = bm25_score(query, stats.documents["d2"], stats)
    score_d3 = bm25_score(query, stats.documents["d3"], stats)

    assert score_d1 > score_d2 > 0.0
    assert score_d3 == 0.0


def test_ranking_enforces_paper_tie_break_lexicographically() -> None:
    """When paper scores are equal, stable tie-break uses paper_id ascending."""
    shared_text = "Standard clinical observation and methodology."
    paper_b = EligiblePaper(
        paper_id="paper-beta",
        title="Same Title",
        segments=(
            EligibleSegment(
                segment_id="paper-beta:s1",
                paper_id="paper-beta",
                content_type="publisher_abstract",
                text=shared_text,
                content_item_order=0,
                source_start=0,
                source_end=len(shared_text),
                sha256=sha256_bytes(shared_text.encode("utf-8")),
            ),
        ),
    )
    paper_a = EligiblePaper(
        paper_id="paper-alpha",
        title="Same Title",
        segments=(
            EligibleSegment(
                segment_id="paper-alpha:s1",
                paper_id="paper-alpha",
                content_type="publisher_abstract",
                text=shared_text,
                content_item_order=0,
                source_start=0,
                source_end=len(shared_text),
                sha256=sha256_bytes(shared_text.encode("utf-8")),
            ),
        ),
    )
    # Give input in reverse order (beta then alpha)
    result = rank_corpus(("clinical", "methodology"), (paper_b, paper_a))
    returned_ids = [p["paper_id"] for p in result.payload["papers"]]
    assert returned_ids == ["paper-alpha", "paper-beta"]


def test_ranking_enforces_segment_tie_break() -> None:
    """Within-paper segments tie-break by content_item_order, source_start, segment_id."""
    text1 = "Identical segment text."
    text2 = "Identical segment text."
    paper = EligiblePaper(
        paper_id="paper-01",
        title="Test Title",
        segments=(
            EligibleSegment(
                segment_id="paper-01:seg-b",
                paper_id="paper-01",
                content_type="publisher_abstract",
                text=text2,
                content_item_order=1,
                source_start=50,
                source_end=50 + len(text2),
                sha256=sha256_bytes(text2.encode("utf-8")),
            ),
            EligibleSegment(
                segment_id="paper-01:seg-a",
                paper_id="paper-01",
                content_type="publisher_abstract",
                text=text1,
                content_item_order=0,
                source_start=0,
                source_end=len(text1),
                sha256=sha256_bytes(text1.encode("utf-8")),
            ),
        ),
    )
    result = rank_corpus(("identical",), (paper,), segments_per_paper=1)
    # The chosen segment must be seg-a due to content_item_order=0
    assert result.payload["papers"][0]["segments"][0]["text"] == text1


def test_output_budget_and_payload_allowlist() -> None:
    """Payload must respect paper cap, segment cap, and strictly contain allowlisted keys."""
    corpus_dict = _sample_corpus_dict()
    papers, _ = load_eligible_candidates(corpus_dict)
    result = rank_corpus(("migraine",), papers)

    # 1. Budget caps
    assert len(result.payload["papers"]) <= PAPER_CAP
    total_segments = sum(len(p["segments"]) for p in result.payload["papers"])
    assert total_segments <= TOTAL_SEGMENT_CAP
    for p in result.payload["papers"]:
        assert len(p["segments"]) <= SEGMENTS_PER_PAPER

    # 2. Strict allowlist validation
    assert set(result.payload.keys()) == {"papers"}
    for p in result.payload["papers"]:
        assert set(p.keys()) == {"paper_id", "title", "segments"}
        assert isinstance(p["paper_id"], str)
        assert isinstance(p["title"], str)
        assert isinstance(p["segments"], list)
        for s in p["segments"]:
            assert set(s.keys()) == {"content_type", "text"}
            assert s["content_type"] == "publisher_abstract"
            assert isinstance(s["text"], str)

    # 3. Canonical JSON bytes and SHA-256
    expected_bytes = canonical_json_bytes(result.payload)
    assert result.payload_bytes == expected_bytes
    assert result.payload_sha256 == sha256_bytes(expected_bytes)


# =========================================================================
# VM-CONTRACT-020-01: Model Input Boundary Tests
# =========================================================================


def test_input_validation_accepts_valid_natural_language_query(tmp_path: Path) -> None:
    """Valid natural language query passes input validation."""
    retriever, _, _ = _setup_retriever(tmp_path)
    res = retriever.search(
        {"query": "What are the preventive treatments for migraine?"}
    )
    assert "papers" in res
    assert len(res["papers"]) > 0


def test_input_validation_rejects_non_dict_arguments(tmp_path: Path) -> None:
    """Non-dict tool arguments fail closed with INVALID_QUERY."""
    retriever, _, _ = _setup_retriever(tmp_path)
    for bad in ["migraine", ["migraine"], None, 123]:
        with pytest.raises(IdeationInputError) as exc:
            retriever.search(bad)  # type: ignore[arg-type]
        assert exc.value.code == "INVALID_QUERY"


def test_input_validation_rejects_unknown_fields(tmp_path: Path) -> None:
    """Any extra/unknown argument in tool input must be rejected."""
    retriever, _, _ = _setup_retriever(tmp_path)
    for bad_args in [
        {"query": "migraine", "top_k": 5},
        {"query": "migraine", "corpus": "custom.json"},
        {"query": "migraine", "case_id": "other"},
        {"query": "migraine", "filter": "year>2020"},
        {"query": "migraine", "search_mode": "dense"},
    ]:
        with pytest.raises(IdeationInputError) as exc:
            retriever.search(bad_args)
        assert exc.value.code == "INVALID_QUERY"
        assert "Unknown tool arguments" in exc.value.message


def test_input_validation_rejects_empty_or_whitespace_query(tmp_path: Path) -> None:
    """Empty or whitespace-only query fails closed with INVALID_QUERY."""
    retriever, _, _ = _setup_retriever(tmp_path)
    for empty in ["", "   ", "\t\n  \r"]:
        with pytest.raises(IdeationInputError) as exc:
            retriever.search({"query": empty})
        assert exc.value.code == "INVALID_QUERY"


def test_input_validation_rejects_non_string_query(tmp_path: Path) -> None:
    """Non-string query value fails closed with INVALID_QUERY."""
    retriever, _, _ = _setup_retriever(tmp_path)
    for bad_query in [123, True, {"text": "migraine"}, ["migraine"]]:
        with pytest.raises(IdeationInputError) as exc:
            retriever.search({"query": bad_query})
        assert exc.value.code == "INVALID_QUERY"


def test_input_validation_rejects_query_exceeding_scalar_limit(tmp_path: Path) -> None:
    """Query exceeding 256 scalar characters fails closed with QUERY_TOO_LONG."""
    retriever, _, _ = _setup_retriever(tmp_path)
    long_query = "migraine " * 35  # > 256 chars
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": long_query})
    assert exc.value.code == "QUERY_TOO_LONG"
    assert exc.value.details["maximum"] == 256
    assert exc.value.details["actual"] > 256


def test_input_validation_rejects_unpaired_surrogates(tmp_path: Path) -> None:
    """Query with unpaired surrogate fails closed."""
    retriever, _, _ = _setup_retriever(tmp_path)
    surrogate_query = "migraine \ud800 investigation"
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": surrogate_query})
    assert exc.value.code == "INVALID_QUERY"
    assert "surrogate" in exc.value.message


def test_input_validation_rejects_query_with_no_searchable_tokens(
    tmp_path: Path,
) -> None:
    """Query with only symbols/punctuation yields no tokens and fails with INVALID_QUERY."""
    retriever, _, _ = _setup_retriever(tmp_path)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "??? !!! --- ... @@@ $$$"})
    assert exc.value.code == "INVALID_QUERY"
    assert "no searchable tokens" in exc.value.message


# =========================================================================
# VM-CONTRACT-020-02: Scope Binding Invariants Tests
# =========================================================================


def test_scope_binding_fails_closed_if_corpus_file_tampered(tmp_path: Path) -> None:
    """If corpus file bytes are modified on disk, retriever fails closed immediately."""
    rel, sha, count = _setup_workspace_corpus(tmp_path)
    store = RunStore(tmp_path)
    run = store.create_run()
    retriever = bind_corpus(
        tmp_path,
        corpus_relpath=rel,
        corpus_sha256=sha,
        case_id=CASE_ID,
        record_count=count,
        run_id=run.run_id,
        store=store,
    )

    # Tamper with file
    corpus_file = tmp_path / rel
    corpus_file.write_bytes(corpus_file.read_bytes() + b" ")

    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "migraine"})
    assert exc.value.code == "HASH_MISMATCH"


def test_scope_binding_fails_closed_if_corpus_file_missing(tmp_path: Path) -> None:
    """If corpus file is deleted, retriever fails closed."""
    rel, sha, count = _setup_workspace_corpus(tmp_path)
    store = RunStore(tmp_path)
    run = store.create_run()
    retriever = bind_corpus(
        tmp_path,
        corpus_relpath=rel,
        corpus_sha256=sha,
        case_id=CASE_ID,
        record_count=count,
        run_id=run.run_id,
        store=store,
    )

    (tmp_path / rel).unlink()
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "migraine"})
    assert exc.value.code == "MISSING_CORPUS"


def test_scope_binding_fails_closed_if_corpus_case_mismatch(tmp_path: Path) -> None:
    """If corpus case_id does not match the bound case_id, fails closed."""
    data = _sample_corpus_dict(case_id="case-different")
    rel, sha, count = _setup_workspace_corpus(tmp_path, corpus_dict=data)
    store = RunStore(tmp_path)
    run = store.create_run()
    retriever = bind_corpus(
        tmp_path,
        corpus_relpath=rel,
        corpus_sha256=sha,
        case_id=CASE_ID,
        record_count=count,
        run_id=run.run_id,
        store=store,
    )
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "migraine"})
    assert exc.value.code == "IDENTITY_MISMATCH"


# =========================================================================
# VM-CONTRACT-020-03: Reference Content Eligibility Tests
# =========================================================================


def test_eligibility_skips_records_with_only_ineligible_content() -> None:
    """Records lacking validated publisher_abstract are excluded from candidates."""
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-eligible",
                "title": "Eligible Paper Title",
                "content_items": [
                    {
                        "content_id": "abs-01",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": "Validated abstract text.",
                        "sha256": sha256_bytes(b"Validated abstract text."),
                    }
                ],
            },
            {
                "paper_id": "paper-ineligible-fulltext-only",
                "title": "Fulltext Only Paper",
                "content_items": [
                    {
                        "content_id": "ft-01",
                        "type": "official_full_text",
                        "status": "validated",
                        "text": "Official full text.",
                        "sha256": sha256_bytes(b"Official full text."),
                    }
                ],
            },
            {
                "paper_id": "paper-ineligible-unvalidated",
                "title": "Unvalidated Abstract Paper",
                "content_items": [
                    {
                        "content_id": "abs-02",
                        "type": "publisher_abstract",
                        "status": "pending",
                        "text": "Pending abstract.",
                        "sha256": sha256_bytes(b"Pending abstract."),
                    }
                ],
            },
        ],
    }
    eligible, ineligible = load_eligible_candidates(data)
    assert len(eligible) == 1
    assert eligible[0].paper_id == "paper-eligible"
    assert len(ineligible) == 2
    ineligible_ids = {item["paper_id"] for item in ineligible}
    assert ineligible_ids == {
        "paper-ineligible-fulltext-only",
        "paper-ineligible-unvalidated",
    }


def test_eligibility_fails_closed_if_no_eligible_candidates_in_corpus(
    tmp_path: Path,
) -> None:
    """If corpus contains zero eligible candidates, fail closed; not a legal empty result."""
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-only-ft",
                "title": "Fulltext Only",
                "content_items": [
                    {
                        "content_id": "ft-01",
                        "type": "official_full_text",
                        "status": "validated",
                        "text": "Full text body.",
                        "sha256": sha256_bytes(b"Full text body."),
                    }
                ],
            }
        ],
    }
    retriever, _, _ = _setup_retriever(tmp_path, corpus_dict=data)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "migraine"})
    assert exc.value.code == "NO_ELIGIBLE_CANDIDATES"


# =========================================================================
# VM-CONTRACT-020-04: Audit Release Gate & Error Vocabulary Tests
# =========================================================================


def test_audit_release_gate_persists_and_verifies_evidence(tmp_path: Path) -> None:
    """Audit release gate writes payload and audit artifacts, appends event, and verifies."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    retriever, run_id, store = _setup_retriever(workspace)

    payload = retriever.search(
        {"query": "migraine prevention trials"}, operation_seq=1, attempt_seq=1
    )
    assert "papers" in payload

    # 1. Verify operation artifacts exist
    run_root = workspace / "artifacts/ideation-runs" / run_id
    attempt_dir = run_root / "artifacts/operations/000001/attempts/000001"
    assert (attempt_dir / "payload.json").is_file()
    assert (attempt_dir / "audit.json").is_file()

    # 2. Verify payload on disk matches returned payload
    payload_on_disk = parse_json_bytes(
        (attempt_dir / "payload.json").read_bytes(), label="disk payload"
    )
    assert payload_on_disk == payload

    # 3. Verify audit on disk contains private fields
    audit_on_disk = parse_json_bytes(
        (attempt_dir / "audit.json").read_bytes(), label="disk audit"
    )
    assert audit_on_disk["schema_version"] == "retrieval-audit-v1.0.0"
    assert audit_on_disk["case_id"] == CASE_ID
    assert audit_on_disk["outcome"] == "success"
    assert "candidate_scores" in audit_on_disk
    assert len(audit_on_disk["candidate_scores"]) > 0
    assert audit_on_disk["canonical_model_payload_sha256"] == sha256_bytes(
        canonical_json_bytes(payload)
    )

    # 4. Verify event in events/
    events_dir = run_root / "events"
    event_files = sorted(events_dir.glob("*.json"))
    assert len(event_files) == 1
    event_doc = parse_json_bytes(event_files[0].read_bytes(), label="event 1")
    assert event_doc["event_type"] == "operation.finished"
    assert event_doc["operation"]["operation_seq"] == 1
    assert event_doc["operation"]["operation_kind"] == "literature_retrieval"
    assert len(event_doc["artifact_refs"]) == 2

    # 5. Verify chain integrity
    assert store.verify_chain(run_id) == 1


def test_audit_release_gate_fails_closed_if_disk_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If audit artifact persistence or verification fails, payload is never released."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    retriever, run_id, store = _setup_retriever(workspace)

    # Monkeypatch store.read_artifact to simulate corrupted file read during gate
    def _corrupt_read(*args: object, **kwargs: object) -> bytes:
        raise OSError("Disk corruption during readback")

    monkeypatch.setattr(store, "read_artifact", _corrupt_read)

    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "migraine"}, operation_seq=1, attempt_seq=1)

    assert exc.value.code == "AUDIT_RELEASE_GATE_FAILED"


def test_input_error_records_failed_operation_event(tmp_path: Path) -> None:
    """When model submits an invalid query, a failed operation audit is recorded."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    retriever, run_id, store = _setup_retriever(workspace)

    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "   "}, operation_seq=1, attempt_seq=1)
    assert exc.value.code == "INVALID_QUERY"

    # Evidence of failure must be retained
    run_root = workspace / "artifacts/ideation-runs" / run_id
    audit_file = run_root / "artifacts/operations/000001/attempts/000001/audit.json"
    assert audit_file.is_file()
    audit_doc = parse_json_bytes(audit_file.read_bytes(), label="failed audit")
    assert audit_doc["outcome"] == "input_error"

    event_file = run_root / "events/00000001.json"
    assert event_file.is_file()
    event_doc = parse_json_bytes(event_file.read_bytes(), label="failed event")
    assert event_doc["event_type"] == "operation.failed"
    assert event_doc["payload"]["status"] == "input_error"


# =========================================================================
# VM-REPLAY-03: Deterministic Replay Tests
# =========================================================================


def test_replay_produces_identical_canonical_payloads_and_hashes(
    tmp_path: Path,
) -> None:
    """Repeated retrievals with same pinned corpus and normalized query must be byte-identical."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    retriever, _, _ = _setup_retriever(workspace)

    query = {"query": "monoclonal antibodies targeting CGRP for chronic migraine"}

    res1 = retriever.search(query, operation_seq=1, attempt_seq=1)
    bytes1 = canonical_json_bytes(res1)
    hash1 = sha256_bytes(bytes1)

    res2 = retriever.search(query, operation_seq=2, attempt_seq=1)
    bytes2 = canonical_json_bytes(res2)
    hash2 = sha256_bytes(bytes2)

    res3 = retriever.search(query, operation_seq=3, attempt_seq=1)
    bytes3 = canonical_json_bytes(res3)
    hash3 = sha256_bytes(bytes3)

    assert bytes1 == bytes2 == bytes3
    assert hash1 == hash2 == hash3


# =========================================================================
# Adversarial Hardening Tests
# =========================================================================


def test_adversarial_duplicate_content_id_across_papers_does_not_collide_in_bm25(
    tmp_path: Path,
) -> None:
    """When multiple papers share identical content_id (e.g. 'item-01'), segment IDs must not collide."""
    text_migraine = (
        "Groundbreaking monoclonal antibody clinical trials for migraine prophylaxis."
    )
    text_cardiac = "Emergency protocol for acute myocardial infarction and ventricular fibrillation."
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-cardiac",
                "title": "Cardiac Resuscitation Handbook",
                "content_items": [
                    {
                        "content_id": "item-01",  # Same content_id
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": text_cardiac,
                        "sha256": sha256_bytes(text_cardiac.encode("utf-8")),
                    }
                ],
            },
            {
                "paper_id": "paper-migraine",
                "title": "Migraine Treatment Innovations",
                "content_items": [
                    {
                        "content_id": "item-01",  # Same content_id
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": text_migraine,
                        "sha256": sha256_bytes(text_migraine.encode("utf-8")),
                    }
                ],
            },
        ],
    }
    retriever, _, _ = _setup_retriever(tmp_path, corpus_dict=data)
    result = retriever.search(
        {"query": "migraine antibody trials"}, operation_seq=1, attempt_seq=1
    )
    # The migraine paper MUST be ranked first despite identical content_id in source records
    assert result["papers"][0]["paper_id"] == "paper-migraine"
    assert "migraine" in result["papers"][0]["segments"][0]["text"].lower()


def test_adversarial_duplicate_paper_id_in_corpus_fails_closed(tmp_path: Path) -> None:
    """Corpus with duplicate paper_id records must fail closed with INVALID_CORPUS."""
    abstract = "Valid abstract text."
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-dup",
                "title": "Title One",
                "content_items": [
                    {
                        "content_id": "item-01",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract,
                        "sha256": sha256_bytes(abstract.encode("utf-8")),
                    }
                ],
            },
            {
                "paper_id": "paper-dup",  # Duplicate paper_id
                "title": "Title Two",
                "content_items": [
                    {
                        "content_id": "item-02",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract,
                        "sha256": sha256_bytes(abstract.encode("utf-8")),
                    }
                ],
            },
        ],
    }
    retriever, _, _ = _setup_retriever(tmp_path, corpus_dict=data)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "test"}, operation_seq=1, attempt_seq=1)
    assert exc.value.code == "INVALID_CORPUS"
    assert "Duplicate paper_id" in exc.value.message


def test_adversarial_duplicate_content_id_within_paper_fails_closed(
    tmp_path: Path,
) -> None:
    """Paper with duplicate content_id must fail closed with INVALID_CORPUS."""
    abstract = "Valid abstract text."
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-01",
                "title": "Title One",
                "content_items": [
                    {
                        "content_id": "item-01",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract,
                        "sha256": sha256_bytes(abstract.encode("utf-8")),
                    },
                    {
                        "content_id": "item-01",  # Duplicate content_id in same paper
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract,
                        "sha256": sha256_bytes(abstract.encode("utf-8")),
                    },
                ],
            }
        ],
    }
    retriever, _, _ = _setup_retriever(tmp_path, corpus_dict=data)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "test"}, operation_seq=1, attempt_seq=1)
    assert exc.value.code == "INVALID_CORPUS"
    assert "Duplicate content_id" in exc.value.message


def test_adversarial_heterogeneous_non_string_keys_in_arguments(tmp_path: Path) -> None:
    """Non-string dictionary keys in tool input must fail with INVALID_QUERY without throwing TypeError."""
    retriever, _, _ = _setup_retriever(tmp_path)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({1: "bad", "query": "migraine"})
    assert exc.value.code == "INVALID_QUERY"
    assert "Unknown tool arguments" in exc.value.message


def test_adversarial_unknown_arguments_records_failed_operation_event(
    tmp_path: Path,
) -> None:
    """When arguments contain unknown keys, operation.failed event and audit are persisted."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    retriever, run_id, store = _setup_retriever(workspace)

    with pytest.raises(IdeationInputError) as exc:
        retriever.search(
            {"query": "migraine", "top_k": 5}, operation_seq=1, attempt_seq=1
        )
    assert exc.value.code == "INVALID_QUERY"

    # Verify audit.json and operation.failed event are persisted
    run_root = workspace / "artifacts/ideation-runs" / run_id
    audit_file = run_root / "artifacts/operations/000001/attempts/000001/audit.json"
    assert audit_file.is_file()
    audit_doc = parse_json_bytes(audit_file.read_bytes(), label="failed audit")
    assert audit_doc["outcome"] == "input_error"

    event_file = run_root / "events/00000001.json"
    assert event_file.is_file()
    event_doc = parse_json_bytes(event_file.read_bytes(), label="failed event")
    assert event_doc["event_type"] == "operation.failed"
    assert event_doc["payload"]["status"] == "input_error"


def test_adversarial_missing_run_context_fails_closed(tmp_path: Path) -> None:
    """Calling search() without an admitted run identity fails closed."""
    rel, sha, count = _setup_workspace_corpus(tmp_path)
    # Deliberately omit run_id
    retriever = bind_corpus(
        tmp_path,
        corpus_relpath=rel,
        corpus_sha256=sha,
        case_id=CASE_ID,
        record_count=count,
        run_id=None,
    )
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "migraine"})
    assert exc.value.code == "AUDIT_RELEASE_GATE_FAILED"


def test_adversarial_paper_with_unsearchable_title_fails_closed(tmp_path: Path) -> None:
    """Paper with zero searchable tokens in title fails closed with INVALID_CORPUS."""
    abstract = "Valid abstract text."
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-01",
                "title": "... ::: --- @@@",  # No searchable tokens
                "content_items": [
                    {
                        "content_id": "item-01",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": abstract,
                        "sha256": sha256_bytes(abstract.encode("utf-8")),
                    }
                ],
            }
        ],
    }
    retriever, _, _ = _setup_retriever(tmp_path, corpus_dict=data)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "test"})
    assert exc.value.code == "INVALID_CORPUS"
    assert "no searchable tokens" in exc.value.message


def test_adversarial_segment_with_unsearchable_text_fails_closed(
    tmp_path: Path,
) -> None:
    """Abstract segment with zero searchable tokens fails closed with INVALID_CORPUS."""
    data = {
        "case_id": CASE_ID,
        "records": [
            {
                "paper_id": "paper-01",
                "title": "Valid Title",
                "content_items": [
                    {
                        "content_id": "item-01",
                        "type": "publisher_abstract",
                        "status": "validated",
                        "text": "... ??? ---",  # No searchable tokens
                        "sha256": sha256_bytes(b"... ??? ---"),
                    }
                ],
            }
        ],
    }
    retriever, _, _ = _setup_retriever(tmp_path, corpus_dict=data)
    with pytest.raises(IdeationInputError) as exc:
        retriever.search({"query": "test"})
    assert exc.value.code == "INVALID_CORPUS"
    assert "no searchable tokens" in exc.value.message


def test_adversarial_invalid_coordinates_fail_closed(tmp_path: Path) -> None:
    """Invalid operation_seq or attempt_seq fail closed with INVALID_COORDINATE."""
    retriever, _, _ = _setup_retriever(tmp_path)
    for bad_seq in [0, -1, "1", 1.5]:
        with pytest.raises(IdeationInputError) as exc:
            retriever.search({"query": "migraine"}, operation_seq=bad_seq)  # type: ignore[arg-type]
        assert exc.value.code == "INVALID_COORDINATE"
    for bad_att in [0, -1, "1", 1.5]:
        with pytest.raises(IdeationInputError) as exc:
            retriever.search({"query": "migraine"}, attempt_seq=bad_att)  # type: ignore[arg-type]
        assert exc.value.code == "INVALID_COORDINATE"
