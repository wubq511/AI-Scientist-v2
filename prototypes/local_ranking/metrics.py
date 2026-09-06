from __future__ import annotations

import math
from statistics import fmean
from typing import Any

from .canonical import canonical_json_bytes
from .ranking import QueryRanking
from .schema import Qrels


def _dcg(grades: list[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1)
    )


def query_metrics(ranking: QueryRanking, qrels: Qrels) -> dict[str, Any]:
    ordered_papers = [paper.paper_id for paper in ranking.papers]
    grades = [
        qrels.paper_grades[(ranking.query_id, paper_id)] for paper_id in ordered_papers
    ]
    ideal = sorted(grades, reverse=True)[:5]
    ideal_dcg = _dcg(ideal)
    ndcg_at_5 = _dcg(grades[:5]) / ideal_dcg if ideal_dcg else 0.0
    relevant = {
        paper_id
        for paper_id in ordered_papers
        if qrels.paper_grades[(ranking.query_id, paper_id)] >= 2
    }

    def recall_at(k: int) -> float:
        if not relevant:
            return 0.0
        return len(relevant & set(ordered_papers[:k])) / len(relevant)

    reciprocal_rank = 0.0
    for rank, paper_id in enumerate(ordered_papers, 1):
        if paper_id in relevant:
            reciprocal_rank = 1 / rank
            break
    returned_segment_ids: set[str] = set()
    payload_paper_ids: set[str] = set()
    for payload_paper in ranking.payload["papers"]:
        payload_paper_ids.add(payload_paper["paper_id"])
        ranked_paper = next(
            paper
            for paper in ranking.papers
            if paper.paper_id == payload_paper["paper_id"]
        )
        returned_segment_ids.update(
            segment.segment_id
            for segment in ranked_paper.segments[: len(payload_paper["segments"])]
        )
    evidence_hit = any(
        qrels.segment_grades.get((ranking.query_id, segment_id)) == 2
        for segment_id in returned_segment_ids
    )
    grade_3 = {
        paper_id
        for paper_id in ordered_papers
        if qrels.paper_grades[(ranking.query_id, paper_id)] == 3
    }
    catastrophic_miss = len(grade_3 - set(ordered_papers[:5]))
    return {
        "query_id": ranking.query_id,
        "nDCG@5": ndcg_at_5,
        "Recall@3": recall_at(3),
        "Recall@5": recall_at(5),
        "MRR": reciprocal_rank,
        "EvidenceHit@budget": evidence_hit,
        "grade_3_catastrophic_miss": catastrophic_miss,
        "payload_paper_count": len(payload_paper_ids),
        "payload_segment_count": len(returned_segment_ids),
        "payload_utf8_bytes": len(canonical_json_bytes(ranking.payload)),
        "no_relevant_papers": not relevant,
    }


def aggregate_metrics(per_query: list[dict[str, Any]]) -> dict[str, Any]:
    if not per_query:
        return {"query_count": 0}
    numeric = ["nDCG@5", "Recall@3", "Recall@5", "MRR", "payload_utf8_bytes"]
    return {
        "query_count": len(per_query),
        **{
            f"mean_{name}": fmean(float(item[name]) for item in per_query)
            for name in numeric
        },
        "EvidenceHit@budget_rate": fmean(
            1.0 if item["EvidenceHit@budget"] else 0.0 for item in per_query
        ),
        "grade_3_catastrophic_miss_total": sum(
            int(item["grade_3_catastrophic_miss"]) for item in per_query
        ),
        "no_relevant_query_count": sum(
            1 for item in per_query if item["no_relevant_papers"]
        ),
    }
