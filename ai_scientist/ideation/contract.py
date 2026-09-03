from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re

from .canonical import relative_posix, sha256_bytes

WORKSHOP_CONTRACT_VERSION = "workshop-contract-v1.0"
WORKSHOP_AUTHORING_SOURCE_SCHEMA_VERSION = "workshop-authoring-source-v1.0"
WORKSHOP_PREPARATION_SCHEMA_VERSION = "workshop-preparation-v1.0"
WORKSHOP_DERIVATION_SCHEMA_VERSION = "workshop-derivation-v1.0"
WORKSHOP_ATTEMPT_SCHEMA_VERSION = "workshop-attempt-v1.0"
WORKSHOP_VALIDATION_SCHEMA_VERSION = "workshop-validation-v1.0"
WORKSHOP_SEMANTIC_PACKET_SCHEMA_VERSION = "workshop-semantic-packet-v1.1"
WORKSHOP_SEMANTIC_DECISION_SCHEMA_VERSION = "workshop-semantic-decision-v1.1"
WORKSHOP_RESOLUTION_SCHEMA_VERSION = "workshop-resolution-v1.0"
WORKSHOP_MANIFEST_SCHEMA_VERSION = "approved-workshop-manifest-v1.1"
WORKSHOP_VALIDATOR_VERSION = "workshop-validator-v1.1"
WORKSHOP_POLICY_PATH = Path("ai_scientist/ideation/policies/workshop-leakage-v1.json")
WORKSHOP_POLICY_SHA256 = (
    "5147d6b1d951e2de0f50fb132955e053e638ffd3daa6292c08a047f8fdc21f61"
)
SOURCE_ALLOWLIST = ["title", "abstract"]
SEMANTIC_CHECKS = (
    "abstract_is_neutral_problem_scope",
    "allows_multiple_method_families",
    "keywords_are_established_terms",
    "no_answer_leakage",
    "no_identity_leakage",
    "target_relevant",
    "title_is_identity_free_problem_area",
    "tldr_is_open_question_or_tension",
    "written_in_english",
)
TARGET_REQUIRED_FIELDS = {
    "paperId",
    "title",
    "abstract",
    "externalIds",
    "abstract_summary",
}
REFERENCE_REQUIRED_FIELDS = {"targetPaperId", "paperId", "contexts"}
WORKSHOP_PATTERN = re.compile(
    r"\A# Title: ([^\n]+)\n\n"
    r"## Keywords\n([^\n]+)\n\n"
    r"## TL;DR\n([^\n]+)\n\n"
    r"## Abstract\n(.+)\n\Z",
    re.DOTALL,
)
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
PAPER_ID_PATTERN = re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    target_path: Path
    target_sha256: str
    target_row: dict[str, str]
    target_row_number: int
    target_row_sha256: str
    reference_path: Path
    reference_sha256: str
    reference_rows: tuple[tuple[int, dict[str, str], str], ...]
    external_ids: tuple[tuple[str, str], ...]
    reference_contexts: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class LeakagePolicy:
    version: str
    schema_version: str
    normalization_version: str
    ngram_tokens: int
    comparison_sources: tuple[str, ...]
    calibration_status: str
    sha256: str


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _artifact_ref(path: Path, workspace_root: Path, data: bytes) -> dict[str, str]:
    return {
        "path": relative_posix(path, workspace_root),
        "sha256": sha256_bytes(data),
    }
