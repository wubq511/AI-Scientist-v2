from __future__ import annotations

import json

from prototypes.local_ranking.input_preparation import (
    CaseFeature,
    SourceData,
    _build_corpus_bundle,
    _case_assignments,
    _optional_int,
    select_cases,
    validate_workshop_bytes,
)


def _features() -> tuple[CaseFeature, ...]:
    clusters = [
        "Environmental Sciences",
        "Genetics & Molecular Biology",
        "Health & Medicine",
        "Materials Science",
        "Neuroscience & Cognitive Sciences",
        "Public Health & Policy",
        "Social & Behavioral Sciences",
        "Technology & Engineering",
    ]
    values: list[CaseFeature] = []
    counts = {"small": (3, 8), "medium": (9, 18), "large": (19, 36)}
    for split_index, split in enumerate(("development", "holdout")):
        for stratum_index, (stratum, pair) in enumerate(counts.items()):
            for item_index, reference_count in enumerate(pair):
                index = split_index * 6 + stratum_index * 2 + item_index
                values.append(
                    CaseFeature(
                        target_id=f"target-{index:02d}",
                        cluster=clusters[index % len(clusters)],
                        strategy=2 if index == 0 else 1,
                        reference_count=reference_count,
                        stratum=stratum,
                        overlap_ppm=10_000 if item_index == 0 else 200_000,
                        split_bucket=split,
                        selection_key=f"{index:064x}",
                        target_row_number=index + 2,
                        target_row_sha256=f"{index + 100:064x}",
                    )
                )
    return tuple(values)


def test_case_selection_is_deterministic_and_stratified() -> None:
    first = select_cases(_features())
    second = select_cases(tuple(reversed(_features())))

    assert first == second
    assignments = _case_assignments(first)
    assert len(assignments) == 12
    assert len({case.target_id for _, _, case in assignments}) == 12
    assert len({case.cluster for _, _, case in assignments}) == 8
    for split in ("development", "holdout"):
        chosen = [case for _, item_split, case in assignments if item_split == split]
        assert len(chosen) == 6
        assert {
            stratum: sum(case.stratum == stratum for case in chosen)
            for stratum in ("small", "medium", "large")
        } == {
            "small": 2,
            "medium": 2,
            "large": 2,
        }


def test_integer_valued_raw_year_is_canonicalized() -> None:
    assert _optional_int("2018", label="year") == 2018
    assert _optional_int("2018.0", label="year") == 2018


def test_corpus_builder_quarantines_target_edge_fields(tmp_path) -> None:
    target_id = "a" * 40
    paper_id = "b" * 40
    target_row = {"paperId": target_id, "title": "Target", "abstract": "Target text"}
    reference_row = {
        "abstract": "A sufficiently detailed source-faithful abstract for local retrieval evidence.",
        "citationCount": "100",
        "contexts": "['target-authored citation context']",
        "externalIds": "{'DOI': '10.1000/reference'}",
        "intents": "['background']",
        "isInfluential": "True",
        "paperId": paper_id,
        "publicationTypes": "['JournalArticle']",
        "targetPaperId": target_id,
        "title": "Reference title",
        "venue": "Journal",
        "year": "2018.0",
    }
    source = SourceData(
        target_rows={target_id: target_row},
        target_row_numbers={target_id: 2},
        references_by_target={target_id: (reference_row,)},
        reference_row_numbers={(target_id, paper_id): 2},
        clusters={target_id: "Health & Medicine"},
        source_hashes={"filtered_references.csv": "c" * 64},
    )
    feature = CaseFeature(
        target_id=target_id,
        cluster="Health & Medicine",
        strategy=1,
        reference_count=3,
        stratum="small",
        overlap_ppm=50_000,
        split_bucket="development",
        selection_key="d" * 64,
        target_row_number=2,
        target_row_sha256="e" * 64,
    )

    result = _build_corpus_bundle(tmp_path, "case-a", feature, source)
    corpus = json.loads((tmp_path / "corpora/case-a/corpus.json").read_text())
    evidence = (tmp_path / "corpora/case-a/evidence/source-rows.jsonl").read_text()
    runtime_text = json.dumps(corpus)

    assert result["status"] == "pending_robert_approval"
    assert corpus["records"][0]["year"] == 2018
    assert "contexts" not in runtime_text
    assert "targetPaperId" not in runtime_text
    assert "target-authored citation context" in evidence
    assert (
        json.loads((tmp_path / "corpora/case-a/validation-report.json").read_text())[
            "status"
        ]
        == "pass"
    )


def _target_row() -> dict[str, str]:
    return {
        "abstract": (
            "Older adults experience changing mobility constraints, and broad preventive "
            "strategies remain difficult to compare across community settings."
        ),
        "abstract_summary": "This study proposes a named intervention and reports improved mobility.",
        "externalIds": "{'DOI': '10.1000/example', 'PubMed': '12345'}",
        "title": "A Named Intervention for Improved Mobility",
    }


def test_workshop_validator_accepts_canonical_problem_space_draft() -> None:
    workshop = (
        b"# Title: Mobility resilience in later life\n\n"
        b"## Keywords\naging, mobility, community health\n\n"
        b"## TL;DR\nHow can mobility resilience be studied across diverse community settings?\n\n"
        b"## Abstract\nMobility changes can affect independence and participation in later life. "
        b"Research is needed to characterize modifiable constraints and compare multiple "
        b"families of preventive or supportive approaches without presupposing one intervention.\n"
    )

    report = validate_workshop_bytes(
        workshop,
        target_id="a" * 40,
        target_row=_target_row(),
        reference_rows=(),
    )

    assert report["deterministic_status"] == "pass"
    assert report["semantic_review_status"] == "pending_independent_review"


def test_workshop_validator_rejects_identity_and_copied_spans() -> None:
    target = _target_row()
    workshop = (
        b"# Title: A Named Intervention for Improved Mobility\n\n"
        b"## Keywords\naging, mobility\n\n"
        b"## TL;DR\nWhat should be studied?\n\n"
        b"## Abstract\nOlder adults experience changing mobility constraints, and broad preventive "
        b"strategies remain difficult to compare across community settings. See "
        b"https://doi.org/10.1000/example.\n"
    )

    report = validate_workshop_bytes(
        workshop,
        target_id="a" * 40,
        target_row=target,
        reference_rows=(),
    )

    assert report["deterministic_status"] == "fail"
    rule_ids = {failure["rule_id"] for failure in report["failures"]}
    assert "WORKSHOP-IDENTITY-TITLE" in rule_ids
    assert "WORKSHOP-IDENTITY-URL" in rule_ids
    assert "WORKSHOP-IDENTITY-DOI" in rule_ids
    assert "WORKSHOP-LEAKAGE-NGRAM" in rule_ids


def test_workshop_validator_rejects_an_extra_section() -> None:
    workshop = (
        b"# Title: Mobility questions\n\n"
        b"## Keywords\naging, mobility\n\n"
        b"## TL;DR\nWhat constraints matter?\n\n"
        b"## Abstract\nSeveral approaches remain plausible.\n\n"
        b"## Method\nUse the held-out answer.\n"
    )

    report = validate_workshop_bytes(
        workshop,
        target_id="a" * 40,
        target_row=_target_row(),
        reference_rows=(),
    )

    assert report["deterministic_status"] == "fail"
    assert "WORKSHOP-SCHEMA-004" in {
        failure["rule_id"] for failure in report["failures"]
    }


def test_review_report_contains_hashes_not_copied_ngram_text() -> None:
    target = _target_row()
    workshop = (
        "# Title: Mobility questions\n\n"
        "## Keywords\naging, mobility\n\n"
        "## TL;DR\nWhat constraints matter?\n\n"
        f"## Abstract\n{target['abstract']}\n"
    ).encode()

    report = validate_workshop_bytes(
        workshop,
        target_id="a" * 40,
        target_row=target,
        reference_rows=(),
    )
    serialized = json.dumps(report)

    assert target["abstract"] not in serialized
    assert "ngram_sha256" in serialized
