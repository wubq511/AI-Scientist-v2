"""Scoped Literature Retriever binding for an admitted run (ticket 04).

Ticket 04 only constructs the retriever bound to one Approved Target
Reference Corpus during preflight; the BM25 scoring, per-invocation corpus
re-verification, and audit-release machinery belong to ticket 05.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import fail

RETRIEVAL_POLICY_VERSION = "scoped-retrieval-policy-v1"


@dataclass(frozen=True, slots=True)
class BoundCorpus:
    """A preflight-validated corpus binding; the retriever's sole scope."""

    workspace_root: Path
    corpus_relpath: str
    corpus_sha256: str
    case_id: str
    record_count: int


def bind_corpus(
    workspace_root: Path,
    *,
    corpus_relpath: str,
    corpus_sha256: str,
    case_id: str,
    record_count: int,
) -> ScopedLiteratureRetriever:
    """Construct the retriever bound to exactly one Approved corpus."""
    bound = BoundCorpus(
        workspace_root=workspace_root,
        corpus_relpath=corpus_relpath,
        corpus_sha256=corpus_sha256,
        case_id=case_id,
        record_count=record_count,
    )
    return ScopedLiteratureRetriever(bound)


class ScopedLiteratureRetriever:
    """The model-visible literature tool bound to one Approved corpus.

    Ticket 04 admits runs without retrieval execution; `search` arrives
    with ticket 05 and must never be reachable before admission.
    """

    def __init__(self, bound: BoundCorpus) -> None:
        self._bound = bound

    @property
    def policy_version(self) -> str:
        return RETRIEVAL_POLICY_VERSION

    def search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        fail(
            "RETRIEVAL_NOT_AVAILABLE",
            "Retrieval execution is not implemented before ticket 05",
        )
