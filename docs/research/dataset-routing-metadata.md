# IdeaBench dataset routing metadata

Research date: 2026-08-28

Scope: semantics of target `strategy`, the eight clusters, and reference-edge `contexts`, `intents`, and `isInfluential`. Sources are limited to the official IdeaBench paper, repository/code/data at inspected commit `9dbd125f2e72987a852a26afa3abd018bf518049`, and the provided local files. No model or downstream stage was run.

## Bottom line

| Field/artifact | Confirmed source and role | Official generation input? | Leakage classification |
|---|---|---:|---|
| Target `strategy` | Target-collection provenance: `1` means the top-venue retrieval path; `2` means the any-venue, Medicine/Biology, at-least-20-citations path | No | Not target-authored content; safe as internal provenance, but unnecessary in prompts |
| Eight clusters | A mapping from broad category name to Target Paper IDs, consumed by the official notebook for category-specific result analysis | No | Broad metadata, not answer text; prompt use is unsupported and could narrow/identify a case |
| Reference `contexts` | Citation-edge text returned while retrieving one Target Paper's references; local values are snippets from the Target Paper around citations | No | **Direct Target-authored leakage surface; never expose to ideation** |
| Reference `intents` | Citation-edge labels such as `background`, `methodology`, and `result`; used by the official reference-filtering step | No | Target-derived structural metadata; suitable for filtering/audit, not model context |
| Reference `isInfluential` | Boolean copied from the reference edge and stored in the CSV | No | Exact semantics and intended use are undocumented by IdeaBench; do not use as a gate |

The only official generation-time fields from the reference table are `targetPaperId` for case routing and the matched reference `abstract` values for prompt content. The released generator does not read `strategy`, cluster labels, `contexts`, `intents`, or `isInfluential`. ([official generator](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_hypotheses.py#L77-L139))

## Evidence labels

- **Confirmed**: stated or mechanically demonstrated by the official paper/code/data or current local files.
- **Inference**: the narrowest operational conclusion supported by confirmed facts.
- **Unknown**: not documented in the allowed primary sources.

## 1. Target `strategy`

### Confirmed semantics

The official target builder makes two Semantic Scholar bulk searches and writes the numeric argument passed to `retrieve_papers` into a `strategy` column. ([official target builder](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/get_target_papers.py#L15-L41))

- **Strategy `1`: top-venue path.** It searches a hard-coded venue list for the requested year, requires at least one citation, and sorts by citation count. The code comment says the venues were chosen from Google Scholar. ([lines 44–60](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/get_target_papers.py#L44-L60))
- **Strategy `2`: citation-threshold path.** It searches any venue for the requested year, restricts `fieldsOfStudy` to `Medicine,Biology`, requires at least 20 citations, and sorts by citation count. ([lines 62–71](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/get_target_papers.py#L62-L71))
- The two result frames are concatenated in `1`-then-`2` order and deduplicated by `paperId` with `keep='first'`; a paper selected by both therefore retains strategy `1`. Several non-primary publication types are then removed. ([lines 73–85](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/get_target_papers.py#L73-L85))
- This matches the paper's prose: targets come either from selected top biomedical venues with at least one citation or from other venues with at least 20 citations. ([IdeaBench, Data Collection](https://arxiv.org/html/2411.02429))

In the local [`target_papers.csv`](../../data/raw/target_papers.csv), 229 of 237 targets have `strategy=1` and 8 have `strategy=2`.

### Classification

- **Confirmed: dataset-construction provenance.** No official generation or evaluation code branches on `strategy`.
- **Inference: not a runtime “routing strategy.”** Its name is easy to misread; it records how the target entered the dataset, not how its references should be retrieved or how an Ideation Run should execute.
- **Unknown:** the paper/code does not define whether strategy should be used for stratified evaluation, canary selection, weighting, or quality ranking. Any such use would be project policy.

## 2. The eight clusters

### Confirmed shape and use

The official [`ideabench_clustering.json`](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/data/dataset/ideabench_clustering.json) is a JSON object whose keys are eight broad labels and whose values are lists of Target Paper IDs:

1. `Health & Medicine`
2. `Genetics & Molecular Biology`
3. `Environmental Sciences`
4. `Neuroscience & Cognitive Sciences`
5. `Technology & Engineering`
6. `Social & Behavioral Sciences`
7. `Materials Science`
8. `Public Health & Policy`

At the inspected official commit, the mapping contains all 2,374 official target IDs exactly once. The local [`ideabench_clustering.json`](../../data/raw/ideabench_clustering.json) contains all 237 local target IDs exactly once, and every local assignment matches the official full mapping.

| Cluster | Official targets | Local targets |
|---|---:|---:|
| Health & Medicine | 764 | 76 |
| Genetics & Molecular Biology | 760 | 76 |
| Environmental Sciences | 123 | 12 |
| Neuroscience & Cognitive Sciences | 248 | 25 |
| Technology & Engineering | 114 | 11 |
| Social & Behavioral Sciences | 181 | 18 |
| Materials Science | 55 | 6 |
| Public Health & Policy | 129 | 13 |

The official README directs users to `data/idea_bench_topic_specific_results.ipynb` for “Category-Specific Results.” ([README](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/README.md#L43-L49)) The [official notebook](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/data/idea_bench_topic_specific_results.ipynb) loads the JSON, selects already evaluated result rows whose `paperId` appears in each list, and computes per-cluster BERTScore, LLM-rating, novelty, and feasibility summaries.

Repository history reinforces that purpose but does not explain construction: the JSON first appears in the official commit named [`Different categories of papers`](https://github.com/amir-hassan25/IdeaBench/commit/e00969da78d93350bc7701a2714c54377da23fa8), followed by the analysis notebook in [`Add files via upload`](https://github.com/amir-hassan25/IdeaBench/commit/70dcecd4201d83a465384852e29e5b521070d5cd).

### Classification

- **Confirmed: evaluation/reporting metadata.** The released pipeline does not use cluster labels to select references or build generation prompts.
- **Inference: valid for coverage stratification.** A later project could use them to choose cross-domain canaries or report grouped failure rates, while retaining the target-level route as authoritative.
- **Unknown: assignment provenance.** No clustering script, classifier, prompt, taxonomy definition, confidence, multi-label policy, or human-review procedure appears in the official paper/repository. The JSON is the only executable truth.
- **Unknown: semantic precision.** Labels are called both clusters and categories in official artifacts; there is no claim that they are learned clusters, fields-of-study labels, mutually exclusive natural-science disciplines, or suitable topic prompts.
- **Inference: do not treat a cluster label as the Workshop File.** It is too broad to satisfy target-derived topic preparation, while concatenating it into the model prompt is not part of the official protocol.

## 3. Reference-edge metadata model

The reference table mixes two different kinds of data:

- **Reference-paper node data:** `paperId`, `externalIds`, `title`, `abstract`, `venue`, `year`, `citationCount`, `publicationTypes`.
- **Target → Reference citation-edge data:** `targetPaperId`, `contexts`, `intents`, `isInfluential`.

This distinction is confirmed by the official retriever: for each target ID it calls `/paper/{target_paper_id}/references`; it copies `contexts`, `intents`, and `isInfluential` from the returned reference edge, while copying bibliographic fields from its nested `citedPaper`. ([official reference retriever](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/retrieve_references.py#L27-L53))

The local data provides a useful integrity check: 8 reference `paperId` values each occur under two different targets. All 8 have different `contexts`, and 3 also have different `intents`; there are no duplicate `(targetPaperId, paperId)` pairs. Therefore edge metadata must be keyed by the pair, not globally by reference `paperId`.

## 4. `contexts`

### Confirmed semantics

- The field is requested from the per-target references endpoint and copied from the reference relationship, not from `citedPaper`. ([retrieval code](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/retrieve_references.py#L31-L51))
- Local values are lists of citation-bearing sentences or snippets with citation markers and target-specific framing. They are distinct from the cited reference's `abstract` stored later in the same row.
- Every one of the 2,296 local rows has at least one context; lists range from 1 to 21 snippets.
- Official reference filtering does not inspect `contexts`, and official idea generation does not pass them to the prompt. ([filter code](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/filter_references.py#L12-L40); [generator](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_hypotheses.py#L77-L139))

### Classification

- **Inference, strongly supported by the edge structure and local text: direct Target-authored leakage surface.** These snippets reveal how the Target Paper frames, combines, or interprets its references and can include method/result statements from the target.
- They may be preserved privately for provenance, audit, or diagnosing the supplied filtering, but must not become Workshop content, retriever result text, query-generation context, reflection context, or model-visible logs.
- **Unknown:** IdeaBench does not document the extraction window, completeness, ordering, truncation, section attribution, or reliability of `contexts`.

## 5. `intents`

### Confirmed semantics and use

- `intents` is also copied from the Target → Reference edge. Local values are lists drawn from `background`, `methodology`, and `result`.
- The paper's third reference-filtering criterion is “Background Section Relevance”: exclude references not cited in the background section. ([paper, Relevance and Significance Based Reference Filtering](https://arxiv.org/html/2411.02429))
- The released implementation operationalizes that criterion by dropping exactly three serialized values: `[]`, `['result']`, and `['methodology']` are excluded; any other non-empty serialized list is retained. ([official filter](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/filter_references.py#L30-L38))
- `intents` is not included in the generation prompt. It is dataset-construction filtering metadata only.

The 2,296 local filtered rows have these order-insensitive intent sets:

| Intent set | Rows |
|---|---:|
| `{background}` | 2,000 |
| `{background, methodology}` | 145 |
| `{background, result}` | 99 |
| `{background, methodology, result}` | 37 |
| `{methodology, result}` | 15 |

### Important paper/code mismatch

- **Confirmed:** 15 retained local rows have no `background` label at all. They survive because the implementation excludes only a sole `['result']` or sole `['methodology']`; mixed `['result', 'methodology']` in either order is not excluded.
- **Inference:** “filtered references” therefore does not prove “every reference was cited in background.” A project validator should report the actual intent sets and must not silently upgrade the code's behavior to the paper's stronger prose claim.
- **Unknown:** IdeaBench does not document how intent labels were assigned, their accuracy/confidence, whether order matters, or whether mixed labels correspond to multiple citation sites versus one multi-purpose citation.

### Leakage classification

The low-cardinality labels do not contain Target prose, but they are derived from where/how the Target cites a reference. Keep them as private filtering and audit metadata. Passing them to the model is unnecessary and unsupported by the official generator; it can also reveal which references the Target authors considered background or methodological/result support.

## 6. `isInfluential`

### Confirmed facts

- The official retriever requests `isInfluential` from the per-target reference relationship, defaults it to `False` when absent, and stores it. ([retrieval code lines 27–51](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/retrieve_references.py#L27-L51))
- The local filtered file contains 285 `True` and 2,011 `False` values.
- Repository-wide official code usage stops at retrieval/storage: reference filtering, generation, evaluation, and category analysis do not consume the field.
- The paper's “significance-relevancy” filter lists citation count, publication type, and background relevance; it does not name `isInfluential` as a criterion. ([paper](https://arxiv.org/html/2411.02429); [filter implementation](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/filter_references.py#L12-L40))

### Classification

- **Unknown:** the allowed IdeaBench sources do not define what `True` means, how the upstream service computes it, its confidence, stability, or intended benchmark use.
- **Inference:** do not reinterpret it as “ground-truth important,” “safe,” “background,” or “must retrieve.” It is opaque edge metadata and should not control corpus membership, rank, or prompt content without a separately sourced decision.

## 7. Authoritative routing and exposure contract

Everything in this section is **Inference** from the confirmed official behavior.

1. The authoritative case route is `Target.paperId == Reference.targetPaperId`.
2. Corpus membership must be represented at the `(targetPaperId, reference paperId)` edge, even when the same reference appears for multiple targets.
3. Reference `abstract` is eligible model-visible paper content after the target-pair boundary is proven.
4. `strategy` remains target acquisition provenance.
5. Cluster remains post-hoc evaluation/coverage metadata.
6. `intents` remains filter provenance and a validation signal; report discrepancies rather than inventing corrected semantics.
7. `contexts` remains private Target-derived evidence and must be excluded from all ideation prompts and retriever responses.
8. `isInfluential` remains opaque, unused metadata.

## 8. Unknowns requiring later decisions

1. Whether the project should preserve the provided filtered set exactly or enforce the paper's stricter “must include background” prose and thereby exclude the 15 mixed methodology/result rows.
2. Whether cluster labels may be used for canary sampling and aggregate reporting; their assignment process and reliability are undocumented.
3. Whether `strategy` should be retained only for provenance or also used for stratified validation.
4. Whether `contexts` should be retained in a highly restricted raw-data/audit artifact or omitted entirely from normalized runtime data.
5. Whether a primary upstream definition of `isInfluential` and citation-intent labeling should be researched before deciding to use either beyond reproducing the supplied filter.
6. Whether the normalized schema should preserve every original edge field while exposing only an allowlisted model view; the official CSV itself does not define this separation.

## Recommended decision statement

**Treat only `(targetPaperId, reference paperId)` as the corpus-routing identity and only the matched reference's own paper content as retrievable model input. Preserve `strategy`, cluster, `intents`, and `isInfluential` as non-model-visible provenance/evaluation metadata; treat `contexts` as quarantined Target-authored evidence. Do not use cluster or `isInfluential` for retrieval, and explicitly decide whether to reproduce or tighten the official intent-filter mismatch.**
