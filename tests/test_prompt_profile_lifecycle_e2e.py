"""End-to-end Prompt Profile lifecycle tests (ticket 01).

Exercises the full governed seam for BOTH registered profiles with recorded
stub transport only: CLI/party admission with pinned profile identity ->
controller execution (profile-rendered prompt bytes) -> seal -> static
Evidence Chain validation -> sanitized export -> SIGINT suspension ->
admission-driven resume to the equivalent chain.

Plus the negative contracts: unknown profile at the CLI, cross-profile
substitution during resume, and registry drift mid-life. Zero network, zero
cost, no real provider request.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.prompt_profile_lifecycle import (
    FINALIZE_RESPONSE_ID,
    PROFILE_PARAMS,
    SEARCH_RESPONSE_ID,
    _CapturingStubTransport,
    _finalize_content,
    _search_stub,
    _stub,
    admit,
    execute,
    helpers as helpers_fixture,
    idea_payload,
    make_request,
    read_events,
    resume,
)
from ai_scientist.ideation import contract, profiles
from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    parse_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.deepseek import StubTransport, TransportResponse
from ai_scientist.ideation.evidence import (
    export_sanitized_evidence,
    validate_evidence_chain,
)
from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted
from ai_scientist.ideation.profiles import (
    CROSS_DOMAIN_V1 as CROSS_DOMAIN_V1_REF,
)
from ai_scientist.ideation.profiles import (
    ML_BASELINE_V1 as ML_BASELINE_V1_REF,
)
from ai_scientist.ideation.run_store import RunStore
from ai_scientist.perform_ideation_temp_free import _run_new_run

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def helpers(helpers_fixture):
    return helpers_fixture


def _prepared_workspace(
    tmp_path: Path, helpers_module: Any
) -> tuple[Path, dict[str, str]]:
    workspace = helpers_module._workspace(tmp_path)
    corpus_rel, corpus_sha = helpers_module._approved_corpus(workspace)
    workshop_rel, workshop_sha = helpers_module._approved_workshop(workspace)
    helpers_module._commit_all(workspace)
    return workspace, {
        "corpus": corpus_rel,
        "corpus_sha256": corpus_sha,
        "workshop": workshop_rel,
        "workshop_sha256": workshop_sha,
    }


def _finalize_stub_with_paper(workspace: Path, corpus_rel: str) -> TransportResponse:
    data = json.loads((workspace / corpus_rel).read_text(encoding="utf-8"))
    paper_id = data["records"][0]["paper_id"]
    content = _finalize_content().replace("__PAPER_ID__", paper_id)
    return _stub(content, FINALIZE_RESPONSE_ID)


def _kill_sigint(payload: dict[str, Any]) -> TransportResponse:
    os.kill(os.getpid(), signal.SIGINT)
    raise AssertionError("the signal handler must abort before this returns")


def _stub_responses(workspace: Path, inputs: dict[str, str]):
    return [_search_stub(), _finalize_stub_with_paper(workspace, inputs["corpus"])]


def _run_root(workspace: Path, run_id: str) -> Path:
    return workspace / "artifacts/ideation-runs" / run_id


# ==========================================================================
# Lifecycle: admit -> execute -> seal -> validate -> export for both profiles
# ==========================================================================


@pytest.mark.parametrize(("profile", "profile_id"), PROFILE_PARAMS)
def test_full_lifecycle_seals_validates_and_exports_with_pinned_profile(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
    profile,
    profile_id: str,
) -> None:
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, profile_id)

    # Admission pins the resolved profile identity.
    run_root = _run_root(workspace, run_id)
    request_doc = parse_json_bytes(
        (run_root / "request.json").read_bytes(), label="request.json"
    )
    admission_doc = parse_json_bytes(
        (run_root / "admission.json").read_bytes(), label="admission.json"
    )
    assert request_doc["schema_version"] == "run-request-v1.1.0"
    assert admission_doc["schema_version"] == "run-admission-v1.1.0"
    expected_field = {
        "bundle_sha256": profiles.profile_bundle_sha256(profile),
        "contract_version": profile.contract_version,
        "profile_id": profile_id,
        "registry_sha256": profiles.profile_registry_sha256(),
    }
    assert request_doc["prompt_profile"] == expected_field
    assert admission_doc["prompt_profile"] == expected_field
    assert admission_doc["model"]["max_tokens"] == 32768
    assert admission_doc["model"]["reasoning_effort"] == "high"

    transport = _CapturingStubTransport(_stub_responses(workspace, inputs))
    result = execute(workspace, run_id, transport)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 1

    # The system prompt sent to the transport is exactly the profile rendering.
    sent = transport.sent_requests
    assert len(sent) == 2
    assert sent[0]["messages"][0]["role"] == "system"
    assert sent[0]["messages"][0]["content"] == profiles.render_system_prompt(profile)
    # Generation prompt keeps workshop/diversity framing; reflection keeps the
    # tool-result frame.
    generation = sent[0]["messages"][1]["content"]
    assert generation.startswith("# Title: Migraine care questions")
    assert "Here are the proposals that you have already generated:" in generation
    assert (
        "Begin by generating an interestingly new high-level research proposal"
        in generation
    )
    reflection = sent[1]["messages"][-1]["content"]
    assert reflection.startswith("Round 2/2.")
    assert "Results from your last action (if any):" in reflection
    if profile_id == "cross-domain-v1":
        assert "domain-method mismatch" in reflection
        assert "top ML conferences" not in sent[0]["messages"][0]["content"]
    else:
        assert "top ML conferences" in sent[0]["messages"][0]["content"]
        assert "domain-method mismatch" not in reflection

    # Static Evidence Chain validation passes with the profile pin.
    validation = validate_evidence_chain(workspace, run_id, check_sealed=True)
    assert validation["status"] == "valid"

    # Sanitized export exposes only the safe profile identity.
    export = export_sanitized_evidence(workspace, run_id)
    assert export["status"] == "exported"
    manifest = parse_json_bytes(
        (workspace / "evidence/ideation-runs" / run_id / "manifest.json").read_bytes(),
        label="manifest.json",
    )
    assert manifest["prompt_profile"] == {
        "bundle_sha256": profiles.profile_bundle_sha256(profile),
        "profile_id": profile_id,
        "profile_contract_version": profile.contract_version,
    }
    events_text = (
        workspace / "evidence/ideation-runs" / run_id / "events.json"
    ).read_text(encoding="utf-8")
    manifest_text = json.dumps(manifest)
    # No prompt text, workshop text, or template bytes leak into sanitized output.
    for needle in (
        "top ML conferences",
        "multidisciplinary research scientist",
        "workshop_description",
        "{tool_descriptions}",
    ):
        assert needle not in events_text
        assert needle not in manifest_text


def test_cli_new_run_rejects_unknown_profile_before_admission(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """An unregistered profile id fails closed as a preflight rejection."""
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    args = argparse.Namespace(
        case_id=helpers.CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=2,
        prompt_profile="cross-domain-v2",
        entry="new-run",
    )
    exit_code = _run_new_run(args, workspace_root=workspace, execute=False)
    assert exit_code == 2
    runs_root = workspace / "artifacts/ideation-runs"
    if runs_root.exists():
        for run_dir in runs_root.iterdir():
            assert not (run_dir / "admission.json").exists()


def test_cli_new_run_rejects_free_text_profile(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixture-present")
    args = argparse.Namespace(
        case_id=helpers.CASE_ID,
        workshop=inputs["workshop"],
        workshop_sha256=inputs["workshop_sha256"],
        corpus=inputs["corpus"],
        corpus_sha256=inputs["corpus_sha256"],
        max_num_generations=1,
        num_reflections=2,
        prompt_profile="prompts/ml_baseline.txt",
        entry="new-run",
    )
    exit_code = _run_new_run(args, workspace_root=workspace, execute=False)
    assert exit_code == 2


def test_profile_id_never_enters_transport_request_or_authorization(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """The profile id and pin field never appear in any provider request
    payload, header surface, or credential line (spec Security tests)."""
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "cross-domain-v1")
    result = execute(
        workspace, run_id, StubTransport(_stub_responses(workspace, inputs))
    )
    assert result["status"] == "sealed"

    run_root = _run_root(workspace, run_id)
    # The recorded private request.json artifacts carry the model-visible
    # prompt only: no profile id, no Authorization material.
    for attempt_file in sorted(
        run_root.glob("artifacts/operations/*/attempts/*/request.json")
    ):
        body = attempt_file.read_text(encoding="utf-8")
        assert "cross-domain-v1" not in body
        assert "prompt_profile" not in body
        assert "bundle_sha256" not in body
        assert "Authorization" not in body
        assert "Bearer" not in body
    # The canonical request/admission documents carry the closed pin field,
    # but never any credential-shaped value.
    for name in ("request.json", "admission.json"):
        doc = parse_json_bytes((run_root / name).read_bytes(), label=name)
        assert doc["prompt_profile"]["profile_id"] in (
            "ml-baseline-v1",
            "cross-domain-v1",
        )
    admission_text = (run_root / "admission.json").read_text(encoding="utf-8")
    assert "Bearer" not in admission_text
    assert "sk-" not in admission_text


def test_legacy_request_cannot_inject_a_profile_field(
    tmp_path: Path, monkeypatch: Any, helpers: Any
) -> None:
    """A legacy v1.0.0 request.json carrying prompt_profile fails closed in
    the Evidence Chain validator (injection attempt)."""
    from ai_scientist.ideation.canonical import canonical_json_bytes as _cjb

    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "ml-baseline-v1")
    result = execute(
        workspace, run_id, StubTransport(_stub_responses(workspace, inputs))
    )
    assert result["status"] == "sealed"

    run_root = _run_root(workspace, run_id)
    request_path = run_root / "request.json"
    data = json.loads(request_path.read_text(encoding="utf-8"))
    data.pop("prompt_profile", None)
    data["schema_version"] = "run-request-v1.0.0"
    data["prompt_profile"] = {"profile_id": "cross-domain-v1"}
    request_path.write_bytes(_cjb(data))
    with pytest.raises(IdeationInputError, match="RUN_CORRUPT"):
        validate_evidence_chain(workspace, run_id, check_sealed=True)


def test_new_run_accepts_no_extra_configuration_keys() -> None:
    """The parser exposes no model/provider/effort/tokens overrides."""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ai_scientist" / "perform_ideation_temp_free.py"),
            "new-run",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for forbidden in (
        "--reasoning-effort",
        "--max-tokens",
        "--model",
        "--provider",
        "--base-url",
        "--system-prompt",
        "--prompt-path",
        "--prompt-text",
        "--temperature",
    ):
        assert forbidden not in result.stdout


# ==========================================================================
# Resume: admission-driven profile reconstruction, drift rejection
# ==========================================================================


@pytest.mark.parametrize(("profile", "profile_id"), PROFILE_PARAMS)
def test_suspended_run_resumes_from_admitted_profile_without_model_default(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
    profile,
    profile_id: str,
) -> None:
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, profile_id)

    # Interrupt mid-round-0 transport.
    with pytest.raises(RunInterrupted):
        execute(workspace, run_id, _CapturingStubTransport([_kill_sigint]))
    run_root = _run_root(workspace, run_id)
    assert not (run_root / "seal.json").exists()

    # Pin the CURRENT default to the *other* profile: a resumed run must
    # ignore the mutable default and rebuild from the admission.
    other_profile = (
        CROSS_DOMAIN_V1_REF if profile_id == "ml-baseline-v1" else ML_BASELINE_V1_REF
    )
    monkeypatch.setattr(profiles, "DEFAULT_PROMPT_PROFILE_ID", other_profile.profile_id)

    capturing = _CapturingStubTransport(
        [
            _search_stub(),
            _finalize_stub_with_paper(workspace, inputs["corpus"]),
        ]
    )
    result = resume(helpers, workspace, run_id, capturing, monkeypatch)
    assert result["status"] == "sealed"
    assert result["terminal_outcome"] == "success"
    assert result["idea_count"] == 1

    sent = capturing.sent_requests
    # Round 0 was re-executed by the resumed writer; both rounds used the
    # admitted profile rendering, never the mutable default.
    assert sent[0]["messages"][0]["content"] == profiles.render_system_prompt(profile)
    assert sent[-1]["messages"][0]["content"] == profiles.render_system_prompt(profile)

    # Validation and export stay green for the resumed run.
    assert (
        validate_evidence_chain(workspace, run_id, check_sealed=True)["status"]
        == "valid"
    )
    export = export_sanitized_evidence(workspace, run_id)
    assert export["status"] == "exported"


def test_resume_rejects_registry_drift(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """Registry drift after admission fails closed before any model round."""
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "cross-domain-v1")
    with pytest.raises(RunInterrupted):
        execute(workspace, run_id, _CapturingStubTransport([_kill_sigint]))

    monkeypatch.setattr(contract, "PROMPT_PROFILE_REGISTRY_SHA256", "0" * 64)
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_REGISTRY_MISMATCH"):
        resume(helpers, workspace, run_id, _CapturingStubTransport([]), monkeypatch)
    assert not (_run_root(workspace, run_id) / "seal.json").exists()


def test_resume_rejects_profile_hash_mismatch_in_admission(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """A tampered admission profile bundle hash cannot resume.

    The tamper is re-pinned into the chain (canonical rewrite of the
    admission hash in the `admitted` event and seal) so the failure comes
    from the profile pin validation itself, not merely from the hash pin.
    """
    from ai_scientist.ideation.canonical import canonical_json_bytes as _cjb

    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "cross-domain-v1")
    with pytest.raises(RunInterrupted):
        execute(workspace, run_id, _CapturingStubTransport([_kill_sigint]))

    run_root = _run_root(workspace, run_id)
    admission_path = run_root / "admission.json"
    data = json.loads(admission_path.read_text(encoding="utf-8"))
    data["prompt_profile"]["bundle_sha256"] = "4" * 64
    admission_bytes = _cjb(data)
    admission_path.write_bytes(admission_bytes)
    admission_sha = sha256_bytes(admission_bytes)

    _repin_admission_hash(run_root, admission_sha)
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_HASH_MISMATCH"):
        resume(helpers, workspace, run_id, _CapturingStubTransport([]), monkeypatch)
    assert not (run_root / "seal.json").exists()


def _repin_admission_hash(run_root: Path, admission_sha: str) -> None:
    """Rewrite the admission-hash pins in the event chain and seal to a new
    canonical admission document (tamper-simulation helper).

    Rehashes every subsequent event so the chain stays internally valid: the
    tested failure must come from the profile pin validation, not the hash
    chain.
    """
    from ai_scientist.ideation.canonical import canonical_json_bytes as _cjb
    from ai_scientist.ideation.canonical import parse_json_bytes

    event_paths = sorted((run_root / "events").glob("*.json"))
    prev_hash = None
    for event_path in event_paths:
        event = parse_json_bytes(event_path.read_bytes(), label=event_path.name)
        event["prev_event_hash"] = prev_hash
        if event.get("event_type") == "admitted":
            event["admission_sha256"] = admission_sha
        without_hash = {k: v for k, v in event.items() if k != "event_hash"}
        event["event_hash"] = sha256_bytes(_cjb(without_hash))
        prev_hash = event["event_hash"]
        event_path.write_bytes(_cjb(event))
    seal_path = run_root / "seal.json"
    if seal_path.is_file():
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
        seal["admission_sha256"] = admission_sha
        last_event = parse_json_bytes(event_paths[-1].read_bytes(), label="final event")
        seal["final_event"] = {
            "event_hash": last_event["event_hash"],
            "event_seq": last_event["event_seq"],
        }
        seal_path.write_bytes(_cjb(seal))


def test_resume_rejects_attempted_profile_change_via_request_tamper(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """Swapping the profile inside request.json fails closed: the request
    profile pin must equal the admission profile pin."""
    from ai_scientist.ideation.canonical import canonical_json_bytes as _cjb

    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "ml-baseline-v1")
    with pytest.raises(RunInterrupted):
        execute(workspace, run_id, _CapturingStubTransport([_kill_sigint]))

    run_root = _run_root(workspace, run_id)
    request_path = run_root / "request.json"
    data = json.loads(request_path.read_text(encoding="utf-8"))
    data["prompt_profile"]["profile_id"] = "cross-domain-v1"
    data["prompt_profile"]["bundle_sha256"] = profiles.profile_bundle_sha256(
        CROSS_DOMAIN_V1_REF
    )
    request_bytes = _cjb(data)
    request_path.write_bytes(request_bytes)
    request_sha = sha256_bytes(request_bytes)

    # Re-pin request bytes into the admission + chain so the run stays
    # internally consistent and the rejection comes from the profile
    # cross-check, not the outer hash pin.
    admission_path = run_root / "admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["request_sha256"] = request_sha
    # The admission keeps its ORIGINAL ml-baseline pin: the swapped request
    # profile now disagrees with the admission profile pin.
    admission_bytes = _cjb(admission)
    admission_path.write_bytes(admission_bytes)
    admission_sha = sha256_bytes(admission_bytes)

    event_paths = sorted((run_root / "events").glob("*.json"))
    prev_hash = None
    for event_path in event_paths:
        event = parse_json_bytes(event_path.read_bytes(), label=event_path.name)
        event["prev_event_hash"] = prev_hash
        if event.get("event_type") == "preflight_started":
            event["request_sha256"] = request_sha
        if event.get("event_type") == "admitted":
            event["admission_sha256"] = admission_sha
        without_hash = {k: v for k, v in event.items() if k != "event_hash"}
        event["event_hash"] = sha256_bytes(_cjb(without_hash))
        prev_hash = event["event_hash"]
        event_path.write_bytes(_cjb(event))
    seal_path = run_root / "seal.json"
    if seal_path.is_file():
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
        seal["request_sha256"] = request_sha
        seal["admission_sha256"] = admission_sha
        last_event = parse_json_bytes(event_paths[-1].read_bytes(), label="final event")
        seal["final_event"] = {
            "event_hash": last_event["event_hash"],
            "event_seq": last_event["event_seq"],
        }
        seal_path.write_bytes(_cjb(seal))

    with pytest.raises(
        IdeationInputError,
        match="The request profile pin does not match the admission pin",
    ):
        resume(helpers, workspace, run_id, _CapturingStubTransport([]), monkeypatch)


def test_resume_of_legacy_admission_stays_baseline(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """A legacy v1.0.0 admission without profile fields resumes as baseline
    even when the current default is the challenger."""
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "ml-baseline-v1")
    with pytest.raises(RunInterrupted):
        execute(workspace, run_id, _CapturingStubTransport([_kill_sigint]))

    # Degrade the run to legacy evidence: strip profile pins and downgrade
    # schema versions (a historical run never had these fields).
    run_root = _run_root(workspace, run_id)
    for name in ("request.json", "admission.json"):
        path = run_root / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("prompt_profile", None)
        data["schema_version"] = (
            f"run-{'request' if name.startswith('request') else 'admission'}-v1.0.0"
        )
        path.write_bytes(
            (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
    # The admission hash pinned in the chain no longer matches the degraded
    # document, so a raw resume must fail closed — legacy documents are
    # interpreted at validation/export level, not rewritten in place.
    with pytest.raises(IdeationInputError, match="ADMISSION_TAMPERED"):
        resume(helpers, workspace, run_id, _CapturingStubTransport([]), monkeypatch)
    monkeypatch.setattr(profiles, "DEFAULT_PROMPT_PROFILE_ID", "cross-domain-v1")
    assert (
        profiles.resolve_admission_profile(
            {"schema_version": "run-admission-v1.0.0"}
        ).profile_id
        == "ml-baseline-v1"
    )


def test_legacy_sealed_run_validates_and_exports_as_baseline(
    tmp_path: Path,
    monkeypatch: Any,
    helpers: Any,
) -> None:
    """A fully legacy (v1.0.0) sealed run keeps validating and exporting;
    its sanitized profile identity is ml-baseline-v1 without profile pins."""
    workspace, inputs = _prepared_workspace(tmp_path, helpers)
    run_id = admit(helpers, workspace, inputs, monkeypatch, "ml-baseline-v1")
    result = execute(
        workspace, run_id, StubTransport(_stub_responses(workspace, inputs))
    )
    assert result["status"] == "sealed"

    run_root = _run_root(workspace, run_id)
    for name in ("request.json", "admission.json"):
        path = run_root / name
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("prompt_profile", None)
        data["schema_version"] = (
            "run-request-v1.0.0" if name == "request.json" else "run-admission-v1.0.0"
        )
        path.write_bytes(
            (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
    # Re-pin the chain to the degraded documents (simulating a legacy run's
    # canonical bytes): recompute the request/admission hashes and rewrite the
    # chain pins. This mirrors what a real legacy run looks like on disk.
    from ai_scientist.ideation.canonical import canonical_json_bytes as _cjb

    request_sha = sha256_bytes((run_root / "request.json").read_bytes())
    # The legacy admission re-binds the degraded request bytes, exactly like a
    # real legacy admission document does.
    admission_doc = json.loads(
        (run_root / "admission.json").read_text(encoding="utf-8")
    )
    admission_doc["request_sha256"] = request_sha
    (run_root / "admission.json").write_bytes(_cjb(admission_doc))
    admission_sha = sha256_bytes((run_root / "admission.json").read_bytes())
    events_dir = run_root / "events"
    event_paths = sorted(events_dir.glob("*.json"))

    prev_hash = None
    for index, event_path in enumerate(event_paths, start=1):
        event = parse_json_bytes(event_path.read_bytes(), label=event_path.name)
        event["prev_event_hash"] = prev_hash
        if event.get("event_type") == "preflight_started":
            event["request_sha256"] = request_sha
        if event.get("event_type") == "admitted":
            event["admission_sha256"] = admission_sha
        event["event_seq"] = index
        without_hash = {k: v for k, v in event.items() if k != "event_hash"}
        event["event_hash"] = sha256_bytes(_cjb(without_hash))
        prev_hash = event["event_hash"]
        event_path.write_bytes(_cjb(event))
    seal_path = run_root / "seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["request_sha256"] = request_sha
    seal["admission_sha256"] = admission_sha
    last_event = parse_json_bytes(
        event_paths[-1].read_bytes(), label=event_paths[-1].name
    )
    seal["final_event"] = {
        "event_hash": last_event["event_hash"],
        "event_seq": last_event["event_seq"],
    }
    seal_path.write_bytes(_cjb(seal))

    validation = validate_evidence_chain(workspace, run_id, check_sealed=True)
    assert validation["status"] == "valid"
    export = export_sanitized_evidence(workspace, run_id)
    assert export["status"] == "exported"
    manifest = parse_json_bytes(
        (workspace / "evidence/ideation-runs" / run_id / "manifest.json").read_bytes(),
        label="manifest.json",
    )
    assert manifest["prompt_profile"]["profile_id"] == "ml-baseline-v1"
    assert manifest["prompt_profile"][
        "bundle_sha256"
    ] == profiles.profile_bundle_sha256(ML_BASELINE_V1_REF)
