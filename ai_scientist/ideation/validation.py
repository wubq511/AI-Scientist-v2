from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable
import unicodedata

from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    read_exact,
    read_json,
    relative_posix,
    sha256_bytes,
    workspace_relative_path,
    write_tree_once,
)
from .contract import (
    DOI_PATTERN,
    PAPER_ID_PATTERN,
    SEMANTIC_CHECKS,
    SOURCE_ALLOWLIST,
    URL_PATTERN,
    WORKSHOP_ATTEMPT_SCHEMA_VERSION,
    WORKSHOP_CONTRACT_VERSION,
    WORKSHOP_DERIVATION_SCHEMA_VERSION,
    WORKSHOP_PATTERN,
    WORKSHOP_SEMANTIC_DECISION_SCHEMA_VERSION,
    WORKSHOP_SEMANTIC_PACKET_SCHEMA_VERSION,
    WORKSHOP_VALIDATION_SCHEMA_VERSION,
    WORKSHOP_VALIDATOR_VERSION,
    LeakagePolicy,
    SourceSnapshot,
    _artifact_ref,
    _now,
)
from .errors import fail
from .preparation import (
    _assert_frozen_case_binding,
    _load_bound_preparation,
    _parse_ref,
)
from .schema import (
    boolean,
    case_id as parse_case_id,
    closed_object,
    nonempty_string,
    positive_integer,
    sha256 as parse_sha256,
    stage_id,
    timestamp,
)
from .text import normalize_text, tokenize_text


def _parse_derivation(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("INVALID_SCHEMA", "derivation record must be an object")
    mechanism = value.get("mechanism")
    common = {
        "actor",
        "authoring_source_sha256",
        "completed_at",
        "mechanism",
        "mechanism_version",
        "schema_version",
        "source_fields",
    }
    keys = (
        common
        if mechanism == "manual"
        else common | {"config_sha256", "model", "prompt_sha256", "provider"}
    )
    record = closed_object(value, label="derivation record", keys=keys)
    if record["schema_version"] != WORKSHOP_DERIVATION_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop derivation schema is unsupported")
    if mechanism not in {"manual", "model"}:
        fail("INVALID_SCHEMA", "derivation mechanism is invalid")
    for field in ("actor", "mechanism_version"):
        nonempty_string(record[field], label=f"derivation.{field}")
    parse_sha256(
        record["authoring_source_sha256"],
        label="derivation.authoring_source_sha256",
    )
    timestamp(record["completed_at"], label="derivation.completed_at")
    if record["source_fields"] != SOURCE_ALLOWLIST:
        fail("BOUNDARY_VIOLATION", "Derivation source fields are not allowlisted")
    if mechanism == "model":
        for field in ("model", "provider"):
            nonempty_string(record[field], label=f"derivation.{field}")
        for field in ("config_sha256", "prompt_sha256"):
            parse_sha256(record[field], label=f"derivation.{field}")
    return record


def _failure(
    rule_id: str,
    reason: str,
    *,
    source: str | None = None,
    evidence: str | None = None,
) -> dict[str, str | None]:
    return {
        "evidence_sha256": evidence,
        "reason": reason,
        "rule_id": rule_id,
        "source": source,
    }


def _append_failure(
    failures: list[dict[str, str | None]], failure: dict[str, str | None]
) -> None:
    identity = (
        failure["rule_id"],
        failure["source"],
        failure["evidence_sha256"],
    )
    if all(
        (item["rule_id"], item["source"], item["evidence_sha256"]) != identity
        for item in failures
    ):
        failures.append(failure)


def validate_workshop_bytes(
    data: bytes,
    *,
    target_paper_id: str,
    target_row: dict[str, str],
    external_ids: Iterable[tuple[str, str]],
    reference_contexts: Iterable[tuple[str, str]],
    policy: LeakagePolicy,
) -> dict[str, Any]:
    failures: list[dict[str, str | None]] = []
    sections: dict[str, str] | None = None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        text = None
        failures.append(
            _failure(
                "WORKSHOP-CANONICAL-UTF8",
                "candidate is not valid UTF-8",
                evidence=sha256_bytes(str(exc.start).encode("ascii")),
            )
        )

    if text is not None:
        if text.startswith("\ufeff"):
            failures.append(
                _failure("WORKSHOP-CANONICAL-UTF8", "UTF-8 BOM is forbidden")
            )
        if unicodedata.normalize("NFC", text) != text:
            failures.append(_failure("WORKSHOP-CANONICAL-NFC", "candidate is not NFC"))
        if "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
            failures.append(
                _failure(
                    "WORKSHOP-CANONICAL-LF",
                    "candidate must use LF and one final newline",
                )
            )
        if any(line.endswith((" ", "\t")) for line in text.splitlines()):
            failures.append(
                _failure(
                    "WORKSHOP-CANONICAL-WHITESPACE",
                    "candidate has trailing line whitespace",
                )
            )
        match = WORKSHOP_PATTERN.fullmatch(text)
        if match is None or "<!--" in text:
            failures.append(
                _failure(
                    "WORKSHOP-SCHEMA",
                    "candidate does not match the closed four-section rendering",
                )
            )
        else:
            sections = {
                "abstract": match.group(4),
                "keywords": match.group(2),
                "title": match.group(1),
                "tldr": match.group(3),
            }
            if any(not section.strip() for section in sections.values()):
                failures.append(
                    _failure("WORKSHOP-SCHEMA", "candidate contains an empty section")
                )
            keywords = [item.strip() for item in sections["keywords"].split(",")]
            if any(not item for item in keywords):
                failures.append(
                    _failure("WORKSHOP-SCHEMA", "candidate keywords are malformed")
                )
            if re.search(r"(?m)^#{1,6}(?:\s|$)", sections["abstract"]):
                failures.append(
                    _failure("WORKSHOP-SCHEMA", "candidate has an extra section")
                )

        normalized_workshop = normalize_text(text, label="workshop")
        normalized_title = normalize_text(target_row["title"], label="target.title")
        if normalized_title and normalized_title in normalized_workshop:
            failures.append(
                _failure(
                    "WORKSHOP-IDENTITY-TITLE",
                    "candidate contains the exact normalized Target Paper title",
                    source="target.title",
                    evidence=sha256_bytes(normalized_title.encode("utf-8")),
                )
            )
        identifiers = [("target.paper_id", target_paper_id), *external_ids]
        for name, identifier in identifiers:
            if identifier and identifier.casefold() in text.casefold():
                failures.append(
                    _failure(
                        "WORKSHOP-IDENTITY-ID",
                        "candidate contains a private Target Paper identifier",
                        source=name,
                        evidence=sha256_bytes(identifier.encode("utf-8")),
                    )
                )
        if URL_PATTERN.search(text):
            failures.append(
                _failure("WORKSHOP-IDENTITY-URL", "candidate contains a URL")
            )
        if DOI_PATTERN.search(text):
            failures.append(
                _failure("WORKSHOP-IDENTITY-DOI", "candidate contains a DOI")
            )
        if PAPER_ID_PATTERN.search(text):
            failures.append(
                _failure("WORKSHOP-IDENTITY-PAPER", "candidate contains a paper ID")
            )

        comparison_sources = [
            ("target.raw_abstract", target_row["abstract"]),
            ("target.abstract_summary", target_row["abstract_summary"]),
            *reference_contexts,
        ]
        workshop_tokens = tokenize_text(text, label="workshop")
        workshop_ngrams = {
            tuple(workshop_tokens[index : index + policy.ngram_tokens])
            for index in range(len(workshop_tokens) - policy.ngram_tokens + 1)
        }
        for source, source_text in comparison_sources:
            if not source_text:
                continue
            if source_text in text:
                _append_failure(
                    failures,
                    _failure(
                        "WORKSHOP-LEAKAGE-EXACT",
                        "candidate contains an exact private comparison source",
                        source=source,
                        evidence=sha256_bytes(source_text.encode("utf-8")),
                    ),
                )
            normalized_source = normalize_text(source_text, label=source)
            if normalized_source and normalized_source in normalized_workshop:
                _append_failure(
                    failures,
                    _failure(
                        "WORKSHOP-LEAKAGE-NORMALIZED",
                        "candidate contains a normalized private comparison source",
                        source=source,
                        evidence=sha256_bytes(normalized_source.encode("utf-8")),
                    ),
                )
            source_tokens = tokenize_text(source_text, label=source)
            for index in range(len(source_tokens) - policy.ngram_tokens + 1):
                ngram = tuple(source_tokens[index : index + policy.ngram_tokens])
                if ngram in workshop_ngrams:
                    _append_failure(
                        failures,
                        _failure(
                            "WORKSHOP-LEAKAGE-NGRAM",
                            f"candidate shares a {policy.ngram_tokens}-token span",
                            source=source,
                            evidence=sha256_bytes(" ".join(ngram).encode("utf-8")),
                        ),
                    )

    failures.sort(
        key=lambda item: (
            item["rule_id"] or "",
            item["source"] or "",
            item["evidence_sha256"] or "",
        )
    )
    deterministic_status = "pass" if not failures else "fail"
    return {
        "canonical_sha256": sha256_bytes(data),
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "deterministic_status": deterministic_status,
        "failures": failures,
        "lengths": (
            None
            if text is None or sections is None
            else {
                "abstract_chars": len(sections["abstract"]),
                "full_chars": len(text),
                "keywords_chars": len(sections["keywords"]),
                "title_chars": len(sections["title"]),
                "tldr_chars": len(sections["tldr"]),
            }
        ),
        "normalization_version": policy.normalization_version,
        "policy_sha256": policy.sha256,
        "policy_version": policy.version,
        "schema_version": WORKSHOP_VALIDATION_SCHEMA_VERSION,
        "semantic_status": (
            "pending_independent_review"
            if deterministic_status == "pass"
            else "not_run"
        ),
        "validator_version": WORKSHOP_VALIDATOR_VERSION,
    }


def _approved_resolution_exists(case_root: Path) -> bool:
    attempts_root = case_root / "attempts"
    if not attempts_root.is_dir():
        return False
    for resolution in attempts_root.glob("*/resolution/workshop-manifest.json"):
        if resolution.is_file():
            return True
    return False


def _semantic_packet_value(
    *,
    attempt_id: str,
    candidate_path: Path,
    candidate_bytes: bytes,
    case_id: str,
    preparation: dict[str, Any],
    snapshot: SourceSnapshot,
    workspace: Path,
) -> dict[str, Any]:
    return {
        "attempt_id": attempt_id,
        "candidate": _artifact_ref(candidate_path, workspace, candidate_bytes),
        "case_id": case_id,
        "required_checks": list(SEMANTIC_CHECKS),
        "private_comparison_sources": {
            "reference_contexts": [
                {"source": source, "text": text}
                for source, text in snapshot.reference_contexts
            ],
            "target": {
                "abstract_summary": snapshot.target_row["abstract_summary"],
                "raw_abstract": snapshot.target_row["abstract"],
                "title": snapshot.target_row["title"],
            },
            "target_identity": preparation["target_identity"],
        },
        "schema_version": WORKSHOP_SEMANTIC_PACKET_SCHEMA_VERSION,
    }


def validate_workshop(
    workspace_root: Path,
    *,
    preparation_manifest: str,
    attempt_id: str,
    candidate: str,
    derivation_record: str,
) -> dict[str, Any]:
    workspace = workspace_root.resolve(strict=True)
    manifest_path = workspace_relative_path(
        workspace, preparation_manifest, label="preparation_manifest"
    )
    preparation, preparation_bytes, snapshot, policy = _load_bound_preparation(
        workspace, manifest_path
    )
    case_root = manifest_path.parent.parent.parent
    _assert_frozen_case_binding(workspace, case_root, preparation)
    parsed_attempt_id = stage_id(attempt_id, label="attempt_id")
    candidate_path = workspace_relative_path(workspace, candidate, label="candidate")
    derivation_path = workspace_relative_path(
        workspace, derivation_record, label="derivation_record"
    )
    if not candidate_path.is_file():
        fail("MISSING_ARTIFACT", "Workshop candidate is missing")
    candidate_bytes = candidate_path.read_bytes()
    derivation_value, _ = read_json(derivation_path, label="derivation record")
    derivation = _parse_derivation(derivation_value)
    if (
        derivation["authoring_source_sha256"]
        != preparation["authoring_source"]["sha256"]
    ):
        fail("HASH_MISMATCH", "Derivation record binds a different authoring source")

    if _approved_resolution_exists(case_root):
        fail("WORKSHOP_ALREADY_APPROVED", "This case already has an Approved Workshop")
    attempt_root = case_root / "attempts" / parsed_attempt_id
    copied_candidate_path = attempt_root / f"{preparation['case_id']}.md"
    copied_derivation_path = attempt_root / "derivation-record.json"
    report_path = attempt_root / "validation-report.json"
    packet_path = attempt_root / "semantic-review-packet.json"
    attempt_manifest_path = attempt_root / "attempt-manifest.json"

    report = validate_workshop_bytes(
        candidate_bytes,
        target_paper_id=preparation["target_identity"]["paper_id"],
        target_row=snapshot.target_row,
        external_ids=(
            (item["name"], item["value"])
            for item in preparation["target_identity"]["external_ids"]
        ),
        reference_contexts=snapshot.reference_contexts,
        policy=policy,
    )
    report_bytes = canonical_json_bytes(report)
    derivation_bytes = canonical_json_bytes(derivation)
    packet_bytes: bytes | None = None
    if report["deterministic_status"] == "pass":
        packet = _semantic_packet_value(
            attempt_id=parsed_attempt_id,
            candidate_path=copied_candidate_path,
            candidate_bytes=candidate_bytes,
            case_id=preparation["case_id"],
            preparation=preparation,
            snapshot=snapshot,
            workspace=workspace,
        )
        packet_bytes = canonical_json_bytes(packet)

    status = (
        "pending_independent_review"
        if report["deterministic_status"] == "pass"
        else "rejected_deterministic"
    )
    attempt_manifest = {
        "attempt_id": parsed_attempt_id,
        "candidate": _artifact_ref(copied_candidate_path, workspace, candidate_bytes),
        "case_id": preparation["case_id"],
        "created_at": _now(),
        "derivation_record": _artifact_ref(
            copied_derivation_path, workspace, derivation_bytes
        ),
        "preparation_manifest": _artifact_ref(
            manifest_path, workspace, preparation_bytes
        ),
        "schema_version": WORKSHOP_ATTEMPT_SCHEMA_VERSION,
        "semantic_review_packet": (
            None
            if packet_bytes is None
            else _artifact_ref(packet_path, workspace, packet_bytes)
        ),
        "status": status,
        "validation_report": _artifact_ref(report_path, workspace, report_bytes),
    }
    files = {
        f"{preparation['case_id']}.md": candidate_bytes,
        "derivation-record.json": derivation_bytes,
        "validation-report.json": report_bytes,
        "attempt-manifest.json": canonical_json_bytes(attempt_manifest),
    }
    if packet_bytes is not None:
        files["semantic-review-packet.json"] = packet_bytes
    write_tree_once(attempt_root, files)
    return {
        "attempt_manifest": relative_posix(attempt_manifest_path, workspace),
        "case_id": preparation["case_id"],
        "deterministic_status": report["deterministic_status"],
        "semantic_review_packet": (
            None if packet_bytes is None else relative_posix(packet_path, workspace)
        ),
        "status": status,
        "validation_report": relative_posix(report_path, workspace),
    }


def _parse_attempt(value: object) -> dict[str, Any]:
    root = closed_object(
        value,
        label="attempt manifest",
        keys={
            "attempt_id",
            "candidate",
            "case_id",
            "created_at",
            "derivation_record",
            "preparation_manifest",
            "schema_version",
            "semantic_review_packet",
            "status",
            "validation_report",
        },
    )
    if root["schema_version"] != WORKSHOP_ATTEMPT_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop attempt schema is unsupported")
    root["case_id"] = parse_case_id(root["case_id"])
    root["attempt_id"] = stage_id(root["attempt_id"], label="attempt_id")
    timestamp(root["created_at"], label="attempt.created_at")
    for field in (
        "candidate",
        "derivation_record",
        "preparation_manifest",
        "validation_report",
    ):
        root[field] = _parse_ref(root[field], label=f"attempt.{field}")
    if root["semantic_review_packet"] is not None:
        root["semantic_review_packet"] = _parse_ref(
            root["semantic_review_packet"], label="attempt.semantic_review_packet"
        )
    if root["status"] not in {
        "pending_independent_review",
        "rejected_deterministic",
    }:
        fail("INVALID_SCHEMA", "Workshop attempt status is invalid")
    return root


def _parse_report(value: object) -> dict[str, Any]:
    report = closed_object(
        value,
        label="validation report",
        keys={
            "canonical_sha256",
            "contract_version",
            "deterministic_status",
            "failures",
            "lengths",
            "normalization_version",
            "policy_sha256",
            "policy_version",
            "schema_version",
            "semantic_status",
            "validator_version",
        },
    )
    if report["schema_version"] != WORKSHOP_VALIDATION_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop validation schema is unsupported")
    parse_sha256(report["canonical_sha256"], label="report.canonical_sha256")
    parse_sha256(report["policy_sha256"], label="report.policy_sha256")
    if report["deterministic_status"] not in {"pass", "fail"}:
        fail("INVALID_SCHEMA", "Workshop deterministic status is invalid")
    if report["semantic_status"] not in {
        "pending_independent_review",
        "not_run",
    }:
        fail("INVALID_SCHEMA", "Workshop semantic status is invalid")
    if not isinstance(report["failures"], list):
        fail("INVALID_SCHEMA", "Workshop failures must be an array")
    for index, failure in enumerate(report["failures"]):
        parsed = closed_object(
            failure,
            label=f"report.failures[{index}]",
            keys={"evidence_sha256", "reason", "rule_id", "source"},
        )
        nonempty_string(parsed["reason"], label="failure.reason")
        nonempty_string(parsed["rule_id"], label="failure.rule_id")
        if parsed["evidence_sha256"] is not None:
            parse_sha256(parsed["evidence_sha256"], label="failure.evidence_sha256")
        if parsed["source"] is not None:
            nonempty_string(parsed["source"], label="failure.source")
    if (report["deterministic_status"] == "pass") != (not report["failures"]):
        fail("INVALID_SCHEMA", "Workshop report status and failures disagree")
    expected_semantic_status = (
        "pending_independent_review"
        if report["deterministic_status"] == "pass"
        else "not_run"
    )
    if report["semantic_status"] != expected_semantic_status:
        fail("INVALID_SCHEMA", "Workshop gate statuses disagree")
    if report["lengths"] is not None:
        lengths = closed_object(
            report["lengths"],
            label="report.lengths",
            keys={
                "abstract_chars",
                "full_chars",
                "keywords_chars",
                "title_chars",
                "tldr_chars",
            },
        )
        for key, value in lengths.items():
            positive_integer(value, label=f"report.lengths.{key}")
    return report


def _parse_semantic_decision(value: object) -> dict[str, Any]:
    decision = closed_object(
        value,
        label="semantic decision",
        keys={
            "attempt_manifest_sha256",
            "candidate_sha256",
            "case_id",
            "checks",
            "decision",
            "rationale",
            "reviewed_at",
            "reviewer",
            "schema_version",
        },
    )
    if decision["schema_version"] != WORKSHOP_SEMANTIC_DECISION_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop semantic decision schema is unsupported")
    decision["case_id"] = parse_case_id(decision["case_id"])
    parse_sha256(
        decision["attempt_manifest_sha256"],
        label="semantic_decision.attempt_manifest_sha256",
    )
    parse_sha256(
        decision["candidate_sha256"],
        label="semantic_decision.candidate_sha256",
    )
    nonempty_string(decision["rationale"], label="semantic_decision.rationale")
    nonempty_string(decision["reviewer"], label="semantic_decision.reviewer")
    timestamp(decision["reviewed_at"], label="semantic_decision.reviewed_at")
    checks = closed_object(
        decision["checks"],
        label="semantic_decision.checks",
        keys=set(SEMANTIC_CHECKS),
    )
    parsed_checks = [
        boolean(value, label=f"semantic_decision.checks.{key}")
        for key, value in checks.items()
    ]
    all_pass = all(parsed_checks)
    if decision["decision"] not in {"approved", "rejected"}:
        fail("INVALID_SCHEMA", "Workshop semantic decision is invalid")
    if (decision["decision"] == "approved") != all_pass:
        fail("INVALID_SCHEMA", "Workshop semantic decision contradicts its checks")
    return decision


@dataclass(frozen=True, slots=True)
class LoadedAttempt:
    attempt: dict[str, Any]
    manifest_bytes: bytes
    derivation: dict[str, Any]
    candidate_bytes: bytes
    preparation: dict[str, Any]
    snapshot: SourceSnapshot
    policy: LeakagePolicy
    report: dict[str, Any]


def _load_attempt(workspace: Path, attempt_manifest_path: Path) -> LoadedAttempt:
    attempt_value, attempt_bytes = read_json(
        attempt_manifest_path, label="attempt manifest"
    )
    attempt = _parse_attempt(attempt_value)
    if (
        attempt_manifest_path.name != "attempt-manifest.json"
        or attempt_manifest_path.parent.name != attempt["attempt_id"]
        or attempt_manifest_path.parent.parent.name != "attempts"
        or attempt_manifest_path.parent.parent.parent.name != attempt["case_id"]
    ):
        fail("IDENTITY_MISMATCH", "Attempt path identity does not match")
    preparation_path = workspace_relative_path(
        workspace,
        attempt["preparation_manifest"]["path"],
        label="attempt.preparation_manifest.path",
    )
    preparation, preparation_bytes, snapshot, policy = _load_bound_preparation(
        workspace,
        preparation_path,
        expected_sha256=attempt["preparation_manifest"]["sha256"],
    )
    _assert_frozen_case_binding(
        workspace, preparation_path.parent.parent.parent, preparation
    )
    if attempt["case_id"] != preparation["case_id"]:
        fail("IDENTITY_MISMATCH", "Attempt and preparation cases differ")
    candidate_path = workspace_relative_path(
        workspace, attempt["candidate"]["path"], label="attempt.candidate.path"
    )
    candidate_bytes = read_exact(
        candidate_path, attempt["candidate"]["sha256"], label="Workshop candidate"
    )
    derivation_path = workspace_relative_path(
        workspace,
        attempt["derivation_record"]["path"],
        label="attempt.derivation_record.path",
    )
    derivation_bytes = read_exact(
        derivation_path,
        attempt["derivation_record"]["sha256"],
        label="derivation record",
    )
    derivation = _parse_derivation(
        parse_json_bytes(derivation_bytes, label="derivation record")
    )
    if (
        derivation["authoring_source_sha256"]
        != preparation["authoring_source"]["sha256"]
    ):
        fail("HASH_MISMATCH", "Derivation record binds a different authoring source")
    report_path = workspace_relative_path(
        workspace,
        attempt["validation_report"]["path"],
        label="attempt.validation_report.path",
    )
    report_bytes = read_exact(
        report_path,
        attempt["validation_report"]["sha256"],
        label="validation report",
    )
    report = _parse_report(parse_json_bytes(report_bytes, label="validation report"))
    if report["canonical_sha256"] != attempt["candidate"]["sha256"]:
        fail("HASH_MISMATCH", "Validation report binds a different candidate")
    expected_attempt_status = (
        "pending_independent_review"
        if report["deterministic_status"] == "pass"
        else "rejected_deterministic"
    )
    if attempt["status"] != expected_attempt_status:
        fail("INVALID_SCHEMA", "Workshop attempt and validation statuses disagree")
    recomputed = validate_workshop_bytes(
        candidate_bytes,
        target_paper_id=preparation["target_identity"]["paper_id"],
        target_row=snapshot.target_row,
        external_ids=(
            (item["name"], item["value"])
            for item in preparation["target_identity"]["external_ids"]
        ),
        reference_contexts=snapshot.reference_contexts,
        policy=policy,
    )
    if canonical_json_bytes(report) != canonical_json_bytes(recomputed):
        fail("VALIDATION_DRIFT", "Workshop validation report is not replayable")
    if report["deterministic_status"] == "pass":
        if attempt["semantic_review_packet"] is None:
            fail("MISSING_ARTIFACT", "Semantic review packet is missing")
        semantic_packet_path = workspace_relative_path(
            workspace,
            attempt["semantic_review_packet"]["path"],
            label="attempt.semantic_review_packet.path",
        )
        semantic_packet_bytes = read_exact(
            semantic_packet_path,
            attempt["semantic_review_packet"]["sha256"],
            label="semantic review packet",
        )
        expected_packet = _semantic_packet_value(
            attempt_id=attempt["attempt_id"],
            candidate_path=candidate_path,
            candidate_bytes=candidate_bytes,
            case_id=attempt["case_id"],
            preparation=preparation,
            snapshot=snapshot,
            workspace=workspace,
        )
        if semantic_packet_bytes != canonical_json_bytes(expected_packet):
            fail("VALIDATION_DRIFT", "Semantic review packet is not replayable")
    elif attempt["semantic_review_packet"] is not None:
        fail("INVALID_SCHEMA", "Rejected attempt cannot have a semantic packet")
    return LoadedAttempt(
        attempt=attempt,
        manifest_bytes=attempt_bytes,
        derivation=derivation,
        candidate_bytes=candidate_bytes,
        preparation=preparation,
        snapshot=snapshot,
        policy=policy,
        report=report,
    )
