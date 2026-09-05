"""AI-assisted single-review evaluation (authoring contract v2, tickets 01+02).

Implements the single-idea AI review mode of the evaluation authoring
contract v2 (docs/agents/ai-review-authoring-contract-v2.md) on top of the
existing post-seal evaluation machinery:

- register_review_config: write-once review execution config binding the two
  independent evaluator slots (exact model ids, distinct model families) and
  the pinned prompt versions; the second evaluator never sees the first
  one's answers (isolated contexts, per-slot storage).
- export_review_package: derives an anonymous, deterministic review package
  (Workshop text, the sealed idea fields, the complete per-paper release
  record of the sidecar-bound retrieval operations, the Target Comparator,
  and an honest audit scope statement) plus a ready-to-send review request
  rendered from the hash-pinned single-review prompt template.
- import_review_response: stores an operator-supplied model response
  write-once with explicit ``user_supplied`` provenance (the program never
  claims it executed the model call), parses the response text, and reports
  parse failures explicitly while retaining the raw response.
- validate_ai_review: fail-closed validation of the latest stored response
  for one evaluator slot — closed schema, seven dimensions with the original
  rubric verdict enums and the independent ``insufficient_evidence`` status,
  per-ref verbatim quote verification against the package sources, linear
  supersedes — then commits the immutable write-once AI review record and
  the regenerable Chinese evidence card for that slot.
- aggregate_review: merges the two slots' validated single-review records
  into a dual-review consensus record plus the consensus card. Per dimension
  only two valid judgments with the same verdict form a consensus (a shared
  negative stays negative); conflicts and abstentions stay unresolved;
  missing/invalid responses are accounted separately and can never masquerade
  as complete.

AI review files live under ``artifacts/evaluations/<run_id>/ideas/<idx>/ai/``
so the v1 human Evaluation Artifact layout, its validation, and coverage
stay byte-identical. Per-evaluator records live in ``ai/primary/`` and
``ai/second/``; the consensus record lives in ``ai/consensus/``. A consensus
record is honest advice for Robert: it carries no promotion authority and no
claim of scientific ground truth; pairwise review is delivered by
``ai_pair_review`` (ticket 02).
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
    EVALUATION_AI_REVIEW_CONSENSUS_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION,
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_PATH,
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_SHA256,
    EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION,
    EVALUATION_AI_REVIEW_RECORD_SCHEMA_VERSION,
    EVALUATION_AI_REVIEW_RESPONSE_SCHEMA_VERSION,
    EVALUATION_AUTHORING_CONTRACT_VERSION,
    EVALUATION_REVIEW_EXECUTION_CONFIG_SCHEMA_VERSION,
    EVALUATION_REVIEW_MATERIALS_SCHEMA_VERSION,
    EVALUATION_REVIEW_PACKAGE_SCHEMA_VERSION,
    EVALUATION_REVIEW_RESPONSE_IMPORT_SCHEMA_VERSION,
    EVALUATION_ROOT_RELPATH,
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

# Two independent evaluator slots. The execution config must bind them to
# two different model families; two personas of the same model are never two
# independent evaluators.
EVALUATOR_SLOTS = ("primary", "second")
CONFIG_NAME = "ai-review-config.json"
CONSENSUS_DIRNAME = "consensus"
CONSENSUS_CARD_NAME = "consensus-card.md"
CONSENSUS_CARD_HTML_NAME = "consensus-card.html"

REVIEW_TASK_ID = "single_idea_review"
JUDGED_STATUS = "judged"
INSUFFICIENT_EVIDENCE_STATUS = "insufficient_evidence"
ASSESSMENT_STATUSES = frozenset({JUDGED_STATUS, INSUFFICIENT_EVIDENCE_STATUS})
REF_STANCES = frozenset({"supports", "contradicts"})
VALIDATED_BY_TOOL = "ai_scientist.ideation.ai_review.validate_ai_review"
AGGREGATED_BY_TOOL = "ai_scientist.ideation.ai_review.aggregate_review"
# Dimensions whose judged claims are scope statements about the audit facts:
# the template requires citing the audit_statement source so the claimed
# scope is anchored to the checks the package actually carries.
AUDIT_CITED_DIMENSIONS = frozenset({"contamination_signal", "leakage_review"})
AUDIT_SOURCE_KIND = "audit_statement"

# Pre-registered rubric-floor dimensions and their problem verdicts (mirrors
# comparison.RUBRIC_FLOOR_PROBLEM_VALUES): a dual-review consensus on one of
# these is a negative quality-floor result and is preserved as such.
QUALITY_FLOOR_PROBLEM_VERDICTS = {
    "problem_space_match": "mismatched",
    "feasibility_soundness": "unsound",
    "grounding_synthesis": "name_dropped",
    "contamination_signal": "signal_found",
    "leakage_review": "leak_found",
}

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


def _ensure_ai_dirs(ai_path: Path) -> None:
    try:
        ai_path.mkdir(parents=True, exist_ok=True)
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
    _ensure_ai_dirs(ai_path)
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


def _check_evaluator_slot(slot: object) -> str:
    if slot not in EVALUATOR_SLOTS:
        fail(
            "INVALID_COORDINATE",
            f"evaluator_slot must be one of {list(EVALUATOR_SLOTS)}",
        )
    return str(slot)


def _slot_dir(ai_path: Path, slot: str) -> Path:
    slot_path = ai_path / slot
    if slot_path.is_symlink():
        fail("SYMLINK_FORBIDDEN", f"The {slot} evaluator directory is a symlink")
    return slot_path


# ==============================================================================
# Review execution config (two independent evaluators, distinct families)
# ==============================================================================

_CONFIG_EVALUATOR_KEYS = {"model_family", "model_id", "provider", "slot"}
_CONFIG_AUTHORIZATION_KEYS = {
    "approved_at",
    "approved_by",
    "cost_boundary",
    "outbound_scope",
    "token_budget",
}


def _check_review_config(
    value: object, *, at_registration: bool = False
) -> dict[str, Any]:
    """Closed validation of the review execution config document.

    Prompt-version equality with the current code constants is enforced only
    at registration. Templates are versioned so they can be revised during a
    session (the runbook's prompt-revision path); at load time version
    compatibility is enforced per artifact — every request render, response
    import, and record pins its own prompt version — so re-comparing the
    registered declaration here would retroactively brick configs across
    unrelated modes.
    """
    config = closed_object(
        value,
        label="review execution config",
        keys={
            "authoring_contract_version",
            "evaluators",
            "prompt_versions",
            "real_call_authorization",
            "schema_version",
        },
    )
    if config["schema_version"] != EVALUATION_REVIEW_EXECUTION_CONFIG_SCHEMA_VERSION:
        fail(
            "UNSUPPORTED_SCHEMA",
            "Unsupported review execution config schema_version: "
            f"{config['schema_version']}",
        )
    if config["authoring_contract_version"] != EVALUATION_AUTHORING_CONTRACT_VERSION:
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            "The review execution config binds another authoring contract version",
        )
    prompt_versions = closed_object(
        config["prompt_versions"],
        label="review execution config.prompt_versions",
        keys={"pair", "single"},
    )
    if at_registration and (
        prompt_versions["single"] != EVALUATION_AI_REVIEW_PROMPT_SINGLE_VERSION
        or prompt_versions["pair"] != EVALUATION_AI_REVIEW_PROMPT_PAIR_VERSION
    ):
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            "The review execution config pins unapproved prompt versions",
        )
    evaluators_value = config["evaluators"]
    if not isinstance(evaluators_value, list) or len(evaluators_value) != len(
        EVALUATOR_SLOTS
    ):
        fail(
            "INVALID_SCHEMA",
            "review execution config.evaluators must list exactly "
            f"{len(EVALUATOR_SLOTS)} evaluators",
        )
    evaluators: dict[str, dict[str, str]] = {}
    for index, item in enumerate(evaluators_value):
        entry = closed_object(
            item,
            label=f"review execution config.evaluators[{index}]",
            keys=_CONFIG_EVALUATOR_KEYS,
        )
        slot = _check_evaluator_slot(entry["slot"])
        if slot in evaluators:
            fail("INVALID_SCHEMA", f"Duplicate evaluator slot: {slot}")
        evaluators[slot] = {
            "model_family": nonempty_string(
                entry["model_family"], label=f"evaluators[{index}].model_family"
            ),
            "model_id": nonempty_string(
                entry["model_id"], label=f"evaluators[{index}].model_id"
            ),
            "provider": nonempty_string(
                entry["provider"], label=f"evaluators[{index}].provider"
            ),
            "slot": slot,
        }
    if set(evaluators) != set(EVALUATOR_SLOTS):
        fail(
            "INVALID_SCHEMA",
            f"review execution config must bind the slots {list(EVALUATOR_SLOTS)}",
        )
    if evaluators["primary"]["model_family"] == evaluators["second"]["model_family"]:
        fail(
            "REVIEW_CONFIG_FAMILIES_NOT_DISTINCT",
            "The two evaluator slots must come from different model families; "
            "two personas of one model are not independent evaluators",
        )
    if evaluators["primary"]["model_id"] == evaluators["second"]["model_id"]:
        fail(
            "REVIEW_CONFIG_MODELS_NOT_DISTINCT",
            "The two evaluator slots must bind different exact model ids",
        )
    authorization = config["real_call_authorization"]
    if authorization is not None:
        auth = closed_object(
            authorization,
            label="review execution config.real_call_authorization",
            keys=_CONFIG_AUTHORIZATION_KEYS,
        )
        nonempty_string(
            auth["approved_by"], label="real_call_authorization.approved_by"
        )
        timestamp(auth["approved_at"], label="real_call_authorization.approved_at")
        nonempty_string(
            auth["token_budget"], label="real_call_authorization.token_budget"
        )
        nonempty_string(
            auth["cost_boundary"], label="real_call_authorization.cost_boundary"
        )
        nonempty_string(
            auth["outbound_scope"], label="real_call_authorization.outbound_scope"
        )
    return config


def register_review_config(workspace_root: Path, config_path: Path) -> dict[str, Any]:
    """Validate and register the write-once review execution config.

    The config binds the two evaluator slots (provider, exact model id, and
    the operator-declared model family) plus the pinned prompt versions. It
    is a declared operator input: the program cannot verify the family
    classification, so it enforces only that the declared values differ and
    records them verbatim.
    """
    workspace = workspace_root.resolve(strict=True)
    if config_path.is_symlink() or not config_path.is_file():
        fail("INVALID_INPUT", f"Config file is missing: {config_path}")
    value = parse_json_bytes(config_path.read_bytes(), label="review execution config")
    checked = _check_review_config(value, at_registration=True)
    root = workspace / EVALUATION_ROOT_RELPATH
    if root.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The evaluations root is a symlink")
    try:
        root.mkdir(parents=True, exist_ok=True)
        _fsync_directory(root)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create evaluations root: {detail}")
    target = root / CONFIG_NAME
    _write_bytes_once(target, canonical_json_bytes(checked), label=CONFIG_NAME)
    return {
        "config": EVALUATION_ROOT_RELPATH.joinpath(CONFIG_NAME).as_posix(),
        "config_sha256": sha256_bytes(canonical_json_bytes(checked)),
        "evaluators": {
            entry["slot"]: {
                "model_family": entry["model_family"],
                "model_id": entry["model_id"],
                "provider": entry["provider"],
            }
            for entry in sorted(checked["evaluators"], key=lambda item: item["slot"])
        },
        "status": "registered",
    }


def _config_registered(workspace: Path) -> bool:
    path = workspace / EVALUATION_ROOT_RELPATH / CONFIG_NAME
    return path.is_file() and not path.is_symlink()


def _load_review_config(workspace: Path) -> dict[str, Any]:
    """Load and re-validate the registered config; missing file fails closed."""
    path = workspace / EVALUATION_ROOT_RELPATH / CONFIG_NAME
    if path.is_symlink() or not path.is_file():
        fail(
            "REVIEW_CONFIG_NOT_FOUND",
            "No registered review execution config; run evaluation "
            "register-review-config first",
        )
    value = parse_json_bytes(path.read_bytes(), label="review execution config")
    return _check_review_config(value)


def _config_evaluator(config: dict[str, Any], slot: str) -> dict[str, str]:
    for entry in config["evaluators"]:
        if entry["slot"] == slot:
            return entry
    fail("REVIEW_CONFIG_MISMATCH", f"The config does not bind slot {slot}")


def _check_config_binding(
    config: dict[str, Any], slot: str, declared: dict[str, Any]
) -> None:
    """A stored record may only merge into the slot the config binds it to.

    ``declared`` is either an import record's ``declared`` block or a
    validated record's ``evaluator`` block; both carry the provider and
    model id under different key names.
    """
    provider = declared.get("provider", declared.get("declared_provider"))
    model_id = declared.get("model_id", declared.get("declared_model_id"))
    binding = _config_evaluator(config, slot)
    if provider != binding["provider"] or model_id != binding["model_id"]:
        fail(
            "REVIEW_CONFIG_MISMATCH",
            f"The {slot} record declares provider/model "
            f"{provider}/{model_id} but the config "
            f"binds {binding['provider']}/{binding['model_id']}",
        )


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
    evaluator_slot: str = "primary",
) -> dict[str, Any]:
    """Store one operator-supplied model response write-once and parse it.

    Each evaluator slot stores its responses separately: the second
    evaluator's answers never flow into the first one's context or storage.
    Provenance is always ``user_supplied``: this command records who provided
    the file, never a claim that the program executed the model call. An
    unparseable response is retained on disk and reported as an explicit
    failure; it can never become a validated record.
    """
    idea_index = _validate_idea_index(idea_index)
    slot = _check_evaluator_slot(evaluator_slot)
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

    slot_path = _slot_dir(ai_path, slot)
    responses_dir = slot_path / RESPONSES_DIRNAME
    if responses_dir.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The responses directory is a symlink")
    try:
        slot_path.mkdir(parents=True, exist_ok=True)
        responses_dir.mkdir(exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail(
            "STORAGE_WRITE_FAILED", f"Cannot create {slot} response directory: {detail}"
        )
    _fsync_directory(slot_path)
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
        "evaluator_slot": slot,
        "parse_status": parse_status,
        "prompt_version": prompt.version,
        "response_file": _ai_relpath(
            run_id, idea_index, slot, RESPONSES_DIRNAME, response_name
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


def _load_head_response(slot_path: Path, slot: str) -> tuple[str, dict[str, Any]]:
    responses_dir = slot_path / RESPONSES_DIRNAME
    if not responses_dir.is_dir() or responses_dir.is_symlink():
        fail(
            "REVIEW_RESPONSE_NOT_FOUND",
            f"No imported review responses for slot {slot}; run evaluation "
            "import-review-response first",
        )
    versions = _existing_versions(
        responses_dir, pattern=RESPONSE_NAME_PATTERN, label="Review response"
    )
    if not versions:
        fail(
            "REVIEW_RESPONSE_NOT_FOUND",
            f"No imported review responses found for slot {slot}",
        )
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
    *,
    evaluator_slot: str = "primary",
) -> dict[str, Any]:
    """Validate the latest imported response of one slot and commit its record.

    Every rule is deterministic and fail-closed: a failed response never
    becomes a record, and the raw response plus the review package stay
    untouched for audit. When a review execution config is registered, the
    record's declared provider/model must match the slot's binding.
    """
    idea_index = _validate_idea_index(idea_index)
    slot = _check_evaluator_slot(evaluator_slot)
    workspace, context, target, rubric = _load_context_and_comparator(
        workspace_root, run_id
    )
    _, _, _, idea_entry = _load_idea_evidence(context, run_id, idea_index)

    idea_dir = _evaluation_idea_dir(workspace, run_id, idea_index)
    ai_path = _ai_dir(idea_dir)
    slot_path = _slot_dir(ai_path, slot)
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

    head_name, head = _load_head_response(slot_path, slot)
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
    config = _load_review_config(workspace) if _config_registered(workspace) else None
    if config is not None:
        _check_config_binding(config, slot, head["declared"])

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

    versions = _existing_versions(slot_path)
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
            "evaluator_slot": slot,
            "author_type": "AI",
            "declared_provider": head["declared"]["provider"],
            "declared_model_id": head["declared"]["model_id"],
            "provenance": dict(head["provenance"]),
            "response_file": f"{slot}/{RESPONSES_DIRNAME}/{head_name}",
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
        idea_dir=slot_path,
        run_id=run_id,
        idea_index=idea_index,
    )

    version_name = f"v{new_seq:04d}.json"
    card_bytes = _render_evidence_card(record, version_name)
    card_html_bytes = _render_evidence_card_html(record, version_name)

    record_bytes = canonical_json_bytes(record)
    _write_bytes_once(slot_path / version_name, record_bytes, label=version_name)
    _write_bytes_overwrite(slot_path / CARD_NAME, card_bytes, label=CARD_NAME)
    _write_bytes_overwrite(
        slot_path / CARD_HTML_NAME, card_html_bytes, label=CARD_HTML_NAME
    )

    return {
        "evidence_card": _ai_relpath(run_id, idea_index, slot, CARD_NAME),
        "evidence_card_html": _ai_relpath(run_id, idea_index, slot, CARD_HTML_NAME),
        "evaluator_slot": slot,
        "idea_index": idea_index,
        "record": _ai_relpath(run_id, idea_index, slot, version_name),
        "record_sha256": sha256_bytes(record_bytes),
        "response_file": _ai_relpath(
            run_id, idea_index, slot, RESPONSES_DIRNAME, head_name
        ),
        "run_id": run_id,
        "status": "validated",
        "supersedes": expected_supersedes,
        "version": version_name,
    }


# ==============================================================================
# Dual-review aggregation (ticket 02): consensus across two isolated slots
# ==============================================================================

_SINGLE_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "authoring_contract_version",
        "record_kind",
        "run_id",
        "case_id",
        "seal_sha256",
        "idea",
        "target_paper",
        "rubric_version",
        "prompt_version",
        "response_schema_version",
        "review_package_sha256",
        "review_request_sha256",
        "evaluator",
        "judgments",
        "citation_verification",
        "audit",
        "supersedes",
    }
)
_SINGLE_EVALUATOR_KEYS = frozenset(
    {
        "evaluator_slot",
        "author_type",
        "declared_provider",
        "declared_model_id",
        "provenance",
        "response_file",
        "response_sha256",
        "responded_at",
        "imported_at",
        "imported_by",
    }
)
_RESPONSE_IMPORT_KEYS = frozenset(
    {
        "schema_version",
        "authoring_contract_version",
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
        "review_package_sha256",
        "review_request_sha256",
    }
)


def _config_sha256(workspace: Path) -> str:
    path = workspace / EVALUATION_ROOT_RELPATH / CONFIG_NAME
    return sha256_bytes(path.read_bytes())


def _verify_supersedes_chain(
    records_dir: Path, *, label: str = "Review record"
) -> None:
    """Every record version must supersede exactly its predecessor."""
    versions = _existing_versions(records_dir)
    expected: str | None = None
    for _seq, name in versions:
        document = parse_json_bytes(
            (records_dir / name).read_bytes(), label=f"{label.lower()} {name}"
        )
        if not isinstance(document, dict) or document.get("supersedes") != expected:
            fail(
                "EVALUATION_SUPERSEDES_INVALID",
                f"{label} {name} breaks the linear supersedes chain",
                expected=expected,
            )
        expected = name


def _slot_record_state(
    *,
    ai_path: Path,
    slot: str,
    package_bytes: bytes,
    document: dict[str, Any],
    rubric: Any,
    run_id: str,
    idea_index: int,
    idea_entry: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    """Load one slot's head record with full integrity re-verification.

    Returns {"state", "record", "record_name", "record_sha256", "note"}.
    state: "valid" (a verified record heads the slot), "unvalidated"
    (responses exist, none validated), "invalid" (the only/unvalidated head
    response is unparseable), "missing" (no responses). A tampered record,
    response, or chain fails closed instead of returning a state.
    """
    slot_path = _slot_dir(ai_path, slot)
    record_versions = _existing_versions(slot_path)
    if record_versions:
        _verify_supersedes_chain(slot_path)
        head_seq, head_record_name = record_versions[-1]
        record = parse_json_bytes(
            (slot_path / head_record_name).read_bytes(),
            label=f"single review record {head_record_name}",
        )
        record = closed_object(
            record, label="single review record", keys=_SINGLE_RECORD_KEYS
        )
        if record["schema_version"] != EVALUATION_AI_REVIEW_RECORD_SCHEMA_VERSION:
            fail(
                "UNSUPPORTED_SCHEMA",
                f"Unsupported single review record schema_version: "
                f"{record['schema_version']}",
            )
        if record["record_kind"] != "single_ai_review":
            fail("RUN_CORRUPT", f"Review record {head_record_name} has the wrong kind")
        if (
            record["run_id"] != run_id
            or record["case_id"] != context.case_id
            or record["seal_sha256"] != context.seal_sha256
        ):
            fail(
                "IDENTITY_MISMATCH",
                f"Review record {head_record_name} belongs to another run or seal",
            )
        idea_link = closed_object(
            record["idea"],
            label="record.idea",
            keys={"idea_index", "relative_path", "sha256"},
        )
        if (
            idea_link["idea_index"] != idea_index
            or idea_link["relative_path"] != idea_entry["relative_path"]
            or idea_link["sha256"] != idea_entry["sha256"]
        ):
            fail(
                "HASH_MISMATCH",
                f"Review record {head_record_name} binds another idea payload",
            )
        if record["review_package_sha256"] != sha256_bytes(package_bytes):
            fail(
                "REVIEW_RESPONSE_PACKAGE_MISMATCH",
                f"Review record {head_record_name} binds another review package",
            )
        if record["prompt_version"] != document["prompt_version"]:
            fail(
                "REVIEW_CONTRACT_MISMATCH",
                f"Review record {head_record_name} was produced under another "
                "prompt version",
            )
        if record["rubric_version"] != rubric.version:
            fail(
                "RUBRIC_VERSION_NOT_APPROVED",
                f"Review record {head_record_name} pins an unapproved rubric",
            )
        evaluator = closed_object(
            record["evaluator"],
            label="record.evaluator",
            keys=_SINGLE_EVALUATOR_KEYS,
        )
        if evaluator["evaluator_slot"] != slot or evaluator["author_type"] != "AI":
            fail(
                "IDENTITY_MISMATCH",
                f"Review record {head_record_name} does not belong to slot {slot}",
            )
        provenance = closed_object(
            evaluator["provenance"],
            label="record.evaluator.provenance",
            keys={"kind", "supplied_by"},
        )
        if provenance["kind"] != "user_supplied":
            fail(
                "IDENTITY_MISMATCH",
                f"Review record {head_record_name} does not carry user_supplied "
                "provenance",
            )
        response_path = ai_path / evaluator["response_file"]
        if response_path.is_symlink() or not response_path.is_file():
            fail(
                "REVIEW_RESPONSE_NOT_FOUND",
                f"Review record {head_record_name} binds a missing response file",
            )
        # The bound file is the stored import record; its integrity anchor is
        # the hash of the embedded raw response text.
        stored = parse_json_bytes(
            response_path.read_bytes(), label="stored review response import record"
        )
        stored = closed_object(
            stored, label="stored review response", keys=_RESPONSE_IMPORT_KEYS
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
        sources_by_id = {
            source["source_id"]: source
            for source in document["model_payload"]["materials"]["sources"]
        }
        # Re-validate the authentic response and prove the committed record
        # is exactly what it yields — any tamper on either side fails closed.
        parsed = closed_object(
            reparsed, label="review response", keys=RESPONSE_TOP_KEYS
        )
        if parsed["task"] != REVIEW_TASK_ID:
            fail(
                "RUN_CORRUPT",
                f"Review record {head_record_name} binds a response with the "
                "wrong task",
            )
        checked = _check_review_judgments(parsed["dimensions"], rubric, sources_by_id)
        if canonical_json_bytes(checked["dimensions"]) != canonical_json_bytes(
            record["judgments"]
        ):
            fail(
                "RUN_CORRUPT",
                f"Review record {head_record_name} does not match its bound "
                "response",
            )
        return {
            "state": "valid",
            "record": record,
            "record_name": head_record_name,
            "record_sha256": sha256_bytes((slot_path / head_record_name).read_bytes()),
            "note": None,
        }
    responses_dir = slot_path / RESPONSES_DIRNAME
    if not responses_dir.is_dir() or responses_dir.is_symlink():
        return {
            "state": "missing",
            "record": None,
            "record_name": None,
            "record_sha256": None,
            "note": None,
        }
    response_versions = _existing_versions(
        responses_dir, pattern=RESPONSE_NAME_PATTERN, label="Review response"
    )
    if not response_versions:
        return {
            "state": "missing",
            "record": None,
            "record_name": None,
            "record_sha256": None,
            "note": None,
        }
    head_name, head = _load_head_response(slot_path, slot)
    if head["parse_status"] != "ok" or not isinstance(head["parsed_response"], dict):
        return {
            "state": "invalid",
            "record": None,
            "record_name": None,
            "record_sha256": None,
            "note": f"the latest imported response {head_name} is not parseable",
        }
    return {
        "state": "unvalidated",
        "record": None,
        "record_name": None,
        "record_sha256": None,
        "note": f"the latest imported response {head_name} has not been validated",
    }


def aggregate_review(
    workspace_root: Path,
    run_id: str,
    idea_index: int,
) -> dict[str, Any]:
    """Merge the two slots' validated single-review records into a consensus.

    Per dimension only two valid, same-verdict judgments form a consensus; a
    shared negative stays negative, conflicts and abstentions stay
    unresolved, and a missing or invalid slot is accounted separately — it
    can never masquerade as complete_unresolved. Both original rationales are
    preserved even under agreement so common errors remain checkable.
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
    config = _load_review_config(workspace)

    package_sha = sha256_bytes(package_bytes)
    slot_results: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, Any] | None] = {}
    for slot in EVALUATOR_SLOTS:
        result = _slot_record_state(
            ai_path=ai_path,
            slot=slot,
            package_bytes=package_bytes,
            document=document,
            rubric=rubric,
            run_id=run_id,
            idea_index=idea_index,
            idea_entry=idea_entry,
            context=context,
        )
        slot_results[slot] = result
        records[slot] = result["record"]
        if result["record"] is not None:
            _check_config_binding(config, slot, result["record"]["evaluator"])
    if all(result["record"] is None for result in slot_results.values()):
        fail(
            "REVIEW_RESPONSE_NOT_FOUND",
            "No validated single-review record in either evaluator slot",
        )

    judgments: dict[str, Any] = {}
    refs_total = 0
    for criterion_id, _verdicts in rubric.criteria:
        sides: dict[str, Any] = {}
        for slot in EVALUATOR_SLOTS:
            record = records[slot]
            sides[slot] = None if record is None else record["judgments"][criterion_id]
        first, second = sides["primary"], sides["second"]
        consensus_verdict = None
        if first is None or second is None:
            state = "incomplete_evaluator"
        elif (
            first["assessment_status"] == JUDGED_STATUS
            and second["assessment_status"] == JUDGED_STATUS
        ):
            if first["proposed_verdict"] == second["proposed_verdict"]:
                state = "consensus"
                consensus_verdict = first["proposed_verdict"]
            else:
                state = "conflict"
        else:
            state = "abstained"
        judgments[criterion_id] = {
            "state": state,
            "consensus_verdict": consensus_verdict,
            "sides": sides,
        }
        refs_total += sum(
            len(side["evidence_refs"]) for side in (first, second) if side is not None
        )

    if any(slot_results[slot]["state"] == "invalid" for slot in EVALUATOR_SLOTS):
        coverage = "invalid"
    elif any(slot_results[slot]["state"] != "valid" for slot in EVALUATOR_SLOTS):
        coverage = "missing"
    elif all(item["state"] == "consensus" for item in judgments.values()):
        coverage = "complete_resolved"
    else:
        coverage = "complete_unresolved"

    floor_dimensions = {
        dimension: (
            judgments[dimension]["consensus_verdict"]
            if judgments[dimension]["state"] == "consensus"
            else None
        )
        for dimension in QUALITY_FLOOR_PROBLEM_VERDICTS
    }
    if any(
        verdict == QUALITY_FLOOR_PROBLEM_VERDICTS[dimension]
        for dimension, verdict in floor_dimensions.items()
        if verdict is not None
    ):
        floor_state = "violated"
    elif all(verdict is not None for verdict in floor_dimensions.values()):
        floor_state = "clean"
    else:
        floor_state = "unresolved"

    evaluators: dict[str, Any] = {}
    for slot in EVALUATOR_SLOTS:
        binding = _config_evaluator(config, slot)
        result = slot_results[slot]
        record = result["record"]
        if record is None:
            evaluators[slot] = {
                "declared_provider": None,
                "declared_model_id": None,
                "model_family": binding["model_family"],
                "record_file": None,
                "record_sha256": None,
                "state": result["state"],
                "note": result["note"],
            }
        else:
            evaluators[slot] = {
                "declared_provider": record["evaluator"]["declared_provider"],
                "declared_model_id": record["evaluator"]["declared_model_id"],
                "model_family": binding["model_family"],
                "record_file": f"{slot}/{result['record_name']}",
                "record_sha256": result["record_sha256"],
                "state": "valid",
                "note": None,
            }

    consensus_dir = ai_path / CONSENSUS_DIRNAME
    if consensus_dir.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The consensus directory is a symlink")
    try:
        consensus_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create consensus directory: {detail}")
    _fsync_directory(consensus_dir)
    versions = _existing_versions(consensus_dir)
    expected_supersedes = versions[-1][1] if versions else None
    new_seq = (versions[-1][0] + 1) if versions else 1

    record_document: dict[str, Any] = {
        "schema_version": EVALUATION_AI_REVIEW_CONSENSUS_RECORD_SCHEMA_VERSION,
        "authoring_contract_version": EVALUATION_AUTHORING_CONTRACT_VERSION,
        "record_kind": "dual_ai_review_consensus",
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
        "review_package_sha256": package_sha,
        "review_config_sha256": _config_sha256(workspace),
        "coverage": coverage,
        "evaluators": evaluators,
        "judgments": judgments,
        "citation_verification": {
            "refs_total": refs_total,
            "semantic_support_verification": "not_performed",
        },
        "quality_floor": {
            "dimensions": floor_dimensions,
            "state": floor_state,
        },
        "audit": {
            "aggregated_at": _now(),
            "aggregated_by": AGGREGATED_BY_TOOL,
            "validation_result": "passed",
        },
        "supersedes": expected_supersedes,
    }
    _check_supersedes(
        record_document["supersedes"],
        expected_name=expected_supersedes,
        idea_dir=consensus_dir,
        run_id=run_id,
        idea_index=idea_index,
    )

    version_name = f"v{new_seq:04d}.json"
    card_bytes = _render_consensus_card(record_document, version_name)
    card_html_bytes = _render_consensus_card_html(record_document, version_name)
    record_bytes = canonical_json_bytes(record_document)
    _write_bytes_once(consensus_dir / version_name, record_bytes, label=version_name)
    _write_bytes_overwrite(
        consensus_dir / CONSENSUS_CARD_NAME, card_bytes, label=CONSENSUS_CARD_NAME
    )
    _write_bytes_overwrite(
        consensus_dir / CONSENSUS_CARD_HTML_NAME,
        card_html_bytes,
        label=CONSENSUS_CARD_HTML_NAME,
    )

    return {
        "consensus_card": _ai_relpath(
            run_id, idea_index, CONSENSUS_DIRNAME, CONSENSUS_CARD_NAME
        ),
        "consensus_card_html": _ai_relpath(
            run_id, idea_index, CONSENSUS_DIRNAME, CONSENSUS_CARD_HTML_NAME
        ),
        "coverage": coverage,
        "idea_index": idea_index,
        "quality_floor_state": floor_state,
        "record": _ai_relpath(run_id, idea_index, CONSENSUS_DIRNAME, version_name),
        "record_sha256": sha256_bytes(record_bytes),
        "run_id": run_id,
        "status": "aggregated",
        "supersedes": expected_supersedes,
        "version": version_name,
    }


_COVERAGE_ZH = {
    "complete_resolved": "complete_resolved（两位评审完成，七维全部形成共识）",
    "complete_unresolved": "complete_unresolved（两位评审完成，但存在弃权或分歧）",
    "invalid": "invalid（存在无效响应，不能视为完成）",
    "missing": "missing（至少一位评审缺少已验证记录）",
}
_FLOOR_STATE_ZH = {
    "violated": "violated（共识触及质量底线，负面结论按原样保留）",
    "clean": "clean（五个底线维度全部形成共识且无问题判定）",
    "unresolved": "unresolved（底线维度未全部形成共识；未决不等于通过）",
}
_DIMENSION_STATE_ZH = {
    "consensus": "共识",
    "conflict": "冲突（unresolved）",
    "abstained": "弃权（unresolved）",
    "incomplete_evaluator": "评审不完整（unresolved）",
}


def _slot_display_name(slot: str) -> str:
    return "评审一（primary）" if slot == "primary" else "评审二（second）"


def _render_side_lines(side: dict[str, Any] | None, indent: str = "- ") -> list[str]:
    if side is None:
        return [f"{indent}该侧缺少已验证评审记录"]
    lines = []
    status = side["assessment_status"]
    if status == JUDGED_STATUS:
        lines.append(f"{indent}建议 `{side['proposed_verdict']}`：{side['rationale']}")
    else:
        lines.append(
            f"{indent}弃权（{INSUFFICIENT_EVIDENCE_STATUS}）：{side['rationale']}"
        )
    for ref in side["evidence_refs"]:
        stance = "支持" if ref["stance"] == "supports" else "反驳"
        lines.append(
            f"{indent}  - 引用 [`{ref['source_id']}`] “{ref['quote']}” — {stance}论点："
            f"{ref['claim']}（存在性已核验；语义支持未核验）"
        )
    if side["missing_information"]:
        lines.append(f"{indent}  - 缺失信息：" + "；".join(side["missing_information"]))
    return lines


def _render_consensus_card(record: dict[str, Any], version_name: str) -> bytes:
    lines: list[str] = []
    lines.append("# AI 评审共识卡（双评审汇总）")
    lines.append("")
    lines.append(
        f"绑定：run_id `{record['run_id']}` · idea_index "
        f"{record['idea']['idea_index']} · case_id `{record['case_id']}`"
    )
    lines.append(
        f"共识记录：`{version_name}`（schema `{record['schema_version']}`，"
        f"authoring contract `{record['authoring_contract_version']}`）"
    )
    lines.append(f"Prompt 版本：`{record['prompt_version']}`")
    lines.append(f"覆盖状态：{_COVERAGE_ZH[record['coverage']]}")
    lines.append(f"质量底线：{_FLOOR_STATE_ZH[record['quality_floor']['state']]}")
    lines.append("")
    for slot in EVALUATOR_SLOTS:
        evaluator = record["evaluators"][slot]
        if evaluator["state"] == "valid":
            lines.append(
                f"- {_slot_display_name(slot)}：`{evaluator['declared_provider']}` / "
                f"`{evaluator['declared_model_id']}`（model family "
                f"`{evaluator['model_family']}`，声明值，程序未认证）"
            )
        else:
            note = f"：{evaluator['note']}" if evaluator["note"] else ""
            lines.append(
                f"- {_slot_display_name(slot)}：无已验证记录（{evaluator['state']}"
                f"{note}）"
            )
    lines.append("")
    lines.append(
        "> **证据限度**：本卡是两位来自不同 model family 的 AI 评审的共识汇总。"
        "双评审与换位检查降低但不能消除共同错误、语义支持错判与材料范围外的污染；"
        "一致负面保留为负面，弃权与分歧按原样保留为未决。本卡不构成科研质量证明、"
        "官方分数或晋升指令。"
    )
    lines.append("")
    lines.append("## 七维共识")
    for criterion_id in _card_dimension_order(
        {dim: item for dim, item in record["judgments"].items()}
    ):
        item = record["judgments"][criterion_id]
        lines.append("")
        if item["state"] == "consensus":
            lines.append(f"### {criterion_id} — 共识 `{item['consensus_verdict']}`")
        else:
            lines.append(f"### {criterion_id} — {_DIMENSION_STATE_ZH[item['state']]}")
        lines.append("")
        for slot in EVALUATOR_SLOTS:
            lines.append(f"- {_slot_display_name(slot)}：")
            lines.extend(
                "  " + line for line in _render_side_lines(item["sides"][slot])
            )
    lines.append("")
    lines.append("## 质量底线（pre-registered）")
    for dimension, verdict in record["quality_floor"]["dimensions"].items():
        shown = f"共识 `{verdict}`" if verdict is not None else "未决"
        lines.append(f"- {dimension}：{shown}")
    lines.append("")
    lines.append(
        "未决维度不构成通过或否决；其影响的后续判断必须保持未决状态，"
        "整体偏好不能覆盖质量底线。"
    )
    lines.append("")
    lines.append("## 引用核验")
    lines.append(
        f"- 两侧引用共 {record['citation_verification']['refs_total']} 条，均通过逐字"
        "存在性核验；引用与论点之间的语义支持关系未由程序核验。"
    )
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _render_consensus_card_html(record: dict[str, Any], version_name: str) -> bytes:
    """Render the light-theme consensus card (self-contained, no scripts)."""

    def esc(value: Any) -> str:
        return _html_escape_module.escape(str(value), quote=True)

    def refs_html(side: dict[str, Any] | None) -> str:
        if side is None:
            return ""
        items = []
        for ref in side["evidence_refs"]:
            stance_cls = "sup" if ref["stance"] == "supports" else "con"
            stance_label = "支持" if ref["stance"] == "supports" else "反驳"
            items.append(
                "<li>"
                f'<span class="chip">{esc(ref["source_id"])}</span>'
                f'<blockquote>“{esc(ref["quote"])}”</blockquote>'
                f'<p class="claim"><span class="stance {stance_cls}">{stance_label}论点</span>'
                f'{esc(ref["claim"])} <span class="verify">（存在性已核验；语义支持未核验）</span></p>'
                "</li>"
            )
        return f'<ul class="refs">{"".join(items)}</ul>' if items else ""

    dim_sections: list[str] = []
    for criterion_id in _card_dimension_order(
        {dim: item for dim, item in record["judgments"].items()}
    ):
        item = record["judgments"][criterion_id]
        state = item["state"]
        if state == "consensus":
            verdict = item["consensus_verdict"]
            tone = VERDICT_TONE.get(verdict, "neu")
            badge = f'<span class="badge {tone}">{esc(verdict)}</span>'
            heading = "共识"
        else:
            badge = '<span class="badge abst">unresolved</span>'
            heading = _DIMENSION_STATE_ZH[state]
        side_blocks: list[str] = []
        for slot in EVALUATOR_SLOTS:
            side = item["sides"][slot]
            if side is None:
                side_blocks.append(
                    f'<div class="side"><p class="side-name">{esc(_slot_display_name(slot))}</p>'
                    '<p class="digest">该侧缺少已验证评审记录</p></div>'
                )
                continue
            if side["assessment_status"] == JUDGED_STATUS:
                side_verdict = (
                    f'<span class="badge {VERDICT_TONE.get(side["proposed_verdict"], "neu")}">'
                    f'{esc(side["proposed_verdict"])}</span>'
                )
                side_rationale = esc(side["rationale"])
            else:
                side_verdict = '<span class="badge abst">弃权</span>'
                side_rationale = esc(side["rationale"])
            missing = ""
            if side["missing_information"]:
                missing = (
                    '<p class="missing-inline">缺少材料：'
                    + "；".join(esc(item_) for item_ in side["missing_information"])
                    + "</p>"
                )
            side_blocks.append(
                f'<div class="side"><p class="side-name">{esc(_slot_display_name(slot))} {side_verdict}</p>'
                f'<p class="rationale">{side_rationale}</p>'
                + refs_html(side)
                + missing
                + "</div>"
            )
        dim_sections.append(
            '<article class="dim">'
            "<h3>"
            f'<span class="zh">{esc(DIMENSION_ZH_LABELS.get(criterion_id, criterion_id))}</span>'
            f'<span class="en">{esc(criterion_id)}</span>'
            f"{badge}"
            f'<span class="state-label">{esc(heading)}</span>'
            "</h3>" + "".join(side_blocks) + "</article>"
        )

    floor_items = "".join(
        f"<li>{esc(dimension)}："
        + (f"共识 <code>{esc(verdict)}</code>" if verdict is not None else "未决")
        + "</li>"
        for dimension, verdict in record["quality_floor"]["dimensions"].items()
    )
    evaluator_rows = []
    for slot in EVALUATOR_SLOTS:
        evaluator = record["evaluators"][slot]
        if evaluator["state"] == "valid":
            evaluator_rows.append(
                (
                    _slot_display_name(slot),
                    f"<code>{esc(evaluator['declared_provider'])}</code> / "
                    f"<code>{esc(evaluator['declared_model_id'])}</code> · family "
                    f"<code>{esc(evaluator['model_family'])}</code>（声明值，程序未认证）",
                )
            )
        else:
            note = f"：{esc(evaluator['note'])}" if evaluator["note"] else ""
            evaluator_rows.append(
                (
                    _slot_display_name(slot),
                    f"无已验证记录（{esc(evaluator['state'])}{note}）",
                )
            )
    meta_rows = [
        ("run_id", f'<code>{esc(record["run_id"])}</code>'),
        (
            "idea_index / case_id",
            f'{esc(record["idea"]["idea_index"])} · <code>{esc(record["case_id"])}</code>',
        ),
        (
            "共识记录",
            f'<code>{esc(version_name)}</code>（schema {esc(record["schema_version"])}，'
            f'authoring contract {esc(record["authoring_contract_version"])}）',
        ),
        ("Prompt 版本", f'<code>{esc(record["prompt_version"])}</code>'),
        ("覆盖状态", esc(_COVERAGE_ZH[record["coverage"]])),
        ("质量底线", esc(_FLOOR_STATE_ZH[record["quality_floor"]["state"]])),
        *evaluator_rows,
        (
            "程序汇总",
            f'<code>{esc(record["audit"]["aggregated_by"])}</code> 于 '
            f'{esc(record["audit"]["aggregated_at"])}',
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
        f"<title>AI 评审共识卡 — idea {esc(record['idea']['idea_index'])} · "
        f"run {esc(record['run_id'][:8])}…</title>\n"
        f"<style>{_CARD_CSS}</style>\n"
        "<style>.side{border-top:1px dashed var(--line);padding-top:10px;margin-top:10px}"
        ".side-name{margin:0 0 4px;font-weight:700;font-size:13.5px}"
        ".state-label{font-size:12px;color:var(--muted);font-weight:600}</style>\n"
        "</head>\n<body>\n<main>\n"
        '<div class="card">\n'
        '<header>\n<p class="kind">AI Review Consensus Card · 双评审汇总</p>\n'
        "<h1>双评审七维共识卡</h1>\n"
        f'<dl class="meta">{meta_html}</dl>\n'
        '<p class="limit"><strong>证据限度</strong>：本卡是两位不同 model family 的 '
        "AI 评审的共识汇总。双评审与换位检查降低但不能消除共同错误、语义支持错判与"
        "材料范围外的污染；一致负面保留为负面，弃权与分歧按原样保留为未决。"
        "本卡不构成科研质量证明、官方分数或晋升指令。</p>\n"
        "</header>\n"
        "<section>\n<h2>七维共识</h2>\n"
        '<p class="legend">颜色仅为阅读辅助（绿=支持面、黄=中间、红=触及质量底线、蓝=方向中立），'
        "判断语义以 rubric 枚举定义为准；unresolved 徽标表示该维度无共识。</p>\n"
        + "".join(dim_sections)
        + "</section>\n"
        "<section>\n<h2>质量底线（pre-registered）</h2>\n"
        f'<ul class="digest">{floor_items}</ul>'
        '<p class="digest">未决维度不构成通过或否决；整体偏好不能覆盖质量底线。</p>'
        "</section>\n"
        "<section>\n<h2>引用核验</h2>\n"
        f'<p class="digest">两侧引用共 {record["citation_verification"]["refs_total"]} 条，'
        "均通过逐字存在性核验；引用与论点之间的语义支持关系未由程序核验。</p>\n"
        "</section>\n"
        "<footer>由 ai_scientist.ideation.ai_review.aggregate_review 从已验证记录"
        f"确定性渲染 · {esc(version_name)} · 本卡不是 Robert 的判断，也不是晋升依据。</footer>\n"
        "</div>\n</main>\n</body>\n</html>\n"
    )
    return document.encode("utf-8")
