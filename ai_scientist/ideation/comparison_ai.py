"""Comparison consumption of AI review evidence (ticket 03).

The deterministic, fail-closed bridge between the AI evaluation side
(authoring contract v2 records under ``artifacts/evaluations/``) and the
governed comparison boundary in ``comparison``:

- ``consume_pair_reduction``: locate the pair reduction record that binds a
  comparison pair (by its two sealed arms), re-derive the pair package from
  the sealed chains, re-verify all four slot-direction records and the head
  reduction record (the same integrity re-verification ``reduce_pair_review``
  applies), and derive the comparison-facing verdict document. Only a
  ``complete`` reduction with a stable overall preference yields an ingested
  verdict; every other outcome is recorded and blocks the pair's promotion
  judgment instead of being smoothed into a winner.

The verdict is written into the comparison vault's ``ai-verdicts/`` area,
separate from Robert's blinded human verdicts (``verdicts/``): the two
sources stay separated by authorship, and the reducer consumes exactly the
channel the registered evaluation protocol authorizes. The bridge never
reads credentials, never issues requests, and never rewrites AI records.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai_pair_review import (
    PAIR_ID_PATTERN,
    REDUCTION_DIRNAME,
    _pair_dir,
    _rederive_pair,
)
from .ai_review import (
    AI_REVIEW_COVERAGE_STATES,
    _config_sha256,
    _existing_versions,
    _load_review_config,
)
from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import (
    EVALUATION_AI_PAIR_REDUCTION_SCHEMA_VERSION,
    EVALUATION_ROOT_RELPATH,
)
from .errors import fail
from .evaluation_protocol import load_evaluation_protocol
from .schema import closed_object

AI_VERDICT_SCHEMA_VERSION = "comparison-ai-verdict-v1.0.0"
AI_VERDICTS_DIRNAME = "ai-verdicts"

# Per-arm quality floor states that block the pair's promotion judgment
# regardless of the stable preference (the shared negative stays negative).
QUALITY_FLOOR_BLOCKING_STATES = frozenset({"violated"})

_PAIR_REDUCTION_KEYS = frozenset(
    {
        "schema_version",
        "authoring_contract_version",
        "record_kind",
        "pair_id",
        "case_id",
        "arms",
        "prompt_version",
        "pair_package_sha256",
        "review_config_sha256",
        "coverage",
        "evaluators",
        "direction_results",
        "reduction",
        "quality_floor",
        "citation_verification",
        "audit",
        "supersedes",
    }
)


def _pair_reduction_path(pair_path: Path) -> Path | None:
    """The head write-once reduction record for one pair, if any."""
    reduction_dir = pair_path / REDUCTION_DIRNAME
    if reduction_dir.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The pair reduction directory is a symlink")
    if not reduction_dir.is_dir():
        return None
    versions = []
    for path in reduction_dir.iterdir():
        if path.is_symlink():
            fail("SYMLINK_FORBIDDEN", "A pair reduction version is a symlink")
        if not path.is_file():
            continue
        if path.name.startswith("v") and path.name.endswith(".json"):
            versions.append(path.name)
    if not versions:
        return None
    return reduction_dir / sorted(versions)[-1]


def list_pair_reductions(workspace_root: Path) -> list[dict[str, Any]]:
    """Enumerate head pair-reduction records under the private pairs root."""
    workspace = workspace_root.resolve(strict=True)
    pairs_root = workspace / EVALUATION_ROOT_RELPATH / "pairs"
    if pairs_root.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The pairs root is a symlink")
    documents: list[dict[str, Any]] = []
    if not pairs_root.is_dir():
        return documents
    for child in sorted(pairs_root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        head = _pair_reduction_path(child)
        if head is None:
            continue
        document = parse_json_bytes(
            head.read_bytes(), label=f"pair reduction {head.name}"
        )
        if not isinstance(document, dict):
            fail("RUN_CORRUPT", f"Pair reduction {head.name} is not a JSON object")
        if (
            document.get("schema_version")
            != EVALUATION_AI_PAIR_REDUCTION_SCHEMA_VERSION
        ):
            fail(
                "UNSUPPORTED_SCHEMA",
                f"Unsupported pair reduction schema_version: "
                f"{document.get('schema_version')}",
            )
        documents.append({"pair_id": child.name, "path": head})
    return documents


def consume_pair_reduction(
    workspace_root: Path,
    *,
    case_id: str,
    baseline_run_id: str,
    baseline_idea_index: int,
    challenger_run_id: str,
    challenger_idea_index: int,
    review_config_sha256: str,
) -> dict[str, Any]:
    """Derive the comparison-facing AI verdict facts for one matrix pair.

    Locates the head pair reduction record whose two arms are exactly the
    matrix pair's (baseline, challenger) sealed ideas, re-derives the pair
    package from the sealed evidence, re-verifies the record against it, and
    checks the protocol binding (config hash + protocol manifest). Returns
    the verdict document bytes' inputs and the per-arm quality floor; raises
    a canonical error for every not-ingestable state.
    """
    workspace = workspace_root.resolve(strict=True)
    protocol = load_evaluation_protocol(workspace)
    config = _load_review_config(workspace)
    config_sha = _config_sha256(workspace)
    if review_config_sha256 != config_sha:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The comparison package's pinned evaluation protocol binds "
            "another review execution config",
            expected=review_config_sha256,
            actual=config_sha,
        )
    expected_arms = {
        (baseline_run_id, baseline_idea_index),
        (challenger_run_id, challenger_idea_index),
    }
    matches: list[Path] = []
    for entry in list_pair_reductions(workspace):
        head_path = entry["path"]
        document = parse_json_bytes(head_path.read_bytes(), label="pair reduction")
        document = closed_object(
            document, label="pair reduction", keys=_PAIR_REDUCTION_KEYS
        )
        if document["case_id"] != case_id:
            continue
        arms = _check_arms(document["arms"])
        observed = {
            (arms["content_1"]["run_id"], arms["content_1"]["idea_index"]),
            (arms["content_2"]["run_id"], arms["content_2"]["idea_index"]),
        }
        if observed == expected_arms:
            matches.append(head_path)
    if not matches:
        fail(
            "AI_PAIR_REDUCTION_NOT_FOUND",
            "No pair reduction record binds this matrix pair's two arms; run "
            "the dual review and evaluation reduce-pair-review first",
            case_id=case_id,
        )
    if len(matches) > 1:
        fail(
            "AI_PAIR_REDUCTION_AMBIGUOUS",
            "More than one pair reduction record binds the same two arms; "
            "the matrix pair cannot consume a duplicated identity",
            case_id=case_id,
        )
    head_path = matches[0]
    document, pair_document, _pair_path = _load_and_verify_reduction(
        workspace, head_path, config_sha
    )
    if document["case_id"] != case_id:
        fail(
            "IDENTITY_MISMATCH",
            "The pair reduction record belongs to another case",
        )
    _check_protocol_binding(document, protocol, config_sha)
    if document["coverage"] != "complete":
        fail(
            "AI_PAIR_NOT_COMPLETE",
            "The pair reduction is not complete (missing or unvalidated "
            "direction records); an incomplete pair cannot be ingested",
            case_id=case_id,
            coverage=document["coverage"],
        )
    preference = document["reduction"]["overall_preference"]
    if preference["outcome"] != "stable":
        fail(
            "AI_PAIR_NOT_STABLE",
            "The pair reduction is incomparable; the matrix pair stays "
            "un-ingestable until a genuinely converged result exists (never "
            "by rerunning to taste)",
            case_id=case_id,
            reasons=preference.get("reasons", []),
        )
    content_value = preference["content_value"]
    if content_value not in ("content_1", "content_2", "tie"):
        fail(
            "INVALID_SCHEMA",
            f"The stable preference carries an unknown content value: {content_value}",
        )
    arms = document["arms"]
    verdict_run_id = None if content_value == "tie" else arms[content_value]["run_id"]
    verdict_idea_index = (
        None if content_value == "tie" else arms[content_value]["idea_index"]
    )
    return {
        "arms": document["arms"],
        "case_id": case_id,
        "pair_id": document["pair_id"],
        "pair_package_sha256": document["pair_package_sha256"],
        "quality_floor": document["quality_floor"],
        "record": head_path.name,
        "reduction": document["reduction"],
        "review_config_sha256": config_sha,
        "verdict_idea_index": verdict_idea_index,
        "verdict_run_id": verdict_run_id,
    }


def _check_protocol_binding(
    document: dict[str, Any], protocol: dict[str, Any], config_sha: str
) -> None:
    """The record's config hash must equal both the workspace config and the
    comparison package's pinned protocol binding; the manifest itself was
    already re-verified by ``load_evaluation_protocol``."""
    if protocol["protocol_id"] is None:  # pragma: no cover - defensive shape
        fail("EVALUATION_PROTOCOL_MISMATCH", "The protocol manifest lacks an id")
    if document["review_config_sha256"] != config_sha:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The AI pair reduction was produced under another review "
            "execution config than the one the protocol manifest binds",
            record_config=document["review_config_sha256"],
            protocol_config=config_sha,
        )


def _check_arms(arms: object) -> dict[str, dict[str, Any]]:
    if not isinstance(arms, dict) or set(arms) != {"content_1", "content_2"}:
        fail("RUN_CORRUPT", "Pair reduction arms binding is malformed")
    checked: dict[str, dict[str, Any]] = {}
    for content in ("content_1", "content_2"):
        arm = closed_object(
            arms[content],
            label=f"pair reduction arm {content}",
            keys={
                "idea_index",
                "idea_relative_path",
                "idea_sha256",
                "review_package_sha256",
                "run_id",
            },
        )
        checked[content] = arm
    return checked


def _load_and_verify_reduction(
    workspace: Path, head_path: Path, config_sha: str
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Load the head reduction record and re-verify it against a fresh
    ``_rederive_pair`` of its pair.

    This bridge re-verifies every load-bearing binding directly: schema/kind,
    package bytes, prompt version, config hash, and the four direction
    records' file hashes and states as recorded in the reduction.
    """
    workspace_resolved = workspace.resolve(strict=True)
    pair_document, _prompt, pair_path = _rederive_pair(
        workspace_resolved, head_path.parent.parent.name
    )
    document = parse_json_bytes(head_path.read_bytes(), label="pair reduction head")
    document = closed_object(
        document, label="pair reduction", keys=_PAIR_REDUCTION_KEYS
    )
    if document["record_kind"] != "pair_ai_reduction":
        fail("RUN_CORRUPT", "The head reduction record has the wrong record kind")
    if document["pair_id"] != pair_document["pair_id"]:
        fail("IDENTITY_MISMATCH", "The reduction record binds another pair_id")
    if document["case_id"] != pair_document["case_id"]:
        fail("IDENTITY_MISMATCH", "The reduction record belongs to another case")
    if document["arms"] != pair_document["arms"]:
        fail(
            "IDENTITY_MISMATCH",
            "The reduction record's arm bindings drifted from the re-derived "
            "pair package",
        )
    if document["pair_package_sha256"] != sha256_bytes(
        canonical_json_bytes(pair_document)
    ):
        fail(
            "REVIEW_RESPONSE_PACKAGE_MISMATCH",
            "The reduction record binds another pair package than a "
            "re-derivation from the sealed runs",
        )
    if document["prompt_version"] != pair_document["prompt_version"]:
        fail(
            "REVIEW_CONTRACT_MISMATCH",
            "The reduction record was produced under another prompt version",
        )
    config = _load_review_config(workspace_resolved)
    if document["review_config_sha256"] != _config_sha256(workspace_resolved):
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "The reduction record binds another review execution config",
        )
    direction_states = {}
    for slot, directions in document["direction_results"].items():
        for direction, result in directions.items():
            result = closed_object(
                result,
                label=f"direction result {slot}/{direction}",
                keys={"effective", "record_file", "record_sha256", "state"},
            )
            direction_states[(slot, direction)] = result
            record_file = result["record_file"]
            if result["state"] == "valid":
                if not isinstance(record_file, str):
                    fail(
                        "RUN_CORRUPT",
                        f"A valid direction result lacks its record file: {slot}/{direction}",
                    )
                record_path = pair_path / record_file
                if record_path.is_symlink() or not record_path.is_file():
                    fail(
                        "REVIEW_RESPONSE_NOT_FOUND",
                        f"The direction record bound by the reduction is "
                        f"missing: {slot}/{direction}",
                    )
                if sha256_bytes(record_path.read_bytes()) != result["record_sha256"]:
                    fail(
                        "HASH_MISMATCH",
                        f"The direction record bound by the reduction was "
                        f"modified: {slot}/{direction}",
                    )
    return document, pair_document, pair_path


def ai_verdict_document(
    *,
    case_id: str,
    consumed: dict[str, Any],
    recorded_at: str,
) -> tuple[dict[str, Any], str]:
    """Derive the comparison-facing AI verdict document from consumed facts.

    The mapping is the same content-space merge the blind human verdict
    carries: a stable ``content_N`` preference plus the two per-arm quality
    floors, with the AI authorship recorded explicitly. The reference frame
    stays pair-relative: the verdict names which anonymous content won, and
    the caller (comparison side) maps content back to baseline/challenger
    through the reveal mapping, exactly like a human verdict.
    """
    preference = consumed["reduction"]["overall_preference"]
    content_value = preference["content_value"]
    if content_value == "tie":
        verdict = "tie"
    elif content_value == "content_1":
        verdict = "a_better"
    else:
        verdict = "b_better"
    arms = consumed["arms"]
    # The comparison packet's blind display arms are derived at packet-build
    # time; the AI verdict is recorded in content space, so the document
    # carries the content binding for the later display-side substitution.
    fit = consumed["reduction"]["domain_method_fit"]
    intrusion = consumed["reduction"]["unjustified_ml_intrusion"]
    for judgment in (preference, fit, intrusion):
        if judgment["outcome"] != "stable":
            fail(
                "AI_PAIR_NOT_STABLE",
                "A non-stable judgment cannot feed the comparison reducer",
                judgment=judgment["outcome"],
            )
    floor_a = consumed["quality_floor"]["content_1"]
    floor_b = consumed["quality_floor"]["content_2"]
    document = {
        "authorship": {
            "kind": "ai_pair_reduction",
            "pair_id": consumed["pair_id"],
            "review_config_sha256": consumed["review_config_sha256"],
            "verdict_run_id": consumed["verdict_run_id"],
            "verdict_idea_index": consumed["verdict_idea_index"],
        },
        "case_id": case_id,
        "content_space": {
            "overall_preference": content_value,
            "domain_method_fit": fit["content_value"],
            "unjustified_ml_intrusion": intrusion["content_value"],
            "quality_floor_content_1": floor_a["state"],
            "quality_floor_content_2": floor_b["state"],
            "arm_content_1": {
                "idea_index": arms["content_1"]["idea_index"],
                "idea_sha256": arms["content_1"]["idea_sha256"],
                "run_id": arms["content_1"]["run_id"],
            },
            "arm_content_2": {
                "idea_index": arms["content_2"]["idea_index"],
                "idea_sha256": arms["content_2"]["idea_sha256"],
                "run_id": arms["content_2"]["run_id"],
            },
        },
        "recorded_at": recorded_at,
        "schema_version": AI_VERDICT_SCHEMA_VERSION,
    }
    return document, sha256_bytes(canonical_json_bytes(document))


def record_comparison_ai_verdict(
    workspace_root: Path,
    *,
    package_dir: Path,
    case_id: str,
    baseline_run_id: str,
    challenger_run_id: str,
    packet_sha256: str,
    recorded_by: str,
) -> dict[str, Any]:
    """Consume one matrix pair's AI reduction into the vault's AI channel.

    Full chain: the evaluation protocol must be registered, the workspace
    review config must equal the package's pinned binding, exactly one
    complete + stable pair reduction must bind the two ingested arms, and
    the vault must not have recorded this case's AI verdict before
    (write-once). The vault AI verdict carries the same packet binding a
    human verdict carries, so the reducer's packet check applies unchanged.
    """
    from .comparison import ComparisonVault, ai_verdict_facts
    from .contract import _now
    from .schema import nonempty_string, sha256 as parse_sha256

    recorded_by = nonempty_string(recorded_by, label="recorded_by")
    packet_sha256 = parse_sha256(packet_sha256, label="packet_sha256")
    workspace = workspace_root.resolve(strict=True)
    # The package pin carries the review-config binding the generation side
    # froze before any evaluation ran; the workspace's registered config must
    # equal it or the two ends have drifted apart.
    pin_path = package_dir / "evaluation-protocol-pin.json"
    if pin_path.is_symlink() or not pin_path.is_file():
        fail(
            "MIGRATION_PACKAGE_MISSING",
            "The comparison package lacks its evaluation-protocol pin",
            path=str(pin_path),
        )
    pin = parse_json_bytes(pin_path.read_bytes(), label="evaluation protocol pin")
    if not isinstance(pin, dict) or len(pin.get("review_config_sha256", "")) != 64:
        fail(
            "INVALID_SCHEMA",
            "The evaluation-protocol pin does not carry a review-config hash",
        )
    consumed = consume_pair_reduction(
        workspace,
        case_id=case_id,
        baseline_run_id=baseline_run_id,
        baseline_idea_index=_single_idea_index(workspace, baseline_run_id),
        challenger_run_id=challenger_run_id,
        challenger_idea_index=_single_idea_index(workspace, challenger_run_id),
        review_config_sha256=pin["review_config_sha256"],
    )
    vault = ComparisonVault(package_dir / "vault")
    if vault.load_ai_verdict(case_id) is not None:
        fail(
            "ARTIFACT_EXISTS",
            "An AI verdict is already recorded for this case; verdicts are "
            "write-once",
            case_id=case_id,
        )
    document, document_sha = ai_verdict_document(
        case_id=case_id,
        consumed=consumed,
        recorded_at=_now(),
    )
    facts = ai_verdict_facts(
        document,
        baseline_run_id=baseline_run_id,
        challenger_run_id=challenger_run_id,
        mapping=_display_mapping_for_case(package_dir, case_id),
        packet_sha256=packet_sha256,
        recorded_at=document["recorded_at"],
    )
    vault_sha = vault.record_ai_verdict(document)
    return {
        "case_id": case_id,
        "facts_sha256": facts.get("packet_sha256"),
        "pair_id": consumed["pair_id"],
        "record_sha256": vault_sha,
        "status": "recorded",
        "verdict": facts["verdict"],
        "verdict_document_sha256": document_sha,
    }


def _single_idea_index(workspace: Path, run_id: str) -> int:
    """The one finalized-idea index of a comparison run (exactly one)."""
    from .comparison import load_sealed_final_idea
    from .run_store import RunStore

    store = RunStore(workspace)
    idea_dir = store.runs_root / run_id / "artifacts" / "ideas"
    if not idea_dir.is_dir() or idea_dir.is_symlink():
        fail(
            "RUN_CORRUPT",
            "The ingested run lacks a finalized-idea directory",
            run_id=run_id,
        )
    indexes = []
    for candidate in sorted(idea_dir.iterdir()):
        if (
            candidate.is_dir()
            and not candidate.is_symlink()
            and candidate.name.isdigit()
        ):
            indexes.append(int(candidate.name))
    load_sealed_final_idea(workspace, run_id)  # exact-one + seven-field checks
    if len(indexes) != 1:
        fail(
            "RUN_CORRUPT",
            "The ingested run must hold exactly one finalized idea",
            run_id=run_id,
            idea_count=len(indexes),
        )
    return indexes[0]


def _display_mapping_for_case(package_dir: Path, case_id: str):
    """The frozen blind mapping row for one case, from the package bytes."""
    from .comparison import BlindPairMapping, assert_blind_mapping_document_shape

    mapping_document = parse_json_bytes(
        (package_dir / "blind-mapping.json").read_bytes(),
        label="blind mapping",
    )
    mappings: tuple[BlindPairMapping, ...] = assert_blind_mapping_document_shape(
        mapping_document
    )
    for mapping in mappings:
        if mapping.case_id == case_id:
            return mapping
    fail(
        "COMPARISON_IDENTITY_MISMATCH",
        "The frozen blind mapping lacks this case",
        case_id=case_id,
    )
