from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations, product
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_json_bytes,
    resolve_repo_relative,
    sha256_bytes,
    write_json_once,
    write_once,
)
from .errors import HarnessError, fail
from .normalization import normalize_text, tokenize_text

SELECTION_VERSION = "local-ranking-case-selection-v1.1"
OPERATIONAL_SELECTION_VERSION = "local-ranking-operational-case-selection-v1.0.1"
SELECTION_SPLIT_SEED_VERSION = "local-ranking-case-selection-v1"
CORPUS_SCHEMA_VERSION = "prototype-frozen-corpus-v1"
CORPUS_NORMALIZATION_VERSION = "source-text-nfc-lf-trim-v1"
ENRICHMENT_POLICY_VERSION = "raw-ideabench-reference-v1"
CORPUS_VALIDATOR_VERSION = "prototype-corpus-validator-v1.0.1"
WORKSHOP_VALIDATOR_VERSION = "prototype-workshop-validator-v1.0.1"
WORKSHOP_CONTRACT_VERSION = "workshop-contract-v1.0"
INPUT_REVIEW_SCHEMA_VERSION = "prototype-input-review-v1.0"
INPUT_APPROVAL_SCHEMA_VERSION = "prototype-input-approval-v1.0"
WORKSHOP_NGRAM_TOKENS = 8
SPLITS = ("development", "holdout")
OPERATIONAL_SPLIT = "operational"
STRATA = ("small", "medium", "large")
OPERATIONAL_CASES_PER_STRATUM = 4
AUDITED_UNREADY_REFERENCE_ID_HASHES = {
    "c31acf1c711e32b3e56b3e2e3be3f0822b403b1f17c12010627814171a6f4c85",
    "d0456963cabaab0703cd04f1aa3258e5a034659fce2ee1229cce07a9287783c7",
    "df6feb0d52a9864816ffc2ced84e63f8331969c54a406b1f2fd7effb17a3724c",
}
EXPECTED_SOURCE_HASHES = {
    "filtered_references.csv": (
        "afaa733c6cddac1b0d31c240189cc3dd73b449dc7b99cb9ddc0cd8a4847930a6"
    ),
    "ideabench_clustering.json": (
        "ce67a168545067130f8892554a5453cde7a37073e583b8d09ea6fbbc21a4f423"
    ),
    "target_papers.csv": (
        "ba71dc35e1209ff0e51a440dea1d3ba96dfa5a92a2af2e472313a1b79240b96c"
    ),
}
WORKSHOP_PATTERN = re.compile(
    r"\A# Title: ([^\n]+)\n\n"
    r"## Keywords\n([^\n]+)\n\n"
    r"## TL;DR\n([^\n]+)\n\n"
    r"## Abstract\n(.+)\n\Z",
    re.DOTALL,
)
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
PAPER_ID_PATTERN = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)
APPROVAL_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class SourceData:
    target_rows: dict[str, dict[str, str]]
    target_row_numbers: dict[str, int]
    references_by_target: dict[str, tuple[dict[str, str], ...]]
    reference_row_numbers: dict[tuple[str, str], int]
    clusters: dict[str, str]
    source_hashes: dict[str, str]


@dataclass(frozen=True, slots=True)
class CaseFeature:
    target_id: str
    cluster: str
    strategy: int
    reference_count: int
    stratum: str
    overlap_ppm: int
    split_bucket: str
    selection_key: str
    target_row_number: int
    target_row_sha256: str


def _literal(value: str, *, label: str, expected: type[Any]) -> Any:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        fail("INVALID_RAW_DATA", f"{label} is not a Python literal", error=str(exc))
    if not isinstance(parsed, expected):
        fail(
            "INVALID_RAW_DATA",
            f"{label} has an unexpected type",
            expected=expected.__name__,
            actual=type(parsed).__name__,
        )
    return parsed


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            fail("INVALID_RAW_DATA", f"{path.name} has no header")
        rows = list(reader)
    return list(reader.fieldnames), rows


def _source_hash(path: Path) -> str:
    digest = sha256_bytes(path.read_bytes())
    expected = EXPECTED_SOURCE_HASHES.get(path.name)
    if expected is not None and digest != expected:
        fail(
            "SOURCE_DRIFT",
            f"{path.name} differs from the approved source snapshot",
            expected=expected,
            actual=digest,
        )
    return digest


def load_source_data(raw_root: Path) -> SourceData:
    paths = {name: raw_root / name for name in EXPECTED_SOURCE_HASHES}
    for path in paths.values():
        if not path.is_file():
            fail("MISSING_ARTIFACT", "Required raw input is missing", path=str(path))
    source_hashes = {name: _source_hash(path) for name, path in paths.items()}

    _, target_rows_raw = _read_csv(paths["target_papers.csv"])
    _, reference_rows = _read_csv(paths["filtered_references.csv"])
    try:
        cluster_groups = json.loads(
            paths["ideabench_clustering.json"].read_text(encoding="utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_RAW_DATA", "Cluster file is not valid UTF-8 JSON", error=str(exc))
    if not isinstance(cluster_groups, dict):
        fail("INVALID_RAW_DATA", "Cluster file must be an object")

    target_rows: dict[str, dict[str, str]] = {}
    target_row_numbers: dict[str, int] = {}
    for row_number, row in enumerate(target_rows_raw, start=2):
        target_id = row.get("paperId", "")
        if not target_id or target_id in target_rows:
            fail("INVALID_RAW_DATA", "Target IDs must be non-empty and unique")
        target_rows[target_id] = row
        target_row_numbers[target_id] = row_number

    references: dict[str, list[dict[str, str]]] = defaultdict(list)
    reference_row_numbers: dict[tuple[str, str], int] = {}
    for row_number, row in enumerate(reference_rows, start=2):
        target_id = row.get("targetPaperId", "")
        paper_id = row.get("paperId", "")
        edge = (target_id, paper_id)
        if not target_id or not paper_id or edge in reference_row_numbers:
            fail("INVALID_RAW_DATA", "Reference memberships must be unique")
        references[target_id].append(row)
        reference_row_numbers[edge] = row_number

    clusters: dict[str, str] = {}
    for cluster_name, target_ids in cluster_groups.items():
        if not isinstance(cluster_name, str) or not isinstance(target_ids, list):
            fail("INVALID_RAW_DATA", "Cluster entries have an invalid schema")
        for target_id in target_ids:
            if not isinstance(target_id, str) or target_id in clusters:
                fail("INVALID_RAW_DATA", "Cluster membership must be unique")
            clusters[target_id] = cluster_name

    target_ids = set(target_rows)
    if set(references) != target_ids or set(clusters) != target_ids:
        fail(
            "INVALID_RAW_DATA",
            "Target, reference-membership, and cluster identities must match",
        )
    return SourceData(
        target_rows=target_rows,
        target_row_numbers=target_row_numbers,
        references_by_target={
            target_id: tuple(rows) for target_id, rows in references.items()
        },
        reference_row_numbers=reference_row_numbers,
        clusters=clusters,
        source_hashes=source_hashes,
    )


def _stratum(reference_count: int) -> str:
    if 3 <= reference_count <= 8:
        return "small"
    if 9 <= reference_count <= 18:
        return "medium"
    if 19 <= reference_count <= 36:
        return "large"
    fail(
        "INVALID_RAW_DATA",
        "Reference count is outside the approved 3-36 range",
        reference_count=reference_count,
    )


def _row_sha256(row: dict[str, str]) -> str:
    return sha256_bytes(canonical_json_bytes(row))


def _title_content_overlap_ppm(references: Iterable[dict[str, str]]) -> int:
    values: list[int] = []
    for row in references:
        title_tokens = set(tokenize_text(row["title"], label="reference.title"))
        abstract_tokens = set(
            tokenize_text(row["abstract"], label="reference.abstract")
        )
        union = title_tokens | abstract_tokens
        values.append(
            0
            if not union
            else (len(title_tokens & abstract_tokens) * 1_000_000) // len(union)
        )
    return sum(values) // len(values)


def _source_split(target_id: str, source_hashes: dict[str, str]) -> tuple[str, str]:
    seed = "|".join(
        [
            SELECTION_SPLIT_SEED_VERSION,
            *(source_hashes[name] for name in sorted(source_hashes)),
        ]
    )
    selection_key = sha256_bytes(f"{seed}|{target_id}".encode())
    split = SPLITS[int(selection_key[:8], 16) % len(SPLITS)]
    return split, selection_key


def derive_case_features(source: SourceData) -> tuple[CaseFeature, ...]:
    features: list[CaseFeature] = []
    for target_id, row in source.target_rows.items():
        references = source.references_by_target[target_id]
        if not row["title"].strip() or not row["abstract"].strip():
            continue
        if any(
            not reference["title"].strip()
            or not reference["abstract"].strip()
            or sha256_bytes(reference["paperId"].encode())
            in AUDITED_UNREADY_REFERENCE_ID_HASHES
            for reference in references
        ):
            continue
        strategy = _literal(
            row["strategy"], label=f"target {target_id} strategy", expected=int
        )
        split, selection_key = _source_split(target_id, source.source_hashes)
        features.append(
            CaseFeature(
                target_id=target_id,
                cluster=source.clusters[target_id],
                strategy=strategy,
                reference_count=len(references),
                stratum=_stratum(len(references)),
                overlap_ppm=_title_content_overlap_ppm(references),
                split_bucket=split,
                selection_key=selection_key,
                target_row_number=source.target_row_numbers[target_id],
                target_row_sha256=_row_sha256(row),
            )
        )
    return tuple(features)


def _pair_sort_key(pair: tuple[CaseFeature, CaseFeature]) -> tuple[Any, ...]:
    left, right = pair
    return (
        -len({left.cluster, right.cluster}),
        -int(left.strategy == 2 or right.strategy == 2),
        -abs(left.reference_count - right.reference_count),
        -abs(left.overlap_ppm - right.overlap_ppm),
        tuple(sorted((left.selection_key, right.selection_key))),
    )


def _selection_sort_key(selection: tuple[CaseFeature, ...]) -> tuple[Any, ...]:
    by_stratum = {
        stratum: tuple(case for case in selection if case.stratum == stratum)
        for stratum in STRATA
    }
    return (
        -len({case.cluster for case in selection}),
        -sum(case.strategy == 2 for case in selection),
        -sum(
            abs(cases[0].reference_count - cases[1].reference_count)
            for cases in by_stratum.values()
            if len(cases) == 2
        ),
        -sum(
            abs(cases[0].overlap_ppm - cases[1].overlap_ppm)
            for cases in by_stratum.values()
            if len(cases) == 2
        ),
        tuple(sorted(case.selection_key for case in selection)),
    )


def _split_selections(
    features: tuple[CaseFeature, ...], split: str, *, keep: int = 300
) -> list[tuple[CaseFeature, ...]]:
    pair_lists: dict[str, list[tuple[CaseFeature, CaseFeature]]] = {}
    for stratum in STRATA:
        candidates = sorted(
            (
                case
                for case in features
                if case.split_bucket == split and case.stratum == stratum
            ),
            key=lambda case: case.selection_key,
        )
        if len(candidates) < 2:
            fail(
                "INSUFFICIENT_CASES",
                "A deterministic split lacks two cases in a required stratum",
                split=split,
                stratum=stratum,
                count=len(candidates),
            )
        pair_lists[stratum] = sorted(combinations(candidates, 2), key=_pair_sort_key)[
            :1000
        ]

    states: list[tuple[CaseFeature, ...]] = [()]
    for stratum in STRATA:
        expanded = [state + pair for state in states for pair in pair_lists[stratum]]
        states = sorted(expanded, key=_selection_sort_key)[:1000]
    return sorted(states, key=_selection_sort_key)[:keep]


def _combined_selection_sort_key(
    development: tuple[CaseFeature, ...], holdout: tuple[CaseFeature, ...]
) -> tuple[Any, ...]:
    combined = development + holdout
    count_balance = 0
    overlap_balance = 0
    for stratum in STRATA:
        dev_cases = [case for case in development if case.stratum == stratum]
        hold_cases = [case for case in holdout if case.stratum == stratum]
        count_balance += abs(
            sum(case.reference_count for case in dev_cases)
            - sum(case.reference_count for case in hold_cases)
        )
        overlap_balance += abs(
            sum(case.overlap_ppm for case in dev_cases)
            - sum(case.overlap_ppm for case in hold_cases)
        )
    return (
        -len({case.cluster for case in combined}),
        -min(
            len({case.cluster for case in development}),
            len({case.cluster for case in holdout}),
        ),
        -sum(case.strategy == 2 for case in combined),
        _selection_sort_key(development)[:-1],
        _selection_sort_key(holdout)[:-1],
        count_balance,
        overlap_balance,
        tuple(sorted(case.selection_key for case in combined)),
    )


def select_cases(
    features: tuple[CaseFeature, ...],
) -> dict[str, tuple[CaseFeature, ...]]:
    candidates = {split: _split_selections(features, split) for split in SPLITS}
    combinations_to_score = (
        (development, holdout)
        for development in candidates["development"]
        for holdout in candidates["holdout"]
    )
    development, holdout = min(
        combinations_to_score,
        key=lambda pair: _combined_selection_sort_key(pair[0], pair[1]),
    )
    if len({case.cluster for case in development + holdout}) < 8:
        fail(
            "INSUFFICIENT_CASE_DIVERSITY",
            "The selected ranking cases do not cover all eight available clusters",
        )
    return {
        "development": development,
        "holdout": holdout,
    }


def _case_assignments(
    selected: dict[str, tuple[CaseFeature, ...]],
) -> list[tuple[str, str, CaseFeature]]:
    stratum_index = {name: index for index, name in enumerate(STRATA)}
    assignments: list[tuple[str, str, CaseFeature]] = []
    for split in SPLITS:
        ordered = sorted(
            selected[split],
            key=lambda case: (
                stratum_index[case.stratum],
                case.reference_count,
                case.selection_key,
            ),
        )
        for index, case in enumerate(ordered, start=1):
            assignments.append((f"lr-{split[:3]}-{index:02d}", split, case))
    return assignments


def _operational_selection_key(
    feature: CaseFeature, *, source_hashes: dict[str, str], spent_sha256: str
) -> str:
    seed = "|".join(
        [
            OPERATIONAL_SELECTION_VERSION,
            spent_sha256,
            *(source_hashes[name] for name in sorted(source_hashes)),
        ]
    )
    return sha256_bytes(f"{seed}|{feature.target_id}".encode())


def select_operational_cases(
    features: tuple[CaseFeature, ...],
    *,
    spent_target_ids: set[str],
    source_hashes: dict[str, str],
    spent_sha256: str,
) -> tuple[CaseFeature, ...]:
    fresh = tuple(
        feature for feature in features if feature.target_id not in spent_target_ids
    )
    expected_total = OPERATIONAL_CASES_PER_STRATUM * len(STRATA)
    by_stratum = {
        stratum: tuple(feature for feature in fresh if feature.stratum == stratum)
        for stratum in STRATA
    }
    for stratum, candidates in by_stratum.items():
        if len(candidates) < OPERATIONAL_CASES_PER_STRATUM:
            fail(
                "INSUFFICIENT_CASES",
                "Fresh operational selection lacks a required stratum",
                stratum=stratum,
                count=len(candidates),
            )

    clusters = tuple(sorted({feature.cluster for feature in fresh}))
    if len(clusters) > expected_total:
        fail(
            "INSUFFICIENT_CASE_DIVERSITY",
            "Operational case budget cannot cover every source cluster",
            cluster_count=len(clusters),
            case_budget=expected_total,
        )
    keys = {
        feature.target_id: _operational_selection_key(
            feature,
            source_hashes=source_hashes,
            spent_sha256=spent_sha256,
        )
        for feature in fresh
    }
    representatives: dict[tuple[str, str], CaseFeature] = {}
    cluster_options: list[tuple[str, tuple[str, ...]]] = []
    for cluster in clusters:
        options: list[str] = []
        for stratum in STRATA:
            candidates = [
                feature for feature in by_stratum[stratum] if feature.cluster == cluster
            ]
            if not candidates:
                continue
            representative = min(
                candidates,
                key=lambda feature: (
                    -int(feature.strategy == 2),
                    keys[feature.target_id],
                ),
            )
            representatives[(cluster, stratum)] = representative
            options.append(stratum)
        if not options:
            fail(
                "INSUFFICIENT_CASE_DIVERSITY",
                "A source cluster has no fresh eligible case",
                cluster=cluster,
            )
        cluster_options.append((cluster, tuple(options)))

    feasible_assignments: list[tuple[tuple[Any, ...], tuple[CaseFeature, ...]]] = []
    for assignment in product(*(options for _, options in cluster_options)):
        counts = {stratum: assignment.count(stratum) for stratum in STRATA}
        if any(
            counts[stratum] < 1 or counts[stratum] > OPERATIONAL_CASES_PER_STRATUM
            for stratum in STRATA
        ):
            continue
        selected = tuple(
            representatives[(cluster, stratum)]
            for (cluster, _), stratum in zip(cluster_options, assignment, strict=True)
        )
        score = (
            -sum(feature.strategy == 2 for feature in selected),
            sum(int(keys[feature.target_id][:16], 16) for feature in selected),
            tuple(sorted(keys[feature.target_id] for feature in selected)),
        )
        feasible_assignments.append((score, selected))
    if not feasible_assignments:
        fail(
            "INSUFFICIENT_CASE_DIVERSITY",
            "No stratum-balanced assignment covers every source cluster",
        )
    selected = list(min(feasible_assignments, key=lambda item: item[0])[1])

    for stratum in STRATA:
        stratum_selected = [
            feature for feature in selected if feature.stratum == stratum
        ]
        ref_values = [feature.reference_count for feature in by_stratum[stratum]]
        overlap_values = [feature.overlap_ppm for feature in by_stratum[stratum]]
        ref_span = max(ref_values) - min(ref_values)
        overlap_span = max(overlap_values) - min(overlap_values)
        while len(stratum_selected) < OPERATIONAL_CASES_PER_STRATUM:
            candidates = [
                feature for feature in by_stratum[stratum] if feature not in selected
            ]

            def fill_key(feature: CaseFeature) -> tuple[Any, ...]:
                distances = []
                for existing in stratum_selected:
                    ref_distance = (
                        abs(feature.reference_count - existing.reference_count)
                        * 1_000_000
                        // max(1, ref_span)
                    )
                    overlap_distance = (
                        abs(feature.overlap_ppm - existing.overlap_ppm)
                        * 1_000_000
                        // max(1, overlap_span)
                    )
                    distances.append(ref_distance + overlap_distance)
                return (
                    -min(distances, default=0),
                    -int(feature.strategy == 2),
                    keys[feature.target_id],
                )

            chosen = min(candidates, key=fill_key)
            selected.append(chosen)
            stratum_selected.append(chosen)

    if (
        len(selected) != expected_total
        or len({item.target_id for item in selected}) != expected_total
    ):
        fail("INVALID_SELECTION", "Operational selection is incomplete or duplicated")
    if {item.cluster for item in selected} != set(clusters):
        fail(
            "INSUFFICIENT_CASE_DIVERSITY", "Operational selection lost cluster coverage"
        )
    return tuple(
        sorted(
            selected,
            key=lambda feature: (
                STRATA.index(feature.stratum),
                feature.reference_count,
                keys[feature.target_id],
            ),
        )
    )


def _operational_assignments(
    selected: tuple[CaseFeature, ...],
) -> list[tuple[str, str, CaseFeature]]:
    return [
        (f"lr-op-{index:02d}", OPERATIONAL_SPLIT, feature)
        for index, feature in enumerate(selected, start=1)
    ]


def _canonical_source_text(value: str, *, label: str) -> tuple[str, list[str]]:
    if not isinstance(value, str) or not value:
        fail("INVALID_RAW_DATA", f"{label} must be a non-empty string")
    transforms: list[str] = []
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if normalized != value:
        transforms.append("line-endings-to-lf")
    nfc = unicodedata.normalize("NFC", normalized)
    if nfc != normalized:
        transforms.append("unicode-nfc")
    trimmed = nfc.strip()
    if trimmed != nfc:
        transforms.append("outer-whitespace-trim")
    if not trimmed:
        fail("INVALID_RAW_DATA", f"{label} is empty after normalization")
    return trimmed, transforms


def _canonical_external_ids(raw: str, *, label: str) -> dict[str, str | int]:
    value = _literal(raw, label=label, expected=dict)
    result: dict[str, str | int] = {}
    for key, item in value.items():
        if (
            not isinstance(key, str)
            or isinstance(item, bool)
            or not isinstance(item, (str, int))
        ):
            fail("INVALID_RAW_DATA", f"{label} contains an invalid identifier")
        result[key] = item
    if not result:
        fail("INVALID_RAW_DATA", f"{label} contains no identifier")
    return dict(sorted(result.items()))


def _optional_int(value: str, *, label: str) -> int | None:
    if not value:
        return None
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        fail("INVALID_RAW_DATA", f"{label} is not numeric", error=str(exc))
    if isinstance(parsed, bool) or not isinstance(parsed, (int, float)):
        fail("INVALID_RAW_DATA", f"{label} is not an integer-valued number")
    if isinstance(parsed, float) and not parsed.is_integer():
        fail("INVALID_RAW_DATA", f"{label} is not integer-valued", value=parsed)
    return int(parsed)


def _validation_rule(rule_id: str, *, summary: str) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "severity": "error",
        "status": "pass",
        "summary": summary,
    }


def _build_corpus_bundle(
    output_root: Path,
    case_id: str,
    feature: CaseFeature,
    source: SourceData,
) -> dict[str, Any]:
    bundle_root = output_root / "corpora" / case_id
    reference_rows = sorted(
        source.references_by_target[feature.target_id], key=lambda row: row["paperId"]
    )
    evidence_bytes = b"".join(canonical_json_bytes(row) for row in reference_rows)
    evidence_path = bundle_root / "evidence" / "source-rows.jsonl"
    write_once(evidence_path, evidence_bytes)
    evidence_sha256 = sha256_bytes(evidence_bytes)

    paper_ids = [row["paperId"] for row in reference_rows]
    private_membership_sha256 = sha256_bytes(
        canonical_json_bytes(
            {"paper_ids": paper_ids, "target_paper_id": feature.target_id}
        )
    )
    runtime_membership_sha256 = sha256_bytes(
        canonical_json_bytes({"case_id": case_id, "paper_ids": paper_ids})
    )
    records: list[dict[str, Any]] = []
    transform_count = 0
    for row in reference_rows:
        paper_id = row["paperId"]
        title, title_transforms = _canonical_source_text(
            row["title"], label=f"{paper_id}.title"
        )
        abstract, abstract_transforms = _canonical_source_text(
            row["abstract"], label=f"{paper_id}.abstract"
        )
        if sha256_bytes(paper_id.encode()) in AUDITED_UNREADY_REFERENCE_ID_HASHES:
            fail(
                "UNREADY_REFERENCE_CONTENT",
                "Selected case contains an audited reference awaiting enrichment",
                case_id=case_id,
                paper_id=paper_id,
            )
        transform_count += len(title_transforms) + len(abstract_transforms)
        row_sha256 = _row_sha256(row)
        raw_publication_types = _literal(
            row["publicationTypes"],
            label=f"{paper_id}.publicationTypes",
            expected=list,
        )
        if any(not isinstance(item, str) or not item for item in raw_publication_types):
            fail(
                "INVALID_RAW_DATA",
                f"{paper_id}.publicationTypes contains an invalid value",
            )
        publication_types = sorted(set(raw_publication_types))
        record = {
            "content_items": [
                {
                    "content_id": "abstract-01",
                    "provenance_ref": f"evidence/source-rows.jsonl#sha256={row_sha256}",
                    "sha256": sha256_bytes(abstract.encode("utf-8")),
                    "status": "validated",
                    "text": abstract,
                    "transforms": abstract_transforms,
                    "type": "publisher_abstract",
                }
            ],
            "external_ids": _canonical_external_ids(
                row["externalIds"], label=f"{paper_id}.externalIds"
            ),
            "paper_id": paper_id,
            "provenance_ref": f"evidence/source-rows.jsonl#sha256={row_sha256}",
            "publication_types": publication_types,
            "title": title,
            "title_transforms": title_transforms,
            "venue": row["venue"] or None,
            "year": _optional_int(row["year"], label=f"{paper_id}.year"),
        }
        records.append(record)

    corpus = {
        "case_id": case_id,
        "enrichment_policy_version": ENRICHMENT_POLICY_VERSION,
        "normalization_version": CORPUS_NORMALIZATION_VERSION,
        "private_raw_membership_sha256": private_membership_sha256,
        "records": records,
        "runtime_membership_sha256": runtime_membership_sha256,
        "schema_version": CORPUS_SCHEMA_VERSION,
        "source_dataset": {
            "path": "data/raw/filtered_references.csv",
            "sha256": source.source_hashes["filtered_references.csv"],
        },
    }
    corpus_bytes = canonical_json_bytes(corpus)
    corpus_path = bundle_root / "corpus.json"
    write_once(corpus_path, corpus_bytes)
    corpus_sha256 = sha256_bytes(corpus_bytes)

    forbidden_runtime_keys = {
        "targetPaperId",
        "contexts",
        "intents",
        "isInfluential",
        "citationCount",
        "abstract_summary",
        "query",
        "score",
        "rank",
    }
    serialized = json.dumps(corpus, ensure_ascii=False)
    leaked = sorted(key for key in forbidden_runtime_keys if f'"{key}"' in serialized)
    if leaked:
        fail(
            "BOUNDARY_VIOLATION",
            "Quarantined keys entered corpus.json",
            keys=leaked,
        )
    if [record["paper_id"] for record in records] != sorted(set(paper_ids)):
        fail("NON_CANONICAL_INPUT", "Corpus records are not sorted and unique")

    bundle_content = {
        "corpus.json": corpus_sha256,
        "evidence/source-rows.jsonl": evidence_sha256,
    }
    bundle_content_sha256 = sha256_bytes(canonical_json_bytes(bundle_content))
    rules = [
        _validation_rule("CORPUS-SCHEMA-001", summary="closed prototype schema"),
        _validation_rule("CORPUS-MAPPING-001", summary="one opaque case mapping"),
        _validation_rule("CORPUS-MEMBERSHIP-001", summary="membership hashes match"),
        _validation_rule("CORPUS-IDENTITY-001", summary="paper identities are unique"),
        _validation_rule(
            "CORPUS-CONTENT-001", summary="title and content are non-empty"
        ),
        _validation_rule(
            "CORPUS-PROVENANCE-001", summary="every record links a raw row hash"
        ),
        _validation_rule("CORPUS-HASH-001", summary="canonical artifact hashes match"),
        _validation_rule(
            "CORPUS-QUARANTINE-001", summary="forbidden fields stay in evidence"
        ),
        _validation_rule(
            "CORPUS-SOURCE-001", summary="source snapshot hash is approved"
        ),
    ]
    validation_report = {
        "bundle_content_sha256": bundle_content_sha256,
        "case_id": case_id,
        "corpus_sha256": corpus_sha256,
        "error_count": 0,
        "rules": rules,
        "status": "pass",
        "validator_version": CORPUS_VALIDATOR_VERSION,
        "warning_count": transform_count,
        "warnings": (
            []
            if transform_count == 0
            else [
                "Source-faithful NFC/LF/outer-whitespace canonicalization was recorded per field."
            ]
        ),
    }
    report_bytes = canonical_json_bytes(validation_report)
    report_path = bundle_root / "validation-report.json"
    write_once(report_path, report_bytes)
    report_sha256 = sha256_bytes(report_bytes)
    manifest = {
        "approval_status": "pending_robert_approval",
        "bundle_content_sha256": bundle_content_sha256,
        "case_id": case_id,
        "human_review": {
            "exceptional_content_count": 0,
            "ordinary_abstract_sampling_status": "pending",
            "policy_versions_approval_status": "pending",
        },
        "inventory": {
            "corpus.json": corpus_sha256,
            "evidence/source-rows.jsonl": evidence_sha256,
            "validation-report.json": report_sha256,
        },
        "versions": {
            "enrichment_policy": ENRICHMENT_POLICY_VERSION,
            "normalization": CORPUS_NORMALIZATION_VERSION,
            "schema": CORPUS_SCHEMA_VERSION,
            "validator": CORPUS_VALIDATOR_VERSION,
        },
    }
    manifest_path = bundle_root / "bundle-manifest.json"
    write_json_once(manifest_path, manifest)
    return {
        "bundle_content_sha256": bundle_content_sha256,
        "case_id": case_id,
        "corpus_sha256": corpus_sha256,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "record_count": len(records),
        "status": "pending_robert_approval",
        "validation_report_sha256": report_sha256,
    }


def prepare_inputs(
    repo_root: Path, raw_root: Path, output_root: Path
) -> dict[str, Any]:
    source = load_source_data(raw_root)
    features = derive_case_features(source)
    selected = select_cases(features)
    assignments = _case_assignments(selected)
    excluded_count = len(source.target_rows) - len(features)

    source_manifest = {
        "source_hashes": source.source_hashes,
        "source_paths": {
            name: (raw_root / name).relative_to(repo_root).as_posix()
            for name in sorted(source.source_hashes)
        },
    }
    write_json_once(output_root / "source-manifest.json", source_manifest)

    cases: list[dict[str, Any]] = []
    authoring_cases: list[dict[str, Any]] = []
    corpus_bundles: list[dict[str, Any]] = []
    for case_id, split, feature in assignments:
        target_row = source.target_rows[feature.target_id]
        cases.append(
            {
                "case_id": case_id,
                "cluster": feature.cluster,
                "overlap_ppm": feature.overlap_ppm,
                "reference_count": feature.reference_count,
                "selection_key": feature.selection_key,
                "split": split,
                "strategy": feature.strategy,
                "stratum": feature.stratum,
                "target_paper_id": feature.target_id,
                "target_row_number": feature.target_row_number,
                "target_row_sha256": feature.target_row_sha256,
            }
        )
        authoring_cases.append(
            {
                "case_id": case_id,
                "raw_abstract": target_row["abstract"],
                "source_allowlist": ["title", "abstract"],
                "target_row_sha256": feature.target_row_sha256,
                "title": target_row["title"],
            }
        )
        corpus_bundles.append(
            _build_corpus_bundle(output_root, case_id, feature, source)
        )

    selection_manifest = {
        "cases": sorted(cases, key=lambda item: item["case_id"]),
        "eligible_case_count": len(features),
        "excluded_unready_case_count": excluded_count,
        "selection_version": SELECTION_VERSION,
        "source_hashes": source.source_hashes,
    }
    write_json_once(output_root / "selection-manifest.json", selection_manifest)
    write_json_once(
        output_root / "workshop-authoring.json",
        {
            "cases": sorted(authoring_cases, key=lambda item: item["case_id"]),
            "contract_version": WORKSHOP_CONTRACT_VERSION,
            "notice": "Derivation input contains only target title and raw abstract.",
        },
    )
    preparation_manifest = {
        "approval_status": "pending_robert_approval",
        "case_count": len(cases),
        "corpus_bundles": sorted(corpus_bundles, key=lambda item: item["case_id"]),
        "selection_manifest_sha256": sha256_bytes(
            (output_root / "selection-manifest.json").read_bytes()
        ),
        "source_manifest_sha256": sha256_bytes(
            (output_root / "source-manifest.json").read_bytes()
        ),
        "workshop_authoring_sha256": sha256_bytes(
            (output_root / "workshop-authoring.json").read_bytes()
        ),
    }
    write_json_once(output_root / "preparation-manifest.json", preparation_manifest)

    strata_counts = {
        split: {
            stratum: sum(
                item["split"] == split and item["stratum"] == stratum for item in cases
            )
            for stratum in STRATA
        }
        for split in SPLITS
    }
    return {
        "approval_status": "pending_robert_approval",
        "case_count": len(cases),
        "cluster_count": len({item["cluster"] for item in cases}),
        "excluded_unready_case_count": excluded_count,
        "output_root": output_root.relative_to(repo_root).as_posix(),
        "split_counts": {
            split: sum(item["split"] == split for item in cases) for split in SPLITS
        },
        "strata_counts": strata_counts,
        "strategy_2_count": sum(item["strategy"] == 2 for item in cases),
    }


def prepare_operational_inputs(
    repo_root: Path,
    raw_root: Path,
    output_root: Path,
    spent_selection_path: Path,
) -> dict[str, Any]:
    source = load_source_data(raw_root)
    spent_selection, spent_bytes = _read_json_object(
        spent_selection_path, label="spent selection manifest"
    )
    if spent_selection.get("selection_version") != SELECTION_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Spent selection manifest version does not match")
    if spent_selection.get("source_hashes") != source.source_hashes:
        fail("SOURCE_DRIFT", "Spent selection uses a different source snapshot")
    spent_cases = spent_selection.get("cases")
    if not isinstance(spent_cases, list) or not spent_cases:
        fail("INVALID_SELECTION", "Spent selection contains no cases")
    spent_target_ids = {
        item.get("target_paper_id")
        for item in spent_cases
        if isinstance(item, dict) and isinstance(item.get("target_paper_id"), str)
    }
    if len(spent_target_ids) != len(spent_cases):
        fail("INVALID_SELECTION", "Spent selection target identities are incomplete")
    spent_sha256 = sha256_bytes(spent_bytes)
    features = derive_case_features(source)
    selected = select_operational_cases(
        features,
        spent_target_ids=spent_target_ids,
        source_hashes=source.source_hashes,
        spent_sha256=spent_sha256,
    )
    assignments = _operational_assignments(selected)
    excluded_count = len(source.target_rows) - len(features)
    selection_keys = {
        feature.target_id: _operational_selection_key(
            feature,
            source_hashes=source.source_hashes,
            spent_sha256=spent_sha256,
        )
        for feature in selected
    }

    source_manifest = {
        "source_hashes": source.source_hashes,
        "source_paths": {
            name: (raw_root / name).relative_to(repo_root).as_posix()
            for name in sorted(source.source_hashes)
        },
    }
    write_json_once(output_root / "source-manifest.json", source_manifest)

    cases: list[dict[str, Any]] = []
    authoring_cases: list[dict[str, Any]] = []
    corpus_bundles: list[dict[str, Any]] = []
    for case_id, split, feature in assignments:
        target_row = source.target_rows[feature.target_id]
        cases.append(
            {
                "case_id": case_id,
                "cluster": feature.cluster,
                "overlap_ppm": feature.overlap_ppm,
                "reference_count": feature.reference_count,
                "selection_key": selection_keys[feature.target_id],
                "split": split,
                "strategy": feature.strategy,
                "stratum": feature.stratum,
                "target_paper_id": feature.target_id,
                "target_row_number": feature.target_row_number,
                "target_row_sha256": feature.target_row_sha256,
            }
        )
        authoring_cases.append(
            {
                "case_id": case_id,
                "raw_abstract": target_row["abstract"],
                "source_allowlist": ["title", "abstract"],
                "target_row_sha256": feature.target_row_sha256,
                "title": target_row["title"],
            }
        )
        corpus_bundles.append(
            _build_corpus_bundle(output_root, case_id, feature, source)
        )

    spent_relative = _repo_relative(
        spent_selection_path, repo_root, label="spent selection manifest"
    )
    selection_manifest = {
        "cases": cases,
        "eligible_case_count": len(features),
        "excluded_spent_case_count": len(spent_target_ids),
        "excluded_unready_case_count": excluded_count,
        "fresh_candidate_count": len(features) - len(spent_target_ids),
        "selection_version": OPERATIONAL_SELECTION_VERSION,
        "source_hashes": source.source_hashes,
        "spent_selection": {
            "path": spent_relative,
            "sha256": spent_sha256,
        },
    }
    write_json_once(output_root / "selection-manifest.json", selection_manifest)
    write_json_once(
        output_root / "workshop-authoring.json",
        {
            "cases": authoring_cases,
            "contract_version": WORKSHOP_CONTRACT_VERSION,
            "notice": "Derivation input contains only target title and raw abstract.",
        },
    )
    preparation_manifest = {
        "approval_status": "pending_robert_approval",
        "case_count": len(cases),
        "corpus_bundles": corpus_bundles,
        "selection_manifest_sha256": sha256_bytes(
            (output_root / "selection-manifest.json").read_bytes()
        ),
        "source_manifest_sha256": sha256_bytes(
            (output_root / "source-manifest.json").read_bytes()
        ),
        "workshop_authoring_sha256": sha256_bytes(
            (output_root / "workshop-authoring.json").read_bytes()
        ),
    }
    write_json_once(output_root / "preparation-manifest.json", preparation_manifest)
    return {
        "approval_status": "pending_robert_approval",
        "case_count": len(cases),
        "cluster_count": len({item["cluster"] for item in cases}),
        "fresh_candidate_count": len(features) - len(spent_target_ids),
        "output_root": output_root.relative_to(repo_root).as_posix(),
        "selection_version": OPERATIONAL_SELECTION_VERSION,
        "spent_selection_sha256": spent_sha256,
        "strata_counts": {
            stratum: sum(item["stratum"] == stratum for item in cases)
            for stratum in STRATA
        },
        "strategy_2_count": sum(item["strategy"] == 2 for item in cases),
    }


def _ngram_hash_hits(
    workshop_text: str, sources: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    workshop_tokens = tokenize_text(workshop_text, label="workshop")
    if len(workshop_tokens) < WORKSHOP_NGRAM_TOKENS:
        return []
    workshop_ngrams = {
        tuple(workshop_tokens[index : index + WORKSHOP_NGRAM_TOKENS])
        for index in range(len(workshop_tokens) - WORKSHOP_NGRAM_TOKENS + 1)
    }
    hits: list[dict[str, Any]] = []
    for label, source_text in sources:
        source_tokens = tokenize_text(source_text, label=label)
        for index in range(len(source_tokens) - WORKSHOP_NGRAM_TOKENS + 1):
            ngram = tuple(source_tokens[index : index + WORKSHOP_NGRAM_TOKENS])
            if ngram in workshop_ngrams:
                hits.append(
                    {
                        "ngram_sha256": sha256_bytes(" ".join(ngram).encode("utf-8")),
                        "source": label,
                        "source_token_offset": index,
                    }
                )
    return hits


def validate_workshop_bytes(
    data: bytes,
    *,
    target_id: str,
    target_row: dict[str, str],
    reference_rows: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_WORKSHOP", "Workshop is not valid UTF-8", offset=exc.start)
    failures: list[dict[str, Any]] = []
    if unicodedata.normalize("NFC", text) != text:
        failures.append({"rule_id": "WORKSHOP-CANONICAL-NFC", "reason": "non-NFC"})
    if "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
        failures.append(
            {"rule_id": "WORKSHOP-CANONICAL-LF", "reason": "non-canonical newline"}
        )
    if any(line.endswith((" ", "\t")) for line in text.splitlines()):
        failures.append(
            {
                "rule_id": "WORKSHOP-CANONICAL-WHITESPACE",
                "reason": "trailing line whitespace",
            }
        )
    match = WORKSHOP_PATTERN.fullmatch(text)
    if match is None:
        failures.append({"rule_id": "WORKSHOP-SCHEMA-001", "reason": "schema mismatch"})
        sections = None
    else:
        sections = {
            "abstract": match.group(4),
            "keywords": match.group(2),
            "title": match.group(1),
            "tldr": match.group(3),
        }
        if any(not value.strip() for value in sections.values()):
            failures.append(
                {"rule_id": "WORKSHOP-SCHEMA-002", "reason": "empty section"}
            )
        keywords = [value.strip() for value in sections["keywords"].split(",")]
        if len(keywords) < 2 or any(not value for value in keywords):
            failures.append(
                {"rule_id": "WORKSHOP-SCHEMA-003", "reason": "invalid keywords"}
            )
        if re.search(r"(?m)^#{1,6}(?:\s|$)", sections["abstract"]):
            failures.append(
                {"rule_id": "WORKSHOP-SCHEMA-004", "reason": "extra section"}
            )

    normalized_workshop = normalize_text(text, label="workshop")
    normalized_title = normalize_text(target_row["title"], label="target.title")
    if normalized_title and normalized_title in normalized_workshop:
        failures.append(
            {"rule_id": "WORKSHOP-IDENTITY-TITLE", "reason": "exact target title"}
        )
    identifiers = [target_id]
    identifiers.extend(
        str(value)
        for value in _literal(
            target_row["externalIds"], label="target.externalIds", expected=dict
        ).values()
    )
    for identifier in identifiers:
        if identifier and identifier.casefold() in text.casefold():
            failures.append(
                {
                    "identifier_sha256": sha256_bytes(identifier.encode("utf-8")),
                    "rule_id": "WORKSHOP-IDENTITY-ID",
                    "reason": "target identifier",
                }
            )
    if URL_PATTERN.search(text):
        failures.append({"rule_id": "WORKSHOP-IDENTITY-URL", "reason": "URL"})
    if DOI_PATTERN.search(text):
        failures.append({"rule_id": "WORKSHOP-IDENTITY-DOI", "reason": "DOI"})
    if PAPER_ID_PATTERN.search(text):
        failures.append({"rule_id": "WORKSHOP-IDENTITY-PAPER", "reason": "paper ID"})

    sources = [
        ("target.raw_abstract", target_row["abstract"]),
        ("target.abstract_summary", target_row["abstract_summary"]),
    ]
    for row_index, row in enumerate(reference_rows):
        contexts = _literal(
            row["contexts"], label=f"reference[{row_index}].contexts", expected=list
        )
        sources.extend(
            (f"reference[{row_index}].context[{context_index}]", context)
            for context_index, context in enumerate(contexts)
            if isinstance(context, str) and context
        )
    ngram_hits = _ngram_hash_hits(text, sources)
    if ngram_hits:
        failures.append(
            {
                "hit_count": len(ngram_hits),
                "hits": ngram_hits,
                "rule_id": "WORKSHOP-LEAKAGE-NGRAM",
                "reason": f"shared consecutive {WORKSHOP_NGRAM_TOKENS}-token span",
            }
        )
    status = "pass" if not failures else "fail"
    return {
        "canonical_sha256": sha256_bytes(data),
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "deterministic_status": status,
        "failures": failures,
        "lengths": (
            None
            if sections is None
            else {
                "abstract_chars": len(sections["abstract"]),
                "full_chars": len(text),
                "keywords_chars": len(sections["keywords"]),
                "title_chars": len(sections["title"]),
                "tldr_chars": len(sections["tldr"]),
            }
        ),
        "semantic_review_status": "pending_independent_review",
        "validator_version": WORKSHOP_VALIDATOR_VERSION,
    }


def validate_workshops(
    repo_root: Path,
    raw_root: Path,
    preparation_root: Path,
    draft_set: str,
) -> dict[str, Any]:
    source = load_source_data(raw_root)
    selection_path = preparation_root / "selection-manifest.json"
    if not selection_path.is_file():
        fail("MISSING_ARTIFACT", "selection-manifest.json is missing")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("selection_version") not in {
        SELECTION_VERSION,
        OPERATIONAL_SELECTION_VERSION,
    }:
        fail("UNSUPPORTED_SCHEMA", "Selection manifest version does not match")
    draft_root = preparation_root / "workshops" / draft_set
    validation_root = preparation_root / "workshop-validations" / draft_set
    reports: list[dict[str, Any]] = []
    review_sections: list[str] = [
        "# Workshop semantic review packet",
        "",
        "This private packet exposes Target title/abstract only to the independent reviewer. ",
        "For every case, review target relevance, answer leakage, multiple-answer breadth, and identity risk.",
        "",
    ]
    for case in selection["cases"]:
        case_id = case["case_id"]
        target_id = case["target_paper_id"]
        draft_path = draft_root / f"{case_id}.md"
        if not draft_path.is_file():
            fail("MISSING_ARTIFACT", "Workshop draft is missing", case_id=case_id)
        data = draft_path.read_bytes()
        report = validate_workshop_bytes(
            data,
            target_id=target_id,
            target_row=source.target_rows[target_id],
            reference_rows=source.references_by_target[target_id],
        )
        report["case_id"] = case_id
        report["draft_path"] = draft_path.relative_to(repo_root).as_posix()
        report_path = validation_root / f"{case_id}.json"
        write_json_once(report_path, report)
        reports.append(report)
        target = source.target_rows[target_id]
        review_sections.extend(
            [
                f"## {case_id}",
                "",
                "### Private Target title",
                "",
                target["title"],
                "",
                "### Private Target abstract",
                "",
                target["abstract"],
                "",
                "### Workshop draft",
                "",
                data.decode("utf-8").rstrip("\n"),
                "",
                f"Deterministic validation: **{report['deterministic_status']}**",
                "",
                "- [ ] Relevant to the target problem without stating the target answer",
                "- [ ] Allows multiple materially different method families",
                "- [ ] Contains no method, mechanism, design, result, or conclusion leakage",
                "- [ ] Contains no identifying or near-identifying phrasing",
                "",
                "Reviewer verdict: `pending`",
                "",
            ]
        )

    review_packet = "\n".join(review_sections).rstrip() + "\n"
    write_once(validation_root / "semantic-review.md", review_packet.encode("utf-8"))
    deterministic_failures = sum(
        report["deterministic_status"] != "pass" for report in reports
    )
    manifest = {
        "approval_status": (
            "blocked_by_deterministic_validation"
            if deterministic_failures
            else "pending_independent_semantic_review"
        ),
        "case_count": len(reports),
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "deterministic_failure_count": deterministic_failures,
        "draft_set": draft_set,
        "reports": [
            {
                "case_id": report["case_id"],
                "draft_sha256": report["canonical_sha256"],
                "status": report["deterministic_status"],
                "validation_report_sha256": sha256_bytes(
                    (validation_root / f"{report['case_id']}.json").read_bytes()
                ),
            }
            for report in reports
        ],
        "review_packet_sha256": sha256_bytes(
            (validation_root / "semantic-review.md").read_bytes()
        ),
        "validator_version": WORKSHOP_VALIDATOR_VERSION,
    }
    write_json_once(validation_root / "workshop-manifest.json", manifest)
    return {
        "approval_status": manifest["approval_status"],
        "case_count": len(reports),
        "deterministic_failure_count": deterministic_failures,
        "review_packet": (validation_root / "semantic-review.md")
        .relative_to(repo_root)
        .as_posix(),
        "validation_root": validation_root.relative_to(repo_root).as_posix(),
    }


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        fail("MISSING_ARTIFACT", f"{label} is missing", path=str(path))
    data = path.read_bytes()
    try:
        value = json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", f"{label} is not valid UTF-8", offset=exc.start)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_JSON",
            f"{label} is not valid JSON",
            line=exc.lineno,
            column=exc.colno,
        )
    if not isinstance(value, dict):
        fail("INVALID_REVIEW", f"{label} must be a JSON object")
    return value, data


def _require_exact_keys(
    value: dict[str, Any], expected: set[str], *, label: str
) -> None:
    actual = set(value)
    if actual != expected:
        fail(
            "INVALID_REVIEW",
            f"{label} has unexpected keys",
            missing=sorted(expected - actual),
            unknown=sorted(actual - expected),
        )


def _repo_relative(path: Path, repo_root: Path, *, label: str) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(repo_root):
        fail("PATH_ESCAPE", f"{label} must stay inside the repository")
    return resolved.relative_to(repo_root).as_posix()


def _validate_review_decision(
    decision: dict[str, Any],
    *,
    approval_id: str,
    case_ids: list[str],
    protocol_path: str,
    protocol_sha256: str,
    protocol_version: str,
    selection_sha256: str,
) -> dict[str, dict[str, Any]]:
    _require_exact_keys(
        decision,
        {
            "approval_id",
            "approved_on",
            "authority",
            "case_reviews",
            "corpus_policy",
            "protocol",
            "schema_version",
            "selection",
        },
        label="decision record",
    )
    if decision["schema_version"] != INPUT_REVIEW_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Decision record schema version does not match")
    if decision["approval_id"] != approval_id:
        fail("INVALID_REVIEW", "Decision approval_id does not match the command")
    if not isinstance(decision["approved_on"], str) or not decision["approved_on"]:
        fail("INVALID_REVIEW", "approved_on must be a non-empty string")

    authority = decision["authority"]
    if not isinstance(authority, dict):
        fail("INVALID_REVIEW", "authority must be an object")
    _require_exact_keys(
        authority,
        {"decision_actor", "delegated_by", "delegation_text", "review_method"},
        label="authority",
    )
    if any(not isinstance(value, str) or not value for value in authority.values()):
        fail("INVALID_REVIEW", "authority values must be non-empty strings")

    protocol = decision["protocol"]
    if not isinstance(protocol, dict):
        fail("INVALID_REVIEW", "protocol must be an object")
    _require_exact_keys(protocol, {"path", "sha256", "version"}, label="protocol")
    if (
        protocol["path"] != protocol_path
        or protocol["sha256"] != protocol_sha256
        or protocol["version"] != protocol_version
    ):
        fail("HASH_MISMATCH", "Decision does not approve the exact protocol revision")

    selection = decision["selection"]
    if not isinstance(selection, dict):
        fail("INVALID_REVIEW", "selection must be an object")
    _require_exact_keys(
        selection,
        {"rationale", "selection_manifest_sha256", "status"},
        label="selection",
    )
    if (
        selection["status"] != "approved"
        or selection["selection_manifest_sha256"] != selection_sha256
        or not isinstance(selection["rationale"], str)
        or not selection["rationale"]
    ):
        fail("APPROVAL_REQUIRED", "Case selection has not been approved exactly")

    corpus_policy = decision["corpus_policy"]
    if not isinstance(corpus_policy, dict):
        fail("INVALID_REVIEW", "corpus_policy must be an object")
    _require_exact_keys(
        corpus_policy,
        {
            "allowed_content_types",
            "conclusion_scope",
            "limitations",
            "rationale",
            "status",
            "versions",
        },
        label="corpus_policy",
    )
    expected_versions = {
        "enrichment_policy": ENRICHMENT_POLICY_VERSION,
        "normalization": CORPUS_NORMALIZATION_VERSION,
        "schema": CORPUS_SCHEMA_VERSION,
        "validator": CORPUS_VALIDATOR_VERSION,
    }
    if (
        corpus_policy["status"] != "approved"
        or corpus_policy["allowed_content_types"] != ["publisher_abstract"]
        or corpus_policy["conclusion_scope"] != "abstract_level_local_paper_ranking"
        or corpus_policy["versions"] != expected_versions
        or not isinstance(corpus_policy["rationale"], str)
        or not corpus_policy["rationale"]
        or not isinstance(corpus_policy["limitations"], list)
        or not corpus_policy["limitations"]
        or any(
            not isinstance(item, str) or not item
            for item in corpus_policy["limitations"]
        )
    ):
        fail("APPROVAL_REQUIRED", "Abstract-only corpus policy is not fully approved")

    reviews = decision["case_reviews"]
    if not isinstance(reviews, list):
        fail("INVALID_REVIEW", "case_reviews must be an array")
    by_case: dict[str, dict[str, Any]] = {}
    expected_checks = {
        "multiple_method_families",
        "no_answer_leakage",
        "no_identity_leakage",
        "target_relevance",
    }
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            fail("INVALID_REVIEW", "A case review must be an object", index=index)
        _require_exact_keys(
            review,
            {"case_id", "checks", "rationale", "status"},
            label=f"case_reviews[{index}]",
        )
        case_id = review["case_id"]
        checks = review["checks"]
        if not isinstance(case_id, str) or case_id in by_case:
            fail("INVALID_REVIEW", "Case review identities must be unique")
        if not isinstance(checks, dict):
            fail("INVALID_REVIEW", "Case review checks must be an object")
        _require_exact_keys(checks, expected_checks, label=f"{case_id}.checks")
        if (
            review["status"] != "approved"
            or any(checks[key] is not True for key in expected_checks)
            or not isinstance(review["rationale"], str)
            or not review["rationale"]
        ):
            fail(
                "APPROVAL_REQUIRED", "A Workshop case is not approved", case_id=case_id
            )
        by_case[case_id] = review
    if sorted(by_case) != case_ids:
        fail(
            "APPROVAL_REQUIRED",
            "Case reviews do not match the frozen selection",
            expected=case_ids,
            actual=sorted(by_case),
        )
    return by_case


def approve_inputs(
    repo_root: Path,
    preparation_root: Path,
    draft_set: str,
    decision_path: Path,
    protocol_path: Path,
    approval_id: str,
) -> dict[str, Any]:
    if APPROVAL_ID_PATTERN.fullmatch(approval_id) is None:
        fail("INVALID_REVIEW", "approval_id has an invalid format")

    selection, selection_bytes = _read_json_object(
        preparation_root / "selection-manifest.json", label="selection manifest"
    )
    preparation, preparation_bytes = _read_json_object(
        preparation_root / "preparation-manifest.json", label="preparation manifest"
    )
    workshop_root = preparation_root / "workshops" / draft_set
    validation_root = preparation_root / "workshop-validations" / draft_set
    workshop_manifest, workshop_manifest_bytes = _read_json_object(
        validation_root / "workshop-manifest.json", label="Workshop manifest"
    )
    decision, decision_bytes = _read_json_object(
        decision_path, label="input review decision"
    )
    if not protocol_path.is_file():
        fail("MISSING_ARTIFACT", "Approved protocol is missing")
    protocol_bytes = protocol_path.read_bytes()
    protocol_sha256 = sha256_bytes(protocol_bytes)
    protocol_relative = _repo_relative(
        protocol_path, repo_root, label="approved protocol"
    )

    selection_version = selection.get("selection_version")
    if selection_version not in {
        SELECTION_VERSION,
        OPERATIONAL_SELECTION_VERSION,
    }:
        fail("UNSUPPORTED_SCHEMA", "Selection manifest version does not match")
    selection_cases = selection.get("cases")
    if not isinstance(selection_cases, list) or not selection_cases:
        fail("INVALID_REVIEW", "Selection manifest contains no cases")
    case_ids = sorted(case["case_id"] for case in selection_cases)
    if len(case_ids) != len(set(case_ids)):
        fail("INVALID_REVIEW", "Selection case IDs are not unique")
    selection_sha256 = sha256_bytes(selection_bytes)
    if preparation.get("selection_manifest_sha256") != selection_sha256:
        fail("HASH_MISMATCH", "Preparation does not reference this selection")
    if preparation.get("case_count") != len(case_ids):
        fail("HASH_MISMATCH", "Preparation case count does not match selection")

    if (
        workshop_manifest.get("approval_status")
        != "pending_independent_semantic_review"
        or workshop_manifest.get("deterministic_failure_count") != 0
        or workshop_manifest.get("case_count") != len(case_ids)
        or workshop_manifest.get("draft_set") != draft_set
        or workshop_manifest.get("validator_version") != WORKSHOP_VALIDATOR_VERSION
    ):
        fail("APPROVAL_REQUIRED", "Workshop deterministic gate has not passed")
    workshop_reports = workshop_manifest.get("reports")
    if not isinstance(workshop_reports, list):
        fail("INVALID_REVIEW", "Workshop reports must be an array")
    reports_by_case = {report.get("case_id"): report for report in workshop_reports}
    if sorted(reports_by_case) != case_ids:
        fail("HASH_MISMATCH", "Workshop reports do not match selected cases")

    _validate_review_decision(
        decision,
        approval_id=approval_id,
        case_ids=case_ids,
        protocol_path=protocol_relative,
        protocol_sha256=protocol_sha256,
        protocol_version=(
            "v1.4" if selection_version == OPERATIONAL_SELECTION_VERSION else "v1.1"
        ),
        selection_sha256=selection_sha256,
    )

    preparation_bundles = preparation.get("corpus_bundles")
    if not isinstance(preparation_bundles, list):
        fail("INVALID_REVIEW", "Preparation corpus_bundles must be an array")
    bundles_by_case = {bundle.get("case_id"): bundle for bundle in preparation_bundles}
    if sorted(bundles_by_case) != case_ids:
        fail("HASH_MISMATCH", "Corpus bundles do not match selected cases")

    approved_workshops: list[dict[str, Any]] = []
    workshop_copies: list[tuple[Path, bytes]] = []
    approved_corpora: list[dict[str, Any]] = []
    expected_versions = decision["corpus_policy"]["versions"]
    for case_id in case_ids:
        report_entry = reports_by_case[case_id]
        if report_entry.get("status") != "pass":
            fail("APPROVAL_REQUIRED", "A Workshop report did not pass", case_id=case_id)
        workshop_path = workshop_root / f"{case_id}.md"
        if not workshop_path.is_file():
            fail(
                "MISSING_ARTIFACT",
                "Approved Workshop draft is missing",
                case_id=case_id,
            )
        workshop_bytes = workshop_path.read_bytes()
        workshop_sha256 = sha256_bytes(workshop_bytes)
        if workshop_sha256 != report_entry.get("draft_sha256"):
            fail("HASH_MISMATCH", "Workshop draft hash changed", case_id=case_id)
        validation_report_path = validation_root / f"{case_id}.json"
        validation_report_bytes = validation_report_path.read_bytes()
        if sha256_bytes(validation_report_bytes) != report_entry.get(
            "validation_report_sha256"
        ):
            fail("HASH_MISMATCH", "Workshop validation hash changed", case_id=case_id)
        approved_workshops.append(
            {
                "case_id": case_id,
                "draft_sha256": workshop_sha256,
                "source_validation_report_sha256": sha256_bytes(
                    validation_report_bytes
                ),
            }
        )
        workshop_copies.append((Path("workshops") / f"{case_id}.md", workshop_bytes))

        bundle_entry = bundles_by_case[case_id]
        bundle_root = preparation_root / "corpora" / case_id
        bundle_manifest, bundle_manifest_bytes = _read_json_object(
            bundle_root / "bundle-manifest.json", label=f"{case_id} bundle manifest"
        )
        corpus, corpus_bytes = _read_json_object(
            bundle_root / "corpus.json", label=f"{case_id} corpus"
        )
        corpus_report, corpus_report_bytes = _read_json_object(
            bundle_root / "validation-report.json", label=f"{case_id} corpus report"
        )
        if (
            sha256_bytes(bundle_manifest_bytes) != bundle_entry.get("manifest_sha256")
            or sha256_bytes(corpus_bytes) != bundle_entry.get("corpus_sha256")
            or sha256_bytes(corpus_report_bytes)
            != bundle_entry.get("validation_report_sha256")
        ):
            fail("HASH_MISMATCH", "A corpus bundle hash changed", case_id=case_id)
        if (
            bundle_manifest.get("approval_status") != "pending_robert_approval"
            or bundle_manifest.get("versions") != expected_versions
            or corpus_report.get("status") != "pass"
            or corpus_report.get("error_count") != 0
            or corpus_report.get("validator_version") != CORPUS_VALIDATOR_VERSION
        ):
            fail(
                "APPROVAL_REQUIRED",
                "A corpus bundle is not approvable",
                case_id=case_id,
            )
        records = corpus.get("records")
        if not isinstance(records, list) or not records:
            fail(
                "INVALID_REVIEW", "Approved corpus contains no records", case_id=case_id
            )
        for record in records:
            content_items = (
                record.get("content_items") if isinstance(record, dict) else None
            )
            if (
                not isinstance(content_items, list)
                or len(content_items) != 1
                or not isinstance(content_items[0], dict)
                or content_items[0].get("type") != "publisher_abstract"
                or content_items[0].get("status") != "validated"
                or not isinstance(content_items[0].get("text"), str)
                or not content_items[0]["text"]
            ):
                fail(
                    "APPROVAL_REQUIRED",
                    "Approved corpus must be publisher-abstract-only",
                    case_id=case_id,
                )
        approved_corpora.append(
            {
                "bundle_content_sha256": bundle_entry["bundle_content_sha256"],
                "bundle_manifest_sha256": sha256_bytes(bundle_manifest_bytes),
                "case_id": case_id,
                "corpus_sha256": sha256_bytes(corpus_bytes),
                "record_count": len(records),
                "validation_report_sha256": sha256_bytes(corpus_report_bytes),
                "versions": expected_versions,
            }
        )

    approval_root = preparation_root / "approvals" / approval_id
    if approval_root.exists():
        fail(
            "ARTIFACT_EXISTS",
            "Immutable input approval already exists",
            path=str(approval_root),
        )
    query_packet_root = approval_root / "query-author-packet"
    for relative_path, workshop_bytes in workshop_copies:
        write_once(query_packet_root / relative_path, workshop_bytes)
    query_packet_manifest = {
        "approval_id": approval_id,
        "case_count": len(case_ids),
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "draft_set": draft_set,
        "notice": (
            "Query author may read only this packet. Target authoring input, corpus/reference "
            "content, qrels, and ranker output remain forbidden."
        ),
        "schema_version": INPUT_APPROVAL_SCHEMA_VERSION,
        "workshops": [
            {
                "case_id": item["case_id"],
                "path": f"workshops/{item['case_id']}.md",
                "sha256": item["draft_sha256"],
            }
            for item in approved_workshops
        ],
    }
    query_manifest_path = query_packet_root / "manifest.json"
    write_json_once(query_manifest_path, query_packet_manifest)
    query_manifest_sha256 = sha256_bytes(query_manifest_path.read_bytes())

    approved_workshops_document = {
        "approval_id": approval_id,
        "case_count": len(case_ids),
        "draft_set": draft_set,
        "schema_version": INPUT_APPROVAL_SCHEMA_VERSION,
        "source_workshop_manifest_sha256": sha256_bytes(workshop_manifest_bytes),
        "workshops": approved_workshops,
    }
    approved_workshops_path = approval_root / "approved-workshops.json"
    write_json_once(approved_workshops_path, approved_workshops_document)
    approved_corpora_document = {
        "approval_id": approval_id,
        "case_count": len(case_ids),
        "content_profile": "title-and-publisher-abstract-only",
        "corpora": approved_corpora,
        "schema_version": INPUT_APPROVAL_SCHEMA_VERSION,
    }
    approved_corpora_path = approval_root / "approved-corpora.json"
    write_json_once(approved_corpora_path, approved_corpora_document)

    approval_manifest = {
        "approval_id": approval_id,
        "approval_status": "approved",
        "approved_on": decision["approved_on"],
        "artifacts": {
            "approved-corpora.json": sha256_bytes(approved_corpora_path.read_bytes()),
            "approved-workshops.json": sha256_bytes(
                approved_workshops_path.read_bytes()
            ),
            "query-author-packet/manifest.json": query_manifest_sha256,
        },
        "authority": decision["authority"],
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "content_profile": "title-and-publisher-abstract-only",
        "decision_record": {
            "path": _repo_relative(decision_path, repo_root, label="decision record"),
            "sha256": sha256_bytes(decision_bytes),
        },
        "preparation": {
            "preparation_manifest_sha256": sha256_bytes(preparation_bytes),
            "selection_manifest_sha256": selection_sha256,
            "workshop_manifest_sha256": sha256_bytes(workshop_manifest_bytes),
        },
        "protocol": decision["protocol"],
        "schema_version": INPUT_APPROVAL_SCHEMA_VERSION,
    }
    approval_manifest_path = approval_root / "approval-manifest.json"
    write_json_once(approval_manifest_path, approval_manifest)
    return {
        "approval_id": approval_id,
        "approval_manifest": _repo_relative(
            approval_manifest_path, repo_root, label="approval manifest"
        ),
        "approval_manifest_sha256": sha256_bytes(approval_manifest_path.read_bytes()),
        "approval_status": "approved",
        "case_count": len(case_ids),
        "query_author_packet": _repo_relative(
            query_packet_root, repo_root, label="query author packet"
        ),
        "query_author_packet_manifest_sha256": query_manifest_sha256,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare private approved-input candidates for ranking comparison"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--raw-root", default="data/raw")
    prepare.add_argument("--output-root", required=True)
    operational = subparsers.add_parser("prepare-operational")
    operational.add_argument("--raw-root", default="data/raw")
    operational.add_argument("--output-root", required=True)
    operational.add_argument("--spent-selection", required=True)
    validate = subparsers.add_parser("validate-workshops")
    validate.add_argument("--raw-root", default="data/raw")
    validate.add_argument("--preparation-root", required=True)
    validate.add_argument("--draft-set", required=True)
    approve = subparsers.add_parser("approve")
    approve.add_argument("--preparation-root", required=True)
    approve.add_argument("--draft-set", required=True)
    approve.add_argument("--decision-record", required=True)
    approve.add_argument("--protocol", required=True)
    approve.add_argument("--approval-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    failure_root: Path | None = None
    try:
        if args.command in {"prepare", "prepare-operational"}:
            raw_root = resolve_repo_relative(repo_root, args.raw_root, label="raw-root")
            output_root = resolve_repo_relative(
                repo_root, args.output_root, label="output-root"
            )
            failure_root = output_root
            allowed_root = (repo_root / "artifacts/local-ranking-prototype").resolve()
            if not output_root.is_relative_to(allowed_root):
                fail(
                    "INVALID_PATH",
                    "Preparation output must stay under artifacts/local-ranking-prototype",
                )
            if args.command == "prepare-operational":
                spent_selection_path = resolve_repo_relative(
                    repo_root,
                    args.spent_selection,
                    label="spent-selection",
                )
                result = prepare_operational_inputs(
                    repo_root,
                    raw_root,
                    output_root,
                    spent_selection_path,
                )
            else:
                result = prepare_inputs(repo_root, raw_root, output_root)
        elif args.command == "validate-workshops":
            raw_root = resolve_repo_relative(repo_root, args.raw_root, label="raw-root")
            preparation_root = resolve_repo_relative(
                repo_root, args.preparation_root, label="preparation-root"
            )
            result = validate_workshops(
                repo_root, raw_root, preparation_root, args.draft_set
            )
        else:
            preparation_root = resolve_repo_relative(
                repo_root, args.preparation_root, label="preparation-root"
            )
            decision_path = resolve_repo_relative(
                repo_root, args.decision_record, label="decision-record"
            )
            protocol_path = resolve_repo_relative(
                repo_root, args.protocol, label="protocol"
            )
            allowed_root = (repo_root / "artifacts/local-ranking-prototype").resolve()
            if not preparation_root.is_relative_to(allowed_root):
                fail(
                    "INVALID_PATH",
                    "Preparation root must stay under artifacts/local-ranking-prototype",
                )
            result = approve_inputs(
                repo_root,
                preparation_root,
                args.draft_set,
                decision_path,
                protocol_path,
                args.approval_id,
            )
    except HarnessError as exc:
        if failure_root is not None:
            try:
                write_json_once(
                    failure_root / "failure.json",
                    {"error": exc.as_dict(), "status": "failed"},
                )
            except HarnessError:
                pass
        print(json.dumps({"error": exc.as_dict(), "status": "failed"}, sort_keys=True))
        return 2
    print(json.dumps({"result": result, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
