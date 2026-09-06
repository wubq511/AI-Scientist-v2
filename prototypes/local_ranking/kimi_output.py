from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, write_json_once, write_once
from .errors import HarnessError, fail
from .schema import SAFE_ID_PATTERN

EXTRACTION_SCHEMA_VERSION = "local-ranking-kimi-response-extraction-v1.0"
KIMI_TEXT_RENDERER_PREFIX = "\u2022 "


def _read(path: Path, *, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        fail("MISSING_ARTIFACT", f"{label} is unreadable", error=str(exc))


def _read_text(path: Path, *, label: str) -> tuple[str, bytes]:
    data = _read(path, label=label)
    try:
        return data.decode("utf-8"), data
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", f"{label} is not UTF-8", offset=exc.start)


def _nonempty(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        fail("INVALID_INVOCATION", f"{label} must be a non-empty trimmed string")
    return value


def extract_response(
    *,
    raw_stdout_path: Path,
    raw_stderr_path: Path,
    prompt_path: Path,
    agent_file_path: Path,
    config_snapshot_path: Path,
    exit_code_path: Path,
    started_at_path: Path,
    finished_at_path: Path,
    output_root: Path,
    execution_id: str,
    cli_version: str,
    model_alias: str,
    provider: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    if not SAFE_ID_PATTERN.fullmatch(execution_id):
        fail("INVALID_INVOCATION", "execution_id must be a safe identifier")
    for value, label in (
        (cli_version, "cli_version"),
        (model_alias, "model_alias"),
        (provider, "provider"),
        (reasoning_effort, "reasoning_effort"),
    ):
        _nonempty(value, label=label)

    raw_stdout = _read(raw_stdout_path, label="raw stdout")
    raw_stderr = _read(raw_stderr_path, label="raw stderr")
    prompt = _read(prompt_path, label="prompt")
    agent_file = _read(agent_file_path, label="agent file")
    config_snapshot = _read(config_snapshot_path, label="config snapshot")
    exit_code_text, exit_code_bytes = _read_text(exit_code_path, label="exit code")
    started_at, started_at_bytes = _read_text(started_at_path, label="started_at")
    finished_at, finished_at_bytes = _read_text(finished_at_path, label="finished_at")
    if exit_code_text.strip() != "0":
        fail(
            "MODEL_INVOCATION_FAILED",
            "Kimi Code invocation did not exit successfully",
            exit_code=exit_code_text.strip(),
        )
    _nonempty(started_at.strip(), label="started_at")
    _nonempty(finished_at.strip(), label="finished_at")

    try:
        rendered = raw_stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", "raw stdout is not UTF-8", offset=exc.start)
    renderer_prefix_removed = rendered.startswith(KIMI_TEXT_RENDERER_PREFIX)
    if renderer_prefix_removed:
        rendered = rendered[len(KIMI_TEXT_RENDERER_PREFIX) :]
    try:
        response = json.loads(rendered)
    except json.JSONDecodeError as exc:
        fail(
            "INVALID_MODEL_RESPONSE",
            "Kimi response is not exactly one JSON value",
            line=exc.lineno,
            column=exc.colno,
        )
    if not isinstance(response, dict):
        fail("INVALID_MODEL_RESPONSE", "Kimi response must be a JSON object")
    response_bytes = canonical_json_bytes(response)

    inputs = {
        "agent_file.md": agent_file,
        "config-snapshot.json": config_snapshot,
        "exit-code.txt": exit_code_bytes,
        "finished-at.txt": finished_at_bytes,
        "prompt.txt": prompt,
        "raw-stderr.txt": raw_stderr,
        "raw-stdout.txt": raw_stdout,
        "started-at.txt": started_at_bytes,
    }
    receipt = {
        "execution": {
            "cli": {"name": "kimi-code", "version": cli_version},
            "execution_id": execution_id,
            "finished_at": finished_at.strip(),
            "fresh_session": True,
            "model_alias": model_alias,
            "provider": provider,
            "reasoning_effort": reasoning_effort,
            "started_at": started_at.strip(),
            "subagents": [],
            "tools": [],
        },
        "input_hashes": {
            name: sha256_bytes(data) for name, data in sorted(inputs.items())
        },
        "renderer": {
            "format": "kimi-code-text",
            "prefix_removed": renderer_prefix_removed,
            "removed_prefix": "U+2022 SPACE" if renderer_prefix_removed else None,
        },
        "response_json_sha256": sha256_bytes(response_bytes),
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "status": "pass",
    }
    for name, data in inputs.items():
        write_once(output_root / "raw" / name, data)
    write_once(output_root / "response.json", response_bytes)
    write_json_once(output_root / "receipt.json", receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract one immutable JSON response from Kimi Code text output"
    )
    parser.add_argument("--raw-stdout", type=Path, required=True)
    parser.add_argument("--raw-stderr", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--agent-file", type=Path, required=True)
    parser.add_argument("--config-snapshot", type=Path, required=True)
    parser.add_argument("--exit-code", type=Path, required=True)
    parser.add_argument("--started-at", type=Path, required=True)
    parser.add_argument("--finished-at", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--cli-version", required=True)
    parser.add_argument("--model-alias", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = extract_response(
            raw_stdout_path=args.raw_stdout,
            raw_stderr_path=args.raw_stderr,
            prompt_path=args.prompt,
            agent_file_path=args.agent_file,
            config_snapshot_path=args.config_snapshot,
            exit_code_path=args.exit_code,
            started_at_path=args.started_at,
            finished_at_path=args.finished_at,
            output_root=args.output_root,
            execution_id=args.execution_id,
            cli_version=args.cli_version,
            model_alias=args.model_alias,
            provider=args.provider,
            reasoning_effort=args.reasoning_effort,
        )
    except HarnessError as exc:
        print(json.dumps(exc.as_dict(), sort_keys=True))
        return 1
    print(json.dumps({"result": receipt, "status": "success"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
