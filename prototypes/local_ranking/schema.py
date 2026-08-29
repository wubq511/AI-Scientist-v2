from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from . import INPUT_SCHEMA_VERSION, PROTOCOL_SCHEMA_VERSION, QRELS_SCHEMA_VERSION
from .errors import fail
from .normalization import NORMALIZATION_VERSION, tokenize_text

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
CONTENT_TYPES = {"publisher_abstract", "official_full_text"}
LEXICAL_SCORERS = {"idf_coverage", "tfidf_cosine", "bm25", "dph"}
AGGREGATIONS = {"max", "mean_top_2", "sum_all"}


def _object(value: Any, *, label: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("INVALID_SCHEMA", f"{label} must be an object")
    unknown = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    if unknown or missing:
        fail(
            "INVALID_SCHEMA",
            f"{label} has an invalid closed schema",
            unknown=unknown,
            missing=missing,
        )
    return value


def _string(value: Any, *, label: str, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        fail("INVALID_SCHEMA", f"{label} must be a non-empty string")
    return value


def _safe_id(value: Any, *, label: str) -> str:
    text = _string(value, label=label)
    if not SAFE_ID_PATTERN.fullmatch(text):
        fail("INVALID_SCHEMA", f"{label} is not a safe opaque identifier", value=text)
    return text


def _sha256(value: Any, *, label: str) -> str:
    text = _string(value, label=label)
    if not SHA256_PATTERN.fullmatch(text):
        fail("INVALID_SCHEMA", f"{label} must be a lowercase SHA-256 hex digest")
    return text


def _int(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        fail("INVALID_SCHEMA", f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, *, label: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail("INVALID_SCHEMA", f"{label} must be a number")
    number = float(value)
    if minimum is not None and number < minimum:
        fail("INVALID_SCHEMA", f"{label} must be >= {minimum}")
    return number


def _bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        fail("INVALID_SCHEMA", f"{label} must be boolean")
    return value


def _sorted_unique(values: Iterable[str], *, label: str) -> tuple[str, ...]:
    result = tuple(values)
    if tuple(sorted(result)) != result or len(set(result)) != len(result):
        fail("NON_CANONICAL_INPUT", f"{label} must be sorted and unique")
    return result


@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: str
    content_type: str
    text: str
    content_item_order: int
    source_start: int


@dataclass(frozen=True, slots=True)
class Paper:
    paper_id: str
    title: str
    segments: tuple[Segment, ...]


@dataclass(frozen=True, slots=True)
class Query:
    query_id: str
    kind: str
    text: str


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    corpus_sha256: str
    queries: tuple[Query, ...]
    papers: tuple[Paper, ...]


@dataclass(frozen=True, slots=True)
class RankingInput:
    split: str
    cases: tuple[Case, ...]

    @property
    def queries(self) -> tuple[tuple[Case, Query], ...]:
        return tuple((case, query) for case in self.cases for query in case.queries)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class OutputBudget:
    paper_cap: int
    segments_per_paper: int
    total_segment_cap: int


@dataclass(frozen=True, slots=True)
class CandidateSpec:
    candidate_id: str
    scorer: str
    parameters: dict[str, float]
    title_weight: float
    aggregation: str
    phrase_bonus: bool
    output_budget: OutputBudget
    rrf_sources: tuple[str, ...]
    rrf_k: int | None


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    required_python: str
    enforce_reference_runtime: bool
    device: str
    dtype: str
    thread_count: int
    warm_repetitions: int
    cold_repetitions: int
    measure_resources: bool


@dataclass(frozen=True, slots=True)
class DenseModelSpec:
    model_id: str
    revision: str
    artifact_dir: str
    artifact_manifest: ArtifactRef
    weight_sha256: str
    weight_bytes: int
    query_prefix: str
    passage_prefix: str
    max_length: int
    embedding_dimension: int
    torch_version: str
    transformers_version: str


@dataclass(frozen=True, slots=True)
class ProtocolSpec:
    protocol_version: str
    comparison_id: str
    attempt_id: str
    split: str
    artifact_root: str
    input_ref: ArtifactRef
    qrels_ref: ArtifactRef | None
    evaluation_mode: str
    runtime: RuntimeSpec
    dense_model: DenseModelSpec | None
    candidates: tuple[CandidateSpec, ...]


@dataclass(frozen=True, slots=True)
class Qrels:
    split: str
    paper_grades: dict[tuple[str, str], int]
    segment_grades: dict[tuple[str, str], int]
    no_supporting_segment: frozenset[tuple[str, str]]


def parse_ranking_input(value: Any) -> RankingInput:
    root = _object(value, label="input", keys={"schema_version", "split", "cases"})
    if root["schema_version"] != INPUT_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Unsupported ranking input schema")
    split = _string(root["split"], label="input.split")
    if split not in {"fixture", "development", "holdout"}:
        fail("INVALID_SCHEMA", "input.split is invalid", value=split)
    if not isinstance(root["cases"], list) or not root["cases"]:
        fail("INVALID_SCHEMA", "input.cases must be a non-empty array")
    cases: list[Case] = []
    for case_index, raw_case in enumerate(root["cases"]):
        case_obj = _object(
            raw_case,
            label=f"cases[{case_index}]",
            keys={"case_id", "corpus_sha256", "queries", "papers"},
        )
        case_id = _safe_id(case_obj["case_id"], label=f"cases[{case_index}].case_id")
        corpus_sha256 = _sha256(
            case_obj["corpus_sha256"], label=f"cases[{case_index}].corpus_sha256"
        )
        raw_queries = case_obj["queries"]
        raw_papers = case_obj["papers"]
        if not isinstance(raw_queries, list) or not raw_queries:
            fail("INVALID_SCHEMA", f"{case_id}.queries must be a non-empty array")
        if not isinstance(raw_papers, list) or not raw_papers:
            fail("INVALID_SCHEMA", f"{case_id}.papers must be a non-empty array")
        if split != "fixture" and not 3 <= len(raw_papers) <= 36:
            fail("INVALID_SCHEMA", f"{case_id} must contain 3-36 papers")
        if split != "fixture" and len(raw_queries) != 2:
            fail("INVALID_SCHEMA", f"{case_id} must contain exactly two frozen queries")
        queries: list[Query] = []
        for query_index, raw_query in enumerate(raw_queries):
            query_obj = _object(
                raw_query,
                label=f"{case_id}.queries[{query_index}]",
                keys={"query_id", "kind", "text"},
            )
            query_id = _safe_id(
                query_obj["query_id"],
                label=f"{case_id}.queries[{query_index}].query_id",
            )
            kind = _string(query_obj["kind"], label=f"{query_id}.kind")
            if kind not in {"broad", "focused", "diagnostic"}:
                fail("INVALID_SCHEMA", f"{query_id}.kind is invalid")
            text = _string(query_obj["text"], label=f"{query_id}.text")
            queries.append(Query(query_id=query_id, kind=kind, text=text))
        _sorted_unique(
            (query.query_id for query in queries), label=f"{case_id}.query_ids"
        )
        papers: list[Paper] = []
        for paper_index, raw_paper in enumerate(raw_papers):
            paper_obj = _object(
                raw_paper,
                label=f"{case_id}.papers[{paper_index}]",
                keys={"paper_id", "title", "segments"},
            )
            paper_id = _safe_id(
                paper_obj["paper_id"], label=f"{case_id}.papers[{paper_index}].paper_id"
            )
            title = _string(paper_obj["title"], label=f"{paper_id}.title")
            if not tokenize_text(title, label=f"{paper_id}.title"):
                fail("INVALID_CORPUS", f"{paper_id}.title has no searchable tokens")
            raw_segments = paper_obj["segments"]
            if not isinstance(raw_segments, list) or not raw_segments:
                fail("INVALID_CORPUS", f"{paper_id}.segments must be non-empty")
            segments: list[Segment] = []
            for segment_index, raw_segment in enumerate(raw_segments):
                segment_obj = _object(
                    raw_segment,
                    label=f"{paper_id}.segments[{segment_index}]",
                    keys={
                        "segment_id",
                        "content_type",
                        "text",
                        "content_item_order",
                        "source_start",
                    },
                )
                segment_id = _safe_id(
                    segment_obj["segment_id"],
                    label=f"{paper_id}.segments[{segment_index}].segment_id",
                )
                content_type = _string(
                    segment_obj["content_type"], label=f"{segment_id}.content_type"
                )
                if content_type not in CONTENT_TYPES:
                    fail(
                        "BOUNDARY_VIOLATION",
                        f"{segment_id} has an ineligible content type",
                    )
                text = _string(segment_obj["text"], label=f"{segment_id}.text")
                if not tokenize_text(text, label=f"{segment_id}.text"):
                    fail(
                        "INVALID_CORPUS", f"{segment_id}.text has no searchable tokens"
                    )
                segments.append(
                    Segment(
                        segment_id=segment_id,
                        content_type=content_type,
                        text=text,
                        content_item_order=_int(
                            segment_obj["content_item_order"],
                            label=f"{segment_id}.content_item_order",
                        ),
                        source_start=_int(
                            segment_obj["source_start"],
                            label=f"{segment_id}.source_start",
                        ),
                    )
                )
            segment_order = tuple(
                (segment.content_item_order, segment.source_start, segment.segment_id)
                for segment in segments
            )
            if tuple(sorted(segment_order)) != segment_order or len(
                {segment.segment_id for segment in segments}
            ) != len(segments):
                fail(
                    "NON_CANONICAL_INPUT",
                    f"{paper_id}.segments must be canonically ordered with unique IDs",
                )
            papers.append(
                Paper(paper_id=paper_id, title=title, segments=tuple(segments))
            )
        _sorted_unique(
            (paper.paper_id for paper in papers), label=f"{case_id}.paper_ids"
        )
        case_segment_ids = [
            segment.segment_id for paper in papers for segment in paper.segments
        ]
        if len(case_segment_ids) != len(set(case_segment_ids)):
            fail(
                "INVALID_SCHEMA",
                f"{case_id} segment_id values must be unique within the case",
            )
        cases.append(
            Case(
                case_id=case_id,
                corpus_sha256=corpus_sha256,
                queries=tuple(queries),
                papers=tuple(papers),
            )
        )
    _sorted_unique((case.case_id for case in cases), label="input.case_ids")
    query_ids = [query.query_id for case in cases for query in case.queries]
    if len(query_ids) != len(set(query_ids)):
        fail("INVALID_SCHEMA", "query_id must be globally unique")
    if split != "fixture" and len(cases) != 6:
        fail("INVALID_SCHEMA", f"{split} split must contain exactly six cases")
    return RankingInput(split=split, cases=tuple(cases))


def _parse_artifact_ref(value: Any, *, label: str) -> ArtifactRef:
    obj = _object(value, label=label, keys={"path", "sha256"})
    return ArtifactRef(
        path=_string(obj["path"], label=f"{label}.path"),
        sha256=_sha256(obj["sha256"], label=f"{label}.sha256"),
    )


def _parse_budget(value: Any, *, label: str) -> OutputBudget:
    obj = _object(
        value,
        label=label,
        keys={"paper_cap", "segments_per_paper", "total_segment_cap"},
    )
    paper_cap = _int(obj["paper_cap"], label=f"{label}.paper_cap", minimum=1)
    segments_per_paper = _int(
        obj["segments_per_paper"], label=f"{label}.segments_per_paper", minimum=1
    )
    total_segment_cap = _int(
        obj["total_segment_cap"], label=f"{label}.total_segment_cap", minimum=1
    )
    if paper_cap not in {3, 5} or segments_per_paper not in {1, 2}:
        fail("PROTOCOL_DEVIATION", f"{label} is outside the approved v1 grid")
    if total_segment_cap != 6:
        fail("PROTOCOL_DEVIATION", f"{label}.total_segment_cap must equal 6")
    return OutputBudget(paper_cap, segments_per_paper, total_segment_cap)


def parse_protocol(value: Any) -> ProtocolSpec:
    root = _object(
        value,
        label="protocol",
        keys={
            "schema_version",
            "protocol_version",
            "comparison_id",
            "attempt_id",
            "split",
            "artifact_root",
            "input",
            "qrels",
            "evaluation_mode",
            "runtime",
            "normalization_version",
            "dense_model",
            "candidates",
        },
    )
    if root["schema_version"] != PROTOCOL_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Unsupported protocol schema")
    if root["protocol_version"] != "1.0.0":
        fail(
            "UNSUPPORTED_PROTOCOL", "Only approved protocol version 1.0.0 is supported"
        )
    if root["normalization_version"] != NORMALIZATION_VERSION:
        fail("PROTOCOL_DEVIATION", "Unsupported normalization version")
    split = _string(root["split"], label="protocol.split")
    if split not in {"fixture", "development", "holdout"}:
        fail("INVALID_SCHEMA", "protocol.split is invalid")
    evaluation_mode = _string(root["evaluation_mode"], label="protocol.evaluation_mode")
    if evaluation_mode not in {"scoring_only", "with_qrels"}:
        fail("INVALID_SCHEMA", "protocol.evaluation_mode is invalid")
    input_ref = _parse_artifact_ref(root["input"], label="protocol.input")
    qrels_ref = None
    if root["qrels"] is not None:
        qrels_ref = _parse_artifact_ref(root["qrels"], label="protocol.qrels")
    if evaluation_mode == "with_qrels" and qrels_ref is None:
        fail("INVALID_SCHEMA", "with_qrels mode requires a frozen qrels artifact")
    if evaluation_mode == "scoring_only" and qrels_ref is not None:
        fail("INVALID_SCHEMA", "scoring_only mode must not expose qrels")
    runtime_obj = _object(
        root["runtime"],
        label="protocol.runtime",
        keys={
            "required_python",
            "enforce_reference_runtime",
            "device",
            "dtype",
            "thread_count",
            "warm_repetitions",
            "cold_repetitions",
            "measure_resources",
        },
    )
    runtime = RuntimeSpec(
        required_python=_string(
            runtime_obj["required_python"], label="runtime.required_python"
        ),
        enforce_reference_runtime=_bool(
            runtime_obj["enforce_reference_runtime"],
            label="runtime.enforce_reference_runtime",
        ),
        device=_string(runtime_obj["device"], label="runtime.device"),
        dtype=_string(runtime_obj["dtype"], label="runtime.dtype"),
        thread_count=_int(
            runtime_obj["thread_count"], label="runtime.thread_count", minimum=1
        ),
        warm_repetitions=_int(
            runtime_obj["warm_repetitions"], label="runtime.warm_repetitions", minimum=1
        ),
        cold_repetitions=_int(
            runtime_obj["cold_repetitions"], label="runtime.cold_repetitions", minimum=1
        ),
        measure_resources=_bool(
            runtime_obj["measure_resources"], label="runtime.measure_resources"
        ),
    )
    if runtime.device != "cpu" or runtime.dtype != "float32":
        fail("PROTOCOL_DEVIATION", "Full relevance comparison must use CPU FP32")
    if split != "fixture" and not runtime.enforce_reference_runtime:
        fail("PROTOCOL_DEVIATION", "Formal splits must enforce the reference runtime")
    if split != "fixture" and runtime.required_python != "3.13.7":
        fail("PROTOCOL_DEVIATION", "Formal splits must use Python 3.13.7")
    if split != "fixture" and not runtime.measure_resources:
        fail("PROTOCOL_DEVIATION", "Formal splits must measure runtime resources")
    if runtime.warm_repetitions != 30 or runtime.cold_repetitions != 5:
        fail("PROTOCOL_DEVIATION", "Runtime repetition counts differ from v1")
    dense_model = None
    if root["dense_model"] is not None:
        dense_obj = _object(
            root["dense_model"],
            label="protocol.dense_model",
            keys={
                "model_id",
                "revision",
                "artifact_dir",
                "artifact_manifest",
                "weight_sha256",
                "weight_bytes",
                "query_prefix",
                "passage_prefix",
                "max_length",
                "embedding_dimension",
                "torch_version",
                "transformers_version",
            },
        )
        dense_model = DenseModelSpec(
            model_id=_string(dense_obj["model_id"], label="dense_model.model_id"),
            revision=_string(dense_obj["revision"], label="dense_model.revision"),
            artifact_dir=_string(
                dense_obj["artifact_dir"], label="dense_model.artifact_dir"
            ),
            artifact_manifest=_parse_artifact_ref(
                dense_obj["artifact_manifest"], label="dense_model.artifact_manifest"
            ),
            weight_sha256=_sha256(
                dense_obj["weight_sha256"], label="dense_model.weight_sha256"
            ),
            weight_bytes=_int(
                dense_obj["weight_bytes"], label="dense_model.weight_bytes", minimum=1
            ),
            query_prefix=_string(
                dense_obj["query_prefix"], label="dense_model.query_prefix"
            ),
            passage_prefix=_string(
                dense_obj["passage_prefix"], label="dense_model.passage_prefix"
            ),
            max_length=_int(
                dense_obj["max_length"], label="dense_model.max_length", minimum=1
            ),
            embedding_dimension=_int(
                dense_obj["embedding_dimension"],
                label="dense_model.embedding_dimension",
                minimum=1,
            ),
            torch_version=_string(
                dense_obj["torch_version"], label="dense_model.torch_version"
            ),
            transformers_version=_string(
                dense_obj["transformers_version"],
                label="dense_model.transformers_version",
            ),
        )
        expected_dense = {
            "model_id": "intfloat/e5-small-v2",
            "revision": "ffb93f3bd4047442299a41ebb6fa998a38507c52",
            "weight_sha256": "45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1",
            "weight_bytes": 133466304,
            "query_prefix": "query: ",
            "passage_prefix": "passage: ",
            "max_length": 512,
            "embedding_dimension": 384,
            "torch_version": "2.13.0",
            "transformers_version": "5.16.1",
        }
        for field, expected in expected_dense.items():
            if getattr(dense_model, field) != expected:
                fail(
                    "PROTOCOL_DEVIATION",
                    f"dense_model.{field} differs from approved v1",
                )
    raw_candidates = root["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        fail("INVALID_SCHEMA", "protocol.candidates must be a non-empty array")
    candidates: list[CandidateSpec] = []
    for index, raw_candidate in enumerate(raw_candidates):
        candidate_obj = _object(
            raw_candidate,
            label=f"candidates[{index}]",
            keys={
                "candidate_id",
                "scorer",
                "parameters",
                "title_weight",
                "aggregation",
                "phrase_bonus",
                "output_budget",
                "rrf_sources",
                "rrf_k",
            },
        )
        candidate_id = _safe_id(
            candidate_obj["candidate_id"], label=f"candidates[{index}].candidate_id"
        )
        scorer = _string(candidate_obj["scorer"], label=f"{candidate_id}.scorer")
        if scorer not in LEXICAL_SCORERS | {"dense_biencoder", "rrf"}:
            fail("INVALID_SCHEMA", f"{candidate_id}.scorer is unsupported")
        parameters_obj = candidate_obj["parameters"]
        if not isinstance(parameters_obj, dict) or any(
            not isinstance(key, str) for key in parameters_obj
        ):
            fail("INVALID_SCHEMA", f"{candidate_id}.parameters must be an object")
        parameters = {
            key: _number(number, label=f"{candidate_id}.parameters.{key}")
            for key, number in parameters_obj.items()
        }
        expected_parameter_keys = {"bm25": {"k1", "b"}}.get(scorer, set())
        if set(parameters) != expected_parameter_keys:
            fail(
                "INVALID_SCHEMA",
                f"{candidate_id}.parameters has invalid keys for {scorer}",
            )
        if scorer == "bm25" and (
            parameters["k1"] not in {0.8, 1.2, 1.6}
            or parameters["b"] not in {0.0, 0.5, 0.75}
        ):
            fail(
                "PROTOCOL_DEVIATION",
                f"{candidate_id} BM25 parameters are outside v1 grid",
            )
        title_weight = _number(
            candidate_obj["title_weight"], label=f"{candidate_id}.title_weight"
        )
        if title_weight not in {0.0, 1.0, 2.0}:
            fail(
                "PROTOCOL_DEVIATION", f"{candidate_id}.title_weight is outside v1 grid"
            )
        aggregation = _string(
            candidate_obj["aggregation"], label=f"{candidate_id}.aggregation"
        )
        if aggregation not in AGGREGATIONS:
            fail("INVALID_SCHEMA", f"{candidate_id}.aggregation is unsupported")
        phrase_bonus = _bool(
            candidate_obj["phrase_bonus"], label=f"{candidate_id}.phrase_bonus"
        )
        raw_sources = candidate_obj["rrf_sources"]
        if not isinstance(raw_sources, list) or any(
            not isinstance(item, str) for item in raw_sources
        ):
            fail(
                "INVALID_SCHEMA", f"{candidate_id}.rrf_sources must be an array of IDs"
            )
        rrf_sources = tuple(raw_sources)
        rrf_k = candidate_obj["rrf_k"]
        if scorer == "rrf":
            if len(rrf_sources) != 2 or len(set(rrf_sources)) != 2:
                fail(
                    "INVALID_SCHEMA",
                    f"{candidate_id} must fuse exactly two distinct sources",
                )
            rrf_k = _int(rrf_k, label=f"{candidate_id}.rrf_k", minimum=1)
            if rrf_k not in {10, 60}:
                fail("PROTOCOL_DEVIATION", f"{candidate_id}.rrf_k is outside v1 grid")
            if parameters or title_weight != 0 or aggregation != "max" or phrase_bonus:
                fail(
                    "INVALID_SCHEMA", f"{candidate_id} contains irrelevant RRF settings"
                )
        elif rrf_sources or rrf_k is not None:
            fail("INVALID_SCHEMA", f"{candidate_id} has RRF settings but is not RRF")
        if scorer == "dense_biencoder" and dense_model is None:
            fail("INVALID_SCHEMA", f"{candidate_id} requires protocol.dense_model")
        if phrase_bonus and scorer not in LEXICAL_SCORERS:
            fail("PROTOCOL_DEVIATION", "Phrase bonus is lexical-only")
        if aggregation == "sum_all" and scorer not in LEXICAL_SCORERS:
            fail("PROTOCOL_DEVIATION", "sum_all is a lexical negative control only")
        candidates.append(
            CandidateSpec(
                candidate_id=candidate_id,
                scorer=scorer,
                parameters=parameters,
                title_weight=title_weight,
                aggregation=aggregation,
                phrase_bonus=phrase_bonus,
                output_budget=_parse_budget(
                    candidate_obj["output_budget"],
                    label=f"{candidate_id}.output_budget",
                ),
                rrf_sources=rrf_sources,
                rrf_k=rrf_k,
            )
        )
    ids = [candidate.candidate_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        fail("INVALID_SCHEMA", "candidate_id must be unique")
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.scorer == "rrf" and not set(candidate.rrf_sources) <= seen:
            fail(
                "INVALID_SCHEMA",
                f"{candidate.candidate_id} RRF sources must appear earlier",
            )
        seen.add(candidate.candidate_id)
    if root["artifact_root"] != "artifacts/local-ranking-prototype":
        fail(
            "PROTOCOL_DEVIATION",
            "artifact_root must use the approved private prototype root",
        )
    return ProtocolSpec(
        protocol_version=_string(
            root["protocol_version"], label="protocol.protocol_version"
        ),
        comparison_id=_safe_id(root["comparison_id"], label="protocol.comparison_id"),
        attempt_id=_safe_id(root["attempt_id"], label="protocol.attempt_id"),
        split=split,
        artifact_root=root["artifact_root"],
        input_ref=input_ref,
        qrels_ref=qrels_ref,
        evaluation_mode=evaluation_mode,
        runtime=runtime,
        dense_model=dense_model,
        candidates=tuple(candidates),
    )


def parse_qrels(value: Any, ranking_input: RankingInput) -> Qrels:
    root = _object(
        value,
        label="qrels",
        keys={
            "schema_version",
            "split",
            "paper_judgments",
            "segment_judgments",
            "issues",
        },
    )
    if root["schema_version"] != QRELS_SCHEMA_VERSION:
        fail("UNSUPPORTED_SCHEMA", "Unsupported qrels schema")
    split = _string(root["split"], label="qrels.split")
    if split != ranking_input.split:
        fail("INPUT_IDENTITY_MISMATCH", "qrels split does not match ranking input")
    query_to_case = {
        query.query_id: case for case in ranking_input.cases for query in case.queries
    }
    paper_grades: dict[tuple[str, str], int] = {}
    paper_order: list[tuple[str, str]] = []
    if not isinstance(root["paper_judgments"], list):
        fail("INVALID_SCHEMA", "qrels.paper_judgments must be an array")
    for index, raw in enumerate(root["paper_judgments"]):
        obj = _object(
            raw,
            label=f"paper_judgments[{index}]",
            keys={"query_id", "paper_id", "grade"},
        )
        query_id = _safe_id(obj["query_id"], label=f"paper_judgments[{index}].query_id")
        paper_id = _safe_id(obj["paper_id"], label=f"paper_judgments[{index}].paper_id")
        grade = _int(obj["grade"], label=f"paper_judgments[{index}].grade")
        if grade > 3:
            fail("INVALID_QRELS", "paper grade must be in 0-3")
        key = (query_id, paper_id)
        if key in paper_grades:
            fail("INVALID_QRELS", "duplicate paper judgment", key=key)
        paper_order.append(key)
        paper_grades[key] = grade
    if paper_order != sorted(paper_order):
        fail("NON_CANONICAL_INPUT", "paper judgments must be sorted")
    expected_papers = {
        (query.query_id, paper.paper_id)
        for case in ranking_input.cases
        for query in case.queries
        for paper in case.papers
    }
    if set(paper_grades) != expected_papers:
        fail(
            "INCOMPLETE_QRELS",
            "paper judgments must cover every query-paper pair in the same case",
            missing=len(expected_papers - set(paper_grades)),
            extra=len(set(paper_grades) - expected_papers),
        )
    segment_grades: dict[tuple[str, str], int] = {}
    segment_order: list[tuple[str, str]] = []
    if not isinstance(root["segment_judgments"], list):
        fail("INVALID_SCHEMA", "qrels.segment_judgments must be an array")
    segment_to_paper_by_case = {
        case.case_id: {
            segment.segment_id: paper.paper_id
            for paper in case.papers
            for segment in paper.segments
        }
        for case in ranking_input.cases
    }
    for index, raw in enumerate(root["segment_judgments"]):
        obj = _object(
            raw,
            label=f"segment_judgments[{index}]",
            keys={"query_id", "segment_id", "grade"},
        )
        query_id = _safe_id(
            obj["query_id"], label=f"segment_judgments[{index}].query_id"
        )
        segment_id = _safe_id(
            obj["segment_id"], label=f"segment_judgments[{index}].segment_id"
        )
        grade = _int(obj["grade"], label=f"segment_judgments[{index}].grade")
        if grade > 2:
            fail("INVALID_QRELS", "segment grade must be in 0-2")
        key = (query_id, segment_id)
        if key in segment_grades:
            fail("INVALID_QRELS", "duplicate segment judgment", key=key)
        case = query_to_case.get(query_id)
        paper_id = (
            segment_to_paper_by_case[case.case_id].get(segment_id)
            if case is not None
            else None
        )
        if case is None or paper_id is None:
            fail("INVALID_QRELS", "segment judgment crosses case boundary", key=key)
        if paper_grades[(query_id, paper_id)] < 2:
            fail(
                "INVALID_QRELS",
                "grade 0/1 papers must not add segment judgments",
                key=key,
            )
        segment_order.append(key)
        segment_grades[key] = grade
    if segment_order != sorted(segment_order):
        fail("NON_CANONICAL_INPUT", "segment judgments must be sorted")
    no_supporting: set[tuple[str, str]] = set()
    issue_order: list[tuple[str, str]] = []
    if not isinstance(root["issues"], list):
        fail("INVALID_SCHEMA", "qrels.issues must be an array")
    for index, raw in enumerate(root["issues"]):
        obj = _object(
            raw,
            label=f"issues[{index}]",
            keys={"query_id", "paper_id", "code"},
        )
        if obj["code"] != "no_supporting_segment":
            fail("INVALID_QRELS", "unsupported qrels issue code")
        key = (
            _safe_id(obj["query_id"], label=f"issues[{index}].query_id"),
            _safe_id(obj["paper_id"], label=f"issues[{index}].paper_id"),
        )
        if key in no_supporting or key not in paper_grades or paper_grades[key] < 2:
            fail("INVALID_QRELS", "invalid no_supporting_segment issue", key=key)
        issue_order.append(key)
        no_supporting.add(key)
    if issue_order != sorted(issue_order):
        fail("NON_CANONICAL_INPUT", "qrels issues must be sorted")
    for case in ranking_input.cases:
        for query in case.queries:
            for paper in case.papers:
                key = (query.query_id, paper.paper_id)
                if paper_grades[key] < 2:
                    continue
                expected_segments = {
                    (query.query_id, segment.segment_id) for segment in paper.segments
                }
                actual_segments = expected_segments & set(segment_grades)
                if actual_segments != expected_segments:
                    fail(
                        "INCOMPLETE_QRELS",
                        "grade >=2 papers require judgments for every eligible segment",
                        query_id=query.query_id,
                        paper_id=paper.paper_id,
                    )
                has_direct = any(
                    segment_grades[item] == 2 for item in expected_segments
                )
                if has_direct == (key in no_supporting):
                    fail(
                        "INVALID_QRELS",
                        "grade >=2 paper needs a direct segment or exactly one data issue",
                        query_id=query.query_id,
                        paper_id=paper.paper_id,
                    )
    return Qrels(
        split=split,
        paper_grades=paper_grades,
        segment_grades=segment_grades,
        no_supporting_segment=frozenset(no_supporting),
    )
