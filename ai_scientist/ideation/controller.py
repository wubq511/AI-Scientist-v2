"""Ideation Run Controller (tickets 07, 08, 09, 10, 023, 024, 025, 026, 038).

Drives the approved generation/reflection loop for an admitted Ideation Run:
executes model inference rounds via DeepSeek adapter, invokes Scoped Literature
Retriever for evidence, enforces the FinalizeIdea gate (payload hygiene,
seven-field structure, Declared Grounding, and within-run duplicates in the
approved fixed priority), commits accepted ideas atomically before advancing to
the next generation, seals terminal outcomes -- success or explicit failed --
with a canonical seal.json, and suspends without a seal on environment-class
failures. The resume path (ticket 10) re-verifies the chain and admission pins,
rebuilds control state from canonical events/artifacts under a new writer
epoch, and continues a suspended run to its terminal seal.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import signal
import threading
from typing import Any, Iterator, NamedTuple, Sequence

from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
    workspace_relative_path,
)
from .contract import _now
from .profiles import PromptProfile, require_executable_profile
from .profiles import (
    render_generation_prompt as _render_generation_prompt,
)
from .profiles import (
    render_reflection_prompt as _render_reflection_prompt,
)
from .profiles import (
    render_system_prompt as _render_system_prompt,
)
from .profiles import (
    resolve_admission_profile as _resolve_admission_profile,
)
from .deepseek import (
    DEEPSEEK_ADAPTER_SCHEMA_VERSION,
    DeepSeekAdapter,
    DeepSeekMessage,
    DeepSeekRequest,
    ModelRoundError,
    ModelRoundResult,
    TERMINAL_FAILURES,
    parse_stored_response_content,
)
from .errors import IdeationInputError, RunInterrupted, fail
from .retrieval import ScopedLiteratureRetriever, bind_corpus
from .run_store import (
    RUN_SEAL_SCHEMA_VERSION,
    RunStore,
)

IDEA_SIDECAR_SCHEMA_VERSION = "idea-sidecar-v1.0.0"
ACTION_OUTCOME_SCHEMA_VERSION = "action-outcome-v1.0.0"
WORKSHOP_RENDERING_VERSION = "raw_markdown_v1"

# Final-round convergence (Proposal 002 remediation, Layer 1): the last
# reflection round of a generation must end with FinalizeIdea. The controller
# records a closed correction outcome for the violating response and re-asks
# once on the same operation as attempt 2. The suffix below is controller-
# owned (never a Prompt Profile template), so the profile registry stays
# byte-frozen and both comparison arms receive the identical corrective bytes.
FINAL_ROUND_CORRECTION_OUTCOME = "final_round_correction"
FINAL_ROUND_FINALIZE_REQUIRED_CODE = "FINAL_ROUND_FINALIZE_REQUIRED"
FINAL_ROUND_CORRECTION_MARKER = "[CONTROLLER CORRECTION]"


def _final_round_correction_suffix(feedback_text: str) -> str:
    """Deterministic corrective suffix appended to the final round's prompt.

    Rebuilt from the event chain's correction feedback on resume, so the
    re-ask request is byte-identical to the live one.
    """
    return (
        f"\n\n{FINAL_ROUND_CORRECTION_MARKER} This was the final reflection "
        "round; there is no next round. Your last response did not finalize "
        f"an idea. Feedback: {feedback_text}\n"
        "You must now respond with exactly:\n\n"
        "ACTION:\nFinalizeIdea\n\n"
        "ARGUMENTS:\n"
        '{"idea": { ...the seven-field IDEA JSON... }, '
        '"grounding": ["paper_id", ...]}\n\n'
        "Declare grounding only with paper_ids retrieved in this generation. "
        "This is the last attempt: a response that is not a valid FinalizeIdea "
        "ends the run."
    )


MODEL_FIXABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "PARSE_ERROR",
        "UNKNOWN_ACTION",
        "INVALID_ARGUMENTS_JSON",
        "INVALID_QUERY",
        "QUERY_TOO_LONG",
        "GATE_REJECTED",
        "INVALID_IDEA_STRUCTURE",
        "INVALID_GROUNDING",
        "EMPTY_GROUNDING",
        "UNRETRIEVED_PAPER",
        "DUPLICATE_IDEA_NAME",
        "DUPLICATE_IDEA",
    }
)

# Terminal (non-model-fixable) codes that seal the run `failed` (Ticket 025).
# Sealed failure reasons are the approved closed vocabulary only:
# - Controller terminal conditions (Ticket 026 hygiene gate, 020 backstop).
# - Deterministic adapter failures from the closed taxonomy (Ticket 025
#   terminal row), surfaced as `reason_kind=provider`.
# - Retriever/evidence boundary failures (Ticket 020), surfaced verbatim as
#   `reason_kind=retriever_evidence`.
CONTROLLER_TERMINAL_CODES: frozenset[str] = frozenset(
    {
        "PAYLOAD_HYGIENE_VIOLATION",
        "PAYLOAD_CORRUPT",
        "RETRIEVAL_BACKSTOP_FAILED",
    }
)

ADAPTER_TERMINAL_CODES: frozenset[str] = TERMINAL_FAILURES

RETRIEVER_EVIDENCE_TERMINAL_CODES: frozenset[str] = frozenset(
    {
        "AUDIT_RELEASE_GATE_FAILED",
        "HASH_MISMATCH",
        "IDENTITY_MISMATCH",
        "INVALID_CORPUS",
        "INVALID_SCORE",
        "MISSING_CORPUS",
        "NO_ELIGIBLE_CANDIDATES",
        "PATH_ESCAPE",
        "SYMLINK_FORBIDDEN",
    }
)

# Single source of truth for the sealed failure vocabulary: reason code ->
# reason kind. Unknown codes fail closed in _seal_failed_run (Ticket 025).
TERMINAL_REASON_KINDS: dict[str, str] = {
    code: "controller" for code in CONTROLLER_TERMINAL_CODES
} | {code: "provider" for code in ADAPTER_TERMINAL_CODES}
TERMINAL_REASON_KINDS.update(
    {code: "retriever_evidence" for code in RETRIEVER_EVIDENCE_TERMINAL_CODES}
)

# Versioned payload hygiene pattern list (Ticket 026 / VM-LEAKAGE-02).
# Patterns derive from the tickets 023/024 identifier formats: the `case_id`
# schema shape, canonical SHA-256 hex digests, canonical lowercase UUIDv4 run
# identifiers, the fixed run trust roots, and internal lifecycle artifact
# names. Retrieved paper_id values are 40-hex (ticket 020) and deliberately
# NOT matched: they are model-visible evidence, not private identifiers.
PAYLOAD_HYGIENE_PATTERNS_VERSION = "payload-hygiene-patterns-v1.0.0"
PAYLOAD_HYGIENE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("case_id_format", re.compile(r"case-[0-9a-f]{32}")),
    ("sha256_hex", re.compile(r"\b[0-9a-f]{64}\b")),
    (
        "uuidv4_format",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
        ),
    ),
    (
        "run_root_path",
        re.compile(r"artifacts/ideation-runs/|evidence/ideation-runs/|ideation-runs/"),
    ),
    (
        "internal_evidence_path",
        re.compile(
            r"data/raw/|artifacts/operations/|artifacts/ideas/|artifacts/validations/"
            r"|projections/|events/|reviews/"
        ),
    ),
    (
        "internal_artifact_filename",
        re.compile(
            r"\b(admission|request|seal|bundle-manifest)\.json\b|\bgrounding\.json\b|\bsidecar\.json\b"
        ),
    ),
)

# Model-visible FinalizeIdea surface re-parseable from raw submission bytes.
HYGIENE_SCAN_ARGUMENTS_PATTERN = re.compile(
    r"ARGUMENTS:\s*(.*?)(?:\nTHOUGHT:|\Z)", re.DOTALL | re.IGNORECASE
)

REQUIRED_IDEA_FIELDS: tuple[str, ...] = (
    "Name",
    "Title",
    "Short Hypothesis",
    "Related Work",
    "Abstract",
    "Experiments",
    "Risk Factors and Limitations",
)

MODEL_VISIBLE_ACTIONS: frozenset[str] = frozenset({"SearchLiterature", "FinalizeIdea"})

ACTION_PATTERN = re.compile(r"ACTION:\s*(.*?)\s*ARGUMENTS:", re.DOTALL | re.IGNORECASE)
ARGUMENTS_PATTERN = re.compile(
    r"ARGUMENTS:\s*(.*?)(?:$|\nTHOUGHT:|\n$)", re.DOTALL | re.IGNORECASE
)


def build_tool_catalog() -> tuple[str, str]:
    """Return the active profile's model-visible tool descriptions and names."""
    from .profiles import CROSS_DOMAIN_V1

    return (
        CROSS_DOMAIN_V1.tool_descriptions_template,
        CROSS_DOMAIN_V1.tool_names_template,
    )


def build_system_prompt() -> str:
    """Build the cross-domain system prompt; baseline has no default path."""
    from .profiles import CROSS_DOMAIN_V1

    return _render_system_prompt(CROSS_DOMAIN_V1)


def _failure_message(exc: ModelRoundError) -> str:
    """Extract the provider failure message from a ModelRoundError."""
    message = exc.failure.message
    if isinstance(message, str) and message:
        return message
    return str(exc)


@contextmanager
def _signal_interrupt_guard() -> Iterator[None]:
    """Abort the run writer immediately on SIGINT/SIGTERM (ticket 025).

    The handler raises RunInterrupted inside the main thread, so an in-flight
    blocking transport call is not awaited (PEP 475: a raising handler is not
    retried). Outside the main thread no handler can be installed; injection
    of RunInterrupted remains possible for tests.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def _handler(signum: int, frame: Any) -> None:
        raise RunInterrupted(signal.Signals(signum).name)

    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig, handler in ((signal.SIGINT, _handler), (signal.SIGTERM, _handler)):
        signal.signal(sig, handler)
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def parse_action_and_arguments(response_text: str) -> tuple[str, dict[str, Any]]:
    """Extract and parse ACTION and ARGUMENTS from model response."""
    action_match = ACTION_PATTERN.search(response_text)
    arguments_match = ARGUMENTS_PATTERN.search(response_text)
    if not action_match or not arguments_match:
        fail("PARSE_ERROR", "Failed to parse ACTION and ARGUMENTS from response")

    action = action_match.group(1).strip()
    arguments_text = arguments_match.group(1).strip()

    if arguments_text.startswith("```json"):
        json_match = re.search(r"```json\s*(.*?)\s*```", arguments_text, re.DOTALL)
        if json_match:
            arguments_text = json_match.group(1).strip()
    elif arguments_text.startswith("```"):
        generic_match = re.search(r"```\s*(.*?)\s*```", arguments_text, re.DOTALL)
        if generic_match:
            arguments_text = generic_match.group(1).strip()

    try:
        arguments_obj = json.loads(arguments_text)
    except json.JSONDecodeError as exc:
        fail("INVALID_ARGUMENTS_JSON", f"Arguments are not valid JSON: {exc}")

    if not isinstance(arguments_obj, dict):
        fail("INVALID_ARGUMENTS_JSON", "Arguments must be a JSON object")

    return action, arguments_obj


def _check_string_hygiene(val: str, field_name: str) -> None:
    """Ensure string does not contain null bytes, surrogate codes, or malformed characters."""
    if "\x00" in val:
        fail("PAYLOAD_CORRUPT", f"Field '{field_name}' contains null byte")
    for ch in val:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            fail(
                "PAYLOAD_CORRUPT", f"Field '{field_name}' contains surrogate code point"
            )


def scan_payload_hygiene(text: str) -> list[dict[str, Any]]:
    """Scan raw FinalizeIdea submission text for private identifier patterns.

    Returns one entry per hit: {"pattern_id", "pattern_version", "span"}.
    The report deliberately carries no secret material: only the matched
    pattern identity and its character span (Ticket 026 / VM-LEAKAGE-02).
    """
    hits: list[dict[str, Any]] = []
    for pattern_id, pattern in PAYLOAD_HYGIENE_PATTERNS:
        for match in pattern.finditer(text):
            hits.append(
                {
                    "pattern_id": pattern_id,
                    "pattern_version": PAYLOAD_HYGIENE_PATTERNS_VERSION,
                    "span": [match.start(), match.end()],
                }
            )
    return hits


def validate_idea_structure(idea: Any) -> dict[str, Any]:
    """Validate 7-field typed structure per Ticket 008 and Ticket 024."""
    if not isinstance(idea, dict):
        fail("INVALID_IDEA_STRUCTURE", "Idea payload must be a dictionary")

    extra_keys = set(idea.keys()) - set(REQUIRED_IDEA_FIELDS)
    if extra_keys:
        fail(
            "INVALID_IDEA_STRUCTURE",
            f"Idea contains unknown fields: {sorted(extra_keys)}",
        )

    missing_keys = set(REQUIRED_IDEA_FIELDS) - set(idea.keys())
    if missing_keys:
        fail(
            "INVALID_IDEA_STRUCTURE",
            f"Idea lacks required fields: {sorted(missing_keys)}",
        )

    # Name descriptor: lowercase alphanumeric with underscores
    name_val = idea.get("Name")
    if not isinstance(name_val, str) or not re.match(r"^[a-z0-9_]+$", name_val):
        fail(
            "INVALID_IDEA_STRUCTURE",
            "Idea field 'Name' must be a non-empty lowercase string with letters, numbers, and underscores only",
        )

    # 4 remaining string fields
    for field in (
        "Title",
        "Short Hypothesis",
        "Related Work",
        "Abstract",
    ):
        val = idea.get(field)
        if not isinstance(val, str) or not val.strip():
            fail(
                "INVALID_IDEA_STRUCTURE",
                f"Idea field '{field}' must be a non-empty string",
            )
        _check_string_hygiene(val, field)

    # 2 list-of-string fields
    for field in ("Experiments", "Risk Factors and Limitations"):
        val = idea.get(field)
        if not isinstance(val, list) or not val:
            fail(
                "INVALID_IDEA_STRUCTURE",
                f"Idea field '{field}' must be a non-empty list of strings",
            )
        for idx, item in enumerate(val):
            if not isinstance(item, str) or not item.strip():
                fail(
                    "INVALID_IDEA_STRUCTURE",
                    f"Idea field '{field}[{idx}]' must be a non-empty string",
                )
            _check_string_hygiene(item, f"{field}[{idx}]")

    return {field: idea[field] for field in REQUIRED_IDEA_FIELDS}


def validate_declared_grounding(
    grounding: Any, eligible_paper_ids: set[str]
) -> list[str]:
    """Validate Declared Grounding per Ticket 038."""
    if not isinstance(grounding, list):
        fail("INVALID_GROUNDING", "Grounding must be a list of strings")
    if not grounding:
        fail("EMPTY_GROUNDING", "Declared grounding cannot be empty")

    seen = set()
    normalized_list = []
    for item in grounding:
        if not isinstance(item, str) or not item.strip():
            fail(
                "INVALID_GROUNDING",
                "Grounding items must be non-empty paper_id strings",
            )
        if item.strip() != item:
            fail(
                "INVALID_GROUNDING",
                f"Grounding paper_id '{item}' must not contain leading/trailing whitespace",
            )
        if "/" in item or "\\" in item:
            fail(
                "INVALID_GROUNDING",
                f"Grounding paper_id '{item}' contains invalid path separator",
            )
        _check_string_hygiene(item, "grounding_item")
        if item in seen:
            fail("INVALID_GROUNDING", f"Duplicate paper_id in grounding: {item}")
        seen.add(item)
        if item not in eligible_paper_ids:
            fail(
                "UNRETRIEVED_PAPER",
                f"Paper was not retrieved in this generation: {item}",
            )
        normalized_list.append(item)

    return normalized_list


def format_retrieval_for_reflection(payload: dict[str, Any]) -> str:
    """Format canonical retrieval result for reflection prompt."""
    papers = payload.get("papers", [])
    if not papers:
        return "No relevant literature found for query."

    parts = [f"Found {len(papers)} relevant paper(s):"]
    for paper in papers:
        parts.append(f"\n- Paper ID: {paper['paper_id']}")
        parts.append(f"  Title: {paper.get('title', '')}")
        for seg in paper.get("segments", []):
            parts.append(f"  Abstract: {seg.get('text', '')}")
    return "\n".join(parts)


# Terminal failure message for a payload hygiene hit (Ticket 026). Kept as a
# module constant so resume-time rebuild seals the identical message.
HYGIENE_FAILURE_MESSAGE = (
    "FinalizeIdea submission matched a private identifier hygiene pattern"
)


@dataclass
class _GenerationState:
    """Mutable per-generation control state.

    On resume the state is rebuilt from the committed event chain and
    artifacts instead of being accumulated live (ticket 10).
    """

    msg_history: list[dict[str, str]] = field(default_factory=list)
    last_tool_results: str = ""
    retrieved_paper_ids: set[str] = field(default_factory=set)
    retrieval_op_seqs: list[int] = field(default_factory=list)
    finalized: bool = False


@dataclass(frozen=True)
class PendingResponse:
    """A committed model response whose action processing was interrupted.

    `retrieval_op_seq`/`retrieval_attempt_seq` carry the coordinates of an
    orphaned retrieval request when the interruption happened mid-retrieval
    (the retrieval is re-executed under the same operation_seq).

    `corrective_dispatch` marks a committed final-round corrective response:
    its dispatch records the corrective attempt's outcome (never a new
    correction) at `response_attempt_seq`.
    """

    response_text: str
    model_op_seq: int
    retrieval_op_seq: int | None
    retrieval_attempt_seq: int
    corrective_dispatch: bool = False
    response_attempt_seq: int = 1


@dataclass(frozen=True)
class PendingReexecute:
    """An interrupted model call re-executed under the same operation_seq."""

    op_seq: int
    next_attempt_seq: int


@dataclass(frozen=True)
class RoundResume:
    """Resume coordinates for the generation interrupted mid-round."""

    start_round: int
    state: _GenerationState
    pending: PendingResponse | PendingReexecute | None
    final_round_correction: str | None = None


class _FinalRoundCorrection(NamedTuple):
    """The armed final-round correction of the generation in flight."""

    operation_seq: int
    feedback: str
    round_prompt: str


@dataclass(frozen=True)
class SealFailedCompletion:
    """The run must still be sealed `failed` for a committed terminal failure."""

    reason_code: str
    reason_message: str


@dataclass(frozen=True)
class SealTerminalCompletion:
    """The terminal event is committed; only seal.json is missing."""

    outcome: str
    summary: dict[str, Any]
    event_seq: int
    event_hash: str


@dataclass(frozen=True)
class ResumePlan:
    """Control state rebuilt from the evidence chain for a resumed run."""

    writer_epoch: int
    op_seq: int
    accepted_ideas: tuple[dict[str, Any], ...]
    idea_str_archive: tuple[str, ...]
    disposition_counts: dict[str, int]
    run_has_non_empty_retrieval: bool
    remaining_model_rounds: int
    bookkeeping: tuple[dict[str, Any], ...]
    start_generation: int
    round_resume: RoundResume | None
    terminal: SealFailedCompletion | SealTerminalCompletion | None


class IdeationController:
    """Coordinates the full execution of an admitted Ideation Run."""

    def __init__(
        self,
        workspace_root: Path,
        run_id: str,
        *,
        store: RunStore | None = None,
        adapter: DeepSeekAdapter | None = None,
        retriever: ScopedLiteratureRetriever | None = None,
        writer_epoch: int = 1,
        resume_plan: ResumePlan | None = None,
        progress_stream: Any = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve(strict=True)
        self.run_id = run_id
        self.store = store or RunStore(self.workspace_root)
        self.writer_epoch = writer_epoch
        self.resume_plan = resume_plan
        self.progress_stream = progress_stream

        # Load and verify write-once admission
        admission_bytes = self.store.read_artifact(self.run_id, "admission.json")
        self.admission = parse_json_bytes(admission_bytes, label="admission.json")
        self.admission_sha = sha256_bytes(admission_bytes)
        self.request_sha = self.admission["request_sha256"]

        # Resolve the Prompt Profile pinned by the admission (ticket 01).
        # Legacy admissions without a profile field are interpreted
        # exclusively as ml-baseline-v1; new admissions are re-validated
        # against the registry so model-visible bytes match the pin before
        # the first model operation.
        self.profile: PromptProfile = _resolve_admission_profile(self.admission)
        require_executable_profile(self.profile.profile_id)

        # Verify admission event pin in evidence chain. The `admitted` event
        # is located by type, not by fixed sequence: a preflight re-run during
        # resume (ticket 10) rewrites the preflight events, so its position is
        # not stable.
        admitted_events = [
            event
            for event in self.store.read_events(self.run_id)
            if event.get("event_type") == "admitted"
        ]
        if len(admitted_events) != 1:
            fail(
                "ADMISSION_TAMPERED",
                "Evidence chain must contain exactly one admitted event",
            )
        admitted_event = admitted_events[0]
        if admitted_event.get("admission_sha256") != self.admission_sha:
            fail(
                "ADMISSION_TAMPERED",
                "admission.json content does not match admission hash pinned in event chain",
            )

        # Bound inputs from admission
        self.max_num_generations = self.admission["budgets"]["max_num_generations"]
        self.num_reflections = self.admission["budgets"]["num_reflections"]
        self.case_id = self.admission["case_id"]

        # Read pinned workshop content
        workshop_rel = self.admission["workshop"]["path"]
        workshop_sha = self.admission["workshop"]["sha256"]
        workshop_path = workspace_relative_path(
            self.workspace_root, workshop_rel, label="workshop_path"
        )
        workshop_bytes = workshop_path.read_bytes()
        if sha256_bytes(workshop_bytes) != workshop_sha:
            fail(
                "HASH_MISMATCH", "Pinned workshop content does not match admission hash"
            )
        self.workshop_description = workshop_bytes.decode("utf-8")

        # Bind or use injected retriever
        if retriever is not None:
            self.retriever = retriever
        else:
            corpus_info = self.admission["corpus"]
            self.retriever = bind_corpus(
                self.workspace_root,
                corpus_relpath=corpus_info["path"],
                corpus_sha256=corpus_info["sha256"],
                case_id=self.case_id,
                record_count=corpus_info["record_count"],
                run_id=self.run_id,
                store=self.store,
            )

        # Bind or use injected adapter
        if adapter is not None:
            if getattr(adapter, "run_id", None) is None:
                adapter.run_id = self.run_id
            if getattr(adapter, "store", None) is None:
                adapter.store = self.store
            self.adapter = adapter
        else:
            from .pricing import load_price_table

            price_table = load_price_table(self.workspace_root)
            self.adapter = DeepSeekAdapter(
                price_table=price_table,
                run_id=self.run_id,
                store=self.store,
            )

        # Operation sequence counter (advances monotonically per logical operation)
        self.op_seq = 0
        # Run-level tracking
        self.accepted_ideas: list[dict[str, Any]] = []
        self.idea_str_archive: list[str] = []
        self.run_has_non_empty_retrieval = False
        self.disposition_counts = {"finalized": 0, "budget_exhausted": 0}

    def _report(self, message: str) -> None:
        if self.progress_stream is not None:
            self.progress_stream.write(f"{message}\n")
            self.progress_stream.flush()

    def _next_op_seq(self) -> int:
        self.op_seq += 1
        return self.op_seq

    def run(self) -> dict[str, Any]:
        """Execute the complete generation loop through final seal.

        SIGINT/SIGTERM aborts immediately: the writer best-effort appends an
        `interrupted` lifecycle event and the run stays unsealed for a later
        resume (ticket 025: Run Suspension is not a Terminal Outcome).

        When constructed with a `resume_plan` (ticket 10), the controller
        restores the rebuilt control state, applies bookkeeping completions,
        and continues from the interruption point instead of starting over.
        """
        with _signal_interrupt_guard():
            try:
                if self.resume_plan is not None:
                    return self._run_resumed(self.resume_plan)
                return self._run_loop()
            except RunInterrupted as exc:
                self._record_interrupted(exc.signal_name)
                raise

    def _record_interrupted(self, signal_name: str) -> None:
        """Best-effort `interrupted` event; a recording failure never masks
        the abort (kill -9/power loss leaves no event; the resume-time chain
        verification is the backstop with identical semantics)."""
        try:
            self.store.append_event(
                self.run_id,
                {
                    "event_type": "interrupted",
                    "payload": {"signal": signal_name},
                    "writer_epoch": self.writer_epoch,
                },
            )
        except Exception:
            pass

    def _run_loop(self) -> dict[str, Any]:
        """Execute the complete generation loop through final seal."""
        system_prompt = _render_system_prompt(self.profile)
        sealed = self._run_generations(system_prompt, 0)
        if sealed is not None:
            return sealed
        return self._finish_run()

    def _run_generations(
        self,
        system_prompt: str,
        start_generation: int,
        round_resume: RoundResume | None = None,
    ) -> dict[str, Any] | None:
        """Run generations from `start_generation`; return a mid-loop seal or None."""
        for gen_idx in range(start_generation, self.max_num_generations):
            self._report(
                f"\n🚀 [Generation {gen_idx + 1}/{self.max_num_generations}] 开始探索科研构想..."
            )
            try:
                sealed = self._execute_generation(
                    gen_idx,
                    system_prompt,
                    round_resume=(
                        round_resume if gen_idx == start_generation else None
                    ),
                )
            except IdeationInputError as exc:
                # Retriever/evidence boundary failures in the approved terminal
                # vocabulary terminate the run through an explicit failed seal;
                # no retry, no fallback, and no model-fixable masking
                # (Ticket 020/025). Any other error — including storage/IO
                # failures, which are suspend-class per the 025 disposition
                # table — propagates unsealed for Run Suspension (ticket 10).
                if exc.code in TERMINAL_REASON_KINDS:
                    return self._seal_failed_run(exc.code, exc.message or str(exc))
                raise
            except ModelRoundError as exc:
                # Adapter failures follow the closed disposition table
                # (Ticket 025): terminal provider failures seal `failed`;
                # suspend-class failures propagate for Run Suspension.
                if exc.disposition == "terminal":
                    return self._seal_failed_run(exc.code, _failure_message(exc))
                raise
            if sealed is not None:
                # A terminal condition inside the generation (e.g. hygiene
                # hit) already sealed the run; stop immediately.
                return sealed
        return None

    def _finish_run(self) -> dict[str, Any]:
        """Run-level backstop check and terminal success seal."""
        # Run-level backstop check (Ticket 020 / Ticket 025):
        # The run must have retrieved at least one non-empty retrieval result across all generations.
        if not self.run_has_non_empty_retrieval:
            return self._seal_failed_run(
                "RETRIEVAL_BACKSTOP_FAILED",
                "Run completed without obtaining any non-empty literature retrieval results",
                detail_artifact_name="backstop-violation.json",
                detail={
                    "generations_executed": self.max_num_generations,
                    "disposition_counts": dict(self.disposition_counts),
                    "idea_count": len(self.accepted_ideas),
                },
            )

        return self._seal_success_run()

    def _run_resumed(self, plan: ResumePlan) -> dict[str, Any]:
        """Restore rebuilt control state and continue from the interruption.

        Bookkeeping completions are applied first (events/artifacts whose
        commit was interrupted mid-sequence are finished under the new writer
        epoch), then the plan either completes a pending seal or resumes the
        generation loop at the rebuilt position.
        """
        self.op_seq = plan.op_seq
        self.accepted_ideas = list(plan.accepted_ideas)
        self.idea_str_archive = list(plan.idea_str_archive)
        self.disposition_counts = dict(plan.disposition_counts)
        self.run_has_non_empty_retrieval = plan.run_has_non_empty_retrieval

        for entry in plan.bookkeeping:
            kind = entry["kind"]
            if kind == "append_event":
                self.store.append_event(self.run_id, entry["event"])
            elif kind == "model_fixable_feedback":
                self._record_model_fixable_error(
                    action=entry["action"],
                    error_code=entry["error_code"],
                    error_message=entry["error_message"],
                    operation_seq=entry["operation_seq"],
                    pipeline_pos=entry["pipeline_pos"],
                )
            else:
                fail(
                    "RUN_CORRUPT",
                    f"Unknown resume bookkeeping entry kind: {kind}",
                )

        terminal = plan.terminal
        if isinstance(terminal, SealFailedCompletion):
            return self._seal_failed_run(terminal.reason_code, terminal.reason_message)
        if isinstance(terminal, SealTerminalCompletion):
            return self._write_missing_seal(terminal)

        system_prompt = _render_system_prompt(self.profile)
        sealed = self._run_generations(
            system_prompt, plan.start_generation, plan.round_resume
        )
        if sealed is not None:
            return sealed
        return self._finish_run()

    def _write_missing_seal(self, completion: SealTerminalCompletion) -> dict[str, Any]:
        """Write seal.json for a run whose terminal event is already committed
        (the interruption landed between terminal event and seal write)."""
        result_payload = (
            {"reason_code": completion.summary["reason_code"]}
            if completion.outcome == "failed"
            else {}
        )
        return self._write_seal_document(
            outcome=completion.outcome,
            summary=completion.summary,
            event_seq=completion.event_seq,
            event_hash=completion.event_hash,
            result_payload=result_payload,
        )

    def _seal_success_run(self) -> dict[str, Any]:
        """Commit the terminal event and canonical seal for a successful run."""
        return self._write_terminal_seal(
            outcome="success",
            summary={
                "disposition_counts": dict(self.disposition_counts),
                "idea_count": len(self.accepted_ideas),
                "outcome": "success",
            },
            result_payload={},
        )

    def _seal_failed_run(
        self,
        reason_code: str,
        reason_message: str,
        *,
        detail_artifact_name: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Seal an explicit terminal `failed` outcome (Ticket 025/026/020).

        The failure class is recorded as the final terminal event payload, an
        optional sanitized violation report artifact is persisted before the
        terminal event so the seal inventory can reference it, and the run is
        closed with a canonical seal.json. No model round follows a terminal
        failure and no lower-priority model-fixable feedback can mask it.
        """
        if reason_code not in TERMINAL_REASON_KINDS:
            fail(
                "INVALID_FAILURE_CODE",
                f"Reason code is not an approved terminal outcome code: {reason_code}",
            )
        reason_kind = TERMINAL_REASON_KINDS[reason_code]

        terminal_summary: dict[str, Any] = {
            "disposition_counts": dict(self.disposition_counts),
            "idea_count": len(self.accepted_ideas),
            "outcome": "failed",
            "reason_code": reason_code,
            "reason_kind": reason_kind,
        }

        detail_ref: dict[str, Any] | None = None
        if detail_artifact_name is not None:
            detail_doc: dict[str, Any] = {
                "message": reason_message,
                "reason_code": reason_code,
            }
            if detail is not None:
                detail_doc.update(detail)
            detail_bytes = canonical_json_bytes(detail_doc)
            detail_rel, detail_len, detail_sha = self.store.write_artifact(
                self.run_id,
                f"artifacts/failures/{detail_artifact_name}",
                detail_bytes,
                label="terminal failure detail",
            )
            detail_ref = {
                "byte_length": detail_len,
                "media_type": "application/json",
                "relative_path": detail_rel,
                "role": "terminal_failure_detail",
                "sha256": detail_sha,
            }

        return self._write_terminal_seal(
            outcome="failed",
            summary=terminal_summary,
            result_payload={"reason_code": reason_code},
            extra_artifact_refs=[detail_ref] if detail_ref else [],
        )

    def _write_terminal_seal(
        self,
        *,
        outcome: str,
        summary: dict[str, Any],
        result_payload: dict[str, Any],
        extra_artifact_refs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Append the terminal event, verify the chain, and write seal.json."""
        terminal_payload: dict[str, Any] = dict(summary)
        artifact_refs: list[dict[str, Any]] = list(extra_artifact_refs or [])
        if artifact_refs:
            terminal_payload["artifact_refs"] = artifact_refs
        terminal_record = self.store.append_event(
            self.run_id,
            {
                "event_type": "terminal",
                "payload": terminal_payload,
                "writer_epoch": self.writer_epoch,
            },
        )
        return self._write_seal_document(
            outcome=outcome,
            summary=summary,
            event_seq=terminal_record.event_seq,
            event_hash=terminal_record.event_hash,
            result_payload=result_payload,
        )

    def _write_seal_document(
        self,
        *,
        outcome: str,
        summary: dict[str, Any],
        event_seq: int,
        event_hash: str,
        result_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify the chain, write the canonical seal.json, and build the result."""
        self.store.verify_chain(self.run_id)

        inventory = self.store.build_artifact_inventory(self.run_id)
        seal_document = {
            "admission_sha256": self.admission_sha,
            "artifact_inventory": inventory,
            "final_event": {
                "event_hash": event_hash,
                "event_seq": event_seq,
            },
            "request_sha256": self.request_sha,
            "run_id": self.run_id,
            "schema_version": RUN_SEAL_SCHEMA_VERSION,
            "sealed_at": _now(),
            "terminal_outcome": outcome,
            "terminal_summary": summary,
        }

        seal_sha = self.store.write_seal(self.run_id, seal_document)
        self.store.verify_chain(self.run_id)
        self._report(
            f"\n🔒 [Seal] Run 证据链封印完成 (Terminal Outcome: {outcome}, Run ID: {self.run_id})\n"
        )

        result = {
            "idea_count": len(self.accepted_ideas),
            "run_id": self.run_id,
            "seal_sha256": seal_sha,
            "status": "sealed",
            "terminal_outcome": outcome,
        }
        result.update(result_payload)
        return result

    def _record_model_fixable_error(
        self,
        *,
        action: str | None,
        error_code: str,
        error_message: str,
        operation_seq: int,
        pipeline_pos: dict[str, Any],
        outcome: str = "model_fixable_error",
        attempt_seq: int = 1,
    ) -> str:
        """Record model-fixable error feedback, write artifact, and append action_outcome event.

        `outcome` is the closed action_outcome value; the final-round
        correction records `final_round_correction` instead of the default.
        `attempt_seq` coordinates the feedback artifact with the provider
        attempt that produced the dispatched response.
        """
        feedback_text = (
            f"Error [{error_code}]: {error_message}"
            if error_code not in error_message
            else error_message
        )
        feedback_bytes = feedback_text.encode("utf-8")
        rel_path, byte_length, sha = self.store.write_operation_artifact(
            self.run_id,
            operation_seq,
            attempt_seq,
            "feedback.txt",
            feedback_bytes,
            label="model-fixable error feedback",
        )
        self.store.append_event(
            self.run_id,
            {
                "artifact_refs": [
                    {
                        "byte_length": byte_length,
                        "media_type": "text/plain",
                        "relative_path": rel_path,
                        "role": "model_fixable_feedback",
                        "sha256": sha,
                    }
                ],
                "event_type": "action_outcome",
                "payload": {
                    "action": action or "unknown",
                    "error_code": error_code,
                    "feedback": feedback_text,
                    "outcome": outcome,
                    "schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
                },
                "pipeline_position": pipeline_pos,
                "writer_epoch": self.writer_epoch,
            },
        )
        return feedback_text

    def _record_hygiene_hit(
        self,
        *,
        hits: list[dict[str, Any]],
        operation_seq: int,
        pipeline_pos: dict[str, Any],
    ) -> dict[str, Any]:
        """Record a terminal payload hygiene violation and seal the run failed.

        The private violation report (pattern id + span only, no secret bytes)
        is persisted before the terminal event so the seal inventory carries
        the full failure evidence. No feedback text is produced: the model
        never sees this round again (Ticket 026 hygiene = terminal).
        """
        report_doc = {
            "action": "FinalizeIdea",
            "hits": hits,
            "hit_count": len(hits),
            "patterns_version": PAYLOAD_HYGIENE_PATTERNS_VERSION,
        }
        report_bytes = canonical_json_bytes(report_doc)
        report_rel, report_len, report_sha = self.store.write_operation_artifact(
            self.run_id,
            operation_seq,
            1,
            "hygiene-violation.json",
            report_bytes,
            label="payload hygiene violation report",
        )
        report_ref = {
            "byte_length": report_len,
            "media_type": "application/json",
            "relative_path": report_rel,
            "role": "hygiene_violation_report",
            "sha256": report_sha,
        }
        self.store.append_event(
            self.run_id,
            {
                "artifact_refs": [report_ref],
                "event_type": "action_outcome",
                "payload": {
                    "action": "FinalizeIdea",
                    "error_code": "PAYLOAD_HYGIENE_VIOLATION",
                    "hit_count": len(hits),
                    "outcome": "hygiene_hit",
                    "patterns_version": PAYLOAD_HYGIENE_PATTERNS_VERSION,
                    "schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
                },
                "pipeline_position": pipeline_pos,
                "writer_epoch": self.writer_epoch,
            },
        )
        return self._seal_failed_run(
            "PAYLOAD_HYGIENE_VIOLATION",
            HYGIENE_FAILURE_MESSAGE,
        )

    def _execute_generation(
        self,
        gen_idx: int,
        system_prompt: str,
        round_resume: RoundResume | None = None,
    ) -> dict[str, Any] | None:
        """Execute a single generation with reflection rounds.

        Returns the sealed run result when a terminal condition sealed the run
        mid-generation (payload hygiene hit), otherwise None.

        With `round_resume` (ticket 10) the generation.started event is not
        re-appended, the rebuilt state continues, and the interrupted round
        either replays its committed response or re-executes the model call
        under the same operation_seq with the next attempt_seq.
        """
        if round_resume is None:
            pipeline_pos = {
                "generation_index": gen_idx,
                "idea_index": None,
                "reflection_index": 0,
            }
            self.store.append_event(
                self.run_id,
                {
                    "event_type": "generation.started",
                    "payload": {"generation_index": gen_idx},
                    "pipeline_position": pipeline_pos,
                    "writer_epoch": self.writer_epoch,
                },
            )
            state = _GenerationState()
            start_round = 0
        else:
            state = round_resume.state
            start_round = round_resume.start_round

        prev_ideas_string = "\n\n".join(self.idea_str_archive)
        # Aliases into the (possibly rebuilt) state keep the round loop body
        # identical between the fresh and resumed paths.
        msg_history = state.msg_history
        last_tool_results = state.last_tool_results
        generation_retrieved_paper_ids = state.retrieved_paper_ids
        generation_retrieval_op_seqs = state.retrieval_op_seqs
        generation_finalized = state.finalized

        final_round_correction: _FinalRoundCorrection | None = None

        def _record_fixable_error(
            *,
            action: str | None,
            error_code: str,
            error_message: str,
            operation_seq: int,
            pipeline_pos: dict[str, Any],
        ) -> str:
            """Record a model-fixable outcome and arm the final-round correction.

            On the final reflection round the outcome is the closed
            `final_round_correction` value and arms exactly one corrective
            re-ask on the round's model operation. A corrective dispatch
            itself records a plain `model_fixable_error` at the corrective
            attempt's coordinates and never re-arms.
            """
            nonlocal final_round_correction
            is_final_round = ref_round == self.num_reflections - 1
            # The correction fires only on a final round whose call consumed
            # exactly one physical attempt; a transport retry already
            # occupying attempt 2 leaves no room for the corrective ask, so
            # the outcome stays a plain model_fixable_error.
            correction_armed = (
                is_final_round and not corrective_dispatch and corrective_attempt == 1
            )
            feedback = self._record_model_fixable_error(
                action=action,
                error_code=error_code,
                error_message=error_message,
                operation_seq=operation_seq,
                pipeline_pos=pipeline_pos,
                outcome=(
                    FINAL_ROUND_CORRECTION_OUTCOME
                    if correction_armed
                    else "model_fixable_error"
                ),
                attempt_seq=corrective_attempt,
            )
            if correction_armed:
                final_round_correction = _FinalRoundCorrection(
                    operation_seq=model_op_seq,
                    feedback=feedback,
                    round_prompt=prompt_text,
                )
            return feedback

        def _report_model_result(round_result: ModelRoundResult) -> None:
            dur_sec = getattr(round_result, "duration_ms", 0.0) / 1000.0
            cost_str = (
                getattr(round_result.cost, "total_cny", "0.00")
                if getattr(round_result, "cost", None) is not None
                else "0.00"
            )
            tokens = (
                getattr(round_result.usage, "total_tokens", 0)
                if getattr(round_result, "usage", None) is not None
                else 0
            )
            reasoning_tokens = (
                getattr(round_result.usage, "reasoning_tokens", 0)
                if getattr(round_result, "usage", None) is not None
                else 0
            )
            reasoning_hint = (
                f" (含思考 {reasoning_tokens} tokens)" if reasoning_tokens else ""
            )
            self._report(
                f"  ✨ [Model] 推理完成 (耗时 {dur_sec:.1f}s | 消耗 {tokens} tokens{reasoning_hint} | 费用 {cost_str} CNY)"
            )

        for ref_round in range(start_round, self.num_reflections + 1):
            # One extra iteration dispatches the armed final-round correction;
            # its committed coordinates stay on the final round.
            correction_active = ref_round == self.num_reflections
            if correction_active and final_round_correction is None:
                break
            dispatch_round = (
                self.num_reflections - 1 if correction_active else ref_round
            )
            pending = (
                round_resume.pending
                if round_resume is not None and ref_round == start_round
                else None
            )
            # A corrective dispatch (the extra iteration, a resumed corrective
            # re-ask, or a committed corrective response) records at the
            # corrective attempt's coordinates and never arms a new correction.
            resumed_corrective = (
                ref_round == self.num_reflections - 1
                and ref_round == start_round
                and round_resume is not None
                and round_resume.final_round_correction is not None
            )
            corrective_dispatch = correction_active or resumed_corrective
            corrective_attempt = 1
            pipeline_pos = {
                "generation_index": gen_idx,
                "idea_index": (
                    len(self.accepted_ideas) if generation_finalized else None
                ),
                "reflection_index": dispatch_round,
            }

            prompt_text = ""
            if not correction_active:
                if ref_round == 0:
                    prompt_text = _render_generation_prompt(
                        self.profile,
                        workshop_description=self.workshop_description,
                        prev_ideas_string=prev_ideas_string,
                    )
                else:
                    prompt_text = _render_reflection_prompt(
                        self.profile,
                        current_round=ref_round + 1,
                        last_tool_results=last_tool_results,
                        num_reflections=self.num_reflections,
                    )
                if resumed_corrective:
                    # The resumed final-round call IS the corrective re-ask:
                    # restore its exact request bytes from the chain feedback.
                    assert round_resume is not None
                    assert round_resume.final_round_correction is not None
                    prompt_text = prompt_text + _final_round_correction_suffix(
                        round_resume.final_round_correction
                    )

            retrieval_reuse: tuple[int, int] | None = None
            if correction_active:
                # Final-round correction: re-ask once on the same operation as
                # attempt 2 with the deterministic finalize instruction plus
                # the specific feedback. The corrective call disables the
                # in-call transport retry, so the operation never exceeds its
                # approved two-attempt bound.
                assert final_round_correction is not None
                correction_op_seq, _correction_feedback, correction_prompt = (
                    final_round_correction
                )
                corrected_prompt = correction_prompt + _final_round_correction_suffix(
                    _correction_feedback
                )
                messages = [DeepSeekMessage(role="system", content=system_prompt)]
                for hist in msg_history[:-2]:
                    messages.append(
                        DeepSeekMessage(role=hist["role"], content=hist["content"])
                    )
                messages.append(DeepSeekMessage(role="user", content=corrected_prompt))

                req = DeepSeekRequest(
                    max_tokens=self.admission["model"]["max_tokens"],
                    messages=tuple(messages),
                    output_mode="text",
                    reasoning_effort=self.admission["model"]["reasoning_effort"],
                    user_id=f"run-{self.run_id[:8]}",
                )
                self._report(
                    "  🧠 [Model] 末轮强制收敛： corrective re-ask (FinalizeIdea required)..."
                )
                model_op_seq = correction_op_seq
                round_result = self.adapter.execute_round(
                    req,
                    model_op_seq,
                    pipeline_position=pipeline_pos,
                    writer_epoch=self.writer_epoch,
                    initial_attempt_seq=2,
                    max_attempts=1,
                )
                _report_model_result(round_result)
                response_text = round_result.visible_content
                corrective_attempt = round_result.attempt_seq
                msg_history.append({"role": "user", "content": corrected_prompt})
                msg_history.append({"role": "assistant", "content": response_text})
            elif isinstance(pending, PendingResponse):
                # The response is already committed and the round's messages
                # are already in the rebuilt history; skip the model call.
                model_op_seq = pending.model_op_seq
                response_text = pending.response_text
                corrective_attempt = pending.response_attempt_seq
                if pending.retrieval_op_seq is not None:
                    retrieval_reuse = (
                        pending.retrieval_op_seq,
                        pending.retrieval_attempt_seq,
                    )
            else:
                # Assemble messages for this round
                messages = [DeepSeekMessage(role="system", content=system_prompt)]
                for hist in msg_history:
                    messages.append(
                        DeepSeekMessage(role=hist["role"], content=hist["content"])
                    )
                messages.append(DeepSeekMessage(role="user", content=prompt_text))

                req = DeepSeekRequest(
                    max_tokens=self.admission["model"]["max_tokens"],
                    messages=tuple(messages),
                    output_mode="text",
                    reasoning_effort=self.admission["model"]["reasoning_effort"],
                    user_id=f"run-{self.run_id[:8]}",
                )

                if ref_round == 0:
                    self._report(
                        "  🧠 [Model] 正在调用 DeepSeek 生成初始构想 (深度思考中)..."
                    )
                else:
                    self._report(
                        f"  🧠 [Model] 正在调用 DeepSeek 进行第 {ref_round} 轮反思批判 (深度推理中)..."
                    )

                if isinstance(pending, PendingReexecute):
                    # Re-execute the interrupted call under the same
                    # operation_seq with the next attempt_seq (ticket 10).
                    model_op_seq = pending.op_seq
                    round_result: ModelRoundResult = self.adapter.execute_round(
                        req,
                        model_op_seq,
                        pipeline_position=pipeline_pos,
                        writer_epoch=self.writer_epoch,
                        initial_attempt_seq=pending.next_attempt_seq,
                    )
                else:
                    # Model inference operation
                    model_op_seq = self._next_op_seq()
                    round_result = self.adapter.execute_round(
                        req,
                        model_op_seq,
                        pipeline_position=pipeline_pos,
                        writer_epoch=self.writer_epoch,
                    )

                _report_model_result(round_result)

                response_text = round_result.visible_content
                corrective_attempt = round_result.attempt_seq
                msg_history.append({"role": "user", "content": prompt_text})
                msg_history.append({"role": "assistant", "content": response_text})

            # Finalization gate priority 0 (raw-submission hygiene, Ticket 038):
            # When this round attempts FinalizeIdea, the raw submission bytes
            # are hygiene-scanned BEFORE ACTION/ARGUMENTS parsing so malformed
            # JSON submissions are scanned too ("JSON parse 失败也照扫"). A
            # pattern hit is a terminal condition; it must never be masked by,
            # or converted into, lower-priority model-fixable feedback
            # (Ticket 026).
            arguments_match = HYGIENE_SCAN_ARGUMENTS_PATTERN.search(response_text)
            if arguments_match and ACTION_PATTERN.search(response_text):
                attempted_action = ACTION_PATTERN.search(response_text).group(1).strip()
                if attempted_action.lower() == "finalizeidea":
                    hygiene_hits = scan_payload_hygiene(arguments_match.group(1))
                    if hygiene_hits:
                        return self._record_hygiene_hit(
                            hits=hygiene_hits,
                            operation_seq=model_op_seq,
                            pipeline_pos=pipeline_pos,
                        )

            # Parse ACTION and ARGUMENTS
            try:
                action, arguments = parse_action_and_arguments(response_text)
            except IdeationInputError as exc:
                if exc.code in MODEL_FIXABLE_ERROR_CODES:
                    last_tool_results = _record_fixable_error(
                        action="unknown",
                        error_code=exc.code,
                        error_message=exc.message or str(exc),
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue
                raise

            if action not in MODEL_VISIBLE_ACTIONS:
                last_tool_results = _record_fixable_error(
                    action=action,
                    error_code="UNKNOWN_ACTION",
                    error_message=f"Action '{action}' is not model-visible. Allowed actions are 'SearchLiterature' and 'FinalizeIdea'.",
                    operation_seq=model_op_seq,
                    pipeline_pos=pipeline_pos,
                )
                continue

            if action == "SearchLiterature":
                if corrective_dispatch or ref_round == self.num_reflections - 1:
                    # Final-round convergence: literature search is no longer
                    # available on (or after) the last round. The corrective
                    # re-ask (one extra attempt on this operation) must
                    # finalize instead; a corrective response that still
                    # searches records the same violation without executing a
                    # retrieval no round will ever consume.
                    last_tool_results = _record_fixable_error(
                        action="SearchLiterature",
                        error_code=FINAL_ROUND_FINALIZE_REQUIRED_CODE,
                        error_message=(
                            "The final reflection round must end with ACTION: "
                            "FinalizeIdea. Literature search is no longer "
                            "available; finalize your idea now using the "
                            "literature already retrieved in this generation."
                        ),
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue
                if retrieval_reuse is not None:
                    # Resume replay: the retrieval request was committed but
                    # produced no retrieval event; re-execute under the same
                    # operation_seq with the next attempt_seq (ticket 10).
                    retrieval_op_seq, retrieval_attempt_seq = retrieval_reuse
                else:
                    retrieval_op_seq = self._next_op_seq()
                    retrieval_attempt_seq = 1
                try:
                    retrieval_payload = self.retriever.search(
                        arguments,
                        operation_seq=retrieval_op_seq,
                        attempt_seq=retrieval_attempt_seq,
                    )
                except IdeationInputError as exc:
                    if exc.code in MODEL_FIXABLE_ERROR_CODES:
                        last_tool_results = _record_fixable_error(
                            action="SearchLiterature",
                            error_code=exc.code,
                            error_message=exc.message or str(exc),
                            operation_seq=retrieval_op_seq,
                            pipeline_pos=pipeline_pos,
                        )
                        continue
                    raise

                generation_retrieval_op_seqs.append(retrieval_op_seq)
                papers = retrieval_payload.get("papers", [])
                if papers:
                    self.run_has_non_empty_retrieval = True
                    for p in papers:
                        generation_retrieved_paper_ids.add(p["paper_id"])

                last_tool_results = format_retrieval_for_reflection(retrieval_payload)
                self._report(
                    f"  🔍 [Tool] 执行文献检索 SearchLiterature -> 命中 {len(papers)} 篇相关文献"
                )

                self.store.append_event(
                    self.run_id,
                    {
                        "event_type": "action_outcome",
                        "payload": {
                            "action": "SearchLiterature",
                            "outcome": "tool_result",
                            "paper_count": len(papers),
                            "paper_ids": sorted(p["paper_id"] for p in papers),
                            "schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
                        },
                        "pipeline_position": pipeline_pos,
                        "writer_epoch": self.writer_epoch,
                    },
                )

            elif action == "FinalizeIdea":
                # Check closed two-key arguments structure (Ticket 038)
                if not isinstance(arguments, dict):
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_ARGUMENTS_JSON",
                        error_message="FinalizeIdea arguments must be a JSON object",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                extra_args = set(arguments.keys()) - {"idea", "grounding"}
                if extra_args:
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_IDEA_STRUCTURE",
                        error_message=f"FinalizeIdea arguments contain unknown fields: {sorted(extra_args)}. Allowed fields are exactly 'idea' and 'grounding'",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                if "idea" not in arguments:
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_IDEA_STRUCTURE",
                        error_message="FinalizeIdea arguments missing required 'idea' field",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                if "grounding" not in arguments:
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_GROUNDING",
                        error_message="FinalizeIdea arguments missing required 'grounding' field",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                # Validate idea 7-field structure
                try:
                    validated_idea = validate_idea_structure(arguments.get("idea"))
                except IdeationInputError as exc:
                    if exc.code in MODEL_FIXABLE_ERROR_CODES:
                        last_tool_results = _record_fixable_error(
                            action="FinalizeIdea",
                            error_code=exc.code,
                            error_message=exc.message or str(exc),
                            operation_seq=model_op_seq,
                            pipeline_pos=pipeline_pos,
                        )
                        continue
                    raise

                # Grounding Gate check: Must have obtained >= 1 non-empty retrieval result in this generation
                if not generation_retrieved_paper_ids:
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="GATE_REJECTED",
                        error_message="Cannot finalize idea without at least one non-empty literature search in this generation. Use SearchLiterature first.",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                # Validate Declared Grounding against eligible retrieved papers in this generation
                try:
                    validated_grounding = validate_declared_grounding(
                        arguments.get("grounding"), generation_retrieved_paper_ids
                    )
                except IdeationInputError as exc:
                    if exc.code in MODEL_FIXABLE_ERROR_CODES:
                        last_tool_results = _record_fixable_error(
                            action="FinalizeIdea",
                            error_code=exc.code,
                            error_message=exc.message or str(exc),
                            operation_seq=model_op_seq,
                            pipeline_pos=pipeline_pos,
                        )
                        continue
                    raise

                # Duplicate checks within this run
                if any(
                    prev["Name"] == validated_idea["Name"]
                    for prev in self.accepted_ideas
                ):
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="DUPLICATE_IDEA_NAME",
                        error_message=f"An idea named '{validated_idea['Name']}' was already accepted in this run. Propose an interestingly new proposal.",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                if any(
                    prev["Title"].strip().lower()
                    == validated_idea["Title"].strip().lower()
                    for prev in self.accepted_ideas
                ):
                    last_tool_results = _record_fixable_error(
                        action="FinalizeIdea",
                        error_code="DUPLICATE_IDEA",
                        error_message=f"Idea title '{validated_idea['Title']}' is a near-duplicate of an already accepted proposal in this run. Propose an interestingly new proposal.",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                # Commit accepted idea atomically
                idea_idx = len(self.accepted_ideas)
                idea_pos = {
                    "generation_index": gen_idx,
                    "idea_index": idea_idx,
                    "reflection_index": dispatch_round,
                }

                finalize_op_seq = self._next_op_seq()

                idea_bytes = canonical_json_bytes(validated_idea)
                idea_rel, idea_len, idea_sha = self.store.write_idea_artifact(
                    self.run_id,
                    idea_idx,
                    "idea.json",
                    idea_bytes,
                    label="finalized idea payload",
                )

                grounding_bytes = canonical_json_bytes(validated_grounding)
                (
                    grounding_rel,
                    grounding_len,
                    grounding_sha,
                ) = self.store.write_idea_artifact(
                    self.run_id,
                    idea_idx,
                    "grounding.json",
                    grounding_bytes,
                    label="declared grounding",
                )

                sidecar_doc = {
                    "declared_grounding": validated_grounding,
                    "finalized_at": _now(),
                    "generation_index": gen_idx,
                    "grounding_sha256": grounding_sha,
                    "idea_index": idea_idx,
                    "idea_sha256": idea_sha,
                    "reflection_index": dispatch_round,
                    "retrieval_operation_seqs": list(generation_retrieval_op_seqs),
                    "run_id": self.run_id,
                    "schema_version": IDEA_SIDECAR_SCHEMA_VERSION,
                }
                sidecar_bytes = canonical_json_bytes(sidecar_doc)
                (
                    sidecar_rel,
                    sidecar_len,
                    sidecar_sha,
                ) = self.store.write_idea_artifact(
                    self.run_id,
                    idea_idx,
                    "sidecar.json",
                    sidecar_bytes,
                    label="idea sidecar",
                )

                # operation.finished for idea_finalization
                self.store.append_event(
                    self.run_id,
                    {
                        "artifact_refs": [
                            {
                                "byte_length": idea_len,
                                "media_type": "application/json",
                                "relative_path": idea_rel,
                                "role": "finalized_idea",
                                "sha256": idea_sha,
                            },
                            {
                                "byte_length": grounding_len,
                                "media_type": "application/json",
                                "relative_path": grounding_rel,
                                "role": "declared_grounding",
                                "sha256": grounding_sha,
                            },
                            {
                                "byte_length": sidecar_len,
                                "media_type": "application/json",
                                "relative_path": sidecar_rel,
                                "role": "idea_sidecar",
                                "sha256": sidecar_sha,
                            },
                        ],
                        "event_type": "operation.finished",
                        "operation": {
                            "attempt_seq": 1,
                            "operation_kind": "idea_finalization",
                            "operation_seq": finalize_op_seq,
                        },
                        "payload": {
                            "idea_index": idea_idx,
                            "status": "success",
                        },
                        "pipeline_position": idea_pos,
                        "writer_epoch": self.writer_epoch,
                    },
                )

                # action_outcome event
                self.store.append_event(
                    self.run_id,
                    {
                        "event_type": "action_outcome",
                        "payload": {
                            "action": "FinalizeIdea",
                            "idea_index": idea_idx,
                            "outcome": "finalize_accepted",
                            "schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
                        },
                        "pipeline_position": idea_pos,
                        "writer_epoch": self.writer_epoch,
                    },
                )

                # generation.finished event
                self.store.append_event(
                    self.run_id,
                    {
                        "event_type": "generation.finished",
                        "payload": {
                            "disposition": "finalized",
                            "generation_index": gen_idx,
                            "idea_index": idea_idx,
                        },
                        "pipeline_position": idea_pos,
                        "writer_epoch": self.writer_epoch,
                    },
                )

                self.accepted_ideas.append(validated_idea)
                self.idea_str_archive.append(json.dumps(validated_idea))
                self.disposition_counts["finalized"] += 1
                generation_finalized = True
                self._report(
                    f"  💡 [Idea] 创意定稿接受成功: \"{validated_idea.get('Title', '')}\" "
                    f"(声明引用 {len(validated_grounding)} 篇文献)"
                )
                break

        if not generation_finalized:
            # Budget exhausted for this generation
            self.disposition_counts["budget_exhausted"] += 1
            self.store.append_event(
                self.run_id,
                {
                    "event_type": "generation.finished",
                    "payload": {
                        "disposition": "budget_exhausted",
                        "generation_index": gen_idx,
                        "idea_index": None,
                    },
                    "pipeline_position": {
                        "generation_index": gen_idx,
                        "idea_index": None,
                        "reflection_index": self.num_reflections - 1,
                    },
                    "writer_epoch": self.writer_epoch,
                },
            )


# ---------------------------------------------------------------------------
# Resume rebuild (ticket 10)
# ---------------------------------------------------------------------------


def rebuild_resume_plan(
    store: RunStore,
    run_id: str,
    admission: dict[str, Any],
    *,
    writer_epoch: int,
    workshop_description: str,
    orphan_operation_artifacts: list[tuple[int, int, str]],
) -> ResumePlan:
    """Rebuild the control state of an interrupted run from its evidence chain.

    The resume gates have already verified the chain, re-checked the
    admission pins, and quarantined orphan artifacts; this function derives
    the generation/round/history state, the in-flight operation disposition,
    and the bookkeeping completions that finish commit sequences the
    interruption cut. Anything outside the approved interruption windows
    fails closed with RUN_CORRUPT; nothing is "repaired".
    """
    events = store.read_events(run_id)
    budgets = admission["budgets"]
    max_generations = budgets["max_num_generations"]
    num_reflections = budgets["num_reflections"]
    # The resume path rebuilds prompt bytes from the admitted profile only:
    # registry drift, unknown versions, or hash mismatch fail closed before
    # any model round; a legacy admission stays ml-baseline-v1.
    profile: PromptProfile = _resolve_admission_profile(admission)

    # -- Group events --------------------------------------------------------
    known_event_types = {
        "preflight_started",
        "preflight_step",
        "admitted",
        "generation.started",
        "generation.finished",
        "provider_attempt.finished",
        "operation.finished",
        "operation.failed",
        "action_outcome",
        "terminal",
        "interrupted",
        "resumed",
        "orphans_quarantined",
    }
    ops_with_events: set[int] = set()
    model_ops: dict[int, list[dict[str, Any]]] = {}
    retrieval_events: list[dict[str, Any]] = []
    finalize_ops: dict[int, dict[str, Any]] = {}
    outcomes_by_round: dict[tuple[int, int], list[dict[str, Any]]] = {}
    gen_started: list[dict[str, Any]] = []
    gen_finished: list[dict[str, Any]] = []
    terminal_events: list[dict[str, Any]] = []
    max_event_op_seq = 0

    for event in events:
        event_type = event.get("event_type")
        if event_type not in known_event_types:
            fail("RUN_CORRUPT", f"Unknown event type in chain: {event_type}")
        operation = event.get("operation")
        if operation is not None:
            op_seq = operation.get("operation_seq")
            op_kind = operation.get("operation_kind")
            if not isinstance(op_seq, int) or op_seq < 1:
                fail("RUN_CORRUPT", "Operation event carries an invalid operation_seq")
            ops_with_events.add(op_seq)
            max_event_op_seq = max(max_event_op_seq, op_seq)
            if event_type == "provider_attempt.finished":
                if op_kind != "model_inference":
                    fail(
                        "RUN_CORRUPT",
                        "provider_attempt event for a non-model operation",
                    )
                model_ops.setdefault(op_seq, []).append(event)
            elif event_type == "operation.finished":
                if op_kind == "model_inference":
                    model_ops.setdefault(op_seq, []).append(event)
                elif op_kind == "literature_retrieval":
                    retrieval_events.append(event)
                elif op_kind == "idea_finalization":
                    if op_seq in finalize_ops:
                        fail("RUN_CORRUPT", "Duplicate idea_finalization operation")
                    finalize_ops[op_seq] = event
                else:
                    fail("RUN_CORRUPT", f"Unknown operation_kind: {op_kind}")
            elif event_type == "operation.failed":
                if op_kind == "model_inference":
                    model_ops.setdefault(op_seq, []).append(event)
                elif op_kind == "literature_retrieval":
                    retrieval_events.append(event)
                else:
                    fail("RUN_CORRUPT", f"Unknown operation_kind: {op_kind}")
            continue
        if event_type == "action_outcome":
            pos = event.get("pipeline_position")
            if not isinstance(pos, dict):
                fail("RUN_CORRUPT", "action_outcome lacks pipeline_position")
            key = (pos.get("generation_index"), pos.get("reflection_index"))
            if not all(isinstance(index, int) and index >= 0 for index in key):
                fail(
                    "RUN_CORRUPT", "action_outcome carries an invalid pipeline_position"
                )
            outcomes_by_round.setdefault(key, []).append(event)
        elif event_type == "generation.started":
            gen_started.append(event)
        elif event_type == "generation.finished":
            gen_finished.append(event)
        elif event_type == "terminal":
            terminal_events.append(event)

    # Per-operation ordering invariants. The one legal post-final attempt is
    # the final-round corrective re-ask (Proposal 002 remediation): after a
    # committed operation.finished, exactly one continuation attempt may run
    # on the same operation. The continuation is cross-checked against the
    # round's final_round_correction outcome below.
    op_final: dict[int, dict[str, Any]] = {}
    corrected_model_ops: set[int] = set()
    for op_seq, op_events in model_ops.items():
        last_attempt_seq = 0
        final: dict[str, Any] | None = None
        corrected = False
        for event in op_events:
            if event["event_type"] == "provider_attempt.finished":
                if final is not None:
                    if corrected:
                        fail(
                            "RUN_CORRUPT",
                            "Attempt event after the operation final state",
                        )
                    corrected = True
                attempt_seq = event["operation"].get("attempt_seq")
                if not isinstance(attempt_seq, int) or attempt_seq <= last_attempt_seq:
                    fail("RUN_CORRUPT", "Attempt sequence is not strictly increasing")
                last_attempt_seq = attempt_seq
                continue
            if final is not None and not corrected:
                fail("RUN_CORRUPT", "Operation carries more than one final state")
            if event["event_type"] == "operation.failed":
                if event["payload"].get("disposition") not in ("suspend", "terminal"):
                    fail(
                        "RUN_CORRUPT", "operation.failed carries an invalid disposition"
                    )
                # A suspend disposition does not close the operation: a later
                # writer epoch may re-execute it. Only terminal closes by failure.
                if event["payload"]["disposition"] == "terminal":
                    final = event
                elif final is not None:
                    # A suspend on the corrective continuation reopens the
                    # operation for a resume re-execute of the re-ask.
                    final = None
            else:
                if final is not None:
                    corrected = True
                final = event
        if corrected:
            corrected_model_ops.add(op_seq)
        # A suspend-only tail leaves the operation open; the last suspend
        # failure still anchors the next attempt coordinate.
        if final is None:
            suspends = [
                e
                for e in op_events
                if e["event_type"] == "operation.failed"
                and e["payload"].get("disposition") == "suspend"
            ]
            if suspends:
                final = suspends[-1]
        if final is not None:
            op_final[op_seq] = final

    for op_seq in corrected_model_ops:
        pos = model_ops[op_seq][0].get("pipeline_position") or {}
        correction_outcomes = outcomes_by_round.get(
            (pos.get("generation_index"), pos.get("reflection_index")), []
        )
        if (
            not correction_outcomes
            or correction_outcomes[0]["payload"].get("outcome")
            != FINAL_ROUND_CORRECTION_OUTCOME
        ):
            fail(
                "RUN_CORRUPT",
                "A post-final corrective attempt lacks its final-round "
                "correction outcome",
            )

    # -- Accepted ideas (needed even for seal-only completions) -------------
    accepted_ideas: list[dict[str, Any]] = []
    idea_str_archive: list[str] = []
    finalize_by_seq = sorted(
        finalize_ops.items(), key=lambda item: item[1]["event_seq"]
    )
    for expected_index, (finalize_op_seq, event) in enumerate(finalize_by_seq):
        idea_index = event.get("payload", {}).get("idea_index")
        if idea_index != expected_index:
            fail("RUN_CORRUPT", "Finalized ideas are not contiguous from index 0")
        idea_ref = next(
            (
                ref
                for ref in event.get("artifact_refs", [])
                if ref.get("role") == "finalized_idea"
            ),
            None,
        )
        if idea_ref is None:
            fail("RUN_CORRUPT", "Finalization event lacks its finalized_idea reference")
        idea_doc = parse_json_bytes(
            store.read_artifact(run_id, idea_ref["relative_path"], idea_ref["sha256"]),
            label="finalized idea",
        )
        if not isinstance(idea_doc, dict) or set(idea_doc) != set(REQUIRED_IDEA_FIELDS):
            fail("RUN_CORRUPT", "Finalized idea artifact lost its seven-field shape")
        # Key order follows REQUIRED_IDEA_FIELDS: the live archive string is
        # json.dumps(validated_idea) with exactly this order.
        validated = {
            field_name: idea_doc[field_name] for field_name in REQUIRED_IDEA_FIELDS
        }
        accepted_ideas.append(validated)
        idea_str_archive.append(json.dumps(validated))

    # -- Generation structure ------------------------------------------------
    for expected, event in enumerate(gen_started):
        if event.get("payload", {}).get("generation_index") != expected:
            fail("RUN_CORRUPT", "generation.started events are not contiguous from 0")
    disposition_counts = {"finalized": 0, "budget_exhausted": 0}
    finished_seq_by_gen: dict[int, int] = {}
    for expected, event in enumerate(gen_finished):
        payload = event.get("payload", {})
        if payload.get("generation_index") != expected:
            fail("RUN_CORRUPT", "generation.finished events are not contiguous from 0")
        disposition = payload.get("disposition")
        if disposition not in disposition_counts:
            fail("RUN_CORRUPT", f"Unknown generation disposition: {disposition}")
        disposition_counts[disposition] += 1
        finished_seq_by_gen[expected] = event["event_seq"]
    if len(gen_started) not in (len(gen_finished), len(gen_finished) + 1):
        fail("RUN_CORRUPT", "Generation started/finished counts are inconsistent")
    if len(gen_started) > max_generations:
        fail("RUN_CORRUPT", "More generations started than the admission budget")
    for event in events:
        pos = event.get("pipeline_position")
        if not isinstance(pos, dict) or event["event_type"] == "generation.finished":
            continue
        gen_idx = pos.get("generation_index")
        if (
            gen_idx in finished_seq_by_gen
            and event["event_seq"] > finished_seq_by_gen[gen_idx]
        ):
            fail("RUN_CORRUPT", "Events follow a generation.finished event")

    run_has_non_empty = any(
        outcome["payload"].get("outcome") == "tool_result"
        and outcome["payload"].get("paper_count", 0) > 0
        for round_outcomes in outcomes_by_round.values()
        for outcome in round_outcomes
    )

    # Orphan coordinates grouped by operation.
    orphan_by_op: dict[int, list[tuple[int, str]]] = {}
    for op_seq, attempt_seq, filename in orphan_operation_artifacts:
        orphan_by_op.setdefault(op_seq, []).append((attempt_seq, filename))
    op_seq_floor = max([max_event_op_seq, *orphan_by_op.keys()], default=0)

    def _plan(
        *,
        start_generation: int,
        round_resume: RoundResume | None,
        terminal: SealFailedCompletion | SealTerminalCompletion | None,
        bookkeeping: list[dict[str, Any]],
        remaining: int,
    ) -> ResumePlan:
        return ResumePlan(
            writer_epoch=writer_epoch,
            op_seq=op_seq_floor,
            accepted_ideas=tuple(accepted_ideas),
            idea_str_archive=tuple(idea_str_archive),
            disposition_counts=dict(disposition_counts),
            run_has_non_empty_retrieval=run_has_non_empty,
            remaining_model_rounds=remaining,
            bookkeeping=tuple(bookkeeping),
            start_generation=start_generation,
            round_resume=round_resume,
            terminal=terminal,
        )

    # -- Terminal / hygiene completions --------------------------------------
    # Lifecycle records (the crashing writer's `interrupted`, and this
    # resume's own `orphans_quarantined`/`resumed`) legitimately follow a
    # committed terminal/hygiene tail; "last" is judged on execution events.
    lifecycle_types = {"interrupted", "resumed", "orphans_quarantined"}
    execution_events = [
        event for event in events if event["event_type"] not in lifecycle_types
    ]
    if terminal_events:
        terminal_event = terminal_events[0]
        if len(terminal_events) > 1 or terminal_event is not execution_events[-1]:
            fail("RUN_CORRUPT", "Events follow the terminal event")
        summary = {
            key: value
            for key, value in terminal_event.get("payload", {}).items()
            if key != "artifact_refs"
        }
        return _plan(
            start_generation=len(gen_started),
            round_resume=None,
            terminal=SealTerminalCompletion(
                outcome=summary["outcome"],
                summary=summary,
                event_seq=terminal_event["event_seq"],
                event_hash=terminal_event["event_hash"],
            ),
            bookkeeping=[],
            remaining=0,
        )

    hygiene_hits = [
        outcome
        for round_outcomes in outcomes_by_round.values()
        for outcome in round_outcomes
        if outcome["payload"].get("outcome") == "hygiene_hit"
    ]
    if hygiene_hits:
        if len(hygiene_hits) > 1 or hygiene_hits[0] is not execution_events[-1]:
            fail("RUN_CORRUPT", "Events follow a hygiene-hit action outcome")
        return _plan(
            start_generation=len(gen_started),
            round_resume=None,
            terminal=SealFailedCompletion(
                reason_code="PAYLOAD_HYGIENE_VIOLATION",
                reason_message=HYGIENE_FAILURE_MESSAGE,
            ),
            bookkeeping=[],
            remaining=0,
        )

    # -- Whole-generation boundary -------------------------------------------
    if len(gen_started) == len(gen_finished):
        # Crash between generations (or right after admission): the next
        # generation starts fresh; a fully consumed budget falls through to
        # the backstop + terminal seal tail.
        return _plan(
            start_generation=len(gen_started),
            round_resume=None,
            terminal=None,
            bookkeeping=[],
            remaining=(max_generations - len(gen_started)) * num_reflections,
        )

    # -- Current generation round replay -------------------------------------
    gen_idx = len(gen_finished)
    state = _GenerationState()
    archive_string = "\n\n".join(idea_str_archive)
    bookkeeping: list[dict[str, Any]] = []

    outcomes_g: dict[int, list[dict[str, Any]]] = {}
    for (outcome_gen, outcome_round), round_outcomes in outcomes_by_round.items():
        if outcome_gen != gen_idx:
            continue
        if len(round_outcomes) > 2 or (
            len(round_outcomes) == 2
            and round_outcomes[0]["payload"].get("outcome")
            != FINAL_ROUND_CORRECTION_OUTCOME
        ):
            fail("RUN_CORRUPT", "Multiple action_outcome events in one round")
        outcomes_g[outcome_round] = list(round_outcomes)

    model_op_round: dict[int, int] = {}
    for op_seq in model_ops:
        pos = model_ops[op_seq][0].get("pipeline_position") or {}
        if pos.get("generation_index") != gen_idx:
            continue
        round_idx = pos.get("reflection_index")
        if not isinstance(round_idx, int) or round_idx < 0:
            fail("RUN_CORRUPT", "Model operation carries an invalid pipeline_position")
        if round_idx in model_op_round:
            fail("RUN_CORRUPT", "Two model operations in one round")
        model_op_round[round_idx] = op_seq

    finalize_round: dict[int, dict[str, Any]] = {}
    for op_seq, event in finalize_ops.items():
        pos = event.get("pipeline_position") or {}
        if pos.get("generation_index") != gen_idx:
            continue
        round_idx = pos.get("reflection_index")
        if not isinstance(round_idx, int) or round_idx < 0:
            fail(
                "RUN_CORRUPT",
                "Finalization operation carries an invalid pipeline_position",
            )
        finalize_round[round_idx] = event

    # Retrieval events carry no pipeline_position: attribute each to the open
    # round (model op.finished committed, no action_outcome yet) whose event
    # interval contains it.
    retrieval_by_round: dict[int, dict[str, Any]] = {}
    for event in retrieval_events:
        event_seq = event["event_seq"]
        assigned_round: int | None = None
        for round_idx, op_seq in model_op_round.items():
            final = op_final.get(op_seq)
            if final is None or final["event_type"] != "operation.finished":
                continue
            if event_seq <= final["event_seq"]:
                continue
            outcome_events = outcomes_g.get(round_idx)
            if outcome_events and event_seq >= outcome_events[-1]["event_seq"]:
                continue
            if assigned_round is not None:
                fail("RUN_CORRUPT", "Retrieval event matches multiple rounds")
            assigned_round = round_idx
        if assigned_round is None:
            fail("RUN_CORRUPT", "Retrieval event has no open round to attach to")
        if assigned_round in retrieval_by_round:
            fail("RUN_CORRUPT", "Two retrieval operations in one round")
        retrieval_by_round[assigned_round] = event

    def _round_prompt(ref_round: int) -> str:
        if ref_round == 0:
            return _render_generation_prompt(
                profile,
                workshop_description=workshop_description,
                prev_ideas_string=archive_string,
            )
        return _render_reflection_prompt(
            profile,
            current_round=ref_round + 1,
            last_tool_results=state.last_tool_results,
            num_reflections=num_reflections,
        )

    def _committed_response(finished_event: dict[str, Any]) -> str:
        resp_ref = next(
            (
                ref
                for ref in finished_event.get("artifact_refs", [])
                if ref.get("role") == "provider_response"
            ),
            None,
        )
        if resp_ref is None:
            fail(
                "RUN_CORRUPT",
                "operation.finished lacks its provider_response reference",
            )
        return parse_stored_response_content(
            store.read_artifact(run_id, resp_ref["relative_path"], resp_ref["sha256"])
        )

    def _retrieval_payload(finished_event: dict[str, Any]) -> dict[str, Any]:
        payload_ref = next(
            (
                ref
                for ref in finished_event.get("artifact_refs", [])
                if ref.get("role") == "model_payload"
            ),
            None,
        )
        if payload_ref is None:
            fail("RUN_CORRUPT", "Retrieval operation lacks its model_payload reference")
        payload = parse_json_bytes(
            store.read_artifact(
                run_id, payload_ref["relative_path"], payload_ref["sha256"]
            ),
            label="retrieval payload",
        )
        if not isinstance(payload, dict):
            fail("RUN_CORRUPT", "Retrieval payload is not a JSON object")
        return payload

    def _failure_message_from_chain(failed_event: dict[str, Any]) -> str:
        """Read the provider failure message for a terminal operation failure."""
        op_seq = failed_event["operation"]["operation_seq"]
        failure_ref: dict[str, Any] | None = None
        for event in reversed(model_ops.get(op_seq, [])):
            if event["event_type"] != "provider_attempt.finished":
                continue
            failure_ref = next(
                (
                    ref
                    for ref in event.get("artifact_refs", [])
                    if ref.get("role") == "provider_failure"
                ),
                None,
            )
            if failure_ref is not None:
                break
        if failure_ref is None:
            fail(
                "RUN_CORRUPT",
                "Terminal operation failure lacks provider_failure evidence",
            )
        failure_doc = parse_json_bytes(
            store.read_artifact(
                run_id, failure_ref["relative_path"], failure_ref["sha256"]
            ),
            label="provider failure",
        )
        message = failure_doc.get("message")
        if not isinstance(message, str) or not message:
            fail("RUN_CORRUPT", "Provider failure artifact lacks its message")
        return message

    def _recovered_finished_event(op_seq: int) -> dict[str, Any]:
        """Rebuild the operation.finished commit whose recording was cut.

        The cut hit between the last successful provider_attempt.finished and
        its operation.finished; the recovered event replays the attempt's own
        evidence under the current writer epoch.
        """
        attempts = [
            event
            for event in model_ops[op_seq]
            if event["event_type"] == "provider_attempt.finished"
        ]
        last_attempt = attempts[-1]
        resp_ref = next(
            (
                ref
                for ref in last_attempt.get("artifact_refs", [])
                if ref.get("role") == "provider_response"
            ),
            None,
        )
        if resp_ref is None:
            fail(
                "RUN_CORRUPT",
                "Successful attempt lacks its provider_response reference",
            )
        last_suspend_seq = max(
            (
                event["event_seq"]
                for event in model_ops[op_seq]
                if event["event_type"] == "operation.failed"
            ),
            default=0,
        )
        segment_attempts = [
            event for event in attempts if event["event_seq"] > last_suspend_seq
        ]
        return {
            "artifact_refs": [resp_ref],
            "event_type": "operation.finished",
            "operation": {
                "attempt_seq": last_attempt["operation"]["attempt_seq"],
                "operation_kind": "model_inference",
                "operation_seq": op_seq,
            },
            "payload": {
                "cost_cny": last_attempt["payload"].get("cost_cny"),
                "model": last_attempt["payload"].get("model"),
                "response_id": last_attempt["payload"].get("response_id"),
                "status": "success",
                "total_attempts": len(segment_attempts),
            },
            "pipeline_position": last_attempt.get("pipeline_position"),
            "writer_epoch": writer_epoch,
        }

    def _close_generation(
        idea_pos: dict[str, Any] | None,
        idea_index: int | None,
    ) -> ResumePlan:
        """Bookkeep the generation.finished commit cut by the interruption."""
        if idea_pos is None:
            disposition_counts["budget_exhausted"] += 1
            bookkeeping.append(
                {
                    "kind": "append_event",
                    "event": {
                        "event_type": "generation.finished",
                        "payload": {
                            "disposition": "budget_exhausted",
                            "generation_index": gen_idx,
                            "idea_index": None,
                        },
                        "pipeline_position": {
                            "generation_index": gen_idx,
                            "idea_index": None,
                            "reflection_index": num_reflections - 1,
                        },
                        "writer_epoch": writer_epoch,
                    },
                }
            )
        else:
            disposition_counts["finalized"] += 1
            bookkeeping.append(
                {
                    "kind": "append_event",
                    "event": {
                        "event_type": "generation.finished",
                        "payload": {
                            "disposition": "finalized",
                            "generation_index": gen_idx,
                            "idea_index": idea_index,
                        },
                        "pipeline_position": idea_pos,
                        "writer_epoch": writer_epoch,
                    },
                }
            )
        return _plan(
            start_generation=gen_idx + 1,
            round_resume=None,
            terminal=None,
            bookkeeping=bookkeeping,
            remaining=(max_generations - gen_idx - 1) * num_reflections,
        )

    def _no_later_round_events(ref_round: int) -> None:
        later = (
            [r for r in outcomes_g if r > ref_round]
            + [r for r in model_op_round if r > ref_round]
            + [r for r in retrieval_by_round if r > ref_round]
            + [r for r in finalize_round if r > ref_round]
        )
        if later:
            fail("RUN_CORRUPT", "Events exist past the interrupted round")

    start_round: int | None = None
    pending: PendingResponse | PendingReexecute | None = None

    for ref_round in range(num_reflections):
        round_outcomes = outcomes_g.get(ref_round)
        op_seq = model_op_round.get(ref_round)
        retrieval_event = retrieval_by_round.get(ref_round)
        finalize_event = finalize_round.get(ref_round)

        if round_outcomes:
            first_outcome = round_outcomes[0]["payload"].get("outcome")
            if first_outcome == FINAL_ROUND_CORRECTION_OUTCOME:
                if ref_round != num_reflections - 1:
                    fail(
                        "RUN_CORRUPT", "Final-round correction outside the final round"
                    )
                if op_seq is None:
                    fail("RUN_CORRUPT", "Action outcome without its model operation")
                _no_later_round_events(ref_round)
                if len(round_outcomes) == 1:
                    # The final-round correction is committed but its
                    # corrective attempt is not resolved: the round is the
                    # interrupted round and the re-ask resumes from here.
                    final = op_final.get(op_seq)
                    if not isinstance(
                        round_outcomes[0]["payload"].get("feedback"), str
                    ):
                        fail("RUN_CORRUPT", "The correction outcome lacks its feedback")
                    correction_feedback = round_outcomes[0]["payload"]["feedback"]
                    attempts = [
                        event
                        for event in model_ops[op_seq]
                        if event["event_type"] == "provider_attempt.finished"
                    ]
                    attempt_seqs = [
                        event["operation"]["attempt_seq"] for event in attempts
                    ]
                    orphan_attempts = [a for a, _ in orphan_by_op.get(op_seq, [])]
                    corrective_finished = (
                        final is not None
                        and final["event_type"] == "operation.finished"
                        and final["operation"]["attempt_seq"] >= 2
                    )
                    if final is not None and final["event_type"] == "operation.failed":
                        if final["payload"]["disposition"] == "terminal":
                            return _plan(
                                start_generation=gen_idx,
                                round_resume=None,
                                terminal=SealFailedCompletion(
                                    reason_code=final["payload"]["error_code"],
                                    reason_message=_failure_message_from_chain(final),
                                ),
                                bookkeeping=bookkeeping,
                                remaining=0,
                            )
                        # The corrective attempt suspended: re-execute the
                        # re-ask under the same operation at the next attempt.
                        pending = PendingReexecute(
                            op_seq=op_seq,
                            next_attempt_seq=max(attempt_seqs + orphan_attempts) + 1,
                        )
                    elif corrective_finished:
                        # The corrective response is committed; its dispatch
                        # was cut. Re-dispatch it without a new model call.
                        first_finished = next(
                            (
                                event
                                for event in model_ops[op_seq]
                                if event["event_type"] == "operation.finished"
                                and event["operation"]["attempt_seq"] == 1
                            ),
                            None,
                        )
                        if first_finished is None:
                            fail(
                                "RUN_CORRUPT",
                                "Correction round lacks its original response",
                            )
                        state.msg_history[-1] = {
                            "role": "assistant",
                            "content": _committed_response(first_finished),
                        }
                        pending = PendingResponse(
                            response_text=_committed_response(final),
                            model_op_seq=op_seq,
                            retrieval_op_seq=None,
                            retrieval_attempt_seq=1,
                            corrective_dispatch=True,
                            response_attempt_seq=final["operation"]["attempt_seq"],
                        )
                    elif final is None and attempt_seqs and attempt_seqs[-1] >= 2:
                        # The cut hit inside the corrective attempt's recording
                        # sequence; recover or re-execute exactly like an open
                        # operation.
                        last_attempt = attempts[-1]
                        if last_attempt["payload"].get("outcome") == "success":
                            recovered = _recovered_finished_event(op_seq)
                            bookkeeping.append(
                                {"kind": "append_event", "event": recovered}
                            )
                            pending = PendingResponse(
                                response_text=_committed_response(recovered),
                                model_op_seq=op_seq,
                                retrieval_op_seq=None,
                                retrieval_attempt_seq=1,
                                corrective_dispatch=True,
                                response_attempt_seq=last_attempt["operation"][
                                    "attempt_seq"
                                ],
                            )
                        elif last_attempt["payload"].get("disposition") == "terminal":
                            error_code = last_attempt["payload"]["error_code"]
                            bookkeeping.append(
                                {
                                    "kind": "append_event",
                                    "event": {
                                        "event_type": "operation.failed",
                                        "operation": {
                                            "attempt_seq": last_attempt["operation"][
                                                "attempt_seq"
                                            ],
                                            "operation_kind": "model_inference",
                                            "operation_seq": op_seq,
                                        },
                                        "payload": {
                                            "disposition": "terminal",
                                            "error_code": error_code,
                                            "status": "failed",
                                            "total_attempts": last_attempt["operation"][
                                                "attempt_seq"
                                            ],
                                        },
                                        "pipeline_position": last_attempt.get(
                                            "pipeline_position"
                                        ),
                                        "writer_epoch": writer_epoch,
                                    },
                                }
                            )
                            return _plan(
                                start_generation=gen_idx,
                                round_resume=None,
                                terminal=SealFailedCompletion(
                                    reason_code=error_code,
                                    reason_message=_failure_message_from_chain(
                                        last_attempt
                                    ),
                                ),
                                bookkeeping=bookkeeping,
                                remaining=0,
                            )
                        else:
                            pending = PendingReexecute(
                                op_seq=op_seq,
                                next_attempt_seq=max(attempt_seqs + orphan_attempts)
                                + 1,
                            )
                    else:
                        # E1: the corrective attempt has not started. An
                        # orphaned corrective request burns its coordinate.
                        pending = PendingReexecute(
                            op_seq=op_seq,
                            next_attempt_seq=max([1] + orphan_attempts) + 1,
                        )
                    start_round = ref_round
                    if isinstance(pending, PendingResponse):
                        state.msg_history.append(
                            {
                                "role": "user",
                                "content": _round_prompt(ref_round)
                                + _final_round_correction_suffix(correction_feedback),
                            }
                        )
                        state.msg_history.append(
                            {
                                "role": "assistant",
                                "content": pending.response_text,
                            }
                        )
                    remaining = (num_reflections - ref_round) + (
                        max_generations - gen_idx - 1
                    ) * num_reflections
                    if isinstance(pending, PendingResponse):
                        # The committed corrective response only needs its
                        # local dispatch replayed, not a new provider attempt.
                        remaining -= 1
                    return _plan(
                        start_generation=gen_idx,
                        round_resume=RoundResume(
                            start_round=ref_round,
                            state=state,
                            pending=pending,
                            final_round_correction=correction_feedback,
                        ),
                        terminal=None,
                        bookkeeping=bookkeeping,
                        remaining=remaining,
                    )
            if op_seq is None:
                fail("RUN_CORRUPT", "Action outcome without its model operation")
            final = op_final.get(op_seq)
            if final is None or final["event_type"] != "operation.finished":
                fail("RUN_CORRUPT", "Action outcome without a committed response")
            response_text = _committed_response(final)
            state.msg_history.append(
                {"role": "user", "content": _round_prompt(ref_round)}
            )
            state.msg_history.append({"role": "assistant", "content": response_text})
            if len(round_outcomes) == 2:
                # Faithful reconstruction of the corrective re-ask pair: the
                # original response, then the corrective response to the
                # suffixed prompt.
                finals = [
                    event
                    for event in model_ops[op_seq]
                    if event["event_type"] == "operation.finished"
                ]
                if len(finals) < 2:
                    fail(
                        "RUN_CORRUPT",
                        "Correction round lacks its corrective response",
                    )
                state.msg_history[-1] = {
                    "role": "assistant",
                    "content": _committed_response(finals[0]),
                }
                state.msg_history.append(
                    {
                        "role": "user",
                        "content": _round_prompt(ref_round)
                        + _final_round_correction_suffix(
                            round_outcomes[0]["payload"]["feedback"]
                        ),
                    }
                )
                state.msg_history.append(
                    {"role": "assistant", "content": response_text}
                )
            for outcome_event in round_outcomes:
                outcome = outcome_event["payload"].get("outcome")
                if outcome == "tool_result":
                    if (
                        retrieval_event is None
                        or retrieval_event["event_type"] != "operation.finished"
                    ):
                        fail(
                            "RUN_CORRUPT",
                            "tool_result outcome without its retrieval operation",
                        )
                    payload = _retrieval_payload(retrieval_event)
                    papers = payload.get("papers", [])
                    paper_ids = sorted(p["paper_id"] for p in papers)
                    expected_ids = sorted(outcome_event["payload"].get("paper_ids", []))
                    if paper_ids != expected_ids or len(papers) != outcome_event[
                        "payload"
                    ].get("paper_count"):
                        fail(
                            "RUN_CORRUPT",
                            "Retrieval payload does not match its action_outcome",
                        )
                    state.retrieval_op_seqs.append(
                        retrieval_event["operation"]["operation_seq"]
                    )
                    if papers:
                        run_has_non_empty = True
                        for paper in papers:
                            state.retrieved_paper_ids.add(paper["paper_id"])
                    state.last_tool_results = format_retrieval_for_reflection(payload)
                elif outcome in ("model_fixable_error", FINAL_ROUND_CORRECTION_OUTCOME):
                    state.last_tool_results = outcome_event["payload"]["feedback"]
                elif outcome == "finalize_accepted":
                    # The generation closed live with generation.finished; gen_idx
                    # is unfinished, so this outcome is only legal as the very last
                    # committed event (the cut hit before generation.finished).
                    if outcome_event is not execution_events[-1]:
                        fail("RUN_CORRUPT", "Events follow a finalize_accepted outcome")
                    if finalize_event is None:
                        fail(
                            "RUN_CORRUPT",
                            "finalize_accepted without its finalization operation",
                        )
                    idea_pos = finalize_event["pipeline_position"]
                    return _close_generation(
                        idea_pos, finalize_event["payload"]["idea_index"]
                    )
                else:
                    fail("RUN_CORRUPT", f"Unknown action outcome: {outcome}")
            continue

        # No action_outcome: this is the interrupted round. Nothing may exist
        # for later rounds of this generation.
        _no_later_round_events(ref_round)
        start_round = ref_round

        if op_seq is None:
            # No model operation events: either a fresh round or a model call
            # interrupted after its request commit (orphan request.json).
            if finalize_event is not None:
                fail(
                    "RUN_CORRUPT", "Finalization operation without its model operation"
                )
            orphan_model_ops = [
                orphan_op
                for orphan_op, triples in orphan_by_op.items()
                if orphan_op not in ops_with_events
                and any(filename == "request.json" for _, filename in triples)
            ]
            if len(orphan_model_ops) > 1:
                fail("RUN_CORRUPT", "Multiple orphaned model requests")
            if orphan_model_ops:
                orphan_op = orphan_model_ops[0]
                next_attempt = max(a for a, _ in orphan_by_op[orphan_op]) + 1
                pending = PendingReexecute(
                    op_seq=orphan_op, next_attempt_seq=next_attempt
                )
            break

        final = op_final.get(op_seq)
        attempts = [
            e
            for e in model_ops[op_seq]
            if e["event_type"] == "provider_attempt.finished"
        ]
        orphan_attempts = [a for a, _ in orphan_by_op.get(op_seq, [])]
        if final is not None and orphan_attempts:
            fail("RUN_CORRUPT", "Orphan attempts beyond a finalized operation")

        if final is not None and final["event_type"] == "operation.failed":
            if final["payload"]["disposition"] == "terminal":
                return _plan(
                    start_generation=gen_idx,
                    round_resume=None,
                    terminal=SealFailedCompletion(
                        reason_code=final["payload"]["error_code"],
                        reason_message=_failure_message_from_chain(final),
                    ),
                    bookkeeping=bookkeeping,
                    remaining=0,
                )
            # Suspend-class failure committed: re-execute at the next attempt.
            attempt_seqs = [
                e["operation"]["attempt_seq"] for e in attempts
            ] + orphan_attempts
            pending = PendingReexecute(
                op_seq=op_seq, next_attempt_seq=max(attempt_seqs) + 1
            )
            break

        if final is None:
            # Only attempt events: the cut hit inside the success/failure
            # recording sequence of the last attempt.
            if not attempts:
                fail("RUN_CORRUPT", "Model operation without attempt events")
            last_attempt = attempts[-1]
            last_outcome = last_attempt["payload"].get("outcome")
            if last_outcome == "success":
                # Recover the operation.finished commit, then continue exactly
                # like the committed-finished path below.
                recovered = _recovered_finished_event(op_seq)
                bookkeeping.append({"kind": "append_event", "event": recovered})
                final = recovered
            elif last_attempt["payload"].get("disposition") == "terminal":
                error_code = last_attempt["payload"]["error_code"]
                bookkeeping.append(
                    {
                        "kind": "append_event",
                        "event": {
                            "event_type": "operation.failed",
                            "operation": {
                                "attempt_seq": last_attempt["operation"]["attempt_seq"],
                                "operation_kind": "model_inference",
                                "operation_seq": op_seq,
                            },
                            "payload": {
                                "disposition": "terminal",
                                "error_code": error_code,
                                "status": "failed",
                                "total_attempts": last_attempt["operation"][
                                    "attempt_seq"
                                ],
                            },
                            "pipeline_position": last_attempt.get("pipeline_position"),
                            "writer_epoch": writer_epoch,
                        },
                    }
                )
                return _plan(
                    start_generation=gen_idx,
                    round_resume=None,
                    terminal=SealFailedCompletion(
                        reason_code=error_code,
                        reason_message=_failure_message_from_chain(last_attempt),
                    ),
                    bookkeeping=bookkeeping,
                    remaining=0,
                )
            else:
                # Suspend-class attempt failure without a committed operation
                # final state (cut mid-call): re-execute at the next attempt.
                attempt_seqs = [
                    e["operation"]["attempt_seq"] for e in attempts
                ] + orphan_attempts
                pending = PendingReexecute(
                    op_seq=op_seq, next_attempt_seq=max(attempt_seqs) + 1
                )
                break

        # final is a committed (or recovered) operation.finished.
        response_text = _committed_response(final)
        round_pos = final.get("pipeline_position")

        if retrieval_event is not None:
            retr_op_seq = retrieval_event["operation"]["operation_seq"]
            if retrieval_event["event_type"] == "operation.finished":
                # Retrieval committed; the action_outcome commit was cut.
                payload = _retrieval_payload(retrieval_event)
                papers = payload.get("papers", [])
                bookkeeping.append(
                    {
                        "kind": "append_event",
                        "event": {
                            "event_type": "action_outcome",
                            "payload": {
                                "action": "SearchLiterature",
                                "outcome": "tool_result",
                                "paper_count": len(papers),
                                "paper_ids": sorted(p["paper_id"] for p in papers),
                                "schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
                            },
                            "pipeline_position": round_pos,
                            "writer_epoch": writer_epoch,
                        },
                    }
                )
                state.retrieval_op_seqs.append(retr_op_seq)
                if papers:
                    run_has_non_empty = True
                    for paper in papers:
                        state.retrieved_paper_ids.add(paper["paper_id"])
                state.msg_history.append(
                    {"role": "user", "content": _round_prompt(ref_round)}
                )
                state.msg_history.append(
                    {"role": "assistant", "content": response_text}
                )
                state.last_tool_results = format_retrieval_for_reflection(payload)
                continue
            # Retrieval input error committed; the feedback commit was cut.
            error_text = retrieval_event["payload"].get("error", "")
            error_code, _, error_message = error_text.partition(": ")
            if error_code not in MODEL_FIXABLE_ERROR_CODES:
                fail("RUN_CORRUPT", "Retrieval input failure is not model-fixable")
            bookkeeping.append(
                {
                    "kind": "model_fixable_feedback",
                    "action": "SearchLiterature",
                    "error_code": error_code,
                    "error_message": error_message,
                    "operation_seq": retr_op_seq,
                    "pipeline_pos": round_pos,
                }
            )
            state.msg_history.append(
                {"role": "user", "content": _round_prompt(ref_round)}
            )
            state.msg_history.append({"role": "assistant", "content": response_text})
            state.last_tool_results = f"Error [{error_code}]: {error_message}"
            continue

        if finalize_event is not None:
            # Finalization artifacts committed; the action_outcome and
            # generation.finished commits were cut.
            idea_pos = finalize_event["pipeline_position"]
            idea_index = finalize_event["payload"]["idea_index"]
            bookkeeping.append(
                {
                    "kind": "append_event",
                    "event": {
                        "event_type": "action_outcome",
                        "payload": {
                            "action": "FinalizeIdea",
                            "idea_index": idea_index,
                            "outcome": "finalize_accepted",
                            "schema_version": ACTION_OUTCOME_SCHEMA_VERSION,
                        },
                        "pipeline_position": idea_pos,
                        "writer_epoch": writer_epoch,
                    },
                }
            )
            return _close_generation(idea_pos, idea_index)

        # Response committed with no follow-up operation events: replay the
        # response. An orphaned retrieval request (payload/audit commit cut)
        # re-executes under its own operation coordinates.
        orphan_retrieval_ops = [
            orphan_op
            for orphan_op, triples in orphan_by_op.items()
            if orphan_op not in ops_with_events
            and any(
                filename in ("payload.json", "audit.json") for _, filename in triples
            )
        ]
        if len(orphan_retrieval_ops) > 1:
            fail("RUN_CORRUPT", "Multiple orphaned retrieval operations")
        if orphan_retrieval_ops:
            orphan_op = orphan_retrieval_ops[0]
            pending = PendingResponse(
                response_text=response_text,
                model_op_seq=op_seq,
                retrieval_op_seq=orphan_op,
                retrieval_attempt_seq=max(a for a, _ in orphan_by_op[orphan_op]) + 1,
            )
        else:
            pending = PendingResponse(
                response_text=response_text,
                model_op_seq=op_seq,
                retrieval_op_seq=None,
                retrieval_attempt_seq=1,
            )
        state.msg_history.append({"role": "user", "content": _round_prompt(ref_round)})
        state.msg_history.append({"role": "assistant", "content": response_text})
        break

    if start_round is None:
        # Every reflection round completed but the generation.finished commit
        # was cut (budget-exhausted close-out).
        return _close_generation(None, None)

    remaining = (num_reflections - start_round) + (
        max_generations - gen_idx - 1
    ) * num_reflections
    if isinstance(pending, PendingResponse):
        # The interrupted round's model call is already committed; its replay
        # (retrieval/action processing) is unpaid local work, so the remaining
        # model-round estimate must not count it again.
        remaining -= 1
    return _plan(
        start_generation=gen_idx,
        round_resume=RoundResume(
            start_round=start_round,
            state=state,
            pending=pending,
        ),
        terminal=None,
        bookkeeping=bookkeeping,
        remaining=remaining,
    )
