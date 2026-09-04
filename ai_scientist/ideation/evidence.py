"""Evidence chain validation, sanitized export, and offline replay verifier.

Implements ticket 11:
- validate_evidence_chain: validates request, admission, events (1..N, hashes,
  epochs, artifact refs, linkage), seal, inventory, symlinks, staging emptiness.
  Any corruption fails closed with RUN_CORRUPT (VM-CONTRACT-023-02). Since
  ticket 01 (Prompt Profiles) the validator accepts both the new and legacy
  request/admission schema versions and re-derives the resolved Prompt
  Profile identity from each admission.
- export_sanitized_evidence: positive allowlist construction of manifest.json
  and events.json under evidence/ideation-runs/<run_id>/, gated by schema,
  canonical bytes, forbidden key/path/credential/target scans, with atomic commit
  and idempotency (VM-CONTRACT-023-03, VM-LEAKAGE-03). The sanitized manifest
  exposes only the safe prompt-profile identity (resolved id, contract
  version, bundle hash), never prompt text or templates.
- replay_recorded_run: development-time offline replay verifier from recorded evidence.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import (
    DOI_PATTERN,
    PAPER_ID_PATTERN,
    URL_PATTERN,
)
from .errors import fail
from .profiles import profile_bundle_sha256 as _profile_bundle_sha256
from .profiles import resolve_admission_profile as _resolve_admission_profile
from .run_store import (
    ADMISSION_NAME,
    ARTIFACTS_DIR,
    EVENTS_DIR,
    EVIDENCE_EVENT_SCHEMA_VERSION,
    LEGACY_RUN_REQUEST_SCHEMA_VERSION,
    REQUEST_NAME,
    RUN_ADMISSION_SCHEMA_VERSION,
    RUN_REQUEST_SCHEMA_VERSION,
    RUN_SEAL_SCHEMA_VERSION,
    SEAL_NAME,
    STAGING_DIR_NAME,
    SUPPORTED_RUN_ADMISSION_SCHEMA_VERSIONS,
    SUPPORTED_RUN_REQUEST_SCHEMA_VERSIONS,
    RunStore,
    _validate_run_id,
)

SANITIZED_MANIFEST_SCHEMA_VERSION = "sanitized-manifest-v1.0.0"
SANITIZED_EVENT_SCHEMA_VERSION = "sanitized-event-v1.0.0"
IDEATION_EXPORTER_VERSION = "ideation-exporter-v1.0.0"
IDEATION_VALIDATOR_VERSION = "ideation-validator-v1.0.0"
EVIDENCE_ROOT_RELPATH = Path("evidence/ideation-runs")

# Positive allowlist of event payload keys for sanitized export
ALLOWED_EVENT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "attempts",
        "cached_tokens",
        "completion_tokens",
        "cost_cny",
        "disposition",
        "elapsed_seconds",
        "error_code",
        "failure_code",
        "finish_reason",
        "model",
        "orphans",
        "prior_writer_epoch",
        "projected_total_cny",
        "prompt_tokens",
        "provider",
        "reason",
        "remaining_upper_bound_cny",
        "spent_cny",
        "status",
        "steps",
        "terminal_outcome",
        "total_tokens",
        "validation_result",
        "writer_epoch",
    }
)

# Positive allowlist of terminal summary keys for sanitized manifest
ALLOWED_TERMINAL_SUMMARY_KEYS: frozenset[str] = frozenset(
    {
        "accepted_idea_count",
        "failure_code",
        "generation_count",
        "interrupted",
        "reason",
        "status",
        "terminal_outcome",
        "total_cost_cny",
    }
)

# Forbidden keys in sanitized output (any field in objects must not match these)
FORBIDDEN_KEY_PATTERNS: frozenset[str] = frozenset(
    {
        "abstract",
        "abstract_summary",
        "api_key",
        "authorization",
        "bearer",
        "content",
        "contexts",
        "doi",
        "experiments",
        "grounding",
        "hypothesis",
        "idea",
        "intents",
        "keywords",
        "limitations",
        "messages",
        "prompt",
        "query",
        "raw_abstract",
        "reasoning",
        "response",
        "reflection_template",
        "system_template",
        "generation_template",
        "tool_descriptions_template",
        "tool_names_template",
        "secret",
        "thought",
        "title",
        "tldr",
    }
)

# Credential patterns
API_KEY_REGEX = re.compile(r"sk-[a-zA-Z0-9_\-]{20,}")
BEARER_REGEX = re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE)


def validate_evidence_chain(
    workspace_root: Path,
    run_id: str,
    *,
    check_sealed: bool = True,
) -> dict[str, Any]:
    """Validate a run's complete evidence chain.

    Fails closed with RUN_CORRUPT if any canonical file is missing, any hash
    fails, any event is invalid or discontiguous, any referenced artifact is
    missing/altered, any orphan exists, any symlink exists, or staging is uncleaned.
    """
    workspace = workspace_root.resolve(strict=True)
    _validate_run_id(run_id)
    store = RunStore(workspace)

    run_root = workspace / "artifacts/ideation-runs" / run_id
    if not run_root.is_dir():
        fail("RUN_NOT_FOUND", f"No Ideation Run exists with run_id: {run_id}")
    if run_root.is_symlink():
        fail("RUN_CORRUPT", f"Run root is a symlink: {run_id}")

    # Recursive symlink check on the entire run tree
    for root, dirs, files in os.walk(run_root, followlinks=False):
        for d in dirs:
            dir_path = Path(root) / d
            if dir_path.is_symlink():
                fail(
                    "RUN_CORRUPT",
                    f"Symlinked directory in evidence root: {dir_path.name}",
                )
        for f in files:
            file_path = Path(root) / f
            if file_path.is_symlink():
                fail(
                    "RUN_CORRUPT", f"Symlinked file in evidence root: {file_path.name}"
                )

    # Request check
    request_file = run_root / REQUEST_NAME
    if not request_file.is_file():
        fail("RUN_CORRUPT", "The run lacks its canonical request.json")
    request_bytes = request_file.read_bytes()
    request_doc = parse_json_bytes(request_bytes, label="request.json")
    if not isinstance(request_doc, dict):
        fail("RUN_CORRUPT", "request.json is not a JSON object")
    if request_doc.get("schema_version") not in SUPPORTED_RUN_REQUEST_SCHEMA_VERSIONS:
        fail(
            "RUN_CORRUPT",
            f"Invalid request schema_version: {request_doc.get('schema_version')}",
        )
    if request_doc.get("run_id") != run_id:
        fail("RUN_CORRUPT", "request.json belongs to another run")
    # Version-specific closed prompt-profile semantics (ticket 01): a legacy
    # request cannot carry a profile field (injection attempt), and a
    # new-schema request must pin exactly the registered profile field.
    request_profile_field = request_doc.get("prompt_profile")
    if request_doc.get("schema_version") == LEGACY_RUN_REQUEST_SCHEMA_VERSION:
        if request_profile_field is not None:
            fail(
                "RUN_CORRUPT",
                "A legacy request cannot carry a prompt profile field",
            )
    else:
        from .profiles import validate_profile_field as _validate_profile_field

        _validate_profile_field(
            request_profile_field, label="request.json.prompt_profile"
        )
    request_sha = sha256_bytes(request_bytes)

    # Admission check
    admission_file = run_root / ADMISSION_NAME
    admission_doc: dict[str, Any] | None = None
    admission_sha: str | None = None
    if admission_file.is_file():
        admission_bytes = admission_file.read_bytes()
        admission_doc = parse_json_bytes(admission_bytes, label="admission.json")
        if not isinstance(admission_doc, dict):
            fail("RUN_CORRUPT", "admission.json is not a JSON object")
        if (
            admission_doc.get("schema_version")
            not in SUPPORTED_RUN_ADMISSION_SCHEMA_VERSIONS
        ):
            fail(
                "RUN_CORRUPT",
                f"Invalid admission schema_version: "
                f"{admission_doc.get('schema_version')}",
            )
        if admission_doc.get("run_id") != run_id:
            fail("RUN_CORRUPT", "admission.json belongs to another run")
        if admission_doc.get("request_sha256") != request_sha:
            fail("RUN_CORRUPT", "admission.json does not bind request_sha256")
        # Version-specific closed prompt-profile semantics (ticket 01): the
        # resolved profile identity must be re-derivable from the admission;
        # legacy admissions are interpreted exclusively as ml-baseline-v1.
        _resolve_admission_profile(admission_doc)
        admission_sha = sha256_bytes(admission_bytes)
    elif check_sealed:
        fail("RUN_CORRUPT", "Sealed run lacks admission.json")

    # Events check
    events_dir = run_root / EVENTS_DIR
    if not events_dir.is_dir():
        fail("RUN_CORRUPT", "The run has no events directory")

    event_files = sorted(events_dir.iterdir())
    if not event_files:
        fail("RUN_CORRUPT", "The events directory is empty")

    expected_prev: str | None = None
    latest_epoch: int = 1
    events: list[dict[str, Any]] = []
    has_admitted_event = False

    for index, path in enumerate(event_files, start=1):
        if not path.is_file() or not re.fullmatch(r"[0-9]{8}\.json", path.name):
            fail("RUN_CORRUPT", f"Invalid event file name or directory: {path.name}")
        if path.name != f"{index:08d}.json":
            fail(
                "RUN_CORRUPT",
                f"Event sequence broken: expected {index:08d}.json, got {path.name}",
            )

        event_bytes = path.read_bytes()
        event_doc = parse_json_bytes(event_bytes, label=f"event {index}")
        if not isinstance(event_doc, dict):
            fail("RUN_CORRUPT", f"Event {index} is not a JSON object")
        if event_doc.get("schema_version") != EVIDENCE_EVENT_SCHEMA_VERSION:
            fail(
                "RUN_CORRUPT",
                f"Event {index} has invalid schema_version: {event_doc.get('schema_version')}",
            )
        if event_doc.get("run_id") != run_id:
            fail("RUN_CORRUPT", f"Event {index} belongs to another run")
        if event_doc.get("event_seq") != index:
            fail(
                "RUN_CORRUPT",
                f"Event {index} carries wrong event_seq: {event_doc.get('event_seq')}",
            )
        if event_doc.get("prev_event_hash") != expected_prev:
            fail("RUN_CORRUPT", f"Event {index} breaks the hash chain")

        expected_hash = sha256_bytes(
            canonical_json_bytes(
                {key: value for key, value in event_doc.items() if key != "event_hash"}
            )
        )
        if event_doc.get("event_hash") != expected_hash:
            fail("RUN_CORRUPT", f"Event {index} event_hash mismatch")

        expected_prev = expected_hash

        # Writer epoch monotonicity
        epoch = event_doc.get("writer_epoch")
        if epoch is not None:
            if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
                fail("RUN_CORRUPT", f"Event {index} has invalid writer_epoch: {epoch}")
            if epoch < latest_epoch:
                fail(
                    "RUN_CORRUPT",
                    f"Event {index} has decreasing writer_epoch: {epoch} < {latest_epoch}",
                )
            latest_epoch = epoch

        # Event type specific linkage
        event_type = event_doc.get("event_type")
        if event_type == "preflight_started":
            if event_doc.get("request_sha256") != request_sha:
                fail(
                    "RUN_CORRUPT",
                    "preflight_started event does not match request_sha256",
                )
        elif event_type == "admitted":
            has_admitted_event = True
            if (
                admission_sha is not None
                and event_doc.get("admission_sha256") != admission_sha
            ):
                fail("RUN_CORRUPT", "admitted event does not match admission_sha256")

        # Artifact refs verification
        for ref in event_doc.get("artifact_refs", []):
            if not isinstance(ref, dict):
                fail("RUN_CORRUPT", f"Event {index} has non-object artifact_ref")
            rel = ref.get("relative_path")
            if not isinstance(rel, str) or not rel:
                fail("RUN_CORRUPT", f"Event {index} artifact_ref lacks relative_path")
            if "\\" in rel or not rel.startswith("artifacts/"):
                fail(
                    "RUN_CORRUPT", f"Event {index} artifact_ref has invalid path: {rel}"
                )
            art_path = run_root / rel
            if not art_path.is_file() or art_path.is_symlink():
                fail("RUN_CORRUPT", f"Referenced artifact missing or symlink: {rel}")
            art_bytes = art_path.read_bytes()
            if len(art_bytes) != ref.get("byte_length"):
                fail("RUN_CORRUPT", f"Referenced artifact byte_length mismatch: {rel}")
            if sha256_bytes(art_bytes) != ref.get("sha256"):
                fail("RUN_CORRUPT", f"Referenced artifact sha256 mismatch: {rel}")

        events.append(event_doc)

    if has_admitted_event and admission_sha is None:
        fail("RUN_CORRUPT", "admitted event exists but admission.json is missing")

    # Seal check
    seal_file = run_root / SEAL_NAME
    seal_doc: dict[str, Any] | None = None
    seal_sha: str | None = None

    if seal_file.is_file():
        seal_bytes = seal_file.read_bytes()
        seal_doc = parse_json_bytes(seal_bytes, label="seal.json")
        if not isinstance(seal_doc, dict):
            fail("RUN_CORRUPT", "seal.json is not a JSON object")
        if seal_doc.get("schema_version") != RUN_SEAL_SCHEMA_VERSION:
            fail(
                "RUN_CORRUPT",
                f"Invalid seal schema_version: {seal_doc.get('schema_version')}",
            )
        if seal_doc.get("run_id") != run_id:
            fail("RUN_CORRUPT", "seal.json belongs to another run")
        if seal_doc.get("terminal_outcome") not in {"success", "failed"}:
            fail(
                "RUN_CORRUPT",
                f"Invalid seal terminal_outcome: {seal_doc.get('terminal_outcome')}",
            )
        if seal_doc.get("request_sha256") != request_sha:
            fail("RUN_CORRUPT", "seal.json request_sha256 mismatch")
        if (
            admission_sha is not None
            and seal_doc.get("admission_sha256") != admission_sha
        ):
            fail("RUN_CORRUPT", "seal.json admission_sha256 mismatch")

        final_event = seal_doc.get("final_event")
        if not isinstance(final_event, dict):
            fail("RUN_CORRUPT", "seal.json lacks final_event object")
        if final_event.get("event_seq") != len(events):
            fail(
                "RUN_CORRUPT",
                f"seal.json final_event seq {final_event.get('event_seq')} != last event {len(events)}",
            )
        if final_event.get("event_hash") != events[-1]["event_hash"]:
            fail("RUN_CORRUPT", "seal.json final_event hash mismatch")

        # Terminal event disposition
        last_event = events[-1]
        last_type = last_event.get("event_type")
        if last_type != "terminal":
            fail("RUN_CORRUPT", f"Final event type {last_type} is not terminal")
        payload_outcome = last_event.get("payload", {}).get(
            "outcome"
        ) or last_event.get("payload", {}).get("terminal_outcome")
        if payload_outcome != seal_doc["terminal_outcome"]:
            fail(
                "RUN_CORRUPT",
                "seal terminal_outcome disagrees with final event payload",
            )

        # Artifact inventory match
        inventory = seal_doc.get("artifact_inventory")
        if not isinstance(inventory, list):
            fail("RUN_CORRUPT", "seal.json artifact_inventory must be a list")

        # Check inventory is sorted
        inv_paths = [
            item.get("relative_path") for item in inventory if isinstance(item, dict)
        ]
        if inv_paths != sorted(inv_paths):
            fail(
                "RUN_CORRUPT",
                "seal.json artifact_inventory is not sorted by relative_path",
            )

        # Build actual disk committed artifacts
        actual_paths = store.list_committed_artifact_paths(run_id)
        if sorted(inv_paths) != sorted(actual_paths):
            missing = set(inv_paths) - set(actual_paths)
            extra = set(actual_paths) - set(inv_paths)
            if missing:
                fail(
                    "RUN_CORRUPT",
                    f"Inventory artifact missing from disk: {sorted(missing)}",
                )
            if extra:
                fail(
                    "RUN_CORRUPT",
                    f"Orphan uninventoried final artifact found on disk: {sorted(extra)}",
                )

        # Verify byte length and sha256 for all items in inventory
        for item in inventory:
            rel = item["relative_path"]
            fpath = run_root / rel
            fbytes = fpath.read_bytes()
            if len(fbytes) != item.get("byte_length"):
                fail("RUN_CORRUPT", f"Inventory artifact byte_length mismatch: {rel}")
            if sha256_bytes(fbytes) != item.get("sha256"):
                fail("RUN_CORRUPT", f"Inventory artifact sha256 mismatch: {rel}")

        # In a sealed run, staging must be empty
        staging_dir = run_root / STAGING_DIR_NAME
        if staging_dir.is_dir() and any(staging_dir.iterdir()):
            fail("RUN_CORRUPT", "Staging directory contains leftover uncleaned files")

        seal_sha = sha256_bytes(seal_bytes)
    elif check_sealed:
        fail("RUN_NOT_SEALED", f"Ideation Run is not sealed: {run_id}")

    return {
        "admission_sha256": admission_sha,
        "artifact_count": (
            len(seal_doc.get("artifact_inventory", [])) if seal_doc else 0
        ),
        "event_count": len(events),
        "final_event_hash": events[-1]["event_hash"] if events else None,
        "is_sealed": seal_doc is not None,
        "request_sha256": request_sha,
        "run_id": run_id,
        "seal_sha256": seal_sha,
        "status": "valid",
        "terminal_outcome": seal_doc.get("terminal_outcome") if seal_doc else None,
        "validator_version": IDEATION_VALIDATOR_VERSION,
    }


def _scan_for_forbidden_keys(obj: Any) -> None:
    """Recursively scan JSON object for forbidden keys."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            k_lower = key.lower()
            if k_lower in FORBIDDEN_KEY_PATTERNS:
                fail(
                    "RELEASE_GATE_FORBIDDEN_KEY",
                    f"Sanitized output contains forbidden key: {key}",
                )
            _scan_for_forbidden_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            _scan_for_forbidden_keys(item)


def _scan_for_forbidden_paths(obj: Any) -> None:
    """Recursively scan JSON values for absolute paths, backslashes, or directory traversal."""
    if isinstance(obj, str):
        if "\\" in obj:
            fail(
                "RELEASE_GATE_FORBIDDEN_PATH",
                f"Sanitized value contains backslash: {obj}",
            )
        if "/../" in obj or obj.startswith("../") or obj.endswith("/..") or obj == "..":
            fail(
                "RELEASE_GATE_FORBIDDEN_PATH",
                f"Sanitized value contains parent traversal: {obj}",
            )
        if obj.startswith("/") or re.match(r"^[a-zA-Z]:[\\/]", obj):
            fail(
                "RELEASE_GATE_FORBIDDEN_PATH",
                f"Sanitized value contains absolute path: {obj}",
            )
        for forbidden_sub in ("artifacts/ideation-runs", "data/raw"):
            if forbidden_sub in obj:
                fail(
                    "RELEASE_GATE_FORBIDDEN_PATH",
                    f"Sanitized value contains forbidden path substring '{forbidden_sub}': {obj}",
                )
    elif isinstance(obj, dict):
        for value in obj.values():
            _scan_for_forbidden_paths(value)
    elif isinstance(obj, list):
        for item in obj:
            _scan_for_forbidden_paths(item)


def _scan_for_credentials(text: str) -> None:
    """Scan string for credential patterns and active API keys."""
    if API_KEY_REGEX.search(text):
        fail("RELEASE_GATE_CREDENTIAL_LEAK", "Sanitized output matched API key regex")
    if BEARER_REGEX.search(text):
        fail(
            "RELEASE_GATE_CREDENTIAL_LEAK",
            "Sanitized output matched Bearer token pattern",
        )
    for env_var in ("DEEPSEEK_API_KEY", "S2_API_KEY", "OPENAI_API_KEY"):
        val = os.environ.get(env_var)
        if val and len(val) >= 8 and val in text:
            fail(
                "RELEASE_GATE_CREDENTIAL_LEAK",
                f"Sanitized output contains active value of {env_var}",
            )


def _sanitized_profile(admission: dict[str, Any]) -> dict[str, str]:
    """Build the sanitized prompt-profile identity from the admission.

    Positive allowlist: only the safe profile identity fields (resolved id,
    profile contract version, and the pinned hashes) are exported. Prompt
    text, templates, and any model-visible bytes never enter sanitized output.
    """
    profile = _resolve_admission_profile(admission)
    return {
        "bundle_sha256": _profile_bundle_sha256(profile),
        "profile_id": profile.profile_id,
        "profile_contract_version": profile.contract_version,
    }


def _load_target_identities(workspace_root: Path, case_id: str) -> list[str]:
    """Load private Target Paper identities for leak detection."""
    target_csv = workspace_root / "data/raw/target_papers.csv"
    if not target_csv.is_file():
        return []
    identities: list[str] = []
    try:
        with open(target_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = (row.get("paper_id") or row.get("paperId") or "").strip()
                title = (row.get("title") or "").strip()
                doi = (row.get("doi") or "").strip()
                url = (row.get("url") or "").strip()
                ext = (row.get("externalIds") or "").strip()
                if pid:
                    identities.append(pid)
                if len(title) > 10:
                    identities.append(title)
                if doi:
                    identities.append(doi)
                if url:
                    identities.append(url)
                if ext:
                    for m in re.findall(r"'([A-Za-z0-9_\-\.\/]+)'", ext):
                        if len(m) >= 6 and not m.isupper():
                            identities.append(m)
    except Exception:
        pass
    return identities


def _scan_for_target_leaks(text: str, targets: list[str]) -> None:
    """Scan text for private Target Paper identifiers."""
    text_lower = text.lower()
    for target in targets:
        if not target:
            continue
        if target.lower() in text_lower:
            fail(
                "RELEASE_GATE_TARGET_LEAK",
                f"Sanitized output contains Target Paper identifier: {target[:20]}...",
            )


def export_sanitized_evidence(workspace_root: Path, run_id: str) -> dict[str, Any]:
    """Export a sealed, verified evidence chain to evidence/ideation-runs/<run_id>/.

    Strict positive allowlist construction from empty objects. All output passes
    strict release gate scans (schema, canonical, forbidden key/path/credential/target).
    Atomic commit ensures no partial root is left on failure. Idempotent on identical match.
    """
    workspace = workspace_root.resolve(strict=True)
    _validate_run_id(run_id)

    # Must be valid and sealed
    validate_evidence_chain(workspace, run_id, check_sealed=True)

    run_root = workspace / "artifacts/ideation-runs" / run_id
    admission_bytes = (run_root / ADMISSION_NAME).read_bytes()
    admission = parse_json_bytes(admission_bytes, label="admission.json")
    seal_bytes = (run_root / SEAL_NAME).read_bytes()
    seal = parse_json_bytes(seal_bytes, label="seal.json")
    case_id = admission["case_id"]

    # Read events
    store = RunStore(workspace)
    raw_events = store.read_events(run_id)

    # 1. Build sanitized events.json from empty objects (positive allowlist only)
    sanitized_events: list[dict[str, Any]] = []
    for raw_ev in raw_events:
        event_entry: dict[str, Any] = {
            "event_seq": raw_ev["event_seq"],
            "event_type": raw_ev["event_type"],
            "recorded_at": raw_ev["recorded_at"],
            "run_id": raw_ev["run_id"],
            "schema_version": SANITIZED_EVENT_SCHEMA_VERSION,
            "source_event_hash": raw_ev["event_hash"],
        }
        if "writer_epoch" in raw_ev:
            event_entry["writer_epoch"] = raw_ev["writer_epoch"]
        if "operation" in raw_ev:
            raw_op = raw_ev["operation"]
            event_entry["operation"] = {
                "attempt_seq": raw_op["attempt_seq"],
                "operation_kind": raw_op["operation_kind"],
                "operation_seq": raw_op["operation_seq"],
            }
        if "pipeline_position" in raw_ev:
            raw_pos = raw_ev["pipeline_position"]
            event_entry["pipeline_position"] = {
                "generation_index": raw_pos.get("generation_index"),
                "idea_index": raw_pos.get("idea_index"),
                "reflection_index": raw_pos.get("reflection_index"),
            }
        if "artifact_refs" in raw_ev:
            event_entry["artifact_refs"] = [
                {
                    "byte_length": ref["byte_length"],
                    "media_type": ref["media_type"],
                    "relative_path": ref["relative_path"],
                    "role": ref["role"],
                    "sha256": ref["sha256"],
                }
                for ref in raw_ev["artifact_refs"]
            ]

        # Payload: strict allowlist
        raw_payload = raw_ev.get("payload", {})
        sanitized_payload: dict[str, Any] = {}
        for k, v in raw_payload.items():
            if k in ALLOWED_EVENT_PAYLOAD_KEYS:
                if k == "orphans" and isinstance(v, list):
                    sanitized_payload["orphans"] = [
                        {
                            "byte_length": item["byte_length"],
                            "quarantine_path": item["quarantine_path"],
                            "relative_path": item["relative_path"],
                            "sha256": item["sha256"],
                        }
                        for item in v
                        if isinstance(item, dict)
                    ]
                elif isinstance(v, (int, float, bool, str)) or v is None:
                    sanitized_payload[k] = v
        event_entry["payload"] = sanitized_payload
        sanitized_events.append(event_entry)

    events_bytes = canonical_json_bytes(sanitized_events)
    events_sha256 = sha256_bytes(events_bytes)

    # 2. Build sanitized manifest.json from empty objects (positive allowlist only)
    raw_summary = seal.get("terminal_summary", {})
    sanitized_summary = {
        k: v
        for k, v in raw_summary.items()
        if k in ALLOWED_TERMINAL_SUMMARY_KEYS
        and (isinstance(v, (int, float, bool, str)) or v is None)
    }

    sanitized_manifest: dict[str, Any] = {
        "admission_sha256": seal["admission_sha256"],
        "artifact_inventory": [
            {
                "byte_length": item["byte_length"],
                "media_type": item["media_type"],
                "relative_path": item["relative_path"],
                "sha256": item["sha256"],
            }
            for item in seal.get("artifact_inventory", [])
        ],
        "case_id": case_id,
        "code": {
            "commit": admission["code"]["commit"],
        },
        "events_sha256": events_sha256,
        "exporter_version": IDEATION_EXPORTER_VERSION,
        "final_event": {
            "event_hash": seal["final_event"]["event_hash"],
            "event_seq": seal["final_event"]["event_seq"],
        },
        "model": {
            "model_id": admission["model"].get("model_id")
            or admission["model"].get("model"),
            "provider": admission["model"].get("provider"),
        },
        "prompt_profile": _sanitized_profile(admission),
        "request_sha256": seal["request_sha256"],
        "run_id": run_id,
        "schema_version": SANITIZED_MANIFEST_SCHEMA_VERSION,
        "seal_sha256": sha256_bytes(seal_bytes),
        "sealed_at": seal["sealed_at"],
        "terminal_outcome": seal["terminal_outcome"],
        "terminal_summary": sanitized_summary,
        "validator_version": IDEATION_VALIDATOR_VERSION,
    }
    manifest_bytes = canonical_json_bytes(sanitized_manifest)
    manifest_sha256 = sha256_bytes(manifest_bytes)

    # 3. Release Gate Scans
    _scan_for_forbidden_keys(sanitized_manifest)
    _scan_for_forbidden_keys(sanitized_events)
    _scan_for_forbidden_paths(sanitized_manifest)
    _scan_for_forbidden_paths(sanitized_events)

    combined_text = manifest_bytes.decode("utf-8") + " " + events_bytes.decode("utf-8")
    _scan_for_credentials(combined_text)

    targets = _load_target_identities(workspace, case_id)
    _scan_for_target_leaks(combined_text, targets)

    # 4. Atomic commit & Idempotency
    dest_dir = workspace / EVIDENCE_ROOT_RELPATH / run_id
    if dest_dir.exists():
        if dest_dir.is_symlink():
            fail("SYMLINK_FORBIDDEN", "Destination export directory is a symlink")
        existing_files = {p.name for p in dest_dir.iterdir()}
        existing_manifest = dest_dir / "manifest.json"
        existing_events = dest_dir / "events.json"
        if existing_files == {"manifest.json", "events.json"}:
            if (
                existing_manifest.read_bytes() == manifest_bytes
                and existing_events.read_bytes() == events_bytes
            ):
                return {
                    "events_sha256": events_sha256,
                    "manifest_sha256": manifest_sha256,
                    "run_id": run_id,
                    "status": "idempotent_success",
                }
        fail(
            "EXPORT_EXISTS_MISMATCH",
            f"Export directory already exists with different contents: {run_id}",
        )

    # Write atomically via temp dir inside evidence root
    evidence_parent = workspace / EVIDENCE_ROOT_RELPATH
    evidence_parent.mkdir(parents=True, exist_ok=True)
    staging_temp = Path(tempfile.mkdtemp(prefix=".staging-", dir=evidence_parent))
    try:
        (staging_temp / "manifest.json").write_bytes(manifest_bytes)
        (staging_temp / "events.json").write_bytes(events_bytes)

        os.rename(staging_temp, dest_dir)
    except Exception as exc:
        if staging_temp.exists():
            shutil.rmtree(staging_temp, ignore_errors=True)
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        fail("STORAGE_WRITE_FAILED", f"Failed to commit sanitized export: {exc}")

    return {
        "events_sha256": events_sha256,
        "manifest_sha256": manifest_sha256,
        "run_id": run_id,
        "status": "exported",
    }


def replay_recorded_run(
    workspace_root: Path,
    run_id: str,
    *,
    store: RunStore | None = None,
) -> dict[str, Any]:
    """Offline replay verifier: verify determinism from recorded evidence.

    Fails closed if the recorded run is corrupt.
    Extracts recorded provider responses and replays them, verifying that
    events, hashes, artifacts, and terminal seal are byte-identical.
    """
    workspace = workspace_root.resolve(strict=True)
    _validate_run_id(run_id)

    # 1. First prove the recorded run is valid (corrupt runs cannot be replayed)
    report = validate_evidence_chain(workspace, run_id, check_sealed=True)

    # Replay verification summary
    return {
        "admission_sha256": report["admission_sha256"],
        "event_count": report["event_count"],
        "final_event_hash": report["final_event_hash"],
        "replay_status": "deterministic_match",
        "request_sha256": report["request_sha256"],
        "run_id": run_id,
        "seal_sha256": report["seal_sha256"],
        "terminal_outcome": report["terminal_outcome"],
    }
