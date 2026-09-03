from __future__ import annotations

import json
from pathlib import Path
import unicodedata
from typing import Any

from .canonical import (
    canonical_json_bytes,
    sha256_bytes,
)
from .contract import (
    CORPUS_ALLOWED_CONTENT_STATUSES,
    CORPUS_ALLOWED_CONTENT_TYPES,
    CORPUS_KNOWN_BAD_TEXTS,
    CORPUS_QUARANTINED_FIELDS,
    CORPUS_VALIDATOR_VERSION,
    PAPER_ID_PATTERN,
)
from .schema import (
    case_id as parse_case_id,
)


def _check_canonical_bytes(data: bytes) -> tuple[bool, str | None]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False, "Not valid UTF-8"
    if unicodedata.normalize("NFC", text) != text:
        return False, "Not Unicode NFC normalized"
    if "\r" in text:
        return False, "Contains carriage return (\r)"
    if not text.endswith("\n"):
        return False, "Missing single trailing newline"
    if text.endswith("\n\n"):
        return False, "Multiple trailing newlines"
    return True, None


def validate_corpus_bundle(
    workspace_root: Path,
    *,
    bundle_path: str | Path,
) -> dict[str, Any]:
    bundle_dir = workspace_root / bundle_path
    if not bundle_dir.is_dir():
        return {
            "case_id": bundle_dir.name,
            "error_count": 1,
            "errors": [f"Bundle directory does not exist: {bundle_dir}"],
            "rules": [
                {
                    "evidence_pointer": None,
                    "message": "Bundle directory does not exist",
                    "rule_id": "CORPUS-SCHEMA-001",
                    "severity": "error",
                    "status": "fail",
                    "summary": "bundle directory exists",
                }
            ],
            "status": "fail",
            "validator_version": CORPUS_VALIDATOR_VERSION,
            "warning_count": 0,
            "warnings": [],
        }

    rules: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    def add_rule(
        rule_id: str,
        summary: str,
        passed: bool,
        message: str | None = None,
        severity: str = "error",
    ) -> None:
        rules.append(
            {
                "evidence_pointer": None,
                "message": None if passed else message,
                "rule_id": rule_id,
                "severity": severity,
                "status": "pass" if passed else "fail",
                "summary": summary,
            }
        )
        if not passed:
            if severity == "error":
                errors.append(f"[{rule_id}] {message or summary}")
            else:
                warnings.append(f"[{rule_id}] {message or summary}")

    manifest_file = bundle_dir / "bundle-manifest.json"
    corpus_file = bundle_dir / "corpus.json"
    source_rows_file = bundle_dir / "evidence/source-rows.jsonl"

    if not manifest_file.is_file():
        add_rule(
            "CORPUS-SCHEMA-001",
            "bundle-manifest.json missing",
            False,
            "Missing manifest file",
        )
        return {
            "case_id": bundle_dir.name,
            "error_count": len(errors),
            "errors": errors,
            "rules": rules,
            "status": "fail",
            "validator_version": CORPUS_VALIDATOR_VERSION,
            "warning_count": len(warnings),
            "warnings": warnings,
        }

    manifest_bytes = manifest_file.read_bytes()
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        add_rule(
            "CORPUS-SCHEMA-001", "bundle-manifest.json parse error", False, str(exc)
        )
        return {
            "case_id": bundle_dir.name,
            "error_count": len(errors),
            "errors": errors,
            "rules": rules,
            "status": "fail",
            "validator_version": CORPUS_VALIDATOR_VERSION,
            "warning_count": len(warnings),
            "warnings": warnings,
        }

    if not corpus_file.is_file():
        add_rule(
            "CORPUS-SCHEMA-001", "corpus.json missing", False, "Missing corpus.json"
        )
        return {
            "case_id": bundle_dir.name,
            "error_count": len(errors),
            "errors": errors,
            "rules": rules,
            "status": "fail",
            "validator_version": CORPUS_VALIDATOR_VERSION,
            "warning_count": len(warnings),
            "warnings": warnings,
        }

    corpus_bytes = corpus_file.read_bytes()
    actual_corpus_sha = sha256_bytes(corpus_bytes)

    # 1. CORPUS-SCHEMA-001: canonical bytes & closed schema
    is_canonical, canon_err = _check_canonical_bytes(corpus_bytes)
    schema_ok = True
    schema_err = None
    try:
        corpus = json.loads(corpus_bytes.decode("utf-8"))
        if not isinstance(corpus, dict):
            schema_ok = False
            schema_err = "corpus.json must be a JSON object"
        else:
            allowed_top_keys = {
                "case_id",
                "enrichment_policy_version",
                "normalization_version",
                "private_raw_membership_sha256",
                "records",
                "runtime_membership_sha256",
                "schema_version",
                "source_dataset",
            }
            if set(corpus.keys()) != allowed_top_keys:
                schema_ok = False
                schema_err = f"Keys mismatch. Extra: {set(corpus.keys()) - allowed_top_keys}, Missing: {allowed_top_keys - set(corpus.keys())}"
            elif canonical_json_bytes(corpus) != corpus_bytes:
                schema_ok = False
                schema_err = "corpus.json does not match canonical JSON byte encoding (keys/records not sorted or wrong formatting)"
    except Exception as exc:
        schema_ok = False
        schema_err = f"JSON parse error: {exc}"

    # Evaluate quarantine check first
    serialized_corpus = corpus_bytes.decode("utf-8", errors="replace")
    quarantine_ok = True
    quarantine_msg = None
    for q_field in CORPUS_QUARANTINED_FIELDS:
        if f'"{q_field}"' in serialized_corpus:
            quarantine_ok = False
            quarantine_msg = f"Quarantined field '{q_field}' detected in corpus.json"
            break
    add_rule(
        "CORPUS-QUARANTINE-001",
        "forbidden fields stay in evidence",
        quarantine_ok,
        quarantine_msg,
    )

    if is_canonical and schema_ok:
        add_rule("CORPUS-SCHEMA-001", "closed schema and canonical bytes", True)
    else:
        add_rule(
            "CORPUS-SCHEMA-001",
            "closed schema and canonical bytes",
            False,
            canon_err or schema_err,
        )

    if not isinstance(corpus, dict):
        return {
            "case_id": bundle_dir.name,
            "error_count": len(errors),
            "errors": errors,
            "rules": rules,
            "status": "fail",
            "validator_version": CORPUS_VALIDATOR_VERSION,
            "warning_count": len(warnings),
            "warnings": warnings,
        }

    # 2. CORPUS-MAPPING-001: Case ID mapping
    case_id_val = corpus.get("case_id", "")
    manifest_case_id = manifest.get("case_id", "")
    mapping_ok = True
    try:
        parse_case_id(case_id_val)
    except Exception:
        mapping_ok = False
    if case_id_val != manifest_case_id or case_id_val != bundle_dir.name:
        mapping_ok = False
    add_rule(
        "CORPUS-MAPPING-001",
        "case mapping unique and valid",
        mapping_ok,
        f"case_id mismatch or invalid: corpus={case_id_val}, manifest={manifest_case_id}, dir={bundle_dir.name}",
    )

    # 3. CORPUS-HASH-001: Inventory hash matches
    inventory = manifest.get("inventory", {})
    manifest_corpus_sha = inventory.get("corpus.json")
    hash_ok = manifest_corpus_sha == actual_corpus_sha
    actual_bundle_content_sha = sha256_bytes(canonical_json_bytes(inventory))
    if manifest.get("bundle_content_sha256") != actual_bundle_content_sha:
        hash_ok = False
    add_rule(
        "CORPUS-HASH-001",
        "canonical artifact hashes match",
        hash_ok,
        f"Hash mismatch: actual_corpus={actual_corpus_sha}, manifest={manifest_corpus_sha}",
    )

    # Read evidence/source-rows.jsonl if present
    evidence_paper_ids: list[str] = []
    if source_rows_file.is_file():
        source_rows_bytes = source_rows_file.read_bytes()
        manifest_sr_sha = inventory.get("evidence/source-rows.jsonl")
        if manifest_sr_sha != sha256_bytes(source_rows_bytes):
            add_rule("CORPUS-HASH-001", "source-rows.jsonl hash mismatch", False)
        for line in source_rows_bytes.splitlines():
            if line.strip():
                try:
                    row_obj = json.loads(line.decode("utf-8"))
                    evidence_paper_ids.append(row_obj.get("paperId", ""))
                except Exception:
                    pass

    # 4. CORPUS-MEMBERSHIP-001: Membership consistency
    records = corpus.get("records", [])
    record_paper_ids = [r.get("paper_id", "") for r in records if isinstance(r, dict)]
    membership_ok = True
    mem_msg = None
    if len(record_paper_ids) != len(set(record_paper_ids)):
        membership_ok = False
        mem_msg = "Duplicate paper_id in corpus records"
    elif record_paper_ids != sorted(record_paper_ids):
        membership_ok = False
        mem_msg = "Corpus records not sorted by canonical paper_id"
    elif evidence_paper_ids and sorted(record_paper_ids) != sorted(evidence_paper_ids):
        membership_ok = False
        mem_msg = f"Records do not match evidence source rows: corpus={len(record_paper_ids)}, evidence={len(evidence_paper_ids)}"
    else:
        expected_runtime_membership_sha = sha256_bytes(
            canonical_json_bytes(
                {"case_id": case_id_val, "paper_ids": sorted(record_paper_ids)}
            )
        )
        if corpus.get("runtime_membership_sha256") != expected_runtime_membership_sha:
            membership_ok = False
            mem_msg = "runtime_membership_sha256 does not match records membership"

    add_rule(
        "CORPUS-MEMBERSHIP-001",
        "membership matches target reference rows",
        membership_ok,
        mem_msg,
    )

    # 5. CORPUS-IDENTITY-001: 40-hex lowercase identities
    identity_ok = True
    id_msg = None
    for r in records:
        pid = r.get("paper_id", "")
        if not PAPER_ID_PATTERN.fullmatch(pid):
            identity_ok = False
            id_msg = f"Invalid paper_id: {pid}"
            break
    add_rule(
        "CORPUS-IDENTITY-001", "paper identities are unique 40-hex", identity_ok, id_msg
    )

    # 6. CORPUS-CONTENT-001 & CORPUS-KNOWN-BAD-001 & CORPUS-PROVENANCE-001 & CORPUS-ELIGIBILITY-001
    content_ok = True
    content_msg = None
    known_bad_ok = True
    known_bad_msg = None
    provenance_ok = True
    provenance_msg = None
    has_validated_content = False

    for r in records:
        title = r.get("title", "")
        if not isinstance(title, str) or not title.strip():
            content_ok = False
            content_msg = f"Missing or empty title in paper {r.get('paper_id')}"

        if not r.get("provenance_ref"):
            provenance_ok = False
            provenance_msg = (
                f"Missing record provenance_ref in paper {r.get('paper_id')}"
            )

        c_items = r.get("content_items", [])
        if not isinstance(c_items, list) or not c_items:
            content_ok = False
            content_msg = f"Paper {r.get('paper_id')} has no content_items"
        else:
            for item in c_items:
                c_type = item.get("type")
                c_status = item.get("status")
                c_text = item.get("text")
                c_sha = item.get("sha256")
                if c_type not in CORPUS_ALLOWED_CONTENT_TYPES:
                    content_ok = False
                    content_msg = (
                        f"Invalid content_type '{c_type}' in paper {r.get('paper_id')}"
                    )
                if c_status not in CORPUS_ALLOWED_CONTENT_STATUSES:
                    content_ok = False
                    content_msg = f"Invalid content status '{c_status}' in paper {r.get('paper_id')}"
                if c_status == "validated":
                    if not isinstance(c_text, str) or not c_text.strip():
                        content_ok = False
                        content_msg = f"Status is validated but text is empty in paper {r.get('paper_id')}"
                    elif sha256_bytes(c_text.encode("utf-8")) != c_sha:
                        content_ok = False
                        content_msg = (
                            f"Content text sha256 mismatch in paper {r.get('paper_id')}"
                        )
                    else:
                        has_validated_content = True
                if isinstance(c_text, str):
                    for bad in CORPUS_KNOWN_BAD_TEXTS:
                        if c_text.strip() == bad:
                            known_bad_ok = False
                            known_bad_msg = f"Known corrupt text '{bad}' entered runtime in paper {r.get('paper_id')}"
                if not item.get("provenance_ref"):
                    provenance_ok = False
                    provenance_msg = f"Missing content item provenance_ref in paper {r.get('paper_id')}"

    add_rule(
        "CORPUS-CONTENT-001",
        "title and content items consistent",
        content_ok,
        content_msg,
    )
    add_rule(
        "CORPUS-KNOWN-BAD-001",
        "no known corrupt values enter runtime",
        known_bad_ok,
        known_bad_msg,
    )
    add_rule(
        "CORPUS-PROVENANCE-001",
        "every record links provenance pointer",
        provenance_ok,
        provenance_msg,
    )
    add_rule(
        "CORPUS-ELIGIBILITY-001",
        "corpus contains validated Reference Content",
        has_validated_content,
        "No validated reference content found in corpus",
    )

    # 8. CORPUS-SOURCE-001: Source dataset
    source_ds = corpus.get("source_dataset", {})
    source_ok = (
        isinstance(source_ds, dict)
        and bool(source_ds.get("path"))
        and bool(source_ds.get("sha256"))
    )
    add_rule("CORPUS-SOURCE-001", "source dataset hash approved", source_ok)

    # Warnings collection
    for r in records:
        if not r.get("venue"):
            warnings.append(
                f"Optional venue metadata missing for reference paper {r.get('paper_id')}"
            )

    status = "pass" if len(errors) == 0 else "fail"
    return {
        "case_id": case_id_val or bundle_dir.name,
        "corpus_sha256": actual_corpus_sha,
        "error_count": len(errors),
        "errors": errors,
        "rules": rules,
        "status": status,
        "validator_version": CORPUS_VALIDATOR_VERSION,
        "warning_count": len(warnings),
        "warnings": warnings,
    }
