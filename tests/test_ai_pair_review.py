"""AI-assisted pairwise blind review tests (authoring contract v2, ticket 02).

Delivers the offline coding acceptance of the pair mode:
- anonymous deterministic pair package export: no arm identity, cost, run
  identity, or expected winner in the model-visible direction payloads;
  swap-symmetric A/B and B/A renders; hash-bound outer envelope;
- four independent review contexts (two evaluator slots x two directions),
  each a write-once import with user_supplied provenance and fail-closed
  validation (closed enums, verbatim quotes, linear supersedes);
- reduction that restores anonymous content through the private blind
  mapping: only four valid, content-converging judgments produce a stable
  winner or tie; position flips, evaluator conflicts, incomparable
  judgments, and missing/invalid records are incomparable with recorded
  reasons and can never be silently rerun or merged across protocol
  versions;
- the pre-registered quality floor of each arm, carried independently from
  its dual-review consensus record.

Offline fixtures prove the software contract only — never model judgment
quality. No real model call happens anywhere in this suite.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from ai_scientist.ideation.admission import NewRunRequest
from ai_scientist.ideation.ai_pair_review import (
    DIRECTIONS,
    PAIR_PACKAGE_NAME,
    PAIR_REPORT_HTML_NAME,
    PAIR_REPORT_NAME,
    REDUCTION_DIRNAME,
    export_pair_package,
    import_pair_response,
    reduce_pair_review,
    validate_pair_review,
)
from ai_scientist.ideation.ai_review import aggregate_review
from ai_scientist.ideation.canonical import canonical_json_bytes, sha256_bytes
from ai_scientist.ideation.deepseek import (
    DeepSeekAdapter,
    StubTransport,
    TransportResponse,
)
from ai_scientist.ideation.errors import IdeationInputError
from ai_scientist.ideation.pricing import load_price_table
from ai_scientist.perform_ideation_temp_free import run_new_run
from test_ai_review_evaluation import (
    _config_document,
    _register_config,
    _setup_review_workspace,
)
from test_post_seal_evaluation import (
    CASE_ID,
    _approved_corpus,
    _approved_workshop,
    _evaluation_cli,
    _idea_payload,
    _make_response_bytes,
)

SLOT_MODELS = {
    "primary": ("example-provider", "example-model-1"),
    "second": ("other-provider", "other-model-9"),
}
RESPONDED_AT = "2026-09-05T09:00:00.000000Z"

# Corpus/workshop approval is write-once per workspace id; cache the approved
# inputs so a workspace can seal several runs (the pair needs two ideas).
_APPROVED_INPUTS: dict[Path, tuple[str, str, str, str, str]] = {}


def _approved_inputs(workspace: Path) -> tuple[str, str, str, str, str]:
    if workspace not in _APPROVED_INPUTS:
        workshop_rel, workshop_sha = _approved_workshop(workspace)
        corpus_rel, corpus_sha = _approved_corpus(workspace)
        corpus_data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
        _APPROVED_INPUTS[workspace] = (
            workshop_rel,
            workshop_sha,
            corpus_rel,
            corpus_sha,
            corpus_data["records"][0]["paper_id"],
        )
    return _APPROVED_INPUTS[workspace]


def _seal_run(workspace: Path, idea_payload: dict[str, Any]) -> str:
    workshop_rel, workshop_sha, corpus_rel, corpus_sha, expected_paper_id = (
        _approved_inputs(workspace)
    )
    round_0_content = (
        "ACTION: SearchLiterature\n"
        'ARGUMENTS: {"query": "clinical forecasting migraine"}'
    )
    round_1_content = (
        "ACTION: FinalizeIdea\n"
        f'ARGUMENTS: {{"idea": {json.dumps(idea_payload)}, '
        f'"grounding": ["{expected_paper_id}"]}}'
    )
    responses = [
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(round_0_content, "chatcmpl-round-0"),
            duration_ms=45.0,
        ),
        TransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=_make_response_bytes(round_1_content, "chatcmpl-round-1"),
            duration_ms=55.0,
        ),
    ]
    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "chore: commit approved inputs"],
        cwd=workspace,
        check=False,
        capture_output=True,
    )
    request = NewRunRequest(
        case_id=CASE_ID,
        workshop=workshop_rel,
        workshop_sha256=workshop_sha,
        corpus=corpus_rel,
        corpus_sha256=corpus_sha,
        max_num_generations=1,
        num_reflections=2,
    )
    adapter = DeepSeekAdapter(
        price_table=load_price_table(workspace), transport=StubTransport(responses)
    )
    result = run_new_run(workspace, request, adapter=adapter, execute=True)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    return result["run_id"]


def _seal_two_runs(workspace: Path) -> tuple[str, str]:
    """Seal two runs with different finalized ideas over the same case."""
    run_a = _seal_run(workspace, _idea_payload())
    run_b = _seal_run(workspace, _second_idea_payload())
    return run_a, run_b


def _second_idea_payload() -> dict[str, Any]:
    """A second, materially different idea for the same case."""
    payload = _idea_payload()
    payload["Name"] = "weekly_clinician_diary_forecasting"
    payload["Title"] = "Structured Weekly Diaries for Migraine Forecasting"
    payload["Short Hypothesis"] = (
        "Structured weekly clinician-collected symptom diaries improve early "
        "warning accuracy for migraine attacks relative to passive telemetry "
        "baselines."
    )
    payload["Abstract"] = payload["Abstract"].replace(
        "adaptive temporal cueing framework", "structured weekly diary framework"
    )
    payload["Related Work"] = (
        "Existing forecasting studies lean on passive sensing streams. Our "
        "proposal instead builds the forecast on structured weekly clinician "
        "diaries."
    )
    return payload


@pytest.fixture(autouse=True)
def _mock_interactive_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    import io

    approval_input = io.StringIO("yes\n" * 100)
    monkeypatch.setattr("sys.stdin", approval_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


# ==============================================================================
# Pair response fixtures over the real direction payloads
# ==============================================================================


def _pair_root(workspace: Path, pair_id: str) -> Path:
    return workspace / "artifacts/evaluations/pairs" / pair_id


def _pair_package(workspace: Path, pair_id: str) -> dict[str, Any]:
    return json.loads(
        (_pair_root(workspace, pair_id) / PAIR_PACKAGE_NAME).read_text(encoding="utf-8")
    )


def _direction_sources(
    workspace: Path, pair_id: str, direction: str
) -> dict[str, dict[str, Any]]:
    package = _pair_package(workspace, pair_id)
    return {
        source["source_id"]: source
        for source in package["direction_payloads"][direction]["materials"]["sources"]
    }


def _norm(text: str) -> str:
    return " ".join(text.split())


def _pair_ref(
    source: dict[str, Any], claim: str, stance: str = "supports"
) -> dict[str, str]:
    return {
        "claim": claim,
        "quote": _norm(source["text"])[:48],
        "source_id": source["source_id"],
        "stance": stance,
    }


def _first_arm_source(
    sources: dict[str, dict[str, Any]], prefix: str
) -> dict[str, Any]:
    return next(
        source
        for source_id, source in sorted(sources.items())
        if source_id.startswith(prefix) and source["kind"] == "idea_field"
    )


def _display_verdicts(preference: str) -> dict[str, str]:
    """Overall-verdict per direction for a content preference.

    "content_1"/"content_2" pick the same anonymous content in both
    directions; "arm_a"/"arm_b" always pick the same display position, which
    necessarily flips content across directions.
    """
    return {
        "content_1": {"ab": "a_better", "ba": "b_better"},
        "content_2": {"ab": "b_better", "ba": "a_better"},
        "arm_a": {"ab": "a_better", "ba": "a_better"},
        "arm_b": {"ab": "b_better", "ba": "b_better"},
        "tie": {"ab": "tie", "ba": "tie"},
    }[preference]


def _pair_response_body(
    workspace: Path,
    pair_id: str,
    direction: str,
    *,
    preference: str,
    intrusion: str = "equal",
) -> dict[str, Any]:
    """A schema-valid pair review response over the real direction payload."""
    sources = _direction_sources(workspace, pair_id, direction)
    a_source = _first_arm_source(sources, "A")
    b_source = _first_arm_source(sources, "B")
    shared = sources["C001"]

    if preference == "incomparable":
        missing = ["缺少两臂可共度的比较基础（关键实验细节缺失）"]
        return {
            "domain_method_fit": {
                "evidence_refs": [],
                "rationale": "两臂的领域方法差异无法在给定材料内判断。",
                "verdict": "incomparable",
            },
            "key_assumptions": [],
            "missing_information": missing,
            "overall_preference": {
                "evidence_refs": [],
                "rationale": "材料不足以支持有意义的整体比较。",
                "verdict": "incomparable",
            },
            "task": "pair_idea_review",
            "unjustified_ml_intrusion": {
                "evidence_refs": [],
                "rationale": "无法判断任一臂的无依据 ML 侵入是否更重。",
                "verdict": "incomparable",
            },
        }

    overall = _display_verdicts(preference)[direction]
    if overall == "tie":
        overall_judgment = {
            "evidence_refs": [
                _pair_ref(shared, "两臂共享同一 target 与 workshop 材料")
            ],
            "rationale": "两臂针对同一问题给出各有侧重的方案，整体难分高下。",
            "verdict": "tie",
        }
    else:
        preferred = a_source if overall == "a_better" else b_source
        overall_judgment = {
            "evidence_refs": [
                _pair_ref(preferred, "该臂的假设与实验计划同 target 的问题空间更贴合"),
                _pair_ref(
                    b_source if overall == "a_better" else a_source,
                    "另一臂的方案与 target 的问题空间贴合度较低",
                    stance="contradicts",
                ),
            ],
            "rationale": (
                f"臂 {'A' if overall == 'a_better' else 'B'} 的假设、方法与验证计划"
                "与 target 的问题空间更贴合。"
            ),
            "verdict": overall,
        }

    fit = _display_verdicts(preference)[direction]
    if fit == "tie":
        fit_judgment = {
            "evidence_refs": [_pair_ref(shared, "两臂面向同一领域问题")],
            "rationale": "两臂的领域-方法匹配度相当。",
            "verdict": "tie",
        }
    else:
        fit_source = a_source if fit == "a_better" else b_source
        fit_judgment = {
            "evidence_refs": [_pair_ref(fit_source, "该臂的方法直接服务于领域问题")],
            "rationale": (
                f"臂 {'A' if fit == 'a_better' else 'B'} 的方法选择与领域问题更匹配。"
            ),
            "verdict": fit,
        }

    if intrusion == "arm_a":
        intrusion_judgment = {
            "evidence_refs": [
                _pair_ref(a_source, "该臂引入了与领域问题无关的 ML 复杂度")
            ],
            "rationale": "臂 A 的方案把与领域问题无关的 ML 组件当作卖点。",
            "verdict": "a_more",
        }
    else:
        intrusion_judgment = {
            "evidence_refs": [
                _pair_ref(a_source, "该臂的 ML 组件服务于领域问题"),
                _pair_ref(b_source, "另一臂的 ML 组件同样服务于领域问题"),
            ],
            "rationale": "两臂的无依据 ML 侵入程度相当。",
            "verdict": "equal",
        }

    return {
        "domain_method_fit": fit_judgment,
        "key_assumptions": ["假设材料包完整覆盖两臂的 idea 内容"],
        "missing_information": [],
        "overall_preference": overall_judgment,
        "task": "pair_idea_review",
        "unjustified_ml_intrusion": intrusion_judgment,
    }


def _import_pair_response(
    workspace: Path,
    pair_id: str,
    slot: str,
    direction: str,
    body_or_text: dict[str, Any] | str,
) -> dict[str, Any]:
    if isinstance(body_or_text, str):
        text = body_or_text
    else:
        text = json.dumps(body_or_text, ensure_ascii=False, indent=2)
    path = (
        workspace
        / f"pair-response-{len(list(workspace.glob('pair-response-*.txt'))) + 1}.txt"
    )
    path.write_text(text, encoding="utf-8")
    provider, model_id = SLOT_MODELS[slot]
    return import_pair_response(
        workspace,
        pair_id,
        slot,
        direction,
        response_path=path,
        provider=provider,
        model_id=model_id,
        responded_at=RESPONDED_AT,
        supplied_by="Robert",
        imported_by="integration-tester",
    )


def _run_four_reviews(
    workspace: Path,
    pair_id: str,
    *,
    primary_preference: str = "content_1",
    second_preference: str = "content_1",
    intrusion: str = "equal",
) -> None:
    """Import+validate all four slot-direction contexts."""
    for slot, preference in (
        ("primary", primary_preference),
        ("second", second_preference),
    ):
        for direction in DIRECTIONS:
            body = _pair_response_body(
                workspace,
                pair_id,
                direction,
                preference=preference,
                intrusion=intrusion,
            )
            _import_pair_response(workspace, pair_id, slot, direction, body)
            validate_pair_review(workspace, pair_id, slot, direction)


# ==============================================================================
# Export: anonymous deterministic pair package
# ==============================================================================


def test_export_pair_package_golden_is_anonymous_and_deterministic(
    tmp_path: Path,
) -> None:
    workspace = _setup_review_workspace(tmp_path)
    run_a, run_b = _seal_two_runs(workspace)

    exported = export_pair_package(workspace, run_a, 0, run_b, 0)
    assert exported["status"] == "exported"
    assert exported["prompt_version"] == "pair-review-v1"
    pair_id = exported["pair_id"]
    assert len(pair_id) == len("pair-") + 16
    assert set(pair_id[len("pair-") :]) <= set("0123456789abcdef")

    pair_root = _pair_root(workspace, pair_id)
    package_bytes = (pair_root / PAIR_PACKAGE_NAME).read_bytes()
    assert exported["pair_package_sha256"] == sha256_bytes(package_bytes)
    for direction in DIRECTIONS:
        request_bytes = (pair_root / f"pair-request-{direction}.txt").read_bytes()
        assert exported["requests"][direction]["sha256"] == sha256_bytes(request_bytes)

    # Deterministic re-export: byte-identical package and requests.
    again = export_pair_package(workspace, run_a, 0, run_b, 0)
    assert again["pair_id"] == pair_id
    assert (pair_root / PAIR_PACKAGE_NAME).read_bytes() == package_bytes

    package = json.loads(package_bytes.decode("utf-8"))
    assert package["schema_version"] == "evaluation-pair-package-v1.0.0"
    assert (
        package["authoring_contract_version"] == "evaluation-authoring-contract-v2.0.0"
    )
    assert package["case_id"] == CASE_ID
    assert package["prompt_version"] == "pair-review-v1"
    assert set(package["arms"]) == {"content_1", "content_2"}
    assert {package["arms"][c]["run_id"] for c in ("content_1", "content_2")} == {
        run_a,
        run_b,
    }
    assert package["blind_mapping"] == {
        "ab": {"arm_a": "content_1", "arm_b": "content_2"},
        "ba": {"arm_a": "content_2", "arm_b": "content_1"},
    }
    for direction in DIRECTIONS:
        payload = package["direction_payloads"][direction]
        assert package["direction_payload_sha256"][direction] == sha256_bytes(
            canonical_json_bytes(payload)
        )
        assert payload["task"] == "pair_idea_review"
        payload_text = json.dumps(payload, ensure_ascii=False)
        # Blind packet hygiene: no identity, cost, or expectation leak.
        assert CASE_ID not in payload_text
        assert run_a not in payload_text and run_b not in payload_text
        assert pair_id not in payload_text
        assert "content_1" not in payload_text
        assert "content_2" not in payload_text
        assert "ml-baseline-v1" not in payload_text
        assert "cross-domain-v1" not in payload_text
        assert "expected_winner" not in payload_text
        assert "cost_cny" not in payload_text

    # Sources: shared case material under C### ids, per-arm material under
    # A###/B### ids (idea fields + audit statement + retrieval segments).
    sources_ab = package["direction_payloads"]["ab"]["materials"]["sources"]
    kinds = [source["kind"] for source in sources_ab]
    assert kinds.count("workshop") == 1
    assert kinds.count("target_comparator") == 2
    shared_ids = [
        source["source_id"]
        for source in sources_ab
        if source["kind"] in ("workshop", "target_comparator")
    ]
    assert shared_ids == ["C001", "C002", "C003"]
    assert kinds.count("idea_field") == 14  # seven per arm
    assert kinds.count("audit_statement") == 2
    a_idea_fields = [
        source
        for source in sources_ab
        if source["source_id"].startswith("A") and source["kind"] == "idea_field"
    ]
    assert len(a_idea_fields) == 7

    # Swap symmetry: what ab shows as arm A, ba shows as arm B.
    def _arm_texts(
        package_doc: dict[str, Any], direction: str, prefix: str
    ) -> list[str]:
        return sorted(
            source["text"]
            for source in package_doc["direction_payloads"][direction]["materials"][
                "sources"
            ]
            if source["source_id"].startswith(prefix)
            and source["kind"] not in ("workshop", "target_comparator")
        )

    assert _arm_texts(package, "ab", "A") == _arm_texts(package, "ba", "B")
    assert _arm_texts(package, "ab", "B") == _arm_texts(package, "ba", "A")

    # The private registry maps every display id back to its origin.
    registry = package["source_registry"]
    assert {entry["direction"] for entry in registry} == {"ab", "ba"}
    assert all(
        entry["arm"] in ("shared", "content_1", "content_2") for entry in registry
    )


def test_export_pair_package_rejects_identical_arms(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    run_a, run_b = _seal_two_runs(workspace)

    with pytest.raises(IdeationInputError) as exc:
        export_pair_package(workspace, run_a, 0, run_a, 0)
    assert exc.value.code == "PAIR_ARMS_IDENTICAL"

    # Two runs with byte-identical idea payloads are also not a pair.
    run_c = _seal_run(workspace, _idea_payload())
    with pytest.raises(IdeationInputError) as exc2:
        export_pair_package(workspace, run_a, 0, run_c, 0)
    assert exc2.value.code == "PAIR_ARMS_IDENTICAL"


def test_export_pair_package_allows_paper_ids_inside_idea_text(
    tmp_path: Path,
) -> None:
    """Corpus-reference hashes inside a finalized idea's own text export fine.

    A finalized idea may cite references as `Paper ID <hash>` (the model's
    declared-grounding style). That hash names a reference paper, not an
    arm; both arms share one corpus, so it cannot reveal the challenger.
    Run/case/profile/pair identities stay fail closed (regression for the
    real-slot-1 baseline idea whose Related Work cited three paper ids).
    """
    workspace = _setup_review_workspace(tmp_path)
    _approved_inputs(workspace)
    payload = _idea_payload()
    paper_id = _APPROVED_INPUTS[workspace][4]
    payload["Related Work"] = (
        f"Prior forecasting work predicted seasonal peaks (Paper ID {paper_id}) "
        "but relied exclusively on static clinical records. Our proposal "
        "introduces adaptive temporal cueing based on passive sensing streams."
    )
    run_a = _seal_run(workspace, payload)
    run_b = _seal_run(workspace, _second_idea_payload())

    exported = export_pair_package(workspace, run_a, 0, run_b, 0)
    package_doc = json.loads(
        (_pair_root(workspace, exported["pair_id"]) / PAIR_PACKAGE_NAME).read_text(
            encoding="utf-8"
        )
    )
    payload_text = json.dumps(package_doc["direction_payloads"], ensure_ascii=False)
    assert paper_id in payload_text  # the idea text carries the citation
    # Non-idea identity secrets stay fail closed.
    assert run_a not in payload_text and CASE_ID not in payload_text


# ==============================================================================
# Import + validate: four independent contexts, fail closed
# ==============================================================================


def test_four_reviews_live_in_isolated_contexts(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    exported = export_pair_package(workspace, run_a, 0, run_b, 0)
    pair_id = exported["pair_id"]
    _run_four_reviews(workspace, pair_id)

    pair_root = _pair_root(workspace, pair_id)
    for slot in ("primary", "second"):
        for direction in DIRECTIONS:
            response_path = pair_root / slot / direction / "responses" / "r0001.json"
            assert response_path.is_file(), f"{slot}/{direction}"
            stored = json.loads(response_path.read_text(encoding="utf-8"))
            assert stored["parse_status"] == "ok"
            assert stored["provenance"] == {
                "kind": "user_supplied",
                "supplied_by": "Robert",
            }
            assert stored["pair_id"] == pair_id
            assert stored["direction"] == direction
            assert stored["evaluator_slot"] == slot
            assert stored["declared"]["model_id"] == SLOT_MODELS[slot][1]
            assert stored["parsed_response"]["task"] == "pair_idea_review"
            record_path = pair_root / slot / direction / "v0001.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            assert record["schema_version"] == (
                "evaluation-ai-pair-review-record-v2.0.0"
            )
            assert record["record_kind"] == "pair_ai_review"
            assert record["direction"] == direction
            assert record["evaluator"]["evaluator_slot"] == slot
            assert record["evaluator"]["response_file"] == (
                f"{slot}/{direction}/responses/r0001.json"
            )
            assert record["citation_verification"]["refs_quote_verified"] == (
                record["citation_verification"]["refs_total"]
            )
            assert record["citation_verification"]["semantic_support_verification"] == (
                "not_performed"
            )

    # Importing twice appends within the same context (write-once files).
    body = _pair_response_body(workspace, pair_id, "ab", preference="tie")
    result = _import_pair_response(workspace, pair_id, "primary", "ab", body)
    assert result["response_seq"] == 2
    assert (pair_root / "primary/ab/responses/r0001.json").is_file()


def test_pair_validate_rejects_fake_citations_and_bad_schemas(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]

    # Fabricated quote (plausible but not verbatim).
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["overall_preference"]["evidence_refs"][0][
        "quote"
    ] = "this idea clearly dominates the other on every axis"
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    with pytest.raises(IdeationInputError) as exc:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc.value.code == "CITATION_QUOTE_NOT_FOUND"

    # Unknown source id.
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["overall_preference"]["evidence_refs"][0]["source_id"] = "A999"
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    with pytest.raises(IdeationInputError) as exc2:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc2.value.code == "CITATION_SOURCE_NOT_FOUND"

    # Judged without refs and without the inference marker.
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["domain_method_fit"]["evidence_refs"] = []
    body["domain_method_fit"]["rationale"] = "看起来更贴合。"
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    with pytest.raises(IdeationInputError) as exc3:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc3.value.code == "EVIDENCE_REF_REQUIRED"

    # Judged with only the inference marker and no refs is accepted.
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["domain_method_fit"]["evidence_refs"] = []
    body["domain_method_fit"]["rationale"] = "推断：两臂方法在给定材料下匹配度相当。"
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    result = validate_pair_review(workspace, pair_id, "primary", "ab")
    assert result["status"] == "validated"

    # Invalid enum.
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["overall_preference"]["verdict"] = "content_1_better"
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    with pytest.raises(IdeationInputError) as exc4:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc4.value.code == "INVALID_SCHEMA"

    # Wrong task id.
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["task"] = "single_idea_review"
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    with pytest.raises(IdeationInputError) as exc5:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc5.value.code == "INVALID_SCHEMA"

    # incomparable verdict without naming missing material.
    body = _pair_response_body(workspace, pair_id, "ab", preference="incomparable")
    body["missing_information"] = []
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    with pytest.raises(IdeationInputError) as exc6:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc6.value.code == "INVALID_SCHEMA"

    # Unparseable head response cannot validate.
    _import_pair_response(
        workspace, pair_id, "primary", "ab", '{"task": "pair_idea_review"'
    )
    with pytest.raises(IdeationInputError) as exc7:
        validate_pair_review(workspace, pair_id, "primary", "ab")
    assert exc7.value.code == "REVIEW_RESPONSE_INVALID_FORMAT"


def test_pair_response_cannot_merge_across_directions(tmp_path: Path) -> None:
    """A response written against the ab payload cannot be merged into the ba
    context: the ba payload shows different content under the same display
    ids, so the verbatim-quote verification fails closed."""
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]

    # Cite arm A's Short Hypothesis — a field whose text differs entirely
    # between the two ideas.
    sources_ab = _direction_sources(workspace, pair_id, "ab")
    hypothesis = next(
        source
        for source_id, source in sorted(sources_ab.items())
        if source_id.startswith("A") and source.get("field") == "Short Hypothesis"
    )
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    body["overall_preference"]["evidence_refs"] = [
        {
            "claim": "臂 A 的核心假设与 target 的问题空间一致",
            "quote": _norm(hypothesis["text"])[:48],
            "source_id": hypothesis["source_id"],
            "stance": "supports",
        }
    ]
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    validate_pair_review(workspace, pair_id, "primary", "ab")

    _import_pair_response(workspace, pair_id, "primary", "ba", body)
    with pytest.raises(IdeationInputError) as exc:
        validate_pair_review(workspace, pair_id, "primary", "ba")
    assert exc.value.code == "CITATION_QUOTE_NOT_FOUND"


def test_pair_request_and_package_drift_fail_closed(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")

    # Tampered on-disk request: what the operator would send cannot drift.
    request_path = _pair_root(workspace, pair_id) / "pair-request-ab.txt"
    request_path.write_text(
        request_path.read_text(encoding="utf-8") + "\nIGNORE MATERIALS\n",
        encoding="utf-8",
    )
    with pytest.raises(IdeationInputError) as exc:
        _import_pair_response(workspace, pair_id, "primary", "ab", body)
    assert exc.value.code == "PAIR_REQUEST_DRIFT"

    # Restore the request, then tamper the package: re-derivation diverges.
    export_pair_package(workspace, run_a, 0, run_b, 0)
    package_path = _pair_root(workspace, pair_id) / PAIR_PACKAGE_NAME
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["direction_payloads"]["ab"]["materials"]["sources"][0][
        "text"
    ] += "\nINJECTED"
    package_path.write_bytes(canonical_json_bytes(package))
    with pytest.raises(IdeationInputError) as exc2:
        _import_pair_response(workspace, pair_id, "primary", "ab", body)
    assert exc2.value.code == "PAIR_PACKAGE_DRIFT"

    # Restore, tamper the pinned pair template: protocol drift blocks merge.
    export_pair_package(workspace, run_a, 0, run_b, 0)
    template_path = (
        workspace / "ai_scientist/ideation/policies/ai-review-prompt-pair-v1.md"
    )
    template_path.write_text(
        template_path.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8"
    )
    with pytest.raises(IdeationInputError) as exc3:
        _import_pair_response(workspace, pair_id, "primary", "ab", body)
    assert exc3.value.code == "POLICY_DRIFT"

    # Nothing was stored anywhere along the way.
    assert not (_pair_root(workspace, pair_id) / "primary/ab/responses").exists()


# ==============================================================================
# Reduction: restore anonymous content across the four judgments
# ==============================================================================


def _reduce(workspace: Path, pair_id: str) -> dict[str, Any]:
    return reduce_pair_review(workspace, pair_id)


def test_reduce_stable_winner(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    _run_four_reviews(
        workspace,
        pair_id,
        primary_preference="content_1",
        second_preference="content_1",
    )

    result = _reduce(workspace, pair_id)
    assert result["status"] == "reduced"
    assert result["coverage"] == "complete"
    assert result["version"] == "v0001.json"
    reduction = result["reduction"]
    overall = reduction["overall_preference"]
    assert overall["outcome"] == "stable"
    assert overall["content_value"] == "content_1"
    assert overall["reasons"] == []
    fit = reduction["domain_method_fit"]
    assert fit["outcome"] == "stable"
    assert fit["content_value"] == "content_1"
    intrusion = reduction["unjustified_ml_intrusion"]
    assert intrusion["outcome"] == "stable"
    assert intrusion["content_value"] == "equal"

    record = json.loads(
        (_pair_root(workspace, pair_id) / REDUCTION_DIRNAME / "v0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["schema_version"] == "evaluation-ai-pair-reduction-record-v2.0.0"
    assert record["record_kind"] == "pair_ai_reduction"
    assert record["coverage"] == "complete"
    assert set(record["direction_results"]["primary"]) == {"ab", "ba"}
    assert all(
        entry["state"] == "valid"
        for slot in record["direction_results"].values()
        for entry in slot.values()
    )
    assert record["evaluators"]["primary"]["declared_model_id"] == "example-model-1"
    assert record["evaluators"]["second"]["model_family"] == "family-beta"
    # The report restores content identities privately.
    report = (_pair_root(workspace, pair_id) / PAIR_REPORT_NAME).read_text(
        encoding="utf-8"
    )
    assert "# 成对盲评还原报告（双评审）" in report
    assert run_a in report and run_b in report
    assert "content_1" in report and "content_2" in report
    html_text = (_pair_root(workspace, pair_id) / PAIR_REPORT_HTML_NAME).read_text(
        encoding="utf-8"
    )
    assert "<!DOCTYPE html>" in html_text and "<script" not in html_text
    assert result["pair_report"].endswith("pair-report.md")

    # Re-reduction supersedes linearly.
    second = _reduce(workspace, pair_id)
    assert second["version"] == "v0002.json"
    assert second["supersedes"] == "v0001.json"


def test_reduce_stable_tie(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    _run_four_reviews(
        workspace, pair_id, primary_preference="tie", second_preference="tie"
    )

    result = _reduce(workspace, pair_id)
    overall = result["reduction"]["overall_preference"]
    assert overall["outcome"] == "stable"
    assert overall["content_value"] == "tie"
    assert overall["reasons"] == []


def test_reduce_position_flip_is_incomparable(tmp_path: Path) -> None:
    """A slot that always prefers display arm A preferred content_1 in A/B but
    content_2 in B/A: its preference tracks position, not content."""
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    _run_four_reviews(
        workspace,
        pair_id,
        primary_preference="arm_a",
        second_preference="content_1",
        intrusion="arm_a",
    )

    result = _reduce(workspace, pair_id)
    assert result["coverage"] == "complete"
    overall = result["reduction"]["overall_preference"]
    assert overall["outcome"] == "incomparable"
    assert overall["content_value"] is None
    codes = {reason["code"] for reason in overall["reasons"]}
    assert "position_flip" in codes
    flip = next(r for r in overall["reasons"] if r["code"] == "position_flip")
    assert flip["slot"] == "primary"
    # The intrusion dimension flips too (same position-driven pattern).
    intrusion = result["reduction"]["unjustified_ml_intrusion"]
    assert intrusion["outcome"] == "incomparable"
    assert "position_flip" in {r["code"] for r in intrusion["reasons"]}


def test_reduce_evaluator_conflict_is_incomparable(tmp_path: Path) -> None:
    """Each slot is internally consistent, but the two evaluators prefer
    different content: the pair is incomparable, never averaged away."""
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    _run_four_reviews(
        workspace,
        pair_id,
        primary_preference="content_1",
        second_preference="content_2",
    )

    result = _reduce(workspace, pair_id)
    overall = result["reduction"]["overall_preference"]
    assert overall["outcome"] == "incomparable"
    codes = {reason["code"] for reason in overall["reasons"]}
    assert codes == {"evaluator_conflict"}
    assert "position_flip" not in codes


def test_reduce_missing_valid_record_is_incomparable(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]

    # Only three of the four contexts are validated.
    for slot, preference in (("primary", "content_1"), ("second", "content_1")):
        for direction in DIRECTIONS:
            if (slot, direction) == ("second", "ba"):
                continue
            body = _pair_response_body(
                workspace, pair_id, direction, preference=preference
            )
            _import_pair_response(workspace, pair_id, slot, direction, body)
            validate_pair_review(workspace, pair_id, slot, direction)

    result = _reduce(workspace, pair_id)
    assert result["coverage"] == "incomplete"
    overall = result["reduction"]["overall_preference"]
    assert overall["outcome"] == "incomparable"
    assert overall["reasons"] == [
        {
            "code": "missing_valid_record",
            "slot_directions": ["second/ba"],
        }
    ]


def test_reduce_invalid_response_is_incomparable(tmp_path: Path) -> None:
    """A slot-direction whose head response is unparseable can never count as
    a completed review: the reduction is incomparable, not a silent skip."""
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]

    for slot, preference in (("primary", "content_1"), ("second", "content_1")):
        for direction in DIRECTIONS:
            if (slot, direction) == ("second", "ab"):
                _import_pair_response(
                    workspace, pair_id, slot, direction, "persuasive prose, not JSON"
                )
                continue
            body = _pair_response_body(
                workspace, pair_id, direction, preference=preference
            )
            _import_pair_response(workspace, pair_id, slot, direction, body)
            validate_pair_review(workspace, pair_id, slot, direction)

    result = _reduce(workspace, pair_id)
    assert result["coverage"] == "incomplete"
    overall = result["reduction"]["overall_preference"]
    assert overall["outcome"] == "incomparable"
    assert overall["reasons"] == [
        {"code": "missing_valid_record", "slot_directions": ["second/ab"]}
    ]
    record = json.loads(
        (_pair_root(workspace, pair_id) / REDUCTION_DIRNAME / "v0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["direction_results"]["second"]["ab"]["state"] == "invalid"


def test_reduce_all_incomparable_judgments(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    _run_four_reviews(
        workspace,
        pair_id,
        primary_preference="incomparable",
        second_preference="incomparable",
    )

    result = _reduce(workspace, pair_id)
    assert result["coverage"] == "complete"
    overall = result["reduction"]["overall_preference"]
    assert overall["outcome"] == "incomparable"
    assert overall["reasons"] == [
        {
            "code": "incomparable_judgment",
            "detail": "all four valid judgments agree the pair is incomparable",
        }
    ]


def test_reduce_carries_quality_floor_from_consensus(tmp_path: Path) -> None:
    """The pre-registered floor of each arm comes from its dual-review
    consensus record and is independent of the pair's overall preference."""
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    package = _pair_package(workspace, pair_id)
    content_1_run = package["arms"]["content_1"]["run_id"]

    # Dual-review both arms; make content_1's consensus violate the floor.
    _run_dual_review_with_floor(workspace, content_1_run, unsound=True)
    other_run = run_b if content_1_run == run_a else run_a
    _run_dual_review_with_floor(workspace, other_run, unsound=False)

    _run_four_reviews(
        workspace, pair_id, primary_preference="tie", second_preference="tie"
    )
    result = _reduce(workspace, pair_id)
    assert result["coverage"] == "complete"
    # A tie stays a stable tie: the floor never overrides the preference.
    assert result["reduction"]["overall_preference"]["content_value"] == "tie"
    assert set(result["quality_floor"]) == {"content_1", "content_2"}
    assert result["quality_floor"]["content_1"] == "violated"
    assert result["quality_floor"]["content_2"] == "clean"
    reduction_record = json.loads(
        (_pair_root(workspace, pair_id) / REDUCTION_DIRNAME / "v0001.json").read_text(
            encoding="utf-8"
        )
    )
    floors = reduction_record["quality_floor"]
    assert floors["content_1"]["consensus_record"].endswith("consensus/v0001.json")
    assert floors["content_1"]["consensus_record_sha256"]
    assert floors["content_1"]["coverage"] == "complete_resolved"


def _generic_single_body(
    workspace: Path, run_id: str, *, unsound: bool
) -> dict[str, Any]:
    """A schema-valid seven-dimension judged response over this run's own
    package, with every quote anchored to the real source text (the shared
    fixture body hardcodes fragments of the default idea only)."""
    from test_ai_review_evaluation import _export, _norm, _sources

    _export(workspace, run_id)
    sources = _sources(workspace, run_id)

    def field(field_name: str) -> dict[str, Any]:
        return next(
            source
            for source in sources.values()
            if source["kind"] == "idea_field" and source["field"] == field_name
        )

    def pick(kind: str, **match: str) -> dict[str, Any]:
        return next(
            source
            for source in sources.values()
            if source["kind"] == kind
            and all(source.get(key) == value for key, value in match.items())
        )

    def ref(source: dict[str, Any], claim: str) -> dict[str, str]:
        return {
            "claim": claim,
            "quote": _norm(source["text"])[:48],
            "source_id": source["source_id"],
            "stance": "supports",
        }

    def dim(verdict: str, rationale: str, refs: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "assessment_status": "judged",
            "evidence_refs": refs,
            "key_assumptions": [],
            "missing_information": [],
            "proposed_verdict": verdict,
            "rationale": rationale,
        }

    hypothesis = field("Short Hypothesis")
    related = field("Related Work")
    experiments = field("Experiments")
    name = field("Name")
    target_summary = pick("target_comparator", part="abstract_summary")
    audit = pick("audit_statement")
    segment = pick("retrieval_segment")
    return {
        "dimensions": {
            "problem_space_match": dim(
                "aligned",
                "idea 与 target 同属同一问题空间。",
                [
                    ref(hypothesis, "idea 的研究问题与 target 对应"),
                    ref(target_summary, "target 的官方摘要锚定同一问题空间"),
                ],
            ),
            "target_contribution_overlap": dim(
                "partial_overlap",
                "idea 与 target 部分重叠。",
                [ref(related, "idea 声称现有方法依赖静态临床记录")],
            ),
            "relative_novelty": dim(
                "on_par",
                "相对给定 target 有实质增量但未超出其问题框架。",
                [ref(related, "idea 引入新的提示机制")],
            ),
            "feasibility_soundness": dim(
                "unsound" if unsound else "sound",
                (
                    "实验计划缺少对照，关键假设无法由给定材料支持。"
                    if unsound
                    else "实验计划给出可比基线与消融，逻辑连贯。"
                ),
                [ref(experiments, "idea 计划与静态基线对比")],
            ),
            "contamination_signal": dim(
                "none_found",
                "在本材料包范围内未发现污染信号。",
                [
                    ref(name, "idea 命名未复现 target 独有命名（限本材料包范围）"),
                    ref(audit, "none_found 仅限本材料包实际审查范围"),
                ],
            ),
            "leakage_review": dim(
                "clean",
                "审计声明显示生成期 hygiene 扫描通过。",
                [ref(audit, "生成期 FinalizeIdea payload 卫生扫描通过")],
            ),
            "grounding_synthesis": dim(
                "synthesized",
                "声明 grounding 的片段被 idea 的假设与实验计划实际使用。",
                [ref(segment, "idea 的预测思路与该检索片段内容一致")],
            ),
        },
        "task": "single_idea_review",
    }


def _run_dual_review_with_floor(workspace: Path, run_id: str, *, unsound: bool) -> None:
    """Two same-verdict single reviews of one run, aggregated into consensus."""
    from ai_scientist.ideation.ai_review import import_review_response
    from test_ai_review_evaluation import (
        _import_body,
        _validate_review,
        _write_response_file,
    )

    body = _generic_single_body(workspace, run_id, unsound=unsound)
    _import_body(workspace, run_id, body)
    _validate_review(workspace, run_id)
    second_path = _write_response_file(workspace, body)
    import_review_response(
        workspace,
        run_id,
        0,
        response_path=second_path,
        evaluator_slot="second",
        provider="other-provider",
        model_id="other-model-9",
        responded_at=RESPONDED_AT,
        supplied_by="Robert",
        imported_by="integration-tester",
    )
    _validate_review(workspace, run_id, evaluator_slot="second")
    aggregate_review(workspace, run_id, 0)


def test_reduce_requires_config_and_package(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    run_a, run_b = _seal_two_runs(workspace)

    with pytest.raises(IdeationInputError) as exc:
        reduce_pair_review(workspace, "pair-0123456789abcdef")
    assert exc.value.code == "PAIR_PACKAGE_NOT_FOUND"

    with pytest.raises(IdeationInputError) as exc2:
        reduce_pair_review(workspace, "not-a-pair-id")
    assert exc2.value.code == "INVALID_COORDINATE"

    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    with pytest.raises(IdeationInputError) as exc3:
        reduce_pair_review(workspace, pair_id)
    assert exc3.value.code == "REVIEW_CONFIG_NOT_FOUND"

    # Import + validate works before any config is registered (binding is
    # only enforced against a registered config).
    body = _pair_response_body(workspace, pair_id, "ab", preference="content_1")
    _import_pair_response(workspace, pair_id, "primary", "ab", body)
    validated = validate_pair_review(workspace, pair_id, "primary", "ab")
    assert validated["status"] == "validated"

    # Reduction itself still requires the registered config.
    with pytest.raises(IdeationInputError) as exc3b:
        reduce_pair_review(workspace, pair_id)
    assert exc3b.value.code == "REVIEW_CONFIG_NOT_FOUND"

    _register_config(workspace)
    # With exactly one validated record the reduction is incomplete, never
    # silently stable.
    result = reduce_pair_review(workspace, pair_id)
    assert result["coverage"] == "incomplete"
    assert result["reduction"]["overall_preference"]["outcome"] == "incomparable"

    # A registered config with no imported responses is also a hard stop.
    workspace2 = _setup_review_workspace(tmp_path / "second")
    run_a2, run_b2 = _seal_two_runs(workspace2)
    _register_config(workspace2)
    pair_id2 = export_pair_package(workspace2, run_a2, 0, run_b2, 0)["pair_id"]
    with pytest.raises(IdeationInputError) as exc5:
        reduce_pair_review(workspace2, pair_id2)
    assert exc5.value.code == "REVIEW_RESPONSE_NOT_FOUND"


def test_reduce_tampered_pair_record_fails_closed(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    _register_config(workspace)
    run_a, run_b = _seal_two_runs(workspace)
    pair_id = export_pair_package(workspace, run_a, 0, run_b, 0)["pair_id"]
    _run_four_reviews(workspace, pair_id)

    # Tampering a stored record's verdict breaks re-validation: the reduction
    # re-runs the full judgment checks from the authentic response and proves
    # the committed record matches it.
    record_path = _pair_root(workspace, pair_id) / "second/ba/v0001.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["judgments"]["overall_preference"]["verdict"] = "arm_a_better"
    record_path.write_bytes(canonical_json_bytes(record))

    with pytest.raises(IdeationInputError) as exc:
        reduce_pair_review(workspace, pair_id)
    assert exc.value.code == "RUN_CORRUPT"

    # Tampering the bound response file instead breaks the hash chain.
    workspace2 = _setup_review_workspace(tmp_path / "second")
    run_a2, run_b2 = _seal_two_runs(workspace2)
    _register_config(workspace2)
    pair_id2 = export_pair_package(workspace2, run_a2, 0, run_b2, 0)["pair_id"]
    _run_four_reviews(workspace2, pair_id2)
    response_path = _pair_root(workspace2, pair_id2) / "second/ba/responses/r0001.json"
    stored = json.loads(response_path.read_text(encoding="utf-8"))
    stored["parsed_response"]["task"] = "tampered"
    response_path.write_bytes(canonical_json_bytes(stored))
    with pytest.raises(IdeationInputError) as exc2:
        reduce_pair_review(workspace2, pair_id2)
    assert exc2.value.code == "HASH_MISMATCH"


# ==============================================================================
# CLI seam
# ==============================================================================


def test_cli_pair_end_to_end(tmp_path: Path) -> None:
    workspace = _setup_review_workspace(tmp_path)
    run_a, run_b = _seal_two_runs(workspace)

    config_path = workspace / "cli-config.json"
    config_path.write_bytes(canonical_json_bytes(_config_document()))
    registered = _evaluation_cli(
        workspace, "register-review-config", "--config-file", str(config_path)
    )
    assert registered.returncode == 0, registered.stderr

    export = _evaluation_cli(
        workspace,
        "export-pair-package",
        "--run-id-a",
        run_a,
        "--idea-index-a",
        "0",
        "--run-id-b",
        run_b,
        "--idea-index-b",
        "0",
    )
    assert export.returncode == 0, export.stderr
    pair_id = json.loads(export.stdout)["pair_id"]

    for slot, preference in (("primary", "content_1"), ("second", "content_1")):
        for direction in DIRECTIONS:
            body = _pair_response_body(
                workspace, pair_id, direction, preference=preference
            )
            response_path = workspace / f"cli-pair-response-{slot}-{direction}.txt"
            response_path.write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            provider, model_id = SLOT_MODELS[slot]
            imported = _evaluation_cli(
                workspace,
                "import-pair-response",
                "--pair-id",
                pair_id,
                "--evaluator-slot",
                slot,
                "--direction",
                direction,
                "--response-file",
                str(response_path),
                "--provider",
                provider,
                "--model-id",
                model_id,
                "--responded-at",
                RESPONDED_AT,
                "--supplied-by",
                "Robert",
                "--imported-by",
                "integration-tester",
            )
            assert imported.returncode == 0, imported.stderr
            validated = _evaluation_cli(
                workspace,
                "validate-pair-review",
                "--pair-id",
                pair_id,
                "--evaluator-slot",
                slot,
                "--direction",
                direction,
            )
            assert validated.returncode == 0, validated.stderr

    reduced = _evaluation_cli(workspace, "reduce-pair-review", "--pair-id", pair_id)
    assert reduced.returncode == 0, reduced.stderr
    payload = json.loads(reduced.stdout)
    assert payload["coverage"] == "complete"
    assert payload["reduction"]["overall_preference"]["content_value"] == "content_1"
    assert (
        workspace / "artifacts/evaluations/pairs" / pair_id / PAIR_REPORT_NAME
    ).is_file()

    # Rejecting path: identical arms exit 1 with a coded error.
    rejected = _evaluation_cli(
        workspace,
        "export-pair-package",
        "--run-id-a",
        run_a,
        "--idea-index-a",
        "0",
        "--run-id-b",
        run_a,
        "--idea-index-b",
        "0",
    )
    assert rejected.returncode == 1
    assert json.loads(rejected.stderr)["code"] == "PAIR_ARMS_IDENTICAL"
