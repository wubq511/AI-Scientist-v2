from __future__ import annotations

import hashlib
import json

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.input_preparation import (
    CORPUS_NORMALIZATION_VERSION,
    CORPUS_SCHEMA_VERSION,
    CORPUS_VALIDATOR_VERSION,
    ENRICHMENT_POLICY_VERSION,
    INPUT_REVIEW_SCHEMA_VERSION,
    SELECTION_VERSION,
    WORKSHOP_CONTRACT_VERSION,
    WORKSHOP_VALIDATOR_VERSION,
    CaseFeature,
    SourceData,
    _build_corpus_bundle,
    _case_assignments,
    _optional_int,
    approve_inputs,
    select_cases,
    select_operational_cases,
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


def test_operational_selection_excludes_spent_and_covers_all_clusters() -> None:
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
    counts = {"small": 3, "medium": 9, "large": 19}
    features = []
    index = 0
    for cluster in clusters:
        for stratum, base_count in counts.items():
            for offset in range(2):
                features.append(
                    CaseFeature(
                        target_id=f"fresh-target-{index:03d}",
                        cluster=cluster,
                        strategy=(
                            2
                            if cluster == "Technology & Engineering"
                            and stratum == "small"
                            else 1
                        ),
                        reference_count=base_count + offset,
                        stratum=stratum,
                        overlap_ppm=10_000 + index * 1_000,
                        split_bucket="development",
                        selection_key=f"{index:064x}",
                        target_row_number=index + 2,
                        target_row_sha256=f"{index + 100:064x}",
                    )
                )
                index += 1
    spent = {features[0].target_id}
    first = select_operational_cases(
        tuple(features),
        spent_target_ids=spent,
        source_hashes={"source": "a" * 64},
        spent_sha256="b" * 64,
    )
    second = select_operational_cases(
        tuple(reversed(features)),
        spent_target_ids=spent,
        source_hashes={"source": "a" * 64},
        spent_sha256="b" * 64,
    )

    assert first == second
    assert len(first) == 12
    assert not spent.intersection(item.target_id for item in first)
    assert {item.cluster for item in first} == set(clusters)
    assert {
        stratum: sum(item.stratum == stratum for item in first)
        for stratum in ("small", "medium", "large")
    } == {"small": 4, "medium": 4, "large": 4}


def test_operational_selection_seeds_every_stratum_before_maximin_fill() -> None:
    features = []
    index = 0
    for cluster in ("cluster-a", "cluster-b", "cluster-c", "cluster-d"):
        for stratum, reference_count in (("small", 3), ("medium", 9), ("large", 19)):
            features.append(
                CaseFeature(
                    target_id=f"target-{index:02d}",
                    cluster=cluster,
                    strategy=1 if stratum == "large" else 2,
                    reference_count=reference_count,
                    stratum=stratum,
                    overlap_ppm=10_000 + index,
                    split_bucket="development",
                    selection_key=f"{index:064x}",
                    target_row_number=index + 2,
                    target_row_sha256=f"{index + 100:064x}",
                )
            )
            index += 1

    selected = select_operational_cases(
        tuple(features),
        spent_target_ids=set(),
        source_hashes={"source": "a" * 64},
        spent_sha256="b" * 64,
    )

    assert len(selected) == 12
    assert {
        stratum: sum(item.stratum == stratum for item in selected)
        for stratum in ("small", "medium", "large")
    } == {"small": 4, "medium": 4, "large": 4}


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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path, value) -> bytes:
    data = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _approval_fixture(tmp_path):
    repo_root = tmp_path
    preparation_root = (
        repo_root
        / "artifacts/local-ranking-prototype/input-preparation-v1/attempts/inputs-test"
    )
    case_id = "lr-dev-01"
    selection_bytes = _write_json(
        preparation_root / "selection-manifest.json",
        {"cases": [{"case_id": case_id}], "selection_version": SELECTION_VERSION},
    )
    selection_sha256 = _sha256(selection_bytes)

    workshop_bytes = (
        b"# Title: General research problem\n\n"
        b"## Keywords\nresearch, evidence\n\n"
        b"## TL;DR\nWhich approaches can address this problem?\n\n"
        b"## Abstract\nSeveral materially different approaches remain plausible.\n"
    )
    workshop_path = preparation_root / f"workshops/workshop-draft-001/{case_id}.md"
    workshop_path.parent.mkdir(parents=True, exist_ok=True)
    workshop_path.write_bytes(workshop_bytes)
    workshop_report_bytes = _write_json(
        preparation_root / f"workshop-validations/workshop-draft-001/{case_id}.json",
        {"deterministic_status": "pass"},
    )
    _write_json(
        preparation_root
        / "workshop-validations/workshop-draft-001/workshop-manifest.json",
        {
            "approval_status": "pending_independent_semantic_review",
            "case_count": 1,
            "contract_version": WORKSHOP_CONTRACT_VERSION,
            "deterministic_failure_count": 0,
            "draft_set": "workshop-draft-001",
            "reports": [
                {
                    "case_id": case_id,
                    "draft_sha256": _sha256(workshop_bytes),
                    "status": "pass",
                    "validation_report_sha256": _sha256(workshop_report_bytes),
                }
            ],
            "review_packet_sha256": "a" * 64,
            "validator_version": WORKSHOP_VALIDATOR_VERSION,
        },
    )

    corpus_root = preparation_root / f"corpora/{case_id}"
    corpus_bytes = _write_json(
        corpus_root / "corpus.json",
        {
            "case_id": case_id,
            "records": [
                {
                    "content_items": [
                        {
                            "status": "validated",
                            "text": "Private reference abstract that query authors must not read.",
                            "type": "publisher_abstract",
                        }
                    ],
                    "paper_id": "b" * 40,
                    "title": "Private reference title",
                }
            ],
        },
    )
    corpus_report_bytes = _write_json(
        corpus_root / "validation-report.json",
        {
            "error_count": 0,
            "status": "pass",
            "validator_version": CORPUS_VALIDATOR_VERSION,
        },
    )
    versions = {
        "enrichment_policy": ENRICHMENT_POLICY_VERSION,
        "normalization": CORPUS_NORMALIZATION_VERSION,
        "schema": CORPUS_SCHEMA_VERSION,
        "validator": CORPUS_VALIDATOR_VERSION,
    }
    bundle_manifest_bytes = _write_json(
        corpus_root / "bundle-manifest.json",
        {
            "approval_status": "pending_robert_approval",
            "versions": versions,
        },
    )
    preparation_bytes = _write_json(
        preparation_root / "preparation-manifest.json",
        {
            "case_count": 1,
            "corpus_bundles": [
                {
                    "bundle_content_sha256": "c" * 64,
                    "case_id": case_id,
                    "corpus_sha256": _sha256(corpus_bytes),
                    "manifest_sha256": _sha256(bundle_manifest_bytes),
                    "validation_report_sha256": _sha256(corpus_report_bytes),
                }
            ],
            "selection_manifest_sha256": selection_sha256,
        },
    )
    assert preparation_bytes

    protocol_path = repo_root / "docs/prototypes/protocol.md"
    protocol_path.parent.mkdir(parents=True, exist_ok=True)
    protocol_bytes = b"approved protocol v1.1\n"
    protocol_path.write_bytes(protocol_bytes)
    decision_path = preparation_root / "review-decisions/input-approval-test.json"
    decision = {
        "approval_id": "input-approval-test",
        "approved_on": "2026-08-30",
        "authority": {
            "decision_actor": "Codex",
            "delegated_by": "Robert",
            "delegation_text": "Review and decide.",
            "review_method": "first-principles semantic and corpus audit",
        },
        "case_reviews": [
            {
                "case_id": case_id,
                "checks": {
                    "multiple_method_families": True,
                    "no_answer_leakage": True,
                    "no_identity_leakage": True,
                    "target_relevance": True,
                },
                "rationale": "The problem remains relevant, open, and non-identifying.",
                "status": "approved",
            }
        ],
        "corpus_policy": {
            "allowed_content_types": ["publisher_abstract"],
            "conclusion_scope": "abstract_level_local_paper_ranking",
            "limitations": ["Does not establish full-text retrieval quality."],
            "rationale": "This comparison measures the runtime's available source content.",
            "status": "approved",
            "versions": versions,
        },
        "protocol": {
            "path": "docs/prototypes/protocol.md",
            "sha256": _sha256(protocol_bytes),
            "version": "v1.1",
        },
        "schema_version": INPUT_REVIEW_SCHEMA_VERSION,
        "selection": {
            "rationale": "The case preserves the frozen selection policy.",
            "selection_manifest_sha256": selection_sha256,
            "status": "approved",
        },
    }
    _write_json(decision_path, decision)
    return preparation_root, decision_path, protocol_path, decision


def test_input_approval_writes_hash_bound_query_author_packet(tmp_path) -> None:
    preparation_root, decision_path, protocol_path, _ = _approval_fixture(tmp_path)

    result = approve_inputs(
        tmp_path,
        preparation_root,
        "workshop-draft-001",
        decision_path,
        protocol_path,
        "input-approval-test",
    )

    assert result["approval_status"] == "approved"
    approval_root = preparation_root / "approvals/input-approval-test"
    packet_text = (approval_root / "query-author-packet/manifest.json").read_text() + (
        approval_root / "query-author-packet/workshops/lr-dev-01.md"
    ).read_text()
    assert "Private reference abstract" not in packet_text
    assert "Private reference title" not in packet_text
    assert (
        json.loads((approval_root / "approval-manifest.json").read_text())[
            "approval_status"
        ]
        == "approved"
    )

    with pytest.raises(HarnessError, match="ARTIFACT_EXISTS"):
        approve_inputs(
            tmp_path,
            preparation_root,
            "workshop-draft-001",
            decision_path,
            protocol_path,
            "input-approval-test",
        )


def test_input_approval_rejects_incomplete_semantic_decision(tmp_path) -> None:
    preparation_root, decision_path, protocol_path, decision = _approval_fixture(
        tmp_path
    )
    decision["case_reviews"][0]["checks"]["no_answer_leakage"] = False
    _write_json(decision_path, decision)

    with pytest.raises(HarnessError, match="APPROVAL_REQUIRED"):
        approve_inputs(
            tmp_path,
            preparation_root,
            "workshop-draft-001",
            decision_path,
            protocol_path,
            "input-approval-test",
        )


def test_input_approval_rejects_corpus_drift(tmp_path) -> None:
    preparation_root, decision_path, protocol_path, _ = _approval_fixture(tmp_path)
    corpus_path = preparation_root / "corpora/lr-dev-01/corpus.json"
    corpus = json.loads(corpus_path.read_text())
    corpus["records"][0]["title"] = "Tampered title"
    _write_json(corpus_path, corpus)

    with pytest.raises(HarnessError, match="HASH_MISMATCH"):
        approve_inputs(
            tmp_path,
            preparation_root,
            "workshop-draft-001",
            decision_path,
            protocol_path,
            "input-approval-test",
        )
