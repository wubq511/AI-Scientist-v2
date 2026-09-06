# Target Paper → Workshop File semantics

Research date: 2026-08-28

Scope: ideation input semantics only. No model was run, and no BFTS, experiment, plotting, write-up, or review stage was entered.

## Bottom line

1. **[Confirmed] In IdeaBench, the Target Paper is primarily a held-out answer and evaluation comparator, plus a routing key for selecting its references.** The benchmark's idea generator receives reference-paper abstracts, not the Target Paper's title, abstract, or `abstract_summary`. The generated ideas are compared against the Target Paper only afterwards. ([IdeaBench paper, Methodology](https://arxiv.org/html/2411.02429); [official generation code at inspected commit](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_hypotheses.py#L77-L139))
2. **[Confirmed] The interview task adds a requirement that is not part of the published IdeaBench generation protocol:** use each Target Paper to create an AI Scientist `Workshop File` (a topic description). ([task email](../task/%E9%9D%A2%E8%AF%95%E9%82%80%E8%AF%B7%E5%8F%8A%E4%BB%BB%E5%8A%A1%E8%AF%B4%E6%98%8Eemail.md); [AI Scientist-v2 topic-description instructions](../../README.md#generate-research-ideas))
3. **[Inference] The only defensible adaptation is a non-answer-bearing topic projection.** A Workshop File may expose the broad domain, research object, pre-existing problem or gap, importance, and neutral scope. It must not disclose the Target Paper's method, intervention, mechanism, experimental design, findings, conclusion, or identifying metadata.
4. **[Confirmed] `abstract_summary` is especially unsafe for Workshop generation.** IdeaBench creates it by asking GPT-4o to restate the Target Paper's main research idea and findings “as if” proposing the idea; the official evaluator then uses that field as the ground truth. ([official summary-generation code](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_summaries.py#L22-L40); [official ranking code](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/evaluation/llm_ranking_eval.py#L121-L146))
5. **[Unknown] No official source found defines a Target Paper → Workshop File transformation, leakage threshold, or approved field-by-field template.** Any such contract in this project is therefore an explicit recruiter-specific design choice, not an IdeaBench reproduction claim.

## Evidence labels

- **Confirmed**: directly stated or mechanically demonstrated by a primary source or the provided files.
- **Inference**: the narrowest design conclusion supported by the confirmed facts; it is not claimed as an official protocol.
- **Unknown**: not specified by the task, benchmark paper, official benchmark repository, AI Scientist paper/repository, or provided dataset inspected here.

## Source hierarchy and identity

The sources answer different questions and should not be conflated:

1. The [interview task email](../task/%E9%9D%A2%E8%AF%95%E9%82%80%E8%AF%B7%E5%8F%8A%E4%BB%BB%E5%8A%A1%E8%AF%B4%E6%98%8Eemail.md) is authoritative for the requested adaptation: Target Paper → Workshop File and target-scoped reference access.
2. The published IdeaBench paper is the primary source for benchmark semantics: [KDD 2025 DOI](https://doi.org/10.1145/3711896.3737419) and the accessible [author manuscript](https://arxiv.org/html/2411.02429).
3. The authors' [official IdeaBench repository](https://github.com/amir-hassan25/IdeaBench/tree/9dbd125f2e72987a852a26afa3abd018bf518049) is the primary executable specification inspected here, frozen at commit `9dbd125f2e72987a852a26afa3abd018bf518049`.
4. The [Nature AI Scientist paper](https://www.nature.com/articles/s41586-026-10265-5) and [official AI Scientist-v2 repository](https://github.com/SakanaAI/AI-Scientist-v2) define the role and shape of a high-level workshop/topic description, but not a Target Paper decontamination protocol.
5. The current local files are the primary source for the actual interview subset: [`target_papers.csv`](../../data/raw/target_papers.csv), [`filtered_references.csv`](../../data/raw/filtered_references.csv), and [`ideabench_clustering.json`](../../data/raw/ideabench_clustering.json).

## 1. Role of the Target Paper

### Published IdeaBench semantics

- **[Confirmed] Ground-truth source.** IdeaBench calls the selected 2024 papers “target papers” because their ground-truth research ideas lie in them. Reference papers are collected to supply the background from which new ideas are generated. ([paper, Dataset Construction](https://arxiv.org/html/2411.02429))
- **[Confirmed] Held-out comparison target.** The paper says the Target Paper's abstract encapsulates the human researchers' primary idea, while reference abstracts contain ideas considered during its formulation. The generator is prompted with the reference abstracts; generated ideas are later compared with the target idea. ([paper, Research Idea Generation](https://arxiv.org/html/2411.02429))
- **[Confirmed] Corpus-routing key.** In the official implementation, `paperId` is read from each target row and used to select rows whose `targetPaperId` matches; only the selected reference `abstract` values are formatted into the generation prompt. No other Target Paper field is included in that prompt. ([generation code lines 77–139](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_hypotheses.py#L77-L139); [lines 153–178](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_hypotheses.py#L153-L178))
- **[Confirmed] Evaluation anchor, not a unique correct answer.** The target idea is ranked together with generated ideas for user-chosen qualities such as novelty and feasibility. The paper explicitly says a generated idea can be better than the target and that the target is not guaranteed to be the most novel idea obtainable from its references. ([paper, Relative Quality Scoring and Different-q Scenarios](https://arxiv.org/html/2411.02429))
- **[Confirmed] Leakage control in the published experiment.** The paper selected 2024 targets and tested models whose stated training cutoffs were before 2024, specifically to reduce training-data leakage. ([paper, Models](https://arxiv.org/html/2411.02429))

### Consequence for this task

- **[Inference] The Target Paper must be treated as a sealed answer-bearing artifact during Ideation Run execution.** Its permitted pre-run role is to route the case and derive a deliberately lossy topic description; its full content may be used only in a separately isolated evaluation/validation step after the idea is finalized.
- **[Inference] “Generate a Workshop File from the Target Paper” cannot mean “summarize the Target Paper.”** A normal summary preserves the answer that IdeaBench holds out. The required operation is closer to projecting a paper back to the problem space that existed before its contribution.

## 2. What an AI Scientist Workshop File means

- **[Confirmed] AI Scientist-v2 expects a high-level topic description**, with sections such as `Title`, `Keywords`, `TL;DR`, and `Abstract`, to define the area or theme the model should explore. ([repository instructions](../../README.md#generate-research-ideas); [provided example](../../ai_scientist/ideas/i_cant_believe_its_not_better.md))
- **[Confirmed] The Nature paper describes ideation as growing high-level directions and hypotheses within a user-specified research subfield.** For the workshop submission, the system was prompted with the workshop's broad theme. ([Nature, “Generating manuscripts” and “Human evaluation results”](https://www.nature.com/articles/s41586-026-10265-5))
- **[Confirmed] AI Scientist-v2 does not define Workshop File as a paper summary.** Its official instructions describe it as a research area, theme, or broad workshop topic. ([official repository, Generate Research Ideas](https://github.com/SakanaAI/AI-Scientist-v2#generate-research-ideas))
- **[Unknown] Neither AI Scientist-v2 nor IdeaBench specifies how to derive that topic description from a held-out target paper.** The transformation required here is bespoke to the interview task.

## 3. Proposed model-visible Workshop contract

Everything in this section is **[Inference]**, not an official benchmark rule. It is the minimum adaptation that satisfies both the recruiter requirement and IdeaBench's held-out-target semantics.

| Workshop element | Safe content | Unsafe content |
|---|---|---|
| `Title` | A generic problem-area title | The Target Paper's exact title; a named target-created method, system, instrument, material, or claimed result |
| `Keywords` | Established domain, phenomenon, population, object, task, or broad measurement family | Target-specific acronym/name; unique combination that effectively identifies the paper; result direction |
| `TL;DR` | One open question or unmet need, phrased without an answer | “Use X to achieve Y”; the target hypothesis, mechanism, or conclusion |
| `Abstract` | Pre-existing background; why the problem matters; unresolved limitations; neutral scope; several admissible families of investigation | Target method/intervention; implementation recipe; experimental groups; target-only dataset/setup; findings, numbers, effect direction, claimed mechanism, conclusion, or application demonstrated by the target |
| Provenance | Keep `paperId`, DOI, exact title, hashes, and source spans in a non-model-visible manifest | Putting identifiers or provenance text into the Workshop/prompt where the model can recall or look up the Target Paper |

### Content that may be extracted, conditionally

- Broad research domain and subdomain.
- Research object, population, system, or phenomenon under study.
- A pre-existing need, limitation, or knowledge gap.
- Why resolving that problem matters.
- Neutral constraints that define the problem but do not encode the target solution.
- General evaluation dimensions already conventional in the field, only when they do not reveal the Target Paper's chosen experiment or outcome.

The condition is important: a statement is safe only if it describes the **question space** and remains compatible with multiple materially different ideas. If it points to the Target Paper's particular answer, it is not safe merely because it appears in a “background” sentence.

### Content that should never be model-visible during ideation

1. Exact Target Paper title, `paperId`, DOI, authors, venue, or a link that enables retrieval of the target.
2. Full Target Paper abstract or a close paraphrase.
3. `abstract_summary`. The official generator that created this field was explicitly prompted to capture the main idea and high-level findings as a proposed hypothesis. ([source](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_summaries.py#L22-L40))
4. The new method, algorithm, architecture, instrument, compound/material design, intervention, workflow, or named system introduced by the Target Paper.
5. The target hypothesis when it includes the proposed causal mechanism or intervention.
6. Experimental design choices that operationalize the target contribution: treatment/control construction, unique datasets, selected endpoints, parameterization, or target-specific evaluation recipe.
7. Result direction, effect size, numerical result, demonstrated capability, mechanism claim, or conclusion.
8. Target-authored citation `contexts`. Although stored on reference rows, these snippets are text from the Target Paper around its citations. The official IdeaBench generator passes reference abstracts, not `contexts`, to the model. ([reference retrieval schema](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/retrieve_references.py); [generation code](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/generation/generate_hypotheses.py#L77-L139))

## 4. Operational leakage tests

These are **[Inference]** validation rules suggested by the source semantics.

### A. Answer-bearing content test

Reject a Workshop if it states or strongly implies any of:

- what the Target Paper built, changed, applied, or discovered;
- how the Target Paper tested it;
- what happened in the test;
- why the authors say the method works;
- the paper's final recommendation or demonstrated application.

### B. Counterfactual breadth test

Ask whether at least several substantively different research ideas could answer the Workshop's question. If the natural completion is essentially the Target Paper's method, the Workshop is too narrow.

### C. Identification test

Remove exact identifiers, named target contributions, distinctive result phrases, and target-specific number/entity combinations. If a model could locate or recall one paper from the Workshop alone, treat it as contaminated.

### D. Source-span test

Every Workshop statement should retain a private provenance span and a classification such as `background`, `problem`, `significance`, or `scope`. Spans classified as `method`, `result`, `conclusion`, or `target_hypothesis` must fail closed. Classification itself is not enough: copied target-authored “background” can still contain an answer-bearing gap-to-solution transition.

### E. Evaluation separation test

The component that builds prompts must not be able to read the held-out target fields used for evaluation. The evaluator may receive them only after final output is immutable. This prevents both direct prompt leakage and accidental reuse through mutable state.

## 5. Why leakage invalidates the intended evaluation

- **[Confirmed] IdeaBench measures semantic similarity and idea overlap against the Target Paper, and ranks the target idea against generated ideas for novelty and feasibility.** ([paper, Baseline Comparison Metrics and Insight Score](https://arxiv.org/html/2411.02429); [official evaluator](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/evaluation/evaluate_hypotheses.py#L25-L60))
- **[Inference] If the Workshop contains the target contribution, high target overlap no longer demonstrates recovery or synthesis from the reference context; it demonstrates copying or paraphrasing an answer supplied in the prompt.** Novelty and feasibility comparisons also cease to measure the intended capability because the “held-out” comparator was exposed.
- **[Inference] A recruiter-specific Workshop means this project is not a strict reproduction of the published IdeaBench generation protocol.** Results should be described as an AI Scientist adaptation over an IdeaBench subset, with explicit leakage controls, rather than as directly comparable official Insight Scores unless the evaluator and inputs are separately reproduced and reported.

## 6. Current local dataset audit

The following are **[Confirmed]** by deterministic inspection of the provided files on 2026-08-28; no external metadata completion was performed.

| Artifact | SHA-256 | Observed facts |
|---|---|---|
| [`target_papers.csv`](../../data/raw/target_papers.csv) | `ba71dc35e1209ff0e51a440dea1d3ba96dfa5a92a2af2e472313a1b79240b96c` | 237 rows; every paper is dated 2024; no missing title, abstract, or `abstract_summary` |
| [`filtered_references.csv`](../../data/raw/filtered_references.csv) | `afaa733c6cddac1b0d31c240189cc3dd73b449dc7b99cb9ddc0cd8a4847930a6` | 2,296 target-reference pairs for all 237 targets; 3–36 rows per target; 2,288 unique reference IDs; 18 missing venues but no missing titles or abstracts |
| [`ideabench_clustering.json`](../../data/raw/ideabench_clustering.json) | `ce67a168545067130f8892554a5453cde7a37073e583b8d09ea6fbbc21a4f423` | Exactly one of eight broad category assignments for each of the 237 local targets |

Additional provenance checks:

- All 237 local Target Paper IDs occur in the official repository's full `target_papers.csv`; their titles, `abstract_summary` values, and whitespace-normalized abstracts match the official rows.
- All 2,296 local `(targetPaperId, paperId)` pairs occur in the official filtered-reference file at inspected commit `9dbd125f2e72987a852a26afa3abd018bf518049`.
- Every local reference row has a non-empty `contexts` field. Most are tagged `background`, but some mixed tags also include `methodology` and/or `result`. Those target-authored snippets are therefore unsafe as hidden substitutes for the held-out Target Paper.
- The local `abstract_summary` values are evaluation answers, not Workshop candidates. The first local record alone illustrates the issue: its summary preserves the introduced technique, its application, and the finding direction rather than only the open nanoplastics-measurement problem. The same risk follows mechanically from the official summary prompt, which requests the main idea and findings.

The official filtering rules explain the reference subset: references require abstracts and publication types, at least five citations, exclusion of several non-primary types, a non-empty citation intent that is not solely result or solely methodology, and at least three retained references for a target. ([official filtering code](https://github.com/amir-hassan25/IdeaBench/blob/9dbd125f2e72987a852a26afa3abd018bf518049/src/dataset/filter_references.py#L12-L48))

## 7. Confirmed protocol versus project policy

| Question | Answer |
|---|---|
| Is Target Paper content an official IdeaBench generation input? | **Confirmed: no.** Only its ID routes to reference abstracts in the released generator. |
| Is the Target Paper the benchmark's held-out human idea source? | **Confirmed: yes.** |
| Is `abstract_summary` a neutral topic summary? | **Confirmed: no.** It is an evaluation-oriented restatement of target idea and findings. |
| Does AI Scientist require a topic/workshop description? | **Confirmed: yes.** |
| Does an official Target → Workshop algorithm exist? | **Unknown.** None was found in the inspected primary sources. |
| Should the Workshop expose only problem-space information? | **Inference: yes.** This is the narrowest contract compatible with both systems. |
| May the evaluator later read the Target Paper? | **Inference: yes, but only after generation and through a separate, auditable boundary.** |

## 8. Remaining unknowns for later decision tickets

1. **Required fidelity to IdeaBench evaluation.** The task asks to generate ideas from the provided dataset but does not explicitly require reproduction of BERTScore, idea-overlap ratings, or Insight Score.
2. **DeepSeek training contamination.** The original paper relied on pre-2024 model cutoffs. Whether `DeepSeek-V4-Pro-0813` was trained on these 2024 targets is not established here; Workshop decontamination cannot eliminate parametric memorization.
3. **Acceptable topic specificity.** No official threshold says how narrow a target-derived problem statement may be before it becomes answer-bearing. Canary review and explicit leakage tests are needed.
4. **Whether the eight-category clustering is intended as model input.** It is safe-looking, broad metadata and covers all local targets, but no task or benchmark source says it must appear in the Workshop.
5. **Evaluation access boundary.** The exact artifact layout that prevents the generator from reading target answer fields remains a system-design decision.
6. **External metadata completion.** The task permits public metadata completion when fields are missing, but it does not say whether target full text may be fetched for Workshop derivation. Fetching more target content increases the leakage surface and should require a separate decision.

## Recommended decision statement

**[Inference] Define Workshop File as a lossy, model-visible projection of a Target Paper's problem space, with `Title`, `Keywords`, `TL;DR`, and `Abstract`; keep the exact Target Paper and its identifiers in a private provenance/evaluation artifact. Reject any Workshop that contains or identifies the Target Paper's answer. Never seed it from `abstract_summary`, never expose target-authored citation `contexts`, and do not let evaluation-only target fields become readable until the final idea output has been frozen.**
