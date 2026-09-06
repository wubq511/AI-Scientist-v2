"""Run-scoped, exclusive-create evidence storage for Ideation Runs.

Implements the ticket-04 slice of the run identity and evidence layout
contract: a fixed repo-relative private trust root, exclusive-create run
roots, write-once request/admission documents, and a strictly linked
canonical event hash chain. Since ticket 01 (Prompt Profiles) the current
request/admission schema versions are v1.1.0 and pin the resolved Prompt
Profile identity; v1.0.0 documents remain valid legacy evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import uuid
from typing import Any, NoReturn

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import _now
from .errors import fail

RUN_REQUEST_SCHEMA_VERSION = "run-request-v1.1.0"
RUN_ADMISSION_SCHEMA_VERSION = "run-admission-v1.1.0"
# Pre-Prompt-Profile documents (ticket 01): interpreted exclusively as
# ml-baseline-v1 and never carrying a prompt_profile field.
LEGACY_RUN_REQUEST_SCHEMA_VERSION = "run-request-v1.0.0"
LEGACY_RUN_ADMISSION_SCHEMA_VERSION = "run-admission-v1.0.0"
EVIDENCE_EVENT_SCHEMA_VERSION = "evidence-event-v1.0.0"
RUN_SEAL_SCHEMA_VERSION = "run-seal-v1.0.0"
# Admission schema versions understood by the version-specific closed
# semantics (ticket 01): v1.1.0 carries the pinned prompt_profile field;
# v1.0.0 legacy admissions are interpreted exclusively as ml-baseline-v1.
SUPPORTED_RUN_REQUEST_SCHEMA_VERSIONS = ("run-request-v1.1.0", "run-request-v1.0.0")
SUPPORTED_RUN_ADMISSION_SCHEMA_VERSIONS = (
    "run-admission-v1.1.0",
    "run-admission-v1.0.0",
)

RUNS_ROOT_RELPATH = Path("artifacts/ideation-runs")
REQUEST_NAME = "request.json"
ADMISSION_NAME = "admission.json"
SEAL_NAME = "seal.json"
EVENTS_DIR = "events"
ARTIFACTS_DIR = "artifacts"
# Run-local subtrees that never hold committed evidence (tickets 023/025):
# staging/ carries in-flight bytes before the atomic rename; quarantine/
# receives approved rename-before-event orphan artifacts at resume time.
STAGING_DIR_NAME = "staging"
QUARANTINE_DIR_NAME = "quarantine"

ALLOWED_IDEA_FILENAMES: frozenset[str] = frozenset(
    {"idea.json", "grounding.json", "sidecar.json"}
)

RUN_ID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}" r"-[0-9a-f]{12}\Z"
)


def new_run_id() -> str:
    """Return a fresh canonical lowercase UUIDv4 run identifier."""
    return str(uuid.uuid4())


def _validate_run_id(value: object, *, label: str = "run_id") -> str:
    if not isinstance(value, str) or not RUN_ID_PATTERN.fullmatch(value):
        fail("INVALID_RUN_ID", f"{label} must be a canonical lowercase UUIDv4")
    return value


@dataclass(frozen=True, slots=True)
class RunHandle:
    run_id: str

    @property
    def request_path(self) -> str:
        return f"{self.run_id}/{REQUEST_NAME}"

    @property
    def admission_path(self) -> str:
        return f"{self.run_id}/{ADMISSION_NAME}"

    def event_path(self, event_seq: int) -> str:
        return f"{self.run_id}/{EVENTS_DIR}/{event_seq:08d}.json"


@dataclass(frozen=True, slots=True)
class EventRecord:
    run_id: str
    event_seq: int
    event_hash: str
    prev_event_hash: str | None


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _storage_failed(action: str, label: str, exc: OSError) -> NoReturn:
    """Storage/IO failures are suspend-class per the ticket-025 table."""
    detail = exc.strerror or str(exc)
    fail("STORAGE_WRITE_FAILED", f"Cannot {action} {label}: {detail}")


class RunStore:
    """Exclusive-create, run-scoped storage bound to one workspace root."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve(strict=True)
        self.runs_root = self.workspace_root / RUNS_ROOT_RELPATH

    def _run_root(self, run_id: str) -> Path:
        parsed = _validate_run_id(run_id)
        if self.runs_root.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The ideation-runs root is a symlink")
        run_root = self.runs_root / parsed
        if run_root.is_symlink():
            fail("SYMLINK_FORBIDDEN", f"The run root is a symlink: {run_id}")
        return run_root

    def _ensure_runs_root(self) -> None:
        if self.runs_root.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The ideation-runs root is a symlink")
        self.runs_root.mkdir(parents=True, exist_ok=True)
        _fsync_directory(self.runs_root.parent)

    def create_run(self, *, run_id: str | None = None) -> RunHandle:
        """Exclusively create a new run root under the fixed private root."""
        parsed = _validate_run_id(run_id) if run_id is not None else new_run_id()
        self._ensure_runs_root()
        run_root = self.runs_root / parsed
        try:
            os.mkdir(run_root, 0o700)
        except FileExistsError:
            fail("RUN_ROOT_EXISTS", f"Run root already exists: {parsed}")
        _fsync_directory(self.runs_root)
        return RunHandle(parsed)

    # -- Atomic commit path (ticket 025) -----------------------------------
    #
    # Every committed byte lands through the same path: staging write inside
    # the run root -> fsync -> SHA-256 -> rename to the final path -> fsync
    # directories. A crash before the rename leaves only staging residue
    # (cleared best-effort at resume); a crash between rename and the event
    # append leaves an orphan final artifact (quarantined at resume). Neither
    # is ever referenced by the event chain.

    def _stage_bytes(self, staging_path: Path, data: bytes, *, label: str) -> None:
        """Write `data` to a fresh staging file and fsync it and its directory.

        Narrow overridable seam for storage/interruption fault injection
        (VM-FAULT-02/VM-FAULT-03).
        """
        try:
            descriptor = os.open(
                staging_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                try:
                    staging_path.unlink()
                except OSError:
                    pass
                raise
            _fsync_directory(staging_path.parent)
        except OSError as exc:
            _storage_failed("stage", label, exc)

    def _rename_staged(self, staging_path: Path, target: Path, *, label: str) -> None:
        """Rename a staged file into its final path; existing targets fail closed.

        Narrow overridable seam for storage/interruption fault injection.
        """
        if target.exists() or target.is_symlink():
            try:
                staging_path.unlink()
            except OSError:
                pass
            fail(
                "ARTIFACT_EXISTS",
                f"{label} already exists; write-once artifacts cannot be overwritten",
            )
        try:
            os.rename(staging_path, target)
            _fsync_directory(target.parent)
            _fsync_directory(staging_path.parent)
        except OSError as exc:
            _storage_failed("commit", label, exc)

    def _commit_file(
        self, run_root: Path, relative: Path, data: bytes, *, label: str
    ) -> str:
        """Commit `data` at `relative` under `run_root`; return its SHA-256."""
        try:
            staging_dir = run_root / STAGING_DIR_NAME
            staging_dir.mkdir(parents=True, exist_ok=True)
            (run_root / relative.parent).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _storage_failed("prepare", label, exc)
        staging_path = staging_dir / str(uuid.uuid4())
        try:
            self._stage_bytes(staging_path, data, label=label)
        except OSError as exc:
            _storage_failed("stage", label, exc)
        digest = sha256_bytes(data)
        try:
            self._rename_staged(staging_path, run_root / relative, label=label)
        except OSError as exc:
            _storage_failed("commit", label, exc)
        return digest

    def write_request(self, run_id: str, document: object) -> str:
        """Write the write-once run request and return its SHA-256."""
        run_root = self._run_root(run_id)
        run_root.mkdir(parents=True, exist_ok=True)
        data = canonical_json_bytes(document)
        return self._commit_file(
            run_root, Path(REQUEST_NAME), data, label="request.json"
        )

    def write_admission(self, run_id: str, document: object) -> str:
        """Write the write-once Run Admission and return its SHA-256."""
        run_root = self._run_root(run_id)
        data = canonical_json_bytes(document)
        return self._commit_file(
            run_root, Path(ADMISSION_NAME), data, label="admission.json"
        )

    def write_operation_artifact(
        self,
        run_id: str,
        operation_seq: int,
        attempt_seq: int,
        filename: str,
        data: bytes,
        *,
        label: str | None = None,
    ) -> tuple[str, int, str]:
        """Exclusively write an operation attempt artifact.

        Returns (relative_path, byte_length, sha256), where relative_path
        is relative to the run root per ticket 023.
        """
        if operation_seq < 1 or attempt_seq < 1:
            fail("INVALID_COORDINATE", "Operation and attempt sequences must be >= 1")
        if "/" in filename or "\\" in filename or not filename.strip():
            fail("INVALID_PATH", "Artifact filename must be a bare filename")
        run_root = self._run_root(run_id)
        rel_parent = (
            Path("artifacts/operations")
            / f"{operation_seq:06d}"
            / "attempts"
            / f"{attempt_seq:06d}"
        )
        rel_path = (rel_parent / filename).as_posix()
        sha = self._commit_file(run_root, Path(rel_path), data, label=label or filename)
        return rel_path, len(data), sha

    def write_idea_artifact(
        self,
        run_id: str,
        idea_index: int,
        filename: str,
        data: bytes,
        *,
        label: str | None = None,
    ) -> tuple[str, int, str]:
        """Exclusively write an idea artifact under artifacts/ideas/<idea_index:06d>/.

        Returns (relative_path, byte_length, sha256).
        """
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
        if filename not in ALLOWED_IDEA_FILENAMES:
            fail(
                "INVALID_PATH",
                f"Artifact filename must be one of {sorted(ALLOWED_IDEA_FILENAMES)}, got '{filename}'",
            )
        run_root = self._run_root(run_id)
        rel_parent = Path("artifacts/ideas") / f"{idea_index:06d}"
        rel_path = (rel_parent / filename).as_posix()
        sha = self._commit_file(run_root, Path(rel_path), data, label=label or filename)
        return rel_path, len(data), sha

    def _validate_run_relative_path(
        self, relative_path: object, *, label: str = "Artifact path"
    ) -> Path:
        if not isinstance(relative_path, str) or not relative_path:
            fail("INVALID_PATH", f"{label} must be a non-empty relative POSIX path")
        if "\\" in relative_path:
            fail("INVALID_PATH", f"{label} must be a POSIX relative path")
        if (
            relative_path != relative_path.strip()
            or relative_path.startswith("./")
            or relative_path.endswith("/")
        ):
            fail(
                "INVALID_PATH",
                f"{label} must be normalized under the run root: {relative_path}",
            )
        relative = Path(relative_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            fail(
                "INVALID_PATH",
                f"{label} must be normalized under the run root: {relative_path}",
            )
        return relative

    def write_artifact(
        self,
        run_id: str,
        relative_path: str,
        data: bytes,
        *,
        label: str | None = None,
    ) -> tuple[str, int, str]:
        """Exclusively write a run artifact at a fixed template relative path.

        The path must be a normalized run-root-relative POSIX path without
        escape segments; parents are created as needed. Returns
        (relative_path, byte_length, sha256).
        """
        relative = self._validate_run_relative_path(
            relative_path, label=label or "Artifact path"
        )
        run_root = self._run_root(run_id)
        current = run_root
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                fail(
                    "SYMLINK_FORBIDDEN",
                    f"Artifact path component is a symlink: {current.name}",
                )
        if (run_root / relative).is_symlink():
            fail(
                "SYMLINK_FORBIDDEN",
                f"Artifact target is a symlink: {relative.name}",
            )
        sha = self._commit_file(run_root, relative, data, label=label or relative.name)
        return relative.as_posix(), len(data), sha

    def write_seal(self, run_id: str, document: object) -> str:
        """Write the write-once run seal and return its SHA-256."""
        if not isinstance(document, dict):
            fail("INVALID_SEAL", "Seal document must be a dictionary")
        if document.get("schema_version") != RUN_SEAL_SCHEMA_VERSION:
            fail(
                "INVALID_SEAL",
                f"Invalid seal schema_version: {document.get('schema_version')}",
            )
        if document.get("run_id") != run_id:
            fail("INVALID_SEAL", "Seal document run_id does not match target run_id")
        for req_field in (
            "terminal_outcome",
            "request_sha256",
            "admission_sha256",
            "final_event",
            "artifact_inventory",
        ):
            if req_field not in document:
                fail(
                    "INVALID_SEAL", f"Seal document missing required field: {req_field}"
                )
        run_root = self._run_root(run_id)
        data = canonical_json_bytes(document)
        return self._commit_file(run_root, Path(SEAL_NAME), data, label="seal.json")

    def build_artifact_inventory(self, run_id: str) -> list[dict[str, Any]]:
        """Collect all committed artifacts under artifacts/, sorted by relative_path."""
        run_root = self._run_root(run_id)
        artifacts_dir = run_root / "artifacts"
        if not artifacts_dir.is_dir():
            return []

        files: list[dict[str, Any]] = []
        for path in artifacts_dir.rglob("*"):
            if path.is_symlink():
                fail(
                    "SYMLINK_FORBIDDEN",
                    f"Committed artifact is a symlink: {path.name}",
                )
            if path.is_file():
                rel_path = path.relative_to(run_root).as_posix()
                data = path.read_bytes()
                media_type = (
                    "application/json"
                    if rel_path.endswith(".json")
                    else "application/octet-stream"
                )
                files.append(
                    {
                        "byte_length": len(data),
                        "media_type": media_type,
                        "relative_path": rel_path,
                        "sha256": sha256_bytes(data),
                    }
                )
        files.sort(key=lambda item: item["relative_path"])
        return files

    def read_artifact(
        self,
        run_id: str,
        relative_path: str,
        expected_sha256: str | None = None,
        *,
        label: str | None = None,
    ) -> bytes:
        """Read a run artifact and optionally verify its SHA-256."""
        relative = self._validate_run_relative_path(
            relative_path, label=label or "Artifact path"
        )
        run_root = self._run_root(run_id)
        current = run_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                fail(
                    "SYMLINK_FORBIDDEN",
                    f"Artifact path component is a symlink: {current.name}",
                )
        target = current
        try:
            resolved = target.resolve(strict=True)
        except OSError:
            fail("MISSING_ARTIFACT", f"{label or relative_path} does not exist")
        if not resolved.is_relative_to(run_root.resolve()):
            fail("PATH_ESCAPE", "Artifact path escapes the run root")
        data = target.read_bytes()
        if expected_sha256 is not None and sha256_bytes(data) != expected_sha256:
            fail(
                "HASH_MISMATCH",
                f"{label or relative_path} hash mismatch",
                expected=expected_sha256,
            )
        return data

    def read_event(self, run_id: str, event_seq: int) -> dict[str, Any]:
        """Read and parse an event from events/<event_seq:08d>.json."""
        if (
            not isinstance(event_seq, int)
            or isinstance(event_seq, bool)
            or event_seq < 1
        ):
            fail("INVALID_COORDINATE", "event_seq must be an integer >= 1")
        data = self.read_artifact(run_id, f"{EVENTS_DIR}/{event_seq:08d}.json")
        return parse_json_bytes(data, label=f"event {event_seq}")

    def append_event(
        self,
        run_id: str,
        event: dict[str, Any],
        *,
        prev_event_hash: str | None = None,
    ) -> EventRecord:
        """Append one immutable event to the linked hash chain.

        writer_epoch is a fencing token (ticket 023): epochs are monotonically
        non-decreasing along the chain, so a stale writer's append fails
        closed with STALE_WRITER_EPOCH. Epoch-less lifecycle events (the
        preflight prefix) are exempt.
        """
        run_root = self._run_root(run_id)
        events_dir = run_root / EVENTS_DIR
        try:
            events_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _storage_failed("prepare", "events directory", exc)

        existing = sorted(
            path
            for path in events_dir.iterdir()
            if path.is_file() and re.fullmatch(r"[0-9]{8}\.json", path.name)
        )
        last_document: dict[str, Any] | None = None
        if existing:
            last_path = existing[-1]
            last_seq = int(last_path.stem)
            last_bytes = last_path.read_bytes()
            parsed_last = parse_json_bytes(last_bytes, label=f"event {last_seq}")
            if not isinstance(parsed_last, dict):
                fail("INVALID_EVENT", f"Event {last_seq} is not a JSON object")
            last_document = parsed_last
            if last_document.get("event_hash") != sha256_bytes(
                canonical_json_bytes(
                    {
                        key: value
                        for key, value in last_document.items()
                        if key != "event_hash"
                    }
                )
            ):
                fail("HASH_MISMATCH", f"Event {last_seq} fails chain verification")
            event_seq = last_seq + 1
            computed_prev = last_document["event_hash"]
        else:
            event_seq = 1
            computed_prev = None

        if prev_event_hash is not None and prev_event_hash != computed_prev:
            fail(
                "MISSING_EVENT",
                "The supplied prev_event_hash does not extend the canonical chain",
            )

        incoming_epoch = event.get("writer_epoch")
        if incoming_epoch is not None:
            if (
                not isinstance(incoming_epoch, int)
                or isinstance(incoming_epoch, bool)
                or incoming_epoch < 1
            ):
                fail(
                    "INVALID_EPOCH",
                    f"writer_epoch must be a positive integer, got {incoming_epoch}",
                )
            latest_epoch = self._latest_writer_epoch(existing, last_document)
            if latest_epoch is not None and incoming_epoch < latest_epoch:
                fail(
                    "STALE_WRITER_EPOCH",
                    f"writer_epoch {incoming_epoch} is stale; the chain is already "
                    f"owned by writer epoch {latest_epoch}",
                )

        document: dict[str, Any] = {
            "schema_version": EVIDENCE_EVENT_SCHEMA_VERSION,
            "run_id": run_id,
            "event_seq": event_seq,
            "event_type": event["event_type"],
            "recorded_at": event.get("recorded_at", _now()),
            "payload": event.get("payload", {}),
            "prev_event_hash": computed_prev,
        }
        if "writer_epoch" in event:
            document["writer_epoch"] = event["writer_epoch"]
        if "operation" in event:
            document["operation"] = event["operation"]
        if "pipeline_position" in event:
            document["pipeline_position"] = event["pipeline_position"]
        if "artifact_refs" in event:
            document["artifact_refs"] = event["artifact_refs"]
        if "request_sha256" in event:
            document["request_sha256"] = event["request_sha256"]
        if "admission_sha256" in event:
            document["admission_sha256"] = event["admission_sha256"]
        event_hash = sha256_bytes(
            canonical_json_bytes(
                {key: value for key, value in document.items() if key != "event_hash"}
            )
        )
        document["event_hash"] = event_hash

        data = canonical_json_bytes(document)
        self._commit_file(
            run_root,
            Path(EVENTS_DIR) / f"{event_seq:08d}.json",
            data,
            label=f"event {event_seq}",
        )
        return EventRecord(
            run_id=run_id,
            event_seq=event_seq,
            event_hash=event_hash,
            prev_event_hash=document["prev_event_hash"],
        )

    def _latest_writer_epoch(
        self, existing: list[Path], last_document: dict[str, Any] | None
    ) -> int | None:
        """Return the newest writer_epoch on the chain (epochs are monotone)."""
        document = last_document
        for index in range(len(existing) - 1, -1, -1):
            if document is None:
                parsed = parse_json_bytes(
                    existing[index].read_bytes(), label=f"event {existing[index].stem}"
                )
                if not isinstance(parsed, dict):
                    fail(
                        "INVALID_EVENT",
                        f"Event {existing[index].stem} is not a JSON object",
                    )
                document = parsed
            epoch = document.get("writer_epoch")
            if epoch is not None:
                if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 1:
                    fail(
                        "INVALID_EVENT",
                        f"Event {existing[index].stem} carries an invalid writer_epoch",
                    )
                return epoch
            document = None
        return None

    def verify_chain(self, run_id: str) -> int:
        """Verify the full event hash chain; return the verified event count."""
        run_root = self._run_root(run_id)
        events_dir = run_root / EVENTS_DIR
        if not events_dir.is_dir():
            fail("MISSING_EVENT", "The run has no events directory")
        files = sorted(events_dir.iterdir())
        expected_prev: str | None = None
        count = 0
        for index, path in enumerate(files, start=1):
            if path.name != f"{index:08d}.json":
                fail("INVALID_EVENT", "Event files are not a contiguous 1..N sequence")
            document = parse_json_bytes(path.read_bytes(), label=f"event {index}")
            if not isinstance(document, dict):
                fail("INVALID_EVENT", f"Event {index} is not a JSON object")
            if document.get("run_id") != run_id:
                fail("IDENTITY_MISMATCH", f"Event {index} belongs to another run")
            if document.get("event_seq") != index:
                fail("INVALID_EVENT", f"Event {index} carries a wrong event_seq")
            if document.get("prev_event_hash") != expected_prev:
                fail("HASH_MISMATCH", f"Event {index} breaks the hash chain")
            expected_event_hash = document.get("event_hash")
            if expected_event_hash != sha256_bytes(
                canonical_json_bytes(
                    {
                        key: value
                        for key, value in document.items()
                        if key != "event_hash"
                    }
                )
            ):
                fail("HASH_MISMATCH", f"Event {index} fails event_hash verification")
            expected_prev = expected_event_hash
            count += 1
        return count

    # -- Resume support (ticket 10) -----------------------------------------

    def run_root_exists(self, run_id: str) -> bool:
        """True when the exact run root exists; a symlinked root fails closed."""
        run_root = self._run_root(run_id)
        if run_root.is_symlink():
            fail("SYMLINK_FORBIDDEN", f"The run root is a symlink: {run_id}")
        return run_root.is_dir()

    def artifact_exists(self, run_id: str, relative_path: str) -> bool:
        """True when the run-root-relative regular file exists."""
        run_root = self._run_root(run_id)
        target = run_root / relative_path
        return target.is_file() and not target.is_symlink()

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        """Load all events in sequence order. Not a verifier: callers must run
        verify_chain first when integrity matters (resume always does)."""
        run_root = self._run_root(run_id)
        events_dir = run_root / EVENTS_DIR
        if not events_dir.is_dir():
            return []
        documents: list[dict[str, Any]] = []
        for path in sorted(events_dir.iterdir()):
            if path.is_file() and re.fullmatch(r"[0-9]{8}\.json", path.name):
                document = parse_json_bytes(
                    path.read_bytes(), label=f"event {path.stem}"
                )
                if not isinstance(document, dict):
                    fail("INVALID_EVENT", f"Event {path.stem} is not a JSON object")
                documents.append(document)
        return documents

    def list_committed_artifact_paths(self, run_id: str) -> list[str]:
        """List all files under artifacts/ as run-root-relative POSIX paths.

        Any symlink inside the committed namespace fails closed.
        """
        run_root = self._run_root(run_id)
        artifacts_dir = run_root / ARTIFACTS_DIR
        if artifacts_dir.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The artifacts directory is a symlink")
        if not artifacts_dir.is_dir():
            return []
        paths: list[str] = []
        for path in sorted(artifacts_dir.rglob("*")):
            if path.is_symlink():
                fail(
                    "SYMLINK_FORBIDDEN",
                    f"Committed artifact is a symlink: "
                    f"{path.relative_to(run_root).as_posix()}",
                )
            if path.is_file():
                paths.append(path.relative_to(run_root).as_posix())
        return paths

    def clear_staging(self, run_id: str) -> None:
        """Best-effort removal of staging residue after chain verification.

        Staging bytes are never evidence (ticket 025); cleanup failure must not
        block a resume.
        """
        run_root = self._run_root(run_id)
        staging_dir = run_root / STAGING_DIR_NAME
        if staging_dir.is_symlink() or not staging_dir.is_dir():
            return
        for path in sorted(staging_dir.rglob("*"), reverse=True):
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                pass

    def quarantine_artifact(
        self, run_id: str, relative_path: str, *, incident: str
    ) -> dict[str, Any]:
        """Move an orphan final artifact into the run-local quarantine area.

        The approved rename-before-event crash window can leave a final
        artifact that no event references (tickets 023/025). The bytes are
        preserved under quarantine/<incident>/ and leave the committed
        artifacts/ namespace. Returns the incident record for the
        `orphans_quarantined` lifecycle event.
        """
        if (
            not isinstance(relative_path, str)
            or "\\" in relative_path
            or not relative_path
        ):
            fail("INVALID_PATH", "Orphan path must be a POSIX relative path")
        relative = Path(relative_path)
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            fail("INVALID_PATH", f"Orphan path is not normalized: {relative_path}")
        if not isinstance(incident, str) or not re.fullmatch(r"[a-z0-9-]+", incident):
            fail("INVALID_PATH", f"Invalid quarantine incident name: {incident}")
        run_root = self._run_root(run_id)
        source = run_root / relative
        if source.is_symlink() or not source.is_file():
            fail("MISSING_ARTIFACT", f"Orphan artifact is missing: {relative_path}")
        data = source.read_bytes()
        target_relative = Path(QUARANTINE_DIR_NAME) / incident / relative
        target = run_root / target_relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, target)
            _fsync_directory(target.parent)
            _fsync_directory(source.parent)
        except OSError as exc:
            _storage_failed("quarantine", relative_path, exc)
        # Prune parent directories left empty under artifacts/ (best-effort).
        artifacts_root = run_root / ARTIFACTS_DIR
        parent = source.parent
        while parent != artifacts_root and parent != run_root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return {
            "byte_length": len(data),
            "quarantine_path": target_relative.as_posix(),
            "relative_path": relative_path,
            "sha256": sha256_bytes(data),
        }
