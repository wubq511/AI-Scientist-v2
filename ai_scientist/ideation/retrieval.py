"""Scoped Literature Retriever for admitted Ideation Runs (tickets 04 and 05).

Binds to exactly one preflight-validated Approved Target Reference Corpus.
Executes frozen Robertson/Sparck Jones positive-IDF BM25 scoring with
lexical_normalization_v1, applies candidate eligibility and output budgets,
persists the private Retrieval Audit Event and payload artifacts to the
Evidence Chain, verifies persistence through the Audit Release Gate, and
returns the minimal canonical model-visible Retrieval Result.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import re
import time
from typing import Any
import unicodedata

from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
    workspace_relative_path,
)
from .contract import _now
from .errors import fail
from .run_store import RunStore

RETRIEVAL_POLICY_VERSION = "scoped-retrieval-policy-v1"
NORMALIZATION_VERSION = "lexical_normalization_v1"
RANKING_VERSION = "bm25_v1"
RETRIEVAL_AUDIT_SCHEMA_VERSION = "retrieval-audit-v1.0.0"

TOKEN_PATTERN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*(?:\+{1,2}|#)?", re.UNICODE)
APOSTROPHES = {"\u2018", "\u2019", "\u02bc"}
MAX_QUERY_SCALARS = 256

PAPER_CAP = 3
SEGMENTS_PER_PAPER = 1
TOTAL_SEGMENT_CAP = 3

BM25_K1 = 1.6
BM25_B = 0.5
TITLE_WEIGHT = 1.0
PHRASE_BONUS = False
AGGREGATION = "max"

ALLOWED_TOOL_ARGUMENTS = frozenset({"query"})


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    version: str = NORMALIZATION_VERSION


def _validate_scalar_string(value: str, *, label: str) -> None:
    for index, char in enumerate(value):
        if 0xD800 <= ord(char) <= 0xDFFF:
            fail(
                "INVALID_QUERY",
                f"{label} contains an unpaired surrogate",
                index=index,
            )


def normalize_text(value: str, *, label: str = "text") -> str:
    if not isinstance(value, str):
        fail("INVALID_TEXT", f"{label} must be a string")
    _validate_scalar_string(value, label=label)
    normalized = unicodedata.normalize("NFC", value).casefold()
    translated: list[str] = []
    for char in normalized:
        if unicodedata.category(char) == "Pd":
            translated.append("-")
        elif char in APOSTROPHES:
            translated.append("'")
        else:
            translated.append(char)
    return " ".join("".join(translated).split())


def tokenize_normalized(value: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in TOKEN_PATTERN.finditer(value))


def tokenize_text(value: str, *, label: str = "text") -> tuple[str, ...]:
    return tokenize_normalized(normalize_text(value, label=label))


def normalize_query(value: Any) -> NormalizedQuery:
    """Normalize and tokenize the single model query; fail closed on input errors."""
    if not isinstance(value, str):
        fail("INVALID_QUERY", "query must be a string")
    _validate_scalar_string(value, label="query")
    trimmed = value.strip()
    if not trimmed:
        fail("INVALID_QUERY", "query must be non-empty after trimming")
    if len(trimmed) > MAX_QUERY_SCALARS:
        fail(
            "QUERY_TOO_LONG",
            "query exceeds the lexical_normalization_v1 scalar limit",
            maximum=MAX_QUERY_SCALARS,
            actual=len(trimmed),
        )
    normalized = normalize_text(trimmed, label="query")
    tokens = tokenize_normalized(normalized)
    if not tokens:
        fail("INVALID_QUERY", "query contains no searchable tokens after normalization")
    return NormalizedQuery(raw=value, normalized=normalized, tokens=tokens)


@dataclass(frozen=True, slots=True)
class CollectionStats:
    documents: dict[str, tuple[str, ...]]
    document_frequency: Counter[str]
    collection_frequency: Counter[str]
    average_document_length: float

    @property
    def size(self) -> int:
        return len(self.documents)


def build_collection(documents: dict[str, str], *, label: str) -> CollectionStats:
    if not documents:
        fail("INVALID_CORPUS", f"{label} collection is empty")
    tokenized: dict[str, tuple[str, ...]] = {}
    document_frequency: Counter[str] = Counter()
    collection_frequency: Counter[str] = Counter()
    total_length = 0
    for document_id, text in documents.items():
        tokens = tokenize_text(text, label=f"{label}.{document_id}")
        tokenized[document_id] = tokens
        total_length += len(tokens)
        document_frequency.update(set(tokens))
        collection_frequency.update(tokens)
    average_document_length = total_length / len(tokenized)
    if average_document_length <= 0 or not math.isfinite(average_document_length):
        fail("INVALID_CORPUS", f"{label} has invalid collection statistics")
    return CollectionStats(
        documents=tokenized,
        document_frequency=document_frequency,
        collection_frequency=collection_frequency,
        average_document_length=average_document_length,
    )


def bm25_score(
    query_tokens: tuple[str, ...],
    document_tokens: tuple[str, ...],
    stats: CollectionStats,
    *,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> float:
    """Robertson/Sparck Jones positive-IDF BM25."""
    if stats.average_document_length <= 0:
        fail("INVALID_SCORE", "BM25 average document length must be positive")
    counts = Counter(document_tokens)
    document_length = len(document_tokens)
    score = 0.0
    for token in dict.fromkeys(query_tokens):
        term_frequency = counts[token]
        if term_frequency == 0:
            continue
        document_frequency = stats.document_frequency[token]
        idf = math.log(
            1.0 + (stats.size - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        denominator = term_frequency + k1 * (
            1.0 - b + b * document_length / stats.average_document_length
        )
        if denominator <= 0:
            fail("INVALID_SCORE", "BM25 denominator must be positive")
        score += idf * (term_frequency * (k1 + 1.0)) / denominator
    return score


@dataclass(frozen=True, slots=True)
class EligibleSegment:
    segment_id: str
    paper_id: str
    content_type: str
    text: str
    content_item_order: int
    source_start: int
    source_end: int
    sha256: str


@dataclass(frozen=True, slots=True)
class EligiblePaper:
    paper_id: str
    title: str
    segments: tuple[EligibleSegment, ...]


@dataclass(frozen=True, slots=True)
class RankedSegment:
    segment: EligibleSegment
    score: float


@dataclass(frozen=True, slots=True)
class RankedPaper:
    paper: EligiblePaper
    score: float
    segments: tuple[RankedSegment, ...]
    title_score: float


@dataclass(frozen=True, slots=True)
class ScoredResult:
    papers: tuple[RankedPaper, ...]
    payload: dict[str, Any]
    payload_sha256: str
    payload_bytes: bytes


def load_eligible_candidates(
    corpus_data: dict[str, Any],
) -> tuple[tuple[EligiblePaper, ...], list[dict[str, Any]]]:
    """Extract eligible publisher_abstract segments; exclude unvalidated / other types.

    Enforces duplicate detection, title searchability, and globally qualified segment IDs.
    """
    records = corpus_data.get("records")
    if not isinstance(records, list):
        fail("INVALID_CORPUS", "Corpus records must be an array")

    eligible_papers: list[EligiblePaper] = []
    ineligible_candidates: list[dict[str, Any]] = []
    seen_paper_ids: set[str] = set()

    for record in records:
        if not isinstance(record, dict):
            fail("INVALID_CORPUS", "Corpus record must be an object")
        paper_id = record.get("paper_id")
        title = record.get("title")
        if not isinstance(paper_id, str) or not paper_id:
            fail("INVALID_CORPUS", "Paper record missing valid paper_id")
        if not isinstance(title, str) or not title:
            fail("INVALID_CORPUS", "Paper record missing valid title")

        if paper_id in seen_paper_ids:
            fail("INVALID_CORPUS", f"Duplicate paper_id: {paper_id}")
        seen_paper_ids.add(paper_id)

        content_items = record.get("content_items", [])
        if not isinstance(content_items, list):
            fail("INVALID_CORPUS", f"Paper {paper_id} content_items must be a list")

        eligible_segments: list[EligibleSegment] = []
        seen_content_ids: set[str] = set()

        for order, item in enumerate(content_items):
            if not isinstance(item, dict):
                continue
            item_status = item.get("status")
            item_type = item.get("type")
            # Only validated publisher_abstract is eligible in v1
            if item_status == "validated" and item_type == "publisher_abstract":
                text = item.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                # Segment text must contain at least one searchable token
                if not tokenize_text(text, label=f"{paper_id}.abstract[{order}]"):
                    fail(
                        "INVALID_CORPUS",
                        f"Content item in paper {paper_id} has no searchable tokens",
                    )
                sha = item.get("sha256")
                if (
                    not isinstance(sha, str)
                    or sha256_bytes(text.encode("utf-8")) != sha
                ):
                    fail(
                        "INVALID_CORPUS",
                        f"Content item hash mismatch for paper {paper_id}",
                    )
                content_id = item.get("content_id", f"abstract-{order:02d}")
                if content_id in seen_content_ids:
                    fail(
                        "INVALID_CORPUS",
                        f"Duplicate content_id '{content_id}' in paper {paper_id}",
                    )
                seen_content_ids.add(content_id)

                # Qualify segment_id with paper_id to prevent collision across papers
                qualified_segment_id = f"{paper_id}:{content_id}"
                eligible_segments.append(
                    EligibleSegment(
                        segment_id=qualified_segment_id,
                        paper_id=paper_id,
                        content_type="publisher_abstract",
                        text=text,
                        content_item_order=order,
                        source_start=0,
                        source_end=len(text),
                        sha256=sha,
                    )
                )

        if eligible_segments:
            # Paper title must contain at least one searchable token
            if not tokenize_text(title, label=f"{paper_id}.title"):
                fail(
                    "INVALID_CORPUS",
                    f"Paper {paper_id} title has no searchable tokens",
                )
            eligible_papers.append(
                EligiblePaper(
                    paper_id=paper_id,
                    title=title,
                    segments=tuple(eligible_segments),
                )
            )
        else:
            ineligible_candidates.append(
                {"paper_id": paper_id, "reason": "no_eligible_content"}
            )

    if not eligible_papers:
        fail("NO_ELIGIBLE_CANDIDATES", "Corpus contains no eligible reference content")

    return tuple(eligible_papers), ineligible_candidates


def rank_corpus(
    query_tokens: tuple[str, ...],
    eligible_papers: tuple[EligiblePaper, ...],
    *,
    paper_cap: int = PAPER_CAP,
    segments_per_paper: int = SEGMENTS_PER_PAPER,
    total_segment_cap: int = TOTAL_SEGMENT_CAP,
) -> ScoredResult:
    """Perform frozen BM25 scoring and construct the canonical model payload."""
    title_stats = build_collection(
        {paper.paper_id: paper.title for paper in eligible_papers},
        label="corpus.titles",
    )
    segment_stats = build_collection(
        {
            segment.segment_id: segment.text
            for paper in eligible_papers
            for segment in paper.segments
        },
        label="corpus.segments",
    )

    ranked_papers: list[RankedPaper] = []
    for paper in eligible_papers:
        title_score = bm25_score(
            query_tokens,
            title_stats.documents[paper.paper_id],
            title_stats,
            k1=BM25_K1,
            b=BM25_B,
        )
        ranked_segments: list[RankedSegment] = []
        for segment in paper.segments:
            seg_score = bm25_score(
                query_tokens,
                segment_stats.documents[segment.segment_id],
                segment_stats,
                k1=BM25_K1,
                b=BM25_B,
            )
            ranked_segments.append(RankedSegment(segment=segment, score=seg_score))

        # Sort segments: score descending -> content_item_order -> source_start -> segment_id
        ranked_segments.sort(
            key=lambda s: (
                -s.score,
                s.segment.content_item_order,
                s.segment.source_start,
                s.segment.segment_id,
            )
        )
        content_score = ranked_segments[0].score
        paper_score = content_score + TITLE_WEIGHT * title_score
        if not math.isfinite(paper_score):
            fail("INVALID_SCORE", f"Non-finite score for paper {paper.paper_id}")

        ranked_papers.append(
            RankedPaper(
                paper=paper,
                score=paper_score,
                segments=tuple(ranked_segments),
                title_score=title_score,
            )
        )

    # Sort papers: score descending -> paper_id ascending (stable tie-break)
    ranked_papers.sort(key=lambda p: (-p.score, p.paper.paper_id))

    # Assemble model-visible payload
    payload_papers: list[dict[str, Any]] = []
    remaining_segments = total_segment_cap
    for ranked_paper in ranked_papers[:paper_cap]:
        if remaining_segments == 0:
            break
        take = min(segments_per_paper, remaining_segments)
        selected = ranked_paper.segments[:take]
        if not selected:
            continue
        payload_papers.append(
            {
                "paper_id": ranked_paper.paper.paper_id,
                "title": ranked_paper.paper.title,
                "segments": [
                    {
                        "content_type": item.segment.content_type,
                        "text": item.segment.text,
                    }
                    for item in selected
                ],
            }
        )
        remaining_segments -= len(selected)

    payload = {"papers": payload_papers}
    payload_bytes = canonical_json_bytes(payload)
    payload_sha256 = sha256_bytes(payload_bytes)
    return ScoredResult(
        papers=tuple(ranked_papers),
        payload=payload,
        payload_sha256=payload_sha256,
        payload_bytes=payload_bytes,
    )


@dataclass(frozen=True, slots=True)
class BoundCorpus:
    """A preflight-validated corpus binding; the retriever's sole scope."""

    workspace_root: Path
    corpus_relpath: str
    corpus_sha256: str
    case_id: str
    record_count: int
    run_id: str | None = None
    store: RunStore | None = None


def bind_corpus(
    workspace_root: Path,
    *,
    corpus_relpath: str,
    corpus_sha256: str,
    case_id: str,
    record_count: int,
    run_id: str | None = None,
    store: RunStore | None = None,
) -> ScopedLiteratureRetriever:
    """Construct the retriever bound to exactly one Approved corpus."""
    bound = BoundCorpus(
        workspace_root=workspace_root,
        corpus_relpath=corpus_relpath,
        corpus_sha256=corpus_sha256,
        case_id=case_id,
        record_count=record_count,
        run_id=run_id,
        store=store or (RunStore(workspace_root) if run_id is not None else None),
    )
    return ScopedLiteratureRetriever(bound)


class ScopedLiteratureRetriever:
    """The model-visible literature tool bound to one Approved corpus."""

    def __init__(self, bound: BoundCorpus) -> None:
        self._bound = bound
        self._operation_counter = 0

    @property
    def policy_version(self) -> str:
        return RETRIEVAL_POLICY_VERSION

    @property
    def bound(self) -> BoundCorpus:
        return self._bound

    def search(
        self,
        arguments: dict[str, Any],
        *,
        operation_seq: int | None = None,
        attempt_seq: int = 1,
    ) -> dict[str, Any]:
        """Execute one audited BM25 retrieval against the bound corpus.

        Enforces model input boundary, corpus re-verification, BM25 ranking,
        Retrieval Audit Event persistence, and the Audit Release Gate.
        """
        started_at = _now()
        t0 = time.perf_counter()

        # Validate sequence coordinates
        if not isinstance(attempt_seq, int) or attempt_seq < 1:
            fail("INVALID_COORDINATE", "attempt_seq must be an integer >= 1")
        if operation_seq is not None and (
            not isinstance(operation_seq, int) or operation_seq < 1
        ):
            fail("INVALID_COORDINATE", "operation_seq must be an integer >= 1")

        if operation_seq is None:
            self._operation_counter += 1
            op_seq = self._operation_counter
        else:
            op_seq = operation_seq

        # Step 1: Validate tool input boundary (unified failure recording)
        try:
            if not isinstance(arguments, dict):
                fail("INVALID_QUERY", "Retriever arguments must be a JSON object")
            extra_keys = set(arguments.keys()) - ALLOWED_TOOL_ARGUMENTS
            if extra_keys:
                fail(
                    "INVALID_QUERY",
                    f"Unknown tool arguments: {sorted(str(k) for k in extra_keys)}",
                )
            if "query" not in arguments:
                fail("INVALID_QUERY", "query argument is required")

            raw_query = arguments["query"]
            norm_query = normalize_query(raw_query)
        except Exception as exc:
            raw_q = arguments.get("query") if isinstance(arguments, dict) else arguments
            self._record_input_failure(op_seq, attempt_seq, raw_q, str(exc), started_at)
            raise

        # Step 2: Verify scope binding and corpus on disk
        corpus_path = workspace_relative_path(
            self._bound.workspace_root,
            self._bound.corpus_relpath,
            label="corpus_path",
        )
        if not corpus_path.is_file():
            fail("MISSING_CORPUS", "Bound corpus file is missing on disk")
        corpus_bytes = corpus_path.read_bytes()
        if sha256_bytes(corpus_bytes) != self._bound.corpus_sha256:
            fail("HASH_MISMATCH", "Corpus bytes do not match bound SHA-256")
        corpus_data = parse_json_bytes(corpus_bytes, label="corpus")
        if not isinstance(corpus_data, dict):
            fail("INVALID_CORPUS", "Corpus root must be a JSON object")
        if corpus_data.get("case_id") != self._bound.case_id:
            fail("IDENTITY_MISMATCH", "Corpus case_id does not match bound case")

        # Step 3: Candidate eligibility filtering
        eligible_papers, ineligible_candidates = load_eligible_candidates(corpus_data)

        # Step 4: Frozen BM25 scoring & payload construction
        scored_result = rank_corpus(norm_query.tokens, eligible_papers)
        duration_ms = round((time.perf_counter() - t0) * 1000, 3)
        finished_at = _now()

        # Step 5: Build private Retrieval Audit Event document
        outcome = "success" if scored_result.payload["papers"] else "empty"
        audit_document = {
            "schema_version": RETRIEVAL_AUDIT_SCHEMA_VERSION,
            "case_id": self._bound.case_id,
            "corpus": {
                "relpath": self._bound.corpus_relpath,
                "sha256": self._bound.corpus_sha256,
            },
            "query": {
                "raw": raw_query,
                "normalized": norm_query.normalized,
                "tokens": list(norm_query.tokens),
                "normalization_version": NORMALIZATION_VERSION,
            },
            "policy_versions": {
                "retrieval_policy": RETRIEVAL_POLICY_VERSION,
                "ranking": RANKING_VERSION,
                "normalization": NORMALIZATION_VERSION,
            },
            "ranking_parameters": {
                "k1": f"{BM25_K1:.1f}",
                "b": f"{BM25_B:.1f}",
                "title_weight": f"{TITLE_WEIGHT:.1f}",
                "phrase_bonus": PHRASE_BONUS,
                "aggregation": AGGREGATION,
            },
            "output_budget": {
                "paper_cap": PAPER_CAP,
                "segments_per_paper": SEGMENTS_PER_PAPER,
                "total_segment_cap": TOTAL_SEGMENT_CAP,
            },
            "eligible_candidates": [p.paper_id for p in eligible_papers],
            "ineligible_candidates": ineligible_candidates,
            "candidate_scores": [
                {
                    "paper_id": p.paper.paper_id,
                    "paper_score": f"{p.score:.6f}",
                    "title_score": f"{p.title_score:.6f}",
                    "segment_scores": [
                        {
                            "segment_id": s.segment.segment_id,
                            "score": f"{s.score:.6f}",
                            "content_item_order": s.segment.content_item_order,
                            "source_start": s.segment.source_start,
                            "source_end": s.segment.source_end,
                            "sha256": s.segment.sha256,
                        }
                        for s in p.segments
                    ],
                }
                for p in scored_result.papers
            ],
            "tie_break": [p.paper.paper_id for p in scored_result.papers],
            "returned_paper_ids": [
                p["paper_id"] for p in scored_result.payload["papers"]
            ],
            "segment_source_pointers": [
                {
                    "paper_id": p.paper.paper_id,
                    "segments": [
                        {
                            "segment_id": s.segment.segment_id,
                            "content_type": s.segment.content_type,
                            "content_item_order": s.segment.content_item_order,
                            "source_start": s.segment.source_start,
                            "source_end": s.segment.source_end,
                            "sha256": s.segment.sha256,
                        }
                        for s in p.segments[:SEGMENTS_PER_PAPER]
                    ],
                }
                for p in scored_result.papers[: len(scored_result.payload["papers"])]
            ],
            "canonical_model_payload_sha256": scored_result.payload_sha256,
            "outcome": outcome,
            "error": None,
            "timing": {
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": f"{duration_ms:.3f}",
            },
        }

        # Step 6: Audit Release Gate (fail closed if run identity is missing or unverified)
        if self._bound.run_id is None or self._bound.store is None:
            fail(
                "AUDIT_RELEASE_GATE_FAILED",
                "Retriever cannot release payload without admitted run audit evidence",
            )

        self._execute_audit_release_gate(
            run_id=self._bound.run_id,
            store=self._bound.store,
            op_seq=op_seq,
            attempt_seq=attempt_seq,
            audit_document=audit_document,
            payload_bytes=scored_result.payload_bytes,
            payload_sha256=scored_result.payload_sha256,
            outcome=outcome,
            paper_count=len(scored_result.payload["papers"]),
        )

        # Release the model-visible payload
        return scored_result.payload

    def _record_input_failure(
        self,
        op_seq: int,
        attempt_seq: int,
        raw_query: Any,
        error_message: str,
        started_at: str,
    ) -> None:
        """Best-effort recording of an input failure in the private evidence chain."""
        if self._bound.run_id is None or self._bound.store is None:
            return
        finished_at = _now()
        audit_doc = {
            "schema_version": RETRIEVAL_AUDIT_SCHEMA_VERSION,
            "case_id": self._bound.case_id,
            "corpus": {
                "relpath": self._bound.corpus_relpath,
                "sha256": self._bound.corpus_sha256,
            },
            "query": {
                "raw": str(raw_query),
                "normalized": None,
                "tokens": [],
                "normalization_version": NORMALIZATION_VERSION,
            },
            "outcome": "input_error",
            "error": error_message,
            "timing": {
                "started_at": started_at,
                "finished_at": finished_at,
            },
        }
        try:
            audit_bytes = canonical_json_bytes(audit_doc)
            audit_rel, _, audit_sha = self._bound.store.write_operation_artifact(
                self._bound.run_id,
                op_seq,
                attempt_seq,
                "audit.json",
                audit_bytes,
                label="retrieval input error audit",
            )
            self._bound.store.append_event(
                self._bound.run_id,
                {
                    "event_type": "operation.failed",
                    "operation": {
                        "operation_seq": op_seq,
                        "operation_kind": "literature_retrieval",
                        "attempt_seq": attempt_seq,
                    },
                    "artifact_refs": [
                        {
                            "role": "retrieval_audit",
                            "relative_path": audit_rel,
                            "media_type": "application/json",
                            "byte_length": len(audit_bytes),
                            "sha256": audit_sha,
                        }
                    ],
                    "payload": {
                        "status": "input_error",
                        "error": error_message,
                    },
                },
            )
        except Exception:
            # Failure recording must not mask the primary input error
            pass

    def _execute_audit_release_gate(
        self,
        *,
        run_id: str,
        store: RunStore,
        op_seq: int,
        attempt_seq: int,
        audit_document: dict[str, Any],
        payload_bytes: bytes,
        payload_sha256: str,
        outcome: str,
        paper_count: int,
    ) -> None:
        """Persist and verify evidence on disk; fail closed if anything fails."""
        try:
            # 1. Write payload artifact
            payload_rel, payload_len, payload_sha = store.write_operation_artifact(
                run_id,
                op_seq,
                attempt_seq,
                "payload.json",
                payload_bytes,
                label="model payload",
            )
            # 2. Write audit artifact
            audit_bytes = canonical_json_bytes(audit_document)
            audit_rel, audit_len, audit_sha = store.write_operation_artifact(
                run_id,
                op_seq,
                attempt_seq,
                "audit.json",
                audit_bytes,
                label="retrieval audit",
            )
            # 3. Append immutable evidence event
            event_data = {
                "event_type": "operation.finished",
                "operation": {
                    "operation_seq": op_seq,
                    "operation_kind": "literature_retrieval",
                    "attempt_seq": attempt_seq,
                },
                "artifact_refs": [
                    {
                        "role": "model_payload",
                        "relative_path": payload_rel,
                        "media_type": "application/json",
                        "byte_length": payload_len,
                        "sha256": payload_sha,
                    },
                    {
                        "role": "retrieval_audit",
                        "relative_path": audit_rel,
                        "media_type": "application/json",
                        "byte_length": audit_len,
                        "sha256": audit_sha,
                    },
                ],
                "payload": {
                    "status": outcome,
                    "payload_sha256": payload_sha256,
                    "returned_paper_count": paper_count,
                },
            }
            store.append_event(run_id, event_data)

            # 4. Verify on-disk release gate (read back and verify hashes and event chain)
            store.read_artifact(run_id, payload_rel, payload_sha)
            store.read_artifact(run_id, audit_rel, audit_sha)
            store.verify_chain(run_id)
        except Exception as exc:
            fail(
                "AUDIT_RELEASE_GATE_FAILED",
                f"Retrieval audit persistence or verification failed: {exc}",
            )
