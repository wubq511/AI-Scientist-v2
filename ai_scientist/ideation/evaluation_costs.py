"""Separate, hash-linked, append-only AI review cost ledger (ticket 03).

AI review call costs (single reviews, pairwise blind reviews, and repair
calls) are recorded in their own append-only ledger instead of the
generation spend ledger (`comparison-spend-ledger-v1.3.0`). Keeping the two
ledgers separate means a review spend can never rewrite generation history,
and the merged view is a read-only report that never extends the old
generation budget silently: review costs are disclosed as NOT covered by
the generation Plan Gate approval and require Robert's separate explicit
authorization.

The ledger document is closed and re-validated on every load: the running
total is recomputed from the entries, and the entries are hash-linked — the
document's ``last_entry_sha256`` must equal the SHA-256 of the canonical
bytes of the last entry document (None while the ledger is empty).
Recording is append-only (each entry's ``entry_seq`` continues the 1-based
sequence and equals ``len(entries) + 1``), and persisting re-checks the
on-disk ledger for concurrent modification before overwriting the ledger
file.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from pathlib import Path
import re
from typing import Any

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import EVALUATION_ROOT_RELPATH, _now
from .errors import fail
from .evaluation import _write_bytes_once, _write_bytes_overwrite
from .run_store import _fsync_directory
from .schema import closed_object, nonempty_string, timestamp

EVALUATION_COST_LEDGER_SCHEMA_VERSION = "evaluation-cost-ledger-v1.0.0"
EVALUATION_COST_LEDGER_NAME = "evaluation-cost-ledger.json"

# Closed call kinds that produce a billable AI review call.
EVALUATION_CALL_KINDS: frozenset[str] = frozenset(
    {"single_review", "pair_review", "repair"}
)

LEDGER_TOP_KEYS: frozenset[str] = frozenset(
    {
        "created_at",
        "created_by",
        "entries",
        "last_entry_sha256",
        "schema_version",
        "status",
        "total_cost_cny",
    }
)
ENTRY_KEYS: frozenset[str] = frozenset(
    {
        "call_kind",
        "cost_cny",
        "entry_seq",
        "idea_index",
        "model_id",
        "note",
        "pair_id",
        "physical_call_count",
        "provider",
        "recorded_at",
        "recorded_by",
        "responded_at",
        "run_id",
    }
)

# Strict decimal CNY strings (mirrors comparison.py's `_MONEY_PATTERN`):
# non-negative, exactly two fraction digits, so money never silently loses
# precision and never carries more than two fraction digits.
_MONEY_PATTERN = re.compile(r"\d+\.\d{2}\Z")
MONEY_QUANTUM = Decimal("0.01")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

MERGE_REPORT_SCHEMA_VERSION = "evaluation-cost-merged-report-v1.0.0"

# The generation money fields carried as-is into the merged report: the
# historical opening balance, the tracked comparison actual spend, the
# forfeited spend, the stage total, the Canary hard cap, and the Plan Gate
# reapproval threshold all stay verbatim. The report never rewrites them.
GENERATION_MONEY_FIELDS: tuple[str, ...] = (
    "historical_spend_cny",
    "comparison_actual_spend_cny",
    "forfeited_spend_cny",
    "total_stage_spend_cny",
    "canary_hard_cap_cny",
    "plan_gate_reapproval_threshold_cny",
)

UNAUTHORIZED_SPEND_DISCLOSURE = (
    "AI review call costs are NOT covered by the generation Plan Gate "
    "approval recorded in the generation spend ledger; they require "
    "Robert's separate, explicit authorization."
)
MERGE_NOTES: tuple[str, ...] = (
    "The merged view is read-only and never rewrites generation history.",
    "AI review costs never silently extend the generation budget.",
)


def _money(value: object, *, label: str) -> Decimal:
    if not isinstance(value, str) or not _MONEY_PATTERN.fullmatch(value):
        fail("INVALID_MONEY", f"{label} must be a decimal CNY amount string")
    return Decimal(value)


def _quantize_cny(amount: Decimal) -> Decimal:
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_CEILING)


def _check_entry(value: object, *, index: int) -> dict[str, Any]:
    """Closed validation of one ledger entry."""
    entry = closed_object(value, label=f"entries[{index}]", keys=ENTRY_KEYS)
    entry_seq = entry["entry_seq"]
    if not isinstance(entry_seq, int) or isinstance(entry_seq, bool) or entry_seq < 1:
        fail(
            "INVALID_SCHEMA",
            f"entries[{index}].entry_seq must be a positive integer",
        )
    if entry_seq != index + 1:
        fail(
            "EVALUATION_COST_LEDGER_ARITHMETIC",
            "Entry sequences must be 1-based and sequential",
            entry_seq=entry_seq,
            expected=index + 1,
        )
    call_kind = entry["call_kind"]
    if call_kind not in EVALUATION_CALL_KINDS:
        fail(
            "INVALID_SCHEMA",
            f"entries[{index}].call_kind must be one of "
            f"{sorted(EVALUATION_CALL_KINDS)}",
        )
    nonempty_string(entry["provider"], label=f"entries[{index}].provider")
    nonempty_string(entry["model_id"], label=f"entries[{index}].model_id")
    nonempty_string(entry["recorded_by"], label=f"entries[{index}].recorded_by")
    timestamp(entry["responded_at"], label=f"entries[{index}].responded_at")
    timestamp(entry["recorded_at"], label=f"entries[{index}].recorded_at")
    run_id = entry["run_id"]
    if run_id is not None:
        nonempty_string(run_id, label=f"entries[{index}].run_id")
        if call_kind == "pair_review":
            fail(
                "INVALID_SCHEMA",
                f"entries[{index}].run_id must be null for a pair review",
            )
    pair_id = entry["pair_id"]
    if pair_id is not None:
        nonempty_string(pair_id, label=f"entries[{index}].pair_id")
    idea_index = entry["idea_index"]
    if idea_index is not None and (
        not isinstance(idea_index, int)
        or isinstance(idea_index, bool)
        or idea_index < 0
    ):
        fail(
            "INVALID_SCHEMA",
            f"entries[{index}].idea_index must be null or a non-negative integer",
        )
    physical_call_count = entry["physical_call_count"]
    if (
        not isinstance(physical_call_count, int)
        or isinstance(physical_call_count, bool)
        or physical_call_count < 1
    ):
        fail(
            "INVALID_SCHEMA",
            f"entries[{index}].physical_call_count must be an integer >= 1",
        )
    _money(entry["cost_cny"], label=f"entries[{index}].cost_cny")
    note = entry["note"]
    if note is not None:
        nonempty_string(note, label=f"entries[{index}].note")
    return entry


def _validate_cost_ledger(document: object) -> dict[str, Any]:
    """Full closed re-validation of the evaluation cost ledger.

    Rechecks the closed shape, the schema version, the sequential entry
    identities, the recomputed total, and the hash-linked
    ``last_entry_sha256`` (recomputed from the last entry's canonical bytes).
    """
    ledger = closed_object(
        document, label="evaluation cost ledger", keys=LEDGER_TOP_KEYS
    )
    if ledger["schema_version"] != EVALUATION_COST_LEDGER_SCHEMA_VERSION:
        fail(
            "UNSUPPORTED_SCHEMA",
            "Unsupported evaluation cost ledger schema_version: "
            f"{ledger['schema_version']}",
        )
    nonempty_string(ledger["created_by"], label="created_by")
    timestamp(ledger["created_at"], label="created_at")
    status = ledger["status"]
    if status not in ("open", "closed"):
        fail("INVALID_SCHEMA", "evaluation cost ledger.status must be open or closed")
    entries_value = ledger["entries"]
    if not isinstance(entries_value, list):
        fail("INVALID_SCHEMA", "evaluation cost ledger.entries must be an array")
    entries = [
        _check_entry(value, index=index) for index, value in enumerate(entries_value)
    ]
    total = sum(
        (
            _money(entry["cost_cny"], label=f"entries[{index}].cost_cny")
            for index, entry in enumerate(entries)
        ),
        Decimal("0.00"),
    )
    total = _quantize_cny(total)
    if _money(ledger["total_cost_cny"], label="total_cost_cny") != total:
        fail(
            "EVALUATION_COST_LEDGER_ARITHMETIC",
            "The evaluation cost ledger total does not recompute from its entries",
            recomputed=str(total),
            stored=ledger["total_cost_cny"],
        )
    if entries:
        last_entry_sha256 = ledger["last_entry_sha256"]
        if not isinstance(last_entry_sha256, str) or not _SHA256_PATTERN.fullmatch(
            last_entry_sha256
        ):
            fail(
                "INVALID_SCHEMA",
                "last_entry_sha256 must be a SHA-256 digest",
            )
        expected = sha256_bytes(canonical_json_bytes(entries[-1]))
        if last_entry_sha256 != expected:
            fail(
                "EVALUATION_COST_LEDGER_CHAIN_DRIFT",
                "The evaluation cost ledger's last-entry hash does not recompute",
            )
    elif ledger["last_entry_sha256"] is not None:
        fail(
            "EVALUATION_COST_LEDGER_CHAIN_DRIFT",
            "An empty evaluation cost ledger must carry a null last_entry_sha256",
        )
    return ledger


def initialize_evaluation_cost_ledger(
    workspace_root: Path, *, created_by: str
) -> dict[str, Any]:
    """Write-once create the evaluation cost ledger.

    The ledger lives at ``artifacts/evaluations/evaluation-cost-ledger.json``
    (0600, exclusive create); a second initialization fails closed with
    ``ARTIFACT_EXISTS``.
    """
    nonempty_string(created_by, label="created_by")
    workspace = workspace_root.resolve(strict=True)
    root = workspace / EVALUATION_ROOT_RELPATH
    if root.is_symlink():
        fail("SYMLINK_FORBIDDEN", "The evaluations root is a symlink")
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("STORAGE_WRITE_FAILED", f"Cannot create evaluations root: {detail}")
    _fsync_directory(root)
    document: dict[str, Any] = {
        "created_at": _now(),
        "created_by": created_by,
        "entries": [],
        "last_entry_sha256": None,
        "schema_version": EVALUATION_COST_LEDGER_SCHEMA_VERSION,
        "status": "open",
        "total_cost_cny": "0.00",
    }
    _write_bytes_once(
        root / EVALUATION_COST_LEDGER_NAME,
        canonical_json_bytes(document),
        label=EVALUATION_COST_LEDGER_NAME,
    )
    return document


def load_evaluation_cost_ledger(workspace_root: Path) -> dict[str, Any]:
    """Load and fully re-validate the evaluation cost ledger.

    A missing file fails closed with ``EVALUATION_COST_LEDGER_MISSING``. The
    closed shape is re-validated, the total is recomputed from the entries,
    and the hash-linked ``last_entry_sha256`` is recomputed and compared.
    """
    path = workspace_root / EVALUATION_ROOT_RELPATH / EVALUATION_COST_LEDGER_NAME
    if path.is_symlink() or not path.is_file():
        fail(
            "EVALUATION_COST_LEDGER_MISSING",
            "No evaluation cost ledger exists; initialize it first",
        )
    value = parse_json_bytes(path.read_bytes(), label="evaluation cost ledger")
    return _validate_cost_ledger(value)


def record_evaluation_cost(
    ledger: dict[str, Any],
    *,
    call_kind: str,
    run_id: object = None,
    pair_id: object = None,
    idea_index: object = None,
    provider: str,
    model_id: str,
    physical_call_count: int,
    cost_cny: str,
    responded_at: str,
    recorded_at: str,
    recorded_by: str,
    note: object = None,
) -> dict[str, Any]:
    """Append one AI review call cost entry (pure; returns the updated ledger).

    The ledger is re-validated and the entry fields fail closed (closed call
    kind enum, non-empty provider/model_id/recorded_by, canonical
    timestamps, a non-negative two-fraction-digit decimal cost, and a
    physical call count >= 1). The new ``entry_seq`` continues the 1-based
    sequence as ``len(entries) + 1``, the total is recomputed, and the
    hash-linked ``last_entry_sha256`` advances to the new last entry.

    Nothing is written here: the caller persists the returned document with
    ``save_evaluation_cost_ledger``.
    """
    checked = _validate_cost_ledger(ledger)
    if checked["status"] != "open":
        fail(
            "EVALUATION_COST_LEDGER_CLOSED",
            "The evaluation cost ledger is closed and is not accepting records",
        )
    if call_kind not in EVALUATION_CALL_KINDS:
        fail(
            "INVALID_SCHEMA",
            f"call_kind must be one of {sorted(EVALUATION_CALL_KINDS)}",
        )
    nonempty_string(provider, label="provider")
    nonempty_string(model_id, label="model_id")
    nonempty_string(recorded_by, label="recorded_by")
    timestamp(responded_at, label="responded_at")
    timestamp(recorded_at, label="recorded_at")
    cost = _money(cost_cny, label="cost_cny")
    if (
        not isinstance(physical_call_count, int)
        or isinstance(physical_call_count, bool)
        or physical_call_count < 1
    ):
        fail("INVALID_SCHEMA", "physical_call_count must be an integer >= 1")
    if run_id is not None:
        nonempty_string(run_id, label="run_id")
        if call_kind == "pair_review":
            fail("INVALID_SCHEMA", "run_id must be null for a pair review")
    if pair_id is not None:
        nonempty_string(pair_id, label="pair_id")
    if idea_index is not None and (
        not isinstance(idea_index, int)
        or isinstance(idea_index, bool)
        or idea_index < 0
    ):
        fail("INVALID_SCHEMA", "idea_index must be null or a non-negative integer")
    if note is not None:
        nonempty_string(note, label="note")

    entry_seq = len(checked["entries"]) + 1
    entry: dict[str, Any] = {
        "call_kind": call_kind,
        "cost_cny": str(cost),
        "entry_seq": entry_seq,
        "idea_index": idea_index,
        "model_id": model_id,
        "note": note,
        "pair_id": pair_id,
        "physical_call_count": physical_call_count,
        "provider": provider,
        "recorded_at": recorded_at,
        "recorded_by": recorded_by,
        "responded_at": responded_at,
        "run_id": run_id,
    }
    updated_total = _quantize_cny(
        cost + _money(checked["total_cost_cny"], label="total_cost_cny")
    )
    return {
        "created_at": checked["created_at"],
        "created_by": checked["created_by"],
        "entries": list(checked["entries"]) + [entry],
        "last_entry_sha256": sha256_bytes(canonical_json_bytes(entry)),
        "schema_version": checked["schema_version"],
        "status": checked["status"],
        "total_cost_cny": str(updated_total),
    }


def save_evaluation_cost_ledger(
    workspace_root: Path, document: dict[str, Any]
) -> dict[str, Any]:
    """Persist an updated ledger, failing closed on concurrent modification.

    The document is fully re-validated before writing. The on-disk ledger is
    then re-loaded and compared against the state the caller loaded — the
    document with its last appended entry removed (recording appends exactly
    one entry before each save). If the on-disk ``total_cost_cny``,
    ``last_entry_sha256``, or entry count no longer match that loaded state,
    another writer modified the ledger and the save fails closed with
    ``EVALUATION_COST_LEDGER_DRIFT``. Only the ledger file is overwritten.
    """
    checked = _validate_cost_ledger(document)
    on_disk = load_evaluation_cost_ledger(workspace_root)
    entries = checked["entries"]
    if entries:
        previous_entries = entries[:-1]
        expected_len = len(previous_entries)
        expected_total = _quantize_cny(
            _money(checked["total_cost_cny"], label="total_cost_cny")
            - _money(entries[-1]["cost_cny"], label="last entry cost")
        )
        expected_last_sha = (
            sha256_bytes(canonical_json_bytes(previous_entries[-1]))
            if previous_entries
            else None
        )
    else:
        expected_len = 0
        expected_total = Decimal("0.00")
        expected_last_sha = None
    if (
        on_disk["total_cost_cny"] != str(expected_total)
        or on_disk["last_entry_sha256"] != expected_last_sha
        or len(on_disk["entries"]) != expected_len
    ):
        fail(
            "EVALUATION_COST_LEDGER_DRIFT",
            "The evaluation cost ledger changed on disk since it was loaded; "
            "reload and re-record before persisting",
        )
    path = workspace_root / EVALUATION_ROOT_RELPATH / EVALUATION_COST_LEDGER_NAME
    _write_bytes_overwrite(
        path, canonical_json_bytes(checked), label=EVALUATION_COST_LEDGER_NAME
    )
    return checked


def merged_cost_report(
    generation_ledger: dict[str, Any], evaluation_ledger: dict[str, Any]
) -> dict[str, Any]:
    """Read-only merged view of generation and AI review costs.

    The generation spend ledger document's money fields are carried verbatim
    (each pattern-validated as a decimal), the evaluation cost ledger is
    re-validated with its closed shape, and the two totals are summed into a
    merged stage spend. Neither input is mutated. The report discloses that
    review costs are NOT covered by the generation Plan Gate approval.
    """
    generation_money = {
        field: _money(generation_ledger.get(field), label=f"generation.{field}")
        for field in GENERATION_MONEY_FIELDS
    }
    evaluation = _validate_cost_ledger(evaluation_ledger)
    evaluation_total = _money(
        evaluation["total_cost_cny"], label="evaluation.total_cost_cny"
    )
    by_call_kind: dict[str, Decimal] = {}
    by_provider_model: dict[str, Decimal] = {}
    for entry in evaluation["entries"]:
        entry_cost = _money(entry["cost_cny"], label="entry.cost_cny")
        kind = entry["call_kind"]
        by_call_kind[kind] = _quantize_cny(
            by_call_kind.get(kind, Decimal("0.00")) + entry_cost
        )
        key = f"{entry['provider']}/{entry['model_id']}"
        by_provider_model[key] = _quantize_cny(
            by_provider_model.get(key, Decimal("0.00")) + entry_cost
        )
    merged = _quantize_cny(generation_money["total_stage_spend_cny"] + evaluation_total)
    return {
        "schema_version": MERGE_REPORT_SCHEMA_VERSION,
        "generation": {
            field: generation_ledger[field] for field in GENERATION_MONEY_FIELDS
        },
        "evaluation": {
            "total_cost_cny": evaluation["total_cost_cny"],
            "entries_count": len(evaluation["entries"]),
            "by_call_kind": {
                kind: str(total) for kind, total in sorted(by_call_kind.items())
            },
            "by_provider_model": {
                key: str(total) for key, total in sorted(by_provider_model.items())
            },
        },
        "merged_stage_spend_cny": str(merged),
        "unauthorized_spend_disclosure": UNAUTHORIZED_SPEND_DISCLOSURE,
        "notes": list(MERGE_NOTES),
    }
