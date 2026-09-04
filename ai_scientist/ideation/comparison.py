"""Offline Prompt-Profile comparison boundary (ticket 02).

One deterministic, credential-free boundary that proves the governed
cross-domain prompt comparison end to end on synthetic sealed evidence:
four-case subset selection from the approved 12-case Canary, the frozen
4-pair/8-run matrix, the frozen blind mapping and sanitized pair packets,
the append-only spend ledger with the Plan Gate sub-cap arithmetic,
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
from typing import Any

from .admission import DEFAULT_MAX_TOKENS, MAX_ATTEMPTS_PER_OPERATION
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
SELECTION_MANIFEST_SCHEMA_VERSION = "comparison-selection-manifest-v1.0.0"
SELECTION_APPROVAL_SCHEMA_VERSION = "comparison-selection-approval-v1.0.0"
SPEND_LEDGER_SCHEMA_VERSION = "comparison-spend-ledger-v1.0.0"
VERDICT_SCHEMA_VERSION = "comparison-pair-verdict-v1.0.0"
REDUCTION_SCHEMA_VERSION = "comparison-reduction-v1.0.0"
RUN_RESULT_SCHEMA_VERSION = "comparison-run-result-v1.0.0"

DEFAULT_PROMPT_COMPARISON_SUBCAP_CNY = Decimal("5.00")
DEFAULT_COMPARISON_PACKAGE_DIR = (
    Path("artifacts")
    / "ideation-inputs"
    / "comparisons"
    / "002-cross-domain-ideation-prompt"
)

VERDICT_ENUM: frozenset[str] = frozenset(
    {"a_better", "b_better", "tie", "incomparable"}
)
DOMAIN_METHOD_FIT_ENUM: frozenset[str] = frozenset(
    {"improved", "unchanged", "worse", "incomparable"}
)
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

_IDEA_INVENTORY_PATTERN = re.compile(r"artifacts/ideas/(\d{6})/idea\.json\Z")
_MONEY_PATTERN = re.compile(r"\d+\.\d{2}\Z")


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
    snapshot (row hash and dataset hash drift fail closed). The winner per
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

    baseline_first: list[CanaryCase] = []
    challenger_first: list[CanaryCase] = []
    for case in selected_cases:
        digest = _canonical_seed_hex("arm_order", f"{seed}|{case.case_id}")
        (baseline_first if int(digest[0], 16) % 2 == 0 else challenger_first).append(
            case
        )

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
    payloads (A/B). The structure scan walks the serialized packet's keys
    and non-idea values: any forbidden operational-metadata key, or a
    profile identity value appearing anywhere outside the idea payloads,
    fails closed. Model-generated idea text is never scanned — legitimate
    English words in a proposal are not blinding leaks.
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
        "arm_a": {"idea": idea_a},
        "arm_b": {"idea": idea_b},
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


# ==========================================================================
# Credential-free exact commands (production parser surface only)
# ==========================================================================

CREDENTIAL_WRAPPER = "scripts/with-project-env"
ENTRY_SCRIPT = "ai_scientist/perform_ideation_temp_free.py"


def build_comparison_commands(
    runs: tuple[ComparisonRun, ...],
    *,
    matrix_document: dict[str, Any],
) -> tuple[str, ...]:
    """Exact credential-free commands, one per planned run, in run order.

    Only production-parser arguments are used; the credential wrapper is
    the project's `scripts/with-project-env` launcher (never an env
    assignment, never a key, never an auto-`yes` pipe). The command text is
    validated against the production parser contract.
    """
    runs_by_pair: dict[int, list[ComparisonRun]] = {}
    for run in runs:
        runs_by_pair.setdefault(run.pair_index, []).append(run)
    commands: list[str] = []
    for run_index in range(1, len(runs) + 1):
        run = next(r for r in runs if r.run_index == run_index)
        matrix_run = _matrix_run_entry(matrix_document, run.run_index)
        parts = [
            "python",
            CREDENTIAL_WRAPPER,
            "--",
            "python",
            ENTRY_SCRIPT,
            "new-run",
            "--case-id",
            run.case_id,
            "--workshop",
            matrix_run["workshop"]["path"],
            "--workshop-sha256",
            matrix_run["workshop"]["sha256"],
            "--corpus",
            matrix_run["corpus"]["path"],
            "--corpus-sha256",
            matrix_run["corpus"]["sha256"],
            "--max-num-generations",
            str(run.max_num_generations),
            "--num-reflections",
            str(run.num_reflections),
            "--prompt-profile",
            run.profile_id,
        ]
        command = " ".join(shlex_quote(part) for part in parts)
        commands.append(command)
    for command in commands:
        _assert_command_contract(command)
    return tuple(commands)


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


def _assert_command_contract(command: str) -> None:
    """Fail closed on any command shape the production parser rejects."""
    from ai_scientist.perform_ideation_temp_free import _build_parser

    tokens = shlex.split(command)
    # Strip "python <wrapper> -- python <entry>" prefix down to the entry
    # module invocation the production parser understands.
    if len(tokens) < 2 or tokens[0] != "python":
        fail("COMMAND_SHAPE_INVALID", "The command must start with the python launcher")
    if "--" in tokens:
        dash_index = tokens.index("--")
        tokens = tokens[dash_index + 1 :]
    if tokens[:2] != ["python", ENTRY_SCRIPT]:
        fail(
            "COMMAND_SHAPE_INVALID", "The command does not invoke the production entry"
        )
    parser = _build_parser()
    try:
        parsed = parser.parse_args(tokens[2:])
    except SystemExit:
        fail(
            "COMMAND_NOT_PARSER_SUPPORTED",
            "A frozen command carries arguments the production parser rejects",
            command=command,
        )
    if parsed.entry != "new-run":
        fail("COMMAND_SHAPE_INVALID", "The command must be a new-run invocation")
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
        "schema_version": "comparison-commands-v1.0.0",
    }


# ==========================================================================
# Append-only spend ledger with Plan Gate arithmetic
# ==========================================================================


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One immutable per-run actual-cost ingest record."""

    run_index: int
    pair_index: int
    case_id: str
    profile_id: str
    run_id: str
    status: str
    actual_cost_cny: Decimal
    worst_case_bound_cny: Decimal
    physical_attempt_count: int


def initialize_comparison_ledger(
    *,
    matrix_document: dict[str, Any],
    plan_gate_subcap_cny: Decimal,
) -> dict[str, Any]:
    """Start the append-only ledger at 0.00 CNY with the frozen bounds."""
    if not isinstance(plan_gate_subcap_cny, Decimal) or plan_gate_subcap_cny <= 0:
        fail("INVALID_SUBCAP", "The Plan Gate sub-cap must be a positive decimal")
    if plan_gate_subcap_cny > CANARY_HARD_CAP_CNY:
        fail(
            "SUBCAP_EXCEEDS_CANARY_CAP",
            "The Plan Gate sub-cap cannot exceed the 30.00 CNY Canary hard cap",
            subcap=str(plan_gate_subcap_cny),
            canary_cap=str(CANARY_HARD_CAP_CNY),
        )
    return {
        "canary_hard_cap_cny": str(CANARY_HARD_CAP_CNY),
        "current_actual_spend_cny": str(LEDGER_INIT_SPEND_CNY),
        "entries": [],
        "matrix_sha256": matrix_sha256(matrix_document),
        "plan_gate_subcap_cny": str(plan_gate_subcap_cny),
        "planned_runs_count": matrix_document["planned_runs_count"],
        "schema_version": SPEND_LEDGER_SCHEMA_VERSION,
        "status": "initialized",
    }


def ledger_current_spend(ledger: dict[str, Any]) -> Decimal:
    return _money(
        ledger.get("current_actual_spend_cny"), label="current_actual_spend_cny"
    )


def _ledger_entry_cost(entry: dict[str, Any]) -> Decimal:
    return _money(entry["actual_cost_cny"], label="ledger entry actual_cost_cny")


def plan_gate_next_run_allowed(
    ledger: dict[str, Any],
    *,
    next_run_worst_case_bound_cny: Decimal,
) -> bool:
    """The frozen Plan Gate rule, evaluated exactly.

    `cumulative_actual_spend + next_run_worst_case_bound <= subcap` and
    `<= 30.00 CNY`. An exact bound to the cap is accepted; one cent over is
    refused. The Plan Gate approval is the matrix-level authorization, not
    a per-run approval: this gate never waives the per-run interactive
    cost approval that preflight requires.
    """
    subcap = _money(ledger["plan_gate_subcap_cny"], label="plan_gate_subcap_cny")
    spend = ledger_current_spend(ledger)
    projected = spend + next_run_worst_case_bound_cny
    return projected <= subcap and projected <= CANARY_HARD_CAP_CNY


def plan_gate_one_cent_over(ledger: dict[str, Any], *, next_bound: Decimal) -> bool:
    """True exactly when the next run would exceed the cap by >= one cent."""
    return not plan_gate_next_run_allowed(
        ledger, next_run_worst_case_bound_cny=next_bound
    )


def ingest_run_actual_cost(
    ledger: dict[str, Any],
    *,
    entry: LedgerEntry,
) -> dict[str, Any]:
    """Append one per-run actual-cost record; the ledger is append-only."""
    if ledger.get("status") not in ("initialized", "ingesting"):
        fail("LEDGER_CLOSED", "The ledger is not accepting run ingests")
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
    spend = ledger_current_spend(ledger)
    new_spend = _quantize_cny(spend + entry.actual_cost_cny)
    if new_spend > CANARY_HARD_CAP_CNY:
        fail(
            "BUDGET_EXCEEDED",
            "Ingesting this run would exceed the 30.00 CNY Canary hard cap",
            current=str(spend),
            run_cost=str(entry.actual_cost_cny),
        )
    record = {
        "actual_cost_cny": str(_quantize_cny(entry.actual_cost_cny)),
        "case_id": entry.case_id,
        "physical_attempt_count": entry.physical_attempt_count,
        "profile_id": entry.profile_id,
        "run_id": entry.run_id,
        "run_index": entry.run_index,
        "status": entry.status,
        "worst_case_bound_cny": str(_quantize_cny(entry.worst_case_bound_cny)),
    }
    updated = dict(ledger)
    updated["entries"] = list(ledger["entries"]) + [record]
    updated["current_actual_spend_cny"] = str(new_spend)
    updated["ingested_runs_count"] = len(updated["entries"])
    updated["status"] = "ingesting"
    return updated


def plan_gate_approval_document(
    *,
    ledger: dict[str, Any],
    approved_by: str,
) -> dict[str, Any]:
    """Record the Plan Gate approval of the comparison matrix.

    The approval authorizes the whole governed matrix inside the sub-cap;
    it is explicitly NOT a per-run approval: each run's preflight still
    requires Robert's interactive `yes` (spec user story 47).
    """
    approved_by = nonempty_string(approved_by, label="approved_by")
    subcap = _money(ledger["plan_gate_subcap_cny"], label="plan_gate_subcap_cny")
    document = {
        "approved_by": approved_by,
        "canary_hard_cap_cny": str(CANARY_HARD_CAP_CNY),
        "current_actual_spend_cny": str(ledger_current_spend(ledger)),
        "plan_gate_subcap_cny": str(subcap),
        "planned_runs_count": ledger["planned_runs_count"],
        "schema_version": "comparison-plan-gate-approval-v1.0.0",
        "scope": "matrix_level_only_not_per_run",
    }
    return document


def plan_gate_does_not_waive_per_run_approval(approval: dict[str, Any]) -> bool:
    """Machine check: the recorded approval carries the no-waive scope."""
    return approval.get("scope") == "matrix_level_only_not_per_run"


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
    deterministic_validation_passed: bool


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
) -> RunMetrics:
    """Ingest one sealed comparison run, fail closed on any drift.

    Validates Run Specification/profile identity, case/input hashes, Run
    Seal, Evidence Chain, sanitized export, Evaluation Artifact coverage,
    finish reasons, attempt topology, latency, and actual cost before the
    result may feed a pair packet or the reducer.
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

    # 4. Evaluation Artifact coverage (VM-QUAL-01 semantics).
    coverage = _evaluation_coverage_for_run(workspace, run_id)
    if coverage is None:
        fail(
            "EVALUATION_ARTIFACT_MISSING",
            "The comparison run lacks a complete Evaluation Artifact",
            run_id=run_id,
        )

    # 5. Derive run metrics from the sealed chain.
    derived = _sealed_run_metrics(store, run_id)
    seal = derived["seal"]
    # Deterministic validation verdict: the gates this ingestion itself ran
    # (chain, seal, export, coverage, identity pins) must all have passed to
    # reach this point; the flag records that verdict for the reducer's
    # zero-tolerance gate rather than asserting it unconditionally.
    deterministic_pass = (
        validation.get("status") == "valid"
        and sanitized_profile.get("profile_id") == expected_profile_id
        and sanitized.get("case_id") == expected_case_id
        and coverage is True
    )
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
        deterministic_validation_passed=deterministic_pass,
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


def _evaluation_coverage_for_run(workspace: Path, run_id: str) -> bool:
    """Deterministic VM-QUAL-01 style check: one covered idea minimum."""
    from .evaluation import list_evaluation_coverage

    try:
        coverage = list_evaluation_coverage(workspace)
    except IdeationInputError:
        return False
    for run_entry in coverage.get("runs", []):
        if run_entry.get("run_id") != run_id:
            continue
        if run_entry.get("status") != "evaluable":
            return False
        ideas = run_entry.get("ideas", [])
        return any(idea.get("state") == "covered" for idea in ideas)
    return False


# ==========================================================================
# Write-once verdicts and the fail-closed reveal gate
# ==========================================================================


@dataclass(frozen=True, slots=True)
class PairVerdict:
    """Robert's write-once blinded verdict for one pair."""

    case_id: str
    verdict: str
    overall_rationale: str
    domain_method_fit: dict[str, str]
    unjustified_ml_intrusion: dict[str, str]
    rubric_floor: dict[str, str]
    recorded_at: str


def verdict_document(verdict: PairVerdict, *, packet_sha256: str) -> dict[str, Any]:
    """Serialize one verdict; closed enums, non-empty rationale."""
    if verdict.verdict not in VERDICT_ENUM:
        fail(
            "INVALID_VERDICT",
            "The pair verdict must use the closed outcome enum",
            verdict=verdict.verdict,
        )
    if not verdict.overall_rationale.strip():
        fail("INVALID_VERDICT", "The overall rationale must be a non-empty string")
    for label, mapping in (
        ("domain_method_fit", verdict.domain_method_fit),
        ("unjustified_ml_intrusion", verdict.unjustified_ml_intrusion),
        ("rubric_floor", verdict.rubric_floor),
    ):
        if set(mapping) != {"arm_a", "arm_b"}:
            fail(
                "INVALID_VERDICT",
                f"{label} must cover both blind arms",
            )
        enum = {
            "domain_method_fit": DOMAIN_METHOD_FIT_ENUM,
            "unjustified_ml_intrusion": ML_INTRUSION_ENUM,
        }.get(label)
        if enum is not None:
            for arm, value in mapping.items():
                if value not in enum:
                    fail(
                        "INVALID_VERDICT",
                        f"{label}.{arm} is not in the closed enum",
                        value=value,
                    )
        else:
            for arm, value in mapping.items():
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
        "domain_method_fit": dict(verdict.domain_method_fit),
        "overall_rationale": verdict.overall_rationale,
        "packet_sha256": packet_sha256,
        "recorded_at": verdict.recorded_at,
        "rubric_floor": dict(verdict.rubric_floor),
        "schema_version": VERDICT_SCHEMA_VERSION,
        "unjustified_ml_intrusion": dict(verdict.unjustified_ml_intrusion),
        "verdict": verdict.verdict,
    }
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


# ==========================================================================
# Deterministic Promotion reducer
# ==========================================================================


@dataclass(frozen=True, slots=True)
class PairFacts:
    """The ingested, revealed facts of one pair feeding the reducer."""

    pair_index: int
    case_id: str
    cluster: str
    baseline_metrics: RunMetrics | None
    challenger_metrics: RunMetrics | None
    verdict: dict[str, Any] | None


def reduce_prompt_comparison(
    *,
    selection_manifest: dict[str, Any],
    matrix_document: dict[str, Any],
    reveal_document: dict[str, Any],
    pair_facts: tuple[PairFacts, ...],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    """Reduce the blinded comparison against the pre-registered criteria.

    The reducer is a pure, deterministic function of the ingested facts,
    the frozen matrix, the write-once reveal document, and the ledger
    state. The blind mapping is consumed only through `reveal_document` —
    the write-once `reveal.json` a ComparisonVault commits after every
    available verdict is frozen — so a reduction can never see the blind
    identity before the fail-closed reveal gate opened it. The same inputs
    reduce to byte-identical output.
    """
    mappings = assert_blind_mapping_document_shape(
        closed_object(
            reveal_document,
            label="reveal document",
            keys={"blind_mapping", "revealed_at", "schema_version"},
        )["blind_mapping"]
    )
    selected_case_ids = sorted({pair.case_id for pair in pair_facts})
    gates: dict[str, Any] = {}
    decision = "promote"

    # Gate 1: completeness. Every pair must be complete on both arms and
    # carry a frozen verdict.
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

    # Gate 3: domain-method fit (>= 2 improved, 0 regressed).
    improved = 0
    regressed = 0
    for facts in pair_facts:
        verdict = facts.verdict or {}
        fit = verdict.get("domain_method_fit", {})
        challenger_fit = _arm_value_for_challenger(facts.case_id, mappings, fit)
        baseline_fit = _arm_value_for_baseline(facts.case_id, mappings, fit)
        if challenger_fit == "improved" and baseline_fit != "improved":
            improved += 1
        if challenger_fit == "worse":
            regressed += 1
    fit_pass = improved >= DOMAIN_METHOD_MIN_IMPROVED and regressed == 0
    gates["domain_method_fit"] = {
        "improved_pairs": improved,
        "regressed_pairs": regressed,
        "pass": fit_pass,
    }
    if not fit_pass:
        decision = "reject"

    # Gate 4: unjustified ML intrusion cannot increase on any pair.
    intrusion_increased: list[str] = []
    for facts in pair_facts:
        verdict = facts.verdict or {}
        intrusion = verdict.get("unjustified_ml_intrusion", {})
        challenger_value = _arm_value_for_challenger(facts.case_id, mappings, intrusion)
        if challenger_value == "increased":
            intrusion_increased.append(facts.case_id)
    gates["ml_intrusion"] = {
        "increased_pairs": intrusion_increased,
        "pass": not intrusion_increased,
    }
    if intrusion_increased:
        decision = "reject"

    # Gate 5: the existing rubric floor (any problem value on either arm).
    floor_hits: list[dict[str, Any]] = []
    for facts in pair_facts:
        verdict = facts.verdict or {}
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

    # Gate 6: deterministic zero-tolerance (ingestion verdicts).
    deterministic_problems: list[dict[str, Any]] = []
    for facts in pair_facts:
        baseline = facts.baseline_metrics
        challenger = facts.challenger_metrics
        if baseline is None or challenger is None:
            continue
        if baseline.deterministic_validation_passed and not (
            challenger.deterministic_validation_passed
        ):
            deterministic_problems.append(
                {"case_id": facts.case_id, "pattern": "baseline_pass_challenger_fail"}
            )
    gates["deterministic_regression"] = {
        "problems": deterministic_problems,
        "pass": not deterministic_problems,
    }
    if deterministic_problems:
        decision = "reject"

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

    # Gate 9: the frozen spend bounds (sub-cap, then the 30 CNY cap).
    spend = ledger_current_spend(ledger)
    subcap = _money(ledger["plan_gate_subcap_cny"], label="plan_gate_subcap_cny")
    budget_ok = spend <= subcap and spend <= CANARY_HARD_CAP_CNY
    gates["budget"] = {
        "current_actual_spend_cny": str(_quantize_cny(spend)),
        "plan_gate_subcap_cny": str(subcap),
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


def _arm_value_for_challenger(
    case_id: str, mappings: tuple[BlindPairMapping, ...], arm_values: dict[str, Any]
) -> Any:
    mapping = _mapping_for_case(mappings, case_id)
    arm = "arm_a" if mapping.arm_a_profile_id == CHALLENGER_PROFILE_ID else "arm_b"
    return arm_values.get(arm)


def _arm_value_for_baseline(
    case_id: str, mappings: tuple[BlindPairMapping, ...], arm_values: dict[str, Any]
) -> Any:
    mapping = _mapping_for_case(mappings, case_id)
    arm = "arm_a" if mapping.arm_a_profile_id == BASELINE_PROFILE_ID else "arm_b"
    return arm_values.get(arm)


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
    plan_gate_subcap_cny: Decimal = DEFAULT_PROMPT_COMPARISON_SUBCAP_CNY,
    target_dir: Path | None = None,
) -> dict[str, Any]:
    """Materialize the full deterministic 4-pair comparison package to disk.

    Performs:
    1. Loads 12 approved Canary cases and verifies workshops, corpora, and manifests.
    2. Deterministically selects 4 cases (one per pre-registered cluster).
    3. Builds selection manifest and selection approval artifacts.
    4. Builds 4-pair / 8-run frozen matrix (2/2 order balance, self-pinning).
    5. Builds frozen blind mapping (2/2 A/B balance).
    6. Builds exact credential-free CLI commands.
    7. Initializes 0.00 CNY spend ledger with sub-cap.
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

    commands = build_comparison_commands(runs, matrix_document=matrix_document)
    commands_text = "\n".join(commands) + "\n"

    ledger = initialize_comparison_ledger(
        matrix_document=matrix_document,
        plan_gate_subcap_cny=plan_gate_subcap_cny,
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
        "plan_gate_subcap_cny": str(plan_gate_subcap_cny),
        "selected_cases": tuple(c.case_id for c in selected),
    }
