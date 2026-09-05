"""Shared Prompt Profile lifecycle fixtures for the ideation CLI seam.

Reuses the established workspace/approval/stub helpers from
tests/test_suspend_resume.py via importlib (tests/ is not a package) and
exposes one module-level adapter that switches the profile under test.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from ai_scientist.ideation.admission import NewRunRequest
from ai_scientist.ideation.canonical import canonical_json_bytes
from ai_scientist.ideation.controller import IdeationController
from ai_scientist.ideation.deepseek import (
    DeepSeekAdapter,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.ideation.profiles import (
    CROSS_DOMAIN_V1,
    ML_BASELINE_V1,
)
from ai_scientist.ideation.resume import resume_run
from ai_scientist.ideation.run_store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_helper_module():
    path = REPO_ROOT / "tests" / "test_suspend_resume.py"
    spec = importlib.util.spec_from_file_location(
        "_prompt_profile_suspend_resume_helpers", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def helpers() -> Any:
    return _load_helper_module()


class _CapturingStubTransport(StubTransport):
    """Alias of StubTransport for the lifecycle tests.

    StubTransport.send already records every canonical request payload into
    `sent_requests`; no extra behavior is needed. Kept as a named alias so
    the lifecycle tests read as "capturing" without duplicating transport
    logic.
    """


CaptureTransport = _CapturingStubTransport


def _response_bytes(content: str, response_id: str) -> bytes:
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {
                    "content": content,
                    "reasoning_content": "Detailed reasoning about the proposal...",
                    "role": "assistant",
                },
            }
        ],
        "created": 1725360000,
        "id": response_id,
        "model": "deepseek-v4-pro",
        "object": "chat.completion",
        "system_fingerprint": "fp_profiles",
        "usage": {
            "completion_tokens": 120,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "prompt_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 80},
            "total_tokens": 220,
        },
    }
    return canonical_json_bytes(body)


def _stub(content: str, response_id: str) -> TransportResponse:
    return TransportResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body=_response_bytes(content, response_id),
        duration_ms=30.0,
    )


SEARCH_CONTENT = (
    'ACTION: SearchLiterature\nARGUMENTS: {"query": "clinical forecasting"}'
)
SEARCH_RESPONSE_ID = "chatcmpl-profile-search"
FINALIZE_RESPONSE_ID = "chatcmpl-profile-finalize"
IDEA_NAME = "adaptive_temporal_cueing"


def idea_payload() -> dict[str, Any]:
    return {
        "Name": IDEA_NAME,
        "Title": "Adaptive Temporal Cueing for Migraine Forecasting",
        "Short Hypothesis": "Continuous passive symptom tracking with adaptive temporal cueing improves early warning accuracy for migraine attacks.",
        "Related Work": "Existing forecasting approaches rely on static clinical records; this proposal introduces adaptive temporal cueing from passive sensing streams.",
        "Abstract": "Migraine forecasting remains challenging due to symptom variability. We propose an adaptive temporal cueing framework that learns individualized warning windows from passive telemetry.",
        "Experiments": [
            "Benchmark adaptive cueing against static baseline predictors on multi-center clinical cohorts.",
            "Ablation study on temporal cueing window lengths and passive sensor feature subsets.",
        ],
        "Risk Factors and Limitations": [
            "Sensitivity to intermittent missing sensor telemetry.",
            "Variation in patient symptom reporting consistency.",
        ],
    }


def _search_stub() -> TransportResponse:
    return _stub(SEARCH_CONTENT, SEARCH_RESPONSE_ID)


def _finalize_content() -> str:
    return (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(idea_payload())}, '
        f'"grounding": ["__PAPER_ID__"]}}'
    )


def make_request(helpers_module: Any, inputs: dict[str, str], profile_id: str):
    return NewRunRequest(
        case_id=helpers_module.CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=2,
        prompt_profile_id=profile_id,
    )


def admit(
    helpers_module: Any,
    workspace: Path,
    inputs: dict[str, str],
    monkeypatch: Any,
    profile_id: str,
) -> str:
    helpers_module._approve_cost(monkeypatch)
    result = helpers_module.run_new_run(
        workspace,
        make_request(helpers_module, inputs, profile_id),
        execute=False,
    )
    assert result["status"] == "admitted", result
    return result["run_id"]


def execute(
    workspace: Path,
    run_id: str,
    transport: StubTransport,
) -> dict[str, Any]:
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )
    return IdeationController(workspace, run_id, adapter=adapter).run()


def resume(
    helpers_module: Any,
    workspace: Path,
    run_id: str,
    transport: StubTransport,
    monkeypatch: Any,
) -> dict[str, Any]:
    helpers_module._approve_cost(monkeypatch)
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=transport
    )
    return resume_run(workspace, run_id, adapter=adapter)


def read_events(run_root: Path) -> list[dict[str, Any]]:
    from ai_scientist.ideation.canonical import parse_json_bytes

    events_dir = run_root / "events"
    return [
        parse_json_bytes(path.read_bytes(), label=path.name)
        for path in sorted(events_dir.glob("*.json"))
    ]


PROFILE_PARAMS = (
    pytest.param(
        CROSS_DOMAIN_V1,
        "cross-domain-v1",
        id="cross-domain-v1",
    ),
)
