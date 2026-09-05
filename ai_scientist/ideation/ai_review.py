"""AI-assisted single-review evaluation (authoring contract v2, ticket 01).

Implements the single-idea AI review mode of the evaluation authoring
contract v2 (docs/agents/ai-review-authoring-contract-v2.md) on top of the
existing post-seal evaluation machinery:

- export_review_package: derives an anonymous, deterministic review package
  (Workshop text, the sealed idea fields, the complete per-paper release
  record of the sidecar-bound retrieval operations, the Target Comparator,
  and an honest audit scope statement) plus a ready-to-send review request
  rendered from the hash-pinned single-review prompt template.
- import_review_response: stores an operator-supplied model response
  write-once with explicit ``user_supplied`` provenance (the program never
  claims it executed the model call), parses the response text, and reports
  parse failures explicitly while retaining the raw response.
- validate_ai_review: fail-closed validation of the latest stored response —
  closed schema, seven dimensions with the original rubric verdict enums and
  the independent ``insufficient_evidence`` status, per-ref verbatim quote
  verification against the package sources, linear supersedes — then commits
  the immutable write-once AI review record and the regenerable Chinese
  evidence card.

AI review files live under ``artifacts/evaluations/<run_id>/ideas/<idx>/ai/``
so the v1 human Evaluation Artifact layout, its validation, and coverage
stay byte-identical. A single-review record is honest advice for Robert: it
carries no promotion authority and no claim of scientific ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
import html as _html_escape_module
import json
from pathlib import Path
import re
from typing import Any

from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
    workspace_relative_path,
)
from .contract import (
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_PATH,
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_SHA256,
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION,
    EVALUATION_AI_REVIEW_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_RESPONSE_SCHEMA_VERSION,
    EVALUATION_AUTHORING_CONTRACT_VERSION,
    EVALUATION_REVIEW_MATERIALS_SCHEMA_VERSION,
    EVALUATION_REVIEW_PACKAGE_SCHEMA_VERSION,
    EVALUATION_REVIEW_RESPONSE_IMPORT_SCHEMA_VERSION,
    _now,
)
from .errors import fail
from .evaluation import (
    _check_supersedes,
    _collect_release_record,
    _evaluation_idea_dir,
    _existing_versions,
    _load_context_and_comparator,
    _load_idea_evidence,
    _load_rubric_policy,
    _validate_idea_index,
    _write_bytes_once,
    _write_bytes_overwrite,
)
from .run_store import _fsync_directory
from .schema import (
    closed_object,
    nonempty_string,
    timestamp,
)

AI_DIRNAME = "ai"
PACKAGE_NAME = "review-package.json"
REQUEST_NAME = "review-request.txt"
RESPONSES_DIRNAME = "responses"
CARD_NAME = "evidence-card.md"
CARD_HTML_NAME = "evidence-card.html"
RESPONSE_NAME_PATTERN = re.compile(r"r(\d{4})\.json\Z")
FENCE_BLOCK_PATTERN = re.compile(
    r"```(?:json)?[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```", re.DOTALL
)

REVIEW_TASK_ID = "single_idea_review"
JUDGED_STATUS = "judged"
INSUFFICIENT_EVIDENCE_STATUS = "insufficient_evidence"
ASSESSMENT_STATUSES = frozenset({JUDGED_STATUS, INSUFFICIENT_EVIDENCE_STATUS})
REF_STANCES = frozenset({"supports", "contradicts"})
VALIDATED_BY_TOOL = "ai_scientist.ideation.ai_review.validate_ai_review"
# Dimensions whose judged claims are scope statements about the audit facts:
# the template requires citing the audit_statement source so the claimed
# scope is anchored to the checks the package actually carries.
AUDIT_CITED_DIMENSIONS = frozenset({"contamination_signal", "leakage_review"})
AUDIT_SOURCE_KIND = "audit_statement"

JUDGMENT_KEYS = {
    "assessment_status",
    "proposed_verdict",
    "rationale",
    "evidence_refs",
    "key_assumptions",
    "missing_information",
}
RESPONSE_TOP_KEYS = {"task", "dimensions"}
INFERENCE_MARKER = "推断："

IDEA_FIELD_ORDER = (
    "Name",
    "Title",
    "Short Hypothesis",
    "Related Work",
    "Abstract",
    "Experiments",
    "Risk Factors and Limitations",
)

# Canonical card rendering order for the pinned rubric v1 dimensions; any
# dimension outside this order (possible only after a rubric version bump)
# is appended sorted.
RUBRIC_DIMENSION_ORDER = (
    "problem_space_match",
    "target_contribution_overlap",
    "relative_novelty",
    "feasibility_soundness",
    "contamination_signal",
    "leakage_review",
    "grounding_synthesis",
)


def _card_dimension_order(judgments: dict[str, Any]) -> list[str]:
    known = [dim for dim in RUBRIC_DIMENSION_ORDER if dim in judgments]
    extras = sorted(set(judgments) - set(known))
    return known + extras


# Presentation-only mappings for the HTML evidence card. They carry no
# contract semantics: colors are reading aids, not judgments, and the
# badge semantics follow the pre-registered quality floor dimensions.
DIMENSION_ZH_LABELS = {
    "problem_space_match": "问题空间匹配度",
    "target_contribution_overlap": "与 target 贡献的重叠性质",
    "relative_novelty": "相对新颖度",
    "feasibility_soundness": "可行性与合理性",
    "contamination_signal": "污染信号检查",
    "leakage_review": "泄漏复核",
    "grounding_synthesis": "文献综合质量",
}
VERDICT_TONE = {
    "aligned": "pos",
    "sound": "pos",
    "clean": "pos",
    "synthesized": "pos",
    "beyond_target": "pos",
    "adjacent": "mid",
    "partial_overlap": "mid",
    "on_par": "mid",
    "questionable": "mid",
    "partially_synthesized": "mid",
    "mismatched": "neg",
    "unsound": "neg",
    "leak_found": "neg",
    "signal_found": "neg",
    "name_dropped": "neg",
    "below_target": "neg",
    "recover": "neu",
    "materially_different": "neu",
}


@dataclass(frozen=True, slots=True)
class ReviewPrompt:
    """The pinned, versioned single-review prompt template."""

    version: str
    text: str
    sha256: str


def _load_review_prompt(workspace: Path) -> ReviewPrompt:
    path = workspace / EVALUATION_AI_REVIEW_PROMPT_SINGLE_PATH
    if not path.is_file():
        fail("MISSING_ARTIFACT", "AI review prompt template is missing")
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != EVALUATION_AI_REVIEW_PROMPT_SINGLE_SHA256:
        fail("POLICY_DRIFT", "AI review prompt template hash changed")
    return ReviewPrompt(
        version=EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION,
        text=data.decode("utf-8"),
        sha256=digest,
    )


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _idea_field_text(value: Any, field: str) -> str:
    """Render one finalized-idea field as quotable source text."""
    if isinstance(value, list):
        return "\n".join(
            f"{position}. {item}" for position, item in enumerate(value, start=1)
        )
    return str(value)


def _collect_released_papers(
    context: Any, run_id: str, sidecar: dict[str, Any], grounding: list[str]
) -> dict[str, dict[str, Any]]:
    """The complete per-paper release record of the sidecar-bound retrieval
    operations (every paper returned, not only declared grounding papers),
    each entry flagged with its grounding membership. Declared grounding
    papers missing from the payloads still fail closed."""
    released = _collect_release_record(context, run_id, sidecar)
    grounding_set = set(grounding)
    for paper_id in grounding:
        if paper_id not in released:
            fail(
                "EVALUATION_LINKAGE_INCONSISTENT",
                f"Declared grounding paper {paper_id} appears in no retrieval payload",
            )
    return {
        paper_id: {
            "declared_grounding": paper_id in grounding_set,
            "title": entry[0]["title"],
            "occurrences": entry,
        }
        for paper_id, entry in released.items()
    }


def _derive_audit_checks() -> list[dict[str, str]]:
    """The honest audit scope facts derivable from a sealed run's binding.

    Every claim is limited to what the Evidence Chain can show; the absent
    provider-side contamination view is reported as incomplete so downstream
    judgments cannot overstate the reviewed scope.
    """
    return [
        {
            "check_id": "generation_payload_hygiene",
            "status": "complete",
            "result": "passed_for_finalized_ideas",
            "scope": (
                "generation-time FinalizeIdea payload hygiene scan; "
                "hygiene-hit submissions seal the run failed and are never "
                "finalized, so every finalized idea passed the scan"
            ),
        },
        {
            "check_id": "workshop_semantic_review",
            "status": "complete",
            "result": "approved",
            "scope": (
                "semantic approval checks recorded at Workshop approval time; "
                "covers the Workshop text only"
            ),
        },
        {
            "check_id": "retrieval_release_record",
            "status": "complete",
            "result": "recorded",
            "scope": (
                "the retrieval_segment sources in this package are the "
                "complete per-paper release record of the sidecar-bound "
                "retrieval operations; papers beyond the Declared Grounding "
                "are included and marked declared_grounding=false"
            ),
        },
        {
            "check_id": "provider_training_contamination_audit",
            "status": "incomplete",
            "result": "not_performed",
            "scope": (
                "no auditable view of provider-side training data exposure "
                "exists in this evidence chain"
            ),
        },
    ]


def _render_audit_statement(checks: list[dict[str, str]]) -> str:
    parts = [
        f"{check['check_id']}: {check['status']}/{check['result']} — {check['scope']}"
        for check in checks
    ]
    return (
        "审计范围声明（audit_statement）：本材料包的审计检查事实如下。"
        + " ".join(parts)
        + " 相关判断受上述范围约束；incomplete 检查相关的维度必须弃权或明确限定范围。"
    )


def _build_review_document(
    *,
    run_id: str,
    workspace: Path,
    context: Any,
    idea_index: int,
    idea_entry: dict[str, Any],
    idea: dict[str, Any],
    grounding: list[str],
    released: dict[str, dict[str, Any]],
    target: Any,
    rubric: Any,
) -> dict[str, Any]:
    """Derive the deterministic, anonymous review package document."""
    sources: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []

    def _add_source(
        kind: str, text: str, visible: dict[str, Any], private: dict[str, Any]
    ) -> str:
        source_id = f"S{len(sources) + 1:03d}"
        sources.append({"source_id": source_id, "kind": kind, "text": text, **visible})
        registry.append(
            {
                "source_id": source_id,
                "kind": kind,
                "text_sha256": sha256_bytes(text.encode("utf-8")),
                **private,
            }
        )
        return source_id

    workshop_path = workspace_relative_path(
        workspace, context.workshop["path"], label="workshop_path"
    )
    workshop_text = (workspace / workshop_path).read_text(encoding="utf-8")
    _add_source(
        "workshop", workshop_text, {}, {"workshop_sha256": context.workshop["sha256"]}
    )
    for field in IDEA_FIELD_ORDER:
        _add_source(
            "idea_field",
            _idea_field_text(idea[field], field),
            {"field": field},
            {"field": field},
        )
    _add_source(
        "target_comparator",
        target.abstract_summary,
        {
            "part": "abstract_summary",
            "title": target.reference["title"],
            "doi": target.reference["doi"],
        },
        {"part": "abstract_summary"},
    )
    _add_source(
        "target_comparator",
        target.raw_abstract,
        {
            "part": "abstract",
            "title": target.reference["title"],
            "doi": target.reference["doi"],
        },
        {"part": "abstract"},
    )
    checks = _derive_audit_checks()
    _add_source("audit_statement", _render_audit_statement(checks), {}, {})
    for paper_id, entry in released.items():
        for occurrence in entry["occurrences"]:
            for segment in occurrence["segments"]:
                _add_source(
                    "retrieval_segment",
                    segment["text"],
                    {
                        "paper_title": entry["title"],
                        "content_type": segment["content_type"],
                        "declared_grounding": entry["declared_grounding"],
                    },
                    {
                        "paper_id": paper_id,
                        "operation_seq": occurrence["operation_seq"],
                    },
                )

    model_payload = {
        "schema_version": EVALUATION_REVIEW_MATERIALS_SCHEMA_VERSION,
        "materials": {"sources": sources},
        "task": REVIEW_TASK_ID,
    }
    return {
        "schema_version": EVALUATION_REVIEW_PACKAGE_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "run_id": run_id,
        "case_id": context.case_id,
        "terminal_outcome": context.terminal_outcome,
        "seal_sha256": context.seal_sha256,
        "idea": {
            "idea_index": idea_index,
            "relative_path": idea_entry["relative_path"],
            "sha256": idea_entry["sha256"],
        },
        "target_paper": target.reference,
        "rubric_version": rubric.version,
        "prompt_version": EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION,
        "response_schema_version": EVALUATION_AI_REVIEW_RESPONSE_SCHEMA_VERSION,
        "model_payload_sha256": sha256_bytes(canonical_json_bytes(model_payload)),
        "audit_checks": checks,
        "source_registry": registry,
        "model_payload": model_payload,
    }


def _render_review_request(prompt_text: str, model_payload: dict[str, Any]) -> bytes:
    payload_text = json.dumps(
        model_payload, ensure_ascii=False, sort_keys=True, indent=2
    )
    return (prompt_text.rstrip("\n") + "\n\n" + payload_text + "\n").encode("utf-8")


def _ai_dir(idea_dir: Path) -> Path:
    ai_path = idea_dir / AI_DIRNAME
    if ai_path.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The ai review directory is a symlink")
    return ai_path


def _ensure_ai_dirs(ai_path: Path, *, with_responses: bool) -> None:
    try:
        ai_path.mkdir(parents=True, exist_ok=True)
        if with_responses:
            responses_dir = ai_path / RESPONSES_DIRNAME
            if responses_dir.is_symlink():
                fail("SYMLINK_FORBIDDEN", "The responses directory is a symlink")
            responses_dir.mkdir(exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create ai review directory: {detail}")
    _fsync_directory(ai_path)


def _derive_package(
    *,
    workspace: Path,
    run_id: str,
    idea_index: int,
    context: Any,
    target: Any,
    rubric: Any,
) -> tuple[dict[str, Any], ReviewPrompt]:
    """Derive the deterministic package document and load the pinned prompt."""
    idea, grounding, sidecar, idea_entry = _load_idea_evidence(
        context, run_id, idea_index
    )
    prompt = _load_review_prompt(workspace)
    released = _collect_released_papers(context, run_id, sidecar, grounding)
    document = _build_review_document(
        run_id=run_id,
        workspace=workspace,
        context=context,
        idea_index=idea_index,
        idea_entry=idea_entry,
        idea=idea,
        grounding=grounding,
        released=released,
        target=target,
        rubric=rubric,
    )
    return document, prompt


def export_review_package(
    workspace_root: Path,
    run_id: str,
    idea_index: int,
) -> dict[str, Any]:
    """Export the anonymous review package and the ready-to-send request.

    The package is a deterministic function of the sealed run, the pinned
    rubric, and the pinned prompt template: re-export produces byte-identical
    files, so A/B and B/A swap material stays identical.
    """
    idea_index = _validate_idea_index(idea_index)
    workspace, context, target, rubric = _load_context_and_comparator(
        workspace_root, run_id
    )
    document, prompt = _derive_package(
        workspace=workspace,
        run_id=run_id,
        idea_index=idea_index,
        context=context,
        target=target,
        rubric=rubric,
    )
    package_bytes = canonical_json_bytes(document)
    request_bytes = _render_review_request(prompt.text, document["model_payload"])

    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    ai_path = _ai_dir(idea_dir)
    _ensure_ai_dirs(ai_path, with_responses=False)
    _write_bytes_overwrite(ai_path / PACKAGE_NAME, package_bytes, label=PACKAGE_NAME)
    _write_bytes_overwrite(ai_path / REQUEST_NAME, request_bytes, label=REQUEST_NAME)

    return {
        "package": _ai_relpath(run_id, idea_index, PACKAGE_NAME),
        "package_sha256": sha256_bytes(package_bytes),
        "prompt_version": prompt.version,
        "request": _ai_relpath(run_id, idea_index, REQUEST_NAME),
        "request_sha256": sha256_bytes(request_bytes),
        "status": "exported",
    }


def _ai_relpath(run_id: str, idea_index: int, *parts: str) -> str:
    return (
        Path("artifacts/evaluations")
        / run_id
        / "ideas"
        / f"{idea_index:06d}"
        / AI_DIRNAME
        / Path(*parts)
    ).as_posix()


def _parse_response_text(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse a model response: a bare JSON object or one fenced JSON block."""
    stripped = text.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value, None
    if value is not None:
        return None, "response JSON is not an object"
    blocks = FENCE_BLOCK_PATTERN.findall(stripped)
    if len(blocks) > 1:
        return None, "multiple fenced JSON blocks; refusing to choose one"
    if len(blocks) == 1:
        try:
            value = json.loads(blocks[0])
        except json.JSONDecodeError as exc:
            return None, f"fenced response JSON failed to parse: {exc.msg}"
        if isinstance(value, dict):
            return value, None
        return None, "fenced response JSON is not an object"
    return None, "response is neither a JSON object nor a single fenced JSON object"


def import_review_response(
    workspace_root: Path,
    run_id: str,
    idea_index: int,
    *,
    response_path: Path,
    provider: str,
    model_id: str,
    responded_at: str,
    supplied_by: str,
    imported_by: str,
) -> dict[str, Any]:
    """Store one operator-supplied model response write-once and parse it.

    Provenance is always ``user_supplied``: this command records who provided
    the file, never a claim that the program executed the model call. An
    unparseable response is retained on disk and reported as an explicit
    failure; it can never become a validated record.
    """
    idea_index = _validate_idea_index(idea_index)
    provider = nonempty_string(provider, label="provider")
    model_id = nonempty_string(model_id, label="model_id")
    timestamp(responded_at, label="responded_at")
    supplied_by = nonempty_string(supplied_by, label="supplied_by")
    imported_by = nonempty_string(imported_by, label="imported_by")
    workspace, context, target, rubric = _load_context_and_comparator(
        workspace_root, run_id
    )

    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    ai_path = _ai_dir(idea_dir)
    package_path = ai_path / PACKAGE_NAME
    if not package_path.is_file() or package_path.is_symlink():
        fail(
            "REVIEW_PACKAGE_NOT_FOUND",
            f"No {PACKAGE_NAME} for idea {idea_index}; run evaluation "
            "export-review-package first",
        )
    package_bytes = package_path.read_bytes()
    document, prompt = _rederive_package(
        workspace=workspace,
        run_id=run_id,
        idea_index=idea_index,
        context=context,
        target=target,
        rubric=rubric,
        package_bytes=package_bytes,
    )
    request_bytes = _render_review_request(prompt.text, document["model_payload"])
    request_path = ai_path / REQUEST_NAME
    if not request_path.is_file() or request_path.is_symlink():
        fail(
            "REVIEW_REQUEST_NOT_FOUND",
            f"No {REQUEST_NAME} for idea {idea_index}; run evaluation "
            "export-review-package first",
        )
    if request_path.read_bytes() != request_bytes:
        fail(
            "REVIEW_REQUEST_DRIFT",
            f"{REQUEST_NAME} on disk does not match the pinned prompt render; "
            "re-run evaluation export-review-package",
        )
    if response_path.is_symlink() or not response_path.is_file():
        fail("INVALID_INPUT", f"Response file is missing: {response_path}")
    try:
        response_text = response_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_RESPONSE_ENCODING", f"Response file is not UTF-8: {exc}")

    parsed, parse_error = _parse_response_text(response_text)
    parse_status = "ok" if parsed is not None else "invalid_format"

    responses_dir = ai_path / RESPONSES_DIRNAME
    _ensure_ai_dirs(ai_path, with_responses=True)
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
        "review_package_sha256": sha256_bytes(package_bytes),
        "review_request_sha256": sha256_bytes(request_bytes),
    }
    _write_bytes_once(
        responses_dir / response_name,
        canonical_json_bytes(response_record),
        label=response_name,
    )

    result = {
        "parse_status": parse_status,
        "prompt_version": prompt.version,
        "response_file": _ai_relpath(
            run_id, idea_index, RESPONSES_DIRNAME, response_name
        ),
        "response_seq": new_seq,
        "run_id": run_id,
        "idea_index": idea_index,
        "status": "imported",
    }
    if parse_error is not None:
        result["parse_error"] = parse_error
    return result


def _rederive_package(
    *,
    workspace: Path,
    run_id: str,
    idea_index: int,
    context: Any,
    target: Any,
    rubric: Any,
    package_bytes: bytes,
) -> tuple[dict[str, Any], ReviewPrompt]:
    """Re-derive the package document from the sealed chain and prove the
    on-disk bytes match, so tampered or stale packages fail closed."""
    document, prompt = _derive_package(
        workspace=workspace,
        run_id=run_id,
        idea_index=idea_index,
        context=context,
        target=target,
        rubric=rubric,
    )
    derived_bytes = canonical_json_bytes(document)
    if derived_bytes != package_bytes:
        fail(
            "REVIEW_PACKAGE_DRIFT",
            "The review package on disk does not match a re-derivation from "
            "the sealed run; re-run evaluation export-review-package",
        )
    if document["prompt_version"] != prompt.version:
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            "The package prompt version is not approved",
        )
    return document, prompt


def _check_evidence_ref(
    ref: object, sources_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    ref_value = closed_object(
        ref,
        label="evidence_ref",
        keys={"claim", "quote", "source_id", "stance"},
    )
    source_id = nonempty_string(ref_value["source_id"], label="evidence_ref.source_id")
    quote = nonempty_string(ref_value["quote"], label="evidence_ref.quote")
    claim = nonempty_string(ref_value["claim"], label="evidence_ref.claim")
    stance = ref_value["stance"]
    if stance not in REF_STANCES:
        fail(
            "INVALID_SCHEMA",
            "evidence_ref.stance must be one of ['supports', 'contradicts']",
        )
    source = sources_by_id.get(source_id)
    if source is None:
        fail(
            "CITATION_SOURCE_NOT_FOUND",
            f"evidence_ref cites unknown source_id {source_id}",
        )
    if _normalize_text(quote) not in _normalize_text(source["text"]):
        fail(
            "CITATION_QUOTE_NOT_FOUND",
            f"evidence_ref quote is not a verbatim excerpt of source {source_id}",
        )
    return ref_value


def _check_review_judgments(
    dimensions: object, rubric: Any, sources_by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Seven dimensions, original verdict enums, independent abstention."""
    criteria_ids = {criterion_id for criterion_id, _ in rubric.criteria}
    verdict_map = dict(rubric.criteria)
    dims = closed_object(dimensions, label="dimensions", keys=criteria_ids)
    audit_source_ids = {
        source_id
        for source_id, source in sources_by_id.items()
        if source["kind"] == AUDIT_SOURCE_KIND
    }
    refs_total = 0
    for criterion_id in sorted(criteria_ids):
        judgment = closed_object(
            dims[criterion_id],
            label=f"dimensions.{criterion_id}",
            keys=JUDGMENT_KEYS,
        )
        status = judgment["assessment_status"]
        if status not in ASSESSMENT_STATUSES:
            fail(
                "INVALID_SCHEMA",
                f"dimensions.{criterion_id}.assessment_status must be one of "
                f"{sorted(ASSESSMENT_STATUSES)}",
            )
        rationale = judgment["rationale"]
        if not isinstance(rationale, str) or not rationale.strip():
            fail(
                "INVALID_SCHEMA",
                f"dimensions.{criterion_id}.rationale must be a non-empty string",
            )
        assumptions = judgment["key_assumptions"]
        if not isinstance(assumptions, list) or not all(
            isinstance(item, str) and item.strip() for item in assumptions
        ):
            fail(
                "INVALID_SCHEMA",
                f"dimensions.{criterion_id}.key_assumptions must be an array "
                "of non-empty strings",
            )
        missing = judgment["missing_information"]
        if not isinstance(missing, list) or not all(
            isinstance(item, str) and item.strip() for item in missing
        ):
            fail(
                "INVALID_SCHEMA",
                f"dimensions.{criterion_id}.missing_information must be an "
                "array of non-empty strings",
            )
        refs_value = judgment["evidence_refs"]
        if not isinstance(refs_value, list):
            fail(
                "INVALID_SCHEMA",
                f"dimensions.{criterion_id}.evidence_refs must be an array",
            )
        refs = [_check_evidence_ref(ref, sources_by_id) for ref in refs_value]
        refs_total += len(refs)
        verdict = judgment["proposed_verdict"]
        if status == JUDGED_STATUS:
            if not isinstance(verdict, str) or verdict not in verdict_map[criterion_id]:
                fail(
                    "INVALID_SCHEMA",
                    f"dimensions.{criterion_id}.proposed_verdict must be one of "
                    f"{list(verdict_map[criterion_id])} for a judged dimension",
                )
            if missing:
                fail(
                    "INVALID_SCHEMA",
                    f"dimensions.{criterion_id} is judged but claims missing "
                    "information; abstain instead",
                )
            if not refs and not rationale.lstrip().startswith(INFERENCE_MARKER):
                fail(
                    "EVIDENCE_REF_REQUIRED",
                    f"dimensions.{criterion_id} is judged without evidence "
                    f"refs; the rationale must start with '{INFERENCE_MARKER}' "
                    "and state the inference basis",
                )
            if criterion_id in AUDIT_CITED_DIMENSIONS and not any(
                ref["source_id"] in audit_source_ids for ref in refs
            ):
                fail(
                    "AUDIT_STATEMENT_REF_REQUIRED",
                    f"dimensions.{criterion_id} is judged without citing the "
                    "audit_statement source; its scope claim must anchor to "
                    "the audit facts the package carries",
                )
        else:
            if verdict is not None:
                fail(
                    "INVALID_SCHEMA",
                    f"dimensions.{criterion_id} abstains but proposes a "
                    "verdict; set proposed_verdict to null",
                )
            if not missing:
                fail(
                    "INVALID_SCHEMA",
                    f"dimensions.{criterion_id} abstains without naming the "
                    "missing material in missing_information",
                )
    return {"dimensions": dims, "refs_total": refs_total}


def _load_head_response(ai_path: Path) -> tuple[str, dict[str, Any]]:
    responses_dir = ai_path / RESPONSES_DIRNAME
    if not responses_dir.is_dir() or responses_dir.is_symlink():
        fail(
            "REVIEW_RESPONSE_NOT_FOUND",
            "No imported review responses; run evaluation import-review-response first",
        )
    versions = _existing_versions(
        responses_dir, pattern=RESPONSE_NAME_PATTERN, label="Review response"
    )
    if not versions:
        fail("REVIEW_RESPONSE_NOT_FOUND", "No imported review responses found")
    head_name = versions[-1][1]
    document = parse_json_bytes(
        (responses_dir / head_name).read_bytes(), label=f"review response {head_name}"
    )
    if not isinstance(document, dict):
        fail("RUN_CORRUPT", f"Review response {head_name} is not a JSON object")
    return head_name, document


def _render_evidence_card(record: dict[str, Any], version_name: str) -> bytes:
    """Render the Chinese evidence card from a validated record."""
    evaluator = record["evaluator"]
    lines: list[str] = []
    lines.append("# AI 评审证据卡（单评审建议）")
    lines.append("")
    lines.append(
        f"绑定：run_id `{record['run_id']}` · idea_index "
        f"{record['idea']['idea_index']} · case_id `{record['case_id']}`"
    )
    lines.append(
        f"评审记录：`{version_name}`（schema `{record['schema_version']}`，"
        f"authoring contract `{record['authoring_contract_version']}`）"
    )
    lines.append(
        f"Prompt 版本：`{record['prompt_version']}` · 响应契约："
        f"`{record['response_schema_version']}`"
    )
    lines.append(
        f"评审模型（声明值）：provider `{evaluator['declared_provider']}` / "
        f"model `{evaluator['declared_model_id']}` · Provenance："
        f"`{evaluator['provenance']['kind']}`（由 {evaluator['provenance']['supplied_by']} "
        f"提供，导入人 {evaluator['imported_by']}；程序未亲自执行该模型调用）"
    )
    lines.append(
        f"程序验证：`{record['audit']['validated_by']}` 于 {record['audit']['validated_at']}"
    )
    lines.append("")
    lines.append(
        "> **证据限度**：本卡是单个 AI 评审的建议，未经领域专家校准，不构成科研质量"
        "证明、官方分数或晋升指令。引用仅经程序逐字存在性核验；引用与论点之间的语义"
        "支持关系未自动核验。弃权与未决按原样保留。"
    )
    lines.append("")
    lines.append("## 七维建议")
    abstentions: list[tuple[str, dict[str, Any]]] = []
    assumptions: list[str] = []
    refs_total = 0
    for criterion_id in _card_dimension_order(record["judgments"]):
        judgment = record["judgments"][criterion_id]
        lines.append("")
        status = judgment["assessment_status"]
        if status == JUDGED_STATUS:
            lines.append(f"### {criterion_id} — 建议 `{judgment['proposed_verdict']}`")
        else:
            lines.append(f"### {criterion_id} — 弃权（{INSUFFICIENT_EVIDENCE_STATUS}）")
            abstentions.append((criterion_id, judgment))
        lines.append("")
        lines.append(f"- 理由：{judgment['rationale']}")
        for ref in judgment["evidence_refs"]:
            refs_total += 1
            lines.append(
                f"- 引用 [`{ref['source_id']}`] “{ref['quote']}” — "
                f"{'支持' if ref['stance'] == 'supports' else '反驳'}论点：{ref['claim']}"
                "（存在性已核验；语义支持未核验）"
            )
        if judgment["key_assumptions"]:
            for assumption in judgment["key_assumptions"]:
                assumptions.append(assumption)
            lines.append("- 关键假设：" + "；".join(judgment["key_assumptions"]))
        if judgment["missing_information"]:
            lines.append("- 缺失信息：" + "；".join(judgment["missing_information"]))
    lines.append("")
    lines.append("## 未决与弃权汇总")
    if abstentions:
        for criterion_id, judgment in abstentions:
            lines.append(
                f"- {criterion_id} — {INSUFFICIENT_EVIDENCE_STATUS}：缺少 "
                + "；".join(judgment["missing_information"])
            )
        lines.append("")
        lines.append("未决维度不构成通过或否决；其影响的后续判断必须保持未决状态。")
    else:
        lines.append("本次评审七个维度均给出建议，无弃权。")
    lines.append("")
    lines.append("## 关键假设汇总")
    if assumptions:
        for assumption in assumptions:
            lines.append(f"- {assumption}")
    else:
        lines.append("无。")
    lines.append("")
    lines.append("## 引用核验")
    lines.append(
        f"- 引用共 {refs_total} 条，全部通过逐字存在性核验（引用片段确实出现在对应"
        "来源原文中）；引用与论点之间的语义支持关系未由程序核验。"
    )
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


_CARD_CSS = """\
:root{--bg:#f5f6f8;--card:#ffffff;--ink:#1f2937;--muted:#64748b;--line:#e5e9f0;
--accent:#2563eb;--pos-ink:#15803d;--pos-bg:#e8f6ee;--mid-ink:#92580a;--mid-bg:#fdf3dd;
--neg-ink:#b91c1c;--neg-bg:#fdecec;--neu-ink:#1d4ed8;--neu-bg:#e9effc;
--quote-bg:#f8fafc;--hl:#fff8e1;--hl-ink:#713f12;--faint:#94a3b8;}
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
.legend{margin:0 0 6px;font-size:12.5px;color:var(--muted);}
.dim{padding:16px 0 14px;border-bottom:1px dashed var(--line);}
.dim:last-of-type{border-bottom:none;}
.dim h3{margin:0 0 6px;font-size:15.5px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.dim .zh{font-weight:700;}
.dim .en{font-family:"SF Mono",Menlo,Consolas,monospace;font-size:12.5px;
color:var(--muted);font-weight:600;}
.badge{display:inline-block;padding:1px 10px;border-radius:999px;font-size:12.5px;
font-weight:700;font-family:"SF Mono",Menlo,Consolas,monospace;}
.badge.pos{color:var(--pos-ink);background:var(--pos-bg);}
.badge.mid{color:var(--mid-ink);background:var(--mid-bg);}
.badge.neg{color:var(--neg-ink);background:var(--neg-bg);}
.badge.neu{color:var(--neu-ink);background:var(--neu-bg);}
.badge.abst{color:var(--mid-ink);background:transparent;border:1.5px dashed #d97706;}
.rationale{margin:6px 0 10px;}
.refs{list-style:none;margin:0;padding:0;display:grid;gap:9px;}
.refs li{background:var(--quote-bg);border:1px solid var(--line);border-radius:10px;
padding:10px 14px;}
.chip{display:inline-block;padding:0 8px;border:1px solid var(--line);border-radius:6px;
background:#fff;font-family:"SF Mono",Menlo,Consolas,monospace;font-size:12px;
font-weight:700;color:var(--muted);}
.refs blockquote{margin:7px 0 4px;padding:1px 0 1px 12px;border-left:3px solid #cbd5e1;
color:#334155;font-size:14px;}
.claim{margin:2px 0 0;font-size:13.5px;color:var(--muted);}
.stance{font-weight:700;margin-right:4px;}
.stance.sup{color:var(--pos-ink);}
.stance.con{color:var(--neg-ink);}
.verify{color:var(--faint);font-size:12px;}
details{margin-top:8px;font-size:13.5px;}
summary{cursor:pointer;color:var(--accent);}
details ul{margin:6px 0 2px;padding-left:22px;}
.missing-inline{margin:8px 0 0;padding:8px 14px;background:var(--mid-bg);
border-radius:8px;font-size:13.5px;color:var(--mid-ink);}
.digest{margin:6px 0 0;font-size:14px;}
.digest.none{color:var(--pos-ink);}
footer{margin-top:30px;padding-top:12px;border-top:1px solid var(--line);
font-size:12px;color:var(--faint);}
@media (max-width:640px){.card{padding:22px 18px}.meta{grid-template-columns:1fr}}
@media print{body{background:#fff}main{margin:0;padding:0;max-width:none}
.card{box-shadow:none;border:none;padding:0 6px}}
"""


def _render_evidence_card_html(record: dict[str, Any], version_name: str) -> bytes:
    """Render the light-theme, self-contained HTML evidence card.

    A single deterministic document with no scripts and no external
    resources; all dynamic text is HTML-escaped. Badge colors are reading
    aids keyed to the pre-registered quality floor, not extra judgments.
    """

    def esc(value: Any) -> str:
        return _html_escape_module.escape(str(value), quote=True)

    def esc_all(values: list[str]) -> str:
        return "".join(f"<li>{esc(value)}</li>" for value in values)

    evaluator = record["evaluator"]
    provenance = evaluator["provenance"]
    abstentions: list[tuple[str, dict[str, Any]]] = []
    assumptions: list[str] = []
    refs_total = 0

    dim_sections: list[str] = []
    for criterion_id in _card_dimension_order(record["judgments"]):
        judgment = record["judgments"][criterion_id]
        status = judgment["assessment_status"]
        if status == JUDGED_STATUS:
            verdict = esc(judgment["proposed_verdict"])
            tone = VERDICT_TONE.get(judgment["proposed_verdict"], "neu")
            badge = f'<span class="badge {tone}">{verdict}</span>'
        else:
            abstentions.append((criterion_id, judgment))
            badge = '<span class="badge abst">弃权 · insufficient_evidence</span>'
        refs_html: list[str] = []
        for ref in judgment["evidence_refs"]:
            refs_total += 1
            supports = ref["stance"] == "supports"
            stance_cls = "sup" if supports else "con"
            stance_label = "支持" if supports else "反驳"
            refs_html.append(
                "<li>"
                f'<span class="chip">{esc(ref["source_id"])}</span>'
                f'<blockquote>“{esc(ref["quote"])}”</blockquote>'
                f'<p class="claim"><span class="stance {stance_cls}">{stance_label}论点</span>'
                f'{esc(ref["claim"])} <span class="verify">（存在性已核验；语义支持未核验）</span></p>'
                "</li>"
            )
        zh_label = DIMENSION_ZH_LABELS.get(criterion_id, "")
        extras: list[str] = []
        if judgment["key_assumptions"]:
            assumptions.extend(judgment["key_assumptions"])
            extras.append(
                "<details><summary>关键假设 "
                f"({len(judgment['key_assumptions'])})</summary><ul>"
                + esc_all(judgment["key_assumptions"])
                + "</ul></details>"
            )
        if status == JUDGED_STATUS and judgment["missing_information"]:
            extras.append(
                "<details><summary>缺失信息 "
                f"({len(judgment['missing_information'])})</summary><ul>"
                + esc_all(judgment["missing_information"])
                + "</ul></details>"
            )
        abstain_missing = ""
        if status != JUDGED_STATUS and judgment["missing_information"]:
            abstain_missing = (
                '<p class="missing-inline">缺少材料：'
                + "；".join(esc(item) for item in judgment["missing_information"])
                + "</p>"
            )
        dim_sections.append(
            '<article class="dim">'
            "<h3>"
            f'<span class="zh">{esc(zh_label or criterion_id)}</span>'
            f'<span class="en">{esc(criterion_id)}</span>'
            f"{badge}"
            "</h3>"
            f'<p class="rationale">{esc(judgment["rationale"])}</p>'
            + (f'<ul class="refs">{"".join(refs_html)}</ul>' if refs_html else "")
            + abstain_missing
            + "".join(extras)
            + "</article>"
        )

    if abstentions:
        abstain_html = (
            '<ul class="digest">%s</ul>'
            % "".join(
                f"<li>{esc(DIMENSION_ZH_LABELS.get(criterion_id, criterion_id))}（{esc(criterion_id)}）"
                " — 缺少："
                + "；".join(esc(item) for item in judgment["missing_information"])
                + "</li>"
                for criterion_id, judgment in abstentions
            )
            + '<p class="digest">未决维度不构成通过或否决；其影响的后续判断必须保持未决状态。</p>'
        )
    else:
        abstain_html = '<p class="digest none">本次评审七个维度均给出建议，无弃权。</p>'

    assumptions_html = (
        f'<ul class="digest">{esc_all(assumptions)}</ul>'
        if assumptions
        else '<p class="digest">无。</p>'
    )
    citation_html = (
        f'<p class="digest">引用共 {refs_total} 条，全部通过逐字存在性核验'
        "（引用片段确实出现在对应来源原文中）；引用与论点之间的语义支持关系未由程序核验。</p>"
    )

    meta_rows = [
        ("run_id", f'<code>{esc(record["run_id"])}</code>'),
        (
            "idea_index / case_id",
            f'{esc(record["idea"]["idea_index"])} · <code>{esc(record["case_id"])}</code>',
        ),
        (
            "评审记录",
            f'<code>{esc(version_name)}</code>（schema {esc(record["schema_version"])}，'
            f'authoring contract {esc(record["authoring_contract_version"])}）',
        ),
        (
            "Prompt / 响应契约",
            f'<code>{esc(record["prompt_version"])}</code> · '
            f'<code>{esc(record["response_schema_version"])}</code>',
        ),
        (
            "评审模型（声明值）",
            f'<code>{esc(evaluator["declared_provider"])}</code> / '
            f'<code>{esc(evaluator["declared_model_id"])}</code>',
        ),
        (
            "Provenance",
            f'{esc(provenance["kind"])}（由 {esc(provenance["supplied_by"])} 提供，'
            f'导入人 {esc(evaluator["imported_by"])}；程序未亲自执行该模型调用）',
        ),
        (
            "程序验证",
            f'<code>{esc(record["audit"]["validated_by"])}</code> 于 '
            f'{esc(record["audit"]["validated_at"])}',
        ),
    ]
    meta_html = "".join(
        f"<div><dt>{esc(label)}</dt><dd>{value}</dd></div>"
        for label, value in meta_rows
    )

    document = (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>AI 评审证据卡 — idea {esc(record['idea']['idea_index'])} · "
        f"run {esc(record['run_id'][:8])}…</title>\n"
        f"<style>{_CARD_CSS}</style>\n</head>\n<body>\n<main>\n"
        '<div class="card">\n'
        '<header>\n<p class="kind">AI Review Evidence Card · 单评审建议</p>\n'
        "<h1>七维初评证据卡</h1>\n"
        f'<dl class="meta">{meta_html}</dl>\n'
        '<p class="limit"><strong>证据限度</strong>：本卡是单个 AI 评审的建议，未经领域专家校准，'
        "不构成科研质量证明、官方分数或晋升指令。引用仅经程序逐字存在性核验；"
        "引用与论点之间的语义支持关系未自动核验。弃权与未决按原样保留。</p>\n"
        "</header>\n"
        "<section>\n<h2>七维建议</h2>\n"
        '<p class="legend">颜色仅为阅读辅助（绿=支持面、黄=中间、红=触及质量底线、蓝=方向中立），'
        "判断语义以 rubric 枚举定义为准。</p>\n"
        + "".join(dim_sections)
        + "</section>\n"
        "<section>\n<h2>未决与弃权</h2>\n" + abstain_html + "</section>\n"
        "<section>\n<h2>关键假设</h2>\n" + assumptions_html + "</section>\n"
        "<section>\n<h2>引用核验</h2>\n" + citation_html + "</section>\n"
        "<footer>由 ai_scientist.ideation.ai_review 从已验证评审记录确定性渲染 · "
        f"{esc(version_name)} · 本卡不是 Robert 的判断，也不是晋升依据。</footer>\n"
        "</div>\n</main>\n</body>\n</html>\n"
    )
    return document.encode("utf-8")


def validate_ai_review(
    workspace_root: Path,
    run_id: str,
    idea_index: int,
) -> dict[str, Any]:
    """Validate the latest imported response and commit the AI review record.

    Every rule is deterministic and fail-closed: a failed response never
    becomes a record, and the raw response plus the review package stay
    untouched for audit.
    """
    idea_index = _validate_idea_index(idea_index)
    workspace, context, target, rubric = _load_context_and_comparator(
        workspace_root, run_id
    )
    _, _, _, idea_entry = _load_idea_evidence(context, run_id, idea_index)

    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    ai_path = _ai_dir(idea_dir)
    package_path = ai_path / PACKAGE_NAME
    if not package_path.is_file() or package_path.is_symlink():
        fail(
            "REVIEW_PACKAGE_NOT_FOUND",
            f"No {PACKAGE_NAME} for idea {idea_index}; run evaluation "
            "export-review-package first",
        )
    package_bytes = package_path.read_bytes()
    document, _prompt = _rederive_package(
        workspace=workspace,
        run_id=run_id,
        idea_index=idea_index,
        context=context,
        target=target,
        rubric=rubric,
        package_bytes=package_bytes,
    )
    request_path = ai_path / REQUEST_NAME
    if not request_path.is_file() or request_path.is_symlink():
        fail(
            "REVIEW_REQUEST_NOT_FOUND",
            f"No {REQUEST_NAME} for idea {idea_index}; run evaluation "
            "export-review-package first",
        )
    if request_path.read_bytes() != _render_review_request(
        _load_review_prompt(workspace).text, document["model_payload"]
    ):
        fail(
            "REVIEW_REQUEST_DRIFT",
            f"{REQUEST_NAME} on disk does not match the pinned prompt render; "
            "re-run evaluation export-review-package",
        )

    head_name, head = _load_head_response(ai_path)
    if head["review_package_sha256"] != sha256_bytes(package_bytes):
        fail(
            "REVIEW_RESPONSE_PACKAGE_MISMATCH",
            f"The head response {head_name} was imported against a different "
            "review package",
        )
    if head["prompt_version"] != document["prompt_version"]:
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            f"The head response {head_name} was imported under another prompt "
            "version",
        )
    if head["parse_status"] != "ok" or not isinstance(head["parsed_response"], dict):
        fail(
            "REVIEW_RESPONSE_INVALID_FORMAT",
            f"The head response {head_name} is not a parseable review response",
            parse_error=head["parse_error"],
        )

    parsed = closed_object(
        head["parsed_response"], label="review response", keys=RESPONSE_TOP_KEYS
    )
    if parsed["task"] != REVIEW_TASK_ID:
        fail(
            "INVALID_SCHEMA",
            f"review response task must be '{REVIEW_TASK_ID}'",
        )
    sources_by_id = {
        source["source_id"]: source
        for source in document["model_payload"]["materials"]["sources"]
    }
    checked = _check_review_judgments(parsed["dimensions"], rubric, sources_by_id)

    versions = _existing_versions(ai_path)
    expected_supersedes = versions[-1][1] if versions else None
    new_seq = (versions[-1][0] + 1) if versions else 1

    record: dict[str, Any] = {
        "schema_version": EVALUATION_AI_REVIEW_RECORD_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "record_kind": "single_ai_review",
        "run_id": run_id,
        "case_id": context.case_id,
        "seal_sha256": context.seal_sha256,
        "idea": {
            "idea_index": idea_index,
            "relative_path": idea_entry["relative_path"],
            "sha256": idea_entry["sha256"],
        },
        "target_paper": document["target_paper"],
        "rubric_version": rubric.version,
        "prompt_version": document["prompt_version"],
        "response_schema_version": document["response_schema_version"],
        "review_package_sha256": sha256_bytes(package_bytes),
        "review_request_sha256": head["review_request_sha256"],
        "evaluator": {
            "evaluator_slot": "primary",
            "author_type": "AI",
            "declared_provider": head["declared"]["provider"],
            "declared_model_id": head["declared"]["model_id"],
            "provenance": dict(head["provenance"]),
            "response_file": f"{RESPONSES_DIRNAME}/{head_name}",
            "response_sha256": head["response_sha256"],
            "responded_at": head["declared"]["responded_at"],
            "imported_at": head["imported_at"],
            "imported_by": head["imported_by"],
        },
        "judgments": checked["dimensions"],
        "citation_verification": {
            "refs_total": checked["refs_total"],
            "refs_quote_verified": checked["refs_total"],
            "semantic_support_verification": "not_performed",
        },
        "audit": {
            "imported_at": head["imported_at"],
            "imported_by": head["imported_by"],
            "validated_at": _now(),
            "validated_by": VALIDATED_BY_TOOL,
            "validation_result": "passed",
        },
        "supersedes": expected_supersedes,
    }
    _check_supersedes(
        record["supersedes"],
        expected_name=expected_supersedes,
        idea_dir=ai_path,
        run_id=run_id,
        idea_index=idea_index,
    )

    version_name = f"v{new_seq:04d}.json"
    card_bytes = _render_evidence_card(record, version_name)
    card_html_bytes = _render_evidence_card_html(record, version_name)

    record_bytes = canonical_json_bytes(record)
    _write_bytes_once(ai_path / version_name, record_bytes, label=version_name)
    _write_bytes_overwrite(ai_path / CARD_NAME, card_bytes, label=CARD_NAME)
    _write_bytes_overwrite(
        ai_path / CARD_HTML_NAME, card_html_bytes, label=CARD_HTML_NAME
    )

    return {
        "evidence_card": _ai_relpath(run_id, idea_index, CARD_NAME),
        "evidence_card_html": _ai_relpath(run_id, idea_index, CARD_HTML_NAME),
        "idea_index": idea_index,
        "record": _ai_relpath(run_id, idea_index, version_name),
        "record_sha256": sha256_bytes(record_bytes),
        "response_file": _ai_relpath(run_id, idea_index, RESPONSES_DIRNAME, head_name),
        "run_id": run_id,
        "status": "validated",
        "supersedes": expected_supersedes,
        "version": version_name,
    }
