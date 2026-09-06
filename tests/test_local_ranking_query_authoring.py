from __future__ import annotations

import json
from pathlib import Path

import pytest

from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.query_authoring import finalize_query_draft


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _draft() -> dict[str, object]:
    return {
        "cases": [
            {
                "case_id": f"lr-op-{number:02d}",
                "queries": [
                    {
                        "authoring_basis": "Workshop concepts only.",
                        "kind": kind,
                        "text": (
                            f"Evidence about operational topic {number} for a {kind} need"
                        ),
                    }
                    for kind in ("broad", "focused")
                ],
            }
            for number in range(1, 13)
        ],
        "schema_version": "local-ranking-operational-query-draft-v1.0",
    }


def _inputs(tmp_path: Path) -> dict[str, Path]:
    protocol = tmp_path / "protocol.md"
    prompt = tmp_path / "prompt.txt"
    agent = tmp_path / "agent.md"
    raw_response = tmp_path / "stdout.txt"
    raw_stderr = tmp_path / "stderr.txt"
    packet = tmp_path / "packet.json"
    approval = tmp_path / "approval.json"
    prompt_manifest = tmp_path / "prompt-manifest.json"
    output = tmp_path / "query-manifest.json"
    _write(protocol, b"approved protocol\n")
    _write(prompt, b"embedded Workshops\n")
    _write(agent, b"---\ntools: []\nsubagents: []\n---\n")
    _write(raw_stderr, b"private reasoning log\n")
    _write(
        raw_response,
        "\u2022 ".encode() + json.dumps(_draft()).encode() + b"\n",
    )
    packet_value = {
        "case_count": 12,
        "workshops": [
            {
                "case_id": f"lr-op-{number:02d}",
                "path": f"workshops/lr-op-{number:02d}.md",
                "sha256": f"{number:064x}",
            }
            for number in range(1, 13)
        ],
    }
    packet_bytes = canonical_json_bytes(packet_value)
    _write(packet, packet_bytes)
    approval_value = {
        "approval_id": "operational-input-approval-001",
        "approval_status": "approved",
        "artifacts": {"query-author-packet/manifest.json": sha256_bytes(packet_bytes)},
        "protocol": {
            "path": "docs/prototypes/protocol.md",
            "sha256": sha256_bytes(protocol.read_bytes()),
            "version": "v1.4",
        },
    }
    _write(approval, canonical_json_bytes(approval_value))
    prompt_manifest_value = {
        "case_count": 12,
        "prompt_bytes": len(prompt.read_bytes()),
        "prompt_sha256": sha256_bytes(prompt.read_bytes()),
        "protocol_sha256": sha256_bytes(protocol.read_bytes()),
        "query_author_packet_manifest_sha256": sha256_bytes(packet_bytes),
        "schema_version": "local-ranking-operational-query-author-prompt-v1.0",
        "status": "ready_for_fresh_isolated_author",
    }
    _write(prompt_manifest, canonical_json_bytes(prompt_manifest_value))
    return {
        "agent": agent,
        "approval": approval,
        "output": output,
        "packet": packet,
        "prompt": prompt,
        "prompt_manifest": prompt_manifest,
        "protocol": protocol,
        "raw_response": raw_response,
        "raw_stderr": raw_stderr,
    }


def _finalize(paths: dict[str, Path]) -> dict[str, object]:
    return finalize_query_draft(
        raw_response_path=paths["raw_response"],
        raw_stderr_path=paths["raw_stderr"],
        prompt_path=paths["prompt"],
        prompt_manifest_path=paths["prompt_manifest"],
        agent_file_path=paths["agent"],
        packet_manifest_path=paths["packet"],
        input_approval_path=paths["approval"],
        protocol_path=paths["protocol"],
        output_path=paths["output"],
        manifest_id="operational-query-manifest-001",
        execution_id="k2-7-001",
        created_at="2026-08-31T15:00:00Z",
        cli_version="0.39.1",
        model_alias="kimi-code/kimi-for-coding",
        model_name="K2.7 Coding",
        provider="managed:kimi-code",
        reasoning_mode="always-thinking-provider-managed",
    )


def test_finalize_query_draft_binds_raw_isolated_execution(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)

    manifest = _finalize(paths)

    assert manifest["case_count"] == 12
    assert manifest["query_count"] == 24
    assert manifest["author"]["renderer_prefix_removed"] is True
    assert manifest["author"]["isolation"]["tools"] == []
    assert manifest["source_binding"]["protocol_version"] == "v1.4"
    assert paths["output"].read_bytes() == canonical_json_bytes(manifest)


def test_finalize_query_draft_rejects_unknown_renderer_text(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    raw = paths["raw_response"].read_text()
    paths["raw_response"].write_text("Answer: " + raw, encoding="utf-8")

    with pytest.raises(HarnessError, match="not one JSON object"):
        _finalize(paths)


def test_finalize_query_draft_rejects_extra_model_field(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    draft = _draft()
    draft["commentary"] = "looks good"
    _write(
        paths["raw_response"],
        "\u2022 ".encode() + json.dumps(draft).encode() + b"\n",
    )

    with pytest.raises(HarnessError, match="invalid closed schema"):
        _finalize(paths)


def test_finalize_query_draft_rejects_changed_prompt(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    paths["prompt"].write_text("changed prompt\n", encoding="utf-8")

    with pytest.raises(HarnessError, match="exact inputs"):
        _finalize(paths)


def test_finalize_query_draft_never_overwrites(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    _finalize(paths)

    with pytest.raises(HarnessError, match="ARTIFACT_EXISTS"):
        _finalize(paths)
