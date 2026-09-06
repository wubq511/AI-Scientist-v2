from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.metrics import aggregate_metrics, query_metrics
from prototypes.local_ranking.normalization import normalize_query
from prototypes.local_ranking.ranking import (
    fuse_query_rankings,
    rank_scored_query,
)
from prototypes.local_ranking.schema import (
    parse_protocol,
    parse_qrels,
    parse_ranking_input,
)
from prototypes.local_ranking.scoring import (
    LexicalCaseScorer,
    build_collection,
    score_lexical_collection,
)

FIXTURES = Path("prototypes/local_ranking/fixtures")


def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_lexical_scorer_golden_values() -> None:
    stats = build_collection(
        {"d1": "alpha beta", "d2": "alpha alpha gamma"}, label="golden"
    )

    assert score_lexical_collection("idf_coverage", ("alpha",), stats, {}) == {
        "d1": 1.0,
        "d2": 1.0,
    }
    tfidf = score_lexical_collection("tfidf_cosine", ("alpha",), stats, {})
    bm25 = score_lexical_collection("bm25", ("alpha",), stats, {"k1": 1.2, "b": 0.75})
    dph = score_lexical_collection("dph", ("alpha",), stats, {})

    assert tfidf == pytest.approx({"d1": 0.5797386715376657, "d2": 0.8181802073667197})
    assert bm25 == pytest.approx({"d1": 0.19856803215183175, "d2": 0.2373416715660948})
    assert dph == pytest.approx({"d1": 0.07033920736279567, "d2": 0.04952862967650673})


def _rank(candidate_id: str, query_id: str):
    ranking_input = parse_ranking_input(_json("input.json"))
    protocol = parse_protocol(_json("protocol.json"))
    case = ranking_input.cases[0]
    query = next(item for item in case.queries if item.query_id == query_id)
    candidate = next(
        item for item in protocol.candidates if item.candidate_id == candidate_id
    )
    scorer = LexicalCaseScorer(case, candidate)
    query_tokens, segment_scores, title_scores = scorer.score(query.text)
    segment_tokens, title_tokens = scorer.unit_tokens()
    normalized = normalize_query(query.text)
    return (
        case,
        candidate,
        rank_scored_query(
            case=case,
            query_id=query.query_id,
            normalized_query=normalized.normalized,
            query_tokens=query_tokens,
            candidate=candidate,
            segment_scores=segment_scores,
            title_scores=title_scores,
            segment_tokens=segment_tokens,
            title_tokens=title_tokens,
        ),
    )


def test_paper_and_segment_order_are_deterministic() -> None:
    _, _, first = _rank("bm25-v1", "fixture-focused")
    _, _, second = _rank("bm25-v1", "fixture-focused")

    assert first.papers[0].paper_id == "p-bm25"
    assert first.payload_sha256 == second.payload_sha256
    assert first.payload == second.payload
    assert set(first.payload) == {"papers"}
    assert set(first.payload["papers"][0]) == {"paper_id", "title", "segments"}
    assert set(first.payload["papers"][0]["segments"][0]) == {"content_type", "text"}


def test_rrf_fuses_ranks_without_raw_score_mixing() -> None:
    case, _, bm25 = _rank("bm25-v1", "fixture-broad")
    _, _, tfidf = _rank("tfidf-v1", "fixture-broad")
    protocol = parse_protocol(_json("protocol.json"))
    rrf = next(item for item in protocol.candidates if item.candidate_id == "rrf-v1")

    fused = fuse_query_rankings(case=case, candidate=rrf, sources=(bm25, tfidf))

    assert {paper.paper_id for paper in fused.papers} == {
        "p-bm25",
        "p-citation",
        "p-dense",
    }
    assert (
        fused.payload_sha256
        == fuse_query_rankings(
            case=case, candidate=rrf, sources=(bm25, tfidf)
        ).payload_sha256
    )


def test_metric_direction_and_evidence_hit() -> None:
    ranking_input = parse_ranking_input(_json("input.json"))
    qrels = parse_qrels(_json("qrels.json"), ranking_input)
    _, _, ranking = _rank("bm25-v1", "fixture-focused")

    metrics = query_metrics(ranking, qrels)
    aggregate = aggregate_metrics([metrics])

    assert metrics["nDCG@5"] == pytest.approx(0.9828422279067397)
    assert metrics["Recall@3"] == pytest.approx(1.0)
    assert metrics["MRR"] == pytest.approx(1.0)
    assert metrics["EvidenceHit@budget"] is True
    assert aggregate["EvidenceHit@budget_rate"] == pytest.approx(1.0)
