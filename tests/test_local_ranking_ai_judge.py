from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from prototypes.local_ranking.ai_judge import (
    ADJUDICATION_QRELS_SCHEMA_VERSION,
    JUDGE_BUNDLE_SCHEMA_VERSION,
    JUDGE_DRAFT_SCHEMA_VERSION,
    _judge_profile,
    finalize_consensus,
    finalize_draft,
    normalize_judge_draft,
    prepare_adjudication_bundle,
    prepare_agreement_diagnostics,
    rebind_judge_result,
)
from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError

ROOT = Path(__file__).parents[1]


def _fixture_input() -> dict[str, object]:
    return json.loads(
        (ROOT / "prototypes/local_ranking/fixtures/input.json").read_text()
    )


def _bundle(judge_id: str, model: str) -> dict[str, object]:
    ranking_input = _fixture_input()
    items = []
    for case in ranking_input["cases"]:
        for query in case["queries"]:
            for paper in case["papers"]:
                items.append(
                    {
                        "case_id": case["case_id"],
                        "item_id": f"{query['query_id']}-{paper['paper_id']}",
                        "paper_id": paper["paper_id"],
                        "paper_title": paper["title"],
                        "query_id": query["query_id"],
                        "query_kind": query["kind"],
                        "query_text": query["text"],
                        "segments": paper["segments"],
                    }
                )
    return {
        "base_protocol_sha256": "a" * 64,
        "forbidden_context": ["ranker outputs"],
        "formal_input_manifest_sha256": "b" * 64,
        "input_sha256": sha256_bytes(canonical_json_bytes(ranking_input)),
        "instructions": {"required_judgment_count": len(items)},
        "items": items,
        "judge": _judge_profile(judge_id, model, "xhigh", "test-provider"),
        "revision_protocol_sha256": "c" * 64,
        "rubric": {"version": "test"},
        "schema_version": JUDGE_BUNDLE_SCHEMA_VERSION,
        "split": ranking_input["split"],
    }


def _draft(bundle: dict[str, object]) -> dict[str, object]:
    judgments = []
    for item in bundle["items"]:
        direct = item["paper_id"] == "p-bm25" and item["query_id"] == "fixture-focused"
        segment = item["segments"][0]
        judgments.append(
            {
                "item_id": item["item_id"],
                "paper_grade": 2 if direct else 0,
                "rationale": "Visible evidence supports the assigned topical grade.",
                "segment_judgments": (
                    [
                        {
                            "grade": 2,
                            "segment_id": segment["segment_id"],
                            "supporting_quotes": ["BM25 ranks exact scientific terms"],
                        }
                    ]
                    if direct
                    else []
                ),
            }
        )
    return {
        "bundle_sha256": sha256_bytes(canonical_json_bytes(bundle)),
        "judge": bundle["judge"],
        "judgments": judgments,
        "schema_version": JUDGE_DRAFT_SCHEMA_VERSION,
        "split": bundle["split"],
    }


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def test_normalize_judge_draft_requires_exact_direct_support() -> None:
    bundle = _bundle("judge-a", "model-a")
    draft = _draft(bundle)

    trace, qrels = normalize_judge_draft(bundle, draft)

    assert len(trace["judgments"]) == 6
    assert len(qrels["paper_judgments"]) == 6
    assert qrels["segment_judgments"] == [
        {"grade": 2, "query_id": "fixture-focused", "segment_id": "seg-bm25"}
    ]
    direct = next(item for item in trace["judgments"] if item["paper_grade"] == 2)
    span = direct["segment_judgments"][0]["supporting_spans"][0]
    assert span == {
        "end": len("BM25 ranks exact scientific terms"),
        "quote": "BM25 ranks exact scientific terms",
        "start": 0,
    }


def test_normalize_judge_draft_rejects_unsupported_quote() -> None:
    bundle = _bundle("judge-a", "model-a")
    draft = _draft(bundle)
    direct = next(item for item in draft["judgments"] if item["paper_grade"] == 2)
    direct["segment_judgments"][0]["supporting_quotes"] = ["not in the segment"]

    with pytest.raises(HarnessError, match="absent from segment"):
        normalize_judge_draft(bundle, draft)


def test_disagreements_are_blindly_adjudicated_and_consensus_is_complete(
    tmp_path: Path,
) -> None:
    bundle_a = _bundle("judge-a", "model-a")
    bundle_b = _bundle("judge-b", "model-b")
    draft_a = _draft(bundle_a)
    draft_b = _draft(bundle_b)
    disputed = next(
        item
        for item in draft_b["judgments"]
        if item["item_id"] == "fixture-broad-p-citation"
    )
    disputed["paper_grade"] = 1
    trace_a, _ = normalize_judge_draft(bundle_a, draft_a)
    trace_b, _ = normalize_judge_draft(bundle_b, draft_b)
    paths = {
        "bundle_a": tmp_path / "bundle-a.json",
        "bundle_b": tmp_path / "bundle-b.json",
        "trace_a": tmp_path / "trace-a.json",
        "trace_b": tmp_path / "trace-b.json",
    }
    _write(paths["bundle_a"], bundle_a)
    _write(paths["bundle_b"], bundle_b)
    _write(paths["trace_a"], trace_a)
    _write(paths["trace_b"], trace_b)
    adjudication_path = tmp_path / "adjudication-bundle.json"

    adjudication_bundle = prepare_adjudication_bundle(
        bundle_a_path=paths["bundle_a"],
        trace_a_path=paths["trace_a"],
        bundle_b_path=paths["bundle_b"],
        trace_b_path=paths["trace_b"],
        adjudicator_profile=_judge_profile(
            "judge-c", "model-c", "xhigh", "test-provider"
        ),
        output_path=adjudication_path,
    )

    assert [item["item_id"] for item in adjudication_bundle["items"]] == [
        "fixture-broad-p-citation"
    ]
    serialized = canonical_json_bytes(adjudication_bundle)
    assert b"paper_grade" not in serialized
    assert b"Visible evidence supports" not in serialized
    draft_c = _draft(adjudication_bundle)
    trace_c, _ = normalize_judge_draft(adjudication_bundle, draft_c)
    trace_c_path = tmp_path / "trace-c.json"
    _write(trace_c_path, trace_c)
    input_path = tmp_path / "input.json"
    _write(input_path, _fixture_input())

    result = finalize_consensus(
        bundle_a_path=paths["bundle_a"],
        trace_a_path=paths["trace_a"],
        bundle_b_path=paths["bundle_b"],
        trace_b_path=paths["trace_b"],
        adjudication_bundle_path=adjudication_path,
        adjudication_trace_path=trace_c_path,
        input_path=input_path,
        output_root=tmp_path / "consensus",
    )

    assert result["disagreement_count"] == 1
    assert result["disagreement_rate"] == pytest.approx(1 / 6)
    consensus = json.loads((tmp_path / "consensus/qrels.json").read_text())
    assert len(consensus["paper_judgments"]) == 6


def test_finalize_adjudication_accepts_only_the_frozen_dispute_subset(
    tmp_path: Path,
) -> None:
    bundle_a = _bundle("judge-a", "model-a")
    bundle_b = _bundle("judge-b", "model-b")
    trace_a, _ = normalize_judge_draft(bundle_a, _draft(bundle_a))
    draft_b = _draft(bundle_b)
    disputed = next(
        item
        for item in draft_b["judgments"]
        if item["item_id"] == "fixture-broad-p-citation"
    )
    disputed["paper_grade"] = 1
    trace_b, _ = normalize_judge_draft(bundle_b, draft_b)
    for name, value in (
        ("bundle-a", bundle_a),
        ("bundle-b", bundle_b),
        ("trace-a", trace_a),
        ("trace-b", trace_b),
        ("input", _fixture_input()),
    ):
        _write(tmp_path / f"{name}.json", value)
    adjudication_path = tmp_path / "adjudication-bundle.json"
    adjudication = prepare_adjudication_bundle(
        bundle_a_path=tmp_path / "bundle-a.json",
        trace_a_path=tmp_path / "trace-a.json",
        bundle_b_path=tmp_path / "bundle-b.json",
        trace_b_path=tmp_path / "trace-b.json",
        adjudicator_profile=_judge_profile(
            "judge-c", "model-c", "xhigh", "test-provider"
        ),
        output_path=adjudication_path,
    )
    draft_path = tmp_path / "adjudication-draft.json"
    _write(draft_path, _draft(adjudication))

    result = finalize_draft(
        bundle_path=adjudication_path,
        draft_path=draft_path,
        input_path=tmp_path / "input.json",
        output_root=tmp_path / "adjudication-result",
    )

    qrels = json.loads((tmp_path / "adjudication-result/qrels.json").read_text())
    assert qrels["schema_version"] == ADJUDICATION_QRELS_SCHEMA_VERSION
    assert len(qrels["paper_judgments"]) == 1
    assert result["qrels_sha256"] == sha256_bytes(canonical_json_bytes(qrels))


def test_finalize_adjudication_rejects_item_payload_drift(tmp_path: Path) -> None:
    bundle_a = _bundle("judge-a", "model-a")
    bundle_b = _bundle("judge-b", "model-b")
    trace_a, _ = normalize_judge_draft(bundle_a, _draft(bundle_a))
    draft_b = _draft(bundle_b)
    draft_b["judgments"][0]["paper_grade"] = 1
    trace_b, _ = normalize_judge_draft(bundle_b, draft_b)
    for name, value in (
        ("bundle-a", bundle_a),
        ("bundle-b", bundle_b),
        ("trace-a", trace_a),
        ("trace-b", trace_b),
        ("input", _fixture_input()),
    ):
        _write(tmp_path / f"{name}.json", value)
    adjudication_path = tmp_path / "adjudication-bundle.json"
    adjudication = prepare_adjudication_bundle(
        bundle_a_path=tmp_path / "bundle-a.json",
        trace_a_path=tmp_path / "trace-a.json",
        bundle_b_path=tmp_path / "bundle-b.json",
        trace_b_path=tmp_path / "trace-b.json",
        adjudicator_profile=_judge_profile(
            "judge-c", "model-c", "xhigh", "test-provider"
        ),
        output_path=adjudication_path,
    )
    adjudication["items"][0]["query_text"] = "tampered"
    _write(tmp_path / "tampered-bundle.json", adjudication)
    _write(tmp_path / "tampered-draft.json", _draft(adjudication))

    with pytest.raises(HarnessError, match="payload changed from the frozen input"):
        finalize_draft(
            bundle_path=tmp_path / "tampered-bundle.json",
            draft_path=tmp_path / "tampered-draft.json",
            input_path=tmp_path / "input.json",
            output_root=tmp_path / "adjudication-result",
        )


def test_consensus_rejects_adjudicator_coverage_drift(tmp_path: Path) -> None:
    bundle_a = _bundle("judge-a", "model-a")
    bundle_b = _bundle("judge-b", "model-b")
    trace_a, _ = normalize_judge_draft(bundle_a, _draft(bundle_a))
    draft_b = _draft(bundle_b)
    draft_b["judgments"][0]["paper_grade"] = 1
    trace_b, _ = normalize_judge_draft(bundle_b, draft_b)
    for name, value in (
        ("bundle-a", bundle_a),
        ("bundle-b", bundle_b),
        ("trace-a", trace_a),
        ("trace-b", trace_b),
    ):
        _write(tmp_path / f"{name}.json", value)
    adjudication_path = tmp_path / "adjudication.json"
    adjudication = prepare_adjudication_bundle(
        bundle_a_path=tmp_path / "bundle-a.json",
        trace_a_path=tmp_path / "trace-a.json",
        bundle_b_path=tmp_path / "bundle-b.json",
        trace_b_path=tmp_path / "trace-b.json",
        adjudicator_profile=_judge_profile(
            "judge-c", "model-c", "xhigh", "test-provider"
        ),
        output_path=adjudication_path,
    )
    wrong = deepcopy(adjudication)
    wrong["items"] = []
    wrong_draft = _draft(wrong)
    wrong_trace, _ = normalize_judge_draft(wrong, wrong_draft)
    wrong_trace["bundle_sha256"] = sha256_bytes(canonical_json_bytes(adjudication))
    _write(tmp_path / "wrong-trace.json", wrong_trace)
    _write(tmp_path / "input.json", _fixture_input())

    with pytest.raises(HarnessError, match="cover every frozen item"):
        finalize_consensus(
            bundle_a_path=tmp_path / "bundle-a.json",
            trace_a_path=tmp_path / "trace-a.json",
            bundle_b_path=tmp_path / "bundle-b.json",
            trace_b_path=tmp_path / "trace-b.json",
            adjudication_bundle_path=adjudication_path,
            adjudication_trace_path=tmp_path / "wrong-trace.json",
            input_path=tmp_path / "input.json",
            output_root=tmp_path / "consensus",
        )


def test_adjudication_rejects_trace_identity_drift(tmp_path: Path) -> None:
    bundle_a = _bundle("judge-a", "model-a")
    bundle_b = _bundle("judge-b", "model-b")
    trace_a, _ = normalize_judge_draft(bundle_a, _draft(bundle_a))
    trace_b, _ = normalize_judge_draft(bundle_b, _draft(bundle_b))
    trace_a = deepcopy(trace_a)
    trace_a["judge"]["model"] = "tampered-model"
    for name, value in (
        ("bundle-a", bundle_a),
        ("bundle-b", bundle_b),
        ("trace-a", trace_a),
        ("trace-b", trace_b),
    ):
        _write(tmp_path / f"{name}.json", value)

    with pytest.raises(HarnessError, match="trace identity changed"):
        prepare_adjudication_bundle(
            bundle_a_path=tmp_path / "bundle-a.json",
            trace_a_path=tmp_path / "trace-a.json",
            bundle_b_path=tmp_path / "bundle-b.json",
            trace_b_path=tmp_path / "trace-b.json",
            adjudicator_profile=_judge_profile(
                "judge-c", "model-c", "xhigh", "test-provider"
            ),
            output_path=tmp_path / "adjudication.json",
        )


def test_agreement_diagnostics_reports_ordinal_and_boundary_failures(
    tmp_path: Path,
) -> None:
    bundle_a = _bundle("judge-a", "model-a")
    bundle_b = _bundle("judge-b", "model-b")
    trace_a, _ = normalize_judge_draft(bundle_a, _draft(bundle_a))
    draft_b = _draft(bundle_b)
    draft_b["judgments"][0]["paper_grade"] = 2
    draft_b["judgments"][0]["segment_judgments"] = [
        {
            "grade": 2,
            "segment_id": bundle_b["items"][0]["segments"][0]["segment_id"],
            "supporting_quotes": ["BM25 ranks exact scientific terms"],
        }
    ]
    draft_b["judgments"][1]["paper_grade"] = 1
    trace_b, _ = normalize_judge_draft(bundle_b, draft_b)
    for name, value in (
        ("bundle-a", bundle_a),
        ("bundle-b", bundle_b),
        ("trace-a", trace_a),
        ("trace-b", trace_b),
    ):
        _write(tmp_path / f"{name}.json", value)

    report = prepare_agreement_diagnostics(
        bundle_a_path=tmp_path / "bundle-a.json",
        trace_a_path=tmp_path / "trace-a.json",
        bundle_b_path=tmp_path / "bundle-b.json",
        trace_b_path=tmp_path / "trace-b.json",
        output_path=tmp_path / "diagnostics.json",
    )

    assert report["item_count"] == 6
    assert report["exact_paper_grade_agreement"]["count"] == 4
    assert report["grade_gap_at_least_2"]["count"] == 1
    assert report["boundary_1_2"]["count"] == 0
    assert -1.0 <= report["linear_weighted_cohen_kappa"] <= 1.0


@pytest.mark.parametrize("use_raw_draft", [True, False])
def test_rebind_changes_only_provenance_and_preserves_qrels(
    tmp_path: Path, use_raw_draft: bool
) -> None:
    source_bundle = _bundle("judge-a", "declared-model")
    target_bundle = deepcopy(source_bundle)
    target_bundle["judge"] = _judge_profile(
        "judge-a",
        "actual-model",
        "provider-managed-not-exposed",
        "actual-provider",
    )
    target_bundle["revision_protocol_sha256"] = "d" * 64
    source_draft = _draft(source_bundle)
    source_trace, source_qrels = normalize_judge_draft(source_bundle, source_draft)
    source_bundle_bytes = canonical_json_bytes(source_bundle)
    source_draft_bytes = canonical_json_bytes(source_draft)
    source_trace_bytes = canonical_json_bytes(source_trace)
    source_qrels_bytes = canonical_json_bytes(source_qrels)
    source_result = {
        "bundle_sha256": sha256_bytes(source_bundle_bytes),
        "draft_sha256": sha256_bytes(source_draft_bytes),
        "judge": source_bundle["judge"],
        "qrels_sha256": sha256_bytes(source_qrels_bytes),
        "schema_version": "local-ranking-ai-judge-result-v1.0",
        "split": source_bundle["split"],
        "trace_sha256": sha256_bytes(source_trace_bytes),
    }
    for name, value in (
        ("source-bundle", source_bundle),
        ("target-bundle", target_bundle),
        ("source-draft", source_draft),
        ("source-qrels", source_qrels),
        ("source-trace", source_trace),
        ("source-result", source_result),
        ("input", _fixture_input()),
    ):
        _write(tmp_path / f"{name}.json", value)

    sidecar = rebind_judge_result(
        source_bundle_path=tmp_path / "source-bundle.json",
        target_bundle_path=tmp_path / "target-bundle.json",
        source_draft_path=(tmp_path / "source-draft.json" if use_raw_draft else None),
        source_qrels_path=tmp_path / "source-qrels.json",
        source_trace_path=tmp_path / "source-trace.json",
        source_result_path=tmp_path / "source-result.json",
        input_path=tmp_path / "input.json",
        output_root=tmp_path / "rebound",
        execution_session_id="private-session-id",
        attested_by="Robert",
    )

    assert (tmp_path / "rebound/qrels.json").read_bytes() == source_qrels_bytes
    rebound_result = json.loads((tmp_path / "rebound/result.json").read_text())
    assert rebound_result["judge"] == target_bundle["judge"]
    assert sidecar["original_raw_draft_available"] is use_raw_draft
    assert sidecar["source"]["representation"] == (
        "raw_draft" if use_raw_draft else "validated_trace_reconstruction"
    )
    assert "private-session-id" not in (tmp_path / "rebound/rebind.json").read_text()
