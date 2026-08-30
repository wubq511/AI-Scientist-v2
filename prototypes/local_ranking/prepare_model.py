from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO

from .canonical import canonical_json_bytes, resolve_repo_relative, sha256_bytes
from .errors import HarnessError, fail

MODEL_ID = "intfloat/e5-small-v2"
MODEL_REVISION = "ffb93f3bd4047442299a41ebb6fa998a38507c52"
MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)
WEIGHT_BYTES = 133_466_304
WEIGHT_SHA256 = "45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1"
MAX_MODEL_BYTES = 256 * 1024 * 1024


def _download_url(filename: str) -> str:
    return (
        f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{filename}"
        "?download=true"
    )


def _stream_download(response: BinaryIO, destination: Path) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError:
        fail("ARTIFACT_EXISTS", "Model preparation never overwrites files")
    size = 0
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "wb") as handle:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_MODEL_BYTES:
                fail("MODEL_TOO_LARGE", "One model artifact exceeded the v1 cap")
            digest.update(chunk)
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    return size, digest.hexdigest()


def prepare_model(
    repo_root: Path, artifact_dir_value: str, manifest_path_value: str
) -> dict[str, object]:
    artifact_dir = resolve_repo_relative(
        repo_root, artifact_dir_value, label="model artifact_dir"
    )
    manifest_path = resolve_repo_relative(
        repo_root, manifest_path_value, label="model manifest"
    )
    if artifact_dir.exists() or manifest_path.exists():
        fail(
            "ARTIFACT_EXISTS",
            "Model preparation uses immutable, previously unused output paths",
        )
    if manifest_path.parent == artifact_dir:
        fail(
            "INVALID_PATH",
            "Model manifest must be outside the allowlisted file directory",
        )
    artifact_dir.mkdir(parents=True, exist_ok=False)

    entries: list[dict[str, object]] = []
    total_bytes = 0
    for filename in MODEL_FILES:
        request = urllib.request.Request(
            _download_url(filename),
            headers={"User-Agent": "AI-Scientist-v2-local-ranking-prototype/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                size, digest = _stream_download(response, artifact_dir / filename)
        except (OSError, urllib.error.URLError) as exc:
            fail(
                "MODEL_DOWNLOAD_FAILED",
                "Pinned model artifact download failed",
                file=filename,
                error=type(exc).__name__,
            )
        total_bytes += size
        entries.append({"path": filename, "bytes": size, "sha256": digest})

    if total_bytes > MAX_MODEL_BYTES:
        fail("MODEL_TOO_LARGE", "Pinned model artifacts exceed the v1 model cap")
    weight = next(item for item in entries if item["path"] == "model.safetensors")
    if weight["bytes"] != WEIGHT_BYTES or weight["sha256"] != WEIGHT_SHA256:
        fail("MODEL_HASH_MISMATCH", "Downloaded dense weight differs from the protocol")

    manifest = {"files": entries}
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(manifest_path, flags, 0o600)
    except FileExistsError:
        fail("ARTIFACT_EXISTS", "Model manifest already exists")
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(manifest_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "artifact_dir": artifact_dir_value,
        "manifest_path": manifest_path_value,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "file_count": len(entries),
        "total_bytes": total_bytes,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download the pinned E5 files for the local-ranking prototype"
    )
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--manifest", required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        result = prepare_model(
            Path.cwd().resolve(), arguments.artifact_dir, arguments.manifest
        )
    except HarnessError as exc:
        print(json.dumps({"status": "failure", "error": exc.as_dict()}, sort_keys=True))
        return 2
    except Exception as exc:  # noqa: BLE001 - normalize unexpected preparation failures
        print(
            json.dumps(
                {
                    "status": "failure",
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": str(exc),
                    },
                },
                sort_keys=True,
            )
        )
        return 3
    print(json.dumps({"status": "success", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
