"""Post-seal qualitative evaluation: brief assembly, artifact validation, coverage.

Implements ticket 12 (contracts 026/032/037):
- assemble_evaluation_brief: reads only a sealed, non-corrupt run's final idea,
  grounding, and retrieval evidence plus the private Target Paper comparator;
  writes a rebuildable brief.md (reading material, overwritable) and a
  linkage pre-filled draft.json skeleton (never clobbered) under
  artifacts/evaluations/<run_id>/ideas/<idea_index>/.
- validate_evaluation_artifact: fail-closed deterministic validation of the
  authored draft (canonical bytes, closed schema, hash linkage, the seven
  approved verdict enums, non-empty rationales, authoring audit, linear
  supersedes); on success commits the immutable write-once v<seq>.json
  Evaluation Artifact. A failed draft never becomes an artifact.
- list_evaluation_coverage: read-only covered/draft_only/missing accounting
  over the seal inventory x artifacts/evaluations/ (VM-QUAL-01). It never
  rewrites run evidence or evaluation artifacts.

Evaluation stays outside the run's Evidence Chain; no numeric score, overall
rating, LLM judgment, or sanitized stub is ever produced (ticket 032 red
lines).
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any

from .admission import WORKSHOP_MANIFEST_NAME
from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
    workspace_relative_path,
)
from .contract import (
    EVALUATION_ARTIFACT_SCHEMA_VERSION,
    EVALUATION_ROOT_RELPATH,
    EVALUATION_RUBRIC_POLICY_PATH,
    EVALUATION_RUBRIC_POLICY_SHA256,
    EVALUATION_RUBRIC_SCHEMA_VERSION,
    _now,
)
from .controller import REQUIRED_IDEA_FIELDS
from .errors import IdeationInputError, fail
from .evidence import validate_evidence_chain
from .preparation import _csv_rows
from .run_store import (
    REQUEST_NAME,
    RUNS_ROOT_RELPATH,
    SEAL_NAME,
    RunStore,
    _fsync_directory,
    _validate_run_id,
)
from .schema import (
    case_id as parse_case_id,
    closed_object,
    nonempty_string,
    sha256 as parse_sha256,
    timestamp,
)

EVALUATION_COVERAGE_SCHEMA_VERSION = "evaluation-coverage-v1.0.0"

BRIEF_NAME = "brief.md"
DRAFT_NAME = "draft.json"
VERSION_NAME_PATTERN = re.compile(r"v(\d{4})\.json\Z")
SUPERSEDES_PATTERN = re.compile(r"v\d{4}\.json\Z")
IDEA_INVENTORY_PATTERN = re.compile(r"artifacts/ideas/(\d{6})/idea\.json\Z")

DRAFT_AUDIT_KEYS = frozenset(
    {
        "assembled_at",
        "assembled_by",
        "authored_at",
        "authored_by",
        "brief_sha256",
    }
)
FINAL_AUDIT_KEYS = DRAFT_AUDIT_KEYS | {
    "validated_at",
    "validated_by",
    "validation_result",
}


@dataclass(frozen=True, slots=True)
class RubricPolicy:
    """The pinned, versioned Idea Quality Rubric (tickets 026/037)."""

    version: str
    criteria: tuple[tuple[str, tuple[str, ...]], ...]
    sha256: str


@dataclass(frozen=True, slots=True)
class TargetComparator:
    """The private Target Paper comparator derived from the Workshop Manifest."""

    reference: dict[str, Any]
    abstract_summary: str
    raw_abstract: str


@dataclass(frozen=True, slots=True)
class RunContext:
    """A validated, sealed, non-corrupt run's evaluation-relevant linkage."""

    store: RunStore
    seal_document: dict[str, Any]
    seal_sha256: str
    terminal_outcome: str
    case_id: str
    workshop: dict[str, str]


def _load_rubric_policy(workspace: Path) -> RubricPolicy:
    path = workspace / EVALUATION_RUBRIC_POLICY_PATH
    if not path.is_file():
        fail("MISSING_ARTIFACT", "Idea quality rubric policy is missing")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != EVALUATION_RUBRIC_POLICY_SHA256:
        fail("POLICY_DRIFT", "Idea quality rubric policy hash changed")
    value = parse_json_bytes(data, label="idea quality rubric policy")
    policy = closed_object(
        value,
        label="idea quality rubric policy",
        keys={"criteria", "schema_version", "version"},
    )
    if policy["schema_version"] != EVALUATION_RUBRIC_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Idea quality rubric policy schema is unsupported")
    version = nonempty_string(policy["version"], label="rubric.version")
    criteria_value = policy["criteria"]
    if not isinstance(criteria_value, list) or not criteria_value:
        fail("INVALID_SCHEMA", "rubric.criteria must be a non-empty array")
    criteria: list[tuple[str, tuple[str, ...]]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(criteria_value):
        entry = closed_object(
            item, label=f"rubric.criteria[{index}]", keys={"id", "verdicts"}
        )
        criterion_id = nonempty_string(
            entry["id"], label=f"rubric.criteria[{index}].id"
        )
        if criterion_id in seen_ids:
            fail("INVALID_SCHEMA", f"Duplicate rubric criterion: {criterion_id}")
        seen_ids.add(criterion_id)
        verdicts = entry["verdicts"]
        if not isinstance(verdicts, list) or not verdicts:
            fail(
                "INVALID_SCHEMA",
                f"rubric.criteria[{index}].verdicts must be a non-empty array",
            )
        parsed_verdicts = tuple(
            nonempty_string(v, label=f"rubric.criteria[{index}].verdicts")
            for v in verdicts
        )
        criteria.append((criterion_id, parsed_verdicts))
    return RubricPolicy(version=version, criteria=tuple(criteria), sha256=digest)


def _validate_idea_index(idea_index: object) -> int:
    if (
        not isinstance(idea_index, int)
        or isinstance(idea_index, bool)
        or idea_index < 0
        or idea_index > 999999
    ):
        fail(
            "INVALID_COORDINATE",
            "idea_index must be an integer between 0 and 999999",
        )
    return idea_index


def _load_run_context(workspace: Path, run_id: str) -> RunContext:
    """Prove the run is sealed and non-corrupt, then load evaluation linkage."""
    validate_evidence_chain(workspace, run_id, check_sealed=True)
    store = RunStore(workspace)
    run_root = workspace / RUNS_ROOT_RELPATH / run_id
    seal_bytes = (run_root / SEAL_NAME).read_bytes()
    seal_document = parse_json_bytes(seal_bytes, label="seal.json")
    if not isinstance(seal_document, dict):
        fail("RUN_CORRUPT", "seal.json is not a JSON object")
    request_value = parse_json_bytes(
        (run_root / REQUEST_NAME).read_bytes(), label="request.json"
    )
    if not isinstance(request_value, dict):
        fail("RUN_CORRUPT", "request.json is not a JSON object")
    workshop_value = request_value.get("workshop")
    if not isinstance(workshop_value, dict):
        fail("RUN_CORRUPT", "request.json lacks the workshop binding")
    workshop = closed_object(
        workshop_value, label="request.workshop", keys={"path", "sha256"}
    )
    return RunContext(
        store=store,
        seal_document=seal_document,
        seal_sha256=sha256_bytes(seal_bytes),
        terminal_outcome=seal_document["terminal_outcome"],
        case_id=parse_case_id(request_value.get("case_id")),
        workshop={
            "path": nonempty_string(workshop["path"], label="request.workshop.path"),
            "sha256": parse_sha256(workshop["sha256"], label="request.workshop.sha256"),
        },
    )


def _load_workshop_manifest(workspace: Path, context: RunContext) -> dict[str, Any]:
    """Re-verify the Approved Workshop binding exactly as admission did."""
    workshop_path = workspace_relative_path(
        workspace, context.workshop["path"], label="workshop_path"
    )
    if not workshop_path.is_file():
        fail("MISSING_ARTIFACT", "The pinned Workshop file is missing")
    if sha256_bytes(workshop_path.read_bytes()) != context.workshop["sha256"]:
        fail("HASH_MISMATCH", "Workshop bytes do not match the pinned SHA-256")
    manifest_path = workshop_path.parent / WORKSHOP_MANIFEST_NAME
    if not manifest_path.is_file():
        fail("WORKSHOP_NOT_APPROVED", "The pinned Workshop has no approval manifest")
    manifest_value = parse_json_bytes(
        manifest_path.read_bytes(), label="workshop manifest"
    )
    if not isinstance(manifest_value, dict):
        fail("INVALID_SCHEMA", "workshop manifest must be a JSON object")
    if manifest_value.get("approval_status") != "approved":
        fail("WORKSHOP_NOT_APPROVED", "The pinned Workshop is not approved")
    if manifest_value.get("case_id") != context.case_id:
        fail("IDENTITY_MISMATCH", "The Workshop belongs to another case")
    workshop_ref = manifest_value.get("workshop")
    if not isinstance(workshop_ref, dict):
        fail("INVALID_SCHEMA", "workshop manifest.workshop must be a JSON object")
    if workshop_ref.get("sha256") != context.workshop["sha256"]:
        fail("HASH_MISMATCH", "Workshop manifest does not bind the pinned bytes")
    return manifest_value


def _derive_target_comparator(
    workspace: Path, manifest: dict[str, Any]
) -> TargetComparator:
    """Derive the Target Paper reference from the Workshop Manifest and verify
    the pinned source dataset row on disk (fail closed on any drift)."""
    identity = closed_object(
        manifest.get("target_identity"),
        label="workshop manifest.target_identity",
        keys={"external_ids", "paper_id"},
    )
    paper_id = nonempty_string(identity["paper_id"], label="target_identity.paper_id")
    external_ids = identity["external_ids"]
    if not isinstance(external_ids, list):
        fail("INVALID_SCHEMA", "target_identity.external_ids must be an array")
    doi_values = []
    for index, item in enumerate(external_ids):
        entry = closed_object(
            item, label=f"target_identity.external_ids[{index}]", keys={"name", "value"}
        )
        if entry["name"] == "DOI":
            doi_values.append(
                nonempty_string(
                    entry["value"], label=f"target_identity.external_ids[{index}].value"
                )
            )
    if len(doi_values) != 1:
        fail("INVALID_SOURCE", "Target identity must carry exactly one DOI")

    provenance = closed_object(
        manifest.get("source_provenance"),
        label="workshop manifest.source_provenance",
        keys={"reference_dataset", "target_dataset"},
    )
    target_source = closed_object(
        provenance["target_dataset"],
        label="source_provenance.target_dataset",
        keys={"path", "row_number", "row_sha256", "sha256"},
    )
    dataset_path_value = nonempty_string(
        target_source["path"], label="target_dataset.path"
    )
    dataset_sha256 = parse_sha256(
        target_source["sha256"], label="target_dataset.sha256"
    )
    row_sha256 = parse_sha256(
        target_source["row_sha256"], label="target_dataset.row_sha256"
    )
    dataset_path = workspace_relative_path(
        workspace, dataset_path_value, label="target_dataset.path"
    )
    if not dataset_path.is_file():
        fail("MISSING_ARTIFACT", "Target source dataset is missing")
    dataset_bytes = dataset_path.read_bytes()
    if sha256_bytes(dataset_bytes) != dataset_sha256:
        fail("HASH_MISMATCH", "Target dataset bytes do not match the pinned SHA-256")
    _, rows = _csv_rows(dataset_bytes, label="target dataset")
    matches = [row for row in rows if row.get("paperId") == paper_id]
    if len(matches) != 1:
        fail(
            "INVALID_SOURCE",
            "Target paper identity must resolve to exactly one row",
            match_count=len(matches),
        )
    row = matches[0]
    if sha256_bytes(canonical_json_bytes(row)) != row_sha256:
        fail("HASH_MISMATCH", "Target row does not match the pinned row SHA-256")
    title = nonempty_string(row.get("title"), label="target.title")
    abstract_summary = nonempty_string(
        row.get("abstract_summary"), label="target.abstract_summary"
    )
    raw_abstract = nonempty_string(row.get("abstract"), label="target.abstract")
    return TargetComparator(
        reference={
            "dataset_path": dataset_path_value,
            "dataset_sha256": dataset_sha256,
            "doi": doi_values[0],
            "row_sha256": row_sha256,
            "title": title,
        },
        abstract_summary=abstract_summary,
        raw_abstract=raw_abstract,
    )


def _inventory_index(seal_document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inventory = seal_document.get("artifact_inventory")
    if not isinstance(inventory, list):
        fail("RUN_CORRUPT", "seal.json artifact_inventory must be a list")
    return {item["relative_path"]: item for item in inventory if isinstance(item, dict)}


def _load_idea_evidence(
    context: RunContext, run_id: str, idea_index: int
) -> tuple[dict[str, Any], list[str], dict[str, Any], dict[str, Any]]:
    """Load the finalized idea payload, declared grounding, and sidecar,
    each verified against the seal inventory entry bytes."""
    inventory = _inventory_index(context.seal_document)
    base = f"artifacts/ideas/{idea_index:06d}"
    idea_rel = f"{base}/idea.json"
    idea_entry = inventory.get(idea_rel)
    if idea_entry is None:
        fail(
            "EVALUATION_IDEA_NOT_FOUND",
            f"No finalized idea with idea_index {idea_index} in the seal inventory",
        )
    for name in ("grounding.json", "sidecar.json"):
        if f"{base}/{name}" not in inventory:
            fail(
                "MISSING_ARTIFACT",
                f"Seal inventory lacks {name} for idea {idea_index}",
            )
    idea_bytes = context.store.read_artifact(
        run_id, idea_rel, idea_entry["sha256"], label="finalized idea"
    )
    idea_value = parse_json_bytes(idea_bytes, label="finalized idea")
    if not isinstance(idea_value, dict):
        fail("RUN_CORRUPT", "Finalized idea payload is not a JSON object")
    for field in REQUIRED_IDEA_FIELDS:
        if field not in idea_value:
            fail(
                "RUN_CORRUPT",
                f"Finalized idea payload violates the seven-field contract: {field}",
            )
        field_value = idea_value[field]
        if field in ("Experiments", "Risk Factors and Limitations"):
            if not isinstance(field_value, list) or not all(
                isinstance(item, str) for item in field_value
            ):
                fail(
                    "RUN_CORRUPT",
                    f"Finalized idea field {field} is not a list of strings",
                )
        elif not isinstance(field_value, str):
            fail("RUN_CORRUPT", f"Finalized idea field {field} is not a string")
    grounding_rel = f"{base}/grounding.json"
    grounding_bytes = context.store.read_artifact(
        run_id,
        grounding_rel,
        inventory[grounding_rel]["sha256"],
        label="declared grounding",
    )
    grounding_value = parse_json_bytes(grounding_bytes, label="declared grounding")
    if not isinstance(grounding_value, list) or not all(
        isinstance(item, str) for item in grounding_value
    ):
        fail("RUN_CORRUPT", "Declared grounding is not a list of paper ids")
    sidecar_rel = f"{base}/sidecar.json"
    sidecar_bytes = context.store.read_artifact(
        run_id,
        sidecar_rel,
        inventory[sidecar_rel]["sha256"],
        label="idea sidecar",
    )
    sidecar_value = parse_json_bytes(sidecar_bytes, label="idea sidecar")
    if not isinstance(sidecar_value, dict):
        fail("RUN_CORRUPT", "Idea sidecar is not a JSON object")
    return idea_value, list(grounding_value), sidecar_value, idea_entry


def _collect_release_record(
    context: RunContext, run_id: str, sidecar: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Collect, for every paper returned by the sidecar-bound retrieval
    operations, the exact segment excerpts the model saw — the complete
    per-paper release record, not limited to declared grounding papers."""
    operation_seqs = sidecar.get("retrieval_operation_seqs")
    if not isinstance(operation_seqs, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in operation_seqs
    ):
        fail("RUN_CORRUPT", "Idea sidecar retrieval_operation_seqs is invalid")
    wanted = set(operation_seqs)
    released: dict[str, list[dict[str, Any]]] = {}
    seen_operations: set[int] = set()
    for event in context.store.read_events(run_id):
        if event.get("event_type") != "operation.finished":
            continue
        operation = event.get("operation")
        if not isinstance(operation, dict):
            continue
        if operation.get("operation_kind") != "literature_retrieval":
            continue
        operation_seq = operation.get("operation_seq")
        if (
            not isinstance(operation_seq, int)
            or isinstance(operation_seq, bool)
            or operation_seq not in wanted
        ):
            continue
        seen_operations.add(operation_seq)
        artifact_refs = event.get("artifact_refs")
        if not isinstance(artifact_refs, list):
            fail(
                "RUN_CORRUPT",
                f"Retrieval operation {operation_seq} event artifact_refs is invalid",
            )
        payload_ref = None
        for ref in artifact_refs:
            if isinstance(ref, dict) and ref.get("role") == "model_payload":
                payload_ref = ref
                break
        if payload_ref is None:
            fail(
                "EVALUATION_LINKAGE_INCONSISTENT",
                f"Retrieval operation {operation_seq} lacks a model payload ref",
            )
        relative_path = payload_ref.get("relative_path")
        payload_sha256 = payload_ref.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(payload_sha256, str):
            fail(
                "RUN_CORRUPT",
                f"Retrieval operation {operation_seq} model payload ref is malformed",
            )
        payload_bytes = context.store.read_artifact(
            run_id,
            relative_path,
            payload_sha256,
            label="retrieval payload",
        )
        payload_value = parse_json_bytes(payload_bytes, label="retrieval payload")
        if not isinstance(payload_value, dict):
            fail("RUN_CORRUPT", "Retrieval payload is not a JSON object")
        papers = payload_value.get("papers")
        if not isinstance(papers, list):
            fail("RUN_CORRUPT", "Retrieval payload papers is not an array")
        for paper in papers:
            if not isinstance(paper, dict):
                fail("RUN_CORRUPT", "Retrieval payload paper is not a JSON object")
            paper_id = paper.get("paper_id")
            if not isinstance(paper_id, str):
                continue
            title = paper.get("title")
            if not isinstance(title, str):
                fail("RUN_CORRUPT", "Retrieval payload paper title is not a string")
            segments = paper.get("segments")
            if not isinstance(segments, list):
                fail("RUN_CORRUPT", "Retrieval payload segments are not an array")
            collected_segments: list[dict[str, str]] = []
            for segment in segments:
                if not isinstance(segment, dict):
                    fail(
                        "RUN_CORRUPT",
                        "Retrieval payload segment is not a JSON object",
                    )
                content_type = segment.get("content_type")
                text = segment.get("text")
                if not isinstance(content_type, str) or not isinstance(text, str):
                    fail("RUN_CORRUPT", "Retrieval payload segment is malformed")
                collected_segments.append({"content_type": content_type, "text": text})
            released.setdefault(paper_id, []).append(
                {
                    "operation_seq": operation_seq,
                    "segments": collected_segments,
                    "title": title,
                }
            )
    if seen_operations != wanted:
        fail(
            "EVALUATION_LINKAGE_INCONSISTENT",
            "Sidecar retrieval operations are missing from the event chain",
            missing=sorted(wanted - seen_operations),
        )
    return released


def _collect_retrieval_excerpts(
    context: RunContext, run_id: str, sidecar: dict[str, Any], grounding: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """Collect, per declared paper, the exact segment excerpts the model saw,
    from the retrieval payloads referenced by the event chain."""
    released = _collect_release_record(context, run_id, sidecar)
    excerpts: dict[str, list[dict[str, Any]]] = {}
    for paper_id in grounding:
        occurrences = released.get(paper_id)
        if not occurrences:
            fail(
                "EVALUATION_LINKAGE_INCONSISTENT",
                f"Declared grounding paper {paper_id} appears in no retrieval payload",
            )
        excerpts[paper_id] = occurrences
    return excerpts


def _render_brief(
    *,
    run_id: str,
    context: RunContext,
    idea_index: int,
    idea_entry: dict[str, Any],
    idea: dict[str, Any],
    grounding: list[str],
    excerpts: dict[str, list[dict[str, Any]]],
    target: TargetComparator,
    rubric: RubricPolicy,
) -> bytes:
    """Render the deterministic Evaluation Brief (no timestamps, LF endings)."""
    lines: list[str] = []
    lines.append("# Evaluation Brief")
    lines.append("")
    lines.append(
        "Reading material for the post-seal qualitative evaluation of one "
        "finalized idea. Not evidence; regenerate by re-running "
        "`evaluation assemble`."
    )
    lines.append("")
    lines.append("## Linkage")
    lines.append("")
    lines.append(f"- run_id: `{run_id}`")
    lines.append(f"- case_id: `{context.case_id}`")
    lines.append(f"- terminal_outcome: `{context.terminal_outcome}`")
    lines.append(f"- seal_sha256: `{context.seal_sha256}`")
    lines.append(f"- idea_index: {idea_index}")
    lines.append(f"- idea_artifact: `{idea_entry['relative_path']}`")
    lines.append(f"- idea_sha256: `{idea_entry['sha256']}`")
    lines.append(f"- target_title: {target.reference['title']}")
    lines.append(f"- target_doi: {target.reference['doi']}")
    lines.append(f"- target_dataset: `{target.reference['dataset_path']}`")
    lines.append(f"- target_dataset_sha256: `{target.reference['dataset_sha256']}`")
    lines.append(f"- target_row_sha256: `{target.reference['row_sha256']}`")
    lines.append(f"- rubric_version: `{rubric.version}`")
    lines.append("")
    lines.append("## Finalized Idea")
    for field in (
        "Name",
        "Title",
        "Short Hypothesis",
        "Related Work",
        "Abstract",
    ):
        lines.append("")
        lines.append(f"### {field}")
        lines.append("")
        lines.append(str(idea[field]))
    for field in ("Experiments", "Risk Factors and Limitations"):
        lines.append("")
        lines.append(f"### {field}")
        lines.append("")
        for position, item in enumerate(idea[field], start=1):
            lines.append(f"{position}. {item}")
    lines.append("")
    lines.append("## Declared Grounding")
    lines.append("")
    for paper_id in grounding:
        lines.append(f"- `{paper_id}`")
    lines.append("")
    lines.append("## Retrieval Excerpts (as released to the model)")
    for paper_id in grounding:
        lines.append("")
        occurrences = excerpts[paper_id]
        first_title = occurrences[0]["title"]
        lines.append(f"### `{paper_id}` — {first_title}")
        for occurrence in occurrences:
            lines.append("")
            lines.append(f"Retrieval operation {occurrence['operation_seq']}:")
            lines.append("")
            for segment in occurrence["segments"]:
                lines.append(f"- [{segment['content_type']}] {segment['text']}")
    lines.append("")
    lines.append("## Target Paper Comparator")
    lines.append("")
    lines.append(f"Title: {target.reference['title']}")
    lines.append(f"DOI: {target.reference['doi']}")
    lines.append("")
    lines.append("### abstract_summary (official ground-truth anchor)")
    lines.append("")
    lines.append(target.abstract_summary)
    lines.append("")
    lines.append("### Full abstract")
    lines.append("")
    lines.append(target.raw_abstract)
    lines.append("")
    lines.append(f"## Judgment Form (rubric `{rubric.version}`)")
    lines.append("")
    lines.append(
        "Fill `draft.json` next to this brief: for each criterion set `verdict` "
        "(closed enum) and `rationale` (1-3 sentences), then set "
        "`audit.authored_by` and `audit.authored_at`. No numeric scores and no "
        "overall rating."
    )
    lines.append("")
    for position, (criterion_id, verdicts) in enumerate(rubric.criteria, start=1):
        joined = ", ".join(f"`{verdict}`" for verdict in verdicts)
        lines.append(f"{position}. `{criterion_id}` — one of {joined}")
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _evaluation_idea_dir(workspace: Path, run_id: str, idea_index: int) -> Path:
    """Resolve the evaluation idea directory with per-component symlink guards."""
    current = workspace
    for part in (
        *EVALUATION_ROOT_RELPATH.parts,
        run_id,
        "ideas",
        f"{idea_index:06d}",
    ):
        current = current / part
        if current.is_symlink():
            fail(
                "SYMLINK_FORBIDDEN",
                f"Evaluation path component is a symlink: {current.name}",
            )
    return current


def _write_bytes_overwrite(path: Path, data: bytes, *, label: str) -> None:
    """Write `data` over `path` (brief.md is regenerable reading material)."""
    if path.is_symlink():
        fail("SYMLINK_FORBIDDEN", f"{label} is a symlink")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot write {label}: {detail}")


def _write_bytes_once(path: Path, data: bytes, *, label: str) -> None:
    """Write `data` exclusively; existing targets fail closed (write-once)."""
    if path.is_symlink():
        fail("SYMLINK_FORBIDDEN", f"{label} is a symlink")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fail("ARTIFACT_EXISTS", f"{label} already exists and cannot be overwritten")
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot write {label}: {detail}")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot write {label}: {detail}")


def _existing_versions(
    idea_dir: Path,
    *,
    pattern: re.Pattern[str] = VERSION_NAME_PATTERN,
    label: str = "Evaluation artifact",
) -> list[tuple[int, str]]:
    """List finalized artifact versions as (seq, filename), ascending."""
    if not idea_dir.is_dir():
        return []
    versions: list[tuple[int, str]] = []
    for path in idea_dir.iterdir():
        if path.is_symlink():
            fail("SYMLINK_FORBIDDEN", f"{label} is a symlink: {path.name}")
        if not path.is_file():
            continue
        match = pattern.fullmatch(path.name)
        if match:
            versions.append((int(match.group(1)), path.name))
    versions.sort()
    return versions


def _check_supersedes(
    value: object,
    *,
    expected_name: str | None,
    idea_dir: Path,
    run_id: str,
    idea_index: int,
) -> None:
    """Linear supersedes: the target exists, is same run/idea, and is the
    latest not-yet-superseded version (contract 037.7/037.8)."""
    if value is None:
        if expected_name is not None:
            fail(
                "EVALUATION_SUPERSEDES_INVALID",
                "A correction must supersede the current latest version "
                f"{expected_name}",
            )
        return
    if not isinstance(value, str) or not SUPERSEDES_PATTERN.fullmatch(value):
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            "supersedes must be null or a version filename like v0001.json",
        )
    if value != expected_name:
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            "Only the latest not-yet-superseded version can be superseded",
            expected=expected_name,
            actual=value,
        )
    target_path = idea_dir / value
    if not target_path.is_file() or target_path.is_symlink():
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            f"supersedes target does not exist: {value}",
        )
    target_value = parse_json_bytes(
        target_path.read_bytes(), label=f"supersedes target {value}"
    )
    if not isinstance(target_value, dict):
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            f"supersedes target is not an Evaluation Artifact: {value}",
        )
    if (
        target_value.get("run_id") != run_id
        or not isinstance(target_value.get("idea"), dict)
        or target_value["idea"].get("idea_index") != idea_index
    ):
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            "supersedes target belongs to another run or idea",
        )


def _check_judgments(value: object, rubric: RubricPolicy) -> None:
    """Seven criteria, approved closed verdict enums, non-empty rationales."""
    judgments = closed_object(
        value,
        label="judgments",
        keys={criterion_id for criterion_id, _ in rubric.criteria},
    )
    verdict_map = dict(rubric.criteria)
    for criterion_id, _ in rubric.criteria:
        judgment = closed_object(
            judgments[criterion_id],
            label=f"judgments.{criterion_id}",
            keys={"rationale", "verdict"},
        )
        verdict = judgment["verdict"]
        if not isinstance(verdict, str) or verdict not in verdict_map[criterion_id]:
            fail(
                "INVALID_SCHEMA",
                f"judgments.{criterion_id}.verdict must be one of "
                f"{list(verdict_map[criterion_id])}",
            )
        rationale = judgment["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            fail(
                "INVALID_SCHEMA",
                f"judgments.{criterion_id}.rationale must be a non-empty string",
            )


def _check_artifact_document(
    document: object,
    *,
    mode: str,
    run_id: str,
    context: RunContext,
    idea_index: int,
    idea_entry: dict[str, Any],
    target: TargetComparator,
    rubric: RubricPolicy,
    expected_supersedes: str | None,
    idea_dir: Path,
    brief_sha256_on_disk: str | None,
) -> dict[str, Any]:
    """The deterministic, fail-closed Evaluation Artifact validation core.

    mode "draft" validates an authored draft (validated_* fields forbidden,
    on-disk brief hash enforced); mode "final" validates a finalized artifact
    (validated_* fields required, brief hash self-contained).
    """
    artifact = closed_object(
        document,
        label="evaluation artifact",
        keys={
            "audit",
            "case_id",
            "idea",
            "judgments",
            "rubric_version",
            "run_id",
            "schema_version",
            "seal_sha256",
            "supersedes",
            "target_paper",
        },
    )
    if artifact["schema_version"] != EVALUATION_ARTIFACT_SCHEMA_VERSION:
        fail(
            "UNSUPPORTED_SCHEMA",
            f"Unsupported evaluation artifact schema_version: "
            f"{artifact['schema_version']}",
        )
    if artifact["rubric_version"] != rubric.version:
        fail(
            "RUBRIC_VERSION_NOT_APPROVED",
            f"rubric_version is not an approved version: {artifact['rubric_version']}",
        )
    if artifact["run_id"] != run_id:
        fail("IDENTITY_MISMATCH", "Evaluation artifact belongs to another run")
    if artifact["case_id"] != context.case_id:
        fail("IDENTITY_MISMATCH", "Evaluation artifact belongs to another case")
    if artifact["seal_sha256"] != context.seal_sha256:
        fail("HASH_MISMATCH", "Evaluation artifact does not bind the current seal")

    idea_link = closed_object(
        artifact["idea"],
        label="idea",
        keys={"idea_index", "relative_path", "sha256"},
    )
    if idea_link["idea_index"] != idea_index:
        fail("IDENTITY_MISMATCH", "Evaluation artifact belongs to another idea")
    if (
        idea_link["relative_path"] != idea_entry["relative_path"]
        or idea_link["sha256"] != idea_entry["sha256"]
    ):
        fail(
            "HASH_MISMATCH",
            "Evaluation artifact idea linkage does not match the seal inventory",
        )

    target_link = closed_object(
        artifact["target_paper"],
        label="target_paper",
        keys={"dataset_path", "dataset_sha256", "doi", "row_sha256", "title"},
    )
    for field in ("dataset_path", "doi", "title"):
        if target_link[field] != target.reference[field]:
            fail(
                "IDENTITY_MISMATCH",
                f"Evaluation artifact target_paper.{field} does not match the "
                "Workshop Manifest record",
            )
    for field in ("dataset_sha256", "row_sha256"):
        if target_link[field] != target.reference[field]:
            fail(
                "HASH_MISMATCH",
                f"Evaluation artifact target_paper.{field} does not match the "
                "Workshop Manifest record",
            )

    _check_supersedes(
        artifact["supersedes"],
        expected_name=expected_supersedes,
        idea_dir=idea_dir,
        run_id=run_id,
        idea_index=idea_index,
    )
    _check_judgments(artifact["judgments"], rubric)

    expected_audit_keys = DRAFT_AUDIT_KEYS if mode == "draft" else FINAL_AUDIT_KEYS
    audit = closed_object(
        artifact["audit"], label="audit", keys=set(expected_audit_keys)
    )
    nonempty_string(audit["assembled_by"], label="audit.assembled_by")
    timestamp(audit["assembled_at"], label="audit.assembled_at")
    brief_sha256 = parse_sha256(audit["brief_sha256"], label="audit.brief_sha256")
    if mode == "draft":
        if brief_sha256_on_disk is None:
            fail(
                "MISSING_ARTIFACT",
                "brief.md is missing; re-run evaluation assemble before validating",
            )
        if brief_sha256 != brief_sha256_on_disk:
            fail(
                "HASH_MISMATCH",
                "The brief on disk is not the brief this draft was assembled from",
            )
    nonempty_string(audit["authored_by"], label="audit.authored_by")
    timestamp(audit["authored_at"], label="audit.authored_at")
    if mode == "final":
        nonempty_string(audit["validated_by"], label="audit.validated_by")
        timestamp(audit["validated_at"], label="audit.validated_at")
        if audit["validation_result"] != "passed":
            fail(
                "INVALID_SCHEMA",
                "audit.validation_result must be 'passed' on a finalized artifact",
            )
    return artifact


def _load_context_and_comparator(
    workspace_root: Path, run_id: str
) -> tuple[Path, RunContext, TargetComparator, RubricPolicy]:
    workspace = workspace_root.resolve(strict=True)
    _validate_run_id(run_id)
    context = _load_run_context(workspace, run_id)
    rubric = _load_rubric_policy(workspace)
    manifest = _load_workshop_manifest(workspace, context)
    target = _derive_target_comparator(workspace, manifest)
    return workspace, context, target, rubric


def assemble_evaluation_brief(
    workspace_root: Path,
    run_id: str,
    idea_index: int,
    *,
    assembled_by: str,
) -> dict[str, Any]:
    """Assemble the private Evaluation Brief and the pre-filled draft skeleton.

    Reads only the sealed, non-corrupt run's evidence and the private Target
    Paper comparator. brief.md is regenerated on every call; an existing
    draft.json (Robert's in-progress work) is never overwritten.
    """
    idea_index = _validate_idea_index(idea_index)
    assembled_by = nonempty_string(assembled_by, label="assembled_by")
    workspace, context, target, rubric = _load_context_and_comparator(
        workspace_root, run_id
    )
    idea, grounding, sidecar, idea_entry = _load_idea_evidence(
        context, run_id, idea_index
    )
    excerpts = _collect_retrieval_excerpts(context, run_id, sidecar, grounding)

    brief_bytes = _render_brief(
        run_id=run_id,
        context=context,
        idea_index=idea_index,
        idea_entry=idea_entry,
        idea=idea,
        grounding=grounding,
        excerpts=excerpts,
        target=target,
        rubric=rubric,
    )
    brief_sha256 = sha256_bytes(brief_bytes)

    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    try:
        idea_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create evaluation directory: {detail}")
    _write_bytes_overwrite(idea_dir / BRIEF_NAME, brief_bytes, label=BRIEF_NAME)

    versions = _existing_versions(idea_dir)
    supersedes = versions[-1][1] if versions else None

    draft_path = idea_dir / DRAFT_NAME
    if draft_path.exists():
        draft_status = "existing_kept"
    else:
        draft = {
            "audit": {
                "assembled_at": _now(),
                "assembled_by": assembled_by,
                "authored_at": None,
                "authored_by": None,
                "brief_sha256": brief_sha256,
            },
            "case_id": context.case_id,
            "idea": {
                "idea_index": idea_index,
                "relative_path": idea_entry["relative_path"],
                "sha256": idea_entry["sha256"],
            },
            "judgments": {
                criterion_id: {"rationale": None, "verdict": None}
                for criterion_id, _ in rubric.criteria
            },
            "rubric_version": rubric.version,
            "run_id": run_id,
            "schema_version": EVALUATION_ARTIFACT_SCHEMA_VERSION,
            "seal_sha256": context.seal_sha256,
            "supersedes": supersedes,
            "target_paper": target.reference,
        }
        _write_bytes_once(draft_path, canonical_json_bytes(draft), label=DRAFT_NAME)
        draft_status = "created"

    return {
        "brief": (
            EVALUATION_ROOT_RELPATH
            / run_id
            / "ideas"
            / f"{idea_index:06d}"
            / BRIEF_NAME
        ).as_posix(),
        "brief_sha256": brief_sha256,
        "case_id": context.case_id,
        "draft": (
            EVALUATION_ROOT_RELPATH
            / run_id
            / "ideas"
            / f"{idea_index:06d}"
            / DRAFT_NAME
        ).as_posix(),
        "draft_status": draft_status,
        "idea_index": idea_index,
        "run_id": run_id,
        "status": "assembled",
        "supersedes": supersedes,
        "terminal_outcome": context.terminal_outcome,
    }


def validate_evaluation_artifact(
    workspace_root: Path,
    run_id: str,
    idea_index: int,
    *,
    validated_by: str,
) -> dict[str, Any]:
    """Validate the authored draft and commit the immutable Evaluation Artifact.

    Every rule is deterministic and fail-closed (contract 037.8): any failure
    produces no finalized artifact and leaves the draft untouched.
    """
    idea_index = _validate_idea_index(idea_index)
    validated_by = nonempty_string(validated_by, label="validated_by")
    workspace, context, target, rubric = _load_context_and_comparator(
        workspace_root, run_id
    )
    _, _, _, idea_entry = _load_idea_evidence(context, run_id, idea_index)

    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    draft_path = idea_dir / DRAFT_NAME
    if not draft_path.is_file() or draft_path.is_symlink():
        fail(
            "EVALUATION_DRAFT_NOT_FOUND",
            f"No draft.json for idea {idea_index}; run evaluation assemble first",
        )
    draft = parse_json_bytes(draft_path.read_bytes(), label="evaluation draft")

    versions = _existing_versions(idea_dir)
    expected_supersedes = versions[-1][1] if versions else None
    new_seq = (versions[-1][0] + 1) if versions else 1

    brief_path = idea_dir / BRIEF_NAME
    brief_sha256_on_disk = (
        sha256_bytes(brief_path.read_bytes())
        if brief_path.is_file() and not brief_path.is_symlink()
        else None
    )

    checked = _check_artifact_document(
        draft,
        mode="draft",
        run_id=run_id,
        context=context,
        idea_index=idea_index,
        idea_entry=idea_entry,
        target=target,
        rubric=rubric,
        expected_supersedes=expected_supersedes,
        idea_dir=idea_dir,
        brief_sha256_on_disk=brief_sha256_on_disk,
    )

    final_document = {
        **checked,
        "audit": {
            **checked["audit"],
            "validated_at": _now(),
            "validated_by": validated_by,
            "validation_result": "passed",
        },
    }
    version_name = f"v{new_seq:04d}.json"
    artifact_bytes = canonical_json_bytes(final_document)
    _write_bytes_once(idea_dir / version_name, artifact_bytes, label=version_name)

    return {
        "artifact": (
            EVALUATION_ROOT_RELPATH
            / run_id
            / "ideas"
            / f"{idea_index:06d}"
            / version_name
        ).as_posix(),
        "artifact_sha256": sha256_bytes(artifact_bytes),
        "idea_index": idea_index,
        "run_id": run_id,
        "status": "validated",
        "supersedes": expected_supersedes,
        "version": version_name,
    }


def _idea_coverage(
    workspace: Path,
    context: RunContext,
    target: TargetComparator,
    rubric: RubricPolicy,
    run_id: str,
    idea_index: int,
    idea_entry: dict[str, Any],
) -> dict[str, Any]:
    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    draft_path = idea_dir / DRAFT_NAME
    draft_present = draft_path.is_file() and not draft_path.is_symlink()
    versions = _existing_versions(idea_dir)

    head_version: str | None = None
    head_sha256: str | None = None
    head_error: dict[str, str] | None = None
    covered = False
    if versions:
        head_seq, head_version = versions[-1]
        head_path = idea_dir / head_version
        head_sha256 = sha256_bytes(head_path.read_bytes())
        expected_supersedes = f"v{head_seq - 1:04d}.json" if head_seq > 1 else None
        try:
            document = parse_json_bytes(
                head_path.read_bytes(), label=f"evaluation artifact {head_version}"
            )
            _check_artifact_document(
                document,
                mode="final",
                run_id=run_id,
                context=context,
                idea_index=idea_index,
                idea_entry=idea_entry,
                target=target,
                rubric=rubric,
                expected_supersedes=expected_supersedes,
                idea_dir=idea_dir,
                brief_sha256_on_disk=None,
            )
            covered = True
        except IdeationInputError as exc:
            head_error = {"code": exc.code, "message": exc.message}
    if covered:
        state = "covered"
    elif draft_present:
        state = "draft_only"
    else:
        state = "missing"
    return {
        "draft_present": draft_present,
        "head_error": head_error,
        "head_sha256": head_sha256 if covered else None,
        "head_version": head_version,
        "idea_index": idea_index,
        "state": state,
    }


def list_evaluation_coverage(workspace_root: Path) -> dict[str, Any]:
    """Read-only coverage accounting over the seal inventory.

    For every sealed run x every finalized idea: covered (a schema-valid
    finalized Evaluation Artifact heads the supersedes chain), draft_only, or
    missing. Corrupt runs are reported, never repaired. A sealed run whose
    case-level comparator inputs (Approved Workshop manifest, target source
    dataset) are unavailable is reported as unevaluable rather than corrupt:
    its own Evidence Chain is intact. Nothing is written.
    """
    workspace = workspace_root.resolve(strict=True)
    runs_root = workspace / RUNS_ROOT_RELPATH
    if runs_root.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The ideation-runs root is a symlink")
    # The pinned rubric is workspace-global; without it no artifact can be
    # schema-validated, so coverage itself fails closed.
    rubric = _load_rubric_policy(workspace)

    runs: list[dict[str, Any]] = []
    summary = {
        "covered": 0,
        "corrupt_runs": 0,
        "draft_only": 0,
        "missing": 0,
        "sealed_runs": 0,
        "unevaluable_runs": 0,
    }
    run_ids: list[str] = []
    if runs_root.is_dir():
        run_ids = sorted(
            child.name
            for child in runs_root.iterdir()
            if child.is_dir() and not child.is_symlink()
        )
    for candidate in run_ids:
        try:
            _validate_run_id(candidate)
        except IdeationInputError:
            continue
        run_root = runs_root / candidate
        if not (run_root / SEAL_NAME).is_file():
            continue  # unsealed runs are not part of the seal inventory
        summary["sealed_runs"] += 1
        try:
            context = _load_run_context(workspace, candidate)
        except IdeationInputError as exc:
            summary["corrupt_runs"] += 1
            runs.append(
                {
                    "error_code": exc.code,
                    "ideas": [],
                    "run_id": candidate,
                    "status": "corrupt",
                }
            )
            continue
        try:
            manifest = _load_workshop_manifest(workspace, context)
            target = _derive_target_comparator(workspace, manifest)
        except IdeationInputError as exc:
            summary["unevaluable_runs"] += 1
            runs.append(
                {
                    "case_id": context.case_id,
                    "error_code": exc.code,
                    "ideas": [],
                    "run_id": candidate,
                    "status": "unevaluable",
                    "terminal_outcome": context.terminal_outcome,
                }
            )
            continue
        inventory = _inventory_index(context.seal_document)
        idea_entries = []
        for relative_path, item in inventory.items():
            match = IDEA_INVENTORY_PATTERN.fullmatch(relative_path)
            if match:
                idea_entries.append((int(match.group(1)), item))
        idea_entries.sort(key=lambda pair: pair[0])
        ideas = [
            _idea_coverage(
                workspace, context, target, rubric, candidate, idea_index, item
            )
            for idea_index, item in idea_entries
        ]
        for idea in ideas:
            summary[idea["state"]] += 1
        runs.append(
            {
                "case_id": context.case_id,
                "ideas": ideas,
                "run_id": candidate,
                "status": "evaluable",
                "terminal_outcome": context.terminal_outcome,
            }
        )

    return {
        "runs": runs,
        "schema_version": EVALUATION_COVERAGE_SCHEMA_VERSION,
        "status": "ok",
        "summary": summary,
    }
