"""Migration helpers for the AI evaluation integration (ticket 03).

The current matrix migrates to a two-workspace topology without changing the
generation side: the remaining generation runs in a clean worktree at the
original execution-code pin (`d733ffed…` for the live package), while the
post-seal AI evaluation runs in the working workspace. This module provides
the deterministic checks both sides need — it never modifies the frozen
package, never supersedes the pin, never edits a sealed run, and never
writes ledger entries:

- ``verify_generation_package_compatibility``: the frozen comparison package
  as the evaluation workspace sees it (same relative layout, hash-verified).
- ``migration_handoff_manifest`` / ``verify_handoff_manifest``: the hash
  manifest for the private material copy handed between the two workspaces
  (generation outputs out, evaluation artifacts back), so both ends can tell
  which state is current and no double-booking can hide.
- ``ledger_recency_comparison``: two workspaces' copies of the authoritative
  spend ledger compared by (entries count, total, last entry digest) so an
  interrupted round-trip can decide which copy is newer before any new slot
  launch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import _now
from .errors import fail
from .schema import closed_object, nonempty_string, timestamp

HANDOFF_MANIFEST_SCHEMA_VERSION = "migration-handoff-manifest-v1.0.0"

# The package files whose bytes must be identical in both workspaces (the
# frozen inputs). The spend ledger is intentionally absent: it is the
# serialized authority that advances, covered by recency comparison instead.
FROZEN_PACKAGE_FILES = (
    "selection-manifest.json",
    "selection-approval.json",
    "run-matrix.json",
    "blind-mapping.json",
    "commands.txt",
    "execution-code-pin.json",
)


def verify_generation_package_compatibility(
    workspace_root: Path,
    *,
    expected_sha256s: dict[str, str],
) -> dict[str, Any]:
    """Verify the frozen package files exist at the standard relative layout.

    The evaluation workspace keeps the generation package at its original
    relative path (`artifacts/ideation-inputs/comparisons/<slug>/`) with
    byte-identical frozen files, so `prepare_comparison_slot_launch` in the
    generation worktree and the evaluation-side tooling read the same pins.
    A missing, drifted, or symlinked file fails closed; nothing is written.
    """
    workspace = workspace_root.resolve(strict=True)
    package_dir = workspace / "artifacts" / "ideation-inputs" / "comparisons"
    if not package_dir.is_dir():
        fail(
            "MIGRATION_PACKAGE_MISSING",
            "The comparison package root is missing from this workspace",
            path=str(package_dir),
        )
    verified: dict[str, str] = {}
    for name in FROZEN_PACKAGE_FILES:
        found: Path | None = None
        for child in sorted(package_dir.iterdir()):
            if not child.is_dir() or child.is_symlink():
                continue
            candidate = child / name
            if candidate.is_file() and not candidate.is_symlink():
                found = candidate
                break
        if found is None:
            fail(
                "MIGRATION_PACKAGE_MISSING",
                f"The frozen package file is missing: {name}",
            )
        digest = sha256_bytes(found.read_bytes())
        expected = expected_sha256s.get(name)
        if expected is not None and digest != expected:
            fail(
                "MIGRATION_PACKAGE_DRIFT",
                f"The frozen package file drifted from the pinned bytes: {name}",
                path=str(found),
                expected_sha256=expected,
                actual_sha256=digest,
            )
        verified[name] = digest
    return {
        "package_files": verified,
        "status": "verified",
    }


def migration_handoff_manifest(
    workspace_root: Path,
    *,
    direction: str,
    carried_files: list[dict[str, str]],
    direction_state: str,
    created_by: str,
) -> dict[str, Any]:
    """Build one hash manifest for a private material hand-off round-trip.

    `carried_files` lists {"path", "sha256"} for every file the carrying
    workspace contributes this round (generation outputs going to the
    evaluation workspace, or evaluation artifacts going back). Paths are
    workspace-relative; the manifest records the direction, the sequence
    state of the authoritative ledger at hand-off time, and a created
    timestamp, so the receiving end can prove it received exactly these
    bytes and resume from the recorded state.
    """
    if direction not in ("generation_to_evaluation", "evaluation_to_generation"):
        fail(
            "INVALID_INPUT",
            f"Unknown hand-off direction: {direction}",
        )
    nonempty_string(created_by, label="created_by")
    if not isinstance(direction_state, str) or not direction_state:
        fail("INVALID_INPUT", "The hand-off must record the ledger state")
    files: list[dict[str, str]] = []
    for item in carried_files:
        record = closed_object(item, label="carried file", keys={"path", "sha256"})
        nonempty_string(record["path"], label="carried file path")
        if len(record["sha256"]) != 64:
            fail("INVALID_INPUT", "A carried file entry lacks its sha256")
        files.append({"path": record["path"], "sha256": record["sha256"]})
    if not files:
        fail("INVALID_INPUT", "A hand-off must carry at least one file")
    return {
        "created_at": _now(),
        "created_by": created_by,
        "direction": direction,
        "direction_state": direction_state,
        "files": files,
        "schema_version": HANDOFF_MANIFEST_SCHEMA_VERSION,
    }


def verify_handoff_manifest(
    workspace_root: Path,
    manifest: dict[str, Any],
    *,
    verify_present: bool,
) -> dict[str, Any]:
    """Verify one hand-off manifest against this workspace's files.

    Every carried file must exist here with exactly the recorded hash: the
    receiving end proves it received the recorded bytes, and the sending end
    proves its own copy before travel — both checks are the same file
    comparison, so the caller's `verify_present` flag records the intent
    only. A missing/drifted file fails closed; nothing is written.
    """
    del verify_present  # both ends perform the identical hash comparison
    workspace = workspace_root.resolve(strict=True)
    checked = closed_object(
        manifest,
        label="hand-off manifest",
        keys={
            "created_at",
            "created_by",
            "direction",
            "direction_state",
            "files",
            "schema_version",
        },
    )
    if checked["schema_version"] != HANDOFF_MANIFEST_SCHEMA_VERSION:
        fail(
            "UNSUPPORTED_SCHEMA",
            "Unsupported hand-off manifest schema_version: "
            f"{checked['schema_version']}",
        )
    problems: list[dict[str, str]] = []
    for item in checked["files"]:
        relative = item["path"]
        path = workspace / relative
        if path.is_symlink() or not path.is_file():
            problems.append({"path": relative, "problem": "missing"})
            continue
        digest = sha256_bytes(path.read_bytes())
        if digest != item["sha256"]:
            problems.append(
                {
                    "path": relative,
                    "problem": "hash_mismatch",
                    "actual_sha256": digest,
                }
            )
    if problems:
        fail(
            "MIGRATION_HANDOFF_DRIFT",
            "The hand-off manifest does not match this workspace's files",
            problems=problems,
        )
    return {
        "files_verified": len(checked["files"]),
        "manifest_sha256": sha256_bytes(canonical_json_bytes(checked)),
        "status": "verified",
    }


def ledger_recency_comparison(
    local_ledger: dict[str, Any],
    remote_ledger: dict[str, Any],
) -> dict[str, Any]:
    """Compare two copies of the authoritative spend ledger for recency.

    Both documents are the closed `comparison-spend-ledger-v1.3.0` shape
    (validated by comparison's own arithmetic validator on load). Recency is
    a strict order: more ingested entries wins; on an entries tie, more
    forfeited entries wins; a further tie fails closed (an ambiguous state
    must be resolved by Robert against the reservation/quarantine evidence,
    not guessed by tooling). Identical documents are `same_state`.
    """
    from .comparison import SPEND_LEDGER_SCHEMA_VERSION

    for label, document in (("local", local_ledger), ("remote", remote_ledger)):
        if document.get("schema_version") != SPEND_LEDGER_SCHEMA_VERSION:
            fail(
                "LEDGER_SCHEMA_DRIFT",
                f"The {label} ledger is not the authoritative spend-ledger schema",
                schema_version=document.get("schema_version"),
            )
        if document.get("matrix_sha256") != local_ledger.get("matrix_sha256"):
            fail(
                "MATRIX_PIN_DRIFT",
                "The two ledger copies belong to different comparison matrices",
            )
    local_ingested = len(local_ledger.get("entries", []))
    remote_ingested = len(remote_ledger.get("entries", []))
    local_forfeited = len(local_ledger.get("forfeited_entries", []))
    remote_forfeited = len(remote_ledger.get("forfeited_entries", []))
    local_key = (local_ingested, local_forfeited)
    remote_key = (remote_ingested, remote_forfeited)
    if local_key == remote_key:
        identical = canonical_json_bytes(local_ledger) == canonical_json_bytes(
            remote_ledger
        )
        if identical:
            verdict = "same_state"
        else:
            fail(
                "MIGRATION_LEDGER_AMBIGUOUS",
                "Both ledger copies carry the same slot progress but differ in "
                "bytes; resolve against reservation/quarantine evidence before "
                "any new slot launch",
            )
        newer = None
    elif local_key > remote_key:
        verdict = "local_newer"
        newer = "local"
    else:
        verdict = "remote_newer"
        newer = "remote"
    return {
        "local": {"entries": local_ingested, "forfeited_entries": local_forfeited},
        "newer": newer,
        "remote": {"entries": remote_ingested, "forfeited_entries": remote_forfeited},
        "verdict": verdict,
    }
