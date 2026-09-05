"""Offline Prompt-Profile comparison boundary (ticket 02).

One deterministic, credential-free boundary that proves the governed
cross-domain prompt comparison end to end on synthetic sealed evidence:
four-case subset selection from the approved 12-case Canary, the frozen
4-pair/8-run matrix, the frozen blind mapping and sanitized pair packets,
the append-only spend ledger with the Plan Gate reapproval threshold,
write-once pair verdicts behind a fail-closed reveal gate, and the
deterministic Promotion reducer. Nothing here issues provider requests,
reads credentials, or consumes real case content: every seam is pure over
pinned inputs and returns canonical bytes.

The boundary is offline-only by construction: selection, matrix, mapping,
commands, ledger, ingestion, verdicts, and reduction are deterministic
functions of hash-pinned inputs. Timestamps appear only in ledger ingest
records (facts at ingest time) and are excluded from determinism checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
import os
from pathlib import Path
import re
import shlex
import statistics
from typing import Any, Callable, Mapping

from . import pricing
from .admission import (
    DEFAULT_MAX_TOKENS,
    MAX_ATTEMPTS_PER_OPERATION,
    WORST_CASE_INPUT_TOKENS_PER_ROUND,
    _require_clean_worktree,
)
from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import DEEPSEEK_MODEL_ID, _now
from .errors import IdeationInputError, fail
from .evaluation import EVALUATION_RUBRIC_SCHEMA_VERSION
from .profiles import (
    CROSS_DOMAIN_V1,
    ML_BASELINE_V1,
    PromptProfile,
    assert_registry_integrity,
    profile_bundle_sha256,
    profile_registry_sha256,
    resolve_profile,
    validate_profile_field,
)
from .retrieval import RETRIEVAL_POLICY_VERSION
from .run_store import RunStore
from .schema import case_id as parse_case_id
from .schema import closed_object, nonempty_string, sha256 as parse_sha256
from .schema import timestamp

COMPARISON_SCHEMA_VERSION = "prompt-comparison-v1.0.0"
COMPARISON_SPEC_VERSION = "cross-domain-ideation-prompt-v1"

# The four pre-registered clusters of the governed comparison (spec: one
# case each from these methodologically distinct families).
COMPARISON_CLUSTERS: tuple[str, ...] = (
    "Genetics & Molecular Biology",
    "Health & Medicine",
    "Social & Behavioral Sciences",
    "Materials Science",
)

# The approved Canary v1.1 selection manifest identity (Robert-approved,
# artifacts/ideation-inputs/canary-v1.1-selection-approval.json pins this
# SHA-256). A different manifest identity is not the approved Canary.
APPROVED_CANARY_SELECTION_MANIFEST_SHA256 = (
    "aae9d766402a7e796bd5fd5db2b3979eefa6a351bb0cdc0716aa71ace5e0bb2f"
)
APPROVED_CANARY_SELECTION_VERSION = "canary-case-selection-v1.1"
APPROVED_CANARY_CASE_COUNT = 12

# The eight clusters of the approved Canary selection (VM: every comparison
# input case must belong to this closed set; a non-Canary cluster fails).
CANARY_CLUSTERS: frozenset[str] = frozenset(
    {
        "Environmental Sciences",
        "Genetics & Molecular Biology",
        "Health & Medicine",
        "Materials Science",
        "Neuroscience & Cognitive Sciences",
        "Public Health & Policy",
        "Social & Behavioral Sciences",
        "Technology & Engineering",
    }
)

BASELINE_PROFILE_ID = ML_BASELINE_V1.profile_id
CHALLENGER_PROFILE_ID = CROSS_DOMAIN_V1.profile_id

# Pinned one-major-variable execution parameters (Proposal 002): the pair
# arms may differ only in Prompt Profile.
COMPARISON_MAX_NUM_GENERATIONS = 1
COMPARISON_NUM_REFLECTIONS = 3
COMPARISON_MAX_TOKENS = DEFAULT_MAX_TOKENS
COMPARISON_REASONING_EFFORT = "high"

# Canary aggregate budget and the Plan Gate machinery.
CANARY_HARD_CAP_CNY = Decimal("30.00")
LEDGER_INIT_SPEND_CNY = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")
# Recorded live-smoke actual cost of the historical Canary stage (the
# documented 0.14 CNY run in docs/research/live-smoke-execution-evidence.md,
# Proposal 002). It is the ledger's immutable opening balance, so the
# enforced 30.00 CNY cap corresponds to the documented 29.86 CNY remaining.
CANARY_STAGE_HISTORICAL_SPEND_CNY = Decimal("0.14")

# Operational Regression Budgets (Proposal 002 pre-registered criteria).
COST_ENVELOPE_FACTOR = Decimal("2.0")
LATENCY_ENVELOPE_FACTOR = Decimal("2.0")

# Promotion thresholds (Proposal 002 pre-registered criteria).
PROMOTION_MIN_CHALLENGER_WINS = 3
PROMOTION_MAX_BASELINE_WINS = 0
DOMAIN_METHOD_MIN_IMPROVED = 2

PAIR_PACKET_SCHEMA_VERSION = "comparison-pair-packet-v1.0.0"
BLIND_MAPPING_SCHEMA_VERSION = "comparison-blind-mapping-v1.0.0"
COMPARISON_MATRIX_SCHEMA_VERSION = "comparison-run-matrix-v1.0.0"
EXECUTION_CODE_PIN_SCHEMA_VERSION = "comparison-execution-code-pin-v1.0.0"
SELECTION_MANIFEST_SCHEMA_VERSION = "comparison-selection-manifest-v1.0.0"
SELECTION_APPROVAL_SCHEMA_VERSION = "comparison-selection-approval-v1.0.0"
SPEND_LEDGER_SCHEMA_VERSION = "comparison-spend-ledger-v1.3.0"
RUN_QUARANTINE_SCHEMA_VERSION = "comparison-run-quarantine-v1.0.0"
RUN_RESERVATION_SCHEMA_VERSION = "comparison-run-reservation-v1.2.0"
PIN_SUPERSEDE_SCHEMA_VERSION = "comparison-execution-code-pin-supersede-v1.0.0"
QUARANTINE_REASON_ZERO_FINALIZED_IDEA = "ZERO_FINALIZED_IDEA"
VERDICT_SCHEMA_VERSION = "comparison-pair-verdict-v1.1.0"
REDUCTION_SCHEMA_VERSION = "comparison-reduction-v1.0.0"
RUN_RESULT_SCHEMA_VERSION = "comparison-run-result-v1.0.0"
# Ticket 03: the comparison-facing AI verdict document (authorship=AI, in
# anonymous content space) recorded in the vault's ai-verdicts/ channel.
AI_VERDICT_SCHEMA_VERSION = "comparison-ai-verdict-v1.0.0"
EVALUATION_PROTOCOL_GATE_SCHEMA_VERSION = "comparison-evaluation-protocol-gate-v1.0.0"

DEFAULT_PROMPT_COMPARISON_REAPPROVAL_THRESHOLD_CNY = Decimal("5.00")
DEFAULT_COMPARISON_PACKAGE_DIR = (
    Path("artifacts")
    / "ideation-inputs"
    / "comparisons"
    / "002-cross-domain-ideation-prompt"
)
SLOT_RUNNER = "scripts/run-prompt-comparison-slot"
EXECUTION_CODE_PIN_NAME = "execution-code-pin.json"

VERDICT_ENUM: frozenset[str] = frozenset(
    {"a_better", "b_better", "tie", "incomparable"}
)
# Pair-level domain-method-fit judgment: the challenger arm's domain-method
# fit is strictly better than / equal to / strictly worse than the baseline
# arm's, judged by Robert on the blinded packet (the reference frame is
# always pair-relative, never an absolute per-arm scale).
DOMAIN_METHOD_FIT_ENUM: frozenset[str] = frozenset(
    {"challenger_better", "tie", "baseline_better", "incomparable"}
)
# Pair-level unjustified-ML-intrusion judgment: the challenger arm's
# unjustified ML intrusion relative to the baseline arm, judged on the
# blinded packet (pre-registered zero-tolerance: it must not increase).
ML_INTRUSION_ENUM: frozenset[str] = frozenset(
    {"increased", "unchanged", "decreased", "incomparable"}
)
# Rubric-floor problem keys from the approved Idea Quality Rubric v1.0.0:
# any of these observed on either arm blocks promotion.
RUBRIC_FLOOR_PROBLEM_VALUES: frozenset[str] = frozenset(
    {
        "mismatched",
        "unsound",
        "name_dropped",
        "signal_found",
        "leak_found",
    }
)
RUBRIC_FLOOR_CLEAN_VALUE = "clean"

# Pair-packet forbidden tokens, matched as JSON keys/field names only (the
# scan inspects the serialized structure, not the model-generated idea text;
# legitimate English words like "cost-effective" in an idea payload are not
# blinding leaks). The blind packet must never carry a profile identity, an
# execution-order marker, or any operational metadata field.
PAIR_PACKET_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "arm_a_profile_id",
        "arm_b_profile_id",
        "arm_position",
        "attempt_count",
        "attempts",
        "bundle_sha256",
        "cost_cny",
        "duration_ms",
        "elapsed_seconds",
        "finish_reason",
        "max_tokens",
        "physical_attempt_count",
        "profile_id",
        "prompt_profile",
        "provider",
        "reasoning_effort",
        "response_id",
        "run_index",
        "terminal_outcome",
        "total_tokens",
        "usage",
        "end_to_end_latency_ms",
    }
)
PAIR_PACKET_FORBIDDEN_IDENTITY_VALUES: frozenset[str] = frozenset(
    {BASELINE_PROFILE_ID, CHALLENGER_PROFILE_ID}
)

# The exact seven IDEA JSON fields a sealed run's finalized idea.json must
# carry (mirrors controller.REQUIRED_IDEA_FIELDS and the profiles.py IDEA
# JSON contract; a sealed payload is the post-validation 7-field dict, so
# missing OR extra keys mean tampering and fail closed as RUN_CORRUPT).
SEALED_IDEA_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "Abstract",
        "Experiments",
        "Name",
        "Related Work",
        "Risk Factors and Limitations",
        "Short Hypothesis",
        "Title",
    }
)

_IDEA_INVENTORY_PATTERN = re.compile(r"artifacts/ideas/(\d{6})/idea\.json\Z")
_MONEY_PATTERN = re.compile(r"\d+\.\d{2}\Z")
_GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


def _money(value: object, *, label: str) -> Decimal:
    if not isinstance(value, str) or not _MONEY_PATTERN.fullmatch(value):
        fail("INVALID_MONEY", f"{label} must be a decimal CNY amount string")
    return Decimal(value)


def _quantize_cny(amount: Decimal) -> Decimal:
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_CEILING)


def _canonical_seed_hex(seed_label: str, digest_input: str) -> str:
    """Deterministic per-purpose hash in the canary selection key tradition."""
    return sha256_bytes(f"{seed_label}|{digest_input}".encode("utf-8"))


# ==========================================================================
# Selection: four cases, one per pre-registered cluster, canonical hash pick
# ==========================================================================


@dataclass(frozen=True, slots=True)
class CanaryCase:
    """The comparison-facing identity of one approved Canary case."""

    case_id: str
    cluster: str
    canonical_hash: str
    target_row_sha256: str
    source_row_snapshot_sha256: str


@dataclass(frozen=True, slots=True)
class TargetSourceSnapshot:
    """Snapshot bindings the selection re-verifies without reading content."""

    target_dataset_sha256: str
    target_row_sha256: str


def select_comparison_cases(
    canary_cases: tuple[CanaryCase, ...],
    *,
    canary_selection_manifest_sha256: str,
    target_source: dict[str, TargetSourceSnapshot],
) -> tuple[CanaryCase, ...]:
    """Deterministically pick one Canary case per pre-registered cluster.

    The input must already be the approved 12-case Canary identity: the
    manifest SHA-256 is pinned to the approved constant, the input must be
    exactly 12 cases over the eight Canary clusters (a forged subset fails
    closed), duplicates fail closed, every pre-registered cluster must be
    present, and each case's target row must match the current source
    snapshot (row hash and dataset hash drift fail closed). Each case's
    canonical hash is recomputed from its case id and must match the
    supplied hash, so a forged canonical hash fails closed
    (CANARY_HASH_FORGERY). The winner per
    cluster is the minimal canonical case hash; the canonical hash is a
    full digest, so ties cannot occur.

    The selection input is identity-only: no Target contribution, result,
    or model output is consulted anywhere in this function.
    """
    parse_sha256(
        canary_selection_manifest_sha256,
        label="canary_selection_manifest_sha256",
    )
    if canary_selection_manifest_sha256 != APPROVED_CANARY_SELECTION_MANIFEST_SHA256:
        fail(
            "CANARY_IDENTITY_UNAPPROVED",
            "The comparison accepts only the approved 12-case Canary manifest identity",
            provided=canary_selection_manifest_sha256,
            expected=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        )
    if not canary_cases:
        fail("EMPTY_CANARY_INPUT", "The Canary case list is empty")
    if len(canary_cases) != APPROVED_CANARY_CASE_COUNT:
        fail(
            "CANARY_IDENTITY_UNAPPROVED",
            "The comparison input must be the full approved 12-case Canary identity",
            provided=len(canary_cases),
            expected=APPROVED_CANARY_CASE_COUNT,
        )

    seen_case_ids: set[str] = set()
    seen_targets: dict[str, str] = {}
    for case in canary_cases:
        parse_case_id(case.case_id)
        parse_sha256(case.canonical_hash, label=f"{case.case_id}.canonical_hash")
        expected_hash = canonical_case_hash_for_canary_case(case.case_id)
        if case.canonical_hash != expected_hash:
            fail(
                "CANARY_HASH_FORGERY",
                "A comparison input case carries a forged canonical hash",
                case_id=case.case_id,
                provided=case.canonical_hash,
                expected=expected_hash,
            )
        parse_sha256(case.target_row_sha256, label=f"{case.case_id}.target_row_sha256")
        parse_sha256(
            case.source_row_snapshot_sha256,
            label=f"{case.case_id}.source_row_snapshot_sha256",
        )
        if case.cluster not in CANARY_CLUSTERS:
            fail(
                "CANARY_IDENTITY_UNAPPROVED",
                "A comparison input case carries a non-Canary cluster",
                case_id=case.case_id,
                cluster=case.cluster,
            )
        if case.case_id in seen_case_ids:
            fail(
                "DUPLICATE_CANARY_CASE",
                "The Canary case list repeats a case id",
                case_id=case.case_id,
            )
        seen_case_ids.add(case.case_id)
        prior = seen_targets.get(case.target_row_sha256)
        if prior is not None:
            fail(
                "DUPLICATE_CANARY_TARGET",
                "The Canary case list repeats a target row",
                case_ids=[prior, case.case_id],
            )
        seen_targets[case.target_row_sha256] = case.case_id

    winners: list[CanaryCase] = []
    for cluster in COMPARISON_CLUSTERS:
        snapshot = target_source.get(cluster)
        if snapshot is None:
            fail(
                "MISSING_SOURCE_SNAPSHOT",
                "The comparison lacks the current source snapshot binding",
                cluster=cluster,
            )
        parse_sha256(
            snapshot.target_dataset_sha256,
            label=f"source snapshot.{cluster}.target_dataset_sha256",
        )
        parse_sha256(
            snapshot.target_row_sha256,
            label=f"source snapshot.{cluster}.target_row_sha256",
        )
        candidates = [case for case in canary_cases if case.cluster == cluster]
        if not candidates:
            fail(
                "MISSING_CLUSTER",
                "The Canary manifest lacks a required cluster",
                cluster=cluster,
            )
        ranked = sorted(
            candidates, key=lambda case: (case.canonical_hash, case.case_id)
        )
        winner = ranked[0]
        if winner.target_row_sha256 != snapshot.target_row_sha256:
            fail(
                "SOURCE_HASH_DRIFT",
                "The selected Canary case no longer matches the source dataset row",
                cluster=cluster,
                case_id=winner.case_id,
            )
        if winner.source_row_snapshot_sha256 != snapshot.target_dataset_sha256:
            fail(
                "SOURCE_HASH_DRIFT",
                "The selected Canary case's source snapshot drifted from the current dataset",
                cluster=cluster,
                case_id=winner.case_id,
            )
        winners.append(winner)

    if len({case.case_id for case in winners}) != len(COMPARISON_CLUSTERS):
        fail(
            "SELECTION_COLLAPSED", "The per-cluster selection collapsed to fewer cases"
        )
    return tuple(winners)


def build_selection_manifest(
    selected_cases: tuple[CanaryCase, ...],
    *,
    canary_selection_manifest_sha256: str,
    target_source: dict[str, TargetSourceSnapshot],
) -> dict[str, Any]:
    """Deterministic sanitized 4-case selection document (identity only)."""
    if len(selected_cases) != len(COMPARISON_CLUSTERS):
        fail(
            "INVALID_SELECTION_SIZE",
            "The comparison selection must cover exactly the four clusters",
        )
    document: dict[str, Any] = {
        "approved_canary_selection_manifest_sha256": canary_selection_manifest_sha256,
        "cases": [
            {
                "canonical_case_hash": case.canonical_hash,
                "case_id": case.case_id,
                "cluster": case.cluster,
                "target_row_sha256": case.target_row_sha256,
            }
            for case in selected_cases
        ],
        "schema_version": SELECTION_MANIFEST_SCHEMA_VERSION,
        "selection_method": "canonical_case_hash_minimal_per_cluster",
        "source_snapshots": {
            cluster: {"target_row_sha256": snapshot.target_row_sha256}
            for cluster, snapshot in sorted(target_source.items())
        },
        "spec_version": COMPARISON_SPEC_VERSION,
    }
    return document


def canonical_case_hash_for_canary_case(
    case_id: str,
    *,
    seed: str = APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
) -> str:
    """Compute the deterministic canonical tie-break hash for a Canary case."""
    parse_case_id(case_id)
    parse_sha256(seed, label="seed")
    return _canonical_seed_hex(f"{seed}|canonical_case_hash", case_id)


def build_selection_approval(
    *,
    selection_manifest: dict[str, Any],
    input_pins: dict[str, dict[str, dict[str, str]]],
    source_canary_selection_manifest_sha256: str = APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
    approved_by: str = "Robert",
    decision: str = "approved",
    canonical_tie_break: str = "canonical_case_hash_minimal_per_cluster",
    approved_at: str = "2026-09-04T07:00:00.000000Z",
) -> dict[str, Any]:
    """Serialize the Robert approval artifact for the 4-case prompt comparison."""
    assert_registry_integrity()
    return {
        "approved_at": approved_at,
        "approved_by": approved_by,
        "canonical_tie_break": canonical_tie_break,
        "cluster_coverage": list(COMPARISON_CLUSTERS),
        "decision": decision,
        "fixed_configuration": {
            "max_num_generations": COMPARISON_MAX_NUM_GENERATIONS,
            "max_tokens": COMPARISON_MAX_TOKENS,
            "model_id": DEEPSEEK_MODEL_ID,
            "num_reflections": COMPARISON_NUM_REFLECTIONS,
            "reasoning_effort": COMPARISON_REASONING_EFFORT,
        },
        "input_hashes": {
            case_id: {
                "corpus": dict(pins["corpus"]),
                "workshop": dict(pins["workshop"]),
            }
            for case_id, pins in sorted(input_pins.items())
        },
        "prompt_profiles": {
            "baseline": {
                "bundle_sha256": profile_bundle_sha256(ML_BASELINE_V1),
                "contract_version": ML_BASELINE_V1.contract_version,
                "profile_id": ML_BASELINE_V1.profile_id,
            },
            "challenger": {
                "bundle_sha256": profile_bundle_sha256(CROSS_DOMAIN_V1),
                "contract_version": CROSS_DOMAIN_V1.contract_version,
                "profile_id": CROSS_DOMAIN_V1.profile_id,
            },
            "registry_sha256": profile_registry_sha256(),
        },
        "rationale": (
            "Approved 4-case comparison package selection across 4 methodologically "
            "distinct Canary clusters (Genetics & Molecular Biology, Health & Medicine, "
            "Materials Science, Social & Behavioral Sciences) with 100% pre-registered "
            "single-variable controls, zero-spend initialization, and zero outcome inspection."
        ),
        "schema_version": SELECTION_APPROVAL_SCHEMA_VERSION,
        "selection_manifest_sha256": sha256_bytes(
            canonical_json_bytes(selection_manifest)
        ),
        "source_canary_selection_manifest_sha256": source_canary_selection_manifest_sha256,
        "zero_outcome_selection_declaration": (
            "The 4 comparison cases were selected deterministically using only "
            "hash-pinned Canary identity records and canonical case hash tie-breaking, "
            "without inspecting Target contribution fields, literature review results, "
            "or model outputs."
        ),
    }


def load_approved_canary_cases(
    workspace_root: Path,
) -> tuple[
    tuple[CanaryCase, ...],
    dict[str, TargetSourceSnapshot],
    dict[str, dict[str, dict[str, str]]],
]:
    """Load the 12 approved Canary cases from the pinned selection manifest.

    Validates:
    - canary-v1.1-selection-manifest.json matches APPROVED_CANARY_SELECTION_MANIFEST_SHA256.
    - canary-v1.1-selection-approval.json exists and decision is approved by Robert.
    - data/raw/target_papers.csv matches source_hashes["target_papers.csv"].
    - 12 distinct cases across the 8 CANARY_CLUSTERS.
    - Approved workshops and corpora exist and have approved manifests and matching hashes.
    """
    manifest_path = (
        workspace_root
        / "artifacts"
        / "ideation-inputs"
        / "canary-v1.1-selection-manifest.json"
    )
    if not manifest_path.is_file():
        fail(
            "CANARY_MANIFEST_NOT_FOUND",
            "The approved Canary selection manifest was not found",
            path=str(manifest_path),
        )
    manifest_bytes = manifest_path.read_bytes()
    observed_manifest_sha256 = sha256_bytes(manifest_bytes)
    if observed_manifest_sha256 != APPROVED_CANARY_SELECTION_MANIFEST_SHA256:
        fail(
            "CANARY_IDENTITY_UNAPPROVED",
            "The Canary selection manifest hash drifted from the pinned approval",
            expected=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
            observed=observed_manifest_sha256,
        )
    manifest = parse_json_bytes(manifest_bytes, label="canary_manifest")

    approval_path = (
        workspace_root
        / "artifacts"
        / "ideation-inputs"
        / "canary-v1.1-selection-approval.json"
    )
    if not approval_path.is_file():
        fail(
            "CANARY_APPROVAL_NOT_FOUND",
            "The Canary selection approval artifact was not found",
            path=str(approval_path),
        )
    approval = parse_json_bytes(approval_path.read_bytes(), label="canary_approval")
    if (
        approval.get("decision") != "approved"
        or approval.get("approved_by") != "Robert"
        or approval.get("selection_manifest_sha256")
        != APPROVED_CANARY_SELECTION_MANIFEST_SHA256
    ):
        fail(
            "CANARY_APPROVAL_INVALID",
            "The Canary selection approval artifact is invalid or drifted",
            approval=approval,
        )

    target_papers_path = workspace_root / "data" / "raw" / "target_papers.csv"
    if not target_papers_path.is_file():
        fail(
            "TARGET_DATASET_NOT_FOUND",
            "The target papers dataset was not found",
            path=str(target_papers_path),
        )
    target_papers_sha256 = sha256_bytes(target_papers_path.read_bytes())
    expected_dataset_sha256 = manifest.get("source_hashes", {}).get("target_papers.csv")
    if target_papers_sha256 != expected_dataset_sha256:
        fail(
            "SOURCE_HASH_DRIFT",
            "The target dataset drifted from the approved Canary source snapshot",
            expected=expected_dataset_sha256,
            observed=target_papers_sha256,
        )

    cases_data = manifest.get("cases")
    if (
        not isinstance(cases_data, list)
        or len(cases_data) != APPROVED_CANARY_CASE_COUNT
    ):
        fail(
            "CANARY_CASE_COUNT_MISMATCH",
            "The Canary manifest does not contain exactly 12 cases",
            case_count=len(cases_data) if isinstance(cases_data, list) else None,
        )

    canary_cases: list[CanaryCase] = []
    for c in cases_data:
        case_id = c.get("case_id")
        cluster = c.get("cluster")
        target_row_sha256 = c.get("target_row_sha256")
        if not case_id or not cluster or not target_row_sha256:
            fail(
                "CORRUPT_CANARY_CASE",
                "A Canary case entry lacks required fields",
                case=c,
            )
        c_hash = canonical_case_hash_for_canary_case(case_id)
        canary_cases.append(
            CanaryCase(
                case_id=case_id,
                cluster=cluster,
                canonical_hash=c_hash,
                target_row_sha256=target_row_sha256,
                source_row_snapshot_sha256=target_papers_sha256,
            )
        )

    target_source: dict[str, TargetSourceSnapshot] = {}
    for cluster in COMPARISON_CLUSTERS:
        candidates = [c for c in canary_cases if c.cluster == cluster]
        if not candidates:
            fail(
                "MISSING_COMPARISON_CLUSTER",
                "Canary lacks comparison cluster",
                cluster=cluster,
            )
        winner = min(candidates, key=lambda c: (c.canonical_hash, c.case_id))
        target_source[cluster] = TargetSourceSnapshot(
            target_dataset_sha256=target_papers_sha256,
            target_row_sha256=winner.target_row_sha256,
        )

    input_pins: dict[str, dict[str, dict[str, str]]] = {}
    for cluster, snapshot in target_source.items():
        candidates = [c for c in canary_cases if c.cluster == cluster]
        winner = min(candidates, key=lambda c: (c.canonical_hash, c.case_id))
        cid = winner.case_id

        workshop_rel = f"artifacts/ideation-inputs/workshops/{cid}/attempts/attempt-001/resolution/{cid}.md"
        corpus_rel = f"artifacts/ideation-inputs/corpora/{cid}/corpus.json"
        w_file = workspace_root / workshop_rel
        c_file = workspace_root / corpus_rel

        if not w_file.is_file():
            fail(
                "WORKSHOP_NOT_FOUND",
                "Approved workshop file missing",
                path=str(w_file),
            )
        if not c_file.is_file():
            fail(
                "CORPUS_NOT_FOUND",
                "Approved corpus file missing",
                path=str(c_file),
            )

        w_sha256 = sha256_bytes(w_file.read_bytes())
        c_sha256 = sha256_bytes(c_file.read_bytes())

        w_manifest_path = (
            workspace_root
            / f"artifacts/ideation-inputs/workshops/{cid}/attempts/attempt-001/resolution/workshop-manifest.json"
        )
        if not w_manifest_path.is_file():
            fail(
                "WORKSHOP_MANIFEST_NOT_FOUND",
                "Approved workshop manifest missing",
                path=str(w_manifest_path),
            )
        w_manifest = parse_json_bytes(
            w_manifest_path.read_bytes(), label=f"{cid}.workshop_manifest"
        )
        if w_manifest.get("approval_status") != "approved":
            fail("WORKSHOP_UNAPPROVED", "Workshop is not approved", case_id=cid)
        if w_manifest.get("workshop", {}).get("sha256") != w_sha256:
            fail(
                "WORKSHOP_HASH_MISMATCH",
                "Workshop bytes drifted from approved manifest",
                case_id=cid,
            )

        c_manifest_path = (
            workspace_root
            / f"artifacts/ideation-inputs/corpora/{cid}/bundle-manifest.json"
        )
        if not c_manifest_path.is_file():
            fail(
                "CORPUS_MANIFEST_NOT_FOUND",
                "Approved corpus bundle manifest missing",
                path=str(c_manifest_path),
            )
        c_manifest = parse_json_bytes(
            c_manifest_path.read_bytes(), label=f"{cid}.corpus_manifest"
        )
        if c_manifest.get("approval_status") != "approved":
            fail("CORPUS_UNAPPROVED", "Corpus is not approved", case_id=cid)
        if c_manifest.get("inventory", {}).get("corpus.json") != c_sha256:
            fail(
                "CORPUS_HASH_MISMATCH",
                "Corpus bytes drifted from approved manifest",
                case_id=cid,
            )

        input_pins[cid] = {
            "corpus": {"path": corpus_rel, "sha256": c_sha256},
            "workshop": {"path": workshop_rel, "sha256": w_sha256},
        }

    return tuple(canary_cases), target_source, input_pins


def comparison_selection_seed(selection_manifest: dict[str, Any]) -> str:
    """The frozen seed every downstream derivation is keyed on."""
    return sha256_bytes(canonical_json_bytes(selection_manifest))


def _balanced_partition(
    items: list[Any], *, digest_of: Any, key_of: Any, need: int
) -> tuple[list[Any], list[Any]]:
    """Deterministic 2/2 balance over a parity partition.

    `digest_of(item)` returns the parity hex digest; items whose digest
    starts even go to the first side, odd to the second, then the sides are
    rebalanced by `key_of` rank (lowest key keeps its parity-assigned side)
    until the exact split holds. No content or output is ever consulted.
    """
    first: list[Any] = []
    second: list[Any] = []
    for item in items:
        digest = digest_of(item)
        (first if int(digest[0], 16) % 2 == 0 else second).append(item)

    def _rebalance() -> None:
        if len(first) < need:
            deficit = need - len(first)
            ordered = sorted(second, key=key_of)
            moved = ordered[:deficit]
            second[:] = [item for item in second if item not in moved]
            first.extend(moved)
        elif len(second) < need:
            deficit = need - len(second)
            ordered = sorted(first, key=key_of)
            moved = ordered[:deficit]
            first[:] = [item for item in first if item not in moved]
            second.extend(moved)

    _rebalance()
    if len(first) != need or len(second) != need:
        fail(
            "BALANCE_INVARIANT_COLLAPSED",
            "The deterministic balance invariant collapsed",
            first=len(first),
            second=len(second),
        )
    return first, second


# ==========================================================================
# Frozen matrix: 4 pairs, 8 runs, balanced order, single-variable arms
# ==========================================================================


@dataclass(frozen=True, slots=True)
class ComparisonRun:
    """One planned Ideation Run of the frozen comparison matrix."""

    run_index: int
    pair_index: int
    arm_position: int
    case_id: str
    cluster: str
    profile_id: str
    max_num_generations: int
    num_reflections: int


@dataclass(frozen=True, slots=True)
class ComparisonPair:
    """One case pair with its balanced order and blind mapping commitments."""

    pair_index: int
    case_id: str
    cluster: str
    first_profile_id: str
    second_profile_id: str


def build_frozen_matrix(
    selected_cases: tuple[CanaryCase, ...],
    *,
    selection_manifest: dict[str, Any],
) -> tuple[tuple[ComparisonRun, ...], tuple[ComparisonPair, ...]]:
    """Build the strict 4-pair/8-run matrix with balanced execution order.

    Exactly 2 pairs start with the baseline arm and 2 with the challenger
    arm, keyed on `sha256(seed|arm_order|case_id)` parity; ties are broken
    deterministically by canonical case hash when the parity split is not
    exactly 2/2. The two arms of every pair differ in exactly one Run
    Specification field: the Prompt Profile id and its bundle hash.
    """
    if len(selected_cases) != len(COMPARISON_CLUSTERS):
        fail(
            "INVALID_SELECTION_SIZE",
            "The frozen matrix requires exactly one case per pre-registered cluster",
        )
    seed = comparison_selection_seed(selection_manifest)

    baseline_first, challenger_first = _balanced_partition(
        list(selected_cases),
        digest_of=lambda case: _canonical_seed_hex(
            "arm_order", f"{seed}|{case.case_id}"
        ),
        key_of=lambda case: (case.canonical_hash, case.case_id),
        need=len(COMPARISON_CLUSTERS) // 2,
    )
    if len(baseline_first) != 2 or len(challenger_first) != 2:
        fail(
            "ORDER_BALANCE_FAILED",
            "The execution-order balance invariant collapsed",
            baseline_first=len(baseline_first),
            challenger_first=len(challenger_first),
        )

    runs: list[ComparisonRun] = []
    pairs: list[ComparisonPair] = []
    run_counter = 1
    baseline_ordered = sorted(baseline_first, key=lambda c: c.cluster)
    challenger_ordered = sorted(challenger_first, key=lambda c: c.cluster)
    ordered_cases = baseline_ordered + challenger_ordered
    for pair_index, case in enumerate(ordered_cases, start=1):
        first_profile = (
            BASELINE_PROFILE_ID if case in baseline_first else CHALLENGER_PROFILE_ID
        )
        second_profile = (
            CHALLENGER_PROFILE_ID
            if first_profile == BASELINE_PROFILE_ID
            else BASELINE_PROFILE_ID
        )
        runs.append(
            ComparisonRun(
                run_index=run_counter,
                pair_index=pair_index,
                arm_position=1,
                case_id=case.case_id,
                cluster=case.cluster,
                profile_id=first_profile,
                max_num_generations=COMPARISON_MAX_NUM_GENERATIONS,
                num_reflections=COMPARISON_NUM_REFLECTIONS,
            )
        )
        run_counter += 1
        runs.append(
            ComparisonRun(
                run_index=run_counter,
                pair_index=pair_index,
                arm_position=2,
                case_id=case.case_id,
                cluster=case.cluster,
                profile_id=second_profile,
                max_num_generations=COMPARISON_MAX_NUM_GENERATIONS,
                num_reflections=COMPARISON_NUM_REFLECTIONS,
            )
        )
        run_counter += 1
        pairs.append(
            ComparisonPair(
                pair_index=pair_index,
                case_id=case.case_id,
                cluster=case.cluster,
                first_profile_id=first_profile,
                second_profile_id=second_profile,
            )
        )

    if len(runs) != 2 * len(COMPARISON_CLUSTERS) or len(pairs) != len(
        COMPARISON_CLUSTERS
    ):
        fail(
            "MATRIX_SHAPE_FAILED",
            "The frozen matrix must hold exactly 4 pairs and 8 runs",
        )
    return tuple(runs), tuple(pairs)


def build_matrix_document(
    runs: tuple[ComparisonRun, ...],
    pairs: tuple[ComparisonPair, ...],
    *,
    selection_manifest: dict[str, Any],
    input_pins: dict[str, dict[str, str]],
    retriever_policy_version: str = RETRIEVAL_POLICY_VERSION,
    rubric_version: str = EVALUATION_RUBRIC_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Serialize the frozen matrix with per-arm input pins and identity only.

    `input_pins` maps case_id -> {"workshop": {path, sha256}, "corpus":
    {path, sha256}}; both arms of one pair must carry identical pins, and
    the single-variable assertion is part of the serialization: any arm
    difference other than the prompt profile fails closed.
    """
    seed = comparison_selection_seed(selection_manifest)
    runs_by_pair: dict[int, list[ComparisonRun]] = {}
    for run in runs:
        runs_by_pair.setdefault(run.pair_index, []).append(run)
    runs_list: list[dict[str, Any]] = []
    for pair in pairs:
        arm_runs = sorted(runs_by_pair[pair.pair_index], key=lambda r: r.arm_position)
        pins = input_pins.get(pair.case_id)
        if not isinstance(pins, dict):
            fail(
                "MISSING_INPUT_PINS",
                "The frozen matrix lacks the approved input pins",
                case_id=pair.case_id,
            )
        workshop = closed_object(
            pins.get("workshop"),
            label=f"input_pins.{pair.case_id}.workshop",
            keys={"path", "sha256"},
        )
        corpus = closed_object(
            pins.get("corpus"),
            label=f"input_pins.{pair.case_id}.corpus",
            keys={"path", "sha256"},
        )
        parse_sha256(workshop["sha256"], label="workshop_sha256")
        parse_sha256(corpus["sha256"], label="corpus_sha256")
        nonempty_string(workshop["path"], label="workshop_path")
        nonempty_string(corpus["path"], label="corpus_path")
        assert_single_variable_matrix(
            {
                "runs": [
                    {
                        "case_id": run.case_id,
                        "cluster": run.cluster,
                        "corpus": corpus,
                        "max_num_generations": run.max_num_generations,
                        "max_tokens": COMPARISON_MAX_TOKENS,
                        "model_id": DEEPSEEK_MODEL_ID,
                        "num_reflections": run.num_reflections,
                        "pair_index": run.pair_index,
                        "prompt_profile_id": run.profile_id,
                        "reasoning_effort": COMPARISON_REASONING_EFFORT,
                        "workshop": workshop,
                    }
                    for run in arm_runs
                ]
            }
        )
        for run in arm_runs:
            runs_list.append(
                {
                    "arm_position": run.arm_position,
                    "case_id": run.case_id,
                    "cluster": run.cluster,
                    "corpus": corpus,
                    "max_num_generations": run.max_num_generations,
                    "max_tokens": COMPARISON_MAX_TOKENS,
                    "model_id": DEEPSEEK_MODEL_ID,
                    "num_reflections": run.num_reflections,
                    "pair_index": run.pair_index,
                    "prompt_profile_id": run.profile_id,
                    "reasoning_effort": COMPARISON_REASONING_EFFORT,
                    "run_index": run.run_index,
                    "workshop": workshop,
                }
            )
    document = {
        "baseline_first_pairs_count": sum(
            1 for pair in pairs if pair.first_profile_id == BASELINE_PROFILE_ID
        ),
        "challenger_first_pairs_count": sum(
            1 for pair in pairs if pair.first_profile_id == CHALLENGER_PROFILE_ID
        ),
        "matrix_seed_sha256": seed,
        "pairs_count": len(pairs),
        "planned_runs_count": len(runs),
        "retriever_policy_version": retriever_policy_version,
        "rubric_version": rubric_version,
        "runtime_controls": {
            "max_attempts_per_operation": MAX_ATTEMPTS_PER_OPERATION,
            "provider": "deepseek",
        },
        "runs": runs_list,
        "schema_version": COMPARISON_MATRIX_SCHEMA_VERSION,
        "selection_manifest": selection_manifest,
    }
    document["matrix_sha256"] = frozen_matrix_digest(document)
    return document


def frozen_matrix_digest(matrix_document: dict[str, Any]) -> str:
    """The digest of a frozen matrix document: its pin key is excluded so
    the digest of the document equals the `matrix_sha256` it carries."""
    without_pin = {
        key: value for key, value in matrix_document.items() if key != "matrix_sha256"
    }
    return sha256_bytes(canonical_json_bytes(without_pin))


def matrix_sha256(matrix_document: dict[str, Any]) -> str:
    """The digest pinned by this matrix document (must equal its own pin)."""
    return frozen_matrix_digest(matrix_document)


def assert_single_variable_matrix(matrix_document: dict[str, Any]) -> None:
    """Machine check: within each pair the arms differ only in profile."""
    runs = matrix_document.get("runs")
    if not isinstance(runs, list):
        fail("INVALID_SCHEMA", "The matrix lacks its runs array")
    by_pair: dict[int, list[dict[str, Any]]] = {}
    for run in runs:
        if not isinstance(run, dict):
            fail("INVALID_SCHEMA", "The matrix run must be an object")
        pair_index = run.get("pair_index")
        if not isinstance(pair_index, int):
            fail("INVALID_SCHEMA", "The matrix run lacks its pair_index")
        by_pair.setdefault(pair_index, []).append(run)
    comparable_fields = (
        "case_id",
        "cluster",
        "corpus",
        "max_num_generations",
        "max_tokens",
        "model_id",
        "num_reflections",
        "reasoning_effort",
        "workshop",
        "retriever_policy_version",
        "rubric_version",
        "runtime_controls",
    )
    for pair_index, arm_runs in sorted(by_pair.items()):
        if len(arm_runs) != 2:
            fail(
                "INVALID_SCHEMA",
                "Each pair must hold exactly two arms",
                pair_index=pair_index,
            )
        first, second = arm_runs
        for field in comparable_fields:
            if first.get(field) != second.get(field):
                fail(
                    "ARM_SPECIFICATION_DRIFT",
                    "The pair arms differ beyond the Prompt Profile",
                    pair_index=pair_index,
                    field=field,
                )
        if first.get("prompt_profile_id") == second.get("prompt_profile_id"):
            fail(
                "ARM_PROFILE_COLLAPSE",
                "The pair arms must differ exactly in the Prompt Profile",
                pair_index=pair_index,
            )


# ==========================================================================
# Frozen blind mapping and blind pair packets
# ==========================================================================


@dataclass(frozen=True, slots=True)
class BlindPairMapping:
    """The frozen, write-once A/B identity of one pair (secret until reveal)."""

    pair_index: int
    case_id: str
    cluster: str
    arm_a_profile_id: str
    arm_b_profile_id: str


def build_blind_mapping(
    pairs: tuple[ComparisonPair, ...],
    *,
    selection_manifest: dict[str, Any],
) -> tuple[BlindPairMapping, ...]:
    """Freeze exactly 2 pairs where A=baseline and 2 where A=challenger.

    The assignment is keyed on `sha256(seed|blind_mapping|case_id)` parity
    and deterministically rebalanced by canonical case hash when the parity
    split is not exactly 2/2. The mapping is serialized separately from the
    matrix so the blind packet builder never needs to see it.
    """
    seed = comparison_selection_seed(selection_manifest)
    a_is_baseline, a_is_challenger = _balanced_partition(
        list(pairs),
        digest_of=lambda pair: _canonical_seed_hex(
            "blind_mapping", f"{seed}|{pair.case_id}"
        ),
        key_of=lambda pair: (pair.case_id,),
        need=len(pairs) // 2,
    )
    need = len(pairs) // 2
    mappings: list[BlindPairMapping] = []
    for pair in sorted(pairs, key=lambda p: p.pair_index):
        arm_a_is_baseline = pair in a_is_baseline
        if arm_a_is_baseline:
            arm_a = BASELINE_PROFILE_ID
            arm_b = CHALLENGER_PROFILE_ID
        else:
            arm_a = CHALLENGER_PROFILE_ID
            arm_b = BASELINE_PROFILE_ID
        mappings.append(
            BlindPairMapping(
                pair_index=pair.pair_index,
                case_id=pair.case_id,
                cluster=pair.cluster,
                arm_a_profile_id=arm_a,
                arm_b_profile_id=arm_b,
            )
        )
    a_baseline_count = sum(
        1 for m in mappings if m.arm_a_profile_id == BASELINE_PROFILE_ID
    )
    a_challenger_count = sum(
        1 for m in mappings if m.arm_a_profile_id == CHALLENGER_PROFILE_ID
    )
    if a_baseline_count != need or a_challenger_count != need:
        fail(
            "BLIND_BALANCE_FAILED",
            "The blind mapping must hold exactly 2 pairs per A-side identity",
            a_is_baseline=a_baseline_count,
            a_is_challenger=a_challenger_count,
        )
    return tuple(mappings)


def blind_mapping_document(
    mappings: tuple[BlindPairMapping, ...],
    *,
    selection_manifest: dict[str, Any],
) -> dict[str, Any]:
    """The frozen mapping document; its bytes stay sealed until reveal."""
    document = {
        "arm_a_is_baseline_count": sum(
            1 for m in mappings if m.arm_a_profile_id == BASELINE_PROFILE_ID
        ),
        "arm_a_is_challenger_count": sum(
            1 for m in mappings if m.arm_a_profile_id == CHALLENGER_PROFILE_ID
        ),
        "matrix_seed_sha256": comparison_selection_seed(selection_manifest),
        "pairs": [
            {
                "arm_a_profile_id": mapping.arm_a_profile_id,
                "arm_b_profile_id": mapping.arm_b_profile_id,
                "case_id": mapping.case_id,
                "cluster": mapping.cluster,
                "pair_index": mapping.pair_index,
            }
            for mapping in sorted(mappings, key=lambda m: m.pair_index)
        ],
        "pairs_count": len(mappings),
        "schema_version": BLIND_MAPPING_SCHEMA_VERSION,
    }
    return document


def blind_mapping_sha256(document: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(document))


def assert_blind_mapping_document_shape(
    document: dict[str, Any],
) -> tuple[BlindPairMapping, ...]:
    """Re-parse the frozen mapping document into typed pairs, fail closed."""
    checked = closed_object(
        document,
        label="blind mapping",
        keys={
            "arm_a_is_baseline_count",
            "arm_a_is_challenger_count",
            "matrix_seed_sha256",
            "pairs",
            "pairs_count",
            "schema_version",
        },
    )
    if checked["schema_version"] != BLIND_MAPPING_SCHEMA_VERSION:
        fail(
            "INVALID_SCHEMA",
            "Unsupported blind mapping schema_version",
            schema_version=checked["schema_version"],
        )
    parse_sha256(
        checked["matrix_seed_sha256"], label="blind mapping matrix_seed_sha256"
    )
    if not isinstance(checked["pairs"], list) or not checked["pairs"]:
        fail("INVALID_SCHEMA", "The blind mapping must carry its pairs")
    mappings: list[BlindPairMapping] = []
    for index, entry in enumerate(checked["pairs"]):
        pair = closed_object(
            entry,
            label=f"blind mapping.pairs[{index}]",
            keys={
                "arm_a_profile_id",
                "arm_b_profile_id",
                "case_id",
                "cluster",
                "pair_index",
            },
        )
        parse_case_id(pair["case_id"])
        if pair["arm_a_profile_id"] not in (BASELINE_PROFILE_ID, CHALLENGER_PROFILE_ID):
            fail(
                "INVALID_SCHEMA",
                "The blind mapping carries an unregistered profile id",
                pair_index=pair["pair_index"],
            )
        if pair["arm_b_profile_id"] not in (BASELINE_PROFILE_ID, CHALLENGER_PROFILE_ID):
            fail(
                "INVALID_SCHEMA",
                "The blind mapping carries an unregistered profile id",
                pair_index=pair["pair_index"],
            )
        if pair["arm_a_profile_id"] == pair["arm_b_profile_id"]:
            fail(
                "INVALID_SCHEMA",
                "The blind mapping collapsed a pair onto one profile",
                pair_index=pair["pair_index"],
            )
        mappings.append(
            BlindPairMapping(
                pair_index=pair["pair_index"],
                case_id=pair["case_id"],
                cluster=pair["cluster"],
                arm_a_profile_id=pair["arm_a_profile_id"],
                arm_b_profile_id=pair["arm_b_profile_id"],
            )
        )
    a_baseline = sum(1 for m in mappings if m.arm_a_profile_id == BASELINE_PROFILE_ID)
    a_challenger = sum(
        1 for m in mappings if m.arm_a_profile_id == CHALLENGER_PROFILE_ID
    )
    if (
        a_baseline != checked["arm_a_is_baseline_count"]
        or a_challenger != checked["arm_a_is_challenger_count"]
        or a_baseline != len(COMPARISON_CLUSTERS) // 2
        or a_challenger != len(COMPARISON_CLUSTERS) // 2
    ):
        fail(
            "BLIND_BALANCE_FAILED",
            "The blind mapping document does not preserve its 2/2 balance",
            arm_a_is_baseline_count=a_baseline,
            arm_a_is_challenger_count=a_challenger,
        )
    return tuple(mappings)


def build_pair_packet(
    pair_index: int,
    case_id: str,
    cluster: str,
    idea_a: dict[str, Any],
    idea_b: dict[str, Any],
    *,
    selection_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Build the blinded Robert-facing packet for one pair.

    The packet contains only the case-identity and the two anonymized idea
    payloads (A/B); each arm also carries the SHA-256 of its canonical idea
    bytes (`idea_sha256`, computed inside from the supplied payload), so a
    packet arm can be audited against the sealed run it was built from.
    The structure scan walks the serialized packet's keys and non-idea
    values: any forbidden operational-metadata key, or a profile identity
    value appearing anywhere outside the idea payloads, fails closed.
    Model-generated idea text is never scanned — legitimate English words
    in a proposal are not blinding leaks.
    """
    parse_case_id(case_id)
    if idea_a == idea_b:
        fail("PACKET_PAYLOAD_COLLAPSE", "The two packet arms are identical")
    packet = {
        "case_id": case_id,
        "cluster": cluster,
        "matrix_seed_sha256": comparison_selection_seed(selection_manifest),
        "pair_index": pair_index,
        "schema_version": PAIR_PACKET_SCHEMA_VERSION,
        "arm_a": {"idea": idea_a, "idea_sha256": final_idea_sha256(idea_a)},
        "arm_b": {"idea": idea_b, "idea_sha256": final_idea_sha256(idea_b)},
    }
    _scan_packet_blinding(packet, idea_payloads=(idea_a, idea_b))
    return packet


def _scan_packet_blinding(
    packet: dict[str, Any], *, idea_payloads: tuple[dict[str, Any], ...]
) -> None:
    """Key-level blinding scan over the packet structure.

    Keys anywhere in the packet must avoid the forbidden metadata key set.
    String values outside the idea payloads must not equal a profile
    identity. Idea payload values are exempt (model-visible content).
    """

    def _walk(value: Any, *, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                key_lower = key.lower()
                if key_lower in PAIR_PACKET_FORBIDDEN_KEYS:
                    fail(
                        "PAIR_PACKET_BLINDING_VIOLATION",
                        "The blind pair packet carries forbidden operational metadata",
                        forbidden=key,
                        path=path,
                    )
                _walk(item, path=f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _walk(item, path=f"{path}[{index}]")
        elif isinstance(value, str):
            if value in PAIR_PACKET_FORBIDDEN_IDENTITY_VALUES:
                fail(
                    "PAIR_PACKET_BLINDING_VIOLATION",
                    "The blind packet carries a profile identity value",
                    path=path,
                )

    def _strip_ideas(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: _strip_ideas(item)
                for key, item in value.items()
                if key not in ("arm_a", "arm_b")
            }
        if isinstance(value, list):
            return [_strip_ideas(item) for item in value]
        return value

    _walk(_strip_ideas(packet), path="packet")
    for index, idea in enumerate(idea_payloads):
        if isinstance(idea, dict):
            for key in idea:
                if key.lower() in PAIR_PACKET_FORBIDDEN_KEYS:
                    fail(
                        "PAIR_PACKET_BLINDING_VIOLATION",
                        "The blind packet idea payload carries a forbidden key",
                        forbidden=key,
                    )


def pair_packet_sha256(packet: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(packet))


def load_sealed_final_idea(workspace_root: Path, run_id: str) -> dict[str, Any]:
    """Load the sealed run's finalized idea payload from its own evidence.

    The finalized idea lives at `artifacts/ideas/<idea_index:06d>/idea.json`
    inside the run root. A comparison run finalizes exactly one idea, so a
    run with zero or multiple finalized ideas is corrupt. The parsed
    payload must carry exactly the seven IDEA JSON fields of the sealed
    contract (controller.REQUIRED_IDEA_FIELDS / profiles.py IDEA JSON);
    missing or extra keys mean the artifact was tampered and fail closed
    as RUN_CORRUPT.
    """
    workspace = workspace_root.resolve(strict=True)
    store = RunStore(workspace)
    idea_rel_paths: list[str] = []
    idea_dir = store.runs_root / run_id / "artifacts" / "ideas"
    if idea_dir.is_dir():
        for candidate in sorted(idea_dir.iterdir()):
            idea_rel = f"artifacts/ideas/{candidate.name}/idea.json"
            try:
                store.read_artifact(run_id, idea_rel, label="finalized idea payload")
            except IdeationInputError:
                continue
            idea_rel_paths.append(idea_rel)
    if len(idea_rel_paths) != 1:
        fail(
            "RUN_CORRUPT",
            "The sealed run must hold exactly one finalized idea",
            run_id=run_id,
            finalized_idea_count=len(idea_rel_paths),
        )
    idea_bytes = store.read_artifact(run_id, idea_rel_paths[0])
    idea = parse_json_bytes(idea_bytes, label="idea.json")
    if not isinstance(idea, dict):
        fail("RUN_CORRUPT", "idea.json is not a JSON object")
    if set(idea) != SEALED_IDEA_REQUIRED_FIELDS:
        fail(
            "RUN_CORRUPT",
            "idea.json drifted from the seven-field IDEA JSON contract",
            run_id=run_id,
            missing=sorted(SEALED_IDEA_REQUIRED_FIELDS - set(idea)),
            extra=sorted(set(idea) - SEALED_IDEA_REQUIRED_FIELDS),
        )
    return idea


def final_idea_sha256(idea: dict[str, Any]) -> str:
    """The canonical digest of one finalized idea payload."""
    return sha256_bytes(canonical_json_bytes(idea))


def build_pair_packets_from_ingested(
    workspace_root: Path,
    *,
    matrix_document: dict[str, Any],
    selection_manifest: dict[str, Any],
    mappings: tuple[BlindPairMapping, ...],
    metrics_by_run: Mapping[str, RunMetrics],
) -> dict[int, dict[str, Any]]:
    """Build every pair packet from the ingested sealed runs.

    This is the ONLY sanctioned way to build live packets: for each pair
    the two arms' RunMetrics are located through `metrics_by_run` by the
    matrix entry's prompt profile id (missing either arm fails closed as
    COMPARISON_IDENTITY_MISMATCH), both idea payloads are loaded from the
    sealed runs' own idea.json artifacts, and the A/B assignment follows
    the frozen blind mapping exactly (`_mapping_for_case`), so the packet
    bytes bind the blinded structure to the sealed evidence at build time.
    """
    runs_by_pair: dict[int, list[dict[str, Any]]] = {}
    for entry in matrix_document["runs"]:
        runs_by_pair.setdefault(entry["pair_index"], []).append(entry)
    by_pair_and_profile: dict[tuple[int, str], tuple[str, RunMetrics]] = {}
    for run_id, metrics in metrics_by_run.items():
        by_pair_and_profile[(metrics.pair_index, metrics.profile_id)] = (
            run_id,
            metrics,
        )
    packets: dict[int, dict[str, Any]] = {}
    for pair_index, arm_runs in sorted(runs_by_pair.items()):
        if len(arm_runs) != 2:
            fail(
                "COMPARISON_IDENTITY_MISMATCH",
                "The matrix pair does not hold exactly two arms",
                pair_index=pair_index,
            )
        case_ids = {entry["case_id"] for entry in arm_runs}
        if len(case_ids) != 1:
            fail(
                "COMPARISON_IDENTITY_MISMATCH",
                "The matrix pair arms disagree on the case id",
                pair_index=pair_index,
            )
        case_id = next(iter(case_ids))
        baseline = by_pair_and_profile.get((pair_index, BASELINE_PROFILE_ID))
        challenger = by_pair_and_profile.get((pair_index, CHALLENGER_PROFILE_ID))
        if baseline is None or challenger is None:
            fail(
                "COMPARISON_IDENTITY_MISMATCH",
                "The pair lacks one of its ingested arm metrics",
                pair_index=pair_index,
                missing_baseline=baseline is None,
                missing_challenger=challenger is None,
            )
        baseline_run_id, _baseline_metrics = baseline
        challenger_run_id, _challenger_metrics = challenger
        mapping = _mapping_for_case(mappings, case_id)
        if mapping.arm_a_profile_id == BASELINE_PROFILE_ID:
            idea_a = load_sealed_final_idea(workspace_root, baseline_run_id)
            idea_b = load_sealed_final_idea(workspace_root, challenger_run_id)
        else:
            idea_a = load_sealed_final_idea(workspace_root, challenger_run_id)
            idea_b = load_sealed_final_idea(workspace_root, baseline_run_id)
        packets[pair_index] = build_pair_packet(
            pair_index,
            case_id,
            mapping.cluster,
            idea_a,
            idea_b,
            selection_manifest=selection_manifest,
        )
    return packets


# ==========================================================================
# Credential-free exact commands (production parser surface only)
# ==========================================================================

CREDENTIAL_WRAPPER = "scripts/with-project-env"
ENTRY_SCRIPT = "ai_scientist/perform_ideation_temp_free.py"


def build_comparison_commands(
    runs: tuple[ComparisonRun, ...],
    *,
    matrix_document: dict[str, Any],
    package_dir: Path = DEFAULT_COMPARISON_PACKAGE_DIR,
    plan_gate_reapproval_threshold_cny: Decimal = (
        DEFAULT_PROMPT_COMPARISON_REAPPROVAL_THRESHOLD_CNY
    ),
) -> tuple[str, ...]:
    """Exact credential-free guarded commands, one per planned run.

    The project credential wrapper launches the comparison slot guard. The
    guard validates the mutable ledger, reserves the next run's peak-price
    worst-case bound against the 30 CNY hard cap, enforces sequential slots,
    and immediately execs the production `new-run` command. No credential,
    automatic approval, or free-form provider control enters the command.
    """
    commands: list[str] = []
    matrix_file_sha256 = sha256_bytes(canonical_json_bytes(matrix_document))
    threshold = _quantize_cny(plan_gate_reapproval_threshold_cny)
    for run_index in range(1, len(runs) + 1):
        parts = [
            "python",
            CREDENTIAL_WRAPPER,
            "--",
            "python",
            SLOT_RUNNER,
            "--package-dir",
            str(package_dir),
            "--matrix-sha256",
            matrix_file_sha256,
            "--reapproval-threshold-cny",
            str(threshold),
            "--run-index",
            str(run_index),
        ]
        command = " ".join(shlex_quote(part) for part in parts)
        commands.append(command)
    for run_index, command in enumerate(commands, start=1):
        _assert_command_contract(
            command,
            matrix_document=matrix_document,
            expected_run_index=run_index,
            expected_package_dir=package_dir,
            expected_reapproval_threshold_cny=threshold,
        )
    return tuple(commands)


def _production_new_run_argv(matrix_run: dict[str, Any]) -> tuple[str, ...]:
    """Build and parser-check the immutable production command for one slot."""
    parts = (
        "python",
        ENTRY_SCRIPT,
        "new-run",
        "--case-id",
        matrix_run["case_id"],
        "--workshop",
        matrix_run["workshop"]["path"],
        "--workshop-sha256",
        matrix_run["workshop"]["sha256"],
        "--corpus",
        matrix_run["corpus"]["path"],
        "--corpus-sha256",
        matrix_run["corpus"]["sha256"],
        "--max-num-generations",
        str(matrix_run["max_num_generations"]),
        "--num-reflections",
        str(matrix_run["num_reflections"]),
        "--prompt-profile",
        matrix_run["prompt_profile_id"],
    )
    _parse_production_new_run_argv(parts)
    return parts


def _matrix_run_entry(
    matrix_document: dict[str, Any], run_index: int
) -> dict[str, Any]:
    for entry in matrix_document["runs"]:
        if entry["run_index"] == run_index:
            return entry
    fail("INVALID_SCHEMA", "The matrix lacks the planned run", run_index=run_index)


def shlex_quote(part: str) -> str:
    """Delegate to the stdlib quoter: any shell-metaphor byte (including
    `|`) must land quoted in a frozen command, never as a pipe operator."""
    return shlex.quote(part)


def _parse_production_new_run_argv(tokens: tuple[str, ...]) -> None:
    """Fail closed unless argv is accepted by the production parser."""
    from ai_scientist.perform_ideation_temp_free import _build_parser

    if tokens[:2] != ("python", ENTRY_SCRIPT):
        fail(
            "COMMAND_SHAPE_INVALID", "The command does not invoke the production entry"
        )
    parser = _build_parser()
    try:
        parsed = parser.parse_args(list(tokens[2:]))
    except SystemExit:
        fail(
            "COMMAND_NOT_PARSER_SUPPORTED",
            "A frozen command carries arguments the production parser rejects",
        )
    if parsed.entry != "new-run":
        fail("COMMAND_SHAPE_INVALID", "The command must be a new-run invocation")


def _assert_command_contract(
    command: str,
    *,
    matrix_document: dict[str, Any],
    expected_run_index: int,
    expected_package_dir: Path,
    expected_reapproval_threshold_cny: Decimal,
) -> None:
    """Fail closed unless the outer guard and inner production argv agree."""
    tokens = shlex.split(command)
    expected_tokens = [
        "python",
        CREDENTIAL_WRAPPER,
        "--",
        "python",
        SLOT_RUNNER,
        "--package-dir",
        str(expected_package_dir),
        "--matrix-sha256",
        sha256_bytes(canonical_json_bytes(matrix_document)),
        "--reapproval-threshold-cny",
        str(_quantize_cny(expected_reapproval_threshold_cny)),
        "--run-index",
        str(expected_run_index),
    ]
    if tokens != expected_tokens:
        fail(
            "COMMAND_SHAPE_INVALID",
            "The frozen command must use the exact guarded slot runner shape",
        )
    _production_new_run_argv(_matrix_run_entry(matrix_document, expected_run_index))
    forbidden_tokens = (
        "--reasoning-effort",
        "--max-tokens",
        "--model",
        "--provider",
        "--base-url",
        "--temperature",
        "--system-prompt",
        "--prompt-path",
        "--prompt-text",
        "yes",
        "DEEPSEEK_API_KEY",
        "sk-",
        "export ",
        "API_KEY",
    )
    for forbidden in forbidden_tokens:
        if forbidden in command:
            fail(
                "COMMAND_FORBIDDEN_ARGUMENT",
                "The frozen command carries a forbidden token",
                forbidden=forbidden,
            )


def commands_document(commands: tuple[str, ...]) -> dict[str, Any]:
    """Deterministic sanitized commands block (schema + shape only)."""
    return {
        "commands": list(commands),
        "count": len(commands),
        "credential_wrapper": CREDENTIAL_WRAPPER,
        "entry_script": ENTRY_SCRIPT,
        "schema_version": "comparison-commands-v1.2.0",
        "slot_runner": SLOT_RUNNER,
    }


# ==========================================================================
# Append-only spend ledger with Plan Gate arithmetic
# ==========================================================================


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One immutable per-run actual-cost ingest record.

    `worst_case_bound_cny` is recorded as admission-approval audit
    metadata only (the live per-run 7.08 CNY worst-case bound belongs to
    the admission approval seam); it takes part in no ledger arithmetic.
    """

    run_index: int
    pair_index: int
    case_id: str
    profile_id: str
    run_id: str
    status: str
    actual_cost_cny: Decimal
    worst_case_bound_cny: Decimal
    physical_attempt_count: int


@dataclass(frozen=True, slots=True)
class ForfeitedLedgerEntry:
    """One quarantined zero-idea run's actual-cost record.

    Forfeited entries live in their own ledger list: the sequential slot
    invariant and per-slot result identity of `entries` stay intact, while
    the spent money still counts toward the hard cap and the reapproval
    threshold (spent money cannot launder budget).
    """

    run_index: int
    run_id: str
    actual_cost_cny: Decimal
    worst_case_bound_cny: Decimal
    physical_attempt_count: int
    reason: str


def initialize_comparison_ledger(
    *,
    matrix_document: dict[str, Any],
    plan_gate_reapproval_threshold_cny: Decimal,
    historical_spend_cny: Decimal,
) -> dict[str, Any]:
    """Start the append-only ledger over the recorded historical balance.

    The ledger's opening balance is the immutable historical Canary-stage
    spend (the documented 0.14 CNY live smoke, Proposal 002); the tracked
    comparison actual spend starts at 0.00 CNY, and the total stage spend
    (historical + tracked + forfeited) is kept current on every ingest.
    """
    threshold = plan_gate_reapproval_threshold_cny
    if not isinstance(threshold, Decimal) or threshold <= 0:
        fail(
            "INVALID_REAPPROVAL_THRESHOLD",
            "The Plan Gate reapproval threshold must be a positive decimal",
        )
    if threshold > CANARY_HARD_CAP_CNY:
        fail(
            "REAPPROVAL_THRESHOLD_EXCEEDS_CANARY_CAP",
            "The reapproval threshold cannot exceed the 30.00 CNY Canary hard cap",
            threshold=str(threshold),
            canary_cap=str(CANARY_HARD_CAP_CNY),
        )
    if not isinstance(historical_spend_cny, Decimal) or historical_spend_cny < 0:
        fail(
            "INVALID_HISTORICAL_SPEND",
            "The historical Canary-stage spend must be a non-negative decimal",
        )
    historical = _quantize_cny(historical_spend_cny)
    return {
        "canary_hard_cap_cny": str(CANARY_HARD_CAP_CNY),
        "comparison_actual_spend_cny": str(LEDGER_INIT_SPEND_CNY),
        "entries": [],
        "forfeited_entries": [],
        "forfeited_spend_cny": str(LEDGER_INIT_SPEND_CNY),
        "historical_spend_cny": str(historical),
        "matrix_sha256": matrix_sha256(matrix_document),
        "plan_gate_reapproval_threshold_cny": str(threshold),
        "planned_runs_count": matrix_document["planned_runs_count"],
        "schema_version": SPEND_LEDGER_SCHEMA_VERSION,
        "status": "initialized",
        "total_stage_spend_cny": str(historical),
    }


def ledger_current_spend(ledger: dict[str, Any]) -> Decimal:
    """The tracked comparison actual spend (the sum of ingested entries)."""
    return _money(
        ledger.get("comparison_actual_spend_cny"),
        label="comparison_actual_spend_cny",
    )


def ledger_total_stage_spend(ledger: dict[str, Any]) -> Decimal:
    """The total stage spend: historical opening balance + tracked spend."""
    return _money(ledger.get("total_stage_spend_cny"), label="total_stage_spend_cny")


def _ledger_entry_cost(entry: dict[str, Any]) -> Decimal:
    return _money(entry["actual_cost_cny"], label="ledger entry actual_cost_cny")


def _validate_ledger_arithmetic(
    ledger: dict[str, Any], *, matrix_document: dict[str, Any]
) -> tuple[Decimal, Decimal]:
    """Recompute every mutable money field and sequential slot identity."""
    if ledger.get("schema_version") != SPEND_LEDGER_SCHEMA_VERSION:
        fail("LEDGER_SCHEMA_DRIFT", "The comparison spend ledger schema drifted")
    if ledger.get("matrix_sha256") != matrix_document.get("matrix_sha256"):
        fail("MATRIX_PIN_DRIFT", "The spend ledger belongs to another matrix")
    if matrix_document.get("matrix_sha256") != frozen_matrix_digest(matrix_document):
        fail("MATRIX_PIN_DRIFT", "The frozen matrix digest no longer verifies")
    if ledger.get("planned_runs_count") != matrix_document.get("planned_runs_count"):
        fail("LEDGER_SCHEMA_DRIFT", "The ledger planned-run count drifted")
    if ledger.get("canary_hard_cap_cny") != str(CANARY_HARD_CAP_CNY):
        fail("LEDGER_SCHEMA_DRIFT", "The ledger Canary hard cap drifted")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        fail("LEDGER_SCHEMA_DRIFT", "The ledger entries field must be an array")
    expected_indexes = list(range(1, len(entries) + 1))
    normalized_entries: list[dict[str, Any]] = []
    for index, value in enumerate(entries):
        normalized_entries.append(
            closed_object(
                value,
                label=f"ledger.entries[{index}]",
                keys={
                    "actual_cost_cny",
                    "case_id",
                    "pair_index",
                    "physical_attempt_count",
                    "profile_id",
                    "run_id",
                    "run_index",
                    "status",
                    "worst_case_bound_cny",
                },
            )
        )
    observed_indexes = [entry.get("run_index") for entry in normalized_entries]
    if observed_indexes != expected_indexes:
        fail("LEDGER_SLOT_DRIFT", "Ledger entries must follow frozen run order")
    if len({entry.get("run_id") for entry in normalized_entries}) != len(
        normalized_entries
    ):
        fail("LEDGER_SLOT_DRIFT", "Ledger run ids must be unique")
    for entry in normalized_entries:
        matrix_run = _matrix_run_entry(matrix_document, entry["run_index"])
        if (
            entry.get("case_id") != matrix_run["case_id"]
            or entry.get("pair_index") != matrix_run["pair_index"]
            or entry.get("profile_id") != matrix_run["prompt_profile_id"]
        ):
            fail("LEDGER_SLOT_DRIFT", "A ledger entry drifted from its matrix slot")
    # Forfeited entries (quarantined zero-idea runs) form their own list with
    # their own closed shape; run ids stay unique across both lists and a run
    # index may appear at most once per list.
    forfeited_entries = ledger.get("forfeited_entries")
    if not isinstance(forfeited_entries, list):
        fail("LEDGER_SCHEMA_DRIFT", "The forfeited entries field must be an array")
    normalized_forfeited: list[dict[str, Any]] = []
    for index, value in enumerate(forfeited_entries):
        normalized_forfeited.append(
            closed_object(
                value,
                label=f"ledger.forfeited_entries[{index}]",
                keys={
                    "actual_cost_cny",
                    "physical_attempt_count",
                    "reason",
                    "run_id",
                    "run_index",
                    "worst_case_bound_cny",
                },
            )
        )
        if normalized_forfeited[-1]["reason"] != QUARANTINE_REASON_ZERO_FINALIZED_IDEA:
            fail("LEDGER_SCHEMA_DRIFT", "A forfeited entry carries an unknown reason")
        run_index = normalized_forfeited[-1]["run_index"]
        if (
            not isinstance(run_index, int)
            or isinstance(run_index, bool)
            or not 1 <= run_index <= matrix_document["planned_runs_count"]
        ):
            fail("LEDGER_SLOT_DRIFT", "A forfeited entry names no frozen matrix slot")
    ingested_run_ids = {entry.get("run_id") for entry in normalized_entries}
    forfeited_run_ids = {entry.get("run_id") for entry in normalized_forfeited}
    if len(ingested_run_ids | forfeited_run_ids) != len(ingested_run_ids) + len(
        forfeited_run_ids
    ):
        fail("LEDGER_SLOT_DRIFT", "Run ids must be unique across entry lists")
    historical = _money(
        ledger.get("historical_spend_cny"), label="historical_spend_cny"
    )
    if historical != CANARY_STAGE_HISTORICAL_SPEND_CNY:
        fail(
            "LEDGER_OPENING_BALANCE_DRIFT",
            "The historical Canary-stage opening balance drifted",
        )
    tracked = sum(
        (_ledger_entry_cost(entry) for entry in normalized_entries), Decimal("0.00")
    )
    tracked = _quantize_cny(tracked)
    forfeited = sum(
        (
            _money(entry["actual_cost_cny"], label="forfeited actual_cost_cny")
            for entry in normalized_forfeited
        ),
        Decimal("0.00"),
    )
    forfeited = _quantize_cny(forfeited)
    total = _quantize_cny(historical + tracked + forfeited)
    if (
        ledger_current_spend(ledger) != tracked
        or ledger_total_stage_spend(ledger) != total
        or _money(ledger.get("forfeited_spend_cny"), label="forfeited_spend_cny")
        != forfeited
    ):
        fail("LEDGER_ARITHMETIC_DRIFT", "The spend ledger totals do not recompute")
    threshold = _money(
        ledger.get("plan_gate_reapproval_threshold_cny"),
        label="plan_gate_reapproval_threshold_cny",
    )
    if threshold <= 0 or threshold > CANARY_HARD_CAP_CNY:
        fail("LEDGER_SCHEMA_DRIFT", "The reapproval threshold is outside its bounds")
    expected_status = (
        "hard_cap_breached"
        if total > CANARY_HARD_CAP_CNY
        else (
            "reapproval_required"
            if total >= threshold
            else "ingesting" if entries or normalized_forfeited else "initialized"
        )
    )
    if ledger.get("status") != expected_status:
        fail("LEDGER_STATUS_DRIFT", "The ledger status disagrees with its totals")
    if entries and ledger.get("ingested_runs_count") != len(entries):
        fail("LEDGER_SCHEMA_DRIFT", "The ledger ingested-run count drifted")
    return total, threshold


def authorize_next_comparison_run(
    ledger: dict[str, Any],
    *,
    matrix_document: dict[str, Any],
    run_index: int,
    next_run_worst_case_bound_cny: Decimal,
) -> dict[str, Any]:
    """Authorize one sequential slot before any irreversible provider request.

    The 5 CNY Plan Gate control is an observed-spend reapproval threshold:
    crossing it on an already individually approved run is recorded, then
    blocks the next slot. The 30 CNY Canary cap is the true hard cap and
    reserves the next run's peak-price worst-case bound before launch.
    """
    total, threshold = _validate_ledger_arithmetic(
        ledger, matrix_document=matrix_document
    )
    entries = ledger["entries"]
    expected_run_index = len(entries) + 1
    if run_index != expected_run_index:
        fail(
            "PREVIOUS_SLOT_NOT_INGESTED",
            "Only the next sequential matrix slot may be launched",
            expected_run_index=expected_run_index,
            requested_run_index=run_index,
        )
    if run_index > matrix_document["planned_runs_count"]:
        fail("MATRIX_COMPLETE", "Every frozen comparison run is already ingested")
    if total > CANARY_HARD_CAP_CNY:
        fail(
            "CANARY_HARD_CAP_BREACHED",
            "Recorded stage spend already exceeds the Canary hard cap",
        )
    if total >= threshold:
        fail(
            "PLAN_GATE_REAPPROVAL_REQUIRED",
            "Observed stage spend reached the Plan Gate reapproval threshold",
            current=str(total),
            threshold=str(threshold),
        )
    bound = next_run_worst_case_bound_cny
    if not isinstance(bound, Decimal) or bound <= 0:
        fail("INVALID_BUDGET", "The next-run worst-case bound must be positive")
    projected = _quantize_cny(total + bound)
    if projected > CANARY_HARD_CAP_CNY:
        fail(
            "CANARY_HARD_CAP_RESERVATION_FAILED",
            "The next run's worst-case bound does not fit the Canary hard cap",
            current=str(total),
            next_run_worst_case_bound_cny=str(bound),
            projected_hard_ceiling_cny=str(projected),
            canary_hard_cap_cny=str(CANARY_HARD_CAP_CNY),
        )
    return {
        "canary_hard_cap_cny": str(CANARY_HARD_CAP_CNY),
        "current_total_stage_spend_cny": str(total),
        "matrix_sha256": matrix_document["matrix_sha256"],
        "next_run_worst_case_bound_cny": str(_quantize_cny(bound)),
        "plan_gate_reapproval_threshold_cny": str(threshold),
        "projected_hard_ceiling_cny": str(projected),
        "run_index": run_index,
        "schema_version": "comparison-run-authorization-v1.0.0",
    }


def _is_full_git_sha(value: object) -> bool:
    return isinstance(value, str) and _GIT_COMMIT_PATTERN.fullmatch(value) is not None


def execution_code_pin_path(package_dir: Path) -> Path:
    return Path(package_dir) / EXECUTION_CODE_PIN_NAME


def create_execution_code_pin(package_dir: Path, *, commit: str) -> dict[str, Any]:
    """Exclusive-create the write-once execution-code pin (first slot only).

    The pin records the clean Git HEAD the whole 8-run matrix must execute
    under, keeping Prompt Profile the only differing execution control. It is
    never deleted silently: a stale pin is evidence and must be reconciled
    against the Evidence Chain before any new-epoch decision.
    """
    if not _is_full_git_sha(commit):
        fail("INVALID_SCHEMA", "The execution code commit must be a full Git SHA")
    document = {
        "commit": commit,
        "pinned_at": _now(),
        "schema_version": EXECUTION_CODE_PIN_SCHEMA_VERSION,
    }
    path = execution_code_pin_path(package_dir)
    digest = _write_bytes_once(
        path,
        canonical_json_bytes(document),
        label="execution code pin",
        exists_code="EXECUTION_CODE_PIN_EXISTS",
    )
    return {
        "document": document,
        "path": str(path),
        "sha256": digest,
    }


def load_execution_code_pin(package_dir: Path) -> dict[str, Any]:
    """Read and validate the execution-code pin; absence fails closed."""
    path = execution_code_pin_path(package_dir)
    if path.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The execution code pin is a symlink")
    if not path.is_file():
        fail(
            "EXECUTION_CODE_PIN_MISSING",
            "The comparison package lacks its execution code pin",
        )
    document = parse_json_bytes(path.read_bytes(), label="execution code pin")
    if not isinstance(document, dict):
        fail("INVALID_SCHEMA", "The execution code pin is not a JSON object")
    pin = closed_object(
        document,
        label="execution code pin",
        keys={"commit", "pinned_at", "schema_version"},
    )
    if pin["schema_version"] != EXECUTION_CODE_PIN_SCHEMA_VERSION:
        fail("EXECUTION_CODE_PIN_DRIFT", "The execution code pin schema drifted")
    nonempty_string(pin["pinned_at"], label="execution code pin pinned_at")
    if not _is_full_git_sha(pin["commit"]):
        fail(
            "EXECUTION_CODE_PIN_DRIFT",
            "The execution code pin commit is not a full Git SHA",
        )
    return pin


def _pin_supersede_records(package_dir: Path) -> list[dict[str, Any]]:
    """All pin supersede records, ordered by their sequence suffix."""
    records: list[tuple[int, Path, dict[str, Any]]] = []
    for path in Path(package_dir).glob("pin-supersede-record*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        match = re.fullmatch(r"pin-supersede-record(?:-seq-(\d+))?\.json", path.name)
        if match is None:
            continue
        seq = int(match.group(1)) if match.group(1) is not None else 1
        document = parse_json_bytes(path.read_bytes(), label="pin supersede record")
        if not isinstance(document, dict):
            fail("INVALID_SCHEMA", "The pin supersede record is not a JSON object")
        records.append((seq, path, document))
    return [document for _seq, _path, document in sorted(records, key=lambda r: r[0])]


def superseded_execution_code_commits(package_dir: Path) -> set[str]:
    """Historic pin commits recorded by governed supersede records."""
    return {
        record["old_commit"]
        for record in _pin_supersede_records(package_dir)
        if isinstance(record.get("old_commit"), str)
    }


def supersede_execution_code_pin(
    package_dir: Path,
    *,
    new_commit: str,
    reason: str,
) -> dict[str, Any]:
    """Governed execution-code re-pin (Design-Epoch change, Robert approved).

    The old pin bytes are archived verbatim under `superseded/` (evidence is
    never deleted), a write-once supersede record links the old and new
    commits, and the new pin is exclusive-created. Old-epoch sealed runs keep
    failing ingestion after a supersede: quarantine is their only exit.
    """
    package = Path(package_dir)
    if not _is_full_git_sha(new_commit):
        fail("INVALID_SCHEMA", "The superseded-to commit must be a full Git SHA")
    reason = nonempty_string(reason, label="supersede reason")
    existing_pin = load_execution_code_pin(package)
    old_commit = existing_pin["commit"]
    if old_commit == new_commit:
        fail(
            "PIN_SUPERSEDE_SAME_COMMIT",
            "The execution code pin already carries this commit",
            commit=new_commit,
        )
    existing_records = _pin_supersede_records(package)
    seq = len(existing_records) + 1
    record_path = package / (
        "pin-supersede-record.json"
        if seq == 1
        else f"pin-supersede-record-seq-{seq}.json"
    )
    archive_dir = package / "superseded"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"execution-code-pin-{old_commit}.json"
    old_bytes = execution_code_pin_path(package).read_bytes()
    old_sha = sha256_bytes(old_bytes)
    _write_bytes_once(
        archive_path,
        old_bytes,
        label="archived execution code pin",
        exists_code="EXECUTION_CODE_PIN_ARCHIVE_EXISTS",
    )
    record_document = {
        "new_commit": new_commit,
        "old_commit": old_commit,
        "reason": reason,
        "schema_version": PIN_SUPERSEDE_SCHEMA_VERSION,
        "superseded_at": _now(),
    }
    record_sha = _write_bytes_once(
        record_path,
        canonical_json_bytes(record_document),
        label="pin supersede record",
        exists_code="PIN_SUPERSEDE_RECORD_EXISTS",
    )
    execution_code_pin_path(package).unlink()
    create_execution_code_pin(package, commit=new_commit)
    return {
        "new_pin": load_execution_code_pin(package),
        "old_sha256": old_sha,
        "record_document": record_document,
        "record_path": str(record_path),
        "record_sha256": record_sha,
    }


def prepare_comparison_slot_launch(
    workspace_root: Path,
    *,
    package_dir: Path,
    expected_matrix_sha256: str,
    expected_reapproval_threshold_cny: Decimal,
    run_index: int,
) -> dict[str, Any]:
    """Verify one frozen slot and return the exact production argv to exec.

    This function performs no network access and never reads credentials. The
    caller must exec the returned argv immediately so the aggregate budget
    decision and the production interactive admission remain one launch path.
    """
    if not isinstance(run_index, int) or isinstance(run_index, bool) or run_index < 1:
        fail("INVALID_RUN_INDEX", "The comparison run index must be positive")
    root = workspace_root.resolve()
    resolved_package = (
        package_dir.resolve()
        if package_dir.is_absolute()
        else (root / package_dir).resolve()
    )
    matrix_path = resolved_package / "run-matrix.json"
    ledger_path = resolved_package / "spend-ledger.json"
    if not matrix_path.is_file() or not ledger_path.is_file():
        fail(
            "COMPARISON_PACKAGE_INCOMPLETE",
            "The comparison package lacks its matrix or spend ledger",
        )
    expected_matrix_digest = parse_sha256(
        expected_matrix_sha256, label="expected_matrix_sha256"
    )
    matrix_bytes = matrix_path.read_bytes()
    observed_matrix_digest = sha256_bytes(matrix_bytes)
    if observed_matrix_digest != expected_matrix_digest:
        fail(
            "MATRIX_FILE_HASH_MISMATCH",
            "The comparison matrix bytes do not match the frozen command",
            expected=expected_matrix_digest,
            actual=observed_matrix_digest,
        )
    matrix_document = parse_json_bytes(matrix_bytes, label="comparison run matrix")
    ledger = parse_json_bytes(ledger_path.read_bytes(), label="comparison spend ledger")
    if not isinstance(matrix_document, dict) or not isinstance(ledger, dict):
        fail("INVALID_SCHEMA", "Comparison matrix and ledger must be objects")
    if matrix_document.get("schema_version") != COMPARISON_MATRIX_SCHEMA_VERSION:
        fail("MATRIX_PIN_DRIFT", "The comparison matrix schema drifted")
    if (
        not isinstance(expected_reapproval_threshold_cny, Decimal)
        or expected_reapproval_threshold_cny <= 0
        or _quantize_cny(expected_reapproval_threshold_cny)
        != expected_reapproval_threshold_cny
    ):
        fail(
            "INVALID_REAPPROVAL_THRESHOLD",
            "The frozen reapproval threshold must be a positive CNY amount",
        )
    if ledger.get("plan_gate_reapproval_threshold_cny") != str(
        expected_reapproval_threshold_cny
    ):
        fail(
            "PLAN_GATE_CONTRACT_DRIFT",
            "The ledger reapproval threshold differs from the frozen command",
        )
    assert_single_variable_matrix(matrix_document)
    matrix_run = _matrix_run_entry(matrix_document, run_index)
    if (
        matrix_run.get("model_id") != DEEPSEEK_MODEL_ID
        or matrix_run.get("reasoning_effort") != COMPARISON_REASONING_EFFORT
        or matrix_run.get("max_tokens") != COMPARISON_MAX_TOKENS
    ):
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The frozen slot's model controls drifted",
        )
    generations = matrix_run.get("max_num_generations")
    reflections = matrix_run.get("num_reflections")
    if (
        not isinstance(generations, int)
        or isinstance(generations, bool)
        or not isinstance(reflections, int)
        or isinstance(reflections, bool)
    ):
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The frozen slot's run counts drifted",
        )
    model_rounds = generations * reflections
    attempts = matrix_document.get("runtime_controls", {}).get(
        "max_attempts_per_operation"
    )
    if (
        model_rounds != COMPARISON_MAX_NUM_GENERATIONS * COMPARISON_NUM_REFLECTIONS
        or attempts != MAX_ATTEMPTS_PER_OPERATION
    ):
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The frozen slot's run budget controls drifted",
        )
    price_table = pricing.load_price_table(root)
    bound = pricing.worst_case_bound(
        price_table,
        input_tokens=model_rounds * WORST_CASE_INPUT_TOKENS_PER_ROUND,
        output_tokens=model_rounds * matrix_run["max_tokens"],
        attempts=attempts,
    )
    authorization = authorize_next_comparison_run(
        ledger,
        matrix_document=matrix_document,
        run_index=run_index,
        next_run_worst_case_bound_cny=bound.total_cny,
    )
    return {
        "authorization": authorization,
        "command_argv": _production_new_run_argv(matrix_run),
        "matrix_file_sha256": observed_matrix_digest,
        "package_dir": str(resolved_package),
        "price_table_sha256": price_table.sha256,
        "workspace_root": str(root),
    }


def _slot_document_seq_matches(filename: str, run_index: int) -> int | None:
    """Parse `run-NNN.json` / `run-NNN-seq-K.json` for one slot; else None."""
    match = re.fullmatch(rf"run-{run_index:03d}(?:-seq-(\d+))?\.json", filename)
    if match is None:
        return None
    return int(match.group(1)) if match.group(1) is not None else 1


def _slot_reservation_documents(
    package_dir: Path, run_index: int
) -> list[tuple[int, Path]]:
    """All reservation documents for one slot, ordered by sequence."""
    reservations_dir = package_dir / "vault" / "run-reservations"
    if not reservations_dir.is_dir():
        return []
    sequenced: list[tuple[int, Path]] = []
    for path in reservations_dir.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        seq = _slot_document_seq_matches(path.name, run_index)
        if seq is not None:
            sequenced.append((seq, path))
    return sorted(sequenced)


def _slot_quarantine_records(
    package_dir: Path, run_index: int
) -> list[tuple[int, Path, dict[str, Any]]]:
    """All quarantine records for one slot, ordered by sequence."""
    quarantine_dir = package_dir / "vault" / "quarantine"
    if not quarantine_dir.is_dir():
        return []
    sequenced: list[tuple[int, Path, dict[str, Any]]] = []
    for path in quarantine_dir.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        seq = _slot_document_seq_matches(path.name, run_index)
        if seq is None:
            continue
        document = parse_json_bytes(path.read_bytes(), label="quarantine record")
        if not isinstance(document, dict):
            fail("INVALID_SCHEMA", "The quarantine record is not a JSON object")
        sequenced.append((seq, path, document))
    return sorted(sequenced, key=lambda item: item[0])


def reserve_comparison_slot(
    launch: dict[str, Any],
    *,
    execution_head_resolver: Callable[[Path], str] | None = None,
) -> dict[str, Any]:
    """Write one exclusive pre-exec reservation for a frozen matrix slot.

    The reservation closes duplicate/concurrent launch races that an
    append-after-run ledger cannot prevent. It is deliberately not released
    automatically: a process failure leaves a visible fail-closed artifact
    that must be reconciled against the Evidence Chain before any retry.

    The first slot's reservation also creates the write-once execution-code
    pin; every later slot must run at the pinned clean HEAD. The HEAD is
    resolved here, at the last comparison-level checkpoint before exec, via
    the admission boundary's clean-worktree check (a dirty tree fails as
    DIRTY_WORKTREE). Tests inject `execution_head_resolver`; the production
    runner never does. A commit drift fails closed before any reservation is
    written, and the stale pin is preserved as evidence.

    A quarantined slot is re-reserved as a new sequenced write-once document
    (`run-NNN-seq-K.json`) whose `supersedes_reservation_sha256` links the
    predecessor; the sequence derives from the slot's quarantine records, so
    an occupied slot still fails closed without a covering quarantine.
    """
    authorization = launch.get("authorization")
    command_argv = launch.get("command_argv")
    package_dir = launch.get("package_dir")
    workspace_root = launch.get("workspace_root")
    if (
        not isinstance(authorization, dict)
        or not isinstance(command_argv, tuple)
        or not command_argv
        or not isinstance(package_dir, str)
        or not isinstance(workspace_root, str)
    ):
        fail("INVALID_SCHEMA", "The comparison launch plan is incomplete")
    run_index = authorization.get("run_index")
    if not isinstance(run_index, int) or isinstance(run_index, bool):
        fail("INVALID_SCHEMA", "The comparison authorization lacks a run index")
    resolve_head = (
        execution_head_resolver
        if execution_head_resolver is not None
        else _require_clean_worktree
    )
    execution_commit = resolve_head(Path(workspace_root))
    if not _is_full_git_sha(execution_commit):
        fail("GIT_UNAVAILABLE", "Cannot resolve the execution HEAD commit")
    package = Path(package_dir)
    if execution_code_pin_path(package).is_file():
        pin = load_execution_code_pin(package)
        if pin["commit"] != execution_commit:
            fail(
                "EXECUTION_CODE_PIN_MISMATCH",
                "The execution HEAD differs from the comparison code pin",
                expected=pin["commit"],
                actual=execution_commit,
            )
    elif run_index != 1:
        fail(
            "EXECUTION_CODE_PIN_MISSING",
            "Only the first comparison slot may create the execution code pin",
        )
    else:
        create_execution_code_pin(package, commit=execution_commit)
    reservations_dir = package / "vault" / "run-reservations"
    reservations_dir.mkdir(parents=True, exist_ok=True)
    reservation_seq = 1 + len(_slot_quarantine_records(package, run_index))
    supersedes_sha256: str | None = None
    if reservation_seq >= 2:
        reservations = _slot_reservation_documents(package, run_index)
        if not reservations:
            fail(
                "COMPARISON_SLOT_ALREADY_RESERVED",
                "The comparison slot has no reservation record to supersede",
                run_index=run_index,
            )
        latest_seq, latest_path = reservations[-1]
        latest_sha = sha256_bytes(latest_path.read_bytes())
        records = _slot_quarantine_records(package, run_index)
        latest_record = records[-1][2]
        if latest_record.get("reservation_sha256") != latest_sha:
            fail(
                "COMPARISON_SLOT_ALREADY_RESERVED",
                "The latest reservation is not covered by a quarantine record",
                run_index=run_index,
            )
        supersedes_sha256 = latest_sha
    reservation_path = reservations_dir / (
        f"run-{run_index:03d}.json"
        if reservation_seq == 1
        else f"run-{run_index:03d}-seq-{reservation_seq}.json"
    )
    document = {
        "authorization": dict(authorization),
        "command_argv_sha256": sha256_bytes(canonical_json_bytes(list(command_argv))),
        "execution_code_commit": execution_commit,
        "price_table_sha256": launch.get("price_table_sha256"),
        "reserved_at": _now(),
        "reservation_seq": reservation_seq,
        "run_index": run_index,
        "schema_version": RUN_RESERVATION_SCHEMA_VERSION,
        "supersedes_reservation_sha256": supersedes_sha256,
    }
    data = canonical_json_bytes(document)
    digest = _write_bytes_once(
        reservation_path,
        data,
        label=f"comparison slot {run_index} reservation",
        exists_code="COMPARISON_SLOT_ALREADY_RESERVED",
    )
    return {
        "document": document,
        "path": str(reservation_path),
        "sha256": digest,
    }


def ingest_run_actual_cost(
    ledger: dict[str, Any],
    *,
    entry: LedgerEntry,
) -> dict[str, Any]:
    """Append actual cost even when it crosses a governance threshold.

    Accounting evidence is never discarded merely because spend crossed a
    limit. The returned status blocks future launches; the hard cap itself
    is enforced by `authorize_next_comparison_run` before provider work.
    """
    if ledger.get("status") not in ("initialized", "ingesting"):
        fail("LEDGER_CLOSED", "The ledger is not accepting run ingests")
    if (
        not isinstance(entry.actual_cost_cny, Decimal)
        or entry.actual_cost_cny < 0
        or not isinstance(entry.worst_case_bound_cny, Decimal)
        or entry.worst_case_bound_cny <= 0
    ):
        fail("INVALID_BUDGET", "Ledger costs must be valid non-negative decimals")
    if (
        not isinstance(entry.physical_attempt_count, int)
        or isinstance(entry.physical_attempt_count, bool)
        or entry.physical_attempt_count < 0
    ):
        fail("INVALID_SCHEMA", "Physical attempt count must be non-negative")
    parse_case_id(entry.case_id)
    for run in ledger["entries"]:
        if run["run_id"] == entry.run_id:
            fail(
                "LEDGER_DUPLICATE_RUN",
                "The ledger already carries this run",
                run_id=entry.run_id,
            )
        if run["run_index"] == entry.run_index:
            fail(
                "LEDGER_DUPLICATE_SLOT",
                "The ledger already carries this planned run slot",
                run_index=entry.run_index,
            )
    if entry.run_index != len(ledger.get("entries", [])) + 1:
        fail("LEDGER_SLOT_DRIFT", "Run costs must be ingested in frozen slot order")
    threshold = _money(
        ledger["plan_gate_reapproval_threshold_cny"],
        label="plan_gate_reapproval_threshold_cny",
    )
    tracked = ledger_current_spend(ledger)
    total = ledger_total_stage_spend(ledger)
    new_tracked = _quantize_cny(tracked + entry.actual_cost_cny)
    new_total = _quantize_cny(total + entry.actual_cost_cny)
    record = {
        "actual_cost_cny": str(_quantize_cny(entry.actual_cost_cny)),
        "case_id": entry.case_id,
        "pair_index": entry.pair_index,
        "physical_attempt_count": entry.physical_attempt_count,
        "profile_id": entry.profile_id,
        "run_id": entry.run_id,
        "run_index": entry.run_index,
        "status": entry.status,
        "worst_case_bound_cny": str(_quantize_cny(entry.worst_case_bound_cny)),
    }
    updated = dict(ledger)
    updated["entries"] = list(ledger["entries"]) + [record]
    updated["comparison_actual_spend_cny"] = str(new_tracked)
    updated["total_stage_spend_cny"] = str(new_total)
    updated["ingested_runs_count"] = len(updated["entries"])
    if new_total > CANARY_HARD_CAP_CNY:
        updated["status"] = "hard_cap_breached"
    elif new_total >= threshold:
        updated["status"] = "reapproval_required"
    else:
        updated["status"] = "ingesting"
    return updated


def ingest_forfeited_comparison_cost(
    ledger: dict[str, Any],
    *,
    entry: ForfeitedLedgerEntry,
) -> dict[str, Any]:
    """Append one quarantined run's forfeited actual cost.

    Forfeited spend never touches `entries` (the sequential slot invariant
    and per-slot result identity stay intact) but always counts toward the
    30.00 CNY hard cap and the 5.00 CNY reapproval threshold: spent money
    cannot launder budget. The returned status blocks future launches; the
    hard cap itself is enforced by `authorize_next_comparison_run`.
    """
    if ledger.get("status") not in ("initialized", "ingesting"):
        fail("LEDGER_CLOSED", "The ledger is not accepting run ingests")
    if (
        not isinstance(entry.actual_cost_cny, Decimal)
        or entry.actual_cost_cny < 0
        or not isinstance(entry.worst_case_bound_cny, Decimal)
        or entry.worst_case_bound_cny <= 0
    ):
        fail("INVALID_BUDGET", "Ledger costs must be valid non-negative decimals")
    if (
        not isinstance(entry.physical_attempt_count, int)
        or isinstance(entry.physical_attempt_count, bool)
        or entry.physical_attempt_count < 0
    ):
        fail("INVALID_SCHEMA", "Physical attempt count must be non-negative")
    if entry.reason != QUARANTINE_REASON_ZERO_FINALIZED_IDEA:
        fail("INVALID_SCHEMA", "Forfeited entries carry the closed quarantine reason")
    for run in ledger["entries"]:
        if run["run_id"] == entry.run_id:
            fail(
                "LEDGER_DUPLICATE_RUN",
                "The ledger already carries this run",
                run_id=entry.run_id,
            )
    for run in ledger.get("forfeited_entries", []):
        if run["run_id"] == entry.run_id:
            fail(
                "LEDGER_DUPLICATE_RUN",
                "The ledger already carries this run",
                run_id=entry.run_id,
            )
    threshold = _money(
        ledger["plan_gate_reapproval_threshold_cny"],
        label="plan_gate_reapproval_threshold_cny",
    )
    tracked = ledger_current_spend(ledger)
    total = ledger_total_stage_spend(ledger)
    forfeited_before = _money(
        ledger.get("forfeited_spend_cny"), label="forfeited_spend_cny"
    )
    new_forfeited = _quantize_cny(forfeited_before + entry.actual_cost_cny)
    new_total = _quantize_cny(total + entry.actual_cost_cny)
    record = {
        "actual_cost_cny": str(_quantize_cny(entry.actual_cost_cny)),
        "physical_attempt_count": entry.physical_attempt_count,
        "reason": entry.reason,
        "run_id": entry.run_id,
        "run_index": entry.run_index,
        "worst_case_bound_cny": str(_quantize_cny(entry.worst_case_bound_cny)),
    }
    updated = dict(ledger)
    updated["forfeited_entries"] = list(ledger.get("forfeited_entries", [])) + [record]
    updated["forfeited_spend_cny"] = str(new_forfeited)
    updated["total_stage_spend_cny"] = str(new_total)
    if tracked == 0 and not ledger["entries"]:
        updated["comparison_actual_spend_cny"] = ledger.get(
            "comparison_actual_spend_cny", str(LEDGER_INIT_SPEND_CNY)
        )
    if new_total > CANARY_HARD_CAP_CNY:
        updated["status"] = "hard_cap_breached"
    elif new_total >= threshold:
        updated["status"] = "reapproval_required"
    else:
        updated["status"] = "ingesting"
    return updated


def quarantine_comparison_run(
    workspace_root: Path,
    run_id: str,
    *,
    package_dir: Path,
    matrix_document: dict[str, Any],
) -> dict[str, Any]:
    """Retire one sealed zero-idea run and unlock its matrix slot for a re-run.

    Quarantine is the single legitimate exit for a run that sealed without a
    finalized idea: a write-once record preserves the run's identity, sealed
    outcome, derived actual cost, admission commit, covering reservation
    hash, and the closed reason; its actual spend enters the ledger as a
    forfeited entry that still counts toward the hard cap and the
    reapproval threshold. Every precondition fails closed: the run must be
    sealed, empty of finalized ideas, un-ingested, mapped to exactly one
    frozen matrix slot by its (case, arm) identity, admitted at a recorded
    code epoch, and covered by a reservation no other quarantine record
    covers yet.
    """
    from .evidence import validate_evidence_chain

    workspace = workspace_root.resolve(strict=True)
    store = RunStore(workspace)
    package = Path(package_dir)

    seal_path = store.runs_root / run_id / "seal.json"
    if seal_path.is_symlink() or not seal_path.is_file():
        fail("RUN_NOT_SEALED", "Only a sealed run can be quarantined", run_id=run_id)
    seal = parse_json_bytes(seal_path.read_bytes(), label="seal.json")
    if not isinstance(seal, dict) or seal.get("terminal_outcome") not in (
        "success",
        "failed",
    ):
        fail(
            "RUN_NOT_SEALED",
            "Only a sealed run with a Terminal Outcome can be quarantined",
            run_id=run_id,
        )
    if validate_evidence_chain(workspace, run_id, check_sealed=True).get("status") != (
        "valid"
    ):
        fail(
            "EVIDENCE_CHAIN_INVALID", "The quarantined run's Evidence Chain is invalid"
        )

    request, admission = _read_run_documents(store, run_id)
    if _sealed_idea_count(seal) != 0:
        fail(
            "QUARANTINE_REQUIRES_EMPTY_RUN",
            "Only a run without finalized ideas can be quarantined",
            run_id=run_id,
        )

    # Map the run to its frozen slot by its (case, arm) identity.
    request_case = request.get("case_id")
    profile_field = validate_profile_field(
        admission.get("prompt_profile"), label="admission.prompt_profile"
    )
    mapped = [
        run
        for run in matrix_document["runs"]
        if run["case_id"] == request_case
        and run["prompt_profile_id"] == profile_field["profile_id"]
    ]
    if len(mapped) != 1:
        fail(
            "MATRIX_SLOT_UNMATCHED",
            "The quarantined run's (case, arm) identity maps to no unique "
            "frozen matrix slot",
            case_id=request_case,
            profile_id=profile_field["profile_id"],
            matches=len(mapped),
        )
    matrix_run = mapped[0]
    run_index = matrix_run["run_index"]

    ledger_path = package / "spend-ledger.json"
    if not ledger_path.is_file():
        fail("COMPARISON_PACKAGE_INCOMPLETE", "The comparison package lacks its ledger")
    ledger = parse_json_bytes(ledger_path.read_bytes(), label="comparison spend ledger")
    _validate_ledger_arithmetic(ledger, matrix_document=matrix_document)
    for run in ledger["entries"]:
        if run["run_id"] == run_id:
            fail(
                "RUN_ALREADY_INGESTED",
                "The run is already ledgered and cannot be quarantined",
                run_id=run_id,
            )
    for run in ledger.get("forfeited_entries", []):
        if run["run_id"] == run_id:
            fail(
                "RUN_ALREADY_QUARANTINED",
                "The run already has a quarantine record",
                run_id=run_id,
            )

    # Provenance: the admission commit must belong to a recorded code epoch
    # (the current pin or a governed superseded pin).
    pin = load_execution_code_pin(package)
    admission_code = admission.get("code", {})
    admission_commit = (
        admission_code.get("commit") if isinstance(admission_code, dict) else None
    )
    if admission_commit != pin["commit"] and (
        admission_commit not in superseded_execution_code_commits(package)
    ):
        fail(
            "EXECUTION_CODE_PIN_MISMATCH",
            "The quarantined run's admission commit belongs to no recorded "
            "code epoch",
            expected=pin["commit"],
            actual=admission_commit,
        )

    # The covering reservation: the slot's latest reservation document must
    # not be covered by another quarantine record yet.
    reservations = _slot_reservation_documents(package, run_index)
    if not reservations:
        fail(
            "COMPARISON_SLOT_RESERVATION_MISSING",
            "The quarantined slot has no reservation record",
            run_index=run_index,
        )
    _latest_seq, latest_reservation_path = reservations[-1]
    reservation_sha256 = sha256_bytes(latest_reservation_path.read_bytes())
    reservation_document = parse_json_bytes(
        latest_reservation_path.read_bytes(), label="comparison slot reservation"
    )
    for _seq, _path, record in _slot_quarantine_records(package, run_index):
        if record.get("reservation_sha256") == reservation_sha256:
            fail(
                "COMPARISON_SLOT_ALREADY_QUARANTINED",
                "The latest reservation is already covered by a quarantine record",
                run_index=run_index,
            )
    authorization = reservation_document.get("authorization", {})
    worst_case_bound_cny = authorization.get("next_run_worst_case_bound_cny")

    derived = _sealed_run_metrics(store, run_id)
    quarantine_seq = 1 + len(_slot_quarantine_records(package, run_index))
    quarantine_dir = package / "vault" / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    record_path = quarantine_dir / (
        f"run-{run_index:03d}.json"
        if quarantine_seq == 1
        else f"run-{run_index:03d}-seq-{quarantine_seq}.json"
    )
    document = {
        "actual_cost_cny": str(derived["actual_cost_cny"]),
        "admission_commit": admission_commit,
        "case_id": matrix_run["case_id"],
        "pair_index": matrix_run["pair_index"],
        "physical_attempt_count": derived["physical_attempt_count"],
        "profile_id": profile_field["profile_id"],
        "quarantined_at": _now(),
        "reason": QUARANTINE_REASON_ZERO_FINALIZED_IDEA,
        "reservation_sha256": reservation_sha256,
        "run_id": run_id,
        "run_index": run_index,
        "schema_version": RUN_QUARANTINE_SCHEMA_VERSION,
        "sealed_outcome": seal.get("terminal_outcome"),
        "worst_case_bound_cny": str(
            _money(worst_case_bound_cny, label="reservation worst_case_bound_cny")
        ),
    }
    digest = _write_bytes_once(
        record_path,
        canonical_json_bytes(document),
        label=f"comparison slot {run_index} quarantine record",
        exists_code="COMPARISON_SLOT_ALREADY_QUARANTINED",
    )

    updated = ingest_forfeited_comparison_cost(
        ledger,
        entry=ForfeitedLedgerEntry(
            run_index=run_index,
            run_id=run_id,
            actual_cost_cny=derived["actual_cost_cny"],
            worst_case_bound_cny=_money(
                worst_case_bound_cny, label="reservation worst_case_bound_cny"
            ),
            physical_attempt_count=derived["physical_attempt_count"],
            reason=QUARANTINE_REASON_ZERO_FINALIZED_IDEA,
        ),
    )
    ledger_path.write_bytes(canonical_json_bytes(updated))
    return {
        "document": document,
        "ledger": updated,
        "path": str(record_path),
        "sha256": digest,
    }


def plan_gate_approval_document(
    *,
    ledger: dict[str, Any],
    approved_by: str,
) -> dict[str, Any]:
    """Record the Plan Gate approval of the comparison matrix.

    The approval sets a matrix reapproval threshold and a separate hard cap;
    it is explicitly NOT a per-run approval. Each run's production preflight
    still requires Robert's interactive `yes` (spec user story 47).
    """
    approved_by = nonempty_string(approved_by, label="approved_by")
    threshold = _money(
        ledger["plan_gate_reapproval_threshold_cny"],
        label="plan_gate_reapproval_threshold_cny",
    )
    historical = _money(ledger["historical_spend_cny"], label="historical_spend_cny")
    document = {
        "approved_by": approved_by,
        "canary_hard_cap_cny": str(CANARY_HARD_CAP_CNY),
        "comparison_actual_spend_cny": str(ledger_current_spend(ledger)),
        "historical_spend_cny": str(historical),
        "plan_gate_reapproval_threshold_cny": str(threshold),
        "planned_runs_count": ledger["planned_runs_count"],
        "schema_version": "comparison-plan-gate-approval-v1.1.0",
        "scope": "matrix_reapproval_threshold_not_per_run",
        "total_stage_spend_cny": str(ledger_total_stage_spend(ledger)),
    }
    return document


def plan_gate_does_not_waive_per_run_approval(approval: dict[str, Any]) -> bool:
    """Machine check: the recorded approval carries the no-waive scope."""
    return approval.get("scope") == "matrix_reapproval_threshold_not_per_run"


# ==========================================================================
# Result ingestion: fail-closed validation before any pair packet
# ==========================================================================


@dataclass(frozen=True, slots=True)
class RunMetrics:
    """The comparison-relevant facts ingested from one sealed run."""

    run_id: str
    run_index: int
    pair_index: int
    arm_position: int
    case_id: str
    profile_id: str
    terminal_outcome: str
    finish_reasons: tuple[str, ...]
    physical_attempt_count: int
    end_to_end_latency_ms: Decimal
    actual_cost_cny: Decimal
    idea_count: int


def _read_run_documents(
    store: RunStore, run_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_bytes = store.read_artifact(run_id, "request.json")
    request = parse_json_bytes(request_bytes, label="request.json")
    if not isinstance(request, dict):
        fail("RUN_CORRUPT", "request.json is not a JSON object")
    admission_bytes = store.read_artifact(run_id, "admission.json")
    admission = parse_json_bytes(admission_bytes, label="admission.json")
    if not isinstance(admission, dict):
        fail("RUN_CORRUPT", "admission.json is not a JSON object")
    return request, admission


def _run_events(store: RunStore, run_id: str) -> list[dict[str, Any]]:
    from .run_store import EVENTS_DIR

    run_root = store.runs_root / run_id
    events_dir = run_root / EVENTS_DIR
    if not events_dir.is_dir():
        fail("RUN_CORRUPT", "The sealed run has no events")
    documents: list[dict[str, Any]] = []
    for path in sorted(events_dir.iterdir()):
        if path.is_file() and path.name.endswith(".json"):
            document = parse_json_bytes(path.read_bytes(), label=path.name)
            if isinstance(document, dict):
                documents.append(document)
    return documents


def _sealed_run_metrics(store: RunStore, run_id: str) -> dict[str, Any]:
    """Derive finish reasons, physical attempts, latency, and cost."""
    events = _run_events(store, run_id)
    finish_reasons: list[str] = []
    attempt_count = 0
    latency_ms = Decimal("0")
    for event in events:
        if event.get("event_type") == "provider_attempt.finished":
            attempt_count += 1
            payload = event.get("payload", {})
            duration = payload.get("duration_ms")
            if isinstance(duration, str):
                try:
                    latency_ms += Decimal(duration)
                except ArithmeticError:
                    fail("RUN_CORRUPT", "A provider attempt duration is not a decimal")
        elif event.get("event_type") == "operation.finished":
            payload = event.get("payload", {})
            finish = payload.get("finish_reason")
            if isinstance(finish, str):
                finish_reasons.append(finish)
    seal_bytes = store.read_artifact(run_id, "seal.json")
    seal = parse_json_bytes(seal_bytes, label="seal.json")
    if not isinstance(seal, dict):
        fail("RUN_CORRUPT", "seal.json is not a JSON object")
    total_cost = Decimal("0.00")
    for event in events:
        if event.get("event_type") != "provider_attempt.finished":
            continue
        cost = event.get("payload", {}).get("cost_cny")
        if cost is not None:
            try:
                total_cost += Decimal(str(cost))
            except ArithmeticError:
                fail("RUN_CORRUPT", "A provider attempt cost is not a decimal")
    return {
        "finish_reasons": finish_reasons,
        "physical_attempt_count": attempt_count,
        "end_to_end_latency_ms": latency_ms,
        "actual_cost_cny": _quantize_cny(total_cost),
        "seal": seal,
        "events": events,
    }


def ingest_comparison_result(
    workspace_root: Path,
    run_id: str,
    *,
    expected_run_index: int,
    expected_arm_position: int,
    expected_pair_index: int,
    expected_case_id: str,
    expected_profile_id: str,
    matrix_document: dict[str, Any],
    package_dir: Path,
) -> RunMetrics:
    """Ingest one sealed comparison run, fail closed on any drift.

    Validates Run Specification/profile identity, case/input hashes, the
    execution-code pin against `admission.code.commit`, Run Seal, Evidence
    Chain, sanitized export, Evaluation Artifact coverage, finish reasons,
    attempt topology, latency, and actual cost before the result may feed a
    pair packet or the reducer.
    """
    from .evidence import validate_evidence_chain

    workspace = workspace_root.resolve(strict=True)
    store = RunStore(workspace)
    without_pin = {
        key: value for key, value in matrix_document.items() if key != "matrix_sha256"
    }
    if sha256_bytes(canonical_json_bytes(without_pin)) != matrix_document_sha256_pin(
        matrix_document
    ):
        fail("MATRIX_PIN_DRIFT", "The comparison matrix pin does not match its bytes")

    # 1. Full Evidence Chain (includes Run Seal validation).
    validation = validate_evidence_chain(workspace, run_id, check_sealed=True)
    if validation.get("status") != "valid":
        fail("EVIDENCE_CHAIN_INVALID", "The comparison run's Evidence Chain is invalid")

    # 2. Run Specification and profile identity against the matrix pin.
    request, admission = _read_run_documents(store, run_id)
    pin = load_execution_code_pin(Path(package_dir))
    admission_code = admission.get("code", {})
    admission_commit = (
        admission_code.get("commit") if isinstance(admission_code, dict) else None
    )
    if admission_commit != pin["commit"]:
        fail(
            "EXECUTION_CODE_PIN_MISMATCH",
            "The sealed run's admission commit differs from the code pin",
            expected=pin["commit"],
            actual=admission_commit,
        )
    profile_field = validate_profile_field(
        admission.get("prompt_profile"), label="admission.prompt_profile"
    )
    if profile_field["profile_id"] != expected_profile_id:
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The ingested run's Prompt Profile does not match its matrix arm",
            expected=expected_profile_id,
            actual=profile_field["profile_id"],
        )
    if request.get("case_id") != expected_case_id:
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The ingested run belongs to another case",
            expected=expected_case_id,
            actual=request.get("case_id"),
        )
    model = admission.get("model", {})
    if (
        model.get("reasoning_effort") != COMPARISON_REASONING_EFFORT
        or model.get("max_tokens") != COMPARISON_MAX_TOKENS
    ):
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The ingested run's execution parameters drifted from the frozen matrix",
        )
    budgets = admission.get("budgets", {})
    if (
        budgets.get("max_num_generations") != COMPARISON_MAX_NUM_GENERATIONS
        or budgets.get("num_reflections") != COMPARISON_NUM_REFLECTIONS
    ):
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The ingested run's budgets drifted from the frozen matrix",
        )
    # The workshop/corpus pins must match the frozen matrix entry.
    for entry in matrix_document["runs"]:
        if entry["run_index"] == expected_run_index:
            if (
                entry["case_id"] != expected_case_id
                or entry["arm_position"] != expected_arm_position
            ):
                fail(
                    "COMPARISON_IDENTITY_MISMATCH",
                    "The ingested run's matrix slot disagrees with its evidence",
                    run_index=expected_run_index,
                )
            request_workshop = request.get("workshop", {})
            request_corpus = request.get("corpus", {})
            if (
                request_workshop.get("sha256") != entry["workshop"]["sha256"]
                or request_corpus.get("sha256") != entry["corpus"]["sha256"]
            ):
                fail(
                    "INPUT_HASH_DRIFT",
                    "The ingested run's pinned inputs drifted from the frozen matrix",
                )
            break
    else:
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The ingested run has no slot in the frozen matrix",
            run_id=run_id,
        )

    # 3. Sanitized export presence and identity.
    evidence_root = workspace / "evidence" / "ideation-runs" / run_id
    manifest_path = evidence_root / "manifest.json"
    if not manifest_path.is_file():
        fail(
            "SANITIZED_EXPORT_MISSING",
            "The comparison run lacks its sanitized export",
            run_id=run_id,
        )
    sanitized = parse_json_bytes(manifest_path.read_bytes(), label="sanitized manifest")
    if not isinstance(sanitized, dict):
        fail("RUN_CORRUPT", "The sanitized manifest is not a JSON object")
    sanitized_profile = sanitized.get("prompt_profile", {})
    if sanitized_profile.get("profile_id") != expected_profile_id:
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The sanitized export's profile identity drifted",
        )
    if sanitized.get("case_id") != expected_case_id:
        fail(
            "COMPARISON_IDENTITY_MISMATCH",
            "The sanitized export belongs to another case",
        )

    # 4. Evaluation coverage. Two explicit version branches (ticket 03): the
    # v1 human artifact (VM-QUAL-01 semantics, unchanged) or the registered
    # evaluation protocol's AI dual-review coverage. Missing and invalid AI
    # coverage never ingest; complete_resolved and complete_unresolved both
    # ingest (unresolved abstentions/conflicts continue the matrix but never
    # pass a quality gate — that is enforced by the reducer's verdict-side
    # floor gates, not here). The channel descriptor itself is enforced here
    # (fail closed on None) and consumed by the reducer through the verdict
    # documents' authorship; the per-run ingestion keeps its boolean gate.
    if _evaluation_coverage_for_run(workspace, run_id) is None:
        fail(
            "EVALUATION_ARTIFACT_MISSING",
            "The comparison run lacks a complete Evaluation Artifact",
            run_id=run_id,
        )

    # 5. Derive run metrics from the sealed chain.
    derived = _sealed_run_metrics(store, run_id)
    seal = derived["seal"]
    # Every arm reaching the reducer passed all ingestion gates (chain,
    # seal, export, coverage, identity pins) fail-closed above; the
    # reducer's deterministic_regression gate records that structural
    # enforcement point instead of an always-True per-run flag.
    return RunMetrics(
        run_id=run_id,
        run_index=expected_run_index,
        pair_index=expected_pair_index,
        arm_position=expected_arm_position,
        case_id=expected_case_id,
        profile_id=expected_profile_id,
        terminal_outcome=seal.get("terminal_outcome"),
        finish_reasons=tuple(derived["finish_reasons"]),
        physical_attempt_count=derived["physical_attempt_count"],
        end_to_end_latency_ms=derived["end_to_end_latency_ms"],
        actual_cost_cny=derived["actual_cost_cny"],
        idea_count=_sealed_idea_count(seal),
    )


def matrix_document_sha256_pin(matrix_document: dict[str, Any]) -> str:
    """A matrix document pins its own digest under `matrix_sha256`."""
    pin = matrix_document.get("matrix_sha256")
    if not isinstance(pin, str):
        fail("MATRIX_PIN_DRIFT", "The matrix document lacks its digest pin")
    return pin


def _sealed_idea_count(seal: dict[str, Any]) -> int:
    summary = seal.get("terminal_summary", {})
    count = summary.get("idea_count") if isinstance(summary, dict) else None
    if not isinstance(count, int) or isinstance(count, bool):
        fail("RUN_CORRUPT", "The seal terminal summary lacks its idea_count")
    return count


def _evaluation_coverage_for_run(workspace: Path, run_id: str) -> dict[str, Any] | None:
    """Deterministic evaluation-coverage decision for one comparison run.

    Returns the evaluation channel descriptor, or None when the run may not
    ingest. Two explicit version branches:

    - v1 human: the historical VM-QUAL-01 check (one schema-valid finalized
      Evaluation Artifact heading the supersedes chain) — the
      ``evaluation_artifact_v1`` channel.
    - v2 AI dual review (registered protocol): the per-idea AI coverage over
      the sealed inventory. ``missing`` and ``invalid`` fail closed here;
      ``complete_resolved`` and ``complete_unresolved`` both ingest, carrying
      the per-idea quality floor state for the reducer's floor gates — the
      ``evaluation_artifact_v2_ai`` channel. A run mixing both channels
      fails closed: one scoring ruler per matrix.
    """
    from .ai_review import list_ai_review_coverage
    from .evaluation import list_evaluation_coverage

    human = _human_coverage_for_run(workspace, run_id)
    ai = _ai_coverage_for_run(workspace, run_id)
    if human is not None and ai is not None:
        fail(
            "EVALUATION_CHANNEL_CONFLICT",
            "The run carries both a v1 human Evaluation Artifact and AI "
            "dual-review coverage; one matrix uses one evaluation protocol",
            run_id=run_id,
        )
    if human is not None:
        return human
    if ai is not None:
        return ai
    return None


def _human_coverage_for_run(workspace: Path, run_id: str) -> dict[str, Any] | None:
    """The v1 human branch: covered/draft_only/missing over the artifact chain.

    None means "not present on the v1 channel" in the channel-conflict sense:
    draft_only and missing ideas are reported but do not ingest (kept as the
    historical boolean behavior).
    """
    from .evaluation import list_evaluation_coverage

    try:
        coverage = list_evaluation_coverage(workspace)
    except IdeationInputError:
        return None
    for run_entry in coverage.get("runs", []):
        if run_entry.get("run_id") != run_id:
            continue
        if run_entry.get("status") != "evaluable":
            return None
        ideas = run_entry.get("ideas", [])
        if any(idea.get("state") == "covered" for idea in ideas):
            return {"channel": "evaluation_artifact_v1", "coverage": "covered"}
        return None
    return None


def _ai_coverage_for_run(workspace: Path, run_id: str) -> dict[str, Any] | None:
    """The v2 AI branch: consensus coverage per idea with the quality floor.

    A run participates on this channel only when at least one finalized idea
    carries complete AI coverage (resolved or unresolved) and none of its
    ideas is invalid; a merely ``unaggregated`` idea (both slots valid, no
    consensus record) fails closed as missing — the honest summary step is
    part of the protocol, not optional bookkeeping.
    """
    from .ai_review import list_ai_review_coverage

    try:
        ai_coverage = list_ai_review_coverage(workspace)
    except IdeationInputError:
        return None
    for run_entry in ai_coverage.get("runs", []):
        if run_entry.get("run_id") != run_id:
            continue
        if run_entry.get("status") != "evaluable":
            return None
        ideas = run_entry.get("ideas", [])
        if any(idea.get("state") == "invalid" for idea in ideas):
            fail(
                "EVALUATION_ARTIFACT_INVALID",
                "The comparison run's AI review coverage is invalid and "
                "cannot ingest",
                run_id=run_id,
            )
        complete = [
            idea for idea in ideas if idea.get("state", "").startswith("complete_")
        ]
        if complete:
            floors = {idea.get("quality_floor", {}).get("state") for idea in complete}
            return {
                "channel": "evaluation_artifact_v2_ai",
                "coverage": sorted({idea["state"] for idea in complete})[0],
                "idea_states": [idea["state"] for idea in ideas],
                "quality_floor_states": sorted(str(state) for state in floors),
            }
        return None
    return None


# ==========================================================================
# Write-once verdicts and the fail-closed reveal gate
# ==========================================================================


@dataclass(frozen=True, slots=True)
class PairVerdict:
    """Robert's write-once blinded verdict for one pair.

    `domain_method_fit` and `unjustified_ml_intrusion` are pair-level
    scalars: the challenger arm judged relative to the baseline arm on the
    blinded packet (never an absolute per-arm scale). `rubric_floor` stays
    the per-blind-arm dict of the approved Idea Quality Rubric.
    """

    case_id: str
    verdict: str
    overall_rationale: str
    domain_method_fit: str
    unjustified_ml_intrusion: str
    rubric_floor: dict[str, str]
    recorded_at: str


def verdict_document(verdict: PairVerdict, *, packet_sha256: str) -> dict[str, Any]:
    """Serialize one verdict; closed enums, non-empty rationale.

    `domain_method_fit` and `unjustified_ml_intrusion` validate their
    pair-level scalar strings against the closed enums (the reference
    frame is the challenger arm relative to the baseline arm, judged on
    the blinded packet); `rubric_floor` validates both blind arms against
    the rubric vocabulary.
    """
    if verdict.verdict not in VERDICT_ENUM:
        fail(
            "INVALID_VERDICT",
            "The pair verdict must use the closed outcome enum",
            verdict=verdict.verdict,
        )
    if not verdict.overall_rationale.strip():
        fail("INVALID_VERDICT", "The overall rationale must be a non-empty string")
    if not isinstance(verdict.domain_method_fit, str) or (
        verdict.domain_method_fit not in DOMAIN_METHOD_FIT_ENUM
    ):
        fail(
            "INVALID_VERDICT",
            "domain_method_fit is not in the closed pair-level enum",
            value=verdict.domain_method_fit,
        )
    if not isinstance(verdict.unjustified_ml_intrusion, str) or (
        verdict.unjustified_ml_intrusion not in ML_INTRUSION_ENUM
    ):
        fail(
            "INVALID_VERDICT",
            "unjustified_ml_intrusion is not in the closed pair-level enum",
            value=verdict.unjustified_ml_intrusion,
        )
    if set(verdict.rubric_floor) != {"arm_a", "arm_b"}:
        fail(
            "INVALID_VERDICT",
            "rubric_floor must cover both blind arms",
        )
    for arm, value in verdict.rubric_floor.items():
        if (
            value != RUBRIC_FLOOR_CLEAN_VALUE
            and value not in RUBRIC_FLOOR_PROBLEM_VALUES
        ):
            fail(
                "INVALID_VERDICT",
                "rubric_floor carries an unknown judgment",
                value=value,
            )
    document = {
        "case_id": verdict.case_id,
        "domain_method_fit": verdict.domain_method_fit,
        "overall_rationale": verdict.overall_rationale,
        "packet_sha256": packet_sha256,
        "recorded_at": verdict.recorded_at,
        "rubric_floor": dict(verdict.rubric_floor),
        "schema_version": VERDICT_SCHEMA_VERSION,
        "unjustified_ml_intrusion": verdict.unjustified_ml_intrusion,
        "verdict": verdict.verdict,
    }
    return document


_AI_VERDICT_KEYS = {
    "authorship",
    "case_id",
    "content_space",
    "recorded_at",
    "schema_version",
}
_CONTENT_SPACE_KEYS = {
    "arm_content_1",
    "arm_content_2",
    "domain_method_fit",
    "overall_preference",
    "quality_floor_content_1",
    "quality_floor_content_2",
    "unjustified_ml_intrusion",
}
_ARM_KEYS = {"idea_index", "idea_sha256", "run_id"}
_AUTHORSHIP_KEYS = {
    "kind",
    "pair_id",
    "review_config_sha256",
    "verdict_idea_index",
    "verdict_run_id",
}


def validate_ai_verdict_document(document: dict[str, Any]) -> dict[str, Any]:
    """Closed validation of one vault AI verdict (content-space document).

    `overall_preference` ∈ {content_1, content_2, tie}; `domain_method_fit`
    ∈ {content_1, content_2, tie}; `unjustified_ml_intrusion` ∈ {content_1,
    content_2, equal}. The quality-floor states are the consensus-record
    vocabulary; anything other than `clean` blocks the reducer's floor gate
    for that arm.
    """
    checked = closed_object(document, label="AI verdict", keys=_AI_VERDICT_KEYS)
    if checked["schema_version"] != AI_VERDICT_SCHEMA_VERSION:
        fail(
            "INVALID_VERDICT",
            "Unsupported AI verdict schema_version",
            schema_version=checked["schema_version"],
        )
    parse_case_id(checked["case_id"])
    content = closed_object(
        checked["content_space"],
        label="AI verdict content_space",
        keys=_CONTENT_SPACE_KEYS,
    )
    preference = content["overall_preference"]
    if preference not in ("content_1", "content_2", "tie"):
        fail(
            "INVALID_VERDICT",
            "The AI verdict overall_preference is not in the closed content enum",
            value=preference,
        )
    fit = content["domain_method_fit"]
    if fit not in ("content_1", "content_2", "tie"):
        fail(
            "INVALID_VERDICT",
            "The AI verdict domain_method_fit is not in the closed content enum",
            value=fit,
        )
    intrusion = content["unjustified_ml_intrusion"]
    if intrusion not in ("content_1", "content_2", "equal"):
        fail(
            "INVALID_VERDICT",
            "The AI verdict unjustified_ml_intrusion is not in the closed content enum",
            value=intrusion,
        )
    for state in (
        content["quality_floor_content_1"],
        content["quality_floor_content_2"],
    ):
        if state not in ("clean", "unresolved", "violated", "not_evaluated"):
            fail(
                "INVALID_VERDICT",
                "The AI verdict carries an unknown quality-floor state",
                value=state,
            )
    for arm_name in ("arm_content_1", "arm_content_2"):
        closed_object(content[arm_name], label=f"AI verdict {arm_name}", keys=_ARM_KEYS)
    authorship = closed_object(
        checked["authorship"], label="AI verdict authorship", keys=_AUTHORSHIP_KEYS
    )
    if authorship["kind"] != "ai_pair_reduction":
        fail(
            "INVALID_VERDICT",
            "The AI verdict authorship must be an AI pair reduction",
            kind=authorship["kind"],
        )
    if not isinstance(authorship["pair_id"], str) or not authorship["pair_id"]:
        fail("INVALID_VERDICT", "The AI verdict lacks its pair_id binding")
    if (
        not isinstance(authorship["review_config_sha256"], str)
        or len(authorship["review_config_sha256"]) != 64
    ):
        fail(
            "INVALID_VERDICT",
            "The AI verdict lacks its review-config hash binding",
        )
    timestamp(checked["recorded_at"], label="AI verdict recorded_at")
    return checked


def ai_verdict_to_display(
    ai_verdict: dict[str, Any],
    *,
    baseline_run_id: str,
    challenger_run_id: str,
    mapping: BlindPairMapping,
) -> dict[str, Any]:
    """Project a content-space AI verdict onto the comparison display arms.

    The comparison packet's display side follows the frozen blind mapping:
    display arm A holds the run whose profile id is `mapping.arm_a_profile_id`
    (baseline or challenger), and the packet was built from exactly the two
    sealed runs this pair ingested. The AI verdict carries its anonymous
    content-space preference (content_1/content_2 plus each arm's run_id
    binding), so the projection verifies the run bindings against the ingested
    facts, then emits the same closed display-side enums a human verdict
    carries — the reducer's pre-registered gates stay byte-identical.

    The quality-floor states move per arm: a floor state is attached to the
    run the AI consensus bound it to, and the vault document exposes them as
    `rubric_floor_baseline` / `rubric_floor_challenger` for the floor gate.
    """
    content = validate_ai_verdict_document(ai_verdict)["content_space"]
    arm_run_ids = {
        "content_1": content["arm_content_1"]["run_id"],
        "content_2": content["arm_content_2"]["run_id"],
    }
    if sorted(arm_run_ids.values()) != sorted([baseline_run_id, challenger_run_id]):
        fail(
            "IDENTITY_MISMATCH",
            "The AI verdict's arm run bindings differ from the ingested pair",
            content_run_ids=sorted(arm_run_ids.values()),
        )
    # Which display arm does each anonymous content occupy? The packet's
    # arm_a holds the profile that the blind mapping placed there; the run
    # on that side is known from the ingested facts.
    arm_a_run_id = (
        baseline_run_id
        if mapping.arm_a_profile_id == BASELINE_PROFILE_ID
        else challenger_run_id
    )
    run_on_arm = {
        "arm_a": arm_a_run_id,
        "arm_b": (
            challenger_run_id if arm_a_run_id == baseline_run_id else baseline_run_id
        ),
    }
    content_by_arm = {
        "arm_a": next(
            content_name
            for content_name, run_id in arm_run_ids.items()
            if run_id == run_on_arm["arm_a"]
        ),
        "arm_b": next(
            content_name
            for content_name, run_id in arm_run_ids.items()
            if run_id == run_on_arm["arm_b"]
        ),
    }

    def prefer(value: str, *, a_word: str, b_word: str) -> str:
        if value in ("tie", "equal"):
            return "tie" if value == "tie" else "unchanged"
        return a_word if content_by_arm["arm_a"] == value else b_word

    def role_prefer(value: str, *, challenger_word: str, baseline_word: str) -> str:
        if value in ("tie", "equal"):
            return "tie" if value == "tie" else "unchanged"
        # Role-anchored enums resolve by which comparison run the preferred
        # content belongs to, never by its display position.
        return challenger_word if value == challenger_content else baseline_word

    baseline_content = next(
        name for name, run_id in arm_run_ids.items() if run_id == baseline_run_id
    )
    challenger_content = next(
        name for name, run_id in arm_run_ids.items() if run_id == challenger_run_id
    )
    intrusion = content["unjustified_ml_intrusion"]
    if intrusion == "equal":
        intrusion_display = "unchanged"
    else:
        # "content_X more intrusion" projects onto the roles: the challenger
        # arm's unjustified ML intrusion relative to the baseline arm is
        # "increased" exactly when the heavier-intrusion content is the
        # challenger's content.
        intrusion_display = (
            "increased" if intrusion == challenger_content else "decreased"
        )
    floor_by_content = {
        "content_1": content["quality_floor_content_1"],
        "content_2": content["quality_floor_content_2"],
    }
    return {
        "verdict": prefer(
            content["overall_preference"], a_word="a_better", b_word="b_better"
        ),
        "domain_method_fit": role_prefer(
            content["domain_method_fit"],
            challenger_word="challenger_better",
            baseline_word="baseline_better",
        ),
        "unjustified_ml_intrusion": intrusion_display,
        "rubric_floor_baseline": floor_by_content[baseline_content],
        "rubric_floor_challenger": floor_by_content[challenger_content],
        "content_space": content,
    }


def ai_verdict_facts(
    ai_verdict: dict[str, Any],
    *,
    baseline_run_id: str,
    challenger_run_id: str,
    mapping: BlindPairMapping,
    packet_sha256: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Assemble the reducer-facing verdict dict for one AI-authored pair.

    The AI verdict is bound to the same packet hash the human channel binds
    to (the packet bytes were built from these sealed runs before any review
    ran), so the reducer's VERDICT_PACKET_MISMATCH check applies unchanged.
    The document keeps the AI authorship explicitly; it is NOT a
    comparison-pair-verdict-v1.1.0 human verdict and can never be recorded in
    the vault's human verdicts directory.
    """
    projected = ai_verdict_to_display(
        ai_verdict,
        baseline_run_id=baseline_run_id,
        challenger_run_id=challenger_run_id,
        mapping=mapping,
    )
    document = {
        "ai_authorship": {
            "pair_id": ai_verdict["authorship"]["pair_id"],
            "review_config_sha256": ai_verdict["authorship"]["review_config_sha256"],
            "schema_version": AI_VERDICT_SCHEMA_VERSION,
        },
        "case_id": ai_verdict["case_id"],
        "domain_method_fit": projected["domain_method_fit"],
        "packet_sha256": packet_sha256,
        "recorded_at": recorded_at,
        "rubric_floor": {
            "baseline": projected["rubric_floor_baseline"],
            "challenger": projected["rubric_floor_challenger"],
        },
        "schema_version": AI_VERDICT_SCHEMA_VERSION,
        "unjustified_ml_intrusion": projected["unjustified_ml_intrusion"],
        "verdict": projected["verdict"],
    }
    if document["verdict"] not in VERDICT_ENUM:
        fail(
            "INVALID_VERDICT",
            "The projected AI verdict is not in the closed outcome enum",
            verdict=document["verdict"],
        )
    if document["domain_method_fit"] not in DOMAIN_METHOD_FIT_ENUM:
        fail(
            "INVALID_VERDICT",
            "The projected AI domain_method_fit is not in the closed enum",
            value=document["domain_method_fit"],
        )
    if document["unjustified_ml_intrusion"] not in ML_INTRUSION_ENUM:
        fail(
            "INVALID_VERDICT",
            "The projected AI unjustified_ml_intrusion is not in the closed enum",
            value=document["unjustified_ml_intrusion"],
        )
    return document


def _write_bytes_once(path: Path, data: bytes, *, label: str, exists_code: str) -> str:
    """Write `data` exclusively at `path`; existing targets fail closed."""
    if path.is_symlink():
        fail("SYMLINK_FORBIDDEN", f"{label} is a symlink")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fail(exists_code, f"{label} already exists and cannot be overwritten")
    except OSError as exc:
        fail("STORAGE_WRITE_FAILED", f"Cannot write {label}: {exc}")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        fail("STORAGE_WRITE_FAILED", f"Cannot write {label}: {exc}")
    return sha256_bytes(data)


class ComparisonVault:
    """A directory-backed write-once vault for verdicts and the reveal.

    Verdict files are committed exclusive-create; the reveal marker is a
    write-once document whose commit fails closed if any required verdict
    is missing, and any verdict write after the reveal is rejected.
    """

    VERDICTS_DIR = "verdicts"
    REVEAL_NAME = "reveal.json"

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._verdicts_dir = self._root / self.VERDICTS_DIR
        self._verdicts_dir.mkdir(parents=True, exist_ok=True)

    def _verdict_path(self, case_id: str) -> Path:
        parse_case_id(case_id)
        path = self._verdicts_dir / f"{case_id}.json"
        if path.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The verdict path is a symlink")
        return path

    @property
    def revealed(self) -> bool:
        return (self._root / self.REVEAL_NAME).is_file()

    def record_verdict(self, verdict: PairVerdict, *, packet_sha256: str) -> str:
        """Write-once the verdict document; an existing verdict fails closed."""
        self._guard_reveal(verdict.case_id)
        path = self._verdict_path(verdict.case_id)
        document = verdict_document(verdict, packet_sha256=packet_sha256)
        return _write_bytes_once(
            path,
            canonical_json_bytes(document),
            label="pair verdict",
            exists_code="ARTIFACT_EXISTS",
        )

    def verdicts_frozen(self, *, required_case_ids: tuple[str, ...]) -> bool:
        """True when every required write-once verdict is on disk."""
        for case_id in required_case_ids:
            if not self._verdict_path(case_id).is_file():
                return False
        return True

    def reveal(
        self,
        *,
        mappings: tuple[BlindPairMapping, ...],
        selection_manifest: dict[str, Any],
        required_case_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        """Freeze all available verdicts, then reveal the blind mapping.

        Fail closed unless every required verdict is already frozen. The
        reveal document is write-once: after it exists, further verdict
        writes are rejected (`VERDICT_AFTER_REVEAL`).
        """
        if not self.verdicts_frozen(required_case_ids=required_case_ids):
            fail(
                "REVEAL_BLOCKED",
                "The reveal requires every available write-once verdict to be frozen first",
            )
        document = {
            "blind_mapping": blind_mapping_document(
                mappings, selection_manifest=selection_manifest
            ),
            "revealed_at": _now(),
            "schema_version": "comparison-reveal-v1.0.0",
        }
        _write_bytes_once(
            self._root / self.REVEAL_NAME,
            canonical_json_bytes(document),
            label="reveal document",
            exists_code="ARTIFACT_EXISTS",
        )
        return document

    def load_verdict(self, case_id: str) -> dict[str, Any]:
        path = self._verdict_path(case_id)
        if not path.is_file():
            fail(
                "MISSING_VERDICT",
                "No write-once verdict exists for this case",
                case_id=case_id,
            )
        document = parse_json_bytes(path.read_bytes(), label=f"verdict {case_id}")
        if not isinstance(document, dict):
            fail("INVALID_VERDICT", "The verdict document is not a JSON object")
        if document.get("schema_version") != VERDICT_SCHEMA_VERSION:
            fail("INVALID_VERDICT", "Unsupported verdict schema_version")
        return document

    def _guard_reveal(self, case_id: str) -> None:
        if self.revealed:
            fail(
                "VERDICT_AFTER_REVEAL",
                "A verdict cannot be recorded after the blind mapping is revealed",
                case_id=case_id,
            )

    # ------------------------------------------------------------------
    # Ticket 03: the AI verdict channel. AI verdicts live in their own
    # write-once directory (`ai-verdicts/`), disjoint from Robert's blinded
    # human verdicts (`verdicts/`). Recording an AI verdict does NOT satisfy
    # `verdicts_frozen` (the human reveal gate); consuming one in the reducer
    # requires the caller to pass it explicitly, which is only reachable
    # under the registered evaluation-protocol revision.
    # ------------------------------------------------------------------

    AI_VERDICTS_DIR = "ai-verdicts"

    def _ai_verdicts_dir(self) -> Path:
        path = self._root / self.AI_VERDICTS_DIR
        if path.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The ai-verdicts directory is a symlink")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _ai_verdict_path(self, case_id: str) -> Path:
        parse_case_id(case_id)
        path = self._ai_verdicts_dir() / f"{case_id}.json"
        if path.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The ai verdict path is a symlink")
        return path

    def record_ai_verdict(self, document: dict[str, Any]) -> str:
        """Write-once an AI verdict document for one case; duplicates fail."""
        case_id = document.get("case_id")
        if not isinstance(case_id, str):
            fail("INVALID_VERDICT", "The AI verdict lacks its case_id")
        if self.revealed:
            fail(
                "VERDICT_AFTER_REVEAL",
                "An AI verdict cannot be recorded after the blind mapping is "
                "revealed",
                case_id=case_id,
            )
        path = self._ai_verdict_path(case_id)
        return _write_bytes_once(
            path,
            canonical_json_bytes(document),
            label="AI pair verdict",
            exists_code="ARTIFACT_EXISTS",
        )

    def load_ai_verdict(self, case_id: str) -> dict[str, Any] | None:
        """The AI verdict for one case, or None when the channel is empty."""
        path = self._ai_verdict_path(case_id)
        if not path.is_file():
            return None
        document = parse_json_bytes(path.read_bytes(), label=f"AI verdict {case_id}")
        if not isinstance(document, dict):
            fail("INVALID_VERDICT", "The AI verdict document is not a JSON object")
        if document.get("schema_version") != AI_VERDICT_SCHEMA_VERSION:
            fail(
                "INVALID_VERDICT",
                "Unsupported AI verdict schema_version",
                schema_version=document.get("schema_version"),
            )
        return document

    def ai_verdicts(
        self, required_case_ids: tuple[str, ...]
    ) -> dict[str, dict[str, Any]]:
        """Every recorded AI verdict for the required cases (missing → None)."""
        verdicts: dict[str, dict[str, Any]] = {}
        for case_id in required_case_ids:
            document = self.load_ai_verdict(case_id)
            if document is not None:
                verdicts[case_id] = document
        return verdicts


# ==========================================================================
# Deterministic Promotion reducer
# ==========================================================================


@dataclass(frozen=True, slots=True)
class PairFacts:
    """The ingested, revealed facts of one pair feeding the reducer.

    `packet_sha256` is the digest of the pair packet the verdict must be
    bound to: the reducer fails closed on any verdict whose recorded
    packet hash differs from these facts.
    """

    pair_index: int
    case_id: str
    cluster: str
    baseline_metrics: RunMetrics | None
    challenger_metrics: RunMetrics | None
    verdict: dict[str, Any] | None
    packet_sha256: str


def reduce_prompt_comparison(
    *,
    selection_manifest: dict[str, Any],
    matrix_document: dict[str, Any],
    reveal_document: dict[str, Any],
    pair_facts: tuple[PairFacts, ...],
    ledger: dict[str, Any],
    ai_verdicts: Mapping[str, dict[str, Any]] | None = None,
    evaluation_protocol: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reduce the blinded comparison against the pre-registered criteria.

    The reducer is a pure, deterministic function of the ingested facts,
    the frozen matrix, the write-once reveal document, and the ledger
    state. The blind mapping is consumed only through `reveal_document` —
    the write-once `reveal.json` a ComparisonVault commits after every
    available verdict is frozen — so a reduction can never see the blind
    identity before the fail-closed reveal gate opened it. The same inputs
    reduce to byte-identical output.

    Packet binding is enforced at two points: the packet bytes are bound
    to the sealed evidence at build time (build_pair_packets_from_ingested
    is the only sanctioned live builder), and each pair's verdict is
    re-checked here against `PairFacts.packet_sha256` (a verdict bound to
    a different packet fails closed as VERDICT_PACKET_MISMATCH).

    Ticket 03 (revised evaluation protocol): `ai_verdicts` carries the
    AI-authored verdict documents from the vault's `ai-verdicts/` channel
    (case_id → document). When supplied, `evaluation_protocol` must be the
    registered evaluation protocol manifest (post-first-output revision) —
    the old Gate continues to reject AI records. Mixing an AI verdict with
    human verdicts inside one reduction fails closed: all eight results of
    the matrix must use one evaluation protocol. AI verdicts bypass no
    gate: their quality floors enter the same rubric-floor gate, and the
    AI channel adds its own floor-state gate for unresolved floors.
    """
    mappings = assert_blind_mapping_document_shape(
        closed_object(
            reveal_document,
            label="reveal document",
            keys={"blind_mapping", "revealed_at", "schema_version"},
        )["blind_mapping"]
    )
    ai_verdicts = dict(ai_verdicts or {})
    if ai_verdicts and evaluation_protocol is None:
        fail(
            "EVALUATION_PROTOCOL_MISMATCH",
            "Consuming AI verdicts requires the registered evaluation "
            "protocol manifest; the pre-revision Promotion Gate keeps "
            "rejecting AI-authored verdicts",
        )
    if ai_verdicts:
        known_case_ids = {facts.case_id for facts in pair_facts}
        for case_id in sorted(ai_verdicts):
            if case_id not in known_case_ids:
                fail(
                    "COMPARISON_IDENTITY_MISMATCH",
                    "An AI verdict belongs to a case outside the reduced matrix",
                    case_id=case_id,
                )
    gates: dict[str, Any] = {}
    decision = "promote"

    # Gate 1: completeness. Every pair must be complete on both arms and
    # carry a frozen verdict bound to these facts' packet.
    completeness_problems: list[dict[str, Any]] = []
    for facts in sorted(pair_facts, key=lambda f: f.pair_index):
        if facts.baseline_metrics is None or facts.challenger_metrics is None:
            completeness_problems.append(
                {"case_id": facts.case_id, "problem": "missing_arm_metrics"}
            )
            continue
        verdict = facts.verdict
        if verdict is None:
            completeness_problems.append(
                {"case_id": facts.case_id, "problem": "missing_verdict"}
            )
        elif verdict.get("packet_sha256") != facts.packet_sha256:
            fail(
                "VERDICT_PACKET_MISMATCH",
                "The verdict is bound to a different pair packet",
                case_id=facts.case_id,
                verdict_packet_sha256=verdict.get("packet_sha256"),
                facts_packet_sha256=facts.packet_sha256,
            )
        elif verdict.get("verdict") == "incomparable":
            completeness_problems.append(
                {"case_id": facts.case_id, "problem": "incomparable_verdict"}
            )
        elif (
            facts.baseline_metrics.terminal_outcome != "success"
            or facts.challenger_metrics.terminal_outcome != "success"
        ):
            completeness_problems.append(
                {"case_id": facts.case_id, "problem": "unsealed_arm_outcome"}
            )
    # One evaluation protocol per reduction: a matrix may not mix AI-authored
    # verdicts with human verdicts (spec §7). When any AI verdict is present,
    # every ingested verdict must be on the AI channel; a reduction without
    # AI verdicts keeps the legacy document byte-identical (no channel book-
    # keeping, no protocol gate).
    verdict_channels: dict[str, str] = {}
    if ai_verdicts:
        for facts in sorted(pair_facts, key=lambda f: f.pair_index):
            if facts.case_id in ai_verdicts:
                if facts.verdict is None:
                    completeness_problems.append(
                        {
                            "case_id": facts.case_id,
                            "problem": "ai_verdict_without_bound_verdict",
                        }
                    )
                    continue
                verdict_channels[facts.case_id] = "ai_pair_reduction"
            elif facts.verdict is not None:
                fail(
                    "EVALUATION_PROTOCOL_MISMATCH",
                    "The reduction mixes AI-authored and human verdicts; all "
                    "eight results must use one evaluation protocol",
                    human_case_id=facts.case_id,
                )
        gates["completeness"] = {
            "pass": not completeness_problems,
            "problems": completeness_problems,
            "verdict_channels": verdict_channels,
        }
    else:
        gates["completeness"] = {
            "pass": not completeness_problems,
            "problems": completeness_problems,
        }
    if completeness_problems:
        decision = "incomplete"
        return _reduction_document(
            decision=decision,
            gates=gates,
            matrix_document=matrix_document,
            mappings=mappings,
            selection_manifest=selection_manifest,
            ledger=ledger,
            reveal=False,
        )

    # Gate 2: quality threshold (3-0 after reveal).
    challenger_wins = 0
    baseline_wins = 0
    pair_outcomes: list[dict[str, Any]] = []
    for facts in sorted(pair_facts, key=lambda f: f.pair_index):
        mapping = _mapping_for_case(mappings, facts.case_id)
        verdict = facts.verdict or {}
        outcome = verdict.get("verdict")
        arm_a_is_baseline = mapping.arm_a_profile_id == BASELINE_PROFILE_ID
        if outcome == "a_better":
            winner = BASELINE_PROFILE_ID if arm_a_is_baseline else CHALLENGER_PROFILE_ID
        elif outcome == "b_better":
            winner = CHALLENGER_PROFILE_ID if arm_a_is_baseline else BASELINE_PROFILE_ID
        else:
            winner = None
        challenger_win = winner == CHALLENGER_PROFILE_ID
        baseline_win = winner == BASELINE_PROFILE_ID
        challenger_wins += int(challenger_win)
        baseline_wins += int(baseline_win)
        pair_outcomes.append(
            {
                "case_id": facts.case_id,
                "pair_index": facts.pair_index,
                "winner": winner,
                "verdict": outcome,
            }
        )
    quality_pass = (
        challenger_wins >= PROMOTION_MIN_CHALLENGER_WINS
        and baseline_wins <= PROMOTION_MAX_BASELINE_WINS
    )
    gates["quality_3_0"] = {
        "baseline_wins": baseline_wins,
        "challenger_wins": challenger_wins,
        "pair_outcomes": pair_outcomes,
        "pass": quality_pass,
    }
    if not quality_pass:
        decision = "reject"

    # Gate 3: domain-method fit (>= 2 challenger-better, 0 baseline-better).
    # The verdict instrument is pair-level: a pair counts as improved only
    # when the challenger arm's fit is strictly better than the baseline
    # arm's (challenger_better), judged on the blinded packet.
    improved = 0
    regressed = 0
    for facts in pair_facts:
        verdict = facts.verdict or {}
        fit = verdict.get("domain_method_fit")
        if fit == "challenger_better":
            improved += 1
        elif fit == "baseline_better":
            regressed += 1
    fit_pass = improved >= DOMAIN_METHOD_MIN_IMPROVED and regressed == 0
    gates["domain_method_fit"] = {
        "improved_pairs": improved,
        "regressed_pairs": regressed,
        "pass": fit_pass,
    }
    if not fit_pass:
        decision = "reject"

    # Gate 4: unjustified ML intrusion cannot increase on any pair
    # (pair-level: the challenger arm's intrusion relative to the baseline
    # arm must not be judged "increased" on the blinded packet).
    intrusion_increased: list[str] = []
    for facts in pair_facts:
        verdict = facts.verdict or {}
        if verdict.get("unjustified_ml_intrusion") == "increased":
            intrusion_increased.append(facts.case_id)
    gates["ml_intrusion"] = {
        "increased_pairs": intrusion_increased,
        "pass": not intrusion_increased,
    }
    if intrusion_increased:
        decision = "reject"

    # Gates 5/5b: the quality floors. Under the AI channel the per-arm floors
    # come from the AI verdict's content-space quality-floor states (the
    # dual-review consensus records), never from the overall preference; a
    # violated floor rejects exactly as a human floor hit would, and an
    # unresolved/not_evaluated floor cannot pass this promotion judgment
    # either (spec §5: 未决状态仍阻止受影响的晋升判断 — the pair may keep
    # collecting evidence, but not be promoted on it).
    floor_hits: list[dict[str, Any]] = []
    unresolved_floors: list[dict[str, Any]] = []
    for facts in pair_facts:
        verdict = facts.verdict or {}
        if facts.case_id in ai_verdicts:
            projected = ai_verdict_to_display(
                ai_verdicts[facts.case_id],
                baseline_run_id=facts.baseline_metrics.run_id,
                challenger_run_id=facts.challenger_metrics.run_id,
                mapping=_mapping_for_case(mappings, facts.case_id),
            )
            arm_states = {
                "baseline": projected["rubric_floor_baseline"],
                "challenger": projected["rubric_floor_challenger"],
            }
            for arm, state in sorted(arm_states.items()):
                if state == "violated":
                    floor_hits.append(
                        {"arm": arm, "case_id": facts.case_id, "value": "violated"}
                    )
                elif state in ("unresolved", "not_evaluated"):
                    unresolved_floors.append(
                        {"arm": arm, "case_id": facts.case_id, "state": state}
                    )
            continue
        floor = verdict.get("rubric_floor", {})
        for arm, value in sorted(floor.items()):
            if (
                value != RUBRIC_FLOOR_CLEAN_VALUE
                and value in RUBRIC_FLOOR_PROBLEM_VALUES
            ):
                floor_hits.append(
                    {"arm": arm, "case_id": facts.case_id, "value": value}
                )
    gates["rubric_floor"] = {"hits": floor_hits, "pass": not floor_hits}
    if floor_hits:
        decision = "reject"

    # Gate 5b (AI channel): record the unresolved floors explicitly so the
    # reduction shows why a complete-unresolved matrix stays unpromotable.
    if ai_verdicts:
        gates["ai_quality_floor_unresolved"] = {
            "unresolved": unresolved_floors,
            "pass": not unresolved_floors,
        }
        if unresolved_floors:
            decision = "reject"

    # Gate 5c (AI channel): the protocol amendment is recorded inside the
    # reduction so the consumed results always disclose the post-first-output
    # revision; the document is not promotion authority by itself.
    if ai_verdicts:
        gates["evaluation_protocol"] = {
            "schema_version": EVALUATION_PROTOCOL_GATE_SCHEMA_VERSION,
            "protocol_id": evaluation_protocol["protocol_id"],
            "revision_disclosure": evaluation_protocol["revision_disclosure"],
            "aggregation_rules_id": evaluation_protocol["aggregation_rules_id"],
            "verdict_channels": verdict_channels,
            "pass": True,
        }

    # Gate 6: deterministic zero-tolerance, recorded honestly. Every arm
    # reaching PairFacts passed all ingestion gates (evidence chain seal,
    # profile and input pins, sanitized export identity, evaluation
    # coverage) fail-closed in ingest_comparison_result, so the
    # pre-registered zero-tolerance criterion is enforced structurally at
    # ingestion; this gate records that enforcement point instead of
    # asserting an always-True per-run flag.
    gates["deterministic_regression"] = {
        "enforced_at": "result_ingestion",
        "ingested_gates": [
            "evidence_chain_seal",
            "profile_and_input_pins",
            "sanitized_export_identity",
            "evaluation_coverage",
        ],
        "problems": [],
        "pass": True,
    }

    # Gate 7: truncation / terminal failure / retry regressions are
    # challenger-only patterns; zero tolerance.
    reliability_problems: list[dict[str, Any]] = []
    for facts in pair_facts:
        baseline = facts.baseline_metrics
        challenger = facts.challenger_metrics
        if baseline is None or challenger is None:
            continue
        if (
            "length" in challenger.finish_reasons
            and "length" not in baseline.finish_reasons
        ):
            reliability_problems.append(
                {"case_id": facts.case_id, "pattern": "challenger_only_truncation"}
            )
        if (
            challenger.terminal_outcome != "success"
            and baseline.terminal_outcome == "success"
        ):
            reliability_problems.append(
                {
                    "case_id": facts.case_id,
                    "pattern": "challenger_only_terminal_failure",
                }
            )
        if challenger.physical_attempt_count > baseline.physical_attempt_count:
            reliability_problems.append(
                {"case_id": facts.case_id, "pattern": "challenger_only_retry_increase"}
            )
    gates["reliability"] = {
        "problems": reliability_problems,
        "pass": not reliability_problems,
    }
    if reliability_problems:
        decision = "reject"

    # Gate 8: cost and median-latency envelopes (2.0x).
    baseline_cost = sum(
        (
            facts.baseline_metrics.actual_cost_cny
            for facts in pair_facts
            if facts.baseline_metrics is not None
        ),
        Decimal("0.00"),
    )
    challenger_cost = sum(
        (
            facts.challenger_metrics.actual_cost_cny
            for facts in pair_facts
            if facts.challenger_metrics is not None
        ),
        Decimal("0.00"),
    )
    baseline_latencies = sorted(
        float(facts.baseline_metrics.end_to_end_latency_ms)
        for facts in pair_facts
        if facts.baseline_metrics is not None
    )
    challenger_latencies = sorted(
        float(facts.challenger_metrics.end_to_end_latency_ms)
        for facts in pair_facts
        if facts.challenger_metrics is not None
    )
    baseline_median = (
        Decimal(str(statistics.median(baseline_latencies)))
        if baseline_latencies
        else Decimal("0")
    )
    challenger_median = (
        Decimal(str(statistics.median(challenger_latencies)))
        if challenger_latencies
        else Decimal("0")
    )
    cost_ok = challenger_cost <= baseline_cost * COST_ENVELOPE_FACTOR
    latency_ok = (
        challenger_latencies
        and challenger_median <= baseline_median * LATENCY_ENVELOPE_FACTOR
    )
    gates["cost_latency_envelope"] = {
        "baseline_cost_cny": str(_quantize_cny(baseline_cost)),
        "challenger_cost_cny": str(_quantize_cny(challenger_cost)),
        "baseline_median_latency_ms": str(baseline_median),
        "challenger_median_latency_ms": str(challenger_median),
        "pass": cost_ok and latency_ok,
    }
    if not (cost_ok and latency_ok):
        decision = "reject"

    # Gate 9: the 30 CNY hard cap. The 5 CNY control is a pre-next-run
    # reapproval threshold, not a post-hoc quality rejection threshold: an
    # individually approved run may cross it before the ledger can know its
    # actual cost. The reducer records whether that happened, while only a
    # true hard-cap breach rejects the comparison.
    total_spend, threshold = _validate_ledger_arithmetic(
        ledger,
        matrix_document=matrix_document,
    )
    budget_ok = total_spend <= CANARY_HARD_CAP_CNY
    gates["budget"] = {
        "comparison_actual_spend_cny": str(_quantize_cny(ledger_current_spend(ledger))),
        "historical_spend_cny": str(
            _money(ledger["historical_spend_cny"], label="historical_spend_cny")
        ),
        "plan_gate_reapproval_threshold_cny": str(threshold),
        "reapproval_threshold_reached": total_spend >= threshold,
        "total_stage_spend_cny": str(_quantize_cny(total_spend)),
        "pass": budget_ok,
    }
    if not budget_ok:
        decision = "reject"

    return _reduction_document(
        decision=decision,
        gates=gates,
        matrix_document=matrix_document,
        mappings=mappings,
        selection_manifest=selection_manifest,
        ledger=ledger,
        reveal=True,
    )


def _mapping_for_case(
    mappings: tuple[BlindPairMapping, ...], case_id: str
) -> BlindPairMapping:
    for mapping in mappings:
        if mapping.case_id == case_id:
            return mapping
    fail("MISSING_BLIND_MAPPING", "The reveal lacks the pair mapping", case_id=case_id)


def _reduction_document(
    *,
    decision: str,
    gates: dict[str, Any],
    matrix_document: dict[str, Any],
    mappings: tuple[BlindPairMapping, ...],
    selection_manifest: dict[str, Any],
    ledger: dict[str, Any],
    reveal: bool,
) -> dict[str, Any]:
    revealed_pairs = (
        [
            {
                "arm_a_profile_id": mapping.arm_a_profile_id,
                "arm_b_profile_id": mapping.arm_b_profile_id,
                "case_id": mapping.case_id,
                "pair_index": mapping.pair_index,
            }
            for mapping in sorted(mappings, key=lambda m: m.pair_index)
        ]
        if reveal
        else None
    )
    document = {
        "decision": decision,
        "gates": gates,
        "matrix_sha256": matrix_document["matrix_sha256"],
        "revealed_pair_profiles": revealed_pairs,
        "schema_version": REDUCTION_SCHEMA_VERSION,
        "selection_manifest_sha256": sha256_bytes(
            canonical_json_bytes(selection_manifest)
        ),
    }
    return document


def freeze_prompt_comparison_package(
    workspace_root: Path,
    *,
    plan_gate_reapproval_threshold_cny: Decimal = (
        DEFAULT_PROMPT_COMPARISON_REAPPROVAL_THRESHOLD_CNY
    ),
    target_dir: Path | None = None,
) -> dict[str, Any]:
    """Materialize the full deterministic 4-pair comparison package to disk.

    Performs:
    1. Loads 12 approved Canary cases and verifies workshops, corpora, and manifests.
    2. Deterministically selects 4 cases (one per pre-registered cluster).
    3. Builds selection manifest and selection approval artifacts.
    4. Builds 4-pair / 8-run frozen matrix (2/2 order balance, self-pinning).
    5. Builds frozen blind mapping (2/2 A/B balance).
    6. Builds exact credential-free guarded slot commands.
    7. Initializes the spend ledger over the recorded 0.14 CNY historical
       Canary-stage opening balance, with the Plan Gate reapproval threshold.
    8. Materializes artifacts to target_dir with idempotent byte-identical safety.
    9. Sets up ComparisonVault for results, pair packets, verdicts, reveal, and reducer.
    """
    canary_cases, target_source, input_pins = load_approved_canary_cases(workspace_root)

    selected = select_comparison_cases(
        canary_cases,
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=target_source,
    )

    selection_manifest = build_selection_manifest(
        selected,
        canary_selection_manifest_sha256=APPROVED_CANARY_SELECTION_MANIFEST_SHA256,
        target_source=target_source,
    )

    selection_approval = build_selection_approval(
        selection_manifest=selection_manifest,
        input_pins=input_pins,
    )

    runs, pairs = build_frozen_matrix(selected, selection_manifest=selection_manifest)

    matrix_document = build_matrix_document(
        runs,
        pairs,
        selection_manifest=selection_manifest,
        input_pins=input_pins,
    )

    mappings = build_blind_mapping(pairs, selection_manifest=selection_manifest)
    blind_document = blind_mapping_document(
        mappings, selection_manifest=selection_manifest
    )

    command_package_dir = (
        target_dir if target_dir is not None else DEFAULT_COMPARISON_PACKAGE_DIR
    )
    commands = build_comparison_commands(
        runs,
        matrix_document=matrix_document,
        package_dir=command_package_dir,
        plan_gate_reapproval_threshold_cny=plan_gate_reapproval_threshold_cny,
    )
    commands_text = "\n".join(commands) + "\n"

    ledger = initialize_comparison_ledger(
        matrix_document=matrix_document,
        plan_gate_reapproval_threshold_cny=plan_gate_reapproval_threshold_cny,
        historical_spend_cny=CANARY_STAGE_HISTORICAL_SPEND_CNY,
    )

    pkg_dir = (
        target_dir
        if target_dir is not None
        else (workspace_root / DEFAULT_COMPARISON_PACKAGE_DIR)
    )
    pkg_dir.mkdir(parents=True, exist_ok=True)

    files_to_write: list[tuple[str, bytes]] = [
        ("selection-manifest.json", canonical_json_bytes(selection_manifest)),
        ("selection-approval.json", canonical_json_bytes(selection_approval)),
        ("run-matrix.json", canonical_json_bytes(matrix_document)),
        ("blind-mapping.json", canonical_json_bytes(blind_document)),
        ("spend-ledger.json", canonical_json_bytes(ledger)),
        ("commands.txt", commands_text.encode("utf-8")),
    ]

    artifact_records: dict[str, dict[str, str]] = {}
    for filename, content_bytes in files_to_write:
        dest = pkg_dir / filename
        content_hash = sha256_bytes(content_bytes)
        if dest.is_file():
            existing_bytes = dest.read_bytes()
            if existing_bytes != content_bytes:
                fail(
                    "PACKAGE_DRIFT",
                    f"Existing artifact drifted from frozen package: {filename}",
                    path=str(dest),
                    existing_sha256=sha256_bytes(existing_bytes),
                    expected_sha256=content_hash,
                )
        else:
            dest.write_bytes(content_bytes)
        key_name = filename.replace(".json", "").replace(".txt", "").replace("-", "_")
        try:
            rel_path = str(dest.relative_to(workspace_root))
        except ValueError:
            rel_path = str(dest)
        artifact_records[key_name] = {
            "path": rel_path,
            "sha256": content_hash,
        }

    # Initialize vault
    vault_dir = pkg_dir / "vault"
    ComparisonVault(vault_dir)

    return {
        "artifacts": artifact_records,
        "commands": commands,
        "first_command": commands[0],
        "frozen_matrix_digest": matrix_document["matrix_sha256"],
        "plan_gate_reapproval_threshold_cny": str(plan_gate_reapproval_threshold_cny),
        "selected_cases": tuple(c.case_id for c in selected),
    }
