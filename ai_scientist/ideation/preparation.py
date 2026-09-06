from __future__ import annotations

import ast
import csv
import io
from pathlib import Path
from typing import Any

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
    REFERENCE_REQUIRED_FIELDS,
    SOURCE_ALLOWLIST,
    TARGET_REQUIRED_FIELDS,
    WORKSHOP_AUTHORING_SOURCE_SCHEMA_VERSION,
    WORKSHOP_CONTRACT_VERSION,
    WORKSHOP_POLICY_PATH,
    WORKSHOP_POLICY_SHA256,
    WORKSHOP_PREPARATION_SCHEMA_VERSION,
    WORKSHOP_VALIDATOR_VERSION,
    LeakagePolicy,
    SourceSnapshot,
    _artifact_ref,
    _now,
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
from .text import NORMALIZATION_VERSION


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
    _assert_frozen_case_binding(workspace, preparation_root.parent.parent, manifest)
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
    workspace: Path,
    manifest_path: Path,
    *,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], bytes, SourceSnapshot, LeakagePolicy]:
    value, manifest_bytes = read_json(manifest_path, label="preparation manifest")
    if expected_sha256 is not None and sha256_bytes(manifest_bytes) != expected_sha256:
        fail(
            "HASH_MISMATCH",
            "bound preparation manifest does not match its approved SHA-256",
        )
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


def _frozen_preparation_binding(preparation: dict[str, Any]) -> dict[str, Any]:
    return {
        "authoring_source_sha256": preparation["authoring_source"]["sha256"],
        "contract_version": preparation["contract_version"],
        "rules": preparation["rules"],
        "source_allowlist": preparation["source_allowlist"],
        "sources": preparation["sources"],
        "target_identity": preparation["target_identity"],
    }


def _assert_frozen_case_binding(
    workspace: Path,
    case_root: Path,
    proposed_preparation: dict[str, Any],
) -> None:
    preparations_root = case_root / "preparations"
    if not preparations_root.exists():
        return
    if not preparations_root.is_dir() or preparations_root.is_symlink():
        fail("INVALID_ARTIFACT", "Workshop preparation inventory is invalid")
    proposed_binding = _frozen_preparation_binding(proposed_preparation)
    for preparation_root in sorted(
        preparations_root.iterdir(), key=lambda path: path.name
    ):
        if preparation_root.name.startswith("."):
            continue
        if not preparation_root.is_dir() or preparation_root.is_symlink():
            fail("INVALID_ARTIFACT", "Workshop preparation inventory is invalid")
        previous, _, _, _ = _load_bound_preparation(
            workspace, preparation_root / "preparation-manifest.json"
        )
        if _frozen_preparation_binding(previous) != proposed_binding:
            fail(
                "FROZEN_SOURCE_MISMATCH",
                "Workshop case is already bound to a different frozen source",
            )
