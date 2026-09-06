from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from .canonical import (
    parse_json_bytes,
    read_exact_bytes,
    resolve_repo_relative,
    sha256_bytes,
)
from .errors import fail
from .normalization import normalize_query, tokenize_text
from .schema import CandidateSpec, Case, DenseModelSpec, ProtocolSpec


@dataclass(frozen=True, slots=True)
class CollectionStats:
    documents: dict[str, tuple[str, ...]]
    document_frequency: Counter[str]
    collection_frequency: Counter[str]
    average_document_length: float

    @property
    def size(self) -> int:
        return len(self.documents)


def build_collection(documents: dict[str, str], *, label: str) -> CollectionStats:
    if not documents:
        fail("INVALID_CORPUS", f"{label} collection is empty")
    tokenized: dict[str, tuple[str, ...]] = {}
    document_frequency: Counter[str] = Counter()
    collection_frequency: Counter[str] = Counter()
    total_length = 0
    for document_id, text in documents.items():
        tokens = tokenize_text(text, label=f"{label}.{document_id}")
        if not tokens:
            fail("INVALID_CORPUS", f"{label}.{document_id} has no searchable tokens")
        tokenized[document_id] = tokens
        total_length += len(tokens)
        document_frequency.update(set(tokens))
        collection_frequency.update(tokens)
    average_document_length = total_length / len(tokenized)
    if average_document_length <= 0 or not math.isfinite(average_document_length):
        fail("INVALID_CORPUS", f"{label} has invalid collection statistics")
    return CollectionStats(
        documents=tokenized,
        document_frequency=document_frequency,
        collection_frequency=collection_frequency,
        average_document_length=average_document_length,
    )


def _smoothed_idf(stats: CollectionStats, token: str) -> float:
    return math.log((stats.size + 1) / (stats.document_frequency[token] + 1)) + 1


def _idf_coverage(
    query_tokens: tuple[str, ...],
    document_tokens: tuple[str, ...],
    stats: CollectionStats,
) -> float:
    unique_query = tuple(dict.fromkeys(query_tokens))
    denominator = sum(_smoothed_idf(stats, token) for token in unique_query)
    if denominator <= 0 or not math.isfinite(denominator):
        fail("INVALID_SCORE", "idf_coverage has an invalid denominator")
    document_terms = set(document_tokens)
    numerator = sum(
        _smoothed_idf(stats, token) for token in unique_query if token in document_terms
    )
    return numerator / denominator


def _tfidf_cosine(
    query_tokens: tuple[str, ...],
    document_tokens: tuple[str, ...],
    stats: CollectionStats,
) -> float:
    query_terms = set(query_tokens)
    document_counts = Counter(document_tokens)
    vocabulary = query_terms | set(document_counts)
    dot = 0.0
    query_norm = 0.0
    document_norm = 0.0
    for token in vocabulary:
        idf = _smoothed_idf(stats, token)
        query_weight = idf if token in query_terms else 0.0
        document_weight = document_counts[token] * idf
        dot += query_weight * document_weight
        query_norm += query_weight * query_weight
        document_norm += document_weight * document_weight
    if query_norm == 0 or document_norm == 0:
        return 0.0
    return dot / math.sqrt(query_norm * document_norm)


def _bm25(
    query_tokens: tuple[str, ...],
    document_tokens: tuple[str, ...],
    stats: CollectionStats,
    *,
    k1: float,
    b: float,
) -> float:
    if stats.average_document_length <= 0:
        fail("INVALID_SCORE", "BM25 average document length must be positive")
    counts = Counter(document_tokens)
    document_length = len(document_tokens)
    score = 0.0
    for token in dict.fromkeys(query_tokens):
        term_frequency = counts[token]
        if term_frequency == 0:
            continue
        document_frequency = stats.document_frequency[token]
        idf = math.log(
            1 + (stats.size - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        denominator = term_frequency + k1 * (
            1 - b + b * document_length / stats.average_document_length
        )
        if denominator <= 0:
            fail("INVALID_SCORE", "BM25 denominator must be positive")
        score += idf * (term_frequency * (k1 + 1)) / denominator
    return score


def _dph(
    query_tokens: tuple[str, ...],
    document_tokens: tuple[str, ...],
    stats: CollectionStats,
) -> float:
    document_length = len(document_tokens)
    if document_length <= 0 or stats.average_document_length <= 0 or stats.size <= 0:
        fail("INVALID_SCORE", "DPH requires positive collection statistics")
    counts = Counter(document_tokens)
    score = 0.0
    for token in dict.fromkeys(query_tokens):
        term_frequency = counts[token]
        if term_frequency == 0:
            continue
        collection_frequency = stats.collection_frequency[token]
        if collection_frequency <= 0:
            fail("INVALID_SCORE", "DPH collection frequency must be positive")
        relative_frequency = (
            term_frequency / document_length
            if term_frequency < document_length
            else 0.99999
        )
        norm = (1 - relative_frequency) ** 2 / (term_frequency + 1)
        first = (
            term_frequency
            * stats.average_document_length
            / document_length
            * (stats.size / collection_frequency)
        )
        second = 2 * math.pi * term_frequency * (1 - relative_frequency)
        if first <= 0 or second <= 0:
            fail("INVALID_SCORE", "DPH logarithm arguments must be positive")
        score += norm * (term_frequency * math.log2(first) + 0.5 * math.log2(second))
    return score


def score_lexical_collection(
    scorer: str,
    query_tokens: tuple[str, ...],
    stats: CollectionStats,
    parameters: dict[str, float],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for document_id, document_tokens in stats.documents.items():
        if scorer == "idf_coverage":
            score = _idf_coverage(query_tokens, document_tokens, stats)
        elif scorer == "tfidf_cosine":
            score = _tfidf_cosine(query_tokens, document_tokens, stats)
        elif scorer == "bm25":
            score = _bm25(
                query_tokens,
                document_tokens,
                stats,
                k1=parameters["k1"],
                b=parameters["b"],
            )
        elif scorer == "dph":
            score = _dph(query_tokens, document_tokens, stats)
        else:
            fail("UNSUPPORTED_SCORER", "Unknown lexical scorer", scorer=scorer)
        if not math.isfinite(score):
            fail(
                "INVALID_SCORE",
                "Scorer produced a non-finite value",
                document_id=document_id,
            )
        scores[document_id] = score
    return scores


class LexicalCaseScorer:
    def __init__(self, case: Case, candidate: CandidateSpec) -> None:
        self.case = case
        self.candidate = candidate
        self.segment_stats = build_collection(
            {
                segment.segment_id: segment.text
                for paper in case.papers
                for segment in paper.segments
            },
            label=f"{case.case_id}.segments",
        )
        self.title_stats = build_collection(
            {paper.paper_id: paper.title for paper in case.papers},
            label=f"{case.case_id}.titles",
        )

    def score(
        self, query_text: str
    ) -> tuple[tuple[str, ...], dict[str, float], dict[str, float]]:
        query = normalize_query(query_text)
        segment_scores = score_lexical_collection(
            self.candidate.scorer,
            query.tokens,
            self.segment_stats,
            self.candidate.parameters,
        )
        title_scores = score_lexical_collection(
            self.candidate.scorer,
            query.tokens,
            self.title_stats,
            self.candidate.parameters,
        )
        return query.tokens, segment_scores, title_scores

    def unit_tokens(
        self,
    ) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
        return self.segment_stats.documents, self.title_stats.documents


ALLOWED_MODEL_FILES = {
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
}


def validate_model_artifacts(repo_root: Path, model: DenseModelSpec) -> Path:
    artifact_dir = resolve_repo_relative(
        repo_root, model.artifact_dir, label="dense artifact_dir"
    )
    if not artifact_dir.is_dir():
        fail("MISSING_MODEL", "Dense model artifact directory is missing")
    actual_files = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    if actual_files != ALLOWED_MODEL_FILES or any(
        path.is_dir() for path in artifact_dir.iterdir()
    ):
        fail(
            "MODEL_ALLOWLIST_VIOLATION",
            "Dense model directory must contain exactly the approved files",
            missing=sorted(ALLOWED_MODEL_FILES - actual_files),
            extra=sorted(actual_files - ALLOWED_MODEL_FILES),
        )
    manifest_path = resolve_repo_relative(
        repo_root, model.artifact_manifest.path, label="dense artifact_manifest"
    )
    manifest_data = read_exact_bytes(
        manifest_path, model.artifact_manifest.sha256, label="dense artifact manifest"
    )
    manifest_value = parse_json_bytes(manifest_data, label="dense artifact manifest")
    if not isinstance(manifest_value, dict) or set(manifest_value) != {"files"}:
        fail("INVALID_MODEL_MANIFEST", "Dense artifact manifest has an invalid schema")
    files = manifest_value["files"]
    if not isinstance(files, list):
        fail("INVALID_MODEL_MANIFEST", "Dense artifact manifest files must be an array")
    entries: dict[str, tuple[int, str]] = {}
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}:
            fail("INVALID_MODEL_MANIFEST", "Dense artifact entry has an invalid schema")
        name = entry["path"]
        size = entry["bytes"]
        digest = entry["sha256"]
        if (
            name not in ALLOWED_MODEL_FILES
            or isinstance(size, bool)
            or not isinstance(size, int)
        ):
            fail("INVALID_MODEL_MANIFEST", "Dense artifact entry is invalid")
        if not isinstance(digest, str) or len(digest) != 64:
            fail("INVALID_MODEL_MANIFEST", "Dense artifact SHA-256 is invalid")
        if name in entries:
            fail(
                "INVALID_MODEL_MANIFEST", "Dense artifact manifest contains duplicates"
            )
        entries[name] = (size, digest)
    if set(entries) != ALLOWED_MODEL_FILES:
        fail("INVALID_MODEL_MANIFEST", "Dense artifact manifest is incomplete")
    for name, (expected_size, expected_digest) in entries.items():
        path = artifact_dir / name
        data = path.read_bytes()
        if len(data) != expected_size or sha256_bytes(data) != expected_digest:
            fail(
                "MODEL_HASH_MISMATCH",
                "Dense model artifact failed verification",
                file=name,
            )
    weight_size, weight_digest = entries["model.safetensors"]
    if weight_size != model.weight_bytes or weight_digest != model.weight_sha256:
        fail("MODEL_HASH_MISMATCH", "Dense weight identity differs from protocol")
    return artifact_dir


class DenseEncoder:
    def __init__(self, repo_root: Path, protocol: ProtocolSpec) -> None:
        model_spec = protocol.dense_model
        if model_spec is None:
            fail("MISSING_MODEL", "Dense candidate has no pinned model specification")
        artifact_dir = validate_model_artifacts(repo_root, model_spec)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        try:
            torch_version = metadata.version("torch")
            transformers_version = metadata.version("transformers")
        except metadata.PackageNotFoundError as exc:
            fail(
                "MISSING_DEPENDENCY",
                "Dense runtime dependency is not installed",
                package=exc.name,
            )
        if (
            torch_version != model_spec.torch_version
            or transformers_version != model_spec.transformers_version
        ):
            fail(
                "DEPENDENCY_VERSION_MISMATCH",
                "Dense runtime dependencies differ from the frozen protocol",
                torch=torch_version,
                transformers=transformers_version,
            )
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:  # noqa: BLE001
            fail(
                "DEPENDENCY_IMPORT_FAILED",
                "Dense dependencies failed to import",
                error=str(exc),
            )
        self.torch = torch
        self.spec = model_spec
        torch.set_num_threads(protocol.runtime.thread_count)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                artifact_dir,
                local_files_only=True,
            )
            self.model = AutoModel.from_pretrained(
                artifact_dir,
                local_files_only=True,
                use_safetensors=True,
            )
        except Exception as exc:  # noqa: BLE001 - normalize all offline loader failures
            fail(
                "MODEL_LOAD_FAILED",
                "Pinned dense model failed to load offline",
                error=str(exc),
            )
        self.model.to("cpu")
        self.model.eval()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=False,
            return_tensors="pt",
        )
        token_lengths = encoded["attention_mask"].sum(dim=1).tolist()
        if any(length > self.spec.max_length for length in token_lengths):
            fail(
                "DENSE_INPUT_TOO_LONG",
                "Dense input exceeds the pinned tokenizer limit without truncation",
                maximum=self.spec.max_length,
                actual=max(token_lengths),
            )
        with self.torch.inference_mode():
            output = self.model(**encoded)
            attention_mask = encoded["attention_mask"]
            masked = output.last_hidden_state.masked_fill(
                ~attention_mask[..., None].bool(), 0.0
            )
            pooled = masked.sum(dim=1) / attention_mask.sum(dim=1)[..., None]
            normalized = self.torch.nn.functional.normalize(pooled, p=2, dim=1)
        if normalized.shape[1] != self.spec.embedding_dimension:
            fail(
                "MODEL_OUTPUT_MISMATCH",
                "Dense embedding dimension differs from protocol",
            )
        return normalized.cpu().tolist()

    def encode_query(self, query_text: str) -> list[float]:
        query = normalize_query(query_text)
        return self._encode([self.spec.query_prefix + query.normalized])[0]

    def encode_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.spec.passage_prefix + text for text in texts])


class DenseCaseScorer:
    def __init__(self, case: Case, encoder: DenseEncoder) -> None:
        self.case = case
        self.encoder = encoder
        self.segment_ids = [
            segment.segment_id for paper in case.papers for segment in paper.segments
        ]
        self.title_ids = [paper.paper_id for paper in case.papers]
        segment_texts = [
            segment.text for paper in case.papers for segment in paper.segments
        ]
        title_texts = [paper.title for paper in case.papers]
        self.segment_embeddings = dict(
            zip(self.segment_ids, encoder.encode_passages(segment_texts), strict=True)
        )
        self.title_embeddings = dict(
            zip(self.title_ids, encoder.encode_passages(title_texts), strict=True)
        )

    @staticmethod
    def _dot(left: list[float], right: list[float]) -> float:
        score = sum(a * b for a, b in zip(left, right, strict=True))
        if not math.isfinite(score):
            fail("INVALID_SCORE", "Dense scorer produced a non-finite value")
        return score

    def score(
        self, query_text: str
    ) -> tuple[tuple[str, ...], dict[str, float], dict[str, float]]:
        query = normalize_query(query_text)
        query_embedding = self.encoder.encode_query(query_text)
        segment_scores = {
            identifier: self._dot(query_embedding, embedding)
            for identifier, embedding in self.segment_embeddings.items()
        }
        title_scores = {
            identifier: self._dot(query_embedding, embedding)
            for identifier, embedding in self.title_embeddings.items()
        }
        return query.tokens, segment_scores, title_scores

    def unit_tokens(
        self,
    ) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
        return (
            {
                segment.segment_id: tokenize_text(segment.text)
                for paper in self.case.papers
                for segment in paper.segments
            },
            {paper.paper_id: tokenize_text(paper.title) for paper in self.case.papers},
        )


def prepare_case_scorer(
    repo_root: Path,
    protocol: ProtocolSpec,
    case: Case,
    candidate: CandidateSpec,
    dense_encoder: DenseEncoder | None,
) -> LexicalCaseScorer | DenseCaseScorer:
    if candidate.scorer in {"idf_coverage", "tfidf_cosine", "bm25", "dph"}:
        return LexicalCaseScorer(case, candidate)
    if candidate.scorer == "dense_biencoder":
        if dense_encoder is None:
            fail("MISSING_MODEL", "Dense candidate was not given a prepared encoder")
        return DenseCaseScorer(case, dense_encoder)
    fail("UNSUPPORTED_SCORER", "Cannot prepare this scorer", scorer=candidate.scorer)
