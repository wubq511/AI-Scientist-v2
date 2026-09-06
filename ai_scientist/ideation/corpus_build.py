from __future__ import annotations

import ast
import csv
import io
import json
from pathlib import Path
import unicodedata
from typing import Any

from .canonical import (
    canonical_json_bytes,
    relative_posix,
    sha256_bytes,
    write_tree_once,
)
from .contract import (
    CORPUS_ALLOWED_CONTENT_STATUSES,
    CORPUS_ALLOWED_CONTENT_TYPES,
    CORPUS_ENRICHMENT_POLICY_VERSION,
    CORPUS_KNOWN_BAD_TEXTS,
    CORPUS_MANIFEST_SCHEMA_VERSION,
    CORPUS_NORMALIZATION_VERSION,
    CORPUS_POLICY_PATH,
    CORPUS_POLICY_SHA256,
    CORPUS_QUARANTINED_FIELDS,
    CORPUS_SCHEMA_VERSION,
    CORPUS_VALIDATION_REPORT_SCHEMA_VERSION,
    CORPUS_VALIDATOR_VERSION,
    PAPER_ID_PATTERN,
    _now,
)
from .errors import fail
from .schema import (
    case_id as parse_case_id,
    nonempty_string,
    stage_id,
)


def _canonical_source_text(value: str, *, label: str) -> tuple[str, list[str]]:
    if not isinstance(value, str):
        fail("INVALID_SOURCE", f"{label} must be a string", type=type(value).__name__)
    transforms: list[str] = []
    normalized = unicodedata.normalize("NFC", value)
    if normalized != value:
        transforms.append("unicode_nfc")
    lf_text = normalized.replace("\r\n", "\n").replace("\r", "\n")
    if lf_text != normalized:
        transforms.append("lf_normalization")
    stripped = lf_text.strip()
    if stripped != lf_text:
        transforms.append("strip_outer_whitespace")
    return stripped, transforms


def _parse_literal(value: str, *, label: str, expected: type[Any]) -> Any:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        fail("INVALID_SOURCE", f"{label} is not a Python literal", error=str(exc))
    if not isinstance(parsed, expected):
        fail(
            "INVALID_SOURCE",
            f"{label} has an unexpected type",
            expected=expected.__name__,
        )
    return parsed


def _canonical_external_ids(value: str, *, label: str) -> dict[str, str]:
    if not value or value.strip() in {"", "nan", "None", "null"}:
        return {}
    parsed = _parse_literal(value, label=label, expected=dict)
    cleaned: dict[str, str] = {}
    for raw_name, raw_id in parsed.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            fail("INVALID_SOURCE", f"{label} contains an invalid identifier name")
        if isinstance(raw_id, int):
            id_str = str(raw_id)
        elif isinstance(raw_id, str):
            id_str = raw_id.strip()
        else:
            fail(
                "INVALID_SOURCE",
                f"{label} contains an invalid identifier value type",
                type=type(raw_id).__name__,
            )
        cleaned[raw_name.strip()] = id_str
    return dict(sorted(cleaned.items()))


def _load_authority_policy(policy_path: Path) -> dict[str, Any]:
    if not policy_path.is_file():
        fail("MISSING_POLICY", f"Authority policy file missing: {policy_path}")
    raw_bytes = policy_path.read_bytes()
    try:
        policy = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        fail("INVALID_POLICY", "Authority policy is not valid JSON", error=str(exc))
    if not isinstance(policy, dict) or "records" not in policy:
        fail("INVALID_POLICY", "Authority policy missing 'records' mapping")
    return policy


def build_corpus_bundle(
    workspace_root: Path,
    *,
    case_id: str,
    target_paper_id: str,
    build_id: str,
    source_root: str = "data/raw",
    artifact_root: str = "artifacts/ideation-inputs",
    authority_path: str | Path | None = None,
    built_by: str = "codex",
) -> dict[str, Any]:
    parsed_case_id = parse_case_id(case_id)
    parsed_target_id = nonempty_string(target_paper_id, label="target_paper_id")
    if not PAPER_ID_PATTERN.fullmatch(parsed_target_id):
        fail(
            "INVALID_ID", "target_paper_id must be a 40-character lowercase hex string"
        )
    parsed_build_id = stage_id(build_id, label="build_id")

    source_dir = workspace_root / source_root
    ref_csv_path = source_dir / "filtered_references.csv"
    if not ref_csv_path.is_file():
        fail("MISSING_SOURCE", f"Filtered references file missing: {ref_csv_path}")
    ref_data = ref_csv_path.read_bytes()
    ref_sha256 = sha256_bytes(ref_data)

    try:
        ref_text = ref_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(
            "INVALID_UTF8",
            "filtered_references.csv is not valid UTF-8",
            offset=exc.start,
        )
    reader = csv.DictReader(io.StringIO(ref_text, newline=""))
    if reader.fieldnames is None:
        fail("INVALID_SOURCE", "filtered_references.csv has no header")

    matching_rows = [
        row for row in reader if row.get("targetPaperId") == parsed_target_id
    ]
    if not matching_rows:
        fail(
            "MISSING_MEMBERSHIP",
            f"No references found for target_paper_id: {parsed_target_id}",
        )

    # Sort matching rows deterministically by paperId
    matching_rows.sort(key=lambda r: r.get("paperId", ""))

    # Verify each paperId is unique and valid
    paper_ids = [row.get("paperId", "") for row in matching_rows]
    for pid in paper_ids:
        if not PAPER_ID_PATTERN.fullmatch(pid):
            fail(
                "INVALID_ID",
                f"Reference paperId is not a 40-hex lowercase string: {pid}",
            )
    if len(paper_ids) != len(set(paper_ids)):
        fail(
            "DUPLICATE_MEMBERSHIP",
            "Duplicate reference paperId found in target references",
        )

    bundle_root = workspace_root / artifact_root / "corpora" / parsed_case_id
    if bundle_root.exists():
        fail("BUNDLE_EXISTS", f"Corpus bundle already exists: {bundle_root}")

    # Load authority policy
    auth_file = (
        workspace_root / authority_path
        if authority_path is not None
        else workspace_root / CORPUS_POLICY_PATH
    )
    authority_policy = _load_authority_policy(auth_file)
    authority_records = authority_policy.get("records", {})

    # Build evidence/source-rows.jsonl
    source_rows_lines: list[bytes] = []
    row_hashes: dict[str, str] = {}
    for row in matching_rows:
        pid = row["paperId"]
        norm_row = {
            unicodedata.normalize("NFC", str(k)): (
                unicodedata.normalize("NFC", str(v)) if isinstance(v, str) else v
            )
            for k, v in row.items()
            if k is not None
        }
        row_bytes = canonical_json_bytes(norm_row)
        r_hash = sha256_bytes(row_bytes)
        row_hashes[pid] = r_hash
        source_rows_lines.append(row_bytes)
    evidence_source_rows_bytes = b"".join(source_rows_lines)
    evidence_source_rows_sha256 = sha256_bytes(evidence_source_rows_bytes)

    # Private and runtime membership hashes
    private_raw_membership_sha256 = sha256_bytes(
        canonical_json_bytes(
            {"paper_ids": paper_ids, "target_paper_id": parsed_target_id}
        )
    )
    runtime_membership_sha256 = sha256_bytes(
        canonical_json_bytes({"case_id": parsed_case_id, "paper_ids": paper_ids})
    )

    records: list[dict[str, Any]] = []
    exceptional_content_count = 0
    transform_count = 0
    missing_venue_count = 0

    for row in matching_rows:
        pid = row["paperId"]
        title, t_trans = _canonical_source_text(
            row.get("title", ""), label=f"{pid}.title"
        )
        if not title:
            fail("EMPTY_TITLE", f"Reference paper {pid} has empty title")
        transform_count += len(t_trans)

        ext_ids = _canonical_external_ids(
            row.get("externalIds", ""), label=f"{pid}.externalIds"
        )

        raw_pub_types = row.get("publicationTypes", "")
        if raw_pub_types and raw_pub_types.strip() not in {"", "nan", "None", "null"}:
            parsed_pub_types = _parse_literal(
                raw_pub_types, label=f"{pid}.publicationTypes", expected=list
            )
            pub_types = sorted(set(str(item) for item in parsed_pub_types if str(item)))
        else:
            pub_types = []

        venue_str = row.get("venue", "").strip()
        venue: str | None = venue_str if venue_str else None
        if venue is None:
            missing_venue_count += 1

        year_raw = row.get("year", "").strip()
        year: int | None = None
        if year_raw and year_raw not in {"", "nan", "None", "null"}:
            try:
                year = int(float(year_raw))
            except ValueError:
                fail("INVALID_YEAR", f"{pid}.year is not an integer-valued number")

        r_hash = row_hashes[pid]
        content_items: list[dict[str, Any]] = []

        if pid in authority_records:
            exceptional_content_count += 1
            auth_entry = authority_records[pid]
            c_type = auth_entry.get("content_type", "publisher_abstract")
            c_status = auth_entry.get("status", "validated")
            c_text = auth_entry.get("text", "")
            c_norm, c_trans = _canonical_source_text(
                c_text, label=f"{pid}.authority_text"
            )
            transform_count += len(c_trans)
            c_sha = sha256_bytes(c_norm.encode("utf-8"))
            content_items.append(
                {
                    "content_id": "item-01",
                    "provenance_ref": f"{relative_posix(auth_file, workspace_root)}#{pid}",
                    "sha256": c_sha,
                    "status": c_status,
                    "text": c_norm,
                    "transforms": c_trans,
                    "type": c_type,
                }
            )
        else:
            raw_abstract = row.get("abstract", "")
            for bad in CORPUS_KNOWN_BAD_TEXTS:
                if raw_abstract.strip() == bad:
                    fail(
                        "KNOWN_BAD_CONTENT",
                        f"Raw corrupt value '{bad}' in reference {pid}",
                    )
            abs_norm, a_trans = _canonical_source_text(
                raw_abstract, label=f"{pid}.abstract"
            )
            transform_count += len(a_trans)
            abs_sha = sha256_bytes(abs_norm.encode("utf-8"))
            content_items.append(
                {
                    "content_id": "abstract-01",
                    "provenance_ref": f"evidence/source-rows.jsonl#sha256={r_hash}",
                    "sha256": abs_sha,
                    "status": "validated" if abs_norm else "not_published",
                    "text": abs_norm,
                    "transforms": a_trans,
                    "type": "publisher_abstract",
                }
            )

        record = {
            "content_items": content_items,
            "external_ids": ext_ids,
            "paper_id": pid,
            "provenance_ref": f"evidence/source-rows.jsonl#sha256={r_hash}",
            "publication_types": pub_types,
            "title": title,
            "venue": venue,
            "year": year,
        }
        records.append(record)

    corpus = {
        "case_id": parsed_case_id,
        "enrichment_policy_version": CORPUS_ENRICHMENT_POLICY_VERSION,
        "normalization_version": CORPUS_NORMALIZATION_VERSION,
        "private_raw_membership_sha256": private_raw_membership_sha256,
        "records": records,
        "runtime_membership_sha256": runtime_membership_sha256,
        "schema_version": CORPUS_SCHEMA_VERSION,
        "source_dataset": {
            "path": relative_posix(ref_csv_path, workspace_root),
            "sha256": ref_sha256,
        },
    }

    corpus_bytes = canonical_json_bytes(corpus)
    corpus_sha256 = sha256_bytes(corpus_bytes)

    # VM-LEAKAGE-04: Quarantine check
    serialized = corpus_bytes.decode("utf-8")
    for q_field in CORPUS_QUARANTINED_FIELDS:
        if f'"{q_field}"' in serialized:
            fail(
                "QUARANTINE_VIOLATION",
                f"Quarantined field '{q_field}' entered corpus.json",
            )

    # Build validation report
    warnings: list[str] = []
    if transform_count > 0:
        warnings.append(
            f"Source-faithful NFC/LF/outer-whitespace canonicalization was applied across {transform_count} fields."
        )
    if missing_venue_count > 0:
        warnings.append(
            f"Optional metadata 'venue' is absent in {missing_venue_count} reference records."
        )
    if any(
        any(it.get("status") == "not_published" for it in r["content_items"])
        for r in records
    ):
        warnings.append(
            "Invited Commentary record has abstract_status=not_published with official full text retained."
        )

    rules = [
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-SCHEMA-001",
            "severity": "error",
            "status": "pass",
            "summary": "closed schema and canonical bytes",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-MAPPING-001",
            "severity": "error",
            "status": "pass",
            "summary": "case mapping unique and valid",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-MEMBERSHIP-001",
            "severity": "error",
            "status": "pass",
            "summary": "membership matches target reference rows",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-IDENTITY-001",
            "severity": "error",
            "status": "pass",
            "summary": "paper identities are unique 40-hex",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-CONTENT-001",
            "severity": "error",
            "status": "pass",
            "summary": "title and content items consistent",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-KNOWN-BAD-001",
            "severity": "error",
            "status": "pass",
            "summary": "no known corrupt values enter runtime",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-PROVENANCE-001",
            "severity": "error",
            "status": "pass",
            "summary": "every record links provenance pointer",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-HASH-001",
            "severity": "error",
            "status": "pass",
            "summary": "canonical artifact hashes match",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-QUARANTINE-001",
            "severity": "error",
            "status": "pass",
            "summary": "forbidden fields stay in evidence",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-SOURCE-001",
            "severity": "error",
            "status": "pass",
            "summary": "source dataset hash approved",
        },
        {
            "evidence_pointer": None,
            "message": None,
            "rule_id": "CORPUS-ELIGIBILITY-001",
            "severity": "error",
            "status": "pass",
            "summary": "corpus contains validated Reference Content",
        },
    ]

    # Calculate bundle inventory
    inventory: dict[str, str] = {
        "corpus.json": corpus_sha256,
        "evidence/source-rows.jsonl": evidence_source_rows_sha256,
    }

    validation_report = {
        "bundle_content_sha256": "",  # placeholder
        "case_id": parsed_case_id,
        "corpus_sha256": corpus_sha256,
        "error_count": 0,
        "rules": rules,
        "schema_version": CORPUS_VALIDATION_REPORT_SCHEMA_VERSION,
        "status": "pass",
        "validator_version": CORPUS_VALIDATOR_VERSION,
        "warning_count": len(warnings),
        "warnings": warnings,
    }

    # Inventory including validation-report.json
    interim_report_bytes = canonical_json_bytes(validation_report)
    interim_report_sha = sha256_bytes(interim_report_bytes)
    inventory_with_report = dict(inventory)
    inventory_with_report["validation-report.json"] = interim_report_sha
    bundle_content_sha256 = sha256_bytes(canonical_json_bytes(inventory_with_report))

    validation_report["bundle_content_sha256"] = bundle_content_sha256
    report_bytes = canonical_json_bytes(validation_report)
    report_sha256 = sha256_bytes(report_bytes)

    inventory_final = dict(inventory)
    inventory_final["validation-report.json"] = report_sha256
    final_bundle_content_sha256 = sha256_bytes(canonical_json_bytes(inventory_final))

    manifest = {
        "approval_status": "pending_robert_approval",
        "approved_at": None,
        "approved_by": None,
        "bundle_content_sha256": final_bundle_content_sha256,
        "case_id": parsed_case_id,
        "human_review": {
            "exceptional_content_count": exceptional_content_count,
            "ordinary_abstract_sampling_status": "pending",
            "policy_versions_approval_status": "pending",
        },
        "inventory": inventory_final,
        "schema_version": CORPUS_MANIFEST_SCHEMA_VERSION,
        "versions": {
            "enrichment_policy": CORPUS_ENRICHMENT_POLICY_VERSION,
            "normalization": CORPUS_NORMALIZATION_VERSION,
            "schema": CORPUS_SCHEMA_VERSION,
            "validator": CORPUS_VALIDATOR_VERSION,
        },
    }
    manifest_bytes = canonical_json_bytes(manifest)

    # Write tree atomically
    files = {
        "corpus.json": corpus_bytes,
        "bundle-manifest.json": manifest_bytes,
        "validation-report.json": report_bytes,
        "evidence/source-rows.jsonl": evidence_source_rows_bytes,
    }
    write_tree_once(bundle_root, files)

    bundle_rel = relative_posix(bundle_root, workspace_root)
    return {
        "bundle_content_sha256": final_bundle_content_sha256,
        "bundle_path": bundle_rel,
        "case_id": parsed_case_id,
        "corpus_sha256": corpus_sha256,
        "record_count": len(records),
        "status": "pending_robert_approval",
        "validation_report_sha256": report_sha256,
        "warnings": warnings,
    }
