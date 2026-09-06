from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes
from .errors import fail
from .schema import CandidateSpec, Case


@dataclass(frozen=True, slots=True)
class RankedSegment:
    segment_id: str
    score: float


@dataclass(frozen=True, slots=True)
class RankedPaper:
    paper_id: str
    score: float
    segments: tuple[RankedSegment, ...]


@dataclass(frozen=True, slots=True)
class QueryRanking:
    case_id: str
    query_id: str
    normalized_query: str
    papers: tuple[RankedPaper, ...]
    payload: dict[str, Any]
    payload_sha256: str


def _phrase_coverage(
    query_tokens: tuple[str, ...], document_tokens: tuple[str, ...]
) -> float:
    query_bigrams = set(pairwise(query_tokens))
    if not query_bigrams:
        return 0.0
    document_bigrams = set(pairwise(document_tokens))
    return len(query_bigrams & document_bigrams) / len(query_bigrams)


def _apply_phrase_bonus(
    query_tokens: tuple[str, ...],
    segment_scores: dict[str, float],
    title_scores: dict[str, float],
    segment_tokens: dict[str, tuple[str, ...]],
    title_tokens: dict[str, tuple[str, ...]],
) -> tuple[dict[str, float], dict[str, float]]:
    combined = {
        **segment_scores,
        **{f"title:{key}": value for key, value in title_scores.items()},
    }
    minimum = min(combined.values())
    maximum = max(combined.values())

    def normalize(score: float) -> float:
        if maximum == minimum:
            return 0.0
        return (score - minimum) / (maximum - minimum)

    adjusted_segments = {
        identifier: 0.9 * normalize(score)
        + 0.1 * _phrase_coverage(query_tokens, segment_tokens[identifier])
        for identifier, score in segment_scores.items()
    }
    adjusted_titles = {
        identifier: 0.9 * normalize(score)
        + 0.1 * _phrase_coverage(query_tokens, title_tokens[identifier])
        for identifier, score in title_scores.items()
    }
    return adjusted_segments, adjusted_titles


def _aggregate(values: list[float], aggregation: str) -> float:
    if not values:
        fail("INVALID_CORPUS", "Paper has no eligible segment scores")
    ordered = sorted(values, reverse=True)
    if aggregation == "max":
        return ordered[0]
    if aggregation == "mean_top_2":
        selected = ordered[:2]
        return sum(selected) / len(selected)
    if aggregation == "sum_all":
        return sum(ordered)
    fail("INVALID_AGGREGATION", "Unknown paper aggregation", aggregation=aggregation)


def _make_payload(
    case: Case, papers: tuple[RankedPaper, ...], candidate: CandidateSpec
) -> tuple[dict[str, Any], str]:
    paper_lookup = {paper.paper_id: paper for paper in case.papers}
    remaining_segments = candidate.output_budget.total_segment_cap
    payload_papers: list[dict[str, Any]] = []
    for ranked_paper in papers[: candidate.output_budget.paper_cap]:
        if remaining_segments == 0:
            break
        source_paper = paper_lookup[ranked_paper.paper_id]
        segment_lookup = {
            segment.segment_id: segment for segment in source_paper.segments
        }
        take = min(candidate.output_budget.segments_per_paper, remaining_segments)
        selected = ranked_paper.segments[:take]
        if not selected:
            fail("INVALID_RANKING", "Ranked paper has no model-visible segment")
        payload_papers.append(
            {
                "paper_id": source_paper.paper_id,
                "title": source_paper.title,
                "segments": [
                    {
                        "content_type": segment_lookup[item.segment_id].content_type,
                        "text": segment_lookup[item.segment_id].text,
                    }
                    for item in selected
                ],
            }
        )
        remaining_segments -= len(selected)
    payload = {"papers": payload_papers}
    return payload, sha256_bytes(canonical_json_bytes(payload))


def rank_scored_query(
    *,
    case: Case,
    query_id: str,
    normalized_query: str,
    query_tokens: tuple[str, ...],
    candidate: CandidateSpec,
    segment_scores: dict[str, float],
    title_scores: dict[str, float],
    segment_tokens: dict[str, tuple[str, ...]],
    title_tokens: dict[str, tuple[str, ...]],
) -> QueryRanking:
    if candidate.phrase_bonus:
        segment_scores, title_scores = _apply_phrase_bonus(
            query_tokens,
            segment_scores,
            title_scores,
            segment_tokens,
            title_tokens,
        )
    ranked_papers: list[RankedPaper] = []
    for paper in case.papers:
        ranked_segments = tuple(
            sorted(
                (
                    RankedSegment(
                        segment.segment_id, segment_scores[segment.segment_id]
                    )
                    for segment in paper.segments
                ),
                key=lambda item: (
                    -item.score,
                    next(
                        segment.content_item_order
                        for segment in paper.segments
                        if segment.segment_id == item.segment_id
                    ),
                    next(
                        segment.source_start
                        for segment in paper.segments
                        if segment.segment_id == item.segment_id
                    ),
                    item.segment_id,
                ),
            )
        )
        content_score = _aggregate(
            [segment.score for segment in ranked_segments], candidate.aggregation
        )
        paper_score = (
            content_score + candidate.title_weight * title_scores[paper.paper_id]
        )
        if not math.isfinite(paper_score):
            fail("INVALID_SCORE", "Paper aggregation produced a non-finite value")
        ranked_papers.append(
            RankedPaper(
                paper_id=paper.paper_id, score=paper_score, segments=ranked_segments
            )
        )
    papers = tuple(sorted(ranked_papers, key=lambda item: (-item.score, item.paper_id)))
    payload, payload_sha256 = _make_payload(case, papers, candidate)
    return QueryRanking(
        case_id=case.case_id,
        query_id=query_id,
        normalized_query=normalized_query,
        papers=papers,
        payload=payload,
        payload_sha256=payload_sha256,
    )


def fuse_query_rankings(
    *,
    case: Case,
    candidate: CandidateSpec,
    sources: tuple[QueryRanking, QueryRanking],
) -> QueryRanking:
    if (
        sources[0].query_id != sources[1].query_id
        or sources[0].case_id != sources[1].case_id
    ):
        fail(
            "INPUT_IDENTITY_MISMATCH",
            "RRF source rankings do not describe the same query",
        )
    k = candidate.rrf_k
    if k is None:
        fail("INVALID_SCHEMA", "RRF candidate is missing k")
    paper_scores: dict[str, float] = {paper.paper_id: 0.0 for paper in case.papers}
    segment_scores: dict[str, float] = {
        segment.segment_id: 0.0 for paper in case.papers for segment in paper.segments
    }
    for source in sources:
        for rank, paper in enumerate(source.papers, start=1):
            paper_scores[paper.paper_id] += 1 / (k + rank)
            for segment_rank, segment in enumerate(paper.segments, start=1):
                segment_scores[segment.segment_id] += 1 / (k + segment_rank)
    papers = tuple(
        sorted(
            (
                RankedPaper(
                    paper_id=paper.paper_id,
                    score=paper_scores[paper.paper_id],
                    segments=tuple(
                        sorted(
                            (
                                RankedSegment(
                                    segment.segment_id,
                                    segment_scores[segment.segment_id],
                                )
                                for segment in paper.segments
                            ),
                            key=lambda item: (
                                -item.score,
                                next(
                                    segment.content_item_order
                                    for segment in paper.segments
                                    if segment.segment_id == item.segment_id
                                ),
                                next(
                                    segment.source_start
                                    for segment in paper.segments
                                    if segment.segment_id == item.segment_id
                                ),
                                item.segment_id,
                            ),
                        )
                    ),
                )
                for paper in case.papers
            ),
            key=lambda item: (-item.score, item.paper_id),
        )
    )
    payload, payload_sha256 = _make_payload(case, papers, candidate)
    return QueryRanking(
        case_id=sources[0].case_id,
        query_id=sources[0].query_id,
        normalized_query=sources[0].normalized_query,
        papers=papers,
        payload=payload,
        payload_sha256=payload_sha256,
    )


def ranking_as_dict(ranking: QueryRanking) -> dict[str, Any]:
    return {
        "case_id": ranking.case_id,
        "query_id": ranking.query_id,
        "normalized_query": ranking.normalized_query,
        "papers": [
            {
                "paper_id": paper.paper_id,
                "score": paper.score,
                "segments": [
                    {"segment_id": segment.segment_id, "score": segment.score}
                    for segment in paper.segments
                ],
            }
            for paper in ranking.papers
        ],
        "payload_sha256": ranking.payload_sha256,
    }


def ranking_from_dict(value: dict[str, Any], payload: dict[str, Any]) -> QueryRanking:
    papers = tuple(
        RankedPaper(
            paper_id=paper["paper_id"],
            score=float(paper["score"]),
            segments=tuple(
                RankedSegment(segment["segment_id"], float(segment["score"]))
                for segment in paper["segments"]
            ),
        )
        for paper in value["papers"]
    )
    payload_hash = sha256_bytes(canonical_json_bytes(payload))
    if payload_hash != value["payload_sha256"]:
        fail("PAYLOAD_HASH_MISMATCH", "Worker payload does not match its recorded hash")
    return QueryRanking(
        case_id=value["case_id"],
        query_id=value["query_id"],
        normalized_query=value["normalized_query"],
        papers=papers,
        payload=payload,
        payload_sha256=payload_hash,
    )
