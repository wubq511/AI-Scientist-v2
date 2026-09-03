"""Ideation Run Controller (tickets 07, 08, 09, 023, 024, 025, 026, 038).

Drives the approved generation/reflection loop for an admitted Ideation Run:
executes model inference rounds via DeepSeek adapter, invokes Scoped Literature
Retriever for evidence, enforces the FinalizeIdea gate (payload hygiene,
seven-field structure, Declared Grounding, and within-run duplicates in the
approved fixed priority), commits accepted ideas atomically before advancing to
the next generation, seals terminal outcomes -- success or explicit failed --
with a canonical seal.json, and suspends without a seal on environment-class
failures.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Sequence

from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
    workspace_relative_path,
)
from .contract import _now
from .deepseek import (
    DEEPSEEK_ADAPTER_SCHEMA_VERSION,
    DeepSeekAdapter,
    DeepSeekMessage,
    DeepSeekRequest,
    ModelRoundError,
    ModelRoundResult,
    TERMINAL_FAILURES,
)
from .errors import IdeationInputError, fail
from .retrieval import ScopedLiteratureRetriever, bind_corpus
from .run_store import (
    RUN_SEAL_SCHEMA_VERSION,
    RunStore,
)

IDEA_SIDECAR_SCHEMA_VERSION = "idea-sidecar-v1.0.0"
ACTION_OUTCOME_SCHEMA_VERSION = "action-outcome-v1.0.0"
WORKSHOP_RENDERING_VERSION = "raw_markdown_v1"

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

TERMINAL_OUTCOME_CODES: frozenset[str] = (
    CONTROLLER_TERMINAL_CODES
    | ADAPTER_TERMINAL_CODES
    | RETRIEVER_EVIDENCE_TERMINAL_CODES
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

# Baseline generation and reflection prompts verbatim (Ticket 006 / Ticket 024)
IDEA_GENERATION_PROMPT = """{workshop_description}

Here are the proposals that you have already generated:

'''
{prev_ideas_string}
'''

Begin by generating an interestingly new high-level research proposal that differs from what you have previously proposed.
"""

IDEA_REFLECTION_PROMPT = """Round {current_round}/{num_reflections}.

In your thoughts, first carefully consider the quality, novelty, and feasibility of the proposal you just created.
Include any other factors that you think are important in evaluating the proposal.
Ensure the proposal is clear and concise, and the JSON is in the correct format.
Do not make things overly complicated.
In the next attempt, try to refine and improve your proposal.
Stick to the spirit of the original idea unless there are glaring issues.

If you have new information from tools, such as literature search results, incorporate them into your reflection and refine your proposal accordingly.

Results from your last action (if any):

{last_tool_results}
"""


def build_tool_catalog() -> tuple[str, str]:
    """Return the model-visible tool descriptions and comma-separated quoted names."""
    descriptions = (
        "- **SearchLiterature**: Search the literature for relevant research papers and background work. "
        'Provide a concise natural language search query as {"query": "your query"}.\n\n'
        "- **FinalizeIdea**: Finalize your idea by providing the idea details and declared grounding.\n\n"
        "The IDEA JSON should include the following fields:\n"
        '- "Name": A short descriptor of the idea. Lowercase, no spaces, underscores allowed.\n'
        '- "Title": A catchy and informative title for the proposal.\n'
        '- "Short Hypothesis": A concise statement of the main hypothesis or research question. '
        "Clarify the need for this specific direction, ensure this is the best setting to investigate this idea, "
        "and there are not obvious other simpler ways to answer the question.\n"
        '- "Related Work": A brief discussion of the most relevant related work and how the proposal clearly '
        "distinguishes from it, and is not a trivial extension.\n"
        '- "Abstract": An abstract that summarizes the proposal in conference format (approximately 250 words).\n'
        '- "Experiments": A list of experiments that would be conducted to validate the proposal. '
        "Ensure these are simple and feasible. Be specific in exactly how you would test the hypothesis, "
        "and detail precise algorithmic changes. Include the evaluation metrics you would use.\n"
        '- "Risk Factors and Limitations": A list of potential risks and limitations of the proposal.'
    )
    names_str = '"SearchLiterature", "FinalizeIdea"'
    return descriptions, names_str


def build_system_prompt() -> str:
    """Build the model-visible system prompt adhering to Ticket 024 and Ticket 038."""
    tool_descriptions, tool_names_str = build_tool_catalog()
    return f"""You are an experienced AI researcher who aims to propose high-impact research ideas resembling exciting grant proposals. Feel free to propose any novel ideas or experiments; make sure they are novel. Be very creative and think out of the box. Each proposal should stem from a simple and elegant question, observation, or hypothesis about the topic. For example, they could involve very interesting and simple interventions or investigations that explore new possibilities or challenge existing assumptions. Clearly clarify how the proposal distinguishes from the existing literature.

Ensure that the proposal does not require resources beyond what an academic lab could afford. These proposals should lead to papers that are publishable at top ML conferences.

You have access to the following tools:

{tool_descriptions}

Respond in the following format:

ACTION:
<The action to take, exactly one of {tool_names_str}>

ARGUMENTS:
<If ACTION is "SearchLiterature", provide the search query as {{"query": "your search query"}}. If ACTION is "FinalizeIdea", provide the idea details and grounding as {{"idea": {{ ... }}, "grounding": ["paper_id_1", ...]}} with the IDEA JSON specified below.>

If you choose to finalize your idea, provide the IDEA JSON in the arguments:

IDEA JSON:
```json
{{
  "idea": {{
    "Name": "...",
    "Title": "...",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "Abstract": "...",
    "Experiments": [
      "..."
    ],
    "Risk Factors and Limitations": [
      "..."
    ]
  }},
  "grounding": [
    "paper_id_1"
  ]
}}
```

Ensure the JSON is properly formatted for automatic parsing.

Note: You should perform at least one literature search before finalizing your idea to ensure it is well-informed by existing research."""


def _failure_message(exc: ModelRoundError) -> str:
    """Extract the provider failure message from a ModelRoundError."""
    failure = getattr(exc, "failure", None)
    message = getattr(failure, "message", None)
    if isinstance(message, str) and message:
        return message
    return str(exc)


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


def _scan_submission_hygiene(arguments_text: str) -> list[dict[str, Any]]:
    """Hygiene-scan the raw ARGUMENTS submission block, parse errors included."""
    return scan_payload_hygiene(arguments_text)


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
    ) -> None:
        self.workspace_root = workspace_root.resolve(strict=True)
        self.run_id = run_id
        self.store = store or RunStore(self.workspace_root)
        self.writer_epoch = writer_epoch

        # Load and verify write-once admission
        admission_bytes = self.store.read_artifact(self.run_id, "admission.json")
        self.admission = parse_json_bytes(admission_bytes, label="admission.json")
        self.admission_sha = sha256_bytes(admission_bytes)
        self.request_sha = self.admission["request_sha256"]

        # Verify admission event pin in evidence chain
        admitted_event = self.store.read_event(self.run_id, 8)
        if (
            admitted_event.get("event_type") != "admitted"
            or admitted_event.get("admission_sha256") != self.admission_sha
        ):
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

    def _next_op_seq(self) -> int:
        self.op_seq += 1
        return self.op_seq

    def run(self) -> dict[str, Any]:
        """Execute the complete generation loop through final seal."""
        system_prompt = build_system_prompt()

        for gen_idx in range(self.max_num_generations):
            try:
                sealed = self._execute_generation(gen_idx, system_prompt)
            except IdeationInputError as exc:
                # Deterministic retriever/evidence boundary failures terminate
                # the run through an explicit failed seal; no retry, no
                # fallback, and no model-fixable masking (Ticket 020/025).
                return self._seal_failed_run(exc.code, exc.message or str(exc))
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
        if reason_code in ADAPTER_TERMINAL_CODES:
            reason_kind = "provider"
        elif reason_code in RETRIEVER_EVIDENCE_TERMINAL_CODES:
            reason_kind = "retriever_evidence"
        elif reason_code in CONTROLLER_TERMINAL_CODES:
            reason_kind = "controller"
        else:
            fail(
                "INVALID_FAILURE_CODE",
                f"Reason code is not an approved terminal outcome code: {reason_code}",
            )

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

        # Verify complete chain integrity up to terminal event
        self.store.verify_chain(self.run_id)

        inventory = self.store.build_artifact_inventory(self.run_id)
        seal_document = {
            "admission_sha256": self.admission_sha,
            "artifact_inventory": inventory,
            "final_event": {
                "event_hash": terminal_record.event_hash,
                "event_seq": terminal_record.event_seq,
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
    ) -> str:
        """Record model-fixable error feedback, write artifact, and append action_outcome event."""
        feedback_text = (
            f"Error [{error_code}]: {error_message}"
            if error_code not in error_message
            else error_message
        )
        feedback_bytes = feedback_text.encode("utf-8")
        rel_path, byte_length, sha = self.store.write_operation_artifact(
            self.run_id,
            operation_seq,
            1,
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
                    "outcome": "model_fixable_error",
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
            "FinalizeIdea submission matched a private identifier hygiene pattern",
        )

    def _execute_generation(
        self, gen_idx: int, system_prompt: str
    ) -> dict[str, Any] | None:
        """Execute a single generation with reflection rounds.

        Returns the sealed run result when a terminal condition sealed the run
        mid-generation (payload hygiene hit), otherwise None.
        """
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

        prev_ideas_string = "\n\n".join(self.idea_str_archive)
        msg_history: list[dict[str, str]] = []
        last_tool_results = ""
        generation_retrieved_paper_ids: set[str] = set()
        generation_retrieval_op_seqs: list[int] = []
        generation_finalized = False

        for ref_round in range(self.num_reflections):
            pipeline_pos = {
                "generation_index": gen_idx,
                "idea_index": (
                    len(self.accepted_ideas) if generation_finalized else None
                ),
                "reflection_index": ref_round,
            }

            if ref_round == 0:
                prompt_text = IDEA_GENERATION_PROMPT.format(
                    workshop_description=self.workshop_description,
                    prev_ideas_string=prev_ideas_string,
                )
            else:
                prompt_text = IDEA_REFLECTION_PROMPT.format(
                    current_round=ref_round + 1,
                    last_tool_results=last_tool_results or "No new results.",
                    num_reflections=self.num_reflections,
                )

            # Assemble messages for this round
            messages = [DeepSeekMessage(role="system", content=system_prompt)]
            for hist in msg_history:
                messages.append(
                    DeepSeekMessage(role=hist["role"], content=hist["content"])
                )
            messages.append(DeepSeekMessage(role="user", content=prompt_text))

            # Model inference operation
            model_op_seq = self._next_op_seq()
            req = DeepSeekRequest(
                max_tokens=self.admission["model"]["max_tokens"],
                messages=tuple(messages),
                output_mode="text",
                reasoning_effort=self.admission["model"]["reasoning_effort"],
                user_id=f"run-{self.run_id[:8]}",
            )

            round_result: ModelRoundResult = self.adapter.execute_round(
                req,
                model_op_seq,
                pipeline_position=pipeline_pos,
                writer_epoch=self.writer_epoch,
            )

            response_text = round_result.visible_content
            msg_history.append({"role": "user", "content": prompt_text})
            msg_history.append({"role": "assistant", "content": response_text})

            # Parse ACTION and ARGUMENTS
            try:
                action, arguments = parse_action_and_arguments(response_text)
            except IdeationInputError as exc:
                if exc.code in MODEL_FIXABLE_ERROR_CODES:
                    last_tool_results = self._record_model_fixable_error(
                        action="unknown",
                        error_code=exc.code,
                        error_message=exc.message or str(exc),
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue
                raise

            if action not in MODEL_VISIBLE_ACTIONS:
                last_tool_results = self._record_model_fixable_error(
                    action=action,
                    error_code="UNKNOWN_ACTION",
                    error_message=f"Action '{action}' is not model-visible. Allowed actions are 'SearchLiterature' and 'FinalizeIdea'.",
                    operation_seq=model_op_seq,
                    pipeline_pos=pipeline_pos,
                )
                continue

            if action == "SearchLiterature":
                retrieval_op_seq = self._next_op_seq()
                try:
                    retrieval_payload = self.retriever.search(
                        arguments,
                        operation_seq=retrieval_op_seq,
                        attempt_seq=1,
                    )
                except IdeationInputError as exc:
                    if exc.code in MODEL_FIXABLE_ERROR_CODES:
                        last_tool_results = self._record_model_fixable_error(
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
                # Finalization gate priority 1: payload hygiene scan on the raw
                # submission bytes (Ticket 038 gate order). A pattern hit is a
                # terminal condition; it must never be masked by, or converted
                # into, lower-priority model-fixable feedback (Ticket 026).
                arguments_match = HYGIENE_SCAN_ARGUMENTS_PATTERN.search(response_text)
                if arguments_match:
                    hygiene_hits = _scan_submission_hygiene(
                        arguments_match.group(1).strip()
                    )
                    if hygiene_hits:
                        return self._record_hygiene_hit(
                            hits=hygiene_hits,
                            operation_seq=model_op_seq,
                            pipeline_pos=pipeline_pos,
                        )

                # Check closed two-key arguments structure (Ticket 038)
                if not isinstance(arguments, dict):
                    last_tool_results = self._record_model_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_ARGUMENTS_JSON",
                        error_message="FinalizeIdea arguments must be a JSON object",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                extra_args = set(arguments.keys()) - {"idea", "grounding"}
                if extra_args:
                    last_tool_results = self._record_model_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_IDEA_STRUCTURE",
                        error_message=f"FinalizeIdea arguments contain unknown fields: {sorted(extra_args)}. Allowed fields are exactly 'idea' and 'grounding'",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                if "idea" not in arguments:
                    last_tool_results = self._record_model_fixable_error(
                        action="FinalizeIdea",
                        error_code="INVALID_IDEA_STRUCTURE",
                        error_message="FinalizeIdea arguments missing required 'idea' field",
                        operation_seq=model_op_seq,
                        pipeline_pos=pipeline_pos,
                    )
                    continue

                if "grounding" not in arguments:
                    last_tool_results = self._record_model_fixable_error(
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
                        last_tool_results = self._record_model_fixable_error(
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
                    last_tool_results = self._record_model_fixable_error(
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
                        last_tool_results = self._record_model_fixable_error(
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
                    last_tool_results = self._record_model_fixable_error(
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
                    last_tool_results = self._record_model_fixable_error(
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
                    "reflection_index": ref_round,
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
                    "reflection_index": ref_round,
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
