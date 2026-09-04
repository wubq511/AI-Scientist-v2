import argparse
import json
import os.path as osp
import re
import traceback
from typing import Any, Dict, List

import sys

sys.path.append(osp.join(osp.dirname(__file__), ".."))
from ai_scientist.llm import (
    AVAILABLE_LLMS,
    create_client,
    get_response_from_llm,
)

from ai_scientist.tools.semantic_scholar import SemanticScholarSearchTool
from ai_scientist.tools.base_tool import BaseTool

# Legacy tool instances are created lazily inside the factory below so that
# importing this module has no import-time side effects.
tools: List[Any] = [
    {
        "name": "FinalizeIdea",
        "description": """Finalize your idea by providing the idea details.

The IDEA JSON should include the following fields:
- "Name": A short descriptor of the idea. Lowercase, no spaces, underscores allowed.
- "Title": A catchy and informative title for the proposal.
- "Short Hypothesis": A concise statement of the main hypothesis or research question. Clarify the need for this specific direction, ensure this is the best setting to investigate this idea, and there are not obvious other simpler ways to answer the question.
- "Related Work": A brief discussion of the most relevant related work and how the proposal clearly distinguishes from it, and is not a trivial extension.
- "Abstract": An abstract that summarizes the proposal in conference format (approximately 250 words).
- "Experiments": A list of experiments that would be conducted to validate the proposal. Ensure these are simple and feasible. Be specific in exactly how you would test the hypothesis, and detail precise algorithmic changes. Include the evaluation metrics you would use.
- "Risk Factors and Limitations": A list of potential risks and limitations of the proposal.""",
    },
]


def _legacy_tools() -> List[Any]:
    """Create the legacy tool instances on demand (no import side effects)."""
    return [SemanticScholarSearchTool()] + list(tools)


def _tool_catalog() -> tuple[Dict[str, Any], str, str]:
    """Build the tool lookup, descriptions, and prompt name list."""
    catalog = _legacy_tools()
    tools_lookup = {tool.name: tool for tool in catalog if isinstance(tool, BaseTool)}
    descriptions = "\n\n".join(
        (
            f"- **{tool.name}**: {tool.description}"
            if isinstance(tool, BaseTool)
            else f"- **{tool['name']}**: {tool['description']}"
        )
        for tool in catalog
    )
    names = [
        f'"{tool.name}"' if isinstance(tool, BaseTool) else f'"{tool["name"]}"'
        for tool in catalog
    ]
    return tools_lookup, descriptions, ", ".join(names)


def _build_system_prompt(tool_descriptions: str, tool_names_str: str) -> str:
    return f"""You are an experienced AI researcher who aims to propose high-impact research ideas resembling exciting grant proposals. Feel free to propose any novel ideas or experiments; make sure they are novel. Be very creative and think out of the box. Each proposal should stem from a simple and elegant question, observation, or hypothesis about the topic. For example, they could involve very interesting and simple interventions or investigations that explore new possibilities or challenge existing assumptions. Clearly clarify how the proposal distinguishes from the existing literature.

Ensure that the proposal does not require resources beyond what an academic lab could afford. These proposals should lead to papers that are publishable at top ML conferences.

You have access to the following tools:

{tool_descriptions}

Respond in the following format:

ACTION:
<The action to take, exactly one of {tool_names_str}>

ARGUMENTS:
<If ACTION is "SearchSemanticScholar", provide the search query as {{"query": "your search query"}}. If ACTION is "FinalizeIdea", provide the idea details as {{"idea": {{ ... }}}} with the IDEA JSON specified below.>

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
    "Experiments": "...",
    "Risk Factors and Limitations": "..."
  }}
}}
```

Ensure the JSON is properly formatted for automatic parsing.

Note: You should perform at least one literature search before finalizing your idea to ensure it is well-informed by existing research."""


# Define the initial idea generation prompt
idea_generation_prompt = """{workshop_description}

Here are the proposals that you have already generated:

'''
{prev_ideas_string}
'''

Begin by generating an interestingly new high-level research proposal that differs from what you have previously proposed.
"""

# Define the reflection prompt
idea_reflection_prompt = """Round {current_round}/{num_reflections}.

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


def generate_temp_free_idea(
    idea_fname: str,
    client: Any,
    model: str,
    workshop_description: str,
    max_num_generations: int = 20,
    num_reflections: int = 5,
    reload_ideas: bool = True,
) -> List[Dict]:
    # Build the tool catalog and prompts lazily: importing this module has no
    # side effects; tool instances are created only when a run is executed.
    tools_dict, tool_descriptions, tool_names_str = _tool_catalog()
    system_prompt = _build_system_prompt(tool_descriptions, tool_names_str)

    idea_str_archive = []
    # load ideas from file
    if reload_ideas and osp.exists(idea_fname):
        with open(idea_fname, "r") as f:
            idea_str_content = json.load(f)
            for idea in idea_str_content:
                idea_str_archive.append(json.dumps(idea))
            print(f"Loaded {len(idea_str_archive)} ideas from {idea_fname}")
    else:
        print(f"No ideas found in {idea_fname}. Starting from scratch.")

    for gen_idx in range(max_num_generations):
        print()
        print(f"Generating proposal {gen_idx + 1}/{max_num_generations}")
        try:
            prev_ideas_string = "\n\n".join(idea_str_archive)

            last_tool_results = ""
            idea_finalized = False
            msg_history = []

            for reflection_round in range(num_reflections):
                if reflection_round == 0:
                    # Use the initial idea generation prompt
                    prompt_text = idea_generation_prompt.format(
                        workshop_description=workshop_description,
                        prev_ideas_string=prev_ideas_string,
                    )
                else:
                    # Use the reflection prompt, including tool results if any
                    prompt_text = idea_reflection_prompt.format(
                        current_round=reflection_round + 1,
                        num_reflections=num_reflections,
                        last_tool_results=last_tool_results or "No new results.",
                    )

                response_text, msg_history = get_response_from_llm(
                    prompt=prompt_text,
                    client=client,
                    model=model,
                    system_message=system_prompt,
                    msg_history=msg_history,
                )

                # Parse the LLM's response
                try:
                    # Use regular expressions to extract the components
                    action_pattern = r"ACTION:\s*(.*?)\s*ARGUMENTS:"
                    arguments_pattern = r"ARGUMENTS:\s*(.*?)(?:$|\nTHOUGHT:|\n$)"

                    action_match = re.search(
                        action_pattern, response_text, re.DOTALL | re.IGNORECASE
                    )
                    arguments_match = re.search(
                        arguments_pattern, response_text, re.DOTALL | re.IGNORECASE
                    )

                    if not all([action_match, arguments_match]):
                        raise ValueError("Failed to parse the LLM response.")

                    action = action_match.group(1).strip()
                    arguments_text = arguments_match.group(1).strip()
                    print(f"Action: {action}")
                    print(f"Arguments: {arguments_text}")

                    # If arguments are wrapped in ```json blocks, extract the content
                    if arguments_text.startswith("```json"):
                        arguments_text = re.search(
                            r"```json\s*(.*?)\s*```", arguments_text, re.DOTALL
                        ).group(1)

                    # Process the action and arguments
                    if action in tools_dict:
                        # It's a tool we have defined
                        tool = tools_dict[action]
                        # Parse arguments
                        try:
                            arguments_json = json.loads(arguments_text)
                        except json.JSONDecodeError:
                            raise ValueError(f"Invalid arguments JSON for {action}.")

                        # Use the tool
                        try:
                            # Assuming the arguments match the parameters of the tool
                            result = tool.use_tool(**arguments_json)
                            last_tool_results = result
                        except Exception as e:
                            last_tool_results = f"Error using tool {action}: {str(e)}"
                    elif action == "FinalizeIdea":
                        # Parse arguments
                        try:
                            arguments_json = json.loads(arguments_text)
                            idea = arguments_json.get("idea")
                            if not idea:
                                raise ValueError("Missing 'idea' in arguments.")

                            # Append the idea to the archive
                            idea_str_archive.append(json.dumps(idea))
                            print(f"Proposal finalized: {idea}")
                            idea_finalized = True
                            break
                        except json.JSONDecodeError:
                            raise ValueError("Invalid arguments JSON for FinalizeIdea.")
                    else:
                        print(
                            "Invalid action. Please specify one of the available tools."
                        )
                        print(f"Available actions are: {tool_names_str}")
                except Exception as e:
                    print(
                        f"Failed to parse LLM response. Response text:\n{response_text}"
                    )
                    traceback.print_exc()
                    break  # Exit the loop if parsing fails

            if idea_finalized:
                continue  # Move to the next idea

        except Exception as e:
            print("Failed to generate proposal:")
            traceback.print_exc()
            continue

    # Save ideas
    ideas = [json.loads(idea_str) for idea_str in idea_str_archive]

    with open(idea_fname, "w") as f:
        json.dump(ideas, f, indent=4)
    print(f"Stored {len(ideas)} ideas in {idea_fname}")
    return ideas


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate AI scientist proposals - template free"
    )
    subparsers = parser.add_subparsers(dest="entry")

    # Safe ideation entry: request, nine-step preflight, cost approval, and
    # Run Admission. No model, ranker, device, output-root, or resume control.
    new_run = subparsers.add_parser(
        "new-run", help="Admit one Ideation Run without any paid work."
    )
    new_run.add_argument("--case-id", required=True)
    new_run.add_argument("--workshop", required=True)
    new_run.add_argument("--workshop-sha256", required=True)
    new_run.add_argument("--corpus", required=True)
    new_run.add_argument("--corpus-sha256", required=True)
    new_run.add_argument("--max-num-generations", type=int, required=True)
    new_run.add_argument("--num-reflections", type=int, required=True)

    # Resume entry: continue one suspended Ideation Run; exact run_id only
    # (ticket 10). No other control surface is accepted.
    resume = subparsers.add_parser(
        "resume", help="Resume one suspended Ideation Run by its exact run_id."
    )
    resume.add_argument("--run-id", required=True)

    # Validate entry: verify a sealed Evidence Chain; exact run_id only (ticket 11).
    validate = subparsers.add_parser(
        "validate", help="Validate one sealed Evidence Chain by its exact run_id."
    )
    validate.add_argument("--run-id", required=True)

    # Export entry: export sanitized evidence; exact run_id only (ticket 11).
    export = subparsers.add_parser(
        "export", help="Export sanitized evidence for one sealed Ideation Run."
    )
    export.add_argument("--run-id", required=True)

    # Retained legacy baseline entry (expand-contract; removed by ticket 13).
    legacy = subparsers.add_parser(
        "legacy", help="Retained pre-fork baseline path (ticket 13 removes it)."
    )
    legacy.add_argument(
        "--model",
        type=str,
        default="gpt-4o-2024-05-13",
        choices=AVAILABLE_LLMS,
        help="Model to use for AI Scientist.",
    )
    legacy.add_argument(
        "--max-num-generations",
        type=int,
        default=1,
        help="Maximum number of proposal generations.",
    )
    legacy.add_argument(
        "--workshop-file",
        type=str,
        default="ideas/i_cant_believe_its_not_better.md",
        help="Path to the workshop description file.",
    )
    legacy.add_argument(
        "--num-reflections",
        type=int,
        default=5,
        help="Number of reflection rounds per proposal.",
    )
    return parser


def run_new_run(
    workspace_root: Path,
    request: Any,
    *,
    command: list[str] | None = None,
    stream: Any = None,
    adapter: Any = None,
    retriever: Any = None,
    store: Any = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Admit and optionally execute an Ideation Run with injected components."""
    from ai_scientist.ideation.admission import admit_new_run

    admission_result = admit_new_run(
        workspace_root,
        request,
        stream=stream,
        command=command,
    )
    if not execute:
        return admission_result

    from ai_scientist.ideation.controller import IdeationController

    controller = IdeationController(
        workspace_root,
        admission_result["run_id"],
        store=store,
        adapter=adapter,
        retriever=retriever,
    )
    return controller.run()


def _suspended_payload(run_id: str | None, code: str, message: str) -> dict[str, Any]:
    """Uniform suspend report: the run stays unsealed and resumable."""
    payload: dict[str, Any] = {
        "code": code,
        "message": message,
        "status": "suspended",
    }
    if run_id is not None:
        payload["run_id"] = run_id
    return payload


def _run_new_run(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
    stream: Any = None,
    adapter: Any = None,
    retriever: Any = None,
    store: Any = None,
    execute: bool | None = None,
) -> int:
    import os
    from ai_scientist.ideation.admission import NewRunRequest, admit_new_run
    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.deepseek import ModelRoundError
    from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted

    root = workspace_root or Path.cwd()
    request = NewRunRequest(
        case_id=args.case_id,
        workshop=args.workshop,
        workshop_sha256=args.workshop_sha256,
        corpus=args.corpus,
        corpus_sha256=args.corpus_sha256,
        max_num_generations=args.max_num_generations,
        num_reflections=args.num_reflections,
    )
    if execute is None:
        execute = adapter is not None or os.environ.get("IDEATION_EXECUTE") == "1"

    command = [
        "python",
        "ai_scientist/perform_ideation_temp_free.py",
        "new-run",
        "--case-id",
        args.case_id,
        "--workshop",
        args.workshop,
        "--workshop-sha256",
        args.workshop_sha256,
        "--corpus",
        args.corpus,
        "--corpus-sha256",
        args.corpus_sha256,
        "--max-num-generations",
        str(args.max_num_generations),
        "--num-reflections",
        str(args.num_reflections),
    ]

    # Admission phase: failures are preflight rejections (exit 2).
    try:
        admission_result = admit_new_run(
            root,
            request,
            stream=stream,
            command=command,
        )
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "preflight_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 2
    except KeyboardInterrupt as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(
                    getattr(exc, "run_id", None),
                    "KEYBOARD_INTERRUPT",
                    "Interrupted during admission",
                )
            )
        )
        return 3

    if not execute:
        sys.stdout.buffer.write(canonical_json_bytes(admission_result))
        return 0

    # Execution phase: suspend-class failures leave the run unsealed and
    # resumable (exit 3); terminal outcomes seal and return normally.
    run_id = admission_result["run_id"]
    try:
        from ai_scientist.ideation.controller import IdeationController

        controller = IdeationController(
            root,
            run_id,
            store=store,
            adapter=adapter,
            retriever=retriever,
        )
        result = controller.run()
    except IdeationInputError as exc:
        if exc.code != "STORAGE_WRITE_FAILED":
            raise
        sys.stdout.buffer.write(
            canonical_json_bytes(_suspended_payload(run_id, exc.code, exc.message))
        )
        return 3
    except ModelRoundError as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(_suspended_payload(run_id, exc.code, str(exc)))
        )
        return 3
    except RunInterrupted as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(run_id, "RUN_INTERRUPTED", str(exc))
            )
        )
        return 3
    except KeyboardInterrupt:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(
                    run_id, "KEYBOARD_INTERRUPT", "Interrupted during execution"
                )
            )
        )
        return 3
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_resume(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
    stream: Any = None,
    adapter: Any = None,
    retriever: Any = None,
    store: Any = None,
) -> int:
    """Resume a suspended run: exit 0 sealed, 2 resume_rejected, 3 suspended."""
    from pathlib import Path as _Path

    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.deepseek import ModelRoundError
    from ai_scientist.ideation.errors import IdeationInputError, RunInterrupted
    from ai_scientist.ideation.resume import resume_run

    root = workspace_root or _Path.cwd()
    try:
        result = resume_run(
            root,
            args.run_id,
            stream=stream,
            adapter=adapter,
            retriever=retriever,
            store=store,
        )
    except IdeationInputError as exc:
        if exc.code == "STORAGE_WRITE_FAILED":
            sys.stdout.buffer.write(
                canonical_json_bytes(
                    _suspended_payload(args.run_id, exc.code, exc.message)
                )
            )
            return 3
        error = {
            "code": exc.code,
            "message": exc.message,
            "status": "resume_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 2
    except ModelRoundError as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(_suspended_payload(args.run_id, exc.code, str(exc)))
        )
        return 3
    except RunInterrupted as exc:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(args.run_id, "RUN_INTERRUPTED", str(exc))
            )
        )
        return 3
    except KeyboardInterrupt:
        sys.stdout.buffer.write(
            canonical_json_bytes(
                _suspended_payload(
                    args.run_id, "KEYBOARD_INTERRUPT", "Interrupted during resume"
                )
            )
        )
        return 3
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_validate(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Validate a sealed run: exit 0 valid, 1 corrupt/error."""
    from pathlib import Path as _Path

    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evidence import validate_evidence_chain

    root = workspace_root or _Path.cwd()
    try:
        result = validate_evidence_chain(root, args.run_id, check_sealed=True)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "corrupt" if exc.code == "RUN_CORRUPT" else "error",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_export(
    args: argparse.Namespace,
    *,
    workspace_root: Path | None = None,
) -> int:
    """Export sanitized evidence: exit 0 exported, 1 corrupt/rejected."""
    from pathlib import Path as _Path

    from ai_scientist.ideation.canonical import canonical_json_bytes
    from ai_scientist.ideation.errors import IdeationInputError
    from ai_scientist.ideation.evidence import export_sanitized_evidence

    root = workspace_root or _Path.cwd()
    try:
        result = export_sanitized_evidence(root, args.run_id)
    except IdeationInputError as exc:
        error = {
            "code": exc.code,
            "message": exc.message,
            "run_id": args.run_id,
            "status": "export_rejected",
        }
        sys.stderr.buffer.write(canonical_json_bytes(error))
        return 1
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


def _run_legacy(args: argparse.Namespace) -> int:
    # Create the LLM client
    client, client_model = create_client(args.model)

    with open(args.workshop_file, "r") as f:
        workshop_description = f.read()
    print(f"Using workshop description from {args.workshop_file} for idea generation.")
    print(f"Workshop description:\n{workshop_description}")

    # Create output filename by replacing .md extension with .json
    idea_fname = args.workshop_file.replace(".md", ".json")
    print("Starting idea generation for", idea_fname)
    ideas = generate_temp_free_idea(
        idea_fname=idea_fname,
        client=client,
        model=client_model,
        workshop_description=workshop_description,
        max_num_generations=args.max_num_generations,
        num_reflections=args.num_reflections,
    )
    print(f"{args.workshop_file} generated {len(ideas)} ideas.")
    return 0


if __name__ == "__main__":
    from pathlib import Path

    _parser = _build_parser()
    _args = _parser.parse_args()
    if _args.entry == "new-run":
        raise SystemExit(_run_new_run(_args))
    if _args.entry == "resume":
        raise SystemExit(_run_resume(_args))
    if _args.entry == "validate":
        raise SystemExit(_run_validate(_args))
    if _args.entry == "export":
        raise SystemExit(_run_export(_args))
    if _args.entry == "legacy":
        raise SystemExit(_run_legacy(_args))
    # No subcommand: print the same help text and exit like --help.
    _parser.print_help()
    raise SystemExit(0)
