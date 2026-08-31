from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.operational_judge import (
    DRAFT_SCHEMA_VERSION,
    finalize,
    prepare,
)
from prototypes.local_ranking.operational_stats import aggregate, exact_case_sign_flip

BASELINE_ID = "bm25-k16-b05-tw1-cap3"
CHALLENGER_ID = "e5-small-v2-tw1-cap3"


def _write_json(path: Path, value: dict) -> bytes:
    data = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _fixture(tmp_path: Path) -> dict[str, Path]:
    cases = []
    selection_cases = []
    baseline_lines = []
    challenger_lines = []
    baseline_hashes = {}
    challenger_hashes = {}
    for case_number in range(1, 13):
        case_id = f"lr-op-{case_number:02d}"
        stratum = ("small", "medium", "large")[(case_number - 1) // 4]
        papers = []
        for paper_number in range(3):
            paper_id = f"{case_number * 10 + paper_number:040x}"
            text = (
                f"Case {case_number} paper {paper_number} provides a sufficiently long exact "
                "evidence segment about mechanisms, constraints, and research implications."
            )
            papers.append(
                {
                    "paper_id": paper_id,
                    "segments": [
                        {
                            "content_item_order": 0,
                            "content_type": "publisher_abstract",
                            "segment_id": f"{paper_id}-s01",
                            "source_start": 0,
                            "text": text,
                        }
                    ],
                    "title": f"Case {case_number} paper {paper_number}",
                }
            )
        queries = [
            {
                "kind": kind,
                "query_id": f"{case_id}-{kind}",
                "text": f"What evidence addresses the {kind} question for case {case_number}?",
            }
            for kind in ("broad", "focused")
        ]
        cases.append(
            {
                "case_id": case_id,
                "corpus_sha256": f"{case_number:064x}",
                "papers": papers,
                "queries": queries,
            }
        )
        selection_cases.append({"case_id": case_id, "stratum": stratum})
        for query in queries:
            baseline_payload = {
                "papers": [
                    {
                        "paper_id": paper["paper_id"],
                        "segments": [
                            {
                                "content_type": paper["segments"][0]["content_type"],
                                "text": paper["segments"][0]["text"],
                            }
                        ],
                        "title": paper["title"],
                    }
                    for paper in papers
                ]
            }
            challenger_payload = {
                "papers": [
                    {
                        "paper_id": paper["paper_id"],
                        "segments": [
                            {
                                "content_type": paper["segments"][0]["content_type"],
                                "text": paper["segments"][0]["text"],
                            }
                        ],
                        "title": paper["title"],
                    }
                    for paper in (papers[1], papers[2], papers[0])
                ]
            }
            for payload, lines, hashes in (
                (baseline_payload, baseline_lines, baseline_hashes),
                (challenger_payload, challenger_lines, challenger_hashes),
            ):
                payload_sha256 = sha256_bytes(canonical_json_bytes(payload))
                hashes[query["query_id"]] = payload_sha256
                lines.append(
                    canonical_json_bytes(
                        {
                            "case_id": case_id,
                            "payload": payload,
                            "payload_sha256": payload_sha256,
                            "query_id": query["query_id"],
                        }
                    )
                )

    input_path = tmp_path / "input.json"
    formal_manifest_path = tmp_path / "formal-manifest.json"
    selection_path = tmp_path / "selection.json"
    protocol_path = tmp_path / "protocol.md"
    summary_path = tmp_path / "summary.json"
    baseline_path = tmp_path / "baseline.jsonl"
    challenger_path = tmp_path / "challenger.jsonl"
    input_bytes = _write_json(
        input_path,
        {
            "cases": cases,
            "schema_version": "local-ranking-input-v1",
            "split": "operational",
        },
    )
    _write_json(
        selection_path,
        {
            "cases": selection_cases,
            "selection_version": "local-ranking-operational-case-selection-v1.0",
        },
    )
    protocol_path.write_text("approved v1.4 protocol\n", encoding="utf-8")
    protocol_sha256 = sha256_bytes(protocol_path.read_bytes())
    selection_sha256 = sha256_bytes(selection_path.read_bytes())
    _write_json(
        formal_manifest_path,
        {
            "files": {"operational/input.json": sha256_bytes(input_bytes)},
            "schema_version": "prototype-formal-input-v1.0",
            "source_binding": {
                "protocol_sha256": protocol_sha256,
                "selection_manifest_sha256": selection_sha256,
            },
            "status": "formal_operational_input_ready",
        },
    )
    _write_json(
        summary_path,
        {
            "candidate_results": [
                {
                    "candidate_id": candidate_id,
                    "payload_hashes": payload_hashes,
                    "resources": {"gate_failures": [], "gate_status": "pass"},
                    "status": "success",
                }
                for candidate_id, payload_hashes in (
                    (BASELINE_ID, baseline_hashes),
                    (CHALLENGER_ID, challenger_hashes),
                )
            ],
            "status": "success",
        },
    )
    baseline_path.write_bytes(b"".join(baseline_lines))
    challenger_path.write_bytes(b"".join(challenger_lines))
    return {
        "baseline": baseline_path,
        "challenger": challenger_path,
        "formal_manifest": formal_manifest_path,
        "input": input_path,
        "protocol": protocol_path,
        "selection": selection_path,
        "summary": summary_path,
    }


def _prepare(tmp_path: Path) -> Path:
    paths = _fixture(tmp_path)
    output_root = tmp_path / "prepared"
    result = prepare(
        input_path=paths["input"],
        formal_manifest_path=paths["formal_manifest"],
        selection_path=paths["selection"],
        protocol_path=paths["protocol"],
        comparison_summary_path=paths["summary"],
        baseline_candidate_id=BASELINE_ID,
        baseline_payload_path=paths["baseline"],
        challenger_candidate_id=CHALLENGER_ID,
        challenger_payload_path=paths["challenger"],
        output_root=output_root,
    )
    assert result["status"] == "ready_for_tool_less_evaluators"
    return output_root


def _draft(bundle: dict, mapping: dict, *, challenger_wins: bool = True) -> dict:
    assignment_by_query = {item["query_id"]: item for item in mapping["assignments"]}
    judgments = []
    orientation = bundle["orientation"]
    for item in bundle["items"]:
        sides = assignment_by_query[item["item_id"]][f"orientation_{orientation}"]
        winner_role = "challenger" if challenger_wins else "baseline"
        winner_side = "left" if sides["left"] == winner_role else "right"
        loser_side = "right" if winner_side == "left" else "left"
        winner_paper = item[winner_side]["papers"][0]
        winner_segment = winner_paper["segments"][0]
        judgments.append(
            {
                "catastrophic_omission_side": "neither",
                "evidence_quotes": [
                    {
                        "paper_id": winner_paper["paper_id"],
                        "quote": winner_segment["text"][:80],
                        "segment_id": winner_segment["segment_id"],
                        "side": winner_side,
                    }
                ],
                "item_id": item["item_id"],
                "left_scores": {
                    field: 2 if winner_side == "left" else 1
                    for field in (
                        "coverage_diversity",
                        "direct_support",
                        "query_usefulness",
                        "specificity",
                    )
                },
                "rationale": "The selected side provides more directly usable visible evidence.",
                "right_scores": {
                    field: 2 if winner_side == "right" else 1
                    for field in (
                        "coverage_diversity",
                        "direct_support",
                        "query_usefulness",
                        "specificity",
                    )
                },
                "winner": winner_side,
            }
        )
        assert loser_side != winner_side
    return {
        "attestation": {
            "bundle_only": True,
            "fresh_session": True,
            "no_external_sources": True,
            "tool_access": "disabled",
        },
        "bundle_sha256": bundle["bundle_sha256"],
        "evaluator": bundle["evaluator"],
        "judgments": judgments,
        "schema_version": DRAFT_SCHEMA_VERSION,
    }


def test_prepare_builds_balanced_mirrored_tool_less_bundles(tmp_path) -> None:
    root = _prepare(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text())
    mapping = json.loads((root / "private/mapping.json").read_text())

    assert len(manifest["bundles"]) == 4
    assert (root / "tool-less-agent.md").read_text().find("tools: []") >= 0
    for evaluator_id in ("judge-kimi", "judge-deepseek"):
        first = json.loads(
            (root / f"public/{evaluator_id}/orientation-1/bundle.json").read_text()
        )
        second = json.loads(
            (root / f"public/{evaluator_id}/orientation-2/bundle.json").read_text()
        )
        second_by_id = {item["item_id"]: item for item in second["items"]}
        for item in first["items"]:
            mirrored = second_by_id[item["item_id"]]
            assert item["left"] == mirrored["right"]
            assert item["right"] == mirrored["left"]
    left_counts = {
        role: sum(
            item["orientation_1"]["left"] == role for item in mapping["assignments"]
        )
        for role in ("baseline", "challenger")
    }
    assert left_counts == {"baseline": 12, "challenger": 12}
    for stratum in ("small", "medium", "large"):
        for query_kind in ("broad", "focused"):
            block = [
                item
                for item in mapping["assignments"]
                if item["stratum"] == stratum and item["query_kind"] == query_kind
            ]
            assert {
                role: sum(item["orientation_1"]["left"] == role for item in block)
                for role in ("baseline", "challenger")
            } == {"baseline": 2, "challenger": 2}
    public_bytes = b"".join(
        (root / item["bundle_path"]).read_bytes() for item in manifest["bundles"]
    ).lower()
    assert b"bm25" not in public_bytes
    assert b"e5-small" not in public_bytes


def test_finalize_rejects_non_exact_quote(tmp_path) -> None:
    root = _prepare(tmp_path)
    mapping = json.loads((root / "private/mapping.json").read_text())
    bundle_path = root / "public/judge-kimi/orientation-1/bundle.json"
    bundle = json.loads(bundle_path.read_text())
    draft = _draft(bundle, mapping)
    draft["judgments"][0]["evidence_quotes"][0][
        "quote"
    ] = "not present in the segment text at all"
    draft_path = tmp_path / "bad-draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")

    with pytest.raises(HarnessError) as raised:
        finalize(
            bundle_path=bundle_path,
            draft_path=draft_path,
            output_root=tmp_path / "result",
        )

    assert raised.value.code == "QUOTE_NOT_EXACT"


def test_four_stable_orientations_promote_large_challenger_effect(tmp_path) -> None:
    root = _prepare(tmp_path)
    mapping = json.loads((root / "private/mapping.json").read_text())
    trace_paths = {}
    for evaluator_id in ("judge-kimi", "judge-deepseek"):
        for orientation in (1, 2):
            bundle_path = (
                root / f"public/{evaluator_id}/orientation-{orientation}/bundle.json"
            )
            bundle = json.loads(bundle_path.read_text())
            draft_path = tmp_path / f"{evaluator_id}-{orientation}-draft.json"
            draft_path.write_text(json.dumps(_draft(bundle, mapping)), encoding="utf-8")
            result_root = tmp_path / f"{evaluator_id}-{orientation}-result"
            finalize(
                bundle_path=bundle_path, draft_path=draft_path, output_root=result_root
            )
            trace_paths[(evaluator_id, orientation)] = result_root / "trace.json"

    report = aggregate(
        mapping_path=root / "private/mapping.json",
        preparation_manifest_path=root / "manifest.json",
        trace_paths=trace_paths,
        output_path=tmp_path / "aggregate.json",
    )

    assert report["resolved_count"] == 24
    assert report["effect"]["observed_delta"] == 1.0
    assert report["effect"]["one_sided_p"] == 1 / 4096
    assert report["challenger_promoted"] is True
    assert report["decision"] == "promote_challenger"


def test_exact_sign_flip_uses_case_level_observations() -> None:
    result = exact_case_sign_flip([1.0] * 12)

    assert result["enumeration_count"] == 4096
    assert result["one_sided_p"] == 1 / 4096
    assert result["two_sided_p"] == 2 / 4096
