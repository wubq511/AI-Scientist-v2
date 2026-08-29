from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.worker import execute_worker

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "prototypes/local_ranking/fixtures"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_workspace(tmp_path: Path) -> Path:
    fixture_dir = tmp_path / "prototypes/local_ranking/fixtures"
    fixture_dir.mkdir(parents=True)
    for name in ("input.json", "qrels.json"):
        (fixture_dir / name).write_bytes((FIXTURES / name).read_bytes())
    protocol = json.loads((FIXTURES / "protocol.json").read_text())
    protocol["input"]["sha256"] = _sha256(fixture_dir / "input.json")
    protocol["qrels"]["sha256"] = _sha256(fixture_dir / "qrels.json")
    protocol_path = fixture_dir / "protocol.json"
    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n")
    return protocol_path


def test_one_command_replay_writes_isolated_evidence(tmp_path: Path) -> None:
    protocol_path = _prepare_workspace(tmp_path)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO_ROOT)
    command = [
        sys.executable,
        "-m",
        "prototypes.local_ranking.run",
        "--protocol",
        protocol_path.relative_to(tmp_path).as_posix(),
    ]

    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    response = json.loads(completed.stdout)
    assert response["status"] == "success"
    attempt_root = tmp_path / response["attempt_root"]
    summary = json.loads((attempt_root / "comparison-summary.json").read_text())
    assert summary["winner"] is None
    assert summary["status"] == "success"
    assert [item["candidate_id"] for item in summary["candidate_results"]] == [
        "idf-v1",
        "tfidf-v1",
        "bm25-v1",
        "dph-v1",
        "rrf-v1",
    ]
    for candidate_id in ("idf-v1", "tfidf-v1", "bm25-v1", "dph-v1", "rrf-v1"):
        run_root = (
            tmp_path
            / "artifacts/local-ranking-prototype/diagnostic-v1/runs"
            / candidate_id
            / "fixture-001"
        )
        assert (run_root / "scores.jsonl").is_file()
        assert (run_root / "payloads.jsonl").is_file()
        assert (run_root / "metrics.json").is_file()

    repeated = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert repeated.returncode == 2
    assert json.loads(repeated.stdout)["error"]["code"] == "ATTEMPT_EXISTS"


def test_dense_candidate_fails_before_network_or_import_when_model_is_missing(
    tmp_path: Path,
) -> None:
    protocol_path = _prepare_workspace(tmp_path)
    protocol = json.loads(protocol_path.read_text())
    protocol["dense_model"] = {
        "artifact_dir": "artifacts/local-ranking-prototype/model-cache/e5-small-v2",
        "artifact_manifest": {
            "path": "artifacts/local-ranking-prototype/model-cache/e5-manifest.json",
            "sha256": "b" * 64,
        },
        "embedding_dimension": 384,
        "max_length": 512,
        "model_id": "intfloat/e5-small-v2",
        "passage_prefix": "passage: ",
        "query_prefix": "query: ",
        "revision": "ffb93f3bd4047442299a41ebb6fa998a38507c52",
        "torch_version": "2.13.0",
        "transformers_version": "5.16.1",
        "weight_bytes": 133466304,
        "weight_sha256": "45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1",
    }
    protocol["candidates"] = [
        {
            "aggregation": "max",
            "candidate_id": "dense-v1",
            "output_budget": {
                "paper_cap": 3,
                "segments_per_paper": 1,
                "total_segment_cap": 6,
            },
            "parameters": {},
            "phrase_bonus": False,
            "rrf_k": None,
            "rrf_sources": [],
            "scorer": "dense_biencoder",
            "title_weight": 0,
        }
    ]
    protocol_path.write_text(json.dumps(protocol, indent=2) + "\n")

    with pytest.raises(HarnessError) as raised:
        execute_worker(
            tmp_path,
            protocol_path.relative_to(tmp_path).as_posix(),
            "dense-v1",
            "preflight",
        )

    assert raised.value.code == "MISSING_MODEL"
