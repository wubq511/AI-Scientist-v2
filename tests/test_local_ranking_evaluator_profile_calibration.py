import json
from copy import deepcopy
from pathlib import Path

import pytest

from prototypes.local_ranking.canonical import canonical_json_bytes, sha256_bytes
from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.evaluator_profile_calibration import aggregate
from prototypes.local_ranking.operational_judge import TRACE_SCHEMA_VERSION


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    return path


def _evaluator() -> dict[str, str]:
    return {
        "harness": "opencode-go-chat-completions",
        "model_alias": "opencode-go/deepseek-v4-flash",
        "provider": "opencode-go",
        "reasoning_effort": "high",
    }


def _trace(*, orientation: int, unstable: int = 0) -> dict:
    judgments = []
    for index in range(24):
        winner = "left"
        if orientation == 2:
            winner = "left" if index < unstable else "right"
        judgments.append({"item_id": f"item-{index:02d}", "winner": winner})
    return {
        "bundle_sha256": str(orientation) * 64,
        "draft_sha256": "d" * 64,
        "evaluator": _evaluator(),
        "judgments": judgments,
        "orientation": orientation,
        "schema_version": TRACE_SCHEMA_VERSION,
        "status": "pass",
    }


def _write_trace(root: Path, trace: dict) -> Path:
    trace_path = _write(root / "trace.json", trace)
    _write(
        root / "result.json",
        {
            "bundle_sha256": trace["bundle_sha256"],
            "draft_sha256": trace["draft_sha256"],
            "judgment_count": 24,
            "schema_version": TRACE_SCHEMA_VERSION,
            "status": "pass",
            "trace_sha256": sha256_bytes(trace_path.read_bytes()),
        },
    )
    return trace_path


def _receipt(*, response_id: str, orientation: int) -> dict:
    return {
        "endpoint": "https://opencode.ai/zen/go/v1/chat/completions",
        "files": {},
        "http_status": 200,
        "identity": {
            "cost": "0",
            "created": 1,
            "model": "deepseek-v4-flash",
            "provider_response_id": response_id,
        },
        "manifest_sha256": "a" * 64,
        "provider": "opencode-go",
        "request_sha256": str(orientation) * 64,
        "schema_version": "local-ranking-opencode-go-chat-receipt-v1.0",
        "status": "pass",
        "transport_qualification": {
            "json_object_accepted": True,
            "reasoning_effort_requested": "high",
            "reasoning_execution_proven": False,
        },
        "usage": {
            "completion_tokens": 1,
            "prompt_tokens": 1,
            "total_tokens": 2,
        },
    }


def _replicates(tmp_path: Path, unstable_counts: tuple[int, int, int]) -> list[dict]:
    replicates = []
    for replicate_index, unstable in enumerate(unstable_counts, start=1):
        root = tmp_path / f"r{replicate_index}"
        replicates.append(
            {
                "orientation_1_receipt": _write(
                    root / "o1-receipt.json",
                    _receipt(response_id=f"r{replicate_index}-o1", orientation=1),
                ),
                "orientation_1_trace": _write_trace(root / "o1", _trace(orientation=1)),
                "orientation_2_receipt": _write(
                    root / "o2-receipt.json",
                    _receipt(response_id=f"r{replicate_index}-o2", orientation=2),
                ),
                "orientation_2_trace": _write_trace(
                    root / "o2",
                    _trace(orientation=2, unstable=unstable),
                ),
                "replicate_id": f"r{replicate_index}",
            }
        )
    return replicates


def test_profile_passes_one_22_and_two_24_replicates(tmp_path) -> None:
    result = aggregate(
        model="deepseek-v4-flash",
        reasoning_effort="high",
        replicates=_replicates(tmp_path, (2, 0, 0)),
        output_path=tmp_path / "result.json",
    )

    assert result["status"] == "pass"
    assert result["decision"] == "profile_qualified"
    assert result["pooled_stable_count"] == 70
    assert result["pairs_at_original_gate"] == 2
    assert all(result["gates"].values())


@pytest.mark.parametrize("unstable_counts", [(2, 1, 1), (3, 0, 0)])
def test_profile_fails_pooled_or_per_pair_gate(
    tmp_path, unstable_counts: tuple[int, int, int]
) -> None:
    result = aggregate(
        model="deepseek-v4-flash",
        reasoning_effort="high",
        replicates=_replicates(tmp_path, unstable_counts),
        output_path=tmp_path / "result.json",
    )

    assert result["status"] == "fail"
    assert result["decision"] == "escalate_profile"


def test_profile_rejects_duplicate_provider_response(tmp_path) -> None:
    replicates = _replicates(tmp_path, (0, 0, 0))
    duplicate = deepcopy(json.loads(replicates[0]["orientation_1_receipt"].read_text()))
    _write(replicates[2]["orientation_2_receipt"], duplicate)

    with pytest.raises(HarnessError) as raised:
        aggregate(
            model="deepseek-v4-flash",
            reasoning_effort="high",
            replicates=replicates,
            output_path=tmp_path / "result.json",
        )

    assert raised.value.code == "DUPLICATE_PROVIDER_RESPONSE"
