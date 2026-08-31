from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    read_exact_bytes,
    resolve_repo_relative,
    sha256_bytes,
    write_json_identical_or_once,
    write_json_once,
    write_once,
)
from .errors import HarnessError, fail
from .metrics import aggregate_metrics, query_metrics
from .ranking import (
    QueryRanking,
    fuse_query_rankings,
    ranking_as_dict,
    ranking_from_dict,
)
from .schema import (
    CandidateSpec,
    ProtocolSpec,
    parse_protocol,
    parse_qrels,
    parse_ranking_input,
)
from .scoring import validate_model_artifacts

RESOURCE_LIMITS = {
    "cold_start_p95_seconds": 15.0,
    "warm_query_p95_seconds": 1.0,
    "max_corpus_build_seconds": 60.0,
    "peak_rss_bytes": 4 * 1024**3,
    "model_artifact_bytes": 256 * 1024**2,
    "environment_bytes": 3 * 1024**3,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile_95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _directory_size(root: Path) -> int:
    if not root.is_dir():
        fail("MISSING_ENVIRONMENT", "Isolated environment directory is missing")
    try:
        return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    except OSError as exc:
        fail(
            "ENVIRONMENT_MEASUREMENT_FAILED",
            "Could not measure the isolated environment",
            error=type(exc).__name__,
        )


def _installed_packages() -> list[dict[str, str]]:
    packages: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            packages[name.lower().replace("_", "-")] = distribution.version
    return [{"name": name, "version": packages[name]} for name in sorted(packages)]


def _total_memory_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.virtual_memory().total)
    except (ImportError, OSError, AttributeError):
        return None


def _collect_environment(
    repo_root: Path, protocol: ProtocolSpec, *, formal: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    if formal and Path(sys.prefix).resolve() == Path(sys.base_prefix).resolve():
        fail(
            "UNISOLATED_ENVIRONMENT",
            "Formal comparisons require a fresh isolated Python environment",
        )
    lock_sha256 = None
    lock_bytes = None
    if protocol.environment_lock_ref is not None:
        lock_path = resolve_repo_relative(
            repo_root,
            protocol.environment_lock_ref.path,
            label="environment lock",
        )
        lock_data = read_exact_bytes(
            lock_path,
            protocol.environment_lock_ref.sha256,
            label="environment lock",
        )
        lock_sha256 = sha256_bytes(lock_data)
        lock_bytes = len(lock_data)
    model_artifact_bytes = 0
    if protocol.dense_model is not None:
        artifact_dir = validate_model_artifacts(repo_root, protocol.dense_model)
        model_artifact_bytes = _directory_size(artifact_dir)
    environment_bytes = (
        _directory_size(Path(sys.prefix))
        if protocol.runtime.measure_resources
        else None
    )
    record = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": os.environ.get("PROCESSOR_IDENTIFIER")
        or platform.processor()
        or None,
        "logical_cpu_count": os.cpu_count(),
        "memory_bytes": _total_memory_bytes(),
        "runtime": {
            "device": protocol.runtime.device,
            "dtype": protocol.runtime.dtype,
            "thread_count": protocol.runtime.thread_count,
            "network_policy": "python_socket_deny",
            "hf_hub_offline": True,
            "transformers_offline": True,
        },
        "environment_lock_sha256": lock_sha256,
        "environment_lock_bytes": lock_bytes,
        "environment_bytes": environment_bytes,
        "model_artifact_bytes": model_artifact_bytes,
        "packages": _installed_packages(),
    }
    context = {
        "environment_lock_sha256": lock_sha256,
        "environment_bytes": environment_bytes,
        "model_artifact_bytes": model_artifact_bytes,
    }
    return record, context


def _apply_resource_gate(
    resources: dict[str, Any], *, measured: bool
) -> dict[str, Any]:
    if not measured:
        resources["gate_status"] = "not_measured"
        resources["gate_failures"] = []
        return resources
    missing = [key for key in RESOURCE_LIMITS if resources.get(key) is None]
    if missing:
        resources["gate_status"] = "incomplete"
        resources["gate_failures"] = [f"missing:{key}" for key in missing]
        return resources
    failures = [
        key for key, limit in RESOURCE_LIMITS.items() if float(resources[key]) > limit
    ]
    resources["gate_status"] = "fail" if failures else "pass"
    resources["gate_failures"] = failures
    return resources


def _git_metadata(repo_root: Path, *, formal: bool) -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        if formal:
            fail(
                "GIT_IDENTITY_UNAVAILABLE", "Formal comparison requires a Git worktree"
            )
        return {"commit": None, "clean": None}
    if formal and status:
        fail("DIRTY_WORKTREE", "Formal comparison requires a clean committed worktree")
    return {"commit": commit, "clean": not bool(status)}


def _load_protocol(
    repo_root: Path, protocol_path: str
) -> tuple[Path, bytes, ProtocolSpec]:
    path = resolve_repo_relative(repo_root, protocol_path, label="protocol path")
    if not path.is_file():
        fail("MISSING_PROTOCOL", "Protocol file does not exist")
    data = path.read_bytes()
    protocol = parse_protocol(parse_json_bytes(data, label="protocol"))
    current_python = platform.python_version()
    if (
        protocol.runtime.enforce_reference_runtime
        and current_python != protocol.runtime.required_python
    ):
        fail(
            "PYTHON_VERSION_MISMATCH",
            "Current Python does not match the frozen reference runtime",
            expected=protocol.runtime.required_python,
            actual=current_python,
        )
    return path, data, protocol


def _load_inputs(
    repo_root: Path, protocol: ProtocolSpec
) -> tuple[Any, Any, bytes, bytes | None]:
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
        fail("INPUT_IDENTITY_MISMATCH", "Protocol split does not match ranking input")
    qrels = None
    qrels_bytes = None
    if protocol.qrels_ref is not None:
        qrels_path = resolve_repo_relative(
            repo_root, protocol.qrels_ref.path, label="qrels"
        )
        qrels_bytes = read_exact_bytes(
            qrels_path, protocol.qrels_ref.sha256, label="qrels"
        )
        qrels = parse_qrels(parse_json_bytes(qrels_bytes, label="qrels"), ranking_input)
    return ranking_input, qrels, input_bytes, qrels_bytes


def _relative_protocol_path(repo_root: Path, protocol_path: Path) -> str:
    return protocol_path.resolve().relative_to(repo_root.resolve()).as_posix()


def _invoke_worker(
    repo_root: Path,
    protocol_path: Path,
    candidate_id: str,
    mode: str,
) -> tuple[dict[str, Any], str, float, list[str]]:
    command = [
        sys.executable,
        "-m",
        "prototypes.local_ranking.worker",
        "--protocol",
        _relative_protocol_path(repo_root, protocol_path),
        "--candidate",
        candidate_id,
        "--mode",
        mode,
    ]
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "LOCAL_RANKING_NETWORK_POLICY": "deny",
        }
    )
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - started
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = {
            "status": "failure",
            "error": {
                "code": "WORKER_PROTOCOL_ERROR",
                "message": "Worker did not return one JSON object",
            },
        }
    if completed.returncode != 0 and result.get("status") != "failure":
        result = {
            "status": "failure",
            "error": {
                "code": "WORKER_FAILED",
                "message": f"Worker exited with status {completed.returncode}",
            },
        }
    return result, completed.stderr, elapsed, command


def _worker_rankings(worker_result: dict[str, Any]) -> list[QueryRanking]:
    return [
        ranking_from_dict(item["ranking"], item["payload"])
        for item in worker_result.get("queries", [])
    ]


def _serialize_jsonl(values: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(value) for value in values)


def _compose_rrf_resources(
    fusion_resources: dict[str, Any],
    source_resources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sources = [source_resources[source_id] for source_id in sorted(source_resources)]
    cold_lists = [source.get("cold_start_seconds", []) for source in sources]
    cold_samples: list[float] = []
    if (
        cold_lists
        and all(cold_lists)
        and len({len(values) for values in cold_lists}) == 1
    ):
        cold_samples = [
            sum(float(values[index]) for values in cold_lists)
            for index in range(len(cold_lists[0]))
        ]
    warm_p50_values = [source.get("warm_query_p50_seconds") for source in sources]
    warm_p95_values = [source.get("warm_query_p95_seconds") for source in sources]
    build_values = [source.get("max_corpus_build_seconds") for source in sources]
    rss_values = [source.get("peak_rss_bytes") for source in sources]
    fusion_p50 = fusion_resources.get("warm_query_p50_seconds")
    fusion_p95 = fusion_resources.get("warm_query_p95_seconds")
    fusion_resources.update(
        {
            "measurement_mode": "conservative_source_composition",
            "cold_start_seconds": cold_samples,
            "cold_start_p95_seconds": _percentile_95(cold_samples),
            "corpus_build_seconds": {
                source_id: source_resources[source_id].get("max_corpus_build_seconds")
                for source_id in sorted(source_resources)
            },
            "max_corpus_build_seconds": (
                sum(float(value) for value in build_values)
                if build_values and all(value is not None for value in build_values)
                else None
            ),
            "warm_query_p50_seconds": (
                sum(float(value) for value in warm_p50_values) + float(fusion_p50)
                if fusion_p50 is not None
                and warm_p50_values
                and all(value is not None for value in warm_p50_values)
                else None
            ),
            "warm_query_p95_seconds": (
                sum(float(value) for value in warm_p95_values) + float(fusion_p95)
                if fusion_p95 is not None
                and warm_p95_values
                and all(value is not None for value in warm_p95_values)
                else None
            ),
            "peak_rss_bytes": (
                sum(int(value) for value in rss_values)
                if rss_values and all(value is not None for value in rss_values)
                else None
            ),
            "model_artifact_bytes": max(
                (int(source.get("model_artifact_bytes") or 0) for source in sources),
                default=0,
            ),
        }
    )
    return fusion_resources


def _write_candidate_success(
    run_root: Path,
    candidate: CandidateSpec,
    rankings: list[QueryRanking],
    worker_result: dict[str, Any],
    command: list[str],
    stderr: str,
    cold_samples: list[float],
    qrels: Any,
    started_at: str,
    resource_context: dict[str, Any],
    measured: bool,
    source_resources: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    per_query_metrics = (
        [query_metrics(ranking, qrels) for ranking in rankings] if qrels else []
    )
    aggregate = (
        aggregate_metrics(per_query_metrics)
        if qrels
        else {"query_count": len(rankings)}
    )
    warm_samples = [
        float(sample)
        for item in worker_result.get("queries", [])
        for sample in item.get("warm_latency_seconds", [])
    ]
    resource_metrics = {
        "cold_start_seconds": cold_samples,
        "cold_start_p95_seconds": _percentile_95(cold_samples),
        "corpus_build_seconds": worker_result.get("corpus_build_seconds", {}),
        "max_corpus_build_seconds": max(
            worker_result.get("corpus_build_seconds", {}).values(), default=None
        ),
        "warm_query_samples": len(warm_samples),
        "warm_query_p50_seconds": (
            sorted(warm_samples)[len(warm_samples) // 2] if warm_samples else None
        ),
        "warm_query_p95_seconds": _percentile_95(warm_samples),
        "peak_rss_bytes": worker_result.get("peak_rss_bytes"),
        "model_artifact_bytes": (
            resource_context["model_artifact_bytes"]
            if candidate.scorer == "dense_biencoder"
            else 0
        ),
        "environment_bytes": resource_context["environment_bytes"],
        "environment_lock_sha256": resource_context["environment_lock_sha256"],
        "measurement_mode": "direct_worker",
    }
    if source_resources is not None:
        resource_metrics = _compose_rrf_resources(resource_metrics, source_resources)
    resource_metrics = _apply_resource_gate(resource_metrics, measured=measured)
    command_record = {
        "candidate_id": candidate.candidate_id,
        "command": command,
        "started_at": started_at,
        "ended_at": _utc_now(),
        "environment": worker_result.get("environment", {}),
    }
    scores = [ranking_as_dict(ranking) for ranking in rankings]
    payloads = [
        {
            "case_id": ranking.case_id,
            "query_id": ranking.query_id,
            "payload": ranking.payload,
            "payload_sha256": ranking.payload_sha256,
        }
        for ranking in rankings
    ]
    metrics_record = {
        "candidate_id": candidate.candidate_id,
        "candidate": asdict(candidate),
        "per_query": per_query_metrics,
        "aggregate": aggregate,
        "resources": resource_metrics,
        "warnings": worker_result.get("warnings", []),
    }
    write_json_once(run_root / "command.json", command_record)
    write_once(run_root / "scores.jsonl", _serialize_jsonl(scores))
    write_once(run_root / "payloads.jsonl", _serialize_jsonl(payloads))
    write_json_once(run_root / "metrics.json", metrics_record)
    write_once(run_root / "stderr.log", stderr.encode("utf-8"))
    return {
        "candidate_id": candidate.candidate_id,
        "status": "success",
        "aggregate": aggregate,
        "resources": resource_metrics,
        "payload_hashes": {
            ranking.query_id: ranking.payload_sha256 for ranking in rankings
        },
    }


def _write_candidate_failure(
    run_root: Path,
    candidate: CandidateSpec,
    error: dict[str, Any],
    command: list[str],
    stderr: str,
    started_at: str,
) -> dict[str, Any]:
    write_json_once(
        run_root / "command.json",
        {
            "candidate_id": candidate.candidate_id,
            "command": command,
            "started_at": started_at,
            "ended_at": _utc_now(),
        },
    )
    write_json_once(
        run_root / "failure.json",
        {"candidate_id": candidate.candidate_id, "status": "failure", "error": error},
    )
    write_once(run_root / "stderr.log", stderr.encode("utf-8"))
    return {"candidate_id": candidate.candidate_id, "status": "failure", "error": error}


def _rrf_worker_result(
    candidate: CandidateSpec,
    rankings: list[QueryRanking],
    latency_samples: list[float],
) -> dict[str, Any]:
    per_query_samples = len(latency_samples) // max(1, len(rankings))
    queries: list[dict[str, Any]] = []
    for index, ranking in enumerate(rankings):
        start = index * per_query_samples
        end = start + per_query_samples
        queries.append(
            {
                "ranking": ranking_as_dict(ranking),
                "payload": ranking.payload,
                "warm_latency_seconds": latency_samples[start:end],
            }
        )
    return {
        "candidate_id": candidate.candidate_id,
        "status": "success",
        "queries": queries,
        "corpus_build_seconds": {},
        "peak_rss_bytes": None,
        "warnings": [
            "RRF resource gate uses a conservative sum of source metrics plus fusion"
        ],
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.system(),
            "machine": platform.machine(),
            "network_policy": "inherited_from_source_workers",
        },
    }


def run_protocol(repo_root: Path, protocol_path_value: str) -> tuple[int, Path]:
    protocol_path, protocol_bytes, protocol = _load_protocol(
        repo_root, protocol_path_value
    )
    formal = protocol.split in {"development", "holdout"}
    git_metadata = _git_metadata(repo_root, formal=formal)
    artifact_root = resolve_repo_relative(
        repo_root, protocol.artifact_root, label="artifact_root"
    )
    comparison_root = artifact_root / protocol.comparison_id
    attempt_root = comparison_root / "attempts" / protocol.attempt_id
    if attempt_root.exists():
        fail("ATTEMPT_EXISTS", "Prototype attempt is immutable and already exists")
    attempt_root.mkdir(parents=True, exist_ok=False)
    write_once(attempt_root / "protocol.json", protocol_bytes)
    try:
        environment_record, resource_context = _collect_environment(
            repo_root, protocol, formal=formal
        )
        environment_record_bytes = canonical_json_bytes(environment_record)
        write_once(attempt_root / "environment.json", environment_record_bytes)
        ranking_input, qrels, input_bytes, qrels_bytes = _load_inputs(
            repo_root, protocol
        )
        input_manifest = {
            "input_sha256": sha256_bytes(input_bytes),
            "qrels_sha256": (
                sha256_bytes(qrels_bytes) if qrels_bytes is not None else None
            ),
            "split": ranking_input.split,
            "case_count": len(ranking_input.cases),
            "query_count": len(ranking_input.queries),
            "paper_count": sum(len(case.papers) for case in ranking_input.cases),
            "segment_count": sum(
                len(paper.segments)
                for case in ranking_input.cases
                for paper in case.papers
            ),
        }
        write_json_identical_or_once(
            comparison_root / "inputs-manifest.json", input_manifest
        )
        summaries: list[dict[str, Any]] = []
        rankings_by_candidate: dict[str, dict[str, QueryRanking]] = {}
        resources_by_candidate: dict[str, dict[str, Any]] = {}
        for candidate in protocol.candidates:
            candidate_root = (
                comparison_root / "runs" / candidate.candidate_id / protocol.attempt_id
            )
            candidate_root.mkdir(parents=True, exist_ok=False)
            started_at = _utc_now()
            if candidate.scorer == "rrf":
                missing = [
                    source
                    for source in candidate.rrf_sources
                    if source not in rankings_by_candidate
                ]
                if missing:
                    summary = _write_candidate_failure(
                        candidate_root,
                        candidate,
                        {
                            "code": "RRF_SOURCE_FAILED",
                            "message": "One or more RRF source candidates did not succeed",
                            "details": {"missing": missing},
                        },
                        ["in-process", "rrf"],
                        "",
                        started_at,
                    )
                    summaries.append(summary)
                    continue
                fused: list[QueryRanking] = []
                latency_samples: list[float] = []
                query_lookup = {
                    query.query_id: (case, query)
                    for case in ranking_input.cases
                    for query in case.queries
                }
                for query_id in sorted(query_lookup):
                    case, _ = query_lookup[query_id]
                    source_rankings = tuple(
                        rankings_by_candidate[source][query_id]
                        for source in candidate.rrf_sources
                    )
                    ranking = fuse_query_rankings(
                        case=case, candidate=candidate, sources=source_rankings  # type: ignore[arg-type]
                    )
                    fused.append(ranking)
                    for _ in range(protocol.runtime.warm_repetitions):
                        started = time.perf_counter()
                        repeated = fuse_query_rankings(
                            case=case, candidate=candidate, sources=source_rankings  # type: ignore[arg-type]
                        )
                        latency_samples.append(time.perf_counter() - started)
                        if repeated.payload_sha256 != ranking.payload_sha256:
                            fail(
                                "NONDETERMINISTIC_RESULT",
                                "RRF payload changed during replay",
                            )
                worker_result = _rrf_worker_result(candidate, fused, latency_samples)
                summary = _write_candidate_success(
                    candidate_root,
                    candidate,
                    fused,
                    worker_result,
                    ["in-process", "rrf"],
                    "",
                    [],
                    qrels,
                    started_at,
                    resource_context,
                    protocol.runtime.measure_resources,
                    {
                        source: resources_by_candidate[source]
                        for source in candidate.rrf_sources
                    },
                )
                rankings_by_candidate[candidate.candidate_id] = {
                    ranking.query_id: ranking for ranking in fused
                }
                resources_by_candidate[candidate.candidate_id] = summary["resources"]
                summaries.append(summary)
                continue
            cold_samples: list[float] = []
            preflight_error: dict[str, Any] | None = None
            preflight_stderr: list[str] = []
            command: list[str] = []
            if protocol.runtime.measure_resources:
                for _ in range(protocol.runtime.cold_repetitions):
                    result, stderr, elapsed, command = _invoke_worker(
                        repo_root, protocol_path, candidate.candidate_id, "preflight"
                    )
                    preflight_stderr.append(stderr)
                    if result.get("status") != "success":
                        preflight_error = result.get(
                            "error",
                            {
                                "code": "PREFLIGHT_FAILED",
                                "message": "Candidate preflight failed",
                            },
                        )
                        break
                    cold_samples.append(elapsed)
            if preflight_error is not None:
                summary = _write_candidate_failure(
                    candidate_root,
                    candidate,
                    preflight_error,
                    command,
                    "".join(preflight_stderr),
                    started_at,
                )
                summaries.append(summary)
                continue
            result, stderr, _, command = _invoke_worker(
                repo_root, protocol_path, candidate.candidate_id, "score"
            )
            if result.get("status") != "success":
                summary = _write_candidate_failure(
                    candidate_root,
                    candidate,
                    result.get(
                        "error", {"code": "WORKER_FAILED", "message": "Worker failed"}
                    ),
                    command,
                    "".join(preflight_stderr) + stderr,
                    started_at,
                )
                summaries.append(summary)
                continue
            rankings = _worker_rankings(result)
            expected_queries = {query.query_id for _, query in ranking_input.queries}
            if {ranking.query_id for ranking in rankings} != expected_queries:
                fail("INCOMPLETE_RESULT", "Candidate did not return every frozen query")
            summary = _write_candidate_success(
                candidate_root,
                candidate,
                rankings,
                result,
                command,
                "".join(preflight_stderr) + stderr,
                cold_samples,
                qrels,
                started_at,
                resource_context,
                protocol.runtime.measure_resources,
            )
            rankings_by_candidate[candidate.candidate_id] = {
                ranking.query_id: ranking for ranking in rankings
            }
            resources_by_candidate[candidate.candidate_id] = summary["resources"]
            summaries.append(summary)
        comparison_summary = {
            "comparison_id": protocol.comparison_id,
            "attempt_id": protocol.attempt_id,
            "protocol_version": protocol.protocol_version,
            "protocol_sha256": sha256_bytes(protocol_bytes),
            "environment_sha256": sha256_bytes(environment_record_bytes),
            "git": git_metadata,
            "started_environment": {
                "python": platform.python_version(),
                "implementation": platform.python_implementation(),
                "system": platform.system(),
                "machine": platform.machine(),
            },
            "ended_at": _utc_now(),
            "candidate_results": summaries,
            "status": (
                "success"
                if summaries and all(item["status"] == "success" for item in summaries)
                else "incomplete"
            ),
            "winner": None,
            "decision_status": "not_run_by_harness",
        }
        write_json_once(attempt_root / "comparison-summary.json", comparison_summary)
        return (0 if comparison_summary["status"] == "success" else 2), attempt_root
    except HarnessError as exc:
        write_json_once(
            attempt_root / "failure.json",
            {"status": "failure", "error": exc.as_dict(), "ended_at": _utc_now()},
        )
        raise
    except Exception as exc:
        write_json_once(
            attempt_root / "failure.json",
            {
                "status": "failure",
                "error": {"code": "INTERNAL_ERROR", "message": str(exc)},
                "ended_at": _utc_now(),
            },
        )
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay a frozen local literature ranking comparison protocol"
    )
    parser.add_argument(
        "--protocol", required=True, help="Repository-relative frozen protocol JSON"
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        exit_code, attempt_root = run_protocol(Path.cwd().resolve(), arguments.protocol)
    except HarnessError as exc:
        print(json.dumps({"status": "failure", "error": exc.as_dict()}, sort_keys=True))
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI must return a typed terminal failure
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
    print(
        json.dumps(
            {
                "status": "success" if exit_code == 0 else "incomplete",
                "attempt_root": attempt_root.relative_to(Path.cwd()).as_posix(),
            },
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
