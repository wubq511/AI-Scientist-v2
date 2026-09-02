# Local-ranking comparison harness

This directory is a throwaway, evidence-producing prototype for Wayfinder ticket `Choose and calibrate local literature ranking`. Production code under `ai_scientist/` must not import it.

The only public replay command is:

```bash
python -m prototypes.local_ranking.run --protocol <repository-relative-frozen-protocol.json>
```

Formal-input preparation is a separate private, immutable prototype step:

```bash
python -m prototypes.local_ranking.input_preparation prepare \
  --output-root artifacts/local-ranking-prototype/input-preparation-v1/attempts/<attempt-id>
```

This command uses target identity, clusters, and reference text only inside the private
preparation boundary. It emits a target `title + abstract`-only Workshop authoring packet,
deterministically stratified 6+6 case proposal, and pending-approval corpus bundles. It does
not create queries/qrels or label any artifact approved. Workshop drafts are validated in a
second immutable step with `validate-workshops`; the query author must use a fresh context
that can read Approved Workshops but cannot read the authoring packet or corpus content.

An explicit, hash-bound review decision becomes immutable approval sidecars with:

```bash
python -m prototypes.local_ranking.input_preparation approve \
  --preparation-root <private-preparation-attempt> \
  --draft-set <validated-draft-set> \
  --decision-record <private-review-decision.json> \
  --protocol <approved-v1.1-protocol.md> \
  --approval-id <new-approval-id>
```

The command revalidates the exact selection, preparation, Workshop, corpus, validator,
policy, and protocol hashes before writing. It never overwrites pending inputs. Its
`query-author-packet/` contains only byte-identical Approved Workshops plus a closed
manifest; Target authoring input, corpus/reference content, qrels, and ranker outputs stay
outside that packet.

Prepare the pinned dense model in previously unused repository-relative paths before entering offline mode:

```bash
python -m prototypes.local_ranking.prepare_model \
  --artifact-dir <model-files-directory> \
  --manifest <sibling-model-manifest.json>
```

The preparation command downloads only the six allowlisted files from the approved E5 commit, verifies the frozen weight size/SHA-256 and model-size gate, writes a closed manifest, and never overwrites an earlier attempt. A failed partial directory is evidence and must not be reused.

The approved abstract length policy can be replayed without loading model weights or running a ranker:

```bash
uv run --no-project --with 'tokenizers==0.23.1' \
  python -m prototypes.local_ranking.length_policy_probe \
  --approval-root <private-input-approval> \
  --corpora-root <approved-preparation-corpora> \
  --tokenizer-json <pinned-e5-tokenizer.json> \
  --output <new-private-attempt>/result.json
```

The probe counts `passage: ` and special tokens inside the 512-token E5 input limit. It preserves every approved abstract and emits deterministic source offsets/hashes for sentence-first, zero-overlap segmentation only where the full input exceeds the model boundary. It does not create queries/qrels, score candidates, or make the formal input adapter optional.

After an isolated author freezes the query manifest, record the delegated or human approval without rewriting those bytes:

```bash
python -m prototypes.local_ranking.query_authoring \
  --raw-response <kimi-raw-stdout.txt> \
  --raw-stderr <kimi-raw-stderr.txt> \
  --prompt <query-author-prompt.txt> \
  --prompt-manifest <query-author-prompt-manifest.json> \
  --agent-file <tool-less-query-author-agent.md> \
  --packet-manifest <approved-query-author-packet/manifest.json> \
  --input-approval <private-input-approval/approval-manifest.json> \
  --protocol <approved-v1.4-protocol.md> \
  --output <new-private-query-manifest.json> \
  --manifest-id <new-manifest-id> \
  --execution-id <fresh-execution-id> \
  --created-at <UTC-timestamp> \
  --cli-version <kimi-code-version> \
  --model-alias <configured-model-alias> \
  --model-name <model-display-name> \
  --provider <configured-provider> \
  --reasoning-mode <recorded-reasoning-mode>

python -m prototypes.local_ranking.formal_input approve-queries \
  --query-manifest <private-query-manifest.json> \
  --packet-manifest <approved-query-author-packet/manifest.json> \
  --protocol <approved-v1.1-protocol.md> \
  --output <new-private-query-approval.json> \
  --approved-on <YYYY-MM-DD> \
  --decision-actor <actor> \
  --delegated-by <authority> \
  --delegation-text <exact-authority-text>
```

The finalizer accepts either bare JSON or the single `\u2022 ` prefix emitted by Kimi Code's
text renderer. It preserves and hash-binds raw stdout/stderr; every other wrapper, unknown
field, case/order drift, duplicate normalized query, forbidden evaluation identity, or
query-shape violation fails closed.

Materialize the formal development/holdout inputs and blind qrels pages with:

```bash
uv run --no-project --with 'tokenizers==0.23.1' \
  python -m prototypes.local_ranking.formal_input materialize \
  --approval-root <private-input-approval> \
  --corpora-root <approved-preparation-corpora> \
  --query-manifest <private-query-manifest.json> \
  --query-approval <private-query-approval.json> \
  --protocol <approved-v1.1-protocol.md> \
  --tokenizer-json <pinned-e5-tokenizer.json> \
  --output-root <new-private-formal-input-attempt>
```

This fail-closed adapter validates every bound hash, uses one shared source-complete segmentation for all arms, checks exact E5 query/title/segment lengths, and emits canonical harness inputs. Its self-contained HTML pages have no external resources and export qrels only after the review form is complete; they never generate relevance labels themselves.

## v1.4 fresh operational evaluation

The approved v1.4 overlay replaces another reuse of the spent holdout with one fresh,
deterministically selected 12-case operational batch. Freeze the protocol and harness in a
clean commit before running this command:

```bash
python -m prototypes.local_ranking.input_preparation prepare-operational \
  --raw-root data/raw \
  --spent-selection <old-12-case-selection-manifest.json> \
  --output-root artifacts/local-ranking-prototype/operational-input-v1/attempts/<attempt-id>
```

This command excludes every old target, selects exactly four cases per corpus-size stratum,
covers every eligible source cluster, and writes the same Workshop/corpus approval inputs as
the legacy preparation path. It does not approve cases, author queries, run rankers, or call a
model. Use the existing `validate-workshops`, `approve`, `approve-queries`, and `materialize`
commands with the v1.4 protocol. Operational materialization emits one
`operational/input.json`; it deliberately emits no qrels review page.

After Windows has produced exact canonical BM25/E5 top-3 payloads for that operational input,
prepare four blinded, mirrored evaluator prompts:

```bash
python -m prototypes.local_ranking.operational_judge prepare \
  --input <formal-operational-input.json> \
  --formal-manifest <formal-operational-manifest.json> \
  --selection <operational-selection-manifest.json> \
  --protocol docs/prototypes/local-literature-ranking-comparison-protocol-v1.4.md \
  --evaluator-protocol docs/prototypes/local-literature-ranking-comparison-protocol-v1.6.md \
  --comparison-summary <windows-comparison-summary.json> \
  --baseline-candidate-id bm25-k16-b05-tw1-cap3 \
  --baseline-payloads <windows-bm25-payloads.jsonl> \
  --challenger-candidate-id e5-small-v2-tw1-cap3 \
  --challenger-payloads <windows-e5-payloads.jsonl> \
  --output-root <new-setwise-preparation-attempt>
```

Evaluator qualification must use all 24 already-spent development and holdout queries. Build
one immutable derived packet first; do not point the qualification harness at either 12-query
split by itself:

```bash
python -m prototypes.local_ranking.qualification_input \
  --development-input <spent-development-input.json> \
  --holdout-input <spent-holdout-input.json> \
  --selection <source-selection-manifest.json> \
  --development-summary <spent-development-comparison-summary.json> \
  --holdout-summary <spent-holdout-comparison-summary.json> \
  --development-baseline-payloads <spent-development-bm25-payloads.jsonl> \
  --holdout-baseline-payloads <spent-holdout-bm25-payloads.jsonl> \
  --development-challenger-payloads <spent-development-e5-payloads.jsonl> \
  --holdout-challenger-payloads <spent-holdout-e5-payloads.jsonl> \
  --output-root <new-spent-qualification-input-attempt>
```

The derived manifest binds both source inputs, both comparison summaries, all four source
payload files, the source selection, and the five combined outputs. Its split is
`spent_qualification`, its scale is exactly 12 cases / 24 queries, and downstream reducers
must retain `spent_diagnostic_only`.

The public bundles expose only query plus anonymous left/right evidence. The private mapping
binds the exact formal manifest, input, selection, protocol, candidate payloads, resource
gates, and side assignments. `tool-less-agent.md` disables tools and subagents. Do not start
the four evaluator sessions until exact prompt sizes, model context support, invocation
count, privacy status, and the one-whole-orientation retry ceiling are frozen.

Validate each raw evaluator JSON without repair:

```bash
python -m prototypes.local_ranking.kimi_output \
  --raw-stdout <immutable-execution/stdout.txt> \
  --raw-stderr <immutable-execution/stderr.txt> \
  --prompt <exact-prompt.txt> \
  --agent-file <tool-less-agent.md> \
  --config-snapshot <redacted-config.json> \
  --exit-code <immutable-execution/exit-code.txt> \
  --started-at <immutable-execution/started-at.txt> \
  --finished-at <immutable-execution/finished-at.txt> \
  --output-root <new-immutable-extraction> \
  --execution-id <fresh-execution-id> \
  --cli-version <kimi-code-version> \
  --model-alias <model-alias> \
  --provider <provider-id> \
  --reasoning-effort <effort>

python -m prototypes.local_ranking.operational_judge finalize \
  --bundle <matching-public-bundle.json> \
  --draft <new-immutable-extraction/response.json> \
  --output-root <new-immutable-evaluator-result>
```

The extraction step preserves and hashes every raw invocation input/output, accepts only bare
JSON or Kimi Code's single text-renderer prefix, and canonicalizes no model semantics. The judge
validator remains a separate closed-schema and visible-segment-reference evidence gate.

DeepSeek stays on `provider=opencode-go`, but bypasses the Kimi Code text renderer. Prepare the
credential-free direct Chat Completions request first:

```bash
python -m prototypes.local_ranking.opencode_go_chat prepare \
  --bundle <judge-deepseek-bundle.json> \
  --prompt <matching-judge-deepseek-prompt.txt> \
  --output-root <new-opencode-go-request-preparation>
```

Execute only an approved synthetic/spent attempt into a new private directory. The adapter can
read `OPENCODE_GO_API_KEY`, or the existing local Kimi Code `opencode-go` credential without
printing it:

```bash
python -m prototypes.local_ranking.opencode_go_chat execute \
  --preparation-root <approved-opencode-go-request-preparation> \
  --output-root <new-private-opencode-go-execution> \
  --kimi-config ~/.kimi-code/config.toml
```

The direct request uses the documented OpenCode Go Chat endpoint. `json_object` and
`reasoning_effort=high` remain qualification candidates rather than assumed provider contracts;
pass the canonical `response.json` through `operational_judge finalize`. The 2026-08-31 DeepSeek
ZDR statement has expired, so only synthetic payloads may be sent until the v1.6 data-retention
gate is satisfied.

For a separately approved SSE transport qualification, derive a streaming request from the same
frozen bundle and prompt. This changes only `stream` from `false` to `true`; it does not add
`stream_options`, alter the evaluator prompt, or relax the local validator:

```bash
python -m prototypes.local_ranking.opencode_go_stream prepare \
  --bundle <judge-deepseek-bundle.json> \
  --prompt <matching-judge-deepseek-prompt.txt> \
  --output-root <new-opencode-go-stream-preparation>

python -m prototypes.local_ranking.opencode_go_stream execute \
  --preparation-root <approved-opencode-go-stream-preparation> \
  --output-root <new-private-opencode-go-stream-execution> \
  --kimi-config ~/.kimi-code/config.toml
```

The streaming adapter preserves the complete SSE body, parsed chunks, safe headers, timestamps,
request identity, and provider response identity. It fails closed on malformed SSE, mixed response
IDs/models, refusal/tools, abnormal finish reasons, content after the terminal chunk, missing
`[DONE]`, incomplete JSON, or a local judge validation failure. A streaming receipt may omit usage
when the provider sends no usage chunk; absence is recorded, never reconstructed.

When a frozen evaluator profile needs repeated mirror calibration, run exactly three fresh pairs
and aggregate every result rather than retrying until one pair passes. Each replicate supplies two
validated traces and their matching direct-transport receipts:

```bash
python -m prototypes.local_ranking.evaluator_profile_calibration \
  --model deepseek-v4-flash \
  --reasoning-effort high \
  --replicate r1 <r1-o1-trace> <r1-o2-trace> <r1-o1-receipt> <r1-o2-receipt> \
  --replicate r2 <r2-o1-trace> <r2-o2-trace> <r2-o1-receipt> <r2-o2-receipt> \
  --replicate r3 <r3-o1-trace> <r3-o2-trace> <r3-o1-receipt> <r3-o2-receipt> \
  --output <new-profile-calibration-result.json>
```

The v1.0 aggregator requires one frozen request/bundle per orientation, six unique provider
response IDs, all three pairs at least 22/24 stable, at least two pairs at the original 23/24 gate,
and pooled stability at least 69/72. Calibration output remains anonymous spent diagnostic
evidence and must never be used as a candidate vote.

The approved atomic v2 contract replaces the 24-judgment model response without modifying the
historical v1.x path. Split one frozen source bundle into 24 single-item public prompts and one
controller-private manifest with:

```bash
python -m prototypes.local_ranking.atomic_judge prepare \
  --bundle <frozen-v1.2-source-bundle.json> \
  --replicate-id <replicate-id> \
  --reasoning-effort <high-or-max> \
  --output-root <new-atomic-preparation>
```

The public prompts contain only query text, visible evidence, and `L1-L3`/`R1-R3` handles. Item,
paper, segment, bundle, and evaluator identities stay controller-owned. Prompts state that no
external or retrieval tools are available and require exactly one `submit_judgment` tool call.
The v2.5 atomic manifest declares `response_submission: forced_submit_judgment_tool`, making the
forced-tool contract explicit and machine-checkable. After each physical call, prepare immutable
OpenCode Go requests. The v3.1 transport adapter freezes `deepseek-v4-pro`, one forced
`submit_judgment` function tool with a closed six-field schema (no `response_format`),
`max_tokens=16384`, concurrency 1-4, request hashes, the same `response_submission` declaration,
and the bounded retry policy:

```bash
python -m prototypes.local_ranking.atomic_opencode_go prepare-atomic \
  --atomic-manifest <atomic-preparation/private/manifest.json> \
  --max-concurrency <1-4> \
  --output-root <new-atomic-transport-preparation>

python -m prototypes.local_ranking.atomic_opencode_go execute-call \
  --preparation-root <atomic-transport-preparation> \
  --call-sequence <1-24> \
  --output-root <new-transport-attempt> \
  --kimi-config <kimi-config-with-opencode-go-key>
```

Execution streams the SSE body, joins fragmented `tool_calls[0]` ID/name/arguments by index, and
accepts only one index-0 `submit_judgment` call whose arguments parse without repair; ordinary
`content` and `reasoning_content` are preserved as raw evidence only and never supply judgment
fields. `finish_reason` must be `tool_calls` or `stop`; multiple/wrong/missing calls, malformed
arguments, refusal, or terminal continuation fail closed. Stream text that cannot be encoded as
UTF-8 (for example a lone surrogate) fails closed as a typed `INVALID_PROVIDER_RESPONSE` or
`INVALID_TOOL_CALL` error with the raw SSE body preserved, never as an encoding crash. The
canonical `response.json` is built
only from the validated-parse tool arguments, and the v3.0 receipt binds the request, tool schema,
tool-call identity, raw/derived evidence hashes, usage, and cost.

After each physical call, preserve and validate its unmodified response together with the exact
provider receipt:

```bash
python -m prototypes.local_ranking.atomic_judge record-attempt \
  --manifest <atomic-preparation/private/manifest.json> \
  --call-sequence <1-24> \
  --attempt-number <1-4> \
  --response <transport-attempt/response.json> \
  --execution-receipt <transport-attempt/receipt.json> \
  --execution-result <transport-attempt/execution-result.json> \
  --output-root <new-call-attempt>
```

Only machine-detectable invalid output may receive attempts 2-4, using exact identical request bytes.
The resolver accepts the first valid response, rejects any retry after a valid response, expands
handles through the private manifest, and fails after four invalid attempts.

Schema versions are separated into two transport families. The legacy JSON-response family —
atomic preparations v2.2/v2.3, transport preparation v2.1, receipt v2.0, execution result v2.0,
attempts v2.3/v2.4 — stays replayable for read-only diagnostic validation. The forced-tool family
covers the current v2.5/v3.1 preparations and the spent v2.3 canary (atomic preparation v2.4,
transport preparation v3.0, identical request bytes without the `response_submission`
declaration); it uses receipt v3.0, execution result v2.1, and attempt v2.5. `execute-call` and
`run-smoke` issue only current v2.5/v3.1 preparations, and `record-attempt` requires the response,
receipt, execution result, and attempt to match the manifest's family; cross-family evidence fails
closed.

For a formal orientation, use the bounded runner instead of issuing calls manually. The runner
first requires both manifests to be current-family — atomic preparation v2.5 and transport
preparation v3.1, each declaring `response_submission: forced_submit_judgment_tool` — and refuses
legacy or canary manifests before reading any credential, creating output, or sending a request;
it is not a resume entry point for spent runs. It executes
at most four calls concurrently, records HTTP/SSE/non-JSON failures as spent physical attempts,
retries only invalid calls up to three times with identical request bytes, refuses to resend an ambiguous
partial attempt after interruption, and replays a completed run without new API calls:

```bash
python -m prototypes.local_ranking.atomic_runner \
  --atomic-manifest <atomic-preparation/private/manifest.json> \
  --preparation-root <atomic-transport-preparation> \
  --output-root <new-orientation-run> \
  --kimi-config <kimi-config-with-opencode-go-key>
```

Every physical execution writes an immutable `execution-result.json`; the attempt ledger copies
all referenced transport evidence. Provider failure, truncation, or malformed JSON therefore
counts toward the same four-attempt ceiling instead of silently disappearing before retry.
After interruption, a complete execution result can rebuild its missing ledger without another
request; evidence that ends before the execution result remains ambiguous and fails closed.

The lower-level resolver remains available for replay and audit:

```bash
python -m prototypes.local_ranking.atomic_judge resolve-orientation \
  --manifest <atomic-preparation/private/manifest.json> \
  --attempt <call-attempt-1/attempt.json> \
  --attempt <call-attempt-2/attempt.json> \
  --output-root <new-resolved-orientation>
```

Supply every attempt from all 24 calls; `--attempt` is repeated 24-96 times. Once three fresh
mirror pairs are complete, aggregate their six resolved traces with:

```bash
python -m prototypes.local_ranking.atomic_calibration \
  --replicate r1 <r1-o1-trace> <r1-o2-trace> \
  --replicate r2 <r2-o1-trace> <r2-o2-trace> \
  --replicate r3 <r3-o1-trace> <r3-o2-trace> \
  --output <new-atomic-calibration-result.json>
```

Atomic v2 keeps only the direct gates: every replicate at least 22/24 mirror-stable, pooled at
least 69/72, and no all-tie/all-both-bad replicate. The old “at least two replicates reach 23”
gate is omitted because the retained gates mathematically imply it. First-attempt validity and
retry rates are diagnostics, not additional admission thresholds. The local prototype does not
accept an attempt without an exact request/response/provider-receipt binding, and provider response
IDs must be unique across the six traces. Before semantic calls, use `prepare-smoke` and `run-smoke`
to prove the frozen concurrency against four transport-only probes; their answers never enter the
ranking gates. A single forced-tool synthetic probe (the v2.3 canary's first authorized call) uses
`prepare-smoke`, one `execute-call`, and then:

```bash
python -m prototypes.local_ranking.atomic_opencode_go validate-smoke-call \
  --preparation-root <smoke-transport-preparation> \
  --call-sequence <1-4> \
  --execution-root <single-smoke-execution>
```

`validate-smoke-call` verifies the full evidence chain before judging the probe: the smoke
preparation (v3.0 or v3.1) must rebuild to the recorded request bytes; the preserved
`response.json`, the v3.0 receipt, and the execution result must all be present (a response
without its receipt or result fails as `INCOMPLETE_SMOKE_EVIDENCE`); and the closed-schema receipt
must bind the preparation manifest, request hash, call binding, tool name plus tool-schema hash,
provider identity, finish reason, usage, cost, and stream diagnostics. The receipt must declare
exactly the seven raw and derived evidence files (`stream-body.sse`, `chunks.jsonl`,
`response.json`, `response-headers.json`, `http-status.txt`, `started-at.txt`, `finished-at.txt`)
and the result exactly those plus `receipt.json`, each hash-checked against the bytes on disk;
`usage` must be a valid non-empty object and `identity.cost` a finite non-negative decimal string,
so the call ledger is provably complete. The validator then replays `stream-body.sse` through the
frozen tool-stream extractor and requires the rebuilt arguments, chunks, identity, diagnostics,
and usage to match the stored evidence exactly. The closed-schema execution result must in turn bind
the receipt and the response. The probe is valid only when, on top of that chain, the executed
call's canonical `response.json` equals the exact prescribed `submit_judgment` arguments for that
smoke call. The bounded v2.3 canary then retries
the spent `pro-max-calibration-002/r1/o1/call-021` with identical request bytes (at most four
sequential attempts, first-valid stop) through `execute-call` plus `record-attempt`; every canary
output is `spent_transport_only` and never becomes a semantic vote. See
`docs/prototypes/local-ranking-atomic-evaluator-contract-v2.0.md`, the v2.2 bounded-retry
correction, and the v2.3 tool-output contract for the approved boundary.

Before the first semantic call, capture the authenticated quota state and freeze all six atomic
and transport manifests into one profile-level budget:

```bash
python -m prototypes.local_ranking.atomic_profile snapshot-usage \
  --output <new-usage-snapshot.json> \
  --kimi-config <kimi-config-with-opencode-go-key>

python -m prototypes.local_ranking.atomic_profile prepare \
  --source-commit <full-commit-sha> \
  --reasoning-effort <high-or-max> \
  --usage-snapshot <usage-snapshot.json> \
  --smoke-result-sha256 <transport-smoke-result-sha256> \
  --canary-summary <transport-canary-summary.json> \
  --replicate r1 <r1-o1-atomic> <r1-o1-prep> <r1-o2-atomic> <r1-o2-prep> \
  --replicate r2 <r2-o1-atomic> <r2-o1-prep> <r2-o2-atomic> <r2-o2-prep> \
  --replicate r3 <r3-o1-atomic> <r3-o1-prep> <r3-o2-atomic> <r3-o2-prep> \
  --output <new-profile-manifest.json>
```

The v2.2 profile manifest fails closed unless the canary summary matches the SHA-256 frozen in
code for the authorized v2.3 canary run (no caller-side override exists) and records
`spent_transport_only` evidence, a passing synthetic
probe, a first-valid stop on canary attempt 1, the approved model alias, and the canary
implementation commit — and unless all six orientations use current-family manifests (atomic
v2.5 plus transport v3.1, both declaring `response_submission`) that bind one Pro/high evaluator,
one frozen source per orientation, concurrency 4, the 16,384-token ceiling, and the exact bounded
retry policy. Its budget is 144 logical and at most 576 physical calls; early stop can reduce use
but cannot authorize additional calls.

After all four orientations pass, reduce them with:

```bash
python -m prototypes.local_ranking.operational_stats \
  --mapping <private-mapping.json> \
  --preparation-manifest <setwise-preparation-manifest.json> \
  --kimi-orientation-1 <validated-trace.json> \
  --kimi-orientation-2 <validated-trace.json> \
  --deepseek-orientation-1 <validated-trace.json> \
  --deepseek-orientation-2 <validated-trace.json> \
  --output <new-statistics-report.json>
```

The reducer uses 12 case-level paired observations, exact `2^12` sign-flip enumeration, a
fixed-seed case-cluster bootstrap, pre-registered E5 promotion gates, and diagnostic-only
fail-closed behavior for any non-operational or spent input.

The approved v1.2/v1.2.1 overlays replace Robert's exhaustive HTML labeling with isolated
synthetic topical qrels. The actual A/B runs used Kimi Code sessions, so freeze their
truthful provider/model profiles with:

```bash
python -m prototypes.local_ranking.ai_judge prepare \
  --formal-root <immutable-formal-input-attempt> \
  --base-protocol docs/prototypes/local-literature-ranking-comparison-protocol.md \
  --revision-protocol docs/prototypes/local-literature-ranking-comparison-protocol-v1.2.1.md \
  --judge-a-model kimi-k3 \
  --judge-a-provider kimi-code-harness \
  --judge-a-reasoning provider-managed-not-exposed \
  --judge-b-model deepseek-v4-flash \
  --judge-b-provider kimi-code-harness \
  --judge-b-reasoning provider-managed-not-exposed \
  --output-root <new-private-judge-bundle-attempt>
```

Each fresh projectless judge writes a draft against exactly one bundle. Convert it to a
canonical trace and qrels only through the fail-closed validator:

```bash
python -m prototypes.local_ranking.ai_judge finalize \
  --bundle <judge-bundle.json> \
  --draft <judge-draft.json> \
  --input <matching-formal-input.json> \
  --output-root <new-private-judge-result-attempt>
```

`prepare-adjudication` emits only the original items on which A/B grades or exact support
spans differ; it never exposes either prior label or rationale to judge C. The same
`finalize` command binds every adjudication item back to the frozen input and emits a
`local-ranking-adjudication-qrels-v1.0` partial evidence artifact. That artifact must never
be passed to a ranker as complete qrels.
`finalize-consensus` requires judge C to cover exactly that frozen dispute set and emits
the consensus trace/qrels. Development artifacts may be unsealed immediately. Holdout
drafts, traces, qrels, disagreement packet, and consensus remain in the projectless judge
tasks until finalists and every parameter are frozen.

`diagnose-agreement` emits deterministic A/B diagnostics: linear-weighted Cohen's kappa,
exact paper-grade agreement, the relevance-boundary `1<->2` rate, grade gaps of at least
two, grade distributions, and exact segment-support agreement when both judges call an
item relevant. These are diagnostics only; promotion still depends on the same ranker
direction under judge A, judge B, and consensus qrels.

If a completed external judge copied the original Codex profile from an earlier bundle,
`rebind` may correct provenance only under v1.2.1. It revalidates the source result, requires
the old/new bundles to have byte-identical inputs/rubric/items, preserves the qrels and full
judgment-semantic hash, records the attested execution-session hash, and never overwrites
the superseded artifact. A missing raw draft may be reconstructed only from its canonical
validated trace and is recorded as provenance degradation.

`fixtures/protocol.json` is a lexical/RRF diagnostic example. An attempt is immutable: running the same `comparison_id + attempt_id` twice fails instead of overwriting evidence. Copy the frozen protocol with a new `attempt_id` to perform another replay; do not edit an already-run attempt.

The harness:

- accepts a strict allowlist-only input schema, so forbidden corpus metadata cannot reach a scorer;
- verifies input/qrels/model hashes before scoring;
- runs non-fusion candidates in isolated child processes with offline flags;
- installs a Python socket deny guard in every measured worker and emits typed `NETWORK_ACCESS_DENIED` failures;
- verifies the frozen environment lock and records a hashable `environment.json` with package, model, and isolated-environment sizes;
- evaluates the approved resource gates directly, using a labeled conservative source-plus-fusion composition for RRF;
- emits candidate-scoped scores, canonical model payloads, hashes, metrics, failures, and resource observations under `artifacts/local-ranking-prototype/`;
- never downloads a model or falls back to another ranker;
- leaves the original qrels `winner` unset. v1.4 makes only the narrower, pre-registered
  setwise deployment decision after four validated tool-less evaluator orientations.

Formal development/holdout protocols must use Python 3.13.7, enable runtime measurement, reference a clean commit, include complete blinded qrels, and reference a hashed `environment_lock`. The tracked fixture may use a null lock and run on another Python only to test harness behavior; its numbers are not decision evidence.
