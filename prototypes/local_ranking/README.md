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
  --comparison-summary <windows-comparison-summary.json> \
  --baseline-candidate-id bm25-k16-b05-tw1-cap3 \
  --baseline-payloads <windows-bm25-payloads.jsonl> \
  --challenger-candidate-id e5-small-v2-tw1-cap3 \
  --challenger-payloads <windows-e5-payloads.jsonl> \
  --output-root <new-setwise-preparation-attempt>
```

The public bundles expose only query plus anonymous left/right evidence. The private mapping
binds the exact formal manifest, input, selection, protocol, candidate payloads, resource
gates, and side assignments. `tool-less-agent.md` disables tools and subagents. Do not start
the four paid evaluator sessions until exact prompt sizes, model context support, invocation
count, and the one-whole-orientation retry ceiling have separate budget approval.

Validate each raw evaluator JSON without repair:

```bash
python -m prototypes.local_ranking.operational_judge finalize \
  --bundle <matching-public-bundle.json> \
  --draft <raw-evaluator-draft.json> \
  --output-root <new-immutable-evaluator-result>
```

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
