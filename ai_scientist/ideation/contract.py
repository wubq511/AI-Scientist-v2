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
CORPUS_CONTRACT_VERSION = "corpus-contract-v1.0"
CORPUS_SCHEMA_VERSION = "corpus-schema-v1.0"
CORPUS_NORMALIZATION_VERSION = "source-text-nfc-lf-trim-v1"
CORPUS_ENRICHMENT_POLICY_VERSION = "reference-authority-v1.0"
CORPUS_VALIDATOR_VERSION = "corpus-validator-v1.0"
CORPUS_MANIFEST_SCHEMA_VERSION = "corpus-manifest-v1.0"
CORPUS_VALIDATION_REPORT_SCHEMA_VERSION = "corpus-validation-report-v1.0"
CORPUS_APPROVAL_DECISION_SCHEMA_VERSION = "corpus-approval-decision-v1.0"
CORPUS_POLICY_PATH = Path("ai_scientist/ideation/policies/reference-authority-v1.json")
CORPUS_POLICY_SHA256 = (
    "65b0d9aa5942eb164370fb6d7162fbd6b4a629488a6093e0e0ebfd44eb1e6a5f"
)
EVALUATION_ARTIFACT_SCHEMA_VERSION = "evaluation-artifact-v1.0.0"
EVALUATION_RUBRIC_SCHEMA_VERSION = "idea-quality-rubric-schema-v1.0"
EVALUATION_RUBRIC_POLICY_PATH = Path(
    "ai_scientist/ideation/policies/idea-quality-rubric-v1.json"
)
EVALUATION_RUBRIC_POLICY_SHA256 = (
    "3b1548d06060047ac29f759d8c5f3e46d0287d6593f3fd839ef80074ca0b3d8c"
)
EVALUATION_ROOT_RELPATH = Path("artifacts/evaluations")
CORPUS_QUARANTINED_FIELDS = frozenset(
    {
        "targetPaperId",
        "contexts",
        "intents",
        "isInfluential",
        "citationCount",
        "abstract_summary",
        "query",
        "score",
        "rank",
    }
)
CORPUS_KNOWN_BAD_TEXTS = frozenset({"falls,", "Statistics Working Papers Series"})
CORPUS_ALLOWED_CONTENT_TYPES = frozenset({"publisher_abstract", "official_full_text"})
CORPUS_ALLOWED_CONTENT_STATUSES = frozenset({"validated", "not_published"})
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

# DeepSeek provider identity and pinned execution defaults (tickets 022/031).
# Single source of truth for both the admission Run Specification pin and the
# adapter enforcement; the Canary-open parameters (035/036) ship as pinned
# defaults so an admitted run stays immutable.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL_ID = "deepseek-v4-pro"
DEFAULT_REASONING_EFFORT = "high"
MAX_ATTEMPTS_PER_OPERATION = 2


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
