"""Closed, versioned Prompt Profiles for Ideation Runs (ticket 01).

A Prompt Profile is a closed, versioned run input: the only initial values
are `ml-baseline-v1` (byte-exact preservation of the current production
prompt semantics) and `cross-domain-v1` (the spec-approved domain-neutral
challenger). Callers cannot supply prompt bytes, paths, fragments, templates
or unregistered identifiers; the resolved profile id, profile contract
version, and the SHA-256 of the complete canonical prompt bundle are pinned
into the Run Request and Run Admission.

The profile registry is an in-code, hash-pinned constant: the registry SHA-256
recorded in `contract.py` fails closed against any template drift, so replay
never guesses which prompt bytes were model-visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import contract
from .canonical import canonical_json_bytes, sha256_bytes
from .errors import fail
from .run_store import (
    LEGACY_RUN_ADMISSION_SCHEMA_VERSION,
    RUN_ADMISSION_SCHEMA_VERSION,
)
from .schema import stage_id as parse_profile_id

ADMISSION_PROFILE_FIELD_KEYS = frozenset(
    {"profile_id", "contract_version", "bundle_sha256", "registry_sha256"}
)

# Shared generation prompt: Workshop injection order, previous-idea diversity
# framing, and whitespace stay byte-identical for every registered profile.
GENERATION_TEMPLATE = """{workshop_description}

Here are the proposals that you have already generated:

'''
{prev_ideas_string}
'''

Begin by generating an interestingly new high-level research proposal that differs from what you have previously proposed.
"""

# Baseline reflection prompt verbatim (production baseline semantics).
BASELINE_REFLECTION_TEMPLATE = """Round {current_round}/{num_reflections}.

In your thoughts, first carefully consider the quality, novelty, and feasibility of the proposal you just created.
Include any other factors that you think are important in evaluating the proposal.
Ensure the proposal is clear and concise, and the JSON is in the correct format.
Do not make things overly complicated.
In the next attempt, try to refine and improve your proposal.
Stick to the spirit of the original idea unless there are glaring issues.

If you have new information from tools, such as literature search results, incorporate them into your reflection and refine your proposal accordingly.

Results from your last action (if any):

{last_tool_results}
"""

# Cross-domain reflection adds the approved field-aware criterion to the
# unchanged baseline reflection text.
CROSS_DOMAIN_REFLECTION_TEMPLATE = """Round {current_round}/{num_reflections}.

In your thoughts, first carefully consider the quality, novelty, and feasibility of the proposal you just created.
Include any other factors that you think are important in evaluating the proposal.
Check whether the proposed methods, evidence, and feasibility assumptions fit the scientific field of the proposal, and correct any domain-method mismatch.
Ensure the proposal is clear and concise, and the JSON is in the correct format.
Do not make things overly complicated.
In the next attempt, try to refine and improve your proposal.
Stick to the spirit of the original idea unless there are glaring issues.

If you have new information from tools, such as literature search results, incorporate them into your reflection and refine your proposal accordingly.

Results from your last action (if any):

{last_tool_results}
"""

# Model-visible tool surface and action/JSON protocol scaffold: shared by
# every registered profile (SearchLiterature + FinalizeIdea only, seven-field
# IDEA JSON, Declared Grounding).
SHARED_SYSTEM_SCAFFOLD = """

You have access to the following tools:

{tool_descriptions}

Respond in the following format:

ACTION:
<The action to take, exactly one of {tool_names_str}>

ARGUMENTS:
<If ACTION is "SearchLiterature", provide the search query as {{"query": "your search query"}}. If ACTION is "FinalizeIdea", provide the idea details and grounding as {{"idea": {{ ... }}, "grounding": ["paper_id_1", ...]}} with the IDEA JSON specified below.>

If you choose to finalize your idea, provide the IDEA JSON in the arguments:

IDEA JSON:
```json
{{
  "idea": {{
    "Name": "...",
    "Title": "...",
    "Short Hypothesis": "...",
    "Related Work": "...",
    "Abstract": "...",
    "Experiments": [
      "..."
    ],
    "Risk Factors and Limitations": [
      "..."
    ]
  }},
  "grounding": [
    "paper_id_1"
  ]
}}
```

Ensure the JSON is properly formatted for automatic parsing.

Note: You should perform at least one literature search before finalizing your idea to ensure it is well-informed by existing research."""

BASELINE_TOOL_DESCRIPTIONS_TEMPLATE = """- **SearchLiterature**: Search the literature for relevant research papers and background work. Provide a concise natural language search query as {"query": "your query"}.

- **FinalizeIdea**: Finalize your idea by providing the idea details and declared grounding.

The IDEA JSON should include the following fields:
- "Name": A short descriptor of the idea. Lowercase, no spaces, underscores allowed.
- "Title": A catchy and informative title for the proposal.
- "Short Hypothesis": A concise statement of the main hypothesis or research question. Clarify the need for this specific direction, ensure this is the best setting to investigate this idea, and there are not obvious other simpler ways to answer the question.
- "Related Work": A brief discussion of the most relevant related work and how the proposal clearly distinguishes from it, and is not a trivial extension.
- "Abstract": An abstract that summarizes the proposal in conference format (approximately 250 words).
- "Experiments": A list of experiments that would be conducted to validate the proposal. Ensure these are simple and feasible. Be specific in exactly how you would test the hypothesis, and detail precise algorithmic changes. Include the evaluation metrics you would use.
- "Risk Factors and Limitations": A list of potential risks and limitations of the proposal."""

TOOL_NAMES_TEMPLATE = '"SearchLiterature", "FinalizeIdea"'


@dataclass(frozen=True, slots=True)
class PromptProfile:
    """One closed, versioned prompt profile identity with its exact templates."""

    profile_id: str
    contract_version: str
    system_template: str
    generation_template: str
    reflection_template: str
    tool_descriptions_template: str
    tool_names_template: str


ML_BASELINE_V1_SYSTEM_TEMPLATE = (
    "You are an experienced AI researcher who aims to propose high-impact "
    "research ideas resembling exciting grant proposals. Feel free to propose "
    "any novel ideas or experiments; make sure they are novel. Be very "
    "creative and think out of the box. Each proposal should stem from a "
    "simple and elegant question, observation, or hypothesis about the topic. "
    "For example, they could involve very interesting and simple "
    "interventions or investigations that explore new possibilities or "
    "challenge existing assumptions. Clearly clarify how the proposal "
    "distinguishes from the existing literature.\n"
    "\n"
    "Ensure that the proposal does not require resources beyond what an "
    "academic lab could afford. These proposals should lead to papers that "
    "are publishable at top ML conferences." + SHARED_SYSTEM_SCAFFOLD
)

CROSS_DOMAIN_V1_SYSTEM_TEMPLATE = (
    "You are an experienced multidisciplinary research scientist. Propose "
    "rigorous, high-impact research ideas appropriate to the scientific field "
    "described by the Workshop and the retrieved literature. Be creative, but "
    "do not assume the problem belongs to machine learning or that a "
    "computational method is required. Each proposal should stem from a clear "
    "question, observation, or hypothesis and explain how it differs "
    "materially from the existing literature.\n"
    "\n"
    "Use methods and evidence appropriate to the field. Computational models, "
    "algorithms, benchmarks, and quantitative metrics should appear only when "
    "justified by the research question and literature. Keep the proposal "
    "feasible for a realistic research team, accounting for relevant "
    "resource, data, equipment, time, ethical, safety, and regulatory "
    "constraints.\n" + SHARED_SYSTEM_SCAFFOLD
)

CROSS_DOMAIN_TOOL_DESCRIPTIONS_TEMPLATE = """- **SearchLiterature**: Search the literature for relevant research papers and background work. Provide a concise natural language search query as {"query": "your query"}.

- **FinalizeIdea**: Finalize your idea by providing the idea details and declared grounding.

The IDEA JSON should include the following fields:
- "Name": A short descriptor of the idea. Lowercase, no spaces, underscores allowed.
- "Title": A clear and informative title for the proposal.
- "Short Hypothesis": A concise statement of the main hypothesis or research question. Clarify the need for this specific direction, ensure this is the best setting to investigate this idea, and there are not obvious other simpler ways to answer the question.
- "Related Work": A brief discussion of the most relevant related work and how the proposal clearly distinguishes from it, and is not a trivial extension.
- "Abstract": An abstract that summarizes the research idea in approximately 250 words, covering the research question, motivation, approach, expected contribution, and the validation logic of the proposal.
- "Experiments": A concrete field-appropriate validation plan for the proposal. Activities may include experiments, observational studies, qualitative studies, simulations, computational analyses, formal analyses, or proofs, as appropriate to the field. For each activity, state the evidence that would support or falsify the proposal, and specify outcomes, measures, or evaluation criteria only where appropriate to the field. Ensure the plan is feasible for a realistic research team, accounting for relevant resource, data, equipment, time, ethical, safety, and regulatory constraints.
- "Risk Factors and Limitations": A list of potential risks and limitations of the proposal."""

ML_BASELINE_V1 = PromptProfile(
    profile_id="ml-baseline-v1",
    contract_version=contract.PROMPT_PROFILE_CONTRACT_VERSION,
    system_template=ML_BASELINE_V1_SYSTEM_TEMPLATE,
    generation_template=GENERATION_TEMPLATE,
    reflection_template=BASELINE_REFLECTION_TEMPLATE,
    tool_descriptions_template=BASELINE_TOOL_DESCRIPTIONS_TEMPLATE,
    tool_names_template=TOOL_NAMES_TEMPLATE,
)

CROSS_DOMAIN_V1 = PromptProfile(
    profile_id="cross-domain-v1",
    contract_version=contract.PROMPT_PROFILE_CONTRACT_VERSION,
    system_template=CROSS_DOMAIN_V1_SYSTEM_TEMPLATE,
    generation_template=GENERATION_TEMPLATE,
    reflection_template=CROSS_DOMAIN_REFLECTION_TEMPLATE,
    tool_descriptions_template=CROSS_DOMAIN_TOOL_DESCRIPTIONS_TEMPLATE,
    tool_names_template=TOOL_NAMES_TEMPLATE,
)

REGISTERED_PROMPT_PROFILE_IDS: tuple[str, ...] = (
    ML_BASELINE_V1.profile_id,
    CROSS_DOMAIN_V1.profile_id,
)

# The production default stays pinned to the baseline until an approved
# Promotion Gate decision opens a new Design Epoch.
DEFAULT_PROMPT_PROFILE_ID = ML_BASELINE_V1.profile_id


# The registry document is deterministic from in-code constants; compute it
# once at import so every resolution is a cheap dict lookup plus one hash
# comparison instead of re-canonicalizing all templates.
def _bundle_sha256_for(profile: PromptProfile, *, cache: dict[str, str]) -> str:
    if profile.profile_id in cache:
        return cache[profile.profile_id]
    return sha256_bytes(
        canonical_json_bytes(
            {
                "contract_version": profile.contract_version,
                "generation_template": profile.generation_template,
                "reflection_template": profile.reflection_template,
                "system_template": profile.system_template,
                "tool_descriptions_template": profile.tool_descriptions_template,
                "tool_names_template": profile.tool_names_template,
            }
        )
    )


_BUNDLE_SHA256_CACHE: dict[str, str] = {
    profile.profile_id: _bundle_sha256_for(profile, cache={})
    for profile in (ML_BASELINE_V1, CROSS_DOMAIN_V1)
}
_REGISTRY_DOCUMENT: dict[str, dict[str, str]] = {
    profile.profile_id: {
        "bundle_sha256": _BUNDLE_SHA256_CACHE[profile.profile_id],
        "contract_version": profile.contract_version,
    }
    for profile in (ML_BASELINE_V1, CROSS_DOMAIN_V1)
}
_REGISTRY_PROFILE_BY_ID: dict[str, PromptProfile] = {
    profile.profile_id: profile for profile in (ML_BASELINE_V1, CROSS_DOMAIN_V1)
}


def _registry_document() -> dict[str, dict[str, str]]:
    return {profile_id: dict(entry) for profile_id, entry in _REGISTRY_DOCUMENT.items()}


def profile_bundle_sha256(profile: PromptProfile) -> str:
    """SHA-256 of the complete canonical prompt bundle of one profile."""
    if profile.profile_id in _BUNDLE_SHA256_CACHE:
        return _BUNDLE_SHA256_CACHE[profile.profile_id]
    return _bundle_sha256_for(profile, cache=_BUNDLE_SHA256_CACHE)


def profile_registry_sha256() -> str:
    """SHA-256 of the canonical two-profile registry document."""
    return sha256_bytes(canonical_json_bytes(_registry_document()))


def assert_registry_integrity() -> None:
    """Fail closed when the in-code registry drifted from its pinned hash."""
    observed = profile_registry_sha256()
    if observed != contract.PROMPT_PROFILE_REGISTRY_SHA256:
        fail(
            "PROMPT_PROFILE_REGISTRY_MISMATCH",
            "The prompt profile registry does not match its pinned SHA-256",
            expected=contract.PROMPT_PROFILE_REGISTRY_SHA256,
            observed=observed,
        )


def resolve_profile(profile_id: object) -> PromptProfile:
    """Resolve a closed profile id; anything else fails closed."""
    parsed = parse_profile_id(profile_id, label="prompt_profile_id")
    assert_registry_integrity()
    profile = _REGISTRY_PROFILE_BY_ID.get(parsed)
    if profile is None:
        fail(
            "UNKNOWN_PROMPT_PROFILE",
            "The prompt profile id is not registered",
            profile_id=parsed,
            registered=sorted(_REGISTRY_PROFILE_BY_ID),
        )
    return profile


def render_system_prompt(profile: PromptProfile) -> str:
    """Render the model-visible system prompt for one profile."""
    return profile.system_template.format(
        tool_descriptions=profile.tool_descriptions_template,
        tool_names_str=profile.tool_names_template,
    )


def render_generation_prompt(
    profile: PromptProfile,
    *,
    workshop_description: str,
    prev_ideas_string: str,
) -> str:
    """Render the round-0 generation prompt for one profile."""
    return profile.generation_template.format(
        workshop_description=workshop_description,
        prev_ideas_string=prev_ideas_string,
    )


def render_reflection_prompt(
    profile: PromptProfile,
    *,
    current_round: int,
    num_reflections: int,
    last_tool_results: str,
) -> str:
    """Render the reflection prompt for one profile."""
    return profile.reflection_template.format(
        current_round=current_round,
        last_tool_results=last_tool_results or "No new results.",
        num_reflections=num_reflections,
    )


def validate_profile_field(value: object, *, label: str) -> dict[str, Any]:
    """Validate a closed prompt-profile pin field (request/admission)."""
    from .schema import closed_object, nonempty_string, sha256 as parse_sha256

    field = closed_object(value, label=label, keys=set(ADMISSION_PROFILE_FIELD_KEYS))
    profile_id = parse_profile_id(field["profile_id"], label=f"{label}.profile_id")
    if field["contract_version"] != contract.PROMPT_PROFILE_CONTRACT_VERSION:
        fail(
            "PROMPT_PROFILE_CONTRACT_MISMATCH",
            "The recorded profile contract version is unsupported",
            label=label,
            contract_version=nonempty_string(
                field["contract_version"], label=f"{label}.contract_version"
            ),
        )
    parse_sha256(field["bundle_sha256"], label=f"{label}.bundle_sha256")
    parse_sha256(field["registry_sha256"], label=f"{label}.registry_sha256")
    profile = resolve_profile(profile_id)
    if field["bundle_sha256"] != profile_bundle_sha256(profile):
        fail(
            "PROMPT_PROFILE_HASH_MISMATCH",
            "The recorded profile bundle hash does not match the registry",
            label=label,
            profile_id=profile_id,
        )
    if field["registry_sha256"] != profile_registry_sha256():
        fail(
            "PROMPT_PROFILE_REGISTRY_MISMATCH",
            "The recorded profile registry hash is drifted",
            label=label,
            profile_id=profile_id,
        )
    return dict(field)


def resolve_admission_profile(admission: dict[str, Any]) -> PromptProfile:
    """Resolve the profile pinned by a Run Admission document.

    Legacy admissions created before Prompt Profiles are interpreted
    exclusively as `ml-baseline-v1`: the interpretation never follows a
    mutable default and never upgrades a historical run to the challenger.
    A legacy-schema admission that carries a prompt_profile field is an
    injection attempt and fails closed.
    """
    field = admission.get("prompt_profile")
    if field is None:
        if admission.get("schema_version") == LEGACY_RUN_ADMISSION_SCHEMA_VERSION:
            return ML_BASELINE_V1
        fail(
            "INVALID_SCHEMA",
            "A new-schema admission must pin a prompt profile",
            schema_version=admission.get("schema_version"),
        )
    if admission.get("schema_version") == LEGACY_RUN_ADMISSION_SCHEMA_VERSION:
        fail(
            "INVALID_SCHEMA",
            "A legacy admission cannot carry a prompt profile field",
        )
    validate_profile_field(field, label="admission.prompt_profile")
    return resolve_profile(field["profile_id"])


__all__ = [
    "CROSS_DOMAIN_V1",
    "DEFAULT_PROMPT_PROFILE_ID",
    "ML_BASELINE_V1",
    "PromptProfile",
    "REGISTERED_PROMPT_PROFILE_IDS",
    "assert_registry_integrity",
    "profile_bundle_sha256",
    "profile_registry_sha256",
    "render_generation_prompt",
    "render_reflection_prompt",
    "render_system_prompt",
    "resolve_admission_profile",
    "resolve_profile",
    "validate_profile_field",
]
