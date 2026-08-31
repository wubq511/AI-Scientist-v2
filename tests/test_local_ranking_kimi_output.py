from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.kimi_output import extract_response


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _fixture(tmp_path: Path) -> dict[str, Path]:
    values = {
        "raw_stdout": tmp_path / "execution/stdout.txt",
        "raw_stderr": tmp_path / "execution/stderr.txt",
        "prompt": tmp_path / "prompt.txt",
        "agent_file": tmp_path / "agent.md",
        "config_snapshot": tmp_path / "config.json",
        "exit_code": tmp_path / "execution/exit-code.txt",
        "started_at": tmp_path / "execution/started-at.txt",
        "finished_at": tmp_path / "execution/finished-at.txt",
        "output_root": tmp_path / "extracted",
    }
    _write(values["raw_stdout"], '\u2022 {"answer":1}\n'.encode())
    _write(values["raw_stderr"], b"private reasoning\n")
    _write(values["prompt"], b"embedded bundle\n")
    _write(values["agent_file"], b"---\ntools: []\nsubagents: []\n---\n")
    _write(values["config_snapshot"], b'{"secrets":"excluded"}\n')
    _write(values["exit_code"], b"0\n")
    _write(values["started_at"], b"2026-08-31T15:00:00Z\n")
    _write(values["finished_at"], b"2026-08-31T15:01:00Z\n")
    return values


def _extract(paths: dict[str, Path]) -> dict[str, object]:
    return extract_response(
        raw_stdout_path=paths["raw_stdout"],
        raw_stderr_path=paths["raw_stderr"],
        prompt_path=paths["prompt"],
        agent_file_path=paths["agent_file"],
        config_snapshot_path=paths["config_snapshot"],
        exit_code_path=paths["exit_code"],
        started_at_path=paths["started_at"],
        finished_at_path=paths["finished_at"],
        output_root=paths["output_root"],
        execution_id="judge-kimi-orientation-1-001",
        cli_version="0.39.1",
        model_alias="kimi-code/k3",
        provider="managed:kimi-code",
        reasoning_effort="high",
    )


def test_extract_response_preserves_raw_and_writes_canonical_json(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    receipt = _extract(paths)

    assert receipt["renderer"]["prefix_removed"] is True
    assert (paths["output_root"] / "response.json").read_bytes() == (
        canonical_json_bytes({"answer": 1})
    )
    assert receipt["input_hashes"]["raw-stdout.txt"] == sha256_bytes(
        paths["raw_stdout"].read_bytes()
    )
    assert (paths["output_root"] / "raw/raw-stdout.txt").read_bytes() == (
        paths["raw_stdout"].read_bytes()
    )


def test_extract_response_rejects_unknown_wrapper(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _write(paths["raw_stdout"], b'Answer: {"answer":1}\n')

    with pytest.raises(HarnessError, match="not exactly one JSON value"):
        _extract(paths)


def test_extract_response_rejects_nonzero_exit(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _write(paths["exit_code"], b"1\n")

    with pytest.raises(HarnessError, match="did not exit successfully"):
        _extract(paths)


def test_extract_response_never_overwrites(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _extract(paths)

    with pytest.raises(HarnessError, match="ARTIFACT_EXISTS"):
        _extract(paths)
