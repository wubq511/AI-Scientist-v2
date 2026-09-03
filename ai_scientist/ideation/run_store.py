"""Run-scoped, exclusive-create evidence storage for Ideation Runs.

Implements the ticket-04 slice of the run identity and evidence layout
contract: a fixed repo-relative private trust root, exclusive-create run
roots, write-once request/admission documents, and a strictly linked
canonical event hash chain.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import uuid
from typing import Any

from .canonical import canonical_json_bytes, parse_json_bytes, sha256_bytes
from .contract import _now
from .errors import fail

RUN_REQUEST_SCHEMA_VERSION = "run-request-v1.0.0"
RUN_ADMISSION_SCHEMA_VERSION = "run-admission-v1.0.0"
EVIDENCE_EVENT_SCHEMA_VERSION = "evidence-event-v1.0.0"
RUN_SEAL_SCHEMA_VERSION = "run-seal-v1.0.0"

RUNS_ROOT_RELPATH = Path("artifacts/ideation-runs")
REQUEST_NAME = "request.json"
ADMISSION_NAME = "admission.json"
SEAL_NAME = "seal.json"
EVENTS_DIR = "events"

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


def _write_exclusive(path: Path, data: bytes, *, label: str) -> None:
    """Durably write `data` to `path` once; an existing file fails closed."""
    if path.exists() or path.is_symlink():
        fail(
            "ARTIFACT_EXISTS",
            f"{label} already exists; write-once artifacts cannot be overwritten",
        )
    parent = path.parent
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    _fsync_directory(parent)


class RunStore:
    """Exclusive-create, run-scoped storage bound to one workspace root."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve(strict=True)
        self.runs_root = self.workspace_root / RUNS_ROOT_RELPATH

    def _run_root(self, run_id: str) -> Path:
        parsed = _validate_run_id(run_id)
        if self.runs_root.is_symlink():
            fail("SYMLINK_FORBIDDEN", "The ideation-runs root is a symlink")
        return self.runs_root / parsed

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

    def write_request(self, run_id: str, document: object) -> str:
        """Write the write-once run request and return its SHA-256."""
        run_root = self._run_root(run_id)
        run_root.mkdir(parents=True, exist_ok=True)
        data = canonical_json_bytes(document)
        _write_exclusive(run_root / REQUEST_NAME, data, label="request.json")
        return sha256_bytes(data)

    def write_admission(self, run_id: str, document: object) -> str:
        """Write the write-once Run Admission and return its SHA-256."""
        run_root = self._run_root(run_id)
        data = canonical_json_bytes(document)
        _write_exclusive(run_root / ADMISSION_NAME, data, label="admission.json")
        return sha256_bytes(data)

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
        target_dir = run_root / rel_parent
        target_dir.mkdir(parents=True, exist_ok=True)
        rel_path = (rel_parent / filename).as_posix()
        target_file = run_root / rel_path
        _write_exclusive(target_file, data, label=label or filename)
        sha = sha256_bytes(data)
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
        target_dir = run_root / rel_parent
        target_dir.mkdir(parents=True, exist_ok=True)
        rel_path = (rel_parent / filename).as_posix()
        target_file = run_root / rel_path
        _write_exclusive(target_file, data, label=label or filename)
        sha = sha256_bytes(data)
        return rel_path, len(data), sha

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
        _write_exclusive(run_root / SEAL_NAME, data, label="seal.json")
        return sha256_bytes(data)

    def build_artifact_inventory(self, run_id: str) -> list[dict[str, Any]]:
        """Collect all committed artifacts under artifacts/, sorted by relative_path."""
        run_root = self._run_root(run_id)
        artifacts_dir = run_root / "artifacts"
        if not artifacts_dir.is_dir():
            return []

        files: list[dict[str, Any]] = []
        for path in artifacts_dir.rglob("*"):
            if path.is_file() and not path.is_symlink():
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
        run_root = self._run_root(run_id)
        target = run_root / relative_path
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
        """Append one immutable event to the linked hash chain."""
        run_root = self._run_root(run_id)
        events_dir = run_root / EVENTS_DIR
        events_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(
            path
            for path in events_dir.iterdir()
            if path.is_file() and re.fullmatch(r"[0-9]{8}\.json", path.name)
        )
        if existing:
            last_path = existing[-1]
            last_seq = int(last_path.stem)
            last_bytes = last_path.read_bytes()
            last_document = parse_json_bytes(last_bytes, label=f"event {last_seq}")
            if not isinstance(last_document, dict):
                fail("INVALID_EVENT", f"Event {last_seq} is not a JSON object")
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
        event_path = events_dir / f"{event_seq:08d}.json"
        _write_exclusive(event_path, data, label=f"event {event_seq}")
        return EventRecord(
            run_id=run_id,
            event_seq=event_seq,
            event_hash=event_hash,
            prev_event_hash=document["prev_event_hash"],
        )

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
