---
name: prototype
description: Build a throwaway prototype to answer a design question. Use when a decision needs a concrete UI or logic artifact, or a cheap fair comparison of algorithms, prompts, models, configurations, or data policies before implementation.
---

# Prototype

A prototype is a **throwaway artifact that answers one decision question**. The question decides the shape.

## Pick a branch

Identify which question is being answered, using the user's prompt, the surrounding code, or by asking if the user is around:

- **"Which option actually works better?"** → [COMPARISON.md](COMPARISON.md). Run the smallest fair comparison that can distinguish algorithms, prompts, models, configurations, or data policies with reproducible evidence.
- **"Does this logic / state model feel right?"** → [LOGIC.md](LOGIC.md). Build a single shareable HTML file (free-play buttons plus tabbed guided walkthroughs) that pushes the state machine through cases that are hard to reason about on paper, and that a non-developer can drive.
- **"What should this look like?"** → [UI.md](UI.md). Generate several radically different UI variations on a single route, switchable via a URL search param and a floating bottom bar.

The three branches produce different evidence, so getting this wrong wastes the prototype. A measurable "which is better" question takes the comparison branch even when the candidates are backend logic. An interaction/state-shape question takes logic; a visual hierarchy question takes UI. If the question remains genuinely ambiguous and the user is unavailable, choose from those distinctions and state the assumption at the top of the artifact.

## Rules that apply to all branches

1. **Throwaway from day one, and clearly marked as such.** Follow the repository's prototype/evidence convention. Keep the artifact isolated from production paths unless the chosen branch explicitly needs an existing host page, and name it so a casual reader can see it is a prototype.
2. **Trivial to run or replay.** Provide one command, one file, or one short procedure. A future reader should not need to reconstruct hidden setup.
3. **Isolated by default.** Keep state in memory and inputs immutable. If the question explicitly involves persistence or an external service, use a scratch target with an unmistakable prototype name and obey the repository's approval gates.
4. **Trust before polish.** Add only the validation, fixtures, and error handling needed to trust the answer. Skip production hardening, generalisation, and unrelated abstractions.
5. **Surface the evidence.** Make relevant state visible for logic/UI branches; retain comparable inputs, outputs, metrics, and failures for comparison branches.
6. **Decision gate.** Present the answer and evidence to the human when the workflow is HITL or the choice is material. Record the verdict, rejected alternatives, and context pointer. Implement the winner only when the current workflow separately authorizes implementation.
7. **Capture the primary source.** Preserve the prototype using the repository's tracker/evidence convention. If that convention uses a throwaway branch, keep the raw artifact there and link it; keep the main branch focused on the approved decision and durable context.
