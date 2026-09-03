from __future__ import annotations

import csv
import io
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes
from .corpus_approval import approve_corpus_bundle
from .corpus_build import build_corpus_bundle
from .corpus_validation import validate_corpus_bundle
from .errors import fail


def build_corpus(
    workspace_root: Path,
    *,
    case_id: str,
    target_paper_id: str,
    build_id: str,
    source_root: str = "data/raw",
    artifact_root: str = "artifacts/ideation-inputs",
    authority_path: str | Path | None = None,
    built_by: str = "codex",
) -> dict[str, Any]:
    return build_corpus_bundle(
        workspace_root,
        case_id=case_id,
        target_paper_id=target_paper_id,
        build_id=build_id,
        source_root=source_root,
        artifact_root=artifact_root,
        authority_path=authority_path,
        built_by=built_by,
    )


def validate_corpus(
    workspace_root: Path,
    *,
    bundle_path: str | Path,
) -> dict[str, Any]:
    return validate_corpus_bundle(
        workspace_root,
        bundle_path=bundle_path,
    )


def approve_corpus(
    workspace_root: Path,
    *,
    bundle_path: str | Path,
    approval_decision: str | Path,
) -> dict[str, Any]:
    return approve_corpus_bundle(
        workspace_root,
        bundle_path=bundle_path,
        approval_decision=approval_decision,
    )


def validate_all_corpora(
    workspace_root: Path,
    *,
    source_root: str = "data/raw",
    authority_path: str | Path | None = None,
) -> dict[str, Any]:
    source_dir = workspace_root / source_root
    target_file = source_dir / "target_papers.csv"
    if not target_file.is_file():
        fail("MISSING_SOURCE", f"target_papers.csv missing: {target_file}")
    target_data = target_file.read_bytes()
    try:
        target_text = target_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("INVALID_UTF8", "target_papers.csv not valid UTF-8", offset=exc.start)
    reader = csv.DictReader(io.StringIO(target_text, newline=""))
    target_ids = [row.get("paperId", "") for row in reader if row.get("paperId")]

    failures: list[dict[str, Any]] = []
    passed_count = 0

    with tempfile.TemporaryDirectory(dir=workspace_root) as tmp_dir:
        tmp_workspace = Path(tmp_dir)
        rel_artifact_root = tmp_workspace.relative_to(workspace_root).as_posix()
        for target_id in target_ids:
            opaque_case_id = f"case-{sha256_bytes(f'deterministic-validation-case-v1:{target_id}'.encode('utf-8'))[:32]}"
            try:
                build_res = build_corpus_bundle(
                    workspace_root,
                    case_id=opaque_case_id,
                    target_paper_id=target_id,
                    build_id="build-validation",
                    source_root=source_root,
                    artifact_root=rel_artifact_root,
                    authority_path=authority_path,
                )
                bundle_path = Path(build_res["bundle_path"])
                val_res = validate_corpus_bundle(
                    workspace_root, bundle_path=bundle_path
                )
                if val_res["status"] == "pass" and val_res["error_count"] == 0:
                    passed_count += 1
                else:
                    failures.append(
                        {
                            "case_id": opaque_case_id,
                            "errors": val_res.get("errors", []),
                            "target_paper_id": target_id,
                        }
                    )
            except Exception as exc:
                failures.append(
                    {
                        "case_id": opaque_case_id,
                        "errors": [str(exc)],
                        "target_paper_id": target_id,
                    }
                )

    return {
        "failed_targets": len(failures),
        "failures": failures,
        "passed_targets": passed_count,
        "status": "pass" if len(failures) == 0 else "fail",
        "total_targets": len(target_ids),
    }
