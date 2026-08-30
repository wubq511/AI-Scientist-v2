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

Prepare the pinned dense model in previously unused repository-relative paths before entering offline mode:

```bash
python -m prototypes.local_ranking.prepare_model \
  --artifact-dir <model-files-directory> \
  --manifest <sibling-model-manifest.json>
```

The preparation command downloads only the six allowlisted files from the approved E5 commit, verifies the frozen weight size/SHA-256 and model-size gate, writes a closed manifest, and never overwrites an earlier attempt. A failed partial directory is evidence and must not be reused.

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
- leaves `winner` unset. Human approval after development and blind holdout remains mandatory.

Formal development/holdout protocols must use Python 3.13.7, enable runtime measurement, reference a clean commit, include complete blinded qrels, and reference a hashed `environment_lock`. The tracked fixture may use a null lock and run on another Python only to test harness behavior; its numbers are not decision evidence.
