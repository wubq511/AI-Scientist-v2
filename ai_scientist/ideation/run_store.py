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

RUNS_ROOT_RELPATH = Path("artifacts/ideation-runs")
REQUEST_NAME = "request.json"
ADMISSION_NAME = "admission.json"
EVENTS_DIR = "events"

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
