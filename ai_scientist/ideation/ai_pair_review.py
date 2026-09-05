"""AI-assisted pairwise blind review (authoring contract v2, ticket 02).

Implements the pair mode of the evaluation authoring contract v2 on top of
the single-review machinery in ``ai_review``:

- export_pair_package: derives an anonymous, deterministic two-arm pair
  package from two sealed same-case ideas. Each direction payload assigns
  the two anonymous contents to display arms A/B (A/B and the swapped B/A);
  the blind mapping stays in the private outer document. Payloads carry no
  arm identity, cost, run identity, or expected winner (scanned fail-closed).
- import_pair_response: stores one operator-supplied response per
  (evaluator slot, direction) write-once with ``user_supplied`` provenance.
  Each of the four reviews is an independent context: nothing reminds the
  second response of the first one's answers.
- validate_pair_review: fail-closed validation of one slot-direction's head
  response — closed schema, three categorical judgments (overall preference,
  domain-method fit, unjustified ML intrusion) with their closed enums,
  per-ref verbatim quote verification against the direction payload sources,
  linear supersedes — then commits the immutable pair review record.
- reduce_pair_review: maps every display-side verdict back to anonymous
  content through the blind mapping and merges the four results. Only four
  valid judgments pointing at the same content (or four ties) produce a
  stable result; everything else is incomparable with recorded reasons.
  The pre-registered quality floor from the single-review consensus records
  is carried independently and is never overridden by the overall preference.

Pair artifacts live under ``artifacts/evaluations/pairs/<pair_id>/``. A
stable pair result is honest AI-review evidence for Robert: it carries no
promotion authority until the comparison integration (ticket 03) explicitly
consumes it under the revised protocol.
"""

from __future__ import annotations

import html as _html_escape_module
import json
from pathlib import Path
import re
from typing import Any

from .ai_review import (
    CONSENSUS_DIRNAME,
    EVALUATOR_SLOTS,
    INFERENCE_MARKER,
    RESPONSES_DIRNAME,
    _SINGLE_EVALUATOR_KEYS as PAIR_EVALUATOR_KEYS,
    _check_config_binding,
    _check_evidence_ref,
    _check_evaluator_slot,
    _config_evaluator,
    _config_registered,
    _config_sha256,
    _derive_package,
    _existing_versions,
    _load_context_and_comparator,
    _load_review_config,
    _parse_response_text,
    _render_review_request,
    _validate_idea_index,
    _verify_supersedes_chain,
    _write_bytes_once,
    _write_bytes_overwrite,
)
from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import (
    EVALUATION_AI_PAIR_REDUCTION_SCHEMA_VERSION,
    EVALUATION_AI_PAIR_REVIEW_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_PAIR_REVIEW_RESPONSE_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_CONSENSUS_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_PROMPT_PAIR_PATH,
    EVALUATION_AI_REVIEW_PROMPT_PAIR_SHA256,
    EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION,
    EVALUATION_AUTHORING_CONTRACT_VERSION,
    EVALUATION_PAIR_MATERIALS_SCHEMA_VERSION,
    EVALUATION_PAIR_PACKAGE_SCHEMA_VERSION,
    EVALUATION_REVIEW_RESPONSE_IMPORT_SCHEMA_VERSION,
    EVALUATION_ROOT_RELPATH,
    _now,
)
from .errors import fail
from .run_store import _fsync_directory
from .schema import closed_object, nonempty_string, timestamp

PAIR_PACKAGE_NAME = "pair-package.json"
REDUCTION_DIRNAME = "reduction"
PAIR_REPORT_NAME = "pair-report.md"
PAIR_REPORT_HTML_NAME = "pair-report.html"
PAIR_ID_PATTERN = re.compile(r"pair-[0-9a-f]{16}\Z")
RESPONSE_NAME_PATTERN = re.compile(r"r(\d{4})\.json\Z")
PAIR_VERSION_PATTERN = re.compile(r"v\d{4}\.json\Z")
DIRECTIONS = ("ab", "ba")
PAIR_TASK_ID = "pair_idea_review"
PAIR_JUDGMENT_NAMES = (
    "overall_preference",
    "domain_method_fit",
    "unjustified_ml_intrusion",
)
PAIR_VERDICT_ENUMS = {
    "overall_preference": frozenset({"a_better", "b_better", "tie", "incomparable"}),
    "domain_method_fit": frozenset({"a_better", "b_better", "tie", "incomparable"}),
    "unjustified_ml_intrusion": frozenset(
        {"a_more", "b_more", "equal", "incomparable"}
    ),
}
PAIR_RESPONSE_TOP_KEYS = {
    "domain_method_fit",
    "key_assumptions",
    "missing_information",
    "overall_preference",
    "task",
    "unjustified_ml_intrusion",
}
PAIR_JUDGMENT_KEYS = {"evidence_refs", "rationale", "verdict"}
PAIR_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "authoring_contract_version",
        "record_kind",
        "pair_id",
        "direction",
        "prompt_version",
        "response_schema_version",
        "pair_package_sha256",
        "pair_request_sha256",
        "evaluator",
        "judgments",
        "citation_verification",
        "audit",
        "supersedes",
    }
)
_PAIR_RESPONSE_IMPORT_KEYS = frozenset(
    {
        "schema_version",
        "authoring_contract_version",
        "pair_id",
        "direction",
        "evaluator_slot",
        "imported_at",
        "imported_by",
        "provenance",
        "declared",
        "prompt_version",
        "parse_status",
        "parse_error",
        "parsed_response",
        "response_sha256",
        "response_text",
        "pair_package_sha256",
        "pair_request_sha256",
    }
)
VALIDATED_BY_TOOL_PAIR = "ai_scientist.ideation.ai_pair_review.validate_pair_review"
REDUCED_BY_TOOL = "ai_scientist.ideation.ai_pair_review.reduce_pair_review"
# Blind-packet hygiene: JSON key names a direction payload must never carry,
# and identity/expectation values that must never appear in its serialized
# text (checked per pair against the real run/case/paper identities).
PAIR_FORBIDDEN_KEYS = frozenset(
    {
        "arm_a_content",
        "arm_b_content",
        "arm_identity",
        "arm_position",
        "baseline",
        "baseline_profile_id",
        "blind_mapping",
        "case_id",
        "challenger",
        "challenger_profile_id",
        "content_1",
        "content_2",
        "cost_cny",
        "expected_winner",
        "pair_id",
        "profile_id",
        "prompt_profile",
        "run_id",
        "winner",
    }
)


class PairPrompt:
    """The pinned, versioned pair-review prompt template."""

    def __init__(self, version: str, text: str, sha256: str):
        self.version = version
        self.text = text
        self.sha256 = sha256


def _validate_pair_id(pair_id: object) -> str:
    if not isinstance(pair_id, str) or not PAIR_ID_PATTERN.fullmatch(pair_id):
        fail("INVALID_COORDINATE", "pair_id must look like pair-<16 hex chars>")
    return pair_id


def _check_direction(direction: object) -> str:
    if direction not in DIRECTIONS:
        fail("INVALID_COORDINATE", f"direction must be one of {list(DIRECTIONS)}")
    return str(direction)


def _pair_dir(workspace: Path, pair_id: str) -> Path:
    current = workspace
    for part in (*EVALUATION_ROOT_RELPATH.parts, "pairs", pair_id):
        current = current / part
        if current.is_symlink():
            fail(
                "SYMLINK_FORBIDDEN",
                f"Pair package path component is a symlink: {current.name}",
            )
    return current


def _pair_relpath(pair_id: str, *parts: str) -> str:
    return (Path("artifacts/evaluations") / "pairs" / pair_id / Path(*parts)).as_posix()


def _direction_dir(pair_path: Path, slot: str, direction: str) -> Path:
    slot_path = pair_path / slot
    if slot_path.is_symlink():
        fail("SYMLINK_FORBIDDEN", f"The {slot} evaluator directory is a symlink")
    direction_path = slot_path / direction
    if direction_path.is_symlink():
        fail("SYMLINK_FORBIDDEN", f"The {direction} direction directory is a symlink")
    return direction_path


def _load_pair_prompt(workspace: Path) -> PairPrompt:
    path = workspace / EVALUATION_AI_REVIEW_PROMPT_PAIR_PATH
    if not path.is_file():
        fail("MISSING_ARTIFACT", "AI pair review prompt template is missing")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != EVALUATION_AI_REVIEW_PROMPT_PAIR_SHA256:
        fail("POLICY_DRIFT", "AI pair review prompt template hash changed")
    return PairPrompt(
        version=EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION,
        text=data.decode("utf-8"),
        sha256=digest,
    )


# ==============================================================================
# Pair package derivation
# ==============================================================================


def _single_source_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["source_id"]: entry for entry in document["source_registry"]}


def _find_source(sources: list[dict[str, Any]], kind: str, predicate) -> dict[str, Any]:
    for source in sources:
        if source["kind"] == kind and predicate(source):
            return source
    fail("PAIR_MATERIAL_MISMATCH", f"Package lacks a {kind} source")


def _check_shared_materials(
    sources_a: list[dict[str, Any]], sources_b: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The three shared sources (workshop, target summary, target abstract)
    must be byte-identical across arms; otherwise the pair is not same-case
    material and fails closed. Returns content_1's shared sources."""
    shared = []
    for kind, predicate in (
        ("workshop", lambda source: True),
        ("target_comparator", lambda source: source.get("part") == "abstract_summary"),
        ("target_comparator", lambda source: source.get("part") == "abstract"),
    ):
        first = _find_source(sources_a, kind, predicate)
        second = _find_source(sources_b, kind, predicate)
        if first["text"] != second["text"]:
            fail(
                "PAIR_MATERIAL_MISMATCH",
                f"The two arms carry different {kind} material; a pair requires "
                "the same case materials",
            )
        shared.append(first)
    return shared


def _iter_payload_keys(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _iter_payload_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_payload_keys(item)


def _scan_payload_keys(payload: dict[str, Any]) -> None:
    for key in _iter_payload_keys(payload):
        if key in PAIR_FORBIDDEN_KEYS:
            fail("PAIR_PACKET_BLIND_LEAK", f"Pair payload carries forbidden key {key}")


def _scan_payload_identity(payload: dict[str, Any], secrets: list[str]) -> None:
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    for secret in secrets:
        if secret and secret in payload_text:
            fail(
                "PAIR_PACKET_BLIND_LEAK",
                "Pair payload leaks an identity or expectation value",
                token_prefix=secret[:24],
            )


def _build_direction_payload(
    *,
    doc_by_content: dict[str, dict[str, Any]],
    mapping: dict[str, str],
    shared_sources: list[dict[str, Any]],
    direction: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One direction's model-visible payload plus its private registry.

    Shared case material gets neutral C### ids; each arm's idea fields, audit
    statement, and retrieval segments get A###/B### ids assigned by display
    arm, so the evaluator can tell which idea a source belongs to without
    learning anything about its identity.
    """
    sources: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []

    def add(
        display_id: str,
        kind: str,
        text: str,
        visible: dict[str, Any],
        arm: str,
        origin: dict[str, Any],
    ) -> None:
        sources.append({"kind": kind, "source_id": display_id, "text": text, **visible})
        registry.append(
            {
                "arm": arm,
                "direction": direction,
                "display_source_id": display_id,
                "kind": kind,
                "origin_source_id": origin["source_id"],
                **{
                    key: origin[key]
                    for key in ("paper_id", "operation_seq", "field")
                    if key in origin
                },
            }
        )

    for position, source in enumerate(shared_sources, start=1):
        visible = {
            key: value
            for key, value in source.items()
            if key not in ("source_id", "kind", "text")
        }
        add(
            f"C{position:03d}",
            source["kind"],
            source["text"],
            visible,
            "shared",
            source,
        )
    for display_prefix, content in (("A", mapping["arm_a"]), ("B", mapping["arm_b"])):
        document = doc_by_content[content]
        registry_index = _single_source_index(document)
        counter = 0
        for source in document["model_payload"]["materials"]["sources"]:
            if source["kind"] in ("workshop", "target_comparator"):
                continue
            counter += 1
            visible = {
                key: value
                for key, value in source.items()
                if key not in ("source_id", "kind", "text")
            }
            add(
                f"{display_prefix}{counter:03d}",
                source["kind"],
                source["text"],
                visible,
                content,
                registry_index[source["source_id"]],
            )
    payload = {
        "schema_version": EVALUATION_PAIR_MATERIALS_SCHEMA_VERSION,
        "materials": {"sources": sources},
        "task": PAIR_TASK_ID,
    }
    _scan_payload_keys(payload)
    return payload, registry


def _derive_pair_document(
    workspace_root: Path,
    run_id_a: str,
    idea_index_a: int,
    run_id_b: str,
    idea_index_b: int,
) -> dict[str, Any]:
    """Derive the deterministic pair package document from the sealed chains."""
    idea_index_a = _validate_idea_index(idea_index_a)
    idea_index_b = _validate_idea_index(idea_index_b)
    workspace, context_a, target_a, rubric = _load_context_and_comparator(
        workspace_root, run_id_a
    )
    _, context_b, target_b, _ = _load_context_and_comparator(workspace_root, run_id_b)
    if context_a.case_id != context_b.case_id:
        fail("PAIR_CASE_MISMATCH", "A pair requires both ideas from the same case")
    if target_a.reference != target_b.reference:
        fail(
            "PAIR_TARGET_MISMATCH",
            "The two arms bind different Target Comparator references",
        )
    if run_id_a == run_id_b and idea_index_a == idea_index_b:
        fail(
            "PAIR_ARMS_IDENTICAL",
            "A pair must compare two different ideas, not one idea twice",
        )
    doc_a, _ = _derive_package(
        workspace=workspace,
        run_id=run_id_a,
        idea_index=idea_index_a,
        context=context_a,
        target=target_a,
        rubric=rubric,
    )
    doc_b, _ = _derive_package(
        workspace=workspace,
        run_id=run_id_b,
        idea_index=idea_index_b,
        context=context_b,
        target=target_b,
        rubric=rubric,
    )
    if doc_a["idea"]["sha256"] == doc_b["idea"]["sha256"]:
        fail(
            "PAIR_ARMS_IDENTICAL",
            "The two arms carry byte-identical idea payloads; a pair must "
            "compare two different ideas",
        )
    shared_sources = _check_shared_materials(
        doc_a["model_payload"]["materials"]["sources"],
        doc_b["model_payload"]["materials"]["sources"],
    )

    ordered = sorted(
        (
            {
                "doc": doc_a,
                "idea_index": idea_index_a,
                "idea_sha256": doc_a["idea"]["sha256"],
                "run_id": run_id_a,
            },
            {
                "doc": doc_b,
                "idea_index": idea_index_b,
                "idea_sha256": doc_b["idea"]["sha256"],
                "run_id": run_id_b,
            },
        ),
        key=lambda arm: (arm["run_id"], arm["idea_index"]),
    )
    doc_by_content = {
        "content_1": ordered[0]["doc"],
        "content_2": ordered[1]["doc"],
    }
    arms = {
        content: {
            "idea_index": arm["idea_index"],
            "idea_relative_path": arm["doc"]["idea"]["relative_path"],
            "idea_sha256": arm["idea_sha256"],
            "review_package_sha256": sha256_bytes(canonical_json_bytes(arm["doc"])),
            "run_id": arm["run_id"],
        }
        for content, arm in (
            ("content_1", ordered[0]),
            ("content_2", ordered[1]),
        )
    }
    blind_mapping = {
        "ab": {"arm_a": "content_1", "arm_b": "content_2"},
        "ba": {"arm_a": "content_2", "arm_b": "content_1"},
    }
    direction_payloads: dict[str, dict[str, Any]] = {}
    source_registry: list[dict[str, Any]] = []
    for direction in DIRECTIONS:
        payload, registry = _build_direction_payload(
            doc_by_content=doc_by_content,
            mapping=blind_mapping[direction],
            shared_sources=shared_sources,
            direction=direction,
        )
        direction_payloads[direction] = payload
        source_registry.extend(registry)

    pair_id = (
        "pair-"
        + sha256_bytes(
            canonical_json_bytes(
                {
                    "arms": [
                        {
                            "idea_index": arms[content]["idea_index"],
                            "idea_sha256": arms[content]["idea_sha256"],
                            "run_id": arms[content]["run_id"],
                        }
                        for content in ("content_1", "content_2")
                    ],
                    "case_id": context_a.case_id,
                }
            )
        )[:16]
    )
    secrets = [
        context_a.case_id,
        *(arm["run_id"] for arm in arms.values()),
        pair_id,
        "content_1",
        "content_2",
        "ml-baseline-v1",
        "cross-domain-v1",
        *sorted(
            {
                entry["paper_id"]
                for single_document in doc_by_content.values()
                for entry in single_document["source_registry"]
                if "paper_id" in entry
            }
        ),
    ]
    for direction in DIRECTIONS:
        _scan_payload_identity(direction_payloads[direction], secrets)

    return {
        "schema_version": EVALUATION_PAIR_PACKAGE_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "pair_id": pair_id,
        "case_id": context_a.case_id,
        "arms": arms,
        "target_paper": target_a.reference,
        "prompt_version": EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION,
        "response_schema_version": EVALUATION_AI_PAIR_REVIEW_RESPONSE_SCHEMA_VERSION,
        "blind_mapping": blind_mapping,
        "direction_payload_sha256": {
            direction: sha256_bytes(canonical_json_bytes(payload))
            for direction, payload in direction_payloads.items()
        },
        "source_registry": source_registry,
        "direction_payloads": direction_payloads,
    }


def export_pair_package(
    workspace_root: Path,
    run_id_a: str,
    idea_index_a: int,
    run_id_b: str,
    idea_index_b: int,
) -> dict[str, Any]:
    """Export the anonymous pair package and both direction requests.

    Re-export is byte-identical: the pair package is a deterministic function
    of the two sealed runs, the pinned rubric, and the pinned pair template.
    """
    workspace = workspace_root.resolve(strict=True)
    document = _derive_pair_document(
        workspace, run_id_a, idea_index_a, run_id_b, idea_index_b
    )
    prompt = _load_pair_prompt(workspace)
    package_bytes = canonical_json_bytes(document)
    pair_path = _pair_dir(workspace, document["pair_id"])
    try:
        pair_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create pair directory: {detail}")
    _fsync_directory(pair_path)
    _write_bytes_overwrite(
        pair_path / PAIR_PACKAGE_NAME, package_bytes, label=PAIR_PACKAGE_NAME
    )
    requests = {}
    for direction in DIRECTIONS:
        request_bytes = _render_review_request(
            prompt.text, document["direction_payloads"][direction]
        )
        name = f"pair-request-{direction}.txt"
        _write_bytes_overwrite(pair_path / name, request_bytes, label=name)
        requests[direction] = {
            "path": _pair_relpath(document["pair_id"], name),
            "sha256": sha256_bytes(request_bytes),
        }
    return {
        "arms": {
            content: {"idea_index": arm["idea_index"], "run_id": arm["run_id"]}
            for content, arm in document["arms"].items()
        },
        "pair_id": document["pair_id"],
        "pair_package": _pair_relpath(document["pair_id"], PAIR_PACKAGE_NAME),
        "pair_package_sha256": sha256_bytes(package_bytes),
        "prompt_version": prompt.version,
        "requests": requests,
        "status": "exported",
    }


def _rederive_pair(
    workspace: Path, pair_id: str
) -> tuple[dict[str, Any], PairPrompt, Path]:
    """Re-derive the pair package from the sealed chains and prove the
    on-disk bytes match; also prove the prompt version is the pinned one."""
    pair_path = _pair_dir(workspace, pair_id)
    package_path = pair_path / PAIR_PACKAGE_NAME
    if not package_path.is_file() or package_path.is_symlink():
        fail(
            "PAIR_PACKAGE_NOT_FOUND",
            f"No {PAIR_PACKAGE_NAME} for {pair_id}; run evaluation "
            "export-pair-package first",
        )
    package_bytes = package_path.read_bytes()
    stored = parse_json_bytes(package_bytes, label="pair package")
    if not isinstance(stored, dict):
        fail("RUN_CORRUPT", "Pair package is not a JSON object")
    arms = stored.get("arms")
    if not isinstance(arms, dict) or set(arms) != {"content_1", "content_2"}:
        fail("RUN_CORRUPT", "Pair package arms binding is malformed")
    for content in ("content_1", "content_2"):
        arm = arms[content]
        if not isinstance(arm, dict) or "idea_index" not in arm or "run_id" not in arm:
            fail("RUN_CORRUPT", f"Pair package arm binding {content} is malformed")
    derived = _derive_pair_document(
        workspace,
        arms["content_1"]["run_id"],
        arms["content_1"]["idea_index"],
        arms["content_2"]["run_id"],
        arms["content_2"]["idea_index"],
    )
    if derived["pair_id"] != pair_id:
        fail(
            "PAIR_PACKAGE_DRIFT",
            "The pair package on disk binds another pair_id than its arms "
            "derive; re-run evaluation export-pair-package",
        )
    if canonical_json_bytes(derived) != package_bytes:
        fail(
            "PAIR_PACKAGE_DRIFT",
            "The pair package on disk does not match a re-derivation from the "
            "sealed runs; re-run evaluation export-pair-package",
        )
    prompt = _load_pair_prompt(workspace)
    if derived["prompt_version"] != prompt.version:
        fail("REVIEW_CONTRACT_MISMATCH", "The pair prompt version is not approved")
    return derived, prompt, pair_path


# ==============================================================================
# Pair response import and validation
# ==============================================================================


def import_pair_response(
    workspace_root: Path,
    pair_id: str,
    evaluator_slot: str,
    direction: str,
    *,
    response_path: Path,
    provider: str,
    model_id: str,
    responded_at: str,
    supplied_by: str,
    imported_by: str,
) -> dict[str, Any]:
    """Store one operator-supplied pair response write-once and parse it.

    One file per (evaluator slot, direction): the four reviews of a pair are
    independent contexts, and nothing carries one answer into another
    context. Provenance is always ``user_supplied``.
    """
    pair_id = _validate_pair_id(pair_id)
    slot = _check_evaluator_slot(evaluator_slot)
    direction = _check_direction(direction)
    provider = nonempty_string(provider, label="provider")
    model_id = nonempty_string(model_id, label="model_id")
    timestamp(responded_at, label="responded_at")
    supplied_by = nonempty_string(supplied_by, label="supplied_by")
    imported_by = nonempty_string(imported_by, label="imported_by")
    workspace = workspace_root.resolve(strict=True)
    document, prompt, pair_path = _rederive_pair(workspace, pair_id)
    request_bytes = _render_review_request(
        prompt.text, document["direction_payloads"][direction]
    )
    request_path = pair_path / f"pair-request-{direction}.txt"
    if not request_path.is_file() or request_path.is_symlink():
        fail(
            "PAIR_REQUEST_NOT_FOUND",
            f"No pair-request-{direction}.txt for {pair_id}; run evaluation "
            "export-pair-package first",
        )
    if request_path.read_bytes() != request_bytes:
        fail(
            "PAIR_REQUEST_DRIFT",
            f"pair-request-{direction}.txt on disk does not match the pinned "
            "render; re-run evaluation export-pair-package",
        )
    if response_path.is_symlink() or not response_path.is_file():
        fail("INVALID_INPUT", f"Response file is missing: {response_path}")
    try:
        response_text = response_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_RESPONSE_ENCODING", f"Response file is not UTF-8: {exc}")

    parsed, parse_error = _parse_response_text(response_text)
    parse_status = "ok" if parsed is not None else "invalid_format"

    direction_dir = _direction_dir(pair_path, slot, direction)
    responses_dir = direction_dir / RESPONSES_DIRNAME
    if responses_dir.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The responses directory is a symlink")
    try:
        direction_dir.mkdir(parents=True, exist_ok=True)
        responses_dir.mkdir(exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail(
            "STORAGE_WRITE_FAILED",
            f"Cannot create {slot}/{direction} response directory: {detail}",
        )
    _fsync_directory(direction_dir)
    existing = []
    if responses_dir.is_dir():
        for path in responses_dir.iterdir():
            match = RESPONSE_NAME_PATTERN.fullmatch(path.name)
            if match:
                existing.append(int(match.group(1)))
    new_seq = (max(existing) + 1) if existing else 1
    response_name = f"r{new_seq:04d}.json"
    response_record = {
        "schema_version": EVALUATION_REVIEW_RESPONSE_IMPORT_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "pair_id": pair_id,
        "direction": direction,
        "evaluator_slot": slot,
        "imported_at": _now(),
        "imported_by": imported_by,
        "provenance": {"kind": "user_supplied", "supplied_by": supplied_by},
        "declared": {
            "provider": provider,
            "model_id": model_id,
            "responded_at": responded_at,
        },
        "prompt_version": prompt.version,
        "parse_status": parse_status,
        "parse_error": parse_error,
        "parsed_response": parsed,
        "response_sha256": sha256_bytes(response_text.encode("utf-8")),
        "response_text": response_text,
        "pair_package_sha256": sha256_bytes(canonical_json_bytes(document)),
        "pair_request_sha256": sha256_bytes(request_bytes),
    }
    _write_bytes_once(
        responses_dir / response_name,
        canonical_json_bytes(response_record),
        label=response_name,
    )
    result = {
        "direction": direction,
        "evaluator_slot": slot,
        "pair_id": pair_id,
        "parse_status": parse_status,
        "prompt_version": prompt.version,
        "response_file": _pair_relpath(
            pair_id, slot, direction, RESPONSES_DIRNAME, response_name
        ),
        "response_seq": new_seq,
        "status": "imported",
    }
    if parse_error is not None:
        result["parse_error"] = parse_error
    return result


def _head_pair_response(direction_dir: Path):
    responses_dir = direction_dir / RESPONSES_DIRNAME
    if not responses_dir.is_dir() or responses_dir.is_symlink():
        return None
    versions = _existing_versions(
        responses_dir, pattern=RESPONSE_NAME_PATTERN, label="Pair review response"
    )
    if not versions:
        return None
    head_name = versions[-1][1]
    document = parse_json_bytes(
        (responses_dir / head_name).read_bytes(),
        label=f"pair review response {head_name}",
    )
    if not isinstance(document, dict):
        fail("RUN_CORRUPT", f"Pair review response {head_name} is not a JSON object")
    return head_name, document


def _check_pair_judgments(
    value: object, sources_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Three categorical judgments, closed enums, verbatim-verified refs."""
    parsed = closed_object(
        value, label="pair review response", keys=PAIR_RESPONSE_TOP_KEYS
    )
    if parsed["task"] != PAIR_TASK_ID:
        fail("INVALID_SCHEMA", f"pair review response task must be '{PAIR_TASK_ID}'")
    assumptions = parsed["key_assumptions"]
    if not isinstance(assumptions, list) or not all(
        isinstance(item, str) and item.strip() for item in assumptions
    ):
        fail("INVALID_SCHEMA", "key_assumptions must be an array of non-empty strings")
    missing = parsed["missing_information"]
    if not isinstance(missing, list) or not all(
        isinstance(item, str) and item.strip() for item in missing
    ):
        fail(
            "INVALID_SCHEMA",
            "missing_information must be an array of non-empty strings",
        )
    judgments: dict[str, Any] = {}
    refs_total = 0
    incomparable_any = False
    for name in PAIR_JUDGMENT_NAMES:
        block = closed_object(parsed[name], label=name, keys=PAIR_JUDGMENT_KEYS)
        verdict = block["verdict"]
        if verdict not in PAIR_VERDICT_ENUMS[name]:
            fail(
                "INVALID_SCHEMA",
                f"{name}.verdict must be one of {sorted(PAIR_VERDICT_ENUMS[name])}",
            )
        rationale = block["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            fail("INVALID_SCHEMA", f"{name}.rationale must be a non-empty string")
        refs_value = block["evidence_refs"]
        if not isinstance(refs_value, list):
            fail("INVALID_SCHEMA", f"{name}.evidence_refs must be an array")
        refs = [_check_evidence_ref(ref, sources_by_id) for ref in refs_value]
        refs_total += len(refs)
        if verdict == "incomparable":
            incomparable_any = True
        elif not refs and not rationale.lstrip().startswith(INFERENCE_MARKER):
            fail(
                "EVIDENCE_REF_REQUIRED",
                f"{name} is judged without evidence refs; the rationale must "
                f"start with '{INFERENCE_MARKER}' and state the inference basis",
            )
        judgments[name] = {
            "evidence_refs": refs,
            "rationale": rationale,
            "verdict": verdict,
        }
    if incomparable_any and not missing:
        fail(
            "INVALID_SCHEMA",
            "an incomparable verdict requires missing_information naming the "
            "material that cannot be compared",
        )
    return {"judgments": judgments, "refs_total": refs_total}


def _check_pair_supersedes(
    value: object,
    *,
    expected_name: str | None,
    direction_dir: Path,
    pair_id: str,
    direction: str | None,
    slot: str | None,
) -> None:
    """Linear supersedes within one pair record chain.

    direction/slot are None for the reduction chain, whose records carry no
    per-direction binding beyond the pair id.
    """
    if value is None:
        if expected_name is not None:
            fail(
                "EVALUATION_SUPERSEDES_INVALID",
                "A correction must supersede the current latest version "
                f"{expected_name}",
            )
        return
    if not isinstance(value, str) or not PAIR_VERSION_PATTERN.fullmatch(value):
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
    target_path = direction_dir / value
    if not target_path.is_file() or target_path.is_symlink():
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            f"supersedes target does not exist: {value}",
        )
    target_value = parse_json_bytes(
        target_path.read_bytes(), label=f"supersedes target {value}"
    )
    if not isinstance(target_value, dict) or target_value.get("pair_id") != pair_id:
        fail(
            "EVALUATION_SUPERSEDES_INVALID",
            "supersedes target belongs to another pair",
        )
    if direction is not None or slot is not None:
        if (
            target_value.get("direction") != direction
            or not isinstance(target_value.get("evaluator"), dict)
            or target_value["evaluator"].get("evaluator_slot") != slot
        ):
            fail(
                "EVALUATION_SUPERSEDES_INVALID",
                "supersedes target belongs to another direction or slot",
            )


def _pair_record_state(
    *,
    pair_path: Path,
    slot: str,
    direction: str,
    pair_id: str,
    document: dict[str, Any],
) -> dict[str, Any]:
    """Load one slot-direction's head record with integrity re-verification.

    Same state vocabulary as the single-review aggregation: valid /
    unvalidated / invalid / missing; tampering fails closed.
    """
    direction_dir = _direction_dir(pair_path, slot, direction)
    record_versions = _existing_versions(direction_dir)
    if record_versions:
        _verify_supersedes_chain(direction_dir, label="Pair review record")
        _head_seq, head_record_name = record_versions[-1]
        record = parse_json_bytes(
            (direction_dir / head_record_name).read_bytes(),
            label=f"pair review record {head_record_name}",
        )
        record = closed_object(
            record, label="pair review record", keys=PAIR_RECORD_KEYS
        )
        if record["schema_version"] != EVALUATION_AI_PAIR_REVIEW_RECORD_SCHEMA_VERSION:
            fail(
                "UNSUPPORTED_SCHEMA",
                "Unsupported pair review record schema_version: "
                f"{record['schema_version']}",
            )
        if record["record_kind"] != "pair_ai_review":
            fail(
                "RUN_CORRUPT",
                f"Pair review record {head_record_name} has the wrong kind",
            )
        if record["pair_id"] != pair_id or record["direction"] != direction:
            fail(
                "IDENTITY_MISMATCH",
                f"Pair review record {head_record_name} belongs to another pair "
                "or direction",
            )
        if record["pair_package_sha256"] != sha256_bytes(
            canonical_json_bytes(document)
        ):
            fail(
                "REVIEW_RESPONSE_PACKAGE_MISMATCH",
                f"Pair review record {head_record_name} binds another pair package",
            )
        if record["prompt_version"] != document["prompt_version"]:
            fail(
                "REVIEW_CONTRACT_MISMATCH",
                f"Pair review record {head_record_name} was produced under "
                "another prompt version",
            )
        evaluator = closed_object(
            record["evaluator"], label="record.evaluator", keys=PAIR_EVALUATOR_KEYS
        )
        if evaluator["evaluator_slot"] != slot or evaluator["author_type"] != "AI":
            fail(
                "IDENTITY_MISMATCH",
                f"Pair review record {head_record_name} does not belong to "
                f"slot {slot}",
            )
        provenance = closed_object(
            evaluator["provenance"],
            label="record.evaluator.provenance",
            keys={"kind", "supplied_by"},
        )
        if provenance["kind"] != "user_supplied":
            fail(
                "IDENTITY_MISMATCH",
                f"Pair review record {head_record_name} does not carry "
                "user_supplied provenance",
            )
        response_path = pair_path / evaluator["response_file"]
        if response_path.is_symlink() or not response_path.is_file():
            fail(
                "REVIEW_RESPONSE_NOT_FOUND",
                f"Pair review record {head_record_name} binds a missing "
                "response file",
            )
        # The bound file is the stored import record; its integrity anchor is
        # the hash of the embedded raw response text.
        stored = parse_json_bytes(
            response_path.read_bytes(), label="stored pair response import record"
        )
        stored = closed_object(
            stored, label="stored pair response", keys=_PAIR_RESPONSE_IMPORT_KEYS
        )
        if stored["parse_status"] != "ok" or not isinstance(
            stored["parsed_response"], dict
        ):
            fail(
                "RUN_CORRUPT",
                f"The response file bound by {head_record_name} is not a "
                "parseable import record",
            )
        text_sha = sha256_bytes(stored["response_text"].encode("utf-8"))
        reparsed, _parse_error = _parse_response_text(stored["response_text"])
        if (
            text_sha != stored["response_sha256"]
            or text_sha != evaluator["response_sha256"]
            or reparsed is None
            or canonical_json_bytes(reparsed)
            != canonical_json_bytes(stored["parsed_response"])
        ):
            fail(
                "HASH_MISMATCH",
                f"The response file bound by {head_record_name} was modified",
            )
        if (
            stored["pair_id"] != pair_id
            or stored["direction"] != direction
            or stored["evaluator_slot"] != slot
        ):
            fail(
                "IDENTITY_MISMATCH",
                f"The response file bound by {head_record_name} was imported "
                "for another pair, slot, or direction",
            )
        sources_by_id = {
            source["source_id"]: source
            for source in document["direction_payloads"][direction]["materials"][
                "sources"
            ]
        }
        # Re-validate the authentic response and prove the committed record
        # is exactly what it yields — any tamper on either side fails closed.
        checked = _check_pair_judgments(reparsed, sources_by_id)
        if canonical_json_bytes(checked["judgments"]) != canonical_json_bytes(
            record["judgments"]
        ):
            fail(
                "RUN_CORRUPT",
                f"Pair review record {head_record_name} does not match its "
                "bound response",
            )
        return {
            "record": record,
            "record_name": head_record_name,
            "record_sha256": sha256_bytes(
                (direction_dir / head_record_name).read_bytes()
            ),
            "state": "valid",
        }
    head = _head_pair_response(direction_dir)
    if head is None:
        return {
            "record": None,
            "record_name": None,
            "record_sha256": None,
            "state": "missing",
        }
    head_name, head_document = head
    if head_document["parse_status"] != "ok" or not isinstance(
        head_document["parsed_response"], dict
    ):
        return {
            "record": None,
            "record_name": None,
            "record_sha256": None,
            "state": "invalid",
        }
    return {
        "record": None,
        "record_name": None,
        "record_sha256": None,
        "state": "unvalidated",
    }


def validate_pair_review(
    workspace_root: Path,
    pair_id: str,
    evaluator_slot: str,
    direction: str,
) -> dict[str, Any]:
    """Validate one slot-direction's head response and commit its record."""
    pair_id = _validate_pair_id(pair_id)
    slot = _check_evaluator_slot(evaluator_slot)
    direction = _check_direction(direction)
    workspace = workspace_root.resolve(strict=True)
    document, _prompt, pair_path = _rederive_pair(workspace, pair_id)
    direction_dir = _direction_dir(pair_path, slot, direction)
    head = _head_pair_response(direction_dir)
    if head is None:
        fail(
            "REVIEW_RESPONSE_NOT_FOUND",
            f"No imported pair responses for {slot}/{direction}; run evaluation "
            "import-pair-response first",
        )
    head_name, head_document = head
    if head_document["pair_package_sha256"] != sha256_bytes(
        canonical_json_bytes(document)
    ):
        fail(
            "REVIEW_RESPONSE_PACKAGE_MISMATCH",
            f"The head response {head_name} was imported against a different "
            "pair package",
        )
    if head_document["prompt_version"] != document["prompt_version"]:
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            f"The head response {head_name} was imported under another prompt "
            "version",
        )
    if (
        head_document["direction"] != direction
        or head_document["evaluator_slot"] != slot
    ):
        fail(
            "IDENTITY_MISMATCH",
            f"The head response {head_name} was imported for another " "slot/direction",
        )
    if head_document["parse_status"] != "ok" or not isinstance(
        head_document["parsed_response"], dict
    ):
        fail(
            "REVIEW_RESPONSE_INVALID_FORMAT",
            f"The head response {head_name} is not a parseable pair review " "response",
            parse_error=head_document["parse_error"],
        )
    config = _load_review_config(workspace) if _config_registered(workspace) else None
    if config is not None:
        _check_config_binding(config, slot, head_document["declared"])
    sources_by_id = {
        source["source_id"]: source
        for source in document["direction_payloads"][direction]["materials"]["sources"]
    }
    checked = _check_pair_judgments(head_document["parsed_response"], sources_by_id)

    versions = _existing_versions(direction_dir)
    expected_supersedes = versions[-1][1] if versions else None
    new_seq = (versions[-1][0] + 1) if versions else 1
    record = {
        "schema_version": EVALUATION_AI_PAIR_REVIEW_RECORD_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "record_kind": "pair_ai_review",
        "pair_id": pair_id,
        "direction": direction,
        "prompt_version": document["prompt_version"],
        "response_schema_version": document["response_schema_version"],
        "pair_package_sha256": sha256_bytes(canonical_json_bytes(document)),
        "pair_request_sha256": head_document["pair_request_sha256"],
        "evaluator": {
            "evaluator_slot": slot,
            "author_type": "AI",
            "declared_provider": head_document["declared"]["provider"],
            "declared_model_id": head_document["declared"]["model_id"],
            "provenance": dict(head_document["provenance"]),
            "response_file": f"{slot}/{direction}/{RESPONSES_DIRNAME}/{head_name}",
            "response_sha256": head_document["response_sha256"],
            "responded_at": head_document["declared"]["responded_at"],
            "imported_at": head_document["imported_at"],
            "imported_by": head_document["imported_by"],
        },
        "judgments": checked["judgments"],
        "citation_verification": {
            "refs_total": checked["refs_total"],
            "refs_quote_verified": checked["refs_total"],
            "semantic_support_verification": "not_performed",
        },
        "audit": {
            "imported_at": head_document["imported_at"],
            "imported_by": head_document["imported_by"],
            "validated_at": _now(),
            "validated_by": VALIDATED_BY_TOOL_PAIR,
            "validation_result": "passed",
        },
        "supersedes": expected_supersedes,
    }
    _check_pair_supersedes(
        record["supersedes"],
        expected_name=expected_supersedes,
        direction_dir=direction_dir,
        pair_id=pair_id,
        direction=direction,
        slot=slot,
    )
    version_name = f"v{new_seq:04d}.json"
    record_bytes = canonical_json_bytes(record)
    _write_bytes_once(direction_dir / version_name, record_bytes, label=version_name)
    return {
        "direction": direction,
        "evaluator_slot": slot,
        "pair_id": pair_id,
        "record": _pair_relpath(pair_id, slot, direction, version_name),
        "record_sha256": sha256_bytes(record_bytes),
        "response_file": _pair_relpath(
            pair_id, slot, direction, RESPONSES_DIRNAME, head_name
        ),
        "status": "validated",
        "supersedes": expected_supersedes,
        "version": version_name,
    }


# ==============================================================================
# Reduction: restore anonymous content and merge the four judgments
# ==============================================================================


def _map_verdict_to_content(
    verdict: str, direction: str, blind_mapping: dict[str, Any]
) -> str:
    if verdict in ("tie", "equal", "incomparable"):
        return verdict
    arm = "arm_a" if verdict.startswith("a_") else "arm_b"
    return blind_mapping[direction][arm]


def _reduce_judgment(
    effective: dict[tuple[str, str], str],
    states: dict[tuple[str, str], str],
) -> dict[str, Any]:
    incomplete = sorted(
        f"{slot}/{direction}"
        for slot in EVALUATOR_SLOTS
        for direction in DIRECTIONS
        if states[(slot, direction)] != "valid"
    )
    if incomplete:
        return {
            "content_value": None,
            "outcome": "incomparable",
            "reasons": [
                {"code": "missing_valid_record", "slot_directions": incomplete}
            ],
        }
    values = set(effective.values())
    if len(values) == 1:
        value = next(iter(values))
        if value == "incomparable":
            return {
                "content_value": None,
                "outcome": "incomparable",
                "reasons": [
                    {
                        "code": "incomparable_judgment",
                        "detail": "all four valid judgments agree the pair is "
                        "incomparable",
                    }
                ],
            }
        return {"content_value": value, "outcome": "stable", "reasons": []}
    reasons: list[dict[str, Any]] = []
    for slot in EVALUATOR_SLOTS:
        if effective[(slot, "ab")] != effective[(slot, "ba")]:
            reasons.append(
                {
                    "code": "position_flip",
                    "detail": (
                        f"slot {slot} preferred {effective[(slot, 'ab')]} in "
                        f"A/B but {effective[(slot, 'ba')]} in B/A"
                    ),
                    "slot": slot,
                }
            )
    primary_values = {effective[("primary", direction)] for direction in DIRECTIONS}
    second_values = {effective[("second", direction)] for direction in DIRECTIONS}
    if (
        len(primary_values) == 1
        and len(second_values) == 1
        and primary_values != second_values
    ):
        reasons.append(
            {
                "code": "evaluator_conflict",
                "detail": (
                    "the two evaluators consistently prefer different content "
                    f"({next(iter(primary_values))} vs {next(iter(second_values))})"
                ),
            }
        )
    if "incomparable" in values:
        reasons.append(
            {
                "code": "incomparable_judgment",
                "detail": "at least one valid judgment returned incomparable",
            }
        )
    if not reasons:
        reasons.append(
            {
                "code": "evaluator_conflict",
                "detail": "the four judgments do not converge on one content",
            }
        )
    return {"content_value": None, "outcome": "incomparable", "reasons": reasons}


def _consensus_floor_for_arm(workspace: Path, arm: dict[str, Any]) -> dict[str, Any]:
    """The quality-floor state of one arm from its dual-review consensus."""
    consensus_dir = (
        workspace
        / EVALUATION_ROOT_RELPATH
        / arm["run_id"]
        / "ideas"
        / f"{arm['idea_index']:06d}"
        / "ai"
        / CONSENSUS_DIRNAME
    )
    empty = {
        "consensus_record": None,
        "consensus_record_sha256": None,
        "coverage": None,
        "state": "not_evaluated",
    }
    if consensus_dir.is_symlink() or not consensus_dir.is_dir():
        return empty
    versions = _existing_versions(consensus_dir)
    if not versions:
        return empty
    head_name = versions[-1][1]
    consensus = parse_json_bytes(
        (consensus_dir / head_name).read_bytes(),
        label=f"consensus record {head_name}",
    )
    if not isinstance(consensus, dict):
        fail("RUN_CORRUPT", f"Consensus record {head_name} is not a JSON object")
    if (
        consensus.get("schema_version")
        != EVALUATION_AI_REVIEW_CONSENSUS_RECORD_SCHEMA_VERSION
        or consensus.get("record_kind") != "dual_ai_review_consensus"
        or consensus.get("run_id") != arm["run_id"]
        or not isinstance(consensus.get("idea"), dict)
        or consensus["idea"].get("idea_index") != arm["idea_index"]
    ):
        fail(
            "IDENTITY_MISMATCH",
            f"Consensus record {head_name} does not bind arm content "
            f"({arm['run_id']} idea {arm['idea_index']})",
        )
    quality_floor = consensus.get("quality_floor")
    floor_state = (
        quality_floor.get("state", "unresolved")
        if isinstance(quality_floor, dict)
        else "unresolved"
    )
    return {
        "consensus_record": (
            f"{EVALUATION_ROOT_RELPATH.as_posix()}/{arm['run_id']}/ideas/"
            f"{arm['idea_index']:06d}/ai/{CONSENSUS_DIRNAME}/{head_name}"
        ),
        "consensus_record_sha256": sha256_bytes(
            (consensus_dir / head_name).read_bytes()
        ),
        "coverage": consensus.get("coverage"),
        "state": floor_state,
    }


def reduce_pair_review(workspace_root: Path, pair_id: str) -> dict[str, Any]:
    """Merge the four slot-direction records into a stable pair result.

    The display-side verdicts are restored to anonymous content through the
    blind mapping; only four valid judgments pointing at the same content
    (or four ties) produce a stable result. The pre-registered quality floor
    of each arm is carried from its single-review consensus record and is
    never overridden by the overall preference.
    """
    pair_id = _validate_pair_id(pair_id)
    workspace = workspace_root.resolve(strict=True)
    document, _prompt, pair_path = _rederive_pair(workspace, pair_id)
    config = _load_review_config(workspace)
    evaluators = {
        slot: {
            "declared_provider": _config_evaluator(config, slot)["provider"],
            "declared_model_id": _config_evaluator(config, slot)["model_id"],
            "model_family": _config_evaluator(config, slot)["model_family"],
        }
        for slot in EVALUATOR_SLOTS
    }
    direction_results: dict[str, dict[str, Any]] = {}
    states: dict[tuple[str, str], str] = {}
    effective: dict[str, dict[tuple[str, str], str]] = {
        name: {} for name in PAIR_JUDGMENT_NAMES
    }
    refs_total = 0
    for slot in EVALUATOR_SLOTS:
        direction_results[slot] = {}
        for direction in DIRECTIONS:
            result = _pair_record_state(
                pair_path=pair_path,
                slot=slot,
                direction=direction,
                pair_id=pair_id,
                document=document,
            )
            direction_results[slot][direction] = result
            states[(slot, direction)] = result["state"]
            record = result["record"]
            if record is None:
                continue
            _check_config_binding(config, slot, record["evaluator"])
            refs_total += record["citation_verification"]["refs_total"]
            for name in PAIR_JUDGMENT_NAMES:
                effective[name][(slot, direction)] = _map_verdict_to_content(
                    record["judgments"][name]["verdict"],
                    direction,
                    document["blind_mapping"],
                )
    if all(state == "missing" for state in states.values()):
        fail(
            "REVIEW_RESPONSE_NOT_FOUND",
            "No validated pair review record in any slot/direction",
        )
    reduction = {
        name: _reduce_judgment(effective[name], states) for name in PAIR_JUDGMENT_NAMES
    }
    quality_floor = {
        content: _consensus_floor_for_arm(workspace, arm)
        for content, arm in document["arms"].items()
    }
    coverage = (
        "complete"
        if all(state == "valid" for state in states.values())
        else "incomplete"
    )

    reduction_dir = pair_path / REDUCTION_DIRNAME
    if reduction_dir.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The reduction directory is a symlink")
    try:
        reduction_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create reduction directory: {detail}")
    _fsync_directory(reduction_dir)
    versions = _existing_versions(reduction_dir)
    expected_supersedes = versions[-1][1] if versions else None
    new_seq = (versions[-1][0] + 1) if versions else 1
    record = {
        "schema_version": EVALUATION_AI_PAIR_REDUCTION_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "record_kind": "pair_ai_reduction",
        "pair_id": pair_id,
        "case_id": document["case_id"],
        "arms": document["arms"],
        "prompt_version": document["prompt_version"],
        "pair_package_sha256": sha256_bytes(canonical_json_bytes(document)),
        "review_config_sha256": _config_sha256(workspace),
        "coverage": coverage,
        "evaluators": evaluators,
        "direction_results": {
            slot: {
                direction: {
                    "effective": {
                        name: effective[name].get((slot, direction))
                        for name in PAIR_JUDGMENT_NAMES
                    },
                    "record_file": (
                        f"{slot}/{direction}/"
                        f"{direction_results[slot][direction]['record_name']}"
                        if direction_results[slot][direction]["record_name"]
                        else None
                    ),
                    "record_sha256": direction_results[slot][direction][
                        "record_sha256"
                    ],
                    "state": direction_results[slot][direction]["state"],
                }
                for direction in DIRECTIONS
            }
            for slot in EVALUATOR_SLOTS
        },
        "reduction": reduction,
        "quality_floor": quality_floor,
        "citation_verification": {
            "refs_total": refs_total,
            "semantic_support_verification": "not_performed",
        },
        "audit": {
            "reduced_at": _now(),
            "reduced_by": REDUCED_BY_TOOL,
            "validation_result": "passed",
        },
        "supersedes": expected_supersedes,
    }
    _check_pair_supersedes(
        record["supersedes"],
        expected_name=expected_supersedes,
        direction_dir=reduction_dir,
        pair_id=pair_id,
        direction=None,
        slot=None,
    )
    version_name = f"v{new_seq:04d}.json"
    report_bytes = _render_pair_report(record, version_name)
    report_html_bytes = _render_pair_report_html(record, version_name)
    record_bytes = canonical_json_bytes(record)
    _write_bytes_once(reduction_dir / version_name, record_bytes, label=version_name)
    _write_bytes_overwrite(
        pair_path / PAIR_REPORT_NAME, report_bytes, label=PAIR_REPORT_NAME
    )
    _write_bytes_overwrite(
        pair_path / PAIR_REPORT_HTML_NAME,
        report_html_bytes,
        label=PAIR_REPORT_HTML_NAME,
    )
    return {
        "coverage": coverage,
        "pair_id": pair_id,
        "pair_report": _pair_relpath(pair_id, PAIR_REPORT_NAME),
        "pair_report_html": _pair_relpath(pair_id, PAIR_REPORT_HTML_NAME),
        "quality_floor": {
            content: floor["state"] for content, floor in quality_floor.items()
        },
        "record": _pair_relpath(pair_id, REDUCTION_DIRNAME, version_name),
        "record_sha256": sha256_bytes(record_bytes),
        "reduction": reduction,
        "status": "reduced",
        "supersedes": expected_supersedes,
        "version": version_name,
    }


# ==============================================================================
# Pair report rendering
# ==============================================================================

_CONTENT_VALUE_ZH = {
    "content_1": "content_1 更优",
    "content_2": "content_2 更优",
    "a_more": "content_1 侵入更重",
    "b_more": "content_2 侵入更重",
    "equal": "两臂相当",
    "tie": "平局（tie）",
    "incomparable": "无法比较（incomparable）",
}
_JUDGMENT_ZH = {
    "overall_preference": "整体偏好（overall_preference）",
    "domain_method_fit": "领域-方法匹配（domain_method_fit）",
    "unjustified_ml_intrusion": "无依据 ML 侵入（unjustified_ml_intrusion）",
}


def _arm_label(arms: dict[str, Any], content: str) -> str:
    arm = arms[content]
    return (
        f"{content} = run `{arm['run_id']}` idea {arm['idea_index']}"
        f"（idea sha256 `{arm['idea_sha256'][:12]}…`）"
    )


def _render_pair_report(record: dict[str, Any], version_name: str) -> bytes:
    lines: list[str] = []
    lines.append("# 成对盲评还原报告（双评审）")
    lines.append("")
    lines.append(f"绑定：pair_id `{record['pair_id']}` · case_id `{record['case_id']}`")
    lines.append(
        f"还原记录：`{version_name}`（schema `{record['schema_version']}`，"
        f"authoring contract `{record['authoring_contract_version']}`）"
    )
    lines.append(
        f"Prompt 版本：`{record['prompt_version']}` · 覆盖：{record['coverage']}"
    )
    lines.append("")
    lines.append("## 臂绑定（私有还原；评审只见匿名 A/B）")
    for content in ("content_1", "content_2"):
        lines.append(f"- {_arm_label(record['arms'], content)}")
    for slot in EVALUATOR_SLOTS:
        evaluator = record["evaluators"][slot]
        lines.append(
            f"- {slot}：`{evaluator['declared_provider']}` / "
            f"`{evaluator['declared_model_id']}`（model family "
            f"`{evaluator['model_family']}`，声明值，程序未认证）"
        )
    lines.append("")
    lines.append(
        "> **证据限度**：本报告由四次独立上下文的盲评响应还原而来。换位检查与双评审"
        "降低但不能消除位置偏差与模型共同错误；稳定结果仍是 AI 评审建议，未经领域"
        "专家校准，不构成科研质量证明或晋升指令。质量底线独立于整体偏好保留。"
    )
    lines.append("")
    lines.append("## 三项判断的还原结果")
    for name in PAIR_JUDGMENT_NAMES:
        item = record["reduction"][name]
        lines.append("")
        if item["outcome"] == "stable":
            lines.append(
                f"### {_JUDGMENT_ZH[name]} — 稳定："
                f"{_CONTENT_VALUE_ZH[item['content_value']]}"
            )
        else:
            codes = (
                "；".join(reason["code"] for reason in item["reasons"]) or "no-reason"
            )
            lines.append(f"### {_JUDGMENT_ZH[name]} — incomparable（{codes}）")
        lines.append("")
        for slot in EVALUATOR_SLOTS:
            for direction in DIRECTIONS:
                result = record["direction_results"][slot][direction]
                if result["state"] == "valid":
                    lines.append(
                        f"- {slot}/{direction}：有效，还原为 "
                        f"`{result['effective'][name]}`"
                    )
                else:
                    lines.append(
                        f"- {slot}/{direction}：无有效记录（{result['state']}）"
                    )
        for reason in item["reasons"]:
            detail = f" — {reason['detail']}" if reason.get("detail") else ""
            targets = (
                f"（{'、'.join(reason['slot_directions'])}）"
                if reason.get("slot_directions")
                else ""
            )
            lines.append(f"- 分歧原因 `{reason['code']}`{targets}{detail}")
    lines.append("")
    lines.append("## 质量底线（pre-registered，独立于整体偏好）")
    for content in ("content_1", "content_2"):
        floor = record["quality_floor"][content]
        bound = (
            f"（共识记录 `{floor['consensus_record']}`，coverage {floor['coverage']}）"
            if floor["consensus_record"]
            else "（尚无双评审共识记录）"
        )
        lines.append(f"- {content}：{floor['state']}{bound}")
    lines.append("")
    lines.append(
        "未决或 violated 的质量底线不因 pair 结果改变；受影响的晋升判断必须保持未决。"
    )
    lines.append("")
    lines.append("## 引用核验")
    lines.append(
        f"- 四次评审引用共 {record['citation_verification']['refs_total']} 条，均通过"
        "逐字存在性核验；引用与论点之间的语义支持关系未由程序核验。"
    )
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


_PAIR_REPORT_CSS = """\
:root{--bg:#f5f6f8;--card:#ffffff;--ink:#1f2937;--muted:#64748b;--line:#e5e9f0;
--accent:#2563eb;--pos-ink:#15803d;--pos-bg:#e8f6ee;--mid-ink:#92580a;--mid-bg:#fdf3dd;
--neg-ink:#b91c1c;--neg-bg:#fdecec;--quote-bg:#f8fafc;--hl:#fff8e1;--hl-ink:#713f12;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.8 -apple-system,"PingFang SC","Hiragino Sans GB","Source Han Sans SC","Microsoft YaHei",sans-serif;}
main{max-width:880px;margin:32px auto;padding:0 20px;}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:34px 40px 26px;box-shadow:0 1px 3px rgba(16,24,40,.06);}
.kind{margin:0 0 4px;font-size:12.5px;font-weight:700;letter-spacing:.12em;
color:var(--accent);text-transform:uppercase;}
h1{margin:0 0 18px;font-size:24px;line-height:1.35;}
.meta{display:grid;grid-template-columns:1fr 1fr;gap:7px 30px;margin:0;padding:14px 0;
border-top:1px solid var(--line);border-bottom:1px solid var(--line);font-size:13.5px;}
.meta>div{display:flex;gap:10px;}
.meta dt{flex:0 0 8.5em;color:var(--muted);}
.meta dd{margin:0;word-break:break-all;}
code,.mono{font-family:"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;font-size:.92em;}
.limit{margin:16px 0 0;background:var(--hl);border-left:4px solid #eab308;
padding:10px 16px;border-radius:0 8px 8px 0;font-size:13.5px;color:var(--hl-ink);}
h2{margin:34px 0 4px;font-size:17px;padding-bottom:8px;border-bottom:1px solid var(--line);}
.dim{padding:16px 0 14px;border-bottom:1px dashed var(--line);}
.dim h3{margin:0 0 6px;font-size:15.5px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.dim .zh{font-weight:700;}
.badge{display:inline-block;padding:1px 10px;border-radius:999px;font-size:12.5px;
font-weight:700;font-family:"SF Mono",Menlo,Consolas,monospace;}
.badge.pos{color:var(--pos-ink);background:var(--pos-bg);}
.badge.abst{color:var(--mid-ink);background:var(--mid-bg);border:1.5px dashed #d97706;}
.rationale{margin:6px 0 10px;}
.digest{margin:6px 0 0;padding-left:22px;font-size:13.5px;}
footer{margin-top:30px;padding-top:12px;border-top:1px solid var(--line);
font-size:12px;color:var(--muted);}
@media (max-width:640px){.card{padding:22px 18px}.meta{grid-template-columns:1fr}}
"""


def _render_pair_report_html(record: dict[str, Any], version_name: str) -> bytes:
    """Render the light-theme pair report (self-contained, no scripts)."""

    def esc(value: Any) -> str:
        return _html_escape_module.escape(str(value), quote=True)

    judgment_sections: list[str] = []
    for name in PAIR_JUDGMENT_NAMES:
        item = record["reduction"][name]
        if item["outcome"] == "stable":
            badge = '<span class="badge pos">稳定</span>'
            headline = esc(_CONTENT_VALUE_ZH[item["content_value"]])
        else:
            badge = '<span class="badge abst">incomparable</span>'
            headline = (
                "、".join(esc(reason["code"]) for reason in item["reasons"]) or "—"
            )
        rows: list[str] = []
        for slot in EVALUATOR_SLOTS:
            for direction in DIRECTIONS:
                result = record["direction_results"][slot][direction]
                if result["state"] == "valid":
                    rows.append(
                        f"<li>{esc(slot)}/{esc(direction)}：有效，还原为 "
                        f"<code>{esc(result['effective'][name])}</code></li>"
                    )
                else:
                    rows.append(
                        f"<li>{esc(slot)}/{esc(direction)}：无有效记录"
                        f"（{esc(result['state'])}）</li>"
                    )
        reason_items = "".join(
            "<li><code>"
            + esc(reason["code"])
            + "</code>"
            + (
                f"（{'、'.join(esc(sd) for sd in reason['slot_directions'])}）"
                if reason.get("slot_directions")
                else ""
            )
            + (f" — {esc(reason['detail'])}" if reason.get("detail") else "")
            + "</li>"
            for reason in item["reasons"]
        )
        judgment_sections.append(
            '<article class="dim">'
            f'<h3><span class="zh">{esc(_JUDGMENT_ZH[name])}</span>{badge}</h3>'
            f'<p class="rationale">{headline}</p>'
            f'<ul class="digest">{"".join(rows)}</ul>'
            + (f'<ul class="digest">{reason_items}</ul>' if reason_items else "")
            + "</article>"
        )
    floor_items = "".join(
        f"<li>{esc(content)}：{esc(record['quality_floor'][content]['state'])}"
        + (
            f"（共识记录 <code>{esc(record['quality_floor'][content]['consensus_record'])}"
            f"</code>，coverage {esc(record['quality_floor'][content]['coverage'])}）"
            if record["quality_floor"][content]["consensus_record"]
            else "（尚无双评审共识记录）"
        )
        + "</li>"
        for content in ("content_1", "content_2")
    )
    arm_items = "".join(
        f"<li>{esc(_arm_label(record['arms'], content))}</li>"
        for content in ("content_1", "content_2")
    )
    evaluator_rows = "".join(
        f"<div><dt>{esc(slot)}</dt><dd>"
        f"<code>{esc(record['evaluators'][slot]['declared_provider'])}</code> / "
        f"<code>{esc(record['evaluators'][slot]['declared_model_id'])}</code> · "
        f"family <code>{esc(record['evaluators'][slot]['model_family'])}</code>"
        "（声明值，程序未认证）</dd></div>"
        for slot in EVALUATOR_SLOTS
    )
    meta_rows = [
        ("pair_id", f'<code>{esc(record["pair_id"])}</code>'),
        ("case_id", f'<code>{esc(record["case_id"])}</code>'),
        (
            "还原记录",
            f'<code>{esc(version_name)}</code>（schema {esc(record["schema_version"])}，'
            f'authoring contract {esc(record["authoring_contract_version"])}）',
        ),
        (
            "Prompt / 覆盖",
            f'<code>{esc(record["prompt_version"])}</code> · {esc(record["coverage"])}',
        ),
        ("评审配置", evaluator_rows),
    ]
    meta_html = "".join(
        f"<div><dt>{esc(label)}</dt><dd>{value}</dd></div>"
        for label, value in meta_rows
    )
    document = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>成对盲评还原报告 — {esc(record['pair_id'])}</title>\n"
        f"<style>{_PAIR_REPORT_CSS}</style>\n</head>\n<body>\n<main>\n"
        '<div class="card">\n'
        '<header>\n<p class="kind">Pair Blind Review Reduction · 双评审还原</p>\n'
        "<h1>成对盲评还原报告</h1>\n"
        f'<dl class="meta">{meta_html}</dl>\n'
        '<p class="limit"><strong>证据限度</strong>：本报告由四次独立上下文的盲评响应'
        "还原而来。换位检查与双评审降低但不能消除位置偏差与模型共同错误；稳定结果"
        "仍是 AI 评审建议，未经领域专家校准，不构成科研质量证明或晋升指令。"
        "质量底线独立于整体偏好保留。</p>\n"
        "</header>\n"
        "<section>\n<h2>臂绑定（私有还原；评审只见匿名 A/B）</h2>\n"
        f'<ul class="digest">{arm_items}</ul>\n</section>\n'
        "<section>\n<h2>三项判断的还原结果</h2>\n"
        + "".join(judgment_sections)
        + "</section>\n"
        "<section>\n<h2>质量底线（pre-registered，独立于整体偏好）</h2>\n"
        f'<ul class="digest">{floor_items}</ul>'
        '<p class="digest">未决或 violated 的质量底线不因 pair 结果改变；'
        "受影响的晋升判断必须保持未决。</p>\n</section>\n"
        "<footer>由 ai_scientist.ideation.ai_pair_review.reduce_pair_review "
        f"确定性渲染 · {esc(version_name)} · 本报告不是 Robert 的判断，也不是晋升依据。</footer>\n"
        "</div>\n</main>\n</body>\n</html>\n"
    )
    return document.encode("utf-8")
