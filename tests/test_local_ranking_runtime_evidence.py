from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.network_guard import install_network_guard
from prototypes.local_ranking.run import _apply_resource_gate, _compose_rrf_resources
from prototypes.local_ranking.schema import parse_protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PROTOCOL = REPO_ROOT / "prototypes/local_ranking/fixtures/protocol.json"


def test_network_guard_denies_dns_and_connect_paths() -> None:
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    try:
        install_network_guard()
        with pytest.raises(HarnessError) as dns_error:
            socket.getaddrinfo("example.invalid", 443)
        assert dns_error.value.code == "NETWORK_ACCESS_DENIED"
        with pytest.raises(HarnessError) as connect_error:
            socket.create_connection(("127.0.0.1", 9))
        assert connect_error.value.code == "NETWORK_ACCESS_DENIED"
    finally:
        socket.socket = original_socket
        socket.create_connection = original_create_connection
        socket.getaddrinfo = original_getaddrinfo


def test_resource_gate_is_closed_and_fail_closed() -> None:
    passing = {
        "cold_start_p95_seconds": 15.0,
        "warm_query_p95_seconds": 1.0,
        "max_corpus_build_seconds": 60.0,
        "peak_rss_bytes": 4 * 1024**3,
        "model_artifact_bytes": 256 * 1024**2,
        "environment_bytes": 3 * 1024**3,
    }
    assert _apply_resource_gate(passing, measured=True)["gate_status"] == "pass"

    failing = {**passing, "warm_query_p95_seconds": 1.000001}
    result = _apply_resource_gate(failing, measured=True)
    assert result["gate_status"] == "fail"
    assert result["gate_failures"] == ["warm_query_p95_seconds"]

    incomplete = {**passing, "environment_bytes": None}
    result = _apply_resource_gate(incomplete, measured=True)
    assert result["gate_status"] == "incomplete"
    assert result["gate_failures"] == ["missing:environment_bytes"]


def test_rrf_resources_conservatively_include_both_sources() -> None:
    fusion = {
        "warm_query_p50_seconds": 0.01,
        "warm_query_p95_seconds": 0.02,
        "environment_bytes": 800,
    }
    sources = {
        "bm25": {
            "cold_start_seconds": [0.1, 0.2],
            "warm_query_p50_seconds": 0.03,
            "warm_query_p95_seconds": 0.04,
            "max_corpus_build_seconds": 0.05,
            "peak_rss_bytes": 10,
            "model_artifact_bytes": 0,
        },
        "dense": {
            "cold_start_seconds": [1.0, 2.0],
            "warm_query_p50_seconds": 0.3,
            "warm_query_p95_seconds": 0.4,
            "max_corpus_build_seconds": 0.5,
            "peak_rss_bytes": 100,
            "model_artifact_bytes": 500,
        },
    }

    result = _compose_rrf_resources(fusion, sources)

    assert result["measurement_mode"] == "conservative_source_composition"
    assert result["cold_start_seconds"] == pytest.approx([1.1, 2.2])
    assert result["warm_query_p95_seconds"] == pytest.approx(0.46)
    assert result["max_corpus_build_seconds"] == pytest.approx(0.55)
    assert result["peak_rss_bytes"] == 110
    assert result["model_artifact_bytes"] == 500


def test_formal_protocol_requires_hashed_environment_lock() -> None:
    protocol = json.loads(FIXTURE_PROTOCOL.read_text())
    protocol["split"] = "development"
    protocol["runtime"]["enforce_reference_runtime"] = True
    protocol["runtime"]["measure_resources"] = True

    with pytest.raises(HarnessError) as raised:
        parse_protocol(protocol)

    assert raised.value.code == "PROTOCOL_DEVIATION"
