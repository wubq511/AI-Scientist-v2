from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import io
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
from .errors import fail
from .schema import (
    boolean,
    case_id as parse_case_id,
    closed_object,
    nonempty_string,
    positive_integer,
    sha256 as parse_sha256,
    stage_id,
    string_list,
    timestamp,
)
from .text import NORMALIZATION_VERSION, normalize_text, tokenize_text

WORKSHOP_CONTRACT_VERSION = "workshop-contract-v1.0"
WORKSHOP_AUTHORING_SOURCE_SCHEMA_VERSION = "workshop-authoring-source-v1.0"
WORKSHOP_PREPARATION_SCHEMA_VERSION = "workshop-preparation-v1.0"
WORKSHOP_DERIVATION_SCHEMA_VERSION = "workshop-derivation-v1.0"
WORKSHOP_ATTEMPT_SCHEMA_VERSION = "workshop-attempt-v1.0"
WORKSHOP_VALIDATION_SCHEMA_VERSION = "workshop-validation-v1.0"
WORKSHOP_SEMANTIC_PACKET_SCHEMA_VERSION = "workshop-semantic-packet-v1.0"
WORKSHOP_SEMANTIC_DECISION_SCHEMA_VERSION = "workshop-semantic-decision-v1.0"
WORKSHOP_RESOLUTION_SCHEMA_VERSION = "workshop-resolution-v1.0"
WORKSHOP_MANIFEST_SCHEMA_VERSION = "approved-workshop-manifest-v1.0"
WORKSHOP_VALIDATOR_VERSION = "workshop-validator-v1.0"
WORKSHOP_POLICY_PATH = Path("ai_scientist/ideation/policies/workshop-leakage-v1.json")
WORKSHOP_POLICY_SHA256 = (
    "5147d6b1d951e2de0f50fb132955e053e638ffd3daa6292c08a047f8fdc21f61"
)
SOURCE_ALLOWLIST = ["title", "abstract"]
TARGET_REQUIRED_FIELDS = {
    "paperId",
    "title",
    "abstract",
    "externalIds",
    "abstract_summary",
}
REFERENCE_REQUIRED_FIELDS = {"targetPaperId", "paperId", "contexts"}
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


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    target_path: Path
    target_sha256: str
    target_row: dict[str, str]
    target_row_number: int
    target_row_sha256: str
    reference_path: Path
    reference_sha256: str
    reference_rows: tuple[tuple[int, dict[str, str], str], ...]
    external_ids: tuple[tuple[str, str], ...]
    reference_contexts: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class LeakagePolicy:
    version: str
    schema_version: str
    normalization_version: str
    ngram_tokens: int
    comparison_sources: tuple[str, ...]
    calibration_status: str
    sha256: str


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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


def _csv_rows(data: bytes, *, label: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", f"{label} is not valid UTF-8", offset=exc.start)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        fail("INVALID_SOURCE", f"{label} has no CSV header")
    rows = list(reader)
    if any(value is None for row in rows for value in row.values()):
        fail("INVALID_SOURCE", f"{label} contains a short CSV row")
    return list(reader.fieldnames), rows


def _load_source_snapshot(
    target_path: Path,
    reference_path: Path,
    *,
    target_paper_id: str,
    expected_target_sha256: str | None = None,
    expected_reference_sha256: str | None = None,
) -> SourceSnapshot:
    if not target_path.is_file() or not reference_path.is_file():
        fail("MISSING_ARTIFACT", "Required Workshop source data is missing")
    target_data = target_path.read_bytes()
    reference_data = reference_path.read_bytes()
    target_sha256 = sha256_bytes(target_data)
    reference_sha256 = sha256_bytes(reference_data)
    if expected_target_sha256 is not None and target_sha256 != expected_target_sha256:
        fail("SOURCE_DRIFT", "Target dataset hash changed")
    if (
        expected_reference_sha256 is not None
        and reference_sha256 != expected_reference_sha256
    ):
        fail("SOURCE_DRIFT", "Reference dataset hash changed")

    target_fields, target_rows = _csv_rows(target_data, label="target dataset")
    reference_fields, reference_rows = _csv_rows(
        reference_data, label="reference dataset"
    )
    if not TARGET_REQUIRED_FIELDS <= set(target_fields):
        fail("INVALID_SOURCE", "Target dataset is missing required fields")
    if not REFERENCE_REQUIRED_FIELDS <= set(reference_fields):
        fail("INVALID_SOURCE", "Reference dataset is missing required fields")

    matches = [
        (row_number, row)
        for row_number, row in enumerate(target_rows, start=2)
        if row["paperId"] == target_paper_id
    ]
    if len(matches) != 1:
        fail(
            "INVALID_SOURCE",
            "Target paper identity must resolve to exactly one row",
            match_count=len(matches),
        )
    target_row_number, target_row = matches[0]
    if not target_row["title"] or not target_row["abstract"]:
        fail("INVALID_SOURCE", "Target title and raw abstract must be non-empty")
    target_row_sha256 = sha256_bytes(canonical_json_bytes(target_row))

    external_ids_value = _parse_literal(
        target_row["externalIds"], label="target.externalIds", expected=dict
    )
    external_ids: list[tuple[str, str]] = []
    for name, value in external_ids_value.items():
        if not isinstance(name, str) or not isinstance(value, (str, int)):
            fail("INVALID_SOURCE", "Target external identifiers are invalid")
        external_ids.append((name, str(value)))

    matching_references: list[tuple[int, dict[str, str], str]] = []
    contexts: list[tuple[str, str]] = []
    for row_number, row in enumerate(reference_rows, start=2):
        if row["targetPaperId"] != target_paper_id:
            continue
        row_sha256 = sha256_bytes(canonical_json_bytes(row))
        matching_references.append((row_number, row, row_sha256))
        parsed_contexts = _parse_literal(
            row["contexts"],
            label=f"reference row {row_number}.contexts",
            expected=list,
        )
        for context_index, context in enumerate(parsed_contexts):
            if not isinstance(context, str):
                fail("INVALID_SOURCE", "Reference contexts must be strings")
            if context:
                contexts.append(
                    (f"reference[{row_number}].context[{context_index}]", context)
                )

    return SourceSnapshot(
        target_path=target_path,
        target_sha256=target_sha256,
        target_row=target_row,
        target_row_number=target_row_number,
        target_row_sha256=target_row_sha256,
        reference_path=reference_path,
        reference_sha256=reference_sha256,
        reference_rows=tuple(matching_references),
        external_ids=tuple(sorted(external_ids)),
        reference_contexts=tuple(contexts),
    )


def _load_policy(workspace_root: Path) -> LeakagePolicy:
    path = workspace_root / WORKSHOP_POLICY_PATH
    if not path.is_file():
        fail("MISSING_ARTIFACT", "Workshop leakage policy is missing")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != WORKSHOP_POLICY_SHA256:
        fail("POLICY_DRIFT", "Workshop leakage policy hash changed")
    value = parse_json_bytes(data, label="Workshop leakage policy")
    policy = closed_object(
        value,
        label="Workshop leakage policy",
        keys={
            "calibration_status",
            "comparison_sources",
            "ngram_tokens",
            "normalization_version",
            "schema_version",
            "version",
        },
    )
    schema_version = nonempty_string(
        policy["schema_version"], label="policy.schema_version"
    )
    if schema_version != "workshop-leakage-policy-v1.0":
        fail("UNSUPPORTED_SCHEMA", "Workshop leakage policy schema is unsupported")
    normalization_version = nonempty_string(
        policy["normalization_version"], label="policy.normalization_version"
    )
    if normalization_version != NORMALIZATION_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop normalization version is unsupported")
    comparison_sources = tuple(
        string_list(
            policy["comparison_sources"],
            label="policy.comparison_sources",
            nonempty=True,
        )
    )
    if comparison_sources != (
        "target.raw_abstract",
        "target.abstract_summary",
        "reference.contexts",
    ):
        fail("UNSUPPORTED_SCHEMA", "Workshop comparison sources are unsupported")
    calibration_status = nonempty_string(
        policy["calibration_status"], label="policy.calibration_status"
    )
    if calibration_status != "pending":
        fail("UNSUPPORTED_SCHEMA", "Workshop calibration status is unsupported")
    return LeakagePolicy(
        version=nonempty_string(policy["version"], label="policy.version"),
        schema_version=schema_version,
        normalization_version=normalization_version,
        ngram_tokens=positive_integer(
            policy["ngram_tokens"], label="policy.ngram_tokens"
        ),
        comparison_sources=comparison_sources,
        calibration_status=calibration_status,
        sha256=digest,
    )


def _artifact_ref(path: Path, workspace_root: Path, data: bytes) -> dict[str, str]:
    return {
        "path": relative_posix(path, workspace_root),
        "sha256": sha256_bytes(data),
    }


def prepare_workshop(
    workspace_root: Path,
    *,
    case_id: str,
    target_paper_id: str,
    preparation_id: str,
    source_root: str = "data/raw",
    artifact_root: str = "artifacts/ideation-inputs",
    prepared_by: str = "codex",
) -> dict[str, Any]:
    workspace = workspace_root.resolve(strict=True)
    parsed_case_id = parse_case_id(case_id)
    parsed_preparation_id = stage_id(preparation_id, label="preparation_id")
    parsed_target_id = nonempty_string(target_paper_id, label="target_paper_id")
    operator = nonempty_string(prepared_by, label="prepared_by")
    source = workspace_relative_path(workspace, source_root, label="source_root")
    target_path = source / "target_papers.csv"
    reference_path = source / "filtered_references.csv"
    snapshot = _load_source_snapshot(
        target_path, reference_path, target_paper_id=parsed_target_id
    )
    policy = _load_policy(workspace)
    artifacts = workspace_relative_path(workspace, artifact_root, label="artifact_root")
    preparation_root = (
        artifacts
        / "workshops"
        / parsed_case_id
        / "preparations"
        / parsed_preparation_id
    )
    authoring_path = preparation_root / "authoring-source.json"
    manifest_path = preparation_root / "preparation-manifest.json"
    authoring_source = {
        "case_id": parsed_case_id,
        "raw_abstract": snapshot.target_row["abstract"],
        "schema_version": WORKSHOP_AUTHORING_SOURCE_SCHEMA_VERSION,
        "source_fields": SOURCE_ALLOWLIST,
        "title": snapshot.target_row["title"],
    }
    authoring_bytes = canonical_json_bytes(authoring_source)
    reference_rows_identity = [
        {"row_number": row_number, "row_sha256": row_sha256}
        for row_number, _, row_sha256 in snapshot.reference_rows
    ]
    manifest = {
        "authoring_source": _artifact_ref(authoring_path, workspace, authoring_bytes),
        "case_id": parsed_case_id,
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "preparation_id": parsed_preparation_id,
        "prepared_at": _now(),
        "prepared_by": operator,
        "rules": {
            "normalization_version": policy.normalization_version,
            "policy_path": WORKSHOP_POLICY_PATH.as_posix(),
            "policy_sha256": policy.sha256,
            "policy_version": policy.version,
            "validator_version": WORKSHOP_VALIDATOR_VERSION,
        },
        "schema_version": WORKSHOP_PREPARATION_SCHEMA_VERSION,
        "source_allowlist": SOURCE_ALLOWLIST,
        "sources": {
            "reference_dataset": {
                "matching_row_count": len(reference_rows_identity),
                "matching_rows_sha256": sha256_bytes(
                    canonical_json_bytes(reference_rows_identity)
                ),
                "path": relative_posix(snapshot.reference_path, workspace),
                "sha256": snapshot.reference_sha256,
            },
            "target_dataset": {
                "path": relative_posix(snapshot.target_path, workspace),
                "row_number": snapshot.target_row_number,
                "row_sha256": snapshot.target_row_sha256,
                "sha256": snapshot.target_sha256,
            },
        },
        "target_identity": {
            "external_ids": [
                {"name": name, "value": value} for name, value in snapshot.external_ids
            ],
            "paper_id": parsed_target_id,
        },
        "validation_source_inventory": {
            "reference_context_count": len(snapshot.reference_contexts),
            "target_abstract_summary_present": bool(
                snapshot.target_row["abstract_summary"]
            ),
        },
    }
    manifest_bytes = canonical_json_bytes(manifest)
    write_tree_once(
        preparation_root,
        {
            "authoring-source.json": authoring_bytes,
            "preparation-manifest.json": manifest_bytes,
        },
    )
    return {
        "authoring_source": relative_posix(authoring_path, workspace),
        "case_id": parsed_case_id,
        "preparation_manifest": relative_posix(manifest_path, workspace),
        "preparation_manifest_sha256": sha256_bytes(manifest_bytes),
        "status": "prepared",
    }


def _parse_ref(value: object, *, label: str) -> dict[str, str]:
    ref = closed_object(value, label=label, keys={"path", "sha256"})
    return {
        "path": nonempty_string(ref["path"], label=f"{label}.path"),
        "sha256": parse_sha256(ref["sha256"], label=f"{label}.sha256"),
    }


def _parse_external_ids(value: object, *, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        fail("INVALID_SCHEMA", f"{label} must be an array")
    parsed: list[dict[str, str]] = []
    for index, item in enumerate(value):
        entry = closed_object(item, label=f"{label}[{index}]", keys={"name", "value"})
        parsed.append(
            {
                "name": nonempty_string(entry["name"], label=f"{label}[{index}].name"),
                "value": nonempty_string(
                    entry["value"], label=f"{label}[{index}].value"
                ),
            }
        )
    if parsed != sorted(parsed, key=lambda item: (item["name"], item["value"])):
        fail("NON_CANONICAL_INPUT", f"{label} must be sorted")
    return parsed


def _parse_preparation(value: object) -> dict[str, Any]:
    root = closed_object(
        value,
        label="preparation manifest",
        keys={
            "authoring_source",
            "case_id",
            "contract_version",
            "preparation_id",
            "prepared_at",
            "prepared_by",
            "rules",
            "schema_version",
            "source_allowlist",
            "sources",
            "target_identity",
            "validation_source_inventory",
        },
    )
    if root["schema_version"] != WORKSHOP_PREPARATION_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop preparation schema is unsupported")
    if root["contract_version"] != WORKSHOP_CONTRACT_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop contract version is unsupported")
    root["case_id"] = parse_case_id(root["case_id"])
    root["preparation_id"] = stage_id(root["preparation_id"], label="preparation_id")
    nonempty_string(root["prepared_by"], label="prepared_by")
    timestamp(root["prepared_at"], label="prepared_at")
    if root["source_allowlist"] != SOURCE_ALLOWLIST:
        fail("BOUNDARY_VIOLATION", "Workshop source allowlist changed")
    root["authoring_source"] = _parse_ref(
        root["authoring_source"], label="authoring_source"
    )

    rules = closed_object(
        root["rules"],
        label="preparation.rules",
        keys={
            "normalization_version",
            "policy_path",
            "policy_sha256",
            "policy_version",
            "validator_version",
        },
    )
    nonempty_string(rules["policy_path"], label="rules.policy_path")
    parse_sha256(rules["policy_sha256"], label="rules.policy_sha256")
    for key in ("normalization_version", "policy_version", "validator_version"):
        nonempty_string(rules[key], label=f"rules.{key}")

    sources = closed_object(
        root["sources"],
        label="preparation.sources",
        keys={"reference_dataset", "target_dataset"},
    )
    target_source = closed_object(
        sources["target_dataset"],
        label="sources.target_dataset",
        keys={"path", "row_number", "row_sha256", "sha256"},
    )
    nonempty_string(target_source["path"], label="target_dataset.path")
    positive_integer(target_source["row_number"], label="target_dataset.row_number")
    parse_sha256(target_source["row_sha256"], label="target_dataset.row_sha256")
    parse_sha256(target_source["sha256"], label="target_dataset.sha256")
    reference_source = closed_object(
        sources["reference_dataset"],
        label="sources.reference_dataset",
        keys={"matching_row_count", "matching_rows_sha256", "path", "sha256"},
    )
    nonempty_string(reference_source["path"], label="reference_dataset.path")
    if (
        isinstance(reference_source["matching_row_count"], bool)
        or not isinstance(reference_source["matching_row_count"], int)
        or reference_source["matching_row_count"] < 0
    ):
        fail(
            "INVALID_SCHEMA",
            "reference_dataset.matching_row_count must be a non-negative integer",
        )
    parse_sha256(
        reference_source["matching_rows_sha256"],
        label="reference_dataset.matching_rows_sha256",
    )
    parse_sha256(reference_source["sha256"], label="reference_dataset.sha256")

    identity = closed_object(
        root["target_identity"],
        label="target_identity",
        keys={"external_ids", "paper_id"},
    )
    identity["paper_id"] = nonempty_string(
        identity["paper_id"], label="target_identity.paper_id"
    )
    identity["external_ids"] = _parse_external_ids(
        identity["external_ids"], label="target_identity.external_ids"
    )
    inventory = closed_object(
        root["validation_source_inventory"],
        label="validation_source_inventory",
        keys={"reference_context_count", "target_abstract_summary_present"},
    )
    if (
        isinstance(inventory["reference_context_count"], bool)
        or not isinstance(inventory["reference_context_count"], int)
        or inventory["reference_context_count"] < 0
    ):
        fail(
            "INVALID_SCHEMA",
            "reference_context_count must be a non-negative integer",
        )
    boolean(
        inventory["target_abstract_summary_present"],
        label="target_abstract_summary_present",
    )
    return root


def _load_bound_preparation(
    workspace: Path, manifest_path: Path
) -> tuple[dict[str, Any], bytes, SourceSnapshot, LeakagePolicy]:
    value, manifest_bytes = read_json(manifest_path, label="preparation manifest")
    preparation = _parse_preparation(value)
    if manifest_path.name != "preparation-manifest.json":
        fail("INVALID_PATH", "Preparation manifest filename is invalid")
    expected_parent = (
        manifest_path.parent.parent.parent.name,
        manifest_path.parent.name,
    )
    if expected_parent != (
        preparation["case_id"],
        preparation["preparation_id"],
    ):
        fail("IDENTITY_MISMATCH", "Preparation path identity does not match")
    if (
        manifest_path.parent.parent.name != "preparations"
        or manifest_path.parent.parent.parent.parent.name != "workshops"
    ):
        fail("IDENTITY_MISMATCH", "Preparation path layout is invalid")

    policy = _load_policy(workspace)
    rules = preparation["rules"]
    if rules != {
        "normalization_version": policy.normalization_version,
        "policy_path": WORKSHOP_POLICY_PATH.as_posix(),
        "policy_sha256": policy.sha256,
        "policy_version": policy.version,
        "validator_version": WORKSHOP_VALIDATOR_VERSION,
    }:
        fail("POLICY_DRIFT", "Preparation rules do not match current rules")

    authoring_ref = preparation["authoring_source"]
    authoring_path = workspace_relative_path(
        workspace, authoring_ref["path"], label="authoring_source.path"
    )
    authoring_data = read_exact(
        authoring_path,
        authoring_ref["sha256"],
        label="authoring source",
    )
    authoring_value = parse_json_bytes(authoring_data, label="authoring source")
    authoring = closed_object(
        authoring_value,
        label="authoring source",
        keys={"case_id", "raw_abstract", "schema_version", "source_fields", "title"},
    )
    if authoring["schema_version"] != WORKSHOP_AUTHORING_SOURCE_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Workshop authoring source is unsupported")
    if authoring["case_id"] != preparation["case_id"]:
        fail("IDENTITY_MISMATCH", "Authoring source case identity differs")
    if authoring["source_fields"] != SOURCE_ALLOWLIST:
        fail("BOUNDARY_VIOLATION", "Authoring source includes forbidden fields")
    nonempty_string(authoring["title"], label="authoring_source.title")
    nonempty_string(authoring["raw_abstract"], label="authoring_source.raw_abstract")

    sources = preparation["sources"]
    target_path = workspace_relative_path(
        workspace, sources["target_dataset"]["path"], label="target_dataset.path"
    )
    reference_path = workspace_relative_path(
        workspace,
        sources["reference_dataset"]["path"],
        label="reference_dataset.path",
    )
    snapshot = _load_source_snapshot(
        target_path,
        reference_path,
        target_paper_id=preparation["target_identity"]["paper_id"],
        expected_target_sha256=sources["target_dataset"]["sha256"],
        expected_reference_sha256=sources["reference_dataset"]["sha256"],
    )
    reference_rows_identity = [
        {"row_number": row_number, "row_sha256": row_sha256}
        for row_number, _, row_sha256 in snapshot.reference_rows
    ]
    if (
        snapshot.target_row_number != sources["target_dataset"]["row_number"]
        or snapshot.target_row_sha256 != sources["target_dataset"]["row_sha256"]
        or len(snapshot.reference_rows)
        != sources["reference_dataset"]["matching_row_count"]
        or sha256_bytes(canonical_json_bytes(reference_rows_identity))
        != sources["reference_dataset"]["matching_rows_sha256"]
    ):
        fail("SOURCE_DRIFT", "Workshop source rows changed")
    expected_external_ids = [
        {"name": name, "value": value} for name, value in snapshot.external_ids
    ]
    if preparation["target_identity"]["external_ids"] != expected_external_ids:
        fail("SOURCE_DRIFT", "Target external identifiers changed")
    inventory = preparation["validation_source_inventory"]
    if inventory["reference_context_count"] != len(
        snapshot.reference_contexts
    ) or inventory["target_abstract_summary_present"] != bool(
        snapshot.target_row["abstract_summary"]
    ):
        fail("SOURCE_DRIFT", "Workshop validation source inventory changed")
    if (
        authoring["title"] != snapshot.target_row["title"]
        or authoring["raw_abstract"] != snapshot.target_row["abstract"]
    ):
        fail("SOURCE_DRIFT", "Authoring source differs from the target row")
    return preparation, manifest_bytes, snapshot, policy


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
        "required_checks": [
            "target_relevant",
            "allows_multiple_method_families",
            "no_answer_leakage",
            "no_identity_leakage",
        ],
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

    case_root = manifest_path.parent.parent.parent
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
        keys={
            "allows_multiple_method_families",
            "no_answer_leakage",
            "no_identity_leakage",
            "target_relevant",
        },
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


def _load_attempt(workspace: Path, attempt_manifest_path: Path) -> tuple[
    dict[str, Any],
    bytes,
    dict[str, Any],
    bytes,
    dict[str, Any],
    SourceSnapshot,
    LeakagePolicy,
]:
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
    preparation_bytes = read_exact(
        preparation_path,
        attempt["preparation_manifest"]["sha256"],
        label="bound preparation manifest",
    )
    preparation, _, snapshot, policy = _load_bound_preparation(
        workspace, preparation_path
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
    return (
        attempt,
        attempt_bytes,
        derivation,
        candidate_bytes,
        preparation,
        snapshot,
        policy,
    )


def _attempt_history(
    workspace: Path,
    case_root: Path,
    *,
    current_attempt_id: str,
    current_decision: dict[str, Any],
) -> list[dict[str, Any]]:
    attempts_root = case_root / "attempts"
    history: list[dict[str, Any]] = []
    for attempt_root in sorted(attempts_root.iterdir(), key=lambda path: path.name):
        if attempt_root.name.startswith("."):
            continue
        if not attempt_root.is_dir() or attempt_root.is_symlink():
            fail("INVALID_ARTIFACT", "Workshop attempt inventory is invalid")
        manifest_path = attempt_root / "attempt-manifest.json"
        (
            attempt,
            manifest_bytes,
            derivation,
            _,
            _,
            _,
            _,
        ) = _load_attempt(workspace, manifest_path)
        if attempt["case_id"] != case_root.name:
            fail("IDENTITY_MISMATCH", "Attempt inventory crosses case boundaries")
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
        report = _parse_report(
            parse_json_bytes(report_bytes, label="validation report")
        )
        semantic_status = "not_run"
        resolution_path = attempt_root / "resolution/semantic-decision.json"
        if attempt["attempt_id"] == current_attempt_id:
            semantic_status = current_decision["decision"]
        elif resolution_path.is_file():
            previous_decision, _ = read_json(resolution_path, label="semantic decision")
            parsed_decision = _parse_semantic_decision(previous_decision)
            if (
                parsed_decision["attempt_manifest_sha256"]
                != sha256_bytes(manifest_bytes)
                or parsed_decision["candidate_sha256"] != attempt["candidate"]["sha256"]
                or parsed_decision["case_id"] != attempt["case_id"]
            ):
                fail("HASH_MISMATCH", "Prior semantic decision binding is invalid")
            if parsed_decision["reviewer"] == derivation["actor"]:
                fail(
                    "REVIEW_NOT_INDEPENDENT",
                    "Prior Workshop reviewer was not independent",
                )
            semantic_status = parsed_decision["decision"]
        elif (attempt_root / "resolution").exists():
            fail("MISSING_ARTIFACT", "Prior Workshop resolution is incomplete")
        elif report["deterministic_status"] == "pass":
            semantic_status = "pending_independent_review"
        history.append(
            {
                "attempt_id": attempt["attempt_id"],
                "attempt_manifest_sha256": sha256_bytes(manifest_bytes),
                "candidate_sha256": attempt["candidate"]["sha256"],
                "derivation_record_sha256": attempt["derivation_record"]["sha256"],
                "deterministic_status": report["deterministic_status"],
                "failure_rule_ids": sorted(
                    {failure["rule_id"] for failure in report["failures"]}
                ),
                "semantic_status": semantic_status,
                "validation_report_sha256": attempt["validation_report"]["sha256"],
            }
        )
    return history


def approve_workshop(
    workspace_root: Path,
    *,
    attempt_manifest: str,
    semantic_decision: str,
) -> dict[str, Any]:
    workspace = workspace_root.resolve(strict=True)
    attempt_manifest_path = workspace_relative_path(
        workspace, attempt_manifest, label="attempt_manifest"
    )
    resolution_root = attempt_manifest_path.parent / "resolution"
    if resolution_root.exists():
        fail("ARTIFACT_EXISTS", "Workshop attempt is already resolved")
    (
        attempt,
        attempt_bytes,
        derivation,
        candidate_bytes,
        preparation,
        _,
        policy,
    ) = _load_attempt(workspace, attempt_manifest_path)
    if attempt["status"] != "pending_independent_review":
        fail(
            "APPROVAL_FORBIDDEN",
            "Deterministically rejected Workshop cannot be approved",
        )
    decision_path = workspace_relative_path(
        workspace, semantic_decision, label="semantic_decision"
    )
    decision_value, _ = read_json(decision_path, label="semantic decision")
    decision = _parse_semantic_decision(decision_value)
    if decision["case_id"] != attempt["case_id"]:
        fail("IDENTITY_MISMATCH", "Semantic decision case differs")
    if decision["attempt_manifest_sha256"] != sha256_bytes(attempt_bytes):
        fail("HASH_MISMATCH", "Semantic decision binds a different attempt")
    if decision["candidate_sha256"] != attempt["candidate"]["sha256"]:
        fail("HASH_MISMATCH", "Semantic decision binds a different candidate")
    if decision["reviewer"] == derivation["actor"]:
        fail(
            "REVIEW_NOT_INDEPENDENT",
            "Workshop reviewer must differ from the derivation actor",
        )
    if decision["reviewed_at"] <= derivation["completed_at"]:
        fail("INVALID_REVIEW", "Semantic review must follow derivation")

    canonical_decision_bytes = canonical_json_bytes(decision)
    decision_target_path = resolution_root / "semantic-decision.json"
    if decision["decision"] == "rejected":
        resolution_manifest = {
            "attempt_id": attempt["attempt_id"],
            "case_id": attempt["case_id"],
            "resolved_at": _now(),
            "schema_version": WORKSHOP_RESOLUTION_SCHEMA_VERSION,
            "semantic_decision": _artifact_ref(
                decision_target_path, workspace, canonical_decision_bytes
            ),
            "status": "rejected_semantic",
            "workshop": None,
            "workshop_manifest": None,
        }
        write_tree_once(
            resolution_root,
            {
                "semantic-decision.json": canonical_decision_bytes,
                "resolution-manifest.json": canonical_json_bytes(resolution_manifest),
            },
        )
        return {
            "case_id": attempt["case_id"],
            "resolution": relative_posix(
                resolution_root / "resolution-manifest.json", workspace
            ),
            "status": "rejected_semantic",
        }

    case_root = attempt_manifest_path.parent.parent.parent
    if _approved_resolution_exists(case_root):
        fail("WORKSHOP_ALREADY_APPROVED", "This case already has an Approved Workshop")
    approved_workshop_path = resolution_root / f"{attempt['case_id']}.md"
    workshop_manifest_path = resolution_root / "workshop-manifest.json"
    history = _attempt_history(
        workspace,
        case_root,
        current_attempt_id=attempt["attempt_id"],
        current_decision=decision,
    )
    report_value, _ = read_json(
        workspace_relative_path(
            workspace,
            attempt["validation_report"]["path"],
            label="validation_report.path",
        ),
        label="validation report",
    )
    report = _parse_report(report_value)
    workshop_manifest = {
        "approval_status": "approved",
        "approved_at": _now(),
        "attempts": history,
        "case_id": attempt["case_id"],
        "contract_version": WORKSHOP_CONTRACT_VERSION,
        "derivation": derivation,
        "independent_review": {
            "decision_sha256": sha256_bytes(canonical_decision_bytes),
            "rationale": decision["rationale"],
            "reviewed_at": decision["reviewed_at"],
            "reviewer": decision["reviewer"],
        },
        "rules": {
            "normalization_version": policy.normalization_version,
            "policy_sha256": policy.sha256,
            "policy_version": policy.version,
            "validator_version": WORKSHOP_VALIDATOR_VERSION,
        },
        "schema_version": WORKSHOP_MANIFEST_SCHEMA_VERSION,
        "source_allowlist": SOURCE_ALLOWLIST,
        "source_provenance": preparation["sources"],
        "target_identity": preparation["target_identity"],
        "validation": {
            "deterministic_status": report["deterministic_status"],
            "failure_rule_ids": [],
            "lengths": report["lengths"],
            "semantic_status": decision["decision"],
            "validation_report_sha256": attempt["validation_report"]["sha256"],
        },
        "workshop": _artifact_ref(approved_workshop_path, workspace, candidate_bytes),
    }
    workshop_manifest_bytes = canonical_json_bytes(workshop_manifest)
    resolution_manifest = {
        "attempt_id": attempt["attempt_id"],
        "case_id": attempt["case_id"],
        "resolved_at": _now(),
        "schema_version": WORKSHOP_RESOLUTION_SCHEMA_VERSION,
        "semantic_decision": _artifact_ref(
            decision_target_path, workspace, canonical_decision_bytes
        ),
        "status": "approved",
        "workshop": _artifact_ref(approved_workshop_path, workspace, candidate_bytes),
        "workshop_manifest": _artifact_ref(
            workshop_manifest_path, workspace, workshop_manifest_bytes
        ),
    }
    write_tree_once(
        resolution_root,
        {
            "semantic-decision.json": canonical_decision_bytes,
            f"{attempt['case_id']}.md": candidate_bytes,
            "workshop-manifest.json": workshop_manifest_bytes,
            "resolution-manifest.json": canonical_json_bytes(resolution_manifest),
        },
    )
    return {
        "case_id": attempt["case_id"],
        "status": "approved",
        "workshop": relative_posix(approved_workshop_path, workspace),
        "workshop_manifest": relative_posix(workshop_manifest_path, workspace),
        "workshop_manifest_sha256": sha256_bytes(workshop_manifest_bytes),
        "workshop_sha256": sha256_bytes(candidate_bytes),
    }
