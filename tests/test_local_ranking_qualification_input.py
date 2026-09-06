from __future__ import annotations

import json
from pathlib import Path

from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.operational_judge import prepare as prepare_judges
from prototypes.local_ranking.qualification_input import (
    prepare as prepare_qualification,
)

BASELINE_ID = "bm25-k16-b05-tw1-cap3"
CHALLENGER_ID = "e5-small-v2-tw1-cap3"


def _write_json(path: Path, value: dict) -> bytes:
    data = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _source_split(tmp_path: Path, *, split: str) -> dict[str, Path | list[dict]]:
    prefix = "dev" if split == "development" else "hol"
    cases = []
    selection_cases = []
    payload_lines = {BASELINE_ID: [], CHALLENGER_ID: []}
    payload_hashes = {BASELINE_ID: {}, CHALLENGER_ID: {}}
    for case_number in range(1, 7):
        case_id = f"lr-{prefix}-{case_number:02d}"
        stratum = ("small", "medium", "large")[(case_number - 1) // 2]
        papers = []
        for paper_number in range(3):
            paper_id = f"{(100 if split == 'holdout' else 0) + case_number * 10 + paper_number:040x}"
            text = (
                f"{split} case {case_number} paper {paper_number} gives visible evidence "
                "about mechanisms, limits, and concrete research implications."
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
                    "title": f"{split} case {case_number} paper {paper_number}",
                }
            )
        queries = [
            {
                "kind": kind,
                "query_id": f"{case_id}-{kind}",
                "text": f"What {kind} evidence applies to {split} case {case_number}?",
            }
            for kind in ("broad", "focused")
        ]
        cases.append(
            {
                "case_id": case_id,
                "corpus_sha256": f"{case_number + (100 if split == 'holdout' else 0):064x}",
                "papers": papers,
                "queries": queries,
            }
        )
        selection_cases.append({"case_id": case_id, "split": split, "stratum": stratum})
        for query in queries:
            for candidate_id, ordered_papers in (
                (BASELINE_ID, papers),
                (CHALLENGER_ID, [papers[1], papers[2], papers[0]]),
            ):
                payload = {
                    "papers": [
                        {
                            "paper_id": paper["paper_id"],
                            "segments": [
                                {
                                    "content_type": paper["segments"][0][
                                        "content_type"
                                    ],
                                    "text": paper["segments"][0]["text"],
                                }
                            ],
                            "title": paper["title"],
                        }
                        for paper in ordered_papers
                    ]
                }
                payload_sha256 = sha256_bytes(canonical_json_bytes(payload))
                payload_hashes[candidate_id][query["query_id"]] = payload_sha256
                payload_lines[candidate_id].append(
                    canonical_json_bytes(
                        {
                            "case_id": case_id,
                            "payload": payload,
                            "payload_sha256": payload_sha256,
                            "query_id": query["query_id"],
                        }
                    )
                )

    root = tmp_path / split
    input_path = root / "input.json"
    summary_path = root / "summary.json"
    baseline_path = root / "baseline.jsonl"
    challenger_path = root / "challenger.jsonl"
    _write_json(
        input_path,
        {
            "cases": cases,
            "schema_version": "local-ranking-input-v1",
            "split": split,
        },
    )
    _write_json(
        summary_path,
        {
            "candidate_results": [
                {
                    "candidate_id": candidate_id,
                    "payload_hashes": payload_hashes[candidate_id],
                    "resources": {"gate_failures": [], "gate_status": "pass"},
                    "status": "success",
                }
                for candidate_id in (BASELINE_ID, CHALLENGER_ID)
            ],
            "status": "success",
        },
    )
    baseline_path.write_bytes(b"".join(payload_lines[BASELINE_ID]))
    challenger_path.write_bytes(b"".join(payload_lines[CHALLENGER_ID]))
    return {
        "baseline": baseline_path,
        "challenger": challenger_path,
        "input": input_path,
        "selection_cases": selection_cases,
        "summary": summary_path,
    }


def test_combines_two_spent_splits_into_exact_24_item_judge_input(tmp_path) -> None:
    development = _source_split(tmp_path, split="development")
    holdout = _source_split(tmp_path, split="holdout")
    selection_path = tmp_path / "selection.json"
    _write_json(
        selection_path,
        {
            "cases": [
                *development["selection_cases"],
                *holdout["selection_cases"],
            ],
            "selection_version": "source-selection-v1",
        },
    )
    qualification_root = tmp_path / "qualification-input"
    manifest = prepare_qualification(
        development_input_path=development["input"],
        holdout_input_path=holdout["input"],
        selection_path=selection_path,
        development_summary_path=development["summary"],
        holdout_summary_path=holdout["summary"],
        development_baseline_payload_path=development["baseline"],
        holdout_baseline_payload_path=holdout["baseline"],
        development_challenger_payload_path=development["challenger"],
        holdout_challenger_payload_path=holdout["challenger"],
        output_root=qualification_root,
    )

    combined_input = json.loads((qualification_root / "input.json").read_text())
    assert combined_input["split"] == "spent_qualification"
    assert len(combined_input["cases"]) == 12
    assert sum(len(case["queries"]) for case in combined_input["cases"]) == 24
    assert manifest["evidence_mode"] == "spent_diagnostic_only"
    assert set(manifest["files"]) == {
        "baseline-payloads.jsonl",
        "challenger-payloads.jsonl",
        "comparison-summary.json",
        "input.json",
        "selection.json",
    }

    protocol_path = tmp_path / "protocol.md"
    evaluator_protocol_path = tmp_path / "evaluator-protocol.md"
    protocol_path.write_text("approved base protocol\n", encoding="utf-8")
    evaluator_protocol_path.write_text(
        "approved evaluator protocol\n", encoding="utf-8"
    )
    judge_root = tmp_path / "judge-input"
    judge_manifest = prepare_judges(
        input_path=qualification_root / "input.json",
        formal_manifest_path=qualification_root / "manifest.json",
        selection_path=qualification_root / "selection.json",
        protocol_path=protocol_path,
        evaluator_protocol_path=evaluator_protocol_path,
        comparison_summary_path=qualification_root / "comparison-summary.json",
        baseline_candidate_id=BASELINE_ID,
        baseline_payload_path=qualification_root / "baseline-payloads.jsonl",
        challenger_candidate_id=CHALLENGER_ID,
        challenger_payload_path=qualification_root / "challenger-payloads.jsonl",
        output_root=judge_root,
    )

    assert judge_manifest["evidence_mode"] == "spent_diagnostic_only"
    for bundle_record in judge_manifest["bundles"]:
        bundle = json.loads((judge_root / bundle_record["bundle_path"]).read_text())
        assert len(bundle["items"]) == 24
