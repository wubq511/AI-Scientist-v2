"""Prompt Profile contract tests (ticket 01).

Proves the closed, versioned Prompt Profile seam:
- exactly two registered profile ids; everything else fails closed
- byte-exact baseline preservation (golden SHA-256 of the three templates)
- the challenger carries the approved domain-neutral semantics and no
  hard-coded ML venue / algorithm / metric mandates
- unchanged shared tool/action scaffold, generation template, tool names
- hash-pinned registry; template drift fails closed
- request/admission profile-field validation and legacy interpretation
- profile fields never enter sanitized export surfaces (allowlist key check)

Zero network, zero cost, no model calls.
"""

from __future__ import annotations

import json

import pytest

from ai_scientist.ideation import contract, profiles
from ai_scientist.ideation.canonical import canonical_json_bytes
from ai_scientist.ideation.errors import IdeationInputError

BASELINE_SYSTEM_SHA256 = (
    "d2c00053fbb9617db5c33f2905c0b0b2a55b811d8fc965b149bb7c6fe3b0c62d"
)
BASELINE_GENERATION_SHA256 = (
    "b933e80e7880d8db0a2cb7eca9a2923179fa4cb9713f51bd83d0fadce709d035"
)
BASELINE_REFLECTION_SHA256 = (
    "8ed8f5d5b9ad75ef0d53aae832d5f24583fee52b8de302491a5a86e55aec47f7"
)


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- Closed identity -------------------------------------------------------


def test_only_two_profile_ids_are_registered() -> None:
    assert profiles.REGISTERED_PROMPT_PROFILE_IDS == (
        "ml-baseline-v1",
        "cross-domain-v1",
    )
    assert profiles.DEFAULT_PROMPT_PROFILE_ID == "ml-baseline-v1"


def test_production_default_template_matches_head_baseline_prompt() -> None:
    """The default profile is byte-identical to the pre-profile production prompt.

    The in-tree legacy constants (controller.IDEA_GENERATION_PROMPT /
    controller.IDEA_REFLECTION_PROMPT) are the pinned evidence of the
    pre-ticket production bytes: this test proves they still carry the
    original golden hashes, and the profile registry reuses them verbatim.
    """
    from ai_scientist.ideation.controller import (
        IDEA_GENERATION_PROMPT,
        IDEA_REFLECTION_PROMPT,
    )

    assert _sha(IDEA_GENERATION_PROMPT) == BASELINE_GENERATION_SHA256
    assert _sha(IDEA_REFLECTION_PROMPT) == BASELINE_REFLECTION_SHA256


def test_retained_legacy_constants_equal_registered_baseline_templates() -> None:
    """The retained controller constants cannot silently drift from the
    registered baseline profile: both must stay byte-identical."""
    from ai_scientist.ideation.controller import (
        IDEA_GENERATION_PROMPT,
        IDEA_REFLECTION_PROMPT,
        build_system_prompt,
        build_tool_catalog,
    )

    baseline = profiles.resolve_profile("ml-baseline-v1")
    assert baseline.generation_template == IDEA_GENERATION_PROMPT
    assert baseline.reflection_template == IDEA_REFLECTION_PROMPT
    assert build_system_prompt() == profiles.render_system_prompt(baseline)
    descriptions, names = build_tool_catalog()
    assert descriptions == baseline.tool_descriptions_template
    assert names == baseline.tool_names_template


def test_baseline_profile_renderings_are_byte_stable_goldens() -> None:
    baseline = profiles.resolve_profile("ml-baseline-v1")
    assert _sha(profiles.render_system_prompt(baseline)) == BASELINE_SYSTEM_SHA256
    assert _sha(baseline.generation_template) == BASELINE_GENERATION_SHA256
    assert _sha(baseline.reflection_template) == BASELINE_REFLECTION_SHA256
    # Rendering the generation/reflection prompts with representative inputs
    # keeps the fixed workshop/diversity/tool-result framing.
    generation = profiles.render_generation_prompt(
        baseline, workshop_description="WORKSHOP", prev_ideas_string="P1"
    )
    assert generation.startswith(
        "WORKSHOP\n\nHere are the proposals that you have already generated:"
    )
    reflection = profiles.render_reflection_prompt(
        baseline, current_round=2, num_reflections=3, last_tool_results=""
    )
    assert reflection.startswith("Round 2/3.")
    assert "No new results." in reflection


def test_free_text_path_fragment_and_unknown_ids_fail_closed() -> None:
    for bad in [
        "gpt-4",
        "ml-baseline-v2",
        "cross-domain-v1x",
        "/path/to/prompt.txt",
        "free prompt text",
        "",
        "  cross-domain-v1  ",
    ]:
        with pytest.raises(IdeationInputError):
            profiles.resolve_profile(bad)
    with pytest.raises(IdeationInputError, match="UNKNOWN_PROMPT_PROFILE"):
        profiles.resolve_profile("ml-baseline-v1x")
    with pytest.raises(IdeationInputError):
        profiles.resolve_profile(None)
    with pytest.raises(IdeationInputError):
        profiles.resolve_profile({"profile_id": "ml-baseline-v1"})


# -- Baseline semantics ------------------------------------------------------


def test_baseline_profile_preserves_head_system_prompt_semantics() -> None:
    """The registered baseline keeps the pre-ticket production mandate tokens
    (proven once against HEAD in the golden-hash test above)."""
    baseline = profiles.render_system_prompt(profiles.ML_BASELINE_V1)
    assert "experienced AI researcher" in baseline
    assert "top ML conferences" in baseline
    assert "conference format" in baseline
    assert "precise algorithmic changes" in baseline
    assert "Include the evaluation metrics you would use" in baseline
    assert "academic lab" in baseline


# -- Cross-domain challenger semantics ----------------------------------------


def test_cross_domain_profile_implements_approved_semantics() -> None:
    challenger = profiles.resolve_profile("cross-domain-v1")
    system = profiles.render_system_prompt(challenger)
    # Approved canonical role and method text fragments.
    assert "multidisciplinary research scientist" in system
    assert (
        "do not assume the problem belongs to machine learning or that a "
        "computational method is required" in system
    )
    assert (
        "accounting for relevant resource, data, equipment, time, ethical, "
        "safety, and regulatory constraints" in system
    )
    assert (
        "Computational models, algorithms, benchmarks, and quantitative "
        "metrics should appear only when justified by the research question "
        "and literature" in system
    )
    # Field-neutral descriptions.
    assert "clear and informative title" in system
    assert "conference format" not in system
    assert "field-appropriate validation plan" in system
    assert (
        "experiments, observational studies, qualitative studies, simulations, "
        "computational analyses, formal analyses, or proofs" in system
    )
    assert "state the evidence that would support or falsify the proposal" in system
    # No ML-venue/algorithm/metric mandates.
    for forbidden in (
        "ML conferences",
        "publishable at top",
        "detail precise algorithmic changes",
        "Include the evaluation metrics you would use",
    ):
        assert forbidden not in system
    # Reflection carries the field-aware criterion.
    reflection = profiles.render_reflection_prompt(
        challenger, current_round=1, num_reflections=3, last_tool_results="results"
    )
    assert (
        "Check whether the proposed methods, evidence, and feasibility "
        "assumptions fit the scientific field" in reflection
    )
    assert "domain-method mismatch" in reflection


def test_cross_domain_profile_keeps_unshared_scaffold_byte_identical() -> None:
    baseline = profiles.resolve_profile("ml-baseline-v1")
    challenger = profiles.resolve_profile("cross-domain-v1")
    assert challenger.generation_template == baseline.generation_template
    assert challenger.tool_names_template == baseline.tool_names_template
    # Shared scaffold: everything after the tool-description block is the
    # same for both profiles.
    scaffold_suffix = lambda profile: profile.system_template.split(  # noqa: E731
        "You have access to the following tools:"
    )[1]
    assert scaffold_suffix(baseline) == scaffold_suffix(challenger)
    # Tool/action surface: exactly the two visible actions.
    for rendered in (
        profiles.render_system_prompt(baseline),
        profiles.render_system_prompt(challenger),
    ):
        assert 'exactly one of "SearchLiterature", "FinalizeIdea"' in rendered
        assert "SearchSemanticScholar" not in rendered
        assert "ExecutePythonInterpreter" not in rendered
        assert '"paper_id_1"' in rendered
        assert '"grounding"' in rendered


# -- Registry hash pin --------------------------------------------------------


def test_registry_is_hash_pinned_and_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profiles.assert_registry_integrity()
    monkeypatch.setattr(contract, "PROMPT_PROFILE_REGISTRY_SHA256", "0" * 64)
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_REGISTRY_MISMATCH"):
        profiles.resolve_profile("ml-baseline-v1")
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_REGISTRY_MISMATCH"):
        profiles.assert_registry_integrity()


def test_profile_bundle_hashes_are_distinct_and_stable() -> None:
    baseline_hash = profiles.profile_bundle_sha256(profiles.ML_BASELINE_V1)
    challenger_hash = profiles.profile_bundle_sha256(profiles.CROSS_DOMAIN_V1)
    assert baseline_hash != challenger_hash
    assert len(baseline_hash) == 64 and len(challenger_hash) == 64
    # Re-computation is deterministic.
    assert profiles.profile_bundle_sha256(profiles.ML_BASELINE_V1) == baseline_hash


# -- Request/admission pin field validation ------------------------------------


def _valid_field(profile: profiles.PromptProfile) -> dict[str, str]:
    return {
        "bundle_sha256": profiles.profile_bundle_sha256(profile),
        "contract_version": profile.contract_version,
        "profile_id": profile.profile_id,
        "registry_sha256": profiles.profile_registry_sha256(),
    }


def test_valid_profile_field_round_trips_for_both_profiles() -> None:
    for profile in (profiles.ML_BASELINE_V1, profiles.CROSS_DOMAIN_V1):
        field = profiles.validate_profile_field(
            _valid_field(profile), label="test.prompt_profile"
        )
        assert field["profile_id"] == profile.profile_id


def test_profile_field_rejects_unknown_or_drifted_values() -> None:
    good = _valid_field(profiles.ML_BASELINE_V1)

    unknown = dict(good, profile_id="cross-domain-v2")
    with pytest.raises(IdeationInputError, match="UNKNOWN_PROMPT_PROFILE"):
        profiles.validate_profile_field(unknown, label="f")

    wrong_contract = dict(good, contract_version="prompt-profile-contract-v0.9")
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_CONTRACT_MISMATCH"):
        profiles.validate_profile_field(wrong_contract, label="f")

    drifted_bundle = dict(good, bundle_sha256="1" * 64)
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_HASH_MISMATCH"):
        profiles.validate_profile_field(drifted_bundle, label="f")

    bundle_swapped = dict(
        good, bundle_sha256=profiles.profile_bundle_sha256(profiles.CROSS_DOMAIN_V1)
    )
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_HASH_MISMATCH"):
        profiles.validate_profile_field(bundle_swapped, label="f")

    drifted_registry = dict(good, registry_sha256="2" * 64)
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_REGISTRY_MISMATCH"):
        profiles.validate_profile_field(drifted_registry, label="f")

    with pytest.raises(IdeationInputError, match="INVALID_SCHEMA"):
        profiles.validate_profile_field(dict(good, extra_key="x"), label="f")
    with pytest.raises(IdeationInputError, match="INVALID_SCHEMA"):
        profiles.validate_profile_field(
            {k: v for k, v in good.items() if k != "profile_id"}, label="f"
        )


def test_legacy_admission_interprets_ml_baseline_and_never_upgrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = {"schema_version": "run-admission-v1.0.0"}
    assert profiles.resolve_admission_profile(legacy).profile_id == "ml-baseline-v1"
    # The legacy interpretation does not follow a mutable default.
    monkeypatch.setattr(profiles, "DEFAULT_PROMPT_PROFILE_ID", "cross-domain-v1")
    assert profiles.resolve_admission_profile(legacy).profile_id == "ml-baseline-v1"


def test_legacy_admission_cannot_carry_or_inject_a_profile_field() -> None:
    legacy_with_field = {
        "schema_version": "run-admission-v1.0.0",
        "prompt_profile": {"profile_id": "cross-domain-v1"},
    }
    with pytest.raises(IdeationInputError, match="INVALID_SCHEMA"):
        profiles.resolve_admission_profile(legacy_with_field)


def test_new_schema_admission_requires_the_profile_pin() -> None:
    with pytest.raises(IdeationInputError, match="INVALID_SCHEMA"):
        profiles.resolve_admission_profile({"schema_version": "run-admission-v1.1.0"})


def test_admission_profile_resolution_rejects_drift() -> None:
    field = _valid_field(profiles.CROSS_DOMAIN_V1)
    admission = {"schema_version": "run-admission-v1.1.0", "prompt_profile": field}
    assert profiles.resolve_admission_profile(admission).profile_id == "cross-domain-v1"
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_HASH_MISMATCH"):
        profiles.resolve_admission_profile(
            {"prompt_profile": dict(field, bundle_sha256="3" * 64)}
        )
    with pytest.raises(IdeationInputError, match="UNKNOWN_PROMPT_PROFILE"):
        profiles.resolve_admission_profile(
            {"prompt_profile": dict(field, profile_id="unknown-profile")}
        )
    with pytest.raises(IdeationInputError, match="PROMPT_PROFILE_CONTRACT_MISMATCH"):
        profiles.resolve_admission_profile(
            {
                "prompt_profile": dict(
                    field, contract_version="prompt-profile-contract-v0"
                )
            }
        )


# -- Sanitized-export privacy boundary -----------------------------------------


def test_profile_pin_keys_stay_out_of_sanitized_export_allowlists() -> None:
    from ai_scientist.ideation import evidence

    for key in (
        "bundle_sha256",
        "prompt_profile",
        "prompt_profile_id",
        "profile_id",
        "contract_version",
        "registry_sha256",
    ):
        assert key not in evidence.ALLOWED_EVENT_PAYLOAD_KEYS
    # Only safe identity/hash keys may appear via the new sanitized manifest
    # section; prompt/template text keys are forbidden by the existing scan set.
    for forbidden in (
        "prompt",
        "system_template",
        "reflection_template",
        "generation_template",
        "tool_descriptions_template",
        "tool_names_template",
    ):
        assert forbidden in evidence.FORBIDDEN_KEY_PATTERNS


def test_canonical_profile_document_contains_no_free_prompt_surface() -> None:
    document = profiles._registry_document()
    assert set(document) == {"ml-baseline-v1", "cross-domain-v1"}
    for entry in document.values():
        assert set(entry) == {"bundle_sha256", "contract_version"}
    # The canonical registry bytes are canonical JSON (sorted, compact).
    assert canonical_json_bytes(document) == canonical_json_bytes(
        json.loads(canonical_json_bytes(document))
    )
