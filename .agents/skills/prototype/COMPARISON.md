# Comparative Prototype

Use this branch when the decision is **which candidate works better under the same constraints**: ranking methods, prompts, model settings, schemas, transformations, or data policies. The prototype is a small evidence loop, not a production implementation.

## Process

### 1. Pre-register the question

Before building the harness, write down:

- the one decision this comparison will inform;
- the viable alternatives, including the simplest credible baseline;
- the inputs and conditions held constant;
- the metrics, acceptance thresholds, qualitative review, and failure cases that can distinguish them;
- the invariants no candidate may trade away;
- the smallest representative cases that exercise the important variation.

If one answer cannot be judged from this protocol, sharpen it before running anything. A comparison that changes multiple material variables at once cannot identify why the result changed.

### 2. Build the smallest trustworthy harness

Run every candidate against the same immutable inputs, ordering, budgets, and evaluation procedure. Isolate outputs by candidate and attempt. Use deterministic seeds where they are meaningful, and record unavoidable nondeterminism instead of hiding it.

Add the fixtures or sanity checks needed to prove the harness measures what it claims: input identity, scope/isolation, output parsing, metric direction, failure capture, and repeatability. Do not add production architecture, compatibility layers, or broad test coverage.

### 3. Clear authority and cost gates

Local, reversible work can proceed. Before a paid model/API run, estimate calls, tokens, and cost and obtain the approval required by the repository. Keep credentials outside code and logs. Never let a prototype cross a scope boundary, mutate production, or enter a prohibited downstream stage.

### 4. Run and retain evidence

Record enough for another agent to replay or audit the comparison:

- commit SHA, input identities/hashes/counts, and representative-case rationale;
- exact command, environment, dependency/model/provider identifiers, and candidate configurations;
- timestamps, raw outputs/logs, output hashes, metrics, latency, resource/cost usage, and failures;
- every deviation from the pre-registered protocol and its effect on comparability.

Keep secrets out of every artifact. Preserve failed attempts; they are evidence about the option and the harness.

### 5. Compare without laundering trade-offs

Show every candidate side by side against the same criteria. Reject any candidate that violates an invariant even if its headline metric is higher. Call out uncertainty, confounders, ties, and cases where the evidence does not separate the options.

Among candidates that meet the evidence threshold, recommend the simplest, lightest design. A recommendation is not approval: in a HITL or material decision, present the evidence and wait for the human verdict.

### 6. Capture the answer

Record the approved choice, why the evidence supports it, what was rejected, known limitations, and the context pointer to the raw prototype evidence. Stop there in a planning workflow. Move into production implementation only under a separate authorization that carries the decision forward.

## Completion criteria

The branch is complete only when every viable alternative has a comparable result or an explicit evidenced failure; every invariant and acceptance criterion has an outcome; the commands and artifacts are replayable; and the decision owner has enough evidence to choose without guessing.

## Anti-patterns

- Tuning one candidate more than the others.
- Choosing metrics after seeing which option wins.
- Treating one happy-path example as representative evidence.
- Hiding failed runs, parser errors, retries, or cost.
- Selecting the most complex option because it is more sophisticated.
- Folding the winner into production before the decision is approved.
