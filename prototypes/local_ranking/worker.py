from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .canonical import parse_json_bytes, read_exact_bytes, resolve_repo_relative
from .errors import HarnessError, fail
from .network_guard import install_network_guard
from .normalization import normalize_query
from .ranking import QueryRanking, rank_scored_query, ranking_as_dict
from .schema import CandidateSpec, parse_protocol, parse_ranking_input
from .scoring import DenseEncoder, prepare_case_scorer


def _peak_rss_bytes() -> tuple[int | None, list[str]]:
    try:
        import psutil

        return psutil.Process().memory_info().rss, []
    except (ImportError, OSError, AttributeError):
        try:
            import resource

            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return int(value), [
                    "psutil unavailable; peak RSS uses macOS resource.ru_maxrss"
                ]
            return int(value * 1024), [
                "psutil unavailable; peak RSS uses resource.ru_maxrss"
            ]
        except (ImportError, OSError, AttributeError):
            return None, ["peak RSS unavailable"]


def _load(repo_root: Path, protocol_path: str) -> tuple[Any, Any, bytes]:
    resolved_protocol = resolve_repo_relative(
        repo_root, protocol_path, label="protocol path"
    )
    protocol_bytes = resolved_protocol.read_bytes()
    protocol = parse_protocol(parse_json_bytes(protocol_bytes, label="protocol"))
    input_path = resolve_repo_relative(
        repo_root, protocol.input_ref.path, label="ranking input"
    )
    input_bytes = read_exact_bytes(
        input_path, protocol.input_ref.sha256, label="ranking input"
    )
    ranking_input = parse_ranking_input(
        parse_json_bytes(input_bytes, label="ranking input")
    )
    if ranking_input.split != protocol.split:
        fail("INPUT_IDENTITY_MISMATCH", "Protocol and ranking input split differ")
    return protocol, ranking_input, protocol_bytes


def _candidate(protocol: Any, candidate_id: str) -> CandidateSpec:
    for candidate in protocol.candidates:
        if candidate.candidate_id == candidate_id:
            if candidate.scorer == "rrf":
                fail(
                    "INVALID_WORKER_REQUEST", "RRF is computed only by the orchestrator"
                )
            return candidate
    fail(
        "UNKNOWN_CANDIDATE",
        "Candidate is not declared in protocol",
        candidate_id=candidate_id,
    )


def execute_worker(
    repo_root: Path, protocol_path: str, candidate_id: str, mode: str
) -> dict[str, Any]:
    protocol, ranking_input, _ = _load(repo_root, protocol_path)
    network_policy = os.environ.get("LOCAL_RANKING_NETWORK_POLICY")
    if protocol.runtime.measure_resources:
        if network_policy != "deny":
            fail(
                "NETWORK_POLICY_MISSING",
                "Measured workers require the local network-denial guard",
            )
        install_network_guard()
    candidate = _candidate(protocol, candidate_id)
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    build_started = time.perf_counter()
    dense_encoder = (
        DenseEncoder(repo_root, protocol)
        if candidate.scorer == "dense_biencoder"
        else None
    )
    prepared: dict[str, Any] = {}
    build_by_case: dict[str, float] = {}
    for case in ranking_input.cases:
        case_started = time.perf_counter()
        prepared[case.case_id] = prepare_case_scorer(
            repo_root, protocol, case, candidate, dense_encoder
        )
        build_by_case[case.case_id] = time.perf_counter() - case_started
    total_build = time.perf_counter() - build_started
    total_corpus_build = sum(build_by_case.values())
    peak_rss, warnings = _peak_rss_bytes()
    if mode == "preflight":
        return {
            "candidate_id": candidate_id,
            "mode": mode,
            "status": "success",
            "corpus_build_seconds": build_by_case,
            "total_corpus_build_seconds": total_corpus_build,
            "total_build_seconds": total_build,
            "peak_rss_bytes": peak_rss,
            "warnings": warnings,
            "environment": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "system": platform.system(),
                "machine": platform.machine(),
                "network_policy": network_policy or "not_enforced",
            },
        }
    results: list[dict[str, Any]] = []
    for case in ranking_input.cases:
        scorer = prepared[case.case_id]
        segment_tokens, title_tokens = scorer.unit_tokens()
        for query in case.queries:
            normalized = normalize_query(query.text)

            def rank_once(
                scorer: Any = scorer,
                query: Any = query,
                case: Any = case,
                normalized: Any = normalized,
                segment_tokens: Any = segment_tokens,
                title_tokens: Any = title_tokens,
            ) -> QueryRanking:
                query_tokens, segment_scores, title_scores = scorer.score(query.text)
                return rank_scored_query(
                    case=case,
                    query_id=query.query_id,
                    normalized_query=normalized.normalized,
                    query_tokens=query_tokens,
                    candidate=candidate,
                    segment_scores=segment_scores,
                    title_scores=title_scores,
                    segment_tokens=segment_tokens,
                    title_tokens=title_tokens,
                )

            ranking = rank_once()
            latency_samples: list[float] = []
            for _ in range(protocol.runtime.warm_repetitions):
                started = time.perf_counter()
                repeated = rank_once()
                latency_samples.append(time.perf_counter() - started)
                if repeated.payload_sha256 != ranking.payload_sha256:
                    fail(
                        "NONDETERMINISTIC_RESULT",
                        "Repeated warm query changed the canonical payload",
                        query_id=query.query_id,
                    )
            results.append(
                {
                    "ranking": ranking_as_dict(ranking),
                    "payload": ranking.payload,
                    "warm_latency_seconds": latency_samples,
                }
            )
    peak_rss_after, rss_warnings = _peak_rss_bytes()
    warnings.extend(item for item in rss_warnings if item not in warnings)
    if peak_rss is None:
        peak_rss = peak_rss_after
    elif peak_rss_after is not None:
        peak_rss = max(peak_rss, peak_rss_after)
    return {
        "candidate_id": candidate_id,
        "mode": mode,
        "status": "success",
        "corpus_build_seconds": build_by_case,
        "total_corpus_build_seconds": total_corpus_build,
        "total_build_seconds": total_build,
        "peak_rss_bytes": peak_rss,
        "warnings": warnings,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "machine": platform.machine(),
            "network_policy": network_policy or "not_enforced",
        },
        "queries": results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Internal local-ranking candidate worker"
    )
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--mode", choices=("preflight", "score"), required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        result = execute_worker(
            Path.cwd().resolve(),
            arguments.protocol,
            arguments.candidate,
            arguments.mode,
        )
    except HarnessError as exc:
        print(json.dumps({"status": "failure", "error": exc.as_dict()}, sort_keys=True))
        return 2
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc(file=sys.stderr)
        print(
            json.dumps(
                {
                    "status": "failure",
                    "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
                },
                sort_keys=True,
            )
        )
        return 3
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
